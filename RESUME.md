# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-29T02:04:56-07:00

## VST3 adapter-correction design approved — written specification pending review

- On 2026-08-29 the user approved replacing the failed CLAP production path
  with one Linux x86-64 VST3 effect built over the preserved format-neutral
  C++17 detector core. The authoritative new specification is
  `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`.
  It is committed at `35f8a88` (`docs: design VST3 adapter correction`) with
  SHA-256
  `247b6f99cfb9de6df4d2b2e64f839df9aac93cf58b851d3ceb80509164f82a22`.
- The selected adapter is Steinberg's official non-distributable
  `SingleComponentEffect`: one host object owns processing, generic parameters,
  state, and prepared-configuration publication. There is no custom GUI,
  worker, helper process, model runtime, lookahead, or declared latency.
- The signal contract is guitar audio to generated VST3 NoteOn/NoteOff events
  to a downstream VSTi. There is one stereo audio input/output, no event input,
  one sixteen-channel event output, up to eight ordinary discrete notes, and no
  raw-MIDI passthrough, CC output, MPE, or event merging.
- M3 tuning remains `G#1 C2 E2 G#2 C3 E3 G#3 C4`; General Tonal mode, the
  fixed 64-sample decision cadence, fifteen writable controls, read-only
  Status, fourteen-value state, dry pass/mute, and every existing detector and
  stability threshold remain unchanged.
- The user explicitly added block size 512 and 96 kHz to the guarded
  capability design. The exact host matrix is ten serial rows: 48 and 96 kHz,
  each at blocks 32, 64, 128, 256, and 512. It stops after the first failed,
  invalid, timed-out, or pressure-aborted row. Separately, the REAPER child
  memory ceiling remains 512 MiB.
- 96 kHz remains a hard release gate with native-rate processing and the same
  64-sample cadence. The existing 96 kHz 32+56 false MIDI-44 regression is not
  waived by an adapter probe and must pass before release.
- No SDK was retrieved, no VST3 or detector source was written, no dependency
  was installed, no REAPER process was launched, and no persistent path or live
  project was touched. The written specification is now ready for user review;
  after approval, the next design artifact is a new VST3 TDD implementation
  plan, not direct implementation or resumption of old CLAP Tasks 11-24.

## Task 10 CLAP capability gate failed — hard stop

- The user explicitly authorized the four-row Task 10 gate on 2026-08-29.
  Fresh non-launching preflight passed with about 30 GiB available, load 2.42,
  temperature 46 C, memory-full PSI 0.00, and I/O-full PSI 0.18. The dry run
  emitted exactly the planned serial workspace-5 rows for 48 kHz block sizes
  32, 64, 128, and 256.
- The real runner launched block 32 only. Its guard returned zero and REAPER
  completed `suite-finish`, but the runner rejected the capability result and
  atomically preserved it at
  `build/test-results/native-clap-probe/batches/32.invalid-20260829T074326Z`.
  Per Gate C2, blocks 64, 128, and 256 were not launched and no retry was made.
- `capability.tsv` records `status=fail`, `failure_count=19`, `dry_error=inf`,
  positive `synth_peak=0.43603515625000033`, zero source fault, and zero capture
  overflow. The failure labels are `parameter-count`, all fourteen persistent
  `parameter-not-writable-*` checks, `status-state-persisted`,
  `scripted-phase-timeout`, `lifecycle-reset`, and `trigger-two-count`.
- The row did prove discovery and bounded execution: create/init/activate/start,
  stop/deactivate/destroy, float32 processing, separate host buffers, and both
  alias/separate activation self-tests passed. The first CC119 trigger reached
  the plug-in. REAPER did not invoke `reset`; the scripted phase did not reach
  its eight-event completion condition, so the held-note/second-trigger phase
  never ran. The empty event transcript and infinite dry-error sentinel are
  therefore non-completion evidence, not independent measurements.
- All fourteen state rows remained at their defaults after attempted ReaScript
  writes. The first sixteen names/ranges/defaults produced no failure labels,
  but REAPER reported a non-exact total parameter count. This single capture
  does not distinguish a CLAP-adapter contract error from a REAPER/ReaScript
  exposure mismatch, so no corrective claim or code change is made.
- Pressure stayed safe: before/after available memory was 29982.57/29808.68
  MiB, load 2.12/2.67, temperature 50/49 C, memory-full PSI 0.00/0.00, and
  I/O-full PSI 0.05/0.03. No REAPER application process remained afterward;
  PID 118 is Linux's `[oom_reaper]` kernel thread, not the DAW.
