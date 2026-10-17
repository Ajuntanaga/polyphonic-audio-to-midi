import pathlib
import tempfile
import unittest

from tools.audit_string_posterior_confusion import (
    SPECTRAL_HEAD_FIELDS,
    audit_detail_files,
    audit_failure_attribution,
    audit_fret_bin_accuracy,
    audit_spectral_head_files,
)


class StringPosteriorConfusionAuditTests(unittest.TestCase):
    def test_aggregates_exact_physical_lane_and_unresolved_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            detail = pathlib.Path(temporary) / "detail.tsv"
            detail.write_text(
                "summary\nvalues\n"
                "string_mask\tlabeled\tstring_fret_posterior_best\n"
                "1\t12\t0:7,1:3,8:2\n"
                "2\t5\t1:4,8:1\n",
                encoding="utf-8",
            )
            result = audit_detail_files([detail])

        self.assertEqual(result[0], [7, 3, 0, 0, 0, 0, 0, 0, 2])
        self.assertEqual(result[1], [0, 4, 0, 0, 0, 0, 0, 0, 1])

    def test_rejects_non_single_lane_labels_and_incomplete_histograms(self):
        for row in ("3\t2\t0:2", "1\t3\t0:2"):
            with self.subTest(row=row), tempfile.TemporaryDirectory() as temporary:
                detail = pathlib.Path(temporary) / "detail.tsv"
                detail.write_text(
                    "summary\nvalues\n"
                    "string_mask\tlabeled\tstring_fret_posterior_best\n"
                    f"{row}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    audit_detail_files([detail])

    def test_aggregates_each_spectral_head_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            detail = pathlib.Path(temporary) / "detail.tsv"
            header = "\t".join(("string_mask", "labeled", *SPECTRAL_HEAD_FIELDS))
            values = "\t".join(("4", "5", "2:5", "1:5", "2:3,8:2", "3:5", "2:5"))
            detail.write_text(
                f"summary\nvalues\n{header}\n{values}\n", encoding="utf-8"
            )
            result = audit_spectral_head_files([detail])

        self.assertEqual(result["spectral_low_best"][2][2], 5)
        self.assertEqual(result["spectral_low_mid_best"][2][1], 5)
        self.assertEqual(result["spectral_high_mid_best"][2][2], 3)
        self.assertEqual(result["spectral_high_mid_best"][2][8], 2)
        self.assertEqual(result["spectral_high_best"][2][3], 5)
        self.assertEqual(
            result["spectral_overtone_separation_best"][2][2], 5
        )

    def test_reports_accuracy_by_physical_fret_region(self):
        with tempfile.TemporaryDirectory() as temporary:
            detail = pathlib.Path(temporary) / "detail.tsv"
            detail.write_text(
                "summary\nvalues\n"
                "midi_note\tstring_mask\tlabeled\tstring_fret_posterior_best\n"
                "32\t1\t10\t0:8,1:2\n"
                "50\t1\t5\t0:1,1:4\n",
                encoding="utf-8",
            )
            result = audit_fret_bin_accuracy(
                [detail], ("string_fret_posterior_best",)
            )

        self.assertEqual(
            result["string_fret_posterior_best"],
            [(8, 10), (0, 0), (0, 0), (1, 5)],
        )

    def test_attributes_lane_outcomes_jointly_to_selector_and_posterior(self):
        with tempfile.TemporaryDirectory() as temporary:
            detail = pathlib.Path(temporary) / "detail.tsv"
            detail.write_text(
                "summary\nvalues\n"
                "selection_selected_lane_outcomes\t"
                "selection_dp_evicted_lane_outcomes\t"
                "posterior_expected_lane_outcomes\t"
                "posterior_other_lane_outcomes\t"
                "posterior_unresolved_lane_outcomes\n"
                "1:7,2:3\t0:5\t1:6,2:1\t2:2\t0:6\n",
                encoding="utf-8",
            )
            result = audit_failure_attribution([detail])

        self.assertEqual(result["selector"]["selected"], [0, 7, 3, 0, 0, 0])
        self.assertEqual(result["selector"]["dp_evicted"], [5, 0, 0, 0, 0, 0])
        self.assertEqual(result["posterior"]["expected"], [0, 6, 1, 0, 0, 0])
        self.assertEqual(result["posterior"]["other"], [0, 0, 2, 0, 0, 0])
        self.assertEqual(result["posterior"]["unresolved"], [6, 0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
