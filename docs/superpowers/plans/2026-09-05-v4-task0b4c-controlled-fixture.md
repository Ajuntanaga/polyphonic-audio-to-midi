# V4 Task 0B4c Controlled Fixture Definition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seal a source-free definition of the one bounded non-REAPER fixture without creating, launching, or mounting it.

**Architecture:** The outer harness is the sole owner of fixture data, ACK, output drains, teardown, and the child census. The session keeps the fixed three-standard-stream protocol and one direct child; the current fail-closed evidence/payload stubs remain an execution prerequisite.

**Tech Stack:** Markdown specifications; Task 0A/0B1 Python contracts; the existing Bubblewrap fixture design as a non-executed reference.

**Spec:** `docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md`

## Global Constraints

- This plan creates and reviews documentation only; it does not modify Python source or tests.
- Do not form or execute a Bubblewrap, systemd, REAPER, X11, audio, network, namespace, mount, process, or fixture command.
- Preserve the pending-review status of Task 0B4b-bootstrap-transport and Task 0B4b-state.
- A reviewed source gate must replace the fail-closed evidence/payload stubs before a fixture-runtime manifest or fixture execution is considered.

---

### Task 1: Define the bounded fixture topology

**Files:**

- Create: `docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md`
- Modify: `docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md`
- Modify: `RESUME.md`

**Interfaces:**

- Consumes: Task 0B3 stream rules, `run_session(config: SessionConfig) -> SessionResult`, and the sealed child-adapter boundary.
- Produces: one parent/session/child topology, exact fixture-data table, fixed data-plane budget, failure cases, and execution entry conditions.

- [x] **Step 1: Write the fixture definition**

Document the fixed fd 0 ACK, fd 1 PRE/POST, fd 2 diagnostic topology; exact synthetic data files; `/usr/bin/true` direct child; and the no-REAPER scope.

- [x] **Step 2: Check the design against the state contract**

Run:

```bash
rg -n "ACK|POST|direct child|fixture-runtime-manifest|fail-closed" \
  docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md \
  docs/superpowers/specs/2026-09-04-v4-task0b4b-state-source-contract.md
```

Expected: ACK EOF dominates the child, uncertainty suppresses terminal POST, and fail-closed stubs are a pre-execution condition.

- [x] **Step 3: Record the draft without advancing a gate**

Add a recovery/plan pointer stating that this draft does not seal B4c-design; bootstrap/state review, runtime evidence implementation, closure, and manifest review still precede execution.

- [x] **Step 4: Validate documentation and commit**

Run:

```bash
git diff --check
git status --short
```

Expected: only the three documentation files are modified; no source or test file changes exist.

- [x] **Step 5: Commit the documentation checkpoint**

```bash
git add RESUME.md docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md docs/superpowers/plans/2026-09-05-v4-task0b4c-controlled-fixture.md docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md
git commit -m "docs: define bounded V4 fixture"
```

### Task 2: Preserve the execution stop line

**Files:**

- Modify: `docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md`
- Modify: `RESUME.md`

**Interfaces:**

- Consumes: the draft fixture definition from Task 1.
- Produces: a consistent statement that no manifest or execution follows from a documentation draft.

- [x] **Step 1: Add the draft-only cross-reference**

State that the B4c document defines topology and budgets but cannot seal B4c-design while bootstrap/state independent review or runtime stub replacement is incomplete.

- [x] **Step 2: Validate no execution authorization appears**

Run:

```bash
rg -n "authorize.*(Bubblewrap|systemd|REAPER|fixture)|execute.*fixture" \
  docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md \
  docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md \
  RESUME.md
```

Expected: every match is a prohibition or future condition, never a current command authority.

- [x] **Step 3: Commit the cross-reference correction**

```bash
git add RESUME.md docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md
git commit -m "docs: retain V4 fixture execution gate"
```

## Self-Review

1. **Spec coverage:** Task 1 covers topology, data, budgets, failure cases, and entry conditions; Task 2 preserves the non-execution boundary in recovery records.
2. **Placeholder scan:** This plan names every data item, stream, limit, and document path used by its two documentation tasks.
3. **Type consistency:** The plan preserves `run_session(config: SessionConfig) -> SessionResult` and the sealed `child_runner.ChildSpec` boundary; it introduces no new code interface.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-05-v4-task0b4c-controlled-fixture.md`. This session uses inline execution and keeps the fixture definition source-free until its explicit entry conditions are satisfied.
