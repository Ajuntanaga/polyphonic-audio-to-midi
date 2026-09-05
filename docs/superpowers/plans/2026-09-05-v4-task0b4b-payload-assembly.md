# V4 Payload Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an owned, verified V4 evidence baseline into exact PRE and POST receipt values without adding a fixture, path, process, or host operation.

**Architecture:** Keep the existing session root and evidence collector intact. A new private common-attestation helper cross-checks the retained immutable baseline against a fresh admitted configuration, then PRE/POST builders create fresh ordinary Python values for the sealed receipt validator and encoder. The existing state finalizer keeps POST exchange validation before encoding.

**Tech Stack:** Python 3 standard library, existing Task 0A protocol, Task 0B1 receipt schema, controlled descriptor fixture, unittest.

**Spec:** `docs/superpowers/specs/2026-09-05-v4-task0b4b-payload-assembly-source-contract.md`

## Global Constraints

- Preserve Task 0A and Task 0B1 source APIs and all existing V4 pure/admission/evidence/bootstrap/state tests.
- Do not add a public API, direct child launch, raw stream operation, filesystem opening, descriptor enumeration, barrier call, namespace, Bubblewrap/systemd command, REAPER, audio, X11 client traffic, network, fixture, or host action.
- The payload helpers consume only an already-owned `_EvidenceBaseline`; `run_session()` remains responsible for barrier and baseline-recheck ordering.
- Build payloads as fresh exact built-in `dict`/`list`/scalar values. Never serialize a frozen mapping or reuse a validator-created snapshot.

---

### Task 1: Establish real receipt-builder REDs

**Files:**

- Create: `tests/test_reaper_v4_task0b4b_payloads.py`
- Modify: `tests/test_reaper_v4_task0b4b_static_contract.py`

**Interfaces:**

- Consumes: `_EvidenceFixture`, `_forged_config`, and the sealed `validate_pre_payload`, `validate_post_payload`, and `validate_exchange` APIs.
- Produces: a behavior test demonstrating the missing payload assembly and a static source contract that can later replace the two stub assertions.

- [x] **Step 1: Write a PRE builder test**

```python
with _EvidenceFixture(session) as fixture:
    baseline = fixture.capture()
    payload = session._assemble_pre_payload(fixture.config, baseline)
    receipt_schema.validate_pre_payload(payload, 0)
    self.assertEqual(payload["phase"], "pre")
    self.assertTrue(payload["no_child_started"])
    self.assertNotIn("scan_root_unchanged", payload["attestation"])
```

- [x] **Step 2: Run the PRE test to verify the stub fails**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest \
  tests.test_reaper_v4_task0b4b_payloads.Task0B4bPayloadTests.test_builds_a_valid_pre_from_an_owned_baseline -v
```

Expected: `SessionError: runtime evidence is not admitted` from the existing stub.

- [x] **Step 3: Write a POST/exchange and refusal test**

```python
outcome = session.child_runner.ChildOutcome(123, 0, False, 4)
post = session._assemble_post_payload(fixture.config, baseline, outcome, 10, 11)
receipt_schema.validate_exchange(pre, b"\x06", post)
self.assertTrue(post["attestation"]["scan_root_unchanged"])
with self.assertRaises(session.SessionError):
    session._assemble_post_payload(fixture.config, baseline,
        session.child_runner.ChildOutcome(123, -9, False, 4), 10, 11)
```

- [x] **Step 4: Run the new behavior module to verify the POST path fails for the missing implementation**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest tests.test_reaper_v4_task0b4b_payloads -v
```

Expected: PRE/POST assembly tests fail only at the two fail-closed stubs; refusal vectors remain meaningful once implementation exists.

### Task 2: Build and validate the shared attestation

**Files:**

- Modify: `tools/reaper_v4_session.py`
- Modify: `tests/test_reaper_v4_task0b4b_payloads.py`

**Interfaces:**

- Consumes: `SessionConfig`, `_EvidenceBaseline`, `_admit_session_config`, `_require_owned_evidence_baseline`, `_materialize_exact_builtins`, and `_certificate_applicability_projection`.
- Produces: `_shared_receipt_attestation(config: SessionConfig, baseline: _EvidenceBaseline) -> dict[str, object]`.

- [x] **Step 1: Implement one retained-baseline cross-check helper**

```python
def _shared_receipt_attestation(
    config: SessionConfig, baseline: _EvidenceBaseline
) -> dict[str, object]:
    admitted = _admit_session_config(config)
    _require_owned_evidence_baseline(baseline)
    if baseline.config.data != admitted.data:
        raise SessionError("evidence baseline configuration is invalid")
    # Materialize and compare environment, measurement, scan, private tree,
    # X11, FD census, mounts, and certificate projection before returning the
    # exact shared receipt fields required by the source contract.
```

The implementation must use the full six-key environment list and the full
finite forbidden-name list in the source contract. It must derive every Boolean
only after checking the retained record which owns that fact.

- [x] **Step 2: Run the behavior module to verify the PRE test passes**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest \
  tests.test_reaper_v4_task0b4b_payloads.Task0B4bPayloadTests.test_builds_a_valid_pre_from_an_owned_baseline -v
