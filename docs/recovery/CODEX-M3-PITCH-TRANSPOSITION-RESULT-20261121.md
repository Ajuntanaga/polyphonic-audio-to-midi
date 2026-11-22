# Coherent pitch transposition: held-out transfer still rejected

Final CPU run [44969797809](https://github.com/Ajuntanaga/m3-offload/actions/runs/44969797809) succeeded, but the research screen is **rejected**. Training passed and both held-out roles failed. Continuous replay was skipped as specified. Installed/default output, all 555 source labels and the scoreboard remain unchanged.

## Frozen change

Each original clean training mixture was retained alongside one companion with a coherent integer pitch shift between -6 and +6 semitones. Every component in a mixture received the same legal shift, preserving intervals and distinct-pitch count; silence and five mixtures without a legal nonzero shift stayed unchanged. Guarded resampling used only the original take, with no padding or wrapping, followed by the original RMS normalization and gain. Held-out audio was never shifted. No source was excluded or relabeled.

The original and companion plans match their pre-recorded hashes. Source roles stay 200 training, 200 calibration, 155 test. Architecture, setwise loss, optimizer, 80 epochs and acceptance gates stayed fixed. This doubles examples and optimizer steps: 32,768 examples and 20,480 steps, one fit taking 210.95 seconds. The cutoff 0.5962355136871338 was selected only on the original clean training plan. The model was persisted before held-out scoring.

Resampling also changes duration and spectral envelope; twice the optimizer steps is another attribution confound. This is one frozen variation using the same recordings, not independent new guitar content.

## Measured result

BASELINE is setwise run 44965135706. CURRENT below is this offline model. Exact means the complete expected distinct-pitch set with no extra pitch in a sampled sustained mixture; these are not installed labeled-frame/string matches.

| Role | Exact sets: BASELINE -> CURRENT | Pitch precision | Pitch recall | Extra pitches | Missing pitches | Five-pitch exact: BASELINE -> CURRENT |
|---|---:|---:|---:|---:|---:|---:|
| train | 14597 -> 14643/16384 (89.09 -> 89.37%) | 99.01 -> 99.00% | 95.91 -> 96.16% | 439 -> 442 | 1871 -> 1753 | 1818 -> 1833/2529 (71.89 -> 72.48%) |
| calibration | 2997 -> 3005/4096 (73.17 -> 73.36%) | 93.95 -> 93.88% | 92.38 -> 92.26% | 687 -> 695 | 880 -> 894 | 283 -> 286/639 (44.29 -> 44.76%) |
| test | 1749 -> 1761/4096 (42.70 -> 42.99%) | 74.73 -> 75.74% | 76.54 -> 76.49% | 2705 -> 2561 | 2452 -> 2457 | 27 -> 37/327 (8.26 -> 11.31%) |

| Role | CURRENT three-pitch exact | CURRENT four-pitch exact | CURRENT five-pitch target progress | Verdict |
|---|---:|---:|---:|---|
| train | 2947/3251 (90.65%) | 2843/3432 (82.84%) | 1833/1771 = 103.50%; headroom 62 sets | pass |
| calibration | 630/837 (75.27%) | 553/885 (62.49%) | 286/448 = 63.84%; gap 162 sets | reject |
| test | 304/932 (32.62%) | 166/813 (20.42%) | 37/229 = 16.16%; gap 192 sets | reject |

Targets remain at least 70% exact sets overall and separately for 3/4/5 pitches, at least 80% pitch recall, at least 99% training / 95% held-out pitch precision, and zero silence extras. Calibration fails precision and four-/five-pitch exact gates. Test fails precision, recall, overall and three-/four-/five-pitch exact gates. Silence extras remain zero on 820/205/205 examples. These are specific gate ratios, not project completion.

The held-out test gains 12 complete sets overall and 10 complete five-pitch sets, while total extras fall 2705 -> 2561 and expected pitches found fall 8000 -> 7995. Within five-pitch mixtures, extras fall 312 -> 277 but missing pitches rise 524 -> 548. Complete-set gains therefore do not demonstrate an aggregate note-recall gain. Single-pitch exact also falls 607 -> 593/869 and three-pitch exact falls 324 -> 304/932. Calibration extras rise 687 -> 695 and expected pitches found fall 10673 -> 10659. The small complete-set improvements do not resolve transfer.

Both held-out roles are source-disjoint development checks already used by earlier experiments, not a fresh final benchmark. Recording protocol, content and annotation uncertainty remain confounded; all unresolved labels were retained. These sustained pitch sets do not establish attacks, decays, lane assignment, same-pitch unison multiplicity, native realtime behavior or delivered MIDI.

## Verification and retained evidence

All 78 GitHub synthetic checks passed with zero skips (3.098 seconds); source CI 44969734602 passed. The collected report records one fit, unchanged original plan identity and no held-out augmentation. The 26,852-byte small archive was collected once and matches its server SHA256. The 8,347,806-byte model/prediction archive remains remote. No local recorded-audio, model or native execution occurred.

- Source: `c671c282e67beb29f266b208f4338ceac47f1c07`.
- Worker: `5511019683c1f339b8cb9ff5baf6ae8513bf84d7`.
- Specification SHA256: `7594771882b75286eebcdbcca1e0f4db004adeda33856e557d4053a88aa20a07`.
- Original plan decompressed SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- Companion plan decompressed SHA256: `79ab8453a9c3fc1ff31200cc7da3fed66e1fa4fe47e46675681dbc6e0aeb773f`.
- Frozen model SHA256: `c2d0956f734ec4f1958e3fd28b1bb97dec5da1e2afa39698b8eea5e8fc5d1637`.
- Report: `build/github-results/harmonic-pitch-transposition-44969797809/artifact/harmonic-pitch-transposition-result/report/report.json`.
- Report SHA256: `04cfb5fde459fa4cd63819029857d4509b8a3907c1ac8a5e1138a4fd4205d57b`.
- Small artifact 14733541008, archive SHA256: `da2dc387d180e271b5407f5fa872f2ce9fa5cceb02ba50ac75ceece310c2af06`.
- Collected: 2026-11-22T01:11:47.011919+00:00.
- Bulk artifact 14733615543 (`m3-harmonic-pitch-transposition-evidence-44969797809-1`), expires 2026-12-06T01:10:55Z. Leave remote unless a distinct, frozen saved-result diagnosis requires named files.

## Next

Use the recorded per-pitch/source error summaries to separate false-pitch rejection from expected-pitch loss before freezing a distinct transfer design. The aggregate comparison above is complete; no automatic refit, threshold tuning, source exclusion or new job is queued. Preserve this rejection and every original gate.

Any next candidate must pass training and both held-out precision/recall/complete-set gates before continuous per-label presence/longest-hold and false/gap-output checks, then native allocation/deadline and external-host verification. Reliable live use remains unverified. Claude is paused; no fresh Claude review is claimed. The broader live-readiness goal remains active.
