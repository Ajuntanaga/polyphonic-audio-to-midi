#!/usr/bin/env python3
"""Summarize the string-resolved labels in a GuitarSet annotation export.

The script intentionally consumes annotations only. It does not download or
open the multi-gigabyte GuitarSet audio archives.

Dataset: https://zenodo.org/records/3371780
Paper: https://ismir2018.ircam.fr/doc/pdfs/188_Paper.pdf
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import statistics


OPEN_MIDI = (40, 45, 50, 55, 59, 64)


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    mix = position - lower
    return ordered[lower] * (1.0 - mix) + ordered[upper] * mix


def note_annotations(document: dict) -> list[tuple[int, list[dict]]]:
    result = []
    for annotation in document.get("annotations", []):
        if annotation.get("namespace") != "note_midi":
            continue
        source = annotation.get("annotation_metadata", {}).get("data_source")
        if not isinstance(source, str) or not source.isdigit():
            raise ValueError("note annotation lacks a numeric string source")
        string_index = int(source)
        rows = annotation.get("data")
        if string_index >= len(OPEN_MIDI) or not isinstance(rows, list):
            raise ValueError("invalid GuitarSet note annotation")
        result.append((string_index, rows))
    return result


def summarize(directory: Path) -> dict:
    files = sorted(directory.glob("*.jams"))
    if not files:
        raise ValueError(f"no .jams files under {directory}")
    notes_by_string: collections.Counter[int] = collections.Counter()
    fret_counts: collections.Counter[tuple[int, int]] = collections.Counter()
    same_pitch_pairs: collections.Counter[tuple[int, int]] = collections.Counter()
    durations: list[float] = []
    contour_points = 0
    overlap_seconds = 0.0
    maximum_polyphony = 0

    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        by_string = note_annotations(document)
        endpoints: list[tuple[float, int]] = []
        for annotation in document.get("annotations", []):
            if annotation.get("namespace") == "pitch_contour":
                data = annotation.get("data", {})
                times = data.get("time", []) if isinstance(data, dict) else []
                contour_points += len(times)
        for string_index, rows in by_string:
            for row in rows:
                start = float(row["time"])
                duration = float(row["duration"])
                note = int(round(float(row["value"])))
                end = start + duration
                if duration <= 0.0 or end <= start:
                    raise ValueError(f"invalid note interval in {path}")
                notes_by_string[string_index] += 1
                fret_counts[string_index, note - OPEN_MIDI[string_index]] += 1
                durations.append(duration)
                endpoints.append((start, 1))
                endpoints.append((end, -1))

        for left_index, (left_string, left_rows) in enumerate(by_string):
            left_rows = sorted(left_rows, key=lambda row: float(row["time"]))
            for right_string, right_rows in by_string[left_index + 1 :]:
                right_rows = sorted(
                    right_rows, key=lambda row: float(row["time"])
                )
                left_cursor = 0
                right_cursor = 0
                while left_cursor < len(left_rows) and right_cursor < len(right_rows):
                    left = left_rows[left_cursor]
                    right = right_rows[right_cursor]
                    left_end = float(left["time"]) + float(left["duration"])
                    right_end = float(right["time"]) + float(right["duration"])
                    overlap = min(left_end, right_end) - max(
                        float(left["time"]), float(right["time"])
                    )
                    if (
                        overlap > 0.020
                        and round(float(left["value"]))
                        == round(float(right["value"]))
                    ):
                        same_pitch_pairs[left_string, right_string] += 1
                        overlap_seconds += overlap
                    if left_end < right_end:
                        left_cursor += 1
                    else:
                        right_cursor += 1

        active = 0
        for _time, change in sorted(endpoints, key=lambda item: (item[0], item[1])):
            active += change
            maximum_polyphony = max(maximum_polyphony, active)

    fret_ranges = {}
    for string_index in range(len(OPEN_MIDI)):
        frets = [
            fret
            for (candidate_string, fret), count in fret_counts.items()
            if candidate_string == string_index and count > 0
        ]
        fret_ranges[str(string_index)] = [min(frets), max(frets)]

    return {
        "schema": 1,
        "tracks": len(files),
        "note_events": sum(notes_by_string.values()),
        "pitch_contour_points": contour_points,
        "notes_by_string_low_to_high": [
            notes_by_string[index] for index in range(len(OPEN_MIDI))
        ],
        "fret_ranges_low_to_high": fret_ranges,
        "note_duration_seconds": {
            "p05": round(quantile(durations, 0.05), 6),
            "median": round(statistics.median(durations), 6),
            "p95": round(quantile(durations, 0.95), 6),
        },
        "same_pitch_cross_string_overlaps": sum(same_pitch_pairs.values()),
        "same_pitch_overlap_seconds": round(overlap_seconds, 6),
        "same_pitch_overlaps_by_string_pair": {
            f"{left}-{right}": count
            for (left, right), count in sorted(same_pitch_pairs.items())
        },
        "maximum_annotated_polyphony": maximum_polyphony,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = summarize(arguments.annotations)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
