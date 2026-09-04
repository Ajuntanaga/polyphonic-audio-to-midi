# V4 Task 0B1 Author-Only Source Contract

Date: 2026-09-01
Status: independently reviewed Task 0B1 author-only source contract; source
files may be authored but never imported or invoked in this task
Depends on: `docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`
Scope: author static source/API and inert data contracts only; run only an
AST/JSON-byte contract test that never imports, compiles, invokes, or
semantically tests an authored module

## Decision

Task 0B1 is intentionally a non-admissible source phase. It may add exactly
four Python source files, their machine-readable contract documents, and
synthetic inert fixtures. It may not create a runtime session, a namespace, a
fixture process, a receipt channel, a child process, or a closure record from
Task 0A or Task 0B1 data.

This avoids inventing a hidden runtime owner. Task 0A is immutable and has no
receipt writer, ACK reader, collector, runner, or admission entrypoint. The
future in-namespace session owner that sequences PRE, ACK, child, and POST is
not a Task 0B1 artifact. It needs a separately reviewed design and separately
authorized source task before it can become a manifest root.

Until then, the Task 0B1 receipt, measurement, and child-runner source files
are non-admissible library components only. Any future static closure record
that includes them must contain the exact unresolved reason
`runtime_session_entrypoint_unresolved`; it cannot use
`COMPLETE_FIXTURE_CANDIDATE`. A library source is never silently promoted to a
runtime root merely because it exists in the repository.

## Authority boundary

Task 0B1 may author only these files:

1. `tools/reaper_v4_closure_constructor.py`
2. `tools/reaper_v4_receipt_schema.py`
3. `tools/reaper_v4_measurements.py`
4. `tools/reaper_v4_child_runner.py`

It may also author the two contract schemas and inert fixtures named below, and
one AST-only contract test that never imports any of the four modules. Running
that byte/AST-only test is authorized because it cannot execute authored source
or form a process. It does not authorize any other `tools/reaper_v4_*` module,
including a session owner.

The task does not authorize target source/bytecode import, execution, loading,
or symbol calls; `ctypes`/`cffi`/`dlopen`; child invocation; namespace or
fixture creation; Bubblewrap, systemd, or REAPER command formation; GUI, X11,
audio, network, installation, MCP, or a host action. No authored module may be
imported, compiled, or called during Task 0B1 verification.

Task 0B2 is a separate authority for constructor-only source/data tests and
static closure construction. A later separately authorized pure-component gate
is required before receipt, measurement, or child-runner behavior can be
tested. Neither gate authorizes a session or fixture.

**Task 0B2 narrow correction amendment.** Under the current user `Proceed`
authorization, and only after the demonstrated sealed-synthetic-data RED,
Task 0B2 may correct only the private normalization in
`tools/reaper_v4_closure_constructor.py` required for that component's own
constructed synthetic record to validate. The constructor source hash must be
resealed, the static contract and Task 0B2 tests rerun, and the result
independently reviewed. No other Task 0B1 source expansion or correction,
target import/execution/loading, fixture or namespace action, or host action is
authorized.

**Task 0B3c narrow correction amendment.** Under the separately scoped
temporary-directory/descriptor gate, the initial synthetic-only RED exposed
collector validation holes. The sole authorized production correction was within
`tools/reaper_v4_measurements.py`: take an exact-plan local snapshot before
validation; reject non-canonical strings, duplicates, and unhashable values
before `os.open`; normalize root-descriptor `OverflowError` and close failures
to `MeasurementError`; and require `MEASUREMENT_KEYS` to be exactly
`("mode", "size")`. This is a fail-closed collector correction, not a new
capability. The sealed collector source SHA-256 is
`27fa32e618a1a1461f3ec50820e7ad8717aa0747f1a6c7e475badefa0b4f7a22`.
The seven-check static contract plus the Task 0B3c synthetic descriptor suite
passed 20 tests, and independent review is CLEAN. This authority did not
create a session or namespace, form or invoke Bubblewrap/systemd/REAPER,
perform X11, audio, network, or host action, or prove ACK, raw-stream, or
session behavior. Task 0B3d remains a separately authorized child-adapter-only
gate.

