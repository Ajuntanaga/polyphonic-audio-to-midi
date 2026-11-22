# Independent partial variation: rejected at the training gate

Final result recorded 2026-11-22T02:21:44.876714+00:00. Run [44975092935](https://github.com/Ajuntanaga/m3-offload/actions/runs/44975092935) completed successfully; the research screen is **rejected**. Clean-training five-pitch complete sets fell below the frozen gate, so calibration, test and continuous replay were skipped. Their trial results are **not measured**, not zero. Installed output, defaults, source labels and the installed scoreboard are unchanged.

The single fit varied the first five harmonic-envelope anchors independently within +/-6 dB on training components, with a 50% exact bypass. Of 47,005 components, 23,471 were unchanged and 23,534 varied. The existing clean training plan selected the cutoff and supplied the gates. Source roles, crops, labels, 62 features, 14,465-parameter model, objective, example count and 80-epoch budget stayed fixed. Held-out audio was never augmented.

## Measured result

These counts describe sustained sampled pitch sets, not tuner frame/string assignments, unique audio duration or delivered MIDI. Exact means the entire expected pitch set with no extra prediction. Baseline is unaugmented setwise run 44965135706.

- Five-pitch CURRENT **1688/2529 (66.75%)**, BASELINE **1818/2529 (71.89%)**: 130 fewer complete sets, -5.14 percentage points.
- TARGET **1771/2529 (70.03%)**, the integer count required by the 70% gate. PROGRESS **1688/1771 = 95.31%**; GAP **83 sets / 3.28 percentage points**. This is a named training-gate ratio, not project completion.
- All-set exact **14597 → 14268/16384 (89.09 → 87.08%)**.
- Expected pitches found **43827 → 43484**; extras **439 → 438**; missing pitches **1871 → 2214**. One fewer extra costs 343 more missed pitches.
- Training precision **99.0028%**, recall **95.1551%**; zero extras on all 820 silence examples. Aggregate precision/recall and 3/4-pitch exact gates pass; the 5-pitch exact gate fails.

| Distinct pitches | Baseline → trial complete sets | Extra pitches | Missing pitches |
|---|---|---|---|
| 1 | 3115 → 3112/3132 (99.46 → 99.36%) | 13 → 19 | 5 → 1 |
| 2 | 3084 → 3069/3220 (95.78 → 95.31%) | 55 → 61 | 93 → 102 |
| 3 | 2954 → 2902/3251 (90.86 → 89.26%) | 102 → 86 | 255 → 316 |
| 4 | 2806 → 2677/3432 (81.76 → 78.00%) | 138 → 134 | 628 → 781 |
| 5 | 1818 → 1688/2529 (71.89 → 66.75%) | 131 → 138 | 890 → 1014 |

Calibration TARGET 448/639 and test TARGET 229/327 remain unchanged. Their trial count, percentage, progress and gap are not measured because the preceding training gate failed. Historical baseline counts (283/639 and 27/327) are not measurements of this trial.

## Provenance and verification

- Source `74f9a276712fc37a8d45b0caba70fb3d6ad81a91`; worker `f99030043abaae2edeaca9af5580058cbf9a494e`; specification SHA256 `0cb231e506435d8aa9cc94cf371225c6b212cfe983d6ef51d733e60b6b5dd5f1`.
- Source CI 44975042554 passed. All **98 GitHub synthetic checks passed, zero skips**; eight local synthetic checks had passed before dispatch. No local recorded-audio, model or native execution.
- One fit, 80 epochs, 122.745 seconds; final loss 0.460030402. Cutoff 0.6209489703178406 chosen on clean training only. Model persisted before the held-out gate, SHA256 `2ba1575f98e723acd9a5f6bf1229511c8774656ee43f256da270d7fc7338df53`.
- All 555 original labels and source roles retained: 200 training, 200 calibration, 155 test, no original-source overlap between roles, no source-consistency filtering.
- Original decoded training-plan SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` and varied-plan SHA256 `7604d928e23018fc4ea172dc1b186d17967b96b0f9e494dd8a114f6d2da8d0d3` both match their pre-dispatch pins.
- Small artifact 14735014273, 18285 bytes, collected once at 2026-11-22T02:20:16.970810+00:00; archive SHA256 `fa1598a4907aca2c5a90657cf3656581d17d47c65adf2f35aa7529f8afad701c` matches the server digest. Two earlier connection failures received zero bytes; only the report read was retried, no compute was repeated.
- Local report `build/github-results/harmonic-partial-variation-44975092935/artifact/harmonic-partial-variation-result/report/report.json`; SHA256 `a4cb9a8d8af027c57b40aa96c0f1e44262dd94a47a356395be1b12405a9a9167`.
- Bulk artifact 14736000295 remains remote (6,729,500 bytes, expires 2026-12-06T02:17:34Z). Model, predictions and plans were not downloaded.
- No new continuous-corpus, allocation/deadline, string-lane/unison, external host or hardware result. Earlier identity/protection checks remain earlier checks.

## Decision and next step

This frozen augmentation regresses clean-training chord recovery and is rejected before transfer evaluation. It does not establish whether a different augmentation distribution could transfer; changing its bounds, seed, cutoff or epoch count would be a new experiment. No such tuning or rerun is queued.

Choose a distinct, evidence-supported source-transfer mechanism before another fit. Any next screen must first recover at least 1771/2529 clean-training five-pitch sets with the unchanged precision, recall, silence and 3/4-pitch gates, then pass calibration/test and continuous safety gates. These repeated feature/augmentation screens have not supplied a safe route to live tracking; another parameter variant alone is not justified by this result.

Known limits remain: same training recordings, intended rather than verified pitch anchors, possible crop-boundary/interharmonic shaping, and source-disjoint development roles already reused in research. No label exclusions or relabeling. Claude remains paused; no fresh Claude review is claimed. The broader live-readiness goal remains active; overall completion is not measured.
