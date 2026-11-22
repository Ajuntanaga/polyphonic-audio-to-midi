# Harmonic level suppression: held-out transfer rejected

Final result recorded 2026-11-22T01:57:14.707101+00:00. Run [44973355304](https://github.com/Ajuntanaga/m3-offload/actions/runs/44973355304) completed successfully; the research screen is **rejected**. Training passed, calibration and test failed, and continuous replay was skipped as specified. No installed output, default, source label or scoreboard changed.

The experiment zeroed only absolute RMS slots 30 and 61 in all roles. All 62 input slots, the other 60 relative coordinates, seeded network shape (14,465 parameters), setwise loss, optimizer, 80 epochs, source roles and original mixture plan were retained. Numeric floors and clipping still permit level dependence near silence; this result does not rule out all level-related mechanisms.

## Measured result

These are sustained sampled pitch sets, not tuner frame/string assignments, unique played duration or delivered MIDI. The baseline is unaugmented setwise run 44965135706. Exact means the complete expected pitch set with no extra prediction.

| Role | Five-pitch baseline → trial | Target | Current / target | Gap or headroom | Role status |
|---|---|---|---|---|---|
| train | 1818 → 1821/2529 (71.89 → 72.00%) | 1771 (≥70%) | 1821/1771 = 102.82% | headroom 50 sets | pass |
| calibration | 283 → 272/639 (44.29 → 42.57%) | 448 (≥70%) | 272/448 = 60.71% | gap 176 sets / 27.43 pp | reject |
| test | 27 → 29/327 (8.26 → 8.87%) | 229 (≥70%) | 29/229 = 12.66% | gap 200 sets / 61.13 pp | reject |

| Role | Expected pitches found | Extra pitches | Missing pitches | Complete sets |
|---|---|---|---|---|
| train | 43827 → 43890 | 439 → 443 | 1871 → 1808 | 14597 → 14587/16384 (89.09 → 89.03%) |
| calibration | 10673 → 10645 | 687 → 675 | 880 → 908 | 2997 → 3004/4096 (73.17 → 73.34%) |
| test | 8000 → 7965 | 2705 → 2756 | 2452 → 2487 | 1749 → 1733/4096 (42.70 → 42.31%) |

| Role | Complete 1-pitch | Complete 2-pitch | Complete 3-pitch | Complete 4-pitch | Complete 5-pitch |
|---|---|---|---|---|---|
| train | 3115 → 3112/3132 (99.36%) | 3084 → 3075/3220 (95.50%) | 2954 → 2952/3251 (90.80%) | 2806 → 2807/3432 (81.79%) | 1818 → 1821/2529 (72.00%) |
| calibration | 691 → 697/753 (92.56%) | 652 → 652/777 (83.91%) | 625 → 624/837 (74.55%) | 541 → 554/885 (62.60%) | 283 → 272/639 (42.57%) |
| test | 607 → 597/869 (68.70%) | 441 → 452/950 (47.58%) | 324 → 294/932 (31.55%) | 145 → 156/813 (19.19%) | 27 → 29/327 (8.87%) |

Training single-pitch sets regress from 3115 to 3112/3132 despite misses falling from 5 to 2, because extras rise from 13 to 19. Test single-pitch exact sets fall from 607 to 597/869 with the same 125 misses and extras rising from 355 to 370. The two additional exact five-pitch test sets do not establish a general improvement: test correct pitches fall by 35, extras rise by 51 and complete sets fall by 16. Calibration has 12 fewer extras but 28 fewer correct pitches; its five-pitch exact sets fall by 11.

Training precision is 99.0007%, recall 96.0436%; calibration precision 94.0371% (below 95%), recall 92.1406%; test precision 74.2934% (below 95%), recall 76.2055% (below 80%). Calibration 4/5-pitch and test overall and 3/4/5-pitch complete-set gates also fail. Silence extras remain zero on 820/205/205 train/calibration/test examples. The original gates were applied without cutoff tuning.

## Provenance and verification

- Source `706e9bca1a71dba803a57ea402a0a1b6cdfe4f8b`; worker `2aa201a38d8e5a31eae925834fb8b87041776811`.
- Source CI 44973305584 passed. All 92 GitHub synthetic checks passed with zero skips. Local checks previously passed 16 with 5 Torch-dependent checks deferred to GitHub.
- Exactly one 80-epoch fit (105.326 seconds); final loss 0.448235352. Cutoff 0.47096869349479675 selected on training only and model persisted before held-out scoring.
- Train/calibration/test retain 200/200/155 source excerpts, all 555 original labels, no cross-role original overlap and no source-consistency filtering. These roles are not independent instruments/sessions or a newly blind research evaluation.
- Original decoded training-plan SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` matches the pinned plan. Model SHA256 `1b4981fe23820eef91d5a39cb6f52daf3e3571d8511c846fa6af462468a24695`.
- Small artifact 14734267762, 26694 bytes, collected once at 2026-11-22T01:54:47.973875+00:00; archive SHA256 `ee13e6075c3db83a7638e023c4a5f5cf3f65cedc6839ee612080da37497cd3a1` equals the server digest.
- Local report `build/github-results/harmonic-level-suppression-44973355304/artifact/harmonic-level-suppression-result/report/report.json`; SHA256 `63e2eea7a165180387170b270872113bc78eaa8035d2cede53ad71f4dc7c9f92`.
- Bulk evidence artifact 14734536990 remains remote (6,922,489 bytes; expires 2026-12-06T01:54:05Z). No model or prediction download.
- No new continuous corpus, native allocation/deadline, string-lane/unison, external host or hardware result. Earlier protection checks remain earlier checks.

## Decision and next step

Suppressing the explicit absolute-level inputs did not fix source transfer and is not accepted. This supports rejecting this frozen ablation, not a unique explanation for the remaining errors.

Choose a distinct source-transfer mechanism before another fit. This ablation did not improve held-out safety; retain all labels, source roles, frozen gates and the rejected result. No cutoff tuning, automatic rerun or new job queued. Claude remains paused; broader live-readiness goal stays active.
