import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_guarded_native_build.py"


class GuardedNativeBuildTests(unittest.TestCase):
    def load_runner(self):
        self.assertTrue(RUNNER.is_file(), "guarded native build runner is absent")
        spec = importlib.util.spec_from_file_location("run_guarded_native_build", RUNNER)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def run_runner(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        self.assertTrue(RUNNER.is_file(), "guarded native build runner is absent")
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_preflight_enforces_every_exact_pressure_boundary(self):
        runner = self.load_runner()
        self.assertEqual(runner.preflight_errors(4096, 12.0, 89.9, 0.24, 1.99), [])
        cases = (
            ((4095, 12.0, 89.9, 0.24, 1.99), "available memory"),
            ((4096, 12.01, 89.9, 0.24, 1.99), "one-minute load"),
            ((4096, 12.0, 90.0, 0.24, 1.99), "temperature"),
            ((4096, 12.0, 89.9, 0.25, 1.99), "memory-full"),
            ((4096, 12.0, 89.9, 0.24, 2.0), "I/O-full"),
        )
        for values, label in cases:
            with self.subTest(label=label):
                errors = runner.preflight_errors(*values)
                self.assertTrue(any(label in error for error in errors), errors)

    def test_pressure_parser_reads_only_full_avg10(self):
        runner = self.load_runner()
        text = (
            "some avg10=99.0 avg60=1.0 avg300=0.0 total=100\n"
            "full avg10=0.24 avg60=0.1 avg300=0.0 total=20\n"
        )
        self.assertEqual(runner.pressure_full_avg10(text), 0.24)
        with self.assertRaisesRegex(ValueError, "full avg10"):
            runner.pressure_full_avg10("some avg10=0.0\n")

    def test_guarded_command_has_serial_scope_timeout_and_priority_limits(self):
        runner = self.load_runner()
        command = runner.guarded_command(
            ["/usr/bin/cmake", "--version"],
            timeout_seconds=30,
            unit="m3-native-build-test",
        )
        joined = " ".join(command)
        for token in (
            "MemoryHigh=1536M",
            "MemoryMax=2048M",
            "MemorySwapMax=256M",
            "TasksMax=128",
            "CPUQuota=100%",
            "/usr/bin/timeout",
            "/usr/bin/nice -n 15",
            "/usr/bin/ionice -c 3",
            "/usr/bin/cmake --version",
        ):
            self.assertIn(token, joined)

        environment = runner.guard_environment()
        self.assertEqual(environment["CMAKE_BUILD_PARALLEL_LEVEL"], "1")
        self.assertEqual(environment["CTEST_PARALLEL_LEVEL"], "1")
        self.assertEqual(environment["MAKEFLAGS"], "-j1")

    def test_command_validation_rejects_network_packages_parallelism_and_escape(self):
        runner = self.load_runner()
        valid = [
            "/usr/bin/cmake",
            "--build",
            str(ROOT / "build/vst3/debug"),
            "--target",
            "m3_native_tests",
            "-j1",
        ]
        self.assertEqual(runner.command_errors(valid), [])
        cases = (
            ([sys.executable, str(RUNNER)], "recursive"),
            (["/usr/bin/apt-get", "install", "cmake"], "package"),
            (["/usr/bin/git", "clone", "https://example.test/sdk"], "network"),
            (["/usr/bin/cmake", "--build", str(ROOT / "build/vst3/debug"), "-j2"], "parallel"),
            (["/usr/bin/cmake", "--build", "/tmp/outside-m3", "-j1"], "outside"),
            (["/usr/bin/cmake", "--build", "../../outside-m3", "-j1"], "outside"),
            (["/usr/bin/cmake", "-S", str(ROOT), "-B/tmp/outside-m3"], "outside"),
        )
        for command, label in cases:
            with self.subTest(label=label):
                errors = runner.command_errors(command)
                self.assertTrue(any(label in error for error in errors), errors)

    def test_command_validation_allows_only_bounded_project_python_tests(self):
        runner = self.load_runner()
        self.assertEqual(
            runner.command_errors(
                [sys.executable, "-m", "unittest", "tests.test_vst3_build_contract"]
            ),
            [],
        )
        self.assertEqual(
            runner.command_errors(
                [sys.executable, str(ROOT / "tools/validate_native_source.py"), str(ROOT)]
            ),
            [],
        )
        cases = (
            ([sys.executable, "-m", "pip", "install", "anything"], "package"),
            ([sys.executable, "-c", "print('unbounded')"], "inline"),
            ([sys.executable, "/tmp/outside-m3.py"], "outside"),
        )
        for command, label in cases:
            with self.subTest(label=label):
                errors = runner.command_errors(command)
                self.assertTrue(any(label in error for error in errors), errors)

    def test_cli_check_and_dry_run_expose_the_complete_guard(self):
        common = (
            "--available-mib", "32000",
            "--load-one", "2.0",
            "--temperature-c", "50",
            "--memory-full", "0.0",
            "--io-full", "0.0",
        )
        check = self.run_runner("--check-only", *common)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("native build preflight: ok", check.stdout)

        dry = self.run_runner(
            "--dry-run",
            "--timeout", "30",
            *common,
            "--",
            "/usr/bin/cmake", "--version",
        )
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("MemoryMax=2048M", dry.stdout)
        self.assertIn("TasksMax=128", dry.stdout)
        self.assertIn("/usr/bin/cmake --version", dry.stdout)

    def test_atomic_json_publication_leaves_one_complete_record(self):
        runner = self.load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            target = pathlib.Path(temporary) / "snapshot.json"
            payload = {"phase": "before", "available_mib": 32000.0}
            runner.atomic_write_json(target, payload)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), payload)
            self.assertEqual(list(target.parent.glob("*.pending")), [])


if __name__ == "__main__":
    unittest.main()
