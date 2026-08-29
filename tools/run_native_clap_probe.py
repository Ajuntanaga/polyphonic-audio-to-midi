#!/usr/bin/env python3
"""Guard and dry-plan the serial disposable native CLAP capability probe."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_guarded_reaper import (  # noqa: E402
    available_memory_mib,
    maximum_temperature_c,
    preflight_errors,
)


BLOCK_SIZES = (32, 64, 128, 256)
BUILD_CLAP_DIR = (ROOT / "build/native/clap").resolve()
PROBE_ARTIFACT = (
    BUILD_CLAP_DIR / "M3_Polyphonic_Audio_to_MIDI_Probe.clap"
).resolve()
STAGING_ROOT = (ROOT / "build/reaper-test").resolve()
PROFILE = (STAGING_ROOT / "reaper.ini").resolve()
PROBE_REPORT = (STAGING_ROOT / "test-results/probe-native.tsv").resolve()
COMPLETION_FILE = (STAGING_ROOT / "test-results/phase.log").resolve()
PROJECT = (ROOT / "build/native-probe.RPP").resolve()
PROBE_SCRIPT = (
    STAGING_ROOT / "Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua"
).resolve()
GUARD = (ROOT / "tools/run_guarded_reaper.py").resolve()
MAX_MEMORY_FULL_PRESSURE_AVG10 = 0.25
MAX_IO_FULL_PRESSURE_AVG10 = 2.0


@dataclasses.dataclass(frozen=True)
class StabilitySnapshot:
    available_mib: float
    load_one: float
    temperature_c: float | None
    memory_full_pressure_avg10: float
    io_full_pressure_avg10: float


def pressure_avg10(path: pathlib.Path) -> float:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return 0.0
    for line in lines:
        fields = line.split()
        if fields[:1] != ["full"]:
            continue
        for field in fields[1:]:
            if field.startswith("avg10="):
                return float(field.split("=", 1)[1])
    return 0.0


def current_stability_snapshot() -> StabilitySnapshot:
    return StabilitySnapshot(
        available_mib=available_memory_mib(),
        load_one=os.getloadavg()[0],
        temperature_c=maximum_temperature_c(),
        memory_full_pressure_avg10=pressure_avg10(
            pathlib.Path("/proc/pressure/memory")
        ),
        io_full_pressure_avg10=pressure_avg10(pathlib.Path("/proc/pressure/io")),
    )


def reaper_pids(proc_root: pathlib.Path = pathlib.Path("/proc")) -> set[int]:
    pids: set[int] = set()
    try:
        processes = proc_root.iterdir()
    except OSError:
        return pids
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            executable = (process / "exe").resolve(strict=True)
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if executable.name == "reaper":
            pids.add(int(process.name))
    return pids


def stability_errors(
    snapshot: StabilitySnapshot,
    existing_reaper_pids: set[int],
) -> list[str]:
    errors = preflight_errors(
        snapshot.available_mib,
        snapshot.load_one,
        snapshot.temperature_c,
    )
    if existing_reaper_pids:
        errors.insert(
            0,
            "existing REAPER process detected: "
            + ",".join(str(pid) for pid in sorted(existing_reaper_pids)),
        )
    if snapshot.memory_full_pressure_avg10 >= MAX_MEMORY_FULL_PRESSURE_AVG10:
        errors.append(
            "memory full-pressure avg10 "
            f"{snapshot.memory_full_pressure_avg10:.2f} is at or above "
            f"{MAX_MEMORY_FULL_PRESSURE_AVG10:.2f}"
        )
    if snapshot.io_full_pressure_avg10 >= MAX_IO_FULL_PRESSURE_AVG10:
        errors.append(
            f"I/O full-pressure avg10 {snapshot.io_full_pressure_avg10:.2f} "
            f"is at or above {MAX_IO_FULL_PRESSURE_AVG10:.2f}"
        )
    return errors


def require_stable_host(snapshot: StabilitySnapshot | None = None) -> StabilitySnapshot:
    captured = snapshot if snapshot is not None else current_stability_snapshot()
    errors = stability_errors(captured, reaper_pids())
    if errors:
        raise RuntimeError("stability guard refusal: " + "; ".join(errors))
    return captured


def _atomic_write_json(path: pathlib.Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_pressure_record(
    destination: pathlib.Path,
    before: StabilitySnapshot,
    after: StabilitySnapshot,
) -> None:
    _atomic_write_json(
        destination,
        {
            "before": dataclasses.asdict(before),
            "after": dataclasses.asdict(after),
        },
    )


def guard_command(block_size: int, dry_run: bool = False) -> list[str]:
    if block_size not in BLOCK_SIZES:
        raise ValueError(f"unsupported native probe block size: {block_size}")
    command = [sys.executable, str(GUARD)]
    if dry_run:
        command.append("--dry-run")
    command.extend(
        [
            "--gui",
            "--workspace",
            "5",
            "--profile",
            str(PROFILE),
            "--clap-path",
            str(BUILD_CLAP_DIR),
            "--probe-report",
            str(PROBE_REPORT),
            "--completion-file",
            str(COMPLETION_FILE),
            "--timeout-seconds",
            "45",
            "--",
            str(PROJECT),
            str(PROBE_SCRIPT),
        ]
    )
    return command


def planned_guard_commands(dry_run: bool = False) -> list[list[str]]:
    return [guard_command(block_size, dry_run=dry_run) for block_size in BLOCK_SIZES]


def _snapshot_with_overrides(
    snapshot: StabilitySnapshot,
    args: argparse.Namespace,
) -> StabilitySnapshot:
    values = dataclasses.asdict(snapshot)
    for argument, field in (
        (args.available_mib, "available_mib"),
        (args.load_one, "load_one"),
        (args.temperature_c, "temperature_c"),
        (args.memory_pressure, "memory_full_pressure_avg10"),
        (args.io_pressure, "io_full_pressure_avg10"),
    ):
        if argument is not None:
            values[field] = argument
    return StabilitySnapshot(**values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Guard and dry-plan the disposable native CLAP probe"
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--available-mib", type=float)
    parser.add_argument("--load-one", type=float)
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("--memory-pressure", type=float)
    parser.add_argument("--io-pressure", type=float)
    args = parser.parse_args(argv)

    snapshot = _snapshot_with_overrides(current_stability_snapshot(), args)
    errors = stability_errors(snapshot, reaper_pids())
    if errors:
        print("native probe refusal: " + "; ".join(errors), file=sys.stderr)
        return 2
    print(
        "native probe preflight: ok "
        f"(available={snapshot.available_mib:.0f} MiB, "
        f"load1={snapshot.load_one:.2f}, "
        f"memory-full={snapshot.memory_full_pressure_avg10:.2f}, "
        f"io-full={snapshot.io_full_pressure_avg10:.2f})"
    )
    if args.check_only:
        return 0
    if not args.dry_run:
        print(
            "native probe refusal: execution is disabled until the capability "
            "payload is assembled and separately authorized",
            file=sys.stderr,
        )
        return 2

    for block_size, command in zip(BLOCK_SIZES, planned_guard_commands(dry_run=True)):
        print(f"native probe block {block_size}: {shlex.join(command)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
