# Batched resonator state: frozen CPU screen

Recorded before implementation or measurements, 2026-11-23 UTC / Nov 22 PST.
Codex owns this bounded implementation and worker. Claude's acoustic re-pluck
lane is separate; Claude explicitly stopped heavy work at its usage limit.
No peer acknowledgement is needed to proceed under the user's standing scope.

The completed observation breakdown (45106622018) attributes 48.10–49.23% of
its instrumented signal-observation subtotal to resonator updates. That is a
location to test, not a production cost share or a promised speedup.

One default-off, replay-only candidate: store the independent enabled resonator
states in aligned arrays and update two different cells together with SSE2.
Keep each cell's existing multiply/add/subtract order, every enabled cell,
both boundary guards, and optional selection-window accumulators. No sharing,
threshold, policy, fast-math, FMA, decimation or skipped samples. Unlike the
rejected packed screen, vector lanes represent independent cells, so the
sample loop needs no per-cell gather/shuffle/scatter to the old structure.

The fixed bank is allocated at detector construction. The old cell structures
are materialized before a decision, before the narrow per-sample consumer,
and before any public diagnostic consumer. Reset, reconfiguration and flag
transitions preserve current state. Sharing and packed flags cannot coexist
with this candidate. All code is under M3_OFFLINE_REPLAY_DIAGNOSTICS; production
VST3/default behavior remains unchanged.

Files: native/include/m3/polyphonic_pitch_detector.hpp,
native/src/polyphonic_pitch_detector.cpp, native/offline/replay.{cpp,hpp},
native/offline/replay_main.cpp, native/tests/test_polyphonic_pitch_detector.cpp;
new tools/portable_batch_cell_update.py and its mock-only test. Worker: new
.github/workflows/batch-cell-update.yml in the recorded m3-offload checkout.

Native verification on GitHub: every state bit versus scalar across rates,
enabled/disabled harmonics and guards, selection window, reset/configure,
flag transitions and diagnostic reads between decisions; paired process
behavior including max_fret 2; zero processing allocations. Existing two native
test targets must pass. No native/audio execution on the laptop.

Use the existing fixed three-pair harness and references without changing its
thresholds: ordinary CURRENT, ordinary completion, physical-long completion.
Six block-32 timing runs in OFF/ON, ON/OFF, OFF/ON order, then six untimed
block-512 raw-MIDI companions. Require all saved snapshot identities, each
paired raw-MIDI identity, zero allocations/frees, at least 2% thread-CPU total
reduction and no thread-CPU p99 growth in every pair. A scientific failure is
final for this screen; no repeat, retune or promotion. A pass only licenses a
separate full-corpus decision, not live/deadline acceptance.

One GitHub CPU workflow after the implementation and mock contracts are ready.
Record both full source and worker SHAs and the single run id. Collect the
small report once with the server digest; keep snapshots/MIDI remote. Installed
scores and the prior rejected candidates remain unchanged in either outcome.

Implementation ready: one source review and all 20 mock-only runner tests pass.
Native state/lifecycle tests remain unexecuted locally and run first on GitHub.
The scalar state test covers deferred reads, toggles and reset; the process
comparison covers three rates, narrow/general modes and pending-state reset.
