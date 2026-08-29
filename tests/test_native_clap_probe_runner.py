import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools import run_native_clap_probe as PROBE_RUNNER


class NativeClapProbeRunnerTests(unittest.TestCase):
    def test_preflight_refuses_existing_reaper_and_every_pressure_boundary(self):
        healthy = PROBE_RUNNER.StabilitySnapshot(
            available_mib=32000.0,
            load_one=2.0,
            temperature_c=70.0,
            memory_full_pressure_avg10=0.0,
            io_full_pressure_avg10=0.0,
        )
        self.assertEqual(PROBE_RUNNER.stability_errors(healthy, set()), [])
        self.assertIn("existing REAPER", PROBE_RUNNER.stability_errors(healthy, {42})[0])

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
                    any(message in error for error in PROBE_RUNNER.stability_errors(changed, set()))
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

    def test_pressure_parser_reads_only_full_avg10(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "memory"
            path.write_text(
                "some avg10=9.00 avg60=1.00 total=1\n"
                "full avg10=0.17 avg60=0.01 total=2\n",
                encoding="utf-8",
            )
            self.assertEqual(PROBE_RUNNER.pressure_avg10(path), 0.17)

    def test_dry_plan_has_four_serial_workspace_five_guard_commands(self):
        commands = PROBE_RUNNER.planned_guard_commands(dry_run=True)
        self.assertEqual(PROBE_RUNNER.BLOCK_SIZES, (32, 64, 128, 256))
        self.assertEqual(len(commands), 4)
        for command in commands:
            rendered = " ".join(command)
            self.assertIn("--dry-run", command)
            self.assertIn("--workspace 5", rendered)
            self.assertIn(str(PROBE_RUNNER.BUILD_CLAP_DIR), rendered)
            self.assertIn(str(PROBE_RUNNER.PROBE_REPORT), rendered)

    def test_pressure_record_is_atomic_json_with_before_and_after(self):
        snapshot = PROBE_RUNNER.StabilitySnapshot(
            available_mib=32000.0,
            load_one=2.0,
            temperature_c=None,
            memory_full_pressure_avg10=0.0,
            io_full_pressure_avg10=0.0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = pathlib.Path(temporary) / "pressure.json"
            PROBE_RUNNER.write_pressure_record(destination, snapshot, snapshot)
            value = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(set(value), {"before", "after"})
            self.assertEqual(value["before"]["available_mib"], 32000.0)
            self.assertEqual(list(destination.parent.glob(".pressure.json.*")), [])

    def test_default_execution_delegates_to_the_serial_matrix(self):
        healthy = PROBE_RUNNER.StabilitySnapshot(
            available_mib=32000.0,
            load_one=2.0,
            temperature_c=70.0,
            memory_full_pressure_avg10=0.0,
            io_full_pressure_avg10=0.0,
        )
        with (
            mock.patch.object(PROBE_RUNNER, "current_stability_snapshot", return_value=healthy),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(PROBE_RUNNER, "run_matrix", return_value={}) as run,
        ):
            result = PROBE_RUNNER.main([])
        self.assertEqual(result, 0)
        run.assert_called_once_with()

    def test_complete_batch_requires_finish_files_rate_block_and_current_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch = pathlib.Path(temporary) / "32"
            batch.mkdir()
            hashes = {"probe.clap": "abc", "runner.py": "def"}
            (batch / "phase.log").write_text(
                "suite-start\nsuite-finish\n", encoding="utf-8"
            )
            (batch / "capability.tsv").write_text(
                "metric\tvalue\nstatus\tpass\nsample_rate\t48000\n"
                "block_size\t32\ndry_error\t0\nsynth_peak\t0.5\n"
                "source_fault\t0\ncapture_overflow\t0\nfailure_count\t0\n",
                encoding="utf-8",
            )
            (batch / "events.tsv").write_text(
                "phase\tindex\tabsolute_sample\toffset\tstatus\tdata1\tdata2\n"
                + "\n".join(f"phase\t{index}\t0\t0\t144\t60\t100" for index in range(13))
                + "\n",
                encoding="utf-8",
            )
            (batch / "state.tsv").write_text(
                "index\tname\tminimum\tmaximum\tdefault\tmutated\trestored\n"
                + "\n".join(f"{index}\tp{index}\t0\t1\t0\t1\t1" for index in range(14))
                + "\n",
                encoding="utf-8",
            )
            (batch / "probe-native.tsv").write_text(
                "metric\tvalue\nschema\t1\n"
                "create\t1\ninit\t1\nactivate\t1\nstart\t1\nreset\t1\n"
                "stop\t1\ndeactivate\t1\ndestroy\t1\nfloat32_seen\t1\n"
                "float64_seen\t0\nself_test_alias_passed\t1\n"
                "self_test_separate_passed\t1\nCC119_trigger_one\t1\n"
                "CC119_trigger_two\t1\ntrigger_overflow\t0\n",
                encoding="utf-8",
            )
            (batch / "pressure.json").write_text(
                '{"before": {}, "after": {}}\n', encoding="utf-8"
            )
            (batch / "metadata.json").write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "sample_rate": 48000,
                        "block_size": 32,
                        "guard_returncode": 0,
                        "inputs": hashes,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                PROBE_RUNNER.batch_validation_errors(batch, 32, hashes), []
            )

            self.assertTrue(
                any(
                    "input hashes" in error
                    for error in PROBE_RUNNER.batch_validation_errors(
                        batch, 32, {**hashes, "runner.py": "changed"}
                    )
                )
            )
            (batch / "phase.log").write_text("suite-start\n", encoding="utf-8")
            self.assertTrue(
                any(
                    "suite-finish" in error
                    for error in PROBE_RUNNER.batch_validation_errors(batch, 32, hashes)
                )
            )

    def test_invalid_batch_is_preserved_with_timestamp_suffix(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch = pathlib.Path(temporary) / "64"
            batch.mkdir()
            (batch / "partial.log").write_text("partial\n", encoding="utf-8")
            archived = PROBE_RUNNER.archive_invalid_batch(
                batch, timestamp="20260829T120000Z"
            )
            self.assertFalse(batch.exists())
            self.assertEqual(archived.name, "64.invalid-20260829T120000Z")
            self.assertEqual(
                (archived / "partial.log").read_text(encoding="utf-8"),
                "partial\n",
            )

    def test_interrupted_staging_is_preserved_before_the_next_serial_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            staging = root / "reaper-test/test-results"
            staging.mkdir(parents=True)
            (staging / "phase.log").write_text("suite-start\n", encoding="utf-8")
            profile = root / "reaper-test/reaper.ini"
            profile.write_text("linux_audio_bsize=64\n", encoding="utf-8")
            batches = root / "batches"
            with (
                mock.patch.object(PROBE_RUNNER, "STAGING_RESULTS", staging),
                mock.patch.object(PROBE_RUNNER, "PROFILE", profile),
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(PROBE_RUNNER, "_timestamp", return_value="20260829T120000Z"),
            ):
                recovered = PROBE_RUNNER.recover_staging_partial()
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered.name, "64.invalid-20260829T120000Z-recovered")
            self.assertEqual(
                (recovered / "phase.log").read_text(encoding="utf-8"),
                "suite-start\n",
            )

    def test_interrupted_pending_directory_is_renamed_not_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            batches = pathlib.Path(temporary) / "batches"
            pending = batches / ".128.pending-42-20260829T110000Z"
            pending.mkdir(parents=True)
            (pending / "phase.log").write_text("suite-start\n", encoding="utf-8")
            with (
                mock.patch.object(PROBE_RUNNER, "BATCH_ROOT", batches),
                mock.patch.object(PROBE_RUNNER, "_timestamp", return_value="20260829T120000Z"),
            ):
                recovered = PROBE_RUNNER.recover_pending_batches()
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].name, "128.invalid-20260829T120000Z")
            self.assertTrue((recovered[0] / "phase.log").is_file())

    def test_matrix_executes_unfinished_blocks_once_in_serial_order(self):
        completed = []

        def run_batch(block_size):
            completed.append(block_size)
            return "completed"

        with (
            mock.patch.object(PROBE_RUNNER, "recover_pending_batches", return_value=[]),
            mock.patch.object(PROBE_RUNNER, "recover_staging_partial", return_value=None),
            mock.patch.object(PROBE_RUNNER, "run_batch", side_effect=run_batch) as run,
        ):
            outcomes = PROBE_RUNNER.run_matrix()
        self.assertEqual(completed, [32, 64, 128, 256])
        self.assertEqual(run.call_count, 4)
        self.assertEqual(outcomes, {32: "completed", 64: "completed", 128: "completed", 256: "completed"})

    def test_check_mode_never_stages_or_launches(self):
        healthy = PROBE_RUNNER.StabilitySnapshot(
            available_mib=32000.0,
            load_one=2.0,
            temperature_c=70.0,
            memory_full_pressure_avg10=0.0,
            io_full_pressure_avg10=0.0,
        )
        with (
            mock.patch.object(PROBE_RUNNER, "current_stability_snapshot", return_value=healthy),
            mock.patch.object(PROBE_RUNNER, "reaper_pids", return_value=set()),
            mock.patch.object(PROBE_RUNNER, "check_batches", return_value=[]) as check,
            mock.patch.object(PROBE_RUNNER, "run_matrix") as run,
        ):
            result = PROBE_RUNNER.main(["--check"])
        self.assertEqual(result, 0)
        check.assert_called_once_with()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
