# V4 Task 0B4b-state-contract — State-Machine Prerequisite Contract

**Status:** sealed documentation-only, pre-implementation checkpoint. This record
names and orders the prerequisites for the later mock-only session state-machine
source gate. It does not admit any session-source change, target import, test
execution, configuration/descriptor I/O, raw transport, barrier, measurement,
child, fixture, namespace, or host action.

**Authority:** The user's fresh `Proceed` authorizes only this documentation
and independent-review checkpoint. The next source/test authority must name the
first successor gate below; it is not implied by this record.

**Review evidence:** Three independent read-only reviews are CLEAN and
`git diff --check` passes. No target module was imported or executed.

## 1. Ruling and non-authority

`Task 0B4c` remains the reserved name for the **outer-harness controlled-
fixture gate**. It must not be used for the in-process session state machine.
The latter is named `Task 0B4b-state` below.

The sealed B4b-pure source was the compatibility baseline and is superseded by
the sealed admission-pure source boundary:

```text
tools/reaper_v4_session.py
SHA-256 = 5bb71ab032b13b59170dd8034528b7b0e990751fd0d0b5b59da6e711a9ce1c11
```

Its public `load_session_config()` and `run_session()` functions still fail
closed immediately. Admission now produces a fresh bounded local SessionConfig
snapshot, but no runnable session or runtime root. In particular, no current
result authorizes Bubblewrap, systemd, REAPER, X11, audio, network, host
scanning, manifest construction, or a fixture.

## 2. Findings that block direct state-machine implementation

The later coordinator cannot be implemented directly from B4b-pure.

1. `_parse_session_config_bytes()` checks supplied canonical bytes, the
   bootstrap digest triple, the top-level key set, and base identity only. It
   deliberately does not validate nested policy, certificate, manifest,
   provenance, or cross-digest relations required by the Task 0B3 design.
   It is therefore a compatibility helper, not configuration admission.
2. `SessionConfig` is a frozen data class, not an authenticity boundary. A
   forged exact instance can be created with Python object primitives, so a
   future `run_session()` must revalidate the complete frozen snapshot before
   its first barrier, transport, clock, evidence, or child edge. It must never
   trust type identity or constructor refusal as proof.
3. The sealed collector establishes only descriptor-rooted `{mode, size}`
   facts for a declared finite plan. It does not establish the FD census,
   mount projection, X11 identities, scan-tree baseline, private-home state,
   certificate applicability, or post-child retained-baseline checks required
   for receipt facts. A generic all-true attestation map or callback would be
   a self-assertion and is prohibited.
4. `_validate_and_encode_receipt()` validates and encodes an individual POST
   directly. Runtime POST requires the stricter order
   `validate_post_payload -> validate_exchange -> encode_frame`. The sealed
   helper may remain a B4b-pure compatibility regression, but cannot be used
   as the runtime POST finalization path.
5. The B4b-pure source contract pins the exact nine-function source shape and
   immediate-failure public functions. Any successor source gate must replace,
   not relax, that contract, while retaining regression coverage for all seven
   B4b-pure helpers.

## 3. Required successor sequence

Each item needs its own explicit user authority, an appropriate reviewed
contract/checkpoint, and independent review. Source/test gates additionally
need a source contract and tests; source-free B4c-design needs documentation
and static-consistency review only. Passing one does not authorize the next.

1. **Task 0B4b-admission-pure — full configuration relation gate (sealed).**
   This bounded in-memory source/test successor adds validation and private
   construction helpers. It validates every closed
   nested `SessionConfig` member and cross-relation in Task 0B3 Section 3:
   direct-input grammar and identity, row, policy and manifest digest shape,
   certificate-minus-digest canonical projections, certificate kind/result,
   user-map arithmetic, descriptor/mount policy bindings, six-key child
   environment and lexicographic `ChildSpec` projection, fixed limits, and
   every required equality relation. At the boundary it must materialize one
   bounded fresh local exact-built-in snapshot, deep-freeze that snapshot into
   a new local value, validate every relation over it, and use only that local
   value thereafter. It must never dereference the caller's `config.data`
   again; a forged or mutable proxy must refuse or be unable to alter a child
   or receipt projection. It may neither open the fixed paths nor claim
   descriptor-pinned provenance. Before changing the session source, this first
   successor retired and replaced the B4b-pure static contract while preserving
   regression coverage for all seven B4b-pure helpers. It remains non-runnable
   and does not authorize any later successor.
