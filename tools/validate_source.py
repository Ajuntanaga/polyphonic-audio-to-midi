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
    "m3_poly_midi/m3_profile.jsfx-inc",
    "m3_poly_midi/lifecycle.jsfx-inc",
    "m3_poly_midi/midi_emitter.jsfx-inc",
)
EXPECTED_SLIDERS = (
    "slider1:0<0,2,1{Left,Right,Downmix}>Detector input",
    "slider2:0<0,1,1{M3 Eight-String,General Tonal}>Mode",
    "slider3:440<400,480,0.1>A4 reference (Hz)",
    "slider4:0<-24,24,0.1>Input trim (dB)",
    "slider5:50<0,100,1>Sensitivity",
    "slider6:25<0,100,1>Response (Fast to Stable)",
    "slider7:32<24,108,1>Lowest MIDI note",
    "slider8:84<24,108,1>Highest MIDI note",
    "slider9:8<1,8,1>Maximum polyphony",
    "slider10:24<0,36,1>M3 maximum fret",
    "slider11:1<0,1,1{Fixed,Dynamic}>Velocity mode",
    "slider12:100<1,127,1>Fixed velocity",
    "slider13:1<1,16,1>MIDI channel",
    "slider14:0<0,1,1{Ready,Panic}>Panic",
    "slider15:1<0,1,1{Muted,Pass through}>Dry audio",
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
    if "m3_bank_process_reference(" in text:
        errors.append("test-only reference call in production effect")

    slider_lines = re.findall(r"(?m)^slider\d+:.*$", text)
    sliders = re.findall(r"(?m)^slider(\d+):", text)
    if len(sliders) != len(set(sliders)):
        errors.append("duplicate slider number")
    if tuple(slider_lines) != EXPECTED_SLIDERS:
        errors.append("production slider surface differs from the stable contract")

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

    if "midirecv(" in text:
        errors.append("production effect consumes incoming MIDI")

    slider = section(text, "slider")
    if "m3_bank_init(" in slider or "m3_host_reset_detector(" in slider:
        errors.append("slider section rebuilds detector")

    block = section(text, "block")
    selection_call = "m3_select_voices("
    profile_call = "m3_profile_filter_selected("
    if selection_call not in block:
        errors.append("production block does not select voices")
    if profile_call not in block:
        errors.append("production block does not filter the selected M3 voicing")
    if selection_call in block and profile_call in block:
        if block.index(selection_call) > block.index(profile_call):
            errors.append("M3 profile filtering must follow voice selection")
    panic_call = "m3_midi_panic("
    reset_call = "m3_host_reset_detector("
    if panic_call not in block:
        errors.append("production block does not perform reachable MIDI cleanup")
    if reset_call not in block:
        errors.append("production block does not perform bounded detector reset")
    if panic_call in block and reset_call in block:
        if block.index(panic_call) > block.index(reset_call):
            errors.append("MIDI cleanup must precede detector reset")

    sample = section(text, "sample")
    if "m3_midi_emit_event(" not in sample:
        errors.append("production sample path does not emit lifecycle MIDI")
    assignments = re.findall(r"(?m)^\s*(spl[01])\s*=\s*([^;]+);", text)
    if assignments != [("spl0", "0"), ("spl1", "0")]:
        errors.append("production dry audio assignment contract is not exact")
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