- The lexical seven-file evidence-manifest digest is
  `12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.
  Individual hashes are recorded in `docs/NATIVE-TESTING.md`.
- **Decision:** Gate C2 failed. Task 11 and all later detector-port work are
  blocked. Do not retry this CLAP row, launch the remaining rows, download a
  VST3 SDK, install anything, or modify the adapter under this authorization.
  Per the approved plan, the only next design action is a separately approved
  VST3 adapter correction.

## Native Tasks 1-9 sealed checkpoint — retained pre-gate state

- Branch `main` is sealed through `cc938f7` (`test: add disposable CLAP
  capability probe`). Native plan Tasks 1-9 are complete in commits
  `c682664`, `52ba588`, `b208f83`, `9e0ba74`, `facd070`, `bbae558`,
  `546ae84`, `ff7e330`, and `cc938f7`.
- The only retrieved dependency is the official CLAP `1.2.10` header tree at
  commit `195b42a004144fab0b3cf95e9c067187d15365b7`, copied with its license and
  exact provenance/checksum manifest. No VST3 SDK or fallback was retrieved.
- The bounded C++17 core foundation, minimal CLAP lifecycle/ports, exact
  parameter and versioned-state surfaces, ordered MIDI/fail-closed cleanup,
  prepared detector-configuration publication, build-local host guard, and
  disposable capability probe are implemented. The probe-only processor and
  report markers are excluded from the production build.
- Latest offline verification is green: 44 normal native tests, the same 44
  tests under AddressSanitizer/UndefinedBehaviorSanitizer, 114 Python tests,
  both source validators, Python bytecode compilation, and Git whitespace
  checks. The staged capability ReaScript matches its repository source
  byte-for-byte.
- Build-local artifact SHA-256 values are
  `4a9b8ff7e0febf7120c91319db5ec49837d35a0908f0b35919a09376329d3840`
  for `M3_Polyphonic_Audio_to_MIDI.clap` and
  `2dedbd2532c84c5d6522b0dd28f7143ba3bfd800cddbb672d7cd355c3e2a9066`
  for `M3_Polyphonic_Audio_to_MIDI_Probe.clap`. Both are x86-64 ELF shared
  objects; only the probe artifact contains `M3_CLAP_PROBE_REPORT`.
- This was the authoritative pre-launch state. Task 10 was subsequently
  authorized and failed at block 32 as recorded above; its remaining rows are
  no longer launchable under the current plan.
- Clean-DI/hardware input, live projects, REAPER MCP, detector-port Tasks
  11+, production-host validation, performance measurement, persistent
  installation, MPE, and a custom GUI remain separately gated.

## Authoritative state

- Branch: `main`. The current native implementation checkpoint is `cc938f7`;
  the newer failed-host gate is recorded by this recovery file. The retained
  Task 13 terminal JSFX checkpoint is `0be04d3` (`feat: complete
  polyphonic JSFX experiment and record native gate`); its predecessor is
  `8a1332d` (`test: generate deterministic synthetic matrix`).
- The approved native CLAP design was introduced at `3ac7dcb` (`docs: approve
  native CLAP architecture`). Its authoritative written specification is
  `docs/superpowers/specs/2026-08-28-native-clap-polyphonic-audio-to-midi-design.md`.
  The architecture and written specification were both approved on 2026-08-28.
  The authorized native implementation plan is now
  `docs/superpowers/plans/2026-08-28-native-clap-polyphonic-audio-to-midi.md`.
  Its SHA-256 is
  `4cb0a1daf31e34dfc853cffba0c0e4e57c5ec7eb8a00e47cfe6cd16cbc9c25b2`.
  It defines 24 TDD tasks, 149 executable checkboxes, and explicit dependency,
  capability-host, production-host, performance, clean-DI, and installation
  gates. At that planning-only checkpoint, no CLAP header, native source,
  build artifact, or REAPER launch had yet been created; the newer Tasks 1-9
  checkpoint above supersedes that implementation state.
- Current runtime fingerprint:
  `7f2724003de54d623b434abf263e6dae3e571d4064194440094ed4367aa29ac4`.
- The deterministic synthetic manifest is byte-identical to its generator and
  has SHA-256
  `683a72b34aaf01354fad11c0479ce03bd28a6b24bc7e5f3ae61dafca7bc67725`.
- Final 48 kHz/128-sample evidence is
  `build/test-results/task13-v232-final-jsfx-48k128-slice`. Within that 48-case
  capture, all 45 M3 cases and 124 expected M3 notes pass with precision,
  recall, and F1 `1.0`, zero false positives, false negatives, duplicates, or
  hanging notes. `events.tsv` SHA-256 is
  `a695ebdc5ac641bf3f51b16cfd0f48dca08f3723f717e296bde003bb437c2f2a`.
- Single-open latency passes at `21.333 ms` median and `40.133 ms` P95. The
  required three/four-note chord gate fails at `78.667 ms` median and
  `99.600 ms` P95 against limits of `40/65 ms`.
- Two independent 10,000-block 48 kHz/128-sample dense-M3 deadline runs failed
  decisively. Run A was `0.588229` median, `1.181451` P95, `19.909088` P99,
  and `20.577708` maximum deadline fraction; Run B was `0.594384`, `1.178591`,
  `19.914089`, and `20.711463`. Every block in both runs exceeded the `0.50`
  hard limit. Raw hashes are
  `30da3aa4a3cf0d19bd63fa7f4d8ea6d54b3f4cf9adf30c01058f48e4f0527122`
  and
  `d608a7039be77f0e0939cfcaab50e00ebbe38dec45f4135d8ecdc15d5fb1e9ab`.
- Current 48 kHz core cases 12101–12118 and case 4102 pass; case 4102 also
  passes at 44.1 kHz. At 96 kHz, its new 32+56 regression detects one false
  MIDI 44, so 96 kHz is independently not release-ready.
- Fresh current-tree checks: all 114 Python tests, 44 native tests, and the
  same 44 native tests under sanitizers pass; both source validators report
  green. Probe-only diagnostics remain excluded from the production artifact.
- The task-local `RESUME.md` remains authoritative. The canonical ResearchOS
  project dashboard and native implementation-plan note are synchronized as a
  human-facing, non-Git index.
- Every earlier JSFX-evidence REAPER instance ran serially, backgrounded on
  workspace 5, under the 50%-of-one-core and 512 MiB limits. Tasks 1-9 added
  no REAPER launch, and no REAPER application process remains.
- Decision: native plan Tasks 1-9 remain complete and sealed, but Task 10's
  capability gate failed at its first row. The JSFX detector remains stopped
  and uninstalled. The VST3 adapter correction is now approved and written;
  exact resume action is to review/seal its specification and then write a new
  VST3 TDD implementation plan. Do not retry CLAP or start old Task 11.
- Clean-DI recording/input, persistent installation, live projects, REAPER
  MCP, detector-port Tasks 11+, and every future REAPER launch remain
  separately gated.

## Approved native-design amendment

- Delivery form: one Linux x86-64 CLAP track effect with stable ID
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`.
- Runtime: format-neutral C++17 detector core plus a narrow CLAP adapter; no
  plug-in-owned worker, helper process, model runtime, lookahead, or declared
  latency.