**Task 0B3d child-adapter checkpoint and narrow correction amendment.** The
separately scoped direct-child gate invoked only
`tools/reaper_v4_child_runner.py`, first through deterministic mock race
vectors and then through a temporary-directory, non-forking Python sentinel
with exact isolated startup flags `-I -S -B -c`. The controlled REDs exposed
the post-bind cleanup boundary, an unsafe cleanup-slot counter placement, and
last-interruption overwriting. The reviewed correction prebinds the process,
keeps the sole launch inside its outer recovery boundary, reserves at most two
direct-child cleanup slots before `kill()`, always reaches the bounded
`wait()` after a `kill()` error within an entered slot, and preserves the first
non-`Exception` interruption, including escalation of a cleanup
non-`Exception` over an ordinary original adapter error. Reaping is confirmed
only after `wait()` returns; every pre-bind or unconfirmed path remains
outer-session/scope uncertainty. The sealed runner SHA-256 is
`a9cecba05537a349355fc204d2a8343a51caf6fabb7ab5d184ef341270f5a946`.
The seven-check static contract plus the twelve Task 0B3d tests passed 19
checks, and two independent reviews are CLEAN. This proves only direct-child
adapter semantics: explicit environment/cwd, no retry on launch failure,
bounded timeout/reap behavior, and isolated sentinel startup. It proves no
session, raw PRE/ACK/POST stream, namespace, Bubblewrap, systemd, REAPER,
X11, audio, network, host scan, or descendant containment. Task 0B4 session
implementation remains a separately scoped future authority.

## Contract artifacts

The source phase must add the following inert, canonical JSON documents:

| Path | Purpose |
| --- | --- |
| `docs/superpowers/schemas/v4-closure-input-bundle.schema.json` | Closed shape for the author-only blocked catalog vector; it deliberately permits no catalog records |
| `docs/superpowers/schemas/v4-receipt-exchange.schema.json` | Structural PRE, one-byte ACK, and POST value grammar; no descriptor or exchange I/O |
| `tests/fixtures/reaper_v4_closure/blocked-input-bundle.json` | Synthetic, deliberately blocked catalog bundle with no live path or artifact |
| `tests/fixtures/reaper_v4_closure/receipt-exchange.json` | Synthetic PRE/ACK/POST data that contains no host identity or secret |

The input-bundle schema has exactly these catalog keys:

```text
resolver_policy, startup_model, module_catalog,
interpreter_module_registry, frozen_effect_catalog, elf_catalog,
branch_policy, native_effect_catalog, virtual_resource_catalog,
source_effect_catalog, resource_policy
```

The `blocked-input-bundle.json` file is a closed **vector wrapper** with exact
`schema`, `case`, `input_bundle`, and `expected_outcome_projection` members. Its nested
`input_bundle` has catalog data only: exact `schema`, closed synthetic
constructor/parser provenance identities, target-platform identity, Task 0A
source-component digest, typed `analysis_roots`, typed `runtime_roots`, and
the eleven embedded catalog objects. Each provenance identity is the exact
closed record `kind`, `raw_path`, `mode`, `device`, `inode`, `byte_size`,
`sha256`, and `version`. `kind` is a closed synthetic discriminator
(`synthetic-constructor` or `synthetic-parser`); `raw_path` is a printable
absolute `/synthetic` or `/synthetic/...` path with no empty, `.` or `..` component; `device` and `inode` are bounded positive
integers; `byte_size` is bounded and nonnegative; `mode` is bounded; and
`version` is bounded printable ASCII. These are synthetic provenance-shape
claims only. They do not read, identify, or prove anything about a live host
filesystem, repository artifact, or path. A root is the exact closed object
`id`, `module`, `kind`, `sha256`, and `role`; both arrays bind into the input
digest. The author-only schema requires exactly four analysis roots, in this
declared order and with no extras: `tools.reaper_v4_protocol` as
`sealed_component`, then `tools.reaper_v4_receipt_schema`,
`tools.reaper_v4_measurements`, and `tools.reaper_v4_child_runner`, each as
`runtime_library`. It deliberately constrains module and role, but does not
pin the synthetic fixture's source-hash placeholder values. `runtime_roots` is
exactly empty for the blocked vector. Every catalog object has exact
`schema`, `kind`, and `records` members; the input schema rejects unknown keys
and fixes each `kind` to its named catalog. Because Task 0B1 has no graph or
retained-dirfd construction authority, each current `records` array is exactly
empty. A later reviewed schema version must define catalog-record references
before nonempty inputs can be constructed; this checkpoint cannot smuggle an
unreviewed record language into the future resolver.

