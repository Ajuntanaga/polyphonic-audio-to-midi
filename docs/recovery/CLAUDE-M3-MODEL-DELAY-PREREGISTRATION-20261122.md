# Model-delay sensitivity: plan and predictions, written before any shifted span is scored

Claude, 2026-11-22. Saved data only (the saved arm A spans, CURRENT, the native confirmation; no audio, model run, job or native edit; nothing promoted).

## Why

Every model-supported candidate (the union CURRENT + Basic Pitch, the cleanup filter whose support includes Basic Pitch) needs Basic Pitch running next to the native tracker, and Codex's ONNX lane is working out whether that is possible. "Real time" has no number yet. This asks what a given extra delay costs: if the model's events arrive L ms later than the saved arm A spans, how much of each candidate's gain survives? The answer is a latency budget for the ONNX lane to compare its measured pace against, not a measurement of any model's delay.

## Plan (fixed here)

- Delay model: every arm A span (l, r, p) becomes (l + L, r + L, p), clipped to the common horizon. A pure additional delay on top of whatever delay arm A already has (arm A is the saved ONNX offline causal run, itself not a real-time measurement). The native confirmation and CURRENT are not shifted.
- Grid, fixed now: L in {0, 50, 100, 250, 500, 1000, 2000} ms.
- Candidates, each scored with the committed gate-menu evaluator against CURRENT: union (CURRENT union shifted arm A), and filter (CURRENT intersect (shifted arm A union native), held D ms) at D = 220 and D = 50.
- Corpora: ordinary and extended-middle (both have an arm A span source).
- Reported per L: coverage, precision, wrong-pitch and gap-voice change, exact-set share, runs, labels losing (any, and over 5 / 25%), largest label loss, and for the union the share of its L = 0 coverage gain that survives.
- Derived, defined now: the **half-gain delay** is the largest grid L at which the union keeps at least 50% of its L = 0 coverage gain over CURRENT (ordinary).
- A label property known before scoring and used to calibrate the predictions below: ordinary labels have median length 748 ms (p10 549 ms, max 749 ms); the six extended-middle labels are 3,600 ms.

## Predictions (fixed before the first run)

| | prediction |
|---|---|
| D0 | L = 0 reproduces the committed gate menu exactly (union 67.52% coverage, 60.55% precision, 743 runs; filter D = 220 six losing labels). |
| D1 | Union coverage gain falls roughly with L / 748 ms: ordinary coverage at L = 250 is 55 to 62%, at L = 500 is 46 to 54%, and at L = 2000 is within 3 pp of CURRENT's 39.99%. |
| D2 | The half-gain delay on ordinary is 250 ms. |
| D3 | The union never removes anything: labels losing is 0 at every L and every tolerance. (Sanity check.) |
| D4 | Union wrong-pitch change stays within 8 pp of its L = 0 value (+23.8%) for every L up to 500 ms; union gap-voice change does not fall as L rises up to 1000 ms (late offsets spill into the gaps). |
| D5 | Filter D = 220, ordinary: the number of losing labels does not fall as L rises, equals 6 at L = 0, and at L = 2000 is within 2 of the native-only control's 9. |
| D6 | Filter D = 220, ordinary: the share of CURRENT's wrong-pitch output removed at L = 2000 is at least its L = 0 value (22.15%), because a model support that has moved out of the way protects less. |
| D7 | Extended-middle (3,600 ms notes): the filter at D = 220 loses 0 labels at every L up to 500 ms. |

Misses will be reported as misses. Anything computed beyond this table is labelled post hoc.

## What this does not do

It does not measure any model's delay, throughput or accuracy; it shifts one saved span list. One recording per corpus. A shifted span can by coincidence cover a later same-pitch note, which would flatter a large delay; the script flags nothing for that, and the large-L rows should be read as an upper bound. It is not a gate, a pass, or a change to Codex's frozen screens, and it needs no decision from the user.
