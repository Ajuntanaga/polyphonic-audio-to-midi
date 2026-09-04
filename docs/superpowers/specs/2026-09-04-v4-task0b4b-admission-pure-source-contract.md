# V4 Task 0B4b-admission-pure — SessionConfig Admission Source Contract

**Status:** sealed source-and-test checkpoint under the user's project-wide
authorization. The implemented session source SHA-256 is
`5bb71ab032b13b59170dd8034528b7b0e990751fd0d0b5b59da6e711a9ce1c11`.
This first source-changing successor to Task 0B4b-pure is deliberately limited
to bounded in-memory configuration admission; it does not authorize a session
run, transport, evidence collection, fixture, namespace, REAPER, or host
action.

**Implements:**
`docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md` §3,
as ordered by
`docs/superpowers/specs/2026-09-04-v4-task0b4b-state-machine-source-contract.md` §3, item 1.

## 1. Scope and non-authority

This increment may modify only:

- `tools/reaper_v4_session.py`;
- `tests/test_reaper_v4_task0b4b_static_contract.py` (replaced in place as the
  admission-pure pre-import source contract);
- `tests/test_reaper_v4_task0b4b_pure_helpers.py` (preserved regressions);
- `tests/test_reaper_v4_task0b4b_admission.py` (new pure admission tests);
- this contract, its implementation plan, `RESUME.md`, the V4 plan, and the
  canonical operations note after the gate is sealed.

It may not modify Task 0A or Task 0B1 sources, schemas, or tests. The successor
source removes the inert `child_runner` and `measurements` imports. Its exact
import set is the existing future/dataclass/hash/json/types/`Mapping` imports
plus `attester`, `protocol`, and `receipt_schema`; no other import is allowed.
It may not import or call `os`, `pathlib`, `stat`, `fcntl`, `select`, `time`,
`socket`, `subprocess`, `io`, `sys`, `importlib`, `ctypes`, `tempfile`,
`pickle`, `marshal`, `inspect`, `platform`, `threading`, `signal`, or any
process, descriptor, path, reflection, dynamic-evaluation, or unlisted
serialization capability. The retained `json.dumps`/`json.loads` calls are
allowed only inside the existing named canonical/digest/parser helpers; no new
serialization edge is allowed. The source may not open a path; inspect a
descriptor; establish the Task 0A barrier; emit/read a frame; construct or run
a child; collect evidence; form a namespace; or launch Bubblewrap, systemd,
REAPER, X11, audio, network, fixture, or host work.

The public surface remains exact and fail closed:

```python
load_session_config(config_path: str, digest_path: str) -> SessionConfig
run_session(config: SessionConfig) -> SessionResult
```

Both functions retain their one-statement `SessionError` bodies. `SessionConfig`
and `SessionResult` retain their existing frozen, `init=False` forms and
one-statement failing constructors. This gate adds no runtime root.

## 2. Trusted-snapshot boundary

Every caller-provided `SessionConfig` is untrusted. Exact type identity,
`MappingProxyType`, and a frozen dataclass are not authenticity proof.

The source adds these private interfaces:

```python
def _admit_session_config(config: SessionConfig) -> SessionConfig: ...
def _validate_session_config_relations(value: Mapping[str, object]) -> None: ...
def _child_spec_projection(value: Mapping[str, object]) -> dict[str, object]: ...
def _canonical_session_sha256(value: object) -> str: ...
```

The exact additional private helper inventory is:

```python
def _require_mapping(value: object, expected: tuple[str, ...], label: str) -> Mapping[str, object]: ...
def _require_ascii(value: object, label: str, minimum: int, maximum: int) -> str: ...
def _require_digest(value: object, label: str) -> str: ...
def _require_integer(value: object, label: str, minimum: int, maximum: int) -> int: ...
def _require_absolute_path(value: object, label: str) -> str: ...
def _require_relative_path(value: object, label: str, components: int, allow_dot: bool) -> str: ...
def _validate_id_map(value: object, label: str) -> list[Mapping[str, object]]: ...
def _mapped_outer_id(records: list[Mapping[str, object]], inside: int, label: str) -> int: ...
def _validate_certificate(value: object, kind: str, config: Mapping[str, object]) -> None: ...
```

