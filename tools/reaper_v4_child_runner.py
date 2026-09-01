"""Single-child adapter reserved for a later authorized in-namespace session owner."""
from __future__ import annotations

import dataclasses
import subprocess
import time


__all__ = (
    "ChildRunnerError",
    "ChildSpec",
    "ChildOutcome",
    "run_child",
)


class ChildRunnerError(ValueError):
    """The declared child command violates the fixed one-process adapter contract."""


@dataclasses.dataclass(frozen=True)
class ChildSpec:
    """The complete, immutable launch declaration for exactly one child."""

    argv: tuple[str, ...]
    cwd: str
    environment: tuple[tuple[str, str], ...]
    timeout_ms: int


@dataclasses.dataclass(frozen=True)
class ChildOutcome:
    """The terminal result of the only child launched by the adapter."""

    child_pid: int
    returncode: int
    timed_out: bool
    elapsed_ms: int


def run_child(spec: ChildSpec) -> ChildOutcome:
    """Launch once with sealed descriptors, then wait or kill and wait on timeout."""
    def bounded_utf8(value: object, maximum: int) -> bool:
        if type(value) is not str:
            return False
        try:
            return len(value.encode("utf-8")) <= maximum
        except UnicodeEncodeError:
            return False

    if type(spec) is not ChildSpec:
        raise ChildRunnerError("spec must be a ChildSpec")
    argv = spec.argv
    cwd = spec.cwd
    environment_entries = spec.environment
    timeout_ms = spec.timeout_ms
    if type(argv) is not tuple or not 0 < len(argv) <= 16:
        raise ChildRunnerError("argv must be a bounded nonempty tuple")
    if any(
        not bounded_utf8(argument, 4096)
        or not argument
        or "\x00" in argument
        for argument in argv
    ):
        raise ChildRunnerError("argv entries must be bounded nonempty strings")
    if not argv[0].startswith("/"):
        raise ChildRunnerError("executable must be absolute")
    if (
        not bounded_utf8(cwd, 4096)
        or not cwd
        or not cwd.startswith("/")
        or "\x00" in cwd
    ):
        raise ChildRunnerError("cwd must be a bounded absolute path")
    if type(timeout_ms) is not int:
        raise ChildRunnerError("timeout_ms must be an integer")
    if not 0 < timeout_ms <= 30000:
        raise ChildRunnerError("timeout_ms exceeds the bounded adapter limit")
    if type(environment_entries) is not tuple or len(environment_entries) > 64:
        raise ChildRunnerError("environment must be a bounded tuple")
    environment: dict[str, str] = {}
    for entry in environment_entries:
        if type(entry) is not tuple or len(entry) != 2:
            raise ChildRunnerError("environment entries must be string pairs")
        name, value = entry
        if (
            not bounded_utf8(name, 128)
            or not bounded_utf8(value, 4096)
            or not name
            or "=" in name
            or "\x00" in name
            or "\x00" in value
        ):
            raise ChildRunnerError("environment entries must be valid string pairs")
        if name == "PATH" or name in environment:
            raise ChildRunnerError("environment may not override PATH or duplicate keys")
        environment[name] = value
    started_ns = time.monotonic_ns()
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=environment,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=(),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ChildRunnerError("child launch failed") from error

    cleanup_started = False

    def stop_and_reap() -> int:
        nonlocal cleanup_started
        cleanup_started = True
        interruption: BaseException | None = None
        last_error: Exception | None = None
        for _ in range(2):
            try:
                process.kill()
            except BaseException as error:
                if isinstance(error, Exception):
                    last_error = error
                elif interruption is None:
                    interruption = error
            try:
                returncode = process.wait(timeout=1)
            except BaseException as error:
                if isinstance(error, Exception):
                    last_error = error
                elif interruption is None:
                    interruption = error
            else:
                if interruption is not None:
                    raise interruption
                return returncode
        if interruption is not None:
            raise interruption
        if last_error is not None:
            raise ChildRunnerError("post-launch child cleanup failed") from last_error
        raise ChildRunnerError("post-launch child cleanup failed")

    try:
        child_pid = process.pid
        if (
            isinstance(child_pid, bool)
            or not isinstance(child_pid, int)
            or not 1 <= child_pid <= 2147483647
        ):
            raise ChildRunnerError("child did not report a positive pid")
        timed_out = False
        try:
            returncode = process.wait(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = stop_and_reap()
        elapsed_ms = (time.monotonic_ns() - started_ns) // 1_000_000
        if (
            isinstance(returncode, bool)
            or not isinstance(returncode, int)
            or not -255 <= returncode <= 255
        ):
            raise ChildRunnerError("child did not report a bounded integer return code")
        return ChildOutcome(
            child_pid=child_pid,
            returncode=returncode,
            timed_out=timed_out,
            elapsed_ms=elapsed_ms,
        )
    except BaseException:
        if not cleanup_started:
            try:
                stop_and_reap()
            except BaseException:
                pass
        raise
