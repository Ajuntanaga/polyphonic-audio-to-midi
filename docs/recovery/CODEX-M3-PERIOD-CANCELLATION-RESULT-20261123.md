# Period cancellation: quiet-note gain, unsafe overall result

**REJECTED_FIXED_MECHANISM_SCREEN.** Subtracting a periodic delayed copy exposed
more quiet upper pitches, but doubled false responses in the full test set and
attenuated too many intended targets. Both the implementable mixture-period
arm and the source-isolated diagnostic fail their frozen screen. This exact
setting is closed; no retuning, second dispatch or tracker integration follows.

| Test-role measurement | Raw | Mixture period | Source-period oracle |
|---|---:|---:|---:|
| Quiet upper queries found / 407 | 3 (0.7371%) | 44 (10.8108%) | 54 (13.2678%) |
| Quiet upper false responses / 407 | 2 (0.4914%) | 2 (0.4914%) | 6 (1.4742%) |
| All queries found / 2585 | 610 (23.5977%) | 370 (14.3133%) | 456 (17.6402%) |
| All matched-negative false responses / 2585 | 27 (1.0445%) | 55 (2.1277%) | 35 (1.3540%) |
| Quiet upper median target/interference gain | 0 dB | 8.7940 dB | 7.0438 dB |
| Targets retaining at least -6 dB power / 407 | 407 (100%) | 276 (67.8133%) | 320 (78.6241%) |

The primary +10.0737 percentage-point gain exceeds the +5-point requirement;
its median power separation also exceeds 3 dB. It fails all-query false-output
noninferiority (55 > 27) and target retention (67.8133% < 75%). The oracle fails
both all-query and primary false-output noninferiority. Source-period knowledge
does not establish a safe alternative. Silence scores remain zero in all arms.

The registered harmonic-related stratum explains one limitation descriptively:
only 57/131 related targets retain -6 dB power, versus 219/276 unrelated targets.
Shared periodic structure is cancelled along with the dominant source. These
strata do not justify an exclusion, threshold change or rescue screen. The
all-query found decrease includes the dominant notes the filter removes by
design; this was never a standalone replacement detector.

## Scope and verification

One CPU GHA job, 1024 mixtures per existing train/calibration/test role; source
counts 200/200/155, all 555 retained, no original take crosses roles. These roles
are reused design data, not fresh external validation. Each distinct intended
pitch has a negative with all its components removed, without renormalization.
The three cutoffs were set from calibration negatives only (28/2838 responses
per arm, within the registered 1% cap), then applied unchanged to the test.

All six top-level integrity checks and each role's five checks pass. Maximum
recomposition error is 2.22e-16; maximum filter-linearity error 3.33e-16, both
below 1e-12. Thirteen worker contracts and source CI pass. No fit, label edits,
native replay, production timing measurement, installed/default change or
scoreboard improvement occurred. These counts are pitch queries in a mechanism
screen, not annotated tuner-frame matches or delivered MIDI.

## Provenance and collection

- Source: `a181cde9605d41d6e7c89aa14ed8d1d2bc2d757c`.
- Worker: `de4b8ce90ed54ff235cc52347f7103ade86ea644`.
- Worker run: `45212865375`, workflow success, completed 2026-11-23 16:08:09Z.
- Source CI: `45212800208`, success.
- Frozen spec SHA-256: `cd2abd3038a6276c7a0da7d27b532f27858fc19a96be3dc716339d6a39deb606`.
- Small artifact: `m3-period-cancellation-report-45212865375-1`, ID
  `14837485861`, 13,620 bytes. Collected once, server digest verified:
  `3cc9544f57dd812cdc7b495f6c4fb84241404b68f2f0cbc7edc7b1fac229aeda`.
- Report: `build/github-results/period-cancellation-45212865375/report/period-cancellation-result/report/report.json`,
  SHA-256 `1693934fd068b22fce36aaa6b877911eb7c65b8b8657c4a003fbf16f924a5991`.
- Receipt: `build/github-results/period-cancellation-45212865375/collection.json`.
- Bulk remains remote: `m3-period-cancellation-evidence-45212865375-1`, ID
  `14837236784`, 1,589,965 bytes, server SHA-256
  `1af528af4e8ed163408de5f5af33b7d581f2b381fc0e935d7508ca235725ac88`.

Claude: the seven-event acoustic result supports the lane-flicker explanation
for those windows. Your separate ordinary58 acoustic lane remains open and is
not duplicated here. This cancellation result supplies no change to your scope,
the label budget, acoustic re-pluck status or the installed tracker.
