# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-09-24

## Current integrated product checkpoint

- Active worktree: repository root, branch `main`. It integrates the current
  stereo/96 kHz staging and generic host tuner parameters with the native
  eight-voice detector, tuner telemetry, and custom VSTGUI editor. The staged
  live preset selects full polyphony by default and opens the editor
  automatically.
- The native suite passes 191/191, including the REAPER custom-to-generic-to-
  custom editor reattach regression and a real detector-driven open-to-fret-24-
  to-open calibration sweep. Its simultaneous-string regressions use
  independent cents offsets, oscillator phases, amplitudes, and harmonic
  profiles, and verify every M3 tuner assignment remains within its physical
  string's configured open-to-maximum-fret range. A calibrated same-note pair
  now remains locked to its two physical tuner lanes throughout slow beating
  at 44.1, 48, 88.2, and 96 kHz, while a single calibrated string remains one
  lane. The VST3 detector matrix now covers those four rates at 17 host buffer
  sizes from 16 through 4096 samples, including non-power-of-two sizes, and
  proves dry-audio equality plus partition-invariant absolute MIDI onset/release
  positions. A Claude read-only audit found the remaining response attack gate
  was measured in raw 64-sample ticks; it is now normalized to elapsed time and
  a regression constrains cross-rate onset spread to 2 ms. This is in-process
  host-contract evidence, not a physical-driver dropout claim. Python discovery
  passes 343/344; its sole
  failure is the workspace-hygiene assertion finding 29 pre-existing ignored
  `.vst3` build bundles beneath `.worktrees/`, which were preserved. The
  plugin-facing checks, `tools/validate_native_source.py`, and Steinberg's
  production VST3 validator pass. The canonical release module is
  `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so`,
  SHA-256 `5ec895e5800fe87c4ed2d1a362ff62a88ae33d2d895bb3c3c8ddcf68ff734379`.
- M3 mode now assigns detector voices to stable physical string lanes and
  supports per-string calibration directly from the tuner: double-click one
  meter, tune and hold its open string, slide steadily to fret 24 and back,
  then hold open briefly to finish. Each 25-fret map stores cents bias and a
  six-harmonic fingerprint, persists in VST3 project state, and influences
  both tuner correction and physical-string assignment. M3 also pins the
  NYXL0980 lane gauges thick-to-thin as `.080, .060, .044, .032, .024, .016,
  .012, .009`; the fixed gauge/tuning prior breaks coarse fingering ties, and
  the measured harmonic maps perform the final same-note identity split. The
  split now reaches generated MIDI as well as tuner telemetry: in `Per Voice`
  mode each physical lane has a distinct stable note identity and deterministic
  base-channel-plus-lane routing, so two strings sounding the same MIDI pitch
  can start and release independently. `Single` mode retains one pitch event.
  The
  installed bundle now matches the validated release at SHA-256
  `5ec895e5800fe87c4ed2d1a362ff62a88ae33d2d895bb3c3c8ddcf68ff734379`.
  The immediately preceding installed bundle is retained at
  `~/.vst3/M3_Polyphonic_Audio_to_MIDI.vst3.backup-before-rate-buffer-fix-20260924`;
  the earlier pre-unison and pre-calibration backups remain available as well.
- The disposable system-audio profile is
  `build/m3-native-live-midi-system/reaper.ini`. It is bound only to the
  built-in `Generic_1` ALC257 codec through `plughw:Generic_1,0`, with REAPER
  configured for 96 kHz and 512 samples. Direct device checks confirmed
  96 kHz/512 stereo capture; built-in playback is physically 48 kHz/256 and is
  converted by ALSA `plughw` while the plug-in graph remains 96 kHz/512.
  The io24 (`R24`) was not opened.
- A real disposable REAPER 7.79 launch discovered the production VST3, created
  the armed `M3 Native 8-String Guitar to MIDI` track, opened the custom editor,
  and held only `/dev/snd/pcmC2D0{c,p}`. This verifies discovery, editor
  integration, and the selected normal-audio route. It does not by itself
  prove musical tracking from a physically played guitar; that still needs a
  player-generated input pass.
- The separate V4 evidence worktree is sealed through Q46 at commit
  `ba895a28c6676116dbca81d16a4d57f104e011dd`. Q46 unifies eight captured ELF
  nodes, ten ordered dependency declarations, and ten exact SONAME matches;
  no unmatched declarations remain. That lane is evidence for future isolated
  fixture/host closure, not a substitute for the working product checks above.

## Current native M3 polyphonic VST3 + tuner checkpoint

- Worktree: `.worktrees/m3-live-editor`, branch `feat/m3-live-editor`. Commit
  `4fa2c09` contains the native polyphonic detector, truthful tuner telemetry,
  and redesigned precision editor. A focused two-file follow-up remains
  uncommitted in `native/vst3/vst3_component.cpp` and
  `native/tests/test_vst3_processing.cpp`.
- The native VST3 now performs bounded polyphonic selection for up to eight
  voices instead of disabling detection when Max Polyphony is greater than
  one. It includes per-new-voice causal evidence, deterministic release/onset
  ordering, subharmonic rejection, and M3 string/fret feasibility with
  backfilling of feasible candidates.
- The audio thread publishes a fixed-capacity, lock-free tuner snapshot to the
  editor. The editor renders a read-only eight-card Voice Stack with note,
  signed cents when valid, confidence, per-row state, configured maximum, and
  explicit no-signal/unavailable states. It never sends parameter edits or
  presents a global in-tune verdict. The editor is now 1024x808 (maximum
  2048x1616), and VSTGUI's developer-only Open UI Editor button is disabled.
- Fresh native verification is green: Debug 151/151, Release 151/151 (including
  the 96 kHz max-eight deadline gate), ThreadSanitizer 150/150, and
  AddressSanitizer plus UndefinedBehaviorSanitizer 150/150. Leak scanning alone
  was disabled because LeakSanitizer cannot operate under this sandbox's ptrace
  boundary; GCC vptr checks are disabled only for the Steinberg COM-style ABI
  representation casts, with all other ASan/UBSan checks retained.
- The broader offline build/source contract is green: 343 Python tests,
  `tools/validate_source.py`, `tools/validate_native_source.py`, and
  `git diff --check`.
- The production bundle and project validation target are green at
  `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3`. Current binary
  SHA-256: `5988a72d5b7783e4e178874af93261dbff1e6dbd6810e05510777dfd4ba4d094`.
- A real headless VSTGUI render was inspected at 1024x808. The editor was then
  visually redesigned as a flat precision-instrument surface: stronger brand
  and status hierarchy, compact labeled mode switches, detailed dial scales,
  restrained section rails, and eight simultaneous vertical pitch lanes with
  meaningful cent rails and segmented confidence. Settling voices do not claim
  a cent estimate. The SDK's developer editor button was also removed. The
  final render was rechecked and temporary screenshot instrumentation removed.
- The official Steinberg validator now passes the production bundle. Evidence
  is retained in
  `build/test-results/vst3-validator/production/result.json` with timestamp
  `2026-09-11T13:45:40.049+00:00` and validator return code 0.
- A guarded disposable REAPER run exposed and fixed a real host-integration
  defect: REAPER may alternate VST3 `kRealtime` and `kPrefetch` process calls
  without another `setupProcessing`, as the VST3 contract permits. The old
  exact-mode comparison rejected those blocks before dry audio and detection.
  The focused repair now accepts realtime/prefetch interchangeably while still
  refusing every offline transition without a matching setup.
- The repaired release completed an exact live E2+B2 lifecycle in disposable
  REAPER: four MIDI events (note-on 40, note-on 47, note-off 40, note-off 47),
  one on/off pair per note, and no capture overflow. Evidence is retained at
  `build/reaper-test/test-results/m3-polyphonic-host-smoke.tsv`. The normal
  REAPER profile remained byte-identical at SHA-256
  `0c9a808df5361758c7f6656ed052332cfe16004b4a9f2d476d9c319829ae0a41`.
- Actual hosted editor evidence is retained at
  `build/evidence/native-m3-host-smoke-20260911.png`. A dynamic dyad screenshot
  is optional presentation evidence only; exact host telemetry and MIDI
  lifecycle are already proven. The next substantive product gate is physical
  guitar/96 kHz audio-interface validation, which must not be inferred from the
  synthetic dyad result.

## V4 scan-isolation design reviewed — Task 0A sealed non-admissible

- Commit `8f0d1db` (`docs: define V4 scan isolation gate`) records the
  independently reviewed V4 one-row scan-isolation design, static runtime
  inventory, and TDD implementation plan. It preserves every sealed v1/v2/v3
  artifact and creates no new execution authority.
- The design places a fresh private VST3 root inside a Bubblewrap namespace,
  keeps control receipts and uncertainty markers solely in an outer
  retained-dirfd controller, and requires scope confirmation, zero REAPER PID
  census, bounded attester PRE/POST evidence, descriptor-pinned regular inputs,
  and anchored nonregular inputs before any future scanner can run.
- Commit `fac3b5e` (`feat: add V4 non-admissible protocol skeleton`) completes
  Task 0A as a deliberately non-admissible source component. It validates only
  an in-memory frame envelope/base configuration and exposes a mocked-testable
  process barrier. A pre-import AST gate proves it has no receipt writer, ACK
  reader, descriptor control, measured collector, runner, admission entrypoint,
  process-launch path, or import-time side effect. Four focused tests pass.
