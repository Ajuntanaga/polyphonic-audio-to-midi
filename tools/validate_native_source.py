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
    "juce",
    "iplug2",
    "iplug_include_in_plug_src.h",
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
REALTIME_PRODUCTION_PREFIXES = (
    "native/include/m3/",
    "native/src/",
    "native/vst3/",
)
REALTIME_PRODUCTION_FILES = {
    "native/plugin/dry_path.hpp",
    "native/plugin/prepared_config_exchange.cpp",
    "native/plugin/prepared_config_exchange.hpp",
}
REALTIME_FORBIDDEN_PATTERNS = (
    (
        "thread",
        re.compile(
            r"#\s*include\s*[<\"](?:thread|pthread\.h)[>\"]|"
            r"\bstd::(?:j?thread|this_thread)\b|\bpthread_(?:create|join)\s*\("
        ),
    ),
    (
        "mutex",
        re.compile(
            r"#\s*include\s*[<\"](?:mutex|shared_mutex)[>\"]|"
            r"\bstd::(?:mutex|recursive_mutex|shared_mutex|timed_mutex|"
            r"lock_guard|unique_lock|scoped_lock)\b"
        ),
    ),
    (
        "condition variable",
        re.compile(
            r"#\s*include\s*[<\"]condition_variable[>\"]|"
            r"\bstd::condition_variable(?:_any)?\b"
        ),
    ),
    (
        "future",
        re.compile(
            r"#\s*include\s*[<\"]future[>\"]|"
            r"\bstd::(?:future|promise|packaged_task|async)\b"
        ),
    ),
    (
        "filesystem",
        re.compile(
            r"#\s*include\s*[<\"]filesystem[>\"]|\bstd::filesystem\b"
        ),
    ),
    (
        "iostream",
        re.compile(
            r"#\s*include\s*[<\"](?:iostream|fstream|sstream)[>\"]|"
            r"\bstd::(?:cin|cout|cerr|clog|ifstream|ofstream|fstream)\b"
        ),
    ),
    (
        "stdio",
        re.compile(
            r"#\s*include\s*[<\"](?:cstdio|stdio\.h)[>\"]|"
            r"\b(?:f?printf|snprintf|fopen|fclose|fread|fwrite|fflush)\s*\("
        ),
    ),
    (
        "sleep or wait",
        re.compile(
            r"\b(?:sleep|usleep|nanosleep|sched_yield|waitpid)\s*\(|"
            r"\.(?:wait|wait_for|wait_until)\s*\("
        ),
    ),
    (
        "exception",
        re.compile(
            r"#\s*include\s*[<\"]exception[>\"]|\b(?:throw|try|catch)\b|"
            r"\bstd::exception\b"
        ),
    ),
    ("RTTI", re.compile(r"\b(?:dynamic_cast|typeid)\s*[<(]")),
    (
        "growable container",
        re.compile(
            r"\bstd::(?:vector|deque|list|forward_list|map|multimap|"
            r"unordered_map|unordered_multimap|set|multiset|unordered_set|"
            r"unordered_multiset)\s*<"
        ),
    ),
    (
        "CLAP",
        re.compile(
            r"#\s*include\s*[<\"][^>\"]*clap[^>\"]*[>\"]|\bclap_[A-Za-z0-9_]+"
        ),
    ),
    (
        "report environment",
        re.compile(
            r"\b(?:getenv|secure_getenv|setenv|unsetenv|putenv)\s*\(|"
            r"\bM3_[A-Z0-9_]*REPORT[A-Z0-9_]*\b"
        ),
    ),
    (
        "test schedule",
        re.compile(r"\b(?:kTestSchedule|TestSchedule|test_schedule)\b"),
    ),
)
FUNCTION_DEFINITION_PATTERN = re.compile(
    r"(?m)^[ \t]*(?:[A-Za-z_~][A-Za-z0-9_:<>,*&\[\]~]*[ \t]+)+"
    r"(?:[A-Za-z_][A-Za-z0-9_]*::)*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*"
    r"\([^;{}]*\)[ \t]*(?:const[ \t]*)?"
    r"(?:noexcept(?:[ \t]*\([^)]*\))?[ \t]*)?"
    r"(?:override[ \t]*)?(?:final[ \t]*)?\{"
)


def is_realtime_production_path(relative: str) -> bool:
    return relative in REALTIME_PRODUCTION_FILES or relative.startswith(
        REALTIME_PRODUCTION_PREFIXES
    )


def strip_cpp_comments_and_literals(text: str) -> str:
    output = list(text)
    index = 0
    state = "code"
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == "/" and following == "/":
                output[index] = output[index + 1] = " "
                index += 2
                state = "line-comment"
                continue
            if char == "/" and following == "*":
                output[index] = output[index + 1] = " "
                index += 2
                state = "block-comment"
                continue
            if char == '"':
                output[index] = " "
                state = "string"
            elif char == "'":
                output[index] = " "
                state = "character"
        elif state == "line-comment":
            if char == "\n":
                state = "code"
            else:
                output[index] = " "
        elif state == "block-comment":
            output[index] = " "
            if char == "*" and following == "/":
                output[index + 1] = " "
                index += 2
                state = "code"
                continue
        elif state in {"string", "character"}:
            output[index] = " "
            if char == "\\" and following:
                output[index + 1] = " "
                index += 2
                continue
            if (state == "string" and char == '"') or (
                state == "character" and char == "'"
            ):
                state = "code"
        index += 1
    return "".join(output)


def recursive_function_names(text: str) -> list[str]:
    stripped = strip_cpp_comments_and_literals(text)
    recursive: list[str] = []
    for match in FUNCTION_DEFINITION_PATTERN.finditer(stripped):
        depth = 1
        cursor = match.end()
        while cursor < len(stripped) and depth > 0:
            if stripped[cursor] == "{":
                depth += 1
            elif stripped[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth != 0:
            continue
        name = match.group("name")
        body = stripped[match.end() : cursor - 1]
        direct_call = re.search(
            rf"(?<![.A-Za-z0-9_]){re.escape(name)}\s*\(", body
        )
        this_call = re.search(rf"\bthis\s*->\s*{re.escape(name)}\s*\(", body)
        if direct_call or this_call:
            recursive.append(name)
    return recursive


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


def vstgui_allowed_path(relative: str) -> bool:
    return (
        relative.startswith("third_party/vst3sdk/vstgui4/")
        or relative in {"CMakeLists.txt", "cmake/M3Vst3Sdk.cmake"}
        or relative == "native/tests/test_vst3_editor.cpp"
        or (
            relative.startswith("native/vst3/")
            and pathlib.PurePosixPath(relative).name.startswith("m3_editor")
        )
    )


def validate_entries(
    entries: list[tuple[str, str]], *, sdk_present: bool
) -> list[str]:
    errors: list[str] = []
    for relative, text in entries:
        lowered = text.lower()
        if "vstgui" in lowered and not vstgui_allowed_path(relative):
            errors.append(f"unapproved dependency token vstgui: {relative}")
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
            if is_realtime_production_path(relative):
                for label, pattern in REALTIME_FORBIDDEN_PATTERNS:
                    if pattern.search(text):
                        errors.append(
                            f"realtime-forbidden {label}: {relative}"
                        )
                if relative.startswith(("native/include/m3/", "native/src/")):
                    for name in recursive_function_names(text):
                        errors.append(
                            f"recursive core function {name}: {relative}"
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
