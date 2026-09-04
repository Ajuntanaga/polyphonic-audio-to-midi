"""Bounded direct-child tests for the V4 single-child adapter."""
from __future__ import annotations

import json
import inspect
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from tools import reaper_v4_child_runner as runner


class _FakeProcess:
    def __init__(self, waits: list[object], pid: int = 4321) -> None:
        self.pid = pid
        self._waits = iter(waits)
        self.calls: list[tuple[str, object]] = []

    def kill(self) -> None:
        self.calls.append(("kill", None))

    def wait(self, timeout: object) -> int:
        self.calls.append(("wait", timeout))
        outcome = next(self._waits)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ChildRunnerCleanupRaceTest(unittest.TestCase):
    def spec(self) -> runner.ChildSpec:
        return runner.ChildSpec(
            argv=("/synthetic/sentinel",),
            cwd="/synthetic",
            environment=(),
            timeout_ms=10,
        )

    def install_one_shot_interrupt(self, matches: object) -> None:
        fired = False

        def trace(frame: object, event: str, argument: object) -> object:
            nonlocal fired
            if not fired and event == "line" and matches(frame):
                fired = True
                raise KeyboardInterrupt("synthetic interruption")
            return trace

        self.addCleanup(sys.settrace, sys.gettrace())
        sys.settrace(trace)

    def test_interrupt_immediately_after_popen_reaps_the_direct_child_before_reraising(self) -> None:
        process = _FakeProcess([17])
        popen_returned = False

        def launch(*arguments: object, **keywords: object) -> _FakeProcess:
            nonlocal popen_returned
            popen_returned = True
            return process

        self.install_one_shot_interrupt(
            lambda frame: (
                popen_returned
                and frame.f_code is runner.run_child.__code__
            )
        )

        with mock.patch.object(runner.subprocess, "Popen", side_effect=launch) as popen:
            with self.assertRaises(KeyboardInterrupt):
                runner.run_child(self.spec())

        popen.assert_called_once()
        self.assertEqual(process.calls, [("kill", None), ("wait", 1)])

    def test_interrupted_first_cleanup_wait_retries_then_reraises_after_reaping(self) -> None:
        process = _FakeProcess(
            [
                runner.subprocess.TimeoutExpired("sentinel", 0.01),
                KeyboardInterrupt("synthetic cleanup interruption"),
                23,
            ]
        )

        with mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(KeyboardInterrupt):
                runner.run_child(self.spec())

        popen.assert_called_once()
        self.assertEqual(
            process.calls,
            [
                ("wait", 0.01),
                ("kill", None),
                ("wait", 1),
                ("kill", None),
                ("wait", 1),
            ],
        )

    def test_interrupted_second_cleanup_kill_waits_once_then_reraises(self) -> None:
        process = _FakeProcess(
            [
                runner.subprocess.TimeoutExpired("sentinel", 0.01),
                runner.subprocess.TimeoutExpired("sentinel", 1),
                23,
            ]
        )
        stop_and_reap = next(
            constant
            for constant in runner.run_child.__code__.co_consts
            if isinstance(constant, types.CodeType) and constant.co_name == "stop_and_reap"
        )
        source_lines, first_line = inspect.getsourcelines(runner.run_child)
        kill_line = next(
            first_line + index
            for index, line in enumerate(source_lines)
            if line.strip() == "process.kill()"
        )
        fired = False

        def trace(frame: object, event: str, argument: object) -> object:
            nonlocal fired
            if (
                not fired
                and event == "line"
                and frame.f_code is stop_and_reap
                and frame.f_lineno == kill_line
                and process.calls
                == [("wait", 0.01), ("kill", None), ("wait", 1)]
            ):
                fired = True
                raise KeyboardInterrupt("synthetic second-cleanup interruption")
            return trace

        self.addCleanup(sys.settrace, sys.gettrace())
        sys.settrace(trace)
        with mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(KeyboardInterrupt):
                runner.run_child(self.spec())

        self.assertTrue(fired)
        popen.assert_called_once()
        self.assertEqual(
            process.calls,
            [
                ("wait", 0.01),
                ("kill", None),
                ("wait", 1),
                ("wait", 1),
            ],
        )

    def test_first_cleanup_interrupt_is_preserved_across_second_cleanup_interrupt(self) -> None:
        process = _FakeProcess(
            [
                runner.subprocess.TimeoutExpired("sentinel", 0.01),
                KeyboardInterrupt("first"),
                KeyboardInterrupt("second"),
            ]
        )

        with mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(KeyboardInterrupt) as raised:
                runner.run_child(self.spec())

        popen.assert_called_once()
        self.assertEqual(raised.exception.args, ("first",))
        self.assertEqual(
            process.calls,
            [
                ("wait", 0.01),
                ("kill", None),
                ("wait", 1),
                ("kill", None),
                ("wait", 1),
            ],
        )

    def test_invalid_primary_return_code_does_not_kill_an_already_reaped_child(self) -> None:
        process = _FakeProcess([256])

        with mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(runner.ChildRunnerError):
                runner.run_child(self.spec())

        popen.assert_called_once()
        self.assertEqual(process.calls, [("wait", 0.01)])

    def test_cleanup_interrupt_supersedes_an_ordinary_postbind_failure(self) -> None:
        process = _FakeProcess(
            [KeyboardInterrupt("cleanup"), 17],
            pid=0,
        )

        with mock.patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(KeyboardInterrupt) as raised:
                runner.run_child(self.spec())

        popen.assert_called_once()
        self.assertEqual(raised.exception.args, ("cleanup",))
        self.assertEqual(
            process.calls,
            [("kill", None), ("wait", 1), ("kill", None), ("wait", 1)],
        )


