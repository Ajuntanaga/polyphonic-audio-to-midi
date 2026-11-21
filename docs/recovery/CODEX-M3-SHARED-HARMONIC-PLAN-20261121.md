# Frozen shared harmonic classifier screen

The previous direct learner recovered 93.96% of complete training mixtures,
but only 53.30% on the second recording pass and 36.55% on the third. The
dictionary and residual methods then failed complete training chords. This
screen returns to supervised learning with a different representation: one
shared binary rule applied at every candidate pitch, instead of 53 independent
outputs over an absolute spectrum grid. No previous rejected policy is rerun.

The shared harmonic-coordinate principle is motivated by
[Deep Salience, Bittner et al. 2017](https://www.justinsalamon.com/uploads/4/3/9/4/4394963/bittner_deepsalience_ismir_2017.pdf).
This experiment is not its HCQT/CNN implementation and inherits no published
performance claim. Two fixed-resolution FFTs also prevent exact pitch-shift
equivariance.

## Frozen inputs and model

- Specification: `shared-harmonic-learning-20261121.json`; source and worker
  repositories, four existing private release hashes, all 555 source rows,
  original labels and CURRENT score references are pinned there.
- Same 16,384 training, 4,096 calibration and 4,096 test mixture plans as the
  earlier direct learner; recording-pass roles 200/200/155. No source exclusion,
  relabeling, extra augmentation or source-consistency-based selection.
- Each MIDI32..84 candidate receives 62 coordinates: trailing 4096/16384-sample
  Hann spectra at 96kHz; harmonic ratios 0.5,1,2,3,4,5, each sampled at offsets
  -0.4,-0.2,0,+0.2,+0.4 semitones, power relative to window RMS squared in dB,
  plus each window's RMS dB. Pitch, string, pass and label identity are absent.
- All training candidates pooled into one training-only StandardScaler and one
  binary MLP, hidden widths64/32, Adam, 80 epochs, batch2048, seed20261121,
  no early stopping or class weighting. Full constants are frozen in the spec.
- One training-only cutoff maximizes recovered target pitches subject to at
  least99% precision, keeping score ties whole. Model/cutoff are persisted
  before either held-out role. There is one fit and no tuning after results.

## Route and acceptance

Training must reach precision>=99%, recall>=80%, complete sets>=70% overall
and separately for each3/4/5 distinct pitches, with zero silence extras. If
training fails, stop. Otherwise score both untouched roles with the frozen
model: each must reach95/80/70% precision/recall/complete sets, each3/4/5>=70%,
and zero silence extras. Neither role tunes anything. Stop continuous work if
either fails.

Only after all three mixture gates pass: replay ordinary and extended-middle
once, block512, existing -9dB input trim and complete saved CURRENT score
identities. Primary clock is measured serial FIFO completion. Require ordinary
pitch-sample coverage gain>=5 points and no per-label presence or longest-hold
loss, wrong-pitch growth or extra-gap growth on either recording. Source-clock
numbers are diagnostic only. These are pitch measurements, not installed
note/string frame scores.

## Execution and limits

One CPU GitHub job,45-minute limit, existing authorized input releases only.
Native/plugin defaults are untouched. Local checks use synthetic arrays only;
the real sklearn API synthetic check and all fitting/audio processing run on
GitHub. Collect the small report/log artifact once with server-digest checking;
keep the model and predictions remote. No promotion on an exploratory pass.

Known source-content disagreements remain in the unchanged denominator.
Recording pass is confounded with ascending/descending/checkpoint protocols.
Sustained RMS-normalized mixtures do not establish attacks, release behavior,
string identity, unison multiplicity or new-instrument transfer. Independent
binary pitch decisions need not explain a chord jointly. The170.67ms trailing
window is not an acceptable-live-latency claim. Measured Python FIFO time does
not establish native allocation/deadline or external DAW/device gates.

Claude is paused. This records the next design for the existing collaboration;
it does not claim a fresh Claude review. Standing authorization is recorded in
`m3-standing-job-authorization-20261121.json`. Earlier requested evidence and
Claude's69-file publication are already complete; do not repeat them.
