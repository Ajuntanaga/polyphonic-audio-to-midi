# Native candidate joint/temporal feasibility — 2026-11-23

Codex owns the new `tools/native_candidate_temporal.py`,
`tools/portable_native_candidate_temporal.py`, their synthetic test, the frozen
specification and the worker `native-candidate-temporal.yml`. Claude's ordinary
58-event acoustic work is independent. This is covered by the standing scoped
CPU-job authorization. No acknowledgement or additional approval is required.

Question: can joint, causal native candidate evidence identify useful additional
pitches without admitting extra wrong notes? The earlier scalar/floor tests
failed. Run 44942243299 tested Basic Pitch trajectories, not native phase,
calibration, selection and energy histories. This screen tests those native
features together once; it is not a retune of that model or a production change.

Use only the pinned ordinary and extended-middle v5 observation artifacts and
the committed CURRENT pitch-span reference. No audio, native replay, new inputs
or Basic Pitch inference. All corpus parsing, fitting and prediction run on
GitHub CPU. Local tests use synthetic tuples only.

Before constructing features, retain only a sufficient label-independent
subset of the legacy writer population: ordinary decisions, observed candidate
energy, score/threshold at least 0.20, direct evidence AND (local peak OR formed
evidence). This is a strict subset of the writer's `native/offline/replay.cpp`
1119-1127 predicate, independently checked before dispatch. Discard
annotation-expanded rows first. Missing history stays missing, not an observed
zero. Neither annotation fields nor note ID, string identity, absolute time,
passage ID, rendered outcomes or trace-row availability can enter the model.

Freeze one shallow histogram gradient-boosted classifier (the same fixed
hyperparameters as the previous feasibility screen), with current native
scalar features and same-pitch lags 1/4/16/64 decisions. Invalid phase/onset
values are missing. Exact feature order is committed in code before dispatch.
No hyperparameter search, feature selection, refit or cutoff change after test.

Use the existing whole-passage split: ordinary first 79 train, next 26
calibration, final 26 test, with three-second boundary purges; extended-middle
is entirely test. Some source takes recur, and both recordings are development
data: this is internal feasibility, not an independent-recording result.

Train on full-interval pitch targets with duration weights balanced by class.
Choose exactly one threshold: the next floating value above the maximum
negative calibration probability. Predictions add pitch occupancy to CURRENT
only from sample+1 to the following decision. No backdating, span extension,
hold, string assignment, deletion or relabelling. Classifier execution cost is
excluded, so this cannot establish live timing or MIDI delivery.

Advance only if ordinary test gains at least 1 percentage point of expected
pitch-sample coverage and at least five labels gain, with no false-pitch/gap,
exact-set/all-expected or per-label safety regression on calibration, ordinary
test and extended-middle. Report gains and false costs separately, plus
per-label holds and span counts. The strict scorer gates remain unchanged.
A failure closes this fixed screen. A pass justifies a separately frozen causal
implementation and independent recording test; it does not authorize promotion.
