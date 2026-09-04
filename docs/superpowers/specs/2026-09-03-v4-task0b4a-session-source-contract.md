# V4 Task 0B4a — Session Source Contract

**Status:** sealed documentation plus intentional-RED checkpoint; no source
implementation.

**Supersession note:** the later, separately authorized Task 0B4b-pure
checkpoint is sealed at
`docs/superpowers/specs/2026-09-03-v4-task0b4b-pure-session-helpers-contract.md`.
It implements only seven bounded in-memory compatibility helpers and preserves
the fail-closed public entrypoints.  Its deliberately non-admitted parser
supersedes this checkpoint's broader proposed parser/admission language; a
state machine still needs its own later authority.

**Authority:** The current Task 0B4a authority permits this contract and a
pre-import AST/source-byte test for
`tools/reaper_v4_session.py`. It permits no import or execution of that module,
no change to its source before independent review of this contract, and no
session, child, barrier, descriptor, pipe, namespace, Bubblewrap, systemd,
REAPER, X11, audio, network, or host action. At the B4a handoff, Task 0B4b
needed a fresh explicit authority before any session source import or execution.
That historical handoff was consumed only by the later sealed B4b-pure scope
described above.

## 1. Immutable boundaries

Task 0A and Task 0B1 are immutable. In particular:

- Task 0A accepts a top-level mapping for frame encoding but cannot serialize
  nested `MappingProxyType` values from a validated receipt snapshot.
- Task 0A base-config validation rejects the frozen top-level mapping held by
  a deep-frozen session snapshot.
- Task 0B1 receipt validation is the authority for receipt grammar and returns
  an immutable snapshot; it is not an encoder input.
- Task 0B1 measurements and child adapter remain their sealed APIs. The
  session owns neither a second coordinator nor a `subprocess` call.

The B4a module therefore owns only private, pure compatibility projections. It
must not weaken the existing validators to accommodate a mutable or frozen
replacement.

## 2. Preserved public surface

The future B4b source, produced from this B4a contract, must preserve exactly
this public surface:

```text
__all__ = (
  SessionError, SessionConfig, SessionResult,
  load_session_config, run_session
)

SESSION_ENTRYPOINT_KIND = "session_entrypoint"
SESSION_ENTRYPOINT_ROLE = "same_namespace_pre_ack_child_post_owner"
SESSION_CONFIG_PATH = "/run/m3-v4/session-config.json"
SESSION_DIGEST_PATH = "/run/m3-v4/session-config.sha256"
```

`SessionConfig` and `SessionResult` remain `@dataclasses.dataclass(frozen=True,
init=False)` data classes. `SessionConfig` has exactly one public annotated
field, `data: Mapping[str, object]`. `SessionResult` has exactly the four
public annotated integer fields `child_pid`, `child_returncode`,
`pre_monotonic_ns`, and `post_monotonic_ns`. Their direct `__init__` methods
remain no-argument fail-closed `SessionError` stubs; a future B4b private
factory may construct a validated instance only with `object.__new__` and
`object.__setattr__`. The public signatures remain exactly:

```text
load_session_config(config_path: str, digest_path: str) -> SessionConfig
run_session(config: SessionConfig) -> SessionResult
```

Neither public function may perform work in B4a: each continues to raise
`SessionError` before configuration I/O, validation, clocks, diagnostics,
descriptor access, raw transport, measurements, barrier work, or child work.

## 3. Private pure-contract surface

The later B4b source implementation must define only these additional private
functions:

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

Their contract is intentionally limited:

1. `_freeze_session_data` accepts only bounded exact built-in JSON-like
   containers and scalars, detects cycles, has explicit node/depth/byte bounds,
   and returns deeply immutable mappings/tuples.
2. `_canonical_session_json_bytes` accepts the same bounded exact-built-in
   shape, rejects floats and non-ASCII keys/identifiers, emits sorted-key UTF-8
   JSON with no insignificant whitespace, and never reads a path.
3. `_session_config_digest` hashes the canonical full configuration with only
   `session_config_sha256` omitted; it has no sidecar or environment input.
4. `_parse_session_config_bytes` accepts only bounded bytes, checks that the
   sidecar is exactly a 64-byte lower-case hexadecimal digest with no newline,
   rejects duplicate JSON object keys and noncanonical raw bytes, performs the
   closed structural/cross-field checks in the Task 0B3 design, and requires
   computed, embedded, and sidecar digest equality. It does not open a file,
   prove descriptor provenance, or claim resistance to a paired substitution.
