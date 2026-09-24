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
    def trusted_vst3_command(
        self, scope_unit: str = "m3-poly-guarded-4321.scope"
    ) -> list[str]:
        return GUARDED_REAPER.GuardedCommand(
            [f"--unit={scope_unit}", "--"], scope_unit
        )

    def run_runner(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_reaper_path_is_portable_and_overrideable(self):
        self.assertEqual(
            GUARDED_REAPER.default_reaper_executable(
                environment={"M3_REAPER": "/opt/reaper/reaper"},
                path_lookup=lambda _name: "/usr/local/bin/reaper",
                home=pathlib.Path("/home/example"),
            ),
            pathlib.Path("/opt/reaper/reaper"),
        )
        self.assertEqual(
            GUARDED_REAPER.default_reaper_executable(
                environment={},
                path_lookup=lambda _name: "/usr/local/bin/reaper",
                home=pathlib.Path("/home/example"),
            ),
            pathlib.Path("/usr/local/bin/reaper"),
        )
        self.assertEqual(
            GUARDED_REAPER.default_reaper_executable(
                environment={},
                path_lookup=lambda _name: None,
                home=pathlib.Path("/home/example"),
            ),
            pathlib.Path("/home/example/opt/REAPER/reaper"),
        )

    def test_guarded_command_uses_the_requested_reaper_executable(self):
        requested = pathlib.Path("/opt/reaper/reaper")
        command = GUARDED_REAPER.guarded_command(
            PROFILE,
            ["-new"],
            45,
            reaper=requested,
        )

        self.assertIn(str(requested), command)

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
        (profile.parent / "reaper-vstplugins64.ini").write_text(
            "[vstcache]\n"
            "M3_Polyphonic_Audio_to_MIDI.vst3=fixture\n"
            "M3_Polyphonic_Audio_to_MIDI_Probe.vst3=fixture\n"
            "reacomp.vst.so=fixture\n",
            encoding="utf-8",
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

    def test_observer_profile_requires_its_exact_completion_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            v2_profile = root / "v2.ini"
            observer_profile = root / "observer.ini"
            v2_completion = root / "v2-phase.log"
            observer_completion = root / "observer-phase.log"
            observer_project = root / "observer.RPP"
            observer_script = root / "observer.lua"
            vst3_path = root / "VST3"
            v2_profile.write_text("[reaper]\n", encoding="utf-8")
            observer_profile.write_text("[reaper]\n", encoding="utf-8")
            patches = (
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", v2_profile),
                mock.patch.object(
                    GUARDED_REAPER,
                    "OBSERVER_DIAGNOSTIC_PROFILE",
                    observer_profile,
                ),
                mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", v2_completion),
                mock.patch.object(
                    GUARDED_REAPER,
                    "OBSERVER_DIAGNOSTIC_COMPLETION_FILE",
                    observer_completion,
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "OBSERVER_DIAGNOSTIC_PROJECT",
                    observer_project,
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "OBSERVER_DIAGNOSTIC_SCRIPT",
                    observer_script,
                ),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "validate_native_vst3_environment",
                    return_value=vst3_path,
                ),
            )
            arguments = [
                "--dry-run",
                "--gui",
                "--workspace",
                "5",
                "--profile",
                str(observer_profile),
                "--vst3-path",
                str(vst3_path),
                "--completion-file",
                str(observer_completion),
                "--timeout-seconds",
                "45",
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
                "--",
                str(observer_project),
                str(observer_script),
            ]
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                patches[5],
                patches[6],
                patches[7],
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 0)
                cross_pair = arguments.copy()
                cross_pair[cross_pair.index(str(observer_completion))] = str(
                    v2_completion
                )
                self.assertEqual(GUARDED_REAPER.main(cross_pair), 2)
                reverse_cross_pair = arguments.copy()
                reverse_cross_pair[
                    reverse_cross_pair.index(str(observer_profile))
                ] = str(v2_profile)
                self.assertEqual(GUARDED_REAPER.main(reverse_cross_pair), 2)
                no_vst3 = arguments.copy()
                vst3_index = no_vst3.index("--vst3-path")
                del no_vst3[vst3_index : vst3_index + 2]
                self.assertEqual(GUARDED_REAPER.main(no_vst3), 2)
                no_completion = arguments.copy()
                completion_index = no_completion.index("--completion-file")
                del no_completion[completion_index : completion_index + 2]
                self.assertEqual(GUARDED_REAPER.main(no_completion), 2)
                no_gui = [argument for argument in arguments if argument != "--gui"]
                self.assertEqual(GUARDED_REAPER.main(no_gui), 2)
                arbitrary_arguments = arguments.copy()
                arbitrary_arguments[-1] = str(root / "other.lua")
                self.assertEqual(GUARDED_REAPER.main(arbitrary_arguments), 2)
                profile_alias = root / "observer-alias.ini"
                profile_alias.symlink_to(observer_profile)
                alias_arguments = arguments.copy()
                alias_arguments[alias_arguments.index(str(observer_profile))] = str(
                    profile_alias
                )
                self.assertEqual(GUARDED_REAPER.main(alias_arguments), 2)

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

    def test_native_vst3_scan_containment_accepts_exact_profile_and_cache(self):
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
                    GUARDED_REAPER.native_vst3_scan_containment_errors(
                        profile, vst3_root
                    ),
                    [],
                )

    def test_native_vst3_scan_containment_record_hashes_profile_and_cache(self):
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
                record = GUARDED_REAPER.native_vst3_scan_containment_record(
                    profile, vst3_root
                )

            self.assertEqual(record["errors"], [])
            self.assertRegex(record["profile_sha256"], r"^[0-9a-f]{64}$")
            self.assertIsNone(record["cache_sha256"]["reaper-vstplugins.ini"])
            self.assertRegex(
                record["cache_sha256"]["reaper-vstplugins64.ini"],
                r"^[0-9a-f]{64}$",
            )

    def test_native_vst3_scan_containment_refuses_rewrite_and_external_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            cache = profile.parent / "reaper-vstplugins64.ini"
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
                profile.write_text(
                    f"[reaper]\nvstpath={vst3_root};~/.vst3\n",
                    encoding="utf-8",
                )
                self.assertIn(
                    "disposable profile VST scan path is not the exact build-local root",
                    GUARDED_REAPER.native_vst3_scan_containment_errors(
                        profile, vst3_root
                    ),
                )
                profile.write_text(
                    f"[reaper]\nvstpath={vst3_root}\n", encoding="utf-8"
                )
                cache.write_text(
                    "[vstcache]\n"
                    "M3_Polyphonic_Audio_to_MIDI.vst3=fixture\n"
                    "M3_Polyphonic_Audio_to_MIDI_Probe.vst3=fixture\n"
                    "ATONE.vst3 =fixture\n",
                    encoding="utf-8",
                )
                self.assertIn(
                    "unexpected cached VST3 bundle: ATONE.vst3",
                    GUARDED_REAPER.native_vst3_scan_containment_errors(
                        profile, vst3_root
                    ),
                )

    def test_native_vst3_scan_containment_refuses_missing_or_malformed_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            cache = profile.parent / "reaper-vstplugins64.ini"
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
                cache.unlink()
                self.assertIn(
                    "disposable VST cache is missing",
                    GUARDED_REAPER.native_vst3_scan_containment_errors(
                        profile, vst3_root
                    ),
                )
                cache.write_text("[other]\n", encoding="utf-8")
                self.assertTrue(
                    any(
                        "does not contain a vstcache section" in error
                        for error in GUARDED_REAPER.native_vst3_scan_containment_errors(
                            profile, vst3_root
                        )
                    )
                )
                cache.unlink()
                cache.symlink_to(root / "missing-cache.ini")
                self.assertIn(
                    "disposable VST cache is not a regular file: reaper-vstplugins64.ini",
                    GUARDED_REAPER.native_vst3_scan_containment_errors(
                        profile, vst3_root
                    ),
                )

    def test_vst3_prelaunch_refuses_external_cache_without_launching(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            cache = profile.parent / "reaper-vstplugins64.ini"
            cache.write_text(
                "[vstcache]\nATONE.vst3=fixture\n", encoding="utf-8"
            )
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_prelaunch_scan_containment_errors",
                    return_value=[],
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded", return_value=0) as launch,
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)

            launch.assert_not_called()

    def test_vst3_containment_inspects_after_guarded_error_or_interrupt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            (profile.parent / "reaper-vstplugins64.ini").unlink()
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(
                    GUARDED_REAPER,
                    "run_gui_guarded",
                    side_effect=[RuntimeError("after launch"), KeyboardInterrupt],
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_scan_containment_errors",
                    return_value=["unexpected cached VST3 bundle: ATONE.vst3"],
                ) as containment,
                mock.patch.object(
                    GUARDED_REAPER,
                    "clear_confirmed_user_scope_exit_receipt",
                    return_value=True,
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "confirmed_user_scope_exit_receipt_present",
                    return_value=True,
                ),
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)
                self.assertEqual(GUARDED_REAPER.main(arguments), 130)

            self.assertEqual(containment.call_count, 0)

    def test_vst3_post_exit_containment_failure_preserves_nonzero_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            (profile.parent / "reaper-vstplugins64.ini").unlink()
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(
                    GUARDED_REAPER, "run_gui_guarded", side_effect=[0, 124]
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_scan_containment_errors",
                    return_value=["unexpected cached VST3 bundle: ATONE.vst3"],
                ) as containment,
                mock.patch.object(
                    GUARDED_REAPER,
                    "clear_confirmed_user_scope_exit_receipt",
                    return_value=True,
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "confirmed_user_scope_exit_receipt_present",
                    return_value=True,
                ),
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)
                self.assertEqual(GUARDED_REAPER.main(arguments), 124)

            self.assertEqual(containment.call_count, 1)

    def test_vst3_nonzero_exit_with_valid_receipt_skips_containment_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_prelaunch_scan_containment_errors",
                    return_value=[],
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded", return_value=37),
                mock.patch.object(
                    GUARDED_REAPER,
                    "clear_confirmed_user_scope_exit_receipt",
                    return_value=True,
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "confirmed_user_scope_exit_receipt_present",
                    return_value=True,
                ),
                mock.patch.object(
                    GUARDED_REAPER, "native_vst3_scan_containment_errors"
                ) as scan,
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 37)

            scan.assert_not_called()

    def test_vst3_gui_rejects_suffixless_or_mismatched_scope_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            completion = profile.parent / "test-results/phase.log"
            completion.parent.mkdir()
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--completion-file",
                str(completion),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            invalid_commands = (
                GUARDED_REAPER.GuardedCommand(
                    ["--unit=m3-poly-guarded-4321"], "m3-poly-guarded-4321"
                ),
                GUARDED_REAPER.GuardedCommand(
                    ["--unit=m3-poly-guarded-9999.scope"],
                    "m3-poly-guarded-4321.scope",
                ),
            )
            for command in invalid_commands:
                with (
                    mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                    mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                    mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                    mock.patch.object(
                        GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                    ),
                    mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                    mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", completion),
                    mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                    mock.patch.object(
                        GUARDED_REAPER, "guarded_command", return_value=command
                    ),
                    mock.patch.object(GUARDED_REAPER, "run_gui_guarded") as launch,
                ):
                    self.assertEqual(GUARDED_REAPER.main(arguments), 2)
                launch.assert_not_called()

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
        self.assertTrue(command.scope_unit.endswith(".scope"))
        self.assertIn(f"--unit={command.scope_unit}", command)

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
            timeout=GUARDED_REAPER.WMCTRL_TIMEOUT_SECONDS,
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
                    timeout=GUARDED_REAPER.WMCTRL_TIMEOUT_SECONDS,
                ),
                mock.call(
                    ["/usr/bin/wmctrl", "-ir", "0x0480000a", "-t", "4"],
                    env={},
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=GUARDED_REAPER.WMCTRL_TIMEOUT_SECONDS,
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
                    timeout=GUARDED_REAPER.WMCTRL_TIMEOUT_SECONDS,
                ),
                mock.call(
                    ["/usr/bin/wmctrl", "-ir", "0x0480000a", "-t", "4"],
                    env={},
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=GUARDED_REAPER.WMCTRL_TIMEOUT_SECONDS,
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
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        completion = pathlib.Path(temporary.name) / "phase.log"
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
                "stop_guarded_scope",
                return_value=True,
            ) as stop,
            mock.patch.object(
                GUARDED_REAPER,
                "user_scope_exited",
                return_value=True,
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "write_confirmed_user_scope_exit_receipt",
                return_value=True,
            ),
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
                completion,
                "m3-poly-guarded-fixture.scope",
            )

        self.assertEqual(result, 0)
        stop.assert_called_once_with(
            process,
            GUARDED_REAPER.signal.SIGTERM,
            "m3-poly-guarded-fixture.scope",
        )

    def test_scope_teardown_refuses_live_scope_after_dead_wrapper_and_group(self):
        process = mock.Mock(pid=4321)
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "user_scope_exit_state",
                side_effect=[None] * 7,
            ),
            mock.patch.object(
                GUARDED_REAPER.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as systemctl,
            mock.patch.object(GUARDED_REAPER.os, "killpg"),
            mock.patch.object(GUARDED_REAPER.time, "sleep"),
        ):
            self.assertFalse(
                GUARDED_REAPER.stop_guarded_scope(
                    process,
                    GUARDED_REAPER.signal.SIGTERM,
                    "m3-poly-guarded-fixture.scope",
                )
            )

        self.assertEqual(
            systemctl.call_args_list,
            [
                mock.call(
                    [
                        "/usr/bin/systemctl",
                        "--user",
                        "kill",
                        "--kill-whom=all",
                        "--signal=TERM",
                        "m3-poly-guarded-fixture.scope",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=GUARDED_REAPER.SYSTEMCTL_TIMEOUT_SECONDS,
                ),
                mock.call(
                    [
                        "/usr/bin/systemctl",
                        "--user",
                        "kill",
                        "--kill-whom=all",
                        "--signal=KILL",
                        "m3-poly-guarded-fixture.scope",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=GUARDED_REAPER.SYSTEMCTL_TIMEOUT_SECONDS,
                ),
            ],
        )

    def test_scope_teardown_permission_error_fails_closed(self):
        process = mock.Mock(pid=4321)
        with (
            mock.patch.object(
                GUARDED_REAPER, "user_scope_exit_state", return_value=None
            ),
            mock.patch.object(
                GUARDED_REAPER.os, "killpg", side_effect=PermissionError
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "_signal_user_scope",
                return_value=False,
            ),
        ):
            self.assertFalse(
                GUARDED_REAPER.stop_guarded_scope(
                    process,
                    GUARDED_REAPER.signal.SIGTERM,
                    "m3-poly-guarded-fixture.scope",
                )
            )

    def test_scope_teardown_accepts_confirmed_inactive_or_absent_scope(self):
        process = mock.Mock(pid=4321)
        process.poll.return_value = 0
        for state in ("inactive", "absent"):
            with self.subTest(state=state), mock.patch.object(
                GUARDED_REAPER,
                "user_scope_exit_state",
                return_value="inactive" if state == "inactive" else "collected",
            ) as exited, mock.patch.object(GUARDED_REAPER.os, "killpg") as killpg:
                self.assertTrue(
                    GUARDED_REAPER.stop_guarded_scope(
                        process,
                        GUARDED_REAPER.signal.SIGTERM,
                        "m3-poly-guarded-fixture.scope",
                    )
                )
            exited.assert_called_once_with("m3-poly-guarded-fixture.scope")
            killpg.assert_not_called()

    def test_scope_teardown_refuses_collected_scope_while_launcher_is_live(self):
        process = mock.Mock(pid=4321)
        process.poll.return_value = None
        with (
            mock.patch.object(
                GUARDED_REAPER,
                "user_scope_exit_state",
                return_value="collected",
            ),
            mock.patch.object(
                GUARDED_REAPER,
                "_signal_user_scope",
                return_value=True,
            ) as signal_scope,
            mock.patch.object(GUARDED_REAPER.os, "killpg") as killpg,
            mock.patch.object(GUARDED_REAPER.time, "sleep"),
        ):
            self.assertFalse(
                GUARDED_REAPER.stop_guarded_scope(
                    process,
                    GUARDED_REAPER.signal.SIGTERM,
                    "m3-poly-guarded-fixture.scope",
                )
            )

        self.assertEqual(
            signal_scope.call_args_list,
            [
                mock.call("m3-poly-guarded-fixture.scope", "TERM"),
                mock.call("m3-poly-guarded-fixture.scope", "KILL"),
            ],
        )
        self.assertIn(mock.call(4321, GUARDED_REAPER.signal.SIGTERM), killpg.call_args_list)
        self.assertIn(mock.call(4321, GUARDED_REAPER.signal.SIGKILL), killpg.call_args_list)

    def test_scope_query_failure_or_ambiguous_output_fails_closed(self):
        unit = "m3-poly-guarded-fixture.scope"
        cases = (
            subprocess.CompletedProcess([], 1, "", "bus unavailable"),
            subprocess.CompletedProcess([], 0, "LoadState=loaded\nActiveState=\n", ""),
            subprocess.CompletedProcess([], 0, "LoadState=not-found\n", ""),
        )
        for result in cases:
            with self.subTest(result=result), mock.patch.object(
                GUARDED_REAPER.subprocess, "run", return_value=result
            ):
                self.assertFalse(GUARDED_REAPER.user_scope_exited(unit))
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("systemctl", 2),
        ):
            self.assertFalse(GUARDED_REAPER.user_scope_exited(unit))

    def test_scope_query_accepts_only_exact_inactive_or_collected_state(self):
        unit = "m3-poly-guarded-fixture.scope"
        for stdout in (
            "LoadState=loaded\nActiveState=inactive\nSubState=dead\n",
            "LoadState=not-found\nActiveState=inactive\nSubState=dead\n",
        ):
            with self.subTest(stdout=stdout), mock.patch.object(
                GUARDED_REAPER.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, stdout, ""),
            ):
                self.assertTrue(GUARDED_REAPER.user_scope_exited(unit))

    def test_scope_exit_receipt_requires_exact_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            completion = pathlib.Path(temporary) / "phase.log"
            receipt = GUARDED_REAPER.confirmed_user_scope_exit_receipt(completion)
            self.assertTrue(
                GUARDED_REAPER.write_confirmed_user_scope_exit_receipt(completion)
            )
            self.assertTrue(
                GUARDED_REAPER.confirmed_user_scope_exit_receipt_present(completion)
            )
            receipt.write_text("partial", encoding="utf-8")
            self.assertFalse(
                GUARDED_REAPER.confirmed_user_scope_exit_receipt_present(completion)
            )
            receipt.unlink()
            target = completion.parent / "outside-receipt"
            target.write_text(
                GUARDED_REAPER.CONFIRMED_USER_SCOPE_EXIT_RECEIPT_CONTENT,
                encoding="utf-8",
            )
            receipt.symlink_to(target)
            with mock.patch.object(
                GUARDED_REAPER.os,
                "open",
                wraps=GUARDED_REAPER.os.open,
            ) as open_receipt:
                self.assertFalse(
                    GUARDED_REAPER.confirmed_user_scope_exit_receipt_present(
                        completion
                    )
                )
            open_receipt.assert_called_once_with(
                receipt,
                GUARDED_REAPER.os.O_RDONLY | GUARDED_REAPER.os.O_NOFOLLOW,
            )

    def test_gui_launcher_exit_refuses_a_still_active_scope(self):
        process = mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        with tempfile.TemporaryDirectory() as temporary:
            completion = pathlib.Path(temporary) / "phase.log"
            with (
                mock.patch.object(
                    GUARDED_REAPER, "require_workspace", return_value=1
                ),
                mock.patch.object(
                    GUARDED_REAPER, "settle_launch_workspace", return_value=0
                ),
                mock.patch.object(
                    GUARDED_REAPER, "restore_launch_workspace", return_value=False
                ),
                mock.patch.object(
                    GUARDED_REAPER, "reaper_window_ids", return_value=set()
                ),
                mock.patch.object(
                    GUARDED_REAPER, "user_scope_exited", return_value=False
                ),
                mock.patch.object(
                    GUARDED_REAPER.subprocess, "Popen", return_value=process
                ),
            ):
                result = GUARDED_REAPER.run_gui_guarded(
                    ["reaper"],
                    {},
                    5,
                    completion,
                    "m3-poly-guarded-fixture.scope",
                )

            self.assertEqual(result, 2)
            self.assertTrue(
                GUARDED_REAPER.unconfirmed_process_group_exit_marker_present(
                    completion
                )
            )

    def test_gui_launcher_exit_allows_confirmed_inactive_scope(self):
        process = mock.Mock()
        process.poll.return_value = 0
        process.returncode = 0
        with (
            mock.patch.object(GUARDED_REAPER, "require_workspace", return_value=1),
            mock.patch.object(GUARDED_REAPER, "settle_launch_workspace", return_value=0),
            mock.patch.object(GUARDED_REAPER, "restore_launch_workspace", return_value=False),
            mock.patch.object(GUARDED_REAPER, "reaper_window_ids", return_value=set()),
            mock.patch.object(GUARDED_REAPER, "user_scope_exited", return_value=True),
            mock.patch.object(GUARDED_REAPER.subprocess, "Popen", return_value=process),
        ):
            self.assertEqual(
                GUARDED_REAPER.run_gui_guarded(
                    ["reaper"],
                    {},
                    5,
                    None,
                    "m3-poly-guarded-fixture.scope",
                ),
                0,
            )

    def test_gui_completion_refuses_unconfirmed_process_group_exit(self):
        process = mock.Mock(pid=4321)
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired(
            cmd="reaper",
            timeout=GUARDED_REAPER.COMPLETION_GRACE_SECONDS,
        )
        with tempfile.TemporaryDirectory() as temporary:
            completion = pathlib.Path(temporary) / "phase.log"
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
                    "stop_guarded_scope",
                    return_value=False,
                ) as stop,
                mock.patch.object(
                    GUARDED_REAPER,
                    "user_scope_exited",
                    return_value=True,
                ),
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
                    completion,
                    "m3-poly-guarded-fixture.scope",
                )

        self.assertEqual(result, 2)
        stop.assert_called_once_with(
            process,
            GUARDED_REAPER.signal.SIGTERM,
            "m3-poly-guarded-fixture.scope",
        )

    def test_gui_unconfirmed_cleanup_seals_marker_before_reraising(self):
        cases = (
            ("interrupt", KeyboardInterrupt(), GUARDED_REAPER.signal.SIGINT),
            ("runtime error", RuntimeError("window failure"), GUARDED_REAPER.signal.SIGTERM),
        )
        for name, failure, expected_signal in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                completion = pathlib.Path(temporary) / "staging/test-results/phase.log"
                completion.parent.mkdir(parents=True)
                marker = GUARDED_REAPER.unconfirmed_process_group_exit_marker(
                    completion
                )
                process = mock.Mock(pid=4321)
                process.poll.return_value = None
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
                        side_effect=failure,
                    ),
                    mock.patch.object(
                        GUARDED_REAPER,
                        "stop_guarded_scope",
                        return_value=False,
                    ) as stop,
                    mock.patch.object(
                        GUARDED_REAPER.subprocess,
                        "Popen",
                        return_value=process,
                    ),
                ):
                    with self.assertRaises(type(failure)):
                        GUARDED_REAPER.run_gui_guarded(
                            [
                                "reaper",
                            ],
                            {},
                            5,
                            completion,
                            "m3-poly-guarded-fixture.scope",
                        )

                self.assertTrue(marker.is_file())
                self.assertEqual(
                    marker.read_text(encoding="utf-8"),
                    '{"schema":1,"status":"process-group-exit-unconfirmed"}\n',
                )
                stop.assert_called_once_with(
                    process,
                    expected_signal,
                    "m3-poly-guarded-fixture.scope",
                )

    def test_vst3_stale_unconfirmed_termination_marker_refuses_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            completion = profile.parent / "test-results/phase.log"
            completion.parent.mkdir()
            marker = completion.parent / ".native-vst3-termination-unconfirmed.json"
            marker.write_text(
                '{"schema":1,"status":"process-group-exit-unconfirmed"}\n',
                encoding="utf-8",
            )
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--completion-file",
                str(completion),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]

            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", completion),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_prelaunch_scan_containment_errors",
                    return_value=[],
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded") as launch,
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_scan_containment_errors",
                    return_value=[],
                ),
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)

            launch.assert_not_called()
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                '{"schema":1,"status":"process-group-exit-unconfirmed"}\n',
            )

    def test_vst3_marker_skips_normal_post_exit_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            completion = profile.parent / "test-results/phase.log"
            completion.parent.mkdir()
            marker = completion.parent / ".native-vst3-termination-unconfirmed.json"
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--completion-file",
                str(completion),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]

            def launch(*_args):
                marker.write_text(
                    '{"schema":1,"status":"process-group-exit-unconfirmed"}\n',
                    encoding="utf-8",
                )
                return 130

            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", completion),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_prelaunch_scan_containment_errors",
                    return_value=[],
                ),
                mock.patch.object(
                    GUARDED_REAPER,
                    "guarded_command",
                    return_value=self.trusted_vst3_command(),
                ),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded", side_effect=launch),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_scan_containment_errors",
                ) as scan,
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 130)

            scan.assert_not_called()

    def test_vst3_post_exit_requires_exact_scope_receipt_before_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            for cache in profile.parent.glob("reaper-vstplugins*.ini"):
                cache.unlink()
            completion = profile.parent / "test-results/phase.log"
            completion.parent.mkdir()
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--completion-file",
                str(completion),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            command = self.trusted_vst3_command()
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", completion),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(
                    GUARDED_REAPER,
                    "native_vst3_prelaunch_scan_containment_errors",
                    return_value=[],
                ),
                mock.patch.object(GUARDED_REAPER, "guarded_command", return_value=command),
                mock.patch.object(GUARDED_REAPER, "runtime_environment", return_value={}),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded", return_value=0),
                mock.patch.object(
                    GUARDED_REAPER, "native_vst3_scan_containment_errors"
                ) as scan,
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)

            scan.assert_not_called()

    def test_vst3_gui_refuses_a_launcher_without_scope_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            vst3_root, bundle, binary, moduleinfo, profile = (
                self.create_vst3_layout(root)
            )
            completion = profile.parent / "test-results/phase.log"
            completion.parent.mkdir()
            arguments = [
                "--gui",
                "--profile",
                str(profile),
                "--vst3-path",
                str(vst3_root),
                "--completion-file",
                str(completion),
                "--available-mib",
                "32000",
                "--load-one",
                "2.5",
                "--temperature-c",
                "72",
            ]
            with (
                mock.patch.object(GUARDED_REAPER, "BUILD_VST3_DIR", vst3_root),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BUNDLE", bundle),
                mock.patch.object(GUARDED_REAPER, "PROBE_VST3_BINARY", binary),
                mock.patch.object(
                    GUARDED_REAPER, "PROBE_VST3_MODULEINFO", moduleinfo
                ),
                mock.patch.object(GUARDED_REAPER, "DISPOSABLE_PROFILE", profile),
                mock.patch.object(GUARDED_REAPER, "COMPLETION_FILE", completion),
                mock.patch.object(GUARDED_REAPER, "REAPER", pathlib.Path("/bin/true")),
                mock.patch.object(GUARDED_REAPER, "guarded_command", return_value=["guard"]),
                mock.patch.object(GUARDED_REAPER, "run_gui_guarded") as launch,
            ):
                self.assertEqual(GUARDED_REAPER.main(arguments), 2)

            launch.assert_not_called()

    def test_stop_process_group_refuses_leader_exit_with_live_descendants(self):
        process = mock.Mock(pid=4321)
        process.poll.return_value = 0
        with (
            mock.patch.object(GUARDED_REAPER.os, "killpg", return_value=None) as killpg,
            mock.patch.object(GUARDED_REAPER.time, "sleep"),
        ):
            self.assertFalse(
                GUARDED_REAPER.stop_process_group(process, GUARDED_REAPER.signal.SIGTERM)
            )

        self.assertEqual(
            killpg.call_args_list[0],
            mock.call(4321, GUARDED_REAPER.signal.SIGTERM),
        )
        self.assertIn(
            mock.call(4321, GUARDED_REAPER.signal.SIGKILL),
            killpg.call_args_list,
        )
        self.assertGreaterEqual(killpg.call_args_list.count(mock.call(4321, 0)), 2)

    def test_unconfirmed_marker_is_fail_closed_and_never_overwrites_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            completion = pathlib.Path(temporary) / "phase.log"
            marker = completion.parent / ".native-vst3-termination-unconfirmed.json"
            marker.write_text("partial", encoding="utf-8")
            self.assertTrue(
                GUARDED_REAPER.unconfirmed_process_group_exit_marker_present(
                    completion
                )
            )
            marker.unlink()
            target = completion.parent / "outside-marker"
            target.write_text("outside", encoding="utf-8")
            marker.symlink_to(target)
            self.assertTrue(
                GUARDED_REAPER.unconfirmed_process_group_exit_marker_present(
                    completion
                )
            )
            self.assertFalse(
                GUARDED_REAPER.write_unconfirmed_process_group_exit_marker(
                    completion
                )
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "outside")

    def test_unconfirmed_marker_uses_external_staging_sidecar_and_reads_legacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = pathlib.Path(temporary) / "staging"
            completion = staging / "test-results/phase.log"
            completion.parent.mkdir(parents=True)
            canonical = GUARDED_REAPER.unconfirmed_process_group_exit_marker(
                completion
            )
            legacy = completion.parent / GUARDED_REAPER.UNCONFIRMED_PROCESS_GROUP_EXIT_MARKER

            self.assertEqual(canonical.parent, staging)
            self.assertTrue(
                GUARDED_REAPER.write_unconfirmed_process_group_exit_marker(
                    completion
                )
            )
            self.assertTrue(canonical.is_file())
            self.assertFalse(legacy.exists())
            canonical.unlink()
            legacy.write_text("legacy", encoding="utf-8")
            self.assertTrue(
                GUARDED_REAPER.unconfirmed_process_group_exit_marker_present(
                    completion
                )
            )

    def test_wmctrl_timeout_becomes_runtime_error(self):
        with mock.patch.object(
            GUARDED_REAPER.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("wmctrl", 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "wmctrl command timed out"):
                GUARDED_REAPER.move_reaper_windows_once({}, 5)

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