- Commit `940f64d` (`docs: harden V4 runtime manifest gate`) records the
  independently reviewed Task 0B block: a closure-construction method and
  explicit offline Task 0B1 authority precede source authoring; fixture
  and host manifests are separate; and any future descriptor-pinned manifest
  must refuse over-copy, FD, `RLIMIT_NOFILE`, or memory/tmpfs budgets.
- The original Task 0B0 method is
  `docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`.
  Its original review and Task 0B1 source-component/runtime-root amendment are
  independently CLEAN. The user has granted the bounded Task 0B1 author-only
  scope. The amendment records that Task 0B1 may author, but not invoke, four
  sources: the static closure
  constructor plus the receipt-schema, measured-collector, and child-adapter
  runtime modules, along with their catalog schemas and synthetic static-data
  fixtures. They are analysis roots only; no Task 0B1 file is a session or
  manifest runtime root. A separate explicit offline Task 0B2 authorization is required to
  test or invoke the constructor against sealed data; it remains data-only and
  excludes target import/execution/loading, namespace or fixture creation,
  Bubblewrap/systemd/REAPER command formation, GUI/X11/audio/network access,
  and all host actions.
- The static source closure is recorded only as an unresolved Task 0B input:
  it includes Python `ctypes`, `hashlib`, `json`, `struct`, and their extension
  / ELF candidates. It is neither fixture-complete nor compatibility-complete.
  Task 0B1 author-only source/catalog work is sealed: the four bounded source
  modules, two schema files, two synthetic fixtures, and their exact hash
  seals passed the seven-check AST/JSON-byte gate. Two independent static
  reviews are CLEAN. No Task 0B1 module was imported, compiled, or invoked,
  and no host process was launched. Any later Task 0B2 invocation must return
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)` until a separately
  reviewed session runtime root exists. Task 0B1 never authorizes testing or
  invoking the constructor; that later step needs its own Task 0B2 authority.
- Under the recorded user `Proceed` authorization, and only after the
  demonstrated sealed-synthetic-data RED, Task 0B2 applied the one private
  normalization correction in `tools/reaper_v4_closure_constructor.py` needed
  for its own constructed synthetic record to validate. It resealed the
  Task 0B1 static constructor source hash, reran the static contract and
  Task 0B2 tests, and received independent review. All other Task 0B1 source
  expansion or correction, target import/execution/loading, fixture or
  namespace action, and host action remained forbidden.
- Task 0B2 is now sealed as an offline constructor-only result. Its first
  synthetic-vector invocation produced the expected RED: private nested
  immutable snapshots reached `ClosureRecord` as non-caller built-in
  containers. The sole source correction normalizes that private record before
  its existing deep freeze; it is sealed at constructor SHA-256
  `2f8b1f02f5a730c70e38b6ebe06a99ec8abbd3c70a05851f66d6be6c5e2a97f7`.
  `ionice -c 3 nice -n 10 python3 -B -m unittest
  tests.test_reaper_v4_task0b2_constructor -v` passed one test, and the
  seven-check Task 0B1 static contract also passed. Independent review is
  CLEAN. The sole output is
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)`, canonical
  digest `0fdb65aa2467554f85fb21e2e570850921cb1615bfe56ebb4b1a0b5d5fb185bf`.
  It uses only sealed synthetic placeholder identities; it does not bind a
  real Task 0A/Task 0B1 graph, produce a fixture manifest, or authorize a host
  action.
- Task 0B3 is now independently reviewed as a design-only session-owner
  checkpoint at
  `docs/superpowers/specs/2026-09-01-v4-task0b3-session-owner-design.md`.
  It assigns exactly one later runtime root for the PRE/ACK/child/POST state
  machine, binds the complete session policy and selected direct input hashes
  through immutable Task 0A receipt identity, keeps durable control artifacts
  with the outer controller, and requires provenance-backed/certificate-bound
  PRE assertions, bounded raw transport, and PRE-only failure for uncertainty.
  It also names separate source, receipt, measurement, runner, state-machine,
  graph-construction, closure, fixture, and host gates. This is not source,
  component, fixture, namespace, Bubblewrap/systemd/REAPER, or host authority.
- Task 0B3a is sealed as a non-admissible session-root source checkpoint.
  Commits `81df235` and `91c86c5` establish the reviewed fail-closed contract;
  `a1808cb` reduces the preliminary pseudo-runtime to an immediate-fail
  skeleton; and `d257b5d` hardens its pre-import AST/hash guard. The sealed
  source SHA-256 is
  `f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60`.
  `ionice -c 3 nice -n 10 python3 -B -m unittest
  tests.test_reaper_v4_task0b3a_static_contract -v` passed one static-only
  test, and the final independent source re-review is CLEAN. That historical
  guard is retired now that the successor B4b static contract pins the
  executable implementation. Neither public
  function can progress past its immediate error; no target or dependency was
  imported, compiled, or invoked, and no fixture, namespace, Bubblewrap,
  systemd, REAPER, X11, audio, or host action occurred. It preserves the
  future single-root identity but remains
  `BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)` for its original
  historical scope. The subsequent B4b implementation replaces that skeleton
  under its own verified static contract.
- Task 0B3b is sealed as a pure in-memory receipt gate. Its 12 adversarial
  tests exercise the real receipt/protocol validators against the synthetic
  PRE/ACK/POST vector: valid immutable snapshots; exact ACK; independently
  valid identity and shared-attestation mismatches; required containment facts;
  row, clock, PID, and return-code boundaries; malformed text; cycles; and
  container subclasses. The sealed seven-check Task 0B1 source contract also
  remains green, and independent review is CLEAN. No production source changed
  and no session, raw stream, namespace, Bubblewrap, systemd, REAPER, X11,
  audio, or host action occurred. This is not evidence of ACK EOF, raw frame
  order, or session behavior. The next safe gate is separately authorized Task
  0B3c measurement validation; full session behavior remains Task 0B4.
- Task 0B3c is sealed as a temporary-directory/descriptor-only measurement
  gate. Its synthetic-only RED exposed collector validation holes; the narrow
  production corrective amendment changed only `tools/reaper_v4_measurements.py` to take
  an exact-plan local snapshot before validation, reject non-canonical strings,
  duplicates, and unhashable values before `os.open`, normalize root
  `OverflowError` and close failures to `MeasurementError`, and require
  `MEASUREMENT_KEYS == ("mode", "size")`. The sealed collector source SHA-256
  is `27fa32e618a1a1461f3ec50820e7ad8717aa0747f1a6c7e475badefa0b4f7a22`.
  The combined static contract and B3c suite passed 20 tests, and independent
  review is CLEAN. This proves neither ACK EOF, raw-frame order, nor session
  behavior; it created no session or namespace and performed no Bubblewrap,
  systemd, REAPER, X11, audio, network, or host action. The next safe gate is
  separately authorized Task 0B3d for the child adapter only; full session
  behavior remains Task 0B4.
- Task 0B3d is sealed as a direct-child adapter gate. Its mock REDs exposed
  post-bind cleanup, cleanup-slot accounting, and interruption-order defects;
  the narrow reviewed correction keeps the single launch inside its
  bound-process recovery boundary, reserves at most two cleanup slots before
  `kill()`, keeps a bounded wait after each entered-slot kill error, and
  preserves the first non-`Exception` interruption, and escalates a cleanup
  non-`Exception` over an ordinary original adapter error. The sealed runner
  SHA-256 is `a9cecba05537a349355fc204d2a8343a51caf6fabb7ab5d184ef341270f5a946`.
  Seven static checks plus twelve B3d tests passed (19 total), including three
  isolated temporary-directory sentinel invocations. Each child was direct and
  non-forking with `-I -S -B -c`; no session, raw stream,
  namespace, Bubblewrap, systemd, REAPER, X11, audio, network, host scan, or
  descendant-containment claim occurred. Pre-bind and unconfirmed cleanup
  paths remain outer-session/scope uncertainty. Task 0B4 session
  implementation requires separate scoped authority.
- Task 0B4a is sealed as a documentation plus intentional-RED checkpoint.
  Pre-implementation review corrected an unsafe combined gate before any
  session code changed: frozen Task 0B1 receipt snapshots cannot be passed
  directly to the sealed Task 0A encoder, and a real namespace controlled
  fixture needs a parent scope/harness the session root does not own. The
  design now splits the work into Task 0B4a, Task 0B4b-pure (bounded
  in-memory compatibility helpers), Task 0B4b-state-contract, separate later
  admission/evidence/bootstrap-transport/state gates, Task 0B4c-design, and
  Task 0B4c-execution (a later separately authorized outer-harness controlled
  fixture). The raw-byte
  skeleton pin is
  `f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60`;
  its source-only test reports one normal pass and two intentionally retained
  expected failures after their RED was recorded. Two independent reviews are
  CLEAN.
