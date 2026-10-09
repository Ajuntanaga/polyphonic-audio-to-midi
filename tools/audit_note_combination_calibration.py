#!/usr/bin/env python3
"""Audit the recorded-note ledger and select a capacity-safe calibration."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence


TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import generate_note_combination_corpus as corpus


def audit_ledger(label_directory: pathlib.Path) -> dict[str, object]:
    catalog = corpus.read_note_catalog(label_directory)
    pairwise = corpus.build_pairwise_fret_plan()
    unisons = corpus.build_unison_plan(catalog)
    states = set(range(-1, corpus.FRET_COUNT))
    expected_pairs = set(itertools.product(states, repeat=2))
    covered_factor_pairs = 0
    for left, right in itertools.combinations(range(8), 2):
        observed = {(row[left], row[right]) for row in pairwise}
        if observed != expected_pairs:
            raise ValueError(f"incomplete pairwise coverage: {left + 1}/{right + 1}")
        covered_factor_pairs += len(observed)

    counts = [len(items) for items in catalog.values()]
    size_counts = Counter(len(row) for row in unisons)
    cents = [
        item.expected_cents
        for items in catalog.values()
        for item in items
        if item.expected_cents is not None
    ]
    return {
        "note_classes": len(catalog),
        "recorded_occurrences": sum(counts),
        "minimum_occurrences_per_class": min(counts, default=0),
        "maximum_occurrences_per_class": max(counts, default=0),
        "pairwise_cases": len(pairwise),
        "covered_factor_pairs": covered_factor_pairs,
        "unison_cases": len(unisons),
        "unison_cases_by_size": {
            str(size): size_counts[size] for size in sorted(size_counts)
        },
        "cents_labeled_occurrences": len(cents),
        "minimum_expected_cents": min(cents) if cents else None,
        "maximum_expected_cents": max(cents) if cents else None,
    }


def score_summary(row: Mapping[str, str]) -> dict[str, float | int]:
    labeled = int(row["labeled"])
    matched = int(row["matched"])
    false_positive = int(row["false_positive_voices"])
    precision = matched / (matched + false_positive) if matched + false_positive else 0.0
    recall = matched / labeled if labeled else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "labeled": labeled,
        "matched": matched,
        "false_positive_voices": false_positive,
        "false_wrong_note_voices": int(row["false_wrong_note_voices"]),
        "false_wrong_string_voices": int(row["false_wrong_string_voices"]),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def choose_calibration(
    rows: Sequence[Mapping[str, str]], minimum_polyphony: int = 4
) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for row in rows:
        polyphony = int(row["polyphony"])
        if polyphony < minimum_polyphony:
            continue
        candidate: dict[str, object] = {
            "trim_db": float(row["trim"]),
            "sensitivity": int(row["sensitivity"]),
            "response": int(row["response"]),
            "polyphony": polyphony,
        }
        candidate.update(score_summary(row))
        candidates.append(candidate)
    if not candidates:
        raise ValueError("no calibration satisfies the polyphony requirement")
    return max(
        candidates,
        key=lambda item: (
            float(item["f1"]),
            float(item["recall"]),
            float(item["precision"]),
        ),
    )


def read_tsv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream, delimiter="\t")]


def parse_lane_mask_histogram(encoded: str) -> dict[int, int]:
    histogram: dict[int, int] = {}
    if not encoded:
        return histogram
    for item in encoded.split(","):
        mask_text, frames_text = item.split(":", 1)
        mask = int(mask_text)
        frames = int(frames_text)
        if mask < 0 or frames <= 0 or mask in histogram:
            raise ValueError("invalid observed lane-mask histogram")
        histogram[mask] = frames
    return histogram


def string_topology(mask: int) -> str:
    if mask <= 0 or mask & ~0xFF:
        raise ValueError("string topology mask must name only the eight strings")
    bits = [bit for bit in range(8) if mask & (1 << bit)]
    if len(bits) < 2:
        raise ValueError("string topology requires at least two physical strings")
    return (
        "consecutive"
        if bits[-1] - bits[0] + 1 == len(bits)
        else "nonconsecutive"
    )


def simultaneous_lane_recovery(
    labels: Sequence[Mapping[str, str]],
    details: Sequence[Mapping[str, str]],
    case_stride: int,
) -> dict[str, object]:
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        groups[
            (
                int(label["start_sample"]) // case_stride,
                int(label["midi_note"]),
            )
        ].append(index)

    totals = {
        "groups": 0,
        "frames": 0,
        "exact_mask_frames": 0,
        "full_inclusion_frames": 0,
        "at_least_three_correct_frames": 0,
    }
    by_size: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_string_set: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_string_topology: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_midi_note: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for (_, midi_note), indices in groups.items():
        if len(indices) < 2:
            continue
        if any("observed_note_lane_masks" not in details[index] for index in indices):
            continue
        expected_mask = 0
        for index in indices:
            expected_mask |= int(labels[index]["string_mask"])
        size = expected_mask.bit_count()
        if size != len(indices):
            raise ValueError("unison group repeats a physical string")
        histograms = [
            parse_lane_mask_histogram(details[index]["observed_note_lane_masks"])
            for index in indices
        ]
        if any(histogram != histograms[0] for histogram in histograms[1:]):
            raise ValueError("unison labels disagree on observed lane masks")
        histogram = histograms[0]
        frames = sum(histogram.values())
        if any(int(details[index]["labeled"]) != frames for index in indices):
            raise ValueError("lane-mask histogram does not cover the labeled hold")
        exact = histogram.get(expected_mask, 0)
        full = sum(
            count
            for observed, count in histogram.items()
            if observed & expected_mask == expected_mask
        )
        at_least_three = sum(
            count
            for observed, count in histogram.items()
            if (observed & expected_mask).bit_count() >= min(3, size)
        )
        totals["groups"] += 1
        totals["frames"] += frames
        totals["exact_mask_frames"] += exact
        totals["full_inclusion_frames"] += full
        totals["at_least_three_correct_frames"] += at_least_three
        by_size[size][0] += frames
        by_size[size][1] += exact
        by_size[size][2] += at_least_three
        string_set = ",".join(
            str(8 - bit)
            for bit in range(7, -1, -1)
            if expected_mask & (1 << bit)
        )
        topology = string_topology(expected_mask)
        for bucket in (
            by_string_set[string_set],
            by_string_topology[topology],
            by_midi_note[midi_note],
        ):
            bucket[0] += frames
            bucket[1] += exact
            bucket[2] += at_least_three

    frames = totals["frames"]
    totals["exact_rate"] = totals["exact_mask_frames"] / frames if frames else 0.0
    totals["full_inclusion_rate"] = (
        totals["full_inclusion_frames"] / frames if frames else 0.0
    )
    totals["at_least_three_correct_rate"] = (
        totals["at_least_three_correct_frames"] / frames if frames else 0.0
    )
    totals["exact_rate_by_unison_size"] = {
        str(size): size_totals[1] / size_totals[0]
        for size, size_totals in sorted(by_size.items())
    }
    totals["at_least_three_rate_by_unison_size"] = {
        str(size): size_totals[2] / size_totals[0]
        for size, size_totals in sorted(by_size.items())
    }
    totals["exact_rate_by_string_set"] = {
        key: values[1] / values[0]
        for key, values in sorted(by_string_set.items())
    }
    totals["at_least_three_rate_by_string_set"] = {
        key: values[2] / values[0]
        for key, values in sorted(by_string_set.items())
    }
    totals["frames_by_string_topology"] = {
        key: values[0] for key, values in sorted(by_string_topology.items())
    }
    totals["exact_rate_by_string_topology"] = {
        key: values[1] / values[0]
        for key, values in sorted(by_string_topology.items())
    }
    totals["at_least_three_rate_by_string_topology"] = {
        key: values[2] / values[0]
        for key, values in sorted(by_string_topology.items())
    }
    totals["exact_rate_by_midi_note"] = {
        str(key): values[1] / values[0]
        for key, values in sorted(by_midi_note.items())
    }
    return totals


def audit_replay(
    label_path: pathlib.Path, replay_path: pathlib.Path, case_stride: int
) -> dict[str, object]:
    if case_stride <= 0:
        raise ValueError("case stride must be positive")
    labels = read_tsv(label_path)
    with replay_path.open(encoding="utf-8", newline="") as stream:
        summary_header = stream.readline().rstrip("\n").split("\t")
        summary_values = stream.readline().rstrip("\n").split("\t")
        detail_header = stream.readline().rstrip("\n").split("\t")
        details = [
            dict(zip(detail_header, line.rstrip("\n").split("\t")))
            for line in stream
            if line.strip()
        ]
    summary = dict(zip(summary_header, summary_values))
    if len(summary_header) != len(summary_values) or len(labels) != len(details):
        raise ValueError("replay and label ledgers differ")

    case_sizes = Counter(
        int(label["start_sample"]) // case_stride for label in labels
    )
    grouped: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for index, (label, detail) in enumerate(zip(labels, details)):
        if (
            int(detail["label_index"]) != index
            or detail["start_sample"] != label["start_sample"]
            or detail["end_sample"] != label["end_sample"]
            or detail["midi_note"] != label["midi_note"]
            or detail["string_mask"] != label["string_mask"]
        ):
            raise ValueError(f"replay detail diverges at label {index}")
        case = int(label["start_sample"]) // case_stride
        physical_string = 9 - int(label["string_mask"]).bit_length()
        fret = int(label["midi_note"]) - corpus.OPEN_NOTES[physical_string]
        for key in (
            ("unison_size", case_sizes[case]),
            ("string", physical_string),
            ("fret", fret),
        ):
            grouped[key][0] += int(detail["matched"])
            grouped[key][1] += int(detail["labeled"])

    def recalls(kind: str) -> dict[str, float]:
        return {
            str(value): matched / labeled if labeled else 0.0
            for (group_kind, value), (matched, labeled) in sorted(grouped.items())
            if group_kind == kind
        }

    return {
        "label_rows": len(labels),
        "summary": score_summary(summary),
        "recall_by_unison_size": recalls("unison_size"),
        "recall_by_string": recalls("string"),
        "recall_by_fret": recalls("fret"),
        "simultaneous_lane_recovery": simultaneous_lane_recovery(
            labels, details, case_stride
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=pathlib.Path)
    parser.add_argument("--combined-sweep", required=True, type=pathlib.Path)
    parser.add_argument("--minimum-polyphony", type=int, default=4)
    parser.add_argument("--validation-labels", type=pathlib.Path)
    parser.add_argument("--validation-replay", type=pathlib.Path)
    parser.add_argument("--case-stride", type=int)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    report = {
        "ledger": audit_ledger(args.labels),
        "selected_calibration": choose_calibration(
            read_tsv(args.combined_sweep), args.minimum_polyphony
        ),
    }
    validation_arguments = (
        args.validation_labels,
        args.validation_replay,
        args.case_stride,
    )
    if any(value is not None for value in validation_arguments):
        if not all(value is not None for value in validation_arguments):
            parser.error(
                "validation requires --validation-labels, --validation-replay, and --case-stride"
            )
        report["validation"] = audit_replay(
            args.validation_labels, args.validation_replay, args.case_stride
        )
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.output is None:
        print(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
