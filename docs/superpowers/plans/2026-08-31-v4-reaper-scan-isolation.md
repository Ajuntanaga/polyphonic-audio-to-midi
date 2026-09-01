# V4 Disposable REAPER Scan-Isolation Implementation Plan

Status: V4 host execution blocked; Task 0A is sealed, and Task 0B permits documentation/read-only inventory only. Task 0B source authoring requires a new explicit offline Task 0B1 authorization.
Date: 2026-08-31
Spec: docs/superpowers/specs/2026-08-31-v4-reaper-scan-isolation-design.md
Inventory: docs/superpowers/specs/2026-08-31-v4-reaper-runtime-inventory.md
Closure method: docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md

## Goal

Build and offline-verify a fail-closed Bubblewrap boundary for one future V4
REAPER VST3 diagnostic row: 44.1 kHz / block 32. The boundary must make only
the two descriptor-pinned probe files visible to REAPER's plug-in scan, while
preserving the host HOME string and keeping all trusted receipts and
termination markers outside the namespace.

This plan does not authorize a REAPER launch. V1, V2, and V3 evidence remain
sealed and untouched. A V4 host row needs separate fresh user authority after
all offline work and independent review are complete.

## Non-negotiable constraints

- Only Task 0A non-admissible protocol/barrier code may begin before a reviewed
  manifest. It must not import process-launch code or call Bubblewrap,
  `subprocess`, REAPER, systemd, or create a namespace. It has no `__main__`,
  no dynamic/lazy launcher import, no descriptor-control API, no `ChildRunner`,
  and no direct `os.system`, `os.popen`, `fork*`, `posix_spawn*`, `spawn*`, or
  `exec*` call. It is structurally unable to emit PRE/POST, consume an ACK, or
  start a child: measured collectors and admission do not exist until Task 0B
  is complete and independently reviewed.
- No REAPER, audio, or GUI launch occurs during plan execution or tests.
- The only candidate bundle is the probe. The production VST3 bundle, host
  build VST3 directory, live home VST3 directory, and all VST2/CLAP/LV2 roots
  are absent.
- Preserve the exact HOME string from pwd.getpwuid(os.getuid()).pw_dir. A
  private mount at that string is permitted; changing the string is not.
- Use only /usr/bin/bwrap with the verified identity recorded in the inventory.
  No unsandboxed fallback, --unshare-all, --*-try, --share-net, duplicate
  namespace override, --cap-add, broad runtime bind, or whole-home/repository
  bind is permitted.
- The outer process uses env={}, non-TTY pipes or DEVNULL, close_fds=True, and
  exact descriptor handoff for every regular read-only runtime/input source.
  The nested REAPER child gets only DEVNULL standard streams, no inherited
  control descriptor, and must fail a proc/ptrace receipt-reopen fixture.
- Retain workspace 5, one core, 50% CPU, 384/512 MiB high/max memory, 64 MiB
  swap, 64 tasks, existing systemd scope receipts, outer 60-second guard, and
  low CPU/I/O priority.
- Every test command runs with ionice -c 3 nice -n 10.

## Proposed files and ownership

| File | Responsibility |
| --- | --- |
| tools/reaper_v4_protocol.py | source-only canonical frame envelope and base-identity grammar only |
| tools/reaper_v4_attester.py | non-admissible config/barrier primitives; no receipt or child API |
| tests/test_reaper_v4_protocol.py | source-only frame, barrier, and no-admission/no-child regression coverage |
| tools/reaper_v4_closure_constructor.py | Task 0B1-only build-time static data parser/resolver; never imports or executes a target module and is never a fixture mount |
| tools/reaper_v4_measurements.py | Task 0B1-only measured namespace collectors, authored only after the closure method and explicit offline authority |
| tools/reaper_v4_receipt_schema.py | Task 0B1-only exact PRE/POST/exchange grammar, authored only after the closure method and explicit offline authority |
| tools/reaper_v4_child_runner.py | Task 0B1-only process adapter; the sole module allowed to import `subprocess` |
| tools/reaper_v4_namespace.py | immutable data types and Bubblewrap argv grammar |
| tools/reaper_v4_launcher.py | trusted parent identity checks, descriptor pinning, standard-stream admission/receipt protocol |
| tests/test_reaper_v4_namespace.py | unit and non-REAPER Bubblewrap fixture coverage |
| tools/stage_reaper_test_env.py | V4-only profile with /opt/m3-vst3-probe |
| tools/run_guarded_reaper.py | outer scope chain, V4 control-root routing, post-exit guard gates |
| tools/run_native_vst3_probe.py | fresh V4 one-row dispatch, evidence, lock, and no-retry sealing |
| tests/test_guarded_reaper.py | V4 scope, receipt, and cache refusal coverage |
| tests/test_native_vst3_probe_runner.py | freshness, routing, evidence, lock, and unchanged V2/V3 coverage |
| tests/test_source_contract.py | static V4 invariant regression coverage |
| RESUME.md, docs/VST3-TESTING.md, Obsidian | offline closure and host-authorization stop |

