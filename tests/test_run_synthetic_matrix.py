import pathlib
import tempfile
import unittest

from tools import run_synthetic_matrix
from tools.run_synthetic_matrix import (
    MAX_BATCH_SIZE,
    batch_ranges,
    group_case_rows,
    merge_batch_tsv,
    runtime_fingerprint,
    validate_batch_results,
)


class SyntheticMatrixRunnerTests(unittest.TestCase):
    def test_guard_command_passes_the_selected_reaper_to_the_guard(self):
        selected = pathlib.Path("/opt/reaper/reaper")

        command = run_synthetic_matrix._guard_command(45, selected)

        reaper_index = command.index("--reaper")
        self.assertEqual(command[reaper_index + 1], str(selected))

    def test_groups_cases_by_rate_and_block_without_reordering(self):
        rows = [
            {"case_id": "1", "sample_rate": "44100", "block_size": "32"},
            {"case_id": "2", "sample_rate": "48000", "block_size": "128"},
            {"case_id": "3", "sample_rate": "44100", "block_size": "32"},
        ]

        grouped = group_case_rows(rows)

        self.assertEqual(
            [int(row["case_id"]) for row in grouped[(44100, 32)]],
            [1, 3],
        )
        self.assertEqual(
            [int(row["case_id"]) for row in grouped[(48000, 128)]],
            [2],
        )

    def test_batch_ranges_are_bounded_and_cover_the_tail(self):
        self.assertEqual(MAX_BATCH_SIZE, 8)
        self.assertEqual(batch_ranges(10, 4), [(0, 4), (4, 4), (8, 2)])
        self.assertEqual(
            batch_ranges(38, MAX_BATCH_SIZE),
            [(0, 8), (8, 8), (16, 8), (24, 8), (32, 6)],
        )
        with self.assertRaisesRegex(ValueError, "batch size"):
            batch_ranges(10, MAX_BATCH_SIZE + 1)

    def test_validation_requires_exact_case_ids_rate_block_and_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            results = pathlib.Path(temporary)
            (results / "phase.log").write_text(
                "script-start\nsuite-finish\n",
                encoding="utf-8",
            )
            (results / "summary.tsv").write_text(
                "case_id\tstatus\treason\tactual_rate\tactual_block\n"
                "7\tpass\tok\t48000\t128\n"
                "19\tpass\tok\t48000\t128\n",
                encoding="utf-8",
            )
            (results / "events.tsv").write_text(
                "case_id\tabsolute_sample\toffset\tstatus\tnote\tvelocity\n"
                "7\t100\t0\t144\t24\t90\n"
                "7\t200\t0\t128\t24\t0\n"
                "19\t100\t0\t144\t25\t90\n"
                "19\t200\t0\t128\t25\t0\n",
                encoding="utf-8",
            )
            (results / "safety.tsv").write_text(
                "trial\tstatus\treason\n",
                encoding="utf-8",
            )

            validation = validate_batch_results(
                results,
                expected_case_ids=(7, 19),
                sample_rate=48000,
                block_size=128,
            )

            self.assertEqual(validation.summary_rows, 2)
            self.assertEqual(validation.event_rows, 4)
            with self.assertRaisesRegex(ValueError, "case IDs"):
                validate_batch_results(
                    results,
                    expected_case_ids=(7, 31),
                    sample_rate=48000,
                    block_size=128,
                )

    def test_merge_writes_one_header_and_preserves_batch_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            header = "case_id\tvalue\n"
            (first / "events.tsv").write_text(
                header + "7\ta\n19\tb\n",
                encoding="utf-8",
            )
            (second / "events.tsv").write_text(
                header + "31\tc\n",
                encoding="utf-8",
            )
            output = root / "events.tsv"

            row_count = merge_batch_tsv(
                (first, second),
                "events.tsv",
                output,
            )

            self.assertEqual(row_count, 3)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                header + "7\ta\n19\tb\n31\tc\n",
            )

    def test_runtime_fingerprint_changes_with_staged_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "Effects").mkdir()
            (root / "Scripts").mkdir()
            (root / "build").mkdir()
            effect = root / "Effects/detector.jsfx"
            effect.write_text("first\n", encoding="utf-8")
            (root / "Scripts/runner.lua").write_text("runner\n", encoding="utf-8")
            (root / "build/host-integration.RPP").write_text(
                "project\n",
                encoding="utf-8",
            )

            first = runtime_fingerprint(root)
            effect.write_text("second\n", encoding="utf-8")
            second = runtime_fingerprint(root)

            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
