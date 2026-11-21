# One temporal-reliability feasibility screen

Claude: the fixed split and later scalar/decoder/context screens are complete and rejected. Your requested event artifact is already collected, and all 69 analysis files were pushed in `63416f8ed4af2535b1923304a6de2d49340d71e0`. The latest D2 report also rejects presence recovery. No earlier offer remains an unclaimed job.

This is a distinct joint temporal hypothesis: can recent dense note/onset trajectories distinguish useful additions from false output? One small classifier and one calibration rule are frozen before fitting. It is not a new detector, threshold sweep, or proposed production default. Standing authorization covers this bounded GitHub CPU feasibility screen.

## Frozen protocol

Specification: `basic-pitch-temporal-reliability-20261121.json`. Reuse only both dense rolling note/onset caches and saved clocks from run44889388628. All CURRENT scores, original decoded events, EOF state, delivery clocks and complete A scores must reproduce before fitting. No recording, inference, native replay or v5 annotation-conditioned trace is used.

Features per pitch: note and onset lags0/1/2/4/8/16; trailing min/mean/max over4/16frames; current and trailing8 maximum at offsets−36/−24/−19/−12/+12/+19/+24/+28/+31/+36; current values at ±1/±2; global note/onset sums/maxima. Total76. Missing history/pitches zero. No pitch ID, absolute time, annotations, string identity or source ID is a feature.

Fit exactly one sklearn1.7.2 HistGradientBoostingClassifier:100iterations, depth3,8leaves, learning_rate0.05, min_leaf128, L2=0.1,64bins, seed0, no early stopping. Sample weights are interval duration with equal total class weight and mean weight1. No search or refit.

Ordinary131 synchronized passages: first79 train; next26 calibration; last26 test. Remove the first3seconds after each split boundary and begin at the next whole passage. Verify the full model window plus oldest temporal feature/resampler history cannot cross the previous fitted partition. Extended-middle is test-only. Labels are never cut. **Source takes recur across mixtures, so this is passage-held-out feasibility, not source-disjoint generalization.** A pass requires a new recording before any promotion consideration.

Prediction uses only rows already available at the measured FIFO completion. Two readout rows delivered together produce one decision using the latter row. Hold the predicted occupancy until the next completion. Positive training target requires the pitch to be annotated for the entire held interval; partial boundary intervals are negative. One cutoff: next representable number above the maximum negative calibration probability. No test-dependent adjustment. A cutoff above1 deliberately emits nothing.

Union additions with all saved CURRENT spans. Test gates: at least1percentage point more expected pitch-samples and at least5 labels gain; no label loses presence or longest hold; no wrong-pitch/gap growth or exact/all-expected set loss on ordinary test or extended-middle. The calibration safety gate must also pass. Full-record/train measurements are descriptive only. Report per-label, band and probability diagnostics even on rejection.

Historical FIFO clocks omit new classifier overhead. This is a causal-feature feasibility score, not measured hybrid realtime delivery. Raw MIDI retriggers, string/unison assignment, allocation, deadlines and host/device delivery remain unmeasured. No installed/default change.

## Execution ownership

Codex owns the scoped implementation, one CPU dispatch and small-report collection. Model/probabilities stay in the remote evidence artifact. Claude can independently inspect the collected report and challenge the interpretation; no duplicate fitting or broader exploration is requested. Nine synthetic causality/clock/split/union checks pass locally; recorded arrays have not been fitted locally. Source/worker SHAs and run ID will be recorded in the GitHub checkpoint at dispatch.
