# Full-gradient consistency: stable fit, held-out rejection

Run [44982269805](https://github.com/Ajuntanaga/m3-offload/actions/runs/44982269805) is final/success, but the research screen is **rejected**. Removing the target detach kept this fixed fit numerically stable and passed the training gates. Both held-out roles still fail; extra pitches increase and single-pitch preservation regresses. Continuous replay was skipped. Installed/default output and the recorded scoreboard are unchanged.

## Measured comparison

BASELINE is the original setwise model, run 44965135706; CURRENT is this offline trial. These are sustained sampled pitch sets, not labeled tuner-frame string matches or delivered-host MIDI. An exact set contains every expected pitch and no extra pitch. The training-only cutoff selection rule and all acceptance gates were unchanged.

| Role | BASELINE expected pitches found | CURRENT expected pitches found | Extra pitches, BASELINE to CURRENT | Exact sets, BASELINE to CURRENT |
| --- | --- | --- | --- | --- |
| train | 43827/45698 (95.91%) | 43959/45698 (96.19%) | 439 to 444 | 14597/16384 (89.09%) to 14653/16384 (89.43%) |
| calibration | 10673/11553 (92.38%) | 10677/11553 (92.42%) | 687 to 700 | 2997/4096 (73.17%) to 2999/4096 (73.22%) |
| test | 8000/10452 (76.54%) | 8090/10452 (77.40%) | 2705 to 2782 | 1749/4096 (42.70%) to 1733/4096 (42.31%) |

| Role / distinct pitches | BASELINE exact sets | CURRENT exact sets | Change |
| --- | --- | --- | --- |
| train / 1 | 3115/3132 (99.46%) | 3109/3132 (99.27%) | -6 |
| train / 2 | 3084/3220 (95.78%) | 3073/3220 (95.43%) | -11 |
| train / 3 | 2954/3251 (90.86%) | 2950/3251 (90.74%) | -4 |
| train / 4 | 2806/3432 (81.76%) | 2840/3432 (82.75%) | +34 |
| train / 5 | 1818/2529 (71.89%) | 1861/2529 (73.59%) | +43 |
| calibration / 1 | 691/753 (91.77%) | 692/753 (91.90%) | +1 |
| calibration / 2 | 652/777 (83.91%) | 662/777 (85.20%) | +10 |
| calibration / 3 | 625/837 (74.67%) | 626/837 (74.79%) | +1 |
| calibration / 4 | 541/885 (61.13%) | 538/885 (60.79%) | -3 |
| calibration / 5 | 283/639 (44.29%) | 276/639 (43.19%) | -7 |
| test / 1 | 607/869 (69.85%) | 591/869 (68.01%) | -16 |
| test / 2 | 441/950 (46.42%) | 433/950 (45.58%) | -8 |
| test / 3 | 324/932 (34.76%) | 302/932 (32.40%) | -22 |
| test / 4 | 145/813 (17.84%) | 162/813 (19.93%) | +17 |
| test / 5 | 27/327 (8.26%) | 40/327 (12.23%) | +13 |

Training five-pitch exact sets improve by 43, but training single-pitch exact sets fall from 3115 to 3109; extras rise from 13 to 17 and missing pitches from 5 to 6. Test single-pitch exact sets fall from 607 to 591; extras stay at 355 and missing pitches rise from 125 to 127. The intended isolated-note preservation is therefore not achieved.

Calibration precision is 93.85% against 95%, and four-/five-pitch exact sets are 60.79%/43.19% against 70%. Test precision is 74.41%, recall 77.40% and overall exact sets 42.31%, against 95%/80%/70%; three-/four-/five-pitch exact sets 32.40%/19.93%/12.23% also fail 70%. Silence extras remain 0 in all three roles. Better training and some recovered pitches do not offset these failures.

| Five-pitch gate | CURRENT | TARGET | PROGRESS = current / target | GAP or headroom |
| --- | --- | --- | --- | --- |
| train | 1861/2529 (73.59%) | 1771 (70.03%) | 1861/1771 = 105.08% | 90 sets headroom |
| calibration | 276/639 (43.19%) | 448 (70.11%) | 276/448 = 61.61% | 172 sets / 26.92 pp short |
| test | 40/327 (12.23%) | 229 (70.03%) | 40/229 = 17.47% | 189 sets / 57.80 pp short |

Integer targets are ceil(70% x role denominator). These are separate sampled-set gates, not overall completion.

## What the gradient change established

The rejected detached run 44980872011 ended with total loss 4668089708544; CURRENT ends at 0.476146851. All 80 epoch losses are finite, range 0.471571 to 2.466918. Final supervised loss is 0.458012145, consistency loss 0.018134707. No loss explosion occurred in this fixed run. This supports the identified same-network semi-gradient mechanism; it does not establish a general convergence guarantee or a source-transfer improvement.

The earlier infeasible cutoff emitted no pitches. CURRENT has a feasible training cutoff 0.5113435983657837, selected by the original maximum-TP rule at >=99% precision with stricter ties. Training precision is 99.000067563%. BASELINE cutoff was 0.5343895554542542. No held-out cutoff fitting, best-epoch selection, clipping, early stopping or refit occurred.

One fit took 202.741 seconds: 80 epochs, 16,384 mixtures, 10,240 optimizer steps, 14,465 parameters. The only change from the detached experiment differentiates both aligned outputs of the same network in the Huber consistency term. Historical stopped-gradient behavior remains available. Architecture, all source roles, original training plan, Adam settings, seed, supervised objective and single-forward inference remain fixed.

Feature-grid translation is not physical audio transposition. Source signatures move with the rows; this failed transfer screen supplies no broader source invariance claim.

## Provenance and verification

- Source `b48cee3a045709f074bec53c3156906461e1600e`; worker `5906f0527cea46aad6f0f674693c0270dc58476f`; workflow `harmonic-full-gradient-consistency.yml`.
- Specification `docs/recovery/harmonic-full-gradient-consistency-20261122.json`, SHA256 `ec911b4965b21cb630831936d07fdeea2d2979ccf5db3a8e4c28596eaeb7e273`.
- All 121 GitHub synthetic/unit tests passed in 3.884 s, including both-branch gradients, finite differences, the shared-parameter counterexample, persistence and historical-mode checks. Source CI [44982242913](https://github.com/Ajuntanaga/polyphonic-audio-to-midi/actions/runs/44982242913) passed.
- Local checks before dispatch: 3 non-Torch tests and 3 AST parses passed; 7 Torch tests deferred to GitHub. One focused failure-mechanism review completed. No local audio/model/native execution.
- All 555 original labels retained (train 200/calibration 200/test 155), no cross-role original overlap, no label exclusions. Holdout is recording pass/source excerpt; protocol, instrument and session are not independent.
- Original decompressed training-plan SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` verified; all 4 existing input archives verified. No new input uploads.
- Persisted model SHA256 `3798d2ad984e8425fc64ea84b9250714dbc0f0cb1432f5885b6dc4d8da0958d3`, frozen before held-out scoring; one fit.
- Small artifact `m3-harmonic-full-gradient-consistency-report-44982269805-1` (id 14738735392, 29,033 bytes), collected once at `2026-11-22T03:53:36.810847+00:00`. Server/local archive SHA256 `380b30ffebedda5ca24fff1f424a805289c3333135d5fab94a153ec9c1c67fc8` agree.
- Report `build/github-results/harmonic-full-gradient-consistency-44982269805/artifact/harmonic-full-gradient-consistency-result/report/report.json`, SHA256 `961be3b6767b31fa78c9461cf247318b71f0be0622a15f863760dd37b555f963`. Adjacent `baseline-comparison.json` retains every role/pitch-count delta and `collection-receipt.json` records the receipt.
- Bulk `m3-harmonic-full-gradient-consistency-evidence-44982269805-1` (id 14738391438, 6,716,166 bytes) remains remote; digest `sha256:ff95847006db62b58f9a6e08591053a86e06359970d5432050636f2949e52362`, expires `2026-12-06T03:53:06Z`.

## Next

Use retained source/pitch-count errors to choose a distinct source-transfer design with explicit single-note preservation. Require every original training, held-out and continuous gate; no cutoff rescue, repeated fit or next job is queued. The gradient correction resolved the observed optimization failure in this run; the remaining measured failure is held-out pitch-set safety and completeness.

No new attacks/releases, string assignment, unison multiplicity, gap-output, native allocation/deadline or DAW/device delivery result exists for this trial. Earlier corpus protections do not certify this model. Reliable live use remains unverified and overall completion is not measured. The broader goal remains active. Claude remains paused; no fresh Claude review is claimed. Do not poll, redownload or rerun this final job.
