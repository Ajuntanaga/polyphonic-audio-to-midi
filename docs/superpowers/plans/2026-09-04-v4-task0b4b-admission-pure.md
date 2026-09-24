# V4 Task 0B4b-admission-pure Implementation Plan

**Status:** sealed implementation checkpoint. The source SHA-256 is
`5bb71ab032b13b59170dd8034528b7b0e990751fd0d0b5b59da6e711a9ce1c11`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit only a fully closed, self-consistent, locally snapshotted
`SessionConfig` in memory while retaining fail-closed public session entrypoints.

**Architecture:** The existing B4b-pure helpers remain compatibility primitives.
New private validation code materializes an untrusted frozen proxy once,
deep-freezes a local snapshot, checks every Task 0B3 Section 3 relation, and
returns a fresh private `SessionConfig`. No code in this plan touches a path,
descriptor, process, frame, barrier, measurement, or child.

**Tech Stack:** Python standard library (`dataclasses`, `hashlib`, `json`,
`types`), existing immutable Task 0A/B1 validators, and `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-04-v4-task0b4b-admission-pure-source-contract.md`

## Global Constraints

- Preserve Task 0A and Task 0B1 byte-sealed APIs unchanged.
- Retain `load_session_config()` and `run_session()` as immediate `SessionError`
  stubs.
- Do not import/call any filesystem, descriptor, timing, transport, child,
  evidence, fixture, namespace, REAPER, or host capability.
- Treat each caller-provided `SessionConfig` as untrusted and retain no
  caller-owned mapping after admission starts.
- Use TDD: every production behavior begins with a focused observed RED.

---

### Task 1: Replace the pre-import source contract

**Files:**
- Modify: `tests/test_reaper_v4_task0b4b_static_contract.py`
- Modify: `tests/test_reaper_v4_task0b4b_pure_helpers.py`
- Test: `tests/test_reaper_v4_task0b4b_static_contract.py`

**Interfaces:**
- Consumes: the sealed B4b-pure public surface and helper signatures.
- Produces: a pre-import AST contract for the seven existing helpers plus
  `_canonical_session_sha256`, `_child_spec_projection`,
  `_validate_session_config_relations`, and `_admit_session_config`.

- [ ] **Step 1: Write the failing source-shape expectation**

```python
EXPECTED_FUNCTIONS |= {
    "_canonical_session_sha256",
    "_child_spec_projection",
    "_validate_session_config_relations",
    "_admit_session_config",
    "_require_mapping", "_require_ascii", "_require_digest",
    "_require_integer", "_require_absolute_path", "_require_relative_path",
    "_validate_id_map", "_mapped_outer_id", "_validate_certificate",
}
```

- [ ] **Step 2: Run the static test and verify RED**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_static_contract -v`

Expected: FAIL because the four admission helpers are absent; the target module
is not imported.

- [ ] **Step 3: Add all 13 exact-signature inert helper stubs after the
      observed RED**

```python
def _admit_session_config(config: SessionConfig) -> SessionConfig:
    raise SessionError("session configuration admission is not implemented")

def _validate_session_config_relations(value: Mapping[str, object]) -> None:
    raise SessionError("session configuration admission is not implemented")
```

Add every other helper named by the source contract with its exact signature
and the same one-statement `SessionError`. Phase A permits only those stubs;
it does not permit a hidden capability or partial implementation.

- [ ] **Step 4: Add Phase-A source-shape guards and verify GREEN**

```python
assert forbidden_module_roots.isdisjoint(referenced_module_roots)
assert public_stub.body == [raise_session_error]
assert no_forbidden_import_or_dynamic_call(tree)
assert every_new_helper_is_exact_signature_one_statement_session_error(functions)
```

- [ ] **Step 4: Run the static test and verify the intended remaining RED**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_static_contract -v`

Expected: PASS; no target module is imported.

### Task 2: Write admission behavior tests

**Files:**
- Create: `tests/test_reaper_v4_task0b4b_admission.py`
- Test: `tests/test_reaper_v4_task0b4b_admission.py`

**Interfaces:**
- Consumes: `_admit_session_config(config) -> SessionConfig` and
  `_child_spec_projection(value) -> dict[str, object]`.
- Produces: an inert, exact-builtins synthetic valid configuration builder and
  pure relation regressions.

- [ ] **Step 1: Write one valid admission test and one forged-proxy test**

```python
admitted = session._admit_session_config(forged_config(valid_config()))
self.assertIs(type(admitted.data), types.MappingProxyType)
backing["child"]["cwd"] = "/mutated"
self.assertEqual(session._child_spec_projection(admitted.data)["cwd"], "/home/vst")
```

- [ ] **Step 2: Run the new test and verify RED against inert stubs**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_admission -v`

Expected: FAIL with the exact admission-not-implemented `SessionError`, not an
I/O, fixture, or host error.

- [ ] **Step 3: Add table-driven relation negatives**

```python
for mutate in (wrong_base_inputs, wrong_policy_digest, wrong_certificate_digest,
               wrong_uid_mapping, wrong_child_environment, wrong_fixed_limit):
    with self.assertRaises(session.SessionError):
        session._admit_session_config(forged_config(mutate(valid_config())))
