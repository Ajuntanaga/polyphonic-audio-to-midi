# Pre-registration: held-out check of the low-register re-render gates on the extended-middle corpus

Claude, 2026-11-22. Written and committed before the extended-middle v5 trace (run 45062999189, Codex's observation) was opened; the commit time is the record. Saved trace and CURRENT's saved spans only: no audio, no model run, no new job, no native edit, nothing promoted, installed scoreboard unchanged.

## What is being tested

The label-free re-render rule B(1.5) and the gates screened for it were all chosen on the ordinary corpus (`CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122`, `CLAUDE-M3-LOWREG-RERENDER-LOSERS-20261122`). The best of them, own `band_score <= 0.108358` (+0.403 coverage points, exact-set x1.276, wrong-pitch -159,291, gap 0, one label losing 1.3 ms), was picked **post hoc** from a 301-gate screen after the results were known. Both of those notes said the same thing: no extended-middle trace existed, so there was no held-out check. Codex's run 45062999189 produced one. This is that check.

Frozen, nothing refit for this corpus: rule B(1.5) (a lower voice with `direct == 0` and a related unrendered pitch whose fundamental share is at least 1.5 times its own); six configurations with exactly the thresholds the ordinary note printed:

1. B(1.5) ungated
2. `o_release >= 12`
3. exclude `rel=octave`
4. `o_band_score <= 0.174142`
5. `o_band_score <= 0.108358` (**the lead**)
6. `o_band_score <= 0.0615331`

Scoring is the ordinary plumbing unchanged: each fire removes the voice's pitch and adds the target over that tick's 64 samples in CURRENT's saved spans, scored by `tools/pitch_detector_comparison.score` with the per-label loss audit; immediate replacement is assumed (an optimistic bound, not a native result). Script: `CLAUDE-M3-LOWREG-HELDOUT-20261122.py`. Regression test on ordinary done before this note: it reproduces the ordinary pool (16,822 fires), all five gate fire counts (11,847 / 7,809 / 5,047 / 3,365 / 1,683), every coverage gain, wrong-pitch delta and losing-label count of the losers note, and CURRENT's saved score (13,525,345 present, 53,249 exact-set, 7,808,309 wrong, 3,621,485 gap). Result file `CLAUDE-M3-LOWREG-HELDOUT-ORDINARY-REGRESSION-20261122.json`.

## What I have and have not seen of this corpus

Seen: CURRENT's saved score and spans on extended-middle (6 labels, 14 spans, 97.49% coverage, 73.97% precision, from the support-filter note), the baseline and report files that give the labels and horizon (2,233,574 samples), Codex's identity checks for run 45062999189. Not seen: the v5 trace, any fire of the rule on this corpus, any edit score, which labels (if any) a fire would hit.

## Predictions, each can fail

| Id | Claim on extended-middle | Odds |
|---|---|---:|
| X0 | An edit with no removals and no additions reproduces CURRENT's saved score exactly (plumbing) | 95% |
| X1 | The B(1.5) pool has at least 100 fires | 65% |
| X2 | Ungated B(1.5) loses present samples on at least one of the 6 labels | 60% |
| X3 | The lead (config 5) loses no label (`labels_losing == 0`) | 60% |
| X4 | The lead lowers wrong-pitch samples (delta < 0) | 75% |
| X5 | The lead's coverage gain is non-negative | 80% |
| X6 | Octave-class fires are at least 50% of the pool (ordinary: 53.6%) | 70% |

## How the lead will be read (fixed now)

- **Supported:** config 5 fires at least 20 times, loses no label, lowers wrong-pitch samples, has a non-negative coverage gain and a gap delta of at most 0.
- **Contradicted:** config 5 removes more than 10 ms of present samples from any label, or raises wrong-pitch samples, or lowers coverage.
- **Uninformative:** config 5 fires fewer than 20 times.
- **Mixed:** anything else, reported as it falls.

The whole six-row table is reported whatever it shows, with per-label losses in milliseconds, fires per label, and the relation-class mix.

## Limits, stated in advance

One recording of about 23 s and 6 labels of sustained chords, so this checks **safety** (does the rule cut held notes, does it add wrong pitches) far better than benefit: CURRENT is already at 97.49% coverage, so the largest possible coverage gain is 2.51 points. Fires within a sustained note are strongly correlated, so counts overstate independence, and one lost label is a large share of the corpus. A "supported" verdict makes the ordinary lead less likely to be a selection artefact; it does not validate it as a rule, does not model onset confirmation, hold or minimum duration, and does not select anything for native code. No lane, unison, callback or live-host claim.