- Scheduling: sample-wise conditioning/resonators and a fixed 64-sample
  salience/selection/lifecycle cadence independent of host block size.
- MIDI: raw MIDI 1.0 input passthrough and generated discrete output on one
  configurable channel; MPE remains deferred.
- Interface: the existing fifteen writable controls through REAPER's generic
  parameter view plus one read-only Status value. A custom GUI is deferred.
- Safety: all active-path storage is bounded and prepared outside `process()`;
  output exhaustion blocks new note-ons, retains pending releases, and keeps
  dry audio available. Native validation inherits the guarded disposable
  workspace-5 REAPER boundary.
- Adapter fallback: a failed minimal CLAP capability probe stops before the
  detector port. VST3 requires its own approved correction; it is not built in
  parallel.

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

## Verified Task 11 evidence

- The staged dummy-audio host chain was Signal Source -> production detector ->
  MIDI Capture -> ReaSynth -> Synth Output Probe. It used only the disposable
  `build/reaper-test/reaper.ini` profile in hidden, nonactivating workspace-5
  launches.
- The accepted run completed all 13 cases: mono, dyad, the full eight M3 open
  strings, and ten repeated eight-note Panic trials. Each row passed with exact
  expected note-on/off coverage, no capture overflow, no duplicate or
  unexpected notes, and nonzero ReaSynth output. Normal dry-path identity had
  maximum error `3.3306690738754696e-16`.
