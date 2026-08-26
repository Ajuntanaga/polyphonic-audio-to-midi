#!/usr/bin/env python3
import argparse
import itertools
import pathlib
import sys
from typing import Any


SAMPLE_RATES = (44100, 48000, 96000)
BLOCK_SIZES = (32, 64, 128, 256)
M3_OPENS = (32, 36, 40, 44, 48, 52, 56, 60)
FIELDS = (
    "case_id",
    "sample_rate",
    "block_size",
    "mode",
    "notes",
    "detune_cents",
    "missing_fundamental",
    "gains_db",
    "noise_db",
    "hum_db",
    "clip",
    "stagger_ms",
    "expected",
)
HEADER = "\t".join(FIELDS)


def _notes_text(notes: tuple[int, ...]) -> str:
    return ",".join(str(note) for note in notes)


def _base_case(
    *,
    mode: str,
    notes: str,
    expected: str,
    detune_cents: int = 0,
    missing_fundamental: int = 0,
    gains_db: str = "0",
    noise_db: int = -120,
    hum_db: int = -120,
    clip: int = 0,
    stagger_ms: int = 0,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "notes": notes,
        "detune_cents": detune_cents,
        "missing_fundamental": missing_fundamental,
        "gains_db": gains_db,
        "noise_db": noise_db,
        "hum_db": hum_db,
        "clip": clip,
        "stagger_ms": stagger_ms,
        "expected": expected,
    }


def build_cases() -> list[dict[str, Any]]:
    base_cases = [
        _base_case(mode="general", notes=str(note), expected=str(note))
        for note in range(24, 109)
    ]
    base_cases.extend(
        _base_case(mode="m3", notes=str(note), expected=str(note))
        for note in M3_OPENS
    )
    for size in (2, 3, 4):
        for combination in itertools.islice(
            itertools.combinations(M3_OPENS, size),
            12,
        ):
            notes = _notes_text(combination)
            base_cases.append(
                _base_case(mode="m3", notes=notes, expected=notes)
            )
    open_notes = _notes_text(M3_OPENS)
    base_cases.append(
        _base_case(mode="m3", notes=open_notes, expected=open_notes)
    )
    base_cases.extend(
        (
            _base_case(mode="general", notes="40", expected="40"),
            _base_case(mode="general", notes="40,47", expected="40,47"),
            _base_case(
                mode="general",
                notes="32,36,40",
                expected="32,36,40",
            ),
            _base_case(mode="general", notes=open_notes, expected=open_notes),
            _base_case(
                mode="general",
                notes="40,47,52,57",
                expected="40,47,52,57",
                gains_db="0,-6,-24,-12",
            ),
            _base_case(
                mode="general:poly=3",
                notes="32,36,40,43",
                expected="32,36,40",
            ),
        )
    )
    for note in M3_OPENS:
        for detune_cents in (-35, 35):
            for noise_db in (-60, -48, -36):
                base_cases.append(
                    _base_case(
                        mode="m3",
                        notes=str(note),
                        expected=str(note),
                        detune_cents=detune_cents,
                        noise_db=noise_db,
                    )
                )
    base_cases.extend(
        (
            _base_case(mode="silence", notes="", expected=""),
            _base_case(
                mode="noise",
                notes="",
                expected="",
                noise_db=-48,
            ),
            _base_case(
                mode="hum50",
                notes="",
                expected="",
                hum_db=-36,
            ),
            _base_case(
                mode="hum60",
                notes="",
                expected="",
                hum_db=-36,
            ),
            _base_case(
                mode="dc",
                notes="",
                expected="",
                noise_db=-36,
            ),
            _base_case(
                mode="general",
                notes="40",
                expected="40",
                clip=1,
            ),
            _base_case(
                mode="general",
                notes="40",
                expected="40",
                missing_fundamental=1,
            ),
            _base_case(
                mode="general",
                notes="40,47,52,57",
                expected="40,47,52,57",
                gains_db="0,-6,-18,-24",
            ),
            _base_case(
                mode="general",
                notes="40,47,52",
                expected="40,47,52",
                stagger_ms=10,
            ),
            _base_case(
                mode="general",
                notes="40,40",
                expected="40",
                gains_db="0,-3",
            ),
            _base_case(mode="release", notes="40", expected="40"),
            _base_case(
                mode="general",
                notes="40,40,40",
                expected="40",
                gains_db="0,-3,-6",
            ),
            _base_case(
                mode="m3",
                notes="44,48,52,56",
                expected="44,48,52,56",
            ),
            _base_case(
                mode="m3",
                notes="32,33,34,35,36,37,38,39",
                expected="32,36",
            ),
        )
    )
    cases: list[dict[str, Any]] = []
    case_id = 1
    for base_case in base_cases:
        for sample_rate in SAMPLE_RATES:
            for block_size in BLOCK_SIZES:
                cases.append(
                    {
                        "case_id": case_id,
                        "sample_rate": sample_rate,
                        "block_size": block_size,
                        **base_case,
                    }
                )
                case_id += 1
    return cases


def _sorted_note_text(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "-"
    return ",".join(
        str(note) for note in sorted({int(token) for token in text.split(",")})
    )


def render_cases(cases: list[dict[str, Any]]) -> str:
    lines = [HEADER]
    for case in cases:
        row = dict(case)
        if not str(row["notes"]).strip():
            row["notes"] = "-"
        row["expected"] = _sorted_note_text(row["expected"])
        lines.append("\t".join(str(row[field]) for field in FIELDS))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic synthetic audio case matrix"
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=pathlib.Path)
    action.add_argument("--check", type=pathlib.Path)
    args = parser.parse_args(argv)

    expected = render_cases(build_cases()).encode("utf-8")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(expected)
        print(f"wrote synthetic manifest: {args.output}")
        return 0

    try:
        actual = args.check.read_bytes()
    except OSError as exc:
        print(f"synthetic manifest check failed: {exc}", file=sys.stderr)
        return 1
    if actual != expected:
        print(f"synthetic manifest differs: {args.check}", file=sys.stderr)
        return 1
    print(f"byte-identical synthetic manifest: {args.check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