- Task 0B4b-pure is sealed as the narrow compatibility-helper increment.
  It retired the B4a expected-failure guard, added an exact pre-import AST
  contract and five in-memory behavior tests, and changed only
  `tools/reaper_v4_session.py` as production source. Its source SHA-256 is
  `9aa503dc77f37ace46202a35797925e784e9e302b866d3c81d880897e7a86c99`
  (the historical B4b-pure source identity before the later admission gate).
  The immutable Task 0B1 static gate, B4b-pure pre-import contract, and
  helper suite passed 13 checks; two independent reviews are CLEAN. The
  session still has immediate-failure public entrypoints and no raw transport,
  configuration-path/descriptor I/O, barrier, measurement, child, fixture,
  namespace, Bubblewrap, systemd, REAPER, X11, audio, network, or host action.
  It proves no session admission, ACK order, receipt emission, or host
  compatibility. Any state-machine source or execution now needs a fresh named
  authority and reviewed contract; Task 0B4c remains a separate outer-harness
  gate.
- Task 0B4b-admission-pure is sealed as the bounded in-memory SessionConfig
  relation gate. It replaces the B4b-pure source contract while preserving its
  helper regressions, removes the inert child-runner/measurement imports, and
  adds a validator-owned snapshot boundary plus closed Task 0B3 §3 relation
  checks. The sealed source SHA-256 is
  `5bb71ab032b13b59170dd8034528b7b0e990751fd0d0b5b59da6e711a9ce1c11`.
  Eighteen checks passed: the immutable Task 0B1 static gate, the new
  pre-import admission source contract, five B4b-pure regressions, and five
  synthetic admission tests. Three independent reviews are CLEAN after
  test-first repairs for forged-object normalization, lexical environment/X11
  bindings, screen syntax, scan-root mount closure, static capability edges,
  and bounded snapshot walkers. This gate did not open a path, establish a
  barrier, read/write a frame, launch a child, create a fixture/namespace, or
  run REAPER, audio, X11, network, or host work. Public session entrypoints
  remain immediate-failure stubs. Task 0B4b-bootstrap-transport is next.
- Task 0B4b-evidence is sealed as the bounded supplied-observation and
  descriptor-retention gate. It replaced the admission static contract while
  preserving B4b-pure/admission regressions, and added cwd/environment,
  measurement, scan/private-home, X11, FD/mount, certificate, retained-recheck,
  and one-shot-release helpers. Its registry binds every successful baseline to
  its original descriptor tuple, refusing forged or mutated values before they
  can close a descriptor. The sealed source SHA-256 is
  `6049ec3096cf9a2fc50678884180fe4e0ef6072032418931f0d48afa14f83a1f`.
  Thirty checks passed across the immutable Task 0B1 static, evidence static,
  B4b-pure, admission, and temporary-resource evidence suites; three
  independent reviews are CLEAN and `git diff --check` passes. Only temporary
  controlled resources/supplied descriptors were used. No fixed `/run` path,
  raw stream, barrier, child, namespace, launcher, REAPER, audio, network, or
  host scan ran; public entrypoints remain fail closed. The next gate is
  Task 0B4b-bootstrap-transport.
- Task 0B4b-bootstrap-transport is locally implemented and verified, but is
  not yet independently reviewed or sealed. Its implementation checkpoint is
  commit `2ce8abc`; it adds only private fixed-literal
  sidecar/config reading and fd-0/fd-1/fd-2 helpers; the current source
  SHA-256 is
  `5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.
  Its static RED recorded the absent imports/helpers, its five behavior REDs
  recorded the fail-closed stubs, and the preserved suite now passes 46
  checks. The added `POLLHUP` regression accepts it only as second-read EOF
  readiness; the read itself must still prove EOF. The raw fd-0/fd-1 waiter
  now sets `O_NONBLOCK` before every bounded poll and refuses a flags failure
  before any raw operation. The tests use syscall/poll doubles and canonical
  synthetic config bytes only. No real `/run`, child,
  state machine, namespace, REAPER, audio,
  or host action has occurred under this checkpoint.
- Task 0B4b-state is now locally implemented and verified as a mock-only
  composition checkpoint in `2ce8abc`, but remains unsealed pending independent review.
  It replaces the predecessor static contract, imports only the sealed child
  adapter, and gives the public root its literal-path loader plus one local
  PRE -> ACK+EOF -> child -> POST transition. At that checkpoint, the runtime
  observation and payload-assembly edges were exact fail-closed stubs, so no
  runtime invocation could self-assert receipt facts. Its checkpoint source
  SHA-256 is
  `5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.
  The preserved suite had 46 checks: mock-only success, failure, outcome,
  post-finalization, interruption, and one-shot terminal-release vectors prove local ordering only. No
  real `/run` read, barrier, measurement, child, fixture, namespace, REAPER,
  audio, X11, network, or host action occurred.
- Task 0B4b-payload-assembly is locally verified, pending independent source
  review. It replaces only the PRE/POST payload stubs with
  `_shared_receipt_attestation`, which re-admits the supplied configuration,
  verifies a registry-owned controlled evidence baseline against its retained
  environment, measurement, scan, private-home, X11, FD/mount, and certificate
  records, and returns fresh ordinary receipt values. PRE and POST now validate
  with the sealed Task 0B1 receipt grammar; POST adds only
  `scan_root_unchanged` and the existing finalizer retains
  `validate_post -> validate_exchange -> encode` ordering. The current source
  SHA-256 is
  `41f8d1fbaebb69c4aad2de50c16ff2fd48ad68b1d55e4fadf1e428889893d937`.
  The test-first PRE vector captured the original stub refusal, then the full
  V4 source-only/controlled-descriptor suite passed 51 checks, including five
  payload vectors. No namespace, real `/run` access, barrier, child process,
  REAPER, audio, X11 client traffic, network, fixture, or host scan ran.
- Task 0B4b-runtime-observation is locally verified, pending source review.
  It replaces the three runtime-evidence stubs with a bounded five-descriptor
  acquisition path, a 64-FD census, a bounded mountinfo projection, retained
  evidence recheck, and one-shot release delegation. The current session
  source SHA-256 is
  6a2bbdfee29c26253ffb4a8f05c62feeab207ea21942aa40368a9ac9e8fcdc1c.
  The complete controlled V4 suite passed 57 checks, including six
  temporary-resource/syscall-double vectors for descriptor handoff, census
  closure, mount projection, partial-open cleanup, invalid-admission
  non-observation, and mountinfo EOF closure. No real /run read, namespace,
  Bubblewrap, child process, REAPER, audio, X11 client traffic, network, or
  host scan ran. A reviewed closure/fixture-manifest and a later controlled
  fixture remain required before any actual session execution.
- Task 0B5 source closure and parent-harness implementation is locally
  verified and committed as `feat: pin V4 observed runtime catalog`.
  `tools/reaper_v4_session_entry.py` establishes the one source root;
  `tools/reaper_v4_fixture_manifest.py` produces a deterministic seven-source,
  eight-edge graph and rejects bootstrap-config self-reference; and
  `tools/reaper_v4_fixture_harness.py` performs the parent-side
  PRE -> ACK+EOF -> POST exchange against an isolated non-REAPER Python
  sentinel. The full V4 discovery suite passed 113 checks. The persisted
  `tests/fixtures/reaper_v4_closure/observed-runtime-catalog.json` pins 77
  observed interpreter/extension/ELF regular inputs (9,499,630 bytes) under
  canonical catalog SHA-256
  `446a7f87e156f4cfa4cf58582261fde22a6557cf06604da6a02c6d393450c76e`.
  Rechecking that catalog plus the seven source files builds only an 84-entry,
  9,647,488-byte `DECLARED_RUNTIME_MANIFEST` in memory; it remains explicitly
  `UNRESOLVED` for builtin/frozen modules, conditional imports, interpreter
  startup, native effects, and virtual resources. The local Bubblewrap probe
  failed before executing a child because this Codex execution environment
  refuses new namespaces even though the host user-namespace sysctls are
  enabled; `strace` is also denied ptrace. No
  fallback, actual fixture, session invocation, REAPER, audio, X11-client,
  network, or host scan was attempted. Resume with the individually pinned
  runtime catalog and complete fixture-runtime-manifest, then use a host that
  permits the reviewed Bubblewrap scope for actual fixture execution.
- Task 0B4b-state-contract is sealed as a documentation-only prerequisite
  checkpoint
  under the user's fresh `Proceed`. It resolves the name boundary that keeps
  Task 0B4c for the later outer-harness fixture, and records why B4b-pure's
  non-admitting parser, descriptor-only collector, and direct POST encoder
  cannot be used as a state-machine admission path. It reserves four future
  ordered the four source gates: `0B4b-admission-pure` for complete in-memory
  SessionConfig relation validation, `0B4b-evidence` for bounded private
  provenance/baseline helper implementation, `0B4b-bootstrap-transport` for
  fixed-loader/raw-helper implementation against doubles, and `0B4b-state` for
  mock-only local composition. Admission and evidence are sealed; bootstrap
  transport and the mock-only state source are now locally verified but pending
  independent review. This documentation checkpoint itself changed no source or
  test and performs no target import/execution, configuration/path/descriptor
  I/O, raw transport, barrier, measurement, child, fixture, namespace,
  Bubblewrap, systemd, REAPER, X11, audio, network, or host action. A
  source-free `0B4c-design` must define the bounded fixture before Task 0B5,
  successor closure review, and bounded fixture-runtime-manifest review;
  `0B4c-execution` stays later and must name one independently reviewed
  non-REAPER scope mechanism rather than silently choosing a launcher. Three
  independent documentation reviews are CLEAN and `git diff --check` passes;
  no source/test/runtime authority was consumed by this checkpoint.
