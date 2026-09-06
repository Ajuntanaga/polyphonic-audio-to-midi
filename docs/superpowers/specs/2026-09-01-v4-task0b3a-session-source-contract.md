# V4 Task 0B3a — Non-Admissible Session-Root Skeleton

**Status:** historical non-admissible skeleton checkpoint, superseded by the
reviewed Task 0B4b session source contracts and their replacement static
verification.

**Authority:** the user's 2026-09-01 `Resume` authorizes only the two source
files and the pre-import AST/hash verification described here. It does not
authorize importing, compiling, calling, or behavior-testing the session or any
Task 0A/0B1 module; nor a fixture, namespace, Bubblewrap/systemd/REAPER
command, GUI/X11/audio, network, or host action.

This safety correction replaces the earlier untestable pseudo-runtime source
scope. It preserves the future Task 0B3 root identity while refusing every
execution path until the component and controlled-fixture gates are separately
authorized and reviewed.

## Scope and non-goals

The historical artifacts were:

1. `tools/reaper_v4_session.py`; and
2. `tests/test_reaper_v4_task0b3a_static_contract.py` (retired once the
   successor session implementation acquired its own pre-import contract).

No Task 0A or Task 0B1 source, schema, or fixture may change. No runtime
closure, fixture manifest, host manifest, control-root artifact, or executable
command is created by this task. The static test may read target bytes and parse
AST only; it must not import, compile, execute, or resolve the target or any
Task 0A/0B1 component.

The source is a reserved **non-admissible session-root skeleton**, not a partial
implementation. A green static test is structural evidence only. It is not a
configuration, descriptor, PRE/ACK/POST, child, fixture, scope, REAPER, or
compatibility result.

## Exact source boundary

The source owns the future root identity only:

```text
kind = "session_entrypoint"
role = "same_namespace_pre_ack_child_post_owner"
```

Its exact public API is:

```python
__all__ = (
    "SessionError",
    "SessionConfig",
    "SessionResult",
    "load_session_config",
    "run_session",
)
```

| Symbol | Skeleton contract |
| --- | --- |
| `SessionError` | A `RuntimeError` subclass for the single fail-closed boundary. |
| `SessionConfig` | `@dataclasses.dataclass(frozen=True, init=False)` with exactly `data: Mapping[str, object]`; direct construction raises `SessionError`. |
| `SessionResult` | `@dataclasses.dataclass(frozen=True, init=False)` with exactly `child_pid`, `child_returncode`, `pre_monotonic_ns`, and `post_monotonic_ns`, all `int`; direct construction raises `SessionError`. |
| `load_session_config(config_path: str, digest_path: str) -> SessionConfig` | Has no defaults or varargs and unconditionally raises `SessionError` before inspecting either argument or performing any operation. |
| `run_session(config: SessionConfig) -> SessionResult` | Has no defaults or varargs and unconditionally raises `SessionError` before inspecting the configuration or performing any operation. |

No factory may construct either dataclass. There are no private semantic
helpers, diagnostics, constants for deferred limits, descriptor/frame/ACK
operations, clock reads, validator calls, measurement calls, child calls,
control artifacts, retries, fallbacks, or execution-surface bootstrap in this
task. The two literal future bootstrap paths may be recorded as constants only:

```text
/run/m3-v4/session-config.json
/run/m3-v4/session-config.sha256
```

They may not be opened, normalized, or otherwise used in Task 0B3a.

## Declaration-only imports

The source has exactly these imports:

```python
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
from tools import reaper_v4_child_runner as child_runner
from tools import reaper_v4_measurements as measurements
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema
```

The five `tools.*` imports record the intended future static dependency graph.
They are not called, accessed, reflected upon, or treated as executable closure
reachability. They do not advance Task 0B0 beyond
`BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)`.

The source has no `__main__`, CLI, top-level executable expression, top-level
resource access, import-time process/namespace action, dynamic import,
reflection, direct process capability, network/GUI/audio capability, or
controller/closure-constructor dependency. In particular it must not import or
call `os`, `subprocess`, `ctypes`, `importlib`, `runpy`, `pathlib`, `socket`,
`asyncio`, `sys`, `shutil`, `glob`, Bubblewrap, systemd, REAPER, a loader API,
`exec`, `eval`, `compile`, `__import__`, `getattr`, `spawn*`, `fork*`, or
`exec*`.

## Static verifier

The verifier must operate before any target import. It reads the exact source
path, checks a pinned lowercase SHA-256, then parses it with `ast.parse`. It
must prove:

- the exact import set, `__all__`, root kind/role, fixed bootstrap-path
  constants, public classes, public fields, public signatures, and exact two
  frozen dataclass decorators;
- no private function/class definitions, no public defaults, varargs, keyword
  defaults, async function, `__main__`, CLI, or top-level executable/resource
  expression;
- each direct dataclass initializer and each public function has exactly one
  executable statement: `raise SessionError(...)`;
- the imported `tools.*` aliases have no runtime use and the source contains no
  allowed-looking but alternate admission, receipt, ACK, child, or control
  surface; and
- no forbidden import, call, attribute, dynamic access, or host capability
  appears anywhere in the AST.

The source SHA-256 is the historical seal for every private syntactic detail.
The static test was retired when the B4b successor contract took over the
executable session source; it did not prove runtime order or behavior.

## Task 1: Non-admissible skeleton authoring and static contract

1. Replace any preliminary session implementation with the exact non-admissible
   skeleton in this contract. No source behavior may survive the replacement.
2. Replace the static test with the pre-import AST/hash verifier described
   above. It must first fail against the preliminary source shape, then pin the
   final skeleton hash.
3. Historically, run only
   `ionice -c 3 nice -n 10 python3 -B -m unittest tests.test_reaper_v4_task0b3a_static_contract -v`.
   The test may parse/read source bytes but must not import any target module.
   Do not run `py_compile`, a component test, or the repository suite.
4. Check whitespace, self-review the two owned files, and commit only those
   files. An independent source-only task review remains mandatory before the
   checkpoint.

## Deferred implementation authority

The complete Task 0B3 execution rules remain binding but are intentionally
unimplemented: fixed bootstrap sidecar validation, exact SessionConfig schema,
bounded `/proc`/mount/FD evidence, certificates, frame transport, ACK EOF,
Task 0A/Task 0B1 validators, child launch, post-child rechecks, diagnostics,
and failure classification.

Task 0B3b, 0B3c, and 0B3d retain their separate pure-component gates. Only a
later explicitly authorized **Task 0B4 session implementation and
state-machine gate** may replace this skeleton, add semantic helpers, change
the static hash, call any declared dependency, and run bounded non-REAPER
controlled-fixture tests. It must preserve the Task 0B3 design, receive a new
source contract and independent review, and still does not authorize
Bubblewrap, systemd, REAPER, X11, audio, or host scanning.