class ChildRunnerSentinelTest(unittest.TestCase):
    """Exercise only a short, non-forking Python child through the adapter."""

    def sentinel_spec(
        self, directory: str, *arguments: str, timeout_ms: int = 500
    ) -> runner.ChildSpec:
        return runner.ChildSpec(
            argv=(sys.executable, "-I", "-S", "-B", "-c", *arguments),
            cwd=directory,
            environment=(
                ("SENTINEL_OUTPUT", os.path.join(directory, "sentinel.json")),
                ("SENTINEL_VALUE", "M3"),
            ),
            timeout_ms=timeout_ms,
        )

    def test_sentinel_uses_isolated_no_site_no_bytecode_startup(self) -> None:
        spec = self.sentinel_spec("/tmp", "pass")

        self.assertEqual(spec.argv[:5], (sys.executable, "-I", "-S", "-B", "-c"))

    def test_success_uses_only_declared_environment_and_working_directory(self) -> None:
        code = (
            "import json, os; "
            "json.dump({'pid': os.getpid(), 'cwd': os.getcwd(), "
            "'value': os.environ.get('SENTINEL_VALUE'), "
            "'parent_only': os.environ.get('M3_PARENT_ONLY')}, "
            "open(os.environ['SENTINEL_OUTPUT'], 'w', encoding='utf-8'))"
        )
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"M3_PARENT_ONLY": "must-not-leak"}):
                outcome = runner.run_child(self.sentinel_spec(directory, code))
            with open(os.path.join(directory, "sentinel.json"), encoding="utf-8") as stream:
                record = json.load(stream)

        self.assertGreater(outcome.child_pid, 0)
        self.assertEqual(record["pid"], outcome.child_pid)
        self.assertEqual(record["cwd"], directory)
        self.assertEqual(record["value"], "M3")
        self.assertIsNone(record["parent_only"])
        self.assertEqual(outcome.returncode, 0)
        self.assertFalse(outcome.timed_out)

    def test_timeout_kills_and_reaps_the_direct_nonforking_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            outcome = runner.run_child(
                self.sentinel_spec(directory, "import time; time.sleep(5)", timeout_ms=40)
            )
            elapsed = time.monotonic() - started

        self.assertTrue(outcome.timed_out)
        self.assertLess(outcome.returncode, 0)
        self.assertLess(elapsed, 1.5)
        with self.assertRaises(ChildProcessError):
            os.waitpid(outcome.child_pid, os.WNOHANG)

    def test_nonzero_exit_is_reported_without_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outcome = runner.run_child(self.sentinel_spec(directory, "import sys; sys.exit(23)"))

        self.assertEqual(outcome.returncode, 23)
        self.assertFalse(outcome.timed_out)

    def test_invalid_specs_are_rejected_before_any_launch(self) -> None:
        valid = self.sentinel_spec("/tmp", "pass")
        invalid_specs = (
            object(),
            runner.ChildSpec(("relative",), "/tmp", (), 10),
            runner.ChildSpec((sys.executable,), "relative", (), 10),
            runner.ChildSpec((sys.executable,), "/tmp", (("PATH", "x"),), 10),
            runner.ChildSpec((sys.executable,), "/tmp", (("A", "x"), ("A", "y")), 10),
            runner.ChildSpec((sys.executable,), "/tmp", (), True),
        )
        self.assertIsInstance(valid, runner.ChildSpec)
        with mock.patch.object(runner.subprocess, "Popen") as popen:
            for spec in invalid_specs:
                with self.assertRaises(runner.ChildRunnerError):
                    runner.run_child(spec)  # type: ignore[arg-type]
        popen.assert_not_called()

    def test_launch_failure_is_normalized_and_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self.sentinel_spec(directory, "pass")
            with mock.patch.object(runner.subprocess, "Popen", side_effect=OSError("denied")) as popen:
                with self.assertRaises(runner.ChildRunnerError) as raised:
                    runner.run_child(spec)

        self.assertIsInstance(raised.exception.__cause__, OSError)
        popen.assert_called_once()