- A source-free **draft** of the Task 0B4c controlled-fixture definition now
  lives at
  `docs/superpowers/specs/2026-09-05-v4-task0b4c-controlled-fixture-design.md`.
  It fixes the intended non-REAPER data plane, stream topology, parent
  ownership, and resource bounds without advancing B4c-design: bootstrap/state
  review, runtime evidence/payload source review, Task 0B5 closure, and
  fixture-manifest review remain required before any fixture execution.
- The future manifests are deliberately distinct. A `fixture-runtime-manifest`
  can permit only a bounded non-REAPER fixture; a
  `reaper-host-runtime-manifest` must reference it and resolve every REAPER,
  libSwell, GUI, X11, Python, and dynamic-load input before compatibility or a
  host request is possible. Both require copy-byte, FD, `RLIMIT_NOFILE`, and
  memory/tmpfs preflight refusal budgets.
- Therefore no V4 REAPER/Bubblewrap/systemd command may be formed or executed.
  Tasks 0B3a, 0B3b, 0B3c, and 0B3d add only sealed non-admissible, receipt,
  synthetic descriptor, and direct-child-adapter evidence respectively. Task
  0B4a adds the sealed source-contract checkpoint, and Task 0B4b-pure adds
  only bounded in-memory compatibility helpers with fail-closed public
  entrypoints. Task 0B4b-admission-pure adds only locally snapshotted,
  self-consistent configuration admission and still exposes no runnable session
  path. Task 0B4b-evidence adds only temporary/supplied-observation and
  descriptor-retention helper behavior, not executable session admission.
  Task 0B4b-state-contract adds documentation-only prerequisite ordering, not
  an executable state machine. Task 0B1 remains preservation-only. Its static
  test may be rerun without importing target modules; bootstrap-transport,
  state-machine, fixture, namespace, or external action follows in its own
  scoped implementation gate.
- Any later V4 host execution needs the compatibility-complete
  `reaper-host-runtime-manifest`,
  implementation and independent review of the isolation controls, fresh roots
  and preflight, and new explicit user authority. It cannot consume prior v2 or
  v3 authority or unblock Task 16.

## Current post-v3 offline correction and containment boundary

- Read-only forensic work established the direct cause of the sealed v3
  timeout: its staged capability ReaScript allowed only the old
  `/build/reaper-test/test-results` suffix, while v3 used
  `/build/reaper-test-observer-diagnostic/test-results`. Its assertion ran
  before any phase/telemetry write or disposable-instance close, which explains
  the empty evidence and fixed-cap `124` without diagnosing the project,
  observer, production adapter, or MIDI path.
- The smallest TDD correction now accepts only the two fixed disposable
  profile suffixes and still rejects a live-profile-shaped path and a near
  miss. The Lua regression proves both allowed profiles reach setup. It changes
  only future staging source; the sealed v3 copy, evidence, marker, and no-retry
  boundary remain untouched.
- A separate read-only review found that REAPER appended `~/.vst3` to the
  sealed profile's `vstpath` and cached an external `ATONE.vst3` bundle. This
  is a scan-containment breach, not a demonstrated timeout cause. Preserve the
  profile as evidence; do not mask or rewrite it. A future host design must add
  pre-launch containment plus post-exit profile/cache validation before any new
  host authority is sought.
- The current safe work is offline fixture-driven scan-containment validation
  and documentation only. Do not retry v1/v2/v3, launch a tail, start Task 16,
  alter the product adapter, or open REAPER without a fresh, separately
  authorized host gate.

## Task 15 v3 one-shot observer diagnostic sealed infrastructure-invalid — Task 16 blocked

- The user's `continue` freshly authorized exactly the presented twenty-row v2
  Gate C5 matrix once: 44.1, 48, 88.2, and 96 kHz at blocks 32, 64, 128, 256,
  and 512, serially in disposable background REAPER instances on workspace 5,
  with permanent stop on the first non-pass and no retry.
- All non-launching gates passed before the host run: guarded native debug and
  sanitizer tests, the exact release probe build, official probe validation,
  the focused host/recovery suite, all 170 repository tests, the native source
  validator, and an exact twenty-row dry plan. Immediately before launch,
  about 25.7 GiB was available, temperature was 48 C, and memory-full and
  I/O-full PSI were zero; workspace 1 remained active and no REAPER process or
  window existed.
- The first runner invocation launched no REAPER process. It conservatively
  recovered stale v1 staging into
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T091010Z-recovered`.
  Its marker has the legacy v1 input hashes and no v2 namespace; each of its
  five staged result files is byte-identical to the corresponding sealed v1
  file. It has no `metadata.json` or `pressure.json` because staging had not
  reached sealing. It is not a v2 attempt and remains preserved.
- TDD commit `a551021` (`fix: namespace VST3 recovery evidence`) adds the v2
  namespace to new attempt markers and ignores only a well-formed recovered
  marker proven to be foreign legacy evidence. Missing, malformed, non-object,
  symlinked, current-v2, or ordinary invalid evidence still blocks forever.
  This offline runner fix consumed none of the twenty launch authority and
  changed no production detector, adapter, probe, timeout, or pressure guard.
- The actual v2 execution launched only 44.1 kHz/block 32. REAPER exited
  normally with guard return code zero; `phase.log` ends in `suite-fail`; and
  the runner classified the row `fail` because the sole assertion label is
  `observer-magic`. The immutable row is
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T092345Z`,
  with seven-file manifest digest
  `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The observer failed closed before parameter, state, audio, MIDI, lifecycle,
  or reporter assertions. The empty event/state bodies and `-1` diagnostics
  are therefore deliberate non-evidence. This result proves no production
  detector or native-adapter defect and authorizes no such edit.
- The row began/ended at 26269.34/26201.62 MiB available, load 0.48/0.84,
  48/50 C, and zero memory-full/I/O-full PSI. Cleanup left zero REAPER
  processes/windows and left workspace 1 active. There was no crash, timeout, or
  meaningful system-pressure spike.
- Per the gate, nineteen rows were not launched and no retry occurred. The v1
  sealed manifest remains unchanged at
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`.
  Check-only adjudication now rejects the sealed v2 invalid row and the missing
  tail, as required.
- A subsequent read-only observer diagnosis made no REAPER launch, retry, or
  source/configuration edit. The staged cache proves that REAPER discovered and
  inserted the exact capability-source JSFX. The ReaScript and all three JSFX
  observers use the same `m3_poly_midi_tests_v1` segment; their indices are
  valid; and no other repository effect writes cells 2205-2209. No static
  naming, address-range, insertion-call, or hexadecimal-literal defect is
  supported by the sources or REAPER's documented APIs.
- The v2 row records only `observer-magic`, not the raw magic, generation,
  ready, heartbeat, acknowledgement, attachment state, source-FX parameter
  state, or JSFX compile state. It therefore proves only that the first live
  observer poll's magic/generation/ready/heartbeat tuple was not all zero while
  magic differed from `0x4D335633`; the raw magic itself could have been zero
  or another value. The row cannot distinguish the earlier cell-address
  pattern from a boot-order, attachment, track-scheduling, compilation, or
  other pre-product host boundary.
- The v1 row proves that the same source later processed real 44.1 kHz,
  32-sample blocks while other observer values followed the exact cell-address
  pattern. The established synthetic harness instead places a short MIDI item
  on its track and waits for a coherent ready/heartbeat tuple until its
  deadline. Those differences make a startup race, attachment transition, or
  empty-track scheduling boundary plausible, but none is proven by the
  immutable v2 evidence.
- The user approved the diagnostic-only non-launching amendment. Commit
  `176923e` (`test: preserve VST3 observer diagnostics`) now records all nine
  raw observer fields after clear, after FX creation, at the first observer
  poll, and at the terminal verdict. It also records both same-name gmem attach
  returns and the source FX's exact name, enabled/offline state, parameter
  count, and rate/block sliders after setup and at the terminal verdict.
- The amendment changes no production source or adapter, dependency, source
  scheduling, timeout, boot verdict, guard, runner, or evidence namespace. Its
  focused Lua tests cover zero, exact address-value, wrong-magic, and
  valid-ready snapshots plus the complete failed-boot diagnostic record.
  Fresh low-priority verification passes 172 repository tests and both source
  validators. The v1/v2 evidence digests remain byte-identical, no REAPER
  process was launched or left running, and the final passive snapshot was
  26079.05 MiB available, load 1.35, 44 C, and zero full memory/I/O pressure.
- The user clarified that 96 kHz with host blocks 256-512 is the normal use
  case. Any later capability, latency, and correctness report must call out
  96 kHz/256 and 96 kHz/512 as the primary real-world rows while retaining the
  mandatory full 20-row matrix and the independent 96 kHz false-note gate.
- Task 16 and Tasks 17-24 remain blocked. The user has now authorized exactly
  one fresh diagnostic execution. Commit `0a216d4` (`feat: isolate one-shot
  VST3 observer diagnostic`) introduces a fixed `--observer-diagnostic-once`
  path for only 44.1 kHz/block 32 under the new
  `native-vst3-probe-v3-observer-diagnostic` namespace. It cannot invoke the
  v2 matrix, check mode, or tail and restores all v2 paths after use.
