# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T11:25:21-07:00

## Authoritative state

- Branch: `main`
- Last verified implementation commit: `544276a` (`feat: track independent
  note lifecycles`).
- Latest stability commit: `bf72bab` (`fix: settle workspace after REAPER
  exits`), following `51bede8` (`fix: preserve workspace during guarded REAPER
  launch`).
- Current task: Task 9, production host, sample-offset MIDI, and reachable
  cleanup.
- Tasks 1–8 are verified and committed.
- Local result: 29 Python tests pass and `python3 tools/validate_source.py .`
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
  `8c154e597dae4d2ef9dddbd2cecb9e87ed6968258651e8517f8d2f880a81306b`.
- Final 44.1 kHz case-4101 PASS panel:
  `build/evidence/task-04-44100-case-4101.png`, SHA-256
  `f9d9181172ba9414e88236aed596bad987a36d3222f16844b06f43ed755948f2`.
- During the final matrix, preflights remained far inside the fixed stops:
  about 29 GiB available memory, load below 3.7, and readable temperature no
  higher than 73 C. No REAPER process remained afterward.

## Verified Task 5 evidence

- Expected interface RED: `m3_select_voices` was undefined in real REAPER.
  Evidence `build/evidence/task-05-selector-interface-red.png`, SHA-256
  `aa3a2cbc770ec7ede0f57fc85e05d72522cf0182b3f87281c18045984f7c4c87`.
- Expected behavioral RED: a bounded zero-result scaffold compiled and failed
  assertion 5102. Evidence
  `build/evidence/task-05-selector-behavior-red-5102.png`, SHA-256
  `8bb0fbe08b62204aeea00f884c7b73458f5b3deb9ac8d1c776698d0aa8eef205`.
- Final selector matrix: cases 5101–5106 passed at 44.1, 48, and 96 kHz in
  18 separate disposable workspace-5 launches. Every run had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 Task 5
  result files is
  `ed8e57aa646282cc8abe76d5672c7905d6c59a373edc9c2232d0b0dcf9026ff8`.
- Final eight-open-string selector panel:
  `build/evidence/task-05-48000-case-5104-pass.png`, SHA-256
  `357a4d05f59d2179659ac9e96934ec6c51bd07fc71d3d5d4b30ed6fb2b36b9c9`.
- These are selector-layer tests over salience and per-harmonic energy cells;
  they are not an end-to-end chord-audio accuracy claim. That remains gated by
  later synthetic and separately authorized clean-DI metrics.

## Verified Task 6 evidence

- Expected interface RED: `m3_bank_process_reference()` was undefined in real
  REAPER. Evidence `build/evidence/task-06-reference-interface-red.png`,
  SHA-256
  `94b831eb431c2fe23b50bb6c4c8dbdbda53197389a641eef0dd8539ff4d92b24`.
- Behavioral RED: assertion 6105 measured 440 full-rate cell updates per input
  sample against a maximum of 45. The observer's numeric result is authoritative;
  the attempted gray GUI capture is not evidence.
- Final Task 6 matrix: cases 6101–6106 passed at 44.1, 48, and 96 kHz in 18
  separate guarded launches. The SHA-256 of the lexically ordered `sha256sum`
  output is
  `b5155c896c3c52b95957c38ce86852b8cd289b5bd38baad9b50f15cbb98a38f5`.
- Worst open-string salience deltas were `0.019250096364574` at 44.1 kHz,
  `0.020745752092474` at 48 kHz, and `0.013100931661116` at 96 kHz, all below
  the `0.03` bound.
- At 48 kHz over MIDI 32..84, 251 cells averaged 44.75 updates per input
  sample, about 89.8% below the 440-update full-rate baseline.
- The final adaptive multi-rate implementation also passed all 18 Task 4 and
  all 18 Task 5 regression cases at 44.1, 48, and 96 kHz. Their refreshed
  result digests are
  `c3793e0626760661340b6b1da5be0433ebb1f232b7369ff74448af07d1e6ab4d`
  and
  `5b199fb184c853421338f011266788c903a8ea6a9ce990e5ed21162daa2519ca`.

## Verified Task 7 evidence

- Expected RED: a zero-result profile scaffold reached assertion 7101 in real
  REAPER with three assertions and observed open-note error 368. Preserved
  result `build/evidence/task-07-profile-red-7101.txt`, SHA-256
  `8aa336e939f82225d9e52e211ca88fd89cd36a1b27f469c1eb0252759cd25b60`.
- Final profile matrix: cases 7101–7106 passed at 44.1, 48, and 96 kHz in 18
  separate guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 Task 7
  results is
  `6096b227cca280fd720c8420be467aedf7b80a7aafd7e243898ebbf3239429d7`.
- Cases 4104, 5104, 6102, and 6105 were rerun at all three rates as a
  proportional cross-layer regression; all 12 passed.
- During these launches, available memory stayed near 28 GiB, load stayed
  below 3.3, and readable temperature stayed at or below 73 C. Workspace 4 was
  restored after each workspace-5 run and no REAPER process remained.

## Verified Task 8 evidence

- Expected RED: the complete 8101–8111 harness plus a zero-result lifecycle
  scaffold reached assertion 8102 in real REAPER at 48 kHz/block 64. It had
  three assertions and aggregate error 64. Preserved result
  `build/evidence/task-08-lifecycle-red-8102.txt`, SHA-256
  `421def10592db36a72b2697beea40573336ab6c663068ab6c77ca5f26e0e24a8`.
- Final lifecycle matrix: cases 8101–8111 passed at block sizes 32, 64, 128,
  and 256 in 44 separate guarded launches. Every result had three assertions,
  suite state `2`, failed assertion ID `0`, matching block identity, and zero
  active notes after cleanup.
