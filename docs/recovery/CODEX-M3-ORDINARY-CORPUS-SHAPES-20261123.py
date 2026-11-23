"""Describe the pinned ordinary labels; reads metadata only, never audio.

Run from any directory. Writes the adjacent JSON report. This is a descriptive
census, not a playability classifier, new acceptance gate, or corpus replay.
"""

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv"
GENERATOR = ROOT / "tools/generate_note_combination_corpus.py"
PIN = "58dd6bb85d839751f3aabf6d369deb906968e0e5b706185f8f6fa4c85ac24b1f"


def main():
    raw = LABELS.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PIN:
        raise ValueError("Ordinary label pin differs; do not substitute another corpus")
    groups = defaultdict(list)
    for index, row in enumerate(csv.DictReader(raw.decode().splitlines(), delimiter="\t")):
        mask = int(row["string_mask"])
        if mask <= 0 or mask & (mask - 1) or mask > 128:
            raise ValueError(f"Label {index}: expected one of the eight strings")
        lane = mask.bit_length() - 1
        note = int(row["midi_note"])
        fret = note - (32 + 4 * lane)
        if not 0 <= fret <= 24:
            raise ValueError(f"Label {index}: fret outside recorded catalog")
        groups[(int(row["start_sample"]), int(row["end_sample"]))].append(
            {"label_index": index, "note": note, "lane": lane, "fret": fret}
        )
    windows = []
    for (start, end), notes in sorted(groups.items()):
        positive_frets = [item["fret"] for item in notes if item["fret"] > 0]
        span = max(positive_frets) - min(positive_frets) if positive_frets else 0
        windows.append({"start_sample": start, "end_sample": end,
                        "notes": notes, "fretted_note_count": len(positive_frets),
                        "fretted_span": span})
    spans = [window["fretted_span"] for window in windows]
    report = {
        "schema": "m3_ordinary_corpus_shape_metadata_v1",
        "classification": "descriptive; no policy or acceptance decision",
        "labels": {"path": str(LABELS.relative_to(ROOT)), "sha256": digest},
        "generator": {"path": str(GENERATOR.relative_to(ROOT)),
                      "sha256": hashlib.sha256(GENERATOR.read_bytes()).hexdigest()},
        "definition": "Group labels with identical start/end; fret=note-(32+4*lane); span=max(fret)-min(fret) over non-open strings only.",
        "window_count": len(windows),
        "label_count": sum(len(window["notes"]) for window in windows),
        "windows_with_two_or_more_fretted_notes": sum(window["fretted_note_count"] >= 2 for window in windows),
        "median_fretted_span": statistics.median(spans),
        "max_fretted_span": max(spans),
        "span_histogram": dict(sorted(Counter(spans).items())),
        "polyphony_histogram": dict(sorted(Counter(len(window["notes"]) for window in windows).items())),
        "descriptive_span_counts": {"at_most_3": sum(x <= 3 for x in spans),
                                    "at_most_5": sum(x <= 5 for x in spans)},
        "limits": ["No audio opened or processed", "No span cutoff asserts physical impossibility",
                   "No labels excluded or changed", "No installed score or gate changed",
                   "Does not measure actual played-chord success"],
        "windows": windows,
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "window_count", "label_count", "median_fretted_span", "max_fretted_span",
        "windows_with_two_or_more_fretted_notes", "descriptive_span_counts", "polyphony_histogram"
    )}))


if __name__ == "__main__":
    main()