- The v3 staging root, project root, and evidence root must each be absent and
  nonsymlinked before any write. Any pre-existing, malformed, pending, or
  interrupted v3 artifact is a permanent refusal; it is never recovered,
  overwritten, adopted, or retried. This preserves the old v2 staging residual
  and both immutable v1/v2 rows exactly.
- The guarded launcher allows the v3 profile only with the exact build-local
  VST3, paired v3 completion sentinel, GUI workspace 5, 45-second limit, and
  fixed project/script arguments. It rejects CLAP/plain REAPER use, aliases,
  cross-paired paths, altered workspace/timeout, and any other arguments.
- Offline verification after the boundary amendment passes all 178 repository
  tests plus both source validators; `git diff --check` is clean. No REAPER
  launch has occurred from v3 and all three v3 roots are absent at this
  checkpoint. The next action is the single guarded row, after a fresh host and
  workspace preflight; stop immediately on any guard refusal or non-pass.
- The authorized v3 row then ran once at 44.1 kHz/block 32. The guard returned
  `124` at its fixed 45-second cap before any `phase.log`, `capability.tsv`,
  `events.tsv`, `state.tsv`, or `probe-vst3.tsv` existed. The runner sealed
  `build/test-results/native-vst3-probe-v3-observer-diagnostic/batches/44100-32.invalid-20260831T113425Z`
  as `infrastructure-invalid`; its two-file metadata/pressure manifest digest
  is `4c6fe0dde5c96cacd8d3f5cd7f1f6fe77a7b66fbde40de78067b6c0166ed921a`.
- The isolated staging marker remains in place by design and makes v3
  permanently non-runnable. REAPER's disposable VST cache did discover the
  exact probe bundle, but its profile records a `faultyproject` and no script
  telemetry. This is an incomplete host-startup boundary, not evidence of an
  observer, production detector, adapter, or MIDI defect.
- Pressure stayed safe: available memory was 25773.08/25772.81 MiB before/after,
  load was 0.71/1.59, temperature 46/47 C, and both full-pressure PSI values
  were zero. Post-run checks found zero REAPER processes/windows and workspace
  1 active. The immutable v1/v2 digests remain exactly
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`
  and `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The one-row authorization is consumed. Do not delete, alter, recover, retry,
  or relaunch v3; do not launch the v2 matrix or tail. Task 16 remains blocked.
  Any later corrective work begins with read-only/offline diagnosis and needs a
  new, separately authorized execution design before another host launch.

- On 2026-08-29, immediately after the sealed Task 2 checkpoint stopped at
  Gate D2, the user explicitly said `Authorize all`. This authorizes every
  remaining named work in the approved 24-task native VST3 plan, including its
  bounded network, build, disposable-host, benchmark, clean-DI, and final
  installation phases. The plan's later Task 15 Gate C5 is an explicit
  exception: its text requires a fresh authorization for exactly twenty
  guarded disposable REAPER launches and says prior general authorization does
  not open that gate.
- This authority does not weaken any pressure guard, stop-on-first-failure
  rule, immutable-evidence boundary, or acceptance threshold. It does not add
  unrelated package changes, REAPER MCP installation, live-project mutation,
  CLAP retries, or work outside the approved plan. Gate D8 still requires
  suitable input material before it can execute, and I9 remains conditional on
  every prerequisite release gate being green.
- Fresh post-authorization baseline verification passed 44 native tests and
  125 Python tests at the unchanged Task 2 checkpoint. No REAPER process was
  present; the tests ran serially at low priority after an unrelated io24 test
  process completed and the ACPI temperature fell.
- Task 3 is sealed at commit `9851237` (`build: vendor pinned VST3 SDK
  3.8.1`). The official root tag and all four root gitlinks/submodule HEADs
  match the approved revisions exactly. The retained 24 MiB source-only tree
  contains 1,003 manifest-covered files under only `base`, `cmake`,
  `pluginterfaces`, and `public.sdk`, with no `.git`, root `doc`, `tutorials`,
  or `vstgui4` content.
- `third_party/vst3sdk/SHA256SUMS` has SHA-256
  `4d5b8c240b842a85b39b97ccc8b69e3bb7ed6b000709e62c07a3e41c855063f0`;
  all 1,003 entries pass offline verification. The SDK contract suite passes
  11/11 and the native source validator passes. `.gitattributes` preserves the
  byte-exact upstream whitespace and intentional short Setext heading while
  keeping project-authored files under the normal Git whitespace check.
- Retrieval ran once into ignored `build/vendor/vst3sdk-src` under low CPU and
  idle I/O priority. No automatic retry or alternate SDK was used. The final
  Task 3 snapshot had about 32 GiB available memory, zero swap/full pressure,
  45 C temperature, no REAPER process, no VST3 `.cpp`, and no bundle or
  persistent plug-in copy.
- Task 4 is sealed at commit `282ba18` (`build: add guarded VST3 CMake
  foundation`). The authoritative source graph is now explicit CMake 3.25+
  with C++17, strict warnings, disabled exceptions/RTTI, hidden symbols,
  RELRO/NOW/no-undefined, reproducible prefix/build-ID flags, VSTGUI and SDK
  examples disabled, and no download or source-glob construct. The official
  validator and module-info utility are excluded from the default build.
- `native/Makefile` is now only a serial wrapper. Every non-clean build/test
  command passes through `tools/run_guarded_native_build.py`, which refuses at
  the approved memory/load/temperature/PSI thresholds; rejects package,
  network, recursive, parallel, and repository-escape commands; and applies a
  one-CPU quota, 1536/2048 MiB memory high/max, 256 MiB swap max, 128-task
  limit, nice 15, idle I/O priority, wall timeout, and atomic before/after JSON.
- Fresh committed-state verification passes the same 44 native tests in both
  debug and ASan/UBSan builds, the focused VST3/guard suite 20/20, all 133
  Python tests, the native source validator, and Git whitespace checks. The
  excluded `m3_clap_history` CMake target also links as a build-local x86-64
  ELF with the expected `clap_entry`; no `.vst3` bundle exists. The final guard
  snapshot recorded 32398 MiB available, load 0.87, 38 C, and zero memory-full
  and I/O-full PSI.
- Task 5 is sealed at commit `c85d9ab` (`refactor: extract format-neutral
  parameter contract`). One host-free constexpr table now owns all sixteen
  IDs, ranges, defaults, increments, update classes, persistence/list/read-only
  metadata, and exact VST3 step counts. It also owns finite canonicalization,
  plain/normalized conversion, config application, and bounded text conversion.
- CLAP flag/type mapping is isolated in `clap_parameter_bridge`; the shared
  header/source contain no CLAP include and the compiled neutral object has no
  CLAP or Steinberg symbol. The exact state image remains compatible. Debug and
  ASan/UBSan runs each pass 48 tests, all 133 Python tests pass, and the final
  guard snapshot recorded 31996 MiB available, load 1.65, 57 C, and zero
  memory-full and I/O-full PSI.
- Task 6 is sealed at commit `42859f7` (`refactor: separate state image from
  host streams`). The exact 184-byte image, explicit little-endian encoding,
  IEEE CRC-32, validation, and atomic decode now live in the host-free
  `m3/state_image` module. The default image SHA-256 is
  `f29e4ef09aaf4a5bfd4719efbe96d4370a31da4be404510329e2c27fee21a475`.
- CLAP partial stream progress and failure handling now live only in
  `clap_state_stream`; neutral roots contain no `clap_istream`,
  `clap_ostream`, or `IBStream` reference. Every truncation plus trailing,
  schema, CRC, ordered-ID, duplicate/missing/unknown-ID, non-finite,
  canonicalization, and atomic-publication case is covered. Debug and
  ASan/UBSan runs each pass 51 tests, all 133 Python tests and the source
  validator pass, and the final guard snapshot recorded 32091 MiB available,
  load 1.79, 63 C, and zero memory-full and I/O-full PSI.
- Task 7 is sealed at commit `5c77caf` (`refactor: extract generated-note
  delivery ledger`). The host-free ledger owns activation-sized transition
  storage, exact `ceil(max_frames/64)*16+8` capacity, off-before-on ordering,
  fixed active/pending pitch bitsets, exhaustive individual note-off cleanup,
  sink rejection inhibition, and explicit quiet-call recovery.
- The historical `MidiPipeline` now delegates generated-note state and output
  failure decisions to that ledger while retaining CLAP raw-event merge and
  CC123/CC120 cleanup locally. Its existing passthrough, every-push-failure,
  Panic/reset, dry-audio, and no-heap tests remain green. Debug and ASan/UBSan
  runs each pass 59 tests; all 133 Python tests, the source validator, and the
  excluded historical CLAP target pass. Neutral source and the compiled ledger
  object contain no CLAP or Steinberg dependency. The final snapshots recorded
  about 31692 MiB available, load 2.02, 68 C, and zero full memory/I/O PSI.
- Task 8 is sealed at commit `d757877` (`feat: add minimal VST3 lifecycle and
  bus adapter`). The build-local probe now exposes exactly one
  non-distributable combined `SingleComponentEffect` class under the locked
  probe identity, with one default-active stereo input/output, no event input,
  one default-active sixteen-channel event output, no editor, and zero declared
  latency or tail.
