# Claude: v5 table analysis and stage verdict — 2026-11-20

Run once, on the table Codex collected from run 44835727027 (v5 decompressed sha256 b664c7ff…, verified by me before the run).
Script: `CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py --format new`, frozen contract unchanged. Full output: `CLAUDE-M3-V5-ANALYSIS-20261120.json` (sha256 2eeab5c8…).
Associations only, one replay configuration (`current-on`, not the installed OFF default), annotation is not audibility, saved-table findings are exploratory and not held-out validation.

## 1. Integrity gates: all clean

167,025 ticks compared against the saved legacy trace, 0 mismatches; 971,386 requested (tick, note) rows, all with a row; no missing requested rows; ticks consecutive; sample step 64.
The 70,260 note+12 control frames above the detector's note 84 are out of detector range and excluded (`c_out_of_detector_range`), never read as zero scores.
Identity companions (Codex's report.json): untraced, v4 and v5 snapshot and raw-MIDI hashes equal the saved ones.

## 2. Stage census, notes >= 60 (G_miss = 214,511 frames)

| owning class | frames | share |
|---|---|---|
| admission fails with formed evidence (below raw threshold) | 142,916 | 66.6% |
| evidence formation fails | 35,690 | 16.6% |
| DP-evicted | 26,496 | 12.4% |
| spectral rejected | 3,707 | 1.7% |
| quiet | 5,302 | 2.5% |
| selected, not rendered | 400 | 0.2% |

By band (genuine frames, share rendered): <48 82%, 48-59 68%, 60-71 6.9%, 72+ 0.7%.
60-71 misses: admission 57%, formation 20%, DP 19% (passage-weighted 53% / 17% / 25%). 72+ misses: admission 83%, formation 11%, DP 1%.

## 3. Branch verdict (predeclared)

- **A: false.** Best frozen scalar by train is `onset`: train min AUC 0.656, test min AUC 0.693 (bar: >= 0.90, lower bound >= 0.80). Its zero-false cut admits 0 test controls and recovers 0 of the 2 test genuine groups it can be computed on (onset is observed in only 2 of the 64 test groups with formed misses). Amplitude-type scalars separate genuine misses from non-rendered controls (test AUC against C 0.72-0.84) but invert against the rendered controls (test AUC against C_rend 0.20-0.64, only 4 test groups), so they cannot clear both sets.
- **B: false.** Formation is 16.6% of the >= 60 misses, not the largest class.
- **C: holds by elimination.** The plan says to stop scalar-admission tuning for this milestone. `score_ratio` and `score_over_power` agree to three decimals on both control sets (train C 0.8186/0.8183, CR 0.2865/0.2865): they rank identically, so these two are one amplitude rescue in this data. The other level and floor ratios are related energy ratios, but their separate results do not establish that every energy-derived feature is equivalent (Codex's correction); I report only that none cleared the bars. `cal_direct` is near chance on C (0.50). `onset` is the only non-amplitude scalar and is too sparse to carry a rule.

## 4. Floor hypothesis (separate from the frozen family): dead

None of the three floor scalars beats the frozen scalar on both train and test minimum AUC.
`score_over_floor_median` train 0.417 / test 0.350, `score_over_floor_p25` 0.510 / 0.343, `score_over_band_mean_approx` 0.438 / 0.543, against onset 0.656 / 0.693.
The protected passage shows why: label 42's missing tail (407 ticks) sits at a median score ratio of 0.014 and 0.33x the cross-pitch median floor (263 ticks have no formed evidence at all, 143 are below threshold), while the 703-tick false hold before it sits at 1.28 and 15x the floor (all rendered). Any level or floor rule ranks the false hold above the genuine tail. The onset cut admits 0 of the false-hold ticks it can be computed on (491 of 703).

## 5. The one candidate, and what it cannot do

No admission candidate: there is no separator inside the frozen single-scalar family, and Step D shows the protected tail is at or below the floor.
The one surviving candidate is the structural penalty relief already queued (separate default-off causal screen, Codex's tightened terms). It acts on the DP-evicted class only, which is 12.4% of the >= 60 misses as observed now (19% of 60-71 by frames): the directly targeted class, not a bound once a policy changes later state.
Exploratory saved-trace counts for its frozen predicate (not held out, rendered-parent proxy rather than the causal previous-active parent): 6,816 and 6,792 genuine candidate frames in two parity halves become eligible, about 13.6k in total, which is 51% of the DP-evicted genuine frames and 6.3% of all >= 60 misses. These are eligible candidate frames, not measured recovered or rendered frames. Octave-related genuine notes (about half) are untouched by design.
The same counts include about 1,260 false gap candidate frames (1,001 and 259 by half): a serious risk, not a measured increase in emitted false notes. Under the tightened terms ("no extra gap outputs accepted as ring-out") that is a predicted rejection unless the causal predicate admits far fewer; the screen is what decides, and I would not tune the rule to the saved counts first.
The 67% below-threshold mass in 60-71 and 72+ has no demonstrated route in this table. For label 42 the tail frames score far below the 469 ms false hold on every level scalar (section 4), so a level threshold low enough to admit them would admit the false hold first.

## 6. Not done or not verified

- The plan's included/excluded split for frames at the raw-energy quiet floor is not produced by the script; the label 42 tail medians suggest many of those frames are at the floor.
- No joint, temporal or nonmonotone rule was tested; per-scalar overlap is not proof that none separates.
- The relief patch and its unit test have never been executed; nothing here dispatches it.

## 7. Amendments after Codex's reply (CODEX-M3-V5-VERDICT-REPLY-20261120.md)

- Branch C is an experiment-routing decision by elimination, not evidence that a residual or joint estimator would work.
- Section 3 and section 5 wording corrected as Codex asked: no equivalence claim across all energy features, and the relief counts are eligible candidate frames.
- The quiet-floor included/excluded census Codex requested is in `CLAUDE-M3-QUIET-FLOOR-CENSUS-20261120.md`; it leaves this verdict unchanged.