The JSON schema is intentionally structural: it bounds each root object and
array but cannot express unique root IDs or same-module/different-digest
conflicts across separate arrays. The constructor owns those global resolver
relations and must fail closed before it can produce a record; Task 0B2 is the
first future authority allowed to execute that behavior against static data.

The input itself never declares `closure_state` or an unresolved conclusion.
The sole Task 0B1 vector supplies empty `runtime_roots`; its separate
`expected_outcome_projection` object—not a closure record or digest preimage—
has `closure_state: "BLOCKED_UNRESOLVED"` and one unresolved object whose exact `code` is
`runtime_session_entrypoint_unresolved` and whose exact `role` is
`same_namespace_pre_ack_child_post_owner`. No fixture may use a live `/usr`,
`/lib*`, repository, home, runtime, REAPER, X11, or `/proc` pathname,
executable bit, symlink, hardlink, special file, or host identity.

The receipt schema extends—never duplicates—the Task 0A identity members:
`schema`, `namespace`, `nonce`, `config_sha256`, and `inputs`. Its exact
*value* shapes are:

```text
PRE:  identity + row={sample_rate_hz: 44100, block_size: 32}
      + phase="pre" + no_child_started=true + attestation
ACK:  exactly one byte 0x06
POST: identity + same row + phase="post" + terminal=true + child_pid + child_returncode
      + pre_monotonic_ns + post_monotonic_ns + attestation
```

Task 0B1 validates those individual values and their PRE/POST relations only.
It validates only that the supplied ACK value is the one byte `0x06`; it does
not read a stream and therefore does not establish ACK EOF, trailing-byte
rejection, raw-frame order, duplicate-frame rejection, or frame-to-payload
binding. The later reviewed in-namespace session owner owns the raw
`PRE(seq=0)`, one ACK, `POST(seq=1)`, EOF exchange and must bind its parsed
values to these pure validators. In particular, this source phase must not
describe an in-memory ACK value check as evidence that an ACK stream was
closed or had no trailing data.

`child_pid` is an integer from 1 through 2147483647; `child_returncode` is an
integer, never a Boolean, from -255 through 255; monotonic values are positive
integers, never Booleans, and POST is not earlier than PRE. PRE and POST must
have byte-identical identity members and byte-identical values for every shared
attestation fact, and the same closed row
`{sample_rate_hz: 44100, block_size: 32}`. POST may add only
`scan_root_unchanged`. The structural schema fixes the attestation fact names,
value types, and required-true containment facts; a
later session owner may measure them but cannot add or omit a fact without a
reviewed schema change.

The JSON schema validates each PRE and POST object independently. It does not
and cannot establish PRE/POST identity equality, shared-attestation equality,
or monotonic ordering across the two objects. Those relational conditions are
the sole responsibility of `validate_exchange`; a later authorized pure-
component gate must execute adversarial receipt vectors against that validator
before any session work is considered.

