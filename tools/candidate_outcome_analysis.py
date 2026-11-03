#!/usr/bin/env python3
"""Stream a paired replay outcome trace without loading the audio or trace in RAM.

Labels are used exclusively to score observed outputs. Feature summaries are
diagnostic associations, not counterfactual proof that a new admission rule
would recover the same outputs. Tracking fields describe post-decision state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import TextIO


CANDIDATE_FIELDS_V1 = (
    "note selection active assigned_mask rescue_mask selector_mask "
    "score_ratio fund_ratio band_score band_fund direct local evidence cal_direct "
    "playable_mask cal_mask best_cal second_cal best_string onset phase_valid "
    "phase_cents phase_updates age attack release evidence_ticks evidence_gap "
    "fine_valid fine_mask committed_mask shadow_interval shadow_kind pitch_band"
).split()
CANDIDATE_FIELDS = CANDIDATE_FIELDS_V1 + (
    "selector_pool_member selector_raw_score selector_best_adjusted_score "
    "selector_option_mask selector_positive_mask selector_used_mask "
    "selector_voice_count selector_open_count"
).split()
FLOAT_FIELDS = set(("score_ratio fund_ratio band_score band_fund best_cal second_cal onset phase_cents "
                    "selector_raw_score selector_best_adjusted_score").split())
SCHEMAS = {"# m3_candidate_outcome_v1\n", "# m3_candidate_outcome_v2\n"}
OUTCOMES = ("correct_voice", "wrong_note", "wrong_string", "extra_gap_output")
HEADER = "sample\ttick\tquiet\tsignal_samples\tlabels\tmatched_labels\tvoices\tcandidates\n"
# Native score includes the fundamental with weight 1 plus nonnegative upper
# partials. This fraction is not the score/admission-threshold ratio.
FUNDAMENTAL_SHARE_BINS = (.15, .2, .5, .7, .9, 1)
NATIVE_FUNDAMENTAL_SHARE_FLOOR = .2
RATIO_UNITS = {
    "score_ratio": "candidate score / admission threshold; may exceed one",
    "fund_ratio": "fundamental energy / weighted total harmonic energy; fraction in [0,1]",
}


def _tuples(text: str, width: int) -> list[tuple[int, ...]]:
    result = [tuple(int(x) for x in part.split(":")) for part in text.split(",")] if text else []
    if any(len(row) != width for row in result):
        raise ValueError(f"expected tuple width {width}")
    return result


def _frame(line: str) -> dict:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 8:
        raise ValueError("outcome trace requires eight columns")
    labels = _tuples(parts[4], 3)
    matched = set(int(x) for x in parts[5].split(",")) if parts[5] else set()
    if not matched.issubset({row[0] for row in labels}):
        raise ValueError("matched label is not active")
    voices = _tuples(parts[6], 8)
    if any(row[3] not in range(4) for row in voices):
        raise ValueError("invalid output outcome")
    return dict(sample=int(parts[0]), tick=int(parts[1]), quiet=int(parts[2]),
                signal_samples=int(parts[3]), labels=labels, matched=matched,
                voices=voices, candidate_text=parts[7])


def _candidates(frame: dict) -> dict[int, dict]:
    result = {}
    for item in frame["candidate_text"].split(",") if frame["candidate_text"] else ():
        values = item.split(":")
        fields = (CANDIDATE_FIELDS if len(values) == len(CANDIDATE_FIELDS)
                  else CANDIDATE_FIELDS_V1)
        if len(values) != len(fields):
            raise ValueError("invalid candidate tuple width")
        row = {name: (float(value) if name in FLOAT_FIELDS else int(value))
               for name, value in zip(fields, values)}
        if any(not math.isfinite(row[name]) for name in FLOAT_FIELDS & row.keys()):
            raise ValueError("nonfinite candidate feature")
        if not 0 <= row["fund_ratio"] <= 1:
            raise ValueError("fundamental share must be in [0,1]")
        if not 0 <= row["note"] <= 127 or row["note"] in result:
            raise ValueError("invalid or duplicate candidate note")
        result[row["note"]] = row
    return result


def _bucket(value: float, limits: tuple) -> str:
    for limit in limits:
        if value < limit:
            return f"<{limit:g}"
    return f">={limits[-1]:g}"


def _features(candidate: dict | None, voice: tuple, frame: dict) -> dict[str, str]:
    features = {"quiet": str(frame["quiet"]), "rendered_note": str(voice[1]),
                "detected_note": str(voice[0]), "string": str(voice[2]),
                "shared_group": str(voice[7].bit_count()),
                "rebinned": str(voice[0] != voice[1])}
    if candidate is None:
        features["candidate"] = "missing"
        return features
    c = candidate
    features.update({
        "candidate": "present", "selection": str(c["selection"]),
        "rescue": str(c["rescue_mask"] != 0), "direct": str(c["direct"]),
        "local": str(c["local"]), "evidence": str(c["evidence"]),
        "cal_direct": str(c["cal_direct"]),
        "score_ratio": _bucket(c["score_ratio"], (.3, .4, .6, .8, 1, 1.5, 2)),
        "fund_ratio": _bucket(c["fund_ratio"], FUNDAMENTAL_SHARE_BINS),
        "band_score": _bucket(c["band_score"], (.01, .03, .1, .3, 1)),
        "band_fund": _bucket(c["band_fund"], (.01, .03, .1, .3, 1)),
        "cal_margin": _bucket(c["best_cal"] - c["second_cal"], (.005, .01, .02, .05, .1)),
        "best_cal": _bucket(c["best_cal"], (.8, .9, .95, .98)),
        "best_string_agrees": str(c["best_string"] == voice[2]),
        "onset": _bucket(c["onset"], (.1, .3, .6, 1)),
        "phase_valid": str(c["phase_valid"]),
        "phase_abs_cents": _bucket(abs(c["phase_cents"]), (10, 25, 50, 75, 100)),
        "phase_updates": _bucket(c["phase_updates"], (1, 2, 4, 8, 16)),
        "age": _bucket(c["age"], (2, 10, 50, 100, 500)),
        "release": _bucket(c["release"], (1, 3, 10, 30)),
        "playable_members": str(c["playable_mask"].bit_count()),
        "fine_members": str(c["fine_mask"].bit_count()),
        "committed_members": str(c["committed_mask"].bit_count()),
        "shadow": f'{c["shadow_kind"]}:{c["shadow_interval"]}',
    })
    features["phase_and_score"] = "/".join(features[k] for k in
        ("phase_valid", "phase_abs_cents", "phase_updates", "score_ratio"))
    features["direct_and_calibration"] = "/".join(features[k] for k in
        ("direct", "cal_direct", "best_string_agrees", "cal_margin"))
    return features


def compare_streams(control: TextIO, trial: TextIO,
                    expected_control: dict | None = None,
                    expected_trial: dict | None = None) -> dict:
    for stream in (control, trial):
        if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
            raise ValueError("unsupported outcome trace schema")
    totals = [Counter(), Counter()]
    deltas = Counter()
    axes = defaultdict(Counter)
    label_changes = Counter()
    examples = []
    seen_examples = set()
    last_sample = -1
    for control_line in control:
        trial_line = trial.readline()
        if not trial_line:
            raise ValueError("trial trace is shorter than control")
        frames = [_frame(control_line), _frame(trial_line)]
        a, b = frames
        if (a["sample"], a["tick"], a["labels"]) != (b["sample"], b["tick"], b["labels"]):
            raise ValueError("paired traces do not refer to the same audio and labels")
        if a["sample"] <= last_sample:
            raise ValueError("samples are not strictly increasing")
        last_sample = a["sample"]
        for total, frame in zip(totals, frames):
            total["snapshots"] += 1
            total["labeled"] += len(frame["labels"])
            total["matched"] += len(frame["matched"])
            for voice in frame["voices"]:
                total[OUTCOMES[voice[3]]] += 1
        deltas["quiet_state_changed_frames"] += a["quiet"] != b["quiet"]
        for direction, labels in (("gained", b["matched"] - a["matched"]),
                                  ("lost", a["matched"] - b["matched"])):
            deltas[f"matched_labels_{direction}"] += len(labels)
            for label_id, note, mask in a["labels"]:
                if label_id in labels:
                    label_changes[f"{direction}/note{note}/mask{mask}"] += 1
        identities = [Counter(v[:3] for v in frame["voices"]) for frame in frames]
        if identities[0] == identities[1]:
            continue
        deltas["output_assignment_changed_frames"] += 1
        candidates = [_candidates(frame) for frame in frames]
        for side, direction in ((0, "removed"), (1, "added")):
            differences = identities[side] - identities[1 - side]
            for voice in frames[side]["voices"]:
                identity = voice[:3]
                if differences[identity] <= 0:
                    continue
                differences[identity] -= 1
                outcome = OUTCOMES[voice[3]]
                deltas[f"{direction}/{outcome}"] += 1
                for source, candidate_side in (("control", 0), ("trial", 1)):
                    features = _features(candidates[candidate_side].get(voice[0]), voice, frames[candidate_side])
                    for name, value in features.items():
                        axes[f"{direction}/{source}/{name}/{value}"][outcome] += 1
                key = (direction, outcome, *identity)
                if len(examples) < 128 and key not in seen_examples:
                    seen_examples.add(key)
                    examples.append(dict(sample=a["sample"], tick=a["tick"], direction=direction,
                        outcome=outcome, voice=voice, labels=a["labels"],
                        control=candidates[0].get(voice[0]), trial=candidates[1].get(voice[0])))
    if trial.readline():
        raise ValueError("trial trace is longer than control")
    aliases = {"wrong_note": "false_wrong_note_voices", "wrong_string": "false_wrong_string_voices",
               "extra_gap_output": "false_gap_voices"}
    for total, expected in zip(totals, (expected_control, expected_trial)):
        for original, aggregate in aliases.items():
            total[aggregate] = total[original]
        total["false_positive_voices"] = sum(total[x] for x in aliases)
        if expected is not None:
            for key in ("labeled", "matched", "false_positive_voices", *aliases.values()):
                if total[key] != int(expected[key]):
                    raise ValueError(f"trace/report mismatch for {key}: {total[key]} != {expected[key]}")
    return dict(schema="m3_candidate_outcome_comparison_v2", ratio_units=RATIO_UNITS,
                control=dict(totals[0]), trial=dict(totals[1]),
                changes=dict(deltas), label_changes=dict(label_changes.most_common()),
                feature_outcomes={key: dict(value) for key, value in sorted(axes.items())}, examples=examples,
                limitation="Associations only: state is observed after each decision. A proposed rule requires causal replay.")


def analyze_calibrated_harmonic_admission(stream: TextIO, expected: dict | None = None) -> dict:
    """Measure the existing below-threshold calibration exception at +19.

    This is a screen of captured decisions, not a proposed suppression policy.
    Labels score the screen only. The preceding frame identifies an already
    active candidate because current tracking fields are post-decision.
    """
    if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
        raise ValueError("unsupported outcome trace schema")
    totals = Counter()
    observations = defaultdict(Counter)
    starts = defaultdict(Counter)
    controls = Counter()
    features = defaultdict(Counter)
    examples = defaultdict(list)
    previous_active = set()
    last_sample = -1
    for line in stream:
        frame = _frame(line)
        if frame["sample"] <= last_sample:
            raise ValueError("samples are not strictly increasing")
        has_preceding_frame = last_sample >= 0
        last_sample = frame["sample"]
        candidates = _candidates(frame)
        totals["snapshots"] += 1
        totals["labeled"] += len(frame["labels"])
        totals["matched"] += len(frame["matched"])
        for voice in frame["voices"]:
            totals[OUTCOMES[voice[3]]] += 1
        notes = {note for _, note, _ in frame["labels"]}
        selected_count = sum(c["selection"] == 4 for c in candidates.values())
        for upper_note in sorted(notes):
            if upper_note - 19 not in notes:
                continue
            controls["labeled_plus19_pair_frames"] += 1
            upper = candidates.get(upper_note)
            if upper is not None:
                controls["upper_captured"] += 1
                controls["upper_selected"] += upper["selection"] == 4
                controls["upper_calibrated_direct"] += bool(upper["cal_direct"])
                controls["upper_below_threshold"] += upper["score_ratio"] <= 1
        if not frame["quiet"]:
            for upper in candidates.values():
                lower = candidates.get(upper["note"] - 19)
                if (upper["selection"] != 4 or not upper["cal_direct"] or
                        upper["score_ratio"] > 1 or upper["playable_mask"].bit_count() != 2 or
                        lower is None or lower["selection"] != 4 or not lower["direct"] or
                        lower["score_ratio"] <= upper["score_ratio"]):
                    continue
                upper_fund = upper["score_ratio"] * upper["fund_ratio"]
                lower_fund = lower["score_ratio"] * lower["fund_ratio"]
                if lower_fund <= 0 or upper_fund >= .70 * lower_fund:
                    continue
                if not notes:
                    outcome = "unlabeled_gap"
                elif upper["note"] in notes:
                    outcome = "expected_upper_pitch"
                else:
                    outcome = "unexpected_upper_pitch"
                stage = ("established" if upper["note"] in previous_active else
                         "starting" if has_preceding_frame else "initial_state_unknown")
                observations[stage][outcome] += 1
                active_start = has_preceding_frame and upper["active"] and stage == "starting"
                if active_start:
                    starts[stage][outcome] += 1
                feature_values = {
                    "selected_count": str(selected_count),
                    "same_best_string": str(upper["best_string"] == lower["best_string"]),
                    "fundamental_ratio": _bucket(upper_fund / lower_fund, (.05, .1, .2, .4, .7)),
                    "score_ratio": _bucket(upper["score_ratio"] / lower["score_ratio"], (.05, .1, .2, .4, .7)),
                    "upper_phase_valid": str(upper["phase_valid"]),
                    "lower_phase_valid": str(lower["phase_valid"]),
                    "lower_expected_pitch": str(lower["note"] in notes),
                }
                for name, value in feature_values.items():
                    features[f"{stage}/{name}/{value}"][outcome] += 1
                if active_start and len(examples[outcome]) < 16:
                    examples[outcome].append(dict(sample=frame["sample"], labels=frame["labels"],
                        upper=upper["note"], lower=lower["note"], selected_count=selected_count,
                        upper_score_ratio=upper["score_ratio"], lower_score_ratio=lower["score_ratio"],
                        fundamental_ratio=upper_fund / lower_fund,
                        upper_best_string=upper["best_string"], lower_best_string=lower["best_string"],
                        upper_phase_valid=upper["phase_valid"], lower_phase_valid=lower["phase_valid"]))
        previous_active = {c["note"] for c in candidates.values() if c["active"]}
    aliases = {"wrong_note": "false_wrong_note_voices", "wrong_string": "false_wrong_string_voices",
               "extra_gap_output": "false_gap_voices"}
    for original, aggregate in aliases.items():
        totals[aggregate] = totals[original]
    totals["false_positive_voices"] = sum(totals[x] for x in aliases)
    if expected is not None:
        for key in ("labeled", "matched", "false_positive_voices", *aliases.values()):
            if totals[key] != int(expected[key]):
                raise ValueError(f"trace/report mismatch for {key}: {totals[key]} != {expected[key]}")
    return dict(schema="m3_calibrated_harmonic_admission_v1", totals=dict(totals),
                observations={k: dict(v) for k, v in observations.items()},
                active_starts={k: dict(v) for k, v in starts.items()},
                controls=dict(controls), features={k: dict(v) for k, v in sorted(features.items())},
                examples=dict(examples), ratio_units=RATIO_UNITS,
                limitation="Selected baseline observations only, not recovered MIDI frames. "
                           "Phase validity and reported onset do not prove an independent source. "
                           "Initial active state is unknown; active starts require a preceding frame.")


def analyze_fret_relief(stream: TextIO, expected: dict | None = None) -> dict:
    """Screen fixed, small score relief using baseline selector evidence only.

    Positive atomic groups and calibrated penalty waivers are excluded. Rebuilt
    edge scores must agree with the captured best score before they are scored.
    Labels and rendered state describe outcomes; they never select candidates.
    Counts are candidate observations, not counterfactual MIDI or frame gains.
    """
    if stream.readline() != "# m3_candidate_outcome_v2\n" or stream.readline() != HEADER:
        raise ValueError("fret relief requires outcome trace schema v2")
    if expected and (expected.get("max_fret", 24) != 24 or expected.get("selector_margin", -1) != -1):
        raise ValueError("fret relief requires the baseline 24-fret selector")
    opens = (32, 36, 40, 44, 48, 52, 56, 60)
    caps = (.025, .05)
    totals = Counter()
    exclusions = Counter()
    deficit_bins = Counter()
    probes = defaultdict(Counter)
    last_sample = -1
    for line in stream:
        frame = _frame(line)
        if frame["sample"] <= last_sample:
            raise ValueError("samples are not strictly increasing")
        last_sample = frame["sample"]
        labels = frame["labels"]
        if (len({label[0] for label in labels}) != len(labels) or
                any(not 0 <= note <= 127 or not 0 <= mask <= 255 for _, note, mask in labels)):
            raise ValueError("invalid or duplicate label")
        totals["snapshots"] += 1
        totals["labeled"] += len(labels)
        totals["matched"] += len(frame["matched"])
        for voice in frame["voices"]:
            totals[OUTCOMES[voice[3]]] += 1
        for c in _candidates(frame).values():
            if "selector_pool_member" not in c:
                raise ValueError("fret relief requires v2 candidate fields")
            if (frame["quiet"] or c["selection"] != 3 or not c["selector_pool_member"] or
                    c["selector_positive_mask"] or c["selector_raw_score"] <= 0 or
                    c["score_ratio"] < .2 or not c["direct"] or
                    not (c["local"] or c["evidence"])):
                continue
            totals["eligible_observations"] += 1
            mask, note = c["selector_option_mask"], c["note"]
            if not 0 < mask <= 255 or mask & ~c["playable_mask"]:
                exclusions["invalid_option_mask"] += 1
                continue
            frets = {i: note - open_note for i, open_note in enumerate(opens) if mask & (1 << i)}
            if any(not 0 <= fret <= 24 for fret in frets.values()):
                exclusions["invalid_fret"] += 1
                continue
            scores = {i: c["selector_raw_score"] - (.20 + .005 * fret if fret > 0 and
                      (c["selector_open_count"] >= 2 or note > opens[-1]) else 0)
                      for i, fret in frets.items()}
            best = max(scores.values())
            if best > 1e-9 or abs(best - c["selector_best_adjusted_score"]) > 2e-7:
                exclusions["score_reconstruction_mismatch"] += 1
                continue
            totals["reconstructed_observations"] += 1
            register = "low" if note < 48 else "middle" if note < 60 else "high"
            topology = "single_option" if mask.bit_count() == 1 else "multiple_options"
            # Repeat the native direct-peak energy floor for readable strata.
            # This is not independent evidence or a newly fitted classifier.
            evidence = ("direct_local_native_fundamental" if c["local"] and
                        c["fund_ratio"] >= NATIVE_FUNDAMENTAL_SHARE_FLOOR else "other")
            deficit = -best
            bucket = "le_0.025" if deficit <= .025 else "le_0.05" if deficit <= .05 else "gt_0.05"
            deficit_bins[(register, topology, evidence, bucket)] += 1
            targets = [target for _, pitch, target in labels if pitch == note]
            target_mask = 0
            for target in targets:
                target_mask |= target
            rendered_mask = 0
            for voice in frame["voices"]:
                if voice[1] == note and 0 <= voice[2] < 8:
                    rendered_mask |= 1 << voice[2]
            for cap in caps:
                newly_positive = sum(1 << i for i, score in scores.items() if score + cap > 1e-9)
                if not newly_positive:
                    continue
                if not labels:
                    outcome = "unlabeled_gap_candidate"
                elif not targets:
                    outcome = "unexpected_pitch"
                elif any(target == 0 for target in targets):
                    outcome = "expected_pitch_string_unspecified"
                elif newly_positive & target_mask and newly_positive & ~target_mask:
                    outcome = "mixed_expected_and_wrong_string_options"
                elif not newly_positive & target_mask:
                    outcome = "wrong_string_options_only"
                elif newly_positive & ~rendered_mask:
                    outcome = "expected_options_only_with_missing_lane"
                else:
                    outcome = "expected_options_only_already_rendered"
                probes[(cap, register, topology, evidence)][outcome] += 1
    aliases = {"wrong_note": "false_wrong_note_voices", "wrong_string": "false_wrong_string_voices",
               "extra_gap_output": "false_gap_voices"}
    for original, aggregate in aliases.items():
        totals[aggregate] = totals[original]
    totals["false_positive_voices"] = sum(totals[x] for x in aliases)
    if expected is not None:
        for key in ("labeled", "matched", "false_positive_voices", *aliases.values()):
            if totals[key] != int(expected[key]):
                raise ValueError(f"trace/report mismatch for {key}: {totals[key]} != {expected[key]}")
    return dict(schema="m3_fret_relief_screen_v2", ratio_units=RATIO_UNITS,
                evidence_definition="direct/local candidates with fundamental share >=0.20 repeat "
                                    "the native direct-peak floor; not independent classification evidence",
                totals=dict(totals), exclusions=dict(exclusions),
                deficit_bins=[dict(register=r, topology=t, evidence=e, deficit=b, observations=n)
                              for (r, t, e, b), n in sorted(deficit_bins.items())],
                probes=[dict(cap=cap, register=r, topology=t, evidence=e, outcomes=dict(counts))
                        for (cap, r, t, e), counts in sorted(probes.items())],
                limitation="Fixed baseline M3/24-fret scores; observations only. No DP competition, "
                           "hysteresis or MIDI replay. Positive options are not recovered frames.")


def analyze_candidate_population(stream: TextIO, expected: dict | None = None) -> dict:
    """Score the output-independent, weak-direct population recorded on every frame.

    Admission fields precede selection. Labels score hypotheses but never enter
    a rule. This population does not cover candidates below the capture floor
    or candidates lacking a direct peak. Multi-string labels score pitch support,
    not successful simultaneous string assignment.
    """
    if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
        raise ValueError("unsupported outcome trace schema")
    totals = Counter()
    coverage = Counter()
    axes = defaultdict(Counter)
    rules = defaultdict(Counter)
    labels = defaultdict(Counter)
    runs: dict[int, int] = {}
    last_sample = -1
    for line in stream:
        frame = _frame(line)
        if frame["sample"] <= last_sample:
            raise ValueError("samples are not strictly increasing")
        last_sample = frame["sample"]
        active = frame["labels"]
        if (len({label[0] for label in active}) != len(active) or
                any(not 0 <= note <= 127 or not 0 <= mask <= 255 for _, note, mask in active)):
            raise ValueError("invalid or duplicate label")
        totals["snapshots"] += 1
        totals["labeled"] += len(active)
        totals["matched"] += len(frame["matched"])
        candidates = _candidates(frame)
        # Reapply the unconditional capture predicate. Selected/emitted rows
        # outside this predicate would introduce output-conditioned sampling.
        population = {note: c for note, c in candidates.items()
                      if c["score_ratio"] >= .2 and c["direct"] and
                      (c["local"] or c["evidence"])}
        runs = {note: runs.get(note, 0) + 1 for note in population}
        totals["candidate_observations"] += len(population)
        for label_id, note, mask in active:
            key = f"label{label_id}/note{note}/mask{mask}"
            counts = labels[key]
            counts["labeled"] += 1
            counts["matched"] += label_id in frame["matched"]
            c = population.get(note)
            names = ["present" if c else "absent"]
            if c:
                names.append("weak" if c["score_ratio"] < 1 else "strong")
                if not mask or c["playable_mask"] & mask:
                    names.append("fret_feasible")
                if mask and c["cal_mask"] & mask:
                    names.append("calibration_intersects")
                if (mask and 0 <= c["best_string"] < 8 and
                        c["cal_mask"] & (1 << c["best_string"]) & mask):
                    names.append("best_string_agrees")
            for name in names:
                counts[name] += 1
                coverage[name] += 1
                if label_id not in frame["matched"]:
                    coverage[f"unmatched/{name}"] += 1
        for note, c in population.items():
            matching = [row for row in active if row[1] == note]
            expected_mask = 0
            for _, _, mask in matching:
                expected_mask |= mask
            best_bit = 1 << c["best_string"] if 0 <= c["best_string"] < 8 else 0
            calibrated_best = bool(best_bit & c["cal_mask"] & c["playable_mask"])
            if not active:
                outcome = "unlabeled_gap_candidate"
            elif not matching:
                outcome = "unexpected_pitch"
            elif not expected_mask:
                outcome = "expected_pitch_string_unspecified"
            elif not c["playable_mask"] & expected_mask:
                outcome = "expected_pitch_fret_infeasible"
            elif not calibrated_best:
                outcome = "expected_pitch_no_calibrated_string"
            elif best_bit & expected_mask:
                outcome = "expected_pitch_best_string_agrees"
            else:
                outcome = "expected_pitch_best_string_disagrees"
            totals[outcome] += 1
            margin = c["best_cal"] - c["second_cal"]
            features = {
                "score": _bucket(c["score_ratio"], (.3, .4, .6, .8, 1, 1.5, 2)),
                "fundamental": _bucket(c["fund_ratio"], FUNDAMENTAL_SHARE_BINS),
                "band_score": _bucket(c["band_score"], (.01, .03, .1, .3, 1)),
                "band_fundamental": _bucket(c["band_fund"], (.01, .03, .1, .3, 1)),
                "calibration": _bucket(c["best_cal"], (.8, .9, .95, .98)),
                "calibration_margin": _bucket(margin, (.005, .01, .02, .05, .1)),
                "cal_direct": str(c["cal_direct"]),
                "best_string": str(c["best_string"]),
                "pitch_band": str(note // 12),
                "consecutive_frames": _bucket(runs[note], (3, 10, 30, 100)),
            }
            strength = "weak" if c["score_ratio"] < 1 else "strong"
            for name, value in features.items():
                axes[f"{strength}/{name}/{value}"][outcome] += 1
            # A small, declared family of label-free probes, not a fitted model.
            # None uses selection, emitted voices, phase, onset or group state.
            probes = {"all": True, "fundamental_share_ge_020":
                          c["fund_ratio"] >= NATIVE_FUNDAMENTAL_SHARE_FLOOR,
                      "calibrated_direct": bool(c["cal_direct"]),
                      "calibrated_best_feasible": calibrated_best,
                      "calibration_ge_095_margin_ge_005": calibrated_best and
                          c["best_cal"] >= .95 and margin >= .05,
                      "calibration_ge_095_margin_ge_010": calibrated_best and
                          c["best_cal"] >= .95 and margin >= .1,
                      "fund_share_ge_020_cal_ge_095_margin_ge_010": calibrated_best and
                          c["fund_ratio"] >= NATIVE_FUNDAMENTAL_SHARE_FLOOR and
                          c["best_cal"] >= .95 and margin >= .1,
                      "persistent_10": runs[note] >= 10,
                      "persistent_30": runs[note] >= 30,
                      "persistent_30_cal_ge_095_margin_ge_010": runs[note] >= 30 and
                          calibrated_best and c["best_cal"] >= .95 and margin >= .1}
            for name, passes in probes.items():
                if passes:
                    rules[f"{strength}/{name}"][outcome] += 1
    if expected is not None:
        for key in ("labeled", "matched"):
            if totals[key] != int(expected[key]):
                raise ValueError(f"trace/report mismatch for {key}: {totals[key]} != {expected[key]}")
    return dict(schema="m3_candidate_population_v2", ratio_units=RATIO_UNITS,
                fundamental_probe="The 0.20 share floor repeats native direct-peak support; "
                                  "it is not an independent classifier",
                totals=dict(totals),
                label_coverage=dict(coverage), per_label={k: dict(v) for k, v in labels.items()},
                feature_population={k: dict(v) for k, v in sorted(axes.items())},
                rule_population={k: dict(v) for k, v in sorted(rules.items())},
                population="score/threshold >=0.2, direct peak, and local peak or candidate evidence; selected state ignored",
                limitation="Pre-selection associations only; labels score pitch/string hypotheses, not MIDI. Counts are candidate observations, except label coverage. This excludes weaker/non-direct candidates; unison membership and causal recovery require replay.")


def analyze_label_failures(stream: TextIO, expected: dict | None = None,
                           *, physical_groups: bool = False) -> dict:
    """Attribute observed label failures without proposing a selection policy.

    Legacy totals always follow replay's exact-row metric. Physical-group mode
    attributes one unioned target per active pitch instead, while also counting
    per-row coverage without penalizing explicitly co-labeled strings. Candidate absence
    means not captured, not proof of a low score: the trace records selected,
    active, emitted and weak-direct candidates, rather than every MIDI pitch.
    """
    if stream.readline() not in SCHEMAS or stream.readline() != HEADER:
        raise ValueError("unsupported outcome trace schema")
    selection_names = ("quiet", "below_threshold", "spectral_rejected",
                       "dp_evicted", "selected", "coasting")
    totals = Counter()
    outcomes = Counter()
    axes = defaultdict(Counter)
    per_label = defaultdict(Counter)
    strong_eviction_joint = Counter()
    strong_eviction_selector = Counter()
    examples = []
    example_keys = set()
    last_sample = -1

    def relation(observed: int, target: int) -> str:
        if not target:
            return "target_unspecified"
        if observed == target:
            return "exact"
        if not observed:
            return "none"
        if not observed & target:
            return "disjoint"
        if observed & target == target:
            return "superset"
        return "partial_with_extra" if observed & ~target else "partial"

    for line in stream:
        frame = _frame(line)
        if frame["sample"] <= last_sample:
            raise ValueError("samples are not strictly increasing")
        last_sample = frame["sample"]
        labels = frame["labels"]
        if (len({label[0] for label in labels}) != len(labels) or
                any(not 0 <= note <= 127 or not 0 <= mask <= 255 for _, note, mask in labels)):
            raise ValueError("invalid or duplicate label")
        candidates = _candidates(frame)
        # All selected candidates are captured even before they emit a voice.
        # This is selector occupancy, not the native snapshot's rendered,
        # non-coasting pitch count. Keep those two quantities distinct.
        selected_count = sum(c["selection"] == 4 for c in candidates.values())
        true_pitch_count = len({note for _, note, _ in labels})
        totals["snapshots"] += 1
        totals["labeled"] += len(labels)
        totals["matched"] += len(frame["matched"])
        for voice in frame["voices"]:
            totals[OUTCOMES[voice[3]]] += 1
        targets = {}
        for label_id, note, mask in labels:
            if note not in targets:
                targets[note] = [label_id, 0, False]
            targets[note][1] |= mask
            targets[note][2] |= mask == 0
        # Validate historical counts before changing the unit of attribution.
        # Unknown-string labels do not authorize extra lanes for typed rows.
        for label_id, note, mask in labels:
            rendered = [v for v in frame["voices"] if v[1] == note]
            observed_mask = 0
            for voice in rendered:
                if 0 <= voice[2] < 8:
                    observed_mask |= 1 << voice[2]
            matched = observed_mask == mask if mask else bool(rendered)
            if matched != (label_id in frame["matched"]):
                raise ValueError("rendered lanes disagree with replay matched labels")
            totals["covered_label_frames"] += (
                (observed_mask & mask == mask and
                 observed_mask & ~targets[note][1] == 0)
                if mask else bool(rendered))
        if physical_groups:
            labels = [(leader, note, 0 if note_only else mask)
                      for note, (leader, mask, note_only) in targets.items()]
        for label_id, note, mask in labels:
            rendered = [v for v in frame["voices"] if v[1] == note]
            detected = [v for v in frame["voices"] if v[0] == note]
            observed_mask = 0
            for voice in rendered:
                if 0 <= voice[2] < 8:
                    observed_mask |= 1 << voice[2]
            matched = (observed_mask == mask if mask else
                       bool(observed_mask) if physical_groups else bool(rendered))
            totals["attributed_frames"] += 1
            totals["attributed_matches"] += matched
            if matched:
                outcome = "matched"
            elif not rendered:
                outcome = "no_rendered_pitch"
            elif not observed_mask & mask:
                outcome = "wrong_strings_only"
            elif observed_mask & mask != mask:
                outcome = "partial_expected_strings"
            else:
                outcome = "expected_strings_plus_extra"
            group = f"{mask.bit_count()}_strings" if mask else "string_unspecified"
            outcomes[outcome] += 1
            per_label[f"note{note}/mask{mask}"][outcome] += 1
            c = candidates.get(note)
            if (c and c["selection"] == 3 and c["score_ratio"] >= 1 and
                    outcome == "no_rendered_pitch"):
                strong_eviction_joint[(true_pitch_count, selected_count,
                                       c["playable_mask"].bit_count())] += 1
                if "selector_pool_member" not in c:
                    cause, voices, opens = "not_measured", -1, -1
                else:
                    positive_free = c["selector_positive_mask"] & ~c["selector_used_mask"]
                    cause = ("not_pooled" if not c["selector_pool_member"] else
                             "no_positive_option" if not c["selector_positive_mask"] else
                             "positive_free_option" if positive_free else
                             "positive_options_occupied")
                    voices, opens = c["selector_voice_count"], c["selector_open_count"]
                strong_eviction_selector[(cause, voices, opens)] += 1
            features = {
                "group": group, "quiet": str(frame["quiet"]),
                "signal_present": str(frame["signal_samples"] > 0),
                "rendered_mask": relation(observed_mask, mask),
                "detected_pitch_emitted": str(bool(detected)),
                "detected_pitch_rebinned": str(any(v[1] != note for v in detected)),
                "rendered_from_other_candidate": str(any(v[0] != note for v in rendered)),
                "candidate": "present" if c else "not_captured",
            }
            if c:
                if c["selection"] not in range(len(selection_names)):
                    raise ValueError("invalid candidate selection disposition")
                strength = "strong" if c["score_ratio"] >= 1 else "weak"
                best_bit = 1 << c["best_string"] if 0 <= c["best_string"] < 8 else 0
                features.update({
                    "selection": selection_names[c["selection"]], "strength": strength,
                    "selection_strength": f'{selection_names[c["selection"]]}/{strength}',
                    "signal_strength": f'{frame["signal_samples"] > 0}/{strength}',
                    "score_ratio": _bucket(c["score_ratio"], (.2, .5, 1, 1.5, 2, 4)),
                    "direct_local": f'{c["direct"]}:{c["local"]}',
                    "fund_ratio": _bucket(c["fund_ratio"], FUNDAMENTAL_SHARE_BINS),
                    "active": str(bool(c["active"])),
                    "assigned": relation(c["assigned_mask"], mask),
                    "playable": relation(c["playable_mask"], mask),
                    "fine_valid": str(bool(c["fine_valid"])),
                    "fine": relation(c["fine_mask"], mask),
                    "committed": relation(c["committed_mask"], mask),
                    "best_string": relation(best_bit & c["cal_mask"], mask),
                    "best_cal": _bucket(c["best_cal"], (.8, .9, .95, .98)),
                    "cal_margin": _bucket(c["best_cal"] - c["second_cal"], (.005, .01, .02, .05, .1)),
                    "onset": _bucket(c["onset"], (.1, .3, .6, 1)),
                    "phase_valid": str(bool(c["phase_valid"])),
                    "phase_abs_cents": _bucket(abs(c["phase_cents"]), (10, 25, 50, 75, 100)),
                    "shadow": f'{c["shadow_kind"]}:{c["shadow_interval"]}',
                })
            for name, value in features.items():
                axes[f"{name}/{value}"][outcome] += 1
                axes[f"{group}/{name}/{value}"][outcome] += 1
                axes[f'quiet{frame["quiet"]}/{name}/{value}'][outcome] += 1
                axes[f'{group}/quiet{frame["quiet"]}/{name}/{value}'][outcome] += 1
            key = (outcome, note, mask)
            if outcome != "matched" and key not in example_keys and len(examples) < 64:
                example_keys.add(key)
                examples.append(dict(sample=frame["sample"], outcome=outcome,
                                     label=(label_id, note, mask), voices=frame["voices"], candidate=c))
    aliases = {"wrong_note": "false_wrong_note_voices", "wrong_string": "false_wrong_string_voices",
               "extra_gap_output": "false_gap_voices"}
    for original, aggregate in aliases.items():
        totals[aggregate] = totals[original]
    totals["false_positive_voices"] = sum(totals[x] for x in aliases)
    if expected is not None:
        for key in ("labeled", "matched", "false_positive_voices", *aliases.values()):
            if totals[key] != int(expected[key]):
                raise ValueError(f"trace/report mismatch for {key}: {totals[key]} != {expected[key]}")
        if physical_groups and expected.get("physical_group_diagnostics"):
            native = expected["physical_group_diagnostics"]
            for local, source in (("attributed_frames", "physical_group_labeled"),
                                  ("attributed_matches", "physical_group_matched")):
                if totals[local] != int(native[source]):
                    raise ValueError(f"trace/report mismatch for {source}: {totals[local]} != {native[source]}")
    return dict(schema="m3_label_failures_v3", ratio_units=RATIO_UNITS,
                totals=dict(totals), outcomes=dict(outcomes),
                scoring="physical_group" if physical_groups else "legacy_label",
                feature_outcomes={k: dict(v) for k, v in sorted(axes.items())},
                strong_eviction_joint=[dict(true_pitch_count=k[0],
                    selector_selected_count=k[1], playable_lane_count=k[2], frames=v)
                    for k, v in sorted(strong_eviction_joint.items())],
                strong_eviction_selector=[dict(cause=k[0], dp_voice_count=k[1],
                    open_count=k[2], frames=v) for k, v in sorted(strong_eviction_selector.items())],
                strong_eviction_scope="Only score/threshold >=1, DP-evicted, no rendered target pitch. Selected count includes pre-attack candidates and excludes coasting. Counts follow the declared scoring unit. Selector diagnostics precede fallback/rescue; positive free lanes do not establish capacity or feasibility for an entire atomic group. Legacy traces report not_measured, never zero-valued evidence.",
                per_pitch_mask={k: dict(v) for k, v in sorted(per_label.items())}, examples=examples,
                limitation="Observed failure attribution, not causal recovery. Historical totals stay unchanged. Physical-group attribution unions overlapping same-pitch labels, counts each pitch once and requires the exact combined mask; any note-only row makes that group note-only, matching native diagnostics. Covered rows allow only explicitly co-labeled extra lanes. These scoring units are not interchangeable. Extra outputs are counted separately. Uncaptured candidates have unknown admission state; tracking and group fields are post-decision.")


def analyze_group_failures(stream: TextIO, expected: dict | None = None) -> dict:
    return analyze_label_failures(stream, expected, physical_groups=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.control.open() as a, args.trial.open() as b:
        result = compare_streams(a, b)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
