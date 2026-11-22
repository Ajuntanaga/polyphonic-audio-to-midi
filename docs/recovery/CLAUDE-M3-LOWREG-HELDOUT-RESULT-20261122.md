# Held-out check of the low-register re-render gates: result

Claude, 2026-11-22. Pre-registration: `CLAUDE-M3-LOWREG-HELDOUT-PREREGISTRATION-20261122.md` (commit `3afec62`, pushed before the trace was opened). Script run once, unchanged: `CLAUDE-M3-LOWREG-HELDOUT-20261122.py`. Saved trace and CURRENT's saved spans only; no audio, model run, job or native edit; nothing promoted.

## Answer

**Verdict on the lead (`o_band_score <= 0.108358`): uninformative.** It fired 0 times on extended-middle, below the 20-fire floor registered for any reading. The held-out check therefore neither supports nor contradicts it. Its safety here is vacuous: a gate that never fires cannot cut a note.

**What the check did show, outside the registered reading:**

- The **ungated rule is unsafe on this corpus**. B(1.5) fires 10,629 times and removes 52 from the two labels it hits: coverage 97.49% to 89.96% (-7.53 points), wrong-pitch samples +156,223, two labels losing present time (up to 1,550 ms on one; the loss audit's `share_of_label_lost` is 0.245), strict gate False. Zero of its fires are good or swap; 9,551 are harm (the removed pitch carries a label and the added pitch carries none) and 1,078 are null.
- **No gate here is shown to help.** The three cheaper gates are strict-safe, but only because they barely fire: `exclude rel=octave` fires 59 times and `<= 0.174142` fires 13, and every one is a null fire that changes no score. Coverage gain is 0.000 for all four gates that fire at most 59 times.
- The `o_release >= 12` gate (5,587 fires) is the only mid-sized gate, and it is unsafe too: -4.01 points, wrong +83,136, two labels losing (up to 858 ms).

## Registered predictions, scored

| Id | Claim | Odds | Observed | Result |
|---|---|---:|---|---|
| X0 | An empty edit reproduces CURRENT's saved score | 95% | `rebuilt_equals_saved` true (2,021,510 present, 1,516,739 exact-set, 528,259 wrong, 183,006 gap) | hit |
| X1 | Pool has at least 100 fires | 65% | 10,629 | hit |
| X2 | Ungated loses at least one label | 60% | 2 labels | hit |
| X3 | Lead loses no label | 60% | 0 labels losing, with 0 fires | hit, **vacuous** |
| X4 | Lead lowers wrong-pitch samples | 75% | delta 0 | **miss** |
| X5 | Lead's coverage gain is non-negative | 80% | +0.000, with 0 fires | hit, **vacuous** |
| X6 | Octave fires are at least 50% of pool | 70% | 10,570 of 10,629 = 99.4% (the other 59 are fifth) | hit |

Four clean hits (X0, X1, X2, X6), two vacuous holds (X3, X5: they held only because the lead never fires, and I do not count them as support), one miss (X4). The miss is the shape of the result: I expected the lead to fire on something and it fired on nothing.

## The six-row table

Saved CURRENT: 97.4879% coverage, 1,516,739 exact-set samples, 528,259 wrong-pitch, 183,006 gap. Horizon 2,233,574 samples.

| Gate | Fires | Coverage gain (pts) | Exact-set ratio | Wrong-pitch delta | Gap delta | Labels losing | Strict gate |
|---|---:|---:|---:|---:|---:|---:|---|
| B(1.5) ungated | 10,629 | -7.531 | 0.993 | +156,223 | 0 | 2 | False |
| `o_release >= 12` | 5,587 | -4.009 | 0.999 | +83,136 | 0 | 2 | False |
| exclude `rel=octave` | 59 | 0.000 | 1.000 | 0 | 0 | 0 | True |
| `o_band_score <= 0.174142` | 13 | 0.000 | 1.000 | 0 | 0 | 0 | True |
| `o_band_score <= 0.108358` (lead) | 0 | 0.000 | 1.000 | 0 | 0 | 0 | True |
| `o_band_score <= 0.0615331` | 0 | 0.000 | 1.000 | 0 | 0 | 0 | True |

Per-label losses (ms present time): ungated label 3 -76.67 (longest run -1,296.0), label 4 -1,550.0 (-1,688.68); `o_release >= 12` label 3 -8.0 (-158.0), label 4 -858.0 (-1,590.01). Removal fires by label, ungated: label 3 251, label 4 9,300; no fire adds a pitch that any label carries (additions by label empty). All six labels have `midi_note` 52, so every removal is the correctly rendered note and every harm fire turns it into the octave above.

Pool mix: 10,629 fires, 10,570 octave and 59 fifth; voice kinds true 9,551, ghost 810, tail 268. The label lookup agrees with the trace's active-frame flag on 100% of the pool.

## Post hoc diagnostic (not registered, verdict unchanged)

`CLAUDE-M3-LOWREG-HELDOUT-DIAGNOSTIC-20261122.py` / `.json` re-reads the same trace and splits the pool by what a fire would have done.

- **Harm fires (9,551, all true voices, all octave): `o_band_score` min 0.423, 1% quantile 0.857, median 1.0.** None sits at or below any of the three ordinary thresholds, so the gate declines every harm fire. It does separate real notes from the rule's target here.
- **Null fires (1,078, ghost and tail voices): median 0.627, 25% quantile 0.328, minimum 0.150.** Only 13 (1.2%) fall at or below 0.174142, none below 0.108358. On ordinary the same cut-offs passed 5,047 / 3,365 / 1,683 fires, so the quantile thresholds are in a different place on this corpus.

So the registered lead is silent here, and the diagnostic says it is silent for a good reason (it refuses the harm fires) and for a poor one (it also refuses nearly all the null fires, so nothing is demonstrated about the fires it would accept). One reading: `o_band_score` is a safe filter on this corpus and a benefit filter on none.

## What this changes

- **Lowers my confidence in the ungated rule and in any gate that lets octave fires through on sustained held notes** (`o_release >= 12` is such a gate). On this corpus a re-render of the fundamental into its octave is harmful in every fire where a label is active.
- **Does not validate the lead.** It was chosen post hoc on ordinary and now has a clean held-out run that is uninformative. The ordinary lead's gain (+0.403 points) stays unconfirmed; its one losing label (1.3 ms) stays as measured.
- **Does not change the standing position:** the strict gate fails on ordinary for all six, nothing is selected for native code, nothing is promoted, and the installed scoreboard is unchanged.

## Limits

One recording of about 23 s, six labels all at MIDI 52, 14 saved spans. It tests safety on held notes far better than benefit: CURRENT is at 97.49%, so the largest possible gain is 2.51 points. Fires within a sustained note are strongly correlated (9,300 of 9,551 harm fires are one label), so the counts overstate independence and the ungated loss is, in effect, two note-runs. Immediate replacement is assumed (an optimistic bound). Onset confirmation, hold and minimum duration are not modelled. No lane, unison, callback or live-host claim. The gate thresholds are the ordinary corpus' quantiles and were not refit.

## Pins

- Trace: `extended-middle-current-on-512-outcome-v5.tsv.gz` from run 45062999189 (artifact 14769684640, 17,847,485 bytes, server SHA-256 `057667821a96542c583eb9e280dc0c522de7ddde3a0ac8e0cb5355f39b44fd60`; compressed trace file SHA-256 prefix `de2e2c19d53db565`; uncompressed v5 SHA-256 `78929974b9cc914f71ef3fa58759728dda93f4a53fea16af17f3217adb6ac267` from Codex's worker report). Source `15da527509b8defd9581480a08928f893ea66e8c`, worker `18a82aca1d95c1383ba8a277a6b11826b35cda48`. Snapshot SHA-256 `826fac40de309ff0838e68a7f301e146291b6197eab2493847ddee853bdf66c3`, raw MIDI SHA-256 `a52eb7d46ae0fd7345e97e5652c29a367b8bfc45bf0db4803eba304bcc8ec601`.
- Files: `CLAUDE-M3-LOWREG-HELDOUT-EXTENDED-MIDDLE-RESULT-20261122.json` (the registered run), `CLAUDE-M3-LOWREG-HELDOUT-DIAGNOSTIC-20261122.json` and `.py` (post hoc), `CLAUDE-M3-LOWREG-HELDOUT-ORDINARY-REGRESSION-20261122.json` (the script reproduces the ordinary pool of 16,822 fires and all five gate counts).
