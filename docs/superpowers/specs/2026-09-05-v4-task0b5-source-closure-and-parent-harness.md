# V4 Task 0B5 — Session Source Closure and Parent Harness

**Status:** locally verified implementation checkpoint; not a complete
fixture-runtime manifest and not fixture execution.

## What this checkpoint adds

The historical Task 0B1 closure constructor remains untouched: it is correctly
sealed to its synthetic, always-blocked vector.  It cannot represent the later
session root.  This checkpoint instead adds three new, narrowly scoped files:

- `tools/reaper_v4_session_entry.py` is the sole executable session entrypoint.
  It loads only the two fixed configuration paths and calls the existing
  `run_session()` root once.
- `tools/reaper_v4_fixture_manifest.py` reads Python source as bytes and follows
  literal `tools.*` imports without importing target modules.  It emits a
  deterministic source graph and can combine it with explicitly supplied,
  individually hashed runtime and fixture-file entries.
- `tools/reaper_v4_fixture_harness.py` is the parent-side raw-pipe protocol
  harness.  It accepts exactly one valid PRE frame, writes `ACK_BYTE`, closes
  the ACK writer, accepts exactly one valid POST frame, validates the sealed
  exchange, and requires clean output EOF.  It launches only the command it is
  given; it contains no REAPER-specific behavior.

The current source root closure is exact and source-only:

```text
/app/tools/reaper_v4_session_entry.py
  -> reaper_v4_session.py
  -> reaper_v4_attester.py -> reaper_v4_protocol.py
  -> reaper_v4_child_runner.py
  -> reaper_v4_measurements.py
  -> reaper_v4_receipt_schema.py -> reaper_v4_protocol.py
```

It contains seven regular Python sources and eight typed import edges.  It does
not yet prove the interpreter, extension, ELF loader, or fixture-data closure.

## Manifest boundary and observed runtime catalog

`build_fixture_runtime_manifest()` deliberately treats the configuration JSON
and its SHA-256 sidecar as a fixed bootstrap pair outside the manifest.  The
SessionConfig carries the fixture-manifest digest, so including that pair would
be self-referential.  The builder rejects either bootstrap destination and
records each supplied source, runtime, or fixture regular file by destination,
host source identity, mode, byte size, and SHA-256.

An isolated `env -i` / `python3 -I -S -B` import observation is persisted in
`tests/fixtures/reaper_v4_closure/observed-runtime-catalog.json`.  It pins 77
regular interpreter/extension/ELF inputs (9,499,630 bytes), with canonical
catalog SHA-256
`fc2e615cdcfc57468d8227074ba260f6c35dc56e9d2f722a53986270d00e90a0`.
The public serialization replaces the seven contributor-local workspace
prefixes with `/REDACTED`; relative tool paths, byte sizes, modes, and hashes
remain unchanged.
`build_fixture_runtime_manifest_from_catalog()` rehashes every cataloged source
before it will assemble a manifest; the current catalog plus the seven source
files produces an 84-entry, 9,647,488-byte declared manifest in memory.

The catalog is explicitly marked `OBSERVED_RUNTIME_CATALOG` / `UNRESOLVED`.
It retains the unresolved builtin/frozen-module registry, conditional-import,
interpreter-startup, native-effect, and virtual-resource closure gaps. It is a
reviewable input—not a complete interpreter closure, fixture-runtime manifest,
or fixture-execution authorization.

## Parent-harness evidence

The new harness test suite uses only an isolated Python sentinel started with
`-I -S -B -c`.  It has four green cases:

1. a valid PRE -> ACK+EOF -> POST exchange;
2. a terminal frame before PRE is refused; and
3. a child exit before PRE is refused; and
4. a POST supplied before the ACK is refused.

Together with the existing V4 suites, discovery runs 113 tests green.
The sentinel is not REAPER, does not access audio, X11, network, or a plug-in,
and supplies no compatibility claim.

## Current execution limit

The reviewed Bubblewrap binary is installed, but a harmless namespace probe is
currently refused by this Codex execution environment before its child starts,
even though the host user-namespace sysctls report enabled:

```text
bwrap: No permissions to create a new namespace
```

`strace` is also denied `PTRACE_TRACEME` in this Codex sandbox. Therefore no
actual Bubblewrap fixture, mount namespace, session invocation, or REAPER host
action occurred here. The code and manifest/harness inputs are ready for an
execution environment that permits the reviewed scope; there is no unsandboxed
fallback.

## Next work

1. Turn the controlled import/ELF inventory into a reviewable, individually
   pinned runtime catalog and complete the fixture-runtime manifest.
2. Run the parent harness around the real session root only on a host that
   permits the reviewed Bubblewrap user namespace.
3. Only after that controlled non-REAPER fixture is clean, construct the
   separate REAPER host-runtime manifest and calibrate the actual live MIDI
   path.
