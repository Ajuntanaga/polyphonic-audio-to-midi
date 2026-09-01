# V4 Disposable REAPER VST3 Scan-Isolation Design

Date: 2026-08-31
Status: proposed offline architecture; Task 0A sealed, Task 0B limited to documentation/read-only inventory, and Task 0B source authoring, namespace, and host execution blocked; no REAPER launch authority
Scope: a future one-row VST3 capability diagnostic only

## 1. Authority and non-goals

This design responds to the preserved v3 scan-containment breach. It defines
offline implementation and review work only. It does not authorize a REAPER
launch, retry v1/v2/v3, alter their profiles/caches/markers/evidence, change a
live profile or project, change `HOME`, install software, enable MCP, or start
Task 16.

Any eventual host request must name the single v4 row, all v4 roots, the exact
isolation mechanism, workspace 5, unchanged resource ceilings, telemetry,
one-shot sealing, and the no-retry result. Offline tests and a clean design
review do not grant that authority.

This is scan-path containment, not a claim that an arbitrary third-party
plug-in is fully sandboxed against the real X server. The parent GUI guard
continues to own workspace 5 and its cleanup boundary.

## 2. Trigger evidence

The sealed v3 profile was staged with one exact build-local `vstpath`, but
REAPER later persisted that path followed by `~/.vst3`, and its VST cache
records the external yabridge `ATONE.vst3` bundle. The evidence is preserved;
it is not rewritten or treated as a timeout cause.

`-cfgfile` selects an alternate resource directory, not a proven scan sandbox.
REAPER 7.79 includes a portable-first-run prompt for system VST/CLAP/LV2 paths,
which is a plausible explanation for the appended user path but not proof of
the precise internal branch. No local command-line option or `reaper.ini` key
has been established that prevents this behavior while preserving `HOME`.

The current post-exit profile/cache check detects a breach after it may already
have happened. It is therefore corroboration, not pre-launch containment.

## 3. Required v4 topology

V4 is a new, one-row namespace. Its roots are fixed, mutually distinct, absent
before first write, and contain no symlink component:

| Purpose | Fixed v4 path |
| --- | --- |
| Disposable profile root | `build/reaper-test-v4-scan-isolated` |
| Staged result directory | `build/reaper-test-v4-scan-isolated/test-results` |
| Trusted control root | `build/reaper-test-v4-scan-isolated-control` |
| Trusted namespace receipt | `build/reaper-test-v4-scan-isolated-control/namespace-receipt.json` |
| Disposable project | `build/vst3-capability-v4-scan-isolated.RPP` |
| Evidence batches | `build/test-results/native-vst3-probe-v4-scan-isolated/batches` |
| Attempt lock | `build/.native-vst3-probe-v4-scan-isolated.lock` |
| Private in-sandbox VST3 root | `/opt/m3-vst3-probe` |

The outer V4 controller, which remains outside the systemd scope, is the sole
control-dirfd owner and the only artifact writer. It first opens the trusted
repository root directory, then `build`, with `O_DIRECTORY|O_NOFOLLOW` and
retains/revalidates both identities. Only then does it create the external
attempt lock with no-follow exclusive creation relative to the held `build`
dirfd. While that lock is held it repeats all freshness checks, creates the
control root with `mkdirat`, and reopens it with `O_DIRECTORY|O_NOFOLLOW`.
It retains the resulting control-dir descriptor and device/inode identity until
final sealing. The following parent-written-only artifacts are addressed
relative to that descriptor, never by a re-resolved path. Before each final
write, the controller revalidates the held control-root identity against the
held `build` dirfd. The descriptor is `CLOEXEC`, is never passed into the
systemd scope, and is therefore unavailable to Bubblewrap and REAPER. V4 must
not derive any of these paths from `completion_file`:

```text
namespace-receipt.json
.native-vst3-user-scope-exit-confirmed.json
.native-vst3-termination-unconfirmed.json
.native-vst3-namespace-uncertain.json
```

`phase.log` remains disposable staged-profile output. It is not a trusted V4
control artifact because the profile is writable inside the namespace.

The v4 row is exactly 44.1 kHz/block 32. It cannot call the v2 matrix, v3
diagnostic, check/adoption/recovery paths, or any tail. v1/v2/v3 roots are
preservation-only and are never mounted read-write inside v4.