- The SHA-256 of the lexically ordered `sha256sum` output for the 44 results is
  `c4698e0d4571f9a53c37d7d0d1524226e78f1787025e55b84b4e52e818deb6ea`.
- Cases 4104, 5104, 6102, 6105, 7102, and 7105 passed again at 48 kHz as a
  six-case proportional regression.
- A first-green harness expectation used raw floating-point `floor` and saw
  191 instead of the intended nearest-sample 192 for 4 ms at 48 kHz. Only the
  expectation changed; lifecycle coefficients and production behavior did not.
- Available memory stayed near 28 GiB, load stayed below 3.8, and readable
  temperature stayed at or below 73 C. The runner restored the user-selected
  workspace (4 early, 1 later) and left no REAPER process running.

## Current implementation and tuning

- The production bank uses fixed eight-word cells, causal 8 ms/35 ms complex
  correlations, 4096-sample oscillator renormalization, and no allocation.
- Four causal streams run at `sr`, `sr/2`, `sr/4`, and `sr/8`, with two
  second-order low-pass sections before each divide-by-two stage. Rate routing
  is fixed until reinitialization and uses a `0.16` threshold plus edge
  promotion. At 44.1 kHz, pitch cells use `sr/4` or faster.
- Harmonic allocation is bounded and adaptive: six partials through MIDI 52,
  four through MIDI 75, three at MIDI 76 and above, and three for analysis-only
  guard notes. This preserves the missing-fundamental E2 regression.
- The M3 profile loads exact open notes `32,36,40,44,48,52,56,60`. Its
  distinct-string matcher uses two fixed 256-word reachability rows and at most
  `8 * 256 * 8` transitions per feasibility pass. Scratch guard words remain
  outside the 512-word working region.
- Production now filters selected M3 sets before the future lifecycle stage.
  Infeasible sets lose the lowest-confidence candidate and retry at most eight
  times; General Tonal mode bypasses the matcher. The user-facing mode control
  remains scheduled for Task 9.
- The lifecycle module stores eight fixed words for each of 128 pitches and an
  82-word ordered event queue. It implements OFF/ATTACK/ON/RELEASE hysteresis,
  eight-active-note enforcement, same-pitch collapse, release-all cleanup,
  note-off-priority overflow, and fixed/dynamic velocity. MIDI encoding and
  host emission are not implemented yet.
- Requested pitch bounds are stored separately from analysis-only guard
  semitones. Production remains requested MIDI 32..84.
- Final Task 4 score coefficients are harmonic mean `0.85`, minimum-three
  `0.05`, missing-fundamental support `0.10`, and neighbor penalty `0.03`.
  Decays, harmonic weights, and base threshold `0.20` remain unchanged.
- The selector uses at most eight fixed iterations, four words per output cell,
  `0.18` harmonic residual attenuation, `0.35` independent-fundamental
  protection, bounded insertion sort, and 117 words inside the 256-word fixed
  selection region.
- `tools/prepare_core_harness_project.py` generates only build-local, literal
  rate/case RPPs. Its seven behavioral tests cover correct slider state and
  refusal of source/output paths outside `build/`.
- `tools/observe_core_harness_case.lua` accepts only the exact disposable Task
  4–8 case path shape, including mandatory collision-free block identity for
  Task 8, removes only that case's old result, publishes atomically, and exits
  REAPER. It does not analyze audio or emit performance MIDI.
- `docs/PERFORMANCE.md` records all measured coefficient, guard, and matrix
  evidence.

## Guarded REAPER boundary

Every GUI launch must use `python3 tools/run_guarded_reaper.py --gui --workspace
5` with only `build/reaper-test/reaper.ini`. The guarded launcher enforces GNOME
workspace 5 (wmctrl desktop index 4), fixed memory/CPU/swap/task limits, one-core
affinity, low CPU/I/O priority, preflight memory/load/thermal checks, clean
interrupt handling, and a bounded retry only for the observed transient X11
`BadWindow` teardown race. GUI tests use `-noactivate`, detached standard
streams, hidden test windows, and 20 ms startup placement. A pre-launch snapshot
excludes already-open REAPER windows. The guard records the user's active
workspace and restores only a focus steal to workspace 5, including a short
post-exit settling window; it never overrides a third workspace the user
selected. Repeated destroyed-window snapshots defer to the next bounded poll;
other workspace failures still refuse immediately. A live 10 ms observation
kept workspace 1 active for the full launch and left no REAPER process behind.

## Exact resume action

1. Add Task 9 assertions 9101–9109 before creating `midi_emitter.jsfx-inc`:
   channel 1/16 encoding, event-offset bounds, rate-change and transport-stop
   cleanup, explicit Panic, duplicate prevention, input selection, and
   block-boundary mode reconfiguration.
2. Preserve the real-REAPER RED at assertion 9101 before implementing the
   emitter.
3. Add the final stable 15-slider parameter surface exactly as specified; never
   renumber it afterward. `@slider` may clamp and set a reconfigure flag but may
   not rebuild detector memory.
4. In `@block`, panic before rate/reset/reload/transport-stop reinitialization,
   apply pending reconfiguration, reset block/event cursors, and keep
   `ext_noinit=1`.
5. Emit each ordered event once from `@sample` with its in-block offset. Never
   call `midirecv`; leave incoming MIDI untouched. Dry passthrough must contain
   no audio assignments when enabled and only the two explicit zero assignments
   when muted.
6. Document reachable versus abrupt cleanup in `docs/MIDI-LIFECYCLE.md`, run
   assertions 9101–9109 plus source-contract checks, then commit as
   `feat: emit sample-offset MIDI with lifecycle cleanup` only when green.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
