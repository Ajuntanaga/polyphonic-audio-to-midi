# Absolute-level input suppression: one source-transfer screen

Frozen before fitting on 2026-11-21. Compare the unaugmented setwise baseline
44965135706, not the rejected peak-contrast model. The baseline finds 8000/10452
expected test pitches with 2705 extras and 1749/4096 complete sets; five-pitch
complete sets are 27/327. Better training fit has not established safe transfer.

## Mechanism and single change

`HarmonicFeatures` supplies 30 relative spectral-power values and one absolute
RMS value for each of two trailing windows. Absolute level is repeated over all
53 pitches. The mixture generator normalizes each source to a common RMS then
applies discrete component and mixture gains. Absolute RMS may therefore expose
generator-specific correlations. The saved errors do not prove the network uses
that shortcut, and do not establish it as the cause of held-out failure.

Replace the two RMS coordinates (30,61) with constant zero for training,
calibration, test and any gated continuous replay. Keep the other 60 coordinates
bit-identical. Retain all 62 slots, the 14465-parameter network, seeded initial
weights, setwise loss, optimizer, 80 epochs, batch ordering, source roles and
original training plan. Constant columns normalize to mean 0, scale 1. No peak
features, source augmentation, level rule or new threshold. Cutoff fitting is the
original training-only rule, performed once; it may produce a different cutoff.

Relative features retain their existing floors and clipping: this is not exact
gain invariance near silence. The named risk is losing useful quiet/noise level
evidence and producing more false pitches. The model can still rely on source
timbre and pitch-grid boundaries. Suppression does not address those alternatives.

## Predeclared execution and decision

- One CPU GitHub run, 45-minute cap, pinned existing releases; no new uploads or
  local audio/model processing. Standing human authorization is recorded in
  `m3-standing-job-authorization-20261121.json`. Claude is paused; this plan does
  not claim a new Claude review.
- Synthetic checks: unchanged relative coordinates, zero RMS under training and
  held-out scaling, gain behavior above/below floors, trailing-only inputs,
  identical network initialization and parameter count, persistence, original
  role gates and continuous extractor propagation.
- Train exactly once on all 200 original training sources. Fail closed on the
  decoded training-plan hash. All 555 intended labels and their roles stay intact.
- Train gate: precision >=99%, recall >=80%, complete sets >=70%, complete
  three/four/five-pitch sets each >=70%, zero silence extras. Five-pitch target is
  1771/2529. If training fails, skip held-out and continuous scoring.
- If training passes, freeze model and cutoff before scoring both other roles.
  Each requires precision >=95%, recall >=80%, complete sets >=70%, complete
  three/four/five-pitch sets each >=70%, zero silence extras. No held-out fitting.
- Only if both pass, run the existing ordinary and extended-middle continuous
  comparisons with CURRENT identity, >=5 percentage-point ordinary gain and no
  per-label presence/longest-hold loss or wrong-pitch/gap growth. No gate change.
- Report presence, misses, extras and complete sets separately, including
  single-pitch regressions. Compare every role with run44965135706. Reject on any
  required failure; no cutoff retune, repeated fit or automatic rerun.

The two held-out source roles have already informed prior development and are
not a new blind benchmark. These sampled sustained pitch-set results do not
measure installed string assignments, repeated-note multiplicity, attacks,
delivered MIDI, native performance or live readiness. Installed/default output
and the recorded scoreboard remain unchanged even if this research screen passes.

Specification: `harmonic-level-suppression-20261121.json`.
