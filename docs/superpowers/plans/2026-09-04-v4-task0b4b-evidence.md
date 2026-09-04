# Task 0B4b-evidence implementation plan

**Goal:** add bounded, descriptor-rooted private evidence comparison and
retained-baseline helpers before any bootstrap transport or session state
machine exists.

**Scope:** only the session module, its replacement static contract, a new
temporary-resource evidence suite, and recovery records. No REAPER, launcher,
namespace, fixed configuration path, `/proc`, raw stream, barrier, or child.

## Task 1: Replace the admission static contract

- [x] Write an intentionally RED pre-import AST contract for the exact evidence
  helper surface and descriptor restrictions.
- [x] Add inert private interface stubs until the source-shape contract passes.

## Task 2: Write temporary-resource evidence REDs

- [x] Build a valid admitted SessionConfig with identities derived from only
  temporary directories/files/socket descriptors.
- [x] Add supplied cwd/environment, capture/recheck/release, malformed tree,
  changed resource, forged-baseline, malformed observation, and cleanup-failure
  tests. Keep every descriptor explicitly owned and closed.

## Task 3: Implement bounded evidence helpers

- [x] Implement supplied cwd/environment plus descriptor-relative
  measurement/scan/private-tree/X11 capture.
- [x] Implement immutable FD/mount comparison, certificate projection, and
  private baseline ownership registration.
- [x] Implement retained post recheck and one-shot release with cleanup
  uncertainty reporting.

## Task 4: Seal

- [x] Run immutable/static/pure/admission/evidence suites plus whitespace check.
- [x] Independently review source and test boundaries, record the SHA/result in
  `RESUME.md`, the V4 plan, this contract, and the canonical operations note.
- [x] Commit the evidence checkpoint, then make bootstrap transport the next
  implementation gate.

## Execution record

- The pre-import evidence contract first failed before the new descriptor
  interfaces existed; the temporary-resource suite then failed against inert
  helpers before implementation.
- Focused source repairs added descriptor-relative scan/private-tree traversal,
  bounded regular-file hashing, supplied cwd/environment comparison, retained
  rechecks, cleanup uncertainty reporting, and registry-bound descriptor
  ownership. The latest session source SHA-256 is
  `6049ec3096cf9a2fc50678884180fe4e0ef6072032418931f0d48afa14f83a1f`.
- `python3 -B -m unittest` over the Task 0B1 static, evidence static,
  B4b-pure, admission, and evidence suites passed 30 checks; `git diff --check`
  was clean. Three independent reviews are CLEAN.
- Only temporary files/directories, a temporary Unix socket, and supplied
  descriptors were exercised. No REAPER, audio capture, fixed `/run` config,
  namespace, launcher, barrier, child, raw stream, or host scan ran.
