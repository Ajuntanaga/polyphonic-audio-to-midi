# Pre-registration: a uniform longer hold for the cropped-ONNX support (post hoc grid)

Claude, 2026-11-22. Written and committed before the grid script is run. Nothing here is a result.

## Why, and what this is not

`CLAUDE-M3-ONNX-SUPPORT-RESULT-20261122.md` found that the cropped-ONNX support keeps the cleanup benefit at hold D = 220 ms but leaves two ordinary labels over the frozen 25 ms / 5% budget (label 263: 34.83 ms, 10.18%; label 364: 50.57 ms, 6.76%), and the unmodified events also lose label 229 (151.99 ms). The open question is whether that is a hold-length problem (the model's note-off arrives early and a slightly longer hold would cover it) or a support-gap problem (the support is missing in the middle of the note, so no hold length helps without giving the wrong output back).

This is a **post hoc grid**. The grid points beyond D = 220 were chosen after seeing the D = 220 losers, so any D that clears them is selected on the very recording that exposed them. It cannot validate a hold length, it is not an acceptance, and it changes no gate, default or native code. Extended-middle cannot help: the filter is CURRENT intersected with a support, so a longer hold can only add output back and that corpus already loses nothing at 220. It is reported only as a safety check. The result is a trade-off curve, to be read as a description.

I have seen the D = 50 and D = 220 results only. No D above 220 has been scored for the cropped events.

## What will be run

`CLAUDE-M3-ONNX-HOLD-GRID-20261122.py` reuses the committed scorer and loser table through `CLAUDE-M3-ONNX-SUPPORT-20261122.py` unchanged, replacing only the hold grid. Support = model spans union the native confirmation, held forward D ms; filter = CURRENT intersect support; clock `emitted_ns`; two supports (cropped unmodified, cropped adapted), both corpora, same four pinned event files. **Grid, fixed now: D in {220, 260, 300, 350, 400, 500, 600} ms.** D = 220 is the reference row and must reproduce the committed `CLAUDE-M3-ONNX-SUPPORT-20261122.json` exactly (coverage, wrong-pitch removed share, gap delta, labels losing); if it does not, nothing else is reported.

## Predictions, each can fail (ordinary, emitted clock)

| Id | Claim | Odds |
|---|---|---:|
| L0 | The D = 220 row reproduces the committed JSON for both supports | 97% |
| L1 | Along the grid, coverage never falls, wrong-pitch removed share never rises and labels losing never rises (true by construction of a growing support; a check on the code) | 99% |
| L2 | Cropped adapted passes the frozen label budget (no label over 25 ms / 5%, none missed, wrong and gap not up) at some grid D | 75% |
| L3 | The smallest such D for cropped adapted is at most 350 ms | 60% |
| L4 | At that D the wrong-pitch removed share is still at least 20% | 35% |
| L5 | At that D the gap delta is still at most -250,000 samples | 55% |
| L6 | Cropped unmodified needs a larger D than cropped adapted to pass the budget, or never passes (label 229 loses 151.99 ms at 220) | 80% |
| L7 | The strict gate (`no_pitch_safety_regression`) is True at some grid D for cropped adapted | 50% |

## Reading rule (fixed now)

For each support, find the smallest grid D at which the budget passes. Then:

- **A, reconciled:** such a D exists and the cleanup benefit is retained there by the same rule as before (ordinary coverage within 0.10 points of CURRENT 39.9932%, wrong-pitch removed share at least 20%, gap delta at most -250,000, extended-middle strict gate True). A longer uniform hold would clear the two labels without losing the benefit. It still needs a recording that was not used to choose D.
- **B, trade-off:** the budget passes only at a D where the benefit is no longer retained. No uniform hold gives both.
- **C, support gap:** the budget fails at every grid D. The losses are not about hold length.

The strict result and the budget result are both reported at every D.

## What cannot be concluded

This is two recordings, both seen. D is selected after the fact. It is a saved-event, emitted-clock reconstruction, not a native or host measurement. It says nothing about lanes, strings, MIDI lifecycle or live behaviour, and promotes nothing.
