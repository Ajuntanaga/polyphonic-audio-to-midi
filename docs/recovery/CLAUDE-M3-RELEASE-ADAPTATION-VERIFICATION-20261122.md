# Independent check of the release-context adaptation result against its saved report

Claude, 2026-11-22. Checked `CODEX-M3-RELEASE-ADAPTATION-RESULT-20261122.md` against the locally collected report (`build/github-results/basic-pitch-release-adaptation-45037966575/artifact/.../report/report.json`, 450,064 bytes), `prior-signature.json`, `tests.log`, `small-report-collection.json` and the repository's validator constants. Read-only; no script, job or rerun; nothing changed.

## Answer

**Every figure I checked matches the saved report, and the rejection follows from the report's own gates.** I found no discrepancy and no overstatement in the note.

## What I compared

| Claim in the note | Report value | Match |
|---|---|---|
| Train: expected 1,742,377; found 1,500,247 → 1,560,054 (86.10 → 89.54%); extras 154,829 → 234,932; exact sets 434,254 → 426,090 of 704,512 frames | same (found 86.1035 → 89.5360%) | yes |
| Calibration: 375,035; 327,835 → 338,577 (87.41 → 90.28%); extras 32,016 → 48,524; exact 120,046 → 116,988 of 176,128 | same | yes |
| Test: 359,633; 247,210 → 263,782 (68.74 → 73.35%); extras 73,075 → 100,436; exact 82,643 → 79,995 of 176,128 (46.922 → 45.419%) | same | yes |
| Test found +16,572 (+4.608 pts), extras +27,361 | 263,782 − 247,210; 73.3476 − 68.7395; 100,436 − 73,075 | yes |
| Silence extras on test 527 → 1,163 | `by_pitch_count[0].extra_note_frames`, prior vs release | yes (train 1,478 → 2,559 and calibration 588 → 907 also grow) |
| Occurrences losing presence / longest: 177 / 179 of 11,358 (train), 33 / 34 of 2,455, 35 / 36 of 2,638 (test) | `paired.prior` | yes |
| Every split fails the representation and occurrence-preservation gates | `representation_pass` False and `no_occurrence_loss` False in all three roles | yes |
| 3,072 batches over two epochs; 555 takes retained (200 / 200 / 155) | 1,536 + 1,536; `retained_takes` | yes |
| `epoch-2.npz` 142,881 bytes, SHA256 `e64ce160…ef02b0` | `training.epochs[1].checkpoint` | yes |
| 22 remote tests passed | `tests.log`: "Ran 22 tests … OK" | yes |
| Original outputs restored bit-identically | `original_restore_output_identity` note, onset, contour True | yes |
| 53,034-byte report with verified server SHA256 | `small-report-collection.json`: download digest equals server digest `fb73f0d9…` | yes |
| Crop stage failed on interface: export has `audio:0` and `Identity:0` / `Identity_1:0`, validator wants `serving_default_input_2:0` and `StatefulPartitionedCall:1` / `:2` | `prior-signature.json` shows the first set; the second set is in `tools/portable_mixed_level_probe.py`, `tools/neural_adapter_fixtures.py`, `tools/basic_pitch_onnx_export.py` and `tools/neural_crop_model.py` | yes |

## Two things worth keeping in view (not errors)

- The note's trade is real and consistent across all three splits: recall rises (test 68.74 → 73.35%) while precision falls (77.18 → 72.42%), exact sets fall, and silence extras roughly double on test (527 → 1,163). The adaptation buys detection with false output, which is the false-output / held-note trade-off the next step has to address.
- The note correctly says the extra training windows mean the change cannot be attributed to release examples alone. I agree and have nothing to add; this check cannot separate them either.

## Limits

I verified the note against the saved report; I did not re-derive the report from audio, and the 929 MB evidence archive was not downloaded. The node-count and crop-target question the note leaves unmeasured stays unmeasured. Nothing here changes the rejection, the installed outputs or any gate.
