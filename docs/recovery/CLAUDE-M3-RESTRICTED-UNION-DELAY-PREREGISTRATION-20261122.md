# Restricted union under model delay: plan and predictions, fixed before any run

Claude, 2026-11-22. Saved data only (saved arm A spans, CURRENT; no audio, model run, job or native edit; nothing promoted).

## Why

The delay sweep (`CLAUDE-M3-MODEL-DELAY-RESULT-20261122.md`) showed the full union pays only under about 150 ms of model lag, because delayed correct notes turn into wrong pitches in the next note's window. My earlier false-output band analysis put most of CURRENT's and the model's false output below MIDI 60, and an earlier note found that adding only model spans at MIDI 60 and above kept most of the coverage gain with less false output (63.32% coverage, 62.37% precision, +13.1% false at L = 0). The user's own framing is that a tuner locks to the string or pitch range it is set to. Question: does that pitch-range partition also widen the lag budget?

## Plan (fixed here)

- Candidate: CURRENT union (arm A spans with pitch >= 60, shifted by L ms and clipped to the common horizon). One cut only, the 60 already used; no other cut is tried.
- Grid, fixed now: L in {0, 50, 100, 150, 200, 250, 500, 1000} ms. Ordinary corpus (extended-middle's notes are all pitch 52, so a >= 60 cut would add nothing there; reported as a check).
- Reported per L, next to the full union from the committed delay JSON: coverage, precision, wrong-pitch change, gap-voice change, combined false change (wrong plus gap voice, against CURRENT's), exact set, runs, labels losing, share of the L = 0 coverage gain kept.
- Same committed evaluator as the delay sweep; no new scoring code.

## Predictions (fixed before the first run)

| | prediction |
|---|---|
| E0 | L = 0 reproduces the earlier restricted numbers: coverage 63.32%, precision 62.37%, combined false +13.1% (to within 0.05). |
| E1 | At every L the restricted union has precision at least the full union's and coverage at most the full union's. |
| E2 | The restricted union's precision stays above CURRENT's 54.20% at L = 200 and is below it at L = 500, so its lag budget is at least 200 ms and under 500 ms. |
| E3 | The restricted union loses no label at any L (it only adds). |
| E4 | Its combined false change at L = 100 is at most +25%. |
| E5 | The share of the L = 0 coverage gain kept at L = 250 is within 5 points of the full union's 70%. |

Misses are reported as misses; anything computed beyond this table is labelled post hoc.

## What this does not do

It does not decide the label rule, change any gate, or say a pitch partition is safe on other material: one recording, the cut at 60 was chosen from earlier looks at this same recording (design use), and the extended-middle check is vacuous by construction. It is still a union, so extras still rise and the strict rule is still unmet.
