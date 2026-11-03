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
LANE_COST_FIELDS = tuple(f"lane_cost_{string}" for string in range(8))
LANE_FIELDS = ["lane_fixed_context", "lane_selected_count", "lane_available_mask",
               *LANE_COST_FIELDS]
EXTENDED_FIELDS = FIELDS + LANE_FIELDS
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


def _lane_choice(row):
    """Native cost units, not posterior probabilities; no label-based ranking."""
    ranked = sorted((row[f"lane_cost_{s}"], s) for s in range(8)
                    if row["lane_available_mask"] & (1 << s))
    if not ranked:
        return None, None
    margin = ranked[1][0] - ranked[0][0] if len(ranked) > 1 else None
    if margin == 0.0:
        return None, margin
    return ranked[0][1], margin


def analyze_stream(stream, capture):
    """Counts are sampled candidate observations, never extrapolated frame gains."""
    if capture.get("truncated") or capture.get("decimation") != 16:
        raise ValueError("complete decimation-16 capture required")
    reader = csv.DictReader(stream, delimiter="\t")
    if reader.fieldnames not in (FIELDS, EXTENDED_FIELDS):
        raise ValueError("unexpected residual-admission trace schema")
    has_lane_costs = reader.fieldnames == EXTENDED_FIELDS
    float_fields = FLOAT_FIELDS | (set(LANE_COST_FIELDS) if has_lane_costs else set())
    totals = Counter()
    population = Counter()
    policies = [dict(gain_floor=g, energy_floor=e, observations=Counter(),
                     sole_free_string=Counter(), calibrated_free_string=Counter(),
                     calibrated_wrong_string=0)
                for g in GAIN_FLOORS for e in ENERGY_FLOORS]
    persistent_pitch = {hold: Counter() for hold in (1, 3, 5)}
    native_policies = [dict(sampled_observations_required=hold, margin_floor=margin,
                            observations=Counter(), wrong_string=0,
                            sole_available_string=0, labeled_string_unavailable=0)
                       for hold in (1, 3, 5) for margin in (0.0, 8.0, 32.0, 64.0)]
    pitch_runs = {}
    lane_runs = [{} for _ in native_policies]
    previous_key = (-1, -1)
    previous_sample = -1
    for source in reader:
        if None in source or any(v is None for v in source.values()):
            raise ValueError("incomplete trace row")
        row = {k: (float(v) if k in float_fields else int(v))
               for k, v in source.items() if k != "base_notes"}
        if not all(math.isfinite(row[k]) for k in float_fields):
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
        if has_lane_costs:
            mask = row["lane_available_mask"]
            if (row["lane_fixed_context"] not in (0, 1) or not 0 <= mask < 256
                    or mask & ~row["free_mask"]
                    or (row["lane_fixed_context"] and
                        not 2 <= row["lane_selected_count"] <= 8)
                    or (not row["lane_fixed_context"] and
                        (mask or row["lane_selected_count"]))
                    or any(row[f"lane_cost_{s}"] != 0.0 for s in range(8)
                           if not mask & (1 << s))):
                raise ValueError("invalid fixed-context lane evidence")
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
        # A fixed, audio-only screen from the prior capture. Persistence counts
        # consecutive sampled rows for the same pitch, not native decisions.
        if row["residual_gain"] < 0.2 or row["independent_energy"] < 0.0001:
            continue
        previous_tick, run = pitch_runs.get(row["note"], (-1, 0))
        run = run + 1 if row["tick"] - previous_tick == capture["decimation"] else 1
        pitch_runs[row["note"]] = (row["tick"], run)
        for hold, counts in persistent_pitch.items():
            if run >= hold:
                counts[truth] += 1
        if not has_lane_costs or not row["lane_fixed_context"]:
            continue
        best, margin = _lane_choice(row)
        if best is None:
            continue
        for policy, runs in zip(native_policies, lane_runs):
            if ((margin is None and policy["margin_floor"] > 0.0) or
                    (margin is not None and margin < policy["margin_floor"])):
                continue
            previous_tick, previous_best, run = runs.get(row["note"], (-1, -1, 0))
            run = (run + 1 if previous_best == best and
                   row["tick"] - previous_tick == capture["decimation"] else 1)
            runs[row["note"]] = (row["tick"], best, run)
            if run < policy["sampled_observations_required"]:
                continue
            policy["observations"][truth] += 1
            policy["sole_available_string"] += margin is None
            if row["expected_note"] and row["expected_mask"]:
                if not row["expected_mask"] & row["lane_available_mask"]:
                    policy["labeled_string_unavailable"] += 1
                elif not row["expected_mask"] & (1 << best):
                    policy["wrong_string"] += 1
    if totals["rows"] != capture["rows"]:
        raise ValueError("trace rows disagree with capture metadata")
    for policy in policies:
        for field in ("observations", "sole_free_string", "calibrated_free_string"):
            policy[field] = {name: policy[field][name] for name in CLASSES}
        counts = policy["observations"]
        policy["expected_pitch_samples"] = (counts["expected_free_string"] +
            counts["expected_unscoped"] + counts["expected_occupied_string"])
        policy["false_pitch_samples"] = counts["wrong_note"] + counts["extra_gap"]
    for policy in native_policies:
        policy["observations"] = {name: policy["observations"][name] for name in CLASSES}
    return dict(
        units="decimated candidate observations, not recovered MIDI frames",
        decimation=capture["decimation"], totals=dict(totals), population=dict(population),
        policies=policies, production_changed=False,
        lane_costs_available=has_lane_costs,
        persistence_screen=dict(gain_floor=0.2, energy_floor=0.0001,
            pitch_observations={str(hold): {name: counts[name] for name in CLASSES}
                                for hold, counts in persistent_pitch.items()},
            native_lane_policies=native_policies if has_lane_costs else [],
            units="Consecutive sampled observations; 3 span 32 native decision ticks."),
        limitation="Fixed-context costs do not simulate admitting a pitch. Counts are not recovered MIDI frames.")
