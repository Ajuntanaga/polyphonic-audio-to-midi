# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T09:21:30-07:00

## Authoritative state

- Branch: `main`
- Last verified commit: `42443ac` (`feat: add streaming harmonic salience bank`)
- Current task: Task 5, bounded polyphonic selection and harmonic explain-away.
- Task 4 is verified and committed. The working tree was clean immediately after
  its commit; this recovery update is the only intended follow-on change.
- Local result: 17 Python tests pass and `python3 tools/validate_source.py .`
  reports `source contract: ok`.
- Disposable profile: `build/reaper-test`; persistent REAPER profile untouched.
- No live guitar, audio interface, live project, download, install, MCP, or native
  fallback was used.

## Verified Task 4 evidence

- Expected RED: assertion 4101 selected MIDI 24 instead of 32. Evidence
  `build/evidence/task-04-resonator-tuning-red-4101.png`, SHA-256
  `a0f797d6ed016930e81debbd3bc14d505467fea27e7e851aad3de41b7757611d`.
- Diagnostic RED: MIDI 32 was a real local peak but an unguarded lower analysis
  edge scored higher. Evidence
  `build/evidence/task-04-resonator-diagnostics-48k.png`, SHA-256
  `91eb621d563a2005b5310146a26745ee5db8b7fe81340ec74ae417d69b6e2e68`.
- Final correctness matrix: cases 4101–4106 all passed at 44.1, 48, and 96 kHz
  in 18 separate disposable workspace-5 launches. Every suite state was `2` and
  every failed assertion ID was `0`.
- Case 4101 ran 19 assertions at each rate; cases 4102–4106 ran three assertions
  each. The SHA-256 of the lexically ordered `sha256sum` output for all 18 result
  files is
  `fc1b8b40f04aa88066ea67baeec0cba43eef2d97e186797b2947da6dbd53c944`.
- Final 44.1 kHz case-4101 PASS panel:
  `build/evidence/task-04-44100-case-4101.png`, SHA-256
  `f9d9181172ba9414e88236aed596bad987a36d3222f16844b06f43ed755948f2`.
- During the final matrix, preflights remained far inside the fixed stops:
  about 29 GiB available memory, load below 3.7, and readable temperature no
  higher than 73 C. No REAPER process remained afterward.

## Current implementation and tuning

- The correctness bank uses fixed eight-word cells, causal 8 ms/35 ms complex
  correlations, 4096-sample oscillator renormalization, and no allocation.
- Requested pitch bounds are stored separately from analysis-only guard
  semitones. Production remains requested MIDI 32..84.
- Final Task 4 score coefficients are harmonic mean `0.85`, minimum-three
  `0.05`, missing-fundamental support `0.10`, and neighbor penalty `0.03`.
  Decays, harmonic weights, and base threshold `0.20` remain unchanged.
- `tools/prepare_core_harness_project.py` generates only build-local, literal
  rate/case RPPs. Its three behavioral tests cover correct slider state and
  refusal of source/output paths outside `build/`.
- `tools/observe_core_harness_case.lua` accepts only the exact disposable case
  path shape, removes only that case's old result, publishes atomically, and
  exits REAPER. It does not analyze audio or emit performance MIDI.
- `docs/PERFORMANCE.md` records all measured coefficient, guard, and matrix
  evidence.

## Guarded REAPER boundary

Every GUI launch must use `python3 tools/run_guarded_reaper.py --gui --workspace
5` with only `build/reaper-test/reaper.ini`. Commit `5a80e95` enforces GNOME
workspace 5 (wmctrl desktop index 4), fixed memory/CPU/swap/task limits, one-core
affinity, low CPU/I/O priority, preflight memory/load/thermal checks, clean
interrupt handling, and a bounded retry only for the observed transient X11
`BadWindow` teardown race. Other workspace failures still refuse immediately.

## Exact resume action

1. Add the exact Task 5 assertions 5101–5106 before modifying selection code:
   suppress E2 harmonic ghosts; select E2+B2; select G#1+C2+E2; select all eight
   open strings; preserve a true note at -24 dB; and cap `max_voices=3` without
   touching selection guard words.
2. Run the bounded disposable suite and preserve the expected earliest RED
   (`5102`, or the earliest new assertion) before implementation.
3. Implement `m3_select_voices(...)` in `salience_selector.jsfx-inc` with a
   fixed eight-iteration cap, residual explain-away, independent-fundamental
   protection, fixed selection cells, and bounded insertion sort.
4. Run assertions 5101–5106 under the unchanged workspace-5 guard, rerun all
   local tests and source validation, then commit as
   `feat: select bounded polyphonic pitch sets` only when every required case is
   green.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