Every current receipt-string field is printable ASCII, so its JSON-schema
character limit is also its UTF-8 byte limit. Every identity or assertion string
is at most 256 bytes (the Bubblewrap version is at most 128); `inputs` and
other bounded receipt arrays/maps have at most 16 entries;
environment and forbidden-environment arrays have at most 32 unique strings of
at most 128 bytes; and `x11_identity` is a closed five-member object with
strings/integers only. The schema applies equivalent finite bounds to every
attestation map/array. `validate_pre_payload`, `validate_post_payload`, and
`validate_exchange` must canonical-encode the payload through the sealed Task
0A `protocol.encode_frame` API and refuse if the result exceeds
`protocol.MAX_PAYLOAD_BYTES` or `protocol.MAX_FRAME_BYTES`. The later session
owner independently requires that accepted full-frame bytes fit its queried
`PIPE_BUF`; a structurally valid but over-limit receipt is never accepted.
Both source and schema reject every non-printable byte, including a trailing
newline, NUL, and DEL.

Receipt validation performs its printable-byte check before any UTF-8 byte
conversion. A lone JSON surrogate or other malformed Unicode value therefore
becomes `ReceiptSchemaError`, never an uncaught encoding failure.

The same printable-ASCII rule applies to bounded constructor/parser provenance
paths and versions, identity kinds, and target-platform strings in the
blocked-input schema, so their JSON-schema limits remain exact byte limits
rather than host-dependent Unicode character counts.

Before any PRE or POST field check or frame encoding, the receipt validator
takes one deep snapshot of exact built-in `dict`, `list`, and `tuple`
containers. It rejects container subclasses, cycles, more than 512 structural
nodes, nesting deeper than 32 levels, strings longer than 256 characters, or
more than 8,192 estimated UTF-8 bytes. The returned `ReceiptPayload` freezes
that same already-validated snapshot; it never makes a second traversal of
caller-owned nested data after validation.

The exact PRE attestation keys are `home`, `pwd`, `cwd`, `environment_keys`,
`forbidden_env_absent`, `runtime_manifest_sha256`,
`run_input_manifest_sha256`, `bwrap_path`, `bwrap_version`,
`bwrap_argv_sha256`,
`production_bundle_absent`, `private_vst_empty`, `private_vst3_empty`,
`private_home_private`, `scan_root_readonly`, `scan_descendants_readonly`,
`no_later_scan_mount`, `x11_identity`, `source_fds_absent`,
`control_root_absent`, `dumpable_disabled`, `capabilities_empty`,
`proc_receipt_blocked`, and `proc_mem_blocked`. POST has those same exact keys
plus `scan_root_unchanged`. The receipt schema defines each scalar, array, map,
and required-true Boolean type; source code may not replace this schema with an
open fact map. `run_input_manifest_sha256` is the receipt's sealed reference to
a later parent-validated run-input manifest. That manifest alone binds the
exact private scan-root entry list and hashes to the selected row; this Task
0B1 payload grammar neither carries nor independently establishes them.

## Source API and import rules

All four modules have a docstring, `from __future__ import annotations`, an
exact literal `__all__`, literal constants, frozen dataclasses/enums/exceptions,
and functions only. They have no CLI, `__main__` path, top-level call or I/O,
decorator/default-factory side effect, dynamic import, or import-time resource
read. An AST-only test reads their source bytes before any import.

