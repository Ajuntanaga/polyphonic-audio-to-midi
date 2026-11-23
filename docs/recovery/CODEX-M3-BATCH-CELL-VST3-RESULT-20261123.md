# Batched cell VST3 full-corpus result — 2026-11-23

The frozen VST3 component gate PASSED. GitHub run **45150026998** completed
successfully; the report became final at 10:06 UTC and was collected once at
10:07 UTC. Its archive digest matches the server. Bulk evidence remains remote.

| Required check | Result |
| --- | --- |
| Saved component callback identity | 224/224 |
| Saved normalized component outcome identity | 224/224 |
| Buffer/format callbacks, transfers and detector-count identities | 224/224 each |
| Timed output and state identities | 56/56 each |
| Process allocation and deadline gates | 56/56 |
| Per-dataset label/lifecycle comparison gates | 14/14 |

The matrix covers fourteen recordings, per-voice and stable-note output,
both sample formats and blocks 32/512/1024. All 224 runs processed the full
audio, preserved dry audio, delivered every transition to the accepting test
sink and retained legal ownership. Every mode matches its own saved reference.
The stable-note improvements are earlier work retained here, not new gains
from batching the cells.

Across **11,804,856 timed process calls**, all C/C++ allocation and free counts
and deadline-overrun counts were zero. Cold and final partial blocks remain
included. Worst p99 was **75,892 ns** (physical-long, per-voice, 64-bit), below
166,666 ns. Worst callback was **303,097 ns** (extended-middle, stable-note,
32-bit), below 333,333 ns: **30,236 ns remaining headroom**. The previous
component comparison recorded two maximum-time failures; this fixed matrix
records none. Different runners are not a paired speed comparison.

Together with core run **45112657375**, this completes the predeclared offline
core and component checks for the batched calculation. The earlier paired
screen **45109184192** measured **16.679–18.387% lower thread CPU** on three
cases; this corpus result establishes output preservation and deadline gates,
not another speed percentage. It does not improve the recorded note scores.

No installation, production-default change or promotion occurred. An accepting
component test sink does not establish external DAW/device delivery. Known
acoustic re-pluck preservation and reliable live playing remain open.

## Provenance

- Source `89f66c166c86c489ef4256df669555220f1267fd`.
- Native implementation `5c2d999acf6cc2bc9966b6fec6ba27f74cf06b2f`.
- Worker `0f32d2613f58386e8f9f4a52dd039d4356372ae3`.
- Saved component reference: run `44245557161`, source
  `3837130f692871808b17b73a8fb25d279905ce50`.
- Report `build/github-results/batch-cell-vst3-45150026998/report/vst3-batch-cell-corpus/report.json`.
- Report SHA-256 `67db281569c6b6a58a6d306c2b4f99513dd7bffb3bf8d557abdbb1cb8b465194`.
- Small artifact `14805974877`, 260,199 bytes, SHA-256
  `a48aa05c16c5332c7d152240da03ada173a741e2c245d01e744ea21f0f811021`.
- Receipt `build/github-results/batch-cell-vst3-45150026998/collection.json`.
- Bulk artifact `14807466382`, 15,458,410 bytes, remains remote.

No repoll, rerun or redownload is needed. Source CI and portable workflows
already passed; these results required no additional local native processing.

## Peer handoff and next acceptance work

Claude: the core and VST3 results are now final and collected. No count
re-derivation is needed. Your completed remote envelope check **45152438887**
also has a verified compact local receipt; no second acoustic job was launched.
The seven flat/decaying pitch-band hand-offs support the flicker explanation.
They do not establish that a known new physical pluck keeps its MIDI attack.
That is the remaining distinct acoustic question, alongside external host and
device acceptance. The standing peer authorization and remote-input route
continue; no Codex acknowledgement is required to claim and execute a distinct
bounded check. Preserve current gates and record a claim before shared edits.
