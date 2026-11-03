# Research route: measured motion across harmonics

Updated 2026-11-03. The offline capture and control experiment are implemented.
This is not an accepted detector change. The installed plugin and its
parameters are unchanged.

## Decision

Test whether the *measured motion* of different harmonics contains useful
string evidence after accounting for the existing string posterior. Start with
saved physical recordings and adversarial single-string controls on Modal.
Do not repeat the stationary harmonic fit, add another general classifier, or
change MIDI admission before this narrower question has an answer.

A string's harmonics can move together as its tension and vibration change.
An overlapping harmonic may follow a different mixture of those movements.
The useful question is whether those differences survive in our recordings,
not whether a sufficiently flexible model can reconstruct the waveform.

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

The next prerequisite for the reference-based separation methods is a measured
reference-quality check on physical isolated recordings. Determine which
harmonic tracks are unavailable because they are weak, have phase slips, or
fail the clock check; do not turn missing bands into agreement. Reference
selection must use signal evidence alone. If a reliable reference and
independent physical takes are available, compare posterior-only against
posterior-plus-motion on whole held-out takes, with false added strings as
an explicit rejection condition. This remains a hypothesis about conditional
information, not another threshold on motion magnitude. The current single
physical unison take cannot establish that generalization result. Repeated
ownership or retention tweaks should not proceed on the strength of the
rejected handoff screen.