### 3.1 Two-phase runtime-manifest prerequisite

Phase A may implement only a **non-admissible** protocol/barrier skeleton: a
canonical frame envelope, base-identity/config grammar, proc-barrier primitive,
and unit tests. It deliberately does not define a PRE/POST receipt payload
schema or exchange validator. It must not import `subprocess` or a
runner/collector adapter; define a `ChildRunner`, control-descriptor API,
default/fallback runner, or admission entrypoint; execute at import time;
dynamically import a launcher; or directly call `os.system`, `os.popen`,
`fork*`, `posix_spawn*`, `spawn*`, or `exec*`. It is structurally unable to
emit PRE/POST or consume an ACK, so it cannot treat configuration claims as
measured namespace evidence. Phase A tests prove that even an all-true
configuration has no admission path and enforce exact public-API and
safe-top-level source allowlists. Its source files and hashes are immutable
inputs. Their transitive Python/import/extension closure remains unresolved
until a separately authorized Task 0B2 invocation applies the reviewed
closure-construction method and seals the complete combined closure; Task 0B
may not alter the source component
or introduce a second skeleton with new runtime imports.

Phase B is two distinct immutable artifacts, never one overloaded "host"
manifest:

1. A **fixture-runtime-manifest** is safety-only. It covers the sealed Task 0A
   skeleton plus the exact receipt-schema, measured-collector, and child-adapter
   source/runtime closure needed for one bounded non-REAPER fixture. It may be
   intentionally incompatible with REAPER, and must never be named or consumed
   as host-compatibility evidence.
2. A **reaper-host-runtime-manifest** references that fixture manifest and adds
   every regular read-only source needed for the one V4 host row: REAPER,
   libSwell, the ELF interpreter, every recursive/dynamic REAPER/libSwell/probe
   GUI dependency, and the complete Python closure. Only this second artifact
   can become compatibility-complete.

The prerequisite before Task 0B source authoring is the separately reviewed,
non-executing method at
`docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`.
It deterministically defines how the source import graph, extension modules,
ELF dependencies, loader inputs, resource budgets, and unresolved branches are
recorded and rejected. Until a new explicit offline Task 0B1 authorization,
Task 0B permits documentation and read-only inventory only; it
does not permit authoring the static closure constructor, measured namespace
collectors, exact PRE/POST receipt-schema/exchange module, or sole process
adapter. When authorized, those four modules must be authored without
invocation. The static closure constructor is build-time provenance only and
never a fixture mount; the reviewed Task 0B0 method must seal the complete Task
0A plus Task 0B1 runtime Python, extension, and ELF closure in a successor
referencing the immutable skeleton source component. The receipt module extends
the sealed envelope/base-identity API; it is not a second skeleton. A separate
explicit offline Task 0B2 authorization is required before the constructor may
be tested or invoked against sealed static inputs. That task remains data-only:
it excludes target import/execution/loading, namespace or fixture creation,
Bubblewrap/systemd/REAPER command formation, GUI/X11/audio/network access, and
all host action. Its reviewed output is only a prerequisite to consider a later
fixture-manifest review, never fixture or host authority.

Every regular manifest entry must record source, destination, file kind, mode,
device/inode, byte size, SHA-256, descriptor mount primitive, and reason.
Before a fixture or host row, its manifest must also declare and preflight the
regular-entry count, source-FD count, total `--ro-bind-data` copy bytes, largest
regular entry, and explicit `RLIMIT_NOFILE` headroom. It must refuse if any
observed value exceeds its declared maximum or the required FDs plus headroom
do not fit the soft limit. The conservative copy-byte total and declared
writable-tree/launcher overhead must fit the unchanged `MemoryHigh`/`MemoryMax`
and tmpfs limits before execution. Socket and writable-directory entries use
the separate identity rules in Section 4.1, not an impossible content hash.

The V4 RPP, ReaScript, private Xauthority copy, and writable staging tree are a
separate immutable **run-input manifest** made in Task 2; it references, but
never mutates, the reaper-host-runtime-manifest.

The current static inventory is deliberately neither fixture-complete nor
compatibility-complete: the Task 0A Python closure remains an unresolved static
overapproximation; REAPER/libSwell dynamically loads GUI/audio/install
components; and the current non-GUI process has no `DISPLAY` or `XAUTHORITY`.
Until a future, separately authorized activity resolves those gaps, this design
is a documented safety boundary rather than fixture or host implementation
authority.