- The component accepts only paired stereo layouts, finite positive host rates,
  blocks through 16384 samples, and float32/float64 processing. Its in-place and
  out-of-place dry pass/mute paths are bit-exact for finite input; NaN/Inf and
  null/shared/unsupported layouts fail closed while zeroing safely addressable
  output. Repeated processing, invalid-layout handling, and processing-state
  transitions perform no allocation after activation.
- The debug probe is an x86-64 Linux VST3 bundle under ignored `build/` with
  SHA-256 `ecff02d3b0a2ecea556d22a1a5ec15ba5ba00ea61769d6fc1d8e85d48ba747b5`.
  Dynamic symbols include `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`;
  compiled identity storage contains the probe FUID and neither production nor
  benchmark FUID. Its source graph contains only the three neutral core files,
  the two VST3 adapter files, and Steinberg's official combined-component and
  Linux-entry sources—no CLAP source or header.
- Debug and ASan/UBSan runs each pass 66 tests; all 134 Python tests, the
  native source validator, Git whitespace checks, and the excluded historical
  CLAP target pass. The final guarded sanitizer snapshot recorded about 32.2
  GiB available, load 1.07, 41 C, and zero memory-full and I/O-full PSI. No
  REAPER process was launched, and no persistent plug-in copy, live project,
  or hardware input was touched.
- Task 9 is sealed at commit `02ba96f` (`feat: add VST3 parameters and exact
  state`). The combined component now registers the sixteen generic VST3
  parameters directly from the neutral contract, including exact IDs, titles,
  defaults, step counts, list/read-only flags, conversions, and bounded text.
  Status cannot be written; Panic is momentary, nonpersistent, and retries its
  Ready output when the host rejects publication.
- Host parameter input is atomic and bounded to sixteen queues with at most 64
  points each. Known controls use the last valid boundary value, unknown queues
  are ignored, and malformed counts, offsets, values, and noncanonical edits
  fail without partial mutation. The process bridge performs no allocation or
  locking; its only new allocations create SDK parameter objects during
  initialization.
- VST3 component/controller state is byte-identical to the neutral 184-byte
  image. Partial `IBStream` progress is handled exactly; null, failed, zero,
  negative, over-reported, truncated, trailing, and invalid images are rejected
  before publication. Component-state synchronization preserves the live,
  nonpersistent Status value and does not invoke a component-handler callback.
- The final committed-state gates pass 78/78 native tests in debug and under
  ASan/UBSan, 134 Python tests plus 50 subtests, the native source validator,
  exact source-graph/build contracts, Git whitespace checks, the guarded VST3
  probe build, and the excluded historical CLAP target. The final probe
  SHA-256 is
  `19958d801a87eb8f078a6f911ec6f630ab4b33b6162007029bfbceca39bcfb76`;
  it is an ELF64 little-endian x86-64 shared object with immediate binding and
  exports `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`.
- The final guard snapshot recorded 32772 MiB available, load 0.81, 66 C, and
  zero memory-full and I/O-full PSI. Task 9 launched no REAPER process and made
  no persistent plug-in copy, live-project mutation, or hardware/input action.
  Its initial missing-bridge RED and the later nonpersistent-Status regression
  RED both failed for the intended reasons before their respective fixes.
- Task 10 is sealed at commit `69f3ab3` (`feat: add fail-closed VST3 note
  delivery`). The narrow sink emits only zero-initialized VST3 NoteOn/NoteOff
  records on bus zero, converts channels 1..16 to 0..15, preserves valid block
  offsets, maps velocity exactly, and uses matching deterministic note IDs
  `-1000-pitch`. Invalid pitch/channel/velocity/kind/offset/context and host
  `addEvent()` rejection all fail closed.
- The combined component now owns the neutral generated-note ledger. Event
  input remains absent and `ProcessData::inputEvents` is never read. Equal-time
  offs precede ons, multiple ticks retain sequence, and output contains no CC,
  DataEvent, note expression, pitch bend, MPE, or passthrough event.
- Every injected note-on and cleanup rejection position latches MIDI Output
  Blocked, inhibits later ons, retains accepted or maybe-active pitches, and
  retries individual offs at offset zero in ascending pitch order with at most
  one bounded 128-pitch pass per call. Dry audio remains bit exact. Explicit
  Panic plus two complete quiet calls is required before ons resume.
- Event delivery performs no heap work or locking after activation. Normal,
  null-output, and rejecting sink paths each passed 100,000 bounded calls with
  allocation/deallocation counters unchanged. Debug and ASan/UBSan each pass
  83/83 native tests; all 134 Python tests plus 50 subtests, the source
  validator, exact source graph, whitespace checks, probe build, and historical
  CLAP target pass.
- The final Task 10 probe SHA-256 is
  `d4a5fc40ede51e07f2ce0a104bb475b71f512979616b839da48b99341551fe33`;
  it retains ELF64 little-endian x86-64 DYN identity, immediate binding, and
  `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`. The final guard snapshot
  recorded 32436 MiB available, load 4.21, 58 C, and zero memory-full and
  I/O-full PSI. No REAPER process, persistent bundle, live project, or
  hardware/input action was used. The primary RED was the intended missing
  `vst3_event_sink.hpp` boundary.
- Task 11 is sealed at commit `db32720` (`feat: complete bounded VST3
  processing lifecycle`). Host setup now accepts finite positive rates from
  the host without a fixed sample-rate matrix, including 44.1, 48, 88.2, 96,
  32, 50, and 192 kHz, while rejecting zero, negative, non-finite, and
  numerically unsafe rates. Prepared timing stores exact sample and 64-sample
  decision periods outside `process()`.
- Main-thread structural edits publish generation-tagged prepared
  configurations through the bounded exchange. The audio callback adopts only
  a matching generation at the parameter boundary; missing preparation enters
  Reconfiguring, releases reachable notes, keeps the old configuration and dry
  path, and never prepares in `process()`. Matching late preparation commits
  once and resets phase and detector transients.
- Stop/start, deactivate/reactivate, and host-rate changes preserve the fixed
  pending-note ledger while freeing transition storage. The first resumed
  process retries old-channel note-offs at offset zero before detector work.
  Input/output layout, sample format, block size, pointers, aliasing,
  non-finite audio, parameter-only calls, silence flags, missing/rejecting host
  output queues, and all processing modes fail closed or pass dry audio under
  their explicit contracts.
- The 64-sample decision phase is invariant across variable partitions,
  process modes, and float32/float64 paths, including multiple ticks in long
  blocks. Repeated 100,000-call process and 100,000-call stop/start runs changed
  neither allocation nor deallocation counters after activation.
- Fresh final gates pass 92/92 native tests in debug, ASan/UBSan, and TSan;
  all 134 Python tests plus 50 subtests; the native source validator; exact
  source graph; Git whitespace checks; the guarded VST3 probe; and the
  historical CLAP target. The final probe SHA-256 is
  `d8382bab6732faf77ee72f50165a3477735ecad98f19e204de513704dc43b0d8`;
  it is a stripped ELF64 little-endian x86-64 shared object with RELRO,
  immediate binding, and only the expected VST3 entry points among the checked
  adapter symbols.
- Task 11's initial RED failed on the absent setup/phase test seams. Its final
  packaging gate then exposed one missing prepared-config source in the
  authoritative CMake graph; that defect was repaired and every affected gate
  reran green. The final stability check showed about 32 GiB available and
  zero full memory/I/O pressure. No REAPER process, persistent bundle, live
  project, or hardware/input action was used.
- Task 12 is sealed at commit `7c02188` (`test: seal offline VST3 adapter and
  validator`). A fixed-seed `0x4D335633` adversarial run now executes 100,000
  bounded operations across malformed parameter/state/process/layout/event and
  lifecycle inputs. Its initial RED exposed delivery of a ninth generated
  voice; the neutral ledger now blocks that event before host delivery and
  retains the first eight for deterministic cleanup.
- The real-time gate performs 100,000 process plus stop/start cycles with
  allocation/deallocation counters and `/proc/self/task` unchanged. The
  production-source validator now rejects threads, locks, conditions, futures,
  filesystem/stream/stdio access, network access, sleep/wait, exceptions,
  RTTI, recursive neutral-core functions, growable containers, CLAP symbols,
  test identities, report environments, and test schedules.
- Production and probe are real two-file build-local VST3 bundles with exact
  official module-info. The production `.so` SHA-256 is
  `e6f6ebfbe522a1eb3a785db97902296931d8f57c0083904f9b656b770302e37d`,
  module-info is
  `7a6247b9d1ccd815c0bf6ff0821a906168e2bb48d755f0e22cd60450734e8738`,
  and the full bundle digest is
  `fed1e4062ba5f29511df2c4b9f430ed3fe0d70172d897ec91dacdc5d2a9e1eaa`.
- Gate O4 is green. The build-local official Steinberg validator ran exactly
  once against the canonical production bundle and reported 47 passed, 0
  failed with classification `pass`, return code zero, and no automatic
  retry. Its atomic evidence is
  `build/test-results/vst3-validator/production/{result.json,stdout.txt,stderr.txt}`.
