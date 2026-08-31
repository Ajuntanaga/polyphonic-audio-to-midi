# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-31T02:28:22-07:00

## Task 15 v2 capability failure sealed at observer handshake — Task 16 blocked

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
  Read-only comparison proved that directory is byte-identical legacy v1
  staging, not a v2 attempt. It remains preserved.
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
- Task 16 and Tasks 17-24 remain blocked. The next safe action is read-only
  diagnosis of why the live JSFX observer did not expose its magic, followed
  only by a separately approved offline amendment if the evidence supports
  one. Do not launch, retry, or edit the production adapter from this result.

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

## Exact resume action

1. Verify harness-recovery commits `7ca54a5` and `a551021`, then verify the
   immutable v1 and v2 seven-file manifest digests
   `98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958`
   and
   `6d47f22e360e202a3c4cd905302ed0e8c8bfe587909e29dc58cd593872776e62`.
2. Preserve both v2 directories exactly: the proven legacy staging duplicate
   ending `091010Z-recovered` and the current-v2 failed row ending
   `092345Z`. Do not adopt, delete, rename, overwrite, or retry either one.
3. Confirm zero REAPER processes/windows, the user's active workspace unchanged,
   and acceptable passive pressure before any further work.
4. Do not rerun the matrix or launch its nineteen-row tail. Task 16 remains
   blocked. The only presently safe next task is read-only diagnosis of the
   JSFX observer attachment/readiness failure; any implementation requires a
   separately approved amendment and fresh tests before any new host gate.
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
  the v2 result.
- Persistent VST3 installation at I9 remains conditional on every required
  release gate being green.
- Clean-DI/live guitar execution at D8 remains conditional on suitable input
  material being available.
- Live-project modification, REAPER MCP installation, CLAP retry/remaining
  Task 10 rows, and custom native GUI work remain outside this authorization.
