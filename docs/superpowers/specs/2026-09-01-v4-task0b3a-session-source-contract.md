# V4 Task 0B3a — Session Source Authoring Contract

**Status:** user-authorized source-only task; implementation not yet reviewed

**Authority:** the user's 2026-09-01 `Resume` authorizes only the authoring and
static source verification described here. It does not authorize importing,
compiling, calling, or behavior-testing the session or any Task 0A/0B1 module;
nor a fixture, namespace, Bubblewrap/systemd/REAPER command, GUI/X11/audio,
network, or host action.

This contract implements the design-only decision in
`docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md`. That
design remains binding wherever this document is shorter.

## Scope and non-goals

The exact implementation artifacts are:

1. `tools/reaper_v4_session.py`; and
2. `tests/test_reaper_v4_task0b3a_static_contract.py`.

This document, the Task 0B3 plan/status entries, `RESUME.md`, and the
human-facing vault may be updated only to record this source-only checkpoint.
No Task 0A or Task 0B1 source/schema/fixture may change. No runtime closure,
fixture manifest, host manifest, control-root artifact, or executable command
is created by this task.

The static test reads source/JSON bytes and parses AST only. It must never
import, compile, or execute the new module or a Task 0A/0B1 component. A green
static test is structural evidence only; it is not a PRE/ACK/POST, descriptor,
child, fixture, scope, REAPER, or compatibility result.

## Source boundary

`tools/reaper_v4_session.py` is the one future runtime-root module. Its later
closure identity is:

```text
kind = "session_entrypoint"
role = "same_namespace_pre_ack_child_post_owner"
```

It has no `__main__`, CLI parser, ambient command-line fallback, top-level
call, top-level resource read, or import-time process/namespace action. A
later reviewed execution-surface task must bind the fixed
`/run/m3-v4/session-config.json` and `/run/m3-v4/session-config.sha256` paths;
this author-only task does not form that command.

This module is the sole **in-namespace state-machine root**, not a standalone
executable. A later, separately authorized execution-surface gate may invoke
only `run_session(load_session_config(fixed_config_path, fixed_digest_path))`.
That source-free transport bootstrap may not admit policy, read/write a control
artifact, construct a child, emit a receipt, or become a second coordinator or
runtime root; its exact launcher identity must be policy-bound and independently
reviewed before it exists. Its sole permitted exception boundary is
`except SessionError: raise SystemExit(1)`: it must emit no text, suppress the
interpreter traceback, and leave the session's at-most-one diagnostic as the
only possible stderr content. This task neither chooses nor forms that command.

The exact literal public API is:

```python
__all__ = (
    "SessionError",
    "SessionConfig",
    "SessionResult",
    "load_session_config",
    "run_session",
)
```

| Symbol | Contract |
| --- | --- |
| `SessionError` | `RuntimeError` subclass for every local fail-closed condition. |
| `SessionConfig` | Frozen, validator-created snapshot with `data: Mapping[str, object]`; direct construction is forbidden. |
| `SessionResult` | Frozen terminal in-memory summary with exactly `child_pid`, `child_returncode`, `pre_monotonic_ns`, and `post_monotonic_ns`. It makes no scope-exit, PID-census, receipt-persistence, scan, or row-acceptance claim. |
| `load_session_config(config_path: str, digest_path: str) -> SessionConfig` | Accepts only the two exact fixed configuration paths, reads the digest sidecar and JSON once each with bounded no-follow regular-file paths, snapshots the JSON before validation, and admits only the closed SessionConfig from Task 0B3. |
| `run_session(config: SessionConfig) -> SessionResult` | The only future state-machine owner: configuration admission → barrier/provenance preflight → PRE → raw ACK+EOF → one child → post checks → POST+EOF. It has no alternate sender, runner, or control channel. |

`SessionConfig` and `SessionResult` use only the exact
`@dataclasses.dataclass(frozen=True, init=False)` decorator. Their only
admitted construction is through private in-module factories after validation;
an uninitialized direct class construction is never a usable `SessionConfig`,
and `run_session` rejects it. All public functions have no default or
keyword-default argument. No public or private function exposes a partial
PRE/POST writer, ACK reader, child admission method, controller artifact
method, or retry/fallback path.

