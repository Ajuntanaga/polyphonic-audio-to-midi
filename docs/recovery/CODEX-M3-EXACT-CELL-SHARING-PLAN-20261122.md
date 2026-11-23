# Exact resonator sharing — frozen CPU experiment

2026-11-23 UTC. Codex owns the detector/replay changes, their synthetic tests,
the new portable comparison tool and `exact-cell-sharing.yml` worker for this
experiment. Claude retains the distinct callback/restart analysis. Neither
workstream waits for the other; this note prevents conflicting edits.

The configured bank contains harmonics with exactly equal oscillator steps.
Equal initial states, input, decay and step bits imply equal state at every
sample. A small Python arithmetic check found 91 duplicate pairs among 245
enabled cells at 48/96 kHz and 93 at 44.1 kHz. These are feasibility counts,
not measurements of the C++ bank or a speed claim.

Implement one default-off `M3_OFFLINE_REPLAY_DIAGNOSTICS` replay option,
`--diagnostic-exact-cell-sharing`. At configure time, group enabled main cells
only when both stored rotation-step doubles are bit-identical. Update one
representative per group and copy its dynamic fields to the other original
slots on every sample. Keep guard cells, original slot indexing, multiplication
order, phase/evidence readers and all selection/lifecycle rules unchanged.
Copy the optional selection-window state too. No allocation in processing.
Production builds and installed/default output remain unchanged.

Direct verification: native synthetic tests compare all cell states bitwise
with the original loop across sample rates, pitch bounds, reset and the
optional selection-window diagnostic. The remote screen uses one binary with
the flag off/on, fixed 32-sample blocks, three paired conditions inherited from
the previous sample-observation screen: ordinary CURRENT, ordinary completion
MIDI retention, physical-long completion MIDI retention. Alternate arm order
by case. Each arm must preserve its pinned reference snapshot and metrics;
paired raw MIDI must also be identical. Timing identities, buffer-resolution
checks and zero processing allocations are required. Report actual C++ unique
and duplicate counts outside the timed callback.

Harness clarification before dispatch: raw MIDI capture is forbidden during
core timing. The same job therefore adds six untimed 512-sample companions,
with the same three conditions and alternating arm order. Each companion
preserves its historical snapshot; the off/on pair has identical complete raw
MIDI. The six 32-sample timing replays remain trace-free. This is twelve fixed
replays total, not a parameter sweep or a second timing measurement.

Usefulness is fixed before execution: every pair must reduce total thread CPU
time by at least 2% without increasing thread CPU p99. Report wall p99/max and
overruns separately; these measurements do not replace full-corpus deadlines
or establish live-host readiness. A faster non-identical arm is rejected.
One scoped GitHub CPU dispatch after the implementation and relevant checks;
no local native build, audio replay, parameter sweep or repeat to obtain a pass.
Small report/log collection once; keep bulk snapshots/MIDI remote.

Ready for the single dispatch: the portable runner's 14 mock tests passed
locally, including fail-closed identity, trace, timing and allocation checks.
The independent static review of the six native files found no material
defect. Compiler and native runtime results remain unmeasured until GitHub
executes the tests and fixed replay pairs. The worker records both source and
worker revisions, and captures output before parsing it.
