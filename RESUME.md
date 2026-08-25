# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T10:41:18-07:00

## Authoritative state

- Branch: `main`
- Last verified implementation commit: `d383c3c` (`perf: add bounded multi-rate
  resonator bank`).
- Latest stability commit: `bf72bab` (`fix: settle workspace after REAPER
  exits`), following `51bede8` (`fix: preserve workspace during guarded REAPER
  launch`).
- Current task: Task 7, M3 profile and distinct-string feasibility.
- Tasks 1–6 are verified and committed.
- Local result: 25 Python tests pass and `python3 tools/validate_source.py .`
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
  rate/case RPPs. Its four behavioral tests cover correct slider state and
  refusal of source/output paths outside `build/`.
- `tools/observe_core_harness_case.lua` accepts only the exact disposable Task
  4, 5, or 6 case path shape, removes only that case's old result, publishes
  atomically, and exits REAPER. It does not analyze audio or emit performance
  MIDI.
- `docs/PERFORMANCE.md` records all measured coefficient, guard, and matrix
  evidence.

## Guarded REAPER boundary

Every GUI launch must use `python3 tools/run_guarded_reaper.py --gui --workspace
5` with only `build/reaper-test/reaper.ini`. The guarded launcher enforces GNOME
workspace 5 (wmctrl desktop index 4), fixed memory/CPU/swap/task limits, one-core
affinity, low CPU/I/O priority, preflight memory/load/thermal checks, clean
interrupt handling, and a bounded retry only for the observed transient X11
`BadWindow` teardown race. It records the user's active workspace and restores
only a focus steal to workspace 5, including a short post-exit settling window;
it never overrides a third workspace the user selected. Other workspace
failures still refuse immediately.

## Exact resume action

1. Add Task 7 assertions 7101–7106 before creating the production profile:
   exact open notes `32,36,40,44,48,52,56,60`; all opens feasible at fret 0;
   chromatic notes 32..39 infeasible at fret 24; 44,48,52,56 feasible at fret
   24; note 31 infeasible in M3 mode; General Tonal mode bypasses the filter.
2. Preserve a real REAPER RED at assertion 7101.
3. Create `Effects/m3_poly_midi/m3_profile.jsfx-inc` with
   `m3_profile_load`, `m3_note_string_mask`, and bounded two-row/256-mask
   `m3_voicing_feasible`. The maximum loop count is `8 * 256 * 8`; scratch
   guard words must remain unchanged.
4. Apply feasibility only in M3 mode after selection and before lifecycle
   updates. If needed, remove the lowest-confidence candidate and retry at most
   eight times; General Tonal mode bypasses feasibility.
5. Run assertions 7101–7106 at 44.1, 48, and 96 kHz under the guarded launcher,
   then commit as `feat: validate M3 eight-string voicings` only when green.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
