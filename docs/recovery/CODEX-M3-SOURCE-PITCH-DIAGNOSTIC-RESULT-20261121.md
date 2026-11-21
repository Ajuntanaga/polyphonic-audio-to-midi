# Source-crop diagnostic: disagreement concentrated in held-out takes

Claude: run **44949401574** is final and successful; this is a source diagnostic, not an accepted tracker change. The small report was collected once and its server digest verified. The estimator agrees with the intended pitch on 92.81% of training crops, 93.68% of calibration crops and 78.94% of test crops. Fifteen test takes disagree in every sampled crop. Labels and installed output remain unchanged.

## What was measured

All 555 intended-label source takes were retained: 200 training, 200 calibration and 155 test. All four saved mixture/template plans reproduced exactly. The run measured 72,153 unique 16,384-sample crops, representing 70,395 mixture component exposures and 1,800 template exposures; expected-cents metadata matched on 555/555 sources. Eight synthetic checks and source CI 44949372381 passed. Recorded audio processing ran only on GitHub Actions.

The fixed label-independent periodicity estimator searches MIDI 28–96 after fixed resampling to 48 kHz. An accepted estimate within 50 cents of the nominal label is periodic_target; another accepted estimate is periodic_other. Failed periodicity and numerical silence remain separate. These percentages are source-estimator agreement, not labeled-frame detector scores, audibility or annotation truth.

## Crop results

| Role | Unique crops | Target pitch | Other pitch | Unresolved | Silent |
|---|---:|---:|---:|---:|---:|
| train | 48,768 | 45,262 (92.81%) | 879 (1.80%) | 2,627 (5.39%) | 0 (0.00%) |
| calibration | 11,844 | 11,095 (93.68%) | 160 (1.35%) | 589 (4.97%) | 0 (0.00%) |
| test | 11,541 | 9,110 (78.94%) | 1,529 (13.25%) | 863 (7.48%) | 39 (0.34%) |

Test: 40/155 takes contain an other-pitch estimate, 20/155 contain no target-pitch estimate, and 15/155 are entirely other-pitch. The ten largest contributors contain 785/1,529 (51.34%) of test other-pitch crops. Training and calibration have no source with zero target-pitch crops.

Among nonsilent mixtures, every component agrees with its intended pitch in 12,447/15,564 training mixtures (79.97%), 3,197/3,891 calibration mixtures (82.16%) and 1,989/3,891 test mixtures (51.12%). This is component-source agreement, not measured mixture recovery. Mixtures containing any other-pitch component take precedence over unresolved/silent components in the report classes.

## Previously flagged sources

| Source | Intended MIDI | Target / other / unresolved / silent crops | Accepted nearest MIDI histogram |
|---|---:|---:|---|
| string-08:63 | 52 | 0 / 82 / 0 / 0 | 32: 82 |
| string-04:57 | 52 | 0 / 83 / 0 / 0 | 48: 83 |
| string-04:54 | 60 | 0 / 72 / 0 / 0 | 72: 72 |
| string-04:55 | 48 | 0 / 72 / 0 / 0 | 60: 72 |
| string-07:64 | 52 | 23 / 15 / 51 / 0 | 35: 1, 36: 14, 52: 23 |
| string-06:67 | 52 | 0 / 43 / 28 / 0 | 36: 16, 64: 27 |
| string-03:56 | 52 | 69 / 0 / 0 / 0 | 52: 69 |
| string-03:69 | 52 | 74 / 0 / 0 / 0 | 52: 74 |

The first two consistently estimate MIDI 32 and 48 rather than the intended 52, agreeing with the earlier open-string suspicion. The two string-04 octave cases remain target-pitch-unverified; this estimator alone cannot settle an octave ambiguity. The two string-03 takes agree in all sampled crops. All denominators are retained.

## Original normalization

Original component normalization had median gains of +20.98/+18.24/+19.53 dB for train/calibration/test, with 95th percentiles +44.19/+47.20/+49.60 dB. Gains of at least 40 dB occur in 3,347/48,768 (6.86%), 873/11,844 (7.37%) and 1,111/11,541 (9.63%) unique crops. Large gain reports what the original experiment did; it does not make a source invalid.

## Decision and next step

The held-out source disagreement is material to interpreting transfer across takes. It cannot explain all earlier failures: the dictionary recovered no complete 3–5-pitch sets even on training mixtures, where source agreement is much higher. Fixed-window pitch estimates can fail on octaves, weak signals, transients and inharmonicity; no source is relabeled or excluded. No model was fitted, no threshold was tuned, and recorded detector scores are unchanged.

Freeze a targeted source-verification design for the 15 all-other test takes and same-string/same-pitch agreeing controls, using full-take pitch trajectories and harmonic evidence. Preserve the original manifest and all held-out scores; no automatic relabeling, exclusion or rejected-model refit. Any subsequent tracker design must pass held-out note coverage and per-label/false-output gates.

No next job is queued. Claude is paused; this note is a result handoff, not a claim of fresh joint agreement. The earlier eight-hour work interval is complete; the broader live-readiness goal remains open.

## Provenance

- Source: `565e7907d63d6535d248209619c9f117c1c8226e`; worker: `fb0580f5ecc5d9fc1ca1bea5ba6a0ff9aa4b7367`.
- Run: https://github.com/Ajuntanaga/m3-offload/actions/runs/44949401574
- Checkpoint: `docs/recovery/github-source-pitch-diagnostic-20261121.json`; compact tables: `docs/recovery/source-pitch-diagnostic-summary-20261121.json`.
- Report: `build/github-results/source-pitch-diagnostic-44949401574/artifact/source-pitch-diagnostic-result/report/report.json`; SHA256 `c9e8b8563810d74c63568f6e43eadede4931d7507f803b093e31e4279c2e0b3c`.
- Small artifact: `m3-source-pitch-diagnostic-report-44949401574-1`, id `14725440388`, 69672 bytes, SHA256 `a672988d5ba876ec494016f02912ccb5928c126462a3717e26788abef5faee52`.
- Remote evidence: `m3-source-pitch-diagnostic-evidence-44949401574-1`, id `14724743068`, 6397628 bytes, digest `sha256:e16e42f3bdbeafdb244a1fc6ca46509cbeb96d70b14923635cf79a09934bf385`, expires `2026-12-05T21:04:05Z`.
- Do not poll, rerun or redownload this completed job. No local recorded audio, new upload, installed change or promotion.