## Task 0: Establish non-circular manifest gates

### Task 0A: Non-admissible protocol/barrier contract

Status: complete as a non-admissible source component; it provides no
fixture-runtime-manifest, fixture, namespace, or host-execution authority.

Create tools/reaper_v4_protocol.py, tools/reaper_v4_attester.py, and their unit
tests as a complete but **non-admissible** canonical frame-envelope,
base-identity, and barrier skeleton. It parses/rejects malformed frame envelopes
and base configuration, and exposes the mocked-testable `PR_SET_DUMPABLE` /
capability primitive, but it deliberately owns no PRE/POST receipt payload
schema, exchange validator, writer, ACK reader, `ChildRunner`, standard-stream
control object, measured namespace collector, or admission entrypoint. No
configuration, including an all-true fact map, can produce PRE/POST or invoke a
child. Source-contract tests use exact public-API and safe-top-level AST
allowlists alongside forbidden import/call checks; they prove the barrier's
success/refusal behavior and no-admission invariant. The two source hashes are
sealed as the immutable skeleton source component. Their transitive Python,
extension, and ELF closure remains an unresolved Task 0B0 input; it is not a
sealed runtime manifest until the reviewed closure-construction method produces
and verifies the complete combined closure.

~~~bash
ionice -c 3 nice -n 10 python3 -m unittest tests.test_reaper_v4_protocol -v
~~~

### Task 0B: Runtime-manifest gates

Status: **BLOCKED — documentation and read-only inventory only.** The
closure-construction method, manifest split, and resource-budget gates have
independent review; source authoring still requires a new explicit offline Task
0B1 authorization. Do not start namespace execution.

The current inventory identifies direct ELF starting points only. It proves
neither the Task 0A Python closure nor REAPER GUI/runtime compatibility. The
current environment also has no `DISPLAY` or `XAUTHORITY`; unresolved dynamic
paths must remain unresolved rather than being replaced with broad binds.

#### Task 0B0: closure-construction method (complete; documentation-only)

The governing method is
`docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`.
It defines a non-executing immutable closure record from supplied static inputs:
the import graph, extension/ELF traversal, interpreter/loader identity,
conditional-import handling, unresolved-branch refusal, source/extension/ELF
hash records, resource budgets, and reproducible output identity. It must not
form a Bubblewrap command, create a namespace, invoke the adapter, or run
REAPER. Independent review is CLEAN. This does not authorize any of the four
Task 0B1 sources below.

#### Task 0B1: source closure (separate future offline authorization)

After the completed Task 0B0 method and explicit offline authorization, this task
may
author, but not invoke, `tools/reaper_v4_closure_constructor.py`,
`tools/reaper_v4_measurements.py`,
`tools/reaper_v4_receipt_schema.py`, and `tools/reaper_v4_child_runner.py`.
It may also author their exact catalog schemas and synthetic static-data test
fixtures. It does not authorize an invocation of the constructor against Task
0A or Task 0B1 inputs.
The closure constructor parses data only and is the sole source allowed to
produce the static closure record; it must not import, execute, load, or call a
target module or artifact, and its source/parser identities are provenance only
rather than fixture-runtime nodes.
The receipt module is the first code allowed to define exact PRE/POST payload
keys, structured measured facts, and exchange validation; it references the
sealed Task 0A frame/base-identity API. The collector is the first code allowed
to measure exact namespace state. The adapter is the only module allowed to
import `subprocess`, has no import-time side effects, uses DEVNULL standard
streams, `close_fds=True`, and `pass_fds=()`, and returns a bounded
`ChildOutcome`.

#### Task 0B2: static closure construction (separate future offline authorization)

