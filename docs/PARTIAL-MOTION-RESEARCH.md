# Research route: measured motion across harmonics

Updated 2026-11-04. Frozen third/fifth-partial cues support a small offline
string-assignment gain. Nine of fourteen corpus screens pass with the
initial-settling guard. Native cues match the reference. The optimized FFT
reduces measured cost but still exceeds the callback budget. A one-hop delay
loses five solo matches; a fixed 128-sample delay preserves all ten controlled
results. The next step is to measure bounded background delivery. The
installed plugin and its parameters are unchanged.

## Decision

Continue the frozen-cue route as an offline string-assignment correction.
The current guard acts only during the first 160 ms of candidate history;
later corrections caused measured passage losses. It retains the nearby-note
gain of 815 to 835 matches out of 3450, with fewer wrong-string outputs.
Pitch admission stays unchanged. Nine corpus screens preserve all passage
matches and false-output limits; this establishes regression coverage, not
better broad-corpus tracking or live readiness. Before integration, require
a scheduling route that preserves the undelayed gains and meets callback
timing. The remaining corpus and MIDI lifecycle checks stay open.

The earlier direct-fundamental admission repair is rejected. It raised
matches from 3250 to 3507/6900 in the equal-RMS MIDI-49 mixture while adding
1666 false outputs. Direct-peak strength alone was insufficient. The sections
below record that failure and the later frozen-partial and assignment results.

The causal measurement experiment is complete. A physical single-string
counterexample rejects motion magnitude as a standalone source-count cue.
Keep the capture and availability diagnostics offline. Defer a learned
posterior-plus-motion comparison until independent physical takes and a
defensible source reference exist; the current capture supplies neither.

The original hypothesis was that *measured motion* across harmonics might add
string evidence beyond the existing string posterior. The experiments below
test the measurement and its failure modes. They do not justify repeating the
stationary harmonic fit, adding a general classifier or changing MIDI admission.

A string's harmonics can move together as its tension and vibration change.
An overlapping harmonic may follow a different mixture of those movements.
The useful question is whether those differences survive in our recordings,
not whether a sufficiently flexible model can reconstruct the waveform.

## Native measurement and the callback constraint

Run `native-frozen-cue-20261104T1023Z` completed on Modal. The native
implementation matches all 175960 note observations across ten controlled
cases; clock, reasons, peaks and numeric features pass the frozen tolerances,
and exported cue files are identical. Four focused boundary, clock, reset and
allocation tests pass. This is a standalone measurement component, not an
installed output change.

Its synchronous FFT fails the callback budget in every case. Worst block
p99 is 5.991700 ms against 0.166666 ms, with a 14.391048 ms maximum against
0.333333 ms. Timing excludes the detector and the rest of the plugin. Numerical
parity therefore does not justify putting this implementation on the audio
thread.

The optional double-precision AVX probe in
`native-frozen-cue-pffft-20261104T1051Z` preserves all ten cue files and all
175960 observations within the same tolerances. All five boundary, reset and
allocation tests pass, including linked C allocations. Worst p99 is
0.291410 ms and maximum is 0.730550 ms: reductions of 95.14% and 94.92%
from the scalar results across separate cloud runs. This is not a controlled
same-CPU comparison. Every case still misses the stated callback gates, so
the synchronous route remains rejected. The fixed workspace is 2110416 bytes,
excluding opaque FFT setup storage. PFFFT is pinned to
`7ae36e8c1d352cba66231de953cfa35f235b9e7a`; source hashes and license notices
are retained. The optional probe defaults off and does not alter the plugin.

Run `cue-fixed-delay-20261104T1034Z` tested one fixed scheduling delay of
1024 samples (10.6667 ms), using the saved replay binary. Both cue availability
and expiry move by one hop; the measurement window and thresholds stay fixed.
The delay is rejected: solo matches fall from 3236 to 3231/3450
(93.7971% to 93.6522%; five fewer matches), while wrong-string outputs rise
from 142 to 147. The original OFF baseline is 3219 matches and 159 wrong
strings; retaining a smaller improvement does not satisfy the stated gate
of preserving every undelayed gain. Nearby matches remain 835/3450 and
quiet-octave matches remain 2079/3450. No other case changes. Further buffer
checks stopped after the failed gate. OFF and unit-test evidence are reused
from the identical saved binary; earlier undelayed corpus passes do not cover
the delayed policy. No incremental FFT was implemented.

The fixed 128-sample delay (1.333333 ms) passes in
`cue-fixed-delay128-20261104T1108Z`. The diagnostic reader keeps the original
cue-file validation, then shifts availability and expiry. Fresh OFF and
zero-delay ON reproduce every saved result. Delayed ON preserves all ten
counts, false-output counts and fingerprints, including solo 3236/3450,
nearby 835/3450 and quiet-octave target 2079/3450. All delayed outputs agree
at blocks 32/512/1024, and all 68 native tests pass. The seven cases without
an undelayed gain remain bit-identical to OFF. Replay SHA-256 is
`8126916ac76d07a4b00932d4c051633015a172f71b3655a7045de853f3a61889`.
The earlier nine corpus passes use the undelayed reference binary and do not
cover this build or policy.

This establishes delay tolerance, not worker scheduling. Next, measure a
bounded background handoff with sample-tagged availability and expiry. Require
exact masks, no lost or late frames, no callback allocation or waiting, safe
reset/overflow behavior and callback timing. Standalone scheduling still leaves
detector integration, the remaining corpora and live MIDI behavior untested.

## Relevant primary sources