- All ten Panic trials released eight notes within `1.750–5.333 ms`, below the
  500 ms gate. Trial 10 executed the actual Safe Bypass ReaScript inline. The
  runner observed the detector disabled after the script's 50 ms cleanup wait,
  then deleted only that detector after all ten trials passed; ReaSynth and the
  output probe remained present.
- Synthetic onset evidence at 48 kHz was: mono E2 `49.333 ms`; dyad E2
  `49.333 ms` and B2 `68.000 ms`; eight opens C4 `41.333 ms`, C3 `54.667 ms`,
  G#2 `60.000 ms`, G#3 `89.333 ms`, E3 `134.667 ms`, E2 `150.667 ms`, and
  G#1/C2 `177.333 ms`. These are causal evidence times, not hardware
  round-trip latency, and the detector declares neither lookahead nor PDC.
- Preserved accepted artifacts are
  `build/evidence/task-11-results/{events.tsv,summary.tsv,safety.tsv,phase.log}`.
  Their individual SHA-256 values are respectively
  `cf3a128ab1442055039bb39eeef434a50630cd30c7ee8b32a5242d20194d987a`,
  `96fbad6c2e175ecfc7060b96c9a69aa0e34c9c9e4edc7f692f7d870ba45db2d2`,
  `1eedf2e3deb52f54687dbe9ebd50f762f543be84bdb1c164c2de467d83e0e92d`,
  and `e616554dbe23678dcc3b3426a506e195b1875c5ed7e57c2d81b3900278decd30`.
- The source/host debugging run exposed one stability boundary: TasksMax 32
  caused a kernel-recorded cgroup fork rejection. A source test was added and
  only TasksMax was raised to 64. The 50%-of-one-CPU quota, 384/512 MiB memory
  bounds, 64 MiB swap cap, low CPU/I/O weights, nice 10, idle I/O class, and
  hard wall timeout were retained. The accepted run caused no later cgroup
  rejection; post-run memory and I/O pressure were zero, about 30 GiB remained
  available, and no REAPER process remained.
- This is synthetic dummy-audio/VSTi-routing evidence. It is not a live-guitar,
  clean-DI, audio-interface, audible-output, or performance-readiness claim.
- A fresh post-documentation rerun against the staged current tree passed core
  cases 4102 and 9108 at 48 kHz, then passed the complete 13-case/10-trial host
  chain again. That rerun contained 182 MIDI events, exactly one inline Safe
  Bypass execution, Panic release times `0.479–2.667 ms`, nonzero ReaSynth
  output for every case, no remaining REAPER process, no recent cgroup/OOM
  record, about 30 GiB available memory, and zero memory/I/O pressure.

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
  distinct-string matcher first builds a 16-note bounded shortlist, then uses
  three fixed 256-word dynamic-programming rows and at most `8 * 256 * 16`
  transitions per feasibility pass. Scratch guards remain outside the 768-word
  working region.
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
  for rate, stop, hard reconfiguration, and explicit Panic. A fixed signal
  floor blocks stale silence selection, and a Panic latch prevents same-block
  detector refill until a quiet block is observed. `@sample` performs streaming
  analysis, one-time MIDI output, and the optional two-assignment dry mute.
  Incoming MIDI is untouched.
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
  protection, a 16-note bounded shortlist, deterministic onset ordering, and
  234 words inside the 256-word fixed selection region.
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
other workspace failures still refuse immediately. TasksMax is 64; CPU remains
limited to 50% of one logical core and memory remains capped at 512 MiB. A live
10 ms observation kept workspace 1 active for the full launch and left no
REAPER process behind.

## Exact resume action

1. Recover the failed Task 10 evidence directory and verify its seven-file
   manifest digest before any discussion of a next implementation.
2. Review and seal
   `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`,
   then write a new VST3 TDD implementation plan. Do not retry the CLAP
   capability row, launch its remaining blocks, modify the CLAP adapter,
   retrieve a VST3 SDK, or begin old Task 11 under this design-only gate.
3. The future VST3 capability plan must retain the approved ten-row matrix:
   48/96 kHz by blocks 32/64/128/256/512, serial, guarded, workspace 5, and
   stopped after the first invalid or failed row.
4. Keep clean-DI/live input, performance work, persistent installation, live
   projects, custom GUI work, and REAPER MCP behind their existing gates.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Still-gated actions

- VST3 SDK retrieval or adapter implementation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- CLAP retry or remaining Task 10 rows
- detector-port Task 11 and all downstream native implementation
- custom native GUI design or implementation
