#!/usr/bin/env python3
import argparse
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = (ROOT / "build").resolve()
FX_MARKER = '<JS "tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx" ""'
RATE_SLIDER = {48000: "0", 44100: "1", 96000: "2"}
CASE_SLIDER = {
    4101: "0",
    4102: "1",
    4103: "2",
    4104: "3",
    4105: "4",
    4106: "5",
    5101: "6",
    5102: "7",
    5103: "8",
    5104: "9",
    5105: "10",
    5106: "11",
    6101: "12",
    6102: "13",
    6103: "14",
    6104: "15",
    6105: "16",
    6106: "17",
    7101: "18",
    7102: "19",
    7103: "20",
    7104: "21",
    7105: "22",
    7106: "23",
}


def prepare_project(
    source: pathlib.Path,
    output_directory: pathlib.Path,
    rate: int,
    case_id: int,
) -> pathlib.Path:
    source = source.resolve()
    output_directory = output_directory.resolve()
    try:
        source.relative_to(BUILD)
    except ValueError as exc:
        raise ValueError(
            f"source project is outside disposable build directory: {source}"
        ) from exc
    try:
        output_directory.relative_to(BUILD)
    except ValueError as exc:
        raise ValueError(
            f"output directory is outside disposable build directory: {output_directory}"
        ) from exc
    if not source.is_file():
        raise ValueError(f"source project is missing: {source}")
    if rate not in RATE_SLIDER:
        raise ValueError("rate must be exactly 44100, 48000, or 96000")
    if case_id not in CASE_SLIDER:
        raise ValueError(
            "case ID must be one of 4101..4106, 5101..5106, "
            "6101..6106, or 7101..7106"
        )

    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    markers = [index for index, line in enumerate(lines) if FX_MARKER in line]
    if len(markers) != 1 or markers[0] + 1 >= len(lines):
        raise ValueError("source project must contain exactly one core harness FX state")

    state_index = markers[0] + 1
    state_line = lines[state_index]
    indentation = state_line[: len(state_line) - len(state_line.lstrip())]
    newline = "\n" if state_line.endswith("\n") else ""
    state = state_line.strip().split()
    if len(state) < 2:
        raise ValueError("core harness FX state has fewer than two slider fields")
    state[0] = RATE_SLIDER[rate]
    state[1] = CASE_SLIDER[case_id]
    lines[state_index] = indentation + " ".join(state) + newline

    output_directory.mkdir(parents=True, exist_ok=True)
    result_directory = BUILD / "evidence" / f"task-{case_id // 1000:02d}-results"
    result_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f"core-harness-{rate}-case-{case_id}.RPP"
    temporary = destination.with_suffix(".RPP.tmp")
    temporary.write_text("".join(lines), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare one build-local core-harness rate/case project"
    )
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--rate", type=int, required=True)
    parser.add_argument("--case-id", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        destination = prepare_project(
            args.source,
            args.output_dir,
            args.rate,
            args.case_id,
        )
    except (OSError, ValueError) as exc:
        print(f"preparer refusal: {exc}", file=sys.stderr)
        return 2
    print(f"prepared disposable core harness: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
