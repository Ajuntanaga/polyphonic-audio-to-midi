# V4 Task 0B4b-state — Mock-Only Session Composition Contract

**Status:** locally implemented and verified; pending independent review before
it can be called sealed. This is the source-and-test contract for the single
session-root composition slice. It succeeds the locally verified
bootstrap-transport source and deliberately proves local ordering only. Its
current source SHA-256 is
`5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.
The current implementation checkpoint is commit `2ce8abc`.
It does not make a fixture, namespace, REAPER, audio, X11, network, or host
claim.

## Scope and non-authority

This gate may modify `tools/reaper_v4_session.py`, replace the predecessor
pre-import source contract, add a mock-only state test, and update recovery
records. It preserves Task 0A, Task 0B1, and the existing pure/admission/
evidence/bootstrap regressions. Tests may import the session module only after
the replacement AST contract passes, then patch its named module edges with
in-process doubles. They must not execute a real fixed `/run` read, barrier,
measurement, child adapter, namespace, fixture, parent drain, or host action.

`Task 0B4c` remains the later outer-harness gate. The explicit fail-closed
evidence assembly stubs below are not an alternate runtime root, callback API,
or assertion that a receipt fact is true.

## Exact public and private surface

Keep exactly one public runtime-root surface:

```text
load_session_config(config_path: str, digest_path: str) -> SessionConfig
run_session(config: SessionConfig) -> SessionResult
kind = "session_entrypoint"
role = "same_namespace_pre_ack_child_post_owner"
```

`load_session_config()` accepts only the two fixed literal paths and delegates
once to the sealed private bootstrap loader. `run_session()` owns the one local
transition below. It has no dependency-injection parameter, no callback,
alternate writer, arbitrary descriptor, fallback coordinator, or second root.

Add only these state helpers:

```text
_capture_runtime_evidence(config: SessionConfig) -> _EvidenceBaseline
_recheck_runtime_evidence(baseline: _EvidenceBaseline) -> None
_release_runtime_evidence(baseline: _EvidenceBaseline) -> None
_assemble_pre_payload(config: SessionConfig, baseline: _EvidenceBaseline) -> dict[str, object]
_assemble_post_payload(config: SessionConfig, baseline: _EvidenceBaseline,
                       outcome: child_runner.ChildOutcome,
                       pre_monotonic_ns: int, post_monotonic_ns: int) -> dict[str, object]
_child_spec_from_config(config: SessionConfig) -> child_runner.ChildSpec
_validate_child_outcome(outcome: child_runner.ChildOutcome) -> child_runner.ChildOutcome
_finalize_post_payload(pre_payload: dict[str, object], ack: bytes,
                       post_payload: dict[str, object]) -> bytes
```

At this historical mock-only checkpoint, the first five evidence/payload
helpers were deliberately one-statement `SessionError` stubs. The later
`2026-09-05-v4-task0b4b-payload-assembly-source-contract.md` replaces only
the PRE/POST payload stubs with an owned-baseline cross-check and leaves the
three runtime-observation helpers fail closed. It adds no ambient path,
transport, barrier, child, or fixture edge, and it does not make direct helper
calls a public interface or fixture authority. Runtime observation acquisition
must still be reviewed before a fixture can call the root.

`_child_spec_from_config()` materializes the admitted private child projection
and constructs exactly one sealed `child_runner.ChildSpec`. `_validate_child_outcome()`
requires the exact sealed `ChildOutcome`, a positive non-Boolean PID, a bounded
non-Boolean return code, an exact Boolean timeout flag, and bounded elapsed
milliseconds. A timed-out or negative-return outcome is uncertainty and raises
before every POST edge. `_finalize_post_payload()` has the only runtime POST
sequence: `validate_post_payload(post, 1)`, then
`validate_exchange(pre, ack, post)`, then `encode_frame(POST, 1, post)`.

## Required transition and exception boundary

The only successful order is:

```text
admit config -> capture evidence -> fresh base projection -> barrier
-> build/validate/encode PRE -> sample pre clock -> one PRE write
-> exact ACK plus EOF -> one ChildSpec -> one run_child
-> exact non-timeout/nonnegative outcome -> recheck evidence
-> sample post clock -> build POST -> validate/exchange/encode POST
-> one POST write -> close stdout -> release evidence -> SessionResult
```

ACK plus observed EOF must dominate ChildSpec construction and `run_child`.
The exact acceptable outcome must dominate recheck, POST assembly, exchange,
encoding, write, stdout close, and result construction. Exchange validation
must dominate POST encoding/write. No `finally` block may emit POST or return a
successful result.

Every ordinary dependency exception is normalized to `SessionError`; a
`BaseException` escapes and cannot advance the transition. If a captured
baseline exists, the local failure path makes one best-effort named release
attempt but never emits a POST. The fd-2 diagnostic helper may be called only
after successful diagnostic setup, at most once on an ordinary failure; its
own errors remain ignored by its sealed boundary. A PRE or POST write failure
is raw-stream uncertainty, never retried and never a successful result.

## Required tests and static source checks

The replacement pre-import contract must preserve all predecessor helper
checks, pin the `child_runner` import and only the listed state interfaces,
forbid direct subprocess/namespace/path/ambient/evidence capability additions,
and check direct call order in `run_session`.

Mock-only behavior must cover a full successful path and every failure row:

- invalid admission, evidence capture, barrier, PRE assembly/validation/encode,
  or PRE write: no child and no POST;
- missing/bad/extra ACK or no EOF: PRE-only, no child and no POST;
- child adapter ordinary error, malformed outcome, timeout, or negative return:
  PRE-only and no POST;
- post recheck, POST assembly, post validation/exchange/encode/write, or stdout
  close failure: no returned result and no retry of terminal POST;
- success: exactly one child after ACK+EOF, PRE then POST bytes, stdout close,
  one release, and an exact `SessionResult`.

The test doubles use an existing canonical synthetic receipt vector only as
data for real receipt/protocol validation; they are not namespace evidence.

At the original state checkpoint the preserved suite had 46 checks. The later
payload-assembly increment reruns the same preserved checks plus five payload
tests (51 total) against its recorded source hash. No real fixed path,
barrier, measurement, child, namespace, fixture, audio device, or host
operation ran.