The only literal configuration paths are:

```text
/run/m3-v4/session-config.json
/run/m3-v4/session-config.sha256
```

The latter contains the final configuration digest as exactly 64 lower-case
hexadecimal bytes with no newline. It is a parent-retained descriptor-pinned
bootstrap anchor, not a receipt input, direct-input digest, session-policy
member, or digest-valued argv value. That separation prevents the config
digest from becoming recursive. The sidecar detects config/sidecar disagreement;
the parent-retained descriptor-pinned source identity, not local equality,
prevents a paired substituted config/sidecar mount.

The source also has one private literal diagnostic code set:

```python
DIAGNOSTIC_CODES = (
    "config",
    "preflight",
    "pre_write",
    "ack",
    "child",
    "post",
)
```

It may emit at most one of these printable-ASCII codes on fd 2 under the fixed
diagnostic byte budget. No diagnostic code carries an admitted value, path,
frame, child output, or control artifact.

The first failure selects the only diagnostic, encoded as the bare ASCII code
with no newline in one best-effort write: `config` for either bootstrap file or
SessionConfig admission; `preflight` for barrier, evidence, descriptor, mount,
or PRE-payload failure; `pre_write` for PRE encode/write failure; `ack` for raw
ACK/EOF uncertainty; `child` for child launch, timeout, or cleanup uncertainty;
and `post` for every post-child recheck, exchange, encode, or POST-write
failure. A later error never replaces an already selected code.

Before it opens either bootstrap path, `load_session_config` performs one
`fstat` on fd 2, requires a pipe/FIFO, and sets it nonblocking. Setup failure
is silent and aborts before either bootstrap read. After successful setup, a diagnostic is one nonblocking write
attempt only; short write, interruption, `EAGAIN`, or any other error is
ignored without retry. The static verifier must require this setup before any
bootstrap-file open or diagnostic write, so a malformed sidecar cannot block on
stderr. `run_session` repeats the same bounded fd-2 setup at its own entry and
never retains or reads module-level diagnostic readiness; its setup failure is
also silent and disables diagnostics only for that call, while its mandatory
descriptor-policy preflight still decides whether it may proceed.

## Exact imports and forbidden capabilities

The source may import only:

```python
import dataclasses
import hashlib
import json
import os
import select
import stat
import time
import types
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
from tools import reaper_v4_child_runner as child_runner
from tools import reaper_v4_measurements as measurements
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema
```

The runtime imports are declaration-only in this task; the static test does
not execute them. `attester.establish_protocol_barrier` is the existing Task
0A barrier primitive even though its module is named `reaper_v4_attester`.

The source must not import or call `subprocess`, `ctypes`, `importlib`,
`runpy`, `pathlib`, `socket`, `asyncio`, `sys`, `shutil`, `glob`, a control
root/controller module, Bubblewrap, systemd, REAPER, GUI, X11, audio, network,
or a loader API. It must not use `exec`, `eval`, `compile`, `__import__`,
`getattr`, `os.system`, `os.popen`, `os.posix_spawn*`, or any `spawn*`,
`fork*`, or `exec*` call. The only eventual child launch is delegated to
`child_runner.run_child` after raw ACK EOF validation.

## Admitted evidence boundary

`SessionConfig` must admit the closed `namespace_expectations` projection from
Task 0B3 exactly as written. No receipt fact may be synthesized from a Boolean
in configuration alone. The future source must derive each required fact from
the following bounded inputs only:

| Fact or precondition | Required admitted input and local evidence |
| --- | --- |
| Configuration identity | The two fixed bootstrap paths; sidecar bytes must equal the embedded and recomputed configuration digest. The parent-held source identity remains the proof against a same-byte host-path replacement. |
| User namespace | Exact `user_namespace` ID-map records, effective IDs, `setgroups`, and matching policy digest; read only the exact `/proc/self/uid_map`, `/proc/self/gid_map`, and `/proc/self/setgroups` paths later authorized for the non-REAPER fixture. |
| Private home / VST emptiness | Exact `private_tree.home_mount` projection and the closed `empty_directories` list. No ambient home, recursive walk, or inferred default path is permitted. |
| Production-bundle absence and scan facts | The two exact `scan_root.entries`, their direct-input bindings, and exact read-only `mount_points`; retain the opened scan-root identity/baseline in memory from before PRE through post-child recheck. |
| X11 receipt projection | Parent-only source identity plus no-follow destination authority mode/size/hash checks and a retained destination dev/inode baseline; `O_PATH|O_NOFOLLOW` socket opening with `stat.S_ISSOCK` then owner/mode/device/inode checks; then emit only the immutable Task 0B1 five-field projection. |
| Source-FD and control visibility | Exact initial `descriptor_policy.inherited_fds`, rehashed FD/mount policy preimages, the complete bounded `control_visibility.mounts` projection, the closed `namespace_root_kind`, and the parent-validated full certificate records. The source must never receive or name a host control-root path. |
| Barrier / proc claims | The Task 0A barrier result plus the parent-validated proc/ptrace certificate identity. |

The richer expectations are part of the exact session-policy projection and
therefore change the Task 0A base identity when altered. The bootstrap pair is
the sole exception: it is retained and mounted by the parent outside every
SessionConfig-derived digest, to avoid a recursive hash. A later fixture gate,
not this source-only task, must prove the actual `/proc`, mountinfo, X11,
descriptor, tree, and sidecar behavior.

The authored source must name and apply these fixed resource ceilings before it
opens or hashes the corresponding object: SessionConfig 8,192 bytes/256
nodes/depth 16; sidecar 64 bytes; mountinfo 64 KiB/128 records; inherited FD
census 16 entries; each UID/GID map at most eight 256-byte records; Xauthority
64 KiB; each scan entry 16 MiB; total scan entries 32 MiB; and all regular-file
hash reads in 64 KiB chunks. A syntactically valid but oversized expectation is
rejected before that object is read in full. The static verifier must assert
these literals and the absence of an unbounded whole-file read helper. It must
also assert the Task 0B3 exact node/depth charge traversal, absolute-path
component-wise no-follow helper, mountinfo escape decoder, and `stat.S_IMODE`
mode comparisons rather than leave any of those definitions to implementation
policy.

## Required authored semantics

The source body must encode, but this task must not execute, all of the
following fail-closed relations:

1. Canonical SessionConfig has the exact top-level/nested shape, byte/node/
   depth/ASCII limits, fixed limits record, sidecar relationship, and SHA-256
   relationships specified by Task 0B3. It rejects duplicate JSON keys,
   non-built-in containers, Booleans in integer fields, extra keys,
   empty/mismatched direct-input maps, noncanonical sidecar bytes, and every
   path except the two fixed configuration paths.
2. `session_policy_sha256` is recomputed from the exact policy projection.
   `namespace_policy_sha256` is separately recomputed from the exact
   `namespace_expectations` projection and must match both certificate records.
   `base_config.inputs` is exactly the canonical union of
   `direct_input_digests` plus `session_policy`; Task 0A validates the resulting
   base identity before a PRE can exist.
3. The session calls the barrier before PRE construction; it derives each
   receipt assertion from the exact admitted-evidence table above and the Task
   0B3 provenance table, never an open self-asserted Boolean map. Parent-owned
   manifest/Bubblewrap/certificate values are copied only from admitted
   configuration. It rehashes the two complete certificate records and binds
   their fixed result, manifests, Bubblewrap, user-map, mount, and FD-policy
   applicability fields before the outer parent independently rechecks them.
4. Fd 0/1 pipe validation, `PIPE_BUF`, nonblocking deadline handling, one
   complete PRE write, bounded stderr, exact ACK byte plus observable EOF, one
   child, post root recheck, relational `validate_exchange`, one complete POST
   write, and stdout EOF are all represented in the sole `run_session` flow.
   Every uncertain path raises `SessionError` before child or after PRE with no
   POST, as appropriate.