## 4. Selected containment architecture

The trusted process chain is:

```text
outer V4 controller (sole control-dirfd owner and artifact writer)
  -> in-process guard verifies scope state and returns GuardedV4Outcome
    -> systemd-run --user --scope (existing limits and workspace guard)
      -> timeout / prlimit / nice / ionice / taskset
        -> trusted v4 launcher (opens only runtime/input FDs)
          -> bwrap (mandatory private filesystem namespace)
            -> v4 namespace attester
              -> REAPER --newinst --noactivate --cfgfile <v4 profile>
            <- framed attester stdout / bounded stderr <-
  <- GuardedV4Outcome (scope status and bounded frames) <-
```

The guard forwards no control-directory descriptor: controller dirfds are
`CLOEXEC`, every scope/wrapper `Popen` uses `close_fds=True` and `pass_fds=()`,
and fixtures inspect descendant descriptor tables. It preserves and bounds the
attester's standard streams through the exact systemd/wrapper chain, verifies
scope-wide TERM/KILL and exit, and returns a structured outcome to the outer
controller. The controller validates that outcome and frames before writing any
control artifact by dirfd. The systemd scope remains outside Bubblewrap so it
owns Bubblewrap, the attester, REAPER, and all descendants. Existing scope-wide
TERM/KILL, process-census, and workspace-5 behavior remains mandatory.

### 4.1 Mandatory Bubblewrap boundary

`/usr/bin/bwrap` version `0.11.1` is a current-host observation, not a portable
assumption. Before and after each future use, the trusted launcher validates
the raw path and every ancestor, regular-file type, root ownership, mode
`0755`, absence of setuid/setgid bits, absence of capabilities, device/inode,
SHA-256 `0abea81db798ebf6b4742ac0664802d97521547a353c2a0dbdc21d76cbbfd2c0`,
and the exact version-command exit/stdout/stderr under `env={}` and a bounded
timeout. Any identity drift, missing tool, unexpected version, namespace
failure, or unsandboxed fallback refuses before REAPER. It uses the following
explicit non-try options rather than `--unshare-all`, whose implementation may
imply try-mode namespaces:

```text
--unshare-user
--unshare-ipc
--unshare-pid
--unshare-net
--unshare-uts
--unshare-cgroup
--disable-userns
--assert-userns-disabled
--die-with-parent
--new-session
--clearenv
```

The outer `Popen` uses the absolute binary, `env={}`, `stdin=PIPE`,
`stdout=PIPE`, bounded `stderr=PIPE`, `close_fds=True`, and in `pass_fds` only
the exact descriptor set for manifest-approved regular snapshots and declared
nonregular anchors. It includes the probe, REAPER, libraries, Python closure,
attester source, RPP, ReaScript, and private Xauthority once those inputs
exist. No pathname read-only bind is permitted. Each regular source is opened
with `O_RDONLY|O_NOFOLLOW`, validated as a one-link regular file, hashed from
that descriptor, rewound, and mounted only with `--ro-bind-data` at its
declared mode. The attester compares in-namespace contents to the manifest
before `PRE`; a pathname replacement or same-inode mutation after validation
therefore cannot alter an admitted run. Descriptor-budget exhaustion is a
refusal, never a broad-bind fallback.

Non-TTY streams prevent `--dev /dev` from inheriting a host terminal as
`/dev/console`; the attester must prove that `/dev/snd` and a host console are
absent. `--clearenv` is still required inside Bubblewrap because it controls
the attester/REAPER environment, but it cannot protect Bubblewrap itself from
inherited dynamic-loader state.

The trusted launcher derives the approved `HOME` value from
`pwd.getpwuid(os.getuid()).pw_dir`, rejects a missing/relative/dot-component
value, and rejects any incoming `HOME` that differs byte-for-byte. It supplies
only `HOME`, `PWD`, `DISPLAY`, private-path `XAUTHORITY`, approved locale
variables, and approved `TZ`, then uses both `--setenv PWD <approved-home>`
and `--chdir <approved-home>`. The attester requires both
`os.environ["PWD"] == HOME` and `os.getcwd() == HOME`. It passes no `VST_PATH`,
`VST3_PATH`, `CLAP_PATH`, session D-Bus, `XDG_RUNTIME_DIR`, network
configuration, or audio-device path. Mapping the approved value to a private
mount is not a `HOME` override.

