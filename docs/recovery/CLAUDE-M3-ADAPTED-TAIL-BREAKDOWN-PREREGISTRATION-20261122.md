# Adapted same-pitch tails by register and label length, paired with the unmodified run: plan and predictions, fixed before any run

Claude, 2026-11-22. Saved data only (the same unmodified and adapted TensorFlow event files from run 45022134487, labels), availability clock, same classification as `CLAUDE-M3-ADAPTED-GAP-EXTRAS-RESULT-20261122.md`. No audio, model run, job or native edit; nothing promoted; no gate touched. It narrows the release probe proposal (`CLAUDE-M3-RELEASE-PROBE-PROPOSAL-20261122.md`) and replaces the unpaired "median versus median" tail comparison in the gap-extras result with a per-label pairing.

## Definitions (fixed here)

- Unit: each ordinary-corpus gap segment the gap-extras script classes as `carried_in_same_pitch_tail` (an adapted span at pitch p covering the sample just before a gap, with a label of pitch p active there). Label length = that label's `end_sample - start_sample`.
- Adapted tail = the gap piece length (`hi - lo`, ms). Unmodified tail = the length of the unmodified run's coverage at pitch p running continuously from the gap start (0 if it does not cover the gap start). Pair difference = adapted minus unmodified tail.
- Register bands by label pitch: low <= 47, mid 48 to 59, high >= 60 (the open strings 32 to 60 span all three).
- Label-length terciles over the segments' labels.

## Predictions (fixed before the first run)

| | prediction |
|---|---|
| T1 | In at least 80% of paired tails the adapted tail is strictly longer than the unmodified tail. |
| T2 | The median paired difference is at least 30 ms and at most 100 ms (consistent with the unpaired +59 ms). |
| T3 | The median adapted tail is larger in the low band than in the high band by at least 20 ms (low-register notes decay slowly, so a residue reads as ring-on longer). |
| T4 | The median paired difference differs by less than 30 ms between the shortest and longest label-length terciles (the lengthening is not a long-note effect). |

Misses are reported as misses; every figure computed beyond this table is labelled post hoc. Nothing here says a tail past a label end is a fault: the labels end at nominal times and real ring-out is plausible.

## What this does not do

It does not say why the adapted model holds longer, and it cannot separate a register effect from the number of notes in each band (counts are reported). One recording per corpus; the ordinary corpus shares source takes with the adaptation fits, so this is descriptive, not held-out generalization.
