#!/usr/bin/env python3
"""Audit M3's offline 102-bin unison spectral shadow classifier."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import statistics
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence


FEATURE_COUNT = 102
STRING_COUNT = 8
M3_OPEN_NOTES = (32, 36, 40, 44, 48, 52, 56, 60)
PHASES = ("corridor", "onset", "settled")
POSITIVE_WEIGHT_FLOOR = 1.0e-9
PIVOT_FLOOR = 1.0e-12
MARGIN_THRESHOLDS = (0.0, 0.00025, 0.0005, 0.001, 0.002, 0.005, 0.01)
SINGLE_SOURCE_MARGIN_THRESHOLDS = (
    0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25, 0.30,
)
CANDIDATE_RESCUE_SCORE_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
CANDIDATE_RESCUE_FUNDAMENTAL_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
CANDIDATE_SPECTRAL_POLICIES = (
    ("global", 0.70), ("global", 0.80), ("global", 0.90),
    ("pitch_band", 0.70), ("pitch_band", 0.80),
    ("pitch_band", 0.90),
)
CANDIDATE_SPECTRAL_FUNDAMENTAL_THRESHOLD = 0.60
CANDIDATE_SPECTRAL_ERROR_THRESHOLDS = (0.05, 0.075, 0.10, 0.125, 0.15, 0.20)
CANDIDATE_SPECTRAL_MARGIN_THRESHOLDS = (0.05, 0.075, 0.10, 0.125, 0.15, 0.20)
SELECTION_DISPOSITIONS = (
    "quiet", "below_threshold", "spectral_rejected", "dp_evicted",
    "selected", "coasting",
)


@dataclass(frozen=True)
class Classification:
    valid: bool = False
    member_mask: int = 0
    member_count: int = 0
    residual: float = math.inf
    runner_up_residual: float = math.inf
    margin: float = 0.0
    weights: tuple[float, ...] = ()
    disposition: str = "invalid"


def _integer(row: Mapping[str, object], field: str, default: int = 0) -> int:
    value = row.get(field, default)
    return int(value) if value not in (None, "") else default


def _normalized(values: Sequence[float]) -> list[float]:
    if len(values) != FEATURE_COUNT:
        raise ValueError("spectral fingerprint has the wrong size")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("spectral fingerprint must be finite and nonnegative")
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("spectral fingerprint has zero energy")
    return [value / norm for value in values]


def parse_fingerprint(text: str) -> list[float]:
    if not text:
        raise ValueError("spectral fingerprint is empty")
    try:
        values = [float(value) for value in text.split(",")]
    except ValueError as error:
        raise ValueError("spectral fingerprint is not numeric") from error
    if len(values) != FEATURE_COUNT:
        raise ValueError("spectral fingerprint has the wrong size")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("spectral fingerprint must be finite and nonnegative")
    if not any(value > 0.0 for value in values):
        raise ValueError("spectral fingerprint has zero energy")
    return values


def read_replay_details(path: pathlib.Path) -> list[dict[str, str]]:
    with pathlib.Path(path).open(newline="", encoding="utf-8") as stream:
        if not stream.readline() or not stream.readline():
            raise ValueError(f"{path}: replay details have no aggregate rows")
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path}: replay details have no header")
        required = {
            "start_sample",
            "end_sample",
            "midi_note",
            "string_mask",
            "spectral_corridor_frames",
            "spectral_corridor_mean",
        }
        if not required.issubset(reader.fieldnames):
            missing = ", ".join(sorted(required.difference(reader.fieldnames)))
            raise ValueError(f"{path}: missing replay detail fields: {missing}")
        return [dict(row) for row in reader]


def read_replay_aggregate(path: pathlib.Path) -> dict[str, str]:
    with pathlib.Path(path).open(newline="", encoding="utf-8") as stream:
        keys = next(csv.reader([stream.readline().rstrip("\n")], delimiter="\t"))
        values = next(csv.reader([stream.readline().rstrip("\n")], delimiter="\t"))
    if not keys or len(keys) != len(values):
        raise ValueError(f"{path}: malformed replay aggregate rows")
    return dict(zip(keys, values))


def _componentwise_median(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise ValueError("cannot form a template from no fingerprints")
    return _normalized(
        [statistics.median(vector[index] for vector in vectors)
         for index in range(FEATURE_COUNT)]
    )


TemplateKey = tuple[int, int]
TemplatePhases = dict[str, list[float]]
TemplateSet = dict[TemplateKey, TemplatePhases]


def build_template_sets(
    corpora: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, TemplateSet]:
    """Build robust string/fret templates and a cross-corpus blend."""
    result: dict[str, TemplateSet] = {}
    for identity, rows in corpora.items():
        grouped: dict[tuple[TemplateKey, str], list[list[float]]] = {}
        for row in rows:
            mask = _integer(row, "string_mask")
            if mask <= 0 or mask >= (1 << STRING_COUNT) or mask & (mask - 1):
                continue
            lane = mask.bit_length() - 1
            note = _integer(row, "midi_note", -1)
            if note < M3_OPEN_NOTES[lane] or note > M3_OPEN_NOTES[lane] + 24:
                continue
            for phase in PHASES:
                if _integer(row, f"spectral_{phase}_frames") <= 0:
                    continue
                text = str(row.get(f"spectral_{phase}_mean", ""))
                if not text:
                    continue
                grouped.setdefault(((lane, note), phase), []).append(
                    parse_fingerprint(text)
                )
        templates: TemplateSet = {}
        for (key, phase), vectors in grouped.items():
            templates.setdefault(key, {})[phase] = _componentwise_median(vectors)
        if templates:
            result[identity] = templates

    blended: TemplateSet = {}
    keys = sorted({key for templates in result.values() for key in templates})
    for key in keys:
        for phase in PHASES:
            vectors = [
                templates[key][phase]
                for templates in result.values()
                if key in templates and phase in templates[key]
            ]
            if vectors:
                blended.setdefault(key, {})[phase] = _componentwise_median(vectors)
    if blended:
        result["blended"] = blended
    return result


def write_template_bank(templates: TemplateSet, path: pathlib.Path) -> None:
    lines = ["phase\tmidi_note\tstring_index\tfingerprint"]
    for (lane, note), phases in sorted(templates.items()):
        for phase in PHASES:
            if phase not in phases:
                continue
            fingerprint = _normalized(phases[phase])
            lines.append(
                f"{phase}\t{note}\t{lane}\t"
                + ",".join(f"{value:.17g}" for value in fingerprint)
            )
    if len(lines) == 1:
        raise ValueError("template bank is empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _solve(matrix: list[list[float]], right: list[float]) -> list[float] | None:
    size = len(right)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) <= PIVOT_FLOOR:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        right[column], right[pivot] = right[pivot], right[column]
        divisor = matrix[column][column]
        matrix[column] = [value / divisor for value in matrix[column]]
        right[column] /= divisor
        for row in range(size):
            if row == column:
                continue
            multiplier = matrix[row][column]
            matrix[row] = [
                value - multiplier * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[column])
            ]
            right[row] -= multiplier * right[column]
    return right


def _popcount(value: int) -> int:
    return value.bit_count()


def _disposition(expected: int | None, observed: int) -> str:
    if expected is None:
        return "unlabeled"
    if observed == expected:
        return "exact"
    overlap = observed & expected
    if overlap == observed:
        return "subset"
    if overlap == expected:
        return "superset"
    return "overlap" if overlap else "disjoint"


def classify_feasible_masks(
    observed: Sequence[float], templates: Mapping[int, Sequence[float]],
    midi_note: int, minimum_members: int = 2, maximum_members: int = 4,
    *, expected_mask: int | None = None,
) -> Classification:
    if not 2 <= minimum_members <= maximum_members <= 4:
        raise ValueError("member bounds must remain within two through four")
    observed_norm = _normalized(observed)
    normalized_templates: dict[int, list[float]] = {}
    playable_mask = 0
    for lane, fingerprint in templates.items():
        if not 0 <= lane < STRING_COUNT:
            raise ValueError("template lane is out of range")
        fret = midi_note - M3_OPEN_NOTES[lane]
        if 0 <= fret <= 24:
            normalized_templates[lane] = _normalized(fingerprint)
            playable_mask |= 1 << lane

    fits: list[tuple[float, int, tuple[float, ...]]] = []
    for mask in range(1, 1 << STRING_COUNT):
        count = _popcount(mask)
        if not minimum_members <= count <= maximum_members or mask & ~playable_mask:
            continue
        members = [lane for lane in range(STRING_COUNT) if mask & (1 << lane)]
        columns = [normalized_templates[lane] for lane in members]
        gram = [
            [sum(a * b for a, b in zip(left, right)) for right in columns]
            for left in columns
        ]
        correlation = [
            sum(value * target for value, target in zip(column, observed_norm))
            for column in columns
        ]
        weights = _solve([row[:] for row in gram], correlation[:])
        if weights is None or any(
            not math.isfinite(weight) or weight <= POSITIVE_WEIGHT_FLOOR
            for weight in weights
        ):
            continue
        residual = sum(
            (target - sum(weight * column[index]
                          for weight, column in zip(weights, columns))) ** 2
            for index, target in enumerate(observed_norm)
        )
        if math.isfinite(residual):
            expanded = [0.0] * STRING_COUNT
            for lane, weight in zip(members, weights):
                expanded[lane] = weight
            fits.append((residual, mask, tuple(expanded)))
    if not fits:
        return Classification()
    fits.sort(key=lambda item: (item[0], item[1]))
    residual, mask, weights = fits[0]
    runner_up = fits[1][0] if len(fits) > 1 else math.inf
    return Classification(
        valid=True,
        member_mask=mask,
        member_count=_popcount(mask),
        residual=residual,
        runner_up_residual=runner_up,
        margin=runner_up - residual,
        weights=weights,
        disposition=_disposition(expected_mask, mask),
    )


def _histogram(text: object) -> dict[int, int]:
    result: dict[int, int] = {}
    if text in (None, ""):
        return result
    for item in str(text).split(","):
        key, separator, value = item.partition(":")
        if not separator:
            raise ValueError("invalid replay histogram")
        mask, count = int(key), int(value)
        if not 0 <= mask < (1 << STRING_COUNT) or count < 0:
            raise ValueError("replay histogram is out of range")
        result[mask] = result.get(mask, 0) + count
    return result


def _joint_histogram(text: object) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    if text in (None, ""):
        return result
    for item in str(text).split(","):
        key, separator, value = item.partition(":")
        row, dot, column = key.partition(".")
        if not separator or not dot:
            raise ValueError("invalid replay joint histogram")
        pair = (int(row), int(column))
        count = int(value)
        if pair[0] < 0 or pair[1] < 0 or count < 0:
            raise ValueError("replay joint histogram is out of range")
        result[pair] = result.get(pair, 0) + count
    return result


def _json_joint_histogram(text: object) -> dict[str, int]:
    return {
        f"{row}.{column}": count
        for (row, column), count in _joint_histogram(text).items()
    }


def _candidate_population_summary(
    aggregates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Measure target admission against every competing playable pitch."""
    required = {
        "candidate_population_labeled_snapshots",
        "candidate_population_target_dispositions",
        "candidate_population_other_dispositions",
        "candidate_population_target_score_ratio_bins",
        "candidate_population_other_score_ratio_bins",
        "candidate_population_target_below_score_ratio_bins",
        "candidate_population_other_below_score_ratio_bins",
        "candidate_population_target_below_fundamental_ratio_bins",
        "candidate_population_other_below_fundamental_ratio_bins",
        "candidate_population_target_below_evidence_flags",
        "candidate_population_other_below_evidence_flags",
        "candidate_population_target_below_direct_evidence_bins",
        "candidate_population_other_below_direct_evidence_bins",
    }
    if not aggregates or any(
        not required.issubset(aggregate) for aggregate in aggregates
    ):
        return {"available": False}

    def combined(field: str) -> dict[int, int]:
        output: dict[int, int] = {}
        for aggregate in aggregates:
            for key, count in _histogram(aggregate.get(field, "")).items():
                output[key] = output.get(key, 0) + count
        return output

    def combined_joint(field: str) -> dict[tuple[int, int], int]:
        output: dict[tuple[int, int], int] = {}
        for aggregate in aggregates:
            for key, count in _joint_histogram(
                aggregate.get(field, "")
            ).items():
                output[key] = output.get(key, 0) + count
        return output

    labeled_snapshots = sum(
        int(aggregate["candidate_population_labeled_snapshots"])
        for aggregate in aggregates
    )
    classes: dict[str, dict[str, object]] = {}
    direct: dict[str, dict[tuple[int, int], int]] = {}
    pitch_band: dict[str, dict[tuple[int, int], int]] = {}
    pitch_band_available = all(
        all(
            f"candidate_population_{name}_below_pitch_band_peak_bins"
            in aggregate
            for aggregate in aggregates
        )
        for name in ("target", "other")
    )
    for name in ("target", "other"):
        dispositions = combined(
            f"candidate_population_{name}_dispositions"
        )
        below_score = combined(
            f"candidate_population_{name}_below_score_ratio_bins"
        )
        direct[name] = combined_joint(
            f"candidate_population_{name}_below_direct_evidence_bins"
        )
        pitch_band[name] = (
            combined_joint(
                f"candidate_population_{name}_below_pitch_band_peak_bins"
            )
            if pitch_band_available
            else {}
        )
        spectral_field = (
            f"candidate_population_{name}_spectral_head_vote_masks"
        )
        classes[name] = {
            "candidate_frames": sum(dispositions.values()),
            "dispositions": dispositions,
            "score_threshold_ratio_bins": combined(
                f"candidate_population_{name}_score_ratio_bins"
            ),
            "below_threshold_candidates": sum(below_score.values()),
            "below_threshold_score_ratio_bins": below_score,
            "below_threshold_fundamental_ratio_bins": combined(
                f"candidate_population_{name}_below_fundamental_ratio_bins"
            ),
            "below_threshold_evidence_flags": combined(
                f"candidate_population_{name}_below_evidence_flags"
            ),
            "below_threshold_direct_evidence_bins": {
                f"{score}.{fundamental}": count
                for (score, fundamental), count in sorted(direct[name].items())
            },
            "below_threshold_pitch_band_peak_bins": {
                f"{score}.{fundamental}": count
                for (score, fundamental), count
                in sorted(pitch_band[name].items())
            },
            "spectral_head_vote_masks": (
                combined(spectral_field)
                if all(spectral_field in aggregate for aggregate in aggregates)
                else {}
            ),
        }

    target_below = int(classes["target"]["below_threshold_candidates"])
    candidates: list[dict[str, object]] = []
    pitch_band_candidates: list[dict[str, object]] = []
    for score_threshold in CANDIDATE_RESCUE_SCORE_THRESHOLDS:
        score_bin = int(round(score_threshold * 20.0))
        for fundamental_threshold in CANDIDATE_RESCUE_FUNDAMENTAL_THRESHOLDS:
            fundamental_bin = int(round(fundamental_threshold * 20.0))
            target = sum(
                count for (score, fundamental), count in direct["target"].items()
                if score >= score_bin and fundamental >= fundamental_bin
            )
            other = sum(
                count for (score, fundamental), count in direct["other"].items()
                if score >= score_bin and fundamental >= fundamental_bin
            )
            total = target + other
            candidates.append({
                "minimum_score_ratio": score_threshold,
                "minimum_fundamental_ratio": fundamental_threshold,
                "target_candidates": target,
                "other_candidates": other,
                "precision": target / total if total else None,
                "target_recall": target / target_below if target_below else 0.0,
                "other_candidates_per_labeled_snapshot": (
                    other / labeled_snapshots if labeled_snapshots else 0.0
                ),
            })
            pitch_target = sum(
                count for (score, fundamental), count
                in pitch_band["target"].items()
                if score >= score_bin and fundamental >= fundamental_bin
            )
            pitch_other = sum(
                count for (score, fundamental), count
                in pitch_band["other"].items()
                if score >= score_bin and fundamental >= fundamental_bin
            )
            pitch_total = pitch_target + pitch_other
            pitch_band_candidates.append({
                "minimum_pitch_band_score_peak_ratio": score_threshold,
                "minimum_pitch_band_fundamental_peak_ratio": (
                    fundamental_threshold
                ),
                "target_candidates": pitch_target,
                "other_candidates": pitch_other,
                "precision": (
                    pitch_target / pitch_total if pitch_total else None
                ),
                "target_recall": (
                    pitch_target / target_below if target_below else 0.0
                ),
                "other_candidates_per_labeled_snapshot": (
                    pitch_other / labeled_snapshots
                    if labeled_snapshots else 0.0
                ),
            })
    return {
        "available": True,
        "labeled_snapshots": labeled_snapshots,
        "target": classes["target"],
        "other": classes["other"],
        "rescue_thresholds": candidates,
        "pitch_band_available": pitch_band_available,
        "pitch_band_rescue_thresholds": pitch_band_candidates,
    }