Manifest entries are type-specific. A regular read-only file has source/dest,
mode, device/inode, SHA-256, and a source FD used by `--ro-bind-data`. A
declared in-namespace symlink has a literal target that resolves only inside
the namespace and no host source. The exact X11 Unix socket has no content
hash; it requires `DISPLAY`, raw source path, socket type, owner/mode,
device/inode, and an `O_PATH|O_NOFOLLOW` anchor FD. Bubblewrap mounts it only
from that inherited anchor via its own `/proc/self/fd/<n>` path; the attester
compares the mounted socket identity to the manifest before `PRE`. A writable
profile/results directory is created fresh under a retained safe parent dirfd
with exact owner/mode/no-symlink/tree rules, opened with an anchored directory
FD, and bind-mounted only from that anchor. The fixture must prove both anchor
mount primitives resist replacement between validation and bind; if either is
unsupported, V4 refuses. Any kind mismatch or identity drift is failure.

The namespace starts from a private root. It does not `--ro-bind / /`, bind the
real home directory, bind the whole repository, bind `/usr/local`, or expose a
full build VST3 root. It mounts only:

- a committed, descriptor-checked manifest of individual REAPER runtime files,
  dynamic-loader files, libraries, and configuration files, read-only; it does
  not bind `/usr`, `/lib`, `/lib64`, or another broad runtime directory;
- the exact disposable RPP and ReaScript, read-only;
- the v4 profile root and staged result path, read-write; and
- a minimal `/dev`, private `/proc`, and the exact X11 socket/Xauthority file
  required for the parent workspace guard; and
- an empty private mount at the unchanged `$HOME` path, including empty
  `$HOME/.vst` and `$HOME/.vst3` directories.

Final batch evidence and the trusted control root are never mounted in
Bubblewrap. The parent copies staged result files only after scope exit and
trusted receipt validation.

The exact argv orders all ancestor creation before descendants, creates the
private home before any mount below it, adds every runtime/profile/project/X11
mount before the probe root is frozen, then creates the private scan root,
adds exactly two `--ro-bind-data` files, applies `--remount-ro` to that root,
and only then adds `--proc /proc`, `--dev /dev`, and `-- <attester argv>`.
It never uses `--tmpfs /`; Bubblewrap already begins with an empty root and a
late root mount would hide earlier `/proc` and `/dev` mounts. Nothing may mount
at or below the scan root after `--remount-ro`.

The runtime manifest contains no VST2/VST3/CLAP/LV2 tree. The fixture plants
canaries in every known user, system, multiarch, and share-based default root
for all four plug-in formats and proves every canary is absent inside the
namespace. This is corroboration, not a finite claim to enumerate every
possible path: the primary proof is an empty private root and an exact
mount-source allowlist. Any new manifest entry or candidate root requires a
design amendment and review.

### 4.2 Descriptor-pinned private scan root

Only the capability probe bundle is needed. The production bundle is absent.
The two probe files are an exact subset of the full regular-file snapshot set
defined in Section 4.1. Before Bubblewrap begins, the trusted parent opens
these two source files with `O_RDONLY|O_NOFOLLOW`, verifies a regular file,
expected SHA-256, and expected source identity, then passes their inherited
descriptors to Bubblewrap along with the separately enumerated runtime/input
snapshot descriptors:

```text
/opt/m3-vst3-probe/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/
  Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so
  Contents/Resources/moduleinfo.json
```

The trusted launcher opens every snapshot descriptor after it is inside the
resource scope, reads/hashes it, rewinds it with `os.lseek`, and starts
Bubblewrap with `close_fds=True` plus exactly the manifest tuple in `pass_fds`.
It closes parent copies immediately after a successful `Popen` and closes any
remaining descriptors on every error path. Bubblewrap consumes the data FDs
for `--ro-bind-data`; the attester must prove all source FDs are absent from
its own descriptor table. The source tree is not visible at the private scan
root, so pathname replacement after validation cannot change the copied
contents. A pre-ACK in-namespace hash catches an in-place mutation of the same
source inode before Bubblewrap consumes it; the post-run hash proves the
admitted snapshot did not change during the child.