| Source | Useful result | Limit for this project |
| --- | --- | --- |
| [Barbedo and Tzanetakis, 2010: Correlation-Based Amplitude Estimation of Coincident Partials](https://webhome.cs.uvic.ca/~gtzan/work/pubs/eurasip2010gtzan.pdf) | Uses correlations in time-varying partial parameters, including frequency trajectories, to estimate contributions to overlapping partials. Discusses equal fundamental frequencies. | Requires a partial sufficiently dominated by a source to act as a reference. An arbitrary mixture peak is not such a reference. This does not establish three- or four-string identification on our guitar. |
| [Woodruff, Li and Wang, ISMIR 2008: Resolving Overlapping Harmonics for Monaural Musical Sound Separation](https://archives.ismir.net/ismir2008/2008_ISMIR_Proceedings.pdf) (proceedings pp. 537–540) | Combines common amplitude modulation, phase evolution and least-squares estimation to resolve overlapping harmonics. | Non-overlapping reference partials and a useful pitch estimate matter. Plucked-string attacks, bends and changing decay can violate the assumed relationships. |
| [Ponce de León and Beltrán, 2012: Blind Separation of Overlapping Partials in Harmonic Musical Notes](https://doi.org/10.1186/1687-6180-2012-223) | Uses complex wavelet information and reference partials for overlapping-harmonic separation. | Complete overlap needs additional source information. Do not treat separated model components as new independent measurements. |
| [Hjerrild and Christensen, ICASSP 2019: Estimation of Guitar String, Fret and Plucking Position Using Parametric Pitch Estimation](https://vbn.aau.dk/en/publications/estimation-of-guitar-string-fret-and-plucking-position-using-para/) | A physical inharmonic model and a trained string/fret classifier can use short guitar segments; plucking position also affects harmonic amplitudes. | The reported experiment is not our simultaneous M3 unison task. Its published error rate cannot be transferred to our acceptance scoreboard. We already use calibrated partial detuning. |
| [Hodgkinson, Timoney and Lazzarini, DAFx 2010: A Model of Partial Tracks for Tension-Modulated Steel-String Guitar Tones](https://dafx10.iem.at/proceedings/papers/HodgkinsonTimoneyLazzarini_DAFx10_P69.pdf) | Models time-varying fundamental frequency and inharmonicity in plucked steel strings. | Hard attacks can change both. A fixed detuning template is not a complete physical source model. Existing drift experiments already cover part of this idea. |
| [SynthTab authors: documented rendering defect](https://github.com/yongyizang/SynthTab#known-bugs) | Their renderer can omit a second same-pitch, same-string note when adjacent MIDI events have no gap. | Synthetic MIDI labels are not proof that the intended attack exists in rendered audio. Check repeated-note attacks before using a synthetic dataset as a teacher or acceptance set. No large dataset download is required for this step. |

These sources motivate a hypothesis. None supplies an M3 accuracy claim or
permission to bypass the existing release, silence, onset or polyphony rules.

## What has already been tried here

Read this alongside [the existing tracking research](POLYPHONIC-TRACKING-RESEARCH.md).
The following evidence is recorded in `build/modal/current-status.json` and
the named reports; these are completed experiments, not new proposals.

| Existing work | Result and consequence |
| --- | --- |
| Six-partial causal detuning and calibrated string posterior | Already implemented and evaluated. Another inharmonicity classifier alone is not a new route. |
| `joint-harmonic-screen-v2-analysis.json` | Calibrated joint fit supported 15 of 36 triple windows and one false third string. Rejected for production. |
| `coupled-harmonic-screen-analysis.json` | Improved later-audio prediction but recovered neither missing triple. Reconstruction quality did not establish correct string count. |
| `harmonic-drift-screen-analysis.json` | Better prediction did not recover the missing triples; alternative pair masks remained plausible. |
| `harmonic-beat-evidence-audit.json` | Expected pair support also supported extra masks. A modulated single source could look like multiple sources. |
| `decay-normalized-beat-audit.json` | Removing exponential decay did not remove the two-decay single-source counterexample. Physical triple support remained absent. |
| `supported-owner-handoff-screen.json` | Offline ordinary matches rose from 145397 to 146147, but wrong-note outputs rose by 2982, wrong-string outputs by 360, and extra gap outputs by 512. Rejected. Holding an owner longer is insufficient without better evidence. |

The new distinction is **incremental information in observed trajectories**.
It is not another fit with more parameters, another beat threshold, or a
source-conditioned projection of the same signal.

## Physical and mathematical constraints

For one idealized stiff string, partial frequency is often modeled as

`f_h(t) = h * f_0(t) * sqrt(1 + B(t) * h^2)`.

Here `f_0` is the ideal flexible-string fundamental. If the reference is the
measured first partial `f_1`, use
`f_h = h * f_1 * sqrt((1 + B * h^2) / (1 + B))` instead.

The model suggests relationships across partial trajectories. It does not
make every guitar partial valid: wound strings, pickup position, noise,
collisions and low signal level can hide or distort those relationships.

For a measured complex partial track `z_h[n]`, a causal phase increment is

`dphi_h[n] = arg(z_h[n] * conj(z_h[n-1]))`.

After accounting for the known demodulation center and sample interval, this
gives a local frequency estimate. Weak-amplitude samples and phase slips must
be marked unavailable. Compare changes across harmonics on a common valid
time interval; compare envelope changes separately. Shared loudness decay is
a nuisance, not evidence of multiple strings.

There is a useful identifiability counterexample. Several sinusoids at exactly
the same frequency with fixed phase offsets sum to one sinusoid. More
generally, sources with proportional complex partial tracks can yield the
same mixture under multiple source assignments. No classifier can identify
which of those indistinguishable assignments generated that observation
without an additional prior or measurement. Real strings may provide extra
cues; this counterexample specifies when to abstain, not a claim that all
physical unisons are impossible to distinguish.

## One bounded Modal experiment

1. **Reuse original measurements.** Start from the saved physical harmonic
   windows referenced by `harmonic-beat-evidence-audit.json`, plus the native
   assignment captures referenced by `profile-pair-evidence.json`. Join only
   when recording, audio/sample origin, calibration and window identities
   agree. A posterior from a different recording or calibration cannot serve
   as the control. Record missing fields explicitly. The current harmonic
   archive has three harmonic bands; do not claim six observed bands.
2. **Check the references before scoring.** A candidate reference must have
   adequate measured signal, valid phase and a stable track. Do not select it
   using the expected string label or a fitted component. If source-dominant
   references are unavailable, record the case as unmeasured. This failure is
   informative and does not authorize manufacturing a reference.
3. **Freeze the baseline and features.** Baseline inputs are the existing
   posterior and its validity. Added inputs are measured cross-partial
   frequency-change and envelope-change relationships, with explicit
   availability masks. Do not include recording IDs, expected masks, time
   since an annotated event, or any future sample. Score every playable mask
   of one through four strings so that a pair must beat the single-string
   explanation. Keep the current fret limits.
4. **Separate training from evaluation.** Fit any nuisance normalization and
   small secondary classifier on training recordings only. Hold out whole
   recordings/takes, preserving ascending, descending, corrected and blended
   identities. Overlapping windows from the same pluck must stay together.
   If only one physical take is available, a within-take result is exploratory
   and cannot pass the generalization gate. Do not tune on protected replays.
5. **Measure conditional gain.** Compare the fixed posterior-only model with
   the same model plus each cue and then their combination. Report held-out
   log-loss difference, expected-mask margin against its strongest alternative,
   false added members, abstentions and signal coverage. Confidence intervals
   resample independent takes/plucks, not correlated audio frames. Log loss
   requires training-calibrated probabilities; an arbitrary residual score
   must not be relabeled a probability.
6. **Use adversarial controls.** Include isolated strings, amplitude-modulated
   singles, the existing two-decay single-source controls, weak partials,
   simultaneous and staggered attacks, global gain changes, and near-equal
   detuning. Synthetic positives only establish mechanism sensitivity. Keep
   corrected and blended material separate from physical recordings.

The first job is a saved-capture analysis with a small memory/CPU bound, not a
new replay matrix or production build. If the saved fields cannot support a
valid comparison, capture only the missing causal diagnostics on Modal,
keeping MIDI/fingerprints unchanged, before attempting the comparison.

### Rejection and promotion rules

Reject the feature if it adds no held-out information beyond the baseline,
requires unavailable upper harmonics or fitted-source references, or increases
false extra-string decisions on the single-source controls. A successful
reconstruction or synthetic separation is not a substitute for this result.
If there are too few independent physical takes, report insufficient evidence
and keep it disconnected rather than inventing a confidence percentage.

Only an informative, conservative result permits a bounded secondary-evidence
implementation. It remains allocation-free, decimated and restricted to
already-active candidates. It may not create pitches or bypass silence,
release, committed ownership, playable masks or total polyphony. Preserve the
three-second close-unison evidence window, 0.20 beat gate and 0.50 retention
floor. Short diagnostic windows cannot certify sustained three-string locks.

Any output trial must first beat the current ordinary control: matched frames
greater than 145397/528632, wrong-note outputs at most 163749, wrong-string
outputs at most 92641, and extra outputs in unlabeled gaps at most 62856.
Those are offline control counts, distinct from the installed baseline.

Then require the current physical-long targets: at least 42128/68441 matches
and 25604/39378 exact-three frames, with wrong strings at most 2709. Exact-three
means all three intended strings assigned correctly at the same time. Preserve
the other protected corpus results, exercise physical/synthetic four-string
cases, and require identical fingerprints at blocks 32, 512 and 1024. Run the
native, deadline/allocation, source-contract, production-build and validator
gates and one code review before any installation.

## Implemented capture and checks

`tools/modal_m3_partial_motion.py` now captures the measured complex baseband
tracks and the existing eight-string posterior at the same decision tick.
The native getter and JSONL writer are compiled only into offline replay.
The writer records the audio clock, demodulation centers, selection/onset
state, assignment masks and signal availability. Labels are used only in
later evaluation; removing labels leaves the capture unchanged.

These are **filtered mixture measurements**, not separated source tracks.
The posterior is the cached single-string distribution, not a fresh joint
mask probability. Audio, calibration, settings and trace hashes identify
each capture. Missing or mismatched join identities fail closed.

Run `partial-motion-20261103T1151Z` completed on Modal:

| Capture | Observed frames | Complete annotated three-second windows |
| --- | ---: | ---: |
| Physical long unisons | 88,232 | 13: five pair, eight triple |
| Isolated string 8, note 40 | 34,800 | 0 |
| Single source with amplitude modulation | 6,000 | 2 |
| Single source with two decay rates | 6,000 | 2 |
| Simultaneous pair | 6,000 | 2 |
| Staggered triple | 6,000 | 2 |

The physical WAV clocks are **96 kHz**; the synthetic controls are 48 kHz.
The isolated note-40 hold is 2.3 seconds, so it cannot supply a complete
three-second control window. There is one physical long-unison take, not an
independent held-out take. Synthetic masks describe the generator and are
not calibrated physical string labels.

For both physical recordings, output fingerprints, counts and diagnostic
bytes are identical at block sizes 32, 512 and 1024. All four synthetic
captures also preserve their control replay output. The two new native
diagnostic tests and all 46 offline-replay tests passed; the latter count
includes the former. Eight Python measurement tests and the native source
contract passed. One independent code review found no material defect after
correcting a test's assumption about enabled harmonic bands. These checks
validate observation and measurement behavior; they are not a new full
production build, deadline/validator pass or live-host certification.

The capture exposed a measurement problem before any classifier was trained:
raw phase derivatives showed large apparent motion even in known single
sources. The resonator's one-pole filter leaves fast spectral contamination;
differentiating its phase twice amplifies that contamination. This is a
plausible mechanism, not evidence of multiple strings. The offline module
therefore also provides a fixed two-stage causal 15 ms complex filter, using
the existing production fundamental phasor filter as its reference. It runs
over the full captured prefix and never resets at annotation boundaries.
It does not reproduce production candidate-state gating, undo prior aliasing,
or establish a source-dominant reference.

The saved-capture comparison uses `--source-run` and launches no build or new
audio replay. It compares raw and conditioned measurements on the same
observations. No filter sweep, string-count threshold or MIDI policy is
introduced.

Run `partial-motion-conditioning-20261103T1158Z` completed using the saved
capture. It verified each decompressed trace against its recorded SHA-256.
For the two known single sources, after one second of settling:

| Control | Raw frequency-error RMS across the six bands | Conditioned frequency-error RMS across the six bands |
| --- | --- | --- |
| Amplitude-modulated single | 48.83–89.94 cents | 0.213–0.683 cents |
| Two-decay single | 48.38–89.04 cents | 0.205–0.653 cents |

These ranges report individual band errors, not string-assignment accuracy.
The raw error's strongest oscillations were at roughly 165–338 Hz, consistent
with harmonic leakage/images. Filtering greatly reduces them, but the
remaining derivatives still exaggerate small fast errors. For harmonics one
and two, conditioned differential-motion RMS spans 630–2646 cents/second in
single-source windows, 5683–5726 in the simultaneous pair, and 913–2300 in
the staggered triple. **Motion magnitude alone does not separate the source
counts:** the entire tested triple range overlaps the single-source range.
That observation rejects a magnitude threshold on these features; it does
not test every possible conditioned feature or establish classifier gain.

### Fixed past-window phase slope

The offline estimator now fits unwrapped phase against time over a complete
past 160 ms window, then compares successive window slopes. The window and
emission period are fixed from the existing phase-evidence timescale. The
three-second unison admission window remains unchanged.

For centered sample times `u = t - mean(t)` and measured unwrapped phase
`phi`, the slope is `sum(u * phi) / sum(u^2)`. It estimates the frequency over
that past window, not the instantaneous frequency when the result becomes
available. For quadratic phase, its effective time is
`mean(t) + sum(u^3) / (2 * sum(u^2))`; this accounts for an irregular clock.
The implementation converts each harmonic's slope to a fundamental-equivalent
cent offset, using the recorded demodulation center. It compares frequency
changes and log-amplitude slopes separately.

Every increment must pass the amplitude, phase-step and clock-gap checks.
Missing or weak observations invalidate the affected window; no interpolation
fills the gap. Both the conditioning and window clock run over the full
captured prefix. Annotations select the scoring span only. A score assigned
to the first timestamp in a span can therefore include past audio from before
that span, as an online estimator would. Twelve valid motion observations
are required for a reported pair statistic; fewer observations mean no score.

Thirteen Python tests pass, including five added for exact chirp slopes on an
irregular clock, harmonic normalization, gain/prefix invariance, silence and
missing-data rejection, annotation-independent state, and rejection of known
fast single-source contamination. These are causal measurement tests, not a
string-count classifier test.

Run `partial-motion-phase-window-20261103T1208Z` completed on Modal using the
same verified saved observations. The fixed estimator further reduced
single-source frequency error:

| Control | Conditioned increment-frequency RMS | Past-window frequency RMS |
| --- | --- | --- |
| Amplitude-modulated single | 0.213–0.683 cents | 0.00115–0.01177 cents |
| Two-decay single | 0.205–0.653 cents | 0.00064–0.00593 cents |

For harmonics one and two, the new differential-motion RMS is 0.009–0.190
cents/second in the synthetic single-source windows and 14.022–18.896 in the
staggered triple. The simultaneous pair has one scored window at 0.457 and
one unavailable window with too few valid measurements. This shows that the
estimator suppresses fast single-source contamination while retaining some
mixture motion. It does not establish a source-count threshold.

The physical pair windows span 42.916–200.541 cents/second; scored physical
triple windows span 36.207–136.573. Those ranges overlap. One of the eight
physical triple windows lacks the required twelve motion observations and
abstains. These physical results rule out promoting motion magnitude alone.

Run `partial-motion-isolated-control-20261103T1213Z` then checked the original
2.3-second isolated note-40 annotation, verifying its label SHA-256 against
the capture. It provides twelve valid H1/H2 motion observations and measures
**40.592 cents/second**, inside the physical triple range. Its frequency-motion
correlation is only 0.078. The other harmonic pairs lack enough valid data:
the six bands have 13, 13, 5, 0, 0 and 0 valid phase-window estimates. This is
one diagnostic single-string control, not a complete three-second admission
example or a population error rate. It is enough to reject the proposed
standalone motion-magnitude cue. A threshold chosen from the synthetic
singles would have missed this real single-string counterexample.

Reproduce the saved comparison with a new output ID:

```sh
MODAL_PROFILE=research modal run --detach tools/modal_m3_partial_motion.py \
  --run-id partial-motion-phase-window-NEW \
  --source-run partial-motion-20261103T1151Z
```

## Current conclusion

The literature led to a working causal capture, a measurement correction and
a physical counterexample. It has not yet produced a measured improvement in
note/string assignment. Both fast filter contamination and real single-string
motion can mislead a source-count rule. The standalone motion-magnitude cue
is rejected; no classifier or MIDI change is promoted.

The reference-quality check below separates weak measurements from clock gaps
and phase failures. It does not establish that an available harmonic belongs
mainly to one string. Reference selection must use signal evidence alone.
If a reliable reference and independent physical takes are available, compare posterior-only against
posterior-plus-motion on whole held-out takes, with false added strings as
an explicit rejection condition. This remains a hypothesis about conditional
information, not another threshold on motion magnitude. The current single
physical unison take cannot establish that generalization result. Repeated
ownership or retention tweaks should not proceed on the strength of the
rejected handoff screen.

## Reference-quality measurement

The saved-capture analysis now explains availability for each enabled harmonic,
on every matching annotated hold. It counts weak or zero amplitude, nonfinite
samples, clock gaps, excessive phase increments and invalid inferred frequencies.
The same reasons propagate to the fixed 160 ms windows. Counts can overlap;
their union explains rejected measurements. Disabled detector bands are reported
separately. None of these diagnostics changes a validity decision.

Amplitude is reported relative to the largest amplitude observed so far across
the captured bands. This is the estimator's existing causal floor, not an SNR
or a measured noise floor. Phase-fit residuals describe departure from a straight
phase trajectory on accepted windows. A small residual establishes smoothness,
not a source-pure harmonic. Neither statistic selects a string or supplies a
classifier vote. Annotations select reporting spans after the full causal trace
has been processed; a window available near an onset can include earlier audio.

Seventeen focused tests pass. The four new tests check rejection accounting,
disabled/weak/empty observations, gain and prefix invariance, and the distinction
between phase curvature and a rejected observation. The Modal analysis reuses
the saved trace and annotation hashes and requires no new audio replay or
production build.

Run `partial-motion-reference-quality-20261103T1222Z` completed on Modal at
12:20:55 UTC. All earlier window statistics, short-hold diagnostics and
single-source control results are unchanged across the six saved datasets.
The new diagnostics explain the physical isolated note-40 measurement:

| Harmonic | Raw valid windows | Conditioned valid windows | Conditioned windows rejected for weak amplitude |
| --- | ---: | ---: | ---: |
| H1 | 13/14 | 13/14 | 1/14 |
| H2 | 6/14 | 13/14 | 1/14 |
| H3 | 3/14 | 5/14 | 9/14 |
| H4 | 10/14 | 0/14 | 14/14 |
| H5 | 8/14 | 0/14 | 14/14 |
| H6 | 6/14 | 0/14 | 14/14 |

All six bands are enabled, with no nonfinite samples or clock gaps in this
hold. After conditioning, the median H4/H5/H6 amplitude ratios are
0.000108, 0.0000748 and 0.0000310 against the existing 0.001 floor. Thus the
upper-band absence is a measurement-floor rejection, not a disabled band or
a missing capture. Filtering also removes much of their
apparent amplitude. The floor is relative to the past peak, so these numbers
do not establish a physical noise level or justify lowering the floor.

On the physical triple hold, conditioned availability is 152/164, 163/164,
150/164, 107/164, 82/164 and 69/164 windows for H1 through H6. H2 is available
in 99.39% of windows, but availability and a smooth phase fit do not identify
which string dominates it. The synthetic controls have much fuller upper-band
coverage than the physical isolated note. Training on those controls alone
would hide this mismatch.

This finishes the measurement diagnostic, not the source-separation decision.
Use the explicit availability masks in any conditional comparison. Do not
recover missing bands by relaxing the floor or interpret a smooth mixture
as an independent reference. Source-dominant reference coverage and added
information beyond the existing posterior remain unmeasured; the installed
MIDI output is unchanged.

## Additional literature and a useful stopping point

Three further primary sources clarify the next route:

| Source | Useful idea | Decision for M3 |
| --- | --- | --- |
| [Simionato and Bigo, 2026: Noise2Fret](https://arxiv.org/html/2608.30854v1) | Joint audio-to-tablature prediction with explicit fretboard constraints. Its ablation separates pitch detection from string assignment. | Consider as an offline comparator, not a callback replacement. The GOAT experiment uses annotated onset crops, standard tuning and excludes electric timbres; its six-string output is not our M3 representation. The reported real-time factor uses an RTX 3090 and does not establish callback deadlines. |
| [Benetos and Dixon, 2013: Temporally constrained shift-invariant transcription](https://openaccess.city.ac.uk/id/eprint/2155/) | Ordered attack, sustain and decay templates combine spectral evidence with a temporal model. | Check whether errors need state-dependent observations before adding persistence. The published multi-instrument task does not establish unison string identity. |
| [Wohlmayr, Stark and Pernkopf, 2011: Multipitch tracking with factorial hidden Markov models](https://tugraz.elsevierpure.com/en/publications/a-probabilistic-interaction-model-for-multipitch-tracking-with-fa/) | Keeps interacting source hypotheses through time and discusses an online inference schedule. | Useful as a design principle for joint temporal alternatives. The experiment is two-speaker speech, so neither its error reduction nor its mixture model transfers directly to guitar. |

The present physical motion capture contains four labeled plucks from one
original recording. Its thirteen complete windows are not thirteen independent
takes. The isolated note-40 hold lasts 2.3 seconds and supplies no complete
three-second admission window. Calibration recordings identify individual
strings; they do not create additional physical multi-string takes.

Also, the captured eight-value posterior is over one string at a time. A
playable mask or a rendered mask is not a joint-mask probability. Multiplying
those values would introduce an unvalidated independence assumption. There
is consequently no defensible held-out learned posterior-plus-motion result
to report from this capture. Keep the measurements for later independent-take
evaluation; do not run a classifier sweep on overlapping windows from this
recording.

The immediate research decision is to close the standalone motion experiment.
The existing `StringFretPosteriorBank::update()` already propagates an eight-way
string distribution through time, combines it with current observations and
weakens prior history at an onset. The detector can consume that distribution
in its joint allocation, but the production cost gate requires stable isolated
reassignment. The completed diagnostic below finds no posterior cost use in
the ordinary-chord capture. A second temporal smoother would duplicate an
existing estimator without resolving that allocation gate.

The next bounded step is to measure observation quality:

1. Inventory the saved isolated-note and ordinary-chord captures for posterior,
   onset and label alignment. Report missing fields before scheduling any
   additional capture. Reuse valid captures without rerunning the replay.
2. Report the labeled string's posterior rank and probability separately at
   onset and during settled sound, keeping recording identities and physical
   takes separate. A correct posterior followed by a wrong allocation directs
   inspection downstream to allocation. A wrong posterior requires separating
   current observation likelihoods from accumulated history before blaming
   either. Report unavailable likelihood fields instead of inferring this
   cause from the posterior or final MIDI counts alone.
3. Only if those results identify a repeatable observation failure, test
   attack/sustain-specific evidence offline against the current posterior.
   Require improvement on independent physical recordings and no protected
   corpus regression before considering an output trial. A learned comparison
   without independent physical coverage remains deferred.

This diagnostic has no MIDI output change and must preserve replay fingerprints.
Any later output candidate still needs at least 42,128/68,441 physical-long
matches and 25,604/39,378 exact three-string frames, with wrong strings no higher
than 2,709, plus the protected corpus and real-time gates. The literature gives
a testable route; no additional classifier gain or live-readiness improvement
has been measured.

## Completed string-evidence diagnostic — 2026-11-03

The next measurement is complete. Offline assignment traces now capture the
current likelihood inputs, cached prior, updated eight-string posterior and
onset strength at the same decision. The prior is the cached bank state before
its transition, not the transition-predicted distribution. Current likelihood
inputs already include causal filtering; they are not raw audio observations.
All new state and trace work is behind the offline diagnostic build guard.
Annotations enter scoring after the decision and never affect allocation.

Modal run `string-evidence-20261103T1258Z`, app
`ap-NqWlIq6poZhVuSSxuzutvJ`, completed at 13:05:27 UTC. The report is
`build/modal/string-evidence-20261103T1258Z.json`. Ordinary chords and isolated
string 8 have identical output fingerprints, counts and trace bytes at block
sizes 32, 512 and 1024. The traced outputs also match the untraced control.
The native offline suite passes 46 tests; the streaming analysis passes 10
Python tests and the source-contract suite passes 32. One focused review found
no consequential defect. These results do not constitute a new production
build, deadline result, validator result or installation.

The diagnostic samples every 1,024 audio samples. Its counts below are
annotated note/tick pairs, not full replay frames or a count of independent
performances. Ranks require one feasible expected string, available likelihood
inputs and a successful posterior update. The complete scoring grid retains
ticks without an assignment row as unavailable; it does not assume these are
missing MIDI notes.

| Ordinary chords: annotation age | Target pairs | Available ranks | Current likelihood correct | Updated posterior correct | Exact rendered string mask |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0–100 ms | 4,679 | 1,331 | 633 | 621 | 362 |
| 100–350 ms | 11,684 | 5,232 | 3,314 | 3,350 | 2,638 |
| At least 350 ms | 16,676 | 7,544 | 4,954 | 5,007 | 5,349 |
| Total | 33,039 | 14,107 | 8,901 | 8,978 | 8,349 |

History corrects 386 likelihood rankings and spoils 309: a net 77 additional
correct rankings, from 63.10% to 63.64% of the available ranks. It is not the
dominant explanation for the observed allocation disagreements. In 2,725
valid allocation decisions, both rankings favor the labeled string while the
joint allocator chooses another. Later rendering recovers the expected string
in 402 of these decisions; it remains absent in 2,323. Intermediate allocator
disagreement must therefore be separated from final output failure.

The saved ordinary trace gives this breakdown of the 2,323 unresolved cases:

| Observed allocation obstacle | Decimated decisions |
| --- | ---: |
| Expected string reserved by a coasting voice | 622 |
| Expected string reserved by an extra unison member | 1 |
| Expected string has lower local cost, but joint allocation differs | 567 |
| Wrong string has lower local cost; profile term is the largest contributor | 391 |
| Same, fret term | 236 |
| Same, cents term | 202 |
| Same, open-string term | 67 |
| Same, retention term | 237 |

Reservations are classified first; remaining local costs are compared only on
valid decisions. The largest positive cost difference is descriptive, not an
isolated causal effect. These counts do not predict gains from changing a
weight: changing ownership also changes later evidence and MIDI lifecycle.
The reproducible saved-trace extraction is
`build/modal/string_evidence_cost_diagnosis.py`, with results in
`build/modal/string-evidence-20261103T1258Z-cost-diagnosis.json`.

Isolated string 8 supplies an important control. Of 1,902 available ranks,
current likelihood is correct in 1,891 and the posterior in 1,895. All 1,647
settled annotated pairs render the expected string exactly, despite 144
intermediate allocator disagreements. A blanket replacement of downstream
assignment would risk removing a correction that already works. These are
conditional diagnostic counts; the full replay remains 29,816/31,050 matched
frames, with 2,462 wrong-note outputs, 579 wrong-string outputs and 2,928 extra
outputs during unlabeled gaps. Ordinary replay remains 145,385/528,632, with
164,263 wrong-note outputs, 92,653 wrong-string outputs and 62,856 extra gap
outputs. Extra outputs are separate from matched-frame percentages.

### Route selected from the evidence

Investigate provisional string cost ordering on fresh ordinary chord attacks
before adding a new classifier or more history. The existing likelihood can
favor the right string while profile/fret costs favor another, and its
posterior penalty is disabled for these chord decisions. Start with those
unreserved local-cost disagreements, keeping coasting owners, committed
strings and resolved unison groups intact. Do not weaken release or retention
to recover the reserved cases; earlier ownership and joint-posterior trials
already failed protected replay checks.

The selected bounded step was a saved-trace shadow comparison of one observation
cost formulation, using the captured likelihood and feasible strings. It must
account for both corrected and spoiled assignments and for downstream
recoveries, with no annotation-dependent proposal rule. It cannot establish
MIDI improvement because it does not evolve state. Only a useful shadow result
justifies one opt-in causal replay on Modal. That replay must improve ordinary
matches above 145,385 while keeping wrong notes <=164,263, wrong strings
<=92,653 and extra gap outputs <=62,856 on the same control source. It must
then preserve every isolated, constructed-chord, short-unison and four-string
gate and meet the physical-long targets above. The full native, real-time,
allocation, lifecycle, source-contract, build and validator gates still apply
before installation. No new output candidate has passed those gates.

### Observation-cost shadow result, 2026-11-03

The fixed formulation replaces profile and cents penalties with the captured
current log likelihood, once, at the existing native posterior scale:
`0.005 * fret + 2 * (maximum feasible likelihood - lane likelihood)`, plus the
existing open-string and provisional retention terms. There was no parameter
search or fit to annotations. Existing reserved lanes stay reserved; rows
outside the recorded eligibility guards keep their native primary string.
Labels and rendered output are used only to score decisions.

Before comparing costs, the auditor reproduces native sequential floating-point
additions, state order and packed-string tie breaking. It exactly reproduces
8,663 feasible sampled frames, with no mismatches; 746 native-infeasible frames
are excluded. Of 19,212 compared candidate rows, 12,232 are eligible for the
alternative cost. The trace lacks pre-assignment selector and pending-group
state, so this remains a conditional diagnostic, not an integration-ready guard.

| Single-string targets in reconstructed decisions | Correct / 12,867 | Match percentage |
| --- | ---: | ---: |
| Native intermediate assignment | 7,636 | 59.35% |
| Observation-cost shadow | 7,307 | 56.79% |

**Rejected.** The formulation corrects 607 assignments and spoils 936: net
-329 (-4.31% relative, -2.56 percentage points). None of the 607 corrections
was already recovered in the rendered mask. Another 928 changed assignments
have a correct rendered string at risk, without proving that final MIDI would
lose it. The shadow also changes 1,125 unlabeled decisions; those are not
claimed as gains. These sampled intermediate counts are not audio replay
results or a prediction of the full MIDI error count.

The tool is `tools/string_observation_shadow.py`; its report is
`build/modal/provisional-observation-cost-shadow-20261103.json`. It streams the
saved trace and verifies its uncompressed SHA-256 against the capture report.
Twenty focused Python tests cover this comparison and the earlier evidence
auditor. The installed plugin is unchanged. The failed shadow does not justify
a new causal replay or protected-corpus expansion.

The next useful question is which likelihood components cause the spoiled
ordinary-chord choices. Reconstruct available profile, cents and detuning
contributions before adding measurements. Separate mixture contamination from
calibration bias and history; promoting the existing likelihood wholesale has
now failed its first screen. Any later candidate retains the acceptance and
production gates above.

### Which likelihood terms overturn correct string choices

The next capture records the exact weighted, centered partial-detuning
contribution for each feasible string, with a separate availability mask.
Both fields exist only in offline diagnostics. Zero contribution does not
mean missing evidence. The native calculation and production state are
unchanged.

`tools/string_likelihood_decomposition.py` separates the captured likelihood
into profile, phase-derived cents, partial detuning and the remaining spectral
descriptor contribution. It compares only playable, unreserved lanes: native
profile costs are not computed for reserved lanes. It verifies the trace hash,
sample clock and row count before reporting results. The margins below are
expected-string likelihood minus competing-string likelihood; positive favors
the expected string.

| Changed assignments in the rejected shadow | Corrected: 607 | Spoiled: 936 |
| --- | ---: | ---: |
| Descriptor favors the expected string | 558 | 133 |
| Descriptor favors the competing string | 49 | 803 |
| Cents favor the expected string | 36 | 758 |
| Both strings have detuning evidence | 221 | 178 |
| Mean profile margin | -0.0615 | +0.0646 |
| Mean cents margin | -0.9265 | +6.0796 |
| Mean detuning margin | +1.9015 | -2.8259 |
| Mean descriptor margin | +24.4819 | -18.7109 |

In 623 of the 936 spoiled pairs, the descriptor contribution reverses a
positive sum of the other likelihood terms. Detuning does so in 95 pairs;
these are separate component comparisons, not disjoint error categories.
Descriptor plus detuning reverse the profile-plus-cents preference in 799
pairs. Among the corrected pairs, however, the descriptor rescues 350 that
the other terms favor incorrectly. Removing this cue wholesale is therefore
not supported by this diagnosis.

The decomposition reproduces all 607 corrections and 936 spoiled assignments
from the earlier shadow. Of 1,067 changes between two wrong strings, 429 have
an unavailable expected lane and are excluded from component comparisons.
None of these pairwise margins is a causal MIDI gain or an independent
performance. The result is in
`build/modal/string-likelihood-components-20261103.json`, from capture
`string-detuning-evidence-20261103T1340Z`.

The next bounded question is whether overlapping notes distort the spectral
descriptor, or whether the isolated calibration itself is biased. Compare
the existing isolated and chord observations at the same note/string, with
attack and sustain kept separate. Examine corridor overlap and individual
descriptor residuals before changing weights. Missing detuning evidence must
remain distinct from a measured neutral result. Hold out whole recorded
segments and preserve corpus identities; a single physical take cannot prove
generalization across performances.

Only a fixed, signal-derived reliability rule with more corrected than
spoiled assignments and no loss of protected downstream recoveries should
advance to one causal Modal replay. The existing ordinary, physical-unison,
isolated, constructed-chord, false-output and real-time gates still apply.
This finding narrows the research route; it does not accept a new output
candidate.

The Modal capture completed at 13:48:45 UTC. Ordinary chords and isolated
string 8 retain their untraced control counts and fingerprints at blocks 32,
512 and 1024; the new trace bytes are identical across those block sizes.
All 46 native offline tests passed. A separate targeted cloud check passed
the strengthened known-signal assertion for the detuning term's sign and
weight. Fifty-seven Python checks passed, including the source contract.
One focused review is complete. The installed bundle is unchanged; no new
production build, callback deadline result, validator result or installation
is claimed for this diagnostic slice.

### Matched isolated and chord evidence, 2026-11-03

The saved traces support a narrow comparison: string 8 at MIDI notes 36–40,
against playable competing strings 7 and, for note 40, 6. Notes 32–35 have no
alternative playable string, and the older middle/high-string captures lack
the required per-frame likelihood fields. Those cases cannot answer this
question. Both compared captures use the same calibration, settings and
sample rate; their decompressed trace hashes are verified before analysis.

`tools/string_descriptor_context.py` compares the expected-minus-competing
descriptor margin at the same pitch, string, fret and annotation age. Negative
means the descriptor favors the competing string. Attack is 0–100 ms; sustain
starts at 350 ms. The middle interval is excluded from this comparison. Each
annotation segment receives equal weight within a comparison, and the report
retains segment and connected-episode counts. These are repeated observations
from two recordings, not independent performances. Missing rows, unavailable
likelihoods and reserved string pairs are excluded rather than scored as zero.

For sustained observations, the percentage favoring the wrong competing
string is:

| MIDI note / competitor | Isolated string 8 | Ordinary chords | Difference | Chord segments / isolated segments |
| --- | ---: | ---: | ---: | ---: |
| 36 / string 7 | 0.00% | 98.65% | +98.65 pp | 2 / 1 |
| 37 / string 7 | 13.66% | 85.61% | +71.94 pp | 5 / 1 |
| 38 / string 7 | 55.19% | 85.46% | +30.27 pp | 6 / 1 |
| 39 / string 7 | 4.37% | 72.97% | +68.60 pp | 3 / 1 |
| 40 / string 7 | 0.00% | 43.86% | +43.86 pp | 3 / 1 |
| 40 / string 6 | 0.00% | 7.89% | +7.89 pp | 2 / 1 |

All six attack comparisons also worsen in chords, by 10–100 percentage
points. Across attack and sustain, the analysis measures 721 eligible chord
pairs and 1,130 isolated pairs. These are pairwise descriptor measurements,
not complete string rankings or final MIDI errors. In particular, note 38
already has substantial isolated ambiguity. Chord context is associated with
worse evidence, but the different performances prevent attributing the whole
difference to overlap.

The physical route is specific. The descriptor uses harmonic-centered
heterodyne cells with a 40 ms one-pole memory, then normalizes harmonic energy
and compares log ratios and spectral balance against calibrated strings.
Other notes can contribute energy to these cells; normalization then changes
the whole descriptor. Fast and settled memories can carry that contamination
forward. This mechanism is plausible from the implementation and the matched
results; it is not yet a measured causal effect.

The next experiment should hold the target waveform fixed: replay an isolated
target alone, then mix that exact target with an existing isolated note.
Compare harmonically colliding and separated notes at declared mix levels,
with target onset and calibration unchanged. Report the induced descriptor
margin change and candidate/phase availability separately. Synthetic mixing
can test interference in this signal path; it cannot establish accuracy on
independent physical performances or justify changing production weights.
Only a signal-derived reliability rule that passes held-out correction-versus-
spoil and downstream-recovery checks may advance to causal MIDI replay.

Modal `descriptor-context-20261103T1407Z` completed this saved-trace analysis
at 14:07:07 UTC, app `ap-HpS34OtwJINmvZ0iaWK3wi`. The result is
`build/modal/descriptor-context-20261103T1407Z.json`. It used one CPU and
performed no audio replay or native build. Thirty-three focused Python tests
pass. The earlier ordinary/string-8 capture parity checks remain valid;
this analysis supplies no new production, deadline, validator or live-use
result. The installed plugin and acceptance targets are unchanged.

### Controlled waveform overlap, 2026-11-03

The controlled experiment holds one physical string-8 MIDI-36 waveform fixed
and adds a physical string-5 MIDI-48 or MIDI-49 waveform at -12 dB and 0 dB
relative RMS. The source crops, annotations, calibration and analysis files
are hashed in the report. All five cases share the target samples, onset,
gain, 250 ms leading silence and one-second release tail. A common peak-safe
gain is computed across every case; it was 1.0 for these recordings. There
is no individual mixture normalization, pitch correction or phase alignment.

`tools/controlled_descriptor_overlap.py` pairs descriptor observations at the
same sample and compares the expected string 8 with playable competitor
string 7. Missing target rows and reserved/infeasible pairs are retained as
separate coverage counts. They never become zero-valued evidence. A negative
descriptor margin favors the competing string.

| Case | Eligible paired observations / 216 sampled target frames | Missing target row | Reserved/infeasible pair | Sustained wrong descriptor margins | Mean sustained margin change |
| --- | ---: | ---: | ---: | ---: | ---: |
| Target alone | 211 | 5 | 0 | 0 / 183 | Reference |
| Added MIDI 48, -12 dB | 142 | 6 | 68 | 2 / 116 (1.72%) | +1.849 |
| Added MIDI 48, 0 dB | 154 | 5 | 57 | 0 / 142 (0.00%) | +5.706 |
| Added MIDI 49, -12 dB | 211 | 5 | 0 | 0 / 183 (0.00%) | -1.443 |
| Added MIDI 49, 0 dB | 85 | 130 | 1 | 2 / 66 (3.03%) | -4.374 |

The target-alone descriptor favors the expected string on every eligible
paired row. The positive changes in the MIDI-48 cases strengthen that pairwise
preference. Added MIDI 49 weakens it, and short attack/early observations can
flip, but this experiment does not reproduce the broad sustained descriptor
collapse suggested by the earlier comparison between different performances.
Blanket descriptor reweighting is not supported by these results.

The generated probes do expose downstream failures:

| Case | Matched / labeled frames | Match rate | Wrong notes | Wrong strings | Extra outputs in unlabeled gaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Target alone | 3210 / 3450 | 93.04% | 486 | 163 | 326 |
| Added MIDI 48, -12 dB | 2077 / 6900 | 30.10% | 384 | 1292 | 325 |
| Added MIDI 48, 0 dB | 471 / 6900 | 6.83% | 2066 | 6169 | 652 |
| Added MIDI 49, -12 dB | 0 / 6900 | 0.00% | 3378 | 4047 | 646 |
| Added MIDI 49, 0 dB | 3250 / 6900 | 47.10% | 3383 | 1642 | 740 |

These percentages measure expected note/string assignments found in labeled
audio; false outputs are separate. They are not overall accuracy. The solo
and mixture denominators differ because each mixture has two expected voices.
These short constructed probes are not replacements for the protected corpus
or independent physical performances.

Two observations narrow the next diagnosis. With quiet added MIDI 49, the
target is available on 211 sampled rows and its descriptor favors the expected
string throughout, yet neither expected voice matches in the full replay.
With equal-RMS added MIDI 49, the target row is absent on 130 sampled frames,
compared with five in the solo control. An absent assignment-trace row is not
by itself proof of missing MIDI or a particular detector failure. Inspect the
saved assignment/selection path to distinguish candidate admission, ownership
and final rendering before proposing a policy change.

The target source is approximately -43.21 cents from its nominal note; the
added sources are +7.18 and +4.51 cents. Thus MIDI 48 is a nominal octave,
not an exact coincidence of harmonics. Added spectra, tuning and envelopes
differ together. One target take and one competing string cannot establish
generalization, and descriptor comparisons are conditional on both lanes
being available and unreserved. The experiment establishes the effect of
adding these exact recorded waveforms, not an isolated collision mechanism.

Modal `controlled-descriptor-overlap-20261103T1423Z`, app
`ap-zrlKXf4xao0BqzCa6toH18`, completed at 14:24:59 UTC. The final report is
`build/modal/controlled-descriptor-overlap-20261103T1423Z.json`; the persistent
volume retains each waveform, label file, compressed assignment trace and
paired observation file. All five cases match their untraced controls and
have identical output fingerprints and trace bytes at blocks 32, 512 and
1024. Twenty focused Python tests, Python compilation and the whitespace
check pass; one focused code review found no consequential issues. This is
an offline diagnostic with no changed native policy or installed output.
No new production, callback deadline, validator or live-use result is claimed.

### Saved-mixture selection diagnosis, 2026-11-03

One additional replay of the saved equal-RMS MIDI-49 mixture separates the
loss before assignment from string-ranking errors. It reuses the exact
waveform, annotations, calibration and native binary from the five-case
control. `tools/selection_trace_diagnosis.py` joins every labeled target
candidate tick to the outcome trace and the saved sampled assignment trace.
It checks clock alignment, full candidate/outcome coverage and agreement of
selection dispositions. An absent outcome entry keeps selector-pool
membership unknown; it is never converted into zero evidence.

| Sampled MIDI-36 assignment row | Frames | Selection disposition |
| --- | ---: | --- |
| Present | 86 / 216 | Selected on all 86 |
| Absent: raw eligibility failed | 117 / 216 | `below_threshold` |
| Absent: quiet/startup | 5 / 216 | `quiet` |
| Absent: coasting | 4 / 216 | `coasting` |
| Absent: selector eviction | 4 / 216 | `dp_evicted`, confirmed in selector pool |

Thus 117/130 (90.00%) of the missing sampled assignment rows fail the earlier
eligibility gate. Across all 3450 labeled target ticks, the dispositions are
1800 below threshold, 1459 selected, 66 coasting, 50 selector evictions and
75 quiet/startup. These are intermediate candidate observations, not final
MIDI error counts or independent performances.

The diagnostic name `below_threshold` is broader than a low amplitude score.
All 1800 such ticks have `score_ratio > 1`: minimum 2.840, median 4.087,
maximum 5.096. All have active, local-peak and candidate-evidence flags false;
1273 still have direct-fundamental support. The sampled 117-tick subset has
the same three false flags, 117 scores above threshold and 84 direct peaks.
The production expression is `active || local_peak || candidate_evidence`
after the scalar threshold check. Its failure explains this exclusion; a
general reduction of the amplitude threshold would not satisfy that gate.
MIDI 37 is selected/coasting on 93 of those 117 sampled ticks, and the added
MIDI 49 on all 117. That association motivates inspecting neighboring pitch
competition, but does not yet prove why the evidence flags fail.

The next bounded implementation should address that admission decision in
offline mode. First distinguish an independent low fundamental from the
added note's lower-octave candidate using the existing peak, harmonic and
calibration evidence. Do not admit a candidate merely because it has a direct
peak or an expected annotation. A proposed guard must improve the saved
mixture without more wrong notes, wrong strings or extra gap outputs, then
improve ordinary matches beyond 145385 with wrong notes <=164263, wrong
strings <=92653 and extra gap outputs <=62856. Every protected unison,
isolated and constructed-chord gate and all realtime/lifecycle checks still
follow. This single detuned target take cannot establish generalization.

Modal `controlled-selection-20261103T1438Z`, app
`ap-EdN3xo0azmWOcY5DHaerud`, completed at 14:38:07 UTC. Report:
`build/modal/controlled-selection-20261103T1438Z.json`. Its binary hash equals
the source control and output fingerprint remains `095d8d9a3e2d65ec`:
3250/6900 matches (47.10%), 3383 wrong notes, 1642 wrong strings, 740 extra
outputs during unlabeled gaps and 5765 total false outputs. Every count is
unchanged. The supplemental `-threshold-breakdown.json` comes from the
hash-verified saved candidate trace. The source five-case 32/512/1024 parity
checks remain valid; this follow-up uses block 512 only and does not claim a
new three-block matrix. Three focused tests, Python compilation and the
whitespace check pass; one focused review found no consequential issue.
No native policy, installed output or release-gate result changed.

### Controlled fundamental-admission trial, 2026-11-03

The saved selection trace located the exclusion before assignment. A bounded
offline intervention then tested whether direct fundamental evidence could
recover that candidate safely. `--diagnostic-fundamental-admission` is off by
default and compiled only with offline diagnostics. It requires a playable
candidate outside the narrow profile, a score above the unchanged threshold,
a direct peak and fundamental support at least 0.85 of its score. A stronger
ordinary-eligible candidate must not explain it through the existing harmonic
or lower-crossharmonic checks. Ordinary eligibility is frozen before this
check, so new admissions cannot recursively justify others. Existing ranking,
polyphony and downstream behavior remain in place.

One Modal build replayed the five exact cached waveforms with the flag OFF
and ON at block 512. All five OFF controls match their saved output fields,
including fingerprints. Counts below describe final replay output, not the
intermediate candidate trace. WN is wrong-note outputs, WS wrong-string
outputs, EG extra outputs during unlabeled gaps, and FP total false outputs.
EG does not count missing notes. Match percentages measure expected annotated
note/string assignments found; they do not include the false-output penalty.

| Case | Matches OFF → ON / labeled | Match rate OFF → ON | Δ WN | Δ WS | Δ EG | Δ FP | Result |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Solo low note | 3210 → 3210 / 3450 | 93.04% → 93.04% | 0 | 0 | 0 | 0 | Unchanged |
| Added octave, -12 dB | 2077 → 2071 / 6900 | 30.10% → 30.01% | +26 | +6 | 0 | +32 | Rejected |
| Added octave, equal RMS | 471 → 1271 / 6900 | 6.83% → 18.42% | -829 | -800 | 0 | -1629 | Aggregate improvement |
| Added nearby note, -12 dB | 0 → 0 / 6900 | 0.00% → 0.00% | 0 | 0 | 0 | 0 | Unchanged |
| Added nearby note, equal RMS | 3250 → 3507 / 6900 | 47.10% → 50.83% | +149 | +1505 | +12 | +1666 | Rejected |

In the main nearby-note case, 257 additional matches are a 7.91% relative
increase and a 3.72 percentage-point increase in matched frames. Total false
outputs rise from 5765 to 7431, or 28.90%. The quieter octave also loses six
matches. Those regressions reject the rule before a full corpus screen.
No production integration or installation follows from the favorable octave
case. This experiment does not isolate which admitted candidate causes every
extra output, and it does not support a threshold sweep.

One review found a scoring defect: the original report's `target_improved`
field actually measures aggregate matches across both notes. Its value is
not evidence that the intended low MIDI-36/string-8 target improved. This
completed run did not save label details, so target-specific gain is **not
measured**. The original report remains unchanged; higher false-output counts
are sufficient to reject the rule without rerunning it.

Future runs use `tools/controlled_admission_gate.py`, gate version
`target-note-v2`. They save `--label-details` and require exactly one matching
MIDI-36/string-mask-1 label with identical identity, span and frame accounting
between OFF and ON. Every case must preserve target matches and aggregate
matches, with no increase in WN, WS, EG or FP. The equal-RMS nearby-note case
must strictly improve the target's matches. Missing, duplicate, inconsistent
or malformed target evidence fails closed. An improvement confined to the
added note cannot satisfy this gate or hide a target loss.

Modal `controlled-admission-20261103T1457Z`, app
`ap-IAhnUeIrJYnBEkFjBz9CCs`, completed at 14:59:37 UTC. Report:
`build/modal/controlled-admission-20261103T1457Z.json`. The cloud build passed
53 focused native tests: two fundamental-admission, five calibrated harmonic
admission and 46 offline replay tests. Six local tests cover the corrected
gate and parser, including misleading aggregate gains, target losses,
individual safety regressions and absent or inconsistent evidence. Python
compilation, the source contract and whitespace checks pass. One review is
complete and its scoring correction is addressed. The first build attempt
failed before replay because test access was not enabled consistently; the
successful build applies `M3_TESTING` across the optional test build.

This ON trial has no three-block parity, full native-suite, callback deadline,
allocation, production-build, validator or live-use result. Earlier control
parity at 32/512/1024 remains separate. The accepted three-second evidence
window, 0.20 beat-coherence gate, 0.50 retention floor and measured baseline
settings remain unchanged.

The next useful experiment must first establish an independent source cue:
for example, a usable non-overlapping higher partial whose causal frequency
and envelope changes support the low candidate across these fixed mixtures.
The overlapping-partial papers above supply a method to investigate, not a
validated cue for these recordings. A single-string counterexample and the
quiet/equal-level controls must reject harmonic impostors before another
output trial. A successful proposal must then pass the target-specific gate,
improve ordinary matches beyond 145385 while preserving its error ceilings,
and pass every protected corpus and real-time/lifecycle gate. If no usable
reference exists, keep the evidence unavailable rather than infer a source
from a better-fitting mixture alone.

### Local reference for weak odd overtones, 2026-11-03

The first independent-partial measurement found no usable third/fifth-overtone
pair: 0/1080 target-present frames and 0/864 source-only frames for the target
hypothesis. Inspection explains the zero without establishing a new cue. The
fifth overtone has a measurable peak in most frames, including the isolated
low note, but none clears the fixed 1% global power floor. Removing that
floor alone would also admit weak peaks from the upper-string controls.

The additive measurement in `tools/independent_partial_evidence.py` compares
each peak with the larger median power in two fixed sidebands. The sidebands
sit three to five window-frequency bins away from the nominal harmonic;
FFT padding does not change their width. Missing, zero or out-of-range
references remain unavailable. Raw third/fifth pitch agreement is recorded
regardless of the original power-floor result. Source-component powers are
used only to score attribution, never to select a peak or form the feature.

Modal `independent-partials-local-reference-20261103T2226Z`, app
`ap-OSl5pMhurkBJzMeraAhu5J`, completed at 22:27:17 UTC. It reconstructed the
five exact saved mixtures and four source-only controls from hash-verified
crops. Report: `build/modal/independent-partials-local-reference-20261103T2226Z.json`.
All nine original case metric groups match the earlier
`build/modal/independent-partials-20261103T1517Z.json` report. No native build,
MIDI replay or installed-output change was made.

The paired feature is the smaller of the third- and fifth-overtone local
contrasts. Negative observations include both MIDI 36 and absent MIDI 37 in
source-only controls, plus absent MIDI 37 in the mixtures. Their observed
maximum is `8.593275855114637` dB for the pair and `15.308089377125054` dB
for the fifth overtone alone. These are descriptive maxima from the same
recordings, not independently validated decision thresholds.

| Case | Scored target frames | Fifth above control maximum | Pair above control maximum | Both pair peaks target-dominated |
| --- | ---: | ---: | ---: | ---: |
| Solo low note | 216 | 71 | 97 | 97 |
| Added octave, -12 dB | 216 | 52 | 79 | 76 |
| Added octave, equal RMS | 216 | 27 | 64 | 49 |
| Added nearby note, -12 dB | 216 | 51 | 76 | 76 |
| Added nearby note, equal RMS | 216 | 0 | 31 | 31 |

Target-dominated means a source-component power share of at least 0.90 for
both selected peaks. This accounting omits interference cross terms and does
not prove source independence. The hardest mixture gives 31/216 paired
contrast frames (14.35%), while the fifth alone gives none. The table does
not apply the pitch-agreement condition, count recovered MIDI or establish
safety. Overlapping windows and gain variants of the same low-note take are
not independent observations or performances.

The next experiment freezes the paired contrast threshold at strictly above
`8.593275855114637` dB and retains the existing 25-cent pitch-agreement limit.
Test separate recorded low and upper-string takes, keeping source-only and
absent-neighbor controls, before considering any admission change. Report
joint feature availability and accepted frames, including note-free intervals;
require useful target evidence with zero false cues in those controls. If no
separate takes exist, report that coverage gap rather than relabeling the
same samples as held-out evidence. Passing this screen only permits the
existing target-specific MIDI replay gate. It does not replace the ordinary
match/error limits, protected recordings or realtime/lifecycle checks.

Eleven focused Python tests pass. They cover causality, gain invariance,
source-component separation, weak but measurable fifth overtones, fixed
sideband selection, absent-note/source-only control accounting and missing
reference handling. Compilation passes, and one focused review is complete.
The analysis uses a past-only 16384-sample window at 96 kHz (170.7 ms); it is
an offline measurement, not a callback timing result or a replacement for
the accepted three-second evidence window.

### Frozen overtone screen on held-out plucks, 2026-11-03

The first pluck in calibration pass 2 was selected for each of MIDI 36, 48
and 49 before measuring the spectrum. Pass-1 raw crops are byte-identical to
the earlier representative training crops; the selected pass-2 spans are
disjoint, with different sample hashes. The manifest records source spans,
label hashes, crop hashes and the frozen rule. No pitch correction,
resampling or crop-specific gain was applied.

The rule requires both H3/H5 local contrasts to exceed
`8.593275855114637` dB and their fundamental-frequency estimates to agree
within 25 cents. Neither labels nor component spectra enter that decision.
The feature code rejects missing and nonfinite evidence. The scorer separates
the causal window tail from wholly note-free windows; the first clear window
ends at `end_sample + window_samples - 1`.

Modal `independent-partials-heldout-20261103T2239Z`, app
`ap-y9qUIPMP9TxRFAquViIciT`, completed at 22:39:53 UTC. Final report:
`build/modal/independent-partials-heldout-20261103T2239Z.json`.

| Held-out target case | Cue frames / observed frames | Cue percentage | First cue after labeled crop start |
| --- | ---: | ---: | ---: |
| Solo low note | 141/216 | 65.28% | 155.33 ms |
| Added octave, -12 dB | 140/216 | 64.81% | 155.33 ms |
| Added octave, equal RMS | 83/216 | 38.43% | 166.00 ms |
| Added nearby note, -12 dB | 122/216 | 56.48% | 155.33 ms |
| Added nearby note, equal RMS | 34/216 | 15.74% | 155.33 ms |

The frozen diagnostic passes its stated screen: useful evidence in all five
target cases, 520/1080 target-present cue frames (48.15%), no cues in 3240
absent-note observations, and no cues in 1700 clear-gap observations. The
negative set includes absent MIDI 37 in each mixture, MIDI 36/37 in the four
higher-note-only controls, and both hypotheses in digital silence. The clear
gap count includes available history before the crop and wholly empty windows
after it. Window-tail cues are zero and reported separately.

This is repeatability on separate plucks from the same source recording
session. Mixtures reuse those plucks, so gain variants and overlapping frames
are correlated. Digital silence does not measure room-noise safety. The
16384-sample causal window spans 170.7 ms at 96 kHz; first-cue timing is
relative to the annotated crop boundary, not a measured pick-to-MIDI latency.
No string assignment, recovered MIDI, native timing, installation or live-use
improvement follows from these counts.

The next step is a default-off native replay experiment using the frozen
signal-derived cues. The target-specific gate must show a strict MIDI36 /
string-mask1 gain in the equal-level nearby-note case, no target or aggregate
match loss and no higher error count in any control. OFF output must remain
identical. A passing output experiment can then advance to ordinary matches
above 145385 with its error ceilings preserved, protected recordings,
partition parity, timing/allocation and lifecycle/actual-host checks.

Thirteen focused Python tests pass, including strict contrast and inclusive
pitch boundaries, missing/nonfinite rejection, unavailable history, explicit
absent-note false cues, and the exact tail-to-gap boundary. Compilation and
whitespace checks pass. The installed plugin and default MIDI policy are
unchanged.

### Frozen-cue replay and assignment diagnosis, 2026-11-03

The frozen signal cue did not improve native replay. The default-off
`--diagnostic-odd-partial-cues` sidecar admits only cue-backed candidates
through the existing direct-fundamental diagnostic guard. It does not boost
their rank, force a string, lower a threshold or bypass later harmonic and
assignment checks. Cue intervals start after the feature's last observed
sample, and each decision uses only the interval active at that sample.

Modal `frozen-cue-replay-20261103T2259Z`, app
`ap-eOOpj5SiCoAPpXf684Oi3V`, completed at 23:02:07 UTC. All ten held-out
cases have identical saved-baseline, new-OFF and new-ON output fingerprints
and counts. ON also matches at block sizes 32/512/1024. The target-specific
gate rejects the candidate because it recovers no additional target frames.

| Equal-level nearby-note mixture | Before | After |
| --- | ---: | ---: |
| Expected MIDI 36 / string-mask 1 matches | 815/3450 (23.62%) | 815/3450 (23.62%) |
| Aggregate expected assignments | 2987/6900 (43.29%) | 2987/6900 (43.29%) |
| Wrong-note outputs | 3178 | 3178 |
| Wrong-string outputs | 1548 | 1548 |
| Extra outputs during unlabeled gaps | 668 | 668 |
| Total false outputs | 5394 | 5394 |

No control loses target or aggregate matches or increases an error count.
These are expected-assignment match rates; false outputs are counted
separately. The passing feature screen remains evidence that the cue exists,
not evidence that the native policy uses it to recover notes.

One follow-up, `frozen-cue-selection-20261103T2310Z`, app
`ap-6bdpsEetQf7CRlyZ5q5uN3`, completed at 23:09:44 UTC. It reused the
saved binary, waveform, labels, calibration and cue file, preserved the
output fingerprint, and captured all 3450 target candidate rows and 5325
outcome rows without truncation. Downloaded traces and cues match the
recorded hashes. `tools/frozen_cue_diagnosis.py` joins each causal interval
to the native matched-label flags and checks those flags against emitted
note/string identities.

The cue is active for 544 labeled decisions: 222 match the target (40.81%)
and 322 do not. The misses break down as follows:

| Target disposition | Wrong string | No target output |
| --- | ---: | ---: |
| Selected | 186 | 0 |
| Coasting | 24 | 2 |
| Below admission | 0 | 97 |
| Selector eviction | 0 | 13 |
| Total | 210 | 112 |

All 210 wrong-string outputs retain MIDI 36 but use internal string index 1
instead of the annotated index 0. None of the misses changes a detected
MIDI 36 to another output pitch. Every below-admission miss exceeds the
scalar score threshold; seven lack a direct peak, 47 fail the 0.85
fundamental-ratio check, and 43 fail both. Relaxing a scalar threshold cannot
address these observed prerequisites.

The expected string carries another output in 148 misses, MIDI 35 in 147
and MIDI 47 in one. The target descriptor prefers the expected string in
153 of the 223 misses with a reported target candidate; the remaining 99
entries are unreported. These observations motivate an assignment experiment,
but do not establish that evicting a competitor would be safe. The next
candidate must use signal-derived pitch and string evidence without reading
the expected labels or forcing this particular note onto a known string.

Require a strict gain above 815/3450 target matches in nearby_0dB, no target
or aggregate loss and no higher false-output count in any control, plus exact
OFF equality. Only a passing result advances to the ordinary-recording and
protected corpus gates. Reports remain in `build/modal/`; the supplemental
saved-trace analysis is
`frozen-cue-selection-20261103T2310Z-output-diagnosis.json`.

Fifty-six focused native tests and 28 Python tests pass, including causal
boundaries, missing-trace rejection and separate wrong-string, changed-pitch
and absent-output accounting. No broader corpus, callback timing, allocation,
lifecycle or live-use result is claimed for this trial. Production defaults
and installed output remain unchanged.

### Guarded correction of an unused string, 2026-11-03

The assignment diagnosis identified 20 missed target frames whose preferred
string was unused and whose raw string evidence cleared the proposed guard.
The next experiment tests that narrow correction. It does not evict a competing
note or add a voice.

The default-off `--diagnostic-cue-free-lane-reassignment` path requires the
frozen causal pitch cue, one selected string, complete calibration for every
playable string, a best raw similarity of at least 0.97 and a margin of at least
0.02 over the next string. The preferred string must differ from the current
assignment and be unused. Reserved strings, other selected or active voices,
continuity, and established or emerging unison groups protect their assignments.
All proposals use the same occupancy snapshot. Conflicting proposals are
rejected together; a correction cannot free a string for a second correction
in the same decision. The replay option requires the frozen cue sidecar.

Modal `cue-free-lane-replay-20261103T2332Z`, app
`ap-hVxZH1KTjz7dZpNUQwBEwy`, completed at 23:35:06 UTC. It passes the
small held-out replay gate and is accepted for corpus screening.

| Case | Target matches before → after | Aggregate matches before → after | Wrong-string outputs before → after |
| --- | ---: | ---: | ---: |
| Solo low note | 3219→3236/3450 | 3219→3236/3450 | 159→142 |
| Added octave, -12 dB | 2070→2079/3450 | 2070→2079/6900 | 1314→1305 |
| Added nearby note, equal RMS | 815→835/3450 | 2987→3007/6900 | 1548→1528 |

The hardest target improves from 23.62% to 24.20% matched frames: 20 additional
frames, a 2.45% relative gain and 0.58 percentage points. Its aggregate match
rate rises from 43.29% to 43.58%. Wrong-note outputs remain 3178 and extra
outputs during unlabeled gaps remain 668; total false outputs fall from 5394
to 5374. Extra-gap outputs are not missing-note counts. The other two improved
cases also preserve wrong-note and extra-gap counts. All seven remaining cases
are bit-identical, including source-only and silence controls.

All ten saved-baseline/new-OFF controls are identical. Every ON result is
identical at blocks 32/512/1024. Sixty focused native tests pass, covering the
new correction guards, existing admission guards and offline replay. The
accepted binary has SHA-256
`0d6a856314563c7302d87f7fa6948e925acda6cbe2ead07796b3af5a77a0ff8c`.
The final report is
`build/modal/cue-free-lane-replay-20261103T2332Z.json`.

This establishes a small assignment gain on separate plucks from the same
recording session. It does not establish broad chord safety, another guitar's
behavior, live latency or reliable live use. Production defaults and installed
output are unchanged. The causal spectral window remains 16384 samples at
96 kHz (170.7 ms), which is not a measured pick-to-MIDI latency.

The next run, `cue-corpus-ordinary-20261103T2350Z`, app
`ap-8WBrg4VJWESiT6oBdQOi97`, screens the complete ordinary recording. It
measures the frozen cue across MIDI 32–84 at every feature frame, without
using annotations to choose pitch hypotheses. Saved source, calibration and
binary hashes must agree before replay. The gate compares each annotated
passage, so an aggregate gain cannot hide a loss elsewhere. Every false-output
count must stay at or below its paired baseline, OFF must match exactly, and
ON must be buffer invariant. Exact three/four-string groups are reported
separately when their labels exist.

The new baseline replay returned 145385/528632 matches, with 164263
wrong-note, 92653 wrong-string and 62856 extra-gap outputs. These match the
installed scoreboard. The older offline reference of 145397 matches was used
when preparing this run; it is not this run's measured baseline. Candidate
gates use the current paired replay. A safe ordinary result permits sequential
protected-corpus screening; a regression stops expansion. Timing/allocation,
lifecycle/routing and actual-host checks remain required before any default
MIDI change.

The first corpus attempt, `cue-corpus-ordinary-20261103T2346Z`, failed
before feature measurement because the recording is PCM16 and the reader
accepted only float32 WAV. The reader now accepts both, with native-equivalent
PCM16 scaling by 32768 and no resampling. Seven focused reader/scoring tests
and twenty related tests pass. They cover per-label losses hidden by aggregate
gains, each error ceiling, label identity, exact-group accounting, PCM16 bounds
and truncation, float32 preservation and unsupported stereo input. Python
compilation and whitespace checks pass. This input failure was not a candidate
rejection.

## Ordinary-corpus rejection and paired trace

The complete ordinary recording rejects the free-string correction. The final
`cue-corpus-ordinary-20261103T2350Z` report records 145385→144719 matches
out of 528632 labeled frames (27.50%→27.38%; −666 frames, −0.46% relative).
Wrong-string outputs increase 92653→94531, while wrong-note outputs decrease
164263→163561 and extra outputs during unlabeled gaps decrease 62856→62795.
The combined false-output count rises 319772→320887. These gap outputs are
extra notes, not missing-note counts.

The old baseline and candidate with the correction disabled are bit-identical.
Eight labeled passages lose matches. The largest loss is label 243: MIDI 55,
string mask 8, samples 4406586–4478400 at 96 kHz, falling 858→0/1123 matches.
The small controlled gain therefore does not justify advancing this candidate.
The screen stopped before additional buffers or protected corpora; neither
has passed for this candidate. Installed output and production defaults remain
unchanged.

The paired diagnostic `cue-corpus-failure-20261104T0025Z` completed at
05:20:32 UTC. It reused the saved binary and frozen cues and processed the
complete recording with correction OFF and ON, preserving earlier detector
history. Both replays reproduce the saved aggregate counts, per-label counts
and output fingerprints exactly. The downloaded assignment traces match their
recorded hashes. No detector policy changed during this diagnostic.

The largest loss is history-dependent. The earlier MIDI-48 assignment first
differs between sampled decisions 4341759 and 4342783: OFF retains the annotated
string index 4, while ON moves to index 3. The ON assignment persists into the
next chord, occupying the string needed by MIDI 55. In label 243, OFF has
858 matched, 240 wrong-string and 25 absent-output frames; ON has 0 matched,
1098 wrong-string and the same 25 absent-output frames. This is an earlier
assignment contaminating the later chord, rather than an immediate correction
of MIDI 55 to the wrong string.

The saved per-tick outcome trace locates the move at sample 4341823. Its raw
SHA-256 matches the diagnostic report. MIDI 48 moves from string index 4 to 3
with measured tuning of 1.163126 cents, compared with learned values of
1.04296875 cents for the original string and 6.19140625 cents for the competing
string. The tuning errors are about 0.12 and 5.03 cents, respectively. Sound
similarity prefers the competing string, but tuning favors the original.
After the move, the retention bonus follows the wrong string.

The strict tuning-agreement candidate required valid tuning and a reduction of
at least 0.75 cents in error before a sound-based string correction. This reused
the existing calibrated-cents threshold. Modal `cue-tuning-guard-20261104T0541Z`,
app `ap-WBakhcGtZ9Pz5dSuYRrG5A`, completed at 05:45:40 UTC. All 62 focused native
tests pass, but the candidate is rejected: all ten ON cases are bit-identical
to OFF. The nearby target remains 815/3450 (23.62%), losing the earlier gain of
20 frames. OFF matches the baseline and ON is identical across blocks
32/512/1024. The ordinary corpus was not repeated for this candidate.

The saved target trace distinguishes missing evidence from contradictory
evidence. There are 20 sound-qualified decisions with an apparently free
destination; all have invalid phase tuning. Five sound-qualified decisions
with valid tuning have an occupied destination. The calibration file matches
the replay hash. These are pre-correction snapshots, not a simulation of the
next policy or a complete view of internal lane reservations. Compact evidence
is in `build/modal/cue-tuning-guard-20261104T0541Z-target-diagnosis.json`.

The next candidate uses a contradiction veto: reject a sound-based move when
valid tuning favors the incumbent by at least 0.75 cents. Unavailable tuning
must not be treated as a measured disagreement. Complete calibration, an
independent pitch cue, an unused destination, unison protection and the
existing sound-similarity gates remain required. The measured ordinary failure
must still be rejected by the unit fixture.

Require a strict held-out gain with no control or error regression before
repeating ordinary. Ordinary acceptance requires at least 145385 matches,
no lost label, no higher false-output count, exact OFF equality and
buffer-invariant ON output. Timing/allocation, lifecycle/routing and actual-host
gates remain open; installed output is unchanged.

## Contradiction veto passes the small screen

Modal `cue-tuning-veto-20261104T0556Z` completed at 05:57:35 UTC on
2026-11-04. The candidate preserves the earlier nearby-note gain:
815→835/3450 target matches (23.62%→24.20%; +20 frames, +2.45% relative).
Aggregate matches rise 2987→3007/6900. Wrong-string outputs fall 1548→1528;
wrong-note outputs remain 3178 and extra outputs in unlabeled gaps remain 668.
Solo gains 17 matches and quiet octave gains nine. The other seven cases
are bit-identical. All ten OFF controls match the old baseline, and ON output
is identical at blocks 32/512/1024. All 63 focused native tests pass.

Unlike the strict guard, this rule allows an otherwise qualified correction
before phase tuning becomes valid. Valid tuning still blocks a correction
when the incumbent has at least a 0.75-cent advantage. The known harmful
MIDI-48 move is rejected by the unit fixture; whether the complete ordinary
recording avoids that failure remains a separate gate.

The same saved binary was tested by
`cue-veto-ordinary-20261104T0600Z`, app `ap-ACqoR75uNSyJ7mt8NCCBsZ`.
The gate requires aggregate and per-label matches and every false-output ceiling,
with exact OFF controls and buffer-invariant ON output, before further corpus
work. This is acceptance for a corpus screen, not an installed improvement or
proof of live performance.

## Ordinary corpus rejects the contradiction veto

The ordinary screen completed at 06:07:03 UTC on 2026-11-04. Matches rise
145385→145596/528632 (27.502%→27.542%; +211 frames, +0.145% relative).
Wrong notes fall 164263→163561, but wrong strings rise 92653→93192 and
extra outputs in unlabeled gaps rise 62856→62947. Total false outputs fall
319772→319700. The lower total does not offset either increased error category.
Labels 187/188/192/196 lose 31/7/11/8 matches, respectively. The previous
858-frame loss on label 243 is absent. OFF reproduces the baseline exactly;
further ON buffer checks and other corpora stopped after the regression.

Diagnostic `cue-veto-failure-20261104T0609Z` traces label 187, MIDI 54 on
string mask 8, whose matches fall 902→871/1122. It reuses the saved binary,
frozen cues and full recording history. The next implementation depends on
locating the correction that causes this loss. Installed output is unchanged;
the candidate remains rejected until all per-passage and safety gates pass.

## Assignment-only cue trial

The saved full-history traces change the diagnosis of the ordinary-corpus loss.
The first outcome difference occurs at sample 3205247, before any string move:
OFF emits candidate 52, while ON suppresses it as a harmonic shadow of 71.
At the next decision, 52 returns with different phase history. Later, MIDI 54
loses its active slot while five earlier voices remain. The target passage
falls 902→871/1122 matches. The first divergence is pitch selection; the later
slot loss does not establish that a string correction caused it.

Both diagnostic replays reproduce their saved outputs and per-label scores.
The full outcome traces were hash-verified and compared on Modal without a new
replay. Evidence: `build/modal/cue-veto-failure-20261104T0609Z.json` and
`build/modal/cue-veto-failure-20261104T0609Z-first-outcome-difference.json`.

The free-lane experiment now uses frozen cues only for string assignment of
already selected pitches. It disables cue-based pitch admission while retaining
the separately requested fundamental-admission diagnostic. The regression test
covers that separation at four common gain levels. The tuning contradiction,
calibration, occupancy and unison guards remain in place. Reports record the
pitch-admission policy explicitly, including propagation to corpus screens.

`cue-assignment-only-20261104T0639Z`, app `ap-N7Iaje4GF6raT6EF3uj2Le`,
completed at 06:42:02 UTC on 2026-11-04. Nearby target matches remain
815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative), with wrong-string
outputs falling 1548→1528. Wrong notes remain 3178 and extra outputs in
unlabeled gaps remain 668. Solo gains 17 matches and quiet octave gains nine;
the other seven cases are bit-identical. All ten OFF controls reproduce the
old baseline, and ON output is identical at blocks 32/512/1024. All 64 focused
native tests pass. Separating pitch admission preserves the measured benefit
on this small screen; it does not yet establish ordinary-chord safety.

The same saved binary passed `cue-assignment-ordinary-20261104T0643Z`,
app `ap-f5lhBeUP48VhBVuJEWuDpE`, at 06:51:49 UTC. ON is bit-identical to
OFF and the old baseline: 145385/528632 matches (27.50%), with wrong-note,
wrong-string and extra-gap counts of 164263/92653/62856; total false outputs
remain 319772. No passage loses matches, and ON is identical at blocks
32/512/1024. Separating pitch admission removes the earlier ordinary-corpus
regressions while retaining the small-screen gains. It adds no matches on
this ordinary recording.

`cue-assignment-constructed-20261104T0653Z`, app `ap-5pXg4vh3Ok2EBe90snEbEx`,
finished cue extraction across 29491200 samples with 59536 intervals. The
local client disconnected at 07:11:33 UTC, canceling the app during baseline
replay. It produced no constructed-corpus verdict.

The detached continuation `cue-assignment-constructed-resume-20261104T0726Z`,
app `ap-BTk31v3Lc3HqrR4BXFOgfK`, reuses the completed cue file. The new
`--cue-checkpoint-run` option checks recording, calibration, source report,
binary, frozen rules, cue hash and complete counts before reuse. It retains
no partial replay result. Eleven focused Python tests pass, including refusal
of incomplete extraction, changed inputs and a changed cue file; runner
syntax and whitespace checks also pass. No native detector code changed.

The continuation completed at 07:33:40 UTC and is rejected. Matches fall
259074→254400/1614601 (16.0457%→15.7562%; −4674 frames, −1.8041% relative).
Wrong-note/wrong-string/extra-gap counts rise
167722/103754/23176→170861/104719/24077; total false outputs rise
294652→299657. Eighteen passages lose matches. OFF exactly reproduces the
baseline and every label score. Further ON buffer and corpus checks stopped.
The ordinary-corpus pass remains separate; installed output is unchanged.

Diagnostic `cue-assignment-failure-20261104T0739Z` reproduced the saved OFF
output, then failed in Python summarization. The native scorer requires the
complete rendered string set to equal the annotation. The summary incorrectly
accepted any matching member, including a correct string plus an extra
same-pitch string. The correction follows native scoring without changing it.
Eleven focused tests pass, including extra strings, incomplete groups and
unconstrained labels; runner syntax and whitespace checks pass.

Detached diagnostic `cue-assignment-failure-resume-20261104T0749Z`, app
`ap-YoCHSm396HwqfBLUURdVXZ`, completed at 07:50:37 UTC. It reused the completed
raw OFF traces after checking the saved inputs, target, window, binary and
replay scores; only ON needed a new replay. Both outputs and every label score
reproduce the saved rejection, with complete trace row counts.

The saved-trace comparison, app `ap-zxkzowp2C7p0otV81VHrTe`, verified all four
raw trace hashes. The first output difference and lost match occur at sample
4751551: MIDI 49 moves from string 2 to string 4 after identical earlier
output. Label 69 falls 1455→507/3448. Pitch selection and admission evidence
are unchanged at the first loss. Report:
`build/modal/cue-assignment-failure-resume-20261104T0749Z-first-assignment-difference.json`.

The admission descriptor snapshot precedes the phase-tuning update, while
assignment recomputes the descriptor afterward. The snapshot similarity of
0.938 therefore does not establish that the move bypassed its 0.97 threshold.
Capture the actual decision inputs before changing that guard.

Any revised guard must preserve at least 259074/1614601 matches, every label,
and wrong-note/wrong-string/extra-gap ceilings of 167722/103754/23176, with
exact OFF equality and ON buffer parity. Isolated strings follow only after
that gate passes. This remains an offline experiment.

## The harmful move loses a settled tuning veto at the pitch-bin boundary

`cue-decision-inputs-20261104T0806Z` completed at 08:10:11 UTC on
2026-11-04. Added diagnostics record the inputs used by the string correction,
its proposed destination and whether it was applied. Every proposed move is
recorded, including those between regularly sampled trace rows. The helpful
nearby recording and harmful constructed recording reproduce every saved label
score and output fingerprint. Eight cue tests and 48 offline tests pass.

At sample 4751551, the harmful MIDI-49 move from string 2 to string 4 has
descriptor similarity 0.98767. It passes the 0.97 threshold; the earlier
snapshot did not expose a bypass. Its phase estimate has settled after
2280 updates, but −51.6409 cents falls outside the narrow ±50-cent pitch bin.
That disables the tuning veto even though the incumbent has 32.2070 cents
less tuning error. The same estimate remains valid under the existing
±60-cent output-projection range. By contrast, the helpful nearby MIDI-36
move at sample 44799 has only 181 updates and remains unsettled.

The candidate uses output-projection validity for the existing contradiction
veto: settled tuning can reject a move across that narrow bin boundary, while
unsettled tuning still permits an otherwise qualified early correction. The
0.75-cent threshold, tuning calculation, pitch admission and other assignment
guards are unchanged. `cue-tuning-range-20261104T0819Z` completed at 08:21:54
UTC and passed the small screen: nearby matches remain 815→835/3450, with
wrong strings reduced 1548→1528 and no added wrong notes or gap outputs.
All ten OFF controls match the baseline, all ten ON outputs agree across
blocks 32/512/1024, and all 64 focused native tests pass.

The constructed screen `cue-tuning-range-constructed-20261104T0824Z` completed
at 08:28:31 UTC and rejects this candidate. Matches fall
259074→257470/1614601 (16.0457%→15.9464%; −1604 frames, −0.6191% relative).
Wrong-note/wrong-string/extra-gap counts change
167722/103754/23176→175058/102380/23627. Total false outputs rise
294652→301065, and sixteen labels lose matches. The reduction in wrong-string
outputs does not offset the other safety failures. OFF exactly reproduces the
baseline; further ON buffer and corpus checks stopped. Installed output is
unchanged. Paired diagnostic `cue-tuning-range-failure-20261104T0832Z` completed
at 08:38:43 UTC. Both complete-history replays reproduce every saved score,
and the traces are complete. The first differing output is sample 4751807:
MIDI 49 moves from string 2 to string 4 as phase reaches −60.7600 cents after
2284 accepted updates. Descriptor similarity is 0.97218, and the incumbent
still has 32.2070 cents less tuning error. Crossing the wider validity boundary
again disables the veto. It delayed the same harmful switch by four detector
frames (256 samples, 2.667 ms).

The next candidate distinguishes early missing evidence from lost mature
evidence. After the existing 160 ms phase-evidence threshold, reassignment
requires a valid output-projection estimate. Before that threshold, an
otherwise qualified early correction remains possible. Valid estimates still
use the existing 0.75-cent contradiction veto. This is an offline candidate;
the small-screen gains and full corpus protections must be measured again.

Corpus screening can now explicitly reuse completed cue features across native
versions. It requires identical audio, annotations, calibration, settings,
feature source and rules, sample clock, cue hash and complete extraction. The
new binary reruns every output and label score; old replays are never reused.
Thirteen focused Python tests pass, including refusal of changed inputs,
changed extraction code and incomplete features. Normal interrupted-run
recovery still requires the original native binary.

## Mature tuning must remain valid before a string correction

The conditional guard preserves the useful early correction in
`cue-mature-tuning-20261104T0847Z`, completed at 08:49:16 UTC on 2026-11-04.
Nearby matches remain 815→835/3450 (23.62%→24.20%; +20 frames, +2.45% relative),
with wrong-string outputs reduced 1548→1528. Wrong-note and extra-gap outputs
remain 3178 and 668. Solo and quiet octave gain 17 and nine matches; the seven
other cases are bit-identical. All ten OFF controls reproduce the baseline,
and all ten ON outputs agree across blocks 32/512/1024. All 65 focused native
tests pass, including a new regression using the first harmful decision's
actual inputs. It distinguishes invalid mature tuning from early evidence and
checks that valid mature tuning still permits a supported correction.

The constructed screen `cue-mature-tuning-constructed-20261104T0850Z` completed
at 08:59:19 UTC and rejects the candidate. Matches fall
259074→258558/1614601 (16.0457%→16.0137%; −516 frames, −0.1992% relative).
Wrong-note/wrong-string/extra-gap counts change
167722/103754/23176→167046/103725/23176, and total false outputs fall
294652→293947. Eight passages lose matches, so the safety gate fails despite
fewer false outputs. OFF exactly reproduces the baseline; further ON buffer
and corpus checks stopped. The earlier MIDI-49 failure no longer changes any
label score. The first remaining loss is label 98, MIDI 51 on string 2:
2305→584/3450. Paired diagnostic `cue-mature-tuning-failure-20261104T0901Z`
completed at 09:06:01 UTC. Both complete-history outputs exactly reproduce
the saved results, and the traces are complete.
Installed output remains unchanged. The next candidate must preserve every
passage and the small-screen gains before the corpus screen can advance.

## A confirmed pitch does not establish a new string identity

The first differing output is sample 6317119. MIDI 51 moves from correct
string 2 to free string 4 after 1258 candidate decisions, about 838.7 ms. Tuning
is valid at +29.3153 cents after 1485 updates. The wrong string has descriptor
similarity 0.988216 and tuning error 14.5067 cents; the incumbent's error is
41.7098 cents. Selection and pitch detection remain identical. This is a
late assignment error despite valid tuning, distinct from the earlier
invalid-tuning failure. The pitch cue does not identify which string played it.

The next candidate allows cue corrections only while candidate age is below
the existing 160 ms evidence period. It preserves established assignments
and retains the other guards. This conservative bound keeps the known useful
correction at about 93 ms eligible; it is not evidence of a generally optimal
settling time. The regression test uses the recorded harmful inputs and
checks that the early correction remains eligible. The small screen
`cue-initial-assignment-20261104T0913Z` completed at 09:17:23 UTC: all 66 focused
native tests pass, nearby matches remain 815→835/3450, solo gains 17 and quiet
octave nine. All ten OFF controls reproduce the baseline, ON is identical
across blocks 32/512/1024, and seven cases remain bit-identical.

Constructed run `cue-initial-assignment-constructed-20261104T0918Z` completed
at 09:32:02 UTC and passed. ON, OFF and baseline are bit-identical:
259074/1614601 matches (16.0457%), wrong-note/wrong-string/extra-gap counts
167722/103754/23176 and total false outputs 294652. No passage changes, and
ON agrees at blocks 32/512/1024. Restricting corrections to initial settling
removes the recorded constructed-corpus regression while retaining the
small-screen gain. Ordinary run `cue-initial-assignment-ordinary-20261104T0933Z`
now checks the same binary with verified saved cue features. The remaining
corpus, realtime and MIDI lifecycle/host gates are open; installed output is
unchanged.

Ordinary run `cue-initial-assignment-ordinary-20261104T0933Z` subsequently
passed at 09:38:30 UTC. ON, OFF and baseline are bit-identical:
145385/528632 matches (27.5021%), wrong-note/wrong-string/extra-gap counts
164263/92653/62856 and total false outputs 319772. Low-string run
`cue-initial-assignment-isolated08-20261104T0940Z` passed at 09:42:41 UTC:
29816/31050 matches (96.0258%), errors 2462/579/2928 and total false outputs
5969. It is also bit-identical to OFF and the baseline. Neither corpus loses
any passage matches, and both agree at blocks 32/512/1024. Extra-gap counts
are extra outputs during unlabeled gaps, not missing notes.

The same saved binary is now checking middle strings in
`cue-initial-assignment-isolated05-20261104T0945Z`. Its gate requires at least
25681/31050 matches, no passage loss and error counts at or below
12028/4037/3860, plus exact OFF equality and ON buffer parity. High strings
and physical/synthetic unisons follow. These checks preserve the earlier
small-screen gain without establishing live behavior; installed output is
unchanged.

Middle-string run `cue-initial-assignment-isolated05-20261104T0945Z` passed
at 09:46:37 UTC: 25681/31050 matches (82.7085%), wrong-note/wrong-string/
extra-gap counts 12028/4037/3860 and total false outputs 19925. High-string
run `cue-initial-assignment-isolated02-20261104T0949Z` passed at 09:52:21 UTC:
29240/35550 matches (82.2504%), errors 2491/1400/1840 and total false outputs
5731. Both are bit-identical to OFF and the baseline, with no lost passage
matches, no added false outputs and identical ON output at blocks 32/512/1024.
This completes the three representative isolated-string screens on the
initial-settling binary; ordinary and constructed chords also pass.

Long physical-unison run `cue-initial-assignment-physical-long-20261104T0953Z`
passed at 09:59:10 UTC. Overall matches remain 41452/68441 (60.5660%) and
exact-three matches remain 25219/39378 (64.0434%). Wrong-note/wrong-string/
extra-gap counts remain 67769/2709/5403, with total false outputs 75881 and
fingerprint `519bc0f9f4710566`. ON, OFF and baseline are bit-identical, and
ON agrees at blocks 32/512/1024. Six of the fixed fourteen corpus screens
now pass on this binary.

The primary improvement targets remain 42128/68441 overall matches and
25604/39378 exact-three matches, with wrong strings at most 2709. A
preservation pass alone does not reach those targets. Middle physical
unisons are running as `cue-initial-assignment-physical-middle-20261104T1001Z`.
Installed output is unchanged; remaining corpus, native cue timing and
MIDI lifecycle/host checks are still required.
