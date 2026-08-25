#!/usr/bin/env python3
import argparse
import pathlib
import re
import sys


REQUIRED = ("desc:", "@init", "@slider", "@block", "@sample", "@gfx")
FILE_CALLS = (
    "file_open(",
    "file_close(",
    "file_mem(",
    "file_var(",
    "file_string(",
)
FORBIDDEN_RT = FILE_CALLS + ("printf(", "gfx_", "while(", "pdc_")
EFFECT_NAME = "ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"


def section(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^@{name}[^\n]*\n(.*?)(?=^@|\Z)", text)
    return match.group(1) if match else ""


def validate_tree(root: pathlib.Path) -> list[str]:
    effect = root / "Effects" / EFFECT_NAME
    if not effect.is_file():
        return [f"missing production effect: {effect}"]

    text = effect.read_text(encoding="utf-8")
    errors = [f"missing {token}" for token in REQUIRED if token not in text]

    sliders = re.findall(r"(?m)^slider(\d+):", text)
    if len(sliders) != len(set(sliders)):
        errors.append("duplicate slider number")

    imports = re.findall(r"(?m)^import\s+(.+?)\s*$", text)
    for imported in imports:
        imported_path = root / "Effects" / imported
        if not imported_path.is_file():
            errors.append(f"missing import: {imported}")
            continue
        module_text = imported_path.read_text(encoding="utf-8")
        forbidden = FILE_CALLS + ("printf(", "while(", "pdc_")
        if not imported.endswith("telemetry_ui.jsfx-inc"):
            forbidden += ("gfx_",)
        errors.extend(
            f"forbidden module token {token}: {imported}"
            for token in forbidden
            if token in module_text
        )

    realtime = section(text, "sample") + section(text, "block")
    errors.extend(
        f"forbidden real-time token: {token}"
        for token in FORBIDDEN_RT
        if token in realtime
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the production JSFX source contract")
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args(argv)

    errors = validate_tree(args.root.resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("source contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
