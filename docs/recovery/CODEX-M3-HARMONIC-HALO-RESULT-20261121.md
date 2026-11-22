# Measured pitch halo: held-out transfer rejected

Run [44978661693](https://github.com/Ajuntanaga/m3-offload/actions/runs/44978661693) completed successfully, but its research screen is **rejected**. Test five-pitch exact sets improved **27 to 39/327 (8.26% to 11.93%)**, while complete sets across the test role fell **1749 to 1725/4096 (42.70% to 42.11%)**. Both held-out gates failed. Continuous replay was skipped by the frozen protocol. Installed/default output and the installed scoreboard are unchanged.

## Result

An exact set contains every expected pitch and no extra pitch. These are sustained sampled pitch sets; they do not measure tuner-frame string assignment, repeated-pitch unisons or delivered-host MIDI.

| Role | Expected pitches found, BASELINE -> CURRENT | Extra pitches | Missing pitches | Complete sets, BASELINE -> CURRENT |
| --- | --- | --- | --- | --- |
| train | 43827 -> 43646/45698 (95.91% -> 95.51%) | 439 -> 440 | 1871 -> 2052 | 14597/16384 (89.09%) -> 14480/16384 (88.38%) |
| calibration | 10673 -> 10587/11553 (92.38% -> 91.64%) | 687 -> 644 | 880 -> 966 | 2997/4096 (73.17%) -> 2970/4096 (72.51%) |
| test | 8000 -> 8028/10452 (76.54% -> 76.81%) | 2705 -> 2472 | 2452 -> 2424 | 1749/4096 (42.70%) -> 1725/4096 (42.11%) |

Test expected-pitch recall improves by 0.27 percentage points and extra pitches fall by 233. However, test single-pitch complete sets fall **607 to 569/869 (69.85% to 65.48%)**, three-pitch sets fall **324 to 308/932**, and calibration complete sets fall by 27. The five-pitch test gain is therefore not a general preservation or promotion result.

### Test complete sets

| Distinct pitches | BASELINE exact sets | CURRENT exact sets | Change |
| --- | --- | --- | --- |
| 1 | 607/869 (69.85%) | 569/869 (65.48%) | -38 |
| 2 | 441/950 (46.42%) | 446/950 (46.95%) | +5 |
| 3 | 324/932 (34.76%) | 308/932 (33.05%) | -16 |
| 4 | 145/813 (17.84%) | 158/813 (19.43%) | +13 |
| 5 | 27/327 (8.26%) | 39/327 (11.93%) | +12 |

### Calibration complete sets

| Distinct pitches | BASELINE exact sets | CURRENT exact sets | Change |
| --- | --- | --- | --- |
| 1 | 691/753 (91.77%) | 690/753 (91.63%) | -1 |
| 2 | 652/777 (83.91%) | 656/777 (84.43%) | +4 |
| 3 | 625/837 (74.67%) | 608/837 (72.64%) | -17 |
| 4 | 541/885 (61.13%) | 536/885 (60.56%) | -5 |
| 5 | 283/639 (44.29%) | 275/639 (43.04%) | -8 |

### Training complete sets

| Distinct pitches | BASELINE exact sets | CURRENT exact sets | Change |
| --- | --- | --- | --- |
| 1 | 3115/3132 (99.46%) | 3103/3132 (99.07%) | -12 |
| 2 | 3084/3220 (95.78%) | 3042/3220 (94.47%) | -42 |
| 3 | 2954/3251 (90.86%) | 2928/3251 (90.06%) | -26 |
| 4 | 2806/3432 (81.76%) | 2796/3432 (81.47%) | -10 |
| 5 | 1818/2529 (71.89%) | 1791/2529 (70.82%) | -27 |

Silence remains exact with zero extra outputs across 820 training, 205 calibration and 205 test mixtures.

## Frozen gates

Training passes: aggregate pitch precision is 99.0020%, expected-pitch recall 95.5097%, and complete sets 88.3789%; each 3/4/5-pitch complete-set rate is at least 70%. Calibration fails precision (94.2659%, target 95%) and four/five-pitch complete sets (60.5650%/43.0360%, target 70%). Test fails precision (76.4571%, target 95%), recall (76.8083%, target 80%), aggregate complete sets (42.1143%, target 70%) and every 3/4/5-pitch complete-set gate.

Five-pitch gate calculations use the smallest integer count reaching 70%:

| Role | CURRENT | TARGET | PROGRESS current/target | GAP or headroom |
| --- | --- | --- | --- | --- |
| train | 1791/2529 (70.82%) | 1771/2529 (70.03%) | 1791/1771 = 101.13% | headroom 20 sets / 0.79 pp |
| calibration | 275/639 (43.04%) | 448/639 (70.11%) | 275/448 = 61.38% | gap 173 sets / 27.07 pp |
| test | 39/327 (11.93%) | 229/327 (70.03%) | 39/229 = 17.03% | gap 190 sets / 58.10 pp |

These ratios describe individual gates, not overall project completion. The cutoff was selected once on training by the unchanged rule: maximum true positives at at least 99% pitch precision, choosing the stricter tie. BASELINE cutoff 0.5343895554542542; CURRENT cutoff 0.6624976396560669. Held-out data was not used for cutoff selection or model fitting. These development roles have been inspected in previous experiments and are not an untouched final benchmark.

## Scope and provenance

The four residual layers have a 73-position receptive field. The trial supplies 36 measured pitch rows on each side of the original 53-row input and removes zero padding through valid convolutions. Input positions cover MIDI -4..120 (125 rows); output targets remain MIDI32..84 (53 rows). Each row retains the same 62 harmonic/RMS coordinates. Central feature values are bit-identical, and the scaler is fitted only on central training rows. The architecture has the same 14465 parameters, seeded initial values, setwise loss, optimizer, 80 epochs, sources, mixture plans and acceptance gates. One fit took 198.307 seconds.

Context addition and boundary removal change together, so the result cannot isolate their effects. Very low halo pitches are poorly resolved by the FFT and high halo pitches can be weak; adding the halo does not establish exact audio transposition equivalence.

- Source: `2c2ced6ac975a34288b0a1dfc26db4c2f100c1a5` in `Ajuntanaga/polyphonic-audio-to-midi`.
- Worker: `ca1fa82801caace567db76265d43c51157400fe8` in `Ajuntanaga/m3-offload`, `harmonic-halo-context.yml`.
- Design: `CODEX-M3-HARMONIC-HALO-PLAN-20261121.md`; specification `harmonic-halo-context-20261121.json`, SHA256 `a8398d57acd442b31a6bd12fa7f03f9123d6b340bb87fd453b2d649e3ac483c5`.
- Baseline: run44965135706, source `6b4d39aa8b308ce8f808486b345dbe865b1bb4a0`, report SHA256 `43b65016f2073661540499843adf12137645e59ed79a62e408c0a8c7449834b9`.
- All **555 original labels** retained: train200, calibration200, test155. No source-role overlap or content-based exclusion. The split is by recording pass/source excerpt; protocol, instrument and session are not independent factors.
- Training-plan decompressed SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` verified against the original plan.
- Model SHA256 `3db5569cfe51b433d8b608e88142f6a4aa1bbe9326b59d8d95b375db23fbbd01`, persisted before held-out scoring.

## Verification and retained evidence

All **111 GitHub synthetic/unit tests** passed in 3.912 seconds. Source CI [44978616060](https://github.com/Ajuntanaga/polyphonic-audio-to-midi/actions/runs/44978616060) passed. Local five-check synthetic/gate-flow validation, six-file AST parsing and one focused implementation review had passed before dispatch. Execution and test success do not override the held-out failures.

The small archive `m3-harmonic-halo-context-report-44978661693-1` (artifact14736488772, 26163 bytes) was collected once at `2026-11-22T03:06:15.329656+00:00`. Server and local archive SHA256 agree: `b84d98a5932439a54f30ada6f8dfa7083b37879358c09bb49a7207e99de64a1c`.

Report: `build/github-results/harmonic-halo-context-44978661693/artifact/harmonic-halo-context-result/report/report.json`, SHA256 `0604b4c4b832e0c05912915d4654859c0a5d8e87ac24615c0fb5b8f782e51a8c`. Adjacent `collection-receipt.json` and `baseline-comparison.json` retain collection details and exact before/after counts.

Bulk artifact `m3-harmonic-halo-context-evidence-44978661693-1` (artifact14737002306, 6878784 bytes, SHA256 `6a0bb83c4ef1394d0a919db0f35330411920cec69d4b51c680d9c5aabe50c4b8`) remains remote and expires `2026-12-06T03:05:43Z`. Do not poll, redownload or rerun this completed screen.

## Limits and next step

This fixed halo does not resolve transfer. Continuous note locking, string assignment, unison multiplicity, attacks, releases, false-gap output, native allocations/deadlines and live DAW/device delivery were not measured for this trial. Earlier protected-corpus checks do not certify this model.

Choose a distinct mechanism supported by the retained source-transfer evidence before another fit. Require preservation of single-note rejection and complete chords, all source labels, the existing training and held-out gates, and continuous/native/host verification before promotion. No next job is queued, no cutoff tuning or automatic rerun is authorized by this result. The broader live-readiness goal remains active; overall completion is not measured. Claude remains paused.
