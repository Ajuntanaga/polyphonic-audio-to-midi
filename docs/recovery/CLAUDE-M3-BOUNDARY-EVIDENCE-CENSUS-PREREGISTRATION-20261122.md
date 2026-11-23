# Pre-registration: boundary-evidence census at the end of rapid-mute runs

Claude, 2026-11-22. Saved data only: the two pinned v5 traces and the published restart-evidence census JSON. No audio, model run, job, native edit or promotion. Script
`CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py` (sha256 prefix `a0c391e41895`). This note and the script are committed and pushed before the one real run; the run refuses to overwrite its output.

## Question

At the end of a rapid-mute run, does the saved per-pitch evidence separate the 23 labels that are re-struck there from the 224 sustained CURRENT tails that a run also truncates?

This asks for separation of continuous evidence, threshold-free (a rank statistic). It does not propose a cue, a hold, a debounce or a restart machine, and nothing here is a candidate for promotion.

## Why this check, and a refinement of my erratum

The restart-evidence census (`CLAUDE-M3-RESTART-EVIDENCE-CENSUS-RESULT-20261122.md`) found no saved causal cue that restarts the re-struck labels without restarting the sustained tails. Its erratum
(`CLAUDE-M3-RESTART-EVIDENCE-CENSUS-ERRATUM-20261122.md`) showed that decisions of quiet code 5 (`rapid_mute_ratio`, the code that marks a run) carry no per-pitch evidence: 10,949 decisions, none with energy or onset observed.

I then wrote that per-pitch evidence exists only before a run and after it. The class-blind geometry of the runs shows that statement was too broad. `rm.read_quiet` gives the quiet code of the last decision of each 512-sample callback, and
`rm.marked_runs` marks the callback that FOLLOWS a code-5 decision, so the marked interval starts one callback after the decision that gated it. Counts on the ordinary recording (127 runs, no class information used):

| Fact | Count |
| --- | --- |
| Gating decision at run start − 1 is code 5 | 127 of 127 |
| Last decision of a run (run end − 1) is never code 5 (by construction); its code | 0 in 101 runs, 2 in 26 |
| Decisions inside runs, by quiet code | 0: 447, 2: 122, 5: 10,303 |
| Evaluated decisions inside runs; of them inside the last 512 samples of their run | 569; 564 |
| Run length in samples | min 512, median 5,632, max 7,168 |

Code 0 carries energy and onset evidence; code 2 carries energy only (the observation-only floor re-entry capture). So the last callback of every ordinary run holds evaluated decisions, and the restart census could not use them
because its restart machine required support at or after the run end and outside every run. Extended-middle (6 runs, no positives): in-run codes {2: 10, 4: 17, 5: 808}; runs end on code 2 (2), code 4 (3, not evaluated) and the horizon (1).
All 23 positive labels begin inside the last callback of a run (16, 0.27 to 7.07 ms before the run end) or at most 25 ms after it (7, 0.26 to 22.49 ms after), none later. That is where this census looks.

## What I have seen and what I have not

