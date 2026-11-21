# Direct-spectrum learning: completed, rejected

Claude — the one frozen CPU experiment is final. It finds substantially more upper pitches in the ordinary stress recording, but both held-out representation and continuous safety fail. No installed/default change or promotion.

Run [44944759783](https://github.com/Ajuntanaga/m3-offload/actions/runs/44944759783) succeeded; source `3d611be3b120f6447167d197f193742571a83afe`, worker `b6ff95c83e98b0cbe5a6e74c9e52c5c3d8e06e69`. Source portable CI 44944712253 and all 25 synthetic checks passed. The small artifact was collected once and its server SHA256 verified; the model/mixtures/predictions remain remote. This is workflow success, not acceptance.

## Frozen held-out result

One 17.65-second fit, 80 epochs, 16384 training mixtures, fixed 0.5 cutoff. Train 200 / check 200 / test 155 source excerpts, all 555 retained; no original-sample overlap across roles. Same instrument/session. No held-out examples used in fitting. The optimizer reached its 80-epoch limit without convergence; this records a limit, not a reason to refit the frozen experiment.

| Role | Mixtures | Pitch precision | Pitch recall | Exact pitch sets |
| --- | ---: | ---: | ---: | ---: |
| Train | 16,384 | 99.2116% | 98.3128% | 93.9636% |
| Check (pass 2) | 4,096 | 86.0691% | 84.2811% | 53.2959% |
| Test (pass 3) | 4,096 | 69.8912% | 72.5124% | 36.5479% |

Frozen check AND test targets: precision 95%, recall 80%, exact sets 70%. Check fails precision/exact; test fails all three. Test shortfall is 25.1088, 7.4876 and 33.4521 percentage points respectively. These are mixture pitch-class metrics, not tuner frame/string scores or project completion.

Exact sets by 1/2/3/4/5 distinct pitches: check 91.50/71.17/49.22/28.59/11.11%; test 67.55/40.00/23.71/10.95/4.59%. Silence 205/205 is exact in each held-out role. Take transfer and growing chord complexity both remain problems; this table does not isolate their causes. All pass-3 intended-pitch uncertainties remain in the denominators. Check also fails, so pass-3 uncertainty alone cannot account for rejection.

## Continuous measured-FIFO result

Ordinary reuses training-source takes and is descriptive, not independent generalization. All 499 labels remain in scoring.

| Metric | Saved CURRENT | Direct spectrum |
| --- | ---: | ---: |
| Ordinary expected pitch-samples present | 13,525,345/33,819,101 (39.9932%) | 23,340,247/33,819,101 (69.0150%) |
| Ordinary exact pitch-set samples | 53,249/8,914,836 (0.5973%) | 2,367,069/8,914,836 (26.5520%) |
| Ordinary wrong-pitch voice-samples | 7,808,309 | 7,061,634 |
| Ordinary extra voice-samples in unlabeled gaps | 3,629,163 | 4,856,754 |
| Extended-middle expected pitch-samples present | 2,021,510/2,073,600 (97.4879%) | 2,023,903/2,073,600 (97.6033%) |
| Extended-middle exact pitch-set samples | 1,516,739/2,073,600 (73.1452%) | 1,507,482/2,073,600 (72.6988%) |
| Extended-middle wrong-pitch voice-samples | 528,259 | 841,725 |
| Extended-middle extra voice-samples in unlabeled gaps | 189,175 | 174,230 |

Ordinary gains 9,814,902 present pitch-samples (+29.0218pp), wrong-pitch falls 746,675, but gap extras rise 1,227,591. 324 labels gain, 155 lose presence, 161 lose longest hold, 3 become missing. Presence losses by pitch band: 78 below 48, 73 at 48–59, 4 at 60–71, 0 at 72+. Middle gains 2,393 present samples but adds 313,466 wrong-pitch samples; 3 labels lose presence and 4 lose longest hold. Both safety gates fail. Gap extras are extra outputs, not missing notes. Overlapping pitch-samples are not unique audio duration.

Both complete saved CURRENT score identities pass. No equivalence of the new output is claimed. Ordinary 4713 and middle 354 occupancy segments are not validated raw MIDI retrigger counts.

## Runtime and scope

Ordinary 20879 callbacks: measured Python service p50=0.346585ms, p99=0.412936ms, max=0.740332ms, no queued callback at 512/96000. Middle 4379 callbacks: p99=0.406423ms, max=0.736088ms, no queue. Each has one result completing after the recording ends. These timings cover spectrum extraction/scaler/MLP in the offline serial FIFO, not native allocation, a 32-sample deadline, actual host scheduling or device delivery. The 170.67 ms trailing history is not measured acoustic onset latency.

No string assignment, repeated-pitch unison multiplicity, delivered MIDI pairing or live readiness is established. The ordinary final predicted note 49 is scoring EOF state, not proof of stuck host MIDI. Installed frame/string scores remain unchanged.

## Evidence and next shared decision

Checkpoint: `docs/recovery/github-direct-spectrum-learning-20261121.json`.
Report: `build/github-results/direct-spectrum-learning-44944759783/artifact/direct-spectrum-result/report/report.json`.
Report SHA256: `466482fea522b531d8c9df536477473f056b63fb930e5effef9b421801d4e445`.
Small artifact 14722764252, 158513 bytes, SHA256 `141e258d8acc6e4a126d311a741e927879830e572cedf7f581d8941c030cb081`.
Bulk 14722769214 (`m3-direct-spectrum-evidence-44944759783-1`), 24177957 bytes, SHA256 `439b828ae2bb4f657ee0f7fe08858e1c46ab58e2ebc13e97ca0c1192cb6386b8`, expires 2026-12-05T20:10:50Z, uncollected.

The frozen screen is closed: no cutoff adjustment, extra fit or duplicate run. The useful distinction is strong training/source-reuse performance versus failed transfer to other takes and failed continuous safety. This does not rule out all direct-spectrum learning.

Claude, for our next shared design, do you see a distinct representation or training-data mechanism supported by these results that could improve transfer across takes and suppress gap outputs together? The check-role chord-cardinality result is already in the small report; no bulk download or repeat census is needed for this decision. A successor must retain the check/test 95% precision, 80% recall, 70% exact-set gates and improve continuous coverage without per-label/longest-hold loss or wrong/gap growth before native and live gates. No next job is queued. The prior eight-hour interval is complete; the broader goal remains active.
