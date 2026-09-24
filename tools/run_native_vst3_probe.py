#!/usr/bin/env python3
"""Run or verify the exact serial disposable native VST3 capability matrix."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from contextlib import contextmanager


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_guarded_reaper import (  # noqa: E402
    VST3_CACHE_FILENAMES,
    UNCONFIRMED_PROCESS_GROUP_EXIT_SENTINEL,
    available_memory_mib,
    maximum_temperature_c,
    native_vst3_prelaunch_scan_containment_errors,
    native_vst3_scan_containment_record,
    native_vst3_scan_containment_unavailable_record,
    preflight_errors,
    confirmed_user_scope_exit_receipt_present,
    unconfirmed_process_group_exit_marker_present,
    validate_native_vst3_environment,
)
from tools.stage_reaper_test_env import stage  # noqa: E402


SAMPLE_RATES = (44100, 48000, 88200, 96000)
BLOCK_SIZES = (32, 64, 128, 256, 512)
MATRIX = tuple(
    (sample_rate, block_size)
    for sample_rate in SAMPLE_RATES
    for block_size in BLOCK_SIZES
)
BUILD_VST3_DIR = (ROOT / "build/vst3/release/VST3").resolve()
PROBE_BUNDLE = (
    BUILD_VST3_DIR / "M3_Polyphonic_Audio_to_MIDI_Probe.vst3"
).resolve()
PROBE_BINARY = (
    PROBE_BUNDLE
    / "Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so"
).resolve()
MODULE_INFO = (PROBE_BUNDLE / "Contents/Resources/moduleinfo.json").resolve()
CAPABILITY_SOURCE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx"
).resolve()
CAPABILITY_SCRIPT = (
    ROOT / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
).resolve()
STAGING_ROOT = (ROOT / "build/reaper-test").resolve()
PROFILE = (STAGING_ROOT / "reaper.ini").resolve()
STAGING_RESULTS = (STAGING_ROOT / "test-results").resolve()
STAGING_ATTEMPT_NAME = ".native-vst3-attempt.json"
ATTEMPT_LOCK_NAME = ".native-vst3-probe-attempt-{}.lock"
OUTER_GUARD_TIMEOUT_SECONDS = 60
EVIDENCE_NAMESPACE = "native-vst3-probe-v2"
COMPLETION_FILE = (STAGING_RESULTS / "phase.log").resolve()
PROBE_SCRIPT = (
    STAGING_ROOT / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
).resolve()
PROJECT_ROOT = (ROOT / "build/native-vst3-probe-projects").resolve()
GUARD = (ROOT / "tools/run_guarded_reaper.py").resolve()
STAGER = (ROOT / "tools/stage_reaper_test_env.py").resolve()
BATCH_ROOT = (ROOT / "build/test-results/native-vst3-probe-v2/batches").resolve()
OBSERVER_DIAGNOSTIC_ROW = (44100, 32)
OBSERVER_DIAGNOSTIC_NAMESPACE = "native-vst3-probe-v3-observer-diagnostic"
OBSERVER_DIAGNOSTIC_STAGING_ROOT = ROOT / "build/reaper-test-observer-diagnostic"
OBSERVER_DIAGNOSTIC_PROFILE = OBSERVER_DIAGNOSTIC_STAGING_ROOT / "reaper.ini"
OBSERVER_DIAGNOSTIC_STAGING_RESULTS = OBSERVER_DIAGNOSTIC_STAGING_ROOT / "test-results"
OBSERVER_DIAGNOSTIC_COMPLETION_FILE = OBSERVER_DIAGNOSTIC_STAGING_RESULTS / "phase.log"
OBSERVER_DIAGNOSTIC_PROBE_SCRIPT = (
    OBSERVER_DIAGNOSTIC_STAGING_ROOT
    / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
)
OBSERVER_DIAGNOSTIC_PROJECT_ROOT = (
    ROOT / "build/native-vst3-probe-v3-observer-diagnostic-projects"
)
OBSERVER_DIAGNOSTIC_BATCH_ROOT = (
    ROOT / "build/test-results/native-vst3-probe-v3-observer-diagnostic/batches"
)
OBSERVER_DIAGNOSTIC_EVIDENCE_ROOT = OBSERVER_DIAGNOSTIC_BATCH_ROOT.parent
MAX_MEMORY_FULL_PRESSURE_AVG10 = 0.25
MAX_IO_FULL_PRESSURE_AVG10 = 2.0
EXPECTED_RESULT_FILES = (
    "phase.log",
    "capability.tsv",
    "events.tsv",
    "state.tsv",
    "probe-vst3.tsv",
    "pressure.json",
    "metadata.json",
)
REQUIRED_INPUT_HASHES = (
    "probe_binary",
    "capability_source",
    "capability_script",
    "guard",
    "stager",
    "probe_bundle",
    "module_info",
    "runner",
)
HASH_INPUTS = {
    "probe_binary": PROBE_BINARY,
    "capability_source": CAPABILITY_SOURCE,
    "capability_script": CAPABILITY_SCRIPT,
    "guard": GUARD,
    "stager": STAGER,
    "module_info": MODULE_INFO,
    "runner": pathlib.Path(__file__).resolve(),
}
EVENTS_HEADER = (
    "phase\tindex\tabsolute_sample\toffset\ttype\tchannel\tpitch\tvelocity\t"
    "note_id"
)
STATE_HEADER = "index\tstable_id\tname\tdefault\tmutated\trestored"


@contextmanager
def observer_diagnostic_scope():
    names = (
        "STAGING_ROOT",
        "PROFILE",
        "STAGING_RESULTS",
        "COMPLETION_FILE",
        "PROBE_SCRIPT",
        "PROJECT_ROOT",
        "BATCH_ROOT",
        "EVIDENCE_NAMESPACE",
    )
    original = {name: globals()[name] for name in names}
    globals().update(
        {
            "STAGING_ROOT": OBSERVER_DIAGNOSTIC_STAGING_ROOT,
            "PROFILE": OBSERVER_DIAGNOSTIC_PROFILE,
            "STAGING_RESULTS": OBSERVER_DIAGNOSTIC_STAGING_RESULTS,
            "COMPLETION_FILE": OBSERVER_DIAGNOSTIC_COMPLETION_FILE,
            "PROBE_SCRIPT": OBSERVER_DIAGNOSTIC_PROBE_SCRIPT,
            "PROJECT_ROOT": OBSERVER_DIAGNOSTIC_PROJECT_ROOT,
            "BATCH_ROOT": OBSERVER_DIAGNOSTIC_BATCH_ROOT,
            "EVIDENCE_NAMESPACE": OBSERVER_DIAGNOSTIC_NAMESPACE,
        }
    )
    try:
        yield
    finally:
        globals().update(original)


def _path_has_symlink_component(path: pathlib.Path) -> bool:
    candidate = path
    while True:
        if candidate.is_symlink():
            return True
        if candidate == candidate.parent:
            return False
        candidate = candidate.parent


def observer_diagnostic_freshness_errors() -> list[str]:
    errors: list[str] = []
    for root in (
        OBSERVER_DIAGNOSTIC_STAGING_ROOT,
        OBSERVER_DIAGNOSTIC_PROJECT_ROOT,
        OBSERVER_DIAGNOSTIC_EVIDENCE_ROOT,
    ):
        if _path_has_symlink_component(root):
            errors.append(f"observer diagnostic root is symlinked: {root}")
        elif root.exists():
            errors.append(f"observer diagnostic root already exists: {root}")
    return errors


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


def reaper_pids(proc_root: pathlib.Path = pathlib.Path("/proc")) -> set[int] | None:
    pids: set[int] = set()
    try:
        processes = tuple(proc_root.iterdir())
    except OSError:
        return None
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            executable = (process / "exe").resolve(strict=True)
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            return None
        if executable.name == "reaper":
            pids.add(int(process.name))
    return pids


def stability_errors(
    snapshot: StabilitySnapshot,
    existing_reaper_pids: set[int] | None,
) -> list[str]:
    errors = preflight_errors(
        snapshot.available_mib,
        snapshot.load_one,
        snapshot.temperature_c,
    )
    if existing_reaper_pids is None:
        errors.insert(0, "REAPER process census is unavailable")
    elif existing_reaper_pids:
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


def require_stable_host(
    snapshot: StabilitySnapshot | None = None,
) -> StabilitySnapshot:
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


def project_path(sample_rate: int, block_size: int) -> pathlib.Path:
    if (sample_rate, block_size) not in MATRIX:
        raise ValueError(
            f"unsupported native VST3 probe row: {sample_rate}/{block_size}"
        )
    return (
        PROJECT_ROOT / f"M3-Native-VST3-{sample_rate}-{block_size}.RPP"
    ).resolve()


def write_blank_project(path: pathlib.Path) -> None:
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


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def bundle_input_errors(
    bundle: pathlib.Path,
    binary: pathlib.Path,
    module_info: pathlib.Path,
) -> list[str]:
    if bundle.is_symlink() or not bundle.is_dir():
        return [f"probe bundle is missing or a symlink: {bundle}"]
    try:
        expected_files = {
            binary.relative_to(bundle).as_posix(),
            module_info.relative_to(bundle).as_posix(),
        }
    except ValueError:
        return ["probe binary or module-info escapes the bundle"]
    errors: list[str] = []
    actual_files: set[str] = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            errors.append(f"probe bundle contains a symlink: {path}")
        elif path.is_file():
            if not _inside(path, bundle):
                errors.append(f"probe bundle member escapes: {path}")
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != expected_files:
        errors.append("probe bundle file set is not exact")
    for label, path in (("binary", binary), ("module-info", module_info)):
        if not path.is_file() or path.is_symlink() or not _inside(path, bundle):
            errors.append(f"probe {label} is missing, a symlink, or escapes")
    return errors


def bundle_digest(bundle: pathlib.Path) -> str:
    rows: list[str] = []
    for path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        if path.is_symlink():
            raise ValueError(f"probe bundle contains a symlink: {path}")
        rows.append(f"{sha256(path)}  {path.relative_to(bundle).as_posix()}\n")
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()


def input_hashes() -> dict[str, str]:
    missing = [name for name, path in HASH_INPUTS.items() if not path.is_file()]
    bundle_errors = bundle_input_errors(PROBE_BUNDLE, PROBE_BINARY, MODULE_INFO)
    if missing:
        raise ValueError("missing native VST3 probe inputs: " + ", ".join(missing))
    if bundle_errors:
        raise ValueError("invalid native VST3 probe bundle: " + "; ".join(bundle_errors))
    hashes = {name: sha256(path) for name, path in sorted(HASH_INPUTS.items())}
    hashes["probe_bundle"] = bundle_digest(PROBE_BUNDLE)
    if set(hashes) != set(REQUIRED_INPUT_HASHES):
        raise ValueError("native VST3 probe input hash contract is incomplete")
    return hashes


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


def _metric_result_errors(
    path: pathlib.Path,
    sample_rate: int,
    block_size: int,
    *,
    require_status: bool,
) -> list[str]:
    errors: list[str] = []
    try:
        values = _read_metric_tsv(path)
        if require_status and values.get("status") != "pass":
            errors.append(f"{path.name} status is not pass")
        if not require_status and int(values.get("schema", "0")) != 1:
            errors.append(f"{path.name} schema does not match 1")
        if int(values.get("sample_rate", "-1")) != sample_rate:
            errors.append(f"{path.name} sample rate does not match row")
        if int(values.get("block_size", "-1")) != block_size:
            errors.append(f"{path.name} block size does not match row")
        if int(values.get("failure_count", "-1")) != 0:
            errors.append(f"{path.name} failure count is not zero")
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"invalid {path.name}: {exc}")
    return errors


def _trusted_vst3_scan_containment_errors(containment: object) -> list[str]:
    if containment is None:
        return ["metadata VST3 scan containment is missing"]
    if not isinstance(containment, dict) or set(containment) != {
        "errors",
        "profile_sha256",
        "cache_sha256",
    }:
        return ["metadata VST3 scan containment fields are invalid"]

    errors: list[str] = []
    if containment["errors"] != []:
        errors.append("metadata VST3 scan containment errors are not empty")
    profile_digest = containment["profile_sha256"]
    if not (
        isinstance(profile_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", profile_digest)
    ):
        errors.append("metadata VST3 scan containment profile digest is invalid")
    cache_digests = containment["cache_sha256"]
    expected_cache_names = set(VST3_CACHE_FILENAMES)
    if not isinstance(cache_digests, dict) or set(cache_digests) != expected_cache_names:
        errors.append("metadata VST3 scan containment cache keys are invalid")
        return errors
    if all(digest is None for digest in cache_digests.values()):
        errors.append("metadata VST3 scan containment has no cache digest")
    for digest in cache_digests.values():
        if digest is not None and not (
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            errors.append("metadata VST3 scan containment cache digest is invalid")
            break
    return errors


def batch_validation_errors(
    batch: pathlib.Path,
    sample_rate: int,
    block_size: int,
    current_hashes: Mapping[str, str],
) -> list[str]:
    if (sample_rate, block_size) not in MATRIX:
        return [f"unsupported native VST3 probe row: {sample_rate}/{block_size}"]
    if not batch.is_dir() or batch.is_symlink():
        return [f"batch directory is missing or symlinked: {batch}"]

    errors: list[str] = []
    if set(current_hashes) != set(REQUIRED_INPUT_HASHES):
        errors.append("current input hashes are stale or incomplete")
    actual_files: set[str] = set()
    for path in batch.iterdir():
        if path.is_symlink():
            errors.append(f"batch result is a symlink: {path.name}")
        elif path.is_file():
            actual_files.add(path.name)
    expected_files = set(EXPECTED_RESULT_FILES)
    for name in sorted(expected_files - actual_files):
        errors.append(f"missing expected file: {name}")
    for name in sorted(actual_files - expected_files):
        errors.append(f"unexpected result file: {name}")

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
        errors.extend(
            _metric_result_errors(
                capability,
                sample_rate,
                block_size,
                require_status=True,
            )
        )
    probe_report = batch / "probe-vst3.tsv"
    if probe_report.is_file():
        errors.extend(
            _metric_result_errors(
                probe_report,
                sample_rate,
                block_size,
                require_status=False,
            )
        )

    for name, header in (("events.tsv", EVENTS_HEADER), ("state.tsv", STATE_HEADER)):
        path = batch / name
        if not path.is_file():
            continue
        try:
            rows = path.read_text(encoding="utf-8").splitlines()
            if not rows or rows[0] != header:
                errors.append(f"{name} header is invalid")
            elif len(rows) < 2:
                errors.append(f"{name} has no evidence rows")
        except (OSError, UnicodeError) as exc:
            errors.append(f"invalid {name}: {exc}")

    pressure_path = batch / "pressure.json"
    if pressure_path.is_file():
        try:
            pressure = json.loads(pressure_path.read_text(encoding="utf-8"))
            if set(pressure) != {"before", "after"} or not all(
                isinstance(pressure[name], dict) for name in ("before", "after")
            ):
                errors.append("pressure record does not contain before and after")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            errors.append(f"invalid pressure.json: {exc}")

    metadata_path = batch / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("schema") != 1:
                errors.append("metadata schema does not match 1")
            if metadata.get("sample_rate") != sample_rate:
                errors.append("metadata sample rate does not match row")
            if metadata.get("block_size") != block_size:
                errors.append("metadata block size does not match row")
            if metadata.get("guard_returncode") != 0:
                errors.append("metadata guard return code is not zero")
            if metadata.get("classification") != "pass":
                errors.append("metadata classification is not pass")
            if metadata.get("inputs") != dict(current_hashes):
                errors.append("metadata input hashes are stale or incomplete")
            if _trusted_vst3_scan_containment_errors(
                metadata.get("vst3_scan_containment")
            ):
                errors.append("metadata VST3 scan containment is invalid")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid metadata.json: {exc}")
    return errors


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def row_label(sample_rate: int, block_size: int) -> str:
    return f"{sample_rate}-{block_size}"


def archive_invalid_batch(
    batch: pathlib.Path,
    timestamp: str | None = None,
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


def _invalid_destination(
    sample_rate: int,
    block_size: int,
    timestamp: str | None = None,
) -> pathlib.Path:
    stamp = timestamp if timestamp is not None else _timestamp()
    candidate = BATCH_ROOT / (
        f"{row_label(sample_rate, block_size)}.invalid-{stamp}"
    )
    counter = 1
    while candidate.exists():
        candidate = BATCH_ROOT / (
            f"{row_label(sample_rate, block_size)}.invalid-{stamp}-{counter}"
        )
        counter += 1
    return candidate


def prior_invalid_attempts(
    sample_rate: int,
    block_size: int,
) -> list[pathlib.Path]:
    if not BATCH_ROOT.is_dir():
        return []
    label = row_label(sample_rate, block_size)
    attempts = sorted(BATCH_ROOT.glob(f"{label}.invalid-*"))
    return [attempt for attempt in attempts if _blocks_current_namespace(attempt)]


def _blocks_current_namespace(attempt: pathlib.Path) -> bool:
    if "-recovered" not in attempt.name:
        return True
    marker = attempt / STAGING_ATTEMPT_NAME
    if not marker.is_file() or marker.is_symlink():
        return True
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return True
    if not isinstance(document, dict):
        return True
    return document.get("evidence_namespace") == EVIDENCE_NAMESPACE


def guard_command(
    sample_rate: int,
    block_size: int,
    dry_run: bool = False,
) -> list[str]:
    project = project_path(sample_rate, block_size)
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
            "--vst3-path",
            str(BUILD_VST3_DIR),
            "--completion-file",
            str(COMPLETION_FILE),
            "--timeout-seconds",
            "45",
            "--",
            str(project),
            str(PROBE_SCRIPT),
        ]
    )
    return command


def planned_guard_commands(dry_run: bool = False) -> list[list[str]]:
    return [
        guard_command(sample_rate, block_size, dry_run=dry_run)
        for sample_rate, block_size in MATRIX
    ]


def observer_diagnostic_guard_command(dry_run: bool = False) -> list[str]:
    with observer_diagnostic_scope():
        return guard_command(*OBSERVER_DIAGNOSTIC_ROW, dry_run=dry_run)


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


def _staging_attempt_row() -> tuple[int, int] | None:
    marker = STAGING_RESULTS / STAGING_ATTEMPT_NAME
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
        if document.get("schema") != 1:
            return (0, 0)
        row = (int(document["sample_rate"]), int(document["block_size"]))
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return (0, 0)
    return row if row in MATRIX else (0, 0)


def recover_staging_partial() -> pathlib.Path | None:
    if not STAGING_RESULTS.is_dir() or STAGING_RESULTS.is_symlink():
        return None
    marker = STAGING_RESULTS / STAGING_ATTEMPT_NAME
    if not marker.is_file() or marker.is_symlink():
        return None
    partial_files = [path for path in STAGING_RESULTS.iterdir() if path.is_file()]
    if not partial_files:
        return None
    row = _staging_attempt_row()
    phase = STAGING_RESULTS / "phase.log"
    if row is not None and (BATCH_ROOT / row_label(*row)).is_dir():
        try:
            phases = phase.read_text(encoding="utf-8").splitlines()
            if phases and phases[-1] == "suite-finish":
                return None
        except (FileNotFoundError, OSError, UnicodeError):
            pass
    sample_rate, block_size = row if row is not None else (0, 0)
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    destination = _invalid_destination(sample_rate, block_size)
    destination = destination.with_name(destination.name + "-recovered")
    counter = 1
    base = destination
    while destination.exists():
        destination = base.with_name(f"{base.name}-{counter}")
        counter += 1
    STAGING_RESULTS.rename(destination)
    return destination


def recover_pending_batches() -> list[pathlib.Path]:
    if not BATCH_ROOT.is_dir():
        return []
    recovered: list[pathlib.Path] = []
    pattern = re.compile(r"^\.(\d+)-(\d+)\.pending-")
    for pending in sorted(BATCH_ROOT.glob(".*.pending-*")):
        if not pending.is_dir() or pending.is_symlink():
            continue
        match = pattern.match(pending.name)
        if match is None:
            sample_rate, block_size = 0, 0
        else:
            sample_rate, block_size = (int(value) for value in match.groups())
        destination = _invalid_destination(sample_rate, block_size)
        pending.rename(destination)
        recovered.append(destination)
    return recovered


def _copy_staging_results(destination: pathlib.Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in EXPECTED_RESULT_FILES:
        if name in {"pressure.json", "metadata.json"}:
            continue
        source = STAGING_RESULTS / name
        if source.is_file() and not source.is_symlink():
            shutil.copy2(source, destination / name)


def attempt_lock_path() -> pathlib.Path:
    scope = f"{STAGING_ROOT.resolve()}\0{PROFILE.resolve()}".encode("utf-8")
    return STAGING_ROOT.parent / ATTEMPT_LOCK_NAME.format(
        hashlib.sha256(scope).hexdigest()[:16]
    )


def _attempt_lock_content() -> str:
    return json.dumps(
        {
            "schema": 1,
            "staging_root": str(STAGING_ROOT.resolve()),
            "profile": str(PROFILE.resolve()),
        },
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def acquire_attempt_lock() -> tuple[pathlib.Path, int]:
    lock = attempt_lock_path()
    try:
        descriptor = os.open(
            lock,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
    except FileExistsError as exc:
        raise RuntimeError(
            "native VST3 attempt lock already exists; explicit recovery is "
            f"required before staging or launch: {lock}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "native VST3 attempt lock could not be acquired; explicit "
            f"recovery is required before staging or launch: {lock}: {exc}"
        ) from exc
    try:
        os.write(descriptor, _attempt_lock_content().encode("utf-8"))
    except OSError as exc:
        os.close(descriptor)
        raise RuntimeError(
            "native VST3 attempt lock could not be sealed; explicit recovery "
            f"is required before staging or launch: {lock}: {exc}"
        ) from exc
    return lock, descriptor


def release_attempt_lock(lock: pathlib.Path, descriptor: int) -> None:
    try:
        original = os.fstat(descriptor)
        os.close(descriptor)
        reader = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            status = os.fstat(reader)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
                or (status.st_dev, status.st_ino)
                != (original.st_dev, original.st_ino)
            ):
                raise OSError("attempt lock is not a unique regular file")
            expected = _attempt_lock_content().encode("utf-8")
            content = os.read(reader, len(expected) + 1)
        finally:
            os.close(reader)
        if content != expected:
            raise OSError("attempt lock content changed")
        lock.unlink()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(
            "native VST3 attempt completed but its lock was retained; "
            f"explicit recovery is required: {lock}: {exc}"
        ) from exc


def _with_attempt_lock(operation: Callable[[], object]) -> object:
    lock, descriptor = acquire_attempt_lock()
    try:
        result = operation()
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    release_attempt_lock(lock, descriptor)
    return result


def run_row(sample_rate: int, block_size: int) -> str:
    if (sample_rate, block_size) not in MATRIX:
        raise ValueError(
            f"unsupported native VST3 probe row: {sample_rate}/{block_size}"
        )
    result = _with_attempt_lock(
        lambda: _run_row_locked(sample_rate, block_size)
    )
    assert isinstance(result, str)
    return result


def _run_row_locked(sample_rate: int, block_size: int) -> str:
    hashes = input_hashes()
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    batch = BATCH_ROOT / row_label(sample_rate, block_size)
    if batch.exists():
        errors = batch_validation_errors(
            batch, sample_rate, block_size, hashes
        )
        if errors:
            archived = archive_invalid_batch(batch)
            raise RuntimeError(
                "completed native VST3 row changed; no retry; preserved "
                f"{archived}: " + "; ".join(errors)
            )
        return "adopted"

    # Staging removes this directory recursively, so refusal must precede it.
    if unconfirmed_process_group_exit_marker_present(COMPLETION_FILE):
        before = current_stability_snapshot()
        containment = native_vst3_scan_containment_unavailable_record(
            PROFILE,
            [
                "post-exit VST3 scan containment unavailable: "
                "guarded process-group exit was not confirmed"
            ],
        )
        pending = BATCH_ROOT / (
            f".{row_label(sample_rate, block_size)}.pending-"
            f"{os.getpid()}-{_timestamp()}"
        )
        _copy_staging_results(pending)
        write_pressure_record(pending / "pressure.json", before, before)
        _atomic_write_json(
            pending / "metadata.json",
            {
                "schema": 1,
                "evidence_namespace": EVIDENCE_NAMESPACE,
                "sample_rate": sample_rate,
                "block_size": block_size,
                "inputs": hashes,
                "guard_returncode": 2,
                "classification": "infrastructure-invalid",
                "vst3_scan_containment": containment,
            },
        )
        validation = batch_validation_errors(pending, sample_rate, block_size, hashes)
        validation.insert(0, "guard returned 2")
        validation.extend(
            f"VST3 scan containment: {error}"
            for error in containment["errors"]
        )
        metadata = json.loads((pending / "metadata.json").read_text(encoding="utf-8"))
        metadata["errors"] = validation
        _atomic_write_json(pending / "metadata.json", metadata)
        destination = _invalid_destination(sample_rate, block_size)
        pending.rename(destination)
        raise RuntimeError(
            f"native VST3 row {sample_rate}/{block_size} failed; no retry; "
            f"preserved {destination}: " + "; ".join(validation)
        )

    project = project_path(sample_rate, block_size)
    write_blank_project(project)
    stage(
        ROOT,
        STAGING_ROOT,
        case_set="host",
        sample_rate=sample_rate,
        block_size=block_size,
        vst3_path=BUILD_VST3_DIR,
    )
    if not PROBE_SCRIPT.is_file():
        raise RuntimeError(f"staged VST3 capability script is missing: {PROBE_SCRIPT}")
    validate_native_vst3_environment(BUILD_VST3_DIR, PROFILE)

    _atomic_write_json(
        STAGING_RESULTS / STAGING_ATTEMPT_NAME,
        {
            "schema": 1,
            "evidence_namespace": EVIDENCE_NAMESPACE,
            "sample_rate": sample_rate,
            "block_size": block_size,
            "inputs": hashes,
        },
    )
    try:
        before = require_stable_host()
    except RuntimeError as exc:
        destination = _invalid_destination(sample_rate, block_size)
        STAGING_RESULTS.rename(destination)
        raise RuntimeError(
            f"native VST3 row {sample_rate}/{block_size} preflight aborted; "
            f"no retry; preserved {destination}: {exc}"
        ) from exc
    prelaunch_containment_errors = native_vst3_prelaunch_scan_containment_errors(
        PROFILE
    )
    launch_error = ""
    guarded_unconfirmed_teardown = False
    guarded_timeout = False
    guard_invoked = False
    scope_exit_confirmed = False
    if prelaunch_containment_errors:
        returncode = 2
    else:
        command = guard_command(sample_rate, block_size)
        try:
            guard_invoked = True
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
                timeout=OUTER_GUARD_TIMEOUT_SECONDS,
            )
            returncode = completed.returncode
            guarded_stdout = completed.stdout or ""
            guarded_stderr = completed.stderr or ""
            if guarded_stdout:
                sys.stdout.write(guarded_stdout)
            if guarded_stderr:
                sys.stderr.write(guarded_stderr)
            guarded_unconfirmed_teardown = (
                UNCONFIRMED_PROCESS_GROUP_EXIT_SENTINEL in guarded_stdout
                or UNCONFIRMED_PROCESS_GROUP_EXIT_SENTINEL in guarded_stderr
            )
            scope_exit_confirmed = (
                returncode == 0
                and confirmed_user_scope_exit_receipt_present(COMPLETION_FILE)
            )
        except subprocess.TimeoutExpired:
            returncode = 124
            guarded_timeout = True
            guarded_unconfirmed_teardown = True
            launch_error = (
                "guarded subprocess exceeded outer "
                f"{OUTER_GUARD_TIMEOUT_SECONDS}-second limit"
            )
        except OSError as exc:
            returncode = -1
            launch_error = str(exc)
    after = current_stability_snapshot()
    post_reaper_pids = reaper_pids()
    post_errors = stability_errors(after, post_reaper_pids)
    unconfirmed_teardown = (
        guarded_unconfirmed_teardown
        or unconfirmed_process_group_exit_marker_present(COMPLETION_FILE)
    )
    unavailable_errors: list[str] = []
    if prelaunch_containment_errors:
        unavailable_errors.extend(prelaunch_containment_errors)
    if guard_invoked and returncode != 0:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "guarded process did not exit cleanly"
        )
    if guarded_timeout:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "guarded subprocess exceeded its outer time limit"
        )
    if not guard_invoked:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "guarded process was not started"
        )
    if guard_invoked and not scope_exit_confirmed:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "guarded user scope exit receipt is missing or invalid"
        )
    if unconfirmed_teardown:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "guarded process-group exit was not confirmed"
        )
    if post_reaper_pids is None:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "REAPER process census is unavailable"
        )
    elif post_reaper_pids:
        unavailable_errors.append(
            "post-exit VST3 scan containment unavailable: "
            "REAPER process still detected: "
            + ",".join(str(pid) for pid in sorted(post_reaper_pids))
        )
    if unavailable_errors:
        scan_containment = native_vst3_scan_containment_unavailable_record(
            PROFILE,
            unavailable_errors,
        )
    else:
        scan_containment = native_vst3_scan_containment_record(
            PROFILE, BUILD_VST3_DIR
        )
    post_errors.extend(
        f"VST3 scan containment: {error}"
        for error in scan_containment["errors"]
    )

    pending = BATCH_ROOT / (
        f".{row_label(sample_rate, block_size)}.pending-"
        f"{os.getpid()}-{_timestamp()}"
    )
    _copy_staging_results(pending)
    write_pressure_record(pending / "pressure.json", before, after)
    metadata: dict[str, object] = {
        "schema": 1,
        "evidence_namespace": EVIDENCE_NAMESPACE,
        "sample_rate": sample_rate,
        "block_size": block_size,
        "inputs": hashes,
        "guard_returncode": returncode,
        "classification": "pass" if returncode == 0 else "infrastructure-invalid",
        "vst3_scan_containment": scan_containment,
    }
    if launch_error:
        metadata["launch_error"] = launch_error
    _atomic_write_json(pending / "metadata.json", metadata)

    validation = batch_validation_errors(
        pending, sample_rate, block_size, hashes
    )
    if returncode != 0:
        validation.insert(0, f"guard returned {returncode}")
    validation.extend(post_errors)
    if validation:
        if returncode == 0 and not post_errors:
            metadata["classification"] = "fail"
        else:
            metadata["classification"] = "infrastructure-invalid"
        metadata["errors"] = validation
        _atomic_write_json(pending / "metadata.json", metadata)
        destination = _invalid_destination(sample_rate, block_size)
        pending.rename(destination)
        raise RuntimeError(
            f"native VST3 row {sample_rate}/{block_size} failed; no retry; "
            f"preserved {destination}: " + "; ".join(validation)
        )
    os.replace(pending, batch)
    return "completed"


def run_matrix() -> dict[tuple[int, int], str]:
    result = _with_attempt_lock(_run_matrix_locked)
    assert isinstance(result, dict)
    return result


def _run_matrix_locked() -> dict[tuple[int, int], str]:
    recovered_pending = recover_pending_batches()
    recovered_staging = recover_staging_partial()
    recovered = [str(path) for path in recovered_pending]
    if (
        recovered_staging is not None
        and _blocks_current_namespace(recovered_staging)
    ):
        recovered.append(str(recovered_staging))
    if recovered:
        raise RuntimeError(
            "interrupted native VST3 attempt preserved; no retry: "
            + ", ".join(recovered)
        )

    outcomes: dict[tuple[int, int], str] = {}
    for sample_rate, block_size in MATRIX:
        invalid = prior_invalid_attempts(sample_rate, block_size)
        if invalid:
            raise RuntimeError(
                f"no retry allowed after prior invalid native VST3 row "
                f"{sample_rate}/{block_size}: "
                + ", ".join(str(path) for path in invalid)
            )
        outcomes[(sample_rate, block_size)] = _run_row_locked(
            sample_rate, block_size
        )
    return outcomes


def run_observer_diagnostic() -> str:
    freshness_errors = observer_diagnostic_freshness_errors()
    if freshness_errors:
        raise RuntimeError(
            "fresh observer diagnostic required; no retry: "
            + "; ".join(freshness_errors)
        )
    with observer_diagnostic_scope():
        sample_rate, block_size = OBSERVER_DIAGNOSTIC_ROW
        return run_row(sample_rate, block_size)


def check_batches() -> list[str]:
    hashes = input_hashes()
    errors: list[str] = []
    if BATCH_ROOT.is_dir():
        pending = sorted(BATCH_ROOT.glob(".*.pending-*"))
        if pending:
            errors.append("interrupted pending rows exist")
    for sample_rate, block_size in MATRIX:
        invalid = prior_invalid_attempts(sample_rate, block_size)
        if invalid:
            errors.append(
                f"row {sample_rate}/{block_size}: invalid attempt is sealed"
            )
        batch = BATCH_ROOT / row_label(sample_rate, block_size)
        for error in batch_validation_errors(
            batch, sample_rate, block_size, hashes
        ):
            errors.append(f"row {sample_rate}/{block_size}: {error}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run or verify the serial disposable native VST3 probe"
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--observer-diagnostic-once", action="store_true")
    parser.add_argument("--available-mib", type=float)
    parser.add_argument("--load-one", type=float)
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("--memory-pressure", type=float)
    parser.add_argument("--io-pressure", type=float)
    args = parser.parse_args(argv)

    if sum((args.check_only, args.check, args.dry_run)) > 1:
        print(
            "native VST3 probe refusal: choose only one check mode",
            file=sys.stderr,
        )
        return 2
    if args.observer_diagnostic_once and (args.check_only or args.check):
        print(
            "native VST3 probe refusal: observer diagnostic only supports "
            "one guarded row or its dry run",
            file=sys.stderr,
        )
        return 2

    snapshot = _snapshot_with_overrides(current_stability_snapshot(), args)
    errors = stability_errors(snapshot, reaper_pids())
    if errors:
        print(
            "native VST3 probe refusal: " + "; ".join(errors),
            file=sys.stderr,
        )
        return 2
    print(
        "native VST3 probe preflight: ok "
        f"(available={snapshot.available_mib:.0f} MiB, "
        f"load1={snapshot.load_one:.2f}, "
        f"memory-full={snapshot.memory_full_pressure_avg10:.2f}, "
        f"io-full={snapshot.io_full_pressure_avg10:.2f})"
    )
    if args.check_only:
        return 0

    try:
        if args.dry_run:
            if args.observer_diagnostic_once:
                command = observer_diagnostic_guard_command(dry_run=True)
                print(
                    "native VST3 observer diagnostic 44100/32: "
                    f"{shlex.join(command)}"
                )
                return 0
            for (sample_rate, block_size), command in zip(
                MATRIX, planned_guard_commands(dry_run=True)
            ):
                print(
                    f"native VST3 probe {sample_rate}/{block_size}: "
                    f"{shlex.join(command)}"
                )
            return 0
        if args.check:
            batch_errors = check_batches()
            if batch_errors:
                print(
                    "native VST3 probe check failed: "
                    + "; ".join(batch_errors),
                    file=sys.stderr,
                )
                return 1
            print("native VST3 probe check: twenty immutable rows are complete")
            return 0
        if args.observer_diagnostic_once:
            outcome = run_observer_diagnostic()
            print(f"native VST3 observer diagnostic 44100/32: {outcome}")
            return 0
        outcomes = run_matrix()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"native VST3 probe failure: {exc}", file=sys.stderr)
        return 1

    for (sample_rate, block_size), outcome in outcomes.items():
        print(f"native VST3 probe {sample_rate}/{block_size}: {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
