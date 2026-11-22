# Audio level at label ends: ownership and pre-registration (written before any audio is opened)

Claude, 2026-11-22. Nothing below has been measured. I have not opened `ordinary.wav` or `extended-middle.wav`, no level curve exists, and the only data used so far are the labels and the saved ONNX stream tapes of Codex's run 45029161409 (to list the ends and tell which arm detected each). The measurement code and its tests are committed with this note; the ends list is committed before the one worker job that reads the audio.

## Ownership (so we do not overlap)

- **Mine:** the audio-level read of the evaluable label ends of the real-release-curve read (`ordinary` 428, `extended-middle` 6): one CPU job on GitHub Actions, numpy and soundfile only, no model, no weights, one dispatch. This is the "post-label acoustic-support observation" that Codex's note `CODEX-M3-TEMPORAL-CROP-RECOVERY-20261122.md` leaves to me under the standing authority.
- **Codex's (not touched):** the temporal-crop run 45034216124, the causal delivery-lag side, the training/adaptation lane (the abrupt-boundary fit draft stays unexecuted), every frozen gate.
- **Not claimed:** any change to the installed tracker, any promotion, any model run.

## Question

The release-curve read found that the adapted model's output is above 0.3 at 62% of label ends against 29% for the original (145 ends only the adapted model still shows, 121 both, 3 only the original, 159 neither), and that the adapted release is about one frame later. It could not say whether the string is still sounding at those ends: tapes hold no audio. After a label ends, is there still energy at the labelled pitch in the recording, and does that separate the four groups?

## Inputs

- `ordinary.wav`, `extended-middle.wav` (96 kHz, pinned by hash in the spec) from the pinned input release, labels as in every earlier analysis (clipped to the common support).
- The ends: every end of the release-curve read's evaluable set (a union-span end at one MIDI pitch, at least 100 ms long, with at least 120 ms before the window end `W = min(next same-pitch start − 100 ms, E + 1000 ms, horizon)`), with its group from the tapes (`both`, `adapted_only`, `original_only`, `neither`, by the registered plateau at or above 0.3). Built by `CLAUDE-M3-AUDIO-RELEASE-20261122.py build-ends` into `CLAUDE-M3-AUDIO-RELEASE-ENDS-20261122.json`, which the spec pins by hash. The worker reads only pitch and sample positions.

## Measurement (mechanical; `tools/audio_release_levels.py` implements exactly this, tests in `tests/test_audio_release_levels.py`)

- Level of a window: 80 ms Hann (periodic) window of the mono recording, weighted mean removed; for each harmonic `k` of the pitch with `k` from 1 to 4 and `k·f0 ≤ 2000 Hz` (`f0 = 440·2^((m−69)/12)`), amplitude `A_k = 2|Σ w x e^{−2πi k f0 n/fs}| / Σ w`; level `20·log10(sqrt(Σ A_k²) + 1e-9)`, dB relative to full scale. A pure sinusoid of amplitude a reads a.
- The worker returns two level curves per end on a 10 ms grid of window starts: `E + 10 ms·j` for `j = −20..30` and `S + 10 ms·j` for `j = −20..20` (`E` label end, `S` label start). Every quantity below is derived from those curves by the registered analysis, so nothing is tuned after reading.
- Derived: `pre` = level of `[E−80 ms, E)`. `R(τ)` = level of `[E+τ, E+τ+80 ms)` minus `pre` (negative means quieter after the end), for τ = 0, 40, 100, 200 ms, defined only when `E + τ + 80 ms ≤ W`. `within` = `pre` minus the level of `[E−160 ms, E−80 ms)`, defined when the label is at least 160 ms long. `rise(δ)` = level of `[S+δ, S+δ+80 ms)` minus level of `[S+δ−80 ms, S+δ)` for δ = −60..60 ms in steps of 20.
- **Primary quantity: `R(0)`**, the 80 ms after the label end. It is the audio the model's readout at the label end can already see (the readout looks 84 ms past a frame's nominal time).

## Contested ends (label-only flag, computed before any audio)

An end is **contested** when some other labelled pitch overlaps `[E−80 ms, E+200 ms)` and one of its first four harmonics lies within `max(3.5%, 25 Hz)` of a measured harmonic of this pitch (25 Hz is about the half-width of the 80 ms Hann main lobe). Contested ends can look as if they still ring because another note's partial lands in the same bins; the verdict uses the uncontested ends when it can. A start is contested by the same rule over `[S−140 ms, S+140 ms)`.

