# Coherent training transposition screen

Frozen before recorded execution. Specification: `harmonic-pitch-transposition-20261121.json`; worker: `harmonic-pitch-transposition.yml`. One CPU GitHub job under the standing M3 job authorization. No new input upload, local recorded processing, installation, default change or promotion.

The saved source-transfer diagnosis found both single-source and mixed-note errors. Shelf variation did not repair held-out transfer. This screen returns to the setwise baseline run44965135706 and adds coherent pitch transposition to training only. It asks whether exposing each recorded spectrum at other pitches improves source-disjoint complete-note sets without removing the original training examples. It does not assume the errors have one cause.

## Frozen change

- Keep all16384 original training mixtures, then append one companion per mixture. Every component of a companion receives the same integer shift, drawn uniformly from legal nonzero shifts in -6..+6 semitones with seed20261125. Every shifted target must stay in MIDI32..84. This preserves intervals, distinct-pitch count and unisons. Silence and the five non-silent boundary-spanning chords with no legal shift use identity.
- Use a rational resampling ratio approximating `2**(-shift/12)` with denominator<=4096 and pitch error<=0.01cent. A symmetric Kaiser5 FIR of length `20*max(up,down)+1` performs anti-alias filtering. This follows the pinned [SciPy1.13.1 resample_poly convention](https://docs.scipy.org/doc/scipy-1.13.1/reference/generated/scipy.signal.resample_poly.html).
- Preserve each original source key, source role, crop and gain as provenance. Map the original within-take crop quantile to a support interval long enough for the resampled16384-sample output plus64 input samples of guard at each side. No cross-take reads, padding or wrapping enter the output crop. Reapply the existing component RMS normalization and gains after resampling.
- Keep the shared harmonic features, setwise objective, architecture, Adam settings and80 epochs. There are32768 fit examples and20480 optimizer steps, twice the baseline exposure. This is a disclosed confound, not a pure augmentation ablation.
- Choose the cutoff and score the training gates on the original clean16384 examples. Both held-out roles use their original unmodified audio/plans. Source roles remain200/200/155; all555 intended-label sources remain. Source-consistency metadata never filters fitting or scoring.

The original decoded plan hash is `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`; the transposed plan hash, generated from metadata only, is `79ab8453a9c3fc1ff31200cc7da3fed66e1fa4fe47e46675681dbc6e0aeb773f`. All200 training sources and every chord cardinality are retained. The worker must reproduce both pins before fitting.

## Decision and reporting

Training: precision>=99%, recall>=80%, exact pitch sets>=70% overall and separately for3/4/5 pitches; zero silence false outputs. Both held-out roles: precision>=95%, recall>=80%, exact sets>=70% overall and separately for3/4/5; zero silence false outputs. Training failure skips held-out scoring; held-out failure skips continuous replay. If all pass, the existing continuous CURRENT identity, ordinary>=5pp presence gain, every-label presence/longest-hold non-inferiority and no wrong-pitch/gap growth on ordinary and extended-middle still apply. No sweep, refit, cutoff retune or automatic repeat.

Compare clean train/calibration/test counts with setwise run44965135706, including single-pitch false/missing outputs and complete3/4/5 sets. These are sampled sustained pitch-set measurements, not installed labeled-frame/string scores. Report rejection even when the workflow succeeds. Retain bulk model and predictions remotely unless a later specific diagnosis needs them.

Synthetic checks cover deterministic targets/intervals/source roles, boundary identity, pitch tolerance, output frequency/RMS, alias rejection and unison cardinality. Runner tests verify that augmented examples enter only fitting, clean examples select the cutoff, and held-out/continuous gates retain their original order. The remaining existing synthetic pipeline checks run on GitHub before recorded input processing.

## Limits and collaboration

Resampling shifts formants and time scale with pitch; it creates no new recording session or independent timbre. Shifted string masks are provenance only, not verified guitar fingering or lane supervision. Shared pitch-context weights are not exactly shift-equivariant at finite FFT resolution or padded boundaries. These source-disjoint roles have already informed development; they are not a fresh final benchmark. Attacks, note lifetime, lanes, unison multiplicity, native deadlines and delivered live MIDI remain unverified.

A read-only design consult recommended coherent shifts over independently shifting components because preserving interval structure makes complete-chord failures interpretable. Claude is paused; no new Claude review is claimed. The broader live-readiness goal remains active regardless of this screen's outcome.
