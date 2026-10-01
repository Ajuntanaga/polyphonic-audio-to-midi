import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_calibration_bank_experiment as experiment


class CalibrationBankExperimentTests(unittest.TestCase):
    def test_matrix_keeps_audio_truth_independent_from_bank_under_test(self):
        cases = experiment.build_cases(
            bank_names=("raw", "midpoint", "zero", "shuffled", "offset-p3")
        )
        self.assertEqual(
            cases,
            [
                ("raw", "raw"),
                ("raw", "midpoint"),
                ("raw", "zero"),
                ("raw", "shuffled"),
                ("raw", "offset-p3"),
                ("midpoint", "raw"),
                ("midpoint", "midpoint"),
                ("midpoint", "zero"),
                ("exact", "raw"),
                ("exact", "midpoint"),
                ("exact", "zero"),
            ],
        )

    def test_parser_accepts_extended_replay_summary(self):
        output = (
            "sample_rate\tblock\tsamples\tsnapshots\tlabeled\tmatched\t"
            "cents_observations\tcents_mean_error\tfingerprint\n"
            "96000\t512\t1000\t10\t8\t6\t4\t-1.25\tabcd\n"
            "label_index\tstart_sample\n0\t0\n"
        )
        parsed = experiment.parse_replay_summary(output)
        self.assertEqual(parsed["sample_rate"], "96000")
        self.assertEqual(parsed["matched"], "6")
        self.assertEqual(parsed["cents_mean_error"], "-1.25")

    def test_matrix_can_select_a_small_controlled_cross_section(self):
        self.assertEqual(
            experiment.build_cases(
                ("raw", "offset-m3", "shuffled"), ("raw", "exact")
            ),
            [
                ("raw", "raw"),
                ("raw", "offset-m3"),
                ("raw", "shuffled"),
                ("exact", "raw"),
                ("exact", "offset-m3"),
                ("exact", "shuffled"),
            ],
        )
        self.assertEqual(
            experiment.build_cases(("shuffled",)), [("raw", "shuffled")]
        )


if __name__ == "__main__":
    unittest.main()
