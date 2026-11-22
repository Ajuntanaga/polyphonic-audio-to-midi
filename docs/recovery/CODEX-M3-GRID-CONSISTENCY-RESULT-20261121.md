# Feature-grid consistency: training instability, screen rejected

Run [44980872011](https://github.com/Ajuntanaga/m3-offload/actions/runs/44980872011) completed successfully, but the research screen is **rejected at the training gate**. Training loss rose sharply at epoch 23 and ended at **4.668e12**. No training cutoff met the required 99% pitch precision. The existing fail-closed cutoff fallback is above the probability range and emitted no pitches; this is not a usable operating threshold or an installed-tracker result. Held-out calibration, test and continuous replay were skipped. Installed/default output and the scoreboard are unchanged.

## Measured result

These are sustained sampled pitch sets, not tuner-frame string assignments or delivered-host MIDI. An exact set contains every expected pitch and no extra pitch. BASELINE is setwise run44965135706; CURRENT is this offline trial at its infeasible-cutoff fallback.

| Training measure | BASELINE | CURRENT |
| --- | --- | --- |
| Expected pitches found | 43827/45698 (95.91%) | 0/45698 (0%) |
| Extra pitches | 439 | 0 |
| Missing pitches | 1871 | 45698 |
| Complete sets | 14597/16384 (89.09%) | 820/16384 (5.00%) |

All 820 CURRENT exact sets are silence. Every non-silent set fails; zero extra outputs here is not a safety improvement.

| Distinct pitches | BASELINE exact sets | CURRENT exact sets | Change |
| --- | --- | --- | --- |
| 1 | 3115/3132 (99.46%) | 0/3132 (0.00%) | -3115 |
| 2 | 3084/3220 (95.78%) | 0/3220 (0.00%) | -3084 |
| 3 | 2954/3251 (90.86%) | 0/3251 (0.00%) | -2954 |
| 4 | 2806/3432 (81.76%) | 0/3432 (0.00%) | -2806 |
| 5 | 1818/2529 (71.89%) | 0/2529 (0.00%) | -1818 |

Five-pitch TARGET is ceil(70% x 2529) = **1771 sets (70.03%)**. CURRENT is 0/2529; PROGRESS 0/1771 = 0%; GAP 1771 sets / 70.03 percentage points. This is one failed training gate, not overall project completion. Held-out denominators and scores for this trial are not measured.

## Training behavior

| Epoch | Total loss |
| --- | --- |
| 20 | 0.992244 |
| 21 | 1.162426 |
| 22 | 1.224565 |
| 23 | 234.725071 |
| 24 | 627994.609959 |
| 25 | 31626460.289063 |
| 80 | 4668089708544 |

Final supervised loss is 1667754949832 and consistency loss is 3000334753792. Full curves are retained in the report. This establishes optimization instability in this run; its cause has not been isolated. No best-epoch selection, cutoff retuning or refit was performed.

The cutoff rule remained maximum training true positives at >=99% pitch precision, choosing the stricter tie. BASELINE cutoff 0.5343895554542542 was feasible. CURRENT fallback 1.0000000000000002 is explicitly marked `feasible=false`. Zero-output scores describe that fallback; they do not prove that all raw model probabilities are zero.

## Frozen scope and provenance

The sole change adds a training-only consistency loss to the original setwise supervision. A normalized 53x62 feature grid is shifted by one pitch row with zero fill and no wrap. The same network processes both grids; shifted logits at rows 1..52 are compared with detached original logits at rows 0..51 using mean Huber loss, delta 1 and weight 1. Architecture (14465 parameters), seeded initialization, optimizer, all 80 epochs, mixture plan, labels, acceptance gates and inference are unchanged. Training uses two forwards per optimizer step; inference uses one. One fit took 206.719 seconds, with 16384 mixtures and 10240 optimizer steps.

This is a feature-grid translation, not physical audio transposition; source and FFT signatures move with the rows. The failed fit cannot resolve whether this constraint would improve held-out source transfer under a stable optimization procedure.

- Source: `78e9d130ec448f3d1c414695f4b91ef7126a1ca1`, `Ajuntanaga/polyphonic-audio-to-midi`.
- Worker: `268505117e48da91a29d602aecbe8229a452e107`, `Ajuntanaga/m3-offload`, `harmonic-grid-consistency.yml`.
- Specification: `harmonic-grid-consistency-20261121.json`, SHA256 `e97317ff026bfdf12ad44aef2941ab734fa19cb33b430ff1cafbb4a7f79a353b`.
- BASELINE run44965135706, source `6b4d39aa8b308ce8f808486b345dbe865b1bb4a0`, report SHA256 `43b65016f2073661540499843adf12137645e59ed79a62e408c0a8c7449834b9`.
- All **555 original labels** retained: train200, calibration200, test155; no cross-role source overlap or content-based exclusions. The split is by recording pass/source excerpt; protocol, instrument and session are not independent.
- Original decompressed training-plan SHA256 `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d` verified.
- Persisted model SHA256 `d99e4e55ce157299edfd54c76da0b1aabf8bd8a20f2f7b0e16dd9a5d02a62311`; one fit, no held-out fitting or scoring.

## Verification and retained evidence

All **116 GitHub synthetic/unit tests** passed in 4.167 seconds. Source CI [44980841745](https://github.com/Ajuntanaga/polyphonic-audio-to-midi/actions/runs/44980841745) passed. Before dispatch, three local synthetic/spec checks, four-file AST parsing and one focused static review passed; four Torch checks were deferred to GitHub. These checks verify implementation mechanics and do not establish numerical training stability, which this run failed to retain.

Small artifact `m3-harmonic-grid-consistency-report-44980872011-1` (14737862271, 18001 bytes) was collected once at `2026-11-22T03:36:24.603571+00:00`. Server and local archive SHA256 agree: `93d8a2391f13ee2fd8b9038fde4d55b66a0fe4003149abeb24e0cf08146a107c`.

Report: `build/github-results/harmonic-grid-consistency-44980872011/artifact/harmonic-grid-consistency-result/report/report.json`, SHA256 `45445998418da70fc4f009d40b481cbcc166633658ccf02bbd6ee6975fd1814c`. Adjacent `collection-receipt.json` and `baseline-comparison.json` preserve receipt and exact comparisons.

Bulk artifact `m3-harmonic-grid-consistency-evidence-44980872011-1` (14737862275, 950905 bytes) remains remote, SHA256 `b460f97413e2943b7a26dfbbff26bbe52ba3d901180cb19bdb11510648297c9c`, expires `2026-12-06T03:34:16Z`. Do not poll, redownload or rerun this final screen.

## Next

Diagnose the optimization instability from the retained loss curves and configuration before proposing any distinct new fit. Preserve all original labels and gates; do not rescue this rejected run with a tuned cutoff, selected epoch or automatic rerun. No next job is queued.

Continuous tracking, string assignment, unison multiplicity, false-gap output, attacks/releases, native allocations/deadlines and live DAW/device delivery were not measured for this trial. Earlier corpus protections do not certify this model. Reliable live use remains unverified; overall completion is not measured. The broader goal remains active. Claude remains paused; no fresh Claude review is claimed.
