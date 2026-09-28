#!/usr/bin/env python3
"""Create REAPER render projects for the labeled pitch-correction corpus.

REAPER's native elastique 3 Pro mode performs the actual pitch/formant work.
This tool only writes deterministic projects and labels; it does not launch
REAPER, touch audio hardware, or modify the source recordings.
"""

from __future__ import annotations

import argparse
import json
import math
import mmap
import pathlib
import shutil
import struct
import uuid


ELASTIQUE_3_PRO = 9 << 16
FLOAT_WAVE_RENDER_CONFIG = "ZXZhdxgAAQ=="
PITCH_PREROLL_SECONDS = 0.2
FORMANT_SUBMODE_BY_PHYSICAL_STRING = {
    8: 1,  # Preserve Formants (Lowest Pitches)
    7: 2,  # Preserve Formants (Lower Pitches)
    6: 3,  # Preserve Formants (Low Pitches)
    5: 4,  # Preserve Formants (Most Pitches)
    4: 4,
    3: 5,  # Preserve Formants (High Pitches)
    2: 6,  # Preserve Formants (Higher Pitches)
    1: 7,  # Preserve Formants (Highest Pitches)
}


def _validate_variant(variant: str) -> None:
    if not variant or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in variant
    ):
        raise ValueError("variant must be a lowercase filename token")


def _read_label_spans(path: pathlib.Path) -> list[tuple[int, int]]:
    lines = pathlib.Path(path).read_text(encoding="ascii").splitlines()
    expected = (
        "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass"
    )
    if not lines or lines[0] != expected:
        raise ValueError("labels require the five-column replay header")
    spans = []
    previous_end = 0
    for line in lines[1:]:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 5:
            raise ValueError("invalid replay label")
        start, end = int(fields[0]), int(fields[1])
        if start < previous_end or end <= start:
            raise ValueError("label spans must be ordered and disjoint")
        spans.append((start, end))
        previous_end = end
    if not spans:
        raise ValueError("empty replay label file")
    return spans


def _pcm24_data_chunk(path: pathlib.Path) -> tuple[int, int, int]:
    with pathlib.Path(path).open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise ValueError("not a RIFF/WAVE file")
        wave_format = None
        data_chunk = None
        while chunk_header := stream.read(8):
            if len(chunk_header) != 8:
                raise ValueError("truncated WAV chunk header")
            chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
            chunk_offset = stream.tell()
            if chunk_id == b"fmt ":
                payload = stream.read(chunk_size)
                if len(payload) < 16:
                    raise ValueError("short WAV format chunk")
                wave_format = struct.unpack_from("<HHIIHH", payload)
            else:
                if chunk_id == b"data":
                    if data_chunk is not None:
                        raise ValueError("multiple WAV data chunks")
                    data_chunk = (chunk_offset, chunk_size)
                stream.seek(chunk_size, 1)
            if chunk_size & 1:
                stream.seek(1, 1)
        if wave_format is None or data_chunk is None:
            raise ValueError("WAV is missing format or data")
        encoding, channels, sample_rate, _, block_align, bits = wave_format
        if (encoding, channels, block_align, bits) != (1, 1, 3, 24):
            raise ValueError("expected mono PCM24 WAV")
        if data_chunk[1] % block_align:
            raise ValueError("unaligned WAV data")
        return data_chunk[0], data_chunk[1] // block_align, sample_rate


def silence_unlabeled_regions(
    wave_path: pathlib.Path, labels_path: pathlib.Path
) -> int:
    """Restore detector reset gaps after REAPER's audible analysis preroll."""
    wave_path = pathlib.Path(wave_path)
    data_offset, sample_count, _ = _pcm24_data_chunk(wave_path)
    spans = _read_label_spans(labels_path)
    if spans[-1][1] > sample_count:
        raise ValueError("label exceeds rendered WAV")
    gaps = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = end
    if cursor < sample_count:
        gaps.append((cursor, sample_count))
    zero_block = b"\0" * (1024 * 1024)
    with wave_path.open("r+b") as stream:
        with mmap.mmap(stream.fileno(), 0) as image:
            for start, end in gaps:
                byte_start = data_offset + start * 3
                byte_end = data_offset + end * 3
                while byte_start < byte_end:
                    size = min(len(zero_block), byte_end - byte_start)
                    image[byte_start : byte_start + size] = zero_block[:size]
                    byte_start += size
            image.flush()
    return sample_count


