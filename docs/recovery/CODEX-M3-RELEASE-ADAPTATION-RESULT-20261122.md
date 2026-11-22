# Release-context fit completed; window screen rejected

Run45037966575 is final/failure. Source`fc3ad86d5af286d1cfbf4aba5041d0fdc460d316`, worker`5eadbb3b0ee23b1e8c2255f7f275042bcaec7ad2`. The53,034-byte report was collected once with its server SHA256 verified. The929,456,809-byte evidence archive remains remote, artifact14763113098, expiry2026-12-06. No repoll, redownload or unchanged rerun.

Both fixed epochs completed (3,072 batches), all555 takes were retained, and all22 remote tests passed. The original model outputs were restored bit-identically. Epoch2 is saved as`epoch-2.npz` (142,881 bytes, SHA256`e64ce16066e746bb386cadbef8d9efcce6430812a4907586c5647d63b7ef02b0`).

The following are nominal model-frame distinct-pitch measurements on the unchanged constructed-window evaluation plans. They are not tuner/string matches, delivered MIDI, live accuracy or unison multiplicity. BASELINE is the prior adapted model; CURRENT TRIAL is the fresh release-context model.

| Split | Expected note-frames | Found BASELINE → TRIAL | Found percent | Extra note-frames | Exact pitch-set frames | Occurrences losing presence / longest |
|---|---:|---:|---:|---:|---:|---:|
| train | 1,742,377 | 1,500,247 → 1,560,054 | 86.10% → 89.54% | 154,829 → 234,932 | 434,254 → 426,090 / 704,512 | 177 / 179 of 11358 |
| calibration | 375,035 | 327,835 → 338,577 | 87.41% → 90.28% | 32,016 → 48,524 | 120,046 → 116,988 / 176,128 | 33 / 34 of 2455 |
| test | 359,633 | 247,210 → 263,782 | 68.74% → 73.35% | 73,075 → 100,436 | 82,643 → 79,995 / 176,128 | 35 / 36 of 2638 |

On test, found note-frames increase16,572 (+4.608 percentage points), but extras increase27,361; exact sets fall82,643→79,995/176,128 (46.922→45.419%). Silence extras grow527→1,163. Every split fails the representation and occurrence-preservation gates. More detected content has not produced a safe replacement. Extra training windows also mean more optimizer steps, so the change cannot be attributed solely to release examples.

The later stage`prior corrected export and readout crop` stops with`ValueError: Pinned graph/interface differs`. The signature export completed, but the actual failing node count/interface was not persisted; the precise mismatch is not established. No release export, continuous ordinary/middle comparison, export parity, runtime, component or host measurement is available. The window rejection is independent of this execution failure.

A future justified export-only diagnosis can reuse the completed weights, persist actual graph count/names before attempting the crop, and retain the numerical and output gates. It must not repeat the fit. The prepared native temporal runner at032834e is not dispatched because this result does not qualify for promotion. Its source CI45041538501 passed, and its eleven local tests cover only pure/synthetic contracts. The worker workflow remains an undispatched draft.

The separate temporal-crop result45034216124 remains useful: bit-identical consumed outputs at10.88–11.20ms p99, versus about21ms before cropping. The shorter-lookahead166 trial remains rejected. Claude independently found that its losses concentrate at onset/body, with quiet held tails also needing protection. His support-filter research removes many false notes but retains per-label losses and has not passed the installed gates.

Installed/default outputs and the recorded scoreboard are unchanged. Reliable live guitar use, robust chord/unison tracking, external-device delivery and the remaining deadline gates are not established. Overall completion is not measured.

The requested eight-hour window ended2026-11-22 18:25 UTC. Final collection occurred19:32 UTC after a turn interruption; uninterrupted execution and scheduled notification delivery are not claimed. Claude and Codex remain equal peers: this closeout does not pause Claude or create an approval gate.

Local report:`build/github-results/basic-pitch-release-adaptation-45037966575/artifact/basic-pitch-release-adaptation-result/report/report.json`. Full collection receipt:`build/github-results/basic-pitch-release-adaptation-45037966575/small-report-collection.json`. Checkpoint:`docs/recovery/github-basic-pitch-release-adaptation-20261122.json`.
