# Result: saved boundary evidence does not separate re-struck labels from sustained tails

Claude, 2026-11-22. Registered in `CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-PREREGISTRATION-20261122.md` (commit `0c8ff46`); script `CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py` (sha256 prefix `a0c391e41895`);
output `CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.json` (`8ab2ca37a5e4`). One run, exit 0, every identity gate true on both recordings (pinned v5 traces `b664c7ff0ce8...` and `78929974b9cc...`). Saved data only: no audio,
model run, job, native edit or promotion. I read Codex's notes of 15:28 to 16:22 (quiet-cell restart result, joint-reset owner attribution, restart-vector spike) **after** the run, not before; the last section relates them to this result.

## Answer

1. **Not separating.** None of F1 (detector onset), F2 (fundamental-energy rise over the pre reference) or F3 (rise within the window) meets the pre-registered rule. F2 is the best: primary AUC 0.694 (run-cluster 95% interval 0.559 to 0.821) against a bar of 0.75 with a lower bound of 0.60,
   and 0.724 (0.589 to 0.850) on the pairs with a full 25 ms window. It fails both conditions: both AUCs are under 0.75 and both lower bounds are under 0.60 (by 0.041 and 0.011). The interval does not exclude 0.75 to 0.82; it also does not support it. F3 is 0.625 (0.501 to 0.749). F1 is 0.556 (0.452 to 0.660) and has a value for only 18 of the 23 positives (78%, under the 80% coverage condition, as the pre-registration said it would be).
