# Training-source variation: held-out transfer rejected

Final CPU run [44966587324](https://github.com/Ajuntanaga/m3-offload/actions/runs/44966587324) completed successfully, but the research screen is **rejected**. Training passed; calibration and test failed. Continuous replay was skipped as specified. Installed/default output, all source labels and the scoreboard remain unchanged.

## Frozen change

Only training component envelopes varied: half bypassed, half received a seeded shelf between -6 and +6 dB at 1 kHz, applied after cropping and before RMS normalization. The same 47,005 components, original crops/gains, 200/200/155 source roles, 555 labels, architecture, setwise loss, 80 epochs and acceptance gates were preserved. There were 23,571 varied and 23,434 identity components. The model and scaler fitted varied training features; the original clean training matrix selected the cutoff and training gates. Held-out examples were never varied or used for fitting.

One fit, 116.99 seconds; cutoff 0.586877167224884. The model was persisted before both held-out roles were scored. This tests one fixed envelope variation, not all augmentation methods.

## Measured comparison

BASELINE is setwise run 44965135706. CURRENT below is this offline experiment, not installed output. Exact means the complete expected pitch set with no extra pitch in a sampled sustained mixture; these are not labeled-frame/string matches.

| Role | Exact sets: BASELINE -> CURRENT | Pitch precision | Pitch recall | Extra pitches | Missing pitches | Five-pitch exact: BASELINE -> CURRENT |
|---|---:|---:|---:|---:|---:|---:|
| train | 14597 -> 14542/16384 (89.09 -> 88.76%) | 99.01 -> 99.00% | 95.91 -> 95.84% | 439 -> 442 | 1871 -> 1900 | 1818 -> 1779/2529 (71.89 -> 70.34%) |
| calibration | 2997 -> 2966/4096 (73.17 -> 72.41%) | 93.95 -> 93.59% | 92.38 -> 92.31% | 687 -> 730 | 880 -> 889 | 283 -> 269/639 (44.29 -> 42.10%) |
| test | 1749 -> 1756/4096 (42.70 -> 42.87%) | 74.73 -> 75.06% | 76.54 -> 76.48% | 2705 -> 2656 | 2452 -> 2458 | 27 -> 24/327 (8.26 -> 7.34%) |

| Role | CURRENT three-pitch exact | CURRENT four-pitch exact | CURRENT five-pitch target progress | Verdict |
|---|---:|---:|---:|---|
| train | 2942/3251 (90.50%) | 2803/3432 (81.67%) | 1779/1771 = 100.45%; headroom 8 sets | pass |
| calibration | 619/837 (73.95%) | 524/885 (59.21%) | 269/448 = 60.04%; gap 179 sets | reject |
| test | 319/932 (34.23%) | 154/813 (18.94%) | 24/229 = 10.48%; gap 205 sets | reject |

The target is at least 70% complete sets overall and separately for 3/4/5 pitches, at least 80% pitch recall, at least 99% training / 95% held-out pitch precision, and zero silence extras. Calibration fails precision and four-/five-pitch exact gates. Test fails precision, recall, overall and three-/four-/five-pitch exact gates. Silence extras remain zero on 820/205/205 examples. These target ratios are specific gates, not project completion.

Training single-pitch exact falls 3115 -> 3113/3132; extras increase 13 -> 17 and misses fall 5 -> 4. On test, 49 fewer extra pitches accompany six fewer expected pitches and three fewer complete five-pitch sets. Calibration also worsens overall. The frozen variation therefore does not resolve transfer; the small test precision improvement does not offset the failed gates.

Both held-out roles are source-disjoint development checks already used in prior experiments, not a fresh final benchmark. Recording protocol, source content and annotation uncertainty remain confounded. All 555 labels, including known unresolved content disagreements, were retained. No relabeling or source exclusion is justified by these totals. Sustained pitch sets do not establish attack/release behavior, string assignment, unison multiplicity, native timing or delivered MIDI.

## Validation and retained evidence

All 72 GitHub synthetic checks passed with zero skips; source CI 44966574518 passed. The focused implementation review found one workflow specification path error, corrected before dispatch. No further review or processing was needed after collection. The small archive was collected once and its server digest and byte count verified; the bulk model and predictions remain remote.

- Source: `7481905c4b38bad52770c59c7b9c0fdb3eca75a0`.
- Worker: `99e7422982c1394977977bf73ccb8dfb7e40367d`.
- Specification SHA256: `c0b321745674a6ebf54e98056b5c4468fef55c64b1ffdc21d8666f7ab2749bb0`.
- Original plan decompressed SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- Varied plan decompressed SHA256: `1ea90f1e190e889d59574d58683d72889b4725e8b26e5bf47b246274b07597f7`.
- Frozen model SHA256: `bf9a974f1cd6d2e6bb8461044a114e45017661a7276f5b9d759072c8da8b4dec`.
- Report: `build/github-results/harmonic-source-variation-44966587324/artifact/harmonic-source-variation-result/report/report.json`.
- Report SHA256: `05ecd04c986395620b9635814eed3f41ea73462730d68c2a25511dfe92d65971`.
- Small archive SHA256: `6aa02a247975b93a8de09394eeeae10854a8e0c53f2dc6c042e1284f457f8358`.
- Small artifact 14731238625: 26,294 bytes; collected 2026-11-22T00:31:59.757638+00:00.
- Bulk artifact 14731592882 (`m3-harmonic-source-variation-evidence-44966587324-1`): 8,013,695 bytes, expires 2026-12-06T00:29:36Z. Leave remote unless a named saved-prediction diagnosis needs it.

## Next

Use retained predictions and mixture metadata to separate held-out errors already present in single-note examples from mixture-specific losses before choosing a distinct transfer design. Preserve every source, role, cutoff and rejection; no refit or new job queued.

The next design must pass the unchanged training and both held-out gates before continuous per-label presence/longest-hold, false-pitch and gap-output gates, then native allocation/deadline and external-host checks. Claude remains paused; no fresh Claude review is claimed. The live-readiness goal remains active.