```

- [ ] **Step 4: Add the named field-by-field mutation matrix and rerun RED**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_admission -v`

Expected: FAIL through the inert admission helper, not fixture or host errors.

- [ ] **Step 5: Strengthen the static contract to Phase B and observe RED**

```python
assert admit_edges == ["_materialize_exact_builtins", "_freeze_session_data",
                       "_validate_session_config_relations"]
assert count_config_data_reads(functions["_admit_session_config"]) == 1
assert materialize_argument(functions["_admit_session_config"]) == "untrusted_data"
```

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_static_contract -v`

Expected: FAIL because inert stubs do not have the sealed final call graph.

### Task 3: Implement bounded relation admission

**Files:**
- Modify: `tools/reaper_v4_session.py`
- Test: `tests/test_reaper_v4_task0b4b_admission.py`

**Interfaces:**
- Consumes: one untrusted `SessionConfig` whose data is a `MappingProxyType`.
- Produces: a fresh validated `SessionConfig`, a fresh child projection, or
  `SessionError`.

- [ ] **Step 1: Implement one-way snapshot admission**

```python
if type(config) is not SessionConfig:
    raise SessionError("session configuration is invalid")
untrusted_data = config.data
if type(untrusted_data) is not types.MappingProxyType:
    raise SessionError("session configuration is invalid")
materialized = _materialize_exact_builtins(untrusted_data)
frozen = _freeze_session_data(materialized)
_validate_session_config_relations(frozen)
admitted = object.__new__(SessionConfig)
object.__setattr__(admitted, "data", frozen)
return admitted
```

- [ ] **Step 2: Implement exact scalar/key/path/digest helpers and all closed
      Task 0B3 shapes**

```python
if set(value) != expected_keys:
    raise SessionError("session configuration shape is invalid")
if type(number) is not int:
    raise SessionError("session integer is invalid")
```

- [ ] **Step 3: Implement all canonical hash/equality relations**

```python
if _canonical_session_sha256(namespace_expectations) != namespace_policy_sha256:
    raise SessionError("namespace policy digest is invalid")
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b4b_static_contract tests.test_reaper_v4_task0b4b_pure_helpers tests.test_reaper_v4_task0b4b_admission -v`

Expected: PASS with no imported filesystem/process behavior.

### Task 4: Seal the admission gate

**Files:**
- Modify: `RESUME.md`
- Modify: `docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md`
- Modify: `docs/superpowers/specs/2026-09-04-v4-task0b4b-admission-pure-source-contract.md`
- Modify: `$HOME/Documents/Obsidian/ResearchOS/Systems/REAPER/Polyphonic Audio to MIDI/Polyphonic Audio to MIDI.md`

**Interfaces:**
- Consumes: passing static, preserved helper, admission suites, a source hash,
  independent review, and whitespace check.
- Produces: a committed, recoverable Task 0B4b-admission-pure checkpoint whose
  next task is B4b-evidence.

- [x] **Step 1: Run the required test suites and whitespace check**

Run: `python3 -B -m unittest tests.test_reaper_v4_task0b1_static_contract tests.test_reaper_v4_task0b4b_static_contract tests.test_reaper_v4_task0b4b_pure_helpers tests.test_reaper_v4_task0b4b_admission -v && git diff --check`

Expected: PASS; no filesystem/process/host action occurs.

- [x] **Step 2: Obtain independent review and address only confirmed blockers**

```text
Review the source, static contract, and TDD evidence for mutable-proxy,
cross-digest, closed-schema, and forbidden-capability regressions.
```

- [x] **Step 3: Record the source hash, results, non-authority, and next gate**

```text
Task 0B4b-admission-pure is sealed; Task 0B4b-evidence is next; no transport,
barrier, child, fixture, namespace, REAPER, or host behavior was exercised.
```

- [x] **Step 4: Commit the sealed checkpoint**

Run: `git add tools/reaper_v4_session.py tests docs RESUME.md && git commit -m "feat: admit bounded V4 session config"`

Expected: one recoverable checkpoint with the exact test evidence recorded.

## Self-review

- Every Task 0B3 Section 3 closed structure and cross-relation maps to Task 3.
- The plan contains no path, descriptor, barrier, frame, child, fixture, or
  host action.
- The source contract replaces the B4b-pure static test before production code.
- TDD RED precedes each production behavior.

## Execution record

- Phase-A pre-import surface RED was observed against the previous source;
  the exact inert helper stubs then made that surface GREEN without importing
  the target.
- The first admission behavior RED was observed through the inert
  `SessionError`; Phase-B source-shape RED was then observed before semantic
  implementation.
- The final 18-check command passed: immutable Task 0B1 static checks,
  admission static contract, preserved B4b-pure helper regressions, and five
  admission tests. The mutation suite includes named malformed-structure,
  digest, policy, map, certificate, X11, environment, scan/mount, child,
  limit, alias, and depth cases.
- Three independent reviews were CLEAN after test-first repairs for the X11
  environment/screen relations, scan-root mount closure, forged-object error
  normalization, lexical environment order, static module/call restrictions,
  and bounded walker checks.
- No path, descriptor, barrier, frame, child, fixture, namespace, REAPER, or
  host behavior was exercised. `Task 0B4b-evidence` is next.
