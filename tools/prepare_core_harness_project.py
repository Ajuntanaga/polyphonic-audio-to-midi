#!/usr/bin/env python3
import argparse
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = (ROOT / "build").resolve()
FX_MARKER = '<JS "tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx" ""'
RATE_SLIDER = {48000: "0", 44100: "1", 96000: "2"}
BLOCK_SLIDER = {32: "0", 64: "1", 128: "2", 256: "3"}
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
    8101: "24",
    8102: "25",
    8103: "26",
    8104: "27",
    8105: "28",
    8106: "29",
    8107: "30",
    8108: "31",
    8109: "32",
    8110: "33",
    8111: "34",
    9101: "35",
    9102: "36",
    9103: "37",
    9104: "38",
    9105: "39",
    9106: "40",
    9107: "41",
    9108: "42",
    9109: "43",
    10101: "44",
    10102: "45",
    10103: "46",
    10104: "47",
    10105: "48",
    10106: "49",
    12101: "50",
    12102: "51",
    12103: "52",
    12104: "53",
    12105: "54",
    12106: "55",
    12107: "56",
    12108: "57",
    12109: "58",
    12110: "59",
    12111: "60",
    12112: "61",
    12113: "62",
    12114: "63",
    12115: "64",
    12116: "65",
    12117: "66",
    12118: "67",
}


def prepare_project(
    source: pathlib.Path,
    output_directory: pathlib.Path,
    rate: int,
    case_id: int,
    block_size: int | None = None,
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
            "6101..6106, 7101..7106, 8101..8111, 9101..9109, "
            "10101..10106, or 12101..12118"
        )
    task_eight = 8101 <= case_id <= 8111
    if task_eight and block_size not in BLOCK_SLIDER:
        raise ValueError("Task 8 requires block size 32, 64, 128, or 256")
    if not task_eight and block_size is not None:
        raise ValueError("block size is valid only for Task 8 cases")

    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    markers = [index for index, line in enumerate(lines) if FX_MARKER in line]
    if len(markers) != 1 or markers[0] + 1 >= len(lines):
        raise ValueError("source project must contain exactly one core harness FX state")

    state_index = markers[0] + 1
    state_line = lines[state_index]
    indentation = state_line[: len(state_line) - len(state_line.lstrip())]
    newline = "\n" if state_line.endswith("\n") else ""
    state = state_line.strip().split()
    required_fields = 3 if task_eight else 2
    if len(state) < required_fields:
        raise ValueError(
            f"core harness FX state has fewer than {required_fields} slider fields"
        )
    state[0] = RATE_SLIDER[rate]
    state[1] = CASE_SLIDER[case_id]
    if task_eight:
        state[2] = BLOCK_SLIDER[block_size]
    lines[state_index] = indentation + " ".join(state) + newline

    output_directory.mkdir(parents=True, exist_ok=True)
    result_directory = BUILD / "evidence" / f"task-{case_id // 1000:02d}-results"
    result_directory.mkdir(parents=True, exist_ok=True)
    project_name = (
        f"core-harness-{rate}-block-{block_size}-case-{case_id}.RPP"
        if task_eight
        else f"core-harness-{rate}-case-{case_id}.RPP"
    )
    destination = output_directory / project_name
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
    parser.add_argument("--block-size", type=int)
    args = parser.parse_args(argv)
    try:
        destination = prepare_project(
            args.source,
            args.output_dir,
            args.rate,
            args.case_id,
            args.block_size,
        )
    except (OSError, ValueError) as exc:
        print(f"preparer refusal: {exc}", file=sys.stderr)
        return 2
    print(f"prepared disposable core harness: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
