#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import signal
import shlex
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
REAPER = pathlib.Path("/home/ajuntanaga/opt/REAPER/reaper")
DISPOSABLE_PROFILE = (ROOT / "build/reaper-test/reaper.ini").resolve()
OBSERVER_DIAGNOSTIC_PROFILE = ROOT / "build/reaper-test-observer-diagnostic/reaper.ini"
BUILD_CLAP_DIR = (ROOT / "build/native/clap").resolve()
PROBE_ARTIFACT = (
    BUILD_CLAP_DIR / "M3_Polyphonic_Audio_to_MIDI_Probe.clap"
).resolve()
PROBE_REPORT = (
    ROOT / "build/reaper-test/test-results/probe-native.tsv"
).resolve()
BUILD_VST3_DIR = (ROOT / "build/vst3/release/VST3").resolve()
PROBE_VST3_BUNDLE = (
    BUILD_VST3_DIR / "M3_Polyphonic_Audio_to_MIDI_Probe.vst3"
).resolve()
PROBE_VST3_BINARY = (
    PROBE_VST3_BUNDLE
    / "Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so"
).resolve()
PROBE_VST3_MODULEINFO = (
    PROBE_VST3_BUNDLE / "Contents/Resources/moduleinfo.json"
).resolve()
PROBE_VST3_FUID = "6F62F8B1B8A14872A0D92C3C274421D8"
PROBE_VST3_NAME = "M3 Polyphonic Audio to MIDI Probe"
LIVE_REAPER_PROFILE = (pathlib.Path.home() / ".config/REAPER").resolve()
COMPLETION_FILE = (
    ROOT / "build/reaper-test/test-results/phase.log"
).resolve()
OBSERVER_DIAGNOSTIC_COMPLETION_FILE = (
    ROOT / "build/reaper-test-observer-diagnostic/test-results/phase.log"
)
OBSERVER_DIAGNOSTIC_PROJECT = (
    ROOT
    / "build/native-vst3-probe-v3-observer-diagnostic-projects/"
    "M3-Native-VST3-44100-32.RPP"
)
OBSERVER_DIAGNOSTIC_SCRIPT = (
    ROOT
    / "build/reaper-test-observer-diagnostic/Scripts/tests/"
    "ajuntanaga_M3 Native VST3 Capability.lua"
)
COMPLETION_SENTINEL = "suite-finish"
COMPLETION_GRACE_SECONDS = 0.75
MIN_AVAILABLE_MIB = 4096.0
MAX_LOAD_ONE = 12.0
MAX_TEMPERATURE_C = 90.0
MAX_CPU_SECONDS = 45
WMCTRL = pathlib.Path("/usr/bin/wmctrl")
PLUGIN_INJECTION_ENVIRONMENT = (
    "CLAP_PATH",
    "VST_PATH",
    "VST3_PATH",
    "M3_CLAP_PROBE_REPORT",
)


def path_has_symlink_component(path: pathlib.Path) -> bool:
    candidate = path if path.is_absolute() else pathlib.Path.cwd() / path
    while True:
        if candidate.is_symlink():
            return True
        if candidate == candidate.parent:
            return False
        candidate = candidate.parent


def disposable_vst3_profiles() -> tuple[pathlib.Path, pathlib.Path]:
    return DISPOSABLE_PROFILE, OBSERVER_DIAGNOSTIC_PROFILE


def completion_file_for_profile(profile: pathlib.Path) -> pathlib.Path | None:
    if profile == DISPOSABLE_PROFILE:
        return COMPLETION_FILE
    if profile == OBSERVER_DIAGNOSTIC_PROFILE:
        return OBSERVER_DIAGNOSTIC_COMPLETION_FILE
    return None


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


