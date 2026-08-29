#!/usr/bin/env python3
import argparse
import pathlib
import subprocess
import sys


TEXT_SUFFIXES = {
    "",
    ".c",
    ".cc",
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
)
UNAPPROVED_BUILD_TOKENS = (
    "-march=native",
    "cmake",
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
        if name.startswith("build/"):
            continue
        if name.startswith(NATIVE_PREFIXES) or name.startswith(DEPENDENCY_PREFIX):
            path = root / relative
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                paths.append(path)
    return sorted(paths)


def validate_tree(root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    paths = project_paths(root)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        if relative.startswith(NATIVE_PREFIXES):
            for token in UNAPPROVED_DEPENDENCIES:
                if token in lowered:
                    errors.append(f"unapproved dependency token {token}: {relative}")
            for token in NETWORK_TOKENS:
                if token in lowered:
                    errors.append(f"network token {token}: {relative}")
            if path.name.lower().endswith("makefile") or path.suffix.lower() in {".mk", ".make"}:
                for token in UNAPPROVED_BUILD_TOKENS:
                    if token in lowered:
                        errors.append(f"unapproved build token {token}: {relative}")
    return errors


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
