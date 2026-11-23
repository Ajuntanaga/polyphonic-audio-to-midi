# Redundant narrow-state clearing: fixed CPU screen

Codex owns the detector/replay diagnostic, native identity test, one small
runner wrapper and `narrow-clear.yml` worker. Claude keeps the independent
stable-note result check and its next saved-data investigation; no reply or
permission from either peer gates the other's authorized lane.

Source evidence: `process_sample` updates the two narrow fundamental arrays
only in M3 mode with max fret <=2, but clears both on every quiet sample in
every mode. `set_runtime_config` can change that mode without resetting the
arrays. A mode-only shortcut would therefore be incorrect. The proposed path
tracks whether a narrow update has occurred since the last clear; it skips a
clear only when the arrays are already known zero. Track writes even while
the diagnostic is disabled, so switching the flag or profile is safe.

The old stage report 43776647926 attributes about 2.3 s to signal-reset work
on ordinary; this includes instrumentation and other work, so it is motivation,
not a predicted speedup. Packed arithmetic and exact-cell sharing remain
rejected. This is a distinct memory-write reduction, with no arithmetic,
threshold, selection or lifecycle change.

Frozen before implementation and results: `--diagnostic-elide-narrow-clears`,
default off and compiled only under M3_OFFLINE_REPLAY_DIAGNOSTICS. Production
VST3 stays unchanged. Quiet-sample, narrow-update, performed-clear and skipped-
clear counters run in both diagnostic arms. The fixed corpus uses max fret 24:
require no narrow updates, at least one quiet sample, every OFF quiet sample
cleared, every ON quiet sample skipped, and equal quiet counts across arms.
Native tests must additionally exercise nonzero narrow state, runtime mode
switches, flag toggles, reset and reconfigure with bit-identical arrays and no
processing allocations. Pure runner mocks are local; native work stays on GHA.

One same-binary GitHub CPU screen: ordinary CURRENT, ordinary completion-
retention, physical-long completion-retention. Alternate OFF/ON order. Six
block-32 trace-free timing runs first, then six untimed block-512 MIDI companions.
Use the already pinned separate block-32/512 references. Every pair must retain
saved snapshot identity and paired raw MIDI, zero allocations/frees, valid CPU
clocks, >=2% total thread-CPU reduction and no CPU-p99 increase. One failed pair
rejects the screen; no tuning or repeated screen. Counter overhead is included
in both arms. Wall p99/max/overruns remain reported, and this instrumented screen
cannot establish production deadlines or live readiness. A useful result would
still need the separate native corpus gates. No installed/default or label-
budget change. Bulk evidence stays remote.

Preparation verification: 21 pure mocked-runner tests passed locally. The worker
YAML and all six shell sections parsed. One static review found no material
blocker in dirty-state tracking, flag/mode/reset handling or the fixed workflow.
Native execution and the measured result remain for GitHub Actions.
