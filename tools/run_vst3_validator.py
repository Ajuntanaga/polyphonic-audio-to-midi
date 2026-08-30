#!/usr/bin/env python3
"""Run Steinberg's build-local VST3 validator exactly once under the guard."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence


ROOT = pathlib.Path(__file__).resolve().parents[1]
RELEASE_ROOT = (ROOT / "build/vst3/release").resolve()
VALIDATOR = (RELEASE_ROOT / "bin/Release/validator").resolve()
SDK_MANIFEST = (ROOT / "third_party/vst3sdk/SHA256SUMS").resolve()
GUARD = (ROOT / "tools/run_guarded_native_build.py").resolve()
RESULT_ROOT = (ROOT / "build/test-results/vst3-validator").resolve()


@dataclasses.dataclass(frozen=True)
class KindContract:
    bundle_name: str
    binary_name: str
    product_name: str
    fuid: str


KIND_CONTRACTS = {
    "production": KindContract(
        bundle_name="M3_Polyphonic_Audio_to_MIDI.vst3",
        binary_name="M3_Polyphonic_Audio_to_MIDI.so",
        product_name="M3 Polyphonic Audio to MIDI",
        fuid="4A1BA42F6D7046098B52450C3842F11F",
    ),
    "probe": KindContract(
        bundle_name="M3_Polyphonic_Audio_to_MIDI_Probe.vst3",
        binary_name="M3_Polyphonic_Audio_to_MIDI_Probe.so",
        product_name="M3 Polyphonic Audio to MIDI Probe",
        fuid="6F62F8B1B8A14872A0D92C3C274421D8",
    ),
}

REQUIRED_OUTPUT_PATTERNS = (
    re.compile(r"(?i)\bfactory\b"),
    re.compile(r"(?i)\bclass\b"),
    re.compile(r"(?i)\bbus(?:ses)?\b"),
    re.compile(r"(?i)\bparameters?\b"),
    re.compile(r"(?i)\bstate\b"),
    re.compile(r"(?i)\bprocess(?:ing)?\b"),
)
RESULT_PATTERN = re.compile(
    r"Result:\s*([0-9]+)\s+tests passed,\s*([0-9]+)\s+tests failed",
    re.IGNORECASE,
)
INFRASTRUCTURE_PATTERN = re.compile(
    r"AddressSanitizer|ThreadSanitizer|LeakSanitizer|UndefinedBehaviorSanitizer|"
    r"runtime error:|segmentation fault|core dumped|native build preflight failed|"
    r"timed?\s*out|cannot load (?:the )?module|could not load (?:the )?module|"
    r"no such file|permission denied|failed to create (?:scope|stream)|"
    r"systemd-run|sanitizer runtime",
    re.IGNORECASE,
)
PLUGIN_FAILURE_PATTERN = re.compile(
    r"assertion failed|failed assertion|test(?:s)? failed|failed test|"
    r"plug-?in diagnostic|failed to (?:setup|teardown) test",
    re.IGNORECASE,
)


def normalize_fuid(value: object) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", str(value)).upper()


def expected_bundle(kind: str) -> pathlib.Path:
    return (RELEASE_ROOT / "VST3" / KIND_CONTRACTS[kind].bundle_name).resolve()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def sdk_manifest_errors() -> list[str]:
    if not SDK_MANIFEST.is_file():
        return [f"SDK manifest is absent: {SDK_MANIFEST}"]
    errors: list[str] = []
    rows: list[tuple[str, str]] = []
    try:
        lines = SDK_MANIFEST.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"SDK manifest is unreadable: {exc}"]
    for line in lines:
        match = re.fullmatch(
            r"([0-9a-f]{64})  (third_party/vst3sdk/.+)", line
        )
        if match is None:
            errors.append(f"SDK manifest row is invalid: {line!r}")
            continue
        rows.append(match.groups())
    names = [name for _digest, name in rows]
    if not rows:
        errors.append("SDK manifest has no files")
    if names != sorted(names) or len(names) != len(set(names)):
        errors.append("SDK manifest paths are not unique lexical order")
    for expected, relative in rows:
        path = ROOT / relative
        if not _inside(path, ROOT / "third_party/vst3sdk") or not path.is_file():
            errors.append(f"SDK manifest path is absent or escaped: {relative}")
        elif sha256_file(path) != expected:
            errors.append(f"SDK manifest hash mismatch: {relative}")
    actual = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "third_party/vst3sdk").rglob("*")
        if path.is_file() and path.resolve() != SDK_MANIFEST.resolve()
    )
    if names != actual:
        errors.append("SDK manifest file set does not match the retained SDK tree")
    return errors


def _moduleinfo_errors(path: pathlib.Path, contract: KindContract) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
        # Steinberg's official moduleinfotool emits JSON with trailing commas.
        # Parse that exact build-local dialect without accepting comments or
        # otherwise relaxing the document contract.
        document = json.loads(re.sub(r",(\s*[}\]])", r"\1", source))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"moduleinfo.json is invalid: {exc}"]
    errors: list[str] = []
    classes = document.get("Classes")
    if not isinstance(classes, list) or len(classes) != 1:
        return ["moduleinfo.json must contain exactly one class"]
    class_info = classes[0]
    if not isinstance(class_info, dict):
        return ["moduleinfo.json class is not an object"]
    if normalize_fuid(class_info.get("CID")) != contract.fuid:
        errors.append("moduleinfo.json FUID does not match the selected kind")
    if class_info.get("Name") != contract.product_name:
        errors.append("moduleinfo.json product name does not match the selected kind")
    if class_info.get("Category") != "Audio Module Class":
        errors.append("moduleinfo.json category is not Audio Module Class")
    subcategories = class_info.get("Sub Categories")
    if subcategories != ["Fx", "Tools"]:
        errors.append("moduleinfo.json subcategories are not exactly Fx and Tools")
    factory = document.get("Factory Info")
    if not isinstance(factory, dict) or factory.get("Vendor") != "ajuntanaga":
        errors.append("moduleinfo.json factory vendor is not ajuntanaga")
    return errors


def input_errors(kind: str, bundle: pathlib.Path) -> list[str]:
    if kind not in KIND_CONTRACTS:
        return [f"unsupported validator kind: {kind}"]
    contract = KIND_CONTRACTS[kind]
    expected = expected_bundle(kind)
    supplied = bundle.resolve(strict=False)
    if supplied != expected:
        return [f"bundle is not the exact {kind} bundle: {expected}"]

    errors: list[str] = []
    if not bundle.is_dir():
        errors.append(f"exact {kind} bundle is absent: {bundle}")
        return errors
    if bundle.is_symlink() or not _inside(bundle, RELEASE_ROOT / "VST3"):
        errors.append("bundle is a symlink or escapes the build-local VST3 root")

    binary = bundle / "Contents/x86_64-linux" / contract.binary_name
    moduleinfo = bundle / "Contents/Resources/moduleinfo.json"
    expected_files = {
        binary.relative_to(bundle).as_posix(),
        moduleinfo.relative_to(bundle).as_posix(),
    }
    actual_files: set[str] = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            errors.append(f"bundle contains a symlink: {path.relative_to(bundle)}")
        elif path.is_file():
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != expected_files:
        errors.append("bundle file set is not the exact binary plus moduleinfo.json")
    if not binary.is_file():
        errors.append(f"bundle binary is absent: {binary}")
    if not moduleinfo.is_file():
        errors.append(f"moduleinfo.json is absent: {moduleinfo}")
    else:
        errors.extend(_moduleinfo_errors(moduleinfo, contract))

    if not VALIDATOR.is_file() or VALIDATOR.is_symlink() or not os.access(
        VALIDATOR, os.X_OK
    ):
        errors.append(f"official build-local validator is absent or invalid: {VALIDATOR}")
    elif not _inside(VALIDATOR, RELEASE_ROOT / "bin/Release"):
        errors.append("validator escapes the build-local SDK output root")
    if not GUARD.is_file() or not _inside(GUARD, ROOT / "tools"):
        errors.append(f"native build guard is absent or escaped: {GUARD}")
    errors.extend(sdk_manifest_errors())
    return errors


def bundle_digest(bundle: pathlib.Path) -> str:
    rows = []
    for path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        rows.append(f"{sha256_file(path)}  {path.relative_to(bundle).as_posix()}\n")
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()


def collect_hashes(kind: str, bundle: pathlib.Path) -> dict[str, str]:
    contract = KIND_CONTRACTS[kind]
    binary = bundle / "Contents/x86_64-linux" / contract.binary_name
    moduleinfo = bundle / "Contents/Resources/moduleinfo.json"
    return {
        "bundle": bundle_digest(bundle),
        "bundle_binary": sha256_file(binary),
        "guard": sha256_file(GUARD),
        "moduleinfo": sha256_file(moduleinfo),
        "runner": sha256_file(pathlib.Path(__file__).resolve()),
        "sdk_manifest": sha256_file(SDK_MANIFEST),
        "validator": sha256_file(VALIDATOR),
    }


def validator_command(bundle: pathlib.Path) -> list[str]:
    return [
        sys.executable,
        str(GUARD),
        "--timeout",
        "300",
        "--",
        str(VALIDATOR),
        str(bundle),
    ]


def classify_result(returncode: int, stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}"
    match = RESULT_PATTERN.search(combined)
    if returncode == 0:
        required = all(pattern.search(combined) for pattern in REQUIRED_OUTPUT_PATTERNS)
        if match is not None and int(match.group(1)) > 0 and int(match.group(2)) == 0 and required:
            return "pass"
        return "infrastructure-invalid"
    if returncode < 0 or returncode in {124, 125, 126, 127, 137, 139}:
        return "infrastructure-invalid"
    if INFRASTRUCTURE_PATTERN.search(combined):
        return "infrastructure-invalid"
    if match is not None and int(match.group(2)) > 0:
        return "fail"
    if PLUGIN_FAILURE_PATTERN.search(combined):
        return "fail"
    return "infrastructure-invalid"


def atomic_write_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".pending", dir=path.parent
    )
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: pathlib.Path, value: Mapping[str, object]) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def run_once(kind: str, bundle: pathlib.Path) -> int:
    command = validator_command(bundle)
    hashes = collect_hashes(kind, bundle)
    output_directory = RESULT_ROOT / kind
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=330,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        classification = classify_result(returncode, stdout, stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        returncode = -1
        stdout = ""
        stderr = f"validator execution infrastructure error: {exc}\n"
        classification = "infrastructure-invalid"

    atomic_write_text(output_directory / "stdout.txt", stdout)
    atomic_write_text(output_directory / "stderr.txt", stderr)
    record = {
        "schema": 1,
        "recorded_utc": utc_now(),
        "kind": kind,
        "bundle": str(bundle),
        "command": command,
        "classification": classification,
        "validator_returncode": returncode,
        "hashes": hashes,
        "output_hashes": {
            "stdout": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        },
        "automatic_retry": False,
    }
    atomic_write_json(output_directory / "result.json", record)
    print(f"VST3 validator classification: {classification}")
    return {"pass": 0, "fail": 1, "infrastructure-invalid": 2}[classification]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the exact build-local Steinberg VST3 validator once"
    )
    parser.add_argument("--kind", required=True, choices=tuple(KIND_CONTRACTS))
    parser.add_argument("--bundle", required=True, type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = args.bundle.resolve(strict=False)
    errors = input_errors(args.kind, bundle)
    if errors:
        print("validator input refusal: " + "; ".join(errors), file=sys.stderr)
        return 2
    return run_once(args.kind, bundle)


if __name__ == "__main__":
    raise SystemExit(main())
