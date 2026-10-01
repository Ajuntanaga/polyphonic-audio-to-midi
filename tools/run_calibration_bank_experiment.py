#!/usr/bin/env python3
"""Run controlled calibration-bank experiments on the physical M3 corpus."""

from __future__ import annotations

import argparse
import csv
import math
import pathlib
import subprocess
from collections import defaultdict

import generate_pitch_corrected_corpus as corpus


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_BANKS = ("raw", "midpoint", "zero")


def build_cases(
    bank_names: tuple[str, ...], audio_variants: tuple[str, ...] = ()
) -> list[tuple[str, str]]:
    if audio_variants:
        return [
            (audio, bank) for audio in audio_variants for bank in bank_names
        ]
    cases = [("raw", bank) for bank in bank_names]
    cases.extend(
        (audio, bank)
        for audio in ("midpoint", "exact")
        for bank in BASE_BANKS
        if bank in bank_names
    )
    return cases


def parse_replay_summary(output: str) -> dict[str, str]:
    lines = output.splitlines()
    if len(lines) < 2:
        raise ValueError("replay output has no summary")
    rows = list(csv.DictReader(lines[:2], delimiter="\t"))
    if len(rows) != 1 or not rows[0].get("fingerprint"):
        raise ValueError("invalid replay summary")
    return dict(rows[0])


def parse_label_details(output: str) -> list[dict[str, str]]:
    lines = output.splitlines()
    try:
        start = next(
            index for index, line in enumerate(lines) if line.startswith("label_index\t")
        )
    except StopIteration:
        return []
    return [dict(row) for row in csv.DictReader(lines[start:], delimiter="\t")]


def _offset_name(offset: float) -> str:
    sign = "p" if offset >= 0.0 else "m"
    magnitude = f"{abs(offset):g}".replace(".", "p")
    return f"offset-{sign}{magnitude}"


def prepare_banks(
    source: pathlib.Path, output: pathlib.Path, offsets: tuple[float, ...]
) -> dict[str, pathlib.Path]:
    output.mkdir(parents=True, exist_ok=True)
    banks = {"raw": source}
    midpoint = output / "midpoint.m3cb"
    zero = output / "zero.m3cb"
    shuffled = output / "shuffled.m3cb"
    corpus.write_scaled_center_calibration(source, midpoint, 0.5)
    corpus.write_zero_centered_calibration(source, zero)
    corpus.write_note_shuffled_center_calibration(source, shuffled)
    banks.update(midpoint=midpoint, zero=zero, shuffled=shuffled)
    for offset in offsets:
        name = _offset_name(offset)
        path = output / f"{name}.m3cb"
        try:
            corpus.write_adjusted_center_calibration(
                source, path, cents_scale=1.0, cents_offset=offset
            )
        except ValueError as error:
            print(f"skip {name}: {error}", flush=True)
            continue
        banks[name] = path
    return banks


def prepare_labels(
    raw_directory: pathlib.Path,
    midpoint_directory: pathlib.Path,
    exact_directory: pathlib.Path,
    output: pathlib.Path,
    truth_calibration: pathlib.Path,
) -> dict[str, dict[int, pathlib.Path]]:
    directories = {
        "raw": raw_directory,
        "midpoint": midpoint_directory,
        "exact": exact_directory,
    }
    residuals = {"raw": 1.0, "midpoint": 0.5, "exact": 0.0}
    result: dict[str, dict[int, pathlib.Path]] = defaultdict(dict)
    for variant, directory in directories.items():
        target = output / variant
        target.mkdir(parents=True, exist_ok=True)
        for physical_string in range(1, 9):
            name = f"string-{physical_string:02d}"
            destination = target / f"{name}.tsv"
            corpus.write_expected_cents_labels(
                directory / f"{name}.tsv",
                raw_directory / f"{name}-manifest.json",
                destination,
                residual_fraction=residuals[variant],
                truth_calibration=truth_calibration,
            )
            result[variant][physical_string] = destination
    return dict(result)


def _wave_path(directory: pathlib.Path, variant: str, physical: int) -> pathlib.Path:
    suffix = {"raw": "raw", "midpoint": "midpoint", "exact": "corrected"}[
        variant
    ]
    return directory / f"string-{physical:02d}-{suffix}.wav"