Only after Task 0B1 source/catalog implementation review and another explicit
offline authorization may this task test or invoke the closure constructor
against sealed static inputs. Its invocation may parse only pinned supplied
data; it must not import, execute, load, or call a target module, extension, or
ELF artifact. It also must not create a namespace or fixture, form a
Bubblewrap/systemd/REAPER command, access GUI/X11/audio/network facilities, or
perform any host action. A clean static record and independent review remain
only a precondition to consider a later fixture-manifest review; they do not
authorize that fixture.

Before a fixture, use the reviewed Task 0B0 method to seal the complete Task
0A plus Task 0B1 runtime Python, extension, and ELF closure, including the
three runtime source hashes and `subprocess`/`_posixsubprocess`, in a reviewed
successor that references, but never mutates, the immutable Task 0A source
component. The closure constructor/parser identities bind that record but are
not fixture mounts. This work yields two deliberately separate manifest states:

1. **fixture-runtime-manifest**: the skeleton plus the exact
   receipt-schema/collector/adapter closure and only the entries needed by one
   bounded non-REAPER fixture. It can support a safety property but is never a
   reaper-host-runtime-manifest and must never imply REAPER compatibility.
2. **reaper-host-runtime-manifest**: references the fixture manifest and adds
   every resolved REAPER, libSwell, probe GUI, Python, X11, configuration, and
   dynamic-load entry needed for the exact V4 row. Only this is
   compatibility-complete and eligible for a future host request.

Every regular entry in either manifest has safe raw-path/ancestor checks, mode,
device/inode, byte size, SHA-256, executable/read-only destination, source-FD
snapshot, `--ro-bind-data` rule, and reason. Both manifests declare a maximum
regular-entry count, source-FD count, total data-copy bytes, largest entry,
required `RLIMIT_NOFILE` headroom, and conservative writable-tree/launcher
overhead. Preflight refuses if observed values exceed declared limits, if the
required FDs plus headroom exceed the soft limit, or if the conservative memory
and tmpfs total does not fit the unchanged `MemoryHigh`/`MemoryMax` ceilings.
Every X11 socket has exact DISPLAY/raw path/safe ancestors, socket type,
owner/mode, device/inode, `O_PATH|O_NOFOLLOW` anchor, a pre-ACK in-namespace
identity comparison, and post-run revalidation. Every writable directory has
fresh dirfd creation, owner/mode/no-symlink/tree rules, an anchored directory
FD, and a replacement-resistant bind proof. Neither kind claims a SHA-256.

Exact environment and cwd values are HOME, PWD, DISPLAY, private XAUTHORITY,
approved locale/TZ, and no other key. The argv contains both `--setenv PWD
HOME` and `--chdir HOME`. Exact Bubblewrap argv order, full FD set, symlink
topology, and a no-broad-bind proof are recorded. Dynamic dependencies are
either individually included or remain unresolved. A non-REAPER fixture can
prove a safety property only; it cannot prove a REAPER `dlopen` dependency
unnecessary.

Task 2 creates a separate, sealed run-input manifest for its RPP, ReaScript,
private Xauthority copy, and staged writable tree; it references but never
mutates the reaper-host-runtime-manifest. If any applicable manifest cannot be
established without a host launch, record the gap as blocked and request new
authority rather than guessing a broader bind.

## Task 1: Implement isolated namespace primitives

Prerequisite: Task 0A complete plus a reviewed fixture-runtime-manifest and
explicit authority for the bounded non-REAPER fixture.

Create tools/reaper_v4_namespace.py, tools/reaper_v4_launcher.py, and
tests/test_reaper_v4_namespace.py using test-first development.

~~~python
@dataclasses.dataclass(frozen=True)
class V4ProbeFile:
    source: pathlib.Path
    sandbox_path: pathlib.PurePosixPath
    sha256: str
    mode: int

@dataclasses.dataclass(frozen=True)
class RuntimeRegularFile:
    source: pathlib.Path
    sandbox_path: pathlib.PurePosixPath
    sha256: str
    mode: int

@dataclasses.dataclass(frozen=True)
class RuntimeNonregularEntry:
    kind: Literal["symlink", "x11_socket", "writable_dir"]
    sandbox_path: pathlib.PurePosixPath
    identity: Mapping[str, str | int]

@dataclasses.dataclass(frozen=True)
class V4ControlPaths:
    parent_fd: int
    root_fd: int
    root_dev: int
    root_ino: int
    namespace_receipt_name: str
    scope_exit_receipt_name: str
    teardown_marker_name: str
    namespace_uncertainty_marker_name: str