No other module-level helper, nested function, class, lambda, callback, or
callable alias is permitted. The successor static contract pins every signature
and these direct local edges:

```text
_admit_session_config -> _materialize_exact_builtins (once)
                      -> _freeze_session_data (once)
                      -> _validate_session_config_relations (once)
                      -> object.__new__/object.__setattr__
_validate_session_config_relations -> the require helpers,
                                      _canonical_session_sha256,
                                      _validate_id_map,
                                      _mapped_outer_id,
                                      _validate_certificate,
                                      _child_spec_projection,
                                      attester.AttesterConfig/validate_config
_validate_certificate -> the require helpers + _canonical_session_sha256
_child_spec_projection -> the require helpers only
```

`_admit_session_config` requires `type(config) is SessionConfig`, reads
`config.data` exactly once into `untrusted_data`, then requires
`type(untrusted_data) is types.MappingProxyType`. It then, exactly once each:

1. materializes `untrusted_data` to one bounded fresh exact-builtins tree;
2. deep-freezes that local tree into a new local snapshot;
3. validates all relations only against that new snapshot; and
4. returns a freshly `object.__new__`/`object.__setattr__`-constructed
   `SessionConfig` containing only that validated local snapshot.

After the one local assignment, it must not dereference `config` or
`config.data` again. Any ordinary `Exception` caused by traversal, type,
comparison, hashing, or canonicalization normalizes to `SessionError`;
`BaseException` is never caught and cannot produce an admitted result. The returned data must be
unaliased from every caller-owned object and from all projection return values.

`_child_spec_projection` accepts only the frozen local snapshot passed by
`_validate_session_config_relations`; it is not an alternate admission path.
It rechecks the closed child/environment subset before it returns a fresh,
unaliased exact `dict` whose tuple contents are immutable non-JSON values:

```python
{
  "argv": tuple[str, ...],
  "cwd": str,
  "environment": tuple[tuple[str, str], ...],
  "timeout_ms": int,
}
```

It is a pure future-`ChildSpec` projection, not `child_runner.ChildSpec`
construction. Its environment tuple is lexicographically ordered by key.
`child.argv` is an ordered exact list of 1–16 nonempty printable-ASCII strings
of at most 512 bytes. `argv[0]` is an absolute path under the Task 0B3 path
grammar; every later argument is printable ASCII with no NUL. `cwd` is an
absolute path, `timeout_ms == 30000`, and no PATH lookup/fallback is implied.
Direct calls with a mutable/non-frozen mapping, a malformed child map, or a
mutated caller backing object must raise `SessionError` or return a projection
unaffected by that later mutation.

The exact per-helper call policy used by the pre-import source test is:

| Helper | Permitted local calls | Permitted external/module calls | Permitted built-ins/methods |
| --- | --- | --- | --- |
| `_canonical_session_sha256` | `_canonical_session_json_bytes` once | `hashlib.sha256` once | `hexdigest` once |
| `_require_mapping` | none | `types.MappingProxyType` type inspection only | `type`, `set` |
| `_require_ascii` | none | none | `type`, `len`, `encode`, `all` |
| `_require_digest` | `_require_ascii` once | none | `all` |
| `_require_integer` | none | none | `type` |
| `_require_absolute_path` | `_require_ascii` once | none | `split`, `startswith`, `endswith`, `len`, `all` |
| `_require_relative_path` | `_require_ascii` once | none | `split`, `startswith`, `endswith`, `len`, `all` |
| `_validate_id_map` | `_require_mapping`, `_require_integer` | none | `type`, `len`, `append` |
| `_mapped_outer_id` | `_require_integer` | none | none |
| `_validate_certificate` | `_require_mapping`, `_require_ascii`, `_require_digest`, `_require_integer`, `_validate_id_map`, `_mapped_outer_id`, `_canonical_session_sha256` | none | `dict`, `tuple`, `enumerate`, `all`, `any`, `pop` |
| `_child_spec_projection` | `_require_mapping`, `_require_ascii`, `_require_absolute_path`, `_require_integer` | none | `type`, `len`, `tuple`, `sorted`, `dict`, `enumerate`, `append` |
| `_validate_session_config_relations` | every named require/validation helper, `_canonical_session_sha256`, `_child_spec_projection`, `_session_config_digest` | `attester.AttesterConfig` once and `attester.validate_config` once; `types.MappingProxyType` type inspection; `protocol.MAX_FRAME_BYTES` constant read | `dict`, `set`, `tuple`, `len`, `sorted`, `all`, `enumerate`, `items`, `append`, `add`, `startswith` |
| `_admit_session_config` | `_materialize_exact_builtins` once, `_freeze_session_data` once, `_validate_session_config_relations` once | `types.MappingProxyType` type inspection; `object.__new__` once, `object.__setattr__` once | `type` |

