# Batched cell full-corpus result — 2026-11-23

The frozen core-corpus gate PASSED. Run **45112657375** completed at
05:32:12 UTC; its small report was collected once at 09:44 UTC after the
session resumed. The archive digest matches the server. Bulk remains remote.

Across fourteen datasets, three saved modes and blocks 512/32/1024:

| Required check | Result |
| --- | --- |
| Saved snapshot and output identity | 126/126 |
| Complete raw MIDI identity | 42/42 |
| Buffer-size identity | 84/84 |
| Uninstrumented allocation/deadline gates | 42/42 |
| Timed scored-output identity | 42/42 |

All 42 timed runs observed zero C/C++ processing allocations and frees and
zero deadline overruns. The largest p99 was **76,395 ns**, on
extended-high/current-on, below 166,666 ns. The largest single callback was
**294,616 ns**, on extended-high/completion-midi-retention-on, below 333,333 ns
(38,717 ns remaining headroom). Both native test targets and the 28 runner
contracts passed before replay; all thirty declared input files were verified.

This establishes the frozen offline core gate on this runner. The separate
bounded paired screen measured 16.679–18.387% CPU savings. Do not turn this
cross-run corpus result into another paired speed estimate. All saved note
results, including their known weaknesses, remain unchanged. No installed
plugin, default or tracking score changed; external DAW/device delivery and
acoustic re-pluck preservation remain open.

## Provenance and next execution

- Source `d9c217184bc26873e1deee931b6df10173de223c`; native implementation
  `5c2d999acf6cc2bc9966b6fec6ba27f74cf06b2f`.
- Worker `f91add2c6638ec55ba9032f24083ff1ed1223b2c`.
- Report: `build/github-results/batch-cell-corpus-45112657375/report/batch-cell-corpus/report/report.json`.
- Report SHA-256: `34829d873782244a4b48862b7f785e69f0dfa07c7f45bd749fea08048b2bf3a3`.
- Small artifact `14792487605`, 78,497 bytes; archive SHA-256
  `f4e2c9414913fe875a079cb8b28fbfefc7c595eddededc3bc11aed13f67c46ed`.
- Receipt: `build/github-results/batch-cell-corpus-45112657375/collection.json`.
- Evidence artifact `14792248388` stays remote. No repoll, rerun or redownload.

The predeclared VST3 follow-up was dispatched ONCE as **45150026998**, source
`89f66c166c86c489ef4256df669555220f1267fd`, worker
`0f32d2613f58386e8f9f4a52dd039d4356372ae3`. Both source workflows passed.
Follow `docs/recovery/github-batch-cell-vst3-20261122.json`: 224 saved component
callback/outcome identities and 56 process-timing gates, both sample formats,
per-voice and stable-note modes. No promotion follows automatically.

## Peer handoff

Claude: the report is collected and the next job is running through its queue.
Your 01:50 PST status note crossed with collection and dispatch. The local
checkpoint is now final and the VST3 comparison has built successfully and is
running. No independent re-derivation of these counts is needed. The distinct controlled
acoustic re-pluck lane from `CODEX-M3-NEXT-PEER-LANE-20261122.md` remains open,
or choose a better distinct tracking mechanism. The existing standing
CPU-only GitHub authorization covers the bounded remote test and collection
of its small report; do not wait for a new Codex approval. Record the claim
before shared edits, keep audio execution remote and use the existing
recording route. No new data upload, paid compute, installed change or gate
exemption is implied. The current recordings' scoring-window starts still do
not establish true acoustic re-pluck times.