def finalize_renders(
    output_directory: pathlib.Path, variant: str
) -> list[pathlib.Path]:
    _validate_variant(variant)
    output_directory = pathlib.Path(output_directory)
    rendered = []
    for labels_path in sorted(output_directory.glob("string-??.tsv")):
        stem = labels_path.stem
        wave_path = output_directory / f"{stem}-{variant}.wav"
        if not wave_path.is_file():
            raise ValueError(f"missing rendered WAV: {wave_path}")
        silence_unlabeled_regions(wave_path, labels_path)
        rendered.append(wave_path)
    if not rendered:
        raise ValueError("no rendered strings found")
    return rendered


def _guid(seed: str) -> str:
    value = uuid.uuid5(uuid.NAMESPACE_URL, "m3-reaper-corpus:" + seed)
    return "{" + str(value).upper() + "}"


def _quote(value: pathlib.Path | str) -> str:
    text = str(value).replace("\\", "/").replace('"', '\\"')
    return f'"{text}"'


def _item_chunk(
    *,
    seed: str,
    source: pathlib.Path,
    position_seconds: float,
    length_seconds: float,
    source_offset_seconds: float,
    pitch_semitones: float,
    pitch_mode: int,
    volume: float = 1.0,
) -> str:
    return f"""    <ITEM
      POSITION {position_seconds:.12f}
      SNAPOFFS 0
      LENGTH {length_seconds:.12f}
      LOOP 0
      ALLTAKES 0
      FADEIN 1 0 0 1 0 0 0
      FADEOUT 1 0 0 1 0 0 0
      MUTE 0 0
      SEL 0
      IGUID {_guid(seed + ':item')}
      IID 1
      NAME ""
      VOLPAN {volume:.9f} 0 1 -1
      SOFFS {source_offset_seconds:.12f} 0
      PLAYRATE 1 1 {pitch_semitones:.12f} {pitch_mode} 0 0.0025
      CHANMODE 0
      GUID {_guid(seed + ':take')}
      <SOURCE WAVE
        FILE {_quote(source.resolve())}
      >
    >"""