Bubblewrap first mounts `/opt/m3-vst3-probe` as a private tmpfs, creates only
the required parent directories, adds the two `--ro-bind-data` files with
explicit modes, and then `--remount-ro /opt/m3-vst3-probe`. Because that
remount is non-recursive, the attester verifies in `/proc/self/mountinfo` that
the scan-root mount and both descendant file mounts are read-only and that no
later mount appears below that root. The staged v4 `vstpath` is the private
in-sandbox path `/opt/m3-vst3-probe`, never the host build VST3 directory. The
attester walks this root both before and after REAPER and rejects create,
rename, unlink, or extra-entry changes.

### 4.3 Same-namespace attestation and admission

The attester runs inside the same Bubblewrap invocation as REAPER. Standard
streams, not an arbitrary inherited descriptor, form the control channel:

```text
trusted parent stdin  -> attester fd 0: one admission ACK
attester fd 1         -> trusted parent stdout: framed receipts
attester/bwrap fd 2   -> trusted parent stderr: bounded diagnostics
```

The outer parent invokes Bubblewrap with pipes for these standard streams,
while Bubblewrap passes them to the attester. Before it emits `PRE`, the
attester must establish and attest a proc/ptrace barrier: successful
`PR_SET_DUMPABLE=0`, empty effective/permitted/inheritable/ambient capability
sets, and a fixture-proven refusal to open the attester's receipt endpoint or
memory through `/proc/<attester-pid>/fd/1` and `/proc/<attester-pid>/mem`.
Failure to establish or prove that barrier is namespace uncertainty and starts
no child. The attester emits `PRE` only after the barrier, then waits for one
exact ACK on fd 0. Only after the parent validates `PRE` does it write that ACK
and close its write end. The attester retains fd 1 across the REAPER child, but
starts REAPER with stdin/stdout/stderr all directed to `DEVNULL`,
`close_fds=True`, and `pass_fds=()`. The proc/ptrace barrier, together with
those standard-stream settings, prevents REAPER from receiving or reopening
admission/receipt control. After the child exits, the attester emits `POST` and
closes fd 1.

Every frame has a fixed 16-byte header containing magic, schema version, type
(`PRE=1` or `POST=2`), sequence, and big-endian payload length. Payloads are
canonical UTF-8 JSON, at most 2 KiB, and each full frame is no larger than the
queried `PIPE_BUF`. The only accepted exchange is `PRE(seq=0)`, one ACK,
`POST(seq=1, terminal=true)`, then EOF. Duplicate or extra data, a bad
sequence, malformed or oversize JSON, missing EOF, diagnostics overflow,
timeout, or a nonce/config/input mismatch is namespace uncertainty. A failed
`PRE` receives no ACK and starts no REAPER child.

The in-scope launcher and attester retain validated `PRE` only in memory until
a matching terminal `POST` arrives, then relay those bounded raw frames and
receipt state to the outer controller. They receive no `V4ControlPaths`,
control-root descriptor, or control-artifact pathname. The outer controller,
after independently validating the returned `GuardedV4Outcome`, is the only
receipt-file writer. It writes `namespace-receipt.json` without replacement:
no-follow temporary file in the retained control root, `fsync` contents, atomic
no-replace commit, cleanup, and directory `fsync`. Readers use `O_NOFOLLOW`,
`fstat` for a one-link regular file, a bounded read, and exact
schema/key/content validation. A sandboxed REAPER process cannot forge, unlink,
or replace the control receipt. An incomplete, linked, malformed, missing,
stale, or out-of-sequence receipt is failure.

The receipt contains schema/version, v4 namespace name, sample rate/block
size, exact input hashes, sealed host-runtime and run-input manifest digests,
the original/in-sandbox `HOME`/`PWD` strings and working directory, Bubblewrap
identity and complete-argv digest, exact private scan-root entries/hashes,
production-bundle absence, empty private defaults, mount/environment and
proc/ptrace-barrier assertions, and pre/post timestamps with child PID/return
code. `PRE` also contains a fresh nonce, namespace/config digest, and a
no-child-started assertion. `POST` repeats the nonce/config digest and adds
post-walk assertions. The parent independently records its Bubblewrap argv
digest and timestamps; it does not accept a receipt merely because it
self-asserts parent-owned values.

