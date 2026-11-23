# Batched cell calculation in the VST3 component

Recorded 2026-11-23 UTC, before this component replay is run.

Codex temporarily owns `native/vst3/vst3_component.hpp`,
`native/offline/vst3_corpus_replay_main.cpp`,
`tools/portable_vst3_stable_note_corpus.py`, its Python contract tests,
the new compact component reference below, and the `batch-cell-corpus` scenario
in worker `.github/workflows/m3-vst3-replay.yml`. This extends the existing
component harness; Claude's acoustic re-pluck lane remains independent.

## Question and trigger

The bounded core screen 45109184192 saved 16.6–18.4% thread CPU with identical
saved output. The full core corpus job 45112657375 is running. Prepare this
component check while it runs; dispatch once only if its complete identity,
allocation and deadline gates pass. This check measures the actual VST3
`process()` path, including its accepting test sink, which the core replay
cannot establish.

## Frozen execution

Reuse the 44245557161 component protocol: fourteen datasets, per-voice and
stable-note modes, sample formats 32 and 64, blocks 512, 32 and 1024, with an
additional timed block-32 companion for each mode and format: 224 runs,
56 timed. Settings, recordings, calibration, routing and accepting sink are
unchanged. Enable only the already implemented batched cell calculation,
through a test-only switch after activation and before the first process call.
No installed parameter, state or default changes.

Pin every callback byte and normalized native outcome to the already collected
report `build/github-results/vst3-stable-note-corpus-44245557161/vst3-stable-note-corpus/report.json`
(SHA-256 `a4bf4ff24e2b927524624c53276e73916adb93325dee9a561f6d90ae24e129a7`,
source `3837130f692871808b17b73a8fb25d279905ce50`). Store its compact per-mode
references in `docs/recovery/batch-cell-vst3-corpus-references-20261122.json`.
Only sample-format/block identifiers, block count and timing values are
normalized away; the existing harness checks those identifiers and block
accounting directly. The new batch flag must be true. No reference audio or
bulk artifact is downloaded locally.

## Acceptance and reporting

All 224 callback hashes and normalized native states must match; all existing
buffer/format, dry-audio, label, note ownership and pairing checks must pass.
All 56 timing companions require p99 <= 166666 ns, max <= 333333 ns,
zero overruns and zero C/C++ processing allocations or frees. Cold and final
partial blocks stay included. Fail closed on input/output identity or execution
errors; continue the fixed remaining matrix after a timing failure, without
retries or tuning. Report the previous component's two deadline failures
separately from this result; timings from different runners are not a paired
speed comparison.

Local checks are mocked Python contracts and workflow syntax only. Native
builds, tests and recorded audio stay on GitHub Actions. Record source and
worker SHAs, one run id, and collect the small report once with its digest;
keep bulk evidence remote. Passing this screen establishes this offline
component gate, not external DAW/device readiness or acoustic re-pluck
preservation, which remains open.

Preparation checks: 27 mocked Python contracts pass, including changed callback,
state, disabled-switch and wrong-bundle rejection. The worker YAML and all 17
shell sections parse; its new command selects the full matrix and nested corpus
directory. Local receipt: `build/recovery/batch-cell-vst3-20261122/local-checks.json`.
No native build or audio execution was performed locally.
