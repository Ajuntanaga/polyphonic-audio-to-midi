# Setwise objective: training passed, held-out transfer rejected

Final CPU worker run [44965135706](https://github.com/Ajuntanaga/m3-offload/actions/runs/44965135706) completed successfully. The research screen is **rejected**: training gates passed, both held-out roles failed, and continuous replay was skipped. Installed/default output, labels and scoreboard are unchanged. No live-host or real-time performance gain is established.

## Frozen comparison

Same 14,465-parameter model, 62 features, 53 pitches, seed, 80 epochs, training plan and 200/200/155 source roles. All 555 original labels retained. Only the loss changed to mean BCE plus summed true/false log-sum-exp. The train-only cutoff is 0.5343895554542542, selected by the unchanged maximum-recall-at-99%-precision rule. No held-out refitting or exclusion.

| Training measure | BCE baseline 44960075844 | Previous loss 44962588969 | Setwise 44965135706 |
|---|---:|---:|---:|
| Complete single-pitch sets | 3108/3132 (99.23%) | 3097/3132 (98.88%) | 3115/3132 (99.46%) |
| Single-pitch extra / missing pitches | 18 / 8 | 32 / 7 | 13 / 5 |
| Complete five-pitch sets | 1547/2529 (61.17%) | 1759/2529 (69.55%) | 1818/2529 (71.89%) |

The training five-pitch target is 1771/2529: 1818/1771 = 102.65% of that target, with 47 sets of headroom. Single-pitch aggregate preservation also passes: seven more complete sets, five fewer extra pitches and three fewer missing pitches than BCE. These are aggregate comparisons; per-mixture preservation was not measured by the compact report.

## Source-disjoint held-out results

Percentages below are constructed-mixture pitch-set measures, not annotated audio frame matches or string assignment. Exact means every expected pitch and no extra pitch in the sampled mixture.

| Role | Exact sets | Pitch precision | Pitch recall | 3-pitch exact | 4-pitch exact | 5-pitch exact | Extra / missing pitches |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 14597/16384 (89.09%) | 99.01% | 95.91% | 2954/3251 (90.86%) | 2806/3432 (81.76%) | 1818/2529 (71.89%) | 439 / 1871 |
| calibration | 2997/4096 (73.17%) | 93.95% | 92.38% | 625/837 (74.67%) | 541/885 (61.13%) | 283/639 (44.29%) | 687 / 880 |
| test | 1749/4096 (42.70%) | 74.73% | 76.54% | 324/932 (34.76%) | 145/813 (17.84%) | 27/327 (8.26%) | 2705 / 2452 |

Silence produced zero false predictions in all roles (820 training, 205 calibration, 205 test examples). The calibration role fails 95% pitch precision and 70% exact four-/five-pitch gates. The test role fails precision, recall and exact-set gates. Both held-out roles require at least 95% precision, 80% recall, 70% complete sets overall and separately at 3/4/5 pitches, and no silence false predictions. No baseline held-out before/after change is measured: the prior objectives stopped at training gates.

The training improvement is real under the frozen comparison, but it does not establish transfer. Recording pass/source excerpts are disjoint; instrument, session and protocol are not independent. Pass 1 ascending, pass 2 descending and pass 3 checkpoint protocols remain confounded. Known source-content disagreements were retained. This report cannot attribute the gap uniquely to objective, source variation, protocol or annotation quality. No per-label selection, relabelling or dropped source is justified by these totals.

## Validation and collection

All 67 GitHub synthetic checks passed with zero skips; source portable CI 44965120162 passed. One focused static review found no material blockers. Source, worker, specification and training-plan pins match the report. This validates the experimental implementation and arithmetic; native timing, allocations and external DAW/device delivery were not evaluated by this screen.

- Source: `6b4d39aa8b308ce8f808486b345dbe865b1bb4a0`.
- Worker: `9cff32047cf26c6abe227db3f27b992d7a680abc`.
- Specification SHA256: `4e732fc01f20e2b8a0b5cb6d4d3e746890878dc448c1f0bc87417340e9dcecb8`.
- Training-plan decompressed SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- Report: `build/github-results/harmonic-setwise-learning-44965135706/artifact/harmonic-setwise-result/report/report.json`.
- Report SHA256: `43b65016f2073661540499843adf12137645e59ed79a62e408c0a8c7449834b9`.
- Small archive 14730923720: 25,729 bytes, SHA256 `2b9b7b1a96a3c487e15b76ff1140272b103e7218b8da5e4084718a6979b20c63`, server digest verified; collected once at 2026-11-22T00:12:37.851866+00:00.
- Bulk 14731416978 (`m3-harmonic-setwise-evidence-44965135706-1`): 6,951,749 bytes, remote; expires 2026-12-06T00:11:06Z. Do not collect without a named diagnosis.

## Next

Freeze a source-variation training design using training sources only. Preserve both held-out roles, all labels, the cutoff rule and every acceptance gate. Do not rerun or retune this rejected model; no next job queued.

A next design must improve source variation without fitting or selecting on either held-out pass. Acceptance remains the existing held-out gates, then continuous note/false-output/hold gates, then native real-time and host checks. No additional job was queued. Claude remains paused and supplied no new review for this experiment. The broader live-readiness goal remains active.
