# Research route: measured motion across harmonics

Updated 2026-11-03. The offline capture and control experiment are implemented.
This is not an accepted detector change. The installed plugin and its
parameters are unchanged.

## Decision

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