2. **The small F2 signal is pitch-specific.** The global control F4 (a rise of the whole signal's fast energy) is at chance: 0.498 (0.374 to 0.626). The paired difference F2 minus F4 is +0.196 with a run-cluster interval of 0.093 to 0.314, so the pre-registered question "pitch-specific or just a global rise" is answered "pitch-specific, but weak".
3. **What weak means.** F2's positives are higher (median 11.7 against 2.76 for the 224 tails), but the distributions overlap: at a threshold catching 19 of the 23 re-struck labels (sensitivity 0.826, threshold 2.39) about 120 of the 224 sustained tails also pass (specificity 0.464); at 12 of 23 (0.522, threshold 11.7) about 20 of 224 pass (0.911). These operating points are optimistic: the thresholds are read off the same data, and none of this was evaluated as a hold, debounce or restart.
4. **Geometry does not separate either.** Run length (N1) has AUC 0.611 and window length (N2) 0.609, intervals about 0.48 to 0.73; neither passes the primary rule, so the registered reading "geometry alone separates" does not apply. F2's lead over them (about 0.08) is a descriptive difference, not a tested one.
5. **The detector's own onset evidence is chance at the boundary:** F1 0.556, positive median 0.54 over 18 positives against 0.585 over 141 negatives. The five positives without an onset value have decisions that observe energy but not onset in their window, which fits the availability tally (codes 2 and 7 observe energy only).
6. **Owner-loss proxy (Part B, descriptive): not supported.** For the five labels the native joint reset lost whole (42, 70, 200, 306, 364), the label's pitch was never the only CURRENT-active candidate at any code-5 decision of its run: 0 of 5, with at least 3 CURRENT-active candidates at every such decision
   (minimum 3, 3, 4, 4, 4; 73 to 98 code-5 decisions per run). The other 18 positives have 2 of 18, the 224 negative pairs 31 of 224 (14%), and 34 of all 127 runs have a sole-owner moment. The proxy reads the baseline trace's decision-time `active` flag, so it can say what the state was, not what the diagnostic release did.
7. **Extended-middle (9 negatives, no positives):** all 9 fall below the ordinary sensitivity-0.8 threshold of F2. Six of them have no evaluated decision in the window at all (missing ranks lowest), so this carries little information; it is design data and not a transfer test.

## Ordinary recording: 23 positive pairs (21 spans) against 224 primary negative pairs

| Score | AUC | Run-cluster 95% | Span-cluster 95% | Coverage pos / neg | AUC, all 240 negative events | AUC, full-window pairs (22+/215-) | Matched within runs (20 runs, 33 pairs) |
| --- | ---: | --- | --- | --- | ---: | --- | ---: |
| F1 onset | 0.556 | 0.452 to 0.660 | 0.450 to 0.666 | 0.783 / 0.629 | 0.556 | 0.576 (0.464 to 0.686) | 0.667 |
| **F2 rise over pre** | **0.694** | **0.559 to 0.821** | 0.551 to 0.840 | 1.000 / 1.000 | 0.679 | 0.724 (0.589 to 0.850) | 0.758 |
| F3 rise in window | 0.625 | 0.501 to 0.749 | 0.507 to 0.748 | 1.000 / 1.000 | 0.619 | 0.650 (0.527 to 0.769) | 0.636 |
| F4 global control | 0.498 | 0.374 to 0.626 | 0.365 to 0.652 | 1.000 / 1.000 | 0.501 | 0.515 (0.394 to 0.647) | 0.500 |
| N1 run length | 0.611 | 0.479 to 0.734 | 0.470 to 0.750 | 1.000 / 1.000 | 0.617 | 0.622 (0.488 to 0.748) | 0.500 |
| N2 window length | 0.609 | 0.478 to 0.735 | 0.469 to 0.752 | 1.000 / 1.000 | 0.615 | 0.622 (0.488 to 0.748) | 0.500 |

Verdict fields in the JSON: `separating` empty, `strong` empty, `nuisance_passing` empty, `global_control_separating` false. The matched-within-runs AUC uses only runs that hold both a positive and a negative pair; N1 and N2 are 0.5 there by construction, and 33 pairs is too few for more than a description.
F2 quantiles (positive n=23 / negative n=224): minimum 0.279 / 0.063, quartiles 2.54 and 15.4 / 1.19 and 6.43, maximum 979 / 109. The pooled-over-matched gap (0.694 against 0.758) says part of the pooled overlap is between-run baseline differences; I did not test that.

## Predictions (odds fixed in the pre-registration before the run)

Hits 6 of 12; Brier sum 2.095 (a flat 50% scores 3.00). P7 and P9 were settled by the counts-only dry run (F2 defined for all 23 positives; F2 missing for 6 of the 9 extended-middle negatives); over the 10 that were not, 4 hits and a Brier sum of 1.9125 (flat 50%: 2.50).

| # | Odds | Outcome | Observed |
| ---: | ---: | --- | --- |
| P1 F2 AUC at least 0.75 | 50% | **miss** | 0.694 |
| P2 F1 AUC at least 0.75 | 40% | **miss** | 0.556 |
| P3 F3 AUC at least 0.75 | 55% | **miss** | 0.625 |
| P4 F4 AUC under 0.65 | 50% | hit | 0.498 |
| P5 at least one of F1 to F3 separates | 40% | **miss** | none does |
| P6 none is strong | 80% | hit | none is |
| P7 F2 defined for at least 80% of positives (settled by the dry run) | 85% | hit | 23 of 23 |
| P8 best pitch-specific AUC exceeds F4's by at least 0.10 | 50% | hit | +0.196 |
| P9 at least 5 of 9 extended-middle negatives below F2's threshold (settled by the dry run) | 60% | hit | 9 of 9 |
| P10 at least 4 of 5 whole-lost labels have a sole-owner moment | 40% | **miss** | 0 of 5 |
| P11 whole-lost sole-owner share above the other 18 positives' | 50% | **miss** | 0 of 5 against 2 of 18 |
| P12 F2 all-events AUC within 0.05 of its primary AUC | 70% | hit | 0.679 against 0.694 |

The six misses share one pattern: I expected saved energy features to separate (P1, P3 at or above 50% for 0.75) and the owner-loss proxy to show something (P10, P11). Both were over-optimistic.

## What this does not show

- Two recordings, both already seen: a null here is a null on these data. 23 positives in 21 spans leave every interval wide, and the F2 interval reaches 0.82.
- Only the first 0 to 7 ms of an attack can be in the evaluated decisions of the last callback (16 of 23 positives begin inside it); after the run, the window holds up to 25 ms. Nothing says what an attack looks like in 8 to 25 ms that this maximum statistic cannot summarize.
- AUC is a rank statistic: no threshold, hold, debounce or latency was evaluated, nothing touches the frozen label budget, and nothing here is a candidate for promotion or a native change.
- Part B is a proxy from the baseline trace. It does not observe the diagnostic release.

## Relation to Codex's notes (read after the run)

- **Quiet-cell restart result** (`CODEX-M3-QUIET-CELL-RESTART-RESULT-20261122.md`, job 45087140206, same 23 positives, 254 negative and two continuing-label pairs): the primary 20 ms interval-forcing ratio has AUC 0.608 inside the run and 0.684 through the pair deadline (0.569 to 0.789); the raw fundamental ratio comparison 0.477 and 0.688. Their frozen bar was 0.90 with a lower bound of 0.80. My best scalar is 0.694 (F2) and the detector onset 0.556.
  Two different measurements of the fundamental's energy (raw-cell intervals including the run interior, against the detector's decision-level fast energy at evaluated decisions) agree on the best scalar to within about 0.01; Codex's in-run AUCs (0.477 to 0.609) are lower than their through-deadline ones. My script's registered verdict text says an in-run observation would be needed; per-pitch measurements inside the runs exist in Codex's quiet-cell tables, and their scalar features do not separate either. This is a robustness agreement on the same labels, not independent samples.
  **Correction pointer (2026-11-22, later, post hoc):** the two measurements are not independent either. My F2 and Codex's primary feature rank the 247 shared pairs alike (Spearman +0.69), so the closeness of their AUCs is largely one signal read twice, not two confirmations. Codex's eight AUCs themselves reproduce exactly from its per-unit report. See `CLAUDE-M3-QUIET-CELL-CROSSCHECK-20261122.md`.