def build_reaper_project(
    manifest: dict[str, object],
    output_wave: pathlib.Path,
    correction_fraction: float = 1.0,
) -> str:
    if (
        not math.isfinite(correction_fraction)
        or not 0.0 <= correction_fraction <= 1.0
    ):
        raise ValueError("correction fraction must be in 0..1")
    sample_rate = int(manifest["sample_rate_hz"])
    source = pathlib.Path(str(manifest["source_wave"]))
    silence_frames = int(manifest["silence_frames_between_holds"])
    observations = list(manifest["observations"])
    output_sample_count = int(manifest["output_sample_count"])
    physical_string = int(manifest["physical_string_number"])
    pitch_mode = ELASTIQUE_3_PRO + FORMANT_SUBMODE_BY_PHYSICAL_STRING[
        physical_string
    ]
    chunks = []
    cursor = silence_frames
    for observation in observations:
        start = int(observation["source_start_sample"])
        end = int(observation["source_end_sample"])
        target = float(observation["target_hz"])
        measured = float(observation["measured_hz"])
        pitch = correction_fraction * 12.0 * math.log2(target / measured)
        pre_roll = min(
            int(round(PITCH_PREROLL_SECONDS * sample_rate)), start, cursor
        )
        chunks.append(
            _item_chunk(
                seed=f"{manifest['physical_string_number']}:{observation['label_index']}",
                source=source,
                position_seconds=(cursor - pre_roll) / sample_rate,
                length_seconds=(end - start + pre_roll) / sample_rate,
                source_offset_seconds=(start - pre_roll) / sample_rate,
                pitch_semitones=pitch,
                pitch_mode=pitch_mode,
            )
        )
        cursor += end - start + silence_frames
    # A silent tail item forces the render to the exact same sample count as
    # the raw compact corpus without manufacturing a second audio source.
    chunks.append(
        _item_chunk(
            seed=f"{manifest['physical_string_number']}:tail",
            source=source,
            position_seconds=(output_sample_count - silence_frames) / sample_rate,
            length_seconds=silence_frames / sample_rate,
            source_offset_seconds=0.0,
            pitch_semitones=0.0,
            pitch_mode=pitch_mode,
            volume=0.0,
        )
    )
    track_guid = _guid(f"{manifest['physical_string_number']}:track")
    items = "\n".join(chunks)
    return f"""<REAPER_PROJECT 0.1 "7.79/linux-x86_64" 0 0
  RIPPLE 0 0
  GROUPOVERRIDE 0 0 0 0
  AUTOXFADE 0
  ENVATTACH 3
  POOLEDENVATTACH 0
  PEAKGAIN 1
  FEEDBACK 0
  PANLAW 1
  PROJOFFS 0 0 0
  MAXPROJLEN 0 0
  GRID 3199 8 1 8 1 0 0 0
  TIMEMODE 1 5 -1 30 0 0 -1 0
  LOOP 0
  RENDER_FILE {_quote(output_wave.resolve())}
  RENDER_FMT 0 1 {sample_rate}
  RENDER_1X 0
  RENDER_RANGE 1 0 0 0 1000
  RENDER_RESAMPLE 10 0 1
  RENDER_ADDTOPROJ 0
  RENDER_STEMS 0
  RENDER_DITHER 0
  ITEMMIX 0
  DEFPITCHMODE {pitch_mode} 0
  SAMPLERATE {sample_rate} 1 0
  <RENDER_CFG
    {FLOAT_WAVE_RENDER_CONFIG}
  >
  TEMPO 120 4 4 0
  PLAYRATE 1 0 0.25 4
  MASTER_NCH 1 1
  MASTER_VOLUME 1 0 -1 -1 1
  <TRACK {track_guid}
    NAME "M3 corrected string {manifest['physical_string_number']}"
    PEAKCOL 16576
    BEAT -1
    AUTOMODE 0
    VOLPAN 1 0 -1 -1 1
    MUTESOLO 0 0 0
    IPHASE 0
    PLAYOFFS 0 1
    ISBUS 0 0
    BUSCOMP 0 0 0 0 0
    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0
    SEL 0
    REC 0 0 1 0 0 0 0 0
    VU 64
    NCHAN 1
    FX 1
    TRACKID {track_guid}
    PERF 0
    MIDIOUT -1 -1
    MAINSEND 1 0
{items}
  >
>
"""


def prepare_projects(
    source_directory: pathlib.Path,
    output_directory: pathlib.Path,
    correction_fraction: float = 1.0,
    variant: str = "corrected",
) -> list[pathlib.Path]:
    _validate_variant(variant)
    source_directory = pathlib.Path(source_directory)
    output_directory = pathlib.Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    projects = []
    for manifest_path in sorted(source_directory.glob("string-??-manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        physical = int(manifest["physical_string_number"])
        stem = f"string-{physical:02d}"
        labels_source = source_directory / str(manifest["labels"])
        labels_target = output_directory / f"{stem}.tsv"
        shutil.copyfile(labels_source, labels_target)
        output_wave = output_directory / f"{stem}-{variant}.wav"
        project = output_directory / f"{stem}.RPP"
        project.write_text(
            build_reaper_project(manifest, output_wave, correction_fraction),
            encoding="utf-8",
        )
        projects.append(project)
    if not projects:
        raise ValueError("no string manifests found")
    return projects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--correction-fraction", type=float, default=1.0)
    parser.add_argument("--variant", default="corrected")
    parser.add_argument("--finalize-renders", action="store_true")
    args = parser.parse_args()
    if args.finalize_renders:
        for rendered in finalize_renders(args.output, args.variant):
            print(rendered)
        return 0
    for project in prepare_projects(
        args.source,
        args.output,
        correction_fraction=args.correction_fraction,
        variant=args.variant,
    ):
        print(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
