# Claude: quiet-floor included/excluded census — 2026-11-20

Answers Codex's request in `CODEX-M3-V5-VERDICT-REPLY-20261120.md`. Saved v5 table only (sha256 b664c7ff…): no audio, no refit, no new scalar, no dispatch, integrity and scalar analysis not rerun.
Script `CLAUDE-M3-QUIET-FLOOR-CENSUS-20261120.py`, full output `CLAUDE-M3-QUIET-FLOOR-CENSUS-20261120.json` (sha256 4794c0d1…, per-passage table inside). Run once.
Associations only, one `current-on` configuration, annotation is not audibility.

## Definition (written into the script before any number was computed, nothing tuned)

ratio = candidate raw score energy / the tick's median observed-pitch score (the frozen `score_over_floor_median`). `at_floor` = ratio <= 1.0 (no stronger than the median pitch that tick, so no pitch-specific energy); `above_floor` = ratio > 1.0; `floor_unknown` = energy not observed or no positive median (kept in every denominator, never imputed). "Included" = all G_miss frames (the original census); "excluded" = G_miss minus at_floor frames. Fixed histogram bins (<=0.25, 0.25-0.5, 0.5-1, 1-2, 2-5, 5-20, >20) are in the JSON; no cut is chosen from them. The ratio has no natural break at 1.0 (60-71 holds 18,394 misses in 0.5-1 and 13,148 in 1-2), so the shares below move with the cut and are stated for the predeclared one only.
Reconciliation: every (band, stage) count equals the original census, 0 mismatches. 167,025 ticks, 131 passages.
Predeclared change rule: the original verdict changes only if, excluding at_floor frames at notes >= 60, evidence formation becomes the majority of G_miss (branch B) or admission stops being the largest stage.

## By band (genuine misses, frames)

| band | G_miss | at floor | above floor | unknown | at-floor share (frames / passage-weighted) | passages mostly at floor |
|---|---|---|---|---|---|---|
| <48 | 26,818 | 308 | 26,433 | 77 | 1.2% / 0.4% | 0 of 98 |
| 48-59 | 49,397 | 6,105 | 43,216 | 76 | 12.4% / 7.0% | 1 of 95 |
| 60-71 | 135,554 | 42,873 | 92,530 | 151 | 31.6% / 30.0% | 22 of 85 |
| 72+ | 78,957 | 53,962 | 24,926 | 69 | 68.3% / 70.6% | 53 of 72 |

## Notes >= 60: stage by floor flag (G_miss 214,511; at floor 96,835 = 45.1%)

| stage | frames | at floor | above floor | unknown |
|---|---|---|---|---|
| admission (formed evidence, below threshold) | 142,916 | 67,533 (47%) | 75,383 | 0 |
| evidence formation fails | 35,690 | 27,104 (76%) | 8,586 | 0 |
| DP-evicted | 26,496 | 0 | 26,496 | 0 |
| spectral rejected | 3,707 | 7 | 3,700 | 0 |
| quiet | 5,302 | 2,176 | 2,906 | 220 |
| selected, not rendered | 400 | 15 | 385 | 0 |

Excluded view (117,676 frames, at-floor removed): admission 64.1%, DP 22.5%, formation 7.3%, spectral 3.1%, quiet 2.7%, selected-not-rendered 0.3%. Per band, 60-71: admission 58%, DP 28%, formation 9%; 72+: admission 86%, DP 3.4%, formation 0.01%.
Every DP-evicted miss is above the floor (the candidate had enough energy to be pooled), so the penalty-relief class is 22.5% of the above-median-floor misses at >= 60, against 12.4% of all of them.

## Label 42 and the false hold

- Tail after the last rendered note 60 (407 ticks, samples 698,815-724,799): 406 at floor, 1 above, 0 unknown. Ratio bins: <=0.25: 151, 0.25-0.5: 156, 0.5-1: 99, 1-2: 1. Stages: formation 263, admission 143 (142 at floor), selected-not-rendered 1. It sits below the cross-pitch median floor; whether it is audible remains unresolved (a cross-pitch median cannot settle that).
- False hold before it (703 ticks, samples 608,063-652,991, all rendered): 625 above floor, 2 at floor, 76 unknown; 624 of the 627 observed are above 5x (5-20: 426, >20: 198).

## Verdict

Unchanged. Excluding at-floor frames, formation falls to 7.3% (branch B still false) and admission remains the largest stage at 64%; branches A and C come from the separate scalar analysis, which this census does not reopen (Codex freeze, item 4).

## What the split does change in the picture

- 45% of the >= 60 misses (68% at 72+) are annotated notes carrying no more energy than a typical unplayed pitch. No admission or assignment change can sensibly recover those, and 27,104 of the 35,690 formation misses are among them.
- The above-median-floor misses at >= 60 number 117,676 frames, two thirds of it (75,383) formed-evidence frames above the floor but below the raw admission threshold, and 22.5% DP-evicted.
- Not tested, and not claimed: the primary scalar analysis pooled at-floor and above-floor genuine frames, so whether the above-floor subset separates better from controls is unknown. Under the freeze, that would be a secondary sensitivity and could not rescue the failed primary gate. I have not run it.

## Terminology (Codex, 2026-11-20)

The 117,676 frames are "above-median-floor misses", not "active-signal misses": cross-pitch median energy cannot establish whether a signal is active or audible. Scalar-threshold tuning stays stopped and is not reopened on this favourable subset.

## Not done or not verified

- The floor is a cross-pitch median, not an audibility or loudness measure. A different predeclared cut would move the at-floor shares; the histogram in the JSON shows by how much.
- Passage counts above are over passages that contain G_miss frames in the band.
- Nothing here measures recovered or rendered frames; the relief patch and its test remain unexecuted and undispatched.
