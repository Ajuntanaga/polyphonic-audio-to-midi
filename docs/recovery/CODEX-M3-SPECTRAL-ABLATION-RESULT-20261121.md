# Spectral ablation screen rejected before held-out replay

Run **44953542438** completed successfully as a workflow. The research screen failed its frozen training gate. Source `6bfd3af5b47c9023d177f0396a0873ff03cfe595`; worker `e9672b14afc2a7c425c7b3075c4e963298258925`. All 39 synthetic checks and source portable CI44953503086 passed. The small archive was collected once and its SHA-256 matched the server digest; model and predictions remain remote.

| Training measurement | Result | Frozen requirement |
| --- | ---: | ---: |
| Expected pitches recovered | 3,625/11,489 (31.5519%) | At least 80% |
| Predicted pitches correct | 3,625/3,661 (99.0167%) | At least 99% |
| Complete sets, all mixtures | 951/4,096 (23.2178%) | At least 70% |
| Complete three-pitch sets | 24/799 (3.0038%) | At least 70% |
| Complete four-pitch sets | 2/889 (0.2250%) | At least 70% |
| Complete five-pitch sets | 0/635 (0%) | At least 70% |
| Silence false outputs | 0 across 205 mixtures | Zero |

These are sustained mixture pitch instances and complete sets, not tuner labeled-frame matches, string assignments or delivered MIDI. The train-only cutoff was 0.8386819553485484. It produced 36 false pitches and missed 7,864 expected pitches. The model was persisted before the stop; calibration, test and continuous ordinary/middle replay were **not executed**. The 200 training source keys were all used. All 555 original source rows remain in their original roles and no source-consistency flag filtered fitting or scoring.

The new measure still recovers approximately one pitch per nonsilent mixture: 3,661 predictions across 3,891 nonsilent mixtures. At the same three-pitch size, recall is 32.83% with a defined harmonic relation and 32.96% without one. Thus restricting the next investigation to octave-related competition would miss the wider failure. These strata do not identify the cause. The prior relative-coefficient dictionary recovered zero complete three-to-five-pitch training sets; this screen reached 24/799, 2/889 and 0/635. The training counts differ, so that historical comparison is descriptive, not a paired gain.

No installed output, label, threshold or production default changed. No corpus buffer, allocation, timing or live-device gate was newly established. Existing installed scoreboard values remain the baseline. No automatic tuning or rerun of this configuration.

Next: Use the saved training activity and mixture plans for one report-only ranking diagnosis: distinguish weak true pitches ranked below false pitches from a conservative global cutoff, stratified by component level and 3/4/5-pitch mixtures. Preserve this rejection and all labels; no refit, cutoff change, held-out scoring or repeated screen. A future candidate needs complete-chord recovery without false-output growth before corpus or live work.

Full report: `build/github-results/spectral-ablation-44953542438/artifact/spectral-ablation-result/report/report.json` (SHA-256 `d49cf77b9357d54d12ed1cec52c13fc8f18affa0ccb3c1b05abe791f466f78b5`). Compact numbers: `docs/recovery/spectral-ablation-summary-20261121.json`. Checkpoint: `docs/recovery/github-spectral-ablation-20261121.json`. Report archive: artifact14727245180, 11,807 bytes, SHA-256 `74f77a5cf77728291029c5eb4f4f51b87fde5637a57a3918eef6db000f0f2f8b`. Bulk artifact14726114992 remains remote (5,029,034 bytes; expires 2026-12-05). Claude is paused; no fresh Claude analysis is claimed. The broader live-readiness goal remains open.