def _candidate_spectral_admission_summary(
    aggregates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Summarize the label-independent all-candidate admission shadow."""
    required = {
        "candidate_spectral_shadow_active_peak",
        "candidate_spectral_shadow_candidate_frames",
        "candidate_spectral_shadow_ready_frames",
        "candidate_spectral_shadow_selected_frames",
        "candidate_spectral_shadow_target_correct_frames",
        "candidate_spectral_shadow_target_wrong_string_frames",
        "candidate_spectral_shadow_other_false_frames",
    }
    if not aggregates or any(
        not required.issubset(aggregate) for aggregate in aggregates
    ):
        return {"available": False}

    def combined(field: str) -> dict[tuple[int, int], int]:
        output: dict[tuple[int, int], int] = {}
        for aggregate in aggregates:
            for key, count in _joint_histogram(aggregate.get(field, "")).items():
                output[key] = output.get(key, 0) + count
        return output

    candidate = combined("candidate_spectral_shadow_candidate_frames")
    ready = combined("candidate_spectral_shadow_ready_frames")
    selected = combined("candidate_spectral_shadow_selected_frames")
    correct = combined("candidate_spectral_shadow_target_correct_frames")
    wrong_string = combined(
        "candidate_spectral_shadow_target_wrong_string_frames"
    )
    other_false = combined("candidate_spectral_shadow_other_false_frames")
    interval_diagnostics_available = all(
        "candidate_spectral_shadow_other_false_intervals" in aggregate
        for aggregate in aggregates
    )
    false_intervals = (
        combined("candidate_spectral_shadow_other_false_intervals")
        if interval_diagnostics_available else {}
    )
    gates: list[dict[str, object]] = []
    for policy_index, (normalization, minimum_score) in enumerate(
        CANDIDATE_SPECTRAL_POLICIES
    ):
        for error_index, maximum_error in enumerate(
            CANDIDATE_SPECTRAL_ERROR_THRESHOLDS
        ):
            for margin_index, minimum_margin in enumerate(
                CANDIDATE_SPECTRAL_MARGIN_THRESHOLDS
            ):
                gate_index = (
                    error_index * len(CANDIDATE_SPECTRAL_MARGIN_THRESHOLDS)
                    + margin_index
                )
                key = (policy_index, gate_index)
                selected_frames = selected.get(key, 0)
                correct_frames = correct.get(key, 0)
                wrong_frames = wrong_string.get(key, 0)
                false_frames = other_false.get(key, 0)
                flattened_gate = (
                    policy_index
                    * len(CANDIDATE_SPECTRAL_ERROR_THRESHOLDS)
                    * len(CANDIDATE_SPECTRAL_MARGIN_THRESHOLDS)
                    + gate_index
                )
                interval_histogram = {
                    bucket - 48: count
                    for (row, bucket), count in false_intervals.items()
                    if row == flattened_gate
                }
                if selected_frames != correct_frames + wrong_frames + false_frames:
                    raise ValueError(
                        "candidate spectral admission accounting is inconsistent"
                    )
                if (interval_diagnostics_available and
                        sum(interval_histogram.values()) != false_frames):
                    raise ValueError(
                        "candidate spectral false-interval accounting is inconsistent"
                    )
                gates.append({
                    "policy_index": policy_index,
                    "normalization": normalization,
                    "gate_index": gate_index,
                    "minimum_score_ratio": minimum_score,
                    "minimum_fundamental_ratio": (
                        CANDIDATE_SPECTRAL_FUNDAMENTAL_THRESHOLD
                    ),
                    "maximum_error": maximum_error,
                    "minimum_margin": minimum_margin,
                    "selected_frames": selected_frames,
                    "target_correct_frames": correct_frames,
                    "target_wrong_string_frames": wrong_frames,
                    "other_false_frames": false_frames,
                    "other_false_intervals": interval_histogram,
                    "precision": (
                        correct_frames / selected_frames
                        if selected_frames else None
                    ),
                })
    return {
        "available": True,
        "false_interval_diagnostics_available": (
            interval_diagnostics_available
        ),
        "active_peak": max(
            int(aggregate["candidate_spectral_shadow_active_peak"])
            for aggregate in aggregates
        ),
        "policies": [
            {
                "policy_index": policy_index,
                "normalization": normalization,
                "minimum_score_ratio": minimum_score,
                "minimum_fundamental_ratio": (
                    CANDIDATE_SPECTRAL_FUNDAMENTAL_THRESHOLD
                ),
                "target_candidate_frames": candidate.get((policy_index, 0), 0),
                "other_candidate_frames": candidate.get((policy_index, 1), 0),
                "target_ready_frames": ready.get((policy_index, 0), 0),
                "other_ready_frames": ready.get((policy_index, 1), 0),
            }
            for policy_index, (normalization, minimum_score) in enumerate(
                CANDIDATE_SPECTRAL_POLICIES
            )
        ],
        "gates": gates,
    }


def _single_source_summary(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Summarize the exact-one-string classifier without double-counting unisons."""
    grouped: dict[tuple[int, int, int], list[Mapping[str, object]]] = {}
    for row in rows:
        key = (
            _integer(row, "start_sample"),
            _integer(row, "end_sample"),
            _integer(row, "midi_note"),
        )
        grouped.setdefault(key, []).append(row)

    def blank() -> dict[str, object]:
        return {
            "group_count": 0,
            "frames": 0,
            "invalid_frames": 0,
            "correct_frames": 0,
            "other_frames": 0,
            "accuracy": None,
            "selection": {
                name: {"invalid": 0, "correct": 0, "other": 0}
                for name in SELECTION_DISPOSITIONS
            },
            "margin_thresholds": [
                {
                    "minimum_margin": threshold,
                    "correct_frames": 0,
                    "other_frames": 0,
                    "precision": None,
                    "coverage": 0.0,
                }
                for threshold in SINGLE_SOURCE_MARGIN_THRESHOLDS
            ],
        }

    buckets = {"ordinary": blank(), "multi_string": blank()}
    available = False
    for grouped_rows in grouped.values():
        row = grouped_rows[0]
        if "spectral_single_group_correct_error_bins" not in row:
            continue
        available = True
        expected_mask = 0
        for item in grouped_rows:
            expected_mask |= _integer(item, "string_mask")
        bucket_name = "ordinary" if _popcount(expected_mask) <= 1 else "multi_string"
        bucket = buckets[bucket_name]
        bucket["group_count"] = int(bucket["group_count"]) + 1
        frames = _integer(row, "spectral_single_frames")
        invalid = _integer(row, "spectral_single_invalid")
        correct_error = _histogram(
            row.get("spectral_single_group_correct_error_bins", "")
        )
        other_error = _histogram(
            row.get("spectral_single_group_other_error_bins", "")
        )
        correct = sum(correct_error.values())
        other = sum(other_error.values())
        if correct + other + invalid != frames:
            raise ValueError("single-source frame accounting is inconsistent")
        bucket["frames"] = int(bucket["frames"]) + frames
        bucket["invalid_frames"] = int(bucket["invalid_frames"]) + invalid
        bucket["correct_frames"] = int(bucket["correct_frames"]) + correct
        bucket["other_frames"] = int(bucket["other_frames"]) + other

        selection = _joint_histogram(
            row.get(
                "spectral_single_group_selection_dispositions",
                row.get("spectral_single_selection_dispositions", ""),
            )
        )
        selection_output = bucket["selection"]
        assert isinstance(selection_output, dict)
        for disposition, name in enumerate(SELECTION_DISPOSITIONS):
            values = selection_output[name]
            values["invalid"] += selection.get((disposition, 0), 0)
            values["correct"] += selection.get((disposition, 1), 0)
            values["other"] += selection.get((disposition, 2), 0)

        correct_margin = _histogram(
            row.get("spectral_single_group_correct_margin_bins", "")
        )
        other_margin = _histogram(
            row.get("spectral_single_group_other_margin_bins", "")
        )
        threshold_output = bucket["margin_thresholds"]
        assert isinstance(threshold_output, list)
        for record in threshold_output:
            threshold_bin = int(round(float(record["minimum_margin"]) * 40.0))
            record["correct_frames"] += sum(
                count for index, count in correct_margin.items()
                if index >= threshold_bin
            )
            record["other_frames"] += sum(
                count for index, count in other_margin.items()
                if index >= threshold_bin
            )

    for bucket in buckets.values():
        classified = int(bucket["correct_frames"]) + int(bucket["other_frames"])
        bucket["accuracy"] = (
            int(bucket["correct_frames"]) / classified if classified else None
        )
        frames = int(bucket["frames"])
        threshold_output = bucket["margin_thresholds"]
        assert isinstance(threshold_output, list)
        for record in threshold_output:
            classified_at_threshold = (
                int(record["correct_frames"]) + int(record["other_frames"])
            )
            record["precision"] = (
                int(record["correct_frames"]) / classified_at_threshold
                if classified_at_threshold else None
            )
            record["coverage"] = (
                classified_at_threshold / frames if frames else 0.0
            )
    return {
        "available": available,
        "group_count": sum(int(bucket["group_count"]) for bucket in buckets.values()),
        **buckets,
    }


def _sequence(
    text: object,
    converter: type[int] | type[float],
    expected_length: int = 7,
) -> list[int] | list[float]:
    if text in (None, ""):
        return []
    try:
        result = [converter(value) for value in str(text).split(",")]
    except ValueError as error:
        raise ValueError("invalid replay sequence") from error
    if len(result) != expected_length or any(
        not math.isfinite(float(value)) or float(value) < 0.0
        for value in result
    ):
        raise ValueError("replay sequence is out of range")
    return result


def _dominant_mask(row: Mapping[str, object], field: str) -> int | None:
    histogram = _histogram(row.get(field, ""))
    if not histogram:
        return None
    return min(histogram, key=lambda mask: (-histogram[mask], mask))


def _classification_record(
    result: Classification, row: Mapping[str, object], expected_mask: int,
) -> dict[str, object]:
    fitted = result.member_mask if result.valid else 0
    fine = _dominant_mask(row, "fine_frequency_member_masks")
    profile = _dominant_mask(row, "profile_unison_proposal_masks")
    temporal = _dominant_mask(row, "temporal_unison_proposal_masks")
    observed = _dominant_mask(row, "observed_note_lane_masks")
    return {
        "valid": result.valid,
        "fitted_mask": fitted,
        "member_count": result.member_count,
        "residual": result.residual if math.isfinite(result.residual) else None,
        "runner_up_residual": (
            result.runner_up_residual
            if math.isfinite(result.runner_up_residual) else None
        ),
        "posterior_margin": result.margin if math.isfinite(result.margin) else None,
        "disposition": _disposition(expected_mask, fitted) if result.valid else "invalid",
        "fine_mask": fine,
        "profile_mask": profile,
        "temporal_mask": temporal,
        "current_assignment_mask": observed,
        "disagrees_with_fine": fine is not None and fitted != fine,
        "disagrees_with_profile": profile is not None and fitted != profile,
        "disagrees_with_temporal": temporal is not None and fitted != temporal,
        "disagrees_with_current_assignment": observed is not None and fitted != observed,
    }


def _tier_completion_records(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Aggregate per-frame tier projections without duplicating note groups."""
    available = [
        row for row in rows
        if row.get("spectral_tier_completion_margin_thresholds", "") not in
        (None, "")
    ]
    if not available:
        return []
    if len(available) != len(rows):
        raise ValueError("tier completion diagnostics are incomplete")
    records = [
        {
            "margin_threshold": threshold,
            "changed_frames": 0,
            "exact_group_frames": 0,
            "matched_label_frames": 0,
            "wrong_string_voices": 0,
        }
        for threshold in MARGIN_THRESHOLDS
    ]
    for row in rows:
        thresholds = _sequence(
            row.get("spectral_tier_completion_margin_thresholds", ""), float
        )
        if thresholds != list(MARGIN_THRESHOLDS):
            raise ValueError("tier completion thresholds drifted")
        fields = {
            "changed_frames": _sequence(
                row.get("spectral_tier_completion_changed", ""), int
            ),
            "exact_group_frames": _sequence(
                row.get("spectral_tier_completion_exact", ""), int
            ),
            "matched_label_frames": _sequence(
                row.get("spectral_tier_completion_matched", ""), int
            ),
            "wrong_string_voices": _sequence(
                row.get("spectral_tier_completion_wrong_strings", ""), int
            ),
        }
        if not all(fields.values()):
            raise ValueError("tier completion sequence is missing")
        for index, record in enumerate(records):
            for field, values in fields.items():
                record[field] = int(record[field]) + int(values[index])
    return records


def _onset_latch_records(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Aggregate the causal onset-mask projection for one or more labels."""
    available = [
        row for row in rows
        if row.get("spectral_onset_latch_projected_frames", "") not in
        (None, "")
    ]
    if not available:
        return []
    if len(available) != len(rows):
        raise ValueError("onset latch diagnostics are incomplete")
    records = [
        {
            "margin_threshold": threshold,
            "committed_mask": 0,
            "qualified_votes": 0,
            "winner_votes": 0,
            "projected_frames": 0,
            "changed_frames": 0,
            "exact_group_frames": 0,
            "matched_label_frames": 0,
            "wrong_string_voices": 0,
        }
        for threshold in MARGIN_THRESHOLDS
    ]
    group_values: dict[str, list[int]] | None = None
    for row_index, row in enumerate(rows):
        values = {
            "committed_mask": _sequence(
                row.get("spectral_onset_latch_committed_masks", ""), int
            ),
            "qualified_votes": _sequence(
                row.get("spectral_onset_latch_qualified_votes", ""), int
            ),
            "winner_votes": _sequence(
                row.get("spectral_onset_latch_winner_votes", ""), int
            ),
            "projected_frames": _sequence(
                row.get("spectral_onset_latch_projected_frames", ""), int
            ),
            "changed_frames": _sequence(
                row.get("spectral_onset_latch_changed", ""), int
            ),
            "exact_group_frames": _sequence(
                row.get("spectral_onset_latch_exact", ""), int
            ),
            "matched_label_frames": _sequence(
                row.get("spectral_onset_latch_matched", ""), int
            ),
            "wrong_string_voices": _sequence(
                row.get("spectral_onset_latch_wrong_strings", ""), int
            ),
        }
        if not all(values.values()):
            raise ValueError("onset latch sequence is missing")
        if group_values is None:
            group_values = {
                field: list(values[field])
                for field in (
                    "committed_mask", "qualified_votes", "winner_votes",
                    "projected_frames",
                )
            }
        else:
            for field in group_values:
                if values[field] != group_values[field]:
                    raise ValueError(f"onset latch {field} disagrees within group")
        for index, record in enumerate(records):
            if row_index == 0:
                for field in (
                    "committed_mask", "qualified_votes", "winner_votes",
                    "projected_frames", "changed_frames",
                ):
                    record[field] = int(values[field][index])
            for field in (
                "exact_group_frames", "matched_label_frames",
                "wrong_string_voices",
            ):
                record[field] = int(record[field]) + int(values[field][index])
    return records


def audit_shadow(
    corpora: Mapping[str, Sequence[Mapping[str, object]]],
    template_sets: Mapping[str, TemplateSet],
) -> dict[str, object]:
    output: dict[str, object] = {
        "schema": 1,
        "feature_count": FEATURE_COUNT,
        "template_identities": sorted(template_sets),
        "corpora": {},
    }
    corpus_output: dict[str, object] = output["corpora"]  # type: ignore[assignment]
    preferred_identity = "blended" if "blended" in template_sets else next(
        iter(template_sets), None
    )
    for corpus_name, rows in corpora.items():
        groups: dict[tuple[int, int, int], list[Mapping[str, object]]] = {}
        for row in rows:
            key = (
                _integer(row, "start_sample"),
                _integer(row, "end_sample"),
                _integer(row, "midi_note"),
            )
            groups.setdefault(key, []).append(row)
        cases: list[dict[str, object]] = []
        exact_cases = 0
        exact_labeled_frames = 0
        current_exact_frames = 0
        bounded_secondary = [
            {
                "margin_threshold": threshold,
                "changed_frames": 0,
                "exact_group_frames": 0,
                "matched_label_frames": 0,
                "wrong_string_voices": 0,
            }
            for threshold in MARGIN_THRESHOLDS
        ]
        onset_latch_projection = [
            {
                "margin_threshold": threshold,
                "changed_frames": 0,
                "exact_group_frames": 0,
                "matched_label_frames": 0,
                "wrong_string_voices": 0,
            }
            for threshold in MARGIN_THRESHOLDS
        ]
        for (start, end, note), grouped_rows in sorted(groups.items()):
            expected_mask = 0
            for row in grouped_rows:
                expected_mask |= _integer(row, "string_mask")
            members = _popcount(expected_mask)
            if not 2 <= members <= 4:
                continue
            row = grouped_rows[0]
            case: dict[str, object] = {
                "start_sample": start,
                "end_sample": end,
                "midi_note": note,
                "expected_mask": expected_mask,
                "member_count": members,
                "labeled_frames": _integer(row, "labeled"),
                "current_matched_frames": min(
                    (_integer(item, "matched") for item in grouped_rows),
                    default=0,
                ),
                "identities": {},
            }
            tier_completion = _tier_completion_records(grouped_rows)
            if tier_completion:
                case["tier_completion"] = tier_completion
            onset_latch = _onset_latch_records(grouped_rows)
            if onset_latch:
                case["onset_latch"] = onset_latch
                for index, record in enumerate(onset_latch):
                    for field in (
                        "changed_frames", "exact_group_frames",
                        "matched_label_frames", "wrong_string_voices",
                    ):
                        onset_latch_projection[index][field] += int(record[field])
            shadow_histogram = _histogram(
                row.get("spectral_shadow_fitted_masks", "")
            )
            shadow_frames = _integer(row, "spectral_shadow_frames")
            shadow_exact_frames = shadow_histogram.get(expected_mask, 0)
            if shadow_frames:
                case["per_frame_shadow"] = {
                    "frames": shadow_frames,
                    "invalid_frames": _integer(row, "spectral_shadow_invalid"),
                    "fitted_masks": shadow_histogram,
                    "exact_frames": shadow_exact_frames,
                    "residual_means": row.get(
                        "spectral_shadow_residual_means", ""
                    ),
                    "margin_means": row.get(
                        "spectral_shadow_margin_means", ""
                    ),
                    "onset_masks": _histogram(
                        row.get("spectral_shadow_onset_masks", "")
                    ),
                    "settled_masks": _histogram(
                        row.get("spectral_shadow_settled_masks", "")
                    ),
                    "single_onset_strings": _histogram(
                        row.get("spectral_single_onset_strings", "")
                    ),
                    "single_settled_strings": _histogram(
                        row.get("spectral_single_settled_strings", "")
                    ),
                    "single_gap_thresholds": _sequence(
                        row.get("spectral_single_gap_thresholds", ""), float,
                        8,
                    ),
                    "single_onset_score_error_means": row.get(
                        "spectral_single_onset_score_error_means", ""
                    ),
                    "single_settled_score_error_means": row.get(
                        "spectral_single_settled_score_error_means", ""
                    ),
                    "single_onset_gap_support": _json_joint_histogram(
                        row.get("spectral_single_onset_gap_support", "")
                    ),
                    "single_settled_gap_support": _json_joint_histogram(
                        row.get("spectral_single_settled_gap_support", "")
                    ),
                    "committed_exact_pairwise_beat_above_gate":
                        _json_joint_histogram(
                            row.get(
                                "committed_exact_pairwise_beat_above_gate", ""
                            )
                        ),
                    "committed_exact_pairwise_beat_connected": _histogram(
                        row.get("committed_exact_pairwise_beat_connected", "")
                    ),
                    "dispositions": _histogram(
                        row.get("spectral_shadow_dispositions", "")
                    ),
                    "fine_disagreements": _integer(
                        row, "spectral_shadow_fine_disagreements"
                    ),
                    "beat_compared": _integer(
                        row, "spectral_shadow_beat_compared"
                    ),
                    "beat_disagreements": _integer(
                        row, "spectral_shadow_beat_disagreements"
                    ),
                    "profile_disagreements": _integer(
                        row, "spectral_shadow_profile_disagreements"
                    ),
                    "temporal_disagreements": _integer(
                        row, "spectral_shadow_temporal_disagreements"
                    ),
                    "assignment_disagreements": _integer(
                        row, "spectral_shadow_assignment_disagreements"
                    ),
                }
                thresholds = _sequence(
                    row.get("spectral_shadow_margin_thresholds", ""), float
                )
                if thresholds:
                    projected_frames = _integer(
                        row, "spectral_shadow_projected_frames"
                    )
                    if projected_frames != _integer(row, "labeled"):
                        raise ValueError(
                            "bounded shadow did not cover every labeled frame"
                        )
                    if thresholds != [
                        entry["margin_threshold"] for entry in bounded_secondary
                    ]:
                        raise ValueError("spectral shadow thresholds drifted")
                    changed = _sequence(
                        row.get("spectral_shadow_projected_changed", ""), int
                    )
                    exact = _sequence(
                        row.get("spectral_shadow_projected_exact", ""), int
                    )
                    wrong = _sequence(
                        row.get("spectral_shadow_projected_wrong_strings", ""),
                        int,
                    )
                    matched_by_label = [
                        _sequence(
                            item.get("spectral_shadow_projected_matched", ""),
                            int,
                        )
                        for item in grouped_rows
                    ]
                    if not all(matched_by_label):
                        raise ValueError("projected matched sequence is missing")
                    projected = []
                    for index, threshold in enumerate(thresholds):
                        record = {
                            "margin_threshold": threshold,
                            "changed_frames": int(changed[index]),
                            "exact_group_frames": int(exact[index]),
                            "matched_label_frames": sum(
                                int(values[index]) for values in matched_by_label
                            ),
                            "wrong_string_voices": int(wrong[index]),
                        }
                        projected.append(record)
                        for field in (
                            "changed_frames",
                            "exact_group_frames",
                            "matched_label_frames",
                            "wrong_string_voices",
                        ):
                            bounded_secondary[index][field] += record[field]
                    case["per_frame_shadow"]["bounded_secondary"] = projected
                    case["per_frame_shadow"]["projected_frames"] = (
                        projected_frames
                    )
            identity_output: dict[str, object] = case["identities"]  # type: ignore[assignment]
            for identity, templates in template_sets.items():
                phase_output: dict[str, object] = {}
                for phase in PHASES:
                    text = str(row.get(f"spectral_{phase}_mean", ""))
                    if _integer(row, f"spectral_{phase}_frames") <= 0 or not text:
                        continue
                    lane_templates = {
                        lane: templates[(lane, note)][phase]
                        for lane in range(STRING_COUNT)
                        if (lane, note) in templates and phase in templates[(lane, note)]
                    }
                    if len(lane_templates) < members:
                        continue
                    result = classify_feasible_masks(
                        parse_fingerprint(text), lane_templates, note, members, members,
                        expected_mask=expected_mask,
                    )
                    phase_output[phase] = _classification_record(
                        result, row, expected_mask
                    )
                if phase_output:
                    identity_output[identity] = phase_output
            if preferred_identity is not None:
                preferred = identity_output.get(preferred_identity, {})
                if isinstance(preferred, Mapping):
                    for phase in PHASES:
                        if phase in preferred:
                            case[phase] = preferred[phase]
                corridor = preferred.get("corridor")
                if isinstance(corridor, Mapping) and corridor.get("fitted_mask") == expected_mask:
                    exact_cases += 1
                    exact_labeled_frames += _integer(row, "labeled")
            current = _dominant_mask(row, "observed_note_lane_masks")
            if current == expected_mask:
                current_exact_frames += _histogram(
                    row.get("observed_note_lane_masks", "")
                ).get(expected_mask, 0)
            cases.append(case)
        corpus_output[corpus_name] = {
            "case_count": len(cases),
            "exact_cases": exact_cases,
            "exact_labeled_frames": exact_labeled_frames,
            "current_exact_frames": current_exact_frames,
            "shadow_frames": sum(
                int(case.get("per_frame_shadow", {}).get("frames", 0))
                for case in cases
            ),
            "shadow_exact_frames": sum(
                int(case.get("per_frame_shadow", {}).get("exact_frames", 0))
                for case in cases
            ),
            "bounded_secondary": bounded_secondary,
            "tier_completion": _tier_completion_records(rows),
            "onset_latch": onset_latch_projection,
            "single_source": _single_source_summary(rows),
            "cases": cases,
        }
    return output


def _named_paths(values: Iterable[str]) -> dict[str, list[pathlib.Path]]:
    result: dict[str, list[pathlib.Path]] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name:
            raise ValueError("inputs must use NAME=PATH values")
        result.setdefault(name, []).append(pathlib.Path(path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", action="append", default=[], metavar="ID=TSV")
    parser.add_argument("--target", action="append", default=[], metavar="ID=TSV")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        template_paths = _named_paths(args.template)
        target_paths = _named_paths(args.target)
        if not template_paths or not target_paths:
            raise ValueError("at least one template and target are required")
        templates = build_template_sets({
            name: [
                row
                for path in paths
                for row in read_replay_details(path)
            ]
            for name, paths in template_paths.items()
        })
        report = audit_shadow(
            {
                name: [
                    row
                    for path in paths
                    for row in read_replay_details(path)
                ]
                for name, paths in target_paths.items()
            },
            templates,
        )
        report["candidate_population"] = {
            name: _candidate_population_summary(
                [read_replay_aggregate(path) for path in paths]
            )
            for name, paths in target_paths.items()
        }
        report["candidate_spectral_admission"] = {
            name: _candidate_spectral_admission_summary(
                [read_replay_aggregate(path) for path in paths]
            )
            for name, paths in target_paths.items()
        }
        text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output is None:
            print(text, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
