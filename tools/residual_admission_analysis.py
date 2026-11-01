"""Summarize decimated, audio-only added-pitch fits without claiming MIDI gains."""
from __future__ import annotations

import csv
import math
from collections import Counter

GAIN_FLOORS = (0.0001, 0.001, 0.003, 0.01, 0.03, 0.1, 0.2)
ENERGY_FLOORS = (0.0001, 0.001, 0.003, 0.01, 0.03, 0.1)
FIELDS = (
    "sample tick note base_count used_mask free_mask any_label expected_note "
    "expected_mask already_emitted base_valid added_valid base_residual "
    "added_residual residual_gain independent_energy shared_fundamental "
    "fundamental_overlap score_ratio fund_ratio direct local "
    "calibration_similarity calibration_string base_notes"
).split()
FLOAT_FIELDS = set((
    "base_residual added_residual residual_gain independent_energy "
    "fundamental_overlap score_ratio fund_ratio calibration_similarity"
).split())
CLASSES = ("expected_free_string", "expected_unscoped", "expected_occupied_string",
           "already_emitted", "wrong_note", "extra_gap")


def _truth(row):
    if not row["expected_note"]:
        return "wrong_note" if row["any_label"] else "extra_gap"
    if row["already_emitted"]:
        return "already_emitted"
    if not row["expected_mask"]:
        return "expected_unscoped"
    return ("expected_free_string" if row["expected_mask"] & row["free_mask"]
            else "expected_occupied_string")


def analyze_stream(stream, capture):
    """Counts are sampled candidate observations, never extrapolated frame gains."""
    if capture.get("truncated") or capture.get("decimation") != 16:
        raise ValueError("complete decimation-16 capture required")
    reader = csv.DictReader(stream, delimiter="\t")
    if reader.fieldnames != FIELDS:
        raise ValueError("unexpected residual-admission trace schema")
    totals = Counter()
    population = Counter()
    policies = [dict(gain_floor=g, energy_floor=e, observations=Counter(),
                     sole_free_string=Counter(), calibrated_free_string=Counter(),
                     calibrated_wrong_string=0)
                for g in GAIN_FLOORS for e in ENERGY_FLOORS]
    previous_key = (-1, -1)
    previous_sample = -1
    for source in reader:
        if None in source or any(v is None for v in source.values()):
            raise ValueError("incomplete trace row")
        row = {k: (float(v) if k in FLOAT_FIELDS else int(v))
               for k, v in source.items() if k != "base_notes"}
        if not all(math.isfinite(row[k]) for k in FLOAT_FIELDS):
            raise ValueError("nonfinite residual evidence")
        key = (row["tick"], row["note"])
        if key <= previous_key or row["sample"] < previous_sample:
            raise ValueError("duplicate or unordered candidate observation")
        previous_key, previous_sample = key, row["sample"]
        if row["tick"] % capture["decimation"] or not 0 <= row["note"] < 128:
            raise ValueError("invalid tick or pitch")
        if (not 0 < row["free_mask"] < 256 or not 0 <= row["used_mask"] < 256
                or row["free_mask"] & row["used_mask"]):
            raise ValueError("candidate conflicts with occupied strings")
        base_notes = [int(n) for n in source["base_notes"].split(",")]
        if (not 0 < row["base_count"] < 8 or len(base_notes) != row["base_count"]
                or len(set(base_notes)) != len(base_notes) or row["note"] in base_notes
                or any(not 0 <= n < 128 for n in base_notes)):
            raise ValueError("invalid base pitch model")
        totals["rows"] += 1
        truth = _truth(row)
        population[truth] += 1
        if not row["base_valid"] or not row["added_valid"]:
            totals["invalid_fit"] += 1
            continue
        if abs(row["base_residual"] - row["added_residual"] - row["residual_gain"]) > 1e-10:
            raise ValueError("residual difference is inconsistent")
        totals["valid_fit"] += 1
        if row["base_count"] < 2:
            totals["fewer_than_two_base_pitches"] += 1
            continue
        if row["shared_fundamental"] or row["fundamental_overlap"] >= 0.99:
            totals["harmonic_ambiguity"] += 1
            continue
        if row["already_emitted"]:
            totals["already_emitted"] += 1
            continue
        totals["eligible"] += 1
        sole = row["free_mask"].bit_count() == 1
        calibrated = (0 <= row["calibration_string"] < 8 and
                      bool(row["free_mask"] & (1 << row["calibration_string"])) and
                      row["calibration_similarity"] >= 0.8)
        for policy in policies:
            if (row["residual_gain"] < policy["gain_floor"] or
                    row["independent_energy"] < policy["energy_floor"]):
                continue
            policy["observations"][truth] += 1
            if sole:
                policy["sole_free_string"][truth] += 1
            if calibrated:
                policy["calibrated_free_string"][truth] += 1
                if row["expected_note"] and row["expected_mask"] and not (
                        row["expected_mask"] & (1 << row["calibration_string"])):
                    policy["calibrated_wrong_string"] += 1
    if totals["rows"] != capture["rows"]:
        raise ValueError("trace rows disagree with capture metadata")
    for policy in policies:
        for field in ("observations", "sole_free_string", "calibrated_free_string"):
            policy[field] = {name: policy[field][name] for name in CLASSES}
        counts = policy["observations"]
        policy["expected_pitch_samples"] = (counts["expected_free_string"] +
            counts["expected_unscoped"] + counts["expected_occupied_string"])
        policy["false_pitch_samples"] = counts["wrong_note"] + counts["extra_gap"]
    return dict(
        units="decimated candidate observations, not recovered MIDI frames",
        decimation=capture["decimation"], totals=dict(totals), population=dict(population),
        policies=policies, production_changed=False,
        limitation="A pitch fit does not prove string ownership or sequence-level MIDI benefit.")
