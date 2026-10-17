import copy
import hashlib
import json
import math
import pathlib
import tempfile
import unittest

from tools.audit_unison_spectral_shadow import (
    FEATURE_COUNT,
    _candidate_population_summary,
    _candidate_spectral_admission_summary,
    _json_joint_histogram,
    _sequence,
    _single_source_summary,
    _tier_completion_records,
    audit_shadow,
    build_template_sets,
    classify_feasible_masks,
    parse_fingerprint,
    read_replay_details,
    write_template_bank,
)
from tools.run_unison_spectral_shadow_experiment import (
    _aggregate,
    _acceptance_report,
    _candidate_spectral_acceptance_report,
    _factory_calibration_bytes,
    _file_sha256,
    _tier_completion_acceptance_report,
)


def vector(*values: float) -> list[float]:
    return [*values, *([0.0] * (FEATURE_COUNT - len(values)))]


def encoded(values: list[float]) -> str:
    return ",".join(f"{value:.9g}" for value in values)


def detail_file(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    lines = ["aggregate", "values", "\t".join(fields)]
    lines.extend("\t".join(str(row[field]) for field in fields) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class UnisonSpectralShadowAuditTests(unittest.TestCase):
    def test_factory_calibration_default_is_the_embedded_production_prior(self):
        calibration = _factory_calibration_bytes()
        self.assertEqual(len(calibration), 6425)
        self.assertEqual(calibration[:8], b"M3CB\x02\x00\x08\x00")
        self.assertEqual(
            hashlib.sha256(calibration).hexdigest(),
            "b7025b4fd3ea55901ea9f189966b4f62b6fe905ad16b9f8d0df88a0a1a76e997",
        )

    def test_candidate_spectral_summary_preserves_joint_gate_accounting(self):
        aggregate = {
            "candidate_spectral_shadow_active_peak": 7,
            "candidate_spectral_shadow_candidate_frames": "0.0:12,0.1:5,2.0:9,2.1:4",
            "candidate_spectral_shadow_ready_frames": "0.0:8,0.1:2,2.0:6,2.1:1",
            "candidate_spectral_shadow_selected_frames": "0.0:7,2.21:5",
            "candidate_spectral_shadow_target_correct_frames": "0.0:5,2.21:4",
            "candidate_spectral_shadow_target_wrong_string_frames": "0.0:1",
            "candidate_spectral_shadow_other_false_frames": "0.0:1,2.21:1",
            "candidate_spectral_shadow_other_false_intervals": "0.48:1,93.60:1",
        }

        summary = _candidate_spectral_admission_summary([aggregate])

        self.assertTrue(summary["available"])
        self.assertTrue(summary["false_interval_diagnostics_available"])
        self.assertEqual(summary["active_peak"], 7)
        strict = next(
            gate for gate in summary["gates"]
            if gate["minimum_score_ratio"] == 0.9
            and gate["maximum_error"] == 0.125
            and gate["minimum_margin"] == 0.125
        )
        self.assertEqual(strict["selected_frames"], 5)
        self.assertEqual(strict["target_correct_frames"], 4)
        self.assertEqual(strict["target_wrong_string_frames"], 0)
        self.assertEqual(strict["other_false_frames"], 1)
        self.assertEqual(strict["other_false_intervals"], {12: 1})
        self.assertEqual(strict["precision"], 0.8)

    def test_candidate_spectral_acceptance_requires_zero_cross_corpus_regression(self):
        clean_gate = {
            "policy_index": 2,
            "gate_index": 21,
            "minimum_score_ratio": 0.9,
            "minimum_fundamental_ratio": 0.6,
            "maximum_error": 0.125,
            "minimum_margin": 0.125,
            "selected_frames": 5,
            "target_correct_frames": 5,
            "target_wrong_string_frames": 0,
            "other_false_frames": 0,
            "precision": 1.0,
        }
        required = (
            "ordinary_chords", "physical_long_low",
            "physical_short_middle", "physical_short_high_mid",
            "physical_short_high", "isolated_08", "isolated_05",
            "isolated_02", "constructed_short_unisons", "synthetic_four",
            "physical_four_diagnostic", "constructed_unisons",
            "constructed_long_three",
        )
        summaries = {
            name: {"available": True, "active_peak": 7, "gates": [copy.deepcopy(clean_gate)]}
            for name in required
        }
        summaries["ordinary_chords"]["gates"][0]["target_correct_frames"] = 390
        summaries["ordinary_chords"]["gates"][0]["selected_frames"] = 390

        accepted = _candidate_spectral_acceptance_report(
            summaries, {"32": "same", "512": "same", "1024": "same"}
        )

        self.assertFalse(accepted["gate_pass"])
        self.assertFalse(accepted["production_integration_authorized"])
        self.assertEqual(
            accepted["diagnostic_best"]["ordinary_target_recovery"], 390,
        )
        self.assertEqual(
            accepted["decision"], "keep_candidate_classifier_offline",
        )
        degraded = copy.deepcopy(summaries)
        degraded["isolated_05"]["gates"][0]["other_false_frames"] = 1
        rejected = _candidate_spectral_acceptance_report(
            degraded, {"32": "same", "512": "same", "1024": "same"}
        )
        self.assertFalse(rejected["gate_pass"])

    def test_sequence_parser_accepts_the_declared_shape_only(self):
        self.assertEqual(
            _sequence("0,0.005,0.01,0.02,0.04,0.08,0.12,0.2", float, 8),
            [0.0, 0.005, 0.01, 0.02, 0.04, 0.08, 0.12, 0.2],
        )
        with self.assertRaises(ValueError):
            _sequence("0,1,2,3,4,5,6", int, 8)

    def test_json_joint_histogram_uses_serializable_keys(self):
        value = _json_joint_histogram("1.2:3,4.5:6")
        self.assertEqual(value, {"1.2": 3, "4.5": 6})
        self.assertEqual(json.loads(json.dumps(value)), value)

    def test_candidate_population_rescue_grid_uses_joint_target_false_counts(self):
        aggregate = {
            "candidate_population_labeled_snapshots": "10",
            "candidate_population_target_dispositions": "1:10,4:20",
            "candidate_population_other_dispositions": "1:30",
            "candidate_population_target_score_ratio_bins": "10:8,16:22",
            "candidate_population_other_score_ratio_bins": "10:21,16:9",
            "candidate_population_target_below_score_ratio_bins": "10:8,16:2",
            "candidate_population_other_below_score_ratio_bins": "10:21,16:9",
            "candidate_population_target_below_fundamental_ratio_bins": "18:8,19:2",
            "candidate_population_other_below_fundamental_ratio_bins": "18:21,19:9",
            "candidate_population_target_below_evidence_flags": "14:10",
            "candidate_population_other_below_evidence_flags": "14:30",
            "candidate_population_target_below_direct_evidence_bins": (
                "10.18:8,16.19:2"
            ),
            "candidate_population_other_below_direct_evidence_bins": (
                "10.18:21,16.19:9"
            ),
            "candidate_population_target_below_pitch_band_peak_bins": (
                "16.18:2,19.20:8"
            ),
            "candidate_population_other_below_pitch_band_peak_bins": (
                "12.15:21,18.19:9"
            ),
            "candidate_population_target_spectral_head_vote_masks": "4:30",
            "candidate_population_other_spectral_head_vote_masks": "4:30",
        }

        summary = _candidate_population_summary([aggregate])

        self.assertTrue(summary["available"])
        self.assertEqual(summary["target"]["below_threshold_candidates"], 10)
        self.assertEqual(summary["other"]["below_threshold_candidates"], 30)
        candidate = next(
            item for item in summary["rescue_thresholds"]
            if item["minimum_score_ratio"] == 0.5
            and item["minimum_fundamental_ratio"] == 0.9
        )
        self.assertEqual(candidate["target_candidates"], 10)
        self.assertEqual(candidate["other_candidates"], 30)
        self.assertEqual(candidate["precision"], 0.25)
        self.assertEqual(candidate["target_recall"], 1.0)
        strict = next(
            item for item in summary["rescue_thresholds"]
            if item["minimum_score_ratio"] == 0.8
            and item["minimum_fundamental_ratio"] == 0.95
        )
        self.assertEqual(strict["target_candidates"], 2)
        self.assertEqual(strict["other_candidates"], 9)
        self.assertTrue(summary["pitch_band_available"])
        pitch_strict = next(
            item for item in summary["pitch_band_rescue_thresholds"]
            if item["minimum_pitch_band_score_peak_ratio"] == 0.9
            and item["minimum_pitch_band_fundamental_peak_ratio"] == 0.95
        )
        self.assertEqual(pitch_strict["target_candidates"], 8)
        self.assertEqual(pitch_strict["other_candidates"], 9)

    def test_single_source_summary_separates_ordinary_and_unison_groups(self):
        rows = [
            {
                "start_sample": 0,
                "end_sample": 100,
                "midi_note": 52,
                "string_mask": 32,
                "spectral_single_frames": 10,
                "spectral_single_invalid": 0,
                "spectral_single_group_correct_error_bins": "1:8",
                "spectral_single_group_other_error_bins": "2:2",
                "spectral_single_group_correct_margin_bins": "8:7,2:1",
                "spectral_single_group_other_margin_bins": "8:1,1:1",
                "spectral_single_selection_dispositions": "1.1:7,1.2:2,4.1:1",
            },
            {
                "start_sample": 100,
                "end_sample": 200,
                "midi_note": 40,
                "string_mask": 1,
                "spectral_single_frames": 6,
                "spectral_single_invalid": 0,
                "spectral_single_group_correct_error_bins": "3:6",
                "spectral_single_group_other_error_bins": "",
                "spectral_single_group_correct_margin_bins": "6:6",
                "spectral_single_group_other_margin_bins": "",
                "spectral_single_selection_dispositions": "4.1:6",
                "spectral_single_group_selection_dispositions": "4.1:6",
            },
            {
                "start_sample": 100,
                "end_sample": 200,
                "midi_note": 40,
                "string_mask": 2,
                "spectral_single_frames": 6,
                "spectral_single_invalid": 0,
                "spectral_single_group_correct_error_bins": "3:6",
                "spectral_single_group_other_error_bins": "",
                "spectral_single_group_correct_margin_bins": "6:6",
                "spectral_single_group_other_margin_bins": "",
                "spectral_single_selection_dispositions": "4.2:6",
                "spectral_single_group_selection_dispositions": "4.1:6",
            },
        ]

        summary = _single_source_summary(rows)
        reordered = _single_source_summary([rows[0], rows[2], rows[1]])

        self.assertEqual(summary["group_count"], 2)
        self.assertEqual(reordered, summary)
        self.assertEqual(summary["ordinary"]["frames"], 10)
        self.assertEqual(summary["ordinary"]["correct_frames"], 8)
        self.assertEqual(summary["multi_string"]["frames"], 6)
        self.assertEqual(summary["multi_string"]["correct_frames"], 6)
        margin = next(
            item for item in summary["ordinary"]["margin_thresholds"]
            if item["minimum_margin"] == 0.2
        )
        self.assertEqual(margin["correct_frames"], 7)
        self.assertEqual(margin["other_frames"], 1)
        self.assertEqual(summary["ordinary"]["selection"]["below_threshold"],
                         {"invalid": 0, "correct": 7, "other": 2})

    def test_tier_completion_aggregates_group_owned_and_per_label_metrics(self):
        thresholds = "0,0.00025,0.0005,0.001,0.002,0.005,0.01"
        leader = {
            "spectral_tier_completion_margin_thresholds": thresholds,
            "spectral_tier_completion_changed": "3,3,3,3,3,3,3",
            "spectral_tier_completion_exact": "7,7,7,7,7,7,7",
            "spectral_tier_completion_matched": "5,5,5,5,5,5,5",
            "spectral_tier_completion_wrong_strings": "2,2,2,2,2,2,2",
        }
        member = {
            "spectral_tier_completion_margin_thresholds": thresholds,
            "spectral_tier_completion_changed": "0,0,0,0,0,0,0",
            "spectral_tier_completion_exact": "0,0,0,0,0,0,0",
            "spectral_tier_completion_matched": "4,4,4,4,4,4,4",
            "spectral_tier_completion_wrong_strings": "0,0,0,0,0,0,0",
        }
        records = _tier_completion_records([leader, member])
        self.assertEqual(len(records), 7)
        self.assertEqual(records[0]["changed_frames"], 3)
        self.assertEqual(records[0]["exact_group_frames"], 7)
        self.assertEqual(records[0]["matched_label_frames"], 9)
        self.assertEqual(records[0]["wrong_string_voices"], 2)

    def test_experiment_cache_identity_tracks_input_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "input.bin"
            path.write_bytes(b"first")
            first = _file_sha256(path)
            path.write_bytes(b"second")
            second = _file_sha256(path)
        self.assertNotEqual(first, second)

    def test_experiment_aggregate_preserves_hex_fingerprint_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "aggregate.tsv"
            path.write_text(
                "matched\tfingerprint\n1\t8108367e10721704\n",
                encoding="utf-8",
            )
            aggregate = _aggregate(path)
        self.assertEqual(aggregate["matched"], 1)
        self.assertEqual(aggregate["fingerprint"], "8108367e10721704")

    def test_fingerprint_parser_requires_exact_finite_nonnegative_shape(self):
        values = vector(1.0, 0.5)
        self.assertEqual(parse_fingerprint(encoded(values)), values)
        for bad in (
            "",
            "1,2",
            encoded([math.nan, *values[1:]]),
            encoded([-1.0, *values[1:]]),
        ):
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                parse_fingerprint(bad)

    def test_templates_use_componentwise_medians_and_keep_corpus_identity(self):
        rows = [
            {
                "start_sample": 0,
                "end_sample": 100,
                "midi_note": 56,
                "string_mask": 1,
                "calibration_pass": 1,
                "spectral_corridor_frames": 2,
                "spectral_onset_frames": 1,
                "spectral_settled_frames": 1,
                "spectral_corridor_mean": encoded(vector(1.0, 0.0)),
                "spectral_onset_mean": encoded(vector(1.0, 0.0)),
                "spectral_settled_mean": encoded(vector(1.0, 0.0)),
            },
            {
                "start_sample": 100,
                "end_sample": 200,
                "midi_note": 56,
                "string_mask": 1,
                "calibration_pass": 2,
                "spectral_corridor_frames": 2,
                "spectral_onset_frames": 1,
                "spectral_settled_frames": 1,
                "spectral_corridor_mean": encoded(vector(0.8, 0.2)),
                "spectral_onset_mean": encoded(vector(0.8, 0.2)),
                "spectral_settled_mean": encoded(vector(0.8, 0.2)),
            },
            {
                "start_sample": 200,
                "end_sample": 300,
                "midi_note": 56,
                "string_mask": 1,
                "calibration_pass": 3,
                "spectral_corridor_frames": 2,
                "spectral_onset_frames": 1,
                "spectral_settled_frames": 1,
                "spectral_corridor_mean": encoded(vector(0.0, 1.0)),
                "spectral_onset_mean": encoded(vector(0.0, 1.0)),
                "spectral_settled_mean": encoded(vector(0.0, 1.0)),
            },
        ]
        templates = build_template_sets({"raw": rows})
        raw = templates["raw"][(0, 56)]["corridor"]
        self.assertGreater(raw[0], raw[1])
        self.assertIn("blended", templates)
        self.assertEqual(templates["blended"][(0, 56)]["corridor"], raw)
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "templates.tsv"
            write_template_bank(templates["blended"], path)
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            lines[0], "phase\tmidi_note\tstring_index\tfingerprint"
        )
        self.assertEqual(len(lines), 4)
        self.assertEqual(len(lines[1].split("\t")[3].split(",")), FEATURE_COUNT)

    def test_classifier_considers_nonconsecutive_fret_feasible_masks(self):
        templates = {
            0: vector(1.0, 0.0, 0.0),
            2: vector(0.0, 1.0, 0.0),
            5: vector(0.0, 0.0, 1.0),
        }
        result = classify_feasible_masks(
            vector(0.8, 0.6, 0.4), templates, 56, 3, 3
        )
        self.assertEqual(result.member_mask, 0x25)
        self.assertEqual(result.member_count, 3)
        self.assertTrue(result.valid)
        self.assertGreater(result.margin, 0.0)

    def test_audit_groups_overlapping_labels_and_reports_evidence_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            template_paths = []
            for lane, feature in ((0, 0), (2, 1), (5, 2)):
                path = root / f"template-{lane}.tsv"
                row = {
                    "start_sample": 0,
                    "end_sample": 100,
                    "midi_note": 56,
                    "string_mask": 1 << lane,
                    "calibration_pass": 1,
                    "spectral_corridor_frames": 5,
                    "spectral_corridor_mean": encoded(vector(*([0.0] * feature), 1.0)),
                    "spectral_onset_mean": encoded(vector(*([0.0] * feature), 1.0)),
                    "spectral_settled_mean": encoded(vector(*([0.0] * feature), 1.0)),
                }
                detail_file(path, [row])
                template_paths.append(path)

            target = root / "target.tsv"
            common = {
                "start_sample": 0,
                "end_sample": 100,
                "midi_note": 56,
                "calibration_pass": 0,
                "labeled": 10,
                "matched": 3,
                "spectral_corridor_frames": 8,
                "spectral_corridor_mean": encoded(vector(0.8, 0.6, 0.4)),
                "spectral_onset_mean": encoded(vector(0.8, 0.6, 0.4)),
                "spectral_settled_mean": encoded(vector(0.8, 0.6, 0.4)),
                "fine_frequency_member_masks": "3:8",
                "profile_unison_proposal_masks": "37:8",
                "temporal_unison_proposal_masks": "0:8",
                "observed_note_lane_masks": "37:3,3:7",
                "spectral_shadow_frames": 8,
                "spectral_shadow_invalid": 0,
                "spectral_shadow_fitted_masks": "37:8",
                "spectral_shadow_projected_frames": 10,
                "spectral_shadow_margin_thresholds": (
                    "0,0.00025,0.0005,0.001,0.002,0.005,0.01"
                ),
                "spectral_shadow_projected_changed": "1,1,1,0,0,0,0",
                "spectral_shadow_projected_exact": "2,2,1,0,0,0,0",
                "spectral_shadow_projected_matched": "3,3,2,1,1,1,1",
                "spectral_shadow_projected_wrong_strings": "4,3,2,1,0,0,0",
            }
            detail_file(
                target,
                [{**common, "string_mask": mask} for mask in (1, 4, 32)],
            )
            templates = build_template_sets(
                {"raw": [row for path in template_paths for row in read_replay_details(path)]}
            )
            report = audit_shadow({"physical": read_replay_details(target)}, templates)

        case = report["corpora"]["physical"]["cases"][0]
        self.assertEqual(case["expected_mask"], 0x25)
        self.assertEqual(case["corridor"]["fitted_mask"], 0x25)
        self.assertTrue(case["corridor"]["disagrees_with_fine"])
        self.assertFalse(case["corridor"]["disagrees_with_profile"])
        self.assertTrue(case["corridor"]["disagrees_with_temporal"])
        self.assertEqual(report["corpora"]["physical"]["exact_cases"], 1)
        projected = report["corpora"]["physical"]["bounded_secondary"][0]
        self.assertEqual(projected["changed_frames"], 1)
        self.assertEqual(projected["exact_group_frames"], 2)
        self.assertEqual(projected["matched_label_frames"], 9)
        self.assertEqual(projected["wrong_string_voices"], 4)

    def test_acceptance_requires_both_long_unison_gains_without_new_errors(self):
        thresholds = (0.0, 0.00025, 0.0005, 0.001, 0.002, 0.005, 0.01)

        def candidates(matched: int, exact: int, wrong: int = 2738):
            return [
                {
                    "margin_threshold": threshold,
                    "changed_frames": 0,
                    "exact_group_frames": exact,
                    "matched_label_frames": matched,
                    "wrong_string_voices": wrong,
                }
                for threshold in thresholds
            ]

        unchanged = [
            {
                "margin_threshold": threshold,
                "changed_frames": 0,
                "exact_group_frames": 0,
                "matched_label_frames": 0,
                "wrong_string_voices": 0,
            }
            for threshold in thresholds
        ]
        report = {
            "corpora": {
                "physical_long_low": {
                    "bounded_secondary": candidates(28171, 28171),
                    "cases": [{
                        "expected_mask": 7,
                        "labeled_frames": 39378,
                        "current_matched_frames": 11338,
                        "per_frame_shadow": {
                            "bounded_secondary": candidates(11732, 11732),
                        },
                    }],
                },
                "ordinary_chords": {
                    "bounded_secondary": candidates(128760, 0, 104018),
                },
                "constructed_short_unisons": {
                    "bounded_secondary": candidates(243954, 0, 112967),
                },
                "isolated_08": {"bounded_secondary": copy.deepcopy(unchanged)},
                "isolated_05": {"bounded_secondary": copy.deepcopy(unchanged)},
                "isolated_02": {"bounded_secondary": copy.deepcopy(unchanged)},
                "physical_short_middle": {"bounded_secondary": copy.deepcopy(unchanged)},
                "physical_short_high_mid": {"bounded_secondary": copy.deepcopy(unchanged)},
                "physical_short_high": {"bounded_secondary": copy.deepcopy(unchanged)},
                "synthetic_four": {},
                "physical_four_diagnostic": {},
            },
            "target_aggregates": {
                "physical_long_low": {
                    "matched": 27486,
                    "false_wrong_string_voices": 2738,
                },
                "ordinary_chords": {
                    "matched": 128760,
                    "false_wrong_string_voices": 104018,
                    "false_wrong_note_voices": 195380,
                    "false_positive_voices": 366835,
                },
                "constructed_short_unisons": {
                    "matched": 243954,
                    "false_wrong_string_voices": 112967,
                    "false_wrong_note_voices": 211147,
                    "false_positive_voices": 345916,
                },
                "isolated_08": {"labeled": 31050, "matched": 27473},
                "isolated_05": {"labeled": 31050, "matched": 19952},
                "isolated_02": {"labeled": 35550, "matched": 24044},
            },
            "block_fingerprints": {"32": "same", "512": "same", "1024": "same"},
        }
        accepted = _acceptance_report(report)
        self.assertTrue(accepted["classifier_gate_pass"])
        self.assertTrue(accepted["intervals"]["passes"])
        self.assertEqual(accepted["intervals"]["required_matched"], 243954)
        self.assertEqual(
            accepted["intervals"]["maximum_wrong_string_voices"], 112967,
        )
        interval_regression = copy.deepcopy(report)
        interval_regression["target_aggregates"][
            "constructed_short_unisons"
        ]["matched"] = 243953
        rejected_interval = _acceptance_report(interval_regression)
        self.assertFalse(rejected_interval["classifier_gate_pass"])
        projected_interval_regression = copy.deepcopy(report)
        projected_interval_regression["corpora"][
            "constructed_short_unisons"
        ]["bounded_secondary"][0]["wrong_string_voices"] = 999999
        rejected_projection = _acceptance_report(
            projected_interval_regression
        )
        self.assertFalse(rejected_projection["candidates"][0]["passes"])
        degraded = copy.deepcopy(report)
        for candidate in degraded["corpora"]["physical_long_low"]["cases"][0]["per_frame_shadow"]["bounded_secondary"]:
            candidate["exact_group_frames"] = 11731
        rejected = _acceptance_report(degraded)
        self.assertFalse(rejected["classifier_gate_pass"])
        self.assertEqual(rejected["decision"], "keep_classifier_disconnected")

        partial = copy.deepcopy(report)
        del partial["corpora"]["constructed_short_unisons"]
        del partial["target_aggregates"]["constructed_short_unisons"]
        partial_result = _acceptance_report(partial)
        self.assertFalse(partial_result["classifier_gate_pass"])
        self.assertFalse(partial_result["intervals"]["available"])
        self.assertFalse(partial_result["intervals"]["passes"])

        no_material_gain = copy.deepcopy(report)
        no_material_gain["target_aggregates"]["physical_long_low"][
            "matched"
        ] = 28171
        no_material_gain["corpora"]["physical_long_low"]["cases"][0][
            "current_matched_frames"
        ] = 11732
        no_gain_result = _acceptance_report(no_material_gain)
        self.assertFalse(no_gain_result["classifier_gate_pass"])
        self.assertEqual(
            no_gain_result["decision"], "keep_classifier_disconnected"
        )

    def test_tier_completion_gate_rejects_cross_corpus_regression(self):
        thresholds = (0.0, 0.00025, 0.0005, 0.001, 0.002, 0.005, 0.01)

        def projected(matched: int, exact: int, wrong: int):
            return [
                {
                    "margin_threshold": threshold,
                    "changed_frames": 0,
                    "exact_group_frames": exact,
                    "matched_label_frames": matched,
                    "wrong_string_voices": wrong,
                }
                for threshold in thresholds
            ]

        report = {
            "corpora": {
                "physical_long_low": {
                    "tier_completion": projected(28556, 12408, 2738),
                    "cases": [{
                        "expected_mask": 7,
                        "labeled_frames": 39378,
                        "current_matched_frames": 11338,
                        "tier_completion": projected(12408, 12408, 0),
                    }],
                },
                "ordinary_chords": {
                    "tier_completion": projected(251628, 0, 110754),
                },
                "constructed_short_unisons": {
                    "tier_completion": projected(243954, 0, 112967),
                },
                "isolated_08": {
                    "tier_completion": projected(27473, 0, 2922),
                },
                "isolated_05": {
                    "tier_completion": projected(19952, 0, 4269),
                },
                "isolated_02": {
                    "tier_completion": projected(24044, 0, 7004),
                },
                "physical_short_middle": {
                    "tier_completion": projected(0, 0, 17921),
                },
                "physical_short_high_mid": {
                    "tier_completion": projected(0, 0, 15340),
                },
                "physical_short_high": {
                    "tier_completion": projected(0, 0, 15497),
                },
                "synthetic_four": {},
                "physical_four_diagnostic": {},
            },
            "target_aggregates": {
                "physical_long_low": {
                    "matched": 27486,
                    "false_wrong_string_voices": 2738,
                },
                "ordinary_chords": {
                    "matched": 251628,
                    "false_wrong_string_voices": 110754,
                },
                "constructed_short_unisons": {
                    "matched": 243954,
                    "false_wrong_string_voices": 112967,
                },
                "isolated_08": {
                    "matched": 27473,
                    "false_wrong_string_voices": 2922,
                },
                "isolated_05": {
                    "matched": 19952,
                    "false_wrong_string_voices": 4269,
                },
                "isolated_02": {
                    "matched": 24044,
                    "false_wrong_string_voices": 7004,
                },
                "physical_short_middle": {
                    "matched": 0,
                    "false_wrong_string_voices": 17921,
                },
                "physical_short_high_mid": {
                    "matched": 0,
                    "false_wrong_string_voices": 15340,
                },
                "physical_short_high": {
                    "matched": 0,
                    "false_wrong_string_voices": 15497,
                },
            },
            "block_fingerprints": {"32": 1, "512": 1, "1024": 1},
        }
        accepted = _tier_completion_acceptance_report(report)
        self.assertTrue(accepted["gate_pass"])
        no_material_gain = copy.deepcopy(report)
        no_material_gain["target_aggregates"]["physical_long_low"][
            "matched"
        ] = 28556
        no_material_gain["corpora"]["physical_long_low"]["cases"][0][
            "current_matched_frames"
        ] = 12408
        no_gain_result = _tier_completion_acceptance_report(no_material_gain)
        self.assertFalse(no_gain_result["gate_pass"])
        degraded = copy.deepcopy(report)
        degraded["corpora"]["ordinary_chords"]["tier_completion"][0][
            "wrong_string_voices"
        ] += 1
        rejected = _tier_completion_acceptance_report(degraded)
        self.assertFalse(rejected["candidates"][0]["passes"])
        interval_regression = copy.deepcopy(report)
        interval_regression["corpora"]["constructed_short_unisons"][
            "tier_completion"
        ][0]["wrong_string_voices"] = 999999
        rejected_interval = _tier_completion_acceptance_report(
            interval_regression
        )
        self.assertFalse(rejected_interval["candidates"][0]["passes"])


if __name__ == "__main__":
    unittest.main()
