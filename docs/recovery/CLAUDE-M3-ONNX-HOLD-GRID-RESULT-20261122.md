# A longer uniform hold does not fix the cropped-ONNX support's two budget failures: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-ONNX-HOLD-GRID-PREREGISTRATION-20261122.md` (commit `ce53d32`, before the run). Post hoc grid on saved events, emitted clock; no audio, model run, job or native edit; nothing promoted.

## Answer

**No.** At every hold from 220 to 600 ms, both cropped supports still fail the frozen 25 ms / 5% label budget on ordinary and the strict gate (reading C in the pre-registration: the losses are not about hold length). Labels 263 and 364 lose 34.83 ms and 50.57 ms at every D, while the wrong-pitch cleanup shrinks as the hold grows.

| Cropped adapted, ordinary | D=220 | 260 | 300 | 350 | 400 | 500 | 600 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Coverage (CURRENT 39.9932) | 39.966 | 39.967 | 39.967 | 39.967 | 39.967 | 39.967 | 39.967 |
| Wrong-pitch removed | 22.28% | 20.19% | 18.66% | 17.08% | 15.68% | 13.30% | 11.54% |
| Gap delta (samples) | -344,176 | -342,512 | -337,830 | -329,813 | -315,413 | -290,360 | -252,127 |
| Labels losing | 5 | 4 | 4 | 4 | 4 | 4 | 4 |
| Largest loss (ms) | 50.57 | 50.57 | 50.57 | 50.57 | 50.57 | 50.57 | 50.57 |
| Over the budget | 263, 364 | 263, 364 | 263, 364 | 263, 364 | 263, 364 | 263, 364 | 263, 364 |
| Cleanup retained (earlier rule) | yes | yes | no | no | no | no | no |

Cropped unmodified: labels losing 6, 5, 5, 5, 5, 5, 5; largest loss 151.99, 138.67, 132.00, 111.32, 98.00, 67.33, 50.57 ms; wrong-pitch removed 22.17% falling to 11.01%; over budget 229, 263, 364 at every D (label 229 falls to 36.67 ms at 600, still above 25 ms); retained at 220 only. Extended-middle keeps 0 labels losing and the strict flag True at every D (by construction: the filter is CURRENT intersect a growing support, so it can only add output back).

## Why (post hoc diagnostic, not registered)

I had assumed a hold-length problem. `CLAUDE-M3-ONNX-HOLD-GRID-DIAGNOSTIC-20261122.py` splits each loser's lost time into head (before the filtered output starts), middle and tail, and it reconciles with the scorer's own loss to 0.05 ms for every row:

- **Labels 263, 364, 389, 398 (the four adapted losers that remain at D = 600) are 100% head loss.** The filtered note starts 40.83, 50.57, 0.68 and 5.34 ms after CURRENT's does. A hold extends the support forward past where a model span ends, so it cannot touch time at the start of a note.
- **Label 229 (unmodified only) and label 42 are tail losses.** A longer hold does shrink them: 229 goes from 151.99 to 36.67 ms by D = 600, and 42 (3.32 ms, adapted) is gone from the list at D = 600 (the adapted count falls from 5 to 4 by D = 260; I did not split the intermediate D rows).

So the filter's remaining cost on this recording is onset latency: it cannot emit a note until the model support appears, which for two labels is 34 to 51 ms after CURRENT began it. That fits the earlier finding that the loss against the offline Basic Pitch run is almost all onset delay, now seen label by label.

## Predictions, scored

| Id | Claim | Odds | Result |
|---|---|---:|---|
| L0 | D = 220 row reproduces the committed JSON | 97% | hit |
| L1 | Monotone in D | 99% | hit |
| L2 | Adapted passes the budget at some D | 75% | **miss** |
| L3 | Smallest passing D at most 350 | 60% | **miss** (no D passes) |
| L4 | Wrong removed at least 20% there | 35% | miss (vacuous: no D passes) |
| L5 | Gap delta at most -250,000 there | 55% | miss (vacuous) |
| L6 | Unmodified needs a larger D or never passes | 80% | hit (never passes) |
| L7 | Strict gate True at some D for adapted | 50% | **miss** |

Three of eight, and the misses share one wrong premise: I put 75% on a hold-length explanation and the head-loss split shows it was an onset explanation. L6 holds for a different reason than I gave (label 229 is a tail loss that does shrink, but 263 and 364 block it regardless).

## Limits

Post hoc grid chosen after the D = 220 losers were known, on two recordings both seen; extended-middle can only show safety. Emitted-clock reconstruction of saved events, not a native or host measurement. Head loss is measured against the label's own pitch within its window; it says nothing about lanes, strings or MIDI lifecycle. Nothing is promoted and no gate changed.

## Provenance

Scripts `CLAUDE-M3-ONNX-HOLD-GRID-20261122.py` (sha256 `76b9d31ce4f4`) and `CLAUDE-M3-ONNX-HOLD-GRID-DIAGNOSTIC-20261122.py` (`7080536ea181`); outputs `CLAUDE-M3-ONNX-HOLD-GRID-20261122.json` and `CLAUDE-M3-ONNX-HOLD-GRID-DIAGNOSTIC-20261122.json`. Inputs: the four hash-verified event members under `build/github-results/basic-pitch-temporal-crop-45034216124/claude-range-members/`. No change after the pre-registration commit.