The source test rejects every other local, imported, bare, method, dynamic, or
computed call target. The preserved B4b-pure helper call rules remain unchanged.

## 3. Exact semantic admission

The existing bounded snapshot/canonical rules remain in force: exact built-in
null/Boolean/integer/string/list/object values, printable ASCII strings and
keys, no aliases/cycles, at most 256 structural nodes, scalar-only depth 16,
at most 512 bytes per string/key, and at most 8,192 canonical bytes. Booleans
never satisfy an integer requirement. Every digest is exactly 64 lower-case
hexadecimal characters.

The validator requires all of the following before returning normally.

1. The exact 16-member `SESSION_CONFIG_KEYS` top-level object, `schema == 1`,
   and every declared digest/path/string/number within its documented bound.
2. `base_config` is exactly `{schema, namespace, nonce, config_sha256, inputs}`;
   its schema/namespace equal the top level, its Task 0A digest validates, and
   `inputs` is exactly `direct_input_digests` plus
   `{"session_policy": session_policy_sha256}`.
3. `row` is exactly `{sample_rate_hz: 44100, block_size: 32}`. Direct-input
   names follow the sealed receipt grammar: 1–128 chars, first `[a-z]`,
   remaining `[a-z0-9_-]`, 1–15 members, and never `session_policy`.
4. `namespace_policy_sha256 == sha256(namespace_expectations)` and
   `session_policy_sha256 == sha256` of exactly
   `{row, direct_input_digests, runtime_manifest_sha256,
   run_input_manifest_sha256, fixture_manifest_sha256,
   namespace_policy_sha256, fixture_certificates, bwrap,
   namespace_expectations, child, limits}`.
5. `fixture_certificates`, `bwrap`, `namespace_expectations`, `child`, and
   `limits` have every exact closed member set in Task 0B3 §3. `limits` equals
   the six fixed values `{5000, 5000, 5000, 1024, 2064, 30000}` under their
   named keys; `child.timeout_ms == 30000`.
6. Every configuration-defined absolute path has the Task 0B3 normalized
   grammar; every relative scan/resource path has the Task 0B3 component
   grammar. This validates strings only and claims no filesystem evidence.
7. User/gid mappings have 1–8 exact triples, monotonically sorted non-overlap,
   valid effective-ID coverage, and canonical policy digest. Descriptor and
   mount policies have their closed projections and canonical digests.
8. The namespace environment and child environment are exact, byte-identical
   six-key maps. Home/PWD/cwd, X11 display/socket/authority, private-home,
   scan tree, measurement plan, inherited FDs, and mount paths meet every
   Section 3 equality, count, order, uniqueness, and range relation.
9. Exactly two certificate records exist. Their canonical self-digests omit
   only `certificate_sha256`; their kinds/results are fixed; their manifest,
   Bubblewrap, namespace, descriptor, mount, and user-map policy fields bind
   exactly to the admitted configuration; and each certificate UID equals the
   mapping-derived host UID.
