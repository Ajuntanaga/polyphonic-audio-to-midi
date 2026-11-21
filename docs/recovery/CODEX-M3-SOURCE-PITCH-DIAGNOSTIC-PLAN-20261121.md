# Frozen source-crop pitch and level diagnostic

One bounded CPU GitHub job; observation only. Standing authorization is recorded in `m3-standing-job-authorization-20261121.json`. No model fit, mixture replay, relabeling, source exclusion, installation or promotion.

Question: did the intended-label source crops used by the rejected direct-spectrum and measured-dictionary experiments contain the intended fundamental, and how much did the original RMS normalization amplify them? Prior isolated checks flagged eight sources, but did not cover all 555 sources or the exact randomly selected crops.

## Frozen inputs and scope

Specification: `source-pitch-diagnostic-20261121.json`. Reuse the exact 555-source manifest (200 train, 200 calibration, 155 test), the three existing authorized input releases, and four saved plans from dictionary run 44946969983. Verify archive/member digests and reproduce every plan object from the pinned unchanged generators before any audio measurement. The direct-spectrum and dictionary runs used the same mixture generator/settings. Retain every source and deduplicate only identical source/crop coordinates; report their mixture and template exposure weights separately.

## Method and outputs

For each exact 16,384-sample crop: raw RMS/dBFS; gain used to normalize to RMS 0.05; label-independent periodicity estimate. The fixed YIN-style estimator uses 48 kHz resampling, constant-length squared difference, cumulative mean normalization, first local trough below 0.1, and parabolic lag interpolation over MIDI 28..96. Classify periodic target only within 50 cents of the nominal label; expected calibration cents are a separate report column. No accepted trough means unresolved, even though the best fallback estimate remains descriptive. Numerical silence uses the existing 1e-12 RMS floor.

Synthetic tests cover exact difference arithmetic, pure/harmonic/missing-fundamental tones through MIDI 95, label-independent estimates, noise/silence/weak tones, saved-crop identity, exposure conservation, and refusal to run recorded inputs locally. A synthetic MIDI84 missing-fundamental signal exposed an octave error at 12 kHz; the final fixed 48 kHz estimator passes it. No recording was used to choose this rate.

Small report: every source's counts, role summaries, class counts weighted by component exposures, original-mixture class composition, known flagged sources, all integrity checks and provenance. Bulk gzip JSONL retains every crop's estimate and coordinates remotely. No source audio is published in artifacts. This diagnoses source agreement; it does not establish annotation truth, audibility or string identity.

## Decision before results

All 555 sources remain in every denominator. Compare role/source concentrations of periodic-other, unresolved and high-normalization crops before choosing the next representation. A disagreement is a verification target, not permission to change a label or exclude a take. If most crops agree, do not blame source fidelity for the earlier model failures; inspect the representation/decision behavior instead. No automatic refit, retry or threshold change follows this report.

The installed scoreboard, full-corpus/lifecycle/deadline requirements and live-host gates remain unchanged. Claude is currently paused; this records the analysis question for the shared queue without claiming a fresh joint review.

Method reference: de Cheveigne and Kawahara (2002), YIN, https://www.ee.columbia.edu/~dpwe/e6820/papers/deChevK02-yin.pdf . This diagnostic implements a fixed-window subset, not the complete algorithm.
