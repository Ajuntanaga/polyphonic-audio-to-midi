# Polyphonic tracking research and data intake

Date: 2026-10-03

This note records the external methods and bounded reference data that are
useful for improving M3's eight physical tuner lanes. It distinguishes
ordinary multi-pitch detection from the harder requirement here: assigning
the same pitch to two or three different physical strings in real time.

## What the leading systems actually establish

### PolyTune and fixed-range polyphonic tuners

TC Electronic's polyphonic tuner patent describes two implementations: a
bandpass filter and monophonic detector per string, or one Fourier transform.
The preferred implementation places one filter around each nominal open-string
target. The patent explicitly says the detector cannot know which string owns
a harmonic set and therefore assumes a nominal frequency range for each
string. That is appropriate for one-strum open-string tuning, but it does not
solve arbitrary-fret string ownership or physical unisons.

Source:
https://patents.google.com/patent/US9070350B2/en#p=11

The UC3 PolyTuna reference implementation independently uses the same class of
method: a 100 ms FFT and a fixed bin range for each standard-tuned open string.
It is useful corroboration, not reusable code: the repository has no declared
software license.

Source: https://github.com/UC3Music/PolyTuna

### Melodyne and commercial polyphonic note editors

Melodyne exposes separate Polyphonic Sustain and Polyphonic Decay algorithms;
the latter is intended for guitars and other sounds whose attack differs from
the sustain. Its manual also states that DNA separates by pitch rather than by
instrument: two sources playing the same note form one blob. This supports
using attack and sustain as distinct evidence in M3, while confirming that a
general commercial polyphonic detector is not a physical-string oracle.

Source:
https://helpcenter.celemony.com/M5/doc/melodyneStudio5/en/M5tour_AudioAlgorithms?env=standAlone

### Basic Pitch and NeuralNote

Spotify Basic Pitch is a lightweight, instrument-agnostic polyphonic model
that jointly predicts pitch contours, note activations, and onsets. That
multi-head division is relevant: candidate pitch, persistent note state, and
attack evidence should remain separate signals. Basic Pitch is suitable as an
offline teacher and multi-pitch benchmark. Its output is not string-resolved,
so embedding it alone would not fix M3's lane identity.

Sources:

- https://arxiv.org/abs/2203.09893
- https://github.com/spotify/basic-pitch
- https://github.com/DamRsn/NeuralNote

NeuralNote v1 used Basic Pitch and demonstrates a DAW-oriented transcription
workflow. The current project is background/offline transcription rather than
sample-causal tuner telemetry, so its model is a comparison target rather
than a drop-in audio-thread design.

### FretNet

FretNet is the closest published formulation to M3's lane problem. It emits
discrete activity and continuous pitch deviation for every string/fret pair,
with a separate onset head. The output representation binds pitch to its
physical source instead of detecting pitches first and guessing strings only
at display time. Its reported ablations also find that inhibition and its
multi-channel feature extractor help compared with an ordinary CQT.

Sources:

- https://arxiv.org/abs/2212.03023
- https://github.com/cwitkowitz/guitar-transcription-continuous

The production implication is architectural, not a license to put a large
PyTorch model in the audio callback: M3 should retain one posterior per
string/fret state and perform the final bounded assignment jointly.

### Multi-F0 and temporal tracking

Klapuri's multiple-F0 work scores harmonic amplitudes, estimates polyphony,
and compares iterative cancellation with joint estimation. The joint form
avoids making the final set depend on detection order. M3 already has a
bounded joint assignment, but it does not yet model enough residual/partial
evidence to make close unisons independently observable.

Source: https://archives.ismir.net/ismir2006/paper/000125.pdf

pYIN shows the temporal principle M3 needs after frame analysis: preserve
multiple candidates with probabilities and decode a stable path rather than
smooth a single early winner. pYIN itself is monophonic; the transferable part
is its candidate-probability plus hidden-state tracking structure.

Source: https://ieeexplore.ieee.org/document/6853678

## Data pulled

Only bounded data was fetched. No multi-gigabyte audio archive was downloaded.
Exact provenance is in `docs/polyphonic-tracking-reference-manifest.json`.

- GuitarSet annotation archive: 39.1 MB, verified MD5
  `b39b78e63d3446f2e54ddb7a54df9b10`.
- 360 string-resolved tracks.
- 62,476 note events and 3,214,786 continuous pitch-contour points.
- 204 annotated cross-string same-pitch overlaps totaling 41.316 seconds.
- Source snapshots: FretNet, Basic Pitch, and PolyTuna at the exact commits in
  the manifest.

The GuitarSet audio collection is 8.2 GB. It was intentionally not pulled.
Its annotations can validate string/fret state machines, playability,
transitions, duration priors, and evaluation code; its standard six-string
acoustic timbre cannot replace the recorded eight-string NYXL 9-80 corpus.

Dataset and paper:

- https://zenodo.org/records/3371780
- https://ismir2018.ircam.fr/doc/pdfs/188_Paper.pdf

GAPS was reviewed but not imported. It offers 14 hours and strong
generalization evidence, but its terms are non-commercial research-only and
its score alignment does not provide trustworthy performed-string ownership
for every note. Its key result still matters: diverse pretraining followed by
target-domain fine-tuning generalizes better than narrow supervised training.

Source: https://arxiv.org/abs/2408.08653

## Results on the M3 physical corpus

The current accepted detector remains at 1,115,298 exact lane frames out of
1,739,486 labeled frames, or 64.1165 percent overall. Per-lane results span
49.8 to 79.3 percent. Correctly tracked frames already have good cents
precision; physical string identity is the limiting problem.

Two bounded feature studies were run without changing production DSP:

1. Recreating the current six-harmonic runtime profile domain and classifying
   the held-out third pass reached 62.0 percent. This rules out merely changing
   the offline template extractor while keeping the same feature space.
2. Adding upper-partial detuning (inharmonicity), local peak bandwidth, and
   pitch-smoothed string/fret templates reached 45/52, or 86.54 percent, on
   the sparse third pass. Other leave-one-pass-out folds reached 82.1 to 89.7
   percent depending on template blend.

These measurements are promising but below the requested greater-than-90
percent per-lane gate. They are not yet production changes.

## First bounded production classifier slice

The first causal implementation uses one final string/fret posterior, not
several competing classifiers. Its observation heads remain separate:

- lower-harmonic shape anchors the fundamental and lower spectrum;
- upper-partial shape carries string and articulation character;
- current-versus-settled spectral distance marks attacks and decays;
- measured cents and the existing beat/fine-frequency evidence retain their
  stronger physical meanings.

Every pitch candidate keeps a fixed-size posterior over all playable physical
strings. Sustained observations accumulate without deleting alternatives, and
a new onset weakens the previous state before applying new evidence. The
existing bounded joint assignment consumes the posterior only during the
settled calibration-reassignment window. Decisive measured cents and resolved
physical-unison evidence take precedence.

On the complete raw eight-string corpus this slice produces 1,117,563 exact
lane frames out of 1,739,486, or 64.2467 percent. That is 2,265 additional
exact frames and +0.1302 percentage points over the accepted 64.1165-percent
baseline. The scored low and middle three-string physical-unison replays are
bit-for-bit unchanged from clean HEAD. This is a measured improvement, but it
is still far below the greater-than-90-percent target.

This slice models upper-partial amplitude shape; it does not yet implement the
offline study's explicit upper-partial frequency-detuning/inharmonicity
descriptor or store new descriptor statistics in the calibration image.

## Causal partial-frequency evidence

The next bounded layer measures frequency displacement independently for the
fundamental and the first five overtones from their complex resonator phase.
For every partial it converts the phase advance between decision frames into a
measured-frequency offset. It then subtracts the fundamental's cents offset
from every partial, rejecting global tuning error while retaining stable
partial stretch and other string-specific frequency structure. Lower and upper
partials remain separately available to the final string/fret posterior.

This estimator has fixed storage, performs no allocation or synchronization,
and runs causally at the detector decision cadence. Two cascaded causal phasor
filters suppress the large twice-line-frequency image present in real-valued
audio. Against the labeled physical-string corpus, the resulting descriptor's
mean absolute error is 0.65--5.53 cents by string (2.90 cents on string 8),
instead of the hundreds of cents produced by the unsmoothed phase estimate.

Calibration image version 2 stores a validity mask and Q8 detuning reference
for each of the six partials at every string/fret point. Version 1 images still
decode, while new images retain the established cents, harmonic-amplitude,
confidence, count, and quality fields byte-for-byte and add only the new
descriptor. The offline derivation accepts a partial reference only when its
bounded local spectral peak is interior, sufficiently energetic, and repeated
measurements have no more than 3 cents of standard deviation. Live calibration
applies the same dispersion gate. In the recorded instrument this provides
broad second-partial coverage, useful third-partial coverage, and intentionally
sparse higher-partial coverage.

The final string posterior now receives a centered likelihood from every
shared valid detuning reference. A diagnostic comparison against every
playable alternative shows the correct string winning 74.94 percent of frames
where both sides have usable references. The descriptor therefore remains a
secondary head: a high-confidence posterior receives stronger joint-assignment
weight only when its best state agrees with the independently best detuning
state.

On the complete raw eight-string corpus this consensus rule produces
1,119,857 exact lane frames out of 1,739,486 (64.3786 percent): 2,294 more than
the prior classifier. Seven string replay fingerprints are unchanged; the
gain is confined to string 2 without the string-6 regression caused by a
global posterior-weight increase. The scored low and middle three-string
physical-unison replays remain bit-for-bit unchanged
(`e09ed3d3cf015468` and `456c71055b07f282`). This is a measured cumulative
gain, not evidence that the greater-than-90-percent target has been reached.
With calibration pass 3 excluded from every string bank, the same detector
scores 1,100,600 exact frames (63.2716 percent), 6,470 more than the retained
pre-detuning pass-3 holdout result. The improvement therefore is not confined
to the full-bank derivation data.

## Production implementation order

1. Extend the causal descriptor set with explicit attack/decay features; the
   upper-partial detuning descriptor and versioned calibration storage are now
   implemented.
2. Continue refining the bounded posterior over all
   playable string/fret states. Emissions combine amplitude shape,
   inharmonicity, attack/decay, cents bias, and current signal confidence.
3. Update those posteriors through time. Reward lane continuity, but retain
   alternatives so later evidence can correct a provisional lane. Reset or
   weaken continuity at a detected onset.
4. Keep the existing joint one-string-per-lane assignment and unison beat
   evidence as constraints over the posterior states. Score the complete set,
   not candidates in discovery order.
5. Use GuitarSet/FretNet/Basic Pitch only for offline tests and teacher
   comparisons. Fine-tune thresholds and compact descriptors on the exact
   eight-string recordings, including physical unisons.
6. Accept a production change only when the full isolated corpus does not
   regress, every lane exceeds 90 percent on held-out data, the physical
   unison cases improve, and callback timing remains within the existing
   sample-rate/buffer matrix.

This order applies the strongest common result across the sources: stable
polyphonic tracking needs richer observations, explicit source states, onset
evidence, and temporal alternatives. More retention or another cosine
threshold cannot manufacture string identity that the observation model does
not contain.
