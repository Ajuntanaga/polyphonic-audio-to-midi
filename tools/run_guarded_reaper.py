#!/usr/bin/env python3
import argparse
import os
import pathlib
import shlex
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
REAPER = pathlib.Path("/home/ajuntanaga/opt/REAPER/reaper")
DISPOSABLE_PROFILE = (ROOT / "build/reaper-test/reaper.ini").resolve()
MIN_AVAILABLE_MIB = 4096.0
MAX_LOAD_ONE = 12.0
MAX_TEMPERATURE_C = 90.0


def available_memory_mib() -> float:
    for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024.0
    raise RuntimeError("MemAvailable is absent from /proc/meminfo")


def maximum_temperature_c() -> float | None:
    temperatures = []
    for path in pathlib.Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            value = float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        temperatures.append(value / 1000.0 if value > 1000 else value)
    return max(temperatures) if temperatures else None


def preflight_errors(
    available_mib: float,
    load_one: float,
    temperature_c: float | None,
) -> list[str]:
    errors = []
    if available_mib < MIN_AVAILABLE_MIB:
        errors.append(
            f"available memory {available_mib:.0f} MiB is below {MIN_AVAILABLE_MIB:.0f} MiB"
        )
    if load_one > MAX_LOAD_ONE:
        errors.append(f"one-minute load {load_one:.2f} exceeds {MAX_LOAD_ONE:.2f}")
    if temperature_c is not None and temperature_c >= MAX_TEMPERATURE_C:
        errors.append(
            f"temperature {temperature_c:.1f} C is at or above {MAX_TEMPERATURE_C:.1f} C"
        )
    return errors


def runtime_environment(gui: bool) -> dict[str, str]:
    uid = os.getuid()
    runtime = pathlib.Path(f"/run/user/{uid}")
    bus = runtime / "bus"
    if not bus.exists():
        raise RuntimeError(f"user session bus is unavailable: {bus}")

    environment = os.environ.copy()
    environment["XDG_RUNTIME_DIR"] = str(runtime)
    environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"

    if gui:
        auth_files = sorted(runtime.glob(".mutter-Xwaylandauth.*"))
        if not auth_files:
            raise RuntimeError("guarded GUI requested but no Mutter Xwayland authority exists")
        environment["DISPLAY"] = ":0"
        environment["XAUTHORITY"] = str(auth_files[0])
    return environment


def guarded_command(
    profile: pathlib.Path,
    reaper_arguments: list[str],
    timeout_seconds: int,
) -> list[str]:
    cpu = max(os.sched_getaffinity(0))
    cpu_seconds = max(5, min(timeout_seconds, 30))
    unit = f"m3-poly-guarded-{os.getpid()}"
    return [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--collect",
        "--quiet",
        f"--unit={unit}",
        "--property=MemoryHigh=384M",
        "--property=MemoryMax=512M",
        "--property=MemorySwapMax=64M",
        "--property=CPUQuota=50%",
        "--property=CPUWeight=10",
        "--property=IOWeight=10",
        "--property=TasksMax=32",
        "--",
        "/usr/bin/timeout",
        "--signal=TERM",
        "--kill-after=5s",
        f"{timeout_seconds}s",
        "/usr/bin/prlimit",
        "--core=0:0",
        "--nice=0:0",
        "--rtprio=0:0",
        f"--cpu={cpu_seconds}:{cpu_seconds}",
        "--nofile=4096:4096",
        "--",
        "/usr/bin/nice",
        "-n",
        "10",
        "/usr/bin/ionice",
        "-c",
        "3",
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        str(REAPER),
        "-newinst",
        "-cfgfile",
        str(profile),
        "-nosplash",
        *reaper_arguments,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run only disposable REAPER under hard limits")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--profile", type=pathlib.Path)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--available-mib", type=float)
    parser.add_argument("--load-one", type=float)
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("reaper_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    available_mib = (
        args.available_mib if args.available_mib is not None else available_memory_mib()
    )
    load_one = args.load_one if args.load_one is not None else os.getloadavg()[0]
    temperature_c = (
        args.temperature_c
        if args.temperature_c is not None
        else maximum_temperature_c()
    )
    errors = preflight_errors(available_mib, load_one, temperature_c)
    if errors:
        print("guardrail refusal: " + "; ".join(errors), file=sys.stderr)
        return 2

    temperature_text = "unavailable" if temperature_c is None else f"{temperature_c:.1f} C"
    print(
        "guardrail preflight: ok "
        f"(available={available_mib:.0f} MiB, load1={load_one:.2f}, temp={temperature_text})"
    )
    if args.check_only:
        return 0

    if args.profile is None:
        parser.error("--profile is required unless --check-only is used")
    profile = args.profile.resolve()
    if profile != DISPOSABLE_PROFILE:
        print(f"guardrail refusal: non-disposable profile: {profile}", file=sys.stderr)
        return 2
    if not profile.is_file():
        print(f"guardrail refusal: disposable profile is missing: {profile}", file=sys.stderr)
        return 2
    if not REAPER.is_file() or not os.access(REAPER, os.X_OK):
        print(f"guardrail refusal: REAPER executable is unusable: {REAPER}", file=sys.stderr)
        return 2
    if not 1 <= args.timeout_seconds <= 300:
        print("guardrail refusal: timeout must be between 1 and 300 seconds", file=sys.stderr)
        return 2

    reaper_arguments = list(args.reaper_args)
    if reaper_arguments[:1] == ["--"]:
        reaper_arguments = reaper_arguments[1:]
    forbidden = {"-cfgfile", "-nonewinst"}
    if any(argument.lower() in forbidden for argument in reaper_arguments):
        print("guardrail refusal: REAPER arguments may not override instance/profile isolation", file=sys.stderr)
        return 2

    command = guarded_command(profile, reaper_arguments, args.timeout_seconds)
    if args.dry_run:
        print(shlex.join(command))
        return 0

    try:
        completed = subprocess.run(command, env=runtime_environment(args.gui), check=False)
    except (OSError, RuntimeError) as exc:
        print(f"guardrail refusal: {exc}", file=sys.stderr)
        return 2
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
