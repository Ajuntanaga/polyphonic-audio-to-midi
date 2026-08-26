import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.summarize_results import (
    match_note_events,
    percentile,
    score_notes,
    summarize,
)


class ReportMathTests(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        values = [10, 20, 30, 40]

        self.assertEqual(percentile(values, 0.5), 25.0)
        self.assertEqual(percentile(values, 0.95), 38.5)

    def test_score_notes_counts_true_false_and_missing_pitches(self):
        metrics = score_notes(
            expected={32, 36, 40},
            observed={32, 40, 44},
        )

        self.assertEqual(
            metrics,
            {
                "tp": 2,
                "fp": 1,
                "fn": 1,
                "precision": 2 / 3,
                "recall": 2 / 3,
                "f1": 2 / 3,
            },
        )

    def test_missing_note_off_counts_one_hanging_note(self):
        expected = [
            {
                "case_id": 7,
                "note": 60,
                "onset_sample": 100,
                "release_sample": 200,
            }
        ]
        observed = [
            {
                "case_id": 7,
                "absolute_sample": 120,
                "status": 0x90,
                "note": 60,
                "velocity": 100,
            }
        ]

        matched = match_note_events(
            expected,
            observed,
            tolerance_samples=100,
        )

        self.assertEqual(matched["matched_notes"], 1)
        self.assertEqual(matched["onset_latencies"], [20])
        self.assertEqual(matched["hanging_notes"], 1)

    def test_matching_note_off_reports_release_latency(self):
        expected = [
            {
                "case_id": 8,
                "note": 64,
                "onset_sample": 100,
                "release_sample": 200,
            }
        ]
        observed = [
            {
                "case_id": 8,
                "absolute_sample": 120,
                "status": 0x90,
                "note": 64,
                "velocity": 90,
            },
            {
                "case_id": 8,
                "absolute_sample": 230,
                "status": 0x80,
                "note": 64,
                "velocity": 0,
            },
        ]

        matched = match_note_events(
            expected,
            observed,
            tolerance_samples=100,
        )

        self.assertEqual(matched["release_latencies"], [30])
        self.assertEqual(matched["hanging_notes"], 0)

    def test_note_on_before_acoustic_onset_is_a_false_trigger(self):
        expected = [
            {
                "case_id": 9,
                "note": 67,
                "onset_sample": 100,
                "release_sample": 200,
            }
        ]
        observed = [
            {
                "case_id": 9,
                "absolute_sample": 99,
                "status": 0x90,
                "note": 67,
                "velocity": 80,
            }
        ]

        matched = match_note_events(
            expected,
            observed,
            tolerance_samples=100,
        )

        self.assertEqual(matched["matched_notes"], 0)
        self.assertEqual(matched["false_triggers"], 1)

    def test_unexpected_active_pitch_counts_as_hanging(self):
        observed = [
            {
                "case_id": 9,
                "absolute_sample": 150,
                "status": 0x90,
                "note": 71,
                "velocity": 80,
            }
        ]

        matched = match_note_events(
            expected=[],
            observed=observed,
            tolerance_samples=100,
        )

        self.assertEqual(matched["false_triggers"], 1)
        self.assertEqual(matched["hanging_notes"], 1)

    def test_repeated_note_on_is_counted_as_a_duplicate(self):
        expected = [
            {
                "case_id": 10,
                "note": 69,
                "onset_sample": 100,
                "release_sample": 200,
            }
        ]
        observed = [
            {
                "case_id": 10,
                "absolute_sample": 120,
                "status": 0x90,
                "note": 69,
                "velocity": 90,
            },
            {
                "case_id": 10,
                "absolute_sample": 130,
                "status": 0x90,
                "note": 69,
                "velocity": 91,
            },
            {
                "case_id": 10,
                "absolute_sample": 230,
                "status": 0x80,
                "note": 69,
                "velocity": 0,
            },
        ]

        matched = match_note_events(
            expected,
            observed,
            tolerance_samples=100,
        )

        self.assertEqual(matched["duplicate_note_ons"], 1)
        self.assertEqual(matched["false_triggers"], 1)

    def test_summarize_reports_note_scores_and_chord_completion(self):
        cases = [
            {
                "case_id": 20,
                "expected": {60, 64},
                "onset_sample": 100,
                "release_sample": 200,
                "timeout_samples": 100,
            }
        ]
        events = [
            {
                "case_id": 20,
                "absolute_sample": 120,
                "status": 0x90,
                "note": 60,
                "velocity": 80,
            },
            {
                "case_id": 20,
                "absolute_sample": 150,
                "status": 0x90,
                "note": 64,
                "velocity": 81,
            },
            {
                "case_id": 20,
                "absolute_sample": 230,
                "status": 0x80,
                "note": 60,
                "velocity": 0,
            },
            {
                "case_id": 20,
                "absolute_sample": 240,
                "status": 0x80,
                "note": 64,
                "velocity": 0,
            },
        ]

        report = summarize(cases, events)

        self.assertEqual(report["tp"], 2)
        self.assertEqual(report["fp"], 0)
        self.assertEqual(report["fn"], 0)
        self.assertEqual(report["precision"], 1.0)
        self.assertEqual(report["recall"], 1.0)
        self.assertEqual(report["f1"], 1.0)
        self.assertEqual(report["onset_latencies"], [20, 50])
        self.assertEqual(report["release_latencies"], [30, 40])
        self.assertEqual(report["chord_completion_latencies"], [50])
        self.assertEqual(report["hanging_notes"], 0)

    def test_summarize_uses_each_staggered_notes_acoustic_onset(self):
        cases = [
            {
                "case_id": 22,
                "expected": {60, 64},
                "expected_events": [
                    {
                        "case_id": 22,
                        "note": 60,
                        "onset_sample": 100,
                        "release_sample": 200,
                    },
                    {
                        "case_id": 22,
                        "note": 64,
                        "onset_sample": 120,
                        "release_sample": 220,
                    },
                ],
                "onset_sample": 100,
                "release_sample": 220,
                "timeout_samples": 140,
            }
        ]
        events = [
            {
                "case_id": 22,
                "absolute_sample": 110,
                "status": 0x90,
                "note": 60,
                "velocity": 80,
            },
            {
                "case_id": 22,
                "absolute_sample": 135,
                "status": 0x90,
                "note": 64,
                "velocity": 80,
            },
            {
                "case_id": 22,
                "absolute_sample": 205,
                "status": 0x80,
                "note": 60,
                "velocity": 0,
            },
            {
                "case_id": 22,
                "absolute_sample": 230,
                "status": 0x80,
                "note": 64,
                "velocity": 0,
            },
        ]

        report = summarize(cases, events)

        self.assertEqual(report["onset_latencies"], [10, 15])
        self.assertEqual(report["release_latencies"], [5, 10])
        self.assertEqual(report["chord_completion_latencies"], [35])

    def test_summarize_counts_note_on_during_silence(self):
        cases = [
            {
                "case_id": 21,
                "expected": set(),
                "onset_sample": 100,
                "release_sample": 200,
                "timeout_samples": 100,
            }
        ]
        events = [
            {
                "case_id": 21,
                "absolute_sample": 150,
                "status": 0x90,
                "note": 48,
                "velocity": 70,
            }
        ]

        report = summarize(cases, events)

        self.assertEqual(report["silence_events"], 1)
        self.assertEqual(report["fp"], 1)

    def test_cli_writes_a_passing_acceptance_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            cases = directory / "cases.tsv"
            events = directory / "events.tsv"
            report = directory / "report.md"
            cases.write_text(
                "case_id\tsample_rate\tblock_size\tmode\tnotes\t"
                "detune_cents\tmissing_fundamental\tgains_db\tnoise_db\t"
                "hum_db\tclip\tstagger_ms\texpected\n"
                "1\t48000\t128\tgeneral\t60\t0\t0\t0\t-120\t-120\t"
                "0\t0\t60\n",
                encoding="utf-8",
            )
            events.write_text(
                "case_id\tabsolute_sample\toffset\tstatus\tnote\tvelocity\n"
                "1\t24020\t0\t144\t60\t90\n"
                "1\t38660\t0\t128\t60\t0\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/summarize_results.py",
                    "--events",
                    str(events),
                    "--cases",
                    str(cases),
                    "--out",
                    str(report),
                    "--fail-below-precision",
                    "0.98",
                    "--fail-below-recall",
                    "0.98",
                    "--fail-on-hanging-note",
                ],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("synthetic acceptance: pass", completed.stdout)
            rendered = report.read_text(encoding="utf-8")
            self.assertIn("| Precision | 1.000000 |", rendered)
            self.assertIn("| Recall | 1.000000 |", rendered)
            self.assertIn("| Hanging notes | 0 |", rendered)

    def test_cli_uses_staggered_ground_truth_for_each_note(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            cases = directory / "cases.tsv"
            events = directory / "events.tsv"
            report = directory / "report.md"
            cases.write_text(
                "case_id\tsample_rate\tblock_size\tmode\tnotes\t"
                "detune_cents\tmissing_fundamental\tgains_db\tnoise_db\t"
                "hum_db\tclip\tstagger_ms\texpected\n"
                "2\t48000\t128\tgeneral\t60,64\t0\t0\t0,0\t-120\t-120\t"
                "0\t1\t60,64\n",
                encoding="utf-8",
            )
            events.write_text(
                "case_id\tabsolute_sample\toffset\tstatus\tnote\tvelocity\n"
                "2\t24010\t0\t144\t60\t90\n"
                "2\t24060\t0\t144\t64\t90\n"
                "2\t38645\t0\t128\t60\t0\n"
                "2\t38690\t0\t128\t64\t0\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/summarize_results.py",
                    "--events",
                    str(events),
                    "--cases",
                    str(cases),
                    "--out",
                    str(report),
                ],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            rendered = report.read_text(encoding="utf-8")
            self.assertIn("| Onset p50 | 11.000 samples |", rendered)
            self.assertIn("| Chord completion p95 | 60.000 samples |", rendered)

    def test_cli_treats_dash_note_sentinel_as_silence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            cases = directory / "cases.tsv"
            events = directory / "events.tsv"
            report = directory / "report.md"
            cases.write_text(
                "case_id\tsample_rate\tblock_size\tmode\tnotes\t"
                "detune_cents\tmissing_fundamental\tgains_db\tnoise_db\t"
                "hum_db\tclip\tstagger_ms\texpected\n"
                "3\t48000\t128\tsilence\t-\t0\t0\t0\t-120\t-120\t"
                "0\t0\t-\n",
                encoding="utf-8",
            )
            events.write_text(
                "case_id\tabsolute_sample\toffset\tstatus\tnote\tvelocity\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/summarize_results.py",
                    "--events",
                    str(events),
                    "--cases",
                    str(cases),
                    "--out",
                    str(report),
                    "--fail-below-precision",
                    "0.98",
                    "--fail-below-recall",
                    "0.98",
                ],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            rendered = report.read_text(encoding="utf-8")
            self.assertIn("| Silence events | 0 |", rendered)
            self.assertIn("| Precision | 1.000000 |", rendered)


if __name__ == "__main__":
    unittest.main()