2. **Task 0B4b-evidence — bounded evidence implementation gate.** A separate
   source/test authority must author and seal the private session-owned
   observation and retention helpers needed for each Task 0B3 Section 4
   assertion. Every helper needs named bounded inputs, output schema,
   retained-resource owner, close/error behavior, PRE/post use, a fixed source
   edge, and negative tests. It must cover the measurement-root descriptor,
   scan-root baseline, private-home tree, mount projection, X11 identities,
   inherited-FD census, certificate applicability projection, and post-child
   recheck. Tests may use only supplied mock or temporary controlled resources;
   they establish helper behavior, not namespace evidence. The implementation
   must exist before the state-machine closure is sealed. It must not add a
   second runtime root, arbitrary callback, raw control channel, or all-true
   fixture vector. Actual namespace/path/FD proof remains for Task
   0B4c-execution.
3. **Task 0B4b-bootstrap-transport — fixed-loader and raw-helper gate.** A
   separate source/test authority must author and seal the fixed-literal
   configuration loader and fixed fd-0/fd-1/fd-2 transport helpers before the
   coordinator is closed. Its tests use syscall/poll doubles or temporary
   controlled pipes only; they must cover literal path equality, sidecar-first
   order, descriptor type/flag checks, bounded EOF reads, one-write short/
   `EINTR`/`EPIPE`/`EAGAIN`/deadline refusal, exact ACK byte plus EOF, and the
   one best-effort fd-2 diagnostic attempt. It may not execute the real
   `/run/m3-v4` paths, establish a namespace, or launch a child. Actual kernel
   behavior under the reviewed fixture remains Task 0B4c-execution. It adds
   private loader/transport helpers only and leaves both public session
   functions as immediate-failure stubs for the later state gate.
4. **Task 0B4b-state — mock-only state-machine composition gate.** Only after
   the preceding source gates are sealed may a further authority replace the
   public fail-closed stubs and test the single root with patched named module
   edges and bounded in-process doubles. It must use no public dependency-
   injection interface, arbitrary control FD, dynamic import, alternate
   coordinator, real barrier, real measurement, real child adapter, or
   sentinel. The later source contract must preserve the seven B4b-pure helper
   regressions through the contract already replaced by admission-pure. Each
   evidence, bootstrap-transport, and state successor must in turn replace the
   immediately preceding closed static contract before changing source.
5. **Task 0B4c-design — controlled-fixture definition gate.** A separate
   source-free design authority must define the bounded non-REAPER fixture,
   parent ownership, standard-stream topology, expected mounts, and resource
   budgets that the future fixture-runtime manifest needs. It creates no
   namespace, process, mount, or fixture execution.
6. **Task 0B5 and successor Task 0B0 closure review.** After a reviewed
   executable state-machine source and fixture definition exist, the separate
   data-only graph constructor and independent closure review must include that
   exact root and its Task 0A/Task 0B1 dependency closure. Any unresolved edge
   or budget excess remains `BLOCKED_UNRESOLVED`.
7. **Fixture-runtime-manifest review, then Task 0B4c-execution.** Only after
   the reviewed executable root, fixture definition, and complete bounded
   fixture-runtime manifest exist may a separately scoped outer-harness
   controlled fixture execute. Its own future source/test/execution authority
   must name exactly one independently reviewed non-REAPER scope mechanism and
   its fixed policy; it may not substitute an unreviewed launcher. It owns
   parent drains, scope teardown, and PID census. It never authorizes REAPER,
   X11, audio, host scanning, or a host launch.

## 4. Reserved state-machine contract

The future Task 0B4b-state contract must preserve the public API and the one
runtime-root identity:

```text
load_session_config(config_path: str, digest_path: str) -> SessionConfig
run_session(config: SessionConfig) -> SessionResult
kind = "session_entrypoint"
role = "same_namespace_pre_ack_child_post_owner"
```

It must define exact private source interfaces before implementation for:

- revalidation of the complete immutable configuration snapshot;
- fixed-literal bootstrap and descriptor-validation helpers, sealed through
  the bootstrap-transport gate and exercised through doubles before any real
  fixed-path fixture;
