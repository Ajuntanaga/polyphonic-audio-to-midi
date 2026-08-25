# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T12:32:03-07:00

## Authoritative state

- Branch: `main`
- Last verified implementation commit: `ca9a256` (`feat: add safe telemetry
  and compact JSFX UI`).
- Latest stability commit: `821ba22` (`fix: background guarded REAPER
  launches`).
- Current task: Task 11, disposable REAPER host integration.
- Tasks 1–10 are verified and committed.
- Local result: 45 Python tests pass and `python3 tools/validate_source.py .`
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

## Verified Task 9 evidence

- Expected RED: the complete 9101–9109 host harness plus a zero-result emitter
  scaffold reached assertion 9101 in real REAPER at 48 kHz. It had three
  assertions and aggregate error 322. Preserved result
  `build/evidence/task-09-midi-host-red-9101.txt`, SHA-256
  `bb4045cf18175e0ce8684c10b75a220e0faf21bb9f62a3f44d5341d0c17664e7`.
- Final host matrix: cases 9101–9109 passed at 44.1, 48, and 96 kHz in 27
  hidden guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 27 results is
  `1a20321b3c6bb43ae671dc306f4ecc326f0ef286fa25faa333cd1c45d52a40e9`.
- Cases 4104, 5104, 6102, 6105, 7102, 7105, and 8102/block 128 passed again at
  48 kHz as a seven-case detector-through-lifecycle regression.
- A separate disposable load smoke instantiated the production JSFX enabled
  and online with two inputs, two outputs, and all fifteen named controls in
  order. Result `build/evidence/task-09-production-smoke.txt`, SHA-256
  `321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
  The script dirtied the disposable project while swapping FX, so the guard
  enforced its 60-second termination bound rather than producing a clean host
  close; Task 11 still owns host-sequence and VSTi-routing proof.
- Matrix preflights stayed above 30 GiB available memory, below load 1.2, and
  at or below 59 C. Workspace 1 stayed active and no REAPER process remained.

## Verified Task 10 evidence

- Expected RED: the complete 10101–10106 harness plus a permissive telemetry
  scaffold reached assertion 10101 in real REAPER at 48 kHz. It had three
  assertions and aggregate error 87. The raw observer result SHA-256 was
  `2d36f7973607e5cc6310aba3d878877b18204fff23f53be456371b50b768e5cd`;
  compact preserved evidence
  `build/evidence/task-10-telemetry-red-10101.txt` has SHA-256
  `c025e01d67f2723e670df7e30748defc9615a7f28a0895c8c9137b44e2e42297`.
- Final telemetry matrix: cases 10101–10106 passed at 44.1, 48, and 96 kHz in
  18 hidden guarded workspace-5 launches. Every result had three assertions,
  suite state `2`, and failed assertion ID `0`.
- The SHA-256 of the lexically ordered `sha256sum` output for all 18 results is
  `56768676bb073d9bba8e84e38322ff01e3692959a41f4ba1e9c2634e26969b47`.
- Cases 4104, 5104, 6102, 6105, 7102, 7105, 8102/block 128, 9101, 9104, and
  9109 passed again at 48 kHz. A transient X11 `BadDrawable` caused one safe
  preflight refusal before the bounded 9109 retry passed.
- The production-load smoke passed enabled and online with two inputs, two
  outputs, and all fifteen named controls, then saved and closed only its
  disposable project. Result `build/evidence/task-10-production-smoke.txt`,
  SHA-256
  `321e87851cbda022d3744f5cc8d1df8530a1a113ca863e0ee4b693780d087173`.
- Matrix preflights stayed above 30 GiB available memory, below load 0.9, and
  at or below 58 C. Workspace 1 stayed active and no REAPER process remained.

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
- Production filters selected M3 sets before lifecycle updates. Infeasible sets
  lose the lowest-confidence candidate and retry at most eight times; the final
  stable mode control exposes M3 Eight-String and General Tonal behavior.
- The lifecycle module stores eight fixed words for each of 128 pitches and an
  82-word ordered event queue. It implements OFF/ATTACK/ON/RELEASE hysteresis,
  eight-active-note enforcement, same-pitch collapse, release-all cleanup,
  note-off-priority overflow, and fixed/dynamic velocity. The emitter encodes
  channel 1–16 events, clamps block offsets, and sends each event once.
- The production effect has the frozen fifteen-slider surface. `@slider` only
  clamps and stages settings. `@block` performs reachable panic-before-reset
  for rate, stop, hard reconfiguration, and explicit Panic; `@sample` performs
  streaming analysis, one-time MIDI output, and the optional two-assignment dry
  mute. Incoming MIDI is untouched.
- Telemetry alternates two fixed 40-word snapshots, marks in-progress writes
  odd, and publishes only completed even generations. The 64-word UI region
  holds one snapshot plus a fixed twelve-note-name table. `@gfx` reads only the
  published snapshot and cannot write detector/lifecycle memory.
- Input trim ramps over 64 samples. Project serialization contains only
  `saved_schema_version=1`; active notes and detector state are discarded on
  load. Fault codes 1–5 disable detection, preserve available dry audio, and
  use reachable note-off cleanup. Two sample-edge `time_precise()` calls feed
  the three-block half-deadline overload indicator.
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
  rate/case RPPs. Its nine behavioral tests cover correct slider state and
  refusal of source/output paths outside `build/`.
- `tools/observe_core_harness_case.lua` accepts only the exact disposable Task
  4–10 case path shape, including mandatory collision-free block identity for
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

1. Add the Task 11 staging RED: require the disposable profile to include the
   production effect, constants module, and test runner under `Scripts/`, while
   still refusing `reaper-kb.ini` and the live profile.
2. Implement dependency-free staging for only the approved Effects, Scripts,
   Data, and test-results trees.
3. Add the bounded signal-source and MIDI-capture JSFX plus the disposable
   three-FX runner. Keep every launch hidden on workspace 5.
4. Run the host sequence before creating Safe Bypass. Require exact ordered
   MIDI, dry-path identity, panic/reconfigure note-offs, and a clean exit.
5. Create Safe Bypass only after that host sequence passes, then document the
   verified host boundary. Do not install into the persistent REAPER profile.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
