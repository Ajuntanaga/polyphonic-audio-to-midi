# V4 Task 0B4b-pure — Session Compatibility Helpers

**Status:** sealed pure-helper source-and-test checkpoint.  This document
admits only the bounded in-memory compatibility layer described here; it does
not admit a session state machine or any runtime action.

**Seal evidence:** `tools/reaper_v4_session.py` SHA-256 is
`9aa503dc77f37ace46202a35797925e784e9e302b866d3c81d880897e7a86c99`.
The immutable Task 0B1 static gate, this pre-import gate, and the five focused
in-memory behavior tests passed 13 checks in total; two independent reviews
are CLEAN.  That evidence remains bounded to this pure helper layer.

## 1. Scope and non-authority

The user's fresh `Proceed` authorizes this deliberately narrow **pure helper**
increment.  It may replace the Task 0B4a preliminary expected-failure checks,
change `tools/reaper_v4_session.py`, import that module for focused unit tests,
and exercise only the pure functions named below with in-memory data.

It does **not** authorize a session state machine, an internal session factory,
configuration-path or descriptor I/O, standard-stream transport, clocks,
diagnostics, barriers, measurement collection, child-adapter invocation,
sentinel process, namespace, Bubblewrap, systemd, REAPER, X11, audio, network,
host scan, manifest construction, or fixture work.  `load_session_config()`
and `run_session()` remain immediate `SessionError` stubs.  A later separately
reviewed and authorized state-machine increment is required before either can
do work.

This contract supersedes the Task 0B4a requirement that the pure parser fully
admit the complete Section 3 policy/certificate graph.  That would require
additional policy and certificate digest projections not admitted by Task
0B4a's helper surface.  Here, parsing is a non-admissible canonical-byte and
bootstrap-digest compatibility check only.  A paired supplied JSON/sidecar
substitution is outside this gate: parent-retained descriptor-pinned identity
and provenance admission remain later requirements, along with the full nested
schema, policy, certificate, and manifest checks.

## 2. Immutable and public boundaries

Task 0A and Task 0B1 sources and APIs remain immutable.  The session keeps
the exact public surface, constants, frozen data-class fields, and direct
constructor refusal specified in Task 0B4a.  It may add exactly these seven
private module-level helpers and no other class or function:

```text
_freeze_session_data(value: object) -> object
_canonical_session_json_bytes(value: object) -> bytes
_session_config_digest(value: object) -> str
_parse_session_config_bytes(config_bytes: bytes, sidecar_bytes: bytes) -> Mapping[str, object]
_materialize_exact_builtins(value: object) -> object
_base_config_projection(config: SessionConfig) -> dict[str, object]
_validate_and_encode_receipt(payload: dict[str, object],
                             phase: receipt_schema.ReceiptPhase,
                             sequence: int) -> tuple[receipt_schema.ReceiptPayload, bytes]
```

`SessionConfig` is still not constructible through its public constructor.
Focused tests may use `object.__new__` plus `object.__setattr__` locally to
exercise only `_base_config_projection`; that test technique does not create a
source factory or an admitted configuration.

## 3. Pure data contract

The helpers accept only bounded, exact built-in data.  A string/key must be
printable ASCII and at most 512 bytes.  A non-Boolean integer is in
`[-9223372036854775808, 9223372036854775807]`.  Values are exact `None`,
`bool`, bounded non-Boolean `int`, `str`, `dict`, or `list`; an exact tuple
object-pair representation is the parser's implementation form for detecting
JSON duplicate keys.  `_freeze_session_data` accepts that private representation
so the supplied-byte parser and focused in-memory tests can exercise it, but it
carries no provenance and a direct caller cannot treat success as configuration
admission.  Container subclasses, generic mappings/sequences, bytes inside
JSON, floats, aliases, and cycles refuse.  The root is depth zero; depth 16 may
contain only a scalar (an empty or nonempty container at that depth refuses), no
value may be deeper than 16, no more than 256 values are charged (keys are uncharged), and
the cumulative semantic byte charge is at most 8,192 bytes: it is an explicitly
conservative pre-serialization estimate of key/string ASCII bytes, canonical
integer or literal bytes, and container syntax.  The exact canonical JSON byte
length (including quote/escape expansion) is independently recomputed and
limited to 8,192 bytes by `_canonical_session_json_bytes` and by the parser
before it returns a frozen snapshot; freezing/materializing alone can accept a
semantic value that the canonical-byte step subsequently rejects.  A repeated nonempty container
identity is refused before a second traversal or charge.  The sole exception
is the immutable zero-length tuple: Python's `object_pairs_hook=tuple` may
reuse that singleton for distinct JSON empty objects, and deep-frozen empty
lists use the same child-free representation.  It is never traversed as a
nonempty container and cannot introduce an alias edge.  A deep-frozen result
uses only `MappingProxyType` mappings and tuples.

`_materialize_exact_builtins` accepts either this exact raw built-in shape or
the preceding frozen shape.  Its `MappingProxyType` input is an internal
representation trusted only when it was produced by `_freeze_session_data` in
the same pure-data boundary; it is not provenance or a generic mapping
authentication mechanism.  A future admitted caller must freeze/revalidate
untrusted input before relying on it.  The helper returns a fresh, unaliased
exact `dict`/`list` snapshot suitable for the sealed Task 0A APIs.  It is never
a generic mapping adapter.

