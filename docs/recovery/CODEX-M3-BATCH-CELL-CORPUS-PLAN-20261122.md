# Batched resonator arithmetic: full corpus validation

Codex owns this bounded CPU validation, its runner, tests, worker workflow and
collection. Claude's independent acoustic re-pluck work is separate. The
default-off native implementation is frozen at source `5c2d999`; no native
policy or implementation change is part of this follow-up.

The single screen `45109184192` passed its predeclared usefulness rule: CPU
total fell 16.679%, 16.601% and 18.387% in its three fixed cases, CPU p99 fell
in each, all twelve snapshots retained saved identity and all three paired
raw MIDI captures were identical. Those instrumented results justify this
uninstrumented corpus check; they do not establish production readiness.

## Frozen execution and reading rule

One GitHub CPU workflow, `batch-cell-corpus.yml`, using the existing
`corpus-20261108` input bundle. No new upload, fit, sweep, policy or settings.
Run all fourteen recorded datasets, three saved modes (`reference-off`,
`current-on`, `completion-midi-retention-on`) and blocks 512, 32 and 1024:
126 replays, each with `--diagnostic-batch-cell-update` enabled.

Compare every snapshot SHA-256, output counters and exact-match counters
against full-corpus run `43756240245`, source
`83c51e3b257f57e9af75293d3a765c6bae677e5b`, report SHA-256
`78c405a8e8845171b49b8240ff6ec91efbc0e62ef18005ad4d920b12d6bea45d`.
The compact reference manifest copies all 126 rows from that report. For each
of the 42 untimed block-512 replays, require complete raw MIDI SHA-256 and row
count identity against the full-recording saved capture. Its existing MIDI
quality limitations remain limitations; identity is not an improvement claim.

The 42 block-32 replays use the scored core-timing path with optional offline
frequency reporting excluded, without thread/stage/allocation trace probes or
MIDI capture. Require p99 <= 166666 ns, maximum <= 333333 ns, zero deadline
overruns, and zero C/C++ processing allocations and frees on every replay.
The allocation guard remains enabled. Compare blocks 32 and 1024 with 512
for 84 buffer-identity checks. Do not average away a failed dataset or mode.

Pass requires 126 snapshot identities, 42 complete MIDI identities, 84 buffer
checks and all 42 allocation/deadline gates. Timing failures are recorded while
the remaining fixed cases finish. A corrupted input, incomplete capture,
reference mismatch, process failure or timeout fails closed; no replay retry.
One runner budget of 9000 seconds, 900 seconds per replay, workflow 180 minutes.

Keep snapshot/MIDI bulk remote; collect only the small report/log artifact
once and verify its server digest. No installation or promotion is authorized
by this validation result. Live-host deadlines and acoustic re-pluck
preservation remain separate requirements.

## Files in this lane

- `tools/portable_batch_cell_corpus.py`
- `tests/test_portable_batch_cell_corpus.py`
- `docs/recovery/batch-cell-corpus-references-20261122.json`
- `docs/recovery/github-batch-cell-corpus-20261122.json`
- Worker `.github/workflows/batch-cell-corpus.yml`
- Task checkpoint and compact result records
