# Measured pitch halo: frozen comparison

The setwise baseline (run 44965135706) uses four shared residual convolutions with dilations 1, 4, 12 and 19. Their receptive-field radius is 36 pitches (73 positions), larger than its 53-pitch input. Every output can therefore depend on a zero-padded boundary. This is a concrete architectural position cue, not proof that it caused the held-out failures.

## Frozen change

Extract the same 62 harmonic/RMS coordinates for 125 positions, MIDI frequency coordinates -4 through 120. Keep the original 53 output targets, MIDI32 through 84. Each dilated convolution becomes valid (zero added padding); crop its residual by the layer dilation at each end before addition. The widths are 125 -> 123 -> 115 -> 91 -> 53. Every output receives a full measured receptive field.

The central 62-coordinate values must be bit-identical to the baseline extraction. Fit the shared mean/std on the central training rows only and apply it unchanged to all 125 rows. Parameter count (14,465), seeded initial weights, setwise loss, optimizer, epochs, batch order, source roles, original mixture plans, labels and training-only cutoff procedure stay fixed. No augmentation, whitening, extra contrast features or level suppression is combined with this test.

Measured context and boundary removal change together; the result cannot attribute an effect uniquely to either. The very low halo frequencies are poorly resolved by the FFT, and high probes can be weak. Removing artificial boundaries does not make the audio front end exactly pitch-equivariant or remove pitch-correlated timbre. These are risks the screen must measure.

## Acceptance and execution

One bounded GitHub CPU job under the existing standing authorization. No new upload, local recorded processing, label edit, installation or promotion. Exact specification: `harmonic-halo-context-20261121.json`. Existing worker serialization prevents overlapping private processing.

All 555 labels remain: train 200, calibration 200, test 155. Training plan decompressed SHA256 remains `7c5c676126082c3bae9fb68dc03cec20f583951c44b7e7de1c84b1ca7b72d25d`.

The same training gate requires a train-only >=99% precision cutoff, recall>=80%, exact sets>=70%, each 3/4/5-pitch exact>=70%, and zero silence false outputs. Five-pitch target is 1771/2529; baseline 1818. Only a training pass permits calibration/test scoring. Each held-out role must pass precision>=95%, recall>=80%, exact>=70%, each 3/4/5-pitch exact>=70%, and zero silence false outputs. Baseline held-out five-pitch counts are 283/639 and 27/327; success on training alone is not acceptance.

Continuous ordinary/extended-middle replay occurs only if all representation gates pass, then requires the existing CURRENT identity, >=5 percentage-point ordinary gain, and no per-label presence/longest-hold loss, wrong-pitch growth or extra-gap growth on either recording. Later full-corpus, lane/unison, lifecycle, allocation, p99/max/deadline and live host/device gates remain open.

Before fitting, GitHub runs synthetic checks for central feature identity, central-only normalization, input/output alignment, unchanged initialized parameters, absence of convolution boundary cues, feature-grid shift equivalence, fit/persist/restore, and existing fail-closed gate orchestration and scoring. Read-only review is one pass; any concrete failure is fixed before proceeding. Collect the small result once with its server digest; keep bulk remotely. No automatic rerun or retuning on rejection.

Claude remains paused; no fresh Claude review is claimed. The earlier split artifact and Claude publication requests were already fulfilled. The broader live-readiness goal remains active.