```

Expected: PASS and the sealed PRE validator accepts the returned ordinary
payload.

- [x] **Step 3: Add baseline mismatch and mutation refusals**

```python
other = _forged_config(session, _valid_config())
with self.assertRaises(session.SessionError):
    session._assemble_pre_payload(other, baseline)
object.__setattr__(baseline, "environment", session._freeze_session_data({}))
with self.assertRaises(session.SessionError):
    session._assemble_pre_payload(fixture.config, baseline)
```

- [x] **Step 4: Run the payload module**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest tests.test_reaper_v4_task0b4b_payloads -v
```

Expected: valid PRE path passes and malformed/changed baseline vectors refuse.

### Task 3: Build exact PRE and POST values

**Files:**

- Modify: `tools/reaper_v4_session.py`
- Modify: `tests/test_reaper_v4_task0b4b_payloads.py`

**Interfaces:**

- Consumes: `_shared_receipt_attestation` and `_validate_child_outcome`.
- Produces: exact-built-in PRE and POST dictionaries accepted by the sealed receipt validators.

- [x] **Step 1: Replace the PRE stub**

```python
return {
    "schema": base["schema"], "namespace": base["namespace"],
    "nonce": base["nonce"], "config_sha256": base["config_sha256"],
    "inputs": dict(base["inputs"]), "row": dict(admitted.data["row"]),
    "phase": "pre", "no_child_started": True,
    "attestation": _shared_receipt_attestation(admitted, baseline),
}
```

- [x] **Step 2: Replace the POST stub**

```python
validated = _validate_child_outcome(outcome)
shared = _shared_receipt_attestation(admitted, baseline)
shared["scan_root_unchanged"] = True
return {**identity, "phase": "post", "terminal": True,
        "child_pid": validated.child_pid,
        "child_returncode": validated.returncode,
        "pre_monotonic_ns": pre_monotonic_ns,
        "post_monotonic_ns": post_monotonic_ns,
        "attestation": shared}
```

The actual implementation must reject non-exact/nonpositive/regressing clocks
before it returns a payload.

- [x] **Step 3: Run the POST/exchange behavior test**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest \
  tests.test_reaper_v4_task0b4b_payloads.Task0B4bPayloadTests.test_builds_a_valid_post_and_exchange -v
```

Expected: PASS with a sealed receipt exchange; timeout, negative return code,
and invalid clocks refuse.

### Task 4: Seal the source shape and checkpoint

**Files:**

- Modify: `tests/test_reaper_v4_task0b4b_static_contract.py`
- Modify: `RESUME.md`
- Modify: `docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md`
- Modify: `docs/superpowers/specs/2026-09-05-v4-task0b4b-payload-assembly-source-contract.md`

**Interfaces:**

- Consumes: the completed helper/test implementation.
- Produces: an updated pre-import static contract, source SHA-256, recovery record, and commit.

- [x] **Step 1: Replace the two static stub assertions**

Require the shared helper and the two assembly helpers, exact signatures,
owned-baseline/admission edges, no added `os`/transport/child/barrier edges,
and `scan_root_unchanged` only in the POST helper.

- [x] **Step 2: Run the complete focused suite**

Run:

```bash
ionice -c 3 nice -n 10 python3 -B -m unittest \
  tests.test_reaper_v4_task0b1_static_contract \
  tests.test_reaper_v4_task0b4b_static_contract \
  tests.test_reaper_v4_task0b4b_pure_helpers \
  tests.test_reaper_v4_task0b4b_admission \
  tests.test_reaper_v4_task0b4b_evidence \
  tests.test_reaper_v4_task0b4b_bootstrap_transport \
  tests.test_reaper_v4_task0b4b_state \
  tests.test_reaper_v4_task0b4b_payloads -v
git diff --check
```

Expected: all source-only and controlled-descriptor checks pass; no fixture,
namespace, process, or host operation is invoked.

- [x] **Step 3: Record the exact source SHA-256 and locally verified scope**

Update recovery records to name the payload stage, test count, source hash,
and the explicit remaining gap: runtime observation acquisition and an outer
fixture still require later reviewed work.

- [x] **Step 4: Commit the checkpoint**

```bash
git add tools/reaper_v4_session.py \
  tests/test_reaper_v4_task0b4b_static_contract.py \
  tests/test_reaper_v4_task0b4b_payloads.py \
  docs/superpowers/specs/2026-09-05-v4-task0b4b-payload-assembly-source-contract.md \
  docs/superpowers/plans/2026-09-05-v4-task0b4b-payload-assembly.md \
  RESUME.md docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md
git commit -m "feat: assemble V4 receipt payloads"
```

## Self-Review

1. **Spec coverage:** Task 1 records the missing behavior; Task 2 validates
   each retained evidence family before a Boolean appears; Task 3 produces only
   Task 0B1 closed payload shapes; Task 4 seals static shape and recovery
   evidence.
2. **Placeholder scan:** This plan names every helper, test module, command,
   payload field class, and later blocking condition used by its steps.
3. **Type consistency:** The plan uses the existing `SessionConfig`,
   `_EvidenceBaseline`, `ChildOutcome`, and `dict[str, object]` signatures;
   POST still delegates exchange/encoding to `_finalize_post_payload`.

## Execution Handoff

Plan implemented with a test-first PRE-stub refusal followed by a 51-check
focused V4 pass. The checkpoint records payload assembly only; independent
review and runtime-observation acquisition still precede any fixture or host
action.
