# Joint native/model release latch: frozen feasibility test

2026-11-22. Codex owns only this CODEX-M3-JOINT-RELEASE plan, script and
result. Claude's independent support-event/anatomy work stays separate; this
note is coordination, not an acknowledgement gate. Saved spans only, no
audio, model execution, native build, dispatch or installed change.

## Question and fixed rule

The bare rapid-mute occupancy mask removed 41.95% of ordinary gap output but
failed the relative label budget and fragmented sustained output. Test a
different causal mechanism: **end an existing CURRENT pitch only when the
existing native rapid-mute flag is true and the emitted neural pitch is
absent; then latch that CURRENT pitch span off**. Do not reopen it merely
because the flag clears or the model later attacks it. Rearm only after
CURRENT has ended and begun a separate maximal same-pitch occupancy span.

One rule, no parameter grid, no label/pitch exceptions, no changed threshold:

1. Use the previously collected CURRENT maximal pitch spans, ordinary and
   extended-middle, on their common scoring horizons.
2. Use the frozen rapid-mute `marked_intervals` from
   `CODEX-M3-RAPID-MUTE-20261122.json`, SHA-256
   `c2008b8956223340d29aa0961f16cc0eba0e73dd648ac9c1894952a6f2c38369`.
   These already project each last native decision to the following completed
   512-sample callback. No v5 reread or new quiet predicate.
3. Neural state comes only from the pinned **cropped adapted** ordinary and
   extended-middle event files listed in `CODEX-M3-SUPPORT-EVENTS-20261122.py`,
   on `emitted_ns`. Do not shift timestamps or dilate support. Before the
   first observed neural NoteOn, absence is unknown and cannot cause a cut.
   This is a conservative event-stream warm-up rule, not a tuned timer.
4. At callback boundary b, consider only CURRENT spans whose start is
   **strictly before b** and whose end is after b. This preserves the native
   attack callback. If b is rapid-mute and the model has been primed, cut at b
   iff the neural same-pitch state is absent. Apply all model events at b
   before the decision: On at b protects; Off at b permits a cut. An event
   after b cannot affect that boundary.
5. Keep the prefix from CURRENT start to the first qualifying cut. The rest
   of that CURRENT span stays off. If no boundary qualifies, retain it whole.
   No added note starts or within-span resurrection are allowed.

This is a callback-causal unique-pitch span simulation, not a native MIDI
implementation. CURRENT merges touching same-pitch spans; lane/unison
ownership and same-sample native retriggers are therefore not modeled.
Measured worker neural delivery clocks are used; live scheduling and the
joint VST3 path remain unverified.

## Gates fixed before combination is scored

First require exact baseline scorer identity and input hashes on both
recordings, valid model pairing, and the earlier trace audit hashes. Check
the state machine on synthetic spans: no cuts before priming; new-On
protection; same-boundary neural On/Off; no future-event access; no
resurrection; reset across a real CURRENT gap; no-cue identity.

Report the unchanged strict scorer and the fixed budget separately:
per-label present and longest-hold losses <=25 ms **and** <=5% of that same
CURRENT metric; no new complete misses; wrong-pitch/gap nonincrease;
exact/all-expected nondecrease on each recording. Report first-present delay,
all label deltas, cut count, shortened samples and pitch-occupancy run count.
Removed samples must reconcile as genuine + wrong-pitch + unlabeled-gap.

A useful feasibility pass also requires **at least 20% ordinary gap-output
removal** (roughly half the bare mask's result) with no increased occupancy
runs. Both protected recordings must pass the fixed budget. Otherwise reject
this exact rule; do not tune its latch, masks, warm-up or label exceptions.
Passing would justify implementation and new held-out validation, not accept
or promote a tracker. These are design recordings already examined.

Known risk before scoring: neural false absence can cut a true note, and the
latch can carry that error into a later label inside one continuous CURRENT
span. Conversely, delayed neural NoteOff may veto the only useful native
decay interval. These risks are the purpose of this one feasibility check.

Freeze this plan and its executable before reading the combined result. The
script refuses a second result. No support-hold or decoder cutoff is varied.
