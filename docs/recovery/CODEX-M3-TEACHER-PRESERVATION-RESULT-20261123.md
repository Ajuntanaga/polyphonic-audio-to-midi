# Original-teacher preservation: rejected window screen — 2026-11-23

Run **45191602866** completed successfully, but the frozen scientific verdict is **REJECTED_WINDOW_SCREEN**. The candidate does not advance to export or continuous replay. This exact setting is closed: no retry or tuning. Installed output, defaults and scoreboard are unchanged.

The original model, the earlier rejected BCE epoch2 and the new teacher-preservation epoch2 were scored on the same 4096 train / 1024 calibration / 1024 test windows. These reuse previously inspected takes from the same instrument/session; they are not a new blind validation.

Counts below are distinct-pitch occupancy in nominal model frames (256/22050 seconds). Found/expected is note-frame recall, extras are separate. These are not tuner string-assignment scores, unison multiplicity, acoustic re-pluck preservation or delivered MIDI.

| Role / arm | Found / expected | Recall | Extra note-frames | Exact frames / all frames | Silence extras |
|---|---:|---:|---:|---:|---:|
| train / original baseline | 1,172,720 / 1,742,377 | 67.3058% | 330,539 | 248,719 / 704,512 | 915 |
| train / prior rejected | 1,500,246 / 1,742,377 | 86.1034% | 154,828 | 434,255 / 704,512 | 1,478 |
| train / teacher candidate | 1,430,917 / 1,742,377 | 82.1244% | 154,199 | 404,997 / 704,512 | 1,098 |
| calibration / original baseline | 258,837 / 375,035 | 69.0168% | 67,165 | 74,198 / 176,128 | 369 |
| calibration / prior rejected | 327,835 / 375,035 | 87.4145% | 32,016 | 120,046 / 176,128 | 588 |
| calibration / teacher candidate | 311,939 / 375,035 | 83.1760% | 29,795 | 113,874 / 176,128 | 476 |
| test / original baseline | 248,985 / 359,633 | 69.2331% | 133,479 | 60,426 / 176,128 | 363 |
| test / prior rejected | 247,210 / 359,633 | 68.7395% | 73,076 | 82,643 / 176,128 | 527 |
| test / teacher candidate | 253,491 / 359,633 | 70.4860% | 73,034 | 81,183 / 176,128 | 447 |

Test gain is **+4,506 found note-frames / +1.2529 percentage points**, below the frozen +5-point target. Extras fall by 60,445 (45.28%), and exact frames increase by 20,757. However, silence extras rise **363 → 447**, and **450/2638 test source occurrences** fail the loss budget, including **93 newly entirely missed occurrences**. Aggregate cleanup does not satisfy individual-note preservation.

| Candidate vs original | Source occurrences | Lose presence | Lose longest hold | Over budget | Newly entirely missed |
|---|---:|---:|---:|---:|---:|
| train | 11,358 | 698 | 710 | 445 | 52 |
| calibration | 2,455 | 129 | 131 | 75 | 4 |
| test | 2,638 | 536 | 548 | 450 | 93 |

The budget remains at most 25 ms **and** at most 5% loss in each occurrence’s own original present time and longest hold, with no newly entirely missed occurrence. Occurrences are placements of source takes in windows, not distinct takes. All three roles pass aggregate extra-note and exact-frame preservation, but all three fail silence and occurrence safety. Strict zero-loss and absolute representation targets also fail. Zero of three roles passes every safety clause.

Against the earlier rejected BCE candidate, the test result has +6,281 found frames, 42 fewer extra frames and 80 fewer silence extras, but 1,460 fewer exact frames. This comparator does not replace the original baseline or change earlier rejection decisions.

All five integrity checks pass; original note/onset/contour outputs are bit-identical after restoring the original weights. The worker passed 19 tests, including the actual TensorFlow gradient and optimizer contracts. The one fit completed two epochs / 2,048 batches; 18 variables changed. Cached teacher targets stayed unchanged. The teacher penalty reduced drift from the original outputs, but it did not preserve every occurrence. It does not establish acoustic onset preservation; comparison with the prior fit is also not a KL-only ablation.

No new native, VST3, allocation, deadline, external device or live-guitar acceptance is measured by this model-window screen. Earlier batch-cell core/component/REAPER passes remain separate. Claude’s seven-event acoustic result and the untested ordinary 58-event set remain a separate articulation lane.

Provenance and collection:

- [GitHub run](https://github.com/Ajuntanaga/m3-offload/actions/runs/45191602866); source `886caf279463eefbfad3081975d3f41cbd1f2ade`, worker `83506417e2ae5658ea572c83eb1a054a4ab9c93a`.
- Spec `docs/recovery/basic-pitch-teacher-adaptation-20261123.json`, SHA-256 `6836721dcb8fbcc2d4e799f8cbde4e91da5552799db23a7955b19cfb4d18caa9`.
- Report `build/github-results/basic-pitch-teacher-adaptation-45191602866/report/basic-pitch-teacher-adaptation-result/report/report.json`, SHA-256 `103913a6190ee77e86bd98bf58c9b85332f1c40e1baa07c0696079c58c2f7c94`; full per-occurrence deltas retained locally.
- Small artifact `m3-basic-pitch-teacher-adaptation-report-45191602866-1`, id `14830368304`, 168,549 bytes, collected once; server/archive SHA-256 `072d353db5bb240fdf2ef6868400c3bbe4c30491c8cdf15deb65a616e67d76e4` verified.
- Bulk artifact `m3-basic-pitch-teacher-adaptation-evidence-45191602866-1`, id `14831781597`, 1,798,122,907 bytes, remains remote; expires 2026-12-07T15:00:21Z. Its server digest is `sha256:8b5ae0c3ffeccf84397ee68bf7169a0d5fd5a28980d2d2e451ff4cc8699029e3`; bulk bytes were not locally downloaded or verified.
- Epoch2 `epoch-2.npz`, 193,295 bytes, SHA-256 `691a1e6765de8a942c4eb66c0fdd63a44cb55cade121d70b87216da7c0e0cd83` (worker report).
- Receipt `build/github-results/basic-pitch-teacher-adaptation-45191602866/collection.json`. Fit/screen elapsed 47.71 minutes. No repeated processing is required.

Next: keep this setting closed. A distinct design must address note losses and silence output together before another acceptance screen; neither loss-budget relaxation nor installed promotion follows from this result.
