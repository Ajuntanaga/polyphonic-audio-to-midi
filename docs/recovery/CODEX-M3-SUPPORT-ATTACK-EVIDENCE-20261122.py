#!/usr/bin/env python3
"""Read two preselected attack windows from the saved v5 table, without audio.

This is a diagnostic extraction, not a fitted rule or candidate evaluation.
Windows and targets were chosen before opening the trace: labels 263 and 364,
250 ms before through 125 ms after their annotated start. Retain every field
of the target candidate, including zero features, and existing rendered voices.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.candidate_outcome_analysis import _candidates

TRACE = ROOT / (
    "build/github-results/unfiltered-observation-44835727027/evidence/"
    "github-results/unfiltered-observation/ordinary-current-on-512-outcome-v5.tsv.gz"
)
BASELINE = ROOT / "docs/recovery/basic-pitch-baseline-20261121.json"
OUT = Path(__file__).with_suffix(".json")
TARGETS = (263, 364)
BLOCK = 512


def main() -> None:
    baseline = json.loads(BASELINE.read_text())["datasets"]["ordinary"]["measurement"]
    rate = baseline["sample_rate"]
    labels = {x["label_index"]: x for x in baseline["labels"] if x["label_index"] in TARGETS}
    assert set(labels) == set(TARGETS)
    result = {
        "kind": "saved-table diagnostic, no candidate or threshold fit",
        "trace": str(TRACE.relative_to(ROOT)),
        "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        "sample_rate": rate,
        "clock": "sample is last processed input; delivery is next block-512 boundary",
        "window_ms": [-250, 125],
        "targets": {str(i): {"label": label, "rows": []} for i, label in labels.items()},
    }
    last_window_end = max(x["start_sample"] for x in labels.values()) + rate // 8
    scanned = 0
    with gzip.open(TRACE, "rt") as stream:
        marker = stream.readline().strip()
        assert marker == "# m3_candidate_outcome_v5", marker
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            sample = int(row["sample"])
            scanned += 1
            if sample > last_window_end:
                break
            for i, label in labels.items():
                relative = sample + 1 - label["start_sample"]
                if not -rate // 4 <= relative <= rate // 8:
                    continue
                note = label["midi_note"]
                candidate_text = ",".join(
                    x for x in row["candidates"].split(",") if x.split(":", 1)[0] == str(note)
                )
                candidate = _candidates({"candidate_text": candidate_text}).get(note)
                delivery = ((sample + 1 + BLOCK - 1) // BLOCK) * BLOCK
                result["targets"][str(i)]["rows"].append({
                    "sample": sample,
                    "relative_ms": relative * 1000 / rate,
                    "delivered_relative_ms": (delivery - label["start_sample"]) * 1000 / rate,
                    "quiet": int(row["quiet"]),
                    "labels": row["labels"],
                    "voices": row["voices"],
                    "candidate": candidate,
                })
    result["rows_scanned"] = scanned
    # These first observations are descriptive, with no new decision threshold.
    for target in result["targets"].values():
        rows = target["rows"]
        target["candidate_missing_rows"] = sum(x["candidate"] is None for x in rows)
        first = {}
        for row in rows:
            c = row["candidate"]
            if row["relative_ms"] < 0 or c is None:
                continue
            for name, yes in {
                "onset_observed": c["onset_observed"] == 1,
                "onset_positive": c["onset_observed"] == 1 and c["onset"] > 0,
                "direct": c["direct"] == 1,
                "local": c["local"] == 1,
                "evidence": c["evidence"] == 1,
                "cal_direct": c["cal_direct"] == 1,
                "pool": c["selector_pool_member"] == 1,
                "pool_and_direct": c["selector_pool_member"] == 1 and c["direct"] == 1,
                "admitted_ratio": c["score_ratio"] >= 1,
            }.items():
                if yes and name not in first:
                    first[name] = {k: row[k] for k in ("relative_ms", "delivered_relative_ms")}
        target["first_after_label"] = first
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "scanned": scanned,
        "targets": {i: {"rows": len(t["rows"]), "missing": t["candidate_missing_rows"],
                         "first_after_label": t["first_after_label"]}
                    for i, t in result["targets"].items()}}, indent=2))


if __name__ == "__main__":
    main()