| Module | Exact imports | Exact public API | Role and boundary |
| --- | --- | --- | --- |
| closure constructor | `ast`, `dataclasses`, `enum`, `hashlib`, `json`, `os`, `stat`, `struct`, `types`, `Mapping` | `ClosureConstructionError`, `ClosureState`, `ClosureInputBundle`, `ClosureRecord`, `canonical_json_bytes`, `sha256_canonical`, `load_input_bundle`, `construct_closure` | Source/data-only parser skeleton. It takes a bounded, cycle-safe immutable snapshot before semantic or digest validation, including at the public canonicalization boundary. No `tools.*`, `subprocess`, `ctypes`, import loader, target evaluation, broad scan, or ambient-state API. It rejects schema-invalid data and pathname loading; for the sole supplied schema-valid empty-catalog vector it returns only the exact blocked output until a separately authorized graph-construction successor supplies retained-directory-FD input and Task 0B3 supplies the reviewed session graph. |
| receipt schema | `dataclasses`, `enum`, `types`, `Mapping`, `tools.reaper_v4_protocol` | `ReceiptSchemaError`, `ReceiptPhase`, `ReceiptPayload`, `ACK_BYTE`, `PRE_KEYS`, `POST_KEYS`, `ATTESTATION_KEYS`, `validate_pre_payload`, `validate_ack_bytes`, `validate_post_payload`, `validate_exchange` | Pure in-memory grammar and payload/value-relation validation only. No descriptor, file, process, clock, measurement, launch, or stream I/O. |
| measurements | `dataclasses`, `os`, `pathlib`, `stat`, `types`, `Mapping` | `MeasurementError`, `MeasurementPlan`, `MeasurementSnapshot`, `MEASUREMENT_KEYS`, `collect_namespace_measurements` | Explicit-plan later collector. It takes an exact-plan local snapshot before validation; permits only canonical one-component printable strings, rejects duplicates and unhashable values before `os.open`, and normalizes root-descriptor `OverflowError` and close failures to `MeasurementError`. `MEASUREMENT_KEYS` is exactly `("mode", "size")`; `MeasurementPlan` snapshots an exact built-in resource tuple and bounded expected facts before any later use. No frame/ACK/child API, write, subprocess, `ctypes`, environment/cwd/HOME read, recursive walk, or implicit resource access. Runtime reads may occur only inside the callable after later authority and use `O_PATH|O_NOFOLLOW|O_CLOEXEC` plus `fstat`, before accepting a regular-file fact. |
| child runner | `dataclasses`, `subprocess`, `time` | `ChildRunnerError`, `ChildSpec`, `ChildOutcome`, `run_child` | The only subprocess importer and a later callable adapter. It contains no admission, ACK consumption, PRE/POST emission, fallback, retry, CLI, or import-time launch. It accepts only an exact `ChildSpec`, captures and validates its immutable bounded fields once, then uses only those locals. It has exactly one syntactic `subprocess.Popen` call, only in `run_child`, with absolute executable/cwd, explicit environment, `shell=False`, DEVNULL standard streams, `close_fds=True`, `pass_fds=()`, one bounded launch, and at most two reserved direct-child cleanup slots after timeout or any `BaseException` **once Python has bound the returned process object**. Within an entered slot, an error from `kill()` still reaches its bounded `wait()`; reaping is confirmed only when that wait returns. An interruption between Python operations or repeated cleanup failure leaves process state uncertain. A later outer session/scope must recover that uncertainty and a partial launch interrupted before binding—including before `Popen` returns or after OS child creation but before Python retains the returned object—and must perform exact row/policy environment admission and binding before it creates `ChildSpec`. |

Every public class is a frozen dataclass, enum, or exception. `ClosureInputBundle`
has one `bundle` mapping that is valid only when it satisfies the closed input-
bundle schema. `ClosureRecord` has one `record` mapping that is valid only when
it contains every canonical Task 0B0 output member: `schema`, method and
producer identities, all catalog/policy digests, task source component digest,
analysis/runtime root identities, nodes, edges, branch records, unresolved,
budgets, `closure_digest`, and `closure_state`. It never returns the vector's
short expected-outcome projection; direct construction rejects any incomplete,
candidate-state, digest-mismatched, or semantically incomplete blocked record
after first taking its immutable snapshot. It recomputes `input_bundle_digest` from the retained
analysis/runtime identities and all eleven catalog-policy digests before it
accepts the outer closure digest. Both objects take a bounded, cycle-safe,
deep immutable snapshot before any semantic or digest decision; the same bound
applies when public canonical JSON receives an input. Its canonical JSON
accepts only exact built-in scalar types, so subclass-controlled comparison or
serialization cannot turn blocked data into a candidate record.
The current author-only bounds are 4,096 structural nodes, 64 nesting levels,
6,144 input-budget bytes, 1,024 bytes per string, 256 integer bits, and a
65,536-byte canonical-output ceiling. Public APIs accept only exact built-in
caller containers; internal immutable snapshots are normalized through a
separate private path and are never used as an ambient caller capability.
`ReceiptPayload` is validator-created: direct construction is unavailable and
only a successful PRE or POST validator can create the frozen value with
`phase`,
`sequence`, and `payload`; `MeasurementPlan` has `root_fd`, `resources`, and
`expected`; `MeasurementSnapshot` has `facts` and `evidence`; `ChildSpec` has
`argv`, `cwd`, `environment`, and `timeout_ms`; and `ChildOutcome` has
`child_pid`, `returncode`, `timed_out`, and `elapsed_ms`. `child_pid` is always
the positive non-Boolean PID reported by the one launched child, including the
post-kill/wait timeout outcome. All functions have no default or keyword-default
arguments.

