# Task 0B4b-bootstrap-transport implementation plan

**Goal:** add only private fixed-literal config bootstrap and fd-0/fd-1/fd-2
raw-helper behavior before the mock-only session state machine exists.

**Boundary:** no public session execution, REAPER, child, barrier, namespace,
launcher, fixed `/run` execution, or host scan. Tests use syscall/poll doubles
or temporary controlled pipes only.

## Task 1: Replace the evidence source contract

- [x] Write a pre-import AST contract for exactly seven bootstrap/transport
  helpers and the new `fcntl`/`select`/`time` import surface.
- [x] Record its expected RED against the sealed evidence source.

## Task 2: Write behavior REDs

- [x] Add controlled sidecar/config doubles for sidecar-first order, regular
  descriptor/flag/mount/EOF bounds, parse/admit, and all refusal paths.
- [x] Add controlled fd-0/fd-1/fd-2 tests for one diagnostic attempt, one
  frame write, timeout/error/short-write refusal, and ACK+EOF distinction.

## Task 3: Implement minimal private helpers

- [x] Implement diagnostic setup/emission, fixed regular reads, and private
  parsed/admitted bootstrap construction.
- [x] Implement fixed pipe poll, one-write frame, and one-byte ACK+EOF read.
- [x] Leave both public functions as immediate `SessionError` stubs.

## Task 4: Seal

- [x] Run all immutable/static/pure/admission/evidence/bootstrap suites plus
  whitespace check (37 checks after the `POLLHUP`-to-EOF regression).
- [ ] Independently review the no-host/no-child boundary, record the source
  SHA/result, update recovery records/canonical note, and commit.
