import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_guarded_reaper.py"
PROFILE = ROOT / "build/reaper-test/reaper.ini"


class GuardedReaperTests(unittest.TestCase):
    def run_runner(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_healthy_preflight_passes(self):
        result = self.run_runner(
            "--check-only",
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("guardrail preflight: ok", result.stdout)

    def test_low_memory_preflight_refuses(self):
        result = self.run_runner(
            "--check-only",
            "--available-mib",
            "3000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("available memory", result.stdout + result.stderr)

    def test_live_profile_is_refused(self):
        result = self.run_runner(
            "--dry-run",
            "--profile",
            str(pathlib.Path.home() / ".config/REAPER/reaper.ini"),
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
            "--",
            "-new",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-disposable profile", result.stdout + result.stderr)

    def test_dry_run_contains_hard_limits(self):
        result = self.run_runner(
            "--dry-run",
            "--profile",
            str(PROFILE),
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
            "--",
            "-new",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MemoryMax=512M", result.stdout)
        self.assertIn("CPUQuota=50%", result.stdout)
        self.assertIn("taskset -c", result.stdout)
        self.assertIn(str(PROFILE), result.stdout)


if __name__ == "__main__":
    unittest.main()