- Two independent serial builds using `SOURCE_DATE_EPOCH=1788129797` under
  `build/repro-{a,b}/release` are byte-identical to each other and to the
  canonical release bundle. Compiler, flags, SDK/module/binary hashes, complete
  manifests, official-validator hashes, and the one-run record are preserved
  in `docs/VST3-TESTING.md`.
- Final Task 12 gates pass 95/95 native tests in debug, ASan/UBSan, and TSan;
  all 142 Python tests; the native source validator; exact production/probe
  targets; the retained historical CLAP link target; and Git whitespace
  validation. One earlier build preflight safely refused at memory-full PSI
  1.49 before compilation; no limit was loosened, and later pressure returned
  to zero. The final snapshot had about 30 GiB available, zero swap/full
  memory/I/O pressure, and no REAPER process. No persistent bundle, live
  profile/project, or hardware/input action was used.
- Task 13 is sealed at commit `f3c3fe2` (`test: guard build-local VST3 host
  matrices`). Disposable staging now permits the exact host-derived rates
  44.1, 48, 88.2, and 96 kHz and block sizes 32, 64, 128, 256, and 512. Only
  the disposable `reaper.ini` receives the exact build-local VST3 scan root;
  stale VST3 and CLAP caches are removed without touching the live profile.
- The generalized launcher accepts mutually exclusive CLAP or VST3 injection,
  validates the exact probe bundle, binary, module-info identity, and
  symlink-free containment, and strips inherited plug-in injection variables
  without changing `HOME`. Existing workspace-5 isolation, background and
  nonactivating window handling, 50%-of-one-CPU quota, 384/512 MiB memory
  high/max, 64 MiB swap, 64-task limit, and bounded CPU/wall time remain.
- `tools/run_native_vst3_probe.py` defines the exact ordered twenty-row matrix.
  Every future row gets a fresh disposable profile, unique project, and one
  guarded process. Input hashes cover the probe binary, bundle, module-info,
  capability source/script, guard, stager, and runner. Complete rows require
  the suite sentinel, rate/block identity, before/after pressure, return
  status, and every expected TSV. Changed or interrupted evidence is renamed
  invalid and cannot be retried; the first failure, timeout, post-stage
  preflight abort, or pressure abort stops the tail.
- Task 13 verification passes 77/77 focused tests, 163/163 repository Python
  tests, Python compilation, the native source validator, and Git whitespace
  checks. The real non-launching dry plan printed all twenty rows in order and
  left zero REAPER processes. One earlier dry-plan preflight correctly refused
  while system memory-full PSI was elevated; no staging or launch occurred,
  the limit was not loosened, and the final dry plan passed after active PSI
  returned to zero. No persistent bundle, live profile/project, hardware/input,
  or REAPER action was used.
- Task 14 is sealed at commit `848bf80` (`test: add audio-triggered VST3
  capability probe`). The test-only factory selects a separate probe processor
  while the production factory and source graph remain free of the probe
  identity, trigger protocol, diagnostics, and capability schedule.
- The probe decodes only a bounded stereo-audio test code at the fixed
  64-sample cadence. It emits deterministic ordinary VST3 note-on/off events,
  validates the complete process contract and every input sample before
  decoding, latches malformed/overflow conditions, and publishes fixed atomic
  diagnostics only once per processing start with a four-attempt bound.
- The disposable JSFX source and ReaScript verify exact VST3 discovery,
  parameters, write protection, state, dry pass/mute, float32/float64 audio
  triggering, lifecycle cleanup, deletion silence, and global diagnostics.
  A disabled reporter is reserved before playback so module-static evidence
  survives deletion of the tested instance; failure never publishes the suite
  sentinel or self-closes the disposable host.
- Fresh Task 14 gates pass 101/101 native tests in debug, ASan/UBSan, and TSan;
  all 164 repository Python tests; all 30 source contracts; the native source
  validator; exact probe and production builds; and Git whitespace checks.
  The official Steinberg validator classifies the probe `pass` with return
  code zero and no automatic retry. Its bundle digest is
  `e21f55b673e529feb35620bb80dcc1426671fb066e7a761739f9ed86bcaa4018`.
- Task 15's non-launching preauthorization gates are green: native debug and
  sanitizer suites, release probe build, official probe validation, 48 focused
  guard/runner tests, and a real dry plan containing exactly twenty ordered
  rows from 44.1 kHz/32 through 96 kHz/512 all pass. The final process scan
  found zero REAPER processes. This was the final state before Gate C5
  authorization; no row had yet been launched.
- In direct response to the exact Gate C5 scope, the user said `Proceed` on
  2026-08-30. This freshly authorized exactly twenty guarded disposable REAPER
  launches once, retaining workspace 5, serial execution, hard resource
  ceilings, stop-on-first-failure, immutable evidence, and no retry.
- The immediate launch preflight passed with 26782.62 MiB available, load
  1.34, temperature 55 C, memory-full and I/O-full PSI 0.00, workspace 5
  present, workspace 1 active, and no REAPER process or window.
- Gate C5 launched only its first row, 44.1 kHz/block 32. The guarded process
  reached its 45-second timeout and returned 124. The runner classified the
  row `infrastructure-invalid`, atomically preserved it at
  `build/test-results/native-vst3-probe/batches/44100-32.invalid-20260831T004349Z`,
  stopped the remaining nineteen rows, and made no retry.
- `phase.log` ends in `suite-fail`, not `suite-finish`; `capability.tsv`
  reports status `fail` with 77 assertion labels; and every probe lifecycle,
  format, buffer, rate/block, and trigger diagnostic remains `-1`. Those
  partial TSV values are invalid non-completion evidence, not product
  capability measurements or a proven adapter diagnosis.
- The seven-file lexical evidence-manifest digest is
  `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`.
  Exact file hashes and the runtime input hashes are recorded in
  `docs/VST3-TESTING.md` and the immutable row metadata.
- Cleanup is green: the after snapshot recorded 26863.25 MiB available, load
  3.16, temperature 59 C, and zero full memory/I/O pressure. Zero REAPER
  processes/windows remain, workspace 1 is still active, and workspace 5
  remains present. The check-only adjudicator fails closed on the sealed
  invalid first row and nineteen unlaunched rows, as required.
- **Decision:** Gate C5 did not pass. Task 16 and all remaining detector-port
  and release work are blocked. The infrastructure-invalid result authorizes
  no retry and no adapter, runner, profile, timeout, or assertion-script edit.
- The subsequently authorized, non-launching harness recovery is sealed at
  `7ca54a5`, and its evidence-namespace recovery correction is sealed at
  `a551021`. The first v2 runner invocation recovered and preserved the stale
  v1 staging duplicate without launching REAPER or consuming launch authority.
