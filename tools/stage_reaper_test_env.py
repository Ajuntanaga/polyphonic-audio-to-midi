#!/usr/bin/env python3
import argparse
import os
import pathlib
import shutil
import sys


LIVE_REAPER = (pathlib.Path.home() / ".config" / "REAPER").resolve()
ALLOWED_SAMPLE_RATES = (44100, 48000, 96000)
ALLOWED_BLOCK_SIZES = (32, 64, 128, 256)
MAX_SYNTHETIC_CASES = 32


def _overlaps_live_profile(output: pathlib.Path) -> bool:
    return (
        output == LIVE_REAPER
        or LIVE_REAPER in output.parents
        or output in LIVE_REAPER.parents
    )


def stage(
    root: pathlib.Path,
    output: pathlib.Path,
    case_set: str = "host",
    sample_rate: int = 48000,
    block_size: int = 128,
    case_offset: int = 0,
    case_limit: int | None = None,
) -> None:
    root = root.resolve()
    output = output.resolve()
    if _overlaps_live_profile(output):
        raise ValueError("refusing to stage into, below, or above live REAPER profile")

    effects = root / "Effects"
    scripts = root / "Scripts"
    case_files = {
        "host": root / "tests" / "fixtures" / "host_cases.tsv",
        "synthetic": root / "tests" / "fixtures" / "synthetic_cases.tsv",
    }
    if case_set not in case_files:
        raise ValueError(f"unknown disposable case set: {case_set}")
    if sample_rate not in ALLOWED_SAMPLE_RATES:
        raise ValueError(f"unsupported sample rate: {sample_rate}")
    if block_size not in ALLOWED_BLOCK_SIZES:
        raise ValueError(f"unsupported block size: {block_size}")
    if case_offset < 0:
        raise ValueError("case offset must be nonnegative")
    if case_set == "synthetic" and case_limit is None:
        raise ValueError("case limit is required for synthetic staging")
    if case_limit is not None and not 1 <= case_limit <= MAX_SYNTHETIC_CASES:
        raise ValueError(
            f"case limit must be between 1 and {MAX_SYNTHETIC_CASES}"
        )
    cases = case_files[case_set]
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
        f"linux_audio_bsize={block_size}\n"
        "linux_audio_bufs=2\n"
        "linux_audio_mode=3\n"
        "linux_audio_nch_in=0\n"
        "linux_audio_nch_out=2\n"
        f"linux_audio_srate={sample_rate}\n"
        "newprojdo=0\n"
        "saveFlags=0\n"
        "warnmaxram64=0\n",
        encoding="utf-8",
    )
    shutil.copytree(effects, output / "Effects")
    shutil.copytree(scripts, output / "Scripts")
    data = output / "Data" / "m3_poly_midi"
    data.mkdir(parents=True)
    staged_cases = data / "synthetic_cases.tsv"
    if case_set == "host":
        shutil.copy2(cases, staged_cases)
    else:
        lines = cases.read_text(encoding="utf-8").splitlines()
        header = lines[0]
        matching = []
        for line in lines[1:]:
            fields = line.split("\t")
            if int(fields[1]) == sample_rate and int(fields[2]) == block_size:
                matching.append(line)
        assert case_limit is not None
        selected = matching[case_offset : case_offset + case_limit]
        if len(selected) != case_limit:
            raise ValueError(
                "synthetic case offset/limit exceeds the selected rate/block batch"
            )
        staged_cases.write_text(
            "\n".join([header, *selected]) + "\n",
            encoding="utf-8",
        )
    (output / "test-results").mkdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage an alternate REAPER test profile")
    parser.add_argument("--reaper", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument(
        "--case-set",
        choices=("host", "synthetic"),
        default="host",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        choices=ALLOWED_SAMPLE_RATES,
        default=48000,
    )
    parser.add_argument(
        "--block-size",
        type=int,
        choices=ALLOWED_BLOCK_SIZES,
        default=128,
    )
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--case-limit", type=int)
    args = parser.parse_args(argv)

    reaper = args.reaper.resolve()
    if not reaper.is_file() or not os.access(reaper, os.X_OK):
        print(f"REAPER executable is not usable: {reaper}", file=sys.stderr)
        return 2

    try:
        stage(
            pathlib.Path(__file__).resolve().parents[1],
            args.output,
            args.case_set,
            args.sample_rate,
            args.block_size,
            args.case_offset,
            args.case_limit,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"staged disposable REAPER profile: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
