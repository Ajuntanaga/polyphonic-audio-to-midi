# Dense harmonic spectral patches: frozen CPU screen

One new representation screen, using the standing authorization in
`m3-standing-job-authorization-20261121.json`. No installed tracker, DSP policy,
label, source-role, or recorded-score change. Claude remains paused.

## Question and evidence

Can denser local spectral shape and a shared shape encoder preserve isolated
notes while improving complete chords on the existing source-disjoint roles?
The original context network already sees the entire 53-pitch candidate range;
this is not a claim that its neighboring pitches were previously inaccessible.

The pitch-scaled-window screen (45004325518) regressed five-pitch training exact
sets from 1818 to 1159 of 2529 and singleton exact sets from 3115 to 3100 of
3132. Return to the original 4096/16384 trailing Hann windows. The paired
component measurement (45000500192) found both source-transfer and mixture
losses; additional neighborhood access alone does not explain those failures.

The new frozen representation takes 25 offsets, -2 to +2 semitones in steps of
1/6, around multipliers 0.5, 1, 2, 3, 4, 5 in each original window. It retains
the two RMS values: 302 measurements per candidate. Two shared offset
convolutions (2->4->4, kernel 3, padding 1, ReLU) preserve all 25 positions. The
600 shape values plus two RMS values feed the existing pitch-context layers.
Total model size is 31,825 parameters, compared with the baseline's 14,465.

Dense measurements, capacity, initialization, and arithmetic change together.
This screen cannot uniquely attribute a gain to measurement density. It does
not claim source separation or exact pitch equivariance. The extractor uses
the existing native FFT interpolation and finite-window measurements; it adds
no identity, label-count, future-audio, or hard rejection feature.

## Fixed execution and gates

- Specification: `harmonic-spectral-patches-20261122.json`.
- Worker: `harmonic-spectral-patches.yml`, one Ubuntu CPU job, 45-minute bound,
  one fit, 80 epochs, seed 20261121, batch 128, one CPU thread. No sweep,
  cutoff retuning on held-out data, or automatic rerun.
- Same 555 excerpts, original 200/200/155 train/calibration/test roles, input
  hashes, mixture plans, crops, gains, targets, optimizer, setwise loss and
  training-only cutoff rule as the fixed-window setwise baseline 44965135706.
- Train: precision >=99%, recall >=80%, complete exact pitch sets >=70%, both
  overall and in each 3/4/5-pitch group; zero silence false outputs.
- Singleton preservation: exact >=3115/3132, extra pitches <=13, missed pitches
  <=5. A chord gain with a singleton regression fails.
- Both held-out roles: precision >=95%, recall >=80%, exact sets >=70%, overall
  and in each 3/4/5-pitch group; zero silence false outputs.
- Continuous ordinary/extended-middle replay only after all preceding gates
  pass. Preserve CURRENT reference identity; require ordinary present-time gain
  >=5 percentage points, no per-label present-time or longest-hold loss, and no
  extra/gap growth. Existing event and scoring checks remain unchanged.
- Keep model/prediction evidence remote; collect the small report once with
  its server digest. Record separate source and worker commits and the run ID.

Feature storage is float32. Normalization fits training-only two-pass float64
moments in 2048-candidate-row chunks; normalize each shuffled batch on demand.
This bounds scratch space without changing the number of optimizer steps.

## Checks before dispatch

Local generated-signal/mock suite: 15 tests, 12 passed and 3 model tests
intentionally reserved for GitHub. Tests cover feature order, original center
and RMS identity, past-only short-window support, relative-level behavior,
invalid inputs, bounded normalization, float32 opt-in storage, and preservation
gate routing. No recordings, model execution, or native processing ran locally.

The three new GitHub-only tests check the encoder layout and parameter count,
finite gradients and saved-model activity identity, and a tiny complete frozen
fit. The worker also runs the existing representation and scoring tests before
the recorded-data screen. Local diff whitespace check and YAML parse passed;
reference pins and gates were compared with the previous specification and
remain unchanged. One direct implementation review found no remaining defect.

This research screen is not native timing, string assignment, MIDI delivery,
unison multiplicity, or live-readiness validation. All intended labels remain,
including unresolved source-content disagreements. Held-out roles have been
examined in previous research and are not a fresh blind evaluation.
