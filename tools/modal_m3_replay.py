#!/usr/bin/env python3
"""Parallel Modal runner for the protected M3 offline replay matrix.

The remote side receives only the replay executable and the corpus files that
participate in accuracy gates.  REAPER, the VST3 bundle, the audio device, and
live deadline/validator checks intentionally remain local.

Set M3_PHYSICAL_RECORDINGS when the original recordings are outside
build/physical-capture/source-recordings.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import time
from typing import Any

import modal


APP_NAME = "m3-protected-replay"
VOLUME_NAME = "m3-protected-replay-data"
MOUNT_ROOT = Path("/mnt/m3")
REPO_ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_ROOT = Path(
    os.environ.get(
        "M3_PHYSICAL_RECORDINGS",
        str(REPO_ROOT / "build/physical-capture/source-recordings"),
    )
)
REPLAY_BINARY = REPO_ROOT / "build/contributor/m3_replay"

CORPUS_FILES: dict[str, Path] = {
    "calibration.m3cb": REPO_ROOT
    / "build/physical-capture/unison-spectral-shadow/factory-current-20261012/factory-calibration-v2.m3cb",
    "templates.tsv": Path(
        os.environ.get(
            "M3_SPECTRAL_TEMPLATES",
            REPO_ROOT
            / "build/physical-capture/unison-spectral-shadow/final-review-fixes/blended-template-bank.tsv",
        )
    ),
    "ordinary.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.wav",
    "ordinary.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv",
    "constructed.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.wav",
    "constructed.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.tsv",
    "isolated-08.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.wav",
    "isolated-08.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.tsv",
    "isolated-05.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.wav",
    "isolated-05.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.tsv",
    "isolated-02.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.wav",
    "isolated-02.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.tsv",
    "physical-long.wav": PHYSICAL_ROOT
    / "string8-fret8_string7-fret4_string6-open_unison.wav",
    "physical-long.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06/unison-labels.tsv",
    "physical-middle.wav": PHYSICAL_ROOT
    / "string3-open_string4-fret4_string5-fret8.wav",
    "physical-middle.tsv": REPO_ROOT
    / "build/physical-capture/unison-05-04-03/unison-labels.tsv",
    "physical-highmid.wav": PHYSICAL_ROOT
    / "string2-open_string3-fret4_string4-fret8.wav",
    "physical-highmid.tsv": REPO_ROOT
    / "build/physical-capture/unison-04-03-02/unison-labels.tsv",
    "physical-high.wav": PHYSICAL_ROOT
    / "string1-open_strin2-fret4_string3-fret8.wav",
    "physical-high.tsv": REPO_ROOT
    / "build/physical-capture/unison-03-02-01/unison-labels.tsv",
    "extended-middle.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.wav",
    "extended-middle.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.tsv",
    "extended-highmid.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.wav",
    "extended-highmid.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.tsv",
    "extended-high.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.wav",
    "extended-high.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.tsv",
    "physical-four.wav": PHYSICAL_ROOT
    / "string4-open_string5-fret4_string6-fret8_string7-fret12_string8-fret16.wav",
    "physical-four.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06-05-04/diagnostic-spans.tsv",
    "synthetic-four.wav": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.wav",
    "synthetic-four.tsv": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.tsv",
}

DATASETS = {
    name: {"wav": f"corpus/{name}.wav", "labels": f"corpus/{name}.tsv"}
    for name in (
        "ordinary",
        "constructed",
        "isolated-08",
        "isolated-05",
        "isolated-02",
        "physical-long",
        "physical-middle",
        "physical-highmid",
        "physical-high",
        "extended-middle",
        "extended-highmid",
        "extended-high",
        "physical-four",
        "synthetic-four",
    )
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_aggregate(tsv: str) -> dict[str, Any]:
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t")
    try:
        row = next(rows)
    except StopIteration as error:
        raise ValueError("replay produced no aggregate row") from error
    integer_fields = (
        "labeled",
        "matched",
        "false_gap_voices",
        "false_wrong_note_voices",
        "false_wrong_string_voices",
        "false_positive_voices",
        "transitions",
        "transitions_inside_holds",
        "transitions_in_gaps",
        "cents_observations",
        "joint_pitch_valid_frames",
        "joint_pitch_invalid_frames",
        "dp_replacement_matched",
        "dp_replacement_false_positive",
        "dp_replacement_false_gap",
        "dp_replacement_false_wrong_note",
        "dp_replacement_false_wrong_string",
        "dp_replacement_changed",
    )
    result: dict[str, Any] = {"fingerprint": row["fingerprint"]}
    for field in integer_fields:
        result[field] = int(row[field])
    for field in ("cents_mean_error", "cents_sd", "cents_p95_abs",
                  "joint_pitch_mean_residual"):
        result[field] = float(row[field])
    result["fine_mask_complexity_penalties"] = [
        float(value) for value in row["fine_mask_complexity_penalties"].split(",")
    ]
    for field in (
        "fine_mask_complexity_matched",
        "fine_mask_complexity_false_positive",
        "fine_mask_complexity_false_gap",
        "fine_mask_complexity_false_wrong_note",
        "fine_mask_complexity_false_wrong_string",
        "fine_mask_complexity_changed",
    ):
        result[field] = [int(value) for value in row[field].split(",")]
    for field in (
        "correlation_shadow_ratio",
        "correlation_shadow_age_seconds",
        "correlation_shadow_fundamental_only",
        "correlation_shadow_protect_pending_unison",
        "joint_pitch_thresholds",
        "joint_pitch_overlap_limits",
    ):
        result[field] = [float(value) for value in row[field].split(",")]
    for field in (
        "correlation_shadow_matched",
        "correlation_shadow_false_positive",
        "correlation_shadow_false_gap",
        "correlation_shadow_false_wrong_note",
        "correlation_shadow_false_wrong_string",
        "correlation_shadow_changed",
        "joint_pitch_matched",
        "joint_pitch_false_positive",
        "joint_pitch_false_gap",
        "joint_pitch_false_wrong_note",
        "joint_pitch_false_wrong_string",
        "joint_pitch_changed",
    ):
        result[field] = [int(value) for value in row[field].split(",")]
    # Keep the compact causal tables beside the scores so a remote diagnostic
    # run does not require downloading its much larger per-label TSV. Preserve
    # the exported encodings and sparse cell identifiers for later analysis.
    result["physical_group_diagnostics"] = {
        field: value
        for field, value in row.items()
        if field.startswith("physical_group_")
    }
    return result


app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("libstdc++6")
    .pip_install("numpy<3")
    .add_local_file(REPLAY_BINARY, "/opt/m3/m3_replay", copy=True)
    .run_commands("chmod 0755 /opt/m3/m3_replay")
)


def _read_float_wave(path: Path) -> tuple[int, Any]:
    import numpy as np

    contents = path.read_bytes()
    if contents[:4] != b"RIFF" or contents[8:12] != b"WAVE":
        raise ValueError(f"not a RIFF/WAVE file: {path}")
    position = 12
    format_fields: tuple[int, int, int, int] | None = None
    payload: bytes | None = None
    while position + 8 <= len(contents):
        chunk_id, chunk_size = struct.unpack_from("<4sI", contents, position)
        position += 8
        chunk = contents[position : position + chunk_size]
        position += chunk_size + (chunk_size & 1)
        if chunk_id == b"fmt " and len(chunk) >= 16:
            audio_format, channels, rate, _, _, bits = struct.unpack_from(
                "<HHIIHH", chunk
            )
            format_fields = audio_format, channels, rate, bits
        elif chunk_id == b"data":
            payload = chunk
    if format_fields is None or payload is None:
        raise ValueError(f"missing WAVE format or data: {path}")
    audio_format, channels, rate, bits = format_fields
    if audio_format != 3 or channels != 1 or bits != 32:
        raise ValueError(f"expected mono float32 WAVE: {path}")
    return rate, np.frombuffer(payload, dtype="<f4").copy()


def _write_float_wave(path: Path, rate: int, samples: Any) -> None:
    import numpy as np

    payload = np.asarray(samples, dtype="<f4").tobytes()
    format_chunk = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(format_chunk))
        + format_chunk
        + b"data"
        + struct.pack("<I", len(payload))
        + payload
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def _extend_remote_hold(samples: Any, target: int, rate: int) -> Any:
    import numpy as np

    if samples.shape[0] >= target:
        return samples[:target].copy()
    sustain = samples[
        int(round(samples.shape[0] * 0.35)) :
        int(round(samples.shape[0] * 0.85))
    ]
    if sustain.shape[0] < int(round(0.40 * rate)):
        raise ValueError("recorded hold has no bounded sustain region")
    crossfade = int(round(0.020 * rate))
    result = samples.copy()
    phase = np.linspace(0.0, np.pi / 2.0, crossfade, endpoint=False)
    fade_out = np.cos(phase)
    fade_in = np.sin(phase)
    while result.shape[0] < target:
        overlap = (
            result[-crossfade:] * fade_out + sustain[:crossfade] * fade_in
        ).astype(samples.dtype, copy=False)
        result = np.concatenate(
            (result[:-crossfade], overlap, sustain[crossfade:])
        ).astype(samples.dtype, copy=False)
    return result[:target]


@app.function(
    image=image,
    volumes={str(MOUNT_ROOT): volume},
    cpu=2.0,
    memory=4096,
    timeout=900,
)
def build_extended_upper_hold(name: str) -> dict[str, Any]:
    import numpy as np

    source_wave = MOUNT_ROOT / "corpus" / f"physical-{name}.wav"
    source_labels = MOUNT_ROOT / "corpus" / f"physical-{name}.tsv"
    output_wave = MOUNT_ROOT / "corpus" / f"extended-{name}.wav"
    output_labels = MOUNT_ROOT / "corpus" / f"extended-{name}.tsv"
    rate, samples = _read_float_wave(source_wave)
    with source_labels.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    target = int(round(3.60 * rate))
    minimum = int(round(1.50 * rate))
    silence_count = int(round(0.25 * rate))
    silence = np.zeros(silence_count, dtype=np.float32)
    output_parts = [silence]
    output_rows: list[dict[str, int]] = []
    cursor = silence_count
    for row in rows:
        start = int(row["start_sample"])
        end = int(row["end_sample"])
        if end - start < minimum:
            continue
        extended = _extend_remote_hold(samples[start:end], target, rate)
        output_rows.append(
            {
                "start_sample": cursor,
                "end_sample": cursor + target,
                "midi_note": int(row["midi_note"]),
                "string_mask": int(row["string_mask"]),
            }
        )
        output_parts.extend((extended, silence))
        cursor += target + silence_count
    if not output_rows:
        raise ValueError(f"no long holds in {name}")
    _write_float_wave(output_wave, rate, np.concatenate(output_parts))
    with output_labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=("start_sample", "end_sample", "midi_note", "string_mask"),
        )
        writer.writeheader()
        writer.writerows(output_rows)
    volume.commit()
    return {"dataset": name, "holds": len(output_rows), "rate": rate}


@app.local_entrypoint()
def build_extended_upper() -> None:
    results = list(
        build_extended_upper_hold.map(
            ("middle", "highmid", "high"), order_outputs=True
        )
    )
    print(json.dumps(results, sort_keys=True))


@app.function(
    image=image,
    volumes={str(MOUNT_ROOT): volume},
    cpu=2.0,
    memory=2048,
    max_containers=128,
    nonpreemptible=True,
    timeout=3600,
)
def run_replay(job: dict[str, Any]) -> dict[str, Any]:
    dataset = DATASETS[job["dataset"]]
    output_relative = Path("results") / job["run_id"] / (
        f"{job['dataset']}-b{job['block']}-m{job['selector_margin']}"
        f"-s{job['selector_mask']}-dr{job['dp_similarity']}"
        f"-{job['dp_calibration_margin']}-{job['dp_score_margin']}"
        f"-dm{job['dp_replacement_mask']}"
        f"-pm{job['production_dp_mask']}-fm{int(job['fine_mask_pruning'])}"
        f"-fb{int(job['fine_beat_pruning'])}"
        f"-fc{int(job['collecting_fine_history_carry'])}"
        f"-cw{job.get('correlation_seconds', -1.0)}"
        f"-so{int(job.get('selection_window_only', False))}"
        f"-cs{int(job.get('correlation_shadow_only', False))}"
        f"-jp{int(job.get('joint_pitch_residual', False))}"
        f"-t{job['input_trim']}"
        f"-se{job['sensitivity']}-r{job['response']}"
        f"-p{job['max_polyphony']}-f{job['max_fret']}.tsv"
    )
    output_path = MOUNT_ROOT / output_relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "/opt/m3/m3_replay",
        "--wav",
        str(MOUNT_ROOT / dataset["wav"]),
        "--labels",
        str(MOUNT_ROOT / dataset["labels"]),
        "--calibration",
        str(MOUNT_ROOT / "corpus/calibration.m3cb"),
        "--block",
        str(job["block"]),
        "--a4",
        "440",
        "--input-trim",
        str(job["input_trim"]),
        "--sensitivity",
        str(job["sensitivity"]),
        "--response",
        str(job["response"]),
        "--max-polyphony",
        str(job["max_polyphony"]),
        "--max-fret",
        str(job["max_fret"]),
    ]
    if bool(job.get("label_details", False)):
        command += [
            "--label-details",
            "--spectral-shadow-templates",
            str(MOUNT_ROOT / "corpus/templates.tsv"),
        ]
    selector_margin = float(job["selector_margin"])
    if selector_margin >= 0.0:
        command += [
            "--diagnostic-calibrated-selector-margin",
            f"{selector_margin:.9g}",
            "--diagnostic-calibrated-selector-string-mask",
            str(int(job["selector_mask"])),
        ]
    if float(job["dp_similarity"]) >= 0.0:
        command += [
            "--diagnostic-dp-replacement-similarity",
            f"{float(job['dp_similarity']):.9g}",
            "--diagnostic-dp-replacement-calibration-margin",
            f"{float(job['dp_calibration_margin']):.9g}",
            "--diagnostic-dp-replacement-score-margin",
            f"{float(job['dp_score_margin']):.9g}",
            "--diagnostic-dp-replacement-string-mask",
            str(int(job["dp_replacement_mask"])),
        ]
    command += [
        "--diagnostic-production-dp-replacement-string-mask",
        str(int(job["production_dp_mask"])),
    ]
    if bool(job.get("fine_mask_pruning", False)):
        command.append("--diagnostic-fine-mask-pruning")
    if bool(job.get("fine_beat_pruning", False)):
        command.append("--diagnostic-fine-beat-pruning")
    if bool(job.get("collecting_fine_history_carry", False)):
        command.append("--diagnostic-collecting-fine-history-carry")
    if float(job.get("correlation_seconds", -1.0)) != -1.0:
        command += [
            "--diagnostic-correlation-seconds",
            f"{float(job['correlation_seconds']):.9g}",
        ]
    if bool(job.get("selection_window_only", False)):
        command.append("--diagnostic-selection-window-only")
    if bool(job.get("correlation_shadow_only", False)):
        command.append("--diagnostic-correlation-shadow-only")
    if bool(job.get("joint_pitch_residual", False)):
        command.append("--diagnostic-joint-pitch-residual")
    started = time.monotonic()
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        timeout=3500,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"m3_replay failed ({completed.returncode}): "
            f"{completed.stderr[-2000:]}"
        )
    if bool(job.get("persist_tsv", False)):
        output_path.write_text(completed.stdout, encoding="utf-8")
        volume.commit()
    result = _parse_aggregate(completed.stdout)
    result.update(
        {
            "dataset": job["dataset"],
            "block": int(job["block"]),
            "selector_margin": selector_margin,
            "selector_mask": int(job["selector_mask"]),
            "dp_similarity": float(job["dp_similarity"]),
            "dp_calibration_margin": float(job["dp_calibration_margin"]),
            "dp_score_margin": float(job["dp_score_margin"]),
            "dp_replacement_mask": int(job["dp_replacement_mask"]),
            "production_dp_mask": int(job["production_dp_mask"]),
            "fine_mask_pruning": bool(job["fine_mask_pruning"]),
            "fine_beat_pruning": bool(job["fine_beat_pruning"]),
            "collecting_fine_history_carry": bool(
                job["collecting_fine_history_carry"]
            ),
            "input_trim": float(job["input_trim"]),
            "correlation_seconds": float(job.get("correlation_seconds", -1.0)),
            "selection_window_only": bool(job.get("selection_window_only", False)),
            "correlation_shadow_only": bool(job.get("correlation_shadow_only", False)),
            "joint_pitch_residual": bool(job.get("joint_pitch_residual", False)),
            "sensitivity": int(job["sensitivity"]),
            "response": int(job["response"]),
            "max_polyphony": int(job["max_polyphony"]),
            "max_fret": int(job["max_fret"]),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "result_path": (
                str(output_relative) if bool(job.get("persist_tsv", False)) else ""
            ),
            "binary_sha256": job["binary_sha256"],
        }
    )
    return result


@app.local_entrypoint()
def sync_corpus() -> None:
    missing = [str(path) for path in CORPUS_FILES.values() if not path.is_file()]
    if missing:
        raise SystemExit("missing protected corpus files:\n" + "\n".join(missing))
    if not REPLAY_BINARY.is_file() or REPLAY_BINARY.stat().st_size == 0:
        raise SystemExit(f"missing replay executable: {REPLAY_BINARY}")
    manifest: dict[str, dict[str, Any]] = {}
    with volume.batch_upload(force=True) as batch:
        for remote_name, local_path in CORPUS_FILES.items():
            batch.put_file(local_path, f"/corpus/{remote_name}")
            manifest[remote_name] = {
                "bytes": local_path.stat().st_size,
                "sha256": _sha256(local_path),
            }
        batch.put_file(
            io.BytesIO(
                json.dumps(
                    manifest, sort_keys=True, separators=(",", ":")
                ).encode()
            ),
            "/corpus/manifest.json",
        )
    print(
        json.dumps(
            {
                "volume": VOLUME_NAME,
                "files": len(manifest),
                "bytes": sum(item["bytes"] for item in manifest.values()),
            },
            sort_keys=True,
        )
    )


@app.local_entrypoint()
def sweep(
    datasets: str = "ordinary,physical-long",
    blocks: str = "512",
    selector_margins: str = "-1,0.02",
    selector_masks: str = "255",
    dp_similarities: str = "-1",
    dp_calibration_margins: str = "-1",
    dp_score_margins: str = "-1",
    dp_replacement_masks: str = "255",
    production_dp_masks: str = "56",
    fine_mask_pruning: bool = False,
    fine_beat_pruning: bool = False,
    collecting_fine_history_carry: bool = False,
    correlation_seconds: str = "-1",
    selection_window_only: bool = False,
    correlation_shadow_only: bool = False,
    joint_pitch_residual: bool = False,
    input_trims: str = "-9",
    sensitivities: str = "60",
    responses: str = "75",
    max_polyphonies: str = "5",
    max_frets: str = "24",
    label_details: bool = False,
    persist_tsv: bool = False,
    tag: str = "manual",
    output: str = "build/modal/m3-replay-results.json",
) -> None:
    dataset_names = [value.strip() for value in datasets.split(",") if value.strip()]
    unknown = sorted(set(dataset_names) - set(DATASETS))
    if unknown:
        raise SystemExit(f"unknown datasets: {','.join(unknown)}")
    block_sizes = [int(value) for value in blocks.split(",")]
    if any(value <= 0 or value > 4096 for value in block_sizes):
        raise SystemExit("blocks must be in 1..4096")
    margins = [float(value) for value in selector_margins.split(",")]
    if any(value < -1.0 or value > 1.0 for value in margins):
        raise SystemExit("selector margins must be -1 or in 0..1")
    masks = [int(value) for value in selector_masks.split(",")]
    if any(value <= 0 or value > 255 for value in masks):
        raise SystemExit("selector masks must be in 1..255")
    similarities = [float(value) for value in dp_similarities.split(",")]
    calibration_margins = [
        float(value) for value in dp_calibration_margins.split(",")
    ]
    score_margins = [float(value) for value in dp_score_margins.split(",")]
    replacement_masks = [int(value) for value in dp_replacement_masks.split(",")]
    production_masks = [int(value) for value in production_dp_masks.split(",")]
    correlation_windows = [float(value) for value in correlation_seconds.split(",")]
    if any(
        not math.isfinite(value)
        or (value != -1.0 and not 0.020 <= value <= 0.200)
        for value in correlation_windows
    ):
        raise SystemExit("correlation seconds must be -1 or in 0.020..0.200")
    if (selection_window_only or correlation_shadow_only) and any(
        value < 0.0 for value in correlation_windows
    ):
        raise SystemExit("secondary windows require an explicit duration")
    if selection_window_only and correlation_shadow_only:
        raise SystemExit("selection-only and shadow-only modes are exclusive")
    if joint_pitch_residual and any(value != -1.0 for value in correlation_windows):
        raise SystemExit("joint pitch residual requires the production window")
    trims = [float(value) for value in input_trims.split(",")]
    sensitivity_values = [int(value) for value in sensitivities.split(",")]
    response_values = [int(value) for value in responses.split(",")]
    polyphony_values = [int(value) for value in max_polyphonies.split(",")]
    fret_values = [int(value) for value in max_frets.split(",")]
    if any(value < -1.0 or value > 1.0 for value in similarities):
        raise SystemExit("DP similarities must be -1 or in 0..1")
    if any(value < -1.0 or value > 1.0 for value in calibration_margins):
        raise SystemExit("DP calibration margins must be -1 or in 0..1")
    if any(value < -1.0 or value > 10.0 for value in score_margins):
        raise SystemExit("DP score margins must be -1 or in 0..10")
    if any(value <= 0 or value > 255 for value in replacement_masks):
        raise SystemExit("DP replacement masks must be in 1..255")
    if any(value < 0 or value > 255 for value in production_masks):
        raise SystemExit("production DP masks must be in 0..255")
    if any(value < -24.0 or value > 24.0 for value in trims):
        raise SystemExit("input trims must be in -24..24")
    if any(value < 0 or value > 100 for value in sensitivity_values):
        raise SystemExit("sensitivities must be in 0..100")
    if any(value < 0 or value > 100 for value in response_values):
        raise SystemExit("responses must be in 0..100")
    if any(value < 1 or value > 8 for value in polyphony_values):
        raise SystemExit("max polyphonies must be in 1..8")
    if any(value < 0 or value > 36 for value in fret_values):
        raise SystemExit("max frets must be in 0..36")
    dp_disabled = (
        similarities == [-1.0]
        and calibration_margins == [-1.0]
        and score_margins == [-1.0]
    )
    if not dp_disabled and (
        any(value < 0.0 for value in similarities)
        or any(value < 0.0 for value in calibration_margins)
        or any(value < 0.0 for value in score_margins)
    ):
        raise SystemExit("DP replacement requires all three nonnegative knobs")
    binary_sha256 = _sha256(REPLAY_BINARY)
    run_id = f"{tag}-{int(time.time())}-{binary_sha256[:12]}"
    jobs = [
        {
            "dataset": dataset,
            "block": block,
            "selector_margin": margin,
            "selector_mask": mask,
            "label_details": label_details,
            "persist_tsv": persist_tsv or label_details,
            "dp_similarity": similarity,
            "dp_calibration_margin": calibration_margin,
            "dp_score_margin": score_margin,
            "dp_replacement_mask": replacement_mask,
            "production_dp_mask": production_mask,
            "fine_mask_pruning": fine_mask_pruning,
            "fine_beat_pruning": fine_beat_pruning,
            "collecting_fine_history_carry": collecting_fine_history_carry,
            "correlation_seconds": correlation_window,
            "selection_window_only": selection_window_only,
            "correlation_shadow_only": correlation_shadow_only,
            "joint_pitch_residual": joint_pitch_residual,
            "input_trim": input_trim,
            "sensitivity": sensitivity,
            "response": response,
            "max_polyphony": max_polyphony,
            "max_fret": max_fret,
            "run_id": run_id,
            "binary_sha256": binary_sha256,
        }
        for dataset in dataset_names
        for block in block_sizes
        for margin in margins
        for mask in masks
        for similarity in similarities
        for calibration_margin in calibration_margins
        for score_margin in score_margins
        for replacement_mask in replacement_masks
        for production_mask in production_masks
        for correlation_window in correlation_windows
        for input_trim in trims
        for sensitivity in sensitivity_values
        for response in response_values
        for max_polyphony in polyphony_values
        for max_fret in fret_values
    ]
    results = list(run_replay.map(jobs, order_outputs=True, return_exceptions=True))
    failures = [repr(value) for value in results if isinstance(value, BaseException)]
    if failures:
        raise SystemExit("remote replay failures:\n" + "\n".join(failures))
    report = {
        "run_id": run_id,
        "binary_sha256": binary_sha256,
        "results": results,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "binary_sha256": binary_sha256,
                "jobs": len(results),
                "output": str(output_path),
            },
            sort_keys=True,
        )
    )
