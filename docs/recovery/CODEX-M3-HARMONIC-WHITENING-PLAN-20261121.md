# One frame-local spectral-whitening screen

The fixed setwise model fits training chords but fails transfer to the other
recording passes. A source-pipeline read found no material construction bug:
roles share crop, gain, normalization and target rules. Training-only shelves,
transposition, partial variation, added peak features and removal of absolute
RMS inputs have not met the unchanged gates. This screen tests a distinct
operation: remove part of each observed frame's broad spectral envelope before
the harmonic features reach the same classifier.

The mechanism is motivated by [Klapuri, ISMIR 2006, section 2.1](https://doi.org/10.5281/zenodo.1416740):
partial spectral whitening reduces timbral dependence in polyphonic pitch
estimation. It is a hypothesis for these recordings, not a demonstrated cause
of their transfer errors. Earlier dictionary whitening used training-template
coordinate weights; it did not estimate a new critical-band envelope in each
observed frame. Peak prominence and overall RMS removal also leave that broad
envelope largely present.

## Frozen operation

Keep the baseline two trailing Hann windows (4096 and 16384 at 96 kHz), FFT
sizes, harmonic/offset grid, 62 coordinates, 14,465-parameter context network,
setwise objective, optimizer, seed, 80 epochs and all mixture plans. No added
zero padding, features, augmentation, future samples or temporal state.

For each window form 30 triangular power bands, centered at
`c_b = 229 * (10 ** ((b+1)/21.4) - 1)`, b=1..30, with c_0/c_31 as outer
endpoints. Compute band variance from the current power spectrum divided by
FFT length. Use exponent nu=0.33; interpolate `variance ** ((nu-1)/2)` linearly
between band centers as an amplitude gain, holding endpoint gains constant.
Square the gain when weighting power. Implementation first scales power to
unit sum, floors band variance at `1e-12 / FFT_length`, and restores the
original one-sided power sum after weighting. These explicit normalization and
floor adaptations make the shape independent of common gain above the existing
feature floors. Silent input remains exactly zero. The two original waveform
RMS coordinates remain bit-identical. There is no extra silence or note gate.

Apply this same operation to training, calibration, test and any continuous
replay. Freeze one training-only global cutoff with the existing 99%-precision
rule. All 555 source labels and original pass roles remain, including the
documented disagreements. No pitch-label input constructs the envelope.

## Acceptance and execution

One bounded CPU GitHub job, at most 45 minutes, using existing pinned private
inputs. Training must meet precision>=99%, recall>=80%, exact sets>=70%
overall and separately at 3/4/5 distinct pitches, and zero silence extras.
The five-pitch training target is 1771/2529; baseline is 1818/2529. Only then
score the unchanged calibration/test roles. Each must independently meet
precision>=95%, recall>=80%, the same complete-set gates and zero silence
extras. No cutoff/seed/exponent retuning or automatic rerun after a rejection.

Only if all representation gates pass, use the existing ordinary/middle
continuous FIFO comparison: CURRENT identity, ordinary pitch-presence gain
>=5pp, no per-label presence or longest-hold loss, no wrong-pitch or gap-extra
growth on either recording. Keep installed labeled-frame/string scores fixed.

Synthetic direct checks cover energy conservation, scaling, silence, envelope
flattening, unchanged RMS/layout, causality and model serialization. GitHub
runs the existing training/scoring/gate checks. No local recorded audio/model
or native processing. Collect only the small report/log artifact once with
server digest verification; model and predictions remain remote.

Risks: whitening can amplify leakage/noise, remove useful instrument evidence
and change relative note strengths in mixtures. The shorter window resolves
low bands poorly. Sustained pitch-set gains cannot establish attacks, lanes,
unison multiplicity, MIDI lifecycle, native deadlines or live readiness. These
reused development passes are not a fresh final evaluation.

Standing authorization: `m3-standing-job-authorization-20261121.json`. Claude
remains paused; no fresh Claude review is claimed. The active record is
`github-harmonic-whitening-20261121.json`.