Counts, from labels and tapes only (`ordinary`): all 428 ends, uncontested 67 (both 16, adapted_only 22, original_only 0, neither 29), contested 361 (both 105, adapted_only 123, original_only 3, neither 130). Clean starts: 70. `extended-middle`: 6 ends, all uncontested, all `both`. The uncontested ends are high notes (median MIDI 74, 10th percentile 57, against median 53 for the contested ones), so an uncontested verdict says nothing about the low strings, where the 80 ms window cannot separate neighbouring pitches anyway.

## Checks that gate the reading (registered)

- **V0 pins:** `wav_sha256` and `sample_count` equal the spec; the ends file hash equals the spec; the tests pass on the worker before the audio is read. Any failure: nothing is measured.
- **V1 alignment of labels and audio.** Over starts that are not contested, the median `rise(0)` is at least +10 dB and the δ with the largest median rise lies within ±20 ms. If it fails, the result is reported as registered and marked "alignment not confirmed", and the read is not decisive.
- **V2 sounding-note control.** Over all ends of the verdict stratum, the median `within` lies in [−8, +1] dB (a note that is still sounding changes by a few dB over 80 ms). If it fails, "measurement not confirmed" and the read is not decisive.

## Predictions (registered; judged as registered, misses reported as misses)

Verdict stratum: `uncontested` when both `adapted_only` and `neither` have at least 15 uncontested ends with a defined `R(0)`, else `all`. Verdicts are from `ordinary`; `extended-middle` (six ends, one group) is shown for completeness and never pooled.

- **A1, adapted-only ends still ring.** The median `R(0)` of the `adapted_only` ends is at least −6 dB.
- **A2, and the audio separates them from `neither`.** The median `R(0)` of the `adapted_only` ends minus that of the `neither` ends is at least +6 dB.
- **A3, level ordering.** Median `pre` of `both` exceeds that of `adapted_only` by at least 3 dB and that of `adapted_only` exceeds `neither` by at least 3 dB (each group needs 15 ends, else not evaluated).
- My expectation, stated now: A1 and A2 pass (about 55% for both together), A3 passes (about 65%). The prior is that the original drops quiet but still sounding notes before the label ends and the adapted model keeps them, so the adapted-only group should be quieter than `both` but still ringing, and `neither` should be the damped or silent ends. The case I take as live is that all three groups ring (A2 miss), which would say the missing ends are a sensitivity problem rather than damped strings.
- Descriptive only (gates nothing): the share of ends with `R ≥ −6 dB` and `≥ −12 dB` per group and τ, a bootstrap 95% interval of the A2 difference (seed 20261122, 2000 resamples; ends within one take are not independent), and every group's medians in each stratum.

## Reading rules

- **A1 and A2 true:** the adapted-only presence has audio support. Those strings keep sounding after the label while the original dropped them, and the `neither` ends are the damped ones. The label-end clause then charges the adapted model for correct output, which bears on the label-rule question put to the user, and the lag levers matter more than a decay fit.
- **A1 true, A2 false:** the audio rings in every group; the labels end before the sound does. The adapted and original differences are then about sensitivity (quiet notes), and the 159 `neither` ends, which both models drop while the audio rings, are the larger problem.
- **A1 false:** the adapted-only ends are already at least 6 dB down at the label end. The adapted model then holds presence past the audible decay, which would be stickiness of the model and would favour the boundary-fit idea more than the earlier probes did.
- **V1 or V2 false:** reported as not decisive, and I say what was measured instead of what was meant.

## Caveats stated in advance

- Harmonic energy is evidence that something sounds at that pitch, not that the labelled string does: overlapping partials of other notes, sympathetic ring and unlabelled strings are indistinguishable here. The contested flag removes only the label-known part.
- The uncontested stratum is high-pitched and small (22 and 29 ends in the groups the verdict compares). `all` ends, where most low notes live, are reported but the 80 ms window cannot resolve neighbouring low pitches, so their ratios lean toward "rings".
- One recording for the verdicts; counts are descriptive. Post hoc readings, if any, are labelled as such.
- No model runs, nothing is promoted, no gate is touched.
