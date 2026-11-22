# Harmonic peak contrast: training improves, held-out safety fails

Final CPU run [44971653845](https://github.com/Ajuntanaga/m3-offload/actions/runs/44971653845) succeeded, but the research screen is **rejected**. Training passed; calibration and test failed. Continuous replay was skipped as specified. Installed/default output, all 555 source labels and the scoreboard remain unchanged.

## Frozen change

The classifier receives 106 features per candidate instead of 62. Added features describe nearby harmonic peak position, prominence and agreement of frequency offsets across partials, using the existing trailing 4096-/16384-sample windows. There is no hard harmonicity veto. The original training mixture plan, gains, 200/200/155 source roles, setwise objective, optimizer, 80 epochs, cutoff-selection rule and acceptance gates stayed fixed. The original plan's decompressed hash reproduces exactly.

One fit used 16,384 mixtures / 868,352 pooled candidate cells and took 202.74 seconds. The cutoff 0.4416719377040863 maximizes training true positives at at least 99% precision; the model was persisted before held-out scoring. Parameter count rises 14,465 -> 15,873, so information, capacity and initialization effects are not isolated. The 170.67 ms maximum trailing context is unchanged and is not a measured pluck-to-MIDI latency.

## Measured result

BASELINE is unaugmented setwise run 44965135706. CURRENT here means this offline trial. Exact means the entire expected distinct-pitch set with no extras in a sampled sustained mixture. It does not mean installed labeled-frame/string matches or delivered MIDI.

| Role | Exact sets: BASELINE -> CURRENT | Pitch precision | Pitch recall | Extra pitches | Missing pitches | Five-pitch exact: BASELINE -> CURRENT |
|---|---:|---:|---:|---:|---:|---:|
| train | 14597 -> 15227/16384 (89.09 -> 92.94%) | 99.01 -> 99.01% | 95.91 -> 97.82% | 439 -> 448 | 1871 -> 998 | 1818 -> 2086/2529 (71.89 -> 82.48%) |
| calibration | 2997 -> 2966/4096 (73.17 -> 72.41%) | 93.95 -> 92.27% | 92.38 -> 93.05% | 687 -> 900 | 880 -> 803 | 283 -> 278/639 (44.29 -> 43.51%) |
| test | 1749 -> 1711/4096 (42.70 -> 41.77%) | 74.73 -> 72.09% | 76.54 -> 78.48% | 2705 -> 3176 | 2452 -> 2249 | 27 -> 33/327 (8.26 -> 10.09%) |

| Role | CURRENT three-pitch exact | CURRENT four-pitch exact | CURRENT five-pitch target progress | Verdict |
|---|---:|---:|---:|---|
| train | 3047/3251 (93.73%) | 3067/3432 (89.36%) | 2086/1771 = 117.79%; headroom 315 sets | pass |
| calibration | 616/837 (73.60%) | 528/885 (59.66%) | 278/448 = 62.05%; gap 170 sets | reject |
| test | 290/932 (31.12%) | 154/813 (18.94%) | 33/229 = 14.41%; gap 196 sets | reject |

Targets remain at least 70% exact sets overall and separately for 3/4/5 pitches, at least 80% pitch recall, at least 99% training / 95% held-out pitch precision, and zero silence extras. Silence extras are zero on 820/205/205 examples. Calibration fails precision and four-/five-pitch exact gates. Test fails precision, recall, overall and three-/four-/five-pitch exact gates. These gate ratios are not project completion.

The training gain does not transfer safely. Test finds 203 more expected pitches (8000 -> 8203) while adding 471 extras (2705 -> 3176); complete sets fall 1749 -> 1711. Calibration finds 77 more expected pitches but adds 213 extras. Test false-output growth occurs in every pitch band: below48 +135, 48-59 +90, 60-71 +185, 72-84 +61. Training single-pitch exact falls 3115 -> 3105/3132; test single-pitch exact falls 607 -> 598/869 and three-pitch exact falls 324 -> 290/932. Five-pitch training improvement alone is insufficient.

Saved contrast summaries are descriptive: in the test long window, found/missing/extra candidate prominence medians are 26.03/13.76/17.03 dB, and partial-offset dispersion medians are 1.35/3.17/2.24 cents. Their ranges overlap substantially. This is not evidence for a new safe threshold; no cutoff or feature was retuned after scoring.

Both held-out roles are source-disjoint development checks already inspected in earlier experiments. Recording protocol, content and annotation uncertainty remain confounded. Earlier spectral verification supports some source/label disagreements, but the saved estimator results do not establish an upper bound on the unchanged exact-set gate. All unresolved sources remain included. Sustained mixtures do not establish attacks, decays, lane assignment, same-pitch unison multiplicity or live stability.

## Verification and evidence

All 87 GitHub synthetic checks passed with zero skips in 5.085 seconds; source CI 44971615865 passed. One independent static review preceded dispatch. The 29,730-byte small archive was collected once and matches its server digest. The 6,981,800-byte model/prediction archive remains remote. No local recorded-audio, model or native execution occurred.

- Source: `5cf22b108649b43493ab5b360847104d27d3115e`.
- Worker: `d1413dfc4f988f42ed676a96e9a9b88f310097e7`.
- Specification SHA256: `3635862c87b80cb8bbe1e16cf7a9aa08a8d6ffd837d3a920a2a46c6406495c3e`.
- Original plan decompressed SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- Frozen model SHA256: `e3edc05643d31b3d8f5cecb95054c905702a5fdc1c41692cbc8c70747fd53c98`.
- Report: `build/github-results/harmonic-peak-contrast-44971653845/artifact/harmonic-peak-contrast-result/report/report.json`.
- Report SHA256: `6e2158049bb6a6bbb1271240edb315c08b8a32ca5e33407639d10b413c0b58f3`.
- Small artifact 14733907205, archive SHA256: `ad2cc55cb8b60fa429657f6a0b8facdd26bd4fd91181d0042981ef269fcc1bb9`.
- Collected: 2026-11-22T01:36:52.384415+00:00.
- Bulk artifact 14733797444 (`m3-harmonic-peak-contrast-evidence-44971653845-1`), expires 2026-12-06T01:36:06Z. Leave remote unless a distinct saved-result question requires named files.

## Next

Preserve this rejection. More detailed harmonic peaks improve the training fit without improving held-out complete-set safety. Choose a distinct mechanism for source transfer before another fit; further cutoff/capacity changes are not supported by this result. Do not repeat completed surveys, relabel/exclude sources, or retry this configuration. No next job is queued.

A candidate still needs the unchanged training and held-out gates before continuous per-label presence/longest-hold and false/gap-output checks, then native allocation/deadline and external-host verification. Reliable live use remains unverified. Claude is paused; no fresh Claude review is claimed. The broader live-readiness goal remains active.
