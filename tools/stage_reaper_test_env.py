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

    effects = root / "Effects"
    scripts = root / "Scripts"
    cases = root / "tests" / "fixtures" / "synthetic_cases.tsv"
    if not effects.is_dir():
        raise ValueError(f"missing Effects tree: {effects}")
    if not scripts.is_dir():
        raise ValueError(f"missing Scripts tree: {scripts}")
    if not cases.is_file():
        raise ValueError(f"missing synthetic case manifest: {cases}")

    output.mkdir(parents=True, exist_ok=True)
    for relative in (
        pathlib.Path("Effects"),
        pathlib.Path("Scripts"),
        pathlib.Path("Data/m3_poly_midi"),
        pathlib.Path("test-results"),
    ):
        destination = output / relative
        if destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()

    for disposable_cache in ("reaper-kb.ini", "reaper-jsfx.ini"):
        cache_path = output / disposable_cache
        if cache_path.exists():
            cache_path.unlink()

    (output / "reaper.ini").write_text(
        "[reaper]\n"
        "linux_audio_bsize=128\n"
        "linux_audio_bufs=2\n"
        "linux_audio_mode=3\n"
        "linux_audio_nch_in=0\n"
        "linux_audio_nch_out=2\n"
        "linux_audio_srate=48000\n"
        "newprojdo=0\n"
        "saveFlags=0\n"
        "warnmaxram64=0\n",
        encoding="utf-8",
    )
    shutil.copytree(effects, output / "Effects")
    shutil.copytree(scripts, output / "Scripts")
    data = output / "Data" / "m3_poly_midi"
    data.mkdir(parents=True)
    shutil.copy2(cases, data / cases.name)
    (output / "test-results").mkdir()


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
