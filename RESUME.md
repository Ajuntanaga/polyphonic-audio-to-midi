# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T07:50:30-07:00

## Authoritative state

- Branch: `main`
- Last verified commit: `5a80e95` (`fix: harden guarded REAPER GUI runs`)
- Current task: Task 4, streaming resonator bank and harmonic salience
- Task 4 detector changes are intentionally uncommitted pending complete
  44.1/48/96 kHz real-JSFX verification.
- Local result: 16 Python tests pass and `python3 tools/validate_source.py .`
  reports `source contract: ok`.
- Disposable profile: `build/reaper-test`; persistent REAPER profile untouched.
- No live guitar, audio interface, live project, download, install, MCP, or native
  fallback was used.

## Verified Task 4 evidence

- Expected RED: assertion 4101 selected MIDI 24 instead of 32. Evidence
  `build/evidence/task-04-resonator-tuning-red-4101.png`, SHA-256
  `a0f797d6ed016930e81debbd3bc14d505467fea27e7e851aad3de41b7757611d`.
- Diagnostic RED: MIDI 32 was a real local peak but the unguarded lower analysis
  edge scored higher. Evidence
  `build/evidence/task-04-resonator-diagnostics-48k.png`, SHA-256
  `91eb621d563a2005b5310146a26745ee5db8b7fe81340ec74ae417d69b6e2e68`.
- Real 48 kHz PASS: 24 assertions, failed ID 0. Evidence
  `build/evidence/task-04-resonator-48k-pass-candidate.png`, SHA-256
  `39cba1522f6c1c8023b3a017065436bd48b7a45068fe5da93ded305f2fec4fe5`.
- 44.1 kHz is not verified. Both the original combined run and a narrowed-case
  run reached the unchanged 60-second/30-CPU-second guard before `@init`
  completed. The blank screenshot is not PASS evidence.
- 96 kHz correctness has not been run. Its disposable rate project was
  regenerated successfully after the transient X-window retry fix.

## Current implementation and tuning

- The correctness bank uses fixed eight-word cells, causal 8 ms/35 ms complex
  correlations, 4096-sample oscillator renormalization, and no allocation.
- Requested pitch bounds are stored separately from analysis-only guard
  semitones. Production remains requested MIDI 32..84.
- Final score coefficients under test are harmonic mean `0.85`, minimum-three
  `0.05`, missing-fundamental support `0.10`, and neighbor penalty `0.03`.
  Decays, harmonic weights, and base threshold `0.20` remain unchanged.
- `docs/PERFORMANCE.md` records every measured coefficient and test-load change.
- `build/core-harness-44100.RPP` stores rate slider value `1` and
  `build/core-harness-96000.RPP` stores value `2`; both are ignored disposable
  build artifacts.

## Guarded REAPER boundary

Every GUI launch must use `python3 tools/run_guarded_reaper.py --gui --workspace
5` with only `build/reaper-test/reaper.ini`. Commit `5a80e95` enforces GNOME
workspace 5 (wmctrl desktop index 4), fixed memory/CPU/swap/task limits, one-core
affinity, low CPU/I/O priority, preflight memory/load/thermal checks, clean
interrupt handling, and a bounded retry only for the observed transient X11
`BadWindow` teardown race. Other workspace failures still refuse immediately.

## Exact resume action

1. Add a second visible test selector that runs exactly one expensive Task 4
   assertion group per disposable launch. Add the source-contract test first.
2. Extend `tools/prepare_core_harness_rate.lua` to persist both allowed rate and
   case values only into `build/core-harness-*.RPP`.
3. Run assertions 4101–4106 separately at 44.1, 48, and 96 kHz, always on
   workspace 5 under the unchanged guard. Aggregate the screenshots/results;
   never treat a timeout or blank panel as PASS.
4. Only after every rate/case is green, trim temporary diagnostics, rerun all 16
   local tests and source validation, update Obsidian, and commit Task 4 as
   `feat: add streaming harmonic salience bank`.

The user requested a hard pause at 07:55 PDT on 2026-08-25. Do not resume until
the user explicitly asks.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
