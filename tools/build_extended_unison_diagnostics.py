#!/usr/bin/env python3
"""Build replay-only long-hold diagnostics from recorded unison clips.

The physical upper-unison labels top out below the detector's accepted
three-second fine-frequency evidence window.  This tool preserves each long
recorded attack, then repeats a central sustain region with short equal-power
crossfades.  The result is diagnostic evidence only: it is never used for
training, factory calibration, production defaults, or a release gate.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.io import wavfile


def _read_labels(path: Path) -> list[dict[str, int]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        return [
            {
                "start_sample": int(row["start_sample"]),
                "end_sample": int(row["end_sample"]),
                "midi_note": int(row["midi_note"]),
                "string_mask": int(row["string_mask"]),
            }
            for row in rows
        ]


def _append_crossfade(
    output: np.ndarray, addition: np.ndarray, crossfade: int
) -> np.ndarray:
    count = min(crossfade, output.shape[0], addition.shape[0])
    if count == 0:
        return np.concatenate((output, addition))
    phase = np.linspace(0.0, np.pi / 2.0, count, endpoint=False)
    fade_out = np.cos(phase)[:, None] if output.ndim == 2 else np.cos(phase)
    fade_in = np.sin(phase)[:, None] if output.ndim == 2 else np.sin(phase)
    overlap = (output[-count:] * fade_out + addition[:count] * fade_in).astype(
        output.dtype, copy=False
    )
    return np.concatenate((output[:-count], overlap, addition[count:])).astype(
        output.dtype, copy=False
    )


def _extend_hold(
    segment: np.ndarray, sample_rate: int, target_samples: int
) -> np.ndarray:
    if segment.shape[0] >= target_samples:
        return segment[:target_samples].copy()
    sustain_start = int(round(segment.shape[0] * 0.35))
    sustain_end = int(round(segment.shape[0] * 0.85))
    sustain = segment[sustain_start:sustain_end]
    minimum_sustain = int(round(0.40 * sample_rate))
    if sustain.shape[0] < minimum_sustain:
        raise ValueError("recorded hold has no bounded sustain region")
    result = segment.copy()
    crossfade = int(round(0.020 * sample_rate))
    while result.shape[0] < target_samples:
        result = _append_crossfade(result, sustain, crossfade)
    return result[:target_samples]


def build(
    source_wav: Path,
    source_labels: Path,
    output_wav: Path,
    output_labels: Path,
    target_seconds: float,
    minimum_source_seconds: float,
) -> None:
    sample_rate, samples = wavfile.read(source_wav)
    if sample_rate <= 0 or samples.ndim not in (1, 2):
        raise ValueError("unsupported source wave")
    if not np.issubdtype(samples.dtype, np.floating):
        samples = samples.astype(np.float32) / float(
            max(abs(np.iinfo(samples.dtype).min), np.iinfo(samples.dtype).max)
        )
    else:
        samples = samples.astype(np.float32, copy=False)

    labels = _read_labels(source_labels)
    target_samples = int(round(target_seconds * sample_rate))
    minimum_source_samples = int(round(minimum_source_seconds * sample_rate))
    silence_samples = int(round(0.25 * sample_rate))
    silence_shape = (silence_samples,) + samples.shape[1:]
    silence = np.zeros(silence_shape, dtype=np.float32)

    output_parts: list[np.ndarray] = [silence]
    output_rows: list[dict[str, int]] = []
    cursor = silence_samples
    for row in labels:
        source_count = row["end_sample"] - row["start_sample"]
        if source_count < minimum_source_samples:
            continue
        segment = samples[row["start_sample"] : row["end_sample"]]
        extended = _extend_hold(segment, sample_rate, target_samples)
        start = cursor
        end = start + extended.shape[0]
        output_rows.append(
            {
                "start_sample": start,
                "end_sample": end,
                "midi_note": row["midi_note"],
                "string_mask": row["string_mask"],
            }
        )
        output_parts.extend((extended, silence))
        cursor = end + silence_samples

    if not output_rows:
        raise ValueError("no source labels cleared the minimum hold duration")
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    output_labels.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(output_wav, sample_rate, np.concatenate(output_parts))
    with output_labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=("start_sample", "end_sample", "midi_note", "string_mask"),
        )
        writer.writeheader()
        writer.writerows(output_rows)
    print(
        f"{output_wav}: {len(output_rows)} holds, "
        f"{target_seconds:.3f}s each at {sample_rate} Hz"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-wav", type=Path, required=True)
    parser.add_argument("--source-labels", type=Path, required=True)
    parser.add_argument("--output-wav", type=Path, required=True)
    parser.add_argument("--output-labels", type=Path, required=True)
    parser.add_argument("--target-seconds", type=float, default=3.60)
    parser.add_argument("--minimum-source-seconds", type=float, default=1.50)
    args = parser.parse_args()
    if args.target_seconds < 3.25 or args.minimum_source_seconds < 0.40:
        raise SystemExit("unsafe diagnostic duration")
    build(
        args.source_wav,
        args.source_labels,
        args.output_wav,
        args.output_labels,
        args.target_seconds,
        args.minimum_source_seconds,
    )


if __name__ == "__main__":
    main()