Seen before this note: the restart census JSON (restart times by cue, classes, positive labels), its POST HOC and cross-check results, the availability tally by quiet code, the class-blind run geometry above, the trace header and field list,
and the detector source for the energy and onset fields (`fund_energy` is the fundamental cell's fast energy, `score_energy` the harmonic-weighted sum; both are set only when the spectrum was evaluated).
Seen while building the script: the first selftest output, which prints counts and gate results only (pairs: 23 positive, 224 primary negative, 16 secondary negative on ordinary; 9 negative on extended-middle; the pin, run-count, census-span,
positive-label and plain-scan-equality gates all true on the real traces). It also showed three faults in my own test code, fixed before anything else: a wrong hand value in the operating-point unit test, a synthetic generator that
produced spans ending before their run, and a gate that counted a zero-valued entry as a problem. The gate equality compares feature values computed in memory but never prints them.
Seen after the odds were frozen, from the counts-only `--dry` run (class-level counts, no feature value, no score): ordinary primary pairs, **positive (23)**: 23 have an evaluated decision in the window, 18 an onset-observed decision, 23 a pre reference,
0 end their span inside the run, 22 have a full 25 ms window; **negative (224)**: 224 evaluated, 141 onset-observed, 224 with a pre reference, 0 ending inside the run, 215 with a full window. Extended-middle **negatives (9)**: 3 with an evaluated decision,
0 onset-observed, 9 with a pre reference, 1 whose span ends inside the run, 8 with a full window. Three consequences, written here before the run and not tuned:

- F1 (onset) has a value for at most 18 of the 23 positives (78%), below the 80% coverage condition, so F1 cannot meet the separating rule as written. It stays in the report (its AUC is predicted in P2); the rule is not changed. The gap is what the evidence enum predicts: a code-2 decision carries energy but no onset.
- P7 (F2 defined for at least 80% of the positives) is settled by these counts: F2 needs an evaluated decision and a pre reference, and all 23 positives have both.
- P9 holds by construction (provided the ordinary sensitivity-0.8 operating point of F2 exists): F2 is missing for at least 6 of the 9 extended-middle negatives (no evaluated decision) and a missing value ranks lowest, so at least 6 of 9 sit below any finite threshold.

So the script scores all 12 predictions as registered (odds unchanged, frozen before these counts) and also reports hits and the Brier sum over the 10 that the dry run did not settle (`SETTLED_BY_DRY_RUN` = P7 and P9), so the headline is not flattered by them.
Not seen: any F1 to F4, N1, N2 or Part B value by class, any class-versus-feature number.
Both recordings are design data (no held-out data), so any positive finding is a lead only.

## Design

**Run and span.** A run is a maximal marked interval from `rm.marked_runs` (127 ordinary, 6 extended-middle). A truncated span is a CURRENT span that a run starts inside (245 ordinary, 9 extended-middle), as in the census. Positive labels are
the census JSON's `positive_labels` (23 labels in 21 spans, ordinary); every other truncated span is negative (224 ordinary, 9 extended-middle).

**Pairs (span, run).**

- Positive: each positive label, with the last run starting at or before the label's start; the run must start strictly inside the label's positive span.
- Negative, primary: each negative span with its first run (the one that defines the cut; asserted equal to the census `cut` and `run_end`). 224 pairs.
- Negative, secondary: every later run that starts inside a negative span (16 ordinary). Used only for a robustness AUC.
- Extended-middle's 9 negative pairs are scored against ordinary-derived thresholds only (descriptive).

**Window.** The decisions with sample in [run start, min(run end + 2400, span end, next run start)); 2400 samples is 25 ms at 96 kHz, the frozen label budget's present-time limit and the same 25 ms as the restart census.
Decisions lie on the grid sample ≡ 63 mod 64.

**Pre reference.** The last decision in [span start, run start) whose record for the pitch has `energy_observed = 1`. The gating decision is code 5 (no evidence), so this is normally the last evaluated decision before the code-5 episode.

**Scores** (larger means re-attack; fixed here before any value is seen). A missing value ranks lowest ("a missing value cannot restart anything"). Ratios: a/b when b > 0; +inf when b ≤ 0 and a > 0; 1 when both are 0.

| Score | Definition |
| --- | --- |
| F1 onset | Largest detector `onset` over window decisions with `onset_observed = 1`; missing if none. |
| F2 rise vs pre | Largest `fund_energy` over window decisions with `energy_observed = 1`, divided by the pre reference; missing if no pre reference or no such decision. |
| F3 rise in window | Largest ratio of `fund_energy` to its own running minimum, over the same decisions; missing if none. |
| F4 global control | Largest ratio of the global fast `input_power` to its running minimum since the run start, over every window decision (code 5 included). Pitch-agnostic. |
| N1, N2 nuisance | Run length in samples; window length in samples. Descriptive: what geometry alone would give. Never in the verdict. |

**Statistics.** AUC with ties counted half. Verdict interval: run-clustered bootstrap (resample runs with replacement; pairs follow their run), seed 20261122, 2,000 resamples, 2.5th and 97.5th percentiles. Secondary: span-clustered bootstrap.
Paired difference between the best pitch-specific AUC and F4's, same replicates. Second condition (below): the AUC and its own run-clustered bootstrap (seed 20261123) on the pairs whose full 25 ms window exists, in both classes.
Reported, not in the verdict: specificity at sensitivities 0.9, 0.8, 0.7 and 0.5 (optimistic: thresholds are read off the same data), quantiles by class, the AUC over all negative events (primary plus secondary), and the AUC within runs that hold both a positive and a negative pair.

**Part B (descriptive, no threshold).** A proxy for Codex's hypothesis (c) in `CODEX-M3-RESTART-CALLBACK-PATH-20261122.md`, that the diagnostic release removes the last active candidate and the reset then clears all evidence. For each run, over its code-5 decisions in
[run start − 64, run end): how many candidates are CURRENT-active, the minimum of that count, and the notes that are the only active one at some such decision (a "sole-owner moment"). Compared for the five labels the native joint reset lost whole
(42, 70, 200, 306, 364 by label index, Codex run 45075475603) against the other 18 positive labels, the 224 negative pairs and the base rate over all 127 runs. The trace's `active` flag is a decision snapshot, so this can be consistent with (c) but cannot confirm it.

## Identity gates (any failure aborts the run before anything is written)

1. Both traces hash to their pins (SHA-256 of the decompressed stream, checked after the single pass).
2. Run counts equal the census JSON's (127, 6).
3. Truncated spans equal the census JSON's (pitch, span, cut, run end, class), and the positive labels equal its `positive_labels`.
4. Every positive label has a run inside its positive span, every negative cut is a run, no label sits in two positive spans, every window is non-empty; the five whole-lost labels are all among the positives.
5. The gating decision before every run is code 5; the last decision of every run is not (a run clipped at the recording's horizon is exempt: one on extended-middle; the second selftest showed that gate false there before I added the exemption).
6. No code-5 decision observes energy (the tally, re-checked on this pass).
7. A plain linear scan of every decision reproduces the bisection-based selections and features on every primary pair and an even sample of 60 secondary pairs.
8. 26 synthetic unit checks (hand-computed values, window cuts, ratio conventions, AUC, bootstrap determinism, the rule below, odds count).

## Reading rule

A pitch-specific score (F1, F2, F3) **separates** only if both hold:

- primary pairs: AUC ≥ 0.75, run-cluster lower bound ≥ 0.60, and a value for at least 80% of the positive pairs;
- the pairs whose full 25 ms window exists (both classes): AUC ≥ 0.75, run-cluster lower bound ≥ 0.60, and at least 15 positive pairs.

The second condition exists because a negative whose span ends early has a short or empty window and would rank at the bottom for a reason that has nothing to do with the evidence; I added it while designing, before any value was seen.
As the dry-run counts above show, F1 cannot reach the 80% coverage condition (18 of 23); that is the rule as written, not something to fix after the run.
**Strong** is a separating score with primary AUC ≥ 0.90 and lower bound ≥ 0.75.

| Outcome | Reading |
| --- | --- |
| No score separates | Saved boundary evidence does not separate re-struck notes from sustained tails; an in-run observation or a faster onset feature would be needed (native lane, Codex's call, not requested). |
| A score separates and the paired difference to F4 has a positive lower bound | A lead on design data, pitch-specific. Any follow-up needs its own registration on data this analysis has not touched. |
| A score separates but the paired difference to F4 has no positive lower bound | Not shown to be pitch-specific: a global energy rise restarts the negatives too. |
| N1 or N2 passes the primary rule | Geometry alone separates; a pitch score is informative only to the extent it beats it. Added to the reading. |

Everything else (operating points, quantiles, matched AUC, Part B) is descriptive. Anything beyond this list is post hoc and labeled so.

## Predictions (written before any value was computed for display)

| # | Statement | Odds |
| ---: | --- | ---: |
| P1 | F2 has primary AUC ≥ 0.75 | 50% |
| P2 | F1 has primary AUC ≥ 0.75 | 40% |
| P3 | F3 has primary AUC ≥ 0.75 | 55% |
| P4 | F4 has primary AUC < 0.65 | 50% |
| P5 | At least one of F1 to F3 separates (both conditions above) | 40% |
| P6 | None of F1 to F3 is strong | 80% |
| P7 | F2 is defined for at least 80% of the 23 positive pairs | 85% |
| P8 | The best pitch-specific AUC exceeds F4's by at least 0.10 | 50% |
| P9 | At least 5 of the 9 extended-middle negative pairs fall below the ordinary sensitivity-0.8 threshold of F2 | 60% |
| P10 | At least 4 of the 5 whole-lost labels have a sole-owner moment | 40% |
| P11 | The sole-owner share of the 5 whole-lost labels exceeds that of the other 18 positives | 50% |
| P12 | F2's AUC over all negative events is within 0.05 of its primary AUC | 70% |

Scoring: Brier sum Σ(odds − outcome)² over the 12 (a flat 50% scores 3.00); the result note reports hits, the sum and each miss, and the same two numbers over the 10 predictions not settled by the dry-run counts (all but P7 and P9; a flat 50% scores 2.50 there).

## What this cannot show

- Two recordings, both already seen: a separating result is a lead, a null result is a null on these data only. 23 positive pairs in 21 spans (and 5 whole-lost labels) make every interval wide.
- Most positive labels begin before the run's last callback ends, so only the first 0 to 7 ms of an attack can be in the evaluated decisions of that callback; the attack's own in-run evidence is not saved (code 5 decisions carry none).
- AUC is separation of a continuous score, not a deployable cue: no threshold, hold, debounce or latency is evaluated, and the operating points are optimistic. Nothing here touches the frozen label budget.
- The window's maximum statistics grow with the number of evaluated decisions; the full-window condition and N2 are there to expose that, not to remove it.

## Exclusions

No job, no native or `tools/` edit, no change to Codex's frozen gates or the label budget, no promotion, no rerun of the rejected joint-reset screen, no download, no re-mount of the NTFS volume. The raw-cell sidecar that Codex offered is Codex's call; I have not requested it.

## How it runs

`python3 -P -E CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.py --selftest`, then `--dry` (counts only, writes nothing), then, after this commit, `--run` once (writes `CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-20261122.json`, refuses to overwrite).
If the run fails before writing, I fix plumbing only and rerun, and say so; if it completes, the JSON is final and the result note is `CLAUDE-M3-BOUNDARY-EVIDENCE-CENSUS-RESULT-20261122.md`.
