# Pre-registration: an onset grace for the cropped-ONNX support filter (post hoc candidate)

Claude, 2026-11-22. Written and committed before the grace script is run. Nothing here is a result.

## Why

`CLAUDE-M3-ONNX-HOLD-GRID-RESULT-20261122.md` (commit `060fb2b`) showed that the cropped-ONNX support's remaining budget failures on ordinary are head-of-note losses (labels 263, 364, 389, 398: the filtered note starts 40.8, 50.6, 0.7 and 5.3 ms after CURRENT's), which no forward hold can recover. The only causal way to recover them is to let CURRENT's own note start through before the support exists: **an onset grace of G ms.** Cost: any CURRENT span with no support also lets its first G ms through, so some wrong-pitch and gap output returns. This asks how large that cost is.

This is a **new post hoc candidate**, chosen after the losers were known, scored on two recordings both seen. It is not an acceptance and promotes nothing. I have not scored any grace. I have seen the D = 50 / 220 results and the D = 220..600 hold grid only.

## Definition

Filter = (CURRENT intersect support held forward D ms) union (the first G ms of every CURRENT span, clipped to the span). Support = model spans union the native confirmation. A span's "first G ms" is measured from its own start; a span that restarts after a gap gets a new grace, as a new MIDI note-on would. Causally this means: emit CURRENT's note-on at once; if no support appears within G ms, cut the note. Clock `emitted_ns`. Event files, scorer and budget code are the same as the earlier results.

**Grid, fixed now:** G in {0, 10, 20, 30, 40, 50, 75, 100} ms, D in {220, 260} (220 is the earlier D; 260 is the largest D at which the adapted support kept the cleanup benefit and where adapted label 42's tail loss is already gone). Two supports (cropped unmodified, cropped adapted), both corpora. G = 0 is the reference and must reproduce the committed `CLAUDE-M3-ONNX-SUPPORT-20261122.json` (D = 220) and the hold-grid JSON (D = 260) exactly, or nothing else is reported.

## Predictions, each can fail (ordinary, emitted clock, D = 220 unless stated)

| Id | Claim | Odds |
|---|---|---:|
| G0 | G = 0 reproduces the committed D = 220 and D = 260 rows for both supports | 97% |
| G1 | Monotone in G: coverage never falls, wrong-pitch removed never rises, labels losing never rises (the output only grows) | 99% |
| G2 | Cropped adapted passes the frozen label budget at some grid G | 88% |
| G3 | The smallest such G is at most 30 ms | 60% |
| G4 | At that G the wrong-pitch removed share is still at least 20% | 35% |
| G5 | At that G the gap delta is still at most -250,000 samples | 60% |
| G6 | Cropped unmodified never passes the budget at any grid G (label 229 is a 152 ms tail loss that a grace cannot touch at D = 220) | 90% |
| G7 | Cropped adapted at D = 260: the strict gate (`no_pitch_safety_regression`) is True at some grid G | 65% |

## Reading rule (fixed now)

For cropped adapted at D = 220, find the smallest grid G that passes the budget. Then:

- **A, reconciled:** it exists and the cleanup benefit is retained there by the earlier rule (ordinary coverage within 0.10 points of CURRENT 39.9932%, wrong-pitch removed share at least 20%, gap delta at most -250,000, extended-middle strict gate True). An onset grace would clear the two labels without giving up the cleanup. It still needs a recording not used to choose G.
- **B, trade-off:** it passes the budget only where the benefit is not retained, so grace buys the budget by returning the wrong output.
- **C:** no grid G passes.

The strict result is reported at every cell. Extended-middle is a safety check only (the output stays a subset of CURRENT and already loses nothing at D = 220, so it cannot get worse).

## What cannot be concluded

G and D are selected after the fact; two recordings, both seen. Saved-event, emitted-clock reconstruction, not native or host behaviour: a real grace would put short-lived false notes into live MIDI, which this scores only as samples of wrong output, not as audible or lifecycle cost. No lane, string or MIDI-lifecycle claim. Promotes nothing; no gate changes.
