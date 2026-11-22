# Independent partial variation: frozen CPU screen

The setwise baseline fits training five-pitch sets (1818/2529, 71.89%) but fails on other takes: calibration 283/639 (44.29%) and test 27/327 (8.26%). Prior correlated shelf augmentation, pitch transposition, peak-contrast features and explicit-level removal did not pass the held-out gates. Saved source-transfer evidence also contains false pitches on unflagged isolated sources, so known annotation disagreements do not explain the whole failure.

## One change

Before component RMS normalization, independently vary h1 through h5 around the original training annotation by fixed uniform gains in [-6,+6] dB. Each component has a 50% chance of exact bypass. Seed 20261127; gains and identity draws are independent of source identity and labels. Gain curves use raised-cosine interpolation in dB, return to unity at 0.5*f0 and 6*f0, and stay unity outside that range. Apply one positive real rFFT multiplier to the complete 16384-sample crop. This changes detailed partial balance rather than the previous shelf's correlated tilt. No added noise, frequency shift, source selection, model change or new feature.

The new hypothesis is that training on this variation reduces dependence on a take-specific harmonic fingerprint. It is not established as the failure mechanism. All 555 original sources and annotations remain, with the original 200/200/155 source roles. Each original training example has one deterministic augmented version, so the fit still sees 16384 mixtures, 80 epochs and the same optimizer steps. Original clean training examples select the cutoff and determine training gates. Calibration/test/continuous audio is never augmented. No bound or seed selection from those roles.

## Frozen acceptance

Unchanged training cutoff: maximum true pitches at >=99% precision, stricter ties. Require recall >=80%, complete pitch sets >=70% overall and separately for 3, 4 and 5 distinct pitches, zero silence extras. Only then score calibration and test, each requiring precision >=95%, recall >=80%, complete sets >=70% overall and separately for 3/4/5 pitches, zero silence extras. The five-pitch targets are 1771/2529, 448/639 and 229/327.

Continuous ordinary and extended-middle replay runs only after every representation gate passes. Existing CURRENT identity, ordinary gain >=5 percentage points, no per-label presence/longest-hold loss and no wrong-pitch or gap-extra growth remain required. A success here would still need native allocation/deadline, lane/unison and live-host gates. This is pitch-set evidence, not installed frame/string improvement.

## Execution and evidence

One 45-minute CPU GitHub job, frozen source SHA, pinned dependencies, existing private input releases; no new upload. Source and worker commits will be recorded in github-harmonic-partial-variation-20261121.json. Collect the small report/log artifact once with server-digest verification; retain model and prediction evidence remotely. No automatic rerun, cutoff retune or promotion. Claude remains paused; no fresh Claude review claimed.

Original decompressed training plan SHA256: `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.
Augmented decompressed plan SHA256: `7604d928e23018fc4ea172dc1b186d17967b96b0f9e494dd8a114f6d2da8d0d3` (metadata only, generated before recorded execution).

## Risks and interpretation

The envelope uses the nominal training pitch, not an acoustic verifier. It can change periodic-crop transients or weaken a useful partial; identity examples retain clean components. DFT phase and bin locations are preserved, not an entire physical attack model. This creates no independent recording content. Reused development roles are not a fresh blind benchmark.

A metadata-only bound found that 85/327 test five-pitch rows include one of eight proven non-octave source conflicts. Conditional on verified alternate pitches replacing their nominal labels, the nominal exact-set ceiling is 242/327 (74.01%), still above target 229 by 13 sets. Seven octave-ambiguous cases were excluded from this bound, but all remain in scoring. This does not justify relabeling or score correction. Calibration's separate failure remains. Keep every original denominator and report rejection if a gate fails.
