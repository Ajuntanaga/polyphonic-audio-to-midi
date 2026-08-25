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
CORE_IMPORTS = (
    "m3_poly_midi/constants.jsfx-inc",
    "m3_poly_midi/pitch_math.jsfx-inc",
)


def section(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^@{name}[^\n]*\n(.*?)(?=^@|\Z)", text)
    return match.group(1) if match else ""


def effect_sources(effects: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        path
        for path in effects.rglob("*")
        if path.is_file()
        and (path.name.endswith(".jsfx") or path.name.endswith(".jsfx-inc"))
    )


def validate_import_graph(effects: pathlib.Path) -> list[str]:
    errors = []
    effects = effects.resolve()
    for source in effect_sources(effects):
        text = source.read_text(encoding="utf-8")
        for imported in re.findall(r"(?m)^import\s+(.+?)\s*$", text):
            imported_path = (source.parent / imported).resolve()
            try:
                imported_path.relative_to(effects)
            except ValueError:
                errors.append(f"import escapes Effects: {source.name} -> {imported}")
                continue
            if not imported_path.is_file():
                errors.append(f"missing import: {source.name} -> {imported}")
    return errors


def validate_modules(effects: pathlib.Path) -> list[str]:
    errors = []
    for module in sorted(effects.rglob("*.jsfx-inc")):
        text = module.read_text(encoding="utf-8")
        forbidden = FILE_CALLS + ("printf(", "while(", "pdc_")
        if module.name != "telemetry_ui.jsfx-inc":
            forbidden += ("gfx_",)
        errors.extend(
            f"forbidden module token {token}: {module.relative_to(effects)}"
            for token in forbidden
            if token in text
        )
    return errors


def validate_tree(root: pathlib.Path) -> list[str]:
    effects = root / "Effects"
    effect = effects / EFFECT_NAME
    if not effect.is_file():
        return [f"missing production effect: {effect}"]

    text = effect.read_text(encoding="utf-8")
    errors = [f"missing {token}" for token in REQUIRED if token not in text]

    sliders = re.findall(r"(?m)^slider(\d+):", text)
    if len(sliders) != len(set(sliders)):
        errors.append("duplicate slider number")

    imports = re.findall(r"(?m)^import\s+(.+?)\s*$", text)
    for core_import in CORE_IMPORTS:
        if core_import not in imports:
            errors.append(f"missing core import: {core_import}")
    if all(core_import in imports for core_import in CORE_IMPORTS):
        if imports.index(CORE_IMPORTS[0]) > imports.index(CORE_IMPORTS[1]):
            errors.append("constants must be imported before pitch math")

    errors.extend(validate_import_graph(effects))
    errors.extend(validate_modules(effects))

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
