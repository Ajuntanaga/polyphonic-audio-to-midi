# Fixed spectral whitening: rejected at the training gate

Run [44977024530](https://github.com/Ajuntanaga/m3-offload/actions/runs/44977024530) completed successfully, but its research screen is **rejected**. Five-pitch exact sets fell from **1818 to 1763/2529 (71.89% to 69.71%)**. The frozen gate requires **1771/2529** (the integer count for at least 70%): eight additional complete sets were needed. Held-out and continuous stages were skipped by the recorded protocol. Installed/default output and the installed scoreboard are unchanged.

## Result

An exact set contains every expected pitch and no extra pitch. These are sustained training-mixture results, not labeled tuner-frame matches or delivered-host MIDI.

| Distinct pitches | BASELINE exact sets | CURRENT exact sets | Change in sets |
| --- | --- | --- | --- |
| 1 | 3115/3132 (99.46%) | 3107/3132 (99.20%) | -8 |
| 2 | 3084/3220 (95.78%) | 3078/3220 (95.59%) | -6 |
| 3 | 2954/3251 (90.86%) | 2912/3251 (89.57%) | -42 |
| 4 | 2806/3432 (81.76%) | 2709/3432 (78.93%) | -97 |
| 5 | 1818/2529 (71.89%) | 1763/2529 (69.71%) | -55 |

Across all 16384 training mixtures, expected pitches found fell **43827 to 43594/45698 (95.91% to 95.40%)**, missing pitches rose **1871 to 2104**, and extra pitches rose **439 to 440**. Exact sets fell **14597 to 14389/16384 (89.09% to 87.82%)**. Silence remained **0 false outputs across 820 mixtures**.

The training-only cutoff was selected once by the unchanged rule (maximum true positives at at least 99% precision; stricter tie): 0.5343895554542542 in the baseline and 0.6791843771934509 here. No held-out cutoff fitting or tuning was performed. The five-pitch gate progress is **1763/1771 = 99.55%**, with **8 sets / 0.32 percentage points** remaining to that integer-count target; this is one failed gate, not project completion.

## Scope and provenance

The only representation change was fixed frame-local critical-band partial whitening before the same 62 harmonic coordinates. Original waveform RMS coordinates, architecture, setwise loss, optimizer, seed, 80 epochs, mixture construction and all acceptance gates were preserved. The frozen design is `CODEX-M3-HARMONIC-WHITENING-PLAN-20261121.md`; the specification is `harmonic-whitening-20261121.json`.

- Source: `d7aee42e6c4c5155b2ba9dab4b765f1149992b85` in `Ajuntanaga/polyphonic-audio-to-midi`.
- Worker: `7120da877f10022920cc2d3f7453c28ac7565094` in `Ajuntanaga/m3-offload`, `harmonic-whitening.yml`.
- Baseline: run44965135706, source `6b4d39aa8b308ce8f808486b345dbe865b1bb4a0`, report SHA256 `43b65016f2073661540499843adf12137645e59ed79a62e408c0a8c7449834b9`.
- All **555 original labels** retained: train200, calibration200, test155; no source-role overlap or content-based exclusion.
- Training-plan decompressed SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` verified against the pinned original plan.
- One fit, 14465 parameters, 150.783 seconds. Model SHA256 `96fc49eb97bac76a05804640365493e8bed843f7c0bda82524f5b4a7828aa6be`.

## Verification and retained evidence

The GitHub screen passed **104 synthetic/unit tests**, including the Torch architecture/serialization check skipped locally. Source CI [44976965511](https://github.com/Ajuntanaga/polyphonic-audio-to-midi/actions/runs/44976965511) passed. The completed workflow and passing checks establish execution and test success; they do not override the failed training gate.

The small report archive `m3-harmonic-whitening-report-44977024530-1` (artifact14736108870, 17689 bytes) was collected once at `2026-11-22T02:43:27.094332+00:00`. Server and local archive SHA256 agree: `d5616ff9bfc2b1971a816e31de7e1c63ec78fc9c9e9d78ce915e7f1fac70d309`.

Report: `build/github-results/harmonic-whitening-44977024530/artifact/harmonic-whitening-result/report/report.json`, SHA256 `2790401c3b8230b481509ec75dccdcb001492bbc65e4913ab7ac05fce857be2f`. The adjacent `collection-receipt.json` and `baseline-comparison.json` retain collection and comparison details.

Bulk artifact `m3-harmonic-whitening-evidence-44977024530-1` (artifact14736073835, 4652653 bytes, SHA256 `0146751470275ecca6b929c4c8aeb124843235e7313f04c3721ea4a1abee23e5`) remains remote and expires on 2026-12-06. Do not redownload, poll or rerun completed work.

## Limits and next step

The result rejects this fixed whitening configuration before transfer was measured. It does **not** measure its held-out transfer, continuous false-note behavior, string assignment, unison multiplicity, attack/decay handling, native deadlines or external DAW/device delivery. Development source roles have been used previously; they are not an untouched final benchmark.

Select a distinct evidence-supported source-transfer mechanism before another fit. Keep all 555 labels and the existing gates; do not tune or rerun this rejected whitening screen. No next job is queued. The broader live-readiness goal remains active; overall completion is not measured. Claude remains paused.