- a fresh base-config projection and the Task 0A barrier;
- named PRE and POST evidence assembly from the separately sealed evidence
  boundary;
- fixed fd-0/fd-1/fd-2 transport helpers, never caller-supplied descriptors;
- one exact ChildSpec builder;
- a POST-only finalizer that calls `validate_post_payload`, then
  `validate_exchange(pre_payload, exact_ack, post_payload)`, then
  `encode_frame(POST, 1, post_payload)`; and
- an exact `SessionResult` construction path after successful POST write and
  stdout close.

The future static test must parse source before import and pin imports,
definitions, signatures, class bodies, decorators, top-level forms, external
module edges, direct local edge counts, and every allowed call argument. It
must reject dynamic calls/imports, `subprocess` outside the sealed adapter,
additional runtime roots/coordinators, generic callbacks, arbitrary descriptor
parameters, and literal/all-true receipt evidence. The B4b-pure static
contract is retired first by B4b-admission-pure; every later successor must
explicitly retire its immediate predecessor's static contract, not leave it to
fail accidentally. The state contract must structurally prove that ACK plus observed EOF dominates
every ChildSpec/run-child edge, a confirmed non-timeout/nonnegative exact
ChildOutcome dominates every post-evidence edge, exchange validation dominates
POST encoding and writing, and no `finally` block can emit POST or return a
successful result. Source-mutant tests must demonstrate each guard rejects the
corresponding ordering regression.

## 5. Future mock-only acceptance matrix

The future Task 0B4b-state tests must patch named module edges rather than
exercise the kernel or host. They may prove local ordering only.

| Condition | Required local result | Not proved |
| --- | --- | --- |
| Complete revalidation and non-barrier preflight, barrier, PRE evidence assembly, PRE validation/encoding, and one PRE write | Child still absent until ACK byte and observed EOF | Fixed-path provenance, actual barrier, pipe atomicity |
| Missing, wrong, extra, delayed, or non-EOF ACK | PRE-only; no child and no POST | Kernel EOF/poll behavior |
| Mocked child timeout, negative return, exception, or pre-bind uncertainty | PRE-only; no POST | Real launch, reaping, scope teardown, PID census |
| Mocked post evidence, POST validation, exchange, encode, write, or close failure | No returned result and no retry of terminal POST | Namespace or raw-stream recovery |
| Successful mocked path | Exact order: admission/non-barrier preflight -> barrier -> PRE evidence -> PRE validation/encode/write -> ACK+EOF -> one child -> post evidence -> POST validation -> exchange -> POST encode/write -> close -> result | Fixture readiness or host compatibility |

For every ordinary dependency `Exception`, the future source must normalize to
`SessionError` before any later state transition. A `BaseException` escapes and
must not trigger a later transition. The fd-2 best-effort diagnostic remains a
separately specified exception to mandatory-dependency normalization; stdout
never carries a diagnostic. A complete or partial unconfirmed write is raw
uncertainty, never an accepted terminal result.

Before any POST edge, the future state gate must verify that the mocked result
is an exact `child_runner.ChildOutcome` with a positive non-Boolean child PID,
a bounded non-Boolean return code, an exact Boolean timeout flag, and bounded
elapsed milliseconds. A forged, malformed, timed-out, negative-return, or
unconfirmed outcome is uncertainty and emits no POST.

## 6. Explicit proof limits

No source or test authorized by this document can prove fixed-path sidecar
identity, paired JSON/sidecar substitution resistance, file mode/link/FD
semantics, actual `PIPE_BUF`/EOF/poll behavior, `PR_SET_DUMPABLE`, namespace
mount/X11/proc state, real child reaping, concurrent parent draining, scope
exit, descendant containment, PID census, closure completeness, fixture
readiness, REAPER compatibility, or a host action. Those claims remain split
across later admission/evidence/state/closure/manifest/outer-harness gates.

## 7. Documentation acceptance

This checkpoint is sealed because the B3 design, V4 plan, and `RESUME.md`
use the same names and order: B4b-pure sealed; B4b-state-contract
documentation-only; B4b-admission-pure then B4b-evidence then
B4b-bootstrap-transport then B4b-state as separate future authorities;
B4c-design; Task 0B5 and the closure/fixture-manifest review; then
B4c-execution; and no host or fixture claim. Three independent reviews are
CLEAN and the whitespace check passes.