5. `_materialize_exact_builtins` creates a fresh, bounded, unaliased exact
   built-in copy from a frozen snapshot. Its output is used only locally.
6. `_base_config_projection` produces only
   `{schema, namespace, nonce, config_sha256, inputs}` as a fresh exact-built-
   in dictionary, then immediately passes it to
   `attester.validate_config(attester.AttesterConfig(...))`. It must never be
   stored in `SessionConfig` or exposed to a caller.
7. `_validate_and_encode_receipt` requires an exact-built-in payload. It
   accepts only `(ReceiptPhase.PRE, 0)` or `(ReceiptPhase.POST, 1)`, calls the
   corresponding Task 0B1 validator exactly once on that very object, and
   calls the Task 0A encoder exactly once on that same unmodified object. It
   returns the immutable validation snapshot and encoded bytes; it never
   encodes `receipt_schema.ReceiptPayload.payload` or a later replacement.

The receipt phase and payload annotations are names under the sealed
`receipt_schema` module alias only. They do not make that module a transport,
I/O, or child owner.

The broader parser/admission proposal in this historical section was narrowed
before source work. The B4b-pure contract is the authoritative specification
for the actual seven-helper source; no current source implements full nested
policy/certificate admission.

### 3.1 Exact external dependency edges

The following table is the complete external/dependency-edge graph. It lists
private-helper relationships and calls into imported modules; ordinary exact-
built-in operations needed to validate bounded values (for example `type`,
`id`, `len`, `encode`, `decode`, and `hexdigest`) are not external edges. B4b
must introduce a separate reviewed static contract before implementation that
enumerates the allowed helper-local builtins and every source-level call. Counts
below apply to one successful helper invocation.

| Helper | Allowed direct calls | Count / side-effect boundary |
| --- | --- | --- |
| `_freeze_session_data` | itself; `types.MappingProxyType` | finite recursive snapshot only; no file, descriptor, clock, or environment read |
| `_canonical_session_json_bytes` | `_materialize_exact_builtins`; `json.dumps` | exactly one canonical JSON serialization; no path read |
| `_session_config_digest` | `_materialize_exact_builtins`; `_canonical_session_json_bytes`; `hashlib.sha256` | exactly one digest over the omission projection |
| `_parse_session_config_bytes` | `json.loads`; `_canonical_session_json_bytes`; `_session_config_digest`; `_freeze_session_data` | parse supplied bytes only; no path, descriptor, or ambient-state call |
| `_materialize_exact_builtins` | itself | finite copy only; no sealed component call |
| `_base_config_projection` | `_materialize_exact_builtins`; `attester.AttesterConfig`; `attester.validate_config` | exactly one base-config validation; private projection only |
| `_validate_and_encode_receipt` | `receipt_schema.validate_pre_payload` **or** `receipt_schema.validate_post_payload`; `protocol.encode_frame` | exactly one matching validator and exactly one matching encoder; no exchange, frame write, ACK, or child call |

## 4. Source-shape boundary

The future B4b **pure compatibility-helper increment** established from this
B4a contract may import only `dataclasses`, `hashlib`, `json`, `types`,
`collections.abc.Mapping`, and the five sealed V4 component modules already
declared by the skeleton. It may not import or dynamically load `os`,
`pathlib`, `stat`, `select`, `time`, `subprocess`, `ctypes`, `importlib`,
`runpy`, networking modules, or an alternate launcher.

It has no `__main__`, CLI, top-level call/I/O, decorator/default-expression
side effect, control-FD API, child-runner wrapper, raw frame/ACK consumer, or
all-true evidence constructor. Its only top-level executable forms are the
module docstring, imports, constant literals, exception/class definitions, and
function definitions. Any future evidence helper, fixed-path reader, raw
transport operation, barrier call, measurement call, clock, or child adapter
invocation is outside this pure increment. A B4b state-machine increment needs
its own fresh user authority and reviewed source contract; B4c retains all
outer-harness work.

## 5. Test-first checkpoint

`tests/test_reaper_v4_task0b4a_static_contract.py` read and parsed the session
source before any target import during B4a. Its current-skeleton assertion
pinned the B3a source bytes and its two future-shape assertions were first
observed RED, then retained as `unittest.expectedFailure` specifications. At
the sealed B4b-pure checkpoint, that preliminary test was retired and replaced
by `tests/test_reaper_v4_task0b4b_static_contract.py`, which enforces exact
function-local rules before the target import. The historical B4a test did not
itself make the contract executable evidence.
