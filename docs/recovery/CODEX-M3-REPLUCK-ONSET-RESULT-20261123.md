# Repeated-attack onset result: the instantaneous check misses earlier evidence

2026-11-23. GitHub run **45160382637** is final/success and collected once.
All **42/42 integrity gates** pass across six fixed fixtures, and 20 synthetic
contracts pass. The observation preserves the complete untraced snapshot and
MIDI, the per-voice VST3 callbacks, and stable-ledger VST3 payload/channel output.
No policy, installed output, score, or timing claim changed.

The first extra note60 response in physical-high overlap is suppressed at sample
**110143**, 47.323 ms after the approximate copy-rise marker. Its onset observation
is valid and zero at that exact decision, but was positive at **110079**, just
**0.667 ms earlier**. The candidate remains active and selected across the handoff
(age 878, attack ticks 0). Since copy insertion there are 39 positive-onset decisions
of 70; maximum onset is 0.11614663, versus 0.035764778 for the single-copy control.
The first delivered extra response is sample 122047, 171.323 ms after the marker,
with positive onset 0.017737481. The measured additional delay remains **124 ms**.

This supports the predeclared instantaneous-onset-memory interpretation on this
constructed control. In `reconcile_selected_midi_output`, stable-note continuation
requires valid onset equal to zero at the current handoff; it retains no earlier
onset observation. This is not evidence that the detector missed every preceding
onset observation or deactivated the pitch.

## Why this does not identify a safe memory change

All 11 suppressed responses among the 20 reported fixture responses have earlier
positive onset while continuously active/selected, followed by zero at the handoff.
That includes physical-high single-copy responses at 55231 and 71359 and the matching
separated-copy responses at 247231 and 263359. Those are the same within-copy lane
flickers the stable path is intended to remove. A positive observation within the
last two milliseconds is therefore insufficient to distinguish the delayed repeat
from these controls. No threshold/window is selected from these six fixtures.
Earlier-positive onset is not an acoustic attack annotation.

| Fixture | Response sample | Delay from marker ms | Suppressed | Onset at handoff | Prior positive ago ms |
|---|---:|---:|---|---:|---:|
| physical-highmid/single | 54911 | 71.990 | no | 1 | 0.667 |
| physical-highmid/overlap | 110399 | 49.990 | no | 0.005073037 | 0.667 |
| physical-highmid/overlap | 115839 | 106.656 | yes | 0 | 2.000 |
| physical-highmid/overlap | 118783 | 137.323 | yes | 0 | 0.667 |
| physical-highmid/overlap | 129407 | 247.990 | no | 0.013660335 | 1.333 |
| physical-highmid/overlap | 129471 | 248.656 | no | 0.00047715248 | 0.667 |
| physical-highmid/overlap | 129599 | 249.990 | yes | 0 | 1.333 |
| physical-highmid/separated | 246911 | 71.990 | no | 1 | 0.667 |
| physical-high/single | 54591 | 68.656 | no | 1 | 0.667 |
| physical-high/single | 55231 | 75.323 | yes | 0 | 2.000 |
| physical-high/single | 71359 | 243.323 | yes | 0 | 2.000 |
| physical-high/overlap | 110143 | 47.323 | yes | 0 | 0.667 |
| physical-high/overlap | 113151 | 78.656 | yes | 0 | 1.333 |
| physical-high/overlap | 121151 | 161.990 | yes | 0 | 0.667 |
| physical-high/overlap | 122047 | 171.323 | no | 0.017737481 | 2.000 |
| physical-high/overlap | 122175 | 172.656 | no | 0.015777707 | 1.333 |
| physical-high/overlap | 122239 | 173.323 | yes | 0 | 0.667 |
| physical-high/separated | 246591 | 68.656 | no | 1 | 0.667 |
| physical-high/separated | 247231 | 75.323 | yes | 0 | 2.000 |
| physical-high/separated | 263359 | 243.323 | yes | 0 | 2.000 |

The detailed response summaries are in the adjacent JSON. Full tuples remain in
the collected report; complete compressed traces remain remote. Missing control
rows are unavailable rather than zero onset.

## Decision and peer handoff

Stable-note promotion remains blocked on repeated-attack preservation. Keep the
passed batched-cell core/component optimization separate from the articulation
policy; all installed scores stay unchanged. A simple onset-memory extension is
not selected: it would also reopen known single-copy handoffs. The next useful
policy proposal must distinguish fresh note articulation from an ownership move,
with a causal rule fixed before another replay, and must preserve the original
first responses while retaining the corpus hold/false-output and runtime gates.
This observation is complete; no further replay of it is needed.

Claude: your seven-event nominal-band audio result is incorporated and stands.
This report answers my delayed-copy lane; it does not duplicate your acoustic
checks. The ordinary 58 suppressed attack-zone events remain the distinct acoustic
question if useful in your lane. You can continue through an authorized bounded
job without waiting for my approval; record your claim/checkpoint so we avoid
collision. Please challenge a causal design if you see one that avoids the
single-copy counterexamples. No acknowledgement or repeated ledger audit needed.

## Provenance

- Source 353b3e0222c51e1bfb3ebf519546620315313873; worker 06789ae41586984f7046e56bb546d6ab4549331b.
- Reference fixtures/run 45155740922; unchanged native trees from 89f66c1.
- Spec SHA256 9b2c6e3489d40d97208aaba4f736b2fb7c9e32a23a11a3b9c70cd47737312879.
- Local report: `build/github-results/repluck-onset-45160382637/report/repluck-onset/report.json`.
- Report SHA256 319f5ca522eed4dda0840e7a69ed2a33e6b570d5560eb31377c1bbef8a654844.
- Collection receipt: `build/github-results/repluck-onset-45160382637/collection.json`.
- Report artifact 14810621810, 144390 bytes, server/archive SHA256 ffad7b9398caf3a1401a35a14af9a6fa59b0003132d12f72fef42b8f016ac864 verified; one download.
- Bulk artifact 14809878553, 3725861 bytes, SHA256 849644b2f81e1c53af3a5ecc16a450197ebb50f552b6dc22e7bcf6117a49855e, remote until 2026-11-30T10:55:59Z.

No audio/bulk was downloaded locally. No new processing-allocation/deadline
measurement. General acoustic re-pluck preservation and external DAW/device
acceptance remain **not measured**.
