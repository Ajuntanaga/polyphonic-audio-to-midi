# Frozen harmonic phase-motion screen

The paired component observation (45000500192) reproduced every original
mixture output. Of 2458 test missing pitches, 1430 were missing alone and 1028
were found alone but lost after summation. Magnitude feature, loss and source
augmentation screens have not passed source-disjoint gates. This screen adds
temporal phase information, rather than another amplitude normalization.

Keep all 62 original magnitude/RMS coordinates bit-identical. Within the same
16384 past samples, measure three 8192-sample Hann FFTs, ending 1024, 512 and
0 samples before the decision. At each MIDI32..84 pitch and ratios
0.5, 1, 2, 3, 4, 5, use the nearest native FFT bin (half-up rounding).
For its complex coefficients X0,X1,X2, compute
`z = (conj(X0)*X1 + conj(X1)*X2) * exp(-i*2*pi*f*512/96000)`
divided by `max(abs(conj(X0)*X1)+abs(conj(X1)*X2), 1e-20)`.
Append real and imaginary parts per ratio: 74 coordinates per pitch.
No complex-bin interpolation, phase unwrapping, presence threshold or hard
harmonicity rule. The total phase span is 9216 past samples, within the
existing context; it adds computation but no future context.

One setwise context-model fit, seed/80 epochs/loss/optimizer unchanged.
The first layer gains 384 parameters (14849 total), so information, capacity
and changed initialization are confounded. Original plan hash, all 555 source
labels, roles, gains, clocks and 99%-precision cutoff rule stay fixed.
Training complete-chord gates precede both held-out roles. Both held-out roles
are scored if that training gate passes. Continuous replay additionally
requires training single-pitch exact>=3115/3132, extras<=13 and misses<=5,
besides every original training/held-out gate. No retune or automatic rerun.
No promotion or installed/default change, even on a research pass.

Hypothesis: phase advance supplies evidence about a stable weak pitch versus
energy leaking into its bins that magnitude alone cannot encode. It can fail:
shared harmonics and coherent ghosts also have stable phase; low-frequency
negative-frequency leakage, noise, bends and transients can corrupt it.
Two highly overlapping increments are not independent observations.
Nearest-bin changes break exact pitch equivariance. This is not ownership,
source separation, a string model, or an audibility measurement.

Validation: synthetic phase sign/detuning/cancellation, occupied-bin gain and initial-phase
invariance, exact base features, silence/finiteness, past-only span and layout;
mocked orchestration including the additional preservation gate; on GitHub,
74-input network fitting and persisted-model roundtrip. Recorded audio/model
work runs only in one bounded CPU GitHub workflow via existing pinned inputs.
Keep small reports local and bulk evidence remote. No duplicate job.

The source-disjoint roles have been inspected in prior research and are not a
fresh blind benchmark. Sampled sustained pitch sets are not labeled-frame
string matches, unison multiplicity, onset latency, native timing or live MIDI.
Claude remains paused; no new Claude review is claimed.

Technical basis: [Smith, phase-vocoder parameters](https://www.dsprelated.com/freebooks/sasp/Computing_Vocoder_Parameters.html)
and [phase-vocoder sinusoidal modeling](https://www.dsprelated.com/freebooks/sasp/Phase_Vocoder_Sinusoidal_Modeling.html).
Phase advance estimates frequency within a sinusoidal model; this screen
learns from the residual and does not assume every bin contains one sinusoid.

Local validation: 11 tests completed: 10 synthetic/mocked checks passed; the
one model-fit roundtrip was skipped locally and scheduled on GitHub. The gain
check covers an occupied bin above the fixed power floor; nearly empty bins
are intentionally level-dependent as they tend to zero. No recorded audio,
model fitting or native execution was performed locally.