@dataclasses.dataclass(frozen=True)
class V4NamespaceConfig:
    approved_home: str
    profile_root: pathlib.Path
    project: pathlib.Path
    script: pathlib.Path
    private_scan_root: pathlib.PurePosixPath
    probe_files: tuple[V4ProbeFile, ...]
    runtime_regular_files: tuple[RuntimeRegularFile, ...]
    runtime_nonregular_entries: tuple[RuntimeNonregularEntry, ...]

@dataclasses.dataclass(frozen=True)
class V4LaunchResult:
    returncode: int
    receipt_state: Literal["terminal", "pre-only", "missing", "invalid"]
    receipt_frames: bytes
    diagnostics: bytes

def checked_bwrap_binary(binary: pathlib.Path = pathlib.Path("/usr/bin/bwrap")) -> BwrapIdentity: ...
def open_regular_snapshots(config: V4NamespaceConfig) -> tuple[tuple[RuntimeRegularFile, int], ...]: ...
def open_nonregular_anchors(config: V4NamespaceConfig) -> tuple[tuple[RuntimeNonregularEntry, int], ...]: ...
def acquire_v4_control(lock: V4AttemptLock, roots: V4Roots) -> V4ControlPaths: ...
def build_bwrap_command(config: V4NamespaceConfig, snapshots: tuple[tuple[RuntimeRegularFile, int], ...], anchors: tuple[tuple[RuntimeNonregularEntry, int], ...], child_argv: list[str], environment: Mapping[str, str]) -> list[str]: ...
def validate_config(config: Mapping[str, object]) -> Mapping[str, object]: ...
def establish_protocol_barrier(config: Mapping[str, object]) -> None: ...
def launch_v4_namespace(config: V4NamespaceConfig, child_argv: list[str], environment: Mapping[str, str]) -> V4LaunchResult: ...
~~~

### 1.1 RED tests

Write failing tests before implementation for:

- raw/ancestor symlink, wrong owner/mode/capability, version, digest, inode, or
  post-check identity drift for Bubblewrap;
- an exact argv comparison, not an inclusion check: explicit user/ipc/pid/net/
  uts/cgroup flags, --disable-userns, --assert-userns-disabled,
  --die-with-parent, --new-session, --clearenv, exact HOME/PWD/DISPLAY/
  XAUTHORITY/locale/TZ setenv values, --chdir HOME, and no forbidden or
  duplicate flag and no --tmpfs /;
- every regular runtime/input source has an O_NOFOLLOW source FD with expected
  hash/mode/identity and `--ro-bind-data` mount; test source symlink, pathname
  replacement, missing/extra/prod bundle, wrong mode, FD offset, and
  same-inode mutation after PRE for the REAPER, library, Python, script/RPP,
  Xauthority, and probe categories;
- every X11 socket and writable staging/profile directory has a valid
  O_PATH|O_NOFOLLOW anchor, FD-anchored Bubblewrap bind, pre-ACK in-namespace
  identity comparison, and replacement-between-validation-and-bind refusal;
- standard stream control only: PRE(sequence 0), validated ACK, terminal
  POST(sequence 1), then EOF; malformed, oversized, duplicate, out-of-order,
  pre-only, nonce/config/input mismatch, bad EOF, and diagnostic overflow all
  fail closed;
- no child before the parent ACK; the fixture child receives DEVNULL on
  descriptors 0/1/2 and no receipt/admission/data FD, cannot open/write
  `/proc/<attester-pid>/fd/1`, cannot read `/proc/<attester-pid>/mem`, and the
  non-dumpable capability-free attester still emits POST; and
- lock-before-freshness-recheck, retained control parent/root dirfds, directory
  rename/replacement detection, dirfd-relative no-replace receipt/marker I/O,
  and no control-root path visibility in the namespace.

Run the focused module and confirm its initial missing-module failure.

~~~bash
ionice -c 3 nice -n 10 python3 -m unittest tests.test_reaper_v4_namespace -v
~~~

### 1.2 GREEN implementation and fixture

Implement descriptor pinning for every regular runtime/input source with
os.open(O_RDONLY|O_NOFOLLOW), fstat, regular-file and single-link checks,
hash-from-FD, and rewind. The outer parent starts absolute Bubblewrap with
env={}, pipes for descriptors 0/1/2, close_fds=True, and pass_fds containing
exactly the complete manifest snapshot tuple. It closes source-FD copies
immediately after successful Popen, drains stdout/stderr concurrently with
finite byte/time limits, and seals external uncertainty on any error.

