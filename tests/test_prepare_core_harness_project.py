import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PREPARER = ROOT / "tools/prepare_core_harness_project.py"
BUILD = ROOT / "build"


class PrepareCoreHarnessProjectTests(unittest.TestCase):
    def test_prepares_literal_rate_and_case_slider_state(self):
        with tempfile.TemporaryDirectory(dir=BUILD) as temporary:
            temporary_path = pathlib.Path(temporary)
            source = temporary_path / "source.RPP"
            output_directory = temporary_path / "prepared"
            source.write_text(
                """<REAPER_PROJECT 0.1 \"7.79/linux-x86_64\" 1777600000
  <TRACK
    <FXCHAIN
      <JS \"tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx\" \"\"
        - - - -
      >
    >
  >
>
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--source",
                    str(source),
                    "--output-dir",
                    str(output_directory),
                    "--rate",
                    "44100",
                    "--case-id",
                    "4104",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            prepared = output_directory / "core-harness-44100-case-4104.RPP"
            self.assertTrue(prepared.is_file())
            lines = prepared.read_text(encoding="utf-8").splitlines()
            marker = next(
                index
                for index, line in enumerate(lines)
                if '<JS "tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx" ""'
                in line
            )
            self.assertEqual(lines[marker + 1].split()[:4], ["1", "3", "-", "-"])

    def test_refuses_output_outside_disposable_build_directory(self):
        with (
            tempfile.TemporaryDirectory(dir=BUILD) as source_temporary,
            tempfile.TemporaryDirectory() as outside_temporary,
        ):
            source = pathlib.Path(source_temporary) / "source.RPP"
            source.write_text(
                """<REAPER_PROJECT 0.1 \"7.79/linux-x86_64\" 1777600000
  <TRACK
    <FXCHAIN
      <JS \"tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx\" \"\"
        - - - -
      >
    >
  >
>
""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--source",
                    str(source),
                    "--output-dir",
                    outside_temporary,
                    "--rate",
                    "48000",
                    "--case-id",
                    "4101",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("outside disposable build directory", result.stderr)

    def test_refuses_source_outside_disposable_build_directory(self):
        with (
            tempfile.TemporaryDirectory() as outside_temporary,
            tempfile.TemporaryDirectory(dir=BUILD) as output_temporary,
        ):
            source = pathlib.Path(outside_temporary) / "live-project.RPP"
            source.write_text(
                """<REAPER_PROJECT 0.1 \"7.79/linux-x86_64\" 1777600000
  <TRACK
    <FXCHAIN
      <JS \"tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx\" \"\"
        - - - -
      >
    >
  >
>
""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARER),
                    "--source",
                    str(source),
                    "--output-dir",
                    output_temporary,
                    "--rate",
                    "48000",
                    "--case-id",
                    "4101",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("source project is outside disposable build directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
