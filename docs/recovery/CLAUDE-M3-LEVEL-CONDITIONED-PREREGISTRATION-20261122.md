# Two saved-data scores, registered before any tape is opened

Claude, 2026-11-22. No new job, no audio, no policy, no promotion, no gate change. Inputs are tapes that already exist: the saved ordinary-corpus streaming tapes of run 45029161409 (`control164`, both models), and, for Part A, the `candidate166` tape from Codex's run 45036257574 (evidence artifact 14759539384, downloaded read-only; its sha256 is checked against the report's `bulk` entry before use).

## What I had seen before writing this

- Codex's report holds per-label whole-label present samples, not label-end presence. Computed from it (post hoc proxy, not the quantity registered below): the 166 change lowers whole-label presence by 4.58 pp on the 334 silent-after labels and 5.18 pp on the other 94, against 4.68 pp over all 428. That says nothing direct about the last frames of a label; it is why Part A needs the tapes.
- Nothing about the conditioning in Part B has been computed. The unconditioned level pattern is in `CLAUDE-M3-LEVEL-DEPENDENCE-20261122.md`.

## Part A: score of my earlier prediction on the 166/167 contrast

Registered earlier (`CLAUDE-M3-AUDIO-RELEASE-RESULT-20261122.md`, about 65%): *removing 23.22 ms of right context leaves label-end presence in the silent-after subset within a few points, since that context is silence there; any change should sit in the other ~22%.* The text gave no number for "a few points"; I fix it now at **3 percentage points**.

- **Unit.** The 428 evaluable ordinary ends of `CLAUDE-M3-AUDIO-RELEASE-ENDS-20261122.json`. *Present at the end* is the registered definition of the audio-level read: mean note posterior at the label pitch over frames g-2..g at least 0.3, g = the frame at or before the label end. *Silent-after* = the 80 ms after the end is exactly digital silence (level at or below -179 dB in the committed curves), 334 ends.
- **A1 (the registered claim).** Adapted arm, `control164` against `candidate166`: the share of silent-after ends that are present changes by at most 3 pp in absolute value. Pass or miss.
- **A2 (the second half of the claim).** The absolute change in the other 94 ends exceeds the absolute change in the silent-after subset. Pass or miss.
- Reported either way: both counts, the number of ends that flip in each direction, and the change by pitch band. Not a pass criterion.
- **Integrity checks before scoring.** The `candidate166` tape's frame clock must satisfy the same `c0a` check as the control (`frames[:,0] == arange`, `frames[:,1] == 256 * frames[:,0]`), its sha256 must match the report, and the `control164` tape must reproduce the saved groups of the ends file. If any fails, the score is withheld and reported as such.

## Part B: does the level pattern survive conditioning on early detection?

Question: the saved-data note found that presence at the label end follows the level just before the end (adapted 0% below -70 dB, 93% above -40 dB). Is that because quiet notes were never detected at all, or because they were detected and then dropped?

- **Early detection.** Mean note posterior at the label pitch over frames g-17..g-13 (about 151 to 197 ms before the end) at least 0.3. Ends whose label span is shorter than 230 ms are excluded so that the early window lies inside the label (the n after exclusion is reported).
- **Level.** `pre`, the level of [E-80 ms, E) at the pitch's first harmonics, from the committed curves (as in the saved-data note). Presence at the end as in Part A. Corpus: ordinary, all evaluable ends not excluded above; the uncontested stratum is reported as a check. Both models, from the saved `control164` tapes.

Registered claims (adapted model unless stated):

| Id | Claim | My odds |
|---|---|---:|
| B1 | Among early-detected ends, presence at the end still rises with `pre`: AUC (level, present vs not) at least 0.65, with at least 20 ends in each outcome class (otherwise not evaluable) | 60% |
| B2 | At least 70% of ends with `pre` below -60 dB are not early-detected | 65% |
| B3 | The conditioned AUC is lower than the unconditioned AUC computed on the same ends by at least 0.05 (conditioning removes part of the effect) | 50% |
| B4 | Among early-detected ends with `pre` below -60 dB, at most half are present at the end (n at least 10, otherwise not evaluable) | 55% |

## Reading rules, fixed now

- **B1 passes:** the level pattern is partly a hold effect (detected, then dropped as the note gets quiet), not only an onset effect. Quiet-end behaviour is then a legitimate target for release-context training and for any end-handling lever, and the shape of the training endings matters.
- **B1 misses and B2 passes:** the pattern is mostly "quiet notes were never detected", and end-presence only inherits that; release-context training would not reach them, and the lever lies earlier (onset, level, front end), which the mixed-level probe already says is not the front end.
- **B3 misses:** conditioning does not change the picture, so detection history is not the confound.
- Nothing here proposes a policy or a gate. Misses are reported as misses; anything computed after seeing the numbers is labelled post hoc.

## Limits

One recording; ends within a take are not independent, so AUCs carry more uncertainty than their n suggests (a bootstrap over ends is reported, a bootstrap over takes is not possible from the committed files). The tape is a posterior, not a decoder event. "Early detected" uses the same 0.3 threshold as the decoder's frame threshold but no onset logic.