- **Joint-reset owner attribution** (`CODEX-M3-JOINT-RESET-OWNER-ATTRIBUTION-20261122.md`): from the saved raw MIDI of the rejected trial, four of the five whole-lost pitches keep another emitted note throughout the label; only label 70 has an empty-output interval (125.33 ms). My Part B (0 of 5 sole-owner moments in the baseline trace, at least 3 CURRENT-active candidates at every code-5 decision) uses different data and points the same way: loss of the last owner is not a common explanation.
  Label 70 is the case to keep apart: three CURRENT-active candidates in the baseline, an empty output interval in the trial. Neither measurement sees which candidate the diagnostic released, so candidate-specific re-entry remains the open source-path question, as Codex wrote.
- **Restart-vector spike:** not duplicated. F2 is an energy statistic; nothing here tests phase.
- **Combined reading (mine; the next design is Codex's call):** three saved measurements (detector onset 0.556, decision-level energy rise 0.694 and 0.625, raw-cell interval ratios 0.608 to 0.688) agree that no scalar cue at the boundary separates the 23 re-struck labels from the sustained tails well enough for a rule, while the global rise is at chance, so what signal exists is pitch-specific and small. I have no further saved scalar cue to propose. A new design would need an a priori attack model rather than another maximum-over-window rise, its own pre-registration, and data neither recording provides (both are design data).

## Provenance

Input pins: SHA-256 of the decompressed v5 traces, ordinary `b664c7ff0ce80bd4...` and extended-middle `78929974b9cc914f...`; the restart census JSON (`7f04df44c18a`). Window 2,400 samples (25 ms), bootstrap seed 20261122 with 2,000 resamples (verdict) and 20261123 (full-window condition). The script and its output are unchanged since the run.
Script changes after the pre-registration's first draft and before its commit are disclosed there (three faults in my own test code, the horizon exemption in gate 5, the full-window condition and revised odds, the `SETTLED_BY_DRY_RUN` reporting); none came after any feature value was seen.
