#!/usr/bin/env python3
"""Run or verify the serial disposable native CLAP capability matrix."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import shlex
import shutil
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
from tools.stage_reaper_test_env import stage  # noqa: E402


BLOCK_SIZES = (32, 64, 128, 256)
SAMPLE_RATE = 48000
BUILD_CLAP_DIR = (ROOT / "build/native/clap").resolve()
PROBE_ARTIFACT = (
    BUILD_CLAP_DIR / "M3_Polyphonic_Audio_to_MIDI_Probe.clap"
).resolve()
STAGING_ROOT = (ROOT / "build/reaper-test").resolve()
PROFILE = (STAGING_ROOT / "reaper.ini").resolve()
STAGING_RESULTS = (STAGING_ROOT / "test-results").resolve()
PROBE_REPORT = (STAGING_RESULTS / "probe-native.tsv").resolve()
COMPLETION_FILE = (STAGING_RESULTS / "phase.log").resolve()
PROJECT = (ROOT / "build/native-probe.RPP").resolve()
PROBE_SCRIPT = (
    STAGING_ROOT / "Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua"
).resolve()
GUARD = (ROOT / "tools/run_guarded_reaper.py").resolve()
BATCH_ROOT = (ROOT / "build/test-results/native-clap-probe/batches").resolve()
MAX_MEMORY_FULL_PRESSURE_AVG10 = 0.25
MAX_IO_FULL_PRESSURE_AVG10 = 2.0
EXPECTED_RESULT_FILES = (
    "phase.log",
    "capability.tsv",
    "events.tsv",
    "state.tsv",
    "probe-native.tsv",
    "pressure.json",
    "metadata.json",
)
HASH_INPUTS = {
    "probe_artifact": PROBE_ARTIFACT,
    "capability_script": (
        ROOT / "Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua"
    ).resolve(),
    "capability_source": (
        ROOT / "Effects/tests/ajuntanaga_M3 Native CLAP Capability Source.jsfx"
    ).resolve(),
    "midi_capture": (
        ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - MIDI Capture.jsfx"
    ).resolve(),
    "synth_output_probe": (
        ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - Synth Output Probe.jsfx"
    ).resolve(),
    "disposable_project": PROJECT,
    "runner": pathlib.Path(__file__).resolve(),
    "guard": GUARD,
    "stager": (ROOT / "tools/stage_reaper_test_env.py").resolve(),
}


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
        prefix=f".{path.name}.", dir=path.parent, text=True
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


def _atomic_write_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent, text=True
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
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


def write_blank_project(path: pathlib.Path = PROJECT) -> None:
    _atomic_write_text(
        path,
        '<REAPER_PROJECT 0.1 "7.0/linux-x86_64" 0\n'
        "  RIPPLE 0\n"
        "  GROUPOVERRIDE 0 0 0\n"
        "  AUTOXFADE 1\n"
        "  ENVATTACH 1\n"
        "  POOLEDENVATTACH 0\n"
        "  MIXERUIFLAGS 11 48\n"
        "  PEAKGAIN 1\n"
        "  FEEDBACK 0\n"
        "  PANLAW 1\n"
        "  PROJOFFS 0 0 0\n"
        "  MAXPROJLEN 0 600\n"
        ">\n",
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hashes() -> dict[str, str]:
    missing = [name for name, path in HASH_INPUTS.items() if not path.is_file()]
    if missing:
        raise ValueError("missing native probe inputs: " + ", ".join(missing))
    return {name: sha256(path) for name, path in sorted(HASH_INPUTS.items())}


def _read_metric_tsv(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "metric\tvalue":
        raise ValueError(f"invalid metric TSV header: {path}")
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != 2 or not fields[0] or fields[0] in values:
            raise ValueError(f"invalid metric TSV row: {path}: {line!r}")
        values[fields[0]] = fields[1]
    return values


def batch_validation_errors(
    batch: pathlib.Path,
    block_size: int,
    current_hashes: Mapping[str, str],
) -> list[str]:
    errors: list[str] = []
    if block_size not in BLOCK_SIZES:
        return [f"unsupported block size: {block_size}"]
    if not batch.is_dir():
        return [f"batch directory is missing: {batch}"]
    for name in EXPECTED_RESULT_FILES:
        if not (batch / name).is_file():
            errors.append(f"missing expected file: {name}")

    phase = batch / "phase.log"
    if phase.is_file():
        try:
            phases = phase.read_text(encoding="utf-8").splitlines()
            if not phases or phases[-1] != "suite-finish":
                errors.append("phase.log does not end in suite-finish")
        except (OSError, UnicodeError) as exc:
            errors.append(f"unreadable phase.log: {exc}")

    capability = batch / "capability.tsv"
    if capability.is_file():
        try:
            values = _read_metric_tsv(capability)
            if values.get("status") != "pass":
                errors.append("capability status is not pass")
            if int(values.get("sample_rate", "-1")) != SAMPLE_RATE:
                errors.append("actual sample rate does not match 48000")
            if int(values.get("block_size", "-1")) != block_size:
                errors.append("actual block size does not match batch")
            if float(values.get("dry_error", "nan")) != 0.0:
                errors.append("dry error is not zero")
            synth_peak = float(values.get("synth_peak", "nan"))
            if not math.isfinite(synth_peak) or synth_peak <= 0.0:
                errors.append("synth peak is not finite and positive")
            if int(values.get("source_fault", "-1")) != 0:
                errors.append("source fault is not zero")
            if int(values.get("capture_overflow", "-1")) != 0:
                errors.append("capture overflow is not zero")
            if int(values.get("failure_count", "-1")) != 0:
                errors.append("capability failure count is not zero")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"invalid capability.tsv: {exc}")

    probe_report = batch / "probe-native.tsv"
    if probe_report.is_file():
        try:
            report = _read_metric_tsv(probe_report)
            if int(report.get("schema", "0")) != 1:
                errors.append("probe report schema does not match 1")
            for name in (
                "create",
                "init",
                "activate",
                "start",
                "reset",
                "stop",
                "deactivate",
                "destroy",
            ):
                if int(report.get(name, "0")) < 1:
                    errors.append(f"probe lifecycle metric is missing: {name}")
            formats = int(report.get("float32_seen", "0")) + int(
                report.get("float64_seen", "0")
            )
            if formats < 1:
                errors.append("probe observed no host sample format")
            for name in (
                "self_test_alias_passed",
                "self_test_separate_passed",
                "CC119_trigger_one",
                "CC119_trigger_two",
            ):
                if int(report.get(name, "0")) != 1:
                    errors.append(f"probe metric does not equal one: {name}")
            if int(report.get("trigger_overflow", "-1")) != 0:
                errors.append("probe trigger overflow is not zero")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"invalid probe-native.tsv: {exc}")

    events = batch / "events.tsv"
    if events.is_file():
        try:
            event_lines = events.read_text(encoding="utf-8").splitlines()
            if not event_lines or event_lines[0] != (
                "phase\tindex\tabsolute_sample\toffset\tstatus\tdata1\tdata2"
            ):
                errors.append("events.tsv header is invalid")
            elif len(event_lines) != 14:
                errors.append("events.tsv does not contain thirteen events")
        except (OSError, UnicodeError) as exc:
            errors.append(f"invalid events.tsv: {exc}")

    state = batch / "state.tsv"
    if state.is_file():
        try:
            state_rows = state.read_text(encoding="utf-8").splitlines()
            if not state_rows or state_rows[0] != (
                "index\tname\tminimum\tmaximum\tdefault\tmutated\trestored"
            ):
                errors.append("state.tsv header is invalid")
            elif len(state_rows) != 15:
                errors.append("state.tsv does not contain fourteen persistent rows")
        except (OSError, UnicodeError) as exc:
            errors.append(f"invalid state.tsv: {exc}")

    pressure_path = batch / "pressure.json"
    if pressure_path.is_file():
        try:
            pressure = json.loads(pressure_path.read_text(encoding="utf-8"))
            if set(pressure) != {"before", "after"}:
                errors.append("pressure record does not contain before and after")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            errors.append(f"invalid pressure.json: {exc}")

    metadata_path = batch / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("schema") != 1:
                errors.append("metadata schema does not match 1")
            if metadata.get("sample_rate") != SAMPLE_RATE:
                errors.append("metadata sample rate does not match 48000")
            if metadata.get("block_size") != block_size:
                errors.append("metadata block size does not match batch")
            if metadata.get("guard_returncode") != 0:
                errors.append("metadata guard return code is not zero")
            if metadata.get("inputs") != dict(current_hashes):
                errors.append("metadata input hashes are stale or incomplete")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid metadata.json: {exc}")

    return errors


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def archive_invalid_batch(
    batch: pathlib.Path, timestamp: str | None = None
) -> pathlib.Path:
    if not batch.exists():
        raise ValueError(f"cannot archive missing batch: {batch}")
    stamp = timestamp if timestamp is not None else _timestamp()
    candidate = batch.with_name(f"{batch.name}.invalid-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = batch.with_name(f"{batch.name}.invalid-{stamp}-{counter}")
        counter += 1
    batch.rename(candidate)
    return candidate


def _invalid_destination(block_size: int, timestamp: str | None = None) -> pathlib.Path:
    stamp = timestamp if timestamp is not None else _timestamp()
    candidate = BATCH_ROOT / f"{block_size}.invalid-{stamp}"
    counter = 1
    while candidate.exists():
        candidate = BATCH_ROOT / f"{block_size}.invalid-{stamp}-{counter}"
        counter += 1
    return candidate


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


def recover_staging_partial() -> pathlib.Path | None:
    if not STAGING_RESULTS.is_dir():
        return None
    partial_files = [path for path in STAGING_RESULTS.iterdir() if path.is_file()]
    if not partial_files:
        return None
    block_size = 0
    try:
        for line in PROFILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("linux_audio_bsize="):
                block_size = int(line.split("=", 1)[1])
                break
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        block_size = 0
    phase = STAGING_RESULTS / "phase.log"
    if block_size in BLOCK_SIZES and (BATCH_ROOT / str(block_size)).is_dir():
        try:
            phases = phase.read_text(encoding="utf-8").splitlines()
            if phases and phases[-1] == "suite-finish":
                return None
        except (FileNotFoundError, OSError, UnicodeError):
            pass
    label = str(block_size) if block_size in BLOCK_SIZES else "unknown"
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    destination = BATCH_ROOT / f"{label}.invalid-{stamp}-recovered"
    counter = 1
    while destination.exists():
        destination = BATCH_ROOT / (
            f"{label}.invalid-{stamp}-recovered-{counter}"
        )
        counter += 1
    shutil.copytree(STAGING_RESULTS, destination)
    return destination


def recover_pending_batches() -> list[pathlib.Path]:
    if not BATCH_ROOT.is_dir():
        return []
    recovered: list[pathlib.Path] = []
    for pending in sorted(BATCH_ROOT.glob(".*.pending-*")):
        if not pending.is_dir():
            continue
        fields = pending.name.split(".")
        try:
            block_size = int(fields[1])
        except (IndexError, ValueError):
            block_size = 0
        destination = _invalid_destination(block_size)
        pending.rename(destination)
        recovered.append(destination)
    return recovered


def _copy_staging_results(destination: pathlib.Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in EXPECTED_RESULT_FILES:
        if name in {"pressure.json", "metadata.json"}:
            continue
        source = STAGING_RESULTS / name
        if source.is_file():
            shutil.copy2(source, destination / name)


def run_batch(block_size: int) -> str:
    if block_size not in BLOCK_SIZES:
        raise ValueError(f"unsupported native probe block size: {block_size}")
    write_blank_project()
    hashes = input_hashes()
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    batch = BATCH_ROOT / str(block_size)
    if batch.exists():
        errors = batch_validation_errors(batch, block_size, hashes)
        if not errors:
            return "adopted"
        archived = archive_invalid_batch(batch)
        print(f"preserved invalid native probe batch: {archived}")

    stage(
        ROOT,
        STAGING_ROOT,
        case_set="host",
        sample_rate=SAMPLE_RATE,
        block_size=block_size,
    )
    if not PROBE_SCRIPT.is_file():
        raise RuntimeError(f"staged capability script is missing: {PROBE_SCRIPT}")

    before = require_stable_host()
    command = guard_command(block_size)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    after = current_stability_snapshot()
    post_errors = stability_errors(after, reaper_pids())

    pending = BATCH_ROOT / f".{block_size}.pending-{os.getpid()}-{_timestamp()}"
    _copy_staging_results(pending)
    write_pressure_record(pending / "pressure.json", before, after)
    _atomic_write_json(
        pending / "metadata.json",
        {
            "schema": 1,
            "sample_rate": SAMPLE_RATE,
            "block_size": block_size,
            "inputs": hashes,
            "guard_returncode": completed.returncode,
        },
    )
    validation = batch_validation_errors(pending, block_size, hashes)
    if completed.returncode != 0:
        validation.insert(0, f"guard returned {completed.returncode}")
    validation.extend(post_errors)
    if validation:
        destination = _invalid_destination(block_size)
        pending.rename(destination)
        raise RuntimeError(
            f"native probe block {block_size} failed; preserved {destination}: "
            + "; ".join(validation)
        )
    os.replace(pending, batch)
    return "completed"


def run_matrix() -> dict[int, str]:
    for pending in recover_pending_batches():
        print(f"preserved interrupted pending native probe batch: {pending}")
    recovered = recover_staging_partial()
    if recovered is not None:
        print(f"preserved interrupted native probe staging: {recovered}")
    outcomes: dict[int, str] = {}
    for block_size in BLOCK_SIZES:
        outcomes[block_size] = run_batch(block_size)
    return outcomes


def check_batches() -> list[str]:
    write_blank_project()
    hashes = input_hashes()
    errors: list[str] = []
    for block_size in BLOCK_SIZES:
        batch = BATCH_ROOT / str(block_size)
        for error in batch_validation_errors(batch, block_size, hashes):
            errors.append(f"block {block_size}: {error}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run or verify the serial disposable native CLAP probe"
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--available-mib", type=float)
    parser.add_argument("--load-one", type=float)
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("--memory-pressure", type=float)
    parser.add_argument("--io-pressure", type=float)
    args = parser.parse_args(argv)

    if sum((args.check_only, args.check, args.dry_run)) > 1:
        print("native probe refusal: choose only one check mode", file=sys.stderr)
        return 2

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

    try:
        if args.dry_run:
            write_blank_project()
            input_hashes()
            for block_size, command in zip(
                BLOCK_SIZES, planned_guard_commands(dry_run=True)
            ):
                print(f"native probe block {block_size}: {shlex.join(command)}")
            return 0
        if args.check:
            batch_errors = check_batches()
            if batch_errors:
                print(
                    "native probe check failed: " + "; ".join(batch_errors),
                    file=sys.stderr,
                )
                return 1
            print("native probe check: four immutable batches are complete")
            return 0

        outcomes = run_matrix()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"native probe failure: {exc}", file=sys.stderr)
        return 1

    for block_size, outcome in outcomes.items():
        print(f"native probe block {block_size}: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