def derive_holdout_bank(
    replay: pathlib.Path,
    source_bank: pathlib.Path,
    raw_directory: pathlib.Path,
    labels: dict[int, pathlib.Path],
    output: pathlib.Path,
    excluded_pass: int,
    block_size: int,
) -> pathlib.Path:
    previous = source_bank
    output.mkdir(parents=True, exist_ok=True)
    for string_index in range(8):
        physical = 8 - string_index
        destination = output / f"holdout-pass{excluded_pass}-string{string_index}.m3cb"
        command = [
            str(replay),
            "--wav",
            str(_wave_path(raw_directory, "raw", physical)),
            "--labels",
            str(labels[physical]),
            "--calibration",
            str(previous),
            "--derive-calibration-string",
            str(string_index),
            "--calibration-output",
            str(destination),
            "--exclude-calibration-pass",
            str(excluded_pass),
            "--block",
            str(block_size),
        ]
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"holdout derivation failed for string {string_index}: "
                f"{completed.stderr.strip()}"
            )
        previous = destination
        print(f"derived holdout string {string_index + 1}/8", flush=True)
    return previous


def _write_tsv(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty result table")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _label_summary(details: list[dict[str, str]]) -> dict[str, object]:
    valid_cents = [row for row in details if int(row["cents_observations"]) > 0]
    first_valid = [
        float(row["first_valid_cents_ms"])
        for row in details
        if float(row["first_valid_cents_ms"]) >= 0.0
    ]
    first_string = [
        float(row["first_correct_string_ms"])
        for row in details
        if float(row["first_correct_string_ms"]) >= 0.0
    ]
    return {
        "label_count": len(details),
        "labels_with_cents": len(valid_cents),
        "string_flips": sum(int(row["string_flips"]) for row in details),
        "mean_first_valid_cents_ms": (
            sum(first_valid) / len(first_valid) if first_valid else -1.0
        ),
        "mean_first_correct_string_ms": (
            sum(first_string) / len(first_string) if first_string else -1.0
        ),
        "maximum_longest_correct_run_ms": max(
            (float(row["longest_correct_run_ms"]) for row in details),
            default=0.0,
        ),
    }


def run_matrix(
    replay: pathlib.Path,
    directories: dict[str, pathlib.Path],
    labels: dict[str, dict[int, pathlib.Path]],
    banks: dict[str, pathlib.Path],
    output: pathlib.Path,
    block_size: int,
    audio_variants: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    details_directory = output / "details"
    details_directory.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    cases = build_cases(tuple(banks), audio_variants)
    total = len(cases) * 8
    completed_count = 0
    for audio_variant, bank_variant in cases:
        for physical in range(1, 9):
            command = [
                str(replay),
                "--wav",
                str(_wave_path(directories[audio_variant], audio_variant, physical)),
                "--labels",
                str(labels[audio_variant][physical]),
                "--calibration",
                str(banks[bank_variant]),
                "--block",
                str(block_size),
                "--label-details",
            ]
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"replay failed for {audio_variant}/{bank_variant}/"
                    f"string-{physical:02d}: {completed.stderr.strip()}"
                )
            detail_path = details_directory / (
                f"{audio_variant}__{bank_variant}__string-{physical:02d}.tsv"
            )
            detail_path.write_text(completed.stdout, encoding="utf-8")
            row: dict[str, object] = {
                "audio_variant": audio_variant,
                "bank_variant": bank_variant,
                "physical_string": physical,
                "string_index": 8 - physical,
            }
            row.update(parse_replay_summary(completed.stdout))
            row.update(_label_summary(parse_label_details(completed.stdout)))
            rows.append(row)
            completed_count += 1
            print(
                f"replay {completed_count}/{total}: "
                f"{audio_variant}/{bank_variant}/string-{physical:02d}",
                flush=True,
            )
    return rows


def summarize_runs(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["audio_variant"]), str(row["bank_variant"]))].append(row)
    summaries = []
    for (audio, bank), group in grouped.items():
        labeled = sum(int(row["labeled"]) for row in group)
        matched = sum(int(row["matched"]) for row in group)
        cents_count = sum(int(row["cents_observations"]) for row in group)
        cents_sum = sum(
            int(row["cents_observations"]) * float(row["cents_mean_error"])
            for row in group
        )
        cents_mean = cents_sum / cents_count if cents_count else 0.0
        second_moment = sum(
            int(row["cents_observations"])
            * (
                float(row["cents_sd"]) ** 2
                + float(row["cents_mean_error"]) ** 2
            )
            for row in group
        )
        cents_sd = (
            math.sqrt(max(0.0, second_moment / cents_count - cents_mean**2))
            if cents_count
            else 0.0
        )
        summaries.append(
            {
                "audio_variant": audio,
                "bank_variant": bank,
                "labeled": labeled,
                "matched": matched,
                "match_percent": 100.0 * matched / labeled if labeled else 0.0,
                "false_positive_voices": sum(
                    int(row["false_positive_voices"]) for row in group
                ),
                "false_gap_voices": sum(int(row["false_gap_voices"]) for row in group),
                "false_wrong_note_voices": sum(
                    int(row["false_wrong_note_voices"]) for row in group
                ),
                "false_wrong_string_voices": sum(
                    int(row["false_wrong_string_voices"]) for row in group
                ),
                "transitions_inside_holds": sum(
                    int(row["transitions_inside_holds"]) for row in group
                ),
                "transitions_in_gaps": sum(
                    int(row["transitions_in_gaps"]) for row in group
                ),
                "cents_observations": cents_count,
                "cents_mean_error": cents_mean,
                "cents_sd": cents_sd,
                "mean_run_cents_p95_abs": sum(
                    float(row["cents_p95_abs"]) for row in group
                )
                / len(group),
                "string_flips": sum(int(row["string_flips"]) for row in group),
                "mean_first_valid_cents_ms": sum(
                    float(row["mean_first_valid_cents_ms"]) for row in group
                )
                / len(group),
                "mean_first_correct_string_ms": sum(
                    float(row["mean_first_correct_string_ms"]) for row in group
                )
                / len(group),
                "maximum_longest_correct_run_ms": max(
                    float(row["maximum_longest_correct_run_ms"]) for row in group
                ),
            }
        )
    return summaries


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    base = ROOT / "build/physical-capture"
    parser.add_argument("--replay", type=pathlib.Path, default=ROOT / "build/contributor/m3_replay")
    parser.add_argument("--raw-dir", type=pathlib.Path, default=base / "pitch-corrected")
    parser.add_argument("--midpoint-dir", type=pathlib.Path, default=base / "pitch-midpoint-reaper")
    parser.add_argument("--exact-dir", type=pathlib.Path, default=base / "pitch-corrected-reaper")
    parser.add_argument(
        "--calibration",
        type=pathlib.Path,
        default=ROOT / "tests/fixtures/m3_physical_a440/calibration-v1.m3cb",
    )
    parser.add_argument("--output", type=pathlib.Path, default=base / "calibration-bank-experiment")
    parser.add_argument("--block", type=int, default=512)
    parser.add_argument("--exclude-pass", type=int, default=3)
    parser.add_argument("--skip-holdout", action="store_true")
    parser.add_argument("--offset", action="append", type=float)
    parser.add_argument(
        "--audio-variant",
        action="append",
        choices=("raw", "midpoint", "exact"),
        help="restrict the matrix to one or more audio variants",
    )
    parser.add_argument(
        "--bank-variant",
        action="append",
        help="restrict the matrix to one or more prepared bank names",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.block <= 0 or not 1 <= args.exclude_pass <= 255:
        raise ValueError("invalid block or excluded pass")
    offsets = tuple(args.offset or (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 5.0, 10.0))
    args.output.mkdir(parents=True, exist_ok=True)
    banks = prepare_banks(args.calibration, args.output / "banks", offsets)
    labels = prepare_labels(
        args.raw_dir,
        args.midpoint_dir,
        args.exact_dir,
        args.output / "labels",
        args.calibration,
    )
    if not args.skip_holdout:
        banks[f"holdout-pass{args.exclude_pass}"] = derive_holdout_bank(
            args.replay,
            args.calibration,
            args.raw_dir,
            labels["raw"],
            args.output / "banks/holdout",
            args.exclude_pass,
            args.block,
        )
    if args.bank_variant:
        unknown = sorted(set(args.bank_variant) - set(banks))
        if unknown:
            raise ValueError(f"unknown bank variant(s): {', '.join(unknown)}")
        banks = {name: banks[name] for name in args.bank_variant}
    directories = {
        "raw": args.raw_dir,
        "midpoint": args.midpoint_dir,
        "exact": args.exact_dir,
    }
    rows = run_matrix(
        args.replay,
        directories,
        labels,
        banks,
        args.output,
        args.block,
        tuple(args.audio_variant or ()),
    )
    summaries = summarize_runs(rows)
    _write_tsv(args.output / "runs.tsv", rows)
    _write_tsv(args.output / "summary.tsv", summaries)
    print(f"wrote {len(rows)} runs and {len(summaries)} summaries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
