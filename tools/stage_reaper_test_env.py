#!/usr/bin/env python3
import argparse
import os
import pathlib
import shutil
import sys


LIVE_REAPER = (pathlib.Path.home() / ".config" / "REAPER").resolve()


def _overlaps_live_profile(output: pathlib.Path) -> bool:
    return (
        output == LIVE_REAPER
        or LIVE_REAPER in output.parents
        or output in LIVE_REAPER.parents
    )


def stage(root: pathlib.Path, output: pathlib.Path) -> None:
    root = root.resolve()
    output = output.resolve()
    if _overlaps_live_profile(output):
        raise ValueError("refusing to stage into, below, or above live REAPER profile")

    output.mkdir(parents=True, exist_ok=True)
    (output / "reaper.ini").write_text(
        "[reaper]\nnewprojdo=0\nsaveFlags=0\n",
        encoding="utf-8",
    )
    shutil.copytree(root / "Effects", output / "Effects", dirs_exist_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage an alternate REAPER test profile")
    parser.add_argument("--reaper", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    reaper = args.reaper.resolve()
    if not reaper.is_file() or not os.access(reaper, os.X_OK):
        print(f"REAPER executable is not usable: {reaper}", file=sys.stderr)
        return 2

    try:
        stage(pathlib.Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"staged disposable REAPER profile: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