The public APIs are non-admissible in this phase because Task 0B1 never calls
them. Their function bodies may be authored now, but no source file may use a
comment, environment variable, command-line option, or ambient state as an
authority override. Collection and child execution remain unavailable until
their separately authorized component/session gates; the source test checks
structure, not their behavior.

## Required static verification

The Task 0B1 test reads source and JSON bytes only. It must run before any
module import and prove:

- the immutable Task 0A hashes still match their seal;
- the four named source files, two schema files, and two inert fixtures exist
  at their declared paths;
- the sealed Task 0B1 source, schema, and fixture hashes; module imports, public names,
  class/function shape, and no-top-level-effect policy match this contract,
  including no nested import, executable
  class-body/top-level binding, dynamic base, or metaclass;
- only the child-runner source imports `subprocess`, and its one
  `subprocess.Popen` call is confined to `run_child` with the exact containment
  keywords above;
- no source contains `subprocess.run`, `call`, `check_call`, `check_output`,
  `getoutput`, `getstatusoutput`, `os.system`/`popen`/`posix_spawn`, a dynamic
  attribute/import, or any `spawn*`, `fork*`, or `exec*` call; the runner has
  no `shell=True`, `preexec_fn`, executable/PATH override, or second/fallback
  process branch;
- the constructor contains no import/evaluation/native-load/broad-scan API;
- direct `ClosureRecord` construction refuses incomplete, candidate-state, or
  digest-mismatched records after bounded cycle-safe snapshotting; public
  canonicalization uses the same snapshot boundary; the measurement collector uses only metadata-only
  `O_PATH|O_NOFOLLOW|O_CLOEXEC` descriptors; and the runner contains bounded
  at most two reserved direct-child cleanup slots once the returned process
  object is bound, confirming reaping only after a bounded wait returns; a
  future outer session/scope owns every unconfirmed cleanup and partial-launch
  recovery before that binding (including after OS child creation but before
  Python retains the returned object) and exact
  environment admission before `ChildSpec` creation;
  the AST gate checks that exact `os.open` flags, the one direct `Popen`
  reference, and the two-attempt kill-then-wait cleanup shape rather than token
  presence alone;
- catalog documents have all eleven exact names and the fixture is deliberately
  `BLOCKED_UNRESOLVED` because the session root is absent, while its expected
  outcome is only a non-digest-bearing projection; and
- the receipt fixture contains only canonical synthetic values and exact ACK
  byte `06`; the schema rejects malformed individual values, while source shape
  requires the later-behaviorally-tested validator to reject non-printable
  characters, regressing POST clocks, and changed shared PRE/POST attestation
  facts. Raw-frame ordering, ACK EOF, duplicate-frame rejection, and stream
  binding remain a later session-owner obligation.

It must not import, compile, invoke, or otherwise evaluate any authored Task
0B1 module. A passing source contract is not a behavioral pass and grants no
Task 0B2, pure-component, session, fixture, or host authority.

## Alternatives rejected

- **Add an unreviewed fifth session module now:** rejected because the user
  authorized four named source files only, and the session owns the critical
  PRE/ACK/child/POST ordering.
- **Treat libraries as implicit runtime roots:** rejected because it hides the
  missing orchestration owner and could yield a false complete manifest.
- **Run pure unit tests under Task 0B1:** rejected because this phase permits
  source authoring only. Later execution needs its own explicit gate.
