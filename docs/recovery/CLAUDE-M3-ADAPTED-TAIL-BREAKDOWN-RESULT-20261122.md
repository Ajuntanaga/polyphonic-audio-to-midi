# Adapted tails are censored by the 102 ms label gaps: still sounding at the gap end 59% of the time, against 21.5% unmodified

Claude, 2026-11-22. Saved data only (Codex's unmodified and adapted TensorFlow event files, run 45022134487, ordinary corpus, availability clock; the labels). No audio, model run, job or native edit; nothing promoted; no gate touched. Plan and four predictions: `CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-PREREGISTRATION-20261122.md` (commit fe01a1d, before the first run). Script `CLAUDE-M3-ADAPTED-TAIL-BREAKDOWN-20261122.py` (sha256 bfeac3f7e5d5, self-test built in), output `.json` (4e3282dc2a26).

## Answer first

**The tail lengths I reported in the gap-extras result are lower bounds, not lengths.** About four-fifths of the 132 label-free gaps in the ordinary corpus are 101 to 102 ms long (labels are 748 ms takes, 72% of them exactly that, followed by a 102 ms gap), and a tail cannot be seen past the next label's start. So the "median 102.1 ms" whole adapted tail is the gap length, not a hold time: 219 of the 424 adapted same-pitch tails (52%) are exactly nine model frames, 102 ms. I withdraw the sentence "the adapted tails are about 2.4 times as long as the unmodified ones" from that note (it compared two medians cut off at the same cap); the correction is in that note now.

**The direction survives, measured without the cap hiding it.** Share of label ends where the run is still sounding when the gap ends:

| gap length | label ends | adapted run | unmodified run | median tail adapted / unmodified |
|---|---|---|---|---|
| under 110 ms | 346 | 61.8% | 22.8% | 101.8 / 60.0 ms (capped) |
| 110 to 300 ms | 32 | 46.9% | 15.6% | 182.4 / 84.1 ms |
| 300 ms or more | 46 | 47.8% | 15.2% | 324.6 / 132.8 ms |
| all | 424 | 59.2% (251) | 21.5% (91) | 102.1 / 63.3 ms (capped) |

In the long gaps, where the cap is far away, the adapted tail is about 2.4 times the unmodified one (325 against 133 ms) and the adapted run is still sounding at the gap's end three times as often. So the adapted model does hold released notes longer, but the size of the effect on notes with a long gap after them is roughly 190 ms of median tail, not 59 ms, and for four-fifths of label ends the corpus cannot show how long the hold really is.

## Registered predictions: 1 of 4 passes

| | prediction | result |
|---|---|---|
| T1 | adapted tail strictly longer than the unmodified tail in at least 80% of pairs | **miss**, 70.8%. Where both runs reach the gap end the pair ties at the cap and counts as not longer; 346 of 424 rows have a gap under 110 ms. |
| T2 | median paired difference between 30 and 100 ms | pass, 34.8 ms (p90 102.3 ms), but a lower bound for the same reason |
| T3 | median adapted tail at least 20 ms larger in the low band (pitch 47 and below) than the high band (60 and above) | **miss**, 102.3 against 96.7 ms (+5.6 ms; 134 and 173 label ends). No register effect is visible, and the cap flattens any that exists. |
| T4 | paired difference within 30 ms between shortest and longest label-length terciles | **miss**, 45.8 ms apart. The terciles are degenerate: the cut points are 747.5 and 747.7 ms because 72% of labels are 748 ms takes. The "short" tercile (78 label ends, labels under 747.5 ms) is the one with long gaps (adapted median tail 230 ms), so this is the gap length again, not the note length. |

## Post hoc (labelled)

- 5 label ends have an unmodified same-pitch tail and no adapted tail at all (adapted shortened the note), against 424 adapted tails; a net lengthening, not uniform.
- Among adapted tails that end inside the gap, the median is 82 ms (73 ms in the short gaps, 243 ms in the long ones); the unmodified run's median on the same label ends is 0 ms, because it had usually already stopped.
- The earlier arm A tail anatomy (`CLAUDE-M3-ADDITIVE-HYBRIDS-20261122.md`: 92% of that run's added gap is a same-pitch tail, median 41 ms past the label end) is subject to the same cap; its share and direction stand, its median is a lower bound.
- The class split in the gap-extras result (96.6% carried in, 3.4% born in the gap) does not depend on tail length and is unchanged.

## What this means

- The release effect is real but its size is mostly unmeasured by this corpus. For a release-adaptation readout, report the share still sounding at the gap end and the long-gap strata, not a pooled tail median. Baseline to beat on the saved run: adapted 59.2%, unmodified 21.5% (all label ends); long gaps 47.8% against 15.2%.
- The long-gap stratum has 46 label ends in one recording; it is a direction, not a held-out measurement.
- A synthetic probe (`CLAUDE-M3-RELEASE-PROBE-PROPOSAL-20261122.md`) does not have this cap, which is a reason to run it: it can measure the hold time directly, on an abrupt cut and on smooth decays.
- Nothing here says a tail past a label end is a fault: the labels end at nominal take boundaries and real ring-out is possible.

## Caveats

One recording per corpus, shared source takes with the adaptation fits (descriptive, not generalization), saved TensorFlow event files only. Gap lengths and the 748 ms take length are properties of this corpus's construction.
