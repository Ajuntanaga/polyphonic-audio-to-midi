# Frozen harmonic context classifier screen

The independent shared harmonic classifier recovered complete three/four/five-pitch training sets at 54.04%, 29.31% and 14.04%, below the fixed 70% requirements. Its cutoff-only and data-transfer explanations cannot account for failure on training. A prior absolute-spectrum MLP learned training chords but failed transfer and continuous false-output gates. This screen tests whether a shared pitch-context model can recover complete chords while transferring across the same recording passes.

## One frozen model

Keep the existing 53 pitch rows (MIDI 32–84), 62 harmonic coordinates per row, source roles, mixtures, gains, seeds, trailing windows and clocks. Normalize each coordinate using only the training mixtures and pitches. Apply a shared 62-to-32 channel projection, four residual 32-channel kernel-3 convolutions with pitch dilations 1, 4, 12 and 19, and a shared one-logit readout. ReLU, unweighted binary cross-entropy, Adam learning rate 0.001 and weight decay 0.0001, batch 128, 80 epochs, seed 20261121, one CPU thread. No early stopping or held-out fit. The exact machine-readable parameters and pins are in `harmonic-context-learning-20261121.json`.

One global cutoff is selected on training only for maximum recovered pitches at at least 99% precision, with the existing stricter tie rule. Save weights, normalization and cutoff before any held-out scoring. No per-label choice, source-label correction, class weighting, top-k selection, threshold sweep or automatic rerun.

## Decision order

1. Run the synthetic feature, context, fit, persistence, clock, source-isolation and orchestration tests on GitHub before reading recordings. Local checks that require Torch or scikit-learn are skipped because those packages are not installed locally.
2. Fit once on the unchanged 16,384 training mixtures. Require precision at least 99%, recall at least 80%, complete sets at least 70% overall and separately for three, four and five distinct pitches, and zero outputs on silent mixtures. A failure ends the screen before held-out or continuous evaluation.
3. If training passes, score both untouched 4,096-example roles. Each must meet precision at least 95%, recall at least 80%, the same complete-set requirements, and zero silence extras. No feedback into the model.
4. Only if all three roles pass, run the existing continuous ordinary and extended-middle screen on the measured FIFO clock. Require full saved CURRENT score identity, at least five percentage points of ordinary pitch-presence gain, no per-label loss of presence or longest hold, and no wrong-pitch or unlabeled-gap output growth on either recording.

## Execution and limits

One CPU GitHub Actions job in `Ajuntanaga/m3-offload`, using existing pinned private releases and an exact public source commit. No new dataset upload, local recorded processing, native/installed change or promotion. Collect the small report once with its server digest; leave model and prediction arrays remote. Standing authorization is recorded in `m3-standing-job-authorization-20261121.json`.

Capacity and optimizer change as well as context, so a gain would not isolate a causal context effect. The 73-position receptive field has radius 36 on a 53-pitch grid; zero padding can encode position and does not establish exact pitch-shift invariance. All 555 intended-label excerpts remain, including unresolved source-content disagreements. The pass protocols differ, ordinary reuses source material, and sustained normalized mixtures do not prove attack tracking, string assignment, unison multiplicity or live performance. The long trailing window spans 170.67 ms; callback service time is separate from musical latency. Claude is paused; this note does not claim a fresh Claude review.
