# Spectral-patch recovery result — 2026-11-22

Claude: run45012604509 is final/success, report collected once and server digest verified. The model is rejected. Your independent lower-register work continues; this does not impose an acknowledgement or dispatch gate. Basic Pitch adaptation45016827324 is still fitting under its separate frozen protocol.

Source `02948b1123888904ded806d0f957b80c234af55c`; worker `b06510cd904fca80310f3813dfd60f755f3f3544`. Checkpoint `docs/recovery/github-harmonic-training-recovery-20261122.json`. Report `build/github-results/harmonic-training-recovery-45012604509/collected/harmonic-training-recovery-result/report/report.json`. Receipt in the same run directory. Model/checkpoint and prediction evidence remain remote; no extra download or rerun.

All80 fixed epochs completed in3277.76 seconds, final loss0.320822. One train-only cutoff0.5963748693, unchanged afterward. All555 original takes retained, source-disjoint passes200/200/155, no held-out fitting. Protocol and instrument/session are not independent and these development roles were previously examined.

| Role | Exact sets | Pitch precision | Pitch recall | Exact 3 / 4 / 5 pitches |
|---|---:|---:|---:|---:|
| Train | 15232/16384 =92.97% | 99.00% | 97.88% | 93.57 /89.45 /82.72% |
| Calibration | 2925/4096 =71.41% | 91.65% | 93.08% | 70.97 /60.79 /43.97% |
| Test | 1664/4096 =40.63% | 71.65% | 78.46% | 30.58 /19.07 /10.09% |

Silence extras are zero in all roles. These are synthetic-mixture pitch-set measurements, not labeled tuner frames, string assignments or delivered MIDI. Training complete-chord gate passes; both held-out gates fail. This is substantial fit without transferable quality at the frozen cutoff.

Single-pitch preservation independently fails: exact sets3115->3102/3132, extras13->30, missing5->1. Thus better recall trades against additional false pitches. The runner correctly stops before continuous-recording replay. Its single-line decision names singleton preservation, but the held-out failures independently reject the route. Installed output and all recorded scoreboard values remain unchanged.

Next: read the already-running pretrained adaptation against its unchanged TensorFlow baseline. Do not retune this frozen model on the held-out scores. If a new spectral design is considered later, it needs a concrete generalization mechanism rather than more epochs on this fit. Exact interruption/resume mechanics passed on GitHub, and this run retained complete-epoch state, but successful training infrastructure is separate from tracker acceptance.
