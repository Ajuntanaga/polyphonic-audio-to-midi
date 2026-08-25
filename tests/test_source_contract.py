import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
REAPER = pathlib.Path("/home/ajuntanaga/opt/REAPER/reaper")


class SourceContractTests(unittest.TestCase):
    def test_production_jsfx_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/validate_source.py"), str(ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_disposable_staging_never_targets_live_profile(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/stage_reaper_test_env.py"),
                "--reaper",
                str(REAPER),
                "--output",
                str(pathlib.Path.home() / ".config/REAPER"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to stage", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
