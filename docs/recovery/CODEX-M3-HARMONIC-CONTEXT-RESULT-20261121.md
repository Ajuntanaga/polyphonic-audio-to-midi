# Harmonic context model: training gain, five-pitch gate rejected

Run [44960075844](https://github.com/Ajuntanaga/m3-offload/actions/runs/44960075844) completed successfully. The frozen research screen is rejected because complete five-pitch training sets reach 61.1704%, below the 70% target. The other training gates pass. Both untouched roles and continuous ordinary/middle replay were skipped as specified. Installed output, defaults, labels and scoreboard remain unchanged.

## Measured result

One fit used 16,384 sustained mixtures, 868,352 candidate rows, 62 harmonic coordinates per pitch and 14,465 parameters. It ran 80 epochs in 184.16 seconds on one GitHub CPU thread. The training-only cutoff is 0.7022203803062439; no held-out data selected weights, normalization or cutoff.

Training expected-pitch recall rises from BASELINE 35,732/45,698 (78.1916%) to CURRENT 43,101/45,698 (94.3170%). False pitches rise from 360 to 433 (+73), with precision 99.0025% -> 99.0054%. Complete sets rise from 9,499/16,384 (57.9773%) to 13,865/16,384 (84.6252%), including 820 silence examples with zero false predictions in both screens. These are training mixture pitch counts, not installed labeled-frame/string matches or delivered MIDI.

| Training stratum | BASELINE independent classifier | CURRENT context model | TARGET complete sets | STATUS |
| --- | --- | --- | --- | --- |
| 3 pitches | 1757/3251 (54.0449%) | 2832/3251 (87.1117%) | 2276/3251 (>=70%) | PASS |
| 4 pitches | 1006/3432 (29.3124%) | 2515/3432 (73.2809%) | 2403/3432 (>=70%) | PASS |
| 5 pitches | 355/2529 (14.0372%) | 1547/2529 (61.1704%) | 1771/2529 (>=70%) | FAIL; 224 sets short |

The five-pitch integer target is 1,771/2,529 (70.0277%); CURRENT 1,547/1,771 = 87.3518% of that target, with 224 sets / 8.8573 percentage points remaining. This is progress toward one training gate, not project completion. Single-pitch complete sets are 3,108/3,132 (99.2337%); two-pitch sets are 3,043/3,220 (94.5031%).

The comparison supports a better training fit from this configuration. Context, capacity and optimizer changed together, so it does not isolate context as the cause. Transfer to untouched takes was not measured. Harmonic-related training mixtures have 69.4606% complete sets versus 91.5850% for the other stratum; chord-size composition differs and the latter includes silence/single pitches, so this does not identify the remaining mechanism.

All 555 intended-label source excerpts are retained, including unresolved source-content disagreements. Recording-pass protocols differ. Sustained mixtures do not establish attacks, decays, string assignment, unison multiplicity, continuous false-output safety or live performance. The 170.67 ms trailing feature context is not a measured pluck-to-MIDI latency. Earlier protected corpus references remain recorded; this gated experiment performed no new protected continuous replay.

## Provenance and verification

- Source `a5f46bab45be9cf87126f21426857358c6f75b2d`; worker `b18546e6556e84659b307f46c4b61037c5bc7d98`.
- Specification SHA-256 `ff3128b13422f80a6d024e32eb7dbdf9183197c90de40d37f4021a3e86c9dd5e`.
- Source CI44960048802 passed. All 54 synthetic checks passed on GitHub, including the real sklearn and CPU Torch checks; zero skips. One focused review found no material blocker. These verify experiment execution, not live tracking acceptance.
- Frozen weights/scaler/cutoff were saved before any held-out scoring. Model SHA-256 `b3d55619274886f75ed823102dfaf1ca31f382e267b6fd2563a1d15893659b83`.
- Small artifact `m3-harmonic-context-report-44960075844-1`, id14729417115, 16,379 bytes, collected once with server digest verified: `5605b35c9dd7620bf1bcc3e36324f8c92f53bc2525e45dff17d9d80a581671b8`.
- Report `build/github-results/harmonic-context-learning-44960075844/artifact/harmonic-context-result/report/report.json`; receipt `build/github-results/harmonic-context-learning-44960075844/collection-receipt.json`.
- Bulk `m3-harmonic-context-evidence-44960075844-1`, id14729601382, 4,582,838 bytes remains remote until 2026-12-05T23:10:10Z; server digest `sha256:bf18a1b950d5146b489d07a7b060d5fd34b70b132636fc1a4786918d06377359`. Do not repeat collection or processing.

## Next

Inspect the saved five-pitch training errors to distinguish weak-target ranking errors from harmonic false outputs before a distinct model design. Preserve this cutoff, rejection and all labels; no automatic rerun or held-out tuning. Require >=70% complete sets overall and for each 3/4/5-pitch stratum at training precision>=99%, then both untouched roles and continuous no-regression/benefit gates. No next job queued.

Claude is paused; this is the collected Codex-run result for the shared record, with no fresh Claude analysis claimed. Claude's 69 files are already published in `63416f8ed4af2535b1923304a6de2d49340d71e0`. The previous eight-hour interval is complete; the broader live-readiness goal remains open.
