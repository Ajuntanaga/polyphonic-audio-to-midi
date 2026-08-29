import importlib.util
import pathlib
import subprocess
import sys
import tempfile
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

    def test_completion_requires_the_final_exact_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            completion = pathlib.Path(temporary) / "phase.log"
            self.assertFalse(GUARDED_REAPER.completion_published(completion))
            completion.write_text("suite-finish\ntrailing\n", encoding="utf-8")
            self.assertFalse(GUARDED_REAPER.completion_published(completion))
            completion.write_text("script-start\nsuite-finish\n", encoding="utf-8")
            self.assertTrue(GUARDED_REAPER.completion_published(completion))

    def test_unexpected_completion_file_is_refused(self):
        result = self.run_runner(
            "--dry-run",
            "--gui",
            "--profile",
            str(PROFILE),
            "--completion-file",
            "/tmp/not-the-m3-completion-file",
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
        self.assertIn("unexpected completion file", result.stdout + result.stderr)

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
        self.assertIn("TasksMax=64", result.stdout)
        self.assertIn("--cpu=45:45", result.stdout)
        self.assertIn("taskset -c", result.stdout)
        self.assertIn(str(PROFILE), result.stdout)
        self.assertIn("-noactivate", result.stdout)

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

    def test_post_exit_settle_catches_delayed_focus_steal(self):
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "restore_launch_workspace",
                side_effect=[False, False, True, False],
            ) as restore,
            mock.patch.object(GUARDED_REAPER.time, "sleep") as sleep,
        ):
            restored = GUARDED_REAPER.settle_launch_workspace(
                {},
                1,
                4,
                polls=4,
                interval_seconds=0.05,
            )

        self.assertEqual(restored, 1)
        self.assertEqual(restore.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_post_exit_settle_is_noop_when_launch_started_on_target(self):
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "restore_launch_workspace",
            ) as restore,
            mock.patch.object(GUARDED_REAPER.time, "sleep") as sleep,
        ):
            restored = GUARDED_REAPER.settle_launch_workspace({}, 4, 4)

        self.assertEqual(restored, 0)
        restore.assert_not_called()
        sleep.assert_not_called()

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

    def test_reaper_window_snapshot_collects_only_existing_reaper_ids(self):
        listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=0,
            stdout=(
                "0x0480000a  1 reaper.REAPER workstation Existing REAPER\n"
                "0x03a00007  1 codex.Codex workstation Codex\n"
                "0x04a00011  4 reaper.REAPER workstation Other REAPER\n"
            ),
            stderr="",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            return_value=listing,
        ):
            window_ids = GUARDED_REAPER.reaper_window_ids({})

        self.assertEqual(window_ids, {"0x0480000a", "0x04a00011"})

    def test_background_workspace_mover_ignores_preexisting_reaper_window(self):
        listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=0,
            stdout=(
                "0x0480000a  0 reaper.REAPER workstation User session\n"
                "0x04a00011  1 reaper.REAPER workstation Disposable test\n"
            ),
            stderr="",
        )
        hidden = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-ir", "0x04a00011", "-b", "add,hidden"],
            returncode=0,
            stdout="",
            stderr="",
        )
        moved = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-ir", "0x04a00011", "-t", "4"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=[listing, hidden, moved],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once(
                {},
                5,
                background=True,
                excluded_window_ids={"0x0480000a"},
            )

        self.assertEqual(count, 1)
        self.assertNotIn("0x0480000a", str(run.call_args_list[1:]))

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

    def test_workspace_mover_retries_a_transient_bad_drawable(self):
        bad_drawable = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=1,
            stdout="",
            stderr=(
                "X Error of failed request: BadDrawable "
                "(invalid Pixmap or Window parameter)"
            ),
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
            side_effect=[bad_drawable, stable_listing],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once({}, 5)

        self.assertEqual(count, 0)
        self.assertEqual(run.call_count, 2)

    def test_workspace_mover_defers_after_repeated_transient_destroyed_windows(self):
        bad_window = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=1,
            stdout="",
            stderr="X Error of failed request: BadWindow (invalid Window parameter)",
        )
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=[bad_window, bad_window, bad_window],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once({}, 5)

        self.assertEqual(count, 0)
        self.assertEqual(run.call_count, 3)

    def test_background_workspace_mover_hides_before_placing_reaper(self):
        listing = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-l", "-x"],
            returncode=0,
            stdout="0x0480000a  1 reaper.REAPER workstation M3 harness\n",
            stderr="",
        )
        hidden = subprocess.CompletedProcess(
            args=["/usr/bin/wmctrl", "-ir", "0x0480000a", "-b", "add,hidden"],
            returncode=0,
            stdout="",
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
            side_effect=[listing, hidden, moved],
        ) as run:
            count = GUARDED_REAPER.move_reaper_windows_once(
                {},
                5,
                background=True,
            )

        self.assertEqual(count, 1)
        run.assert_has_calls(
            [
                mock.call(
                    [
                        "/usr/bin/wmctrl",
                        "-ir",
                        "0x0480000a",
                        "-b",
                        "add,hidden",
                    ],
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

    def test_gui_launch_detaches_standard_streams(self):
        process = mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "require_workspace",
                return_value=1,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "settle_launch_workspace",
                return_value=0,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "restore_launch_workspace",
                return_value=False,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "reaper_window_ids",
                return_value=set(),
            ),
            mock.patch.object(
                GUARDED_REAPER.subprocess,
                "Popen",
                return_value=process,
            ) as popen,
        ):
            result = GUARDED_REAPER.run_gui_guarded(["reaper"], {}, 5)

        self.assertEqual(result, 0)
        popen.assert_called_once_with(
            ["reaper"],
            env={},
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_gui_completion_closes_only_the_disposable_process(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired(
            cmd="reaper",
            timeout=GUARDED_REAPER.COMPLETION_GRACE_SECONDS,
        )
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "require_workspace",
                return_value=1,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "settle_launch_workspace",
                return_value=0,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "restore_launch_workspace",
                return_value=False,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "reaper_window_ids",
                return_value=set(),
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "move_reaper_windows_once",
                return_value=0,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "completion_published",
                return_value=True,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "stop_process_group",
            ) as stop,
            mock.patch.object(
                GUARDED_REAPER.subprocess,
                "Popen",
                return_value=process,
            ),
        ):
            result = GUARDED_REAPER.run_gui_guarded(
                ["reaper"],
                {},
                5,
                GUARDED_REAPER.COMPLETION_FILE,
            )

        self.assertEqual(result, 0)
        stop.assert_called_once_with(process, GUARDED_REAPER.signal.SIGTERM)

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
