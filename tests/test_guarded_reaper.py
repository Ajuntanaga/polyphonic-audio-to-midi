import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_guarded_reaper.py"
PROFILE = ROOT / "build/reaper-test/reaper.ini"
SPEC = importlib.util.spec_from_file_location("run_guarded_reaper", RUNNER)
GUARDED_REAPER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GUARDED_REAPER)


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

    def test_keyboard_interrupt_returns_shell_status_without_traceback(self):
        with (
            mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
            mock.patch.object(
                GUARDED_REAPER.subprocess,
                "run",
                side_effect=KeyboardInterrupt,
            ),
        ):
            result = GUARDED_REAPER.main(
                [
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
                ]
            )
        self.assertEqual(result, 130)

    def test_workspace_five_maps_to_wmctrl_desktop_four(self):
        self.assertEqual(GUARDED_REAPER.workspace_index(5), 4)

    def test_workspace_requirement_returns_the_active_workspace(self):
        listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-d"],
            returncode=0,
            stdout=(
                "0  - DG: 1920x1080 VP: 0,0 WA: 0,0 1920x1080 One\n"
                "1  * DG: 1920x1080 VP: 0,0 WA: 0,0 1920x1080 Two\n"
                "4  - DG: 1920x1080 VP: 0,0 WA: 0,0 1920x1080 Five\n"
            ),
            stderr="",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            return_value=listing,
        ):
            active = GUARDED_REAPER.require_workspace({}, 5)

        self.assertEqual(active, 1)

    def test_launch_focus_restore_returns_from_target_to_original_workspace(self):
        restored = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-s", "1"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "active_workspace_index",
                return_value=4,
            ),
            mock.patch.object(
                GUARDED_REAPER.subprocess,
                "run",
                return_value=restored,
            ) as run,
        ):
            changed = GUARDED_REAPER.restore_launch_workspace({}, 1, 4)

        self.assertTrue(changed)
        run.assert_called_once_with(
            ["/usr/bin/wmctrl", "-s", "1"],
            env={},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_launch_focus_restore_does_not_override_a_third_workspace(self):
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "active_workspace_index",
                return_value=2,
            ),
            mock.patch.object(GUARDED_REAPER.subprocess, "run") as run,
        ):
            changed = GUARDED_REAPER.restore_launch_workspace({}, 1, 4)

        self.assertFalse(changed)
        run.assert_not_called()

    def test_workspace_mover_targets_only_reaper_windows(self):
        listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=0,
            stdout=(
                "0x0480000a  1 reaper.REAPER workstation M3 harness\n"
                "0x03a00007  1 codex.Codex workstation Codex\n"
                "0x04a00011  4 reaper.REAPER workstation Already placed\n"
            ),
            stderr="",
        )
        moved = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-ir", "0x0480000a", "-t", "4"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=[listing, moved],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once({}, 5)

        self.assertEqual(count, 1)
        run.assert_has_calls(
            [
                mock.call(
                    ["/usr/bin/wmctrl", "-l", "-x"],
                    env={},
                    text=True,
                    capture_output=True,
                    check=False,
                ),
                mock.call(
                    ["/usr/bin/wmctrl", "-ir", "0x0480000a", "-t", "4"],
                    env={},
                    text=True,
                    capture_output=True,
                    check=False,
                ),
            ]
        )

    def test_workspace_mover_retries_a_transient_destroyed_window(self):
        bad_window = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=1,
            stdout="",
            stderr="X Error of failed request: BadWindow (invalid Window parameter)",
        )
        stable_listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=[bad_window, stable_listing],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once({}, 5)

        self.assertEqual(count, 0)
        self.assertEqual(run.call_count, 2)

    def test_workspace_mover_refuses_nontransient_listing_errors(self):
        denied = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=1,
            stdout="",
            stderr="Cannot open display",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            return_value=denied,
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "could not list GUI windows"):
                GUARDED_REAPER.move_reaper_windows_once({}, 5)

        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