def validate_native_clap_environment(
    clap_path: pathlib.Path,
    probe_report: pathlib.Path,
    profile: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    resolved_profile = profile.resolve()
    if resolved_profile != DISPOSABLE_PROFILE:
        raise ValueError(
            f"native CLAP injection requires the disposable profile: {resolved_profile}"
        )
    resolved_clap = clap_path.resolve()
    if resolved_clap != BUILD_CLAP_DIR or not resolved_clap.is_dir():
        raise ValueError(
            f"unexpected build-local CLAP path: {resolved_clap}; "
            f"required {BUILD_CLAP_DIR}"
        )
    if not PROBE_ARTIFACT.is_file():
        raise ValueError(f"probe artifact is missing: {PROBE_ARTIFACT}")
    resolved_artifact = PROBE_ARTIFACT.resolve()
    if BUILD_CLAP_DIR not in resolved_artifact.parents:
        raise ValueError(
            f"probe artifact escapes the build-local CLAP directory: {resolved_artifact}"
        )
    resolved_report = probe_report.resolve()
    if resolved_report != PROBE_REPORT:
        raise ValueError(
            f"unexpected probe report path: {resolved_report}; required {PROBE_REPORT}"
        )
    return resolved_clap, resolved_report


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _normalize_fuid(value: object) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", str(value)).upper()


def validate_native_vst3_environment(
    vst3_path: pathlib.Path,
    profile: pathlib.Path,
) -> pathlib.Path:
    resolved_profile = profile.resolve(strict=False)
    if (
        path_has_symlink_component(profile)
        or resolved_profile not in disposable_vst3_profiles()
        or not resolved_profile.is_file()
    ):
        raise ValueError(
            f"native VST3 injection requires the disposable profile: "
            f"{resolved_profile}"
        )

    if vst3_path.is_symlink():
        raise ValueError("build-local VST3 path is a symlink")
    resolved_vst3 = vst3_path.resolve(strict=False)
    if resolved_vst3 != BUILD_VST3_DIR or not resolved_vst3.is_dir():
        raise ValueError(
            f"unexpected build-local VST3 path: {resolved_vst3}; "
            f"required {BUILD_VST3_DIR}"
        )

    bundle = PROBE_VST3_BUNDLE
    binary = PROBE_VST3_BINARY
    moduleinfo = PROBE_VST3_MODULEINFO
    expected_files = {
        binary.relative_to(bundle).as_posix(),
        moduleinfo.relative_to(bundle).as_posix(),
    }
    if (
        bundle.is_symlink()
        or not bundle.is_dir()
        or bundle.parent.resolve(strict=False) != resolved_vst3
        or not _inside(bundle, resolved_vst3)
    ):
        raise ValueError(f"probe VST3 bundle is missing, a symlink, or escapes: {bundle}")

    actual_files: set[str] = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                f"probe VST3 member is a symlink or escapes: "
                f"{path.relative_to(bundle)}"
            )
        if path.is_file():
            if not _inside(path, bundle):
                raise ValueError(
                    f"probe VST3 member is a symlink or escapes: "
                    f"{path.relative_to(bundle)}"
                )
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != expected_files:
        raise ValueError("probe VST3 bundle file set is not exact")
    if not binary.is_file() or binary.is_symlink() or not _inside(binary, bundle):
        raise ValueError("probe VST3 binary is missing, a symlink or escapes")
    if (
        not moduleinfo.is_file()
        or moduleinfo.is_symlink()
        or not _inside(moduleinfo, bundle)
    ):
        raise ValueError("probe VST3 module-info is missing, a symlink or escapes")

    try:
        source = moduleinfo.read_text(encoding="utf-8")
        document = json.loads(re.sub(r",(\s*[}\]])", r"\1", source))
        classes = document["Classes"]
        class_info = classes[0]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"probe VST3 module-info is invalid: {exc}") from exc
    if not isinstance(classes, list) or len(classes) != 1 or not isinstance(
        class_info, dict
    ):
        raise ValueError("probe VST3 module-info must contain exactly one class")
    if _normalize_fuid(class_info.get("CID")) != PROBE_VST3_FUID:
        raise ValueError("probe VST3 module-info FUID is not the probe identity")
    if (
        class_info.get("Name") != PROBE_VST3_NAME
        or class_info.get("Category") != "Audio Module Class"
        or class_info.get("Sub Categories") != ["Fx", "Tools"]
    ):
        raise ValueError("probe VST3 module-info class metadata is not exact")
    factory = document.get("Factory Info")
    if not isinstance(factory, dict) or factory.get("Vendor") != "ajuntanaga":
        raise ValueError("probe VST3 module-info factory metadata is not exact")

    try:
        profile_text = resolved_profile.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"disposable profile is unreadable: {exc}") from exc
    scan_rows = [
        line
        for line in profile_text.splitlines()
        if line.lower().startswith("vstpath")
    ]
    if scan_rows != [f"vstpath={resolved_vst3}"]:
        raise ValueError(
            "disposable profile VST scan path is not the exact build-local root"
        )
    lowered_profile = profile_text.lower()
    if (
        str(LIVE_REAPER_PROFILE).lower() in lowered_profile
        or "clap_path" in lowered_profile
    ):
        raise ValueError("disposable profile references a live or CLAP path")
    return resolved_vst3


