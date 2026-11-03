# Research route: measured motion across harmonics

Updated 2026-11-03. This is an offline experiment design, not an accepted
detector change. The installed plugin and its parameters are unchanged.

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

## Current conclusion

The literature offers a credible test of *where additional information might
come from*. It has not yet produced a measured improvement in this project.
The next implementation decision depends on that conditional measurement.
Repeated ownership or retention tweaks should not proceed on the strength of
the rejected handoff screen.
