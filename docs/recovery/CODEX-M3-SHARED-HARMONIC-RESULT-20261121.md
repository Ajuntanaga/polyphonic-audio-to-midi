# Shared harmonic classifier: rejected at training chord gate

Run [44958696453](https://github.com/Ajuntanaga/m3-offload/actions/runs/44958696453) completed successfully. The frozen research screen is rejected: training recall and complete-pitch-set gates fail. Both held-out roles and continuous ordinary/middle replay were skipped as specified. There is no installed output change, promotion, measured live gain, or new held-out transfer result.

## Measured result

One fit over 16,384 sustained mixtures / 868,352 candidate rows took 74.99 seconds. It used a shared binary classifier with 62 harmonic-relative features, 80 epochs, and a training-only cutoff of 0.8947283625602722. All 555 original source labels remain in the corpus, including unresolved source-content disagreements. No cutoff retuning or exclusions followed the result.

Training expected-pitch recall is 35,732/45,698 = 78.1916% (target >=80%; 827 more true pitches needed for the integer target). There are 360 false positives, so precision is 35,732/36,092 = 99.0025% (target >=99%). Complete pitch sets are 9,499/16,384 = 57.9773%, including all 820 silence examples; target >=70% requires 11,469 sets, a gap of 1,970 sets / 12.0227 percentage points. Silence has zero false predictions. These are synthetic-mixture pitch counts, not tuner frame/string scores or delivered MIDI.

| Training stratum | CURRENT complete sets | TARGET | GAP |
| --- | --- | --- | --- |
| 3 pitches | 1757/3251 (54.0449%) | 2276/3251 (>=70%) | 519 sets; 15.9551 pp |
| 4 pitches | 1006/3432 (29.3124%) | 2403/3432 (>=70%) | 1397 sets; 40.6876 pp |
| 5 pitches | 355/2529 (14.0372%) | 1771/2529 (>=70%) | 1416 sets; 55.9628 pp |

Single-pitch complete sets are 3,041/3,132 = 97.0945%; two-pitch sets are 2,520/3,220 = 78.2609%. Harmonic-related mixtures have 27.1052% complete sets versus 72.1460% for the other stratum. The groups differ in chord size, and the latter includes silence and single pitches; that comparison alone does not isolate harmonic overlap as the cause.

The high training precision comes with missed chord members. This configuration therefore fails before transfer is tested. It does not establish that shared harmonic features are fundamentally insufficient. Sustained mixtures also do not establish attack handling, string assignment, unison multiplicity, false-output safety in continuous audio, or realtime readiness.

## Provenance and verification

- Source: `6cb655e108d156c38d543871b2b077a55bc493ef`; worker: `cd26fee87fe049a66725a001e50f71e36bbcaf27`.
- Frozen specification SHA-256: `bcc27b2bfd36d74cdf55228f3bfb970937759683e5b9e3681649281eb86e37e2`.
- Source CI44958668959 passed. All 47 synthetic checks passed on GitHub, including the real scikit-learn API check. One focused review found no blocking issue. These establish experiment execution, not tracking acceptance.
- The model and cutoff were persisted before any held-out scoring; frozen model SHA-256: `0fe7491952deeb1ebb74e7288cf9f8d7f62c3d1490383c01fc745fdfb9d7d00f`.
- Small artifact `m3-shared-harmonic-report-44958696453-1`, id14727774140, 14,897 bytes, collected once and server digest verified: `ed8f48af676a457ae2f3437d4c3cf5d3a51bb4821ede79e031cd25aad296b28b`.
- Report: `build/github-results/shared-harmonic-learning-44958696453/artifact/shared-harmonic-result/report/report.json`. Receipt: `build/github-results/shared-harmonic-learning-44958696453/collection-receipt.json`.
- Bulk `m3-shared-harmonic-evidence-44958696453-1`, id14727689314, 4,648,197 bytes, remains remote; expires2026-12-05T22:51:16Z. Server digest: `e0b0b59777ea7080856feeb4b0f0d73e9b6f206563f5eb0c13ce56586e6590fd`.

## Next

Joint next design: address complete multi-pitch consistency and transfer across recording passes with a distinct representation or model. Freeze one hypothesis and unchanged safety/benefit gates before any new job. No next job queued; do not rerun or retune this rejected screen.

Claude is paused; this is the collected Codex-run result for the shared record, with no fresh Claude analysis claimed. The previous eight-hour interval is complete and the overall live-readiness goal remains open. All installed scoreboard counts remain unchanged.
