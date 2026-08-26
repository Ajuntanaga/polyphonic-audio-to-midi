import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.generate_synthetic_cases import HEADER, build_cases, render_cases


class SyntheticCaseGeneratorTests(unittest.TestCase):
    def test_general_single_note_sweep_is_first_and_crossed_deterministically(self):
        cases = build_cases()
        first_twelve = [
            (
                case["case_id"],
                case["sample_rate"],
                case["block_size"],
                case["mode"],
                case["notes"],
                case["expected"],
            )
            for case in cases[:12]
        ]

        self.assertEqual(
            first_twelve,
            [
                (1, 44100, 32, "general", "24", "24"),
                (2, 44100, 64, "general", "24", "24"),
                (3, 44100, 128, "general", "24", "24"),
                (4, 44100, 256, "general", "24", "24"),
                (5, 48000, 32, "general", "24", "24"),
                (6, 48000, 64, "general", "24", "24"),
                (7, 48000, 128, "general", "24", "24"),
                (8, 48000, 256, "general", "24", "24"),
                (9, 96000, 32, "general", "24", "24"),
                (10, 96000, 64, "general", "24", "24"),
                (11, 96000, 128, "general", "24", "24"),
                (12, 96000, 256, "general", "24", "24"),
            ],
        )
        self.assertEqual(cases[12]["notes"], "25")
        self.assertEqual(cases[84 * 12]["notes"], "108")

    def test_m3_open_strings_and_first_twelve_chord_sizes_follow_the_sweep(self):
        base_cases = build_cases()[::12]

        self.assertEqual(
            [case["notes"] for case in base_cases[85:93]],
            ["32", "36", "40", "44", "48", "52", "56", "60"],
        )
        self.assertEqual(
            [case["mode"] for case in base_cases[85:93]],
            ["m3"] * 8,
        )

        dyads = [case["notes"] for case in base_cases[93:105]]
        triads = [case["notes"] for case in base_cases[105:117]]
        four_note_chords = [case["notes"] for case in base_cases[117:129]]
        self.assertEqual(
            dyads,
            [
                "32,36",
                "32,40",
                "32,44",
                "32,48",
                "32,52",
                "32,56",
                "32,60",
                "36,40",
                "36,44",
                "36,48",
                "36,52",
                "36,56",
            ],
        )
        self.assertEqual(triads[0], "32,36,40")
        self.assertEqual(triads[-1], "32,44,48")
        self.assertEqual(four_note_chords[0], "32,36,40,44")
        self.assertEqual(four_note_chords[-1], "32,36,48,60")
        self.assertEqual(
            base_cases[129]["notes"],
            "32,36,40,44,48,52,56,60",
        )
        self.assertEqual(base_cases[129]["expected"], base_cases[129]["notes"])

    def test_task_five_audio_cases_precede_open_detune_noise_cross(self):
        base_cases = build_cases()[::12]
        task_five = base_cases[130:136]

        self.assertEqual(
            [case["notes"] for case in task_five],
            [
                "40",
                "40,47",
                "32,36,40",
                "32,36,40,44,48,52,56,60",
                "40,47,52,57",
                "32,36,40,43",
            ],
        )
        self.assertEqual(task_five[4]["gains_db"], "0,-6,-24,-12")
        self.assertEqual(task_five[5]["mode"], "general:poly=3")
        self.assertEqual(task_five[5]["expected"], "32,36,40")

        crossed = base_cases[136:184]
        self.assertEqual(len(crossed), 48)
        self.assertEqual(
            [
                (
                    case["notes"],
                    case["detune_cents"],
                    case["noise_db"],
                    case["expected"],
                )
                for case in crossed[:6]
            ],
            [
                ("32", -35, -60, "32"),
                ("32", -35, -48, "32"),
                ("32", -35, -36, "32"),
                ("32", 35, -60, "32"),
                ("32", 35, -48, "32"),
                ("32", 35, -36, "32"),
            ],
        )
        self.assertEqual(
            (
                crossed[-1]["notes"],
                crossed[-1]["detune_cents"],
                crossed[-1]["noise_db"],
            ),
            ("60", 35, -36),
        )

    def test_explicit_adverse_and_lifecycle_cases_are_present_in_order(self):
        base_cases = build_cases()[::12]
        explicit = base_cases[184:198]

        self.assertEqual(
            [case["mode"] for case in explicit],
            [
                "silence",
                "noise",
                "hum50",
                "hum60",
                "dc",
                "general",
                "general",
                "general",
                "general",
                "general",
                "release",
                "general",
                "m3",
                "m3",
            ],
        )
        self.assertEqual(explicit[0]["notes"], "")
        self.assertEqual(explicit[0]["expected"], "")
        self.assertEqual(explicit[1]["noise_db"], -48)
        self.assertEqual(explicit[2]["hum_db"], -36)
        self.assertEqual(explicit[3]["hum_db"], -36)
        self.assertEqual(explicit[4]["noise_db"], -36)
        self.assertEqual(explicit[5]["clip"], 1)
        self.assertEqual(explicit[6]["missing_fundamental"], 1)
        self.assertEqual(explicit[7]["gains_db"], "0,-6,-18,-24")
        self.assertEqual(explicit[8]["stagger_ms"], 10)
        self.assertEqual(explicit[9]["notes"], "40,40")
        self.assertEqual(explicit[9]["expected"], "40")
        self.assertEqual(explicit[10]["notes"], "40")
        self.assertEqual(explicit[11]["notes"], "40,40,40")
        self.assertEqual(explicit[11]["expected"], "40")
        self.assertEqual(explicit[12]["notes"], "44,48,52,56")
        self.assertEqual(explicit[12]["expected"], "44,48,52,56")
        self.assertEqual(explicit[13]["notes"], "32,33,34,35,36,37,38,39")
        self.assertEqual(explicit[13]["expected"], "32,36")

    def test_rendered_manifest_has_exact_header_ids_and_lf_endings(self):
        cases = build_cases()
        rendered = render_cases(cases)
        lines = rendered.splitlines()

        self.assertEqual(
            HEADER,
            "case_id\tsample_rate\tblock_size\tmode\tnotes\t"
            "detune_cents\tmissing_fundamental\tgains_db\tnoise_db\t"
            "hum_db\tclip\tstagger_ms\texpected",
        )
        self.assertEqual(lines[0], HEADER)
        self.assertEqual(len(lines), 2377)
        self.assertEqual(
            [case["case_id"] for case in cases],
            list(range(1, 2377)),
        )
        self.assertTrue(rendered.endswith("\n"))
        self.assertNotIn("\r", rendered)

    def test_rendering_sorts_expected_notes_numerically(self):
        case = {
            **build_cases()[0],
            "expected": "60,32,44",
        }

        rendered = render_cases([case])

        self.assertTrue(rendered.splitlines()[1].endswith("\t32,44,60"))

    def test_rendering_uses_a_non_whitespace_sentinel_for_empty_note_lists(self):
        silence = build_cases()[184 * 12]

        rendered = render_cases([silence])

        self.assertTrue(rendered.endswith("\tsilence\t-\t0\t0\t0\t-120\t-120\t0\t0\t-\n"))

    def test_cli_writes_and_checks_a_byte_identical_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "synthetic_cases.tsv"
            root = pathlib.Path(__file__).resolve().parents[1]

            generated = subprocess.run(
                [
                    sys.executable,
                    "tools/generate_synthetic_cases.py",
                    "--output",
                    str(output),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            checked = subprocess.run(
                [
                    sys.executable,
                    "tools/generate_synthetic_cases.py",
                    "--check",
                    str(output),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(
                output.read_bytes(),
                render_cases(build_cases()).encode("utf-8"),
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn("byte-identical synthetic manifest", checked.stdout)

    def test_cli_check_rejects_a_different_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "synthetic_cases.tsv"
            output.write_text("different\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/generate_synthetic_cases.py",
                    "--check",
                    str(output),
                ],
                cwd=pathlib.Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIn("synthetic manifest differs", completed.stderr)


if __name__ == "__main__":
    unittest.main()