`_canonical_session_json_bytes` first materializes a fresh exact built-in
snapshot, then emits byte-for-byte canonical ASCII JSON: sorted keys, compact
separators, no floats, and no noncanonical whitespace.  It enforces the same
8,192-byte maximum.

`_session_config_digest` requires an exact object containing a string
`session_config_sha256` member, removes only that member from one fresh local
projection, and SHA-256 hashes the canonical result.  It has no path,
environment, sidecar, or ambient input.

`_parse_session_config_bytes` accepts only a nonempty `bytes` configuration of
at most 8,192 bytes and a sidecar of exactly 64 lower-case hexadecimal bytes.
It parses supplied bytes with duplicate-key detection, rejects noncanonical
raw bytes, requires the exact Section 3 top-level key set, requires top-level
`schema == 1`, and checks that `namespace` and the closed five-member
`base_config` agree on schema and namespace.  Its only helper calls are
`_freeze_session_data`, `_canonical_session_json_bytes`, and
`_session_config_digest`; it requires:

```text
computed_session_config_digest == embedded session_config_sha256 == sidecar bytes
```

It returns a frozen **non-admitted** snapshot.  In particular, it does not yet
recompute `namespace_policy_sha256`, `session_policy_sha256`, user/FD/mount
policy digests, certificate digests, direct-input grammar, or any nested
policy/certificate/provenance relation.  Those checks are mandatory before a
future session can emit PRE, but are out of this pure helper increment.

`_base_config_projection` receives an exact `SessionConfig` object whose `data`
member is the internal `MappingProxyType` snapshot, materializes only its
`base_config` member into a fresh five-member `dict`, and immediately passes
`attester.AttesterConfig(projection)` to `attester.validate_config`.
Its returned dictionary is a private compatibility value only: it is never
stored back into `SessionConfig`, exposed through the public API, or treated as
configuration-admission evidence.

`_validate_and_encode_receipt` accepts only a fresh exact built-in `dict` owned
by its immediate caller.  Its `sequence` is an exact non-Boolean `int`; it
accepts only `(ReceiptPhase.PRE, 0)` or `(ReceiptPhase.POST, 1)`, calls the
matching receipt validator once on that same object, and encodes that same
unmodified object once with Task 0A.  It
returns the immutable receipt snapshot and frame bytes.  It never encodes the
validator's `MappingProxyType` snapshot.  The count is a **direct helper-edge**
count; the sealed receipt validator may internally call Task 0A itself.

## 4. Source boundary and direct edges

The only imports are the B4a skeleton imports plus `hashlib`, `json`, and
`types`.  `child_runner` and `measurements` remain inert imported identity
edges only: no attribute of either may be read or called.  The source has no
`__main__`, CLI, nested definition/import, top-level execution, dynamic import
or call target, descriptor/path/environment/clock access, raw receipt/ACK
operation, barrier call, child operation, or all-true evidence construction.

| Helper | Permitted imported-module attribute/call edge |
| --- | --- |
| `_freeze_session_data` | `types.MappingProxyType` only, plus self-recursion |
| `_canonical_session_json_bytes` | `_materialize_exact_builtins`, `json.dumps` |
| `_session_config_digest` | `_materialize_exact_builtins`, `_canonical_session_json_bytes`, `hashlib.sha256` |
| `_parse_session_config_bytes` | `json.loads`, `json.JSONDecodeError` only for supplied-byte normalization, and the three pure helpers above |
| `_materialize_exact_builtins` | `types.MappingProxyType` type inspection only, plus self-recursion |
| `_base_config_projection` | `types.MappingProxyType` type inspection, `_materialize_exact_builtins`, `attester.AttesterConfig`, `attester.validate_config` |
| `_validate_and_encode_receipt` | `ReceiptPhase`/`FrameType` constants, exactly one matching receipt validator and `protocol.encode_frame` |

The B4b static gate must parse the source before importing it, pin the complete
public/private definition and import sets, verify annotations/signatures and
class bodies, and reject every imported-module call outside this table.  The
focused behavior tests must run that pre-import contract before importing the
session target.

## 5. Test-first acceptance

Before implementation, a pre-import source-contract test must RED against the
B3a skeleton for its missing helper surface.  After implementation it must be
GREEN and behavior tests must prove only:

1. bounded snapshot/materialization and canonical-byte rejection behavior;
2. duplicate-key and independent sidecar, embedded, and computed-digest refusal;
3. non-admitted parse returns a frozen snapshot without path I/O;
4. base projection is fresh and calls the sealed Task 0A validator exactly
   once on the exact same projection object supplied to `AttesterConfig`; and
5. PRE and POST compatibility each encode the caller-owned exact payload, not
   the frozen receipt snapshot, with the matching validator before the encoder
   and with the exact unmutated payload object passed to both.

No result from this gate is session admission, raw-stream behavior, namespace
evidence, child launch, fixture readiness, or host compatibility evidence.
