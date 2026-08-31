import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import run_native_vst3_probe as PROBE_RUNNER


class NativeVst3ProbeRunnerTests(unittest.TestCase):
    @staticmethod
    def healthy_snapshot():
        return PROBE_RUNNER.StabilitySnapshot(
            available_mib=32000.0,
            load_one=2.0,
            temperature_c=70.0,
            memory_full_pressure_avg10=0.0,
            io_full_pressure_avg10=0.0,
        )

    @staticmethod
    def current_hashes():
        return {
            name: f"sha256-{name}"
            for name in PROBE_RUNNER.REQUIRED_INPUT_HASHES
        }

    @staticmethod
    def write_complete_batch(
        batch: pathlib.Path,
        sample_rate: int,
        block_size: int,
        hashes: dict[str, str],
    ) -> None:
        batch.mkdir(parents=True)
        (batch / "phase.log").write_text(
            "suite-start\nsuite-finish\n", encoding="utf-8"
        )
        (batch / "capability.tsv").write_text(
            "metric\tvalue\n"
            "status\tpass\n"
            f"sample_rate\t{sample_rate}\n"
            f"block_size\t{block_size}\n"
            "failure_count\t0\n",
            encoding="utf-8",
        )
        (batch / "events.tsv").write_text(
            "phase\tindex\tabsolute_sample\toffset\ttype\tchannel\tpitch\tvelocity\tnote_id\n"
            "trigger-one\t0\t64\t0\ton\t1\t60\t100\t-1060\n",
            encoding="utf-8",
        )
        (batch / "state.tsv").write_text(
            "index\tstable_id\tname\tdefault\tmutated\trestored\n"
            "0\t4D330001\tDetector input\t0\t1\t0\n",
            encoding="utf-8",
        )
        (batch / "probe-vst3.tsv").write_text(
            "metric\tvalue\n"
            "schema\t1\n"
            f"sample_rate\t{sample_rate}\n"
            f"block_size\t{block_size}\n"
            "failure_count\t0\n",
            encoding="utf-8",
        )
        (batch / "pressure.json").write_text(
            '{"before": {}, "after": {}}\n', encoding="utf-8"
        )
        (batch / "metadata.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "sample_rate": sample_rate,
                    "block_size": block_size,
                    "guard_returncode": 0,
                    "classification": "pass",
                    "inputs": hashes,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_exact_twenty_row_matrix_and_dry_plan(self):
        self.assertEqual(PROBE_RUNNER.SAMPLE_RATES, (44100, 48000, 88200, 96000))
        self.assertEqual(PROBE_RUNNER.BLOCK_SIZES, (32, 64, 128, 256, 512))
        expected = tuple(
            (rate, block)
            for rate in PROBE_RUNNER.SAMPLE_RATES
            for block in PROBE_RUNNER.BLOCK_SIZES
        )
        self.assertEqual(PROBE_RUNNER.MATRIX, expected)

        commands = PROBE_RUNNER.planned_guard_commands(dry_run=True)
        self.assertEqual(len(commands), 20)
        projects = set()
        for row, command in zip(expected, commands):
            rate, block = row
            rendered = " ".join(command)
            self.assertIn("--dry-run", command)
            self.assertIn("--gui", command)
            self.assertIn("--workspace 5", rendered)
            self.assertIn(str(PROBE_RUNNER.PROFILE), rendered)
            self.assertIn(str(PROBE_RUNNER.BUILD_VST3_DIR), rendered)
            self.assertIn("--vst3-path", command)
            self.assertIn("--completion-file", command)
            self.assertIn("--timeout-seconds 45", rendered)
            self.assertNotIn("--clap-path", command)
            self.assertNotIn("--probe-report", command)
            project = PROBE_RUNNER.project_path(rate, block)
            self.assertIn(str(project), command)
            projects.add(project)
        self.assertEqual(len(projects), 20)

    def test_recovery_batches_cannot_overlap_sealed_task15_evidence(self):
        sealed = (
            PROBE_RUNNER.ROOT
            / "build/test-results/native-vst3-probe/batches"
        ).resolve()
        self.assertNotEqual(PROBE_RUNNER.BATCH_ROOT, sealed)
        self.assertEqual(
            PROBE_RUNNER.BATCH_ROOT,
            (
                PROBE_RUNNER.ROOT
                / "build/test-results/native-vst3-probe-v2/batches"
            ).resolve(),
        )

    def test_observer_diagnostic_scope_is_fixed_and_restores_v2_paths(self):
        original = (
            PROBE_RUNNER.STAGING_ROOT,
            PROBE_RUNNER.PROFILE,
            PROBE_RUNNER.STAGING_RESULTS,
            PROBE_RUNNER.COMPLETION_FILE,
            PROBE_RUNNER.PROBE_SCRIPT,
            PROBE_RUNNER.PROJECT_ROOT,
            PROBE_RUNNER.BATCH_ROOT,
            PROBE_RUNNER.EVIDENCE_NAMESPACE,
        )
        with PROBE_RUNNER.observer_diagnostic_scope():
            self.assertEqual(
                PROBE_RUNNER.OBSERVER_DIAGNOSTIC_ROW, (44100, 32)
            )
            self.assertEqual(
                PROBE_RUNNER.EVIDENCE_NAMESPACE,
                "native-vst3-probe-v3-observer-diagnostic",
            )
            self.assertEqual(
                PROBE_RUNNER.BATCH_ROOT,
                (
                    PROBE_RUNNER.ROOT
                    / "build/test-results/"
                    "native-vst3-probe-v3-observer-diagnostic/batches"
                ).resolve(),
            )
            command = PROBE_RUNNER.guard_command(
                *PROBE_RUNNER.OBSERVER_DIAGNOSTIC_ROW,
                dry_run=True,
            )
            self.assertIn(str(PROBE_RUNNER.PROFILE), command)
            self.assertIn(str(PROBE_RUNNER.COMPLETION_FILE), command)
            self.assertIn(str(PROBE_RUNNER.PROJECT_ROOT), " ".join(command))
        with self.assertRaisesRegex(RuntimeError, "restore"):
            with PROBE_RUNNER.observer_diagnostic_scope():
                raise RuntimeError("restore")
        self.assertEqual(
            (
                PROBE_RUNNER.STAGING_ROOT,
                PROBE_RUNNER.PROFILE,
                PROBE_RUNNER.STAGING_RESULTS,
                PROBE_RUNNER.COMPLETION_FILE,
                PROBE_RUNNER.PROBE_SCRIPT,
                PROBE_RUNNER.PROJECT_ROOT,
                PROBE_RUNNER.BATCH_ROOT,
                PROBE_RUNNER.EVIDENCE_NAMESPACE,
            ),
            original,
        )

    def test_observer_diagnostic_runs_one_row_and_never_a_tail(self):
        observed = []

        def run_row(sample_rate, block_size):
            observed.append(
                (
                    sample_rate,
                    block_size,
                    PROBE_RUNNER.EVIDENCE_NAMESPACE,
                    PROBE_RUNNER.BATCH_ROOT,
                    PROBE_RUNNER.STAGING_RESULTS,
                )
            )
            return "completed"

        with (
            mock.patch.object(
                PROBE_RUNNER,
                "observer_diagnostic_freshness_errors",
                return_value=[],
            ),
            mock.patch.object(PROBE_RUNNER, "run_row", side_effect=run_row),
        ):
            self.assertEqual(PROBE_RUNNER.run_observer_diagnostic(), "completed")

        self.assertEqual(
            observed,
            [
                (
                    44100,
                    32,
                    "native-vst3-probe-v3-observer-diagnostic",
                    PROBE_RUNNER.OBSERVER_DIAGNOSTIC_BATCH_ROOT,
                    PROBE_RUNNER.OBSERVER_DIAGNOSTIC_STAGING_RESULTS,
                )
            ],
        )
        self.assertEqual(PROBE_RUNNER.EVIDENCE_NAMESPACE, "native-vst3-probe-v2")

    def test_observer_diagnostic_refuses_any_existing_staging_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = pathlib.Path(temporary) / "observer-staging"
            staging.mkdir()
            with (
                mock.patch.object(
                    PROBE_RUNNER, "OBSERVER_DIAGNOSTIC_STAGING_ROOT", staging
                ),
                mock.patch.object(PROBE_RUNNER, "run_row") as run,
                mock.patch.object(
                    PROBE_RUNNER, "recover_pending_batches"
                ) as recover_pending,
                mock.patch.object(
                    PROBE_RUNNER, "recover_staging_partial"
                ) as recover_staging,
            ):
                with self.assertRaisesRegex(RuntimeError, "fresh observer"):
                    PROBE_RUNNER.run_observer_diagnostic()
            run.assert_not_called()
            recover_pending.assert_not_called()
            recover_staging.assert_not_called()

    def test_observer_diagnostic_refuses_broken_staging_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            staging = root / "observer-staging"
            staging.symlink_to(root / "outside")
            with (
                mock.patch.object(
                    PROBE_RUNNER, "OBSERVER_DIAGNOSTIC_STAGING_ROOT", staging
                ),
                mock.patch.object(PROBE_RUNNER, "run_row") as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "symlinked"):
                    PROBE_RUNNER.run_observer_diagnostic()
            run.assert_not_called()

    def test_preflight_refuses_existing_reaper_and_every_pressure_boundary(self):
        healthy = self.healthy_snapshot()
        self.assertEqual(PROBE_RUNNER.stability_errors(healthy, set()), [])
        self.assertIn(
            "existing REAPER",
            PROBE_RUNNER.stability_errors(healthy, {42})[0],
        )
        cases = (
            ("available_mib", 4095.0, "available memory"),
            ("load_one", 12.01, "load"),
            ("temperature_c", 90.0, "temperature"),
            ("memory_full_pressure_avg10", 0.25, "memory full-pressure"),
            ("io_full_pressure_avg10", 2.0, "I/O full-pressure"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                changed = PROBE_RUNNER.StabilitySnapshot(
                    **{**healthy.__dict__, field: value}
                )
                self.assertTrue(
                    any(
                        message in error
                        for error in PROBE_RUNNER.stability_errors(changed, set())
                    )
                )

    def test_reaper_pid_scan_uses_proc_executable_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            binaries = root / "binaries"
            binaries.mkdir()
            reaper = binaries / "reaper"
            other = binaries / "python"
            reaper.write_bytes(b"")
            other.write_bytes(b"")
            for pid, executable in (("123", reaper), ("456", other)):
                process = root / pid
                process.mkdir()
                (process / "exe").symlink_to(executable)
            self.assertEqual(PROBE_RUNNER.reaper_pids(root), {123})

    def test_required_hash_contract_names_every_runtime_input(self):
        self.assertEqual(
            set(PROBE_RUNNER.REQUIRED_INPUT_HASHES),
            {
                "probe_binary",
                "capability_source",
                "capability_script",
                "guard",
                "stager",
                "probe_bundle",
                "module_info",
                "runner",
            },
        )

    def test_bundle_hash_input_rejects_extra_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = pathlib.Path(temporary) / "Probe.vst3"
            binary = bundle / "Contents/x86_64-linux/Probe.so"
            moduleinfo = bundle / "Contents/Resources/moduleinfo.json"
            binary.parent.mkdir(parents=True)
            moduleinfo.parent.mkdir(parents=True)
            binary.write_bytes(b"ELF\n")
            moduleinfo.write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                PROBE_RUNNER.bundle_input_errors(bundle, binary, moduleinfo),
                [],
            )

            extra = bundle / "Contents/extra.txt"
            extra.write_text("extra\n", encoding="utf-8")
            self.assertTrue(
                any(
                    "file set" in error
                    for error in PROBE_RUNNER.bundle_input_errors(
                        bundle, binary, moduleinfo
                    )
                )
            )
            extra.unlink()

            outside = pathlib.Path(temporary) / "outside.so"
            outside.write_bytes(b"outside\n")
            binary.unlink()
            binary.symlink_to(outside)
            self.assertTrue(
                any(
                    "symlink" in error
                    for error in PROBE_RUNNER.bundle_input_errors(
                        bundle, binary, moduleinfo
                    )
                )
            )

    def test_complete_batch_requires_rate_block_sentinel_hashes_and_all_tsvs(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch = pathlib.Path(temporary) / "44100-32"
            hashes = self.current_hashes()
            self.write_complete_batch(batch, 44100, 32, hashes)
            self.assertEqual(
                PROBE_RUNNER.batch_validation_errors(
                    batch, 44100, 32, hashes
                ),
                [],
            )

            stale = {**hashes, "runner": "changed"}
            self.assertTrue(
                any(
                    "input hashes" in error
                    for error in PROBE_RUNNER.batch_validation_errors(
                        batch, 44100, 32, stale
                    )
                )
            )
            (batch / "phase.log").write_text(
                "suite-start\n", encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "suite-finish" in error
                    for error in PROBE_RUNNER.batch_validation_errors(
                        batch, 44100, 32, hashes
                    )
                )
            )
            (batch / "events.tsv").unlink()
            self.assertTrue(
                any(
                    "events.tsv" in error
                    for error in PROBE_RUNNER.batch_validation_errors(
                        batch, 44100, 32, hashes
                    )
                )
            )

    def test_pressure_record_is_atomic_json_with_before_and_after(self):
        snapshot = self.healthy_snapshot()
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / "pressure.json"
            PROBE_RUNNER.write_pressure_record(destination, snapshot, snapshot)
            value = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(set(value), {"before", "after"})
            self.assertEqual(value["before"]["available_mib"], 32000.0)
            self.assertEqual(list(destination.parent.glob(".pressure.json.*")), [])

    def test_invalid_and_interrupted_rows_are_renamed_not_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            batch = root / "44100-32"
            batch.mkdir()
            (batch / "phase.log").write_text("partial\n", encoding="utf-8")
            archived = PROBE_RUNNER.archive_invalid_batch(
                batch, timestamp="20260830T120000Z"
            )
            self.assertEqual(archived.name, "44100-32.invalid-20260830T120000Z")
            self.assertTrue((archived / "phase.log").is_file())

            batches = root / "batches"
            pending = batches / ".48000-64.pending-42-20260830T110000Z"
            pending.mkdir(parents=True)
            (pending / "phase.log").write_text(
                "suite-start\n", encoding="utf-8"
            )
            with (
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(
                    PROBE_RUNNER, "_timestamp", return_value="20260830T120000Z"
                ),
            ):
                recovered = PROBE_RUNNER.recover_pending_batches()
            self.assertEqual(len(recovered), 1)
            self.assertEqual(
                recovered[0].name, "48000-64.invalid-20260830T120000Z"
            )
            self.assertTrue((recovered[0] / "phase.log").is_file())

    def test_interrupted_staging_is_preserved_with_rate_and_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            staging = root / "reaper-test/test-results"
            staging.mkdir(parents=True)
            (staging / "phase.log").write_text(
                "suite-start\n", encoding="utf-8"
            )
            (staging / ".native-vst3-attempt.json").write_text(
                '{"schema": 1, "evidence_namespace": '
                '"native-vst3-probe-v2", "sample_rate": 88200, '
                '"block_size": 512}\n',
                encoding="utf-8",
            )
            profile = root / "reaper-test/reaper.ini"
            profile.write_text(
                "linux_audio_srate=88200\nlinux_audio_bsize=512\n",
                encoding="utf-8",
            )
            batches = root / "batches"
            with (
                mock.patch.object(PROBE_RUNNER, "STAGING_RESULTS", staging),
                mock.patch.object(PROBE_RUNNER, "PROFILE", profile),
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(
                    PROBE_RUNNER, "_timestamp", return_value="20260830T120000Z"
                ),
            ):
                recovered = PROBE_RUNNER.recover_staging_partial()
                blocking = PROBE_RUNNER.prior_invalid_attempts(88200, 512)
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(
                recovered.name,
                "88200-512.invalid-20260830T120000Z-recovered",
            )
            self.assertTrue((recovered / "phase.log").is_file())
            self.assertEqual(blocking, [recovered])

    def test_unmarked_staging_from_another_workflow_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            staging = root / "reaper-test/test-results"
            staging.mkdir(parents=True)
            (staging / "phase.log").write_text(
                "suite-start\n", encoding="utf-8"
            )
            profile = root / "reaper-test/reaper.ini"
            profile.write_text(
                "linux_audio_srate=48000\nlinux_audio_bsize=32\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(PROBE_RUNNER, "STAGING_RESULTS", staging),
                mock.patch.object(PROBE_RUNNER, "PROFILE", profile),
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", root / "batches"),
            ):
                recovered = PROBE_RUNNER.recover_staging_partial()
            self.assertIsNone(recovered)
            self.assertTrue((staging / "phase.log").is_file())

    def test_legacy_recovered_staging_does_not_consume_a_v2_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            batches = pathlib.Path(temporary) / "batches"
            legacy = batches / "44100-32.invalid-old-recovered"
            legacy.mkdir(parents=True)
            marker = legacy / PROBE_RUNNER.STAGING_ATTEMPT_NAME
            marker.write_text(
                '{"schema": 1, "sample_rate": 44100, "block_size": 32}\n',
                encoding="utf-8",
            )
            with (
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(
                    PROBE_RUNNER, "recover_pending_batches", return_value=[]
                ),
                mock.patch.object(
                    PROBE_RUNNER,
                    "recover_staging_partial",
                    return_value=legacy,
                ),
                mock.patch.object(
                    PROBE_RUNNER, "run_row", return_value="completed"
                ) as run,
            ):
                outcomes = PROBE_RUNNER.run_matrix()

            self.assertEqual(len(outcomes), 20)
            self.assertEqual(run.call_count, 20)
            self.assertTrue(marker.is_file())

    def test_unverifiable_recovered_staging_remains_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            batches = pathlib.Path(temporary) / "batches"
            invalid = batches / "44100-32.invalid-broken-recovered"
            invalid.mkdir(parents=True)
            (invalid / PROBE_RUNNER.STAGING_ATTEMPT_NAME).write_text(
                "[]\n", encoding="utf-8"
            )
            with mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches):
                self.assertEqual(
                    PROBE_RUNNER.prior_invalid_attempts(44100, 32), [invalid]
                )

    def test_each_row_freshly_stages_project_and_runs_one_guard_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            batches = root / "batches"
            staging_results = root / "staging-results"
            staging_results.mkdir()
            project = root / "row.RPP"
            script = root / "capability.lua"
            script.write_text("-- fixture\n", encoding="utf-8")
            hashes = self.current_hashes()
            snapshot = self.healthy_snapshot()

            def copy_results(destination):
                self.write_complete_batch(destination, 44100, 32, hashes)

            with (
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(
                    PROBE_RUNNER, "STAGING_RESULTS", staging_results
                ),
                mock.patch.object(PROBE_RUNNER, "PROBE_SCRIPT", script),
                mock.patch.object(
                    PROBE_RUNNER, "project_path", return_value=project
                ),
                mock.patch.object(
                    PROBE_RUNNER, "input_hashes", return_value=hashes
                ),
                mock.patch.object(PROBE_RUNNER, "write_blank_project") as write,
                mock.patch.object(PROBE_RUNNER, "stage") as stage_call,
                mock.patch.object(
                    PROBE_RUNNER, "validate_native_vst3_environment"
                ) as validate,
                mock.patch.object(
                    PROBE_RUNNER, "require_stable_host", return_value=snapshot
                ),
                mock.patch.object(
                    PROBE_RUNNER,
                    "current_stability_snapshot",
                    return_value=snapshot,
                ),
                mock.patch.object(
                    PROBE_RUNNER, "stability_errors", return_value=[]
                ),
                mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
                mock.patch.object(
                    PROBE_RUNNER.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as launch,
                mock.patch.object(
                    PROBE_RUNNER,
                    "_copy_staging_results",
                    side_effect=copy_results,
                ),
            ):
                outcome = PROBE_RUNNER.run_row(44100, 32)

            self.assertEqual(outcome, "completed")
            write.assert_called_once_with(project)
            stage_call.assert_called_once_with(
                PROBE_RUNNER.ROOT,
                PROBE_RUNNER.STAGING_ROOT,
                case_set="host",
                sample_rate=44100,
                block_size=32,
                vst3_path=PROBE_RUNNER.BUILD_VST3_DIR,
            )
            validate.assert_called_once_with(
                PROBE_RUNNER.BUILD_VST3_DIR, PROBE_RUNNER.PROFILE
            )
            launch.assert_called_once()
            self.assertTrue((batches / "44100-32/metadata.json").is_file())

    def test_row_preflight_abort_is_preserved_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            batches = root / "batches"
            staging_results = root / "staging-results"
            staging_results.mkdir()
            script = root / "capability.lua"
            script.write_text("-- fixture\n", encoding="utf-8")
            hashes = self.current_hashes()

            with (
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(
                    PROBE_RUNNER, "STAGING_RESULTS", staging_results
                ),
                mock.patch.object(PROBE_RUNNER, "PROBE_SCRIPT", script),
                mock.patch.object(
                    PROBE_RUNNER, "input_hashes", return_value=hashes
                ),
                mock.patch.object(PROBE_RUNNER, "write_blank_project"),
                mock.patch.object(PROBE_RUNNER, "stage"),
                mock.patch.object(
                    PROBE_RUNNER, "validate_native_vst3_environment"
                ),
                mock.patch.object(
                    PROBE_RUNNER,
                    "require_stable_host",
                    side_effect=RuntimeError("memory full-pressure"),
                ),
                mock.patch.object(PROBE_RUNNER.subprocess, "run") as launch,
                mock.patch.object(
                    PROBE_RUNNER, "_timestamp", return_value="20260830T120000Z"
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "no retry"):
                    PROBE_RUNNER.run_row(44100, 32)

                invalid = PROBE_RUNNER.prior_invalid_attempts(44100, 32)

            launch.assert_not_called()
            self.assertEqual(len(invalid), 1)
            self.assertEqual(
                invalid[0].name, "44100-32.invalid-20260830T120000Z"
            )
            marker = invalid[0] / PROBE_RUNNER.STAGING_ATTEMPT_NAME
            self.assertTrue(marker.is_file())
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["inputs"],
                hashes,
            )
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))[
                    "evidence_namespace"
                ],
                "native-vst3-probe-v2",
            )

    def test_matrix_stops_on_first_failure_and_never_runs_the_tail(self):
        attempted = []

        def run_row(sample_rate, block_size):
            attempted.append((sample_rate, block_size))
            if (sample_rate, block_size) == (44100, 128):
                raise RuntimeError("first row failure")
            return "completed"

        with (
            mock.patch.object(PROBE_RUNNER, "recover_pending_batches", return_value=[]),
            mock.patch.object(PROBE_RUNNER, "recover_staging_partial", return_value=None),
            mock.patch.object(PROBE_RUNNER, "prior_invalid_attempts", return_value=[]),
            mock.patch.object(PROBE_RUNNER, "run_row", side_effect=run_row) as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "first row failure"):
                PROBE_RUNNER.run_matrix()
        self.assertEqual(attempted, [(44100, 32), (44100, 64), (44100, 128)])
        self.assertEqual(run.call_count, 3)

    def test_any_prior_invalid_attempt_prevents_retry(self):
        with (
            mock.patch.object(PROBE_RUNNER, "recover_pending_batches", return_value=[]),
            mock.patch.object(PROBE_RUNNER, "recover_staging_partial", return_value=None),
            mock.patch.object(
                PROBE_RUNNER,
                "prior_invalid_attempts",
                return_value=[pathlib.Path("44100-32.invalid-old")],
            ),
            mock.patch.object(PROBE_RUNNER, "run_row") as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "no retry"):
                PROBE_RUNNER.run_matrix()
        run.assert_not_called()

    def test_check_and_dry_run_never_stage_write_or_launch(self):
        healthy = self.healthy_snapshot()
        no_write_names = ("stage", "write_blank_project", "run_matrix")
        patches = [mock.patch.object(PROBE_RUNNER, name) for name in no_write_names]
        with (
            mock.patch.object(
                PROBE_RUNNER, "current_stability_snapshot", return_value=healthy
            ),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(
                PROBE_RUNNER,
                "planned_guard_commands",
                return_value=[["guard", "--dry-run"]] * 20,
            ) as planned,
            patches[0] as stage_call,
            patches[1] as write_project,
            patches[2] as run_matrix,
        ):
            self.assertEqual(PROBE_RUNNER.main(["--dry-run"]), 0)
        planned.assert_called_once_with(dry_run=True)
        stage_call.assert_not_called()
        write_project.assert_not_called()
        run_matrix.assert_not_called()

        with (
            mock.patch.object(
                PROBE_RUNNER, "current_stability_snapshot", return_value=healthy
            ),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(PROBE_RUNNER, "check_batches", return_value=[]) as check,
            mock.patch.object(PROBE_RUNNER, "stage") as stage_call,
            mock.patch.object(PROBE_RUNNER, "write_blank_project") as write_project,
            mock.patch.object(PROBE_RUNNER, "run_matrix") as run_matrix,
        ):
            self.assertEqual(PROBE_RUNNER.main(["--check"]), 0)
        check.assert_called_once_with()
        stage_call.assert_not_called()
        write_project.assert_not_called()
        run_matrix.assert_not_called()

    def test_observer_diagnostic_cli_never_delegates_to_v2_matrix(self):
        healthy = self.healthy_snapshot()
        with (
            mock.patch.object(
                PROBE_RUNNER, "current_stability_snapshot", return_value=healthy
            ),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(
                PROBE_RUNNER,
                "observer_diagnostic_guard_command",
                return_value=["guard", "--dry-run"],
            ) as plan,
            mock.patch.object(
                PROBE_RUNNER, "run_observer_diagnostic", return_value="completed"
            ) as diagnostic,
            mock.patch.object(PROBE_RUNNER, "run_matrix") as matrix,
        ):
            self.assertEqual(
                PROBE_RUNNER.main(["--observer-diagnostic-once", "--dry-run"]),
                0,
            )
            self.assertEqual(PROBE_RUNNER.main(["--observer-diagnostic-once"]), 0)
            self.assertEqual(
                PROBE_RUNNER.main(["--observer-diagnostic-once", "--check"]),
                2,
            )
        plan.assert_called_once_with(dry_run=True)
        diagnostic.assert_called_once_with()
        matrix.assert_not_called()

    def test_default_execution_delegates_to_serial_matrix(self):
        healthy = self.healthy_snapshot()
        with (
            mock.patch.object(
                PROBE_RUNNER, "current_stability_snapshot", return_value=healthy
            ),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(PROBE_RUNNER, "run_matrix", return_value={}) as run,
        ):
            result = PROBE_RUNNER.main([])
        self.assertEqual(result, 0)
        run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
