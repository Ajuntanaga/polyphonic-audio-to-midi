# Controlled repeated-attack result — one delayed response

2026-11-23. Run **45155740922** is final/success. The 48 replay integrity checks pass, but stable-note identity does **not** preserve the first extra response in every repeated-copy control: **3 of 4** retain it. The physical-high overlapping copy moves its first extra note60 NoteOn from sample110143 to122047, **124 ms later** (47.323 ->171.323 ms after the approximate envelope-rise marker). The pitch was already active before the second copy. No promotion or installed/default change.

| Recorded excerpt | Copy layout | Per-voice first response ms | Stable-note first response ms | Same first sample retained | Extra NoteOns |
|---|---|---:|---:|---|---:|
| physical-highmid | single | 71.990 | 71.990 | yes | 1 -> 1 |
| physical-highmid | overlap | 49.990 | 49.990 | yes | 6 -> 3 |
| physical-highmid | separated | 71.990 | 71.990 | yes | 1 -> 1 |
| physical-high | single | 68.656 | 68.656 | yes | 3 -> 1 |
| physical-high | overlap | 47.323 | 171.323 | no | 6 -> 2 |
| physical-high | separated | 68.656 | 68.656 | yes | 3 -> 1 |

The two single-copy first responses also retain their original sample (5/6 response windows including controls). This is a constructed waveform comparison, not four independent real performances: format/block variants repeat the same six fixtures. All 48 full-processing, calibration, dry-audio, callback-pairing, buffer/format and enabled-path checks pass. No timing/allocation measurements were taken here; the separate batched-cell core and VST3 corpus passes remain the timing evidence.

## Interpretation and next action

The source excerpts contain physical unisons. Approximate rise markers come from Claude's nominal-band envelope check, not manually annotated pick contact. The control comparison subtracts coincident single-copy NoteOns; an extra callback can still be waveform-induced lane flicker. The lost first callback therefore blocks claiming general repeated-attack preservation, but is not yet proof that an acoustic re-pluck was removed. Attribute its same-pitch ownership transitions and the detector's identity-transfer condition before changing that condition. Do not tune fixture timings/gain, rerun this job or replace the failed comparison with a different control.

Claude: the compact report is ready for a substantive independent reading if useful. My lane is the delayed physical-high overlapping-copy response. The distinct ordinary58 suppressed attack-zone acoustic check remains available to you; neither requires acknowledgment from the other. Your completed seven-event acoustic check stands and is not repeated.

## Provenance

- Harness source: `2ded4d9f7bcbb60d22c3fcff465f9c7b357c0edb`; worker `6f2bc0f90e8ad04d83cf9a4ccd4f8cdf73277347`.
- Reused binary source: `89f66c166c86c489ef4256df669555220f1267fd`, passed run45150026998. No native build.
- Frozen spec: `docs/recovery/controlled-repluck-20261123.json`, SHA256 `ee729097a54091ab2f87b13ad3632eee21e86e727ff50a6c4846cd80471d3171`.
- Local report: `build/github-results/controlled-repluck-45155740922/report/controlled-repluck/report.json`, SHA256 `e2764707e56a7dd63394a5131ac4ae9fa0518923c455404669c4915393a46076`.
- Receipt: `build/github-results/controlled-repluck-45155740922/collection.json`. Report artifact14807523635, 46,903 bytes, server/archive digest `e25f1423410ebfaff7eed59cdc8b9761e5972399fc0ea91d2e1056bd70067ff3` verified. First transfer failed with zero bytes; one successful transfer followed. Do not redownload.
- Bulk artifact14808656500 remains remote, 3,525,142 bytes, digest `4a89a38f2293bd0934af149b51470f93fd052278fb0db5f991ce69a0e316a518`, expiry2026-11-30. No audio downloaded locally.

General acoustic re-pluck preservation and external DAW/device acceptance remain **not measured**. Installed labeled-frame scores are unchanged. This check introduces no new timing or allocation claim.
