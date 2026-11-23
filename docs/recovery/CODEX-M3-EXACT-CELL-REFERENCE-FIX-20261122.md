# Exact-cell report reference repair

Codex owns this small harness repair: `tools/portable_exact_cell_sharing.py`,
`tests/test_portable_exact_cell_sharing.py`, a dedicated block-512 reference
manifest in `docs/recovery`, and the existing worker workflow
`.github/workflows/exact-cell-sharing.yml`. Claude keeps its independent
carry-over-credit analysis. No native code, corpus replay or dispatch is part
of this repair.

The completed screen 45094249566 remains scientifically rejected because the
physical-long pair costs 5.46% more CPU. Separately, the runner compared its
first block-512 snapshot to a block-32 byte hash. The mock fixture reused one
snapshot at both block sizes and hid this error.

The repair gives untimed companions their own block-512 reference input,
validates both inputs before execution, and exercises distinct block-size
snapshots in the mocked runner. References come from the already-collected
completion corpus run 43756240245, whose report SHA-256 is
`78c405a8e8845171b49b8240ff6ec91efbc0e62ef18005ad4d920b12d6bea45d`.
Timing, paired MIDI, allocation and usefulness checks stay unchanged.

Validation: all 16 focused mocked runner tests pass. The worker YAML and its
6 shell sections parse, and the scoped diff check passes. No native replay,
audio, model or corpus execution ran locally. Published source `f9e9063385561e1b0b4b4a161aa13ba790e17c6b` and worker
`db8b34cbd1213735d00710345d5e682e57d7c32b`; no workflow was dispatched. The old run is not rerun or rejudged;
its missing paired-MIDI result remains unmeasured.

Routine portable source check `45096861342` completed successfully at 2026-11-23 01:52:39 UTC.
Its completion does not reopen the rejected CPU screen. Publication and exact
source-run observations are recorded under
`build/recovery/exact-cell-reference-fix-20261122/`.