5. The child environment is exactly the ordered tuple for `DISPLAY`, `HOME`,
   `LANG`, `PWD`, `TZ`, and `XAUTHORITY`; it has byte-identical admitted values,
   `PWD == HOME`, and exact `child.timeout_ms == 30000`. `run_session` builds
   one `child_runner.ChildSpec` and delegates to exactly one
   `child_runner.run_child` call.
6. The existing measurement collector is limited to its explicit plan. The
   session retains/rechecks the same manifest-bound measurement root identity
   and its separately observed scan-root baseline around the child. Before POST
   it also rechecks private HOME/VST emptiness, the in-namespace Xauthority
   destination baseline and socket identity, the complete mount projection, and
   inherited-FD policy; it does not compare a copied authority destination to
   its parent-only source device/inode, treat mode/size facts as universal
   mount/tree/X11/control proof, or reuse a stale PRE Boolean.
7. A timed-out child, a child-launch exception, cleanup uncertainty, a
   signal-terminated child (`ChildOutcome.returncode < 0`), failed post
   measurement, failed exchange validation, or raw transport error cannot emit
   POST or classify a row. The static verifier must require the negative
   return-code guard before every post path. The outer controller remains
   responsible for scope-wide teardown, census, durable receipt/marker writing,
   and final acceptance.

The session source may have private helpers only to make these relationships
legible. They must stay closure-covered implementation detail, not a second
runtime root or separately callable admission surface.

The deadline origins are fixed rather than inferred at runtime:

- `pre_deadline_ms` begins on `run_session` entry and covers provenance
  preflight through the one complete PRE write;
- `ack_deadline_ms` begins only after that complete PRE write and ends with the
  exact ACK byte plus observable EOF;
- `child_timeout_ms` is passed unchanged to the one admitted `ChildSpec`; and
- `post_deadline_ms` begins only after a non-timeout direct child outcome has
  been reaped, then covers every post-child identity/measurement check,
  `validate_exchange`, and the one complete POST write.

Expiry at any point is uncertainty, not a retry. A child timeout or cleanup
uncertainty suppresses POST before the post deadline can begin.

## Task 1: Source-only authoring and static contract

1. Add the source and a pre-import AST/hash test. The initial static test must
   fail because the source does not yet exist or fails its exact shape.
2. Author the source without importing, compiling, or invoking it. The source
   hash is pinned in the static test only after the authored source is final.
3. Run only the static test with `python3 -B`; it may parse/read source bytes
   but must import no target module. Do not run `py_compile`, any component
   unit test, or the repository suite in this task.
4. Check whitespace. A self-review and an independent task review must both
   verify source-contract compliance and task quality before checkpointing.

The static test must prove before target import:

- the exact session source path and its final SHA-256; repository-level file
  ownership remains a separate diff/review check;
- exact module imports, `__all__`, class/function/constant shape, no function
  decorators/default arguments, and only the two exact frozen-dataclass
  decorators described above;
- only the five declared `tools.*` dependencies; no controller/closure
  constructor dependency;
- no `__main__`, CLI, top-level executable expression/resource access, dynamic
  import, direct process capability, or network/namespace/host integration;
- single-flow source intent: barrier precedes PRE write; ACK EOF precedes
  `ChildSpec`/`run_child`; `validate_exchange` precedes POST write; and no
  source branch writes a durable control artifact; and
- the source names both fixed SessionConfig bootstrap paths, fixed limits,
  fixed diagnostic codes, deadline origins, fixed six-key child environment,
  direct-input/policy binding, the exact admitted-evidence keys, and Task 0B3
  root role; and
- no all-true receipt map, host control-root path, unbound scan entry, or
  ambient user-map/X11/mount/descriptor evidence path exists.

The test must not claim these structural checks prove runtime order, deadline,
pipe, descriptor, certificate, mount, cleanup, child, or REAPER behavior.

## Later gates retained

After this author-only task, the separate Task 0B3b/c/d, Task 0B4, graph
construction, closure, fixture-manifest, and host-manifest gates from Task
0B3 remain required. A static green result here does not advance any of them.