def overrides_instance_isolation(argument: str) -> bool:
    normalized = argument.lower()
    return any(
        normalized == flag or normalized.startswith(f"{flag}=")
        for flag in ("-nonewinst", "--nonewinst", "-cfgfile", "--cfgfile")
    )


def completion_published(path: pathlib.Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return False
    return bool(lines) and lines[-1] == COMPLETION_SENTINEL


def sanitize_plugin_environment(environment: dict[str, str]) -> dict[str, str]:
    sanitized = environment.copy()
    for name in PLUGIN_INJECTION_ENVIRONMENT:
        sanitized.pop(name, None)
    return sanitized


def runtime_environment(gui: bool) -> dict[str, str]:
    uid = os.getuid()
    runtime = pathlib.Path(f"/run/user/{uid}")
    bus = runtime / "bus"
    if not bus.exists():
        raise RuntimeError(f"user session bus is unavailable: {bus}")

    environment = sanitize_plugin_environment(dict(os.environ))
    environment["XDG_RUNTIME_DIR"] = str(runtime)
    environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"

    if gui:
        auth_files = sorted(runtime.glob(".mutter-Xwaylandauth.*"))
        if not auth_files:
            raise RuntimeError("guarded GUI requested but no Mutter Xwayland authority exists")
        environment["DISPLAY"] = ":0"
        environment["XAUTHORITY"] = str(auth_files[0])
    return environment


def workspace_index(workspace_number: int) -> int:
    if workspace_number < 1:
        raise ValueError("workspace numbers are one-based and must be positive")
    return workspace_number - 1


def transient_window_listing_error(stderr: str) -> bool:
    return "BadWindow" in stderr or "BadDrawable" in stderr


def move_reaper_windows_once(
    environment: dict[str, str],
    workspace_number: int,
    background: bool = False,
    excluded_window_ids: set[str] | None = None,
) -> int:
    target = str(workspace_index(workspace_number))
    excluded = excluded_window_ids or set()
    listing = None
    for attempt in range(3):
        listing = subprocess.run(
            [str(WMCTRL), "-l", "-x"],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if listing.returncode == 0:
            break
        if not transient_window_listing_error(listing.stderr) or attempt == 2:
            break
        time.sleep(0.02)
    assert listing is not None
    if listing.returncode != 0:
        if transient_window_listing_error(listing.stderr):
            return 0
        detail = listing.stderr.strip() or f"exit status {listing.returncode}"
        raise RuntimeError(f"could not list GUI windows: {detail}")

    placed = 0
    for line in listing.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) < 4 or fields[2].lower() != "reaper.reaper":
            continue
        window_id, current_desktop = fields[0], fields[1]
        if window_id in excluded:
            continue
        touched = False
        if background:
            result = subprocess.run(
                [str(WMCTRL), "-ir", window_id, "-b", "add,hidden"],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or f"exit status {result.returncode}"
                raise RuntimeError(
                    f"could not background REAPER window {window_id}: {detail}"
                )
            touched = True
        if current_desktop == target:
            if touched:
                placed += 1
            continue
        result = subprocess.run(
            [str(WMCTRL), "-ir", window_id, "-t", target],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            raise RuntimeError(
                f"could not move REAPER window {window_id} to workspace "
                f"{workspace_number}: {detail}"
            )
        touched = True
        if touched:
            placed += 1
    return placed


def reaper_window_ids(environment: dict[str, str]) -> set[str]:
    listing = None
    for attempt in range(3):
        listing = subprocess.run(
            [str(WMCTRL), "-l", "-x"],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if listing.returncode == 0:
            break
        if not transient_window_listing_error(listing.stderr) or attempt == 2:
            break
        time.sleep(0.02)
    assert listing is not None
    if listing.returncode != 0:
        detail = listing.stderr.strip() or f"exit status {listing.returncode}"
        raise RuntimeError(f"could not snapshot existing REAPER windows: {detail}")

    window_ids = set()
    for line in listing.stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) >= 4 and fields[2].lower() == "reaper.reaper":
            window_ids.add(fields[0])
    return window_ids


def _workspace_state(listing_text: str) -> tuple[set[int], int]:
    indices: set[int] = set()
    active: list[int] = []
    for line in listing_text.splitlines():
        fields = line.split()
        if len(fields) < 2 or not fields[0].isdigit():
            continue
        index = int(fields[0])
        indices.add(index)
        if fields[1] == "*":
            active.append(index)
    if len(active) != 1:
        raise RuntimeError(
            "could not identify exactly one active workspace; refusing GUI launch"
        )
    return indices, active[0]


def _workspace_listing(environment: dict[str, str]) -> str:
    listing = subprocess.run(
        [str(WMCTRL), "-d"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        detail = listing.stderr.strip() or f"exit status {listing.returncode}"
        raise RuntimeError(f"could not list workspaces: {detail}")
    return listing.stdout


def active_workspace_index(environment: dict[str, str]) -> int:
    _, active = _workspace_state(_workspace_listing(environment))
    return active


def restore_launch_workspace(
    environment: dict[str, str],
    original_workspace: int,
    target_workspace: int,
) -> bool:
    if original_workspace == target_workspace:
        return False
    if active_workspace_index(environment) != target_workspace:
        return False
    restored = subprocess.run(
        [str(WMCTRL), "-s", str(original_workspace)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if restored.returncode != 0:
        detail = restored.stderr.strip() or f"exit status {restored.returncode}"
        raise RuntimeError(
            f"could not restore workspace {original_workspace + 1}: {detail}"
        )
    return True


def settle_launch_workspace(
    environment: dict[str, str],
    original_workspace: int,
    target_workspace: int,
    polls: int = 10,
    interval_seconds: float = 0.05,
) -> int:
    if original_workspace == target_workspace:
        return 0
    poll_count = max(1, polls)
    restored_count = 0
    for poll_index in range(poll_count):
        if restore_launch_workspace(
            environment,
            original_workspace,
            target_workspace,
        ):
            restored_count += 1
        if poll_index + 1 < poll_count and interval_seconds > 0:
            time.sleep(interval_seconds)
    return restored_count


def require_workspace(environment: dict[str, str], workspace_number: int) -> int:
    if not WMCTRL.is_file() or not os.access(WMCTRL, os.X_OK):
        raise RuntimeError(f"workspace guard is unavailable: {WMCTRL}")
    target = workspace_index(workspace_number)
    indices, active = _workspace_state(_workspace_listing(environment))
    if target not in indices:
        raise RuntimeError(
            f"workspace {workspace_number} is unavailable; refusing to open REAPER"
        )
    return active


def stop_process_group(process: subprocess.Popen[bytes], first_signal: int) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, first_signal)
        process.wait(timeout=5)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass


def run_gui_guarded(
    command: list[str],
    environment: dict[str, str],
    workspace_number: int,
    completion_file: pathlib.Path | None = None,
) -> int:
    original_workspace = require_workspace(environment, workspace_number)
    target_workspace = workspace_index(workspace_number)
    preexisting_reaper_windows = reaper_window_ids(environment)
    preserve_until = time.monotonic() + 3.0

    def preserve_launch_focus() -> None:
        if time.monotonic() <= preserve_until:
            restore_launch_workspace(
                environment,
                original_workspace,
                target_workspace,
            )

    def finish(result: int) -> int:
        settle_launch_workspace(
            environment,
            original_workspace,
            target_workspace,
        )
        return result

    process = subprocess.Popen(
        command,
        env=environment,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        while process.poll() is None:
            move_reaper_windows_once(
                environment,
                workspace_number,
                background=True,
                excluded_window_ids=preexisting_reaper_windows,
            )
            preserve_launch_focus()
            if completion_file is not None and completion_published(completion_file):
                try:
                    result = process.wait(timeout=COMPLETION_GRACE_SECONDS)
                    return finish(result)
                except subprocess.TimeoutExpired:
                    stop_process_group(process, signal.SIGTERM)
                    print(
                        "guarded REAPER completion observed; "
                        "closed disposable instance after grace period"
                    )
                    return finish(0)
            try:
                poll_seconds = 0.02 if time.monotonic() <= preserve_until else 0.10
                result = process.wait(timeout=poll_seconds)
                preserve_launch_focus()
                return finish(result)
            except subprocess.TimeoutExpired:
                pass
        preserve_launch_focus()
        return finish(process.returncode)
    except KeyboardInterrupt:
        stop_process_group(process, signal.SIGINT)
        raise
    except (OSError, RuntimeError):
        stop_process_group(process, signal.SIGTERM)
        raise


def guarded_command(
    profile: pathlib.Path,
    reaper_arguments: list[str],
    timeout_seconds: int,
    clap_path: pathlib.Path | None = None,
    probe_report: pathlib.Path | None = None,
    vst3_path: pathlib.Path | None = None,
) -> list[str]:
    if vst3_path is not None and (clap_path is not None or probe_report is not None):
        raise ValueError("CLAP and VST3 injection are mutually exclusive")
    cpu = max(os.sched_getaffinity(0))
    cpu_seconds = max(5, min(timeout_seconds, MAX_CPU_SECONDS))
    unit = f"m3-poly-guarded-{os.getpid()}"
    systemd_options = [
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
        "--property=TasksMax=64",
    ]
    if clap_path is not None:
        systemd_options.append(f"--setenv=CLAP_PATH={clap_path}")
    if probe_report is not None:
        systemd_options.append(f"--setenv=M3_CLAP_PROBE_REPORT={probe_report}")
    return [
        *systemd_options,
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
        "-noactivate",
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
    parser.add_argument("--workspace", type=int, default=5)
    parser.add_argument("--profile", type=pathlib.Path)
    parser.add_argument("--clap-path", type=pathlib.Path)
    parser.add_argument("--probe-report", type=pathlib.Path)
    parser.add_argument("--vst3-path", type=pathlib.Path)
    parser.add_argument("--completion-file", type=pathlib.Path)
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
    if path_has_symlink_component(args.profile):
        print(
            f"guardrail refusal: disposable profile path is symlinked: "
            f"{args.profile}",
            file=sys.stderr,
        )
        return 2
    profile = args.profile.resolve()
    if profile not in disposable_vst3_profiles():
        print(f"guardrail refusal: non-disposable profile: {profile}", file=sys.stderr)
        return 2
    if not profile.is_file():
        print(f"guardrail refusal: disposable profile is missing: {profile}", file=sys.stderr)
        return 2
    clap_path = None
    probe_report = None
    vst3_path = None
    if args.vst3_path is not None and (
        args.clap_path is not None or args.probe_report is not None
    ):
        print(
            "guardrail refusal: CLAP and VST3 injection are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    if args.clap_path is not None or args.probe_report is not None:
        if args.clap_path is None or args.probe_report is None:
            print(
                "guardrail refusal: --clap-path and --probe-report must be used together",
                file=sys.stderr,
            )
            return 2
        try:
            clap_path, probe_report = validate_native_clap_environment(
                args.clap_path,
                args.probe_report,
                profile,
            )
        except ValueError as exc:
            print(f"guardrail refusal: {exc}", file=sys.stderr)
            return 2
    if args.vst3_path is not None:
        try:
            vst3_path = validate_native_vst3_environment(
                args.vst3_path,
                profile,
            )
        except ValueError as exc:
            print(f"guardrail refusal: {exc}", file=sys.stderr)
            return 2
    if not REAPER.is_file() or not os.access(REAPER, os.X_OK):
        print(f"guardrail refusal: REAPER executable is unusable: {REAPER}", file=sys.stderr)
        return 2
    completion_file = None
    if args.completion_file is not None:
        if path_has_symlink_component(args.completion_file):
            print(
                f"guardrail refusal: completion file path is symlinked: "
                f"{args.completion_file}",
                file=sys.stderr,
            )
            return 2
        completion_file = args.completion_file.resolve()
        if completion_file != completion_file_for_profile(profile):
            print(
                f"guardrail refusal: unexpected completion file: {completion_file}",
                file=sys.stderr,
            )
            return 2
        if not args.gui:
            print(
                "guardrail refusal: completion monitoring requires --gui",
                file=sys.stderr,
            )
            return 2
    if not 1 <= args.timeout_seconds <= 300:
        print(
            "guardrail refusal: timeout must be between 1 and 300 seconds",
            file=sys.stderr,
        )
        return 2
    if not 1 <= args.workspace <= 32:
        print("guardrail refusal: workspace must be between 1 and 32", file=sys.stderr)
        return 2

    reaper_arguments = list(args.reaper_args)
    if reaper_arguments[:1] == ["--"]:
        reaper_arguments = reaper_arguments[1:]
    if any(overrides_instance_isolation(argument) for argument in reaper_arguments):
        print(
            "guardrail refusal: REAPER arguments may not override "
            "instance/profile isolation",
            file=sys.stderr,
        )
        return 2
    if profile == OBSERVER_DIAGNOSTIC_PROFILE:
        if not args.gui or completion_file is None or vst3_path is None:
            print(
                "guardrail refusal: observer diagnostic requires GUI, exact "
                "completion monitoring, and VST3 injection",
                file=sys.stderr,
            )
            return 2
        if args.workspace != 5 or args.timeout_seconds != 45:
            print(
                "guardrail refusal: observer diagnostic requires workspace 5 "
                "and a 45-second limit",
                file=sys.stderr,
            )
            return 2
        if reaper_arguments != [
            str(OBSERVER_DIAGNOSTIC_PROJECT),
            str(OBSERVER_DIAGNOSTIC_SCRIPT),
        ]:
            print(
                "guardrail refusal: observer diagnostic REAPER arguments are "
                "not the fixed one-row script",
                file=sys.stderr,
            )
            return 2

    command = guarded_command(
        profile,
        reaper_arguments,
        args.timeout_seconds,
        clap_path,
        probe_report,
        vst3_path,
    )
    if args.dry_run:
        if args.gui:
            print(f"guarded GUI workspace: {args.workspace}")
        if completion_file is not None:
            print(f"guarded completion file: {completion_file}")
        if clap_path is not None:
            print(f"guarded CLAP path: {clap_path}")
            print(f"guarded probe report: {probe_report}")
        if vst3_path is not None:
            print(f"guarded VST3 profile path: {vst3_path}")
        print(shlex.join(command))
        return 0

    if completion_file is not None:
        try:
            completion_file.unlink(missing_ok=True)
        except OSError as exc:
            print(
                f"guardrail refusal: could not clear completion file: {exc}",
                file=sys.stderr,
            )
            return 2

    try:
        environment = runtime_environment(args.gui)
        if args.gui:
            return run_gui_guarded(
                command,
                environment,
                args.workspace,
                completion_file,
            )
        completed = subprocess.run(command, env=environment, check=False)
    except KeyboardInterrupt:
        print("guarded REAPER interrupted", file=sys.stderr)
        return 130
    except (OSError, RuntimeError) as exc:
        print(f"guardrail refusal: {exc}", file=sys.stderr)
        return 2
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