- Fresh v2 Gate C5 authorization then launched exactly one row. The 44.1
  kHz/block 32 process exited cleanly with guard return code zero and a terminal
  `suite-fail`; the only assertion label is `observer-magic`. The v2 row is
  immutable at
  `build/test-results/native-vst3-probe-v2/batches/44100-32.invalid-20260831T092345Z`
  with manifest digest
  `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
- The v2 result is a valid capability `fail`, not another infrastructure
  timeout. It stops before any product assertion, so it neither establishes a
  production-adapter defect nor authorizes a corrective edit. Nineteen rows
  remain unlaunched; retry and Task 16 remain blocked.

- The user approved exact-plan inline execution with `Proceed --continuous` on
  2026-08-29. Task 1 is sealed at commit `436b396` (`test: seal VST3
  migration identities and baseline`). The user separately opened Gate T1 by
  naming exact package `cmake=4.2.3-2ubuntu2` with
  `--no-install-recommends` for Task 2 only. Task 2 is sealed at `21f544b`
  (`docs: record authorized VST3 CMake prerequisite`). Task 3 was subsequently
  authorized and sealed at `9851237` as recorded above.
- Task 1 added the SDK-independent production/probe/benchmark identities and
  stable metadata in `native/vst3/vst3_ids.hpp`, ten focused build-contract
  tests, the reusable source-boundary validator seam, and
  `docs/VST3-TESTING.md`. Their Task-1-seal SHA-256 values were respectively
  `40959108a44ab18eb827838fd20a95033d789671cb85858493e108608f0d38d2`,
  `b873e2e35bd170395a73be6f24d9733a558a746a20921dc6db7824f3b3e131d1`,
  `22b34d74f919abf36a2bee3e56b38aa09775326cda2c289ea33176e12b1a6fef`,
  and `296a46bde863dbf12169397bfa6f74eb339f54247ad53ccee5e781e8453a4813`.
- Task 2 adds one real prerequisite contract to
  `tests/test_vst3_build_contract.py` and records the exact package evidence in
  `docs/VST3-TESTING.md`. Their current SHA-256 values are respectively
  `35a817fbffaf739f9d74fed44b8749cf12ab53a30e395feff189060168791aa2`
  and `665becd911275f6e066e0b299b791086d7e37f39356470790db0e32a0df359f1`.
- The exact committed state passes 44 native tests and 125 Python tests; the
  focused VST3 suite passes 11/11. The source validator, C++17 identity
  compile, Python compilation, whitespace check, frozen-JSFX comparison, and
  sealed specification-hash check pass.
- Final Task 2 regression preflight was stable: 32325 MiB available memory,
  load 1.25, memory-full and I/O-full PSI 0.00, and maximum readable
  temperature 54 C.
  Tests ran serially at low CPU and idle I/O priority.
- `/var/log/apt/history.log` records the approved command exactly from 04:35:35
  through 04:35:42 PDT. CMake reports `4.2.3`; dpkg reports `install ok
  installed 4.2.3-2ubuntu2`. Only required automatic dependencies
  `cmake-data`, `libjsoncpp26`, and `librhash1` accompanied it. Swap use and
  full pressure remained zero.
- The exact approved Steinberg SDK is vendored and Task 8 has produced only the
  ignored build-local probe bundle. No persistent M3 plug-in copy or REAPER
  process exists, and no live profile/project, hardware input, or REAPER action
  has occurred under the VST3 plan.
- Gates D2 and the Task 4 build foundation passed at `9851237` and `282ba18`;
  Task 5 neutral parameters passed at `c85d9ab`, and Task 6 neutral state
  images passed at `42859f7`. Task 7's neutral generated-note ledger passed at
  `5c77caf`, opening Gate N3, and Task 8's minimal VST3 lifecycle passed at
  `d757877`. Task 9's generic parameter and exact-state bridge passed at
  `02ba96f`, Task 10's fail-closed VST3 note delivery passed at `69f3ab3`, and
  Task 11's bounded host-rate processing lifecycle passed at `db32720`, and
  Task 12's offline adapter and official-validator seal passed at `7c02188`,
  Task 13's disposable VST3 staging/guard matrix passed at `f3c3fe2`, and Task
  14's offline audio-trigger capability probe passed at `848bf80`. Task 15
  then sealed its first and only launched row infrastructure-invalid. Task 16
  is blocked; do not retry or edit from this result without new direction.

## Approved VST3 design and sealed implementation plan

- On 2026-08-29 the user approved replacing the failed CLAP production path
  with one Linux x86-64 VST3 effect built over the preserved format-neutral
  C++17 detector core. The authoritative new specification is
  `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`.
  Its initial design commit is `35f8a88`; the host-authoritative rate revision
  is `ba1302b` (`docs: make VST3 rate host-authoritative`). The current
  written specification was approved by the user via `Continue on` on
  2026-08-29. Its current SHA-256 is
  `bf27a627432bb360b7e123300e01edb80228b1de0d71331d5d5e968f6d43e4d5`.
- The replacement test-driven implementation plan is
  `docs/superpowers/plans/2026-08-29-native-vst3-polyphonic-audio-to-midi.md`.
  It was written and self-reviewed at commit `9390763`
  (`docs: plan native VST3 implementation`); its SHA-256 is
  `b7dbe1a7eb3a93ba4e06575dc88c45f800191adc5e6e6ef530a7bdc51e768de3`.
  The plan has 24 ordered tasks, 152 executable checkboxes, ten named gates,
  exact files/interfaces/commands/commits, and no unresolved placeholder.
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
- The user clarified that sample rate belongs to the host. The plug-in has no
  sample-rate control, whitelist, preferred-rate override, or hidden resampler;
  it derives bounded coefficients from the finite positive rate supplied by
  VST3 setup. The mandatory verification points are 44.1, 48, 88.2, and 96
  kHz, while other finite host rates remain governed by the same preparation
  and safety contract rather than being silently converted.
- The user explicitly added block size 512. The exact host matrix is twenty
  serial rows: 44.1, 48, 88.2, and 96 kHz, each at blocks 32, 64, 128, 256,
  and 512. It stops after the first failed, invalid, timed-out, or
  pressure-aborted row. Separately, the REAPER child memory ceiling remains
  512 MiB.
- 96 kHz remains a hard release gate with native-rate processing and the same
  64-host-sample cadence. The existing 96 kHz 32+56 false MIDI-44 regression
  is not waived by an adapter probe and must pass before release.
- The stable descriptive identity is
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`. The locked production, probe,
  and benchmark FUIDs are respectively
  `4A1BA42F-6D70-4609-8B52-450C3842F11F`,
  `6F62F8B1-B8A1-4872-A0D9-2C3C274421D8`, and
  `28713895-1CCA-47EC-919F-6CC1BCB88A8F`; they must not be regenerated.
- The pre-Task-1 planning preflight passed 44 native tests and 114 Python tests
  under low-priority serial execution. CMake was absent at that checkpoint and
  the read-only candidate was exactly `4.2.3-2ubuntu2`. Task 1 subsequently
  wrote only the SDK-independent identity/source-boundary files recorded
  above; detector source remains untouched and no dependency, SDK, or host
  action occurred.
- Task 2 subsequently installed only that exact CMake package under separately
  explicit authority and stopped at Gate D2. The later `Authorize all` opened
  D2, and exact SDK retrieval was sealed at `9851237`.

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

- Branch: `main`. The current VST3 implementation feature checkpoint is
  `7c02188`;
  the older CLAP implementation checkpoint is `cc938f7` and its failed-host
  gate remains recorded below as retained history. The retained
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
- Fresh current-tree checks: all 142 Python tests and 95 native tests in debug,
  ASan/UBSan, and TSan pass. The native source validator, exact production and
  probe source graphs/bundles, one-run official validator, reproducibility
  comparison, Git whitespace checks, and historical CLAP target are green.
  Probe-only diagnostics remain excluded from the production artifact.
- The task-local `RESUME.md` remains authoritative. The canonical ResearchOS
  project dashboard and native implementation-plan note are synchronized as a
  human-facing, non-Git index.
- Every earlier JSFX-evidence REAPER instance ran serially, backgrounded on
  workspace 5, under the 50%-of-one-core and 512 MiB limits. Tasks 1-12 added
  no REAPER launch, and no REAPER application process remains.
- Decision: native CLAP plan Tasks 1-9 remain retained, but its Task 10 gate
  failed and must not be retried. The replacement VST3 plan is sealed through
  Task 12 at `7c02188`; continue with VST3 Task 13, not any old CLAP task. The
  JSFX detector remains stopped and uninstalled.
- The user's `Authorize all` covers the remaining actions in the approved VST3
  plan only when their ordered prerequisites are reached. Clean-DI input,
  persistent installation, live-project mutation, and REAPER launch have not
  occurred in Tasks 1-12; REAPER MCP remains outside scope.

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

## Offline scan-containment hardening — future guard only

- The future VST3 guarded path now fails closed on exact scope/receipt,
  symlink, lock, recovery, process-census, marker, and cache-validation
  boundaries. The systemd transient scope is considered exited only after an
  exact inactive state, or after collection with a positively exited launcher.
- Independent read-only review is clean. The low-priority `221`-test repository
  suite, both source validators, Python compilation, and whitespace validation
  pass. Verification used mocks or dry-run paths only: it launched no REAPER
  process and did not alter sealed v1/v2/v3 evidence.
- This is future-guard hardening, not a fresh host design, a proof of
  pre-launch scan isolation, or authorization to launch REAPER. Before any new
  host work, preserve the seals, design and independently review the isolation
  boundary, use a new namespace, and obtain new explicit host authority.

## Exact resume action

1. Verify harness-recovery commits `7ca54a5` and `a551021`, observer-
   diagnostic commit `176923e`, and isolated v3 gate `0a216d4`, then verify the
   immutable v1 and v2 seven-file
   manifest digests
   `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`
   and
   `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
2. Preserve both v2 directories exactly: the proven legacy staging duplicate
   ending `091010Z-recovered` and the current-v2 failed row ending
   `092345Z`. Do not adopt, delete, rename, overwrite, or retry either one.
3. Confirm zero REAPER processes/windows, the user's active workspace unchanged,
   and acceptable passive pressure before any further work.
4. Do not rerun the sealed matrix or launch its nineteen-row tail. The sole
   `--observer-diagnostic-once` authorization is consumed by the sealed v3
   timeout at `44100-32.invalid-20260831T113425Z`; its staging marker and batch
   are preservation-only. Any next host execution requires a new design and
   separate explicit authority.
5. Keep every adapter/probe change, REAPER launch, clean-DI/live input,
   performance run, persistent installation, live project, custom GUI, and
   REAPER MCP behind its named gate.

The prior 07:55 PDT pause boundary was honored. The user explicitly resumed the
task afterward.

## Remaining plan actions and prerequisite gates

- VST3 Task 15 v1 remains sealed `infrastructure-invalid`. Its repaired v2 gate
  is now sealed `fail` after one cleanly exited row stopped at
  `observer-magic`; nineteen rows remain unlaunched. Because the observer gate
  failed before any product assertion, Tasks 16-24 are blocked and no retry,
  production-adapter diagnosis, or corrective implementation is authorized by
  the v2 result. Read-only observer diagnosis cannot recover the raw magic or
  distinguish boot, attachment, scheduling, or compilation. The diagnostic-
  only offline amendment is complete at `176923e`; one separately authorized
  fresh guarded diagnostic row is the next possible evidence step.
- Persistent VST3 installation at I9 remains conditional on every required
  release gate being green.
- Clean-DI/live guitar execution at D8 remains conditional on suitable input
  material being available.
- Live-project modification, REAPER MCP installation, CLAP retry/remaining
  Task 10 rows, and custom native GUI work remain outside this authorization.
