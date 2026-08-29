#!/usr/bin/env python3
"""Run the deterministic synthetic matrix in small, resumable REAPER batches."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_guarded_reaper import (  # noqa: E402
    available_memory_mib,
    maximum_temperature_c,
    preflight_errors,
)
from tools.stage_reaper_test_env import (  # noqa: E402
    ALLOWED_BLOCK_SIZES,
    ALLOWED_SAMPLE_RATES,
    stage,
)
from tools.summarize_results import main as summarize_main  # noqa: E402


SCHEMA_VERSION = 1
MAX_BATCH_SIZE = 8
DEFAULT_BATCH_SIZE = 8
DEFAULT_TIMEOUT_SECONDS = 90
REAPER = pathlib.Path("/home/ajuntanaga/opt/REAPER/reaper")
STAGING_ROOT = ROOT / "build" / "reaper-test"
RESULTS_ROOT = ROOT / "build" / "test-results"
DEFAULT_OUTPUT = RESULTS_ROOT / "synthetic-matrix"
MANIFEST = ROOT / "tests" / "fixtures" / "synthetic_cases.tsv"
PROJECT = ROOT / "build" / "host-integration.RPP"
TEST_SCRIPT = (
    STAGING_ROOT
    / "Scripts"
    / "ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua"
)
GUARD = ROOT / "tools" / "run_guarded_reaper.py"
REQUIRED_BATCH_FILES = (
    "cases.tsv",
    "events.tsv",
    "summary.tsv",
    "safety.tsv",
    "phase.log",
    "guard.log",
    "batch.json",
)
MAX_MEMORY_FULL_PRESSURE_AVG10 = 0.25
MAX_IO_FULL_PRESSURE_AVG10 = 2.0


@dataclasses.dataclass(frozen=True)
class BatchValidation:
    summary_rows: int
    event_rows: int


@dataclasses.dataclass(frozen=True)
class Batch:
    key: str
    sample_rate: int
    block_size: int
    offset: int
    limit: int
    case_ids: tuple[int, ...]


class StaleEvidenceError(ValueError):
    """Raised when saved evidence belongs to a different source payload."""


def _atomic_write_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
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


def _atomic_write_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_fingerprint(root: pathlib.Path) -> str:
    """Hash every staged production/test payload plus the disposable project."""
    root = root.resolve()
    files: list[pathlib.Path] = []
    for relative in (pathlib.Path("Effects"), pathlib.Path("Scripts")):
        directory = root / relative
        if not directory.is_dir():
            raise ValueError(f"missing runtime payload directory: {directory}")
        files.extend(path for path in directory.rglob("*") if path.is_file())
    project = root / "build" / "host-integration.RPP"
    if not project.is_file():
        raise ValueError(f"missing disposable REAPER project: {project}")
    files.append(project)

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def group_case_rows(
    rows: Iterable[Mapping[str, str]],
) -> dict[tuple[int, int], list[Mapping[str, str]]]:
    grouped: dict[tuple[int, int], list[Mapping[str, str]]] = {}
    for row in rows:
        key = (int(row["sample_rate"]), int(row["block_size"]))
        grouped.setdefault(key, []).append(row)
    return grouped


def batch_ranges(total: int, batch_size: int) -> list[tuple[int, int]]:
    if total < 0:
        raise ValueError("total case count must be nonnegative")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch size must be between 1 and {MAX_BATCH_SIZE}"
        )
    return [
        (offset, min(batch_size, total - offset))
        for offset in range(0, total, batch_size)
    ]


def _read_tsv(path: pathlib.Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise ValueError(f"missing batch result: {path.name}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"batch result has no header: {path.name}")
        return list(reader.fieldnames), list(reader)


def validate_batch_results(
    results: pathlib.Path,
    expected_case_ids: Sequence[int],
    sample_rate: int,
    block_size: int,
) -> BatchValidation:
    results = results.resolve()
    phase = results / "phase.log"
    if not phase.is_file():
        raise ValueError("missing batch result: phase.log")
    phase_lines = phase.read_text(encoding="utf-8").splitlines()
    if not phase_lines or phase_lines[-1] != "suite-finish":
        raise ValueError("phase.log does not end in suite-finish")

    summary_header, summary = _read_tsv(results / "summary.tsv")
    required_summary = {"case_id", "actual_rate", "actual_block"}
    if not required_summary.issubset(summary_header):
        raise ValueError("summary.tsv is missing required columns")
    observed_case_ids = tuple(int(row["case_id"]) for row in summary)
    wanted_case_ids = tuple(int(case_id) for case_id in expected_case_ids)
    if observed_case_ids != wanted_case_ids:
        raise ValueError(
            "summary case IDs do not exactly match the staged batch: "
            f"expected {wanted_case_ids}, observed {observed_case_ids}"
        )
    for row in summary:
        if int(row["actual_rate"]) != sample_rate:
            raise ValueError("summary contains an unexpected actual sample rate")
        if int(row["actual_block"]) != block_size:
            raise ValueError("summary contains an unexpected actual block size")

    event_header, events = _read_tsv(results / "events.tsv")
    required_events = {
        "case_id",
        "absolute_sample",
        "status",
        "note",
        "velocity",
    }
    if not required_events.issubset(event_header):
        raise ValueError("events.tsv is missing required columns")
    unexpected_event_ids = {
        int(row["case_id"]) for row in events
    } - set(wanted_case_ids)
    if unexpected_event_ids:
        raise ValueError(
            "events.tsv contains unexpected case IDs: "
            f"{sorted(unexpected_event_ids)}"
        )

    safety_header, _ = _read_tsv(results / "safety.tsv")
    if not {"trial", "status", "reason"}.issubset(safety_header):
        raise ValueError("safety.tsv is missing required columns")
    return BatchValidation(
        summary_rows=len(summary),
        event_rows=len(events),
    )


def merge_batch_tsv(
    batch_directories: Iterable[pathlib.Path],
    filename: str,
    output: pathlib.Path,
) -> int:
    header: str | None = None
    data_lines: list[str] = []
    for directory in batch_directories:
        path = pathlib.Path(directory) / filename
        if not path.is_file():
            raise ValueError(f"missing batch result: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError(f"empty batch result: {path}")
        if header is None:
            header = lines[0]
        elif lines[0] != header:
            raise ValueError(f"inconsistent {filename} header: {path}")
        data_lines.extend(lines[1:])
    if header is None:
        raise ValueError(f"cannot merge {filename} without any batches")
    _atomic_write_text(output, "\n".join([header, *data_lines]) + "\n")
    return len(data_lines)


def _load_manifest(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise ValueError(f"synthetic manifest has no cases: {path}")
    return rows


def _batches(rows: Sequence[Mapping[str, str]], batch_size: int) -> list[Batch]:
    batches: list[Batch] = []
    for (sample_rate, block_size), group in group_case_rows(rows).items():
        for offset, limit in batch_ranges(len(group), batch_size):
            case_ids = tuple(
                int(row["case_id"]) for row in group[offset : offset + limit]
            )
            batches.append(
                Batch(
                    key=(
                        f"{sample_rate}-{block_size}-"
                        f"{offset:03d}-{limit:02d}"
                    ),
                    sample_rate=sample_rate,
                    block_size=block_size,
                    offset=offset,
                    limit=limit,
                    case_ids=case_ids,
                )
            )
    return batches


def _batch_metadata(
    batch: Batch,
    manifest_digest: str,
    runtime_digest: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "key": batch.key,
        "sample_rate": batch.sample_rate,
        "block_size": batch.block_size,
        "offset": batch.offset,
        "limit": batch.limit,
        "case_ids": list(batch.case_ids),
        "manifest_sha256": manifest_digest,
        "runtime_fingerprint": runtime_digest,
    }


def _validate_saved_batch(
    directory: pathlib.Path,
    batch: Batch,
    manifest_digest: str,
    runtime_digest: str,
) -> BatchValidation:
    metadata_path = directory / "batch.json"
    if not metadata_path.is_file():
        raise ValueError("saved batch is missing batch.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"saved batch metadata is unreadable: {exc}") from exc
    if metadata.get("manifest_sha256") != manifest_digest:
        raise StaleEvidenceError(
            f"saved batch {batch.key} belongs to a different manifest"
        )
    if metadata.get("runtime_fingerprint") != runtime_digest:
        raise StaleEvidenceError(
            f"saved batch {batch.key} belongs to a different runtime payload"
        )
    expected_metadata = _batch_metadata(batch, manifest_digest, runtime_digest)
    if metadata != expected_metadata:
        raise ValueError(f"saved batch metadata does not match {batch.key}")
    for filename in REQUIRED_BATCH_FILES:
        if not (directory / filename).is_file():
            raise ValueError(f"saved batch is missing {filename}")
    _, cases = _read_tsv(directory / "cases.tsv")
    case_ids = tuple(int(row["case_id"]) for row in cases)
    if case_ids != batch.case_ids:
        raise ValueError(f"saved batch cases do not match {batch.key}")
    return validate_batch_results(
        directory,
        batch.case_ids,
        batch.sample_rate,
        batch.block_size,
    )


def _checkpoint_template(
    batch_size: int,
    manifest_digest: str,
    runtime_digest: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "batch_size": batch_size,
        "manifest_sha256": manifest_digest,
        "runtime_fingerprint": runtime_digest,
        "completed": {},
    }


def _load_checkpoint(
    path: pathlib.Path,
    batch_size: int,
    manifest_digest: str,
    runtime_digest: str,
) -> dict[str, Any]:
    expected = _checkpoint_template(
        batch_size,
        manifest_digest,
        runtime_digest,
    )
    if not path.exists():
        return expected
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"checkpoint is unreadable: {exc}") from exc
    for field in (
        "schema",
        "batch_size",
        "manifest_sha256",
        "runtime_fingerprint",
    ):
        if checkpoint.get(field) != expected[field]:
            raise StaleEvidenceError(
                f"checkpoint {field} mismatch; refusing stale batch reuse"
            )
    if not isinstance(checkpoint.get("completed"), dict):
        raise ValueError("checkpoint completed field is not an object")
    return checkpoint


def _archive_invalid(directory: pathlib.Path) -> pathlib.Path:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    for suffix in range(1000):
        candidate = directory.with_name(
            f"{directory.name}.invalid-{stamp}-{suffix:03d}"
        )
        if not candidate.exists():
            directory.rename(candidate)
            return candidate
    raise RuntimeError(f"could not preserve invalid batch directory: {directory}")


def _pressure_avg10(kind: str) -> float:
    path = pathlib.Path("/proc/pressure") / kind
    if not path.is_file():
        return 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields[:1] != ["full"]:
            continue
        for field in fields[1:]:
            if field.startswith("avg10="):
                return float(field.split("=", 1)[1])
    return 0.0


def _stability_snapshot() -> dict[str, float | None]:
    return {
        "available_mib": available_memory_mib(),
        "load_one": os.getloadavg()[0],
        "temperature_c": maximum_temperature_c(),
        "memory_full_pressure_avg10": _pressure_avg10("memory"),
        "io_full_pressure_avg10": _pressure_avg10("io"),
    }


def _stability_errors(snapshot: Mapping[str, float | None]) -> list[str]:
    errors = preflight_errors(
        float(snapshot["available_mib"]),
        float(snapshot["load_one"]),
        snapshot["temperature_c"],
    )
    memory_pressure = float(snapshot["memory_full_pressure_avg10"])
    io_pressure = float(snapshot["io_full_pressure_avg10"])
    if memory_pressure >= MAX_MEMORY_FULL_PRESSURE_AVG10:
        errors.append(
            "memory full-pressure avg10 "
            f"{memory_pressure:.2f} is at or above "
            f"{MAX_MEMORY_FULL_PRESSURE_AVG10:.2f}"
        )
    if io_pressure >= MAX_IO_FULL_PRESSURE_AVG10:
        errors.append(
            f"I/O full-pressure avg10 {io_pressure:.2f} is at or above "
            f"{MAX_IO_FULL_PRESSURE_AVG10:.2f}"
        )
    return errors


def _reaper_pids() -> set[int]:
    pids: set[int] = set()
    for process in pathlib.Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            executable = (process / "exe").resolve(strict=True)
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if executable.name == "reaper":
            pids.add(int(process.name))
    return pids


def _guard_command(timeout_seconds: int) -> list[str]:
    return [
        sys.executable,
        str(GUARD),
        "--gui",
        "--workspace",
        "5",
        "--profile",
        str(STAGING_ROOT / "reaper.ini"),
        "--completion-file",
        str(STAGING_ROOT / "test-results" / "phase.log"),
        "--timeout-seconds",
        str(timeout_seconds),
        "--",
        str(PROJECT),
        str(TEST_SCRIPT),
    ]


def _run_batch(
    batch: Batch,
    output: pathlib.Path,
    timeout_seconds: int,
    manifest_digest: str,
    runtime_digest: str,
) -> BatchValidation:
    before_snapshot = _stability_snapshot()
    errors = _stability_errors(before_snapshot)
    if errors:
        raise RuntimeError("stability guard refusal: " + "; ".join(errors))

    stage(
        ROOT,
        STAGING_ROOT,
        case_set="synthetic",
        sample_rate=batch.sample_rate,
        block_size=batch.block_size,
        case_offset=batch.offset,
        case_limit=batch.limit,
    )
    _, staged_rows = _read_tsv(
        STAGING_ROOT / "Data" / "m3_poly_midi" / "synthetic_cases.tsv"
    )
    staged_case_ids = tuple(int(row["case_id"]) for row in staged_rows)
    if staged_case_ids != batch.case_ids:
        raise RuntimeError(
            f"staged case IDs do not match scheduled batch {batch.key}"
        )

    preexisting_pids = _reaper_pids()
    completed = subprocess.run(
        _guard_command(timeout_seconds),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    time.sleep(0.25)
    remaining_pids = _reaper_pids() - preexisting_pids
    if remaining_pids:
        raise RuntimeError(
            "new disposable REAPER process remains after guard exit: "
            f"{sorted(remaining_pids)}"
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"guarded REAPER batch exited {completed.returncode}:\n"
            f"{completed.stdout.strip()}"
        )

    batches_root = output / "batches"
    batches_root.mkdir(parents=True, exist_ok=True)
    pending = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{batch.key}.pending-", dir=batches_root)
    )
    try:
        sources = {
            "cases.tsv": (
                STAGING_ROOT
                / "Data"
                / "m3_poly_midi"
                / "synthetic_cases.tsv"
            ),
            "events.tsv": STAGING_ROOT / "test-results" / "events.tsv",
            "summary.tsv": STAGING_ROOT / "test-results" / "summary.tsv",
            "safety.tsv": STAGING_ROOT / "test-results" / "safety.tsv",
            "phase.log": STAGING_ROOT / "test-results" / "phase.log",
        }
        for filename, source in sources.items():
            if not source.is_file():
                raise RuntimeError(
                    f"guarded REAPER did not publish required {filename}"
                )
            shutil.copy2(source, pending / filename)
        (pending / "guard.log").write_text(completed.stdout, encoding="utf-8")
        _atomic_write_json(
            pending / "batch.json",
            _batch_metadata(batch, manifest_digest, runtime_digest),
        )
        _atomic_write_json(
            pending / "pressure.json",
            {
                "before": before_snapshot,
                "after": _stability_snapshot(),
            },
        )
        validation = _validate_saved_batch(
            pending,
            batch,
            manifest_digest,
            runtime_digest,
        )
        destination = batches_root / batch.key
        if destination.exists():
            archived = _archive_invalid(destination)
            print(f"preserved invalid batch as {archived.name}", flush=True)
        os.replace(pending, destination)
        return validation
    except BaseException:
        if pending.exists():
            archived = _archive_invalid(pending)
            print(f"preserved failed batch as {archived.name}", flush=True)
        raise


def _completion_record(
    batch: Batch,
    validation: BatchValidation,
) -> dict[str, Any]:
    return {
        "case_ids": list(batch.case_ids),
        "summary_rows": validation.summary_rows,
        "event_rows": validation.event_rows,
    }


def _adopt_saved_batches(
    batches: Sequence[Batch],
    output: pathlib.Path,
    checkpoint: dict[str, Any],
    manifest_digest: str,
    runtime_digest: str,
) -> bool:
    changed = False
    completed = checkpoint["completed"]
    for batch in batches:
        directory = output / "batches" / batch.key
        if not directory.exists():
            if batch.key in completed:
                raise ValueError(
                    f"checkpoint names missing batch directory {batch.key}"
                )
            continue
        try:
            validation = _validate_saved_batch(
                directory,
                batch,
                manifest_digest,
                runtime_digest,
            )
        except StaleEvidenceError:
            raise
        except (OSError, ValueError) as exc:
            archived = _archive_invalid(directory)
            completed.pop(batch.key, None)
            print(
                f"preserved invalid saved batch as {archived.name}: {exc}",
                flush=True,
            )
            changed = True
            continue
        record = _completion_record(batch, validation)
        if completed.get(batch.key) != record:
            completed[batch.key] = record
            changed = True
            print(f"adopted complete uncheckpointed batch {batch.key}", flush=True)
    return changed


def _rebuild_aggregates(
    all_batches: Sequence[Batch],
    output: pathlib.Path,
    checkpoint: Mapping[str, Any],
) -> list[pathlib.Path]:
    completed = checkpoint["completed"]
    directories = [
        output / "batches" / batch.key
        for batch in all_batches
        if batch.key in completed
    ]
    if not directories:
        return []
    for filename in ("cases.tsv", "events.tsv", "summary.tsv", "safety.tsv"):
        merge_batch_tsv(directories, filename, output / filename)
    summarize_main(
        [
            "--events",
            str(output / "events.tsv"),
            "--cases",
            str(output / "cases.tsv"),
            "--out",
            str(output / "partial-report.md"),
            "--fail-below-precision",
            "0.98",
            "--fail-below-recall",
            "0.98",
            "--fail-on-hanging-note",
        ]
    )
    return directories


def _require_output_boundary(output: pathlib.Path) -> pathlib.Path:
    output = output.resolve()
    allowed = RESULTS_ROOT.resolve()
    if output == allowed or allowed not in output.parents:
        raise ValueError(
            f"output must be a child of repository test-results: {allowed}"
        )
    return output


def run(args: argparse.Namespace) -> int:
    output = _require_output_boundary(args.output)
    if not 1 <= args.batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch size must be between 1 and {MAX_BATCH_SIZE}"
        )
    if not 15 <= args.timeout_seconds <= 300:
        raise ValueError("timeout must be between 15 and 300 seconds")
    if args.max_batches is not None and args.max_batches < 1:
        raise ValueError("max batches must be positive")
    if args.start_offset is not None and args.start_offset < 0:
        raise ValueError("start offset must be nonnegative")
    if not REAPER.is_file() or not os.access(REAPER, os.X_OK):
        raise ValueError(f"REAPER executable is unusable: {REAPER}")

    rows = _load_manifest(MANIFEST)
    all_batches = _batches(rows, args.batch_size)
    selected = [
        batch
        for batch in all_batches
        if (args.sample_rate is None or batch.sample_rate == args.sample_rate)
        and (args.block_size is None or batch.block_size == args.block_size)
        and (args.start_offset is None or batch.offset >= args.start_offset)
    ]
    if not selected:
        raise ValueError("filters selected no synthetic batches")

    manifest_digest = _sha256(MANIFEST)
    runtime_digest = runtime_fingerprint(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.json"
    checkpoint = _load_checkpoint(
        checkpoint_path,
        args.batch_size,
        manifest_digest,
        runtime_digest,
    )
    if _adopt_saved_batches(
        all_batches,
        output,
        checkpoint,
        manifest_digest,
        runtime_digest,
    ):
        _atomic_write_json(checkpoint_path, checkpoint)
    elif not checkpoint_path.exists():
        _atomic_write_json(checkpoint_path, checkpoint)
    _rebuild_aggregates(all_batches, output, checkpoint)

    launched = 0
    for batch in selected:
        if batch.key in checkpoint["completed"]:
            print(f"skip complete batch {batch.key}", flush=True)
            continue
        if args.max_batches is not None and launched >= args.max_batches:
            break
        print(
            f"batch-start {batch.key} cases={','.join(map(str, batch.case_ids))}",
            flush=True,
        )
        validation = _run_batch(
            batch,
            output,
            args.timeout_seconds,
            manifest_digest,
            runtime_digest,
        )
        checkpoint["completed"][batch.key] = _completion_record(
            batch,
            validation,
        )
        _atomic_write_json(checkpoint_path, checkpoint)
        _rebuild_aggregates(all_batches, output, checkpoint)
        launched += 1
        print(
            f"batch-finish {batch.key} "
            f"progress={len(checkpoint['completed'])}/{len(all_batches)}",
            flush=True,
        )

    complete = len(checkpoint["completed"]) == len(all_batches)
    if not complete:
        print(
            f"synthetic matrix checkpointed: "
            f"{len(checkpoint['completed'])}/{len(all_batches)} batches",
            flush=True,
        )
        return 0

    report_status = summarize_main(
        [
            "--events",
            str(output / "events.tsv"),
            "--cases",
            str(output / "cases.tsv"),
            "--out",
            str(output / "report.md"),
            "--fail-below-precision",
            "0.98",
            "--fail-below-recall",
            "0.98",
            "--fail-on-hanging-note",
        ]
    )
    print(f"synthetic matrix complete: {output}", flush=True)
    return report_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the disposable REAPER synthetic matrix in stable, resumable "
            "batches"
        )
    )
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        choices=ALLOWED_SAMPLE_RATES,
    )
    parser.add_argument(
        "--block-size",
        type=int,
        choices=ALLOWED_BLOCK_SIZES,
    )
    parser.add_argument("--start-offset", type=int)
    parser.add_argument("--max-batches", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("synthetic matrix interrupted; completed batches remain checkpointed")
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"synthetic matrix stopped safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
