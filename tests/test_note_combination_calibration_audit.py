import importlib.util
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "audit_note_combination_calibration.py"


def load_module():
    spec = importlib.util.spec_from_file_location("note_combination_audit", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NoteCombinationCalibrationAuditTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.labels = (
            ROOT
            / "build"
            / "physical-capture"
            / "calibration-bank-experiment-cents16-final"
            / "labels"
            / "raw"
        )

    def test_ledger_audit_proves_note_and_combination_coverage(self):
        audit = self.module.audit_ledger(self.labels)
        self.assertEqual(audit["note_classes"], 200)
        self.assertEqual(audit["recorded_occurrences"], 555)
        self.assertEqual(audit["minimum_occurrences_per_class"], 2)
        self.assertEqual(audit["pairwise_cases"], 1031)
        self.assertEqual(audit["covered_factor_pairs"], 28 * 26 * 26)
        self.assertEqual(audit["unison_cases"], 1060)
        self.assertEqual(
            audit["unison_cases_by_size"], {"2": 367, "3": 410, "4": 283}
        )

    def test_summary_score_does_not_double_count_wrong_note_or_string(self):
        score = self.module.score_summary(
            {
                "labeled": "100",
                "matched": "40",
                "false_positive_voices": "10",
                "false_wrong_note_voices": "7",
                "false_wrong_string_voices": "8",
            }
        )
        self.assertAlmostEqual(score["precision"], 0.8)
        self.assertAlmostEqual(score["recall"], 0.4)
        self.assertAlmostEqual(score["f1"], 8.0 / 15.0)

    def test_string_topology_rejects_masks_outside_the_eight_string_bank(self):
        self.assertEqual(self.module.string_topology(0b00000111), "consecutive")
        self.assertEqual(self.module.string_topology(0b00001011), "nonconsecutive")
        for invalid in (0, 1, 1 << 8, (1 << 8) | 3):
            with self.subTest(mask=invalid), self.assertRaises(ValueError):
                self.module.string_topology(invalid)

    def test_calibration_selection_enforces_required_unison_capacity(self):
        rows = [
            {
                "trim": "-12",
                "sensitivity": "50",
                "response": "20",
                "polyphony": "2",
                "labeled": "100",
                "matched": "60",
                "false_positive_voices": "10",
                "false_wrong_note_voices": "0",
                "false_wrong_string_voices": "0",
            },
            {
                "trim": "-10",
                "sensitivity": "50",
                "response": "20",
                "polyphony": "4",
                "labeled": "100",
                "matched": "55",
                "false_positive_voices": "12",
                "false_wrong_note_voices": "0",
                "false_wrong_string_voices": "0",
            },
        ]
        selected = self.module.choose_calibration(rows, minimum_polyphony=4)
        self.assertEqual(selected["polyphony"], 4)
        self.assertEqual(selected["trim_db"], -10.0)

    def test_replay_audit_reports_exact_unison_size_and_string_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            labels = root / "labels.tsv"
            replay = root / "replay.tsv"
            labels.write_text(
                "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\texpected_cents\n"
                "0\t100\t60\t128\t1\t0.0\n"
                "31\t100\t56\t64\t1\t0.0\n",
                encoding="utf-8",
            )
            replay.write_text(
                "labeled\tmatched\tfalse_positive_voices\tfalse_wrong_note_voices\tfalse_wrong_string_voices\n"
                "20\t15\t5\t2\t3\n"
                "label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\tlabeled\tmatched\n"
                "0\t0\t100\t60\t128\t10\t9\n"
                "1\t31\t100\t56\t64\t10\t6\n",
                encoding="utf-8",
            )
            audit = self.module.audit_replay(labels, replay, case_stride=200)
        self.assertEqual(audit["label_rows"], 2)
        self.assertEqual(audit["recall_by_unison_size"], {"2": 0.75})
        self.assertEqual(audit["recall_by_string"], {"1": 0.9, "2": 0.6})
        self.assertAlmostEqual(audit["summary"]["f1"], 0.75)

    def test_replay_audit_reports_exact_three_lane_simultaneous_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            labels = root / "labels.tsv"
            replay = root / "replay.tsv"
            labels.write_text(
                "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\texpected_cents\n"
                "31\t100\t60\t128\t1\t0.0\n"
                "31\t100\t60\t64\t1\t0.0\n"
                "31\t100\t60\t32\t1\t0.0\n",
                encoding="utf-8",
            )
            detail_header = (
                "label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t"
                "labeled\tmatched\tobserved_note_lane_masks\n"
            )
            histogram = "0:2,192:3,224:5,225:1"
            replay.write_text(
                "labeled\tmatched\tfalse_positive_voices\tfalse_wrong_note_voices\tfalse_wrong_string_voices\n"
                "33\t24\t2\t0\t0\n"
                + detail_header
                + f"0\t31\t100\t60\t128\t11\t8\t{histogram}\n"
                + f"1\t31\t100\t60\t64\t11\t8\t{histogram}\n"
                + f"2\t31\t100\t60\t32\t11\t8\t{histogram}\n",
                encoding="utf-8",
            )
            audit = self.module.audit_replay(labels, replay, case_stride=200)
        recovery = audit["simultaneous_lane_recovery"]
        self.assertEqual(recovery["groups"], 1)
        self.assertEqual(recovery["frames"], 11)
        self.assertEqual(recovery["exact_mask_frames"], 5)
        self.assertEqual(recovery["full_inclusion_frames"], 6)
        self.assertEqual(recovery["at_least_three_correct_frames"], 6)
        self.assertAlmostEqual(recovery["exact_rate_by_unison_size"]["3"], 5 / 11)
        self.assertAlmostEqual(
            recovery["at_least_three_rate_by_unison_size"]["3"], 6 / 11
        )
        self.assertAlmostEqual(recovery["exact_rate_by_string_set"]["1,2,3"], 5 / 11)
        self.assertAlmostEqual(recovery["exact_rate_by_midi_note"]["60"], 5 / 11)

    def test_recovery_by_size_does_not_reuse_the_last_group_counts(self):
        labels = [
            {"start_sample": "0", "midi_note": "60", "string_mask": str(mask)}
            for mask in (128, 64, 32)
        ] + [
            {"start_sample": "200", "midi_note": "56", "string_mask": str(mask)}
            for mask in (64, 32)
        ]
        details = [
            {"labeled": "11", "observed_note_lane_masks": "0:2,192:3,224:5,225:1"}
            for _ in range(3)
        ] + [
            {"labeled": "10", "observed_note_lane_masks": "0:10"}
            for _ in range(2)
        ]
        recovery = self.module.simultaneous_lane_recovery(labels, details, 200)
        self.assertEqual(recovery["exact_rate_by_unison_size"]["2"], 0.0)
        self.assertAlmostEqual(recovery["exact_rate_by_unison_size"]["3"], 5 / 11)

    def test_recovery_separates_consecutive_from_nonconsecutive_string_topology(self):
        labels = [
            {"start_sample": "0", "midi_note": "60", "string_mask": str(mask)}
            for mask in (128, 64, 32)
        ] + [
            {"start_sample": "200", "midi_note": "64", "string_mask": str(mask)}
            for mask in (128, 32, 8)
        ]
        details = [
            {"labeled": "10", "observed_note_lane_masks": "224:7,192:3"}
            for _ in range(3)
        ] + [
            {"labeled": "8", "observed_note_lane_masks": "168:2,160:6"}
            for _ in range(3)
        ]

        recovery = self.module.simultaneous_lane_recovery(labels, details, 200)

        self.assertEqual(
            recovery["frames_by_string_topology"],
            {"consecutive": 10, "nonconsecutive": 8},
        )
        self.assertAlmostEqual(
            recovery["exact_rate_by_string_topology"]["consecutive"], 0.7
        )
        self.assertAlmostEqual(
            recovery["exact_rate_by_string_topology"]["nonconsecutive"], 0.25
        )
        self.assertAlmostEqual(
            recovery["at_least_three_rate_by_string_topology"]["consecutive"],
            0.7,
        )
        self.assertAlmostEqual(
            recovery["at_least_three_rate_by_string_topology"]["nonconsecutive"],
            0.25,
        )


if __name__ == "__main__":
    unittest.main()
