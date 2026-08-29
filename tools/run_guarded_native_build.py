#!/usr/bin/env python3
"""Run one offline native build/test command inside bounded host limits."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_ROOT = (ROOT / "build").resolve()
RECORD_ROOT = BUILD_ROOT / "test-results/native-build-guard"

MIN_AVAILABLE_MIB = 4096.0
MAX_LOAD_ONE = 12.0
MAX_TEMPERATURE_C = 90.0
MAX_MEMORY_FULL_AVG10 = 0.25
MAX_IO_FULL_AVG10 = 2.0

PACKAGE_COMMANDS = {
    "apt",
    "apt-get",
    "dnf",
    "dpkg",
    "flatpak",
    "nix-env",
    "pacman",
    "pip",
    "pip3",
    "snap",
    "yum",
    "zypper",
}
NETWORK_COMMANDS = {
    "aria2c",
    "curl",
    "ftp",
    "nc",
    "scp",
    "sftp",
    "ssh",
    "wget",
}
NETWORK_GIT_OPERATIONS = {"clone", "fetch", "pull", "ls-remote", "submodule"}
ALLOWED_SYSTEM_COMMANDS = {"cmake", "ctest"}
ALLOWED_PYTHON_MODULES = {"unittest"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def pressure_full_avg10(text: str) -> float:
    match = re.search(r"(?m)^full\s+avg10=([0-9]+(?:\.[0-9]+)?)\b", text)
    if match is None:
        raise ValueError("pressure record has no full avg10 value")
    return float(match.group(1))


def preflight_errors(
    available_mib: float,
    load_one: float,
    temperature_c: float | None,
    memory_full_avg10: float,
    io_full_avg10: float,
) -> list[str]:
    errors: list[str] = []
    if available_mib < MIN_AVAILABLE_MIB:
        errors.append(
            f"available memory {available_mib:.1f} MiB is below {MIN_AVAILABLE_MIB:.0f} MiB"
        )
    if load_one > MAX_LOAD_ONE:
        errors.append(
            f"one-minute load {load_one:.2f} exceeds {MAX_LOAD_ONE:.1f}"
        )
    if temperature_c is not None and temperature_c >= MAX_TEMPERATURE_C:
        errors.append(
            f"temperature {temperature_c:.1f} C reached {MAX_TEMPERATURE_C:.0f} C"
        )
    if memory_full_avg10 >= MAX_MEMORY_FULL_AVG10:
        errors.append(
            "memory-full PSI "
            f"{memory_full_avg10:.2f} reached {MAX_MEMORY_FULL_AVG10:.2f}"
        )
    if io_full_avg10 >= MAX_IO_FULL_AVG10:
        errors.append(
            f"I/O-full PSI {io_full_avg10:.2f} reached {MAX_IO_FULL_AVG10:.2f}"
        )
    return errors


def _parallel_errors(command: Sequence[str]) -> list[str]:
    errors: list[str] = []
    index = 0
    while index < len(command):
        token = command[index]
        value: str | None = None
        if token in {"-j", "--parallel"}:
            if index + 1 >= len(command):
                errors.append(f"parallel option {token} has no one-job value")
            else:
                value = command[index + 1]
                index += 1
        elif token.startswith("-j") and token != "-j":
            value = token[2:]
        elif token.startswith("--parallel="):
            value = token.split("=", 1)[1]
        if value is not None and value != "1":
            errors.append(f"parallel build value must be one, not {value!r}")
        index += 1
    return errors


def _inside_project(path: pathlib.Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(ROOT)
        return True
    except ValueError:
        return False


def _declared_path_arguments(
    command: Sequence[str], *, executable_name: str, is_python: bool
) -> list[str]:
    paths: list[str] = []
    separate_flags = {"-S", "-B", "--build", "--install", "--test-dir"}
    attached_prefixes = ("-S", "-B", "--test-dir=")
    index = 1
    if executable_name in ALLOWED_SYSTEM_COMMANDS:
        while index < len(command):
            token = command[index]
            if token in separate_flags and index + 1 < len(command):
                paths.append(command[index + 1])
                index += 2
                continue
            for prefix in attached_prefixes:
                if token.startswith(prefix) and token != prefix:
                    paths.append(token[len(prefix) :])
                    break
            index += 1

    if is_python and "-m" not in command[1:]:
        paths.extend(token for token in command[1:] if token.endswith(".py"))
    return paths


def command_errors(command: Sequence[str]) -> list[str]:
    if not command:
        return ["no command was supplied"]

    errors: list[str] = []
    executable = pathlib.Path(command[0])
    executable_name = executable.name.lower()
    is_python = re.fullmatch(r"python(?:3(?:\.\d+)?)?", executable_name) is not None
    runner = pathlib.Path(__file__).resolve()

    if executable_name == runner.name.lower() or any(
        pathlib.Path(token).resolve(strict=False) == runner
        for token in command[1:]
        if token.endswith(runner.name)
    ):
        errors.append("recursive guarded-build invocation is forbidden")
    if executable_name in PACKAGE_COMMANDS:
        errors.append(f"package command is forbidden: {executable_name}")
    if executable_name in NETWORK_COMMANDS:
        errors.append(f"network command is forbidden: {executable_name}")
    if executable_name == "git" and any(
        token.lower() in NETWORK_GIT_OPERATIONS for token in command[1:]
    ):
        errors.append("network git operation is forbidden")
    if any(re.match(r"(?i)^(?:https?|ftp)://", token) for token in command[1:]):
        errors.append("network URL is forbidden")

    if is_python:
        if "-c" in command[1:]:
            errors.append("inline Python execution is forbidden")
        if "-m" in command[1:]:
            module_index = command.index("-m") + 1
            if module_index >= len(command):
                errors.append("Python module invocation is incomplete")
            else:
                module = command[module_index].lower()
                if module in {"pip", "ensurepip"}:
                    errors.append(f"package Python module is forbidden: {module}")
                elif module not in ALLOWED_PYTHON_MODULES:
                    errors.append(f"Python module is outside the test allowlist: {module}")

    errors.extend(_parallel_errors(command))

    if executable_name not in ALLOWED_SYSTEM_COMMANDS and not is_python:
        resolved_executable = (
            executable.resolve(strict=False)
            if executable.is_absolute() or "/" in command[0]
            else (ROOT / executable).resolve(strict=False)
        )
        if not _inside_project(resolved_executable):
            errors.append(f"executable is outside the repository: {command[0]}")

    for token in command[1:]:
        if not token.startswith("/"):
            continue
        candidate = pathlib.Path(token)
        if not _inside_project(candidate):
            errors.append(f"path is outside the repository/build root: {token}")

    for token in _declared_path_arguments(
        command, executable_name=executable_name, is_python=is_python
    ):
        candidate = pathlib.Path(token)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if not _inside_project(candidate):
            errors.append(f"declared path is outside the repository/build root: {token}")

    return errors


def _required_program(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required guard program is absent: {name}")
    return str(pathlib.Path(path).absolute())


def guarded_command(
    command: Sequence[str], *, timeout_seconds: int, unit: str
) -> list[str]:
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    return [
        _required_program("systemd-run"),
        "--user",
        "--scope",
        "--collect",
        "--quiet",
        f"--unit={unit}",
        "--property=MemoryHigh=1536M",
        "--property=MemoryMax=2048M",
        "--property=MemorySwapMax=256M",
        "--property=TasksMax=128",
        "--property=CPUQuota=100%",
        "--property=CPUWeight=10",
        "--property=IOWeight=10",
        _required_program("timeout"),
        "--signal=TERM",
        "--kill-after=10s",
        f"{timeout_seconds}s",
        _required_program("prlimit"),
        "--core=0:0",
        "--nice=0:0",
        "--rtprio=0:0",
        "--nofile=4096:4096",
        "--",
        _required_program("nice"),
        "-n",
        "15",
        _required_program("ionice"),
        "-c",
        "3",
        *command,
    ]


def atomic_write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f"{path.name}.{os.getpid()}.pending")
    try:
        pending.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(pending, path)
    finally:
        try:
            pending.unlink()
        except FileNotFoundError:
            pass


def _read_available_mib() -> float:
    text = pathlib.Path("/proc/meminfo").read_text(encoding="utf-8")
    match = re.search(r"(?m)^MemAvailable:\s+([0-9]+)\s+kB$", text)
    if match is None:
        raise RuntimeError("MemAvailable is absent from /proc/meminfo")
    return float(match.group(1)) / 1024.0


def _read_pressure(kind: str) -> float:
    return pressure_full_avg10(
        pathlib.Path(f"/proc/pressure/{kind}").read_text(encoding="utf-8")
    )


def _read_temperature_c() -> float | None:
    values: list[float] = []
    thermal_root = pathlib.Path("/sys/class/thermal")
    if thermal_root.is_dir():
        for path in sorted(thermal_root.glob("thermal_zone*/temp")):
            try:
                raw = float(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            value = raw / 1000.0 if raw > 1000.0 else raw
            if 0.0 < value < 200.0:
                values.append(value)
    return max(values) if values else None


def read_metrics() -> dict[str, float | None]:
    return {
        "available_mib": _read_available_mib(),
        "load_one": os.getloadavg()[0],
        "temperature_c": _read_temperature_c(),
        "memory_full_avg10": _read_pressure("memory"),
        "io_full_avg10": _read_pressure("io"),
    }


def _metric_snapshot(args: argparse.Namespace) -> dict[str, float | None]:
    measured = read_metrics()
    overrides = {
        "available_mib": args.available_mib,
        "load_one": args.load_one,
        "temperature_c": args.temperature_c,
        "memory_full_avg10": args.memory_full,
        "io_full_avg10": args.io_full,
    }
    for key, value in overrides.items():
        if value is not None:
            measured[key] = value
    return measured


def _preflight_from_metrics(metrics: dict[str, float | None]) -> list[str]:
    return preflight_errors(
        float(metrics["available_mib"]),
        float(metrics["load_one"]),
        (
            None
            if metrics["temperature_c"] is None
            else float(metrics["temperature_c"])
        ),
        float(metrics["memory_full_avg10"]),
        float(metrics["io_full_avg10"]),
    )


def guard_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["CMAKE_BUILD_PARALLEL_LEVEL"] = "1"
    environment["CTEST_PARALLEL_LEVEL"] = "1"
    environment["MAKEFLAGS"] = "-j1"
    runtime = pathlib.Path(f"/run/user/{os.getuid()}")
    bus = runtime / "bus"
    if bus.is_socket():
        environment.setdefault("XDG_RUNTIME_DIR", str(runtime))
        environment.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus}")
    return environment


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    for sig, seconds in (
        (signal.SIGINT, 2.0),
        (signal.SIGTERM, 3.0),
        (signal.SIGKILL, 1.0),
    ):
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=seconds)
            return
        except subprocess.TimeoutExpired:
            continue


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one serial native build/test command under stability limits"
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--available-mib", type=float)
    parser.add_argument("--load-one", type=float)
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("--memory-full", type=float)
    parser.add_argument("--io-full", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_arguments(argv)
    metrics = _metric_snapshot(args)
    failures = _preflight_from_metrics(metrics)
    if failures:
        for failure in failures:
            print(f"native build preflight refused: {failure}", file=sys.stderr)
        return 2

    print("native build preflight: ok")
    if args.check_only:
        return 0
    if not args.command:
        print("native build guard: no command was supplied", file=sys.stderr)
        return 2

    validation = command_errors(args.command)
    if validation:
        for failure in validation:
            print(f"native build guard refused: {failure}", file=sys.stderr)
        return 2

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    unit = f"m3-native-build-{os.getpid()}-{int(time.time() * 1000)}"
    command = guarded_command(
        args.command,
        timeout_seconds=args.timeout,
        unit=unit,
    )
    if args.dry_run:
        print(shlex.join(command))
        return 0

    before_path = RECORD_ROOT / f"{stamp}-{os.getpid()}-before.json"
    after_path = RECORD_ROOT / f"{stamp}-{os.getpid()}-after.json"
    before = {
        "phase": "before",
        "timestamp_utc": utc_now(),
        "repository": str(ROOT),
        "unit": unit,
        "timeout_seconds": args.timeout,
        "command": list(args.command),
        "guarded_command": command,
        "metrics": metrics,
    }
    atomic_write_json(before_path, before)

    started = time.monotonic()
    result_code = 2
    classification = "launch-failed"
    interrupted = False
    process: subprocess.Popen[Any] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=guard_environment(),
            start_new_session=True,
        )
        result_code = process.wait()
        classification = (
            "passed"
            if result_code == 0
            else "timed-out"
            if result_code == 124
            else "failed"
        )
    except KeyboardInterrupt:
        interrupted = True
        classification = "interrupted"
        result_code = 130
        if process is not None:
            _terminate_process_group(process)
    except OSError as error:
        print(f"native build guard launch failed: {error}", file=sys.stderr)
    finally:
        try:
            after_metrics = read_metrics()
        except (OSError, RuntimeError, ValueError):
            after_metrics = None
        after = {
            "phase": "after",
            "timestamp_utc": utc_now(),
            "repository": str(ROOT),
            "unit": unit,
            "command": list(args.command),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "returncode": result_code,
            "classification": classification,
            "interrupted": interrupted,
            "metrics": after_metrics,
        }
        atomic_write_json(after_path, after)

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