10. The top-level `session_config_sha256` equals SHA-256 of the canonical
    configuration with only that field omitted. This validates supplied data;
    it does not claim descriptor-pinned sidecar identity or paired-substitution
    resistance.

`limits.max_frame_bytes` is validated as the fixed `2064` and equal to
`protocol.MAX_FRAME_BYTES`. The later bootstrap-transport gate alone queries
and binds `PIPE_BUF`; admission-pure neither queries it nor claims that runtime
relation is established.

No rule in this increment infers actual parent retention, certificate
applicability, mount state, FD state, X11 state, scan contents, barrier state,
or receipt fact. Those stay with later evidence/transport/state/fixture gates.

## 4. Source shape and allowed edges

The B4b-pure static contract is replaced before production edits. The replacement
must parse source before import and pin:

- exact imports, `__all__`, constants, data classes, public signatures, and
  immediate-failure public/constructor bodies;
- the seven B4b-pure helpers, the four admission interfaces above, and exactly
  the nine named local validation primitives above;
- no top-level call, dynamic import/call, lambda, assertion, nested definition,
  decorator argument, `with`, or imported attribute use outside a per-helper
  allowlist; generator expressions are allowed only as the direct input to
  the named bounded `all()`/`any()` checks or the existing frozen-snapshot
  helper's exact `tuple()` reconstruction; all bare calls and methods must be in a
  named per-helper allowlist; and
- no imported module/attribute read outside that allowlist, no capability alias,
  no `child_runner`/`measurements` import/read/call, and no I/O/process/clock/
  transport/evidence module edge;
- the one-way ownership edge
  `_admit_session_config -> materialize -> freeze -> relation validation ->
  private SessionConfig construction`; and
- exactly one `config.data` attribute read, assigned to `untrusted_data` before
  its type check and every materialization call; no later `config` or
  `config.data` read.

The pre-import test must refuse optimized Python with an explicit exception.
It used two explicit test-first phases: Phase A admitted only exact-signature
inert `SessionError` stubs for all 13 new helpers and proved the import/public
surface boundary. Phase B was written and observed RED after behavior tests
existed, then sealed the final call graph above. The behavior tests imported the
target only after Phase A passed.

## 5. Required TDD evidence

Tests are written and observed RED before code. They retain all seven B4b-pure
helper regressions and add a fully valid synthetic SessionConfig vector plus
negative coverage for each relation family:

- forged/mutable/aliasing `SessionConfig` and proxy backing mutation;
- every closed key set, bool-as-int, scalar/path/digest bound, canonical byte,
  nesting, alias, and duplicate-key failure;
- each direct-input/base/row/session-policy/namespace-policy mismatch;
- uid/gid map arithmetic, descriptor/mount policy, six-key environment/X11,
  child projection, measurement/scan-root, fixed-limit, and certificate
  mismatch; and
- proof that a returned admitted snapshot and its base/child projections remain
  unchanged after caller-side mutation.

The admission suite records a named mutation case for every nested map/list and
every digest projection: top-level/base/direct-input/row; namespace/session/
user/FD/mount policies; both certificates and their fixed results; uid/gid
ordering, overlap, and UID arithmetic; X11/environment/home/cwd bindings;
measurement/scan/mount/FD ordering and bounds; child argv/environment/timeout;
and each fixed limit. A table-driven family label alone is insufficient.

All failures raise `SessionError`; none may call a later state, receipt,
transport, evidence, or child edge.

## 6. Seal criteria

The replaced pre-import contract, preserved B4b helper tests, new admission
tests, and immutable Task 0B1 static checks passed 18 checks together. Three
independent reviews were CLEAN after test-first repairs for the X11 environment
binding, scan-root mount closure, forged object normalization, lexical
environment order, and no-dot X11 screen relation. `git diff --check` passed.
No path, descriptor, process, transport, barrier, fixture, namespace, REAPER,
or host behavior ran. The next gate is `Task 0B4b-evidence`, not bootstrap
transport, a state machine, fixture, or host work.