It must fail before REAPER starts if any preflight condition differs. It must
not invoke a second Bubblewrap or make an unsandboxed child process. A timeout
or kill can leave only a pre-receipt; the trusted parent records that state as
infrastructure-invalid evidence, not retry authority.

### 4.4 Acceptance after exit

V4 uses a retained-dirfd `V4ControlPaths`, not generic completion-file-derived
marker helpers. All scope receipts, terminal namespace receipts, and markers
are created/read/linked relative to that verified descriptor. The existing
scope-exit receipt, unconfirmed marker, outer timeout, and REAPER-PID census
all remain gates, but their V4 artifacts are written only under the external
control root by the outer controller after a validated `GuardedV4Outcome`; the
guard and all scope descendants write no control artifact. A v4 row may be
classified only after:

1. a clean guarded return and positively confirmed disposable scope exit;
2. an available zero-REAPER post-exit census;
3. a valid terminal parent-owned namespace receipt matching the staged inputs;
4. no external teardown or namespace-uncertainty marker; and
5. only then, a cache containing the probe bundle and allowed host effects and
   a profile whose `vstpath` is exactly the private scan root, optionally
   followed by the exact private `~/.vst3` suffix recorded by the receipt.

Any cache/profile discrepancy, receipt uncertainty, scope uncertainty,
namespace failure, process-census failure, telemetry failure, timeout, or
unexpected external-bundle observation seals the one v4 row as
`infrastructure-invalid`, preserves its evidence and lock, and prevents any
retry or tail. Before the first four gates pass, the guard and runner perform
no normal cache/profile acceptance scan.

## 5. Offline acceptance criteria

Implementation is not complete until offline tests prove all of the following:

1. exact v4 roots and row only; all aliases, prior artifacts, symlink
   components, cross-namespace roots, and matrix/tail routes refuse before any
   write or child process;
2. a missing/wrong/unsafe Bubblewrap identity, failed explicit namespace,
   altered `HOME`/`PWD`, inherited loader environment, missing descriptors,
   source-file symlink, pathname replacement, same-inode mutation of any
   regular runtime/input source, socket/directory identity drift, extra
   probe-root entry, production bundle, writable scan root, forged receipt, or
   unsandboxed fallback refuses before REAPER;
3. an actual non-REAPER Bubblewrap fixture sees the exact unchanged `HOME`, a
   private empty default VST path, the exact descriptor-backed probe files, no
   fixture VST2/VST3/CLAP/LV2 canary, and a read-only scan root that rejects
   create, rename, unlink, and extra-entry injection;
4. a child cannot start before a parent-validated `PRE` and ACK; malformed,
   duplicate, oversized, out-of-order, pre-only, linked, stale, or nonterminal
   namespace receipts prevent normal cache/profile acceptance; a fixture child
   cannot read attester memory or reopen/inject through its receipt endpoint;
5. a private `~/.vst3` suffix is accepted only with a matching trusted receipt;
   otherwise the same suffix is a containment failure; and
6. control-root artifacts are invisible from the namespace, only the parent
   can write them through a retained dirfd despite path rename/replacement, and
   an external scope/namespace uncertainty retains the v4 lock and prevents a
   normal scan; and
7. existing v1/v2/v3 paths, metadata, manifests, and behavior remain
   byte-identical except for the deliberately added v4 code/tests/docs.

The implementation must retain current low-priority testing and resource
limits. It creates no service, daemon, autostart entry, install, or persistent
plug-in path.

## 6. Known limits and fresh authorization gate

The local Bubblewrap feasibility probe proved only the mechanism: an unchanged
`HOME` string can resolve to a private mount that hides the host `~/.vst3`,
while a selected repository path remains read-only. It did not launch REAPER,
exercise X11, or prove dynamic-library compatibility.

Exposing X11 necessarily leaves a real-desktop interaction surface. This design
makes no hostile-plug-in security claim and does not claim an X server sandbox.
Xvfb/Xephyr are not installed and must not be installed merely to broaden this
boundary.

Only after all offline criteria pass and an independent review is clean may a
new, explicit user request be considered for exactly one v4 host row. A failed
first v4 host row remains a sealed result and never becomes retry authority.
