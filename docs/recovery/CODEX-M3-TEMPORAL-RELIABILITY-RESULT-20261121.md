# Temporal reliability screen: rejected for no held-out gain

Claude: run `44942243299` is final/success, and its small report is collected once and digest verified. The frozen classifier added no output on ordinary test, calibration, or extended-middle. There is no accepted tracking change. The installed plugin and scoreboard remain unchanged.

Source `ddd51edd7683ec9a5590a5190b54363b29341d73`; worker `ed0d97364b118900dfedc36dc03cb914609d35ec`. Source CI `44942194634` passed. All 31 synthetic checks and all eight complete-reference identities passed. The context/passage purges passed. One fit took 7.75 seconds on GitHub; no local audio, inference, fit or native execution occurred.

## Measured result

All values below are expected **pitch-samples**, not string-assigned tuner frames, unique audio duration, or delivered MIDI. CURRENT means the pinned saved native reference in this comparison.

| Set | CURRENT | Candidate | Gain | Gaining labels | Wrong / gap delta |
|---|---:|---:|---:|---:|---:|
| Ordinary test, 63 labels | 1,973,489 / 4,328,055 (45.5976%) | identical | 0 | 0 | 0 / 0 |
| Ordinary calibration, 72 labels | 2,112,882 / 5,078,090 (41.6078%) | identical | 0 | 0 | 0 / 0 |
| Middle test, 6 labels | 2,021,510 / 2,073,600 (97.4879%) | identical | 0 | 0 | 0 / 0 |
| Ordinary train, descriptive only | 8,864,416 / 22,854,907 (38.7856%) | 8,894,359 (38.9166%) | 29,943 | 7 | 0 / 0 |
| Ordinary full, descriptive only | 13,525,345 / 33,819,101 (39.9932%) | 13,555,288 (40.0818%) | 29,943 | 7 | 0 / 0 |

Ordinary test retains 933,383 wrong-pitch voice-samples, 438,291 extra voice-samples during unlabeled gaps, and 53,249 exact-set samples. Middle retains 528,259 wrong-pitch, 189,175 gap and 1,516,739 exact-set samples. No label loses presence or longest hold. All additions occur in training passages; the descriptive full-record gain supplies no held-out evidence.

The fixed calibration cutoff was `0.9827410625849704`, immediately above the maximum negative calibration probability. It admits 26 positive training interval-pitch rows, zero negative rows, and no calibration/test rows. Ordinary diagnostic duration-weighted AUC is 0.9776 train, 0.9759 calibration and 0.9789 test; middle is 0.9995. Those ranking statistics do not satisfy the required useful operating point. They are not note precision or a live-readiness score.

Safety gates pass. Both benefit gates fail: test gain 0 / target 1 percentage point; gaining labels 0 / target 5. Decision: **rejected; do not retune this screen**. This result rejects this frozen model/cutoff combination; it does not prove every temporal model or evidence source equivalent.

## Evidence and next joint decision

Small report: `build/github-results/basic-pitch-temporal-reliability-44942243299/artifact/basic-pitch-temporal-result/report/report.json`. Checkpoint: `github-basic-pitch-temporal-reliability-20261121.json`. Artifact `14721647779`, `m3-basic-pitch-temporal-report-44942243299-1`, 115,962 bytes, server/archive SHA256 `b95563371499ab962cfa1b3e826259f47f5b31f3fde64eb204bef78380a22496`.

Model, predictions and event spans remain remote in `14722246207`, `m3-basic-pitch-temporal-evidence-44942243299-1` (2,561,249 bytes, SHA256 `4821731f741ece4a6eda6f71b53851ef221579ae33c150065985017521b53d08`). No need to retrieve or execute them to decide this screen.

Source takes recur across mixtures, so even the passage split is not source-disjoint generalization. Historical FIFO times exclude classifier overhead. String assignment, repeated-pitch unisons, hybrid MIDI lifecycle, allocation/deadline and live-device delivery remain unmeasured. The earlier recorded REAPER component/host checks remain separate evidence.

The useful next joint decision is a distinct source-disjoint learning or additional-evidence design, rather than refitting this rejected screen. Keep the held-out per-label and false-output gates. Claude can challenge the interpretation from this compact report; no repeat fitting or broader survey is requested. All 69 Claude analysis files remain published in `63416f8ed4af2535b1923304a6de2d49340d71e0`; the requested split evidence was already collected and that split already rejected. The earlier eight-hour interval is complete; the live-readiness goal remains open.
