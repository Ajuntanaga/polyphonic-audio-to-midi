#!/usr/bin/env python3
"""Confine M3 discovery to one named directory; no unconfined fallback.

Only ripgrep runs in the sandbox. Host home/archive paths are not mounted.
No arbitrary command or ripgrep options are accepted. This is a per-search
boundary, not a sandbox for the surrounding agent session.
"""
from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
from typing import Iterator


PROJECT = Path(__file__).absolute().parent.parent
BWRAP = "/usr/bin/bwrap"
RG_HOST = str(Path.home() / ".local/share/researchos/tools/rg/15.1.0/rg")
RG = "/rg"


class SearchRefused(ValueError):
    pass


def protected_name(name: str) -> bool:
    folded = name.strip(" .").casefold()
    return folded.startswith("windows.old") or "do not enter" in folded


def scoped_parts(project: Path, requested: str) -> tuple[str, ...]:
    # Lexical checks happen BEFORE resolving or inspecting the requested path.
    path = Path(requested)
    if any(part == ".." or protected_name(part) for part in path.parts):
        raise SearchRefused("parent traversal or protected directory name")
    if path.is_absolute():
        try:
            path = path.relative_to(project)
        except ValueError as exc:
            raise SearchRefused("search root is outside this project") from exc
    return tuple(part for part in path.parts if part != ".")


def mount_paths(text: str) -> list[Path]:
    def unescape(value: str) -> str:
        return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)

    return [Path(unescape(line.split()[4])) for line in text.splitlines() if line]


def reject_nested_mounts(project: Path, scope: Path, mounts: list[Path]) -> None:
    # Mount metadata is read from procfs; never probe a mounted target.
    for mount in mounts:
        if mount != project and mount.is_relative_to(project):
            if mount.is_relative_to(scope) or scope.is_relative_to(mount):
                raise SearchRefused("scope includes a mount point; choose a narrower root")


@contextlib.contextmanager
def open_scope(project: Path, requested: str) -> Iterator[int]:
    parts = scoped_parts(project, requested)
    scope = project.joinpath(*parts)
    reject_nested_mounts(
        project, scope, mount_paths(Path("/proc/self/mountinfo").read_text())
    )
    flags = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(project, flags)
    try:
        device = os.fstat(fd).st_dev
        for part in parts:
            child = os.open(part, flags, dir_fd=fd)
            if os.fstat(child).st_dev != device:
                os.close(child)
                raise SearchRefused("scope crosses a filesystem boundary")
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def sandbox_command(fd: int, search: list[str]) -> list[str]:
    return [
        BWRAP,
        "--unshare-all", "--die-with-parent", "--new-session",
        "--clearenv", "--setenv", "PATH", "/usr/bin",
        "--setenv", "LC_ALL", "C.UTF-8",
        # System runtime only; no host /home, /mnt, /media, /run or /tmp.
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        # Expose this one installed tool, not its containing home directory.
        "--ro-bind", RG_HOST, RG,
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--ro-bind-fd", str(fd), "/work",
        "--chdir", "/work", "--cap-drop", "ALL",
        "--", RG, *search,
    ]


def search_options(args: argparse.Namespace) -> list[str]:
    options = [
        "--no-config", "--no-follow", "--one-file-system", "--hidden",
        "--threads", "1", "--max-depth", str(args.depth),
        "--max-filesize", "2M", "--color", "never",
    ]
    for glob in args.glob:
        options += ["--glob", glob]
    # Last globs win. Callers cannot re-include protected paths.
    options += [
        "--glob", "!.git",
        "--iglob", "!*windows.old*",
        "--iglob", "!*do not enter*",
    ]
    if args.mode == "files":
        options += ["--files", "."]
    else:
        options += ["--line-number", "--with-filename", "--max-count", "200",
                    "-e", args.pattern, "."]
    return options


def child_limits() -> None:
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_CPU, (15, 16))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="mode", required=True)
    for mode in ("files", "text"):
        command = sub.add_parser(mode)
        command.add_argument("root", help="existing directory relative to the project")
        if mode == "text":
            command.add_argument("pattern")
        command.add_argument("--glob", action="append", default=[])
        command.add_argument("--depth", type=int, choices=range(1, 17), default=6)
    return result


def run(args: argparse.Namespace, project: Path = PROJECT, **output: object) -> int:
    with open_scope(project, args.root) as fd:
        completed = subprocess.run(
            sandbox_command(fd, search_options(args)), pass_fds=(fd,),
            stdin=subprocess.DEVNULL, timeout=20, check=False,
            preexec_fn=child_limits, **output,
        )
        return completed.returncode


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (SearchRefused, OSError, subprocess.SubprocessError) as exc:
        print(f"project search refused: {exc}; no unconfined fallback", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
