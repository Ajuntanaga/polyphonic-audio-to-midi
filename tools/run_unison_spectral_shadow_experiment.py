#!/usr/bin/env python3
"""Run the reproducible M3 spectral-shadow experiment on annotated corpora."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from collections.abc import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_unison_spectral_shadow import (
    _candidate_spectral_admission_summary,
    audit_shadow,
    build_template_sets,
    read_replay_details,
    write_template_bank,
)


FACTORY_CALIBRATION_SOURCE = (
    ROOT / "native/assets/m3_factory_calibration_v2.inc"
)
FACTORY_CALIBRATION_SHA256 = (
    "b7025b4fd3ea55901ea9f189966b4f62b6fe905ad16b9f8d0df88a0a1a76e997"
)
PHYSICAL_RECORDINGS = pathlib.Path(
    os.environ.get(
        "M3_PHYSICAL_RECORDINGS",
        str(ROOT / "build/physical-capture/source-recordings"),
    )
)
BASELINE_ARGS = (
    "--a4", "440", "--input-trim", "-9", "--sensitivity", "60",
    "--response", "75", "--max-polyphony", "5", "--max-fret", "24",
    "--label-details",
)
_DIGEST_CACHE: dict[tuple[str, int, int], str] = {}


def _factory_calibration_bytes() -> bytes:
    source = FACTORY_CALIBRATION_SOURCE.read_text(encoding="utf-8")
    calibration = bytes(
        int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", source)
    )
    if (
        len(calibration) != 6425
        or hashlib.sha256(calibration).hexdigest()
        != FACTORY_CALIBRATION_SHA256
    ):
        raise ValueError("embedded factory calibration identity mismatch")
    return calibration


def _materialize_factory_calibration(output: pathlib.Path) -> pathlib.Path:
    calibration = _factory_calibration_bytes()
    path = output / "factory-calibration-v2.m3cb"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != calibration:
        path.write_bytes(calibration)
    return path


def _file_sha256(path: pathlib.Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _DIGEST_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    result = digest.hexdigest()
    _DIGEST_CACHE[key] = result
    return result


def _aggregate(path: pathlib.Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as stream:
        keys = next(csv.reader([stream.readline().rstrip("\n")], delimiter="\t"))
        values = next(csv.reader([stream.readline().rstrip("\n")], delimiter="\t"))
    if len(keys) != len(values):
        raise ValueError(f"{path}: malformed aggregate rows")
    result: dict[str, object] = {}
    for key, value in zip(keys, values):
        if key == "fingerprint":
            result[key] = value
            continue
        try:
            result[key] = int(value)
        except ValueError:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value
    return result


def _valid_detail(path: pathlib.Path, with_shadow: bool) -> bool:
    try:
        with path.open(encoding="utf-8") as stream:
            stream.readline()
            stream.readline()
            header = stream.readline().split("\t")
        required = {"spectral_corridor_mean", "calibration_pass"}
        if with_shadow:
            required.update(
                {
                    "spectral_shadow_fitted_masks",
                    "spectral_shadow_projected_frames",
                    "spectral_shadow_projected_matched",
                    "spectral_single_onset_strings",
                    "spectral_single_onset_score_error_means",
                    "spectral_single_settled_score_error_means",
                    "spectral_single_onset_gap_support",
                    "spectral_single_settled_gap_support",
                    "committed_exact_pairwise_beat_above_gate",
                    "committed_exact_pairwise_beat_connected",
                    "spectral_onset_latch_projected_frames",
                    "spectral_tier_completion_exact",
                    "candidate_spectral_shadow_selected_frames",
                    "candidate_spectral_shadow_target_correct_frames",
                    "candidate_spectral_shadow_target_wrong_string_frames",
                    "candidate_spectral_shadow_other_false_frames",
                    "candidate_spectral_shadow_other_false_intervals",
                }
            )
        return required.issubset(header)
    except OSError:
        return False


def _run_replay(
    replay: pathlib.Path, wave: pathlib.Path, labels: pathlib.Path,
    calibration: pathlib.Path, output: pathlib.Path, block: int,
    template_bank: pathlib.Path | None = None,
) -> None:
    for required in (replay, wave, labels, calibration):
        if not required.is_file():
            raise FileNotFoundError(required)
    command = [
        str(replay), "--wav", str(wave), "--labels", str(labels),
        "--calibration", str(calibration), "--block", str(block),
        *BASELINE_ARGS,
    ]
    if template_bank is not None:
        command.extend(("--spectral-shadow-templates", str(template_bank)))
    identity_inputs = [replay, wave, labels, calibration]
    if template_bank is not None:
        identity_inputs.append(template_bank)
    identity: object = {
        "command": command,
        "input_sha256": {
            str(path): _file_sha256(path) for path in identity_inputs
        },
        "shadow_projection_schema": 12 if template_bank is not None else 0,
    }
    command_identity = hashlib.sha256(
        json.dumps(identity, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    metadata = output.with_suffix(output.suffix + ".meta.json")
    try:
        cached_identity = json.loads(metadata.read_text(encoding="utf-8"))[
            "command_sha256"
        ]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        cached_identity = None
    if (
        cached_identity == command_identity
        and _valid_detail(output, template_bank is not None)
    ):
        print(f"reuse {output.relative_to(ROOT)}", flush=True)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    temporary_metadata = metadata.with_suffix(metadata.suffix + ".partial")
    print(f"run   {output.relative_to(ROOT)}", flush=True)
    started = time.monotonic()
    with temporary.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, check=True)
    temporary_metadata.write_text(
        json.dumps({"command_sha256": command_identity}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    os.replace(temporary_metadata, metadata)
    print(f"done  {output.name} ({time.monotonic() - started:.1f}s)", flush=True)


def _template_sources() -> Iterable[tuple[str, int, pathlib.Path, pathlib.Path]]:
    label_root = (
        ROOT
        / "build/physical-capture/calibration-bank-experiment-cents16-final/labels"
    )
    for identity in ("raw", "midpoint", "corrected"):
        for physical_string in range(1, 9):
            stem = f"string-{physical_string:02}"
            if identity == "raw":
                wave = ROOT / f"build/physical-capture/pitch-corrected/{stem}-raw.wav"
                labels = label_root / "raw" / f"{stem}.tsv"
            elif identity == "midpoint":
                wave = ROOT / f"build/physical-capture/pitch-midpoint-reaper/{stem}-midpoint.wav"
                labels = label_root / "midpoint" / f"{stem}.tsv"
            else:
                wave = ROOT / f"build/physical-capture/pitch-corrected-reaper/{stem}-corrected.wav"
                labels = label_root / "exact" / f"{stem}.tsv"
            yield identity, physical_string, wave, labels


def _target_sources() -> dict[str, tuple[pathlib.Path, pathlib.Path]]:
    return {
        "physical_long_low": (
            PHYSICAL_RECORDINGS
            / "string8-fret8_string7-fret4_string6-open_unison.wav",
            ROOT / "build/physical-capture/unison-08-07-06/unison-labels.tsv",
        ),
        "physical_short_middle": (
            PHYSICAL_RECORDINGS / "string3-open_string4-fret4_string5-fret8.wav",
            ROOT / "build/physical-capture/unison-05-04-03/unison-labels.tsv",
        ),
        "physical_short_high_mid": (
            PHYSICAL_RECORDINGS / "string2-open_string3-fret4_string4-fret8.wav",
            ROOT / "build/physical-capture/unison-04-03-02/unison-labels.tsv",
        ),
        "physical_short_high": (
            PHYSICAL_RECORDINGS / "string1-open_strin2-fret4_string3-fret8.wav",
            ROOT / "build/physical-capture/unison-03-02-01/unison-labels.tsv",
        ),
        "constructed_short_unisons": (
            ROOT / "build/physical-capture/note-combination-corpus-tuning/combinations.wav",
            ROOT / "build/physical-capture/note-combination-corpus-tuning/combinations.tsv",
        ),
        "ordinary_chords": (
            ROOT / "build/physical-capture/note-combination-corpus-practical-chords/combinations.wav",
            ROOT / "build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv",
        ),
        "isolated_08": (
            ROOT / "build/physical-capture/control-sweep/representative/string-08.wav",
            ROOT / "build/physical-capture/control-sweep/representative/string-08.tsv",
        ),
        "isolated_05": (
            ROOT / "build/physical-capture/control-sweep/representative/string-05.wav",
            ROOT / "build/physical-capture/control-sweep/representative/string-05.tsv",
        ),
        "isolated_02": (
            ROOT / "build/physical-capture/control-sweep/representative/string-02.wav",
            ROOT / "build/physical-capture/control-sweep/representative/string-02.tsv",
        ),
        "constructed_short_three": (
            ROOT / "build/physical-capture/stability-evaluation-3plus3-4unison/triple-plus-three.wav",
            ROOT / "build/physical-capture/stability-evaluation-3plus3-4unison/triple-plus-three.tsv",
        ),
        "synthetic_four": (
            ROOT / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.wav",
            ROOT / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.tsv",
        ),
        "physical_four_diagnostic": (
            PHYSICAL_RECORDINGS
            / "string4-open_string5-fret4_string6-fret8_string7-fret12_string8-fret16.wav",
            ROOT
            / "build/physical-capture/unison-08-07-06-05-04/diagnostic-spans.tsv",
        ),
        "constructed_unisons": (
            ROOT / "build/physical-capture/note-combination-corpus-sustained-unison/combinations-synchronized.wav",
            ROOT / "build/physical-capture/note-combination-corpus-sustained-unison/combinations-synchronized.tsv",
        ),
        "constructed_long_three": (
            ROOT / "build/physical-capture/note-combination-corpus-sustained-unison/three-unison-long.wav",
            ROOT / "build/physical-capture/note-combination-corpus-sustained-unison/three-unison-long.tsv",
        ),
    }


_CANDIDATE_SPECTRAL_REQUIRED_CORPORA = (
    "ordinary_chords",
    "physical_long_low",
    "physical_short_middle",
    "physical_short_high_mid",
    "physical_short_high",
    "isolated_08",
    "isolated_05",
    "isolated_02",
    "constructed_short_unisons",
    "synthetic_four",
    "physical_four_diagnostic",
    "constructed_unisons",
    "constructed_long_three",
)


def _candidate_spectral_acceptance_report(
    summaries: dict[str, dict[str, object]],
    block_fingerprints: dict[str, object],
) -> dict[str, object]:
    """Require useful ordinary-chord recovery with zero measured regression."""
    missing = [
        name for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
        if name not in summaries or not summaries[name].get("available", False)
    ]
    block_gate = (
        len(block_fingerprints) == 3
        and len(set(block_fingerprints.values())) == 1
    )
    if missing:
        return {
            "gate_pass": False,
            "production_integration_authorized": False,
            "missing_corpora": missing,
            "block_fingerprints_identical": block_gate,
            "qualified": None,
            "decision": "keep_candidate_classifier_offline",
        }

    gates_by_corpus: dict[str, dict[tuple[int, int], dict[str, object]]] = {
        name: {
            (int(gate["policy_index"]), int(gate["gate_index"])): gate
            for gate in summaries[name]["gates"]  # type: ignore[index]
        }
        for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
    }
    common = set(gates_by_corpus["ordinary_chords"])
    for gates in gates_by_corpus.values():
        common.intersection_update(gates)

    candidates: list[dict[str, object]] = []
    for key in sorted(common):
        ordinary = gates_by_corpus["ordinary_chords"][key]
        total_correct = sum(
            int(gates_by_corpus[name][key]["target_correct_frames"])
            for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
        )
        total_wrong = sum(
            int(gates_by_corpus[name][key]["target_wrong_string_frames"])
            for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
        )
        total_false = sum(
            int(gates_by_corpus[name][key]["other_false_frames"])
            for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
        )
        tracker_bound = max(
            int(summaries[name]["active_peak"])
            for name in _CANDIDATE_SPECTRAL_REQUIRED_CORPORA
        ) <= 12
        candidate = {
            "policy_index": key[0],
            "gate_index": key[1],
            "minimum_score_ratio": ordinary["minimum_score_ratio"],
            "minimum_fundamental_ratio": ordinary[
                "minimum_fundamental_ratio"
            ],
            "maximum_error": ordinary["maximum_error"],
            "minimum_margin": ordinary["minimum_margin"],
            "ordinary_target_recovery": int(
                ordinary["target_correct_frames"]
            ),
            "total_target_recovery": total_correct,
            "total_wrong_string_frames": total_wrong,
            "total_other_false_frames": total_false,
            "tracker_bound_passes": tracker_bound,
            "passes": (
                int(ordinary["target_correct_frames"]) > 0
                and total_wrong == 0
                and total_false == 0
                and tracker_bound
                and block_gate
            ),
        }
        candidates.append(candidate)
    diagnostic_best = max(
        (candidate for candidate in candidates if candidate["passes"]),
        key=lambda candidate: (
            int(candidate["ordinary_target_recovery"]),
            int(candidate["total_target_recovery"]),
        ),
        default=None,
    )
    return {
        # Candidate-population recovery is a diagnostic search only. It does
        # not project the required physical-long gains and protected-corpus
        # metrics, so it can never independently authorize production use.
        "gate_pass": False,
        "production_integration_authorized": False,
        "missing_corpora": [],
        "block_fingerprints_identical": block_gate,
        "qualified": None,
        "diagnostic_best": diagnostic_best,
        "candidates": candidates,
        "decision": "keep_candidate_classifier_offline",
    }


def _acceptance_report(report: dict[str, object]) -> dict[str, object]:
    corpora = report["corpora"]
    aggregates = report["target_aggregates"]
    assert isinstance(corpora, dict) and isinstance(aggregates, dict)
    long_corpus = corpora["physical_long_low"]
    assert isinstance(long_corpus, dict)
    long_candidates = long_corpus["bounded_secondary"]
    assert isinstance(long_candidates, list)
    triple_case = next(
        case
        for case in long_corpus["cases"]
        if case["expected_mask"] == 0x07 and case["labeled_frames"] == 39378
    )
    triple_candidates = triple_case["per_frame_shadow"]["bounded_secondary"]
    current_long_total = int(aggregates["physical_long_low"]["matched"])
    current_long_triple = int(triple_case["current_matched_frames"])
    required_long_total = current_long_total + 685
    required_long_triple = current_long_triple + 394

    ordinary = aggregates["ordinary_chords"]
    assert isinstance(ordinary, dict)
    ordinary_gate = (
        int(ordinary["matched"]) >= 128760
        and int(ordinary["false_wrong_string_voices"]) <= 104018
        and int(ordinary["false_wrong_note_voices"]) <= 195380
        and int(ordinary["false_positive_voices"]) <= 366835
    )
    intervals_value = aggregates.get("constructed_short_unisons")
    intervals_available = isinstance(intervals_value, dict)
    intervals = intervals_value if intervals_available else {}
    intervals_gate = intervals_available and (
        int(intervals["matched"]) >= 243954
        and int(intervals["false_wrong_string_voices"]) <= 112967
        and int(intervals["false_wrong_note_voices"]) <= 211147
        and int(intervals["false_positive_voices"]) <= 345916
    )
    isolated_requirements = {
        "isolated_08": (31050, 27473),
        "isolated_05": (31050, 19952),
        "isolated_02": (35550, 24044),
    }
    isolated_results = {
        name: {
            "labeled": int(aggregates[name]["labeled"]),
            "matched": int(aggregates[name]["matched"]),
            "required_labeled": required_labeled,
            "required_matched": required_matched,
            "passes": (
                int(aggregates[name]["labeled"]) == required_labeled
                and int(aggregates[name]["matched"]) >= required_matched
            ),
        }
        for name, (required_labeled, required_matched)
        in isolated_requirements.items()
    }
    isolated_gate = all(result["passes"] for result in isolated_results.values())
    fingerprints = report["block_fingerprints"]
    assert isinstance(fingerprints, dict)
    block_gate = len(set(fingerprints.values())) == 1
    short_corpora = (
        "physical_short_middle",
        "physical_short_high_mid",
        "physical_short_high",
    )
    candidates: list[dict[str, object]] = []
    for index, long_result in enumerate(long_candidates):
        triple_result = triple_candidates[index]
        threshold = float(long_result["margin_threshold"])
        short_unchanged = all(
            int(corpora[name]["bounded_secondary"][index]["changed_frames"]) == 0
            for name in short_corpora
        )
        isolated_unchanged = all(
            int(corpora[name]["bounded_secondary"][index]["changed_frames"]) == 0
            for name in isolated_requirements
        )
        ordinary_projection = corpora["ordinary_chords"][
            "bounded_secondary"
        ][index]
        ordinary_projection_gate = (
            int(ordinary_projection["matched_label_frames"])
            >= int(ordinary["matched"])
            and int(ordinary_projection["wrong_string_voices"])
            <= int(ordinary["false_wrong_string_voices"])
        )
        interval_projection_gate = False
        if intervals_available:
            interval_projection = corpora["constructed_short_unisons"][
                "bounded_secondary"
            ][index]
            interval_projection_gate = (
                int(interval_projection["matched_label_frames"])
                >= int(intervals["matched"])
                and int(interval_projection["wrong_string_voices"])
                <= int(intervals["false_wrong_string_voices"])
            )
        long_total = int(long_result["matched_label_frames"])
        long_triple = int(triple_result["exact_group_frames"])
        long_wrong = int(long_result["wrong_string_voices"])
        passes = (
            long_total >= required_long_total
            and long_triple >= required_long_triple
            and long_wrong <= 2738
            and ordinary_gate
            and ordinary_projection_gate
            and intervals_gate
            and interval_projection_gate
            and isolated_gate
            and short_unchanged
            and isolated_unchanged
            and block_gate
        )
        candidates.append(
            {
                "margin_threshold": threshold,
                "long_total_matched": long_total,
                "required_long_total_matched": required_long_total,
                "long_total_gain": long_total - current_long_total,
                "long_three_exact": long_triple,
                "required_long_three_exact": required_long_triple,
                "long_three_gain": long_triple - current_long_triple,
                "long_wrong_string_voices": long_wrong,
                "maximum_long_wrong_string_voices": 2738,
                "short_upper_unisons_unchanged": short_unchanged,
                "isolated_replays_unchanged": isolated_unchanged,
                "ordinary_chords_projection_passes":
                    ordinary_projection_gate,
                "interval_projection_passes": interval_projection_gate,
                "passes": passes,
            }
        )
    qualified = next(
        (candidate for candidate in candidates if candidate["passes"]), None
    )
    return {
        "classifier_gate_pass": qualified is not None,
        "production_integration_authorized": qualified is not None,
        "qualified_margin_threshold": (
            qualified["margin_threshold"] if qualified is not None else None
        ),
        "baseline": {
            "long_total_matched": current_long_total,
            "long_three_exact": current_long_triple,
            "long_wrong_string_voices": int(
                aggregates["physical_long_low"]["false_wrong_string_voices"]
            ),
        },
        "ordinary_chords": {
            "matched": int(ordinary["matched"]),
            "wrong_string_voices": int(ordinary["false_wrong_string_voices"]),
            "wrong_note_voices": int(ordinary["false_wrong_note_voices"]),
            "false_positive_voices": int(ordinary["false_positive_voices"]),
            "unchanged_by_shadow": all(
                int(entry["changed_frames"]) == 0
                for entry in corpora["ordinary_chords"]["bounded_secondary"]
            ),
            "passes": ordinary_gate,
        },
        "intervals": {
            "available": intervals_available,
            "matched": (
                int(intervals["matched"]) if intervals_available else None
            ),
            "required_matched": 243954,
            "wrong_string_voices": (
                int(intervals["false_wrong_string_voices"])
                if intervals_available else None
            ),
            "maximum_wrong_string_voices": 112967,
            "wrong_note_voices": (
                int(intervals["false_wrong_note_voices"])
                if intervals_available else None
            ),
            "maximum_wrong_note_voices": 211147,
            "false_positive_voices": (
                int(intervals["false_positive_voices"])
                if intervals_available else None
            ),
            "maximum_false_positive_voices": 345916,
            "unchanged_by_shadow": intervals_available and all(
                int(entry["changed_frames"]) == 0
                for entry in corpora["constructed_short_unisons"][
                    "bounded_secondary"
                ]
            ),
            "passes": intervals_gate,
        },
        "isolated": isolated_results,
        "block_fingerprints_identical": block_gate,
        "four_unison_corpora_exercised": all(
            name in corpora for name in ("synthetic_four", "physical_four_diagnostic")
        ),
        "candidates": candidates,
        "decision": (
            "integrate_bounded_secondary_evidence"
            if qualified is not None
            else "keep_classifier_disconnected"
        ),
    }


def _tier_completion_acceptance_report(
    report: dict[str, object],
) -> dict[str, object]:
    """Apply the production gate to the causal tier-completion shadow."""
    corpora = report["corpora"]
    aggregates = report["target_aggregates"]
    fingerprints = report["block_fingerprints"]
    assert isinstance(corpora, dict)
    assert isinstance(aggregates, dict)
    assert isinstance(fingerprints, dict)

    long_corpus = corpora["physical_long_low"]
    assert isinstance(long_corpus, dict)
    long_candidates = long_corpus.get("tier_completion", [])
    triple_case = next(
        case
        for case in long_corpus["cases"]
        if case["expected_mask"] == 0x07 and case["labeled_frames"] == 39378
    )
    triple_candidates = triple_case.get("tier_completion", [])
    if len(long_candidates) != 7 or len(triple_candidates) != 7:
        return {
            "gate_pass": False,
            "production_integration_authorized": False,
            "decision": "keep_tier_completion_offline",
            "reason": "tier completion diagnostics are incomplete",
        }

    block_gate = len(set(fingerprints.values())) == 1
    current_long_total = int(aggregates["physical_long_low"]["matched"])
    current_long_triple = int(triple_case["current_matched_frames"])
    required_long_total = current_long_total + 685
    required_long_triple = current_long_triple + 394
    isolated_requirements = {
        "isolated_08": 27473,
        "isolated_05": 19952,
        "isolated_02": 24044,
    }
    short_corpora = (
        "physical_short_middle",
        "physical_short_high_mid",
        "physical_short_high",
    )
    candidates: list[dict[str, object]] = []
    for index, (long_result, triple_result) in enumerate(
        zip(long_candidates, triple_candidates)
    ):
        threshold = float(long_result["margin_threshold"])
        ordinary_result = corpora["ordinary_chords"]["tier_completion"][index]
        ordinary_baseline = aggregates["ordinary_chords"]
        ordinary_gate = (
            int(ordinary_result["matched_label_frames"])
            >= int(ordinary_baseline["matched"])
            and int(ordinary_result["wrong_string_voices"])
            <= int(ordinary_baseline["false_wrong_string_voices"])
        )
        intervals_result = corpora["constructed_short_unisons"][
            "tier_completion"
        ][index]
        intervals_baseline = aggregates["constructed_short_unisons"]
        intervals_gate = (
            int(intervals_result["matched_label_frames"])
            >= int(intervals_baseline["matched"])
            and int(intervals_result["wrong_string_voices"])
            <= int(intervals_baseline["false_wrong_string_voices"])
        )
        isolated_gate = all(
            int(corpora[name]["tier_completion"][index]["matched_label_frames"])
            >= required
            and int(corpora[name]["tier_completion"][index]["wrong_string_voices"])
            <= int(aggregates[name]["false_wrong_string_voices"])
            for name, required in isolated_requirements.items()
        )
        short_gate = all(
            int(corpora[name]["tier_completion"][index]["matched_label_frames"])
            >= int(aggregates[name]["matched"])
            and int(corpora[name]["tier_completion"][index]["wrong_string_voices"])
            <= int(aggregates[name]["false_wrong_string_voices"])
            for name in short_corpora
        )
        long_total = int(long_result["matched_label_frames"])
        long_triple = int(triple_result["exact_group_frames"])
        long_wrong = int(long_result["wrong_string_voices"])
        passes = (
            long_total >= required_long_total
            and long_triple >= required_long_triple
            and long_wrong <= 2738
            and ordinary_gate
            and intervals_gate
            and isolated_gate
            and short_gate
            and block_gate
        )
        candidates.append(
            {
                "margin_threshold": threshold,
                "long_total_matched": long_total,
                "required_long_total_matched": required_long_total,
                "long_total_gain": long_total - current_long_total,
                "long_three_exact": long_triple,
                "required_long_three_exact": required_long_triple,
                "long_three_gain": long_triple - current_long_triple,
                "long_wrong_string_voices": long_wrong,
                "ordinary_chords_passes": ordinary_gate,
                "intervals_pass": intervals_gate,
                "isolated_passes": isolated_gate,
                "short_upper_unisons_pass": short_gate,
                "passes": passes,
            }
        )
    qualified = next(
        (candidate for candidate in candidates if candidate["passes"]), None
    )
    return {
        "gate_pass": qualified is not None,
        "production_integration_authorized": qualified is not None,
        "qualified_margin_threshold": (
            qualified["margin_threshold"] if qualified is not None else None
        ),
        "block_fingerprints_identical": block_gate,
        "four_unison_corpora_exercised": all(
            name in corpora
            for name in ("synthetic_four", "physical_four_diagnostic")
        ),
        "candidates": candidates,
        "decision": (
            "integrate_bounded_tier_completion"
            if qualified is not None
            else "keep_tier_completion_offline"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay", type=pathlib.Path,
        default=ROOT / "build/vst3/release/m3_replay",
    )
    parser.add_argument(
        "--output", type=pathlib.Path,
        default=ROOT / "build/physical-capture/unison-spectral-shadow",
    )
    parser.add_argument(
        "--calibration", type=pathlib.Path,
        help="M3CB override; defaults to the embedded production factory prior",
    )
    parser.add_argument("--skip-constructed", action="store_true")
    args = parser.parse_args()
    replay = args.replay.resolve()
    output = args.output.resolve()
    calibration = (
        args.calibration.resolve()
        if args.calibration is not None
        else _materialize_factory_calibration(output)
    )
    details = output / "details"
    template_detail_paths: dict[str, list[pathlib.Path]] = {
        "raw": [], "midpoint": [], "corrected": []
    }
    for identity, physical_string, wave, labels in _template_sources():
        path = details / f"template-{identity}-string-{physical_string:02}.tsv"
        _run_replay(replay, wave, labels, calibration, path, 512)
        template_detail_paths[identity].append(path)

    template_rows = {
        identity: [
            row
            for path in paths
            for row in read_replay_details(path)
        ]
        for identity, paths in template_detail_paths.items()
    }
    corpus_identities = {
        "ascending": [row for row in template_rows["raw"] if int(row["calibration_pass"]) == 1],
        "descending": [row for row in template_rows["raw"] if int(row["calibration_pass"]) == 2],
        "isolated": [row for row in template_rows["raw"] if int(row["calibration_pass"]) == 3],
        "corrected": template_rows["corrected"],
        "midpoint": template_rows["midpoint"],
    }
    templates = build_template_sets(corpus_identities)
    if "blended" not in templates:
        raise ValueError("blended template identity was not produced")
    bank_path = output / "blended-template-bank.tsv"
    write_template_bank(templates["blended"], bank_path)

    target_details: dict[str, pathlib.Path] = {}
    for name, (wave, labels) in _target_sources().items():
        if name.startswith("constructed_") and args.skip_constructed:
            continue
        path = details / f"target-{name}-block-512.tsv"
        _run_replay(replay, wave, labels, calibration, path, 512, bank_path)
        target_details[name] = path
        if name == "physical_long_low":
            for block in (32, 1024):
                partition_path = details / f"target-{name}-block-{block}.tsv"
                _run_replay(
                    replay, wave, labels, calibration, partition_path, block,
                    bank_path,
                )
                fingerprint = _aggregate(partition_path)["fingerprint"]
                if fingerprint != _aggregate(path)["fingerprint"]:
                    raise RuntimeError("block-size replay fingerprint mismatch")

    report = audit_shadow(
        {name: read_replay_details(path) for name, path in target_details.items()},
        templates,
    )
    report["baseline"] = {
        "calibration": str(calibration.relative_to(ROOT)),
        "calibration_sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
        "input_trim_db": -9.0,
        "sensitivity": 60,
        "response": 75,
        "max_polyphony": 5,
        "max_fret": 24,
    }
    report["template_corpora"] = {
        name: {
            "detail_files": [str(path.relative_to(ROOT)) for path in paths],
            "aggregates": [_aggregate(path) for path in paths],
        }
        for name, paths in template_detail_paths.items()
    }
    report["target_aggregates"] = {
        name: _aggregate(path) for name, path in target_details.items()
    }
    report["candidate_spectral_admission"] = {
        name: _candidate_spectral_admission_summary([aggregate])
        for name, aggregate in report["target_aggregates"].items()
    }
    report["block_fingerprints"] = {
        str(block): _aggregate(
            details / f"target-physical_long_low-block-{block}.tsv"
        )["fingerprint"]
        for block in (32, 512, 1024)
    }
    report["acceptance"] = _acceptance_report(report)
    report["tier_completion_acceptance"] = (
        _tier_completion_acceptance_report(report)
    )
    report["candidate_spectral_acceptance"] = (
        _candidate_spectral_acceptance_report(
            report["candidate_spectral_admission"],
            report["block_fingerprints"],
        )
    )
    report_path = output / "audit.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"report {report_path.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"spectral-shadow experiment: {error}", file=sys.stderr)
        raise SystemExit(1)
