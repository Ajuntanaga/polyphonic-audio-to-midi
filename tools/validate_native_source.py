#!/usr/bin/env python3
import argparse
import pathlib
import re
import subprocess
import sys


TEXT_SUFFIXES = {
    "",
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".h",
    ".hpp",
    ".inc",
    ".make",
    ".md",
    ".mk",
    ".py",
    ".txt",
}
NATIVE_PREFIXES = ("native/",)
DEPENDENCY_PREFIX = "third_party/clap/"
BUILD_PREFIX = "cmake/"
BUILD_FILES = {"CMakeLists.txt"}
IGNORED_PREFIXES = ("build/", "third_party/vst3sdk/")
UNAPPROVED_DEPENDENCIES = (
    "neuralnote",
    "basic pitch",
    "reatune",
    "onnx",
    "tensorflow",
    "libtorch",
    "torch/",
    ".tflite",
    ".pt",
    "vstgui",
    "juce",
    "iplug",
)
UNAPPROVED_BUILD_TOKENS = (
    "-march=native",
    "ninja",
    "juce",
    "iplug2",
)
NETWORK_TOKENS = (
    "<curl/",
    "<sys/socket.h>",
    "socket(",
    "connect(",
)
NETWORK_BUILD_TOKENS = (
    "fetchcontent",
    "externalproject_add",
    "file(download",
    "git clone",
    "curl ",
    "wget ",
)
SDK_INCLUDE_PATTERN = re.compile(
    r"(?m)^\s*#\s*include\s*[<\"](?:base|pluginterfaces|public\.sdk)/"
)
HANDWRITTEN_VST3_ABI_PATTERN = re.compile(
    r"\bnamespace\s+steinberg\b", re.IGNORECASE
)
FUID_PATTERNS = (
    (
        "production",
        re.compile(
            r"0x4A1BA42FU?\s*,\s*0x6D704609U?\s*,\s*"
            r"0x8B52450CU?\s*,\s*0x3842F11FU?",
            re.IGNORECASE,
        ),
    ),
    (
        "probe",
        re.compile(
            r"0x6F62F8B1U?\s*,\s*0xB8A14872U?\s*,\s*"
            r"0xA0D92C3CU?\s*,\s*0x274421D8U?",
            re.IGNORECASE,
        ),
    ),
    (
        "benchmark",
        re.compile(
            r"0x28713895U?\s*,\s*0x1CCA47ECU?\s*,\s*"
            r"0x919F6CC1U?\s*,\s*0xBCB88A8FU?",
            re.IGNORECASE,
        ),
    ),
)
IDENTITY_HEADER = "native/vst3/vst3_ids.hpp"
TEST_ONLY_FUID_SYMBOLS = ("kProbeClassIdWords", "kBenchmarkClassIdWords")


def test_only_fuid_allowed(relative: str, symbol: str) -> bool:
    if relative in {IDENTITY_HEADER, "native/vst3/vst3_factory.cpp"}:
        return True
    stem = pathlib.PurePosixPath(relative).stem.lower()
    marker = "probe" if symbol == "kProbeClassIdWords" else "benchmark"
    return marker in stem


def project_paths(root: pathlib.Path) -> list[pathlib.Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = pathlib.Path(raw.decode("utf-8"))
        name = relative.as_posix()
        if name.startswith(IGNORED_PREFIXES):
            continue
        if (
            name.startswith(NATIVE_PREFIXES)
            or name.startswith(DEPENDENCY_PREFIX)
            or name.startswith(BUILD_PREFIX)
            or name in BUILD_FILES
        ):
            path = root / relative
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                paths.append(path)
    return sorted(paths)


def is_build_path(relative: str) -> bool:
    path = pathlib.PurePosixPath(relative)
    return (
        relative in BUILD_FILES
        or relative.startswith(BUILD_PREFIX)
        or path.name.lower().endswith("makefile")
        or path.suffix.lower() in {".cmake", ".mk", ".make"}
    )


def validate_entries(
    entries: list[tuple[str, str]], *, sdk_present: bool
) -> list[str]:
    errors: list[str] = []
    for relative, text in entries:
        lowered = text.lower()
        if relative.startswith(NATIVE_PREFIXES):
            for token in UNAPPROVED_DEPENDENCIES:
                if token in lowered:
                    errors.append(f"unapproved dependency token {token}: {relative}")
            for token in NETWORK_TOKENS:
                if token in lowered:
                    errors.append(f"network token {token}: {relative}")
            path = pathlib.PurePosixPath(relative)
            if path.name.lower().endswith("makefile") or path.suffix.lower() in {
                ".mk",
                ".make",
            }:
                for token in UNAPPROVED_BUILD_TOKENS:
                    if token in lowered:
                        errors.append(f"unapproved build token {token}: {relative}")
            if HANDWRITTEN_VST3_ABI_PATTERN.search(text):
                errors.append(f"handwritten VST3 ABI declaration: {relative}")
            if relative.startswith("native/plugin/") and (
                "vst3" in path.name.lower()
                or "base/source/" in lowered
                or "pluginterfaces/" in lowered
                or "public.sdk/" in lowered
                or "steinberg::" in lowered
            ):
                errors.append(f"VST3 source under native/plugin: {relative}")
            if (
                relative.startswith("native/vst3/")
                and not sdk_present
                and SDK_INCLUDE_PATTERN.search(text)
            ):
                errors.append(f"SDK include before Gate D2: {relative}")
            if relative.startswith("native/vst3/"):
                for symbol in TEST_ONLY_FUID_SYMBOLS:
                    if symbol in text and not test_only_fuid_allowed(relative, symbol):
                        errors.append(
                            f"production reference to test-only FUID {symbol}: "
                            f"{relative}"
                        )
        if is_build_path(relative):
            for token in NETWORK_BUILD_TOKENS:
                if token in lowered:
                    errors.append(f"network build token {token}: {relative}")

    for label, pattern in FUID_PATTERNS:
        locations: list[str] = []
        for relative, text in entries:
            locations.extend(relative for _match in pattern.finditer(text))
        if len(locations) > 1:
            errors.append(
                f"duplicate FUID tuple {label}: {', '.join(sorted(locations))}"
            )
        for relative in locations:
            if relative != IDENTITY_HEADER:
                errors.append(f"FUID tuple outside identity header {label}: {relative}")
    return errors


def validate_tree(root: pathlib.Path) -> list[str]:
    entries = [
        (
            path.relative_to(root).as_posix(),
            path.read_text(encoding="utf-8", errors="replace"),
        )
        for path in project_paths(root)
    ]
    return validate_entries(
        entries,
        sdk_present=(root / "third_party/vst3sdk").is_dir(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate native source boundaries")
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors = validate_tree(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("native source contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