Before emitting PRE, the attester invokes the tested protocol barrier:
PR_SET_DUMPABLE=0 must succeed and all effective/permitted/inheritable/ambient
capability sets must be empty. A failing barrier emits no PRE, receives no ACK,
and starts no child. The implementation is accepted only if the fixture child
cannot use procfd or attester-memory paths to inject a frame while the attester
can still emit POST after that child exits.

Build the argv in this exact logical order:

1. Bubblewrap binary and explicit namespace/no-try flags.
2. --clearenv, exact --setenv HOME/PWD/DISPLAY/XAUTHORITY/locale/TZ whitelist,
   and --chdir HOME.
3. Safe ancestor directories and a mode-0700 private HOME tmpfs, then empty
   .vst and .vst3 under it.
4. Safe runtime/profile/project/script/X11 mount ancestors followed by only
   reviewed manifest entries. Every regular entry uses --ro-bind-data; the X11
   socket and writable directory entries bind only through their inherited
   O_PATH anchors and are reidentified in namespace before PRE.
5. A mode-0755 private /opt/m3-vst3-probe tmpfs, exact bundle ancestors, and
   the two --ro-bind-data probe mounts.
6. --remount-ro /opt/m3-vst3-probe, with nothing later mounted below it.
7. --proc /proc, --dev /dev, --, and the exact attester argv.

The non-REAPER fixture must inspect its own mountinfo and environment, prove
the private home is writable but hides host plug-in roots, prove the scan root
and both file mounts are read-only, reject create/rename/unlink, confirm no
/dev/snd or host console, prove descriptor source FDs are absent in the
attester, verify after-path-replacement plus same-inode-mutation behavior for
all regular source categories, verify FD-anchored socket/directory replacement
resistance and in-namespace identities, and prove the proc/ptrace receipt
barrier.

Run green without REAPER, then commit only the three Task 1 files.

~~~bash
ionice -c 3 nice -n 10 python3 -m unittest tests.test_reaper_v4_namespace -v
~~~

## Task 2: Add fresh V4 staging and evidence routing

Prerequisite: Task 1 green and independently reviewed.

Modify tools/stage_reaper_test_env.py, tools/run_native_vst3_probe.py, and
tests/test_native_vst3_probe_runner.py. Define fixed paths for the new profile,
test-results, control root, terminal receipt, project, batch root, external
lock, and exactly one row SCAN_ISOLATED_V4_ROW = (44100, 32).

A V4 attempt first opens/revalidates a trusted repository dirfd and then its
`build` child with O_DIRECTORY|O_NOFOLLOW. Only relative to that retained
`build` dirfd does it create the external no-follow O_EXCL lock and retain the
lock descriptor. While holding it, it repeats freshness checks for every
leaf/ancestor/symlink and cross-namespace root, creates/opens the new control
root with O_DIRECTORY|O_NOFOLLOW, and retains/rechecks repository/build/control
device/inode identities. All receipt/marker writes use fixed names relative to
the held control dirfd, never a later path lookup. The lock stays outside the
writable profile root, remains on invalid/uncertain result, and is released only
after a clean terminal evidence seal with verified unchanged lock/control
identities.

The V4 profile contains exactly the private scan path and no host VST3 path.
Task 2 seals a separate run-input manifest containing the generated RPP,
ReaScript, private Xauthority copy, regular-file snapshot identities, and
writable-tree identities. It references the immutable reaper-host-runtime-manifest and
cannot modify it. V4 must not call V2/V3 recovery, adoption, dry-run matrix,
or tail routing. The runner receives the retained-dirfd V4ControlPaths, refuses
all control artifacts that are not exact no-follow regular files, and copies the
parent-owned terminal receipt only after scope exit, zero PID census, and clean
guard return. Before those gates it must not invoke normal cache/profile
acceptance scanning.

RED/green tests cover existing root/control/receipt/marker/project/batch/lock,
leaf and ancestor aliases, concurrent attempt/marker insertion, lock-before-
freshness ordering, control-directory rename/replacement, all invalid receipt
states, immutable-host-manifest versus sealed-run-input-manifest separation,
matrix/tail non-entry, V1/V2/V3 byte identity, and no REAPER argv in any
unit-test subprocess. Run focused runner tests and compile checks, then commit
only Task 2 files.

## Task 3: Integrate V4 with the guarded systemd scope

Prerequisite: Task 2 green and independently reviewed. Production V4 command
formation remains a deterministic refusal unless a separately valid,
compatibility-complete reaper-host-runtime-manifest digest is supplied.

