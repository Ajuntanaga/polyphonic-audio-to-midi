#!/usr/bin/env python3
import argparse
import csv
import math
import pathlib
from collections.abc import Iterable, Mapping
from typing import Any


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0 <= q <= 1:
        raise ValueError("percentile q must be between 0 and 1")
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def score_notes(expected: set[int], observed: set[int]) -> dict[str, float | int]:
    true_positives = len(expected & observed)
    false_positives = len(observed - expected)
    false_negatives = len(expected - observed)
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = (
        true_positives / precision_denominator
        if precision_denominator
        else 0.0
    )
    recall = (
        true_positives / recall_denominator
        if recall_denominator
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _is_note_on(event: Mapping[str, Any]) -> bool:
    return int(event["status"]) & 0xF0 == 0x90 and int(event["velocity"]) > 0


def _is_note_off(event: Mapping[str, Any]) -> bool:
    status = int(event["status"]) & 0xF0
    return status == 0x80 or (status == 0x90 and int(event["velocity"]) == 0)


def match_note_events(
    expected: Iterable[Mapping[str, Any]],
    observed: Iterable[Mapping[str, Any]],
    tolerance_samples: int,
) -> dict[str, Any]:
    observed_events = sorted(
        observed,
        key=lambda event: (
            int(event["case_id"]),
            int(event["absolute_sample"]),
        ),
    )
    matched_notes = 0
    hanging_notes = 0
    onset_latencies: list[int] = []
    release_latencies: list[int] = []
    matched_note_on_indices: set[int] = set()
    duplicate_note_ons = 0

    for expected_note in expected:
        case_id = int(expected_note["case_id"])
        note = int(expected_note["note"])
        onset = int(expected_note["onset_sample"])
        deadline = onset + max(0, int(tolerance_samples))
        matching = [
            (index, event)
            for index, event in enumerate(observed_events)
            if int(event["case_id"]) == case_id and int(event["note"]) == note
        ]
        valid_note_ons = [
            (index, event)
            for index, event in matching
            if _is_note_on(event)
            and onset <= int(event["absolute_sample"]) <= deadline
        ]
        note_on_pair = next(
            (
                (index, event)
                for index, event in valid_note_ons
                if index not in matched_note_on_indices
            ),
            None,
        )
        if note_on_pair is None:
            continue
        note_on_index, note_on = note_on_pair
        matched_note_on_indices.add(note_on_index)
        duplicate_note_ons += max(0, len(valid_note_ons) - 1)
        matched_notes += 1
        note_on_sample = int(note_on["absolute_sample"])
        onset_latencies.append(note_on_sample - onset)
        note_off = next(
            (
                event
                for _, event in matching
                if _is_note_off(event)
                and int(event["absolute_sample"]) >= note_on_sample
            ),
            None,
        )
        if note_off is None:
            hanging_notes += 1
        else:
            release_latencies.append(
                int(note_off["absolute_sample"])
                - int(expected_note["release_sample"])
            )

    false_triggers = sum(
        1
        for index, event in enumerate(observed_events)
        if _is_note_on(event) and index not in matched_note_on_indices
    )
    active_notes: set[tuple[int, int]] = set()
    for event in observed_events:
        key = (int(event["case_id"]), int(event["note"]))
        if _is_note_on(event):
            active_notes.add(key)
        elif _is_note_off(event):
            active_notes.discard(key)
    hanging_notes = len(active_notes)

    return {
        "matched_notes": matched_notes,
        "onset_latencies": onset_latencies,
        "release_latencies": release_latencies,
        "hanging_notes": hanging_notes,
        "false_triggers": false_triggers,
        "duplicate_note_ons": duplicate_note_ons,
    }


def summarize(
    cases: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    case_rows = list(cases)
    event_rows = list(events)
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    hanging_notes = 0
    duplicate_note_ons = 0
    silence_events = 0
    onset_latencies: list[int] = []
    release_latencies: list[int] = []
    chord_completion_latencies: list[int] = []

    for case in case_rows:
        case_id = int(case["case_id"])
        expected_notes = sorted({int(note) for note in case["expected"]})
        onset_sample = int(case["onset_sample"])
        release_sample = int(case["release_sample"])
        timeout_samples = int(case["timeout_samples"])
        expected_events = list(case.get("expected_events", []))
        if not expected_events:
            expected_events = [
                {
                    "case_id": case_id,
                    "note": note,
                    "onset_sample": onset_sample,
                    "release_sample": release_sample,
                }
                for note in expected_notes
            ]
        case_events = [
            event for event in event_rows if int(event["case_id"]) == case_id
        ]
        matched = match_note_events(
            expected_events,
            case_events,
            tolerance_samples=timeout_samples,
        )
        matched_count = int(matched["matched_notes"])
        false_count = int(matched["false_triggers"])
        if not expected_notes:
            silence_events += false_count
        true_positives += matched_count
        false_positives += false_count
        false_negatives += len(expected_notes) - matched_count
        hanging_notes += int(matched["hanging_notes"])
        duplicate_note_ons += int(matched["duplicate_note_ons"])
        onset_latencies.extend(matched["onset_latencies"])
        release_latencies.extend(matched["release_latencies"])
        if len(expected_notes) > 1 and matched_count == len(expected_notes):
            earliest_onset = min(
                int(event["onset_sample"]) for event in expected_events
            )
            observed_onsets = [
                int(event["onset_sample"]) + int(latency)
                for event, latency in zip(
                    expected_events,
                    matched["onset_latencies"],
                    strict=True,
                )
            ]
            chord_completion_latencies.append(
                max(observed_onsets) - earliest_onset
            )

    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    precision = (
        true_positives / precision_denominator
        if precision_denominator
        else 1.0
    )
    recall = (
        true_positives / recall_denominator
        if recall_denominator
        else 1.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "case_count": len(case_rows),
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_triggers": false_positives,
        "duplicate_note_ons": duplicate_note_ons,
        "hanging_notes": hanging_notes,
        "silence_events": silence_events,
        "onset_latencies": onset_latencies,
        "release_latencies": release_latencies,
        "chord_completion_latencies": chord_completion_latencies,
    }


def _parse_note_sequence(value: str) -> list[int]:
    if value.strip() in ("", "-"):
        return []
    return [int(token) for token in value.split(",")]


def _parse_note_list(value: str) -> set[int]:
    return set(_parse_note_sequence(value))


def _load_cases(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    cases: list[dict[str, Any]] = []
    for row in rows:
        sample_rate = int(row["sample_rate"])
        note_sequence = _parse_note_sequence(row["notes"])
        expected_notes = _parse_note_list(row["expected"])
        note_count = len(note_sequence)
        stagger_samples = round(float(row["stagger_ms"]) * sample_rate / 1000)
        onset_sample = round(0.500 * sample_rate)
        attack_samples = round(0.005 * sample_rate)
        sustain_samples = round(0.300 * sample_rate)
        release_samples = round(0.020 * sample_rate)
        last_stagger = max(0, note_count - 1) * stagger_samples
        expected_events = []
        for note in expected_notes:
            note_index = note_sequence.index(note)
            note_onset = onset_sample + note_index * stagger_samples
            expected_events.append(
                {
                    "case_id": int(row["case_id"]),
                    "note": note,
                    "onset_sample": note_onset,
                    "release_sample": (
                        note_onset + attack_samples + sustain_samples
                    ),
                }
            )
        expected_events.sort(key=lambda event: int(event["note"]))
        cases.append(
            {
                "case_id": int(row["case_id"]),
                "expected": expected_notes,
                "expected_events": expected_events,
                "onset_sample": onset_sample,
                "release_sample": (
                    onset_sample
                    + attack_samples
                    + sustain_samples
                    + last_stagger
                ),
                "timeout_samples": (
                    attack_samples
                    + sustain_samples
                    + release_samples
                    + last_stagger
                ),
            }
        )
    return cases


def _load_events(path: pathlib.Path) -> list[dict[str, int]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        return [
            {
                "case_id": int(row["case_id"]),
                "absolute_sample": int(row["absolute_sample"]),
                "status": int(row["status"]),
                "note": int(row["note"]),
                "velocity": int(row["velocity"]),
            }
            for row in rows
        ]


def _format_percentile(values: list[int], q: float) -> str:
    if not values:
        return "n/a"
    return f"{percentile(values, q):.3f} samples"


def _render_report(report: Mapping[str, Any], passed: bool) -> str:
    return (
        "# Synthetic Audio-to-MIDI Acceptance Report\n\n"
        f"Status: {'PASS' if passed else 'FAIL'}\n\n"
        "| Metric | Value |\n"
        "| --- | ---: |\n"
        f"| Cases | {report['case_count']} |\n"
        f"| True positives | {report['tp']} |\n"
        f"| False positives | {report['fp']} |\n"
        f"| False negatives | {report['fn']} |\n"
        f"| Precision | {report['precision']:.6f} |\n"
        f"| Recall | {report['recall']:.6f} |\n"
        f"| F1 | {report['f1']:.6f} |\n"
        f"| False triggers | {report['false_triggers']} |\n"
        f"| Duplicate note-ons | {report['duplicate_note_ons']} |\n"
        f"| Hanging notes | {report['hanging_notes']} |\n"
        f"| Silence events | {report['silence_events']} |\n"
        f"| Onset p50 | {_format_percentile(report['onset_latencies'], 0.50)} |\n"
        f"| Onset p95 | {_format_percentile(report['onset_latencies'], 0.95)} |\n"
        f"| Chord completion p95 | "
        f"{_format_percentile(report['chord_completion_latencies'], 0.95)} |\n"
        f"| Release p95 | {_format_percentile(report['release_latencies'], 0.95)} |\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize deterministic audio-to-MIDI case results"
    )
    parser.add_argument("--events", required=True, type=pathlib.Path)
    parser.add_argument("--cases", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--fail-below-precision", type=float, default=0.0)
    parser.add_argument("--fail-below-recall", type=float, default=0.0)
    parser.add_argument("--fail-on-hanging-note", action="store_true")
    args = parser.parse_args(argv)

    report = summarize(_load_cases(args.cases), _load_events(args.events))
    passed = (
        report["precision"] >= args.fail_below_precision
        and report["recall"] >= args.fail_below_recall
        and report["silence_events"] == 0
        and (not args.fail_on_hanging_note or report["hanging_notes"] == 0)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_render_report(report, passed), encoding="utf-8")
    print(f"synthetic acceptance: {'pass' if passed else 'fail'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
