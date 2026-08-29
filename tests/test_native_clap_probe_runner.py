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

    def test_execution_remains_disabled_in_the_initial_guard_shell(self):
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
            mock.patch.object(PROBE_RUNNER.subprocess, "run") as run,
        ):
            result = PROBE_RUNNER.main([])
        self.assertEqual(result, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
