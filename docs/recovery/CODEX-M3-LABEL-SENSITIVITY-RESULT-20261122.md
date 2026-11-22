# Known source disagreements do not explain the full rejection

The saved source-variation model from GitHub run **44966587324** remains rejected. Even granting a perfect prediction to every test example containing any of the fifteen flagged sources leaves complete pitch sets below the original 70% gate. This analysis changes neither labels nor predictions. It is separate from the newest full-gradient trial, run **44982269805**, which also remains rejected.

All 555 sources, original roles, mixture membership, saved predictions and cutoff **0.586877167224884** are retained. The eight hypothetical replacements come only from the previously recorded non-octave disagreements. The seven ambiguous octave cases receive no replacement. The plan was frozen before calculation.

| Test calculation | Complete pitch sets / 4096 | Percent | Extra / missing pitches |
|---|---:|---:|---:|
| Original measured result | 1756 | 42.87% | 2656 / 2458 |
| Hypothetical eight-source target substitution | 2012 | 49.12% | 2189 / 2040 |
| Perfect-output ceiling for eight affected sources | 2329 | 56.86% | Not a measured output |
| Perfect-output ceiling for all fifteen flagged sources | 2780 | 67.87% | Not a measured output |
| Original complete-set target | 2868 | 70.02% | Other gates also required |

The eight-source scenario affects 582 examples: 575 target sets change and 149 change size because unisons split or merge. It makes 262 examples exact and six cease to be exact. Expected unique pitches change from 10452 to 10501; found pitches change from 7994 to 8461. Those are **hypothetical scoring differences, not a detector gain or a corrected benchmark**.

The ceiling grants all affected examples a perfect output while leaving unaffected predictions fixed. Eight-source affected failures are 573, giving 1756 + 573 = 2329, still 539 sets short. The broader fifteen-source set touches 1038 examples and 1024 original failures, giving 1756 + 1024 = 2780, still 88 short. It is deliberately more generous than any label substitution and cannot be reported as achievable performance.

The original five-distinct-pitch group is further from acceptance: original 24/327 (7.34%), hypothetical 35/327 (10.70%), eight-source ceiling 109/327 (33.33%) and fifteen-source ceiling 189/327 (57.80%). TARGET is 229/327 (70.03%); even the broader ceiling is 40 complete sets short. Group membership remains the original pitch count even when a hypothetical unison changes size.

True one-component examples improve hypothetically from 570/809 exact (70.46%) to 619/809 (76.51%); misses 122 to 72 and extras 315 to 265. This shows that the disputed targets matter. It does not justify attributing the remaining failure to a particular model mechanism. Other source labels are not exhaustively verified, and these development roles have already been inspected repeatedly.

Verification: all six prediction/plan files and source metadata pins match; original role, source coverage, target and score identities reproduce. Train and calibration results are unchanged. Five synthetic tests pass, including shared-pitch ownership, newly merged unisons, already-exact affected rows and the perfect-output bound. One local saved-array calculation ran; no audio/model load, native execution, training or remote job. Full groups and per-example evidence remain in the recorded local report.

Next is an exact paired component/mixture observation on the frozen model: reuse each original crop and effective level, first reproduce the saved mixture output, then determine which missing pitches were already absent alone and which are lost only after summation. The existing sampled solo/mixed comparison has no exact crop/level pairs, so it cannot make that distinction. No refit, cutoff adjustment or next job is queued. All original acceptance gates and installed scores remain unchanged; live readiness is unverified. Claude remains paused.

Evidence: `m3-saved-label-sensitivity-20261122.json`; local full report `build/recovery/m3-label-sensitivity-20261122/report.json`; affected rows `build/recovery/m3-label-sensitivity-20261122/affected-examples.json`.
