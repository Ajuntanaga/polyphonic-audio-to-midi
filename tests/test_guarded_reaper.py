import importlib.util
import json
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

    def create_vst3_layout(self, root: pathlib.Path):
        vst3_root = root / "build/vst3/release/VST3"
        bundle = vst3_root / "M3_Polyphonic_Audio_to_MIDI_Probe.vst3"
        binary = (
            bundle
            / "Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so"
        )
        moduleinfo = bundle / "Contents/Resources/moduleinfo.json"
        binary.parent.mkdir(parents=True)
        moduleinfo.parent.mkdir(parents=True)
        binary.write_bytes(b"ELF probe fixture\n")
        moduleinfo.write_text(
            json.dumps(
                {
                    "Factory Info": {"Vendor": "ajuntanaga"},
                    "Classes": [
                        {
                            "CID": "6F62F8B1B8A14872A0D92C3C274421D8",
                            "Category": "Audio Module Class",
                            "Name": "M3 Polyphonic Audio to MIDI Probe",
                            "Sub Categories": ["Fx", "Tools"],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        profile = root / "build/reaper-test/reaper.ini"
        profile.parent.mkdir(parents=True)
        profile.write_text(
            f"[reaper]\nvstpath={vst3_root}\n", encoding="utf-8"
        )
        return vst3_root, bundle, binary, moduleinfo, profile

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
        self.assertIn("MemoryHigh=384M", result.stdout)
        self.assertIn("MemorySwapMax=64M", result.stdout)
        self.assertIn("CPUQuota=50%", result.stdout)
        self.assertIn("TasksMax=64", result.stdout)
        self.assertIn("--cpu=45:45", result.stdout)
        self.assertIn("taskset -c", result.stdout)
        self.assertIn(str(PROFILE), result.stdout)
        self.assertIn("-noactivate", result.stdout)

    def test_native_vst3_environment_requires_exact_bundle_and_profile_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
            ):
                self.assertEqual(
                    GUARDED_REAPER.validate_native_vst3_environment(
                        vst3_root, profile
                    ),
                    vst3_root,
                )
                with self.assertRaisesRegex(ValueError, "build-local VST3 path"):
                    GUARDED_REAPER.validate_native_vst3_environment(
                        root / "outside", profile
                    )
                with self.assertRaisesRegex(ValueError, "disposable profile"):
                    GUARDED_REAPER.validate_native_vst3_environment(
                        vst3_root, root / "other.ini"
                    )

    def test_native_vst3_environment_refuses_wrong_identity_extra_or_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            patches = (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                document = json.loads(moduleinfo.read_text(encoding="utf-8"))
                document["Classes"][0]["CID"] = (
                    "4A1BA42F6D7046098B52450C3842F11F"
                )
                moduleinfo.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "FUID"):
                    GUARDED_REAPER.validate_native_vst3_environment(
                        vst3_root, profile
                    )

                document["Classes"][0]["CID"] = (
                    "6F62F8B1B8A14872A0D92C3C274421D8"
                )
                moduleinfo.write_text(json.dumps(document), encoding="utf-8")
                extra = bundle / "Contents/extra.txt"
                extra.write_text("extra\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "file set"):
                    GUARDED_REAPER.validate_native_vst3_environment(
                        vst3_root, profile
                    )
                extra.unlink()

                outside = root / "outside.so"
                outside.write_bytes(b"outside\n")
                binary.unlink()
                binary.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "symlink or escapes"):
                    GUARDED_REAPER.validate_native_vst3_environment(
                        vst3_root, profile
                    )

    def test_native_vst3_path_is_profile_only_and_never_mixed_with_clap(self):
        command = GUARDED_REAPER.guarded_command(
            PROFILE,
            ["-new"],
            45,
            vst3_path=GUARDED_REAPER.BUILD_VST3_DIR,
        )
        rendered = " ".join(command)
        self.assertNotIn("VST_PATH=", rendered)
        self.assertNotIn("CLAP_PATH=", rendered)
        self.assertNotIn("M3_CLAP_PROBE_REPORT", rendered)
        self.assertNotIn("HOME=", rendered)
        self.assertNotIn(str(pathlib.Path.home() / ".config/REAPER"), rendered)

        result = self.run_runner(
            "--dry-run",
            "--profile",
            str(PROFILE),
            "--clap-path",
            str(GUARDED_REAPER.BUILD_CLAP_DIR),
            "--probe-report",
            str(GUARDED_REAPER.PROBE_REPORT),
            "--vst3-path",
            str(GUARDED_REAPER.BUILD_VST3_DIR),
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mutually exclusive", result.stdout + result.stderr)

    def test_runtime_environment_drops_inherited_plugin_paths_but_keeps_home(self):
        source = {
            "HOME": "/home/example",
            "CLAP_PATH": "/tmp/untrusted-clap",
            "VST_PATH": "/tmp/untrusted-vst",
            "VST3_PATH": "/tmp/untrusted-vst3",
            "M3_CLAP_PROBE_REPORT": "/tmp/untrusted-report",
            "DISPLAY": ":9",
        }
        sanitized = GUARDED_REAPER.sanitize_plugin_environment(source)
        self.assertEqual(sanitized["HOME"], "/home/example")
        self.assertEqual(sanitized["DISPLAY"], ":9")
        for name in (
            "CLAP_PATH",
            "VST_PATH",
            "VST3_PATH",
            "M3_CLAP_PROBE_REPORT",
        ):
            self.assertNotIn(name, sanitized)

    def test_native_clap_environment_requires_exact_build_local_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            clap_path = root / "build/native/clap"
            clap_path.mkdir(parents=True)
            artifact = clap_path / "M3_Polyphonic_Audio_to_MIDI_Probe.clap"
            artifact.write_bytes(b"probe")
            report = root / "build/reaper-test/test-results/probe-native.tsv"
            report.parent.mkdir(parents=True)
            profile = root / "build/reaper-test/reaper.ini"
            profile.write_text("[reaper]\n", encoding="utf-8")
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_CLAP_DIR", clap_path),
                mock.patch.object(GUARDED_REAPER, "PROBE_ARTIFACT", artifact),
                mock.patch.object(GUARDED_REAPER, "PROBE_REPORT", report),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
            ):
                resolved_clap, resolved_report = (
                    GUARDED_REAPER.validate_native_clap_environment(
                        clap_path,
                        report,
                        profile,
                    )
                )
                self.assertEqual(resolved_clap, clap_path)
                self.assertEqual(resolved_report, report)
                with self.assertRaisesRegex(ValueError, "build-local CLAP path"):
                    GUARDED_REAPER.validate_native_clap_environment(
                        root / "outside",
                        report,
                        profile,
                    )
                with self.assertRaisesRegex(ValueError, "probe report"):
                    GUARDED_REAPER.validate_native_clap_environment(
                        clap_path,
                        root / "wrong.tsv",
                        profile,
                    )

    def test_native_clap_environment_refuses_missing_or_escaping_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            clap_path = root / "build/native/clap"
            clap_path.mkdir(parents=True)
            artifact = clap_path / "M3_Polyphonic_Audio_to_MIDI_Probe.clap"
            report = root / "build/reaper-test/test-results/probe-native.tsv"
            report.parent.mkdir(parents=True)
            profile = root / "build/reaper-test/reaper.ini"
            profile.write_text("[reaper]\n", encoding="utf-8")
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_CLAP_DIR", clap_path),
                mock.patch.object(GUARDED_REAPER, "PROBE_ARTIFACT", artifact),
                mock.patch.object(GUARDED_REAPER, "PROBE_REPORT", report),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
            ):
                with self.assertRaisesRegex(ValueError, "probe artifact is missing"):
                    GUARDED_REAPER.validate_native_clap_environment(
                        clap_path,
                        report,
                        profile,
                    )
                outside = root / "outside-probe.clap"
                outside.write_bytes(b"outside")
                artifact.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "escapes"):
                    GUARDED_REAPER.validate_native_clap_environment(
                        clap_path,
                        report,
                        profile,
                    )

    def test_native_clap_environment_is_injected_before_command_separator(self):
        command = GUARDED_REAPER.guarded_command(
            PROFILE,
            ["-new"],
            45,
            GUARDED_REAPER.BUILD_CLAP_DIR,
            GUARDED_REAPER.PROBE_REPORT,
        )
        separator = command.index("--")
        clap_setting = f"--setenv=CLAP_PATH={GUARDED_REAPER.BUILD_CLAP_DIR}"
        report_setting = (
            f"--setenv=M3_CLAP_PROBE_REPORT={GUARDED_REAPER.PROBE_REPORT}"
        )
        self.assertLess(command.index(clap_setting), separator)
        self.assertLess(command.index(report_setting), separator)
        self.assertNotIn("HOME=", " ".join(command))
        self.assertNotIn(
            str(pathlib.Path.home() / ".config/REAPER"), " ".join(command)
        )

    def test_native_clap_arguments_require_profile_and_report_together(self):
        without_profile = self.run_runner(
            "--dry-run",
            "--clap-path",
            str(GUARDED_REAPER.BUILD_CLAP_DIR),
            "--probe-report",
            str(GUARDED_REAPER.PROBE_REPORT),
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
        )
        self.assertNotEqual(without_profile.returncode, 0)
        self.assertIn("--profile is required", without_profile.stderr)

        without_report = self.run_runner(
            "--dry-run",
            "--profile",
            str(PROFILE),
            "--clap-path",
            str(GUARDED_REAPER.BUILD_CLAP_DIR),
            "--available-mib",
            "32000",
            "--load-one",
            "2.5",
            "--temperature-c",
            "72",
        )
        self.assertNotEqual(without_report.returncode, 0)
        self.assertIn("must be used together", without_report.stderr)

    def test_caller_cannot_override_profile_or_instance_isolation(self):
        for override in ("-cfgfile", "-cfgfile=/tmp/live.ini", "-nonewinst"):
            with self.subTest(override=override):
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
                    override,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("may not override", result.stdout + result.stderr)

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