~~~python
@dataclasses.dataclass(frozen=True)
class GuardedV4Outcome:
    returncode: int
    scope_unit: str
    scope_exit_confirmed: bool
    attester_stdout: bytes
    diagnostics: bytes
~~~

Modify tools/run_guarded_reaper.py, the V4 runner call site, and focused tests.
The outer V4 controller owns every control dirfd and artifact; neither the
guard nor a scope descendant receives `V4ControlPaths` or writes one. The guard
returns a structured GuardedV4Outcome containing only verified scope state,
bounded raw attester PRE/POST frames, and bounded diagnostics. The controller
validates that outcome before it writes any receipt or marker through its
retained dirfd. Keep
systemd-run --user --scope --collect outermost. It must preserve those standard
streams through the exact timeout/prlimit/nice/ionice/taskset/launcher chain,
proved with a sentinel non-REAPER child. Inside the scope, run only one trusted
launcher, one Bubblewrap process, and one attester. The V4 GUI command must
carry exactly one trusted m3-poly-guarded-positive-pid.scope identity and
reject missing, suffixless, or mismatched units before launch.

The controller, after validating GuardedV4Outcome, writes scope-exit receipt and
termination/namespace uncertainty markers through its external retained-dirfd
V4ControlPaths. Do not use a completion-file-derived location or re-resolve a
control-root path. The normal cache/profile scanner can run only after return
code zero, exact scope exit receipt, no marker, terminal namespace receipt, and
available zero REAPER census. It allows a private .vst3 suffix only when the
terminal receipt proves the private default root was empty. Existing V2/V3 code
remains byte-compatible.

Tests cover scope lifetime, control-artifact noninheritance and dirfd
replacement, GuardedV4Outcome stream preservation, valid/nonzero result,
scope/namespace uncertainty, improper command composition, compatibility-
manifest refusal before any REAPER command is formed, complete regular-source
snapshot set, nonregular-anchor replacement, proc/ptrace receipt barrier,
receipt provenance, external cache/prod-bundle observations, and scan
suppression on every failure. Run guard and runner tests at low priority, then
commit only Task 3 files.

## Task 4: Offline closure and host-authority stop

Prerequisite: Task 3 green and an independent read-only review with no material
findings.

Add source-contract assertions for exact flags/order, no broad bind/fallback,
private HOME/PWD, external control root, standard-stream admission, probe-only
root, every regular source snapshot, type-specific socket/writable-dir rules,
proc/ptrace receipt barrier, V4 row, freshness, lock/no-retry, and V1-V3
preservation. Update RESUME.md, docs/VST3-TESTING.md, and the two Obsidian
records with the exact offline result and an explicit host-execution stop.

Run each command separately:

~~~bash
ionice -c 3 nice -n 10 python3 -m unittest discover -s tests
ionice -c 3 nice -n 10 python3 tools/validate_source.py .
ionice -c 3 nice -n 10 python3 tools/validate_native_source.py .
ionice -c 3 nice -n 10 python3 -m py_compile tools/reaper_v4_protocol.py tools/reaper_v4_attester.py tools/reaper_v4_namespace.py tools/reaper_v4_launcher.py tools/run_guarded_reaper.py tools/run_native_vst3_probe.py
git diff --check
~~~

Verify no REAPER process, V4 batch, or V4 lock remains from fixtures, while
preserved V1-V3 markers/manifests retain their hashes. Commit precise code,
tests, docs, and vault updates only after the full offline result and review.

Stop there. Even a clean fixture-runtime-manifest non-REAPER fixture does not
provide a REAPER compatibility claim. A compatibility-complete
reaper-host-runtime-manifest and
new user request must explicitly authorize exactly one V4 row, all V4 roots,
workspace 5, resource ceilings, telemetry, terminal receipt, one-shot sealing,
and no-retry outcome before any host process is considered.

## Review checklist

An independent reviewer must examine every task boundary for source-only versus
process-launch separation, every regular-source snapshot and nonregular entry
identity, descriptor/source TOCTOU, Bubblewrap argv/mount order, dynamic REAPER
runtime scope, PWD/cwd, proc/ptrace receipt isolation, standard-stream receipt
lifecycle, parent-only dirfd control provenance, scope/cgroup cleanup,
freshness and concurrency, cache scanning order, receipt replay, lock release,
fixture non-REAPER proof, compatibility-versus-safety manifest claims, and
V1-V3 regression risk. Material findings require a focused RED regression
before a green rerun.
