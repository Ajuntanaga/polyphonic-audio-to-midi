# Complete-set training loss: chord gain, fixed gate rejected

Run [44962588969](https://github.com/Ajuntanaga/m3-offload/actions/runs/44962588969) completed successfully. The frozen research screen is rejected: complete five-pitch training mixtures reach **1759/2529 (69.5532%)**, below the fixed target of **1771/2529 (at least 70%)**. Both held-out roles and continuous ordinary/middle replay were skipped as specified. Installed output, defaults, labels and scoreboard remain unchanged.

## Measured result

Only the loss changed from run44960075844: mean pitch BCE plus an equally weighted per-mixture weakest-true/strongest-false logistic term. The architecture, features, source roles, mixture plan, initialization/order seed, optimizer, 80-epoch schedule and training-only cutoff selection rule stayed fixed. The decompressed training plan has the same SHA-256 as the baseline. One 14,465-parameter fit took 179.89 seconds on one GitHub CPU thread. The new cutoff is 0.4006813168525696; it was selected on training data under the unchanged >=99% precision rule, not adjusted after rejection.

Expected training pitches rise from BASELINE **43101/45698 (94.3170%)** to CURRENT **43654/45698 (95.5272%)**, a gain of 553. False pitches rise **433 to 440 (+7)**; precision is **99.0054% to 99.0021%**. Complete sets rise **13865/16384 (84.6252%) to 14466/16384 (88.2935%)**. All 820 silence examples still produce zero false predictions. These are sustained training-mixture pitch counts, not labeled-frame/string scores or delivered MIDI.

| Distinct pitches | BASELINE complete sets | CURRENT complete sets | Count change |
| --- | --- | --- | --- |
| 1 | 3108/3132 (99.2337%) | 3097/3132 (98.8825%) | -11 |
| 2 | 3043/3220 (94.5031%) | 3069/3220 (95.3106%) | +26 |
| 3 | 2832/3251 (87.1117%) | 2946/3251 (90.6183%) | +114 |
| 4 | 2515/3432 (73.2809%) | 2775/3432 (80.8566%) | +260 |
| 5 | 1547/2529 (61.1704%) | 1759/2529 (69.5532%) | +212 |

Three- and four-pitch training gates pass; five pitches is the sole failed training gate. The integer five-pitch target is 1771/2529 (70.0277%). Progress toward that gate is **1759/1771 = 99.3224%**, with **12 sets / 0.4745 percentage points** remaining. This is one training-gate ratio, not project completion. Single-pitch complete sets decline by eleven despite the chord gains; the false-pitch rise is also retained in the record. The training precision floor is met, but neither tradeoff establishes safety on continuous audio.

The controlled comparison supports a better chord fit from this objective on this fixed configuration. It does not establish transfer: calibration and test scoring were not run, and no fresh continuous or protected-corpus replay occurred. All 555 intended-label source excerpts remain, split 200 training / 200 calibration / 155 test, with no original excerpt crossing roles. Unresolved source-content disagreements remain. Sustained mixtures do not prove attacks, decays, string assignment, unison multiplicity, false-note lifecycle or reliable live performance. The 170.67 ms trailing context is not a measured pluck-to-MIDI latency.

## Provenance and checks

- Source `f6d3fb3e7796f1734a96597e8eda4aaeae7a50d1`; worker `953f3be4b5a5b98b19d5c59df761197fc0b9954c`.
- Specification SHA-256 `20340fd1a644ec8dec4e3118953f34fe93859f7ade6018e3049b95df5f2ea1cc`.
- Training-plan identity verified: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
- Source CI44962573168 passed; **60/60 GitHub synthetic checks passed**, zero skips. Local check: 51 passed, nine deferred to GitHub. One focused review completed before dispatch. These checks establish experiment execution, not live acceptance.
- Model SHA-256 `8b87fd241231379106b5ba9103ca71328eef2701ad86f549235dd27eb6c3cf25`; one fit, weights/scaler/cutoff saved before the skipped held-out stage.
- Small artifact `m3-harmonic-complete-set-report-44962588969-1`, id14730670654, 17087 bytes, collected once and server-digest verified: `65a913a254725a1e11695a90e63f2444106a9b5745ec1926f4047b118a4260c4`.
- Report `build/github-results/harmonic-complete-set-learning-44962588969/artifact/harmonic-complete-set-result/report/report.json`; SHA-256 `e21c4284ab15f2c23fb53988d3eba5c8ce29c1cf18b07181fa6f72f7b807251c`. Receipt `build/github-results/harmonic-complete-set-learning-44962588969/collection-receipt.json`.
- Bulk `m3-harmonic-complete-set-evidence-44962588969-1`, id14730172985, 4574244 bytes remains remote until 2026-12-05T23:40:31Z; digest `sha256:a23bc1cdf58e1d03b6d0ad8c6c90c05bafa6dd35dcd554c4c085975eb350f209`. Do not poll, redownload, rerun or retune this completed job.

## Next

Compare the retained training errors against the baseline, including the eleven fewer complete single-pitch sets, before selecting a distinct design. Preserve this rejection, cutoff, source labels and all safety gates; no automatic rerun or held-out tuning. A later candidate still needs the 70% complete-set training gates, both untouched roles and continuous benefit without per-label or false-output regression. No next job queued.

Claude is paused; no fresh Claude analysis is claimed. Claude's 69 files are already published in `63416f8ed4af2535b1923304a6de2d49340d71e0`. The prior eight-hour interval is complete. The broader live-readiness goal remains active; overall completion is not measured.
