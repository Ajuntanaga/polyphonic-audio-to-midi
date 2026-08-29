# Native VST3 Polyphonic Audio-to-MIDI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a source-editable Linux x86-64 VST3 audio effect that follows REAPER's host sample rate, converts isolated tonal audio into one-to-eight discrete note events in real time, preserves the approved M3 and General Tonal contracts, and passes every offline, guarded-host, correctness, latency, deadline, and stability gate before installation or live-input use.

**Architecture:** Preserve the frozen JSFX as the behavioral oracle and retain the failed CLAP adapter as historical evidence. First extract parameter, state-image, generated-note, dry-path, and prepared-configuration logic into format-neutral C++17 modules; then build one non-distributable Steinberg `SingleComponentEffect` with generic host parameters, no event input, one event output, and no custom GUI. Prove the adapter with a fake host, Steinberg validator, and a disposable audio-triggered REAPER probe before porting detector modules; only then assemble and benchmark the production effect.

**Tech Stack:** GNU C++ 15.2 in C++17 mode, CMake 4.2.3 after a separately authorized install, GNU Make as a thin wrapper, official Steinberg VST3 SDK 3.8.1 tag `v3.8.1_build_84`, Python 3 standard-library `unittest`, Lua ReaScript, existing JSFX fixtures, AddressSanitizer/UndefinedBehaviorSanitizer, and REAPER 7.79 only through the guarded launcher.

**Spec:** `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`

## Global Constraints

- This plan is not source, dependency, installation, or REAPER-launch authorization. Execution begins only after plan approval and stops at every named hard gate.
- The user selected inline execution. Do not spawn or delegate workers unless the user explicitly changes that choice.
- CMake installation, SDK retrieval, every REAPER launch phase, clean-DI or hardware input, persistent installation, live-project use, and REAPER MCP remain separately gated.
- Never retry the failed CLAP capability row or run its remaining rows. Keep commit `6a74b9f` and evidence digest `12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51` immutable.
- Do not edit the production JSFX effect or `Effects/m3_poly_midi/**`; commit `0be04d3` and `tests/fixtures/native/jsfx-48k128/**` remain the behavioral oracle.
- Do not copy ReaTune, NeuralNote, Basic Pitch, or other detector source. Only the exact official Steinberg SDK revision named here may be added as third-party code.
- Keep the product name `M3 Polyphonic Audio to MIDI`; do not place Steinberg's VST trademark or logo in the product name or branding.
- The host's finite positive `ProcessSetup::sampleRate` is the sole runtime sample rate. There is no plug-in rate selector, preferred-rate override, whitelist, resampler, downsampler, lookahead, or fixed-rate conversion.
- Mandatory verification rates are `44100`, `48000`, `88200`, and `96000`; they are release evidence points, not a runtime whitelist.
- Production cadence is exactly 64 host samples at every accepted rate. A 128-sample legacy schedule exists only in `M3_TESTING` parity code.
- The production plug-in owns no thread and performs no allocation, deallocation, locking, waiting, sleep, file or console I/O, logging, unbounded retry, or production clock sampling in `process()` or `setProcessing()`.
- No adaptive fallback may reduce pitch range, polyphony, harmonic work, decision frequency, validation thresholds, or native sample rate to hide a correctness or deadline failure.
- Every native build/test command is serial (`-j1`), low-priority, and bounded by the planned build guard. Refusal, pressure, timeout, or a crash stops the task; it never triggers an automatic retry.
- Every REAPER process is fresh, serial, disposable, nonactivating, backgrounded on workspace 5, limited to 50% of one logical CPU, 384 MiB memory-high, 512 MiB memory maximum, 64 MiB swap, and 64 tasks. The user's active workspace must be restored after any focus steal.
- Build products, SDK retrieval worktrees, profiles, projects, validators, and evidence remain under ignored `build/`. Nothing is copied to `~/.vst3`, a system VST3 directory, the live REAPER profile, or a live project.
- Commit only current-task files. Preserve unrelated user edits and stop if they overlap a planned path.

## Locked Identities and Dependency Revisions

These IDs were generated once on 2026-08-29 and must never be regenerated:

The stable descriptive identity is `com.ajuntanaga.m3-polyphonic-audio-to-midi`; it is metadata only and never substitutes for the locked binary class ID.

| Build | Canonical UUID | `Steinberg::FUID` words |
| --- | --- | --- |
| Production | `4A1BA42F-6D70-4609-8B52-450C3842F11F` | `0x4A1BA42F, 0x6D704609, 0x8B52450C, 0x3842F11F` |
| Capability probe | `6F62F8B1-B8A1-4872-A0D9-2C3C274421D8` | `0x6F62F8B1, 0xB8A14872, 0xA0D92C3C, 0x274421D8` |
| Benchmark-only | `28713895-1CCA-47EC-919F-6CC1BCB88A8F` | `0x28713895, 0x1CCA47EC, 0x919F6CC1, 0xBCB88A8F` |

The dependency gate permits exactly:

| Repository | Exact revision |
| --- | --- |
| `steinbergmedia/vst3sdk` tag `v3.8.1_build_84` | `3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96` |
| `steinbergmedia/vst3_base` | `fcf9da0bd27a16f7f03773a3a39822f28f5c8477` |
| `steinbergmedia/vst3_cmake` | `054c9143cbb8d47fc4694e473f2ee3b4d951a8f5` |
| `steinbergmedia/vst3_pluginterfaces` | `4f547e8e102b47de4a8b8aaf343c73b700786372` |
| `steinbergmedia/vst3_public_sdk` | `586dc5e6c8012c3e4b01c79389375cbe96bdb1da` |

No `doc`, `tutorials`, or `vstgui4` submodule is retrieved. VSTGUI, AAX/AU wrappers, plug-in examples, and unrelated hosts are disabled in CMake; only the official validator and module-info utility may be built from the retained public SDK.

## Hard Gates and Stop Conditions

| Gate | Required authority/evidence | Allowed after pass | Failure action |
| --- | --- | --- | --- |
| P0 Plan | User accepts this exact plan | Run Task 1 local baseline only | Amend documentation only |
| T1 Tool | Explicit approval to install exact CMake candidate `4.2.3-2ubuntu2` | Run Task 2 install command | Stop; do not substitute a package or installer |
| D2 Dependency | Explicit approval to retrieve/vend the exact five revisions above | Run Task 3 network commands | Preserve partial retrieval under `build/`; no alternate SDK |
| N3 Neutral extraction | Existing CLAP/native tests remain green and production VST3 objects contain no CLAP symbols | Begin VST3 component work | Revert only the current extraction task through normal commits; do not alter sealed CLAP evidence |
| O4 Offline adapter | Fake-host, sanitizers, source checks, official validator, and exact bundle checks green | Prepare disposable REAPER probe | Fix the smallest offline adapter slice; no REAPER launch |
| C5 Capability host | Explicit approval for exactly twenty guarded disposable REAPER rows | Port detector modules | Stop on first failed/invalid/timed-out/pressure-aborted row; preserve evidence; no retry |
| N6 Native production host | Offline detector gates green plus explicit approval | Run production correctness/lifecycle matrix | Return to smallest responsible module; no heavy retry |
| P7 Performance | Production-host correctness green plus explicit approval | Run guarded timing matrix | Any callback at or above 50% of deadline stops the experiment and requires amendment |
| D8 Clean DI | Separate approval and input material | Measure clean-DI thresholds | Synthetic success remains experimental |
| I9 Install | Every preceding release gate green plus explicit approval | Copy one production bundle to a persistent path | Leave build-local artifact uninstalled |

This implementation plan ends with a sealed build-local artifact and evidence. D8 and I9 are not execution tasks here.

## Planned File Map

### Build, dependency, and provenance

| Path | Responsibility |
| --- | --- |
| `CMakeLists.txt` | Authoritative explicit target/source graph and bundle generation |
| `cmake/M3CompilerOptions.cmake` | Strict warnings, hardening, sanitizer, reproducibility, and production definitions |
| `cmake/M3Vst3Sdk.cmake` | Offline-only SDK target setup and exact required-tree checks |
| `native/Makefile` | Thin non-networking wrapper around serial CMake configure/build/test targets |
| `third_party/vst3sdk/{base,cmake,pluginterfaces,public.sdk}` | Unmodified official pinned SDK material |
| `third_party/vst3sdk/{LICENSE.txt,UPSTREAM.md,SHA256SUMS}` | License, root/submodule revisions, retrieval time/commands, and lexical hashes |
| `tools/run_guarded_native_build.py` | Low-priority serial build/test guard with pressure, memory, task, and timeout limits |
| `tests/test_vst3_build_contract.py` | Dependency, CMake, identity, source-list, bundle, and production-isolation contracts |

### Format-neutral native modules

| Path | Responsibility |
| --- | --- |
| `native/include/m3/parameter_contract.hpp` / `native/src/parameter_contract.cpp` | Plain IDs, ranges, steps, normalization, validation, and text conversion |
| `native/include/m3/state_image.hpp` / `native/src/state_image.cpp` | Exact 184-byte state image with no host stream type |
| `native/include/m3/generated_note_ledger.hpp` / `native/src/generated_note_ledger.cpp` | Fixed active/pending pitch ledger, ordering, retry, and sink failure state |
| `native/include/m3/dry_path.hpp` | Float32/float64 stereo pass/mute/non-finite handling |
| `native/plugin/{clap_parameter_bridge,clap_state_stream}.hpp/.cpp` | Historical CLAP-only conversions around neutral modules |
| `native/plugin/midi_pipeline.hpp/.cpp` | Frozen CLAP raw-MIDI merge/CC behavior using the neutral ledger where shared |
| `native/plugin/prepared_config_exchange.hpp/.cpp` | Existing generation-tagged fixed publication path |

### VST3 adapter

| Path | Responsibility |
| --- | --- |
| `native/vst3/vst3_ids.hpp` | Locked production/probe/benchmark FUIDs, names, version, and categories |
| `native/vst3/vst3_component.hpp/.cpp` | `SingleComponentEffect`, lifecycle, busses, processing, status, and adapter composition |
| `native/vst3/vst3_factory.cpp` | One selected class per build and exported official module factory |
| `native/vst3/vst3_parameter_bridge.hpp/.cpp` | Generic parameters and bounded input/output parameter queues |
| `native/vst3/vst3_state_stream.hpp/.cpp` | Fixed-size `IBStream` read/write adapter around `StateImage` |
| `native/vst3/vst3_event_sink.hpp/.cpp` | Neutral transition to VST3 `NoteOnEvent`/`NoteOffEvent` conversion |
| `native/vst3/vst3_probe_processor.hpp/.cpp` | Audio-triggered test-only phases and bounded diagnostics |
| `native/tests/fake_vst3_host.hpp/.cpp` | Fixed fake host, event list, parameter queues, streams, and rejection injection |
| `native/tests/test_vst3_*.cpp` | Factory, lifecycle, bus, parameter, state, event, process, fault, and real-time tests |

### Detector, host tooling, and evidence

| Path | Responsibility |
| --- | --- |
| `native/include/m3/{conditioning,resonator_bank,salience_selector,m3_profile,lifecycle,detector_core}.hpp` | Format-neutral bounded detector interfaces |
| `native/src/{conditioning,resonator_bank,salience_selector,m3_profile,lifecycle,detector_core}.cpp` | Source-equivalent detector implementation |
| `Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx` | Deterministic stereo audio phases only; no MIDI trigger |
| `Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua` | Discovery, parameters, state, audio, note, stop/restart, bypass, and destruction assertions |
| `tools/run_native_vst3_probe.py` | Twenty-row serial capability runner with immutable batches |
| `tools/run_native_vst3_matrix.py` | Offline and guarded production correctness runner |
| `tools/run_native_vst3_benchmarks.py` | Offline and guarded deadline runner |
| `docs/VST3-TESTING.md` | Reproduction commands, hashes, evidence, and authorization boundaries |
| `docs/VST3-PERFORMANCE.md` | Exact distributions, pressure, hashes, failures, and release decision |

Generated-only roots are `build/vendor/vst3sdk-src`, `build/vst3`, `build/reaper-test`, and `build/test-results/native-vst3-*`.

## Shared Neutral Interfaces

All later tasks use these names and signatures:

```cpp
namespace m3 {

using ParameterId = std::uint32_t;
inline constexpr ParameterId kPanicParameterId = 0x4D33000EU;
inline constexpr ParameterId kStatusParameterId = 0x4D33FF01U;
inline constexpr std::size_t kParameterCount = 16;
inline constexpr std::size_t kPersistentParameterCount = 14;

enum class ParameterUpdateClass : std::uint8_t {
  structural, runtime, action, telemetry
};

enum class ParameterApplyResult : std::uint8_t {
  rejected, unchanged, changed, panic
};

struct ParameterSpec final {
  ParameterId id;
  const char* name;
  double minimum;
  double maximum;
  double increment;
  double default_value;
  std::int32_t step_count;
  ParameterUpdateClass update_class;
  bool persistent;
  bool list;
  bool read_only;
};

const ParameterSpec* parameter_spec(std::size_t index) noexcept;
const ParameterSpec* find_parameter(ParameterId id) noexcept;
double canonical_plain(const ParameterSpec& spec, double value) noexcept;
double plain_to_normalized(const ParameterSpec& spec, double value) noexcept;
double normalized_to_plain(const ParameterSpec& spec, double value) noexcept;
ParameterApplyResult apply_parameter(PersistentConfig&, ParameterId,
                                     double plain_value) noexcept;

inline constexpr std::size_t kStateSize = 184;
using StateImage = std::array<std::uint8_t, kStateSize>;
bool encode_state(const PersistentConfig&, StateImage&) noexcept;
bool decode_state(const std::uint8_t*, std::size_t,
                  PersistentConfig&) noexcept;

struct NoteEventSink final {
  void* context{};
  bool (*push)(void*, const VoiceTransition&) noexcept = nullptr;
};

struct NoteDeliveryResult final {
  bool output_blocked{};
  bool panic_hold{};
  bool detection_allowed{};
};

class GeneratedNoteLedger final {
 public:
  bool activate(std::uint32_t max_frames) noexcept;
  void deactivate() noexcept;
  void begin_block() noexcept;
  bool queue_transition(const VoiceTransition&, std::uint32_t frames) noexcept;
  void request_release_all() noexcept;
  void request_recovery() noexcept;
  NoteDeliveryResult deliver(std::uint32_t frames, NoteEventSink,
                             double selected_peak, bool finite_input,
                             bool supported_layout) noexcept;
  bool is_active(std::uint8_t note) const noexcept;
  bool is_pending_release(std::uint8_t note) const noexcept;
};

}  // namespace m3
```

The exact VST3 step counts are `2,1,800,480,100,100,84,84,7,36,1,126,15,1,1,5` in parameter-table order. Only Status sets `ParameterInfo::kIsReadOnly`; list controls set `kIsList`; no control sets `kCanAutomate`.

---

## Task 1: Seal the VST3 Migration Baseline and Identities

**Files:**

- Create: `native/vst3/vst3_ids.hpp`
- Create: `tests/test_vst3_build_contract.py`
- Create: `docs/VST3-TESTING.md`
- Modify: `tools/validate_native_source.py`

**Interfaces:**

- Consumes: design SHA and the three FUID word tuples locked above.
- Produces: `m3::vst3::kProductionClassIdWords`, `kProbeClassIdWords`, `kBenchmarkClassIdWords`, stable names/categories, and source-boundary tests used by every VST3 task.

- [ ] **Step 1: Recheck the untouched baseline before source work.**

  Run:

  ```bash
  git diff --exit-code 0be04d3 -- 'Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx' Effects/m3_poly_midi
  spec_sha="$(sha256sum docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md | cut -d' ' -f1)"
  rg -q "$spec_sha" RESUME.md
  nice -n 15 ionice -c3 make -C native -j1 test
  nice -n 15 ionice -c3 python3 -m unittest discover -s tests -p 'test_*.py' -v
  git status --short
  ```

  Expected: frozen JSFX diff empty, the current design hash is present in the authoritative `RESUME.md`, 44 native tests and 114 Python tests pass, and no unrelated tracked change. Stop on any mismatch.

- [ ] **Step 2: Write the identity/source RED.**

  Add assertions that `vst3_ids.hpp` exists, contains each exact four-word tuple once, uses descriptive ID `com.ajuntanaga.m3-polyphonic-audio-to-midi`, product name `M3 Polyphonic Audio to MIDI`, production category `Fx|Tools`, probe/benchmark names that include `Probe`/`Benchmark`, and contains no zero FUID. Require no `third_party/vst3sdk`, `.vst3` directory, SDK-dependent VST3 `.cpp` source, or production SDK include before Gate D2.

  Run:

  ```bash
  python3 -m unittest tests.test_vst3_build_contract -v
  ```

  Expected RED: `native/vst3/vst3_ids.hpp` is absent.

- [ ] **Step 3: Add the SDK-independent identity header.**

  Implement only plain values so this task needs no Steinberg header:

  ```cpp
  namespace m3::vst3 {
  inline constexpr std::array<std::uint32_t, 4> kProductionClassIdWords{
      0x4A1BA42FU, 0x6D704609U, 0x8B52450CU, 0x3842F11FU};
  inline constexpr std::array<std::uint32_t, 4> kProbeClassIdWords{
      0x6F62F8B1U, 0xB8A14872U, 0xA0D92C3CU, 0x274421D8U};
  inline constexpr std::array<std::uint32_t, 4> kBenchmarkClassIdWords{
      0x28713895U, 0x1CCA47ECU, 0x919F6CC1U, 0xBCB88A8FU};
  inline constexpr char kDescriptiveId[] =
      "com.ajuntanaga.m3-polyphonic-audio-to-midi";
  inline constexpr char kProductName[] = "M3 Polyphonic Audio to MIDI";
  inline constexpr char kProductionSubcategories[] = "Fx|Tools";
  }  // namespace m3::vst3
  ```

- [ ] **Step 4: Extend the source validator without changing CLAP behavior.**

  Reject VSTGUI, JUCE, iPlug2, ONNX/model runtimes, handwritten VST3 ABI declarations, network calls in CMake/build files, duplicate FUID tuples, production references to probe/benchmark IDs, and any VST3 source under `native/plugin/`. Ignore `build/` and the still-absent official SDK root.

- [ ] **Step 5: Record and commit the sealed baseline.**

  `docs/VST3-TESTING.md` records the two passing test counts, compiler version, CMake absence, locked IDs, design hash, failed-CLAP evidence digest, and the fact that no SDK/REAPER/install action occurred.

  ```bash
  python3 -m unittest tests.test_vst3_build_contract -v
  python3 tools/validate_native_source.py .
  git diff --check
  git add native/vst3/vst3_ids.hpp tests/test_vst3_build_contract.py tools/validate_native_source.py docs/VST3-TESTING.md
  git commit -m "test: seal VST3 migration identities and baseline"
  ```

## Task 2: Install the Exact CMake Tool Prerequisite

**Gate T1:** Stop before this task until the user explicitly authorizes a host package installation. Task 1 approval does not authorize it.

**Files:**

- Modify after the command: `docs/VST3-TESTING.md`
- Modify: `tests/test_vst3_build_contract.py`

**Interfaces:**

- Consumes: Ubuntu 26.04 package candidate `cmake=4.2.3-2ubuntu2`.
- Produces: a verified `cmake` executable at least 3.25; no SDK or plug-in artifact.

- [ ] **Step 1: Verify the package candidate has not drifted.**

  ```bash
  test "$(apt-cache policy cmake | awk '/Candidate:/ {print $2}')" = 4.2.3-2ubuntu2
  if command -v cmake >/dev/null 2>&1; then
    test "$(cmake --version | awk 'NR == 1 {print $3}')" = 4.2.3
  fi
  ```

  Expected: the exact candidate, with either no existing executable or an already-installed exact `4.2.3`. If either version differs, stop and amend this plan; do not run `apt update` or choose another installer. If the exact version is already installed, record that Task 2 required no mutation and continue only to Gate D2.

- [ ] **Step 2: Install only the approved package.**

  Run once after approval:

  ```bash
  sudo apt-get install --no-install-recommends cmake=4.2.3-2ubuntu2
  ```

  No compiler, Ninja, Qt, VST package, SDK, or recommended package is authorized by this command.

- [ ] **Step 3: Verify the installed tool and system state.**

  ```bash
  cmake --version
  dpkg-query -W -f='${Status} ${Version}\n' cmake
  free -m
  sed -n '1,2p' /proc/pressure/memory
  sed -n '1,2p' /proc/pressure/io
  ```

  Expected: CMake `4.2.3`, package status `install ok installed`, no swap consumption or pressure spike attributable to the command.

- [ ] **Step 4: Lock the observed prerequisite in tests and documentation.**

  Assert `cmake --version` parses at least 3.25 and that repository build files contain no downloader. Record the exact package/version and approval date.

  ```bash
  python3 -m unittest tests.test_vst3_build_contract -v
  git diff --check
  git add tests/test_vst3_build_contract.py docs/VST3-TESTING.md
  git commit -m "docs: record authorized VST3 CMake prerequisite"
  ```

## Task 3: Vendor the Exact Official VST3 SDK Revision

**Gate D2:** Stop until the user explicitly authorizes network retrieval and vendoring of the exact root and four submodule commits locked above. CMake authorization does not authorize this task.

**Files:**

- Create: `third_party/vst3sdk/{CMakeLists.txt,LICENSE.txt,README.md}`
- Create: `third_party/vst3sdk/{base,cmake,pluginterfaces,public.sdk}/**`
- Create: `third_party/vst3sdk/{UPSTREAM.md,SHA256SUMS}`
- Modify: `tests/test_vst3_build_contract.py`

**Interfaces:**

- Consumes: exact five official Git revisions.
- Produces: an offline, hash-complete SDK tree; no system installation or user plug-in copy.

- [ ] **Step 1: Write the dependency-contract RED before retrieval.**

  Require exact root/tag and submodule commits, exact upstream URLs, all four retained subdirectories, MIT license, lexical `SHA256SUMS`, no `.git`, `doc`, `tutorials`, or `vstgui4`, and no unmanifested file.

  ```bash
  python3 -m unittest tests.test_vst3_build_contract -v
  ```

  Expected RED: `third_party/vst3sdk/UPSTREAM.md` is absent.

- [ ] **Step 2: Reverify official refs without downloading source bytes.**

  ```bash
  test "$(git ls-remote https://github.com/steinbergmedia/vst3sdk.git refs/tags/v3.8.1_build_84 | cut -f1)" = 3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96
  ```

  Expected: the exact official root tag is advertised. The four submodule commits are verified from the checked-out root's gitlinks and each retrieved submodule HEAD in Step 3; do not use `ls-remote` with a raw commit as though it were a ref. Stop on any mismatch.

- [ ] **Step 3: Retrieve into ignored build storage under low priority.**

  ```bash
  nice -n 15 ionice -c3 git clone --filter=blob:none --no-checkout https://github.com/steinbergmedia/vst3sdk.git build/vendor/vst3sdk-src
  git -C build/vendor/vst3sdk-src checkout --detach 3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96
  nice -n 15 ionice -c3 git -C build/vendor/vst3sdk-src submodule update --init --depth 1 base cmake pluginterfaces public.sdk
  ```

  Before copying anything, verify root `rev-parse HEAD`, the four gitlink object IDs from `git ls-tree HEAD`, and each submodule `rev-parse HEAD` against the table. Preserve an interrupted checkout under `build/vendor/`; do not delete and retry automatically.

- [ ] **Step 4: Copy only the approved official roots and provenance.**

  Bulk-copy root `CMakeLists.txt`, `LICENSE.txt`, `README.md`, and the four verified submodule worktrees without any `.git` metadata. Do not copy `doc`, `tutorials`, `vstgui4`, archives, or generated files. `UPSTREAM.md` records UTC time, URLs, commits, exact commands, the retained roots, and CMake exclusions. Generate a lexical manifest from the repository root:

  ```bash
  find third_party/vst3sdk -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > third_party/vst3sdk/SHA256SUMS
  ```

- [ ] **Step 5: Validate provenance offline and commit one dependency unit.**

  ```bash
  sha256sum --check third_party/vst3sdk/SHA256SUMS
  python3 -m unittest tests.test_vst3_build_contract -v
  python3 tools/validate_native_source.py .
  git diff --check
  git add third_party/vst3sdk tests/test_vst3_build_contract.py
  git commit -m "build: vendor pinned VST3 SDK 3.8.1"
  ```

## Task 4: Establish the Guarded CMake Build and Bundle Foundation

**Files:**

- Create: `CMakeLists.txt`
- Create: `cmake/{M3CompilerOptions.cmake,M3Vst3Sdk.cmake}`
- Create: `tools/run_guarded_native_build.py`
- Modify: `native/Makefile`
- Modify: `tests/test_vst3_build_contract.py`
- Create: `tests/test_guarded_native_build.py`

**Interfaces:**

- Consumes: pinned SDK target `sdk`, existing neutral/CLAP sources, and CMake 4.2.3.
- Produces: `m3_native_tests`, `m3_clap_history`, `m3_vst3_probe`, `m3_vst3_production`, `m3_vst3_benchmark`, `m3_validate_production`, and serial guarded wrapper commands.

- [ ] **Step 1: Write build-graph and guard RED tests.**

  Assert explicit source lists (no `GLOB`), C++17, exceptions/RTTI disabled for project production targets, strict warnings, hidden symbols, RELRO/NOW/no-undefined, no `-march=native`, no download construct, VSTGUI/examples disabled, `SMTG_CREATE_PLUGIN_LINK=OFF`, build output below `build/vst3`, one-job commands, and guard refusal at the existing memory/load/temperature/PSI boundaries.

  ```bash
  python3 -m unittest tests.test_vst3_build_contract tests.test_guarded_native_build -v
  ```

  Expected RED: root CMake and build guard are absent.

- [ ] **Step 2: Add the offline-only CMake skeleton.**

  The root begins with:

  ```cmake
  cmake_minimum_required(VERSION 3.25)
  project(M3PolyphonicAudioToMIDI VERSION 0.1.0 LANGUAGES C CXX)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)
  set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
  set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
  set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL "" FORCE)
  set(SMTG_ADD_VST3_UTILITIES OFF CACHE BOOL "" FORCE)
  set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)
  set(SMTG_RUN_VST_VALIDATOR OFF CACHE BOOL "" FORCE)
  add_subdirectory(third_party/vst3sdk ${CMAKE_BINARY_DIR}/sdk)
  include(cmake/M3CompilerOptions.cmake)
  ```

  Declare every project source explicitly. `cmake/M3Vst3Sdk.cmake` adds only the official validator and module-info utility subdirectories/targets needed by explicit validation targets; exclude them and every unrelated SDK target from the default build.

- [ ] **Step 3: Implement the stability build guard.**

  `tools/run_guarded_native_build.py --timeout SECONDS -- COMMAND...` must preflight at `4096 MiB` available, load `12.0`, temperature `90 C`, memory-full PSI `0.25`, and I/O-full PSI `2.0`; run `systemd-run --user --scope` with `MemoryHigh=1536M`, `MemoryMax=2048M`, `MemorySwapMax=256M`, `TasksMax=128`, and `CPUQuota=100%`; apply `nice 15`, idle I/O priority, a wall timeout, interrupt cleanup, and pre/post JSON. It rejects recursive invocation, package/network commands, `-j` values other than one, and paths outside this repository/build root.

- [ ] **Step 4: Convert `native/Makefile` into a thin wrapper.**

  Example target shape:

  ```make
  test:
	python3 $(ROOT)/tools/run_guarded_native_build.py --timeout 180 -- \
		cmake -S $(ROOT) -B $(BUILD_DIR)/debug -DCMAKE_BUILD_TYPE=Debug
	python3 $(ROOT)/tools/run_guarded_native_build.py --timeout 300 -- \
		cmake --build $(BUILD_DIR)/debug --target m3_native_tests -j1
	ctest --test-dir $(BUILD_DIR)/debug --output-on-failure
  ```

  Preserve target names `test`, `sanitize`, `tsan`, `probe`, `production`, `benchmark`, and `clean`; every non-clean target stays offline.

- [ ] **Step 5: Prove the existing baseline through CMake.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 -m unittest tests.test_vst3_build_contract tests.test_guarded_native_build -v
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: the same 44 native tests pass in normal and sanitizer builds; no `.vst3` is required yet; guard records remain under `build/test-results/native-build-guard`.

- [ ] **Step 6: Commit the build foundation.**

  ```bash
  git add CMakeLists.txt cmake native/Makefile tools/run_guarded_native_build.py tests/test_guarded_native_build.py tests/test_vst3_build_contract.py
  git commit -m "build: add guarded VST3 CMake foundation"
  ```

## Task 5: Extract the Format-Neutral Parameter Contract

**Files:**

- Create: `native/include/m3/parameter_contract.hpp`
- Create: `native/src/parameter_contract.cpp`
- Create: `native/plugin/{clap_parameter_bridge.hpp,clap_parameter_bridge.cpp}`
- Modify: `native/plugin/{parameter_contract.hpp,parameter_contract.cpp,clap_adapter.cpp}`
- Modify: `native/tests/test_parameter_contract.cpp`
- Create: `native/tests/test_parameter_normalization.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `PersistentConfig`, `Status`, existing sixteen-record CLAP behavior.
- Produces: the shared `ParameterSpec`, plain/normalized conversions, and `ParameterApplyResult` signatures above; CLAP flags/types remain only in `clap_parameter_bridge`.

- [ ] **Step 1: Write neutral table/normalization RED tests.**

  Assert IDs, order, names, exact ranges/defaults/increments, the sixteen VST3 step counts, fourteen persistent IDs, list/read-only/action classes, round-trip `plain -> normalized -> plain` at every endpoint and step, finite clamping, NaN/Inf rejection, one-based channel, and Status/Panic exclusion from state.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: neutral header/functions are absent.

- [ ] **Step 2: Implement one host-free constexpr table.**

  `canonical_plain()` clamps then rounds by `increment`; `plain_to_normalized()` uses `(plain-min)/(max-min)`; `normalized_to_plain()` clamps `[0,1]`, expands, then canonicalizes. Zero-span specifications are rejected by table tests. Text conversion writes only caller-provided buffers.

- [ ] **Step 3: Move CLAP mapping behind a bridge.**

  Map `ParameterSpec::list` to CLAP enum flags, nonzero `step_count` to stepped, Status to read-only, and all rows to non-automatable. Keep the public CLAP parameter IDs, formatted text, and 44-test behavior byte-for-byte. No neutral header includes `clap/`.

- [ ] **Step 4: Run the extraction gate and inspect includes.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  rg -n '#include <clap/' native/include/m3 native/src && exit 1 || true
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: all prior CLAP tests plus new normalization tests pass; neutral roots contain zero CLAP includes.

- [ ] **Step 5: Commit the parameter seam.**

  ```bash
  git add native/include/m3/parameter_contract.hpp native/src/parameter_contract.cpp native/plugin native/tests CMakeLists.txt
  git commit -m "refactor: extract format-neutral parameter contract"
  ```

## Task 6: Extract State Images from Host Stream Adapters

**Files:**

- Create: `native/include/m3/state_image.hpp`
- Create: `native/src/state_image.cpp`
- Create: `native/plugin/{clap_state_stream.hpp,clap_state_stream.cpp}`
- Modify: `native/plugin/{state_codec.hpp,state_codec.cpp,clap_adapter.cpp}`
- Modify: `native/tests/test_state_codec.cpp`
- Create: `native/tests/test_state_image.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: neutral parameter contract and exact existing 184-byte image.
- Produces: `encode_state`/`decode_state` with no host types; `save_clap_state`/`load_clap_state` preserve CLAP stream behavior.

- [ ] **Step 1: Write host-free image RED tests.**

  Require the exact default bytes/hash, all fourteen nondefault values, schema/magic/count/payload/CRC checks, ascending IDs, every truncation, trailing byte, duplicate/missing/unknown ID, NaN/Inf, and finite out-of-range canonicalization through the common parameter validator.

- [ ] **Step 2: Write CLAP bridge progress RED tests.**

  Require partial reads/writes to finish exactly 184 bytes and reject null callbacks, negative/zero progress, over-reported progress, premature end, and trailing data. Confirm a load mutates the destination only after complete decode.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: neutral image and named bridge do not exist.

- [ ] **Step 3: Move only byte encoding/decoding into neutral source.**

  Keep explicit little-endian helpers and IEEE CRC-32. Do not serialize C++ structs. `state_image.hpp` includes only `<array>`, `<cstddef>`, `<cstdint>`, and neutral headers.

- [ ] **Step 4: Wrap CLAP streams without changing the wire image.**

  Existing CLAP state callbacks call `save_clap_state(config, stream)` and `load_clap_state(stream, candidate)`. The latter publishes only after a complete neutral decode.

- [ ] **Step 5: Prove exact compatibility and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  rg -n 'clap_istream|clap_ostream|IBStream' native/include/m3 native/src && exit 1 || true
  git diff --check
  git add native CMakeLists.txt
  git commit -m "refactor: separate state image from host streams"
  ```

## Task 7: Extract the Generated-Note Delivery Ledger

**Files:**

- Create: `native/include/m3/generated_note_ledger.hpp`
- Create: `native/src/generated_note_ledger.cpp`
- Create: `native/tests/test_generated_note_ledger.cpp`
- Modify: `native/plugin/{midi_pipeline.hpp,midi_pipeline.cpp}`
- Modify: `native/tests/test_midi_pipeline.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `VoiceTransition`, fixed 128-pitch state, current CLAP output-failure tests.
- Produces: `GeneratedNoteLedger`, `NoteEventSink`, and `NoteDeliveryResult`; CLAP raw-MIDI passthrough/CC ordering remains local to `MidiPipeline`.

- [ ] **Step 1: Write neutral ordering and capacity RED tests.**

  Cover offsets `0` and `frames-1`, equal-time off-before-on, multiple 64-sample ticks, pitches 0/127, channels outside the ledger, maximum transition capacity `ceil(max_frames/64)*16+8`, overflow, duplicate on, stray off, release-all, and `max_frames` 0/16385 rejection.

- [ ] **Step 2: Write every sink-rejection RED case.**

  Reject each emitted event position in turn. Require rejected ons never become active; accepted/maybe-active pitches enter pending release; later note-ons are blocked; cleanup retries individual offs at offset zero in ascending pitch order; one bounded 128-pitch pass occurs per call; dry processing remains independent; recovery requires explicit Panic/reset followed by a later quiet finite supported call.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: neutral ledger is absent.

- [ ] **Step 3: Implement the fixed ledger and function-pointer sink.**

  Allocate transition storage only in `activate()`. Own two `std::array<std::uint64_t,2>` bitsets and fixed scalar state. `deliver()` calls only the supplied function pointer, never allocates, and treats a null sink as rejection when an event is due.

- [ ] **Step 4: Preserve the historical CLAP output contract.**

  Adapt `MidiPipeline` so generated note active/pending decisions use the neutral ledger while its raw input ordering and CC123/CC120 cleanup stay CLAP-only. Run the existing equal-offset, passthrough, every-push-failure, Panic, and allocation tests unchanged.

- [ ] **Step 5: Prove no heap work after activation and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 tools/validate_native_source.py .
  git add native CMakeLists.txt
  git commit -m "refactor: extract generated-note delivery ledger"
  ```

## Task 8: Prove VST3 Factory, Combined Lifecycle, Busses, and Dry Audio

**Gate N3:** Begin only after Tasks 5-7 preserve all existing tests and production VST3 target dependencies contain no CLAP source.

**Files:**

- Create: `native/vst3/{vst3_component.hpp,vst3_component.cpp,vst3_factory.cpp}`
- Create: `native/tests/{fake_vst3_host.hpp,fake_vst3_host.cpp,test_vst3_factory.cpp,test_vst3_lifecycle.cpp,test_vst3_audio.cpp}`
- Modify: `CMakeLists.txt`
- Modify: `tests/test_vst3_build_contract.py`

**Interfaces:**

- Consumes: official `SingleComponentEffect`, neutral dry path, locked FUIDs.
- Produces: `m3::vst3::M3Component`, factory entry, exact audio/event bus surface, setup/active/processing state machine, and zero-latency/tail reporting.

- [ ] **Step 1: Write the factory/lifecycle RED through `GetPluginFactory()`.**

  Assert one class for each selected build, exact FUID/name/vendor/version/category, `kVstAudioEffectClass`, `PClassInfo::kManyInstances`, no `kDistributable`, successful query of `IAudioProcessor` and `IEditController` on the same object, no separate controller class ID, and exactly-once initialize/terminate/destruction sequencing.

- [ ] **Step 2: Write bus/layout/sample-size RED tests.**

  Require one default-active stereo input/output, zero event inputs, one default-active sixteen-channel event output, paired stereo-only arrangements, float32 and float64 support, rejection of unknown sample size, zero latency, zero tail, and `createView(kEditor)==nullptr`.

- [ ] **Step 3: Write dry-path and invalid-layout RED tests.**

  Cover float32/float64, in-place/out-of-place, shared channel pointers, pass/mute, frames `1,32,64,128,256,512,16384`, zero-sample flush, null buses/channels, and NaN/Inf replacement. Finite pass-through is bit exact; non-finite input writes zero and latches invalid status; unsupported layout emits no note-on and keeps safely addressable dry output.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: factory/component sources are absent.

- [ ] **Step 4: Implement the smallest combined component.**

  Use this public shape:

  ```cpp
  class M3Component final : public Steinberg::Vst::SingleComponentEffect {
   public:
    static Steinberg::FUnknown* createInstance(void*) noexcept;
    Steinberg::tresult PLUGIN_API initialize(Steinberg::FUnknown*) override;
    Steinberg::tresult PLUGIN_API terminate() override;
    Steinberg::tresult PLUGIN_API setBusArrangements(
        Steinberg::Vst::SpeakerArrangement*, Steinberg::int32,
        Steinberg::Vst::SpeakerArrangement*, Steinberg::int32) override;
    Steinberg::tresult PLUGIN_API canProcessSampleSize(Steinberg::int32) override;
    Steinberg::uint32 PLUGIN_API getLatencySamples() override;
    Steinberg::uint32 PLUGIN_API getTailSamples() override;
    Steinberg::IPlugView* PLUGIN_API createView(Steinberg::FIDString) override;
  };
  ```

  `initialize()` calls the base once, adds the three busses, and registers no parameter yet. Factory selection is compile-time; production source/binary contains no probe/benchmark class ID.

- [ ] **Step 5: Arm allocation counters only after activation.**

  Fake-host tests permit allocation during construction/initialize/setup/activation and require zero `new/delete` in repeated `process()` and `setProcessing()` calls. No project source calls a host function from the processing thread except bounded process-data list methods added in later tasks.

- [ ] **Step 6: Build, inspect, and commit the lifecycle slice.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  cmake --build build/vst3/debug --target m3_vst3_probe -j1
  nm -D build/vst3/debug/VST3/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so
  python3 tools/validate_native_source.py .
  git add native/vst3 native/tests CMakeLists.txt tests/test_vst3_build_contract.py
  git commit -m "feat: add minimal VST3 lifecycle and bus adapter"
  ```

## Task 9: Implement Generic VST3 Parameters and Exact State

**Files:**

- Create: `native/vst3/{vst3_parameter_bridge.hpp,vst3_parameter_bridge.cpp,vst3_state_stream.hpp,vst3_state_stream.cpp}`
- Create: `native/tests/{test_vst3_parameters.cpp,test_vst3_state.cpp}`
- Modify: `native/vst3/vst3_component.hpp`
- Modify: `native/vst3/vst3_component.cpp`
- Modify: `native/tests/fake_vst3_host.hpp`
- Modify: `native/tests/fake_vst3_host.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: neutral `ParameterSpec`, normalization functions, `StateImage`, and official `IParameterChanges`/`IBStream` interfaces.
- Produces: sixteen generic parameters, bounded input/output parameter helpers, and byte-exact component/controller state synchronization.

- [ ] **Step 1: Write the exact parameter-info RED.**

  Through `IEditController`, require sixteen records in table order; exact IDs/titles/default normalized values; step counts `2,1,800,480,100,100,84,84,7,36,1,126,15,1,1,5`; `kIsList` only for Detector input, Mode, Velocity mode, Panic, Dry audio, and Status; `kIsReadOnly` only for Status; and no `kCanAutomate`, bypass, program, or hidden flag.

- [ ] **Step 2: Write conversion/edit RED cases.**

  Test every endpoint/step through `getParamStringByValue`, `getParamValueByString`, `normalizedParamToPlain`, `plainParamToNormalized`, and `setParamNormalized`. Reject unknown IDs, NaN/Inf, Status writes, malformed text, and non-canonical values. Panic accepts normalized `1`, publishes Ready back through output changes, and is not persistent.

- [ ] **Step 3: Write `IBStream` and state-sync RED cases.**

  Require default/all-nondefault images byte-identical to neutral/CLAP tests; partial read/write progress; null stream; failure result; zero, negative, or over-reported byte count; every truncation; trailing byte; bad image; and no partial mutation. `setState()` updates the processor request, `setComponentState()` synchronizes controller parameter objects without a component-handler callback, and `getState()` emits exactly 184 bytes.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: VST3 parameter/state bridges are absent.

- [ ] **Step 4: Register parameters from the neutral table.**

  Add one SDK `Parameter` per row during `initialize()`. Use the neutral normalized value and exact step count; copy UTF-8 names through Steinberg string helpers outside processing. Keep parameter ownership in the SDK `parameters` container and live plain configuration in the component.

- [ ] **Step 5: Implement bounded parameter-queue helpers.**

  Define:

  ```cpp
  struct ParameterBatch final {
    PersistentConfig candidate{};
    bool changed{};
    bool structural{};
    bool panic{};
  };

  bool read_last_boundary_values(
      Steinberg::Vst::IParameterChanges*, Steinberg::int32 num_samples,
      const PersistentConfig&, ParameterBatch&) noexcept;
  bool push_output_value(Steinberg::Vst::IParameterChanges*, ParameterId,
                         double normalized, Steinberg::int32 offset) noexcept;
  ```

  Iterate only the host-reported bounded queue/point counts, reject negative counts/offsets and non-finite values, retain the last valid point per known ID in host order, and apply at the call boundary rather than sample-accurately.

- [ ] **Step 6: Implement exact `IBStream` loops.**

  Each loop asks for at most the remaining bytes as `Steinberg::int32`, requires `kResultOk`/`kResultTrue` and progress in `(0, remaining]`, then performs one bounded extra-byte read to reject trailing content. Decode into a candidate and publish only after complete validation.

- [ ] **Step 7: Run and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 tools/validate_native_source.py .
  git diff --check
  git add native/vst3 native/tests CMakeLists.txt
  git commit -m "feat: add VST3 parameters and exact state"
  ```

## Task 10: Implement VST3 Note Delivery and Fail-Closed Cleanup

**Files:**

- Create: `native/vst3/{vst3_event_sink.hpp,vst3_event_sink.cpp}`
- Create: `native/tests/test_vst3_events.cpp`
- Modify: `native/vst3/vst3_component.hpp`
- Modify: `native/vst3/vst3_component.cpp`
- Modify: `native/tests/fake_vst3_host.hpp`
- Modify: `native/tests/fake_vst3_host.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `GeneratedNoteLedger`, VST3 `IEventList`, one-based configured channel.
- Produces: `Vst3EventSinkContext` and deterministic `NoteOnEvent`/`NoteOffEvent` encoding with exhaustive rejection recovery.

- [ ] **Step 1: Write exact event-encoding RED tests.**

  For pitches `0,32,60,84,127`, channels `1,16`, velocities `1,64,127`, and offsets `0,frames-1`, require bus index `0`, zero-based channel, `velocity/127.0f`, zero note-off velocity, tuning `0`, length `0`, and note ID `-1000-pitch` on both matching events. Reject pitch/channel/velocity/offset outside contract.

- [ ] **Step 2: Write ordering and no-input RED tests.**

  Equal-offset note-offs precede note-ons, pitch ordering is deterministic, multiple ticks retain transition sequence, and `ProcessData::inputEvents` is never read. Factory/bus tests still report zero event inputs.

- [ ] **Step 3: Inject every output-list failure.**

  Configure `FakeEventList::addEvent()` to reject each position. Require Status `MIDI Output Blocked`, later ons inhibited, accepted/maybe-active pitches retained, individual offs retried at offset zero in ascending pitch order, at most one 128-pitch retry pass per call, and dry audio unaffected. No CC, `LegacyMIDICCOutEvent`, `DataEvent`, MPE, note expression, or pitch bend is emitted.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: VST3 event sink is absent.

- [ ] **Step 4: Implement the sink as a neutral callback.**

  ```cpp
  struct Vst3EventSinkContext final {
    Steinberg::Vst::IEventList* events{};
    std::uint8_t one_based_channel{1};
  };

  bool push_vst3_note(void* context,
                      const VoiceTransition& transition) noexcept;
  ```

  Construct one zero-initialized `Steinberg::Vst::Event`, set only the approved note fields, and return true only when `addEvent()` returns `kResultOk`/`kResultTrue`.

- [ ] **Step 5: Prove allocation-free delivery and commit.**

  Arm allocation/deallocation counters after activation and run normal, null-output, and every-rejection paths for 100,000 bounded calls.

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 tools/validate_native_source.py .
  git add native/vst3 native/tests CMakeLists.txt
  git commit -m "feat: add fail-closed VST3 note delivery"
  ```

## Task 11: Implement Host-Rate Setup, Prepared Configuration, and Processing Lifecycle

**Files:**

- Create: `native/tests/{test_vst3_setup.cpp,test_vst3_processing.cpp,test_vst3_reconfiguration.cpp}`
- Modify: `native/vst3/vst3_component.hpp`
- Modify: `native/vst3/vst3_component.cpp`
- Modify: `native/vst3/vst3_parameter_bridge.cpp`
- Modify: `native/plugin/prepared_config_exchange.hpp`
- Modify: `native/plugin/prepared_config_exchange.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: host `ProcessSetup`, `AtomicConfigRequest`, `PreparedConfigExchange`, neutral ledger/dry path/parameters.
- Produces: complete inactive setup/activation/processing transitions and one bounded process-call sequence.

- [ ] **Step 1: Write host-authoritative sample-rate RED tests.**

  Require exact acceptance/preparation at `44100`, `48000`, `88200`, and `96000`, plus finite non-matrix rates `32000`, `50000`, and `192000` when coefficient preparation is finite. Reject `0`, negative, NaN, Inf, unsafe coefficients, `maxSamplesPerBlock` 0 or 16385, and setup while active. Assert the prepared sample rate equals the host value exactly and no resampler/rate parameter exists.

- [ ] **Step 2: Write lifecycle/reset RED tests.**

  Cover initialize, setup, active true, processing true, variable process blocks, processing false, active false, new rate setup, reactivation, terminate. `setProcessing(false)` moves every maybe-active note to pending, resets detector transients, blocks ons, emits nothing, and allocates nothing. The first call after `setProcessing(true)` retries offs at offset zero before detector work; pending bits survive `setActive(false)` while activation-sized transition storage is freed only inactive.

- [ ] **Step 3: Write process-call validation RED tests.**

  Cover realtime/prefetch/offline modes, float32/64, samples `0,1,32,64,128,256,512,16384`, changing block partitions, bus counts, channel counts, null pointers, aliasing, silence flags, parameter-only calls, output events absent, output parameter changes absent/rejecting, non-finite audio, and unsupported layouts. Require fixed 64-sample phase across calls and multiple ticks in a long block.

- [ ] **Step 4: Write prepared-generation RED tests.**

  `setParamNormalized()` and state load prepare structural values outside processing. `inputParameterChanges` determines the activation boundary. A matching prepared generation releases notes under the old channel, resets transients, adopts once, and frees the old slot. A missing generation latches Reconfiguring, retains the old config/dry path, releases reachable notes, and never prepares coefficients in `process()`.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: current component has no setup/processing implementation.

- [ ] **Step 5: Implement inactive setup and activation.**

  `setupProcessing()` validates `ProcessSetup`, calls `stage_prepared_config(requested, setup.sampleRate, initial)`, and stores the exact mode/sample size/max block. `setActive(true)` allocates transition capacity with checked arithmetic:

  ```text
  max_ticks = ceil(maxSamplesPerBlock / 64)
  max_transitions = max_ticks * 16 + 8 boundary note-offs
  ```

  It initializes the prepared exchange and ledger. Any overflow or allocation failure returns failure before active state.

- [ ] **Step 6: Implement the process sequence exactly once.**

  The method order is:

  1. validate setup/mode/sample-size/count/busses/channels/pointers;
  2. read and coalesce input parameter queues;
  3. retry pending releases at offset zero;
  4. release under the old channel and adopt a matching prepared generation;
  5. copy/mute/sanitize dry audio and select mono input;
  6. feed the selected samples to the current probe/test seam at 64-sample phase;
  7. deliver validated transitions to `outputEvents`; and
  8. publish dirty Status/Panic values through `outputParameterChanges`, retaining dirtiness after null/rejection.

  No component-handler, preparation, allocation, clock, file, log, or wait call occurs in this sequence.

- [ ] **Step 7: Run concurrency, sanitizer, and source gates.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  make -C native -j1 tsan
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: prepared exchange remains coherent through 100,000 generations, process/setProcessing allocate zero bytes, and TSan reports no race.

- [ ] **Step 8: Commit the processing lifecycle.**

  ```bash
  git add native/vst3 native/tests native/plugin/prepared_config_exchange.* CMakeLists.txt
  git commit -m "feat: complete bounded VST3 processing lifecycle"
  ```

## Task 12: Seal the Offline Adapter, Bundle, and Official Validator

**Files:**

- Create: `native/tests/{test_vst3_adversarial.cpp,test_vst3_realtime.cpp}`
- Create: `tools/run_vst3_validator.py`
- Create: `tests/test_vst3_validator_runner.py`
- Modify: `tests/test_vst3_build_contract.py`
- Modify: `tools/validate_native_source.py`
- Modify: `CMakeLists.txt`
- Modify: `docs/VST3-TESTING.md`

**Interfaces:**

- Consumes: complete adapter/fake host and official validator target.
- Produces: Gate O4 evidence for exact production/probe bundles, source/binary isolation, sanitizers, and validator outcome.

- [ ] **Step 1: Write adversarial RED tests.**

  With fixed seeds, run 100,000 bounded operations over parameter queue counts/offsets/values, state bytes length 0-256, bus/layout/sample formats, frames, event rejection positions, config generations, process modes, start/stop/active sequences, and non-finite samples. Require no crash, hang, out-of-bounds access, duplicate generated on, more than eight active notes, or retained active note after successful cleanup.

- [ ] **Step 2: Enforce the realtime/source RED contract.**

  After activation, run at least 100,000 `process()` and `setProcessing()` calls with allocation counters armed and `/proc/self/task` sampled before/after. Reject project production use of threads, mutexes, condition variables, futures, filesystem/iostream/stdio, networking, sleep/wait, exceptions, RTTI, recursive core functions, growable process containers, CLAP headers/symbols, probe/benchmark IDs, report environment variables, and test schedules.

- [ ] **Step 3: Write validator-runner result tests.**

  The runner requires `--kind production|probe`, accepts only the corresponding exact build-local bundle and FUID plus the official build-local validator, records command/tool/bundle/SDK hashes atomically, applies the native build guard, and classifies: exit 0 plus required checks as pass; validator assertion/plugin diagnostic as fail; validator crash, sanitizer runtime failure, or environment error as infrastructure-invalid. No classification automatically retries.

- [ ] **Step 4: Build exact bundles and inspect structure.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  make -C native -j1 production
  make -C native -j1 probe
  find build/vst3/release/VST3 -maxdepth 5 -type f -printf '%P\n' | LC_ALL=C sort
  ```

  Require each Linux bundle to contain its same-named `.so` under `Contents/x86_64-linux/` and `Contents/Resources/moduleinfo.json`; production exposes exactly production FUID/name/category and contains no probe/benchmark marker.

- [ ] **Step 5: Run the official validator once offline.**

  ```bash
  python3 tools/run_vst3_validator.py --kind production --bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
  ```

  Expected GREEN: factory/class/bus/parameter/state/process tests pass. An infrastructure-invalid result stops Gate O4 and is recorded without claiming plug-in failure or success.

- [ ] **Step 6: Prove reproducible production bundles.**

  ```bash
  epoch="$(git log -1 --format=%ct)"
  SOURCE_DATE_EPOCH="$epoch" make -C native BUILD_DIR="$PWD/build/repro-a" -j1 production
  SOURCE_DATE_EPOCH="$epoch" make -C native BUILD_DIR="$PWD/build/repro-b" -j1 production
  diff -qr build/repro-a/VST3/M3_Polyphonic_Audio_to_MIDI.vst3 build/repro-b/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
  ```

  Record compiler, flags, SDK manifest digest, module-info hash, `.so` hash, and full bundle manifest in `docs/VST3-TESTING.md`.

- [ ] **Step 7: Commit the offline adapter seal.**

  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_native_source.py .
  git diff --check
  git add native/tests tools/run_vst3_validator.py tests/test_vst3_validator_runner.py tests/test_vst3_build_contract.py tools/validate_native_source.py CMakeLists.txt docs/VST3-TESTING.md
  git commit -m "test: seal offline VST3 adapter and validator"
  ```

## Task 13: Extend Disposable Staging and Guards for VST3

**Files:**

- Modify: `tools/run_guarded_reaper.py`
- Modify: `tools/stage_reaper_test_env.py`
- Modify: `tests/test_guarded_reaper.py`
- Modify: `tests/test_source_contract.py`
- Create: `tools/run_native_vst3_probe.py`
- Create: `tests/test_native_vst3_probe_runner.py`

**Interfaces:**

- Consumes: exact build-local probe bundle and existing workspace-5 systemd guard.
- Produces: VST3-only disposable profile staging and the exact twenty-row fail-closed schedule.

- [ ] **Step 1: Write VST3 path/isolation RED tests.**

  Require the resolved probe bundle below `build/vst3/release/VST3`, matching module-info and binary, no symlink escape, the exact disposable profile, no existing REAPER PID, no live-profile path, and no simultaneous CLAP/VST3 injection. The disposable `reaper.ini` alone receives a VST scan path containing only the build-local VST3 root.

- [ ] **Step 2: Write the exact matrix RED.**

  ```python
  SAMPLE_RATES = (44100, 48000, 88200, 96000)
  BLOCK_SIZES = (32, 64, 128, 256, 512)
  MATRIX = tuple((rate, block) for rate in SAMPLE_RATES for block in BLOCK_SIZES)
  ```

  Assert twenty commands in that order, one fresh profile/project/process per row, workspace 5, background/nonactivate flags, 50% CPU, 384/512 MiB memory, 64 MiB swap, 64 tasks, bounded CPU/wall time, and no retry. `--check` and `--dry-run` never stage or launch.

- [ ] **Step 3: Write immutable result/recovery RED tests.**

  Require rate/block, probe/source/script/guard/stager/bundle/module-info hashes, complete phase sentinel, before/after pressure, process return status, and all expected TSVs. Interrupted staging and `.pending` directories are atomically renamed with `.invalid-TIMESTAMP`; a changed hash invalidates a completed row; the first invalid/fail/timeout/pressure abort prevents every later row.

- [ ] **Step 4: Generalize the existing guard without weakening CLAP history.**

  Add mutually exclusive VST3 arguments, exact path validation, and disposable-profile scan configuration. Preserve every current CLAP test and guard limit. Never override `HOME`, touch the live profile, attach to an existing process, or move/hide a pre-existing REAPER window.

- [ ] **Step 5: Implement non-launching runner modes.**

  `planned_guard_commands()` enumerates `MATRIX`; `run_matrix()` checks prior immutable rows, executes only the first unfinished row, validates it, then continues only after a pass. Default real execution remains behind Gate C5; `--dry-run` prints commands and `--check` validates evidence only.

- [ ] **Step 6: Run non-launching tests and commit.**

  ```bash
  python3 -m unittest tests.test_guarded_reaper tests.test_source_contract tests.test_native_vst3_probe_runner -v
  python3 tools/run_native_vst3_probe.py --dry-run
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  git add tools/run_guarded_reaper.py tools/stage_reaper_test_env.py tools/run_native_vst3_probe.py tests/test_guarded_reaper.py tests/test_source_contract.py tests/test_native_vst3_probe_runner.py
  git commit -m "test: guard build-local VST3 host matrices"
  ```

## Task 14: Build the Disposable Audio-Triggered VST3 Capability Probe

**Files:**

- Create: `native/vst3/{vst3_probe_processor.hpp,vst3_probe_processor.cpp}`
- Create: `native/tests/test_vst3_probe.cpp`
- Create: `Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx`
- Create: `Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua`
- Modify: `tools/stage_reaper_test_env.py`
- Modify: `tests/test_source_contract.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: production adapter seams and probe FUID; stereo audio only.
- Produces: deterministic two-phase notes, held-note lifecycle phase, bounded diagnostics, and REAPER assertions without event input or MIDI trigger.

- [ ] **Step 1: Write the offline audio-trigger RED.**

  Feed silence, first signed stereo pulse code, separator silence, second pulse code, and malformed/overflow patterns. Require phase one to emit a complete on/off pair; phase two to emit a held on awaiting stop/Panic; malformed input to emit nothing and latch fault; identical behavior at the four named rates and five block partitions; and no input-event access.

- [ ] **Step 2: Implement the test-only processor.**

  Recognize bounded amplitude/polarity sequences from selected audio samples at the fixed 64-sample cadence. Own no file I/O in `process()`. Store create/init/setup/active/start/process/stop/deactivate/destroy counters, float32/64, alias/separate, rate, block, trigger counts, and overflow in fixed atomics; publish through read-only probe parameters or state queried after processing, not an environment report written by the callback.

- [ ] **Step 3: Write the JSFX source contract.**

  The source generates finite stereo audio phases and a reference dry signal only. Source validation rejects every `midisend`, `midirecv`, file/network call, unbounded loop, and writable path. It records phase/sample progress in slider telemetry for the disposable script.

- [ ] **Step 4: Write the ReaScript assertions.**

  The script must:

  - discover exactly the probe build by FX name/type and confirm `is_instrument=0`;
  - enumerate host parameters, call `TrackFX_GetParamIdent`/`TrackFX_GetParamFromIdent`, and map the sixteen plug-in parameters by stable ID/name without requiring total host parameter count 16;
  - verify names, defaults, steps, formatted values, writes/restores, read-only Status, momentary Panic, and fourteen persistent values across a project-state round trip;
  - verify stereo dry pass/mute, finite output, two audio-triggered note phases, exact channel/velocity/order, and positive downstream synth output;
  - hold a note across stop/restart and verify its off precedes any resumed on;
  - repeat held-note cleanup for bypass/deactivation and observe downstream silence after probe deletion; and
  - publish `suite-finish` only after zero assertion failures and then close only the disposable process.

- [ ] **Step 5: Prove production isolation and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 probe
  strings build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so | rg 'Probe|6F62F8B1|audio-trigger' && exit 1 || true
  python3 -m unittest tests.test_source_contract -v
  python3 tools/validate_native_source.py .
  git add native/vst3 native/tests 'Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx' 'Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua' tools/stage_reaper_test_env.py tests/test_source_contract.py CMakeLists.txt
  git commit -m "test: add audio-triggered VST3 capability probe"
  ```

## Task 15: Execute and Seal the Twenty-Row VST3 Capability Gate

**Gate C5:** Stop until Gate O4 is green and the user explicitly authorizes exactly twenty guarded disposable REAPER launches. Offline success and prior general authorization do not open this gate.

**Files:**

- Modify after evidence: `docs/VST3-TESTING.md`
- Modify after evidence: `RESUME.md`
- Evidence only: `build/test-results/native-vst3-probe/batches/**`

**Interfaces:**

- Consumes: exact probe bundle, script/source hashes, guarded runner.
- Produces: one immutable pass/fail/invalid capability decision before any detector port.

- [ ] **Step 1: Re-run every non-launching gate immediately before authority.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  make -C native -j1 probe
  python3 tools/run_vst3_validator.py --kind probe --bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI_Probe.vst3
  python3 -m unittest tests.test_guarded_reaper tests.test_native_vst3_probe_runner -v
  python3 tools/run_native_vst3_probe.py --dry-run
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  ```

  Expected: exact twenty-row schedule and no REAPER process. Any failure returns to the responsible offline task and consumes no launch authority.

- [ ] **Step 2: Capture a fresh stability preflight.**

  Require at least 4096 MiB available, load at most 12, temperature below 90 C, memory-full PSI below 0.25, I/O-full PSI below 2.0, workspace 5 present, disposable profile/path validation, and no REAPER PID/window. Preserve the snapshot before the first row.

- [ ] **Step 3: Execute the matrix once.**

  ```bash
  python3 tools/run_native_vst3_probe.py
  ```

  The runner begins at 44.1 kHz/block 32 and stops immediately after the first invalid, timeout, pressure abort, guard refusal, crash, or failed assertion. It never retries or skips to another rate/block.

- [ ] **Step 4: Validate all required capability evidence.**

  For a pass, require twenty complete rows with exact hashes and zero failures; discovery; busses; float32/64 support (float64 may be proven offline if REAPER supplies only float32); dry pass/mute; parameter/state/Panic/Status behavior; two audio-trigger phases; held-note stop/restart and bypass/deactivation cleanup; deletion downstream cleanup; zero PDC; finite positive synth output; and no lingering REAPER process/window or active-workspace change.

- [ ] **Step 5: Seal pass, fail, or infrastructure-invalid state.**

  Record every launched row, unlaunched tail, hashes, pressure extrema, exact failure labels, and one decision in `docs/VST3-TESTING.md`/`RESUME.md`. A failed/invalid matrix blocks Task 16; it does not authorize an adapter edit or retry.

  ```bash
  python3 tools/run_native_vst3_probe.py --check
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  git add docs/VST3-TESTING.md RESUME.md
  git commit -m "test: seal VST3 capability gate"
  ```

## Task 16: Port Configuration, Pitch Math, and Input Conditioning

**Files:**

- Modify: `native/include/m3/{types.hpp,pitch_math.hpp}`
- Create: `native/include/m3/conditioning.hpp`
- Create: `native/src/conditioning.cpp`
- Create: `native/tests/{test_config.cpp,test_conditioning.cpp}`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: `PersistentConfig`, host rate from prepared setup, frozen JSFX conditioning formulas.
- Produces: finite `PreparedConfig`, `RuntimeControls`, and allocation-free `Conditioner` used by every detector module.

- [ ] **Step 1: Write configuration/rate RED tests.**

  Cover every endpoint/default/step, reversed General bounds, M3 effective bounds 32-84, maximum eight voices, A4 400/440/480, channels 1/16, exact rates 44.1/48/88.2/96 kHz, finite non-matrix rates 32/50/192 kHz, and rejection of zero/negative/NaN/Inf or any rate producing non-finite coefficients. Test equal-power downmix `(left+right)*0.7071067811865476`.

- [ ] **Step 2: Write conditioner vector RED tests.**

  Use fixed silence, DC, impulse, sine, clipping, subnormal, NaN, and Inf sequences. Compare DC-block, fast/slow energy, noise floor, peak, and clip envelope at every sample to the EEL2 equations with absolute tolerance `1e-12` and relative tolerance `1e-9`.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: conditioner and complete config preparation are absent.

- [ ] **Step 3: Implement pure bounded preparation.**

  Keep requested config separate from derived runtime/prepared values. Clamp only documented ranges, order General bounds, force effective M3 bounds, compute trim gain and all rate-derived finite coefficients, and return typed error. Trim reaches a new detector-only gain linearly over exactly 64 samples; dry audio is unchanged.

- [ ] **Step 4: Port conditioning without retuning.**

  Preserve 15 Hz DC pole, 5 ms fast energy, 100 ms slow energy, 2 s noise rise, 250 ms peak/clip release, `1e-12` floor, and `0.999` clip threshold. Non-finite selected input becomes zero and latches invalid state.

- [ ] **Step 5: Run all four named rates and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 tools/validate_native_source.py .
  git add native CMakeLists.txt
  git commit -m "feat: port host-rate configuration and conditioning"
  ```

## Task 17: Port the Prepared Multi-Rate Resonator Bank

**Files:**

- Create: `native/include/m3/resonator_bank.hpp`
- Create: `native/src/resonator_bank.cpp`
- Create: `native/tests/{test_resonator_bank.cpp,resonator_reference.hpp}`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: finite `PreparedConfig`, conditioned detector sample, 87-candidate/eight-harmonic capacities.
- Produces: immutable prepared resonator coefficients and mutable allocation-free `ResonatorBank` energies/counters.

- [ ] **Step 1: Write preparation RED tests at all four release rates.**

  Assert one guard semitone per available edge within 87 candidates, harmonic counts by pitch, Nyquist/cutoff exclusion, four rate levels, exact two-stage Butterworth coefficients, enabled-cell counts, finite unit rotations, and A4 400/440/480 at `44100`, `48000`, `88200`, and `96000`. Add 50 kHz as a non-matrix host-rate preparation case.

- [ ] **Step 2: Write full-rate reference and multi-rate parity RED tests.**

  Keep the reference bank in test code only. Translate cases 4101-4106 and 6101-6106: guard-edge tuning, open-string local peaks, enabled/update counters, bounded renormalization, alias probes, and worst open-string salience delta at most `0.03` at all four release rates.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: resonator bank is absent.

- [ ] **Step 3: Prepare every coefficient outside processing.**

  Extend `PreparedConfig` with fixed enabled masks, rate assignments, rotations, decay/filter coefficients, requested/effective bounds, and cell counts. `ResonatorBank` owns only fixed mutable cosine/sine/fast/slow/filter state. Reject any non-finite coefficient before activation.

- [ ] **Step 4: Port the current optimized bank exactly.**

  Preserve the `sr`, `sr/2`, `sr/4`, `sr/8` streams; two cascaded second-order low-pass stages at normalized cutoff `0.20`; assignment threshold `0.16`; low-rate promotion; adaptive partial counts six through MIDI 52, four through 75, three above; guard-note three-partial rule; update ceiling; and bounded renormalization. Do not vectorize.

- [ ] **Step 5: Prove bounded work, rate coverage, and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 tools/validate_native_source.py .
  git add native CMakeLists.txt
  git commit -m "feat: port multi-rate harmonic resonator bank"
  ```

  Expected GREEN: reference/parity cases pass at 44.1/48/88.2/96 kHz, no callback allocation occurs, and the 48 kHz MIDI 32-84 point remains at or below 45 cell updates per input sample.

## Task 18: Port Harmonic Salience and Bounded Polyphonic Selection

**Files:**

- Create: `native/include/m3/salience_selector.hpp`
- Create: `native/src/salience_selector.cpp`
- Create: `native/tests/{test_salience.cpp,test_selector.cpp}`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: fixed resonator energies, noise/clip telemetry, prepared candidate metadata.
- Produces: at most sixteen deterministic internal selections and at most eight public voices without heap work.

- [ ] **Step 1: Write salience formula RED cases.**

  Cover harmonic weights, candidate energy, true-fundamental contribution, noise-adaptive threshold, clipping, missing fundamentals, shared partials, octave/fifth parents, quiet low notes, and edge candidates with explicit fixed arrays. Invalid energy/score fails closed and marks invalid state.

- [ ] **Step 2: Write selector RED cases matching 5101-5106.**

  Include one fundamental, octave competition, missing fundamental, shared fifth, eight M3 opens, candidate-limit behavior, deterministic score-then-ascending-pitch ties, zero candidates, sixteen internal candidates, and eight public voices.

- [ ] **Step 3: Write adversarial boundary RED tests.**

  For candidate counts `0,1,53,85,87` and notes 0/127, feed negative, zero, subnormal, huge finite, NaN, and Inf values. Require bounded iteration, no duplicate note, no out-of-range parent/root access, no more than sixteen internal/eight public results, and explicit overflow failure.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: salience/selection interfaces are absent.

- [ ] **Step 4: Port scoring and selection in source order.**

  Preserve harmonic accumulation, effective threshold, smoothed/raw energy, shared-partial downweighting, General octave aliases, missing-fundamental lower aliases/parents, residual attenuation `0.18`, fundamental-protection ratio `0.35`, and existing acquisition smoothing. Use fixed structure-of-arrays storage and explicit insertion ordering; do not call a library sort.

- [ ] **Step 5: Verify numeric and allocation parity, then commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  git add native CMakeLists.txt
  git commit -m "feat: port harmonic salience and polyphonic selection"
  ```

  Expected GREEN: fixed formulas match at `1e-12` absolute / `1e-9` relative tolerance and selection allocates zero bytes.

## Task 19: Port M3 Feasibility and Voice Lifecycle

**Files:**

- Create: `native/include/m3/{m3_profile.hpp,lifecycle.hpp}`
- Create: `native/src/{m3_profile.cpp,lifecycle.cpp}`
- Create: `native/tests/{test_m3_profile.cpp,test_lifecycle_generic.cpp,test_lifecycle_m3.cpp}`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: selected candidates, M3 open notes `32,36,40,44,48,52,56,60`, runtime response/velocity controls.
- Produces: distinct-string feasible voices and ordered `TickTransitions` from 128 fixed per-pitch lifecycle cells.

- [ ] **Step 1: Write tuning/mask/feasibility RED tests.**

  For maximum fret `0,1,12,24,36`, assert exact playable-string masks, duplicate pitch classes, 32/84 boundaries, unplayable notes, all eight opens, maximum-weight distinct-string subset, deterministic ties, open-chord preference, fret penalties, empty input, and 16-to-8 reduction matching cases 7101-7106.

- [ ] **Step 2: Write generic lifecycle/velocity RED tests.**

  Cover response `0,25,50,100` at 44.1/48/88.2/96 kHz with nearest-sample rounding; fixed velocity `1,100,127`; dynamic floor/ceiling; zero off velocity; off/attack/on/release/off; interrupted attack; dropout bridge; reacquisition; replacement off-before-on; duplicate prevention; release-all; event overflow; and absolute-sample wrap protection. Require block-partition invariance for `32,64,128,256,512` and irregular partitions.

- [ ] **Step 3: Write M3 lifecycle RED tests matching 8101-8111.**

  Cover low G-sharp admission, fast/guarded/high open attacks, low-chord delay, octave/parent confirmation, mature/multiple-parent alias blocking, adjacent-open chromatic shadows, low-string conflicts, high-open context, stale attacks, and attack-energy admission. For every open note include adjacent semitones, octave/fifth parents, maximum-fret edge, single, dyad, four-note, and eight-note contexts.

  ```bash
  make -C native -j1 test
  ```

  Expected RED: profile/lifecycle modules are absent.

- [ ] **Step 4: Implement the fixed distinct-string dynamic program.**

  Use two fixed 256-state rows keyed by the used-string mask and fixed predecessor codes; no recursion. If a set is infeasible, remove the lowest-confidence selection with stable compaction and retry at most eight times. General mode bypasses only this filter and retains the eight-voice cap.

- [ ] **Step 5: Implement 128 fixed lifecycle cells without retuning.**

  Use `std::uint64_t` absolute processed-sample counters and ordered subtraction. Copy existing project-owned JSFX constants/formulas exactly; emit through `TickTransitions` with explicit overflow failure. Threshold changes require a separate evidence-backed amendment.

- [ ] **Step 6: Run all rates/partitions and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  git add native CMakeLists.txt
  git commit -m "feat: port M3 feasibility and note lifecycle"
  ```

## Task 20: Assemble the Detector Core and Prove Four-Rate Correctness

**Files:**

- Create: `native/include/m3/detector_core.hpp`
- Create: `native/src/detector_core.cpp`
- Create: `native/tests/{test_detector_core.cpp,synthetic_source.hpp,synthetic_source.cpp,test_jsfx_parity.cpp,test_native_synthetic.cpp}`
- Create: `tools/run_native_vst3_matrix.py`
- Create: `tools/summarize_native_vst3_results.py`
- Create: `tests/test_native_vst3_results.py`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: all detector modules, frozen JSFX TSV oracle, exact synthetic formulas.
- Produces: `DetectorCore` with fixed 64-sample production cadence, test-only legacy schedule, four-rate correctness/latency evidence, and block-segmentation-invariant transitions.

- [ ] **Step 1: Write cadence RED tests independent of pitch.**

  With a counting decision seam, prove reset phase zero; decisions after samples 64/128 at zero-based offsets 63/127; continuity across `1x128`, `2x64`, `4x32`, `2x512`, and `17+47+3+61`; no early tick; multiple long-block ticks; and capacity bounds. Only `M3_TESTING` exposes `TestDecisionSchedule::jsfx_block_boundary_128`; production symbols/source reject it.

- [ ] **Step 2: Compose the real per-sample/tick pipeline.**

  Per sample: trim, condition, update bank, accumulate interval peak. Per tick: score, select, apply M3 feasibility, advance lifecycle, append transitions. Silence drives normal release. Any internal non-finite/overflow invariant returns failure, latches invalid state, and requests release.

- [ ] **Step 3: Write block-segmentation RED tests.**

  Feed byte-identical audio at each release rate through block sizes `32,64,128,256,512` and irregular partitions. Require identical absolute note/type/velocity sequences; per-block offsets equal `absolute_sample - block_start`; sample rate never changes inside the core.

- [ ] **Step 4: Reproduce and verify synthetic input formulas.**

  Match existing phase, harmonic amplitude, detune, missing-fundamental, gain, noise, hum, clipping, stagger, on duration, and release formulas with a recorded fixed PRNG algorithm/seed. Compare waveform checkpoints before using metrics. Parsers reject malformed/stale/missing/extra rows and publish checkpoints atomically.

- [ ] **Step 5: Prove legacy-128 translation parity.**

  For the 45 frozen M3 rows, require exact pitch/type order, zero duplicates/hangs, velocity difference at most one, and onset/release within one 128-sample interval of frozen events. Module checkpoints retain `1e-12` absolute / `1e-9` relative tolerance. Fix translation defects at their module tests; do not retune.

- [ ] **Step 6: Run production-64 offline acceptance at all four rates.**

  ```bash
  make -C native -j1 test
  python3 tools/run_native_vst3_matrix.py --offline --output build/test-results/native-vst3-offline
  python3 tools/summarize_native_vst3_results.py --input build/test-results/native-vst3-offline --check
  ```

  Require 45 M3 cases/124 notes at precision=recall=F1 `1.0`; broader clean synthetic precision/recall at least `0.98`; zero duplicate/hanging/silence events; applicable module/lifecycle cases at 44.1/48/88.2/96 kHz; and no MIDI 44 in the known 96 kHz 32+56 regression. Failure is a hard detector blocker.

- [ ] **Step 7: Enforce approved latency before adapter assembly.**

  At 48 kHz require open-string median/P95 at most `25/45 ms` and three/four-note completion median/P95 at most `40/65 ms`, measured causally from source onset. Keep zero lookahead and zero declared latency. Do not relax metrics or cadence.

- [ ] **Step 8: Run the full offline gate and commit.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_native_source.py .
  git add native tools/run_native_vst3_matrix.py tools/summarize_native_vst3_results.py tests/test_native_vst3_results.py CMakeLists.txt
  git commit -m "test: establish four-rate native detector correctness"
  ```

## Task 21: Assemble and Seal the Production VST3 Effect Offline

**Files:**

- Modify: `native/vst3/{vst3_component.hpp,vst3_component.cpp,vst3_factory.cpp}`
- Create: `native/tests/{test_vst3_production.cpp,test_vst3_production_realtime.cpp}`
- Modify: `tests/test_vst3_build_contract.py`
- Modify: `tools/validate_native_source.py`
- Modify: `docs/VST3-TESTING.md`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: proven adapter seams plus `DetectorCore`.
- Produces: exact production bundle with end-to-end fake-host behavior, real-time seal, validator pass, and reproducible hash.

- [ ] **Step 1: Write end-to-end fake-host RED tests.**

  Instantiate production through `GetPluginFactory`, set up each release rate and every block size, feed stereo synthetic audio and boundary parameter queues, and verify dry samples, generated VST3 notes, parameters/status, state, structural reconfiguration, Panic, stop/restart, deactivate/reactivate, and teardown for float32/64 and alias/separate buffers.

- [ ] **Step 2: Write status priority/recovery RED tests.**

  Require visible priority: Unsupported Layout, Invalid Input or State, MIDI Output Blocked, Reconfiguring, Panic Hold, Ready. A lower-priority recovery cannot clear a higher latch. Explicit Panic/reset plus a later complete quiet finite supported call is required after blocked output.

- [ ] **Step 3: Replace the probe seam with `DetectorCore`.**

  Preserve the Task 11 process order. Feed sanitized selected audio to `DetectorCore::process_sample`; stage every transition in activation-sized storage; use the neutral ledger/VST3 sink; publish bounded telemetry/status. Production target excludes probe/benchmark processors and IDs at both source and binary levels.

- [ ] **Step 4: Run adversarial and real-time gates.**

  After activation, execute 100,000 dense eight-voice process calls with allocation/deallocation/thread/unsafe-host counters armed. Require no owned thread, no heap operation, no invalid offset/event, no duplicate on, at most eight active notes, and successful cleanup. Run normal, ASan/UBSan, and TSan builds under the build guard.

- [ ] **Step 5: Build, validate, reproduce, and inspect production.**

  ```bash
  make -C native -j1 test
  make -C native -j1 sanitize
  make -C native -j1 tsan
  make -C native -j1 production
  python3 tools/run_vst3_validator.py --kind production --bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
  strings build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so | rg 'Probe|Benchmark|6F62F8B1|28713895|CLAP' && exit 1 || true
  ```

  Repeat the Task 12 two-root reproducibility comparison and record exact bundle/source/SDK hashes.

- [ ] **Step 6: Commit the offline production seal.**

  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_native_source.py .
  git diff --check
  git add native/vst3 native/tests tests/test_vst3_build_contract.py tools/validate_native_source.py docs/VST3-TESTING.md CMakeLists.txt
  git commit -m "feat: assemble native VST3 audio-to-MIDI effect"
  ```

## Task 22: Run Production Correctness and Lifecycle in Guarded REAPER

**Gate N6:** Stop until every Task 20-21 offline gate is green and the user explicitly authorizes the guarded production-host matrix.

**Files:**

- Modify minimally: `Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua`
- Create: `Scripts/tests/ajuntanaga_M3 Native VST3 Test Wrapper.lua`
- Modify: `tools/run_native_vst3_matrix.py`
- Modify: `tests/test_run_synthetic_matrix.py`
- Modify: `tests/test_native_vst3_results.py`
- Modify after evidence: `docs/VST3-TESTING.md`
- Modify after evidence: `RESUME.md`
- Evidence only: `build/test-results/native-vst3-host/**`

**Interfaces:**

- Consumes: exact production bundle and existing shared synthetic runner.
- Produces: guarded REAPER correctness/lifecycle evidence at four rates/five blocks with no persistent installation.

- [ ] **Step 1: Select the native effect without changing JSFX defaults.**

  Keep the shared runner's default JSFX name. The wrapper sets the detector to `VST3: M3 Polyphonic Audio to MIDI` and invokes the shared runner. Add a regression that the unwrapped runner remains byte-identical in detector selection.

- [ ] **Step 2: Extend immutable host batches.**

  Use at most eight cases per launch, exact rate/block grouping, atomic checkpoints, invalid-batch archival, process cleanup, pressure snapshots, completion sentinel, and current production bundle/module-info/source/runner hashes. The matrix is serial and stops at first failure; no retry.

- [ ] **Step 3: Run non-launching preparation.**

  ```bash
  make -C native -j1 test
  make -C native -j1 production
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/run_native_vst3_matrix.py --host --dry-run --output build/test-results/native-vst3-host
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  ```

  Expected: exact serial 44.1/48/88.2/96 kHz by 32/64/128/256/512 schedule and no process.

- [ ] **Step 4: Execute once after approval.**

  ```bash
  python3 tools/run_native_vst3_matrix.py --host --output build/test-results/native-vst3-host
  ```

  The guard refuses pressure/thermal/load/existing-process/path/workspace faults and never attaches to a user session.

- [ ] **Step 5: Apply production acceptance.**

  Require 45/124 M3 precision=recall=F1 `1.0`; broader precision/recall at least `0.98`; no duplicates/hangs/silence event; no 96 kHz false MIDI 44; approved 48 kHz latency; exact note ordering/channel/velocity; parameter/state/Panic/reconfiguration; stop/restart/bypass/deactivation cleanup; dry identity/mute; positive downstream VSTi output; zero PDC; and all four rate/five block dimensions represented.

- [ ] **Step 6: Record cleanup and commit host evidence summary.**

  ```bash
  python3 tools/run_native_vst3_matrix.py --host --check --output build/test-results/native-vst3-host
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  git add 'Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua' 'Scripts/tests/ajuntanaga_M3 Native VST3 Test Wrapper.lua' tools/run_native_vst3_matrix.py tests/test_run_synthetic_matrix.py tests/test_native_vst3_results.py docs/VST3-TESTING.md RESUME.md
  git commit -m "test: verify native VST3 effect in guarded REAPER"
  ```

## Task 23: Measure and Seal Four-Rate Deadline Performance

**Gate P7:** Stop until Task 22 is green and the user explicitly authorizes the benchmark matrix. Timing instrumentation is test-only and never linked into production.

**Files:**

- Create: `native/bench/vst3_benchmark_main.cpp`
- Create: `native/vst3/{vst3_benchmark_recorder.hpp,vst3_benchmark_recorder.cpp}`
- Create: `Scripts/tests/ajuntanaga_M3 Native VST3 Benchmark.lua`
- Create: `tools/run_native_vst3_benchmarks.py`
- Create: `tests/test_native_vst3_benchmarks.py`
- Modify: `tools/run_guarded_reaper.py`
- Modify: `tests/test_guarded_reaper.py`
- Create: `docs/VST3-PERFORMANCE.md`
- Modify after evidence: `RESUME.md`
- Modify: `CMakeLists.txt`

**Interfaces:**

- Consumes: benchmark-only FUID, exact production source graph, dense eight-note source.
- Produces: offline/host callback deadline fractions with production isolation and a pass/fail/amendment decision.

- [ ] **Step 1: Write the timing-seam RED contract.**

  `M3_VST3_BENCHMARK` wraps the complete component `process()` call with monotonic sampling and stores durations in activation-sized memory. It never writes/logs in process. The main thread exports after deletion to one guard-validated build result path. Production source/binary tests reject the benchmark FUID, macro, clock call, report path/environment string, and recorder symbols.

- [ ] **Step 2: Run bounded offline timing first.**

  Feed dense eight-note M3 audio for 256 warm-up plus 10,000 measured blocks at every four-rate/five-block row. Compute median/P95/P99/max deadline fractions. If any call reaches 50%, stop before REAPER; do not optimize/retry automatically. A vector kernel is allowed only through a separately amended task with byte-identical MIDI and numeric parity evidence.

- [ ] **Step 3: Write result-validator RED tests.**

  Reject missing/duplicate rows, wrong rate/block/view, too few blocks, NaN/Inf/negative duration, stale hashes, unordered times, P99 at or above `0.25`, any callback at or above `0.50`, dry discontinuity, out-of-block event offset, non-guarded process, or lingering REAPER PID.

- [ ] **Step 4: Dry-run the exact guarded schedule.**

  Each row measures generic UI closed then open, 256 warm-up plus 2,000 blocks per view. Two independent final 48 kHz/block 128 launches measure 10,000 total blocks each, split equally closed/open. All launches remain serial, disposable, workspace 5/background/nonactivate, and under existing limits.

  ```bash
  make -C native -j1 benchmark
  python3 tools/run_native_vst3_benchmarks.py --dry-run
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  ```

- [ ] **Step 5: Execute once after approval and stop on first hard failure.**

  ```bash
  python3 tools/run_native_vst3_benchmarks.py
  ```

  A callback at or above 50%, pressure abort, crash, invalid result, or cleanup fault preserves partial evidence and ends the experiment. No later row or retry runs.

- [ ] **Step 6: Apply and record the complete gate.**

  Require every 44.1/48/88.2/96 kHz by 32/64/128/256/512 closed/open row to have P99 below 25%, no callback at/above 50%, no dry delay/discontinuity/corruption, and ordered in-block notes; both long 48/128 captures also pass. Re-run full offline correctness hashes after timing build choice.

  `docs/VST3-PERFORMANCE.md` records distributions, counts, hashes, pressure, UI state, failures, and exactly one decision: `performance-ready pending clean DI`, `native amendment required`, or `unavailable due to infrastructure`.

- [ ] **Step 7: Commit timing harness and evidence summary.**

  ```bash
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  git add native/bench native/vst3/vst3_benchmark_recorder.* 'Scripts/tests/ajuntanaga_M3 Native VST3 Benchmark.lua' tools/run_native_vst3_benchmarks.py tools/run_guarded_reaper.py tests/test_native_vst3_benchmarks.py tests/test_guarded_reaper.py docs/VST3-PERFORMANCE.md RESUME.md CMakeLists.txt
  git commit -m "test: record native VST3 deadline gate"
  ```

## Task 24: Final Source Seal, Documentation, and Vault Synchronization

**Files:**

- Modify: `README.md`
- Modify: `NOTICE`
- Modify: `RESUME.md`
- Modify: `docs/VST3-TESTING.md`
- Modify: `docs/VST3-PERFORMANCE.md`
- Modify: `tools/validate_native_source.py`
- Modify outside Git: `/home/ajuntanaga/Documents/Obsidian/ResearchOS/Systems/REAPER/Polyphonic Audio to MIDI/Polyphonic Audio to MIDI.md`
- Create or modify outside Git: `/home/ajuntanaga/Documents/Obsidian/ResearchOS/Systems/REAPER/Polyphonic Audio to MIDI/Native VST3 Implementation Plan.md`

**Interfaces:**

- Consumes: every completed gate's exact evidence and hashes.
- Produces: evidence-backed source/documentation seal; no clean-DI claim or persistent installation.

- [ ] **Step 1: State evidence rather than aspiration.**

  Record stable production FUID, name/category, M3 tuning, General mode, discrete note output, host-owned sample rate, zero latency, parameters/state, build commands, SDK revisions/licenses, artifact/bundle hashes, completed/failed/unavailable gates, and remaining D8/I9 decisions. If performance fails, retain experimental status and the exact blocker.

- [ ] **Step 2: Run the complete final source gate from fresh build roots.**

  ```bash
  make -C native clean
  make -C native -j1 test
  make -C native -j1 sanitize
  make -C native -j1 production
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_source.py .
  python3 tools/validate_native_source.py .
  python3 tools/run_vst3_validator.py --kind production --bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
  git diff --check
  test "$(ps -eo comm= | awk '$1==\"reaper\"{n++} END{print n+0}')" -eq 0
  ```

  Expected: every authorized completed gate green, no source/validator issue, no REAPER process, and no persistent VST3 copy.

- [ ] **Step 3: Inspect final bundle and installation boundary.**

  ```bash
  git status --short
  find build/vst3/release/VST3 -maxdepth 5 -type f -printf '%P\n' | LC_ALL=C sort
  find /home/ajuntanaga/.vst3 -maxdepth 1 -name 'M3_Polyphonic_Audio_to_MIDI.vst3' -print 2>/dev/null
  ```

  Expected: one production bundle plus named test-only build-local bundles; persistent search prints nothing; only intended documentation/source changes are tracked.

- [ ] **Step 4: Commit the final repository seal.**

  ```bash
  git add README.md NOTICE RESUME.md docs/VST3-TESTING.md docs/VST3-PERFORMANCE.md tools/validate_native_source.py
  git commit -m "docs: seal native VST3 implementation state"
  ```

- [ ] **Step 5: Synchronize the organized ResearchOS dashboard.**

  Run `obsidian help` first and target `vault="ResearchOS"` if the app is open; otherwise edit canonical Markdown directly. Keep `RESUME.md` authoritative. The VST3 implementation-plan note uses YAML keys `type`, `status`, `workflow`, `group`, `created`, `updated`, `project`, `repository`, `source`, `spec`, `plan_commit`, `checkpoint_commit`, `sha256`, `tags`, `authority`, `gates`, and `next_safe_action`; tags include `area/reaper`, `kind/implementation-plan`, `format/vst3`, `topic/polyphonic-pitch`, `practice/real-time-safety`, and the evidence-backed status.

- [ ] **Step 6: Verify vault links and no background integration.**

  Parse every edited frontmatter block, confirm local source/spec/plan paths and reciprocal wikilinks, compare dashboard state to `RESUME.md`, and verify no Obsidian MCP server, daemon, autostart item, or vault Git repository was added.

## Final Acceptance Checklist

- [ ] Exact SDK 3.8.1 root and four submodule revisions are hash-complete, licensed, offline after retrieval, and excluded from persistent installation.
- [ ] The production bundle exposes only FUID `4A1BA42F-6D70-4609-8B52-450C3842F11F`, one non-distributable `SingleComponentEffect`, `Fx|Tools`, and no custom view.
- [ ] One stereo input/output, zero event inputs, one sixteen-channel event output, float32/64, zero latency/tail, and stereo-only arrangements are proven.
- [ ] Fifteen writable controls plus read-only Status and fourteen-value 184-byte state match the exact contract; no parameter advertises automation.
- [ ] Generated output contains only ordered VST3 note-on/off events with deterministic note IDs and exhaustive individual-off retry after rejection.
- [ ] Host sample rate is authoritative; no rate control/resampling exists; 44.1/48/88.2/96 kHz and blocks 32/64/128/256/512 are all evidenced.
- [ ] Production processing has fixed 64-sample phase, bounded storage, zero callback allocation/locking/I/O/waiting, and no owned thread.
- [ ] The twenty-row capability probe passes before detector porting, with every row serial, disposable, background workspace 5, guarded, and immutable.
- [ ] Frozen legacy parity distinguishes translation correctness from the approved 64-sample cadence.
- [ ] 45/124 M3 accuracy is 1.0; broader precision/recall is at least 0.98; silence, lifecycle, and 96 kHz 32+56 regressions pass.
- [ ] Open/chord latency meets `25/45 ms` and `40/65 ms` at 48 kHz with zero lookahead/declared latency.
- [ ] Every deadline row has P99 below 25% and no callback at/above 50%, including 96 kHz/block 32 and both long 48/128 captures.
- [ ] Final build is sanitizer/validator clean, byte-reproducible, documented, build-local, and leaves no REAPER process or active-workspace change.
- [ ] Clean DI, live hardware/project use, REAPER MCP, and persistent installation remain unclaimed and separately authorized.

## Primary References

- Steinberg VST3 API architecture/threading: <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/API%2BDocumentation/Index.html>
- Steinberg `SingleComponentEffect`: <https://steinbergmedia.github.io/vst3_doc/vstsdk/classSteinberg_1_1Vst_1_1SingleComponentEffect.html>
- Steinberg parameters/automation: <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Parameters%2BAutomation/Index.html>
- Steinberg Linux bundle format: <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Locations%2BFormat/Plugin%2BFormat.html>
- Official SDK 3.8.1 tag: <https://github.com/steinbergmedia/vst3sdk/releases/tag/v3.8.1_build_84>
- REAPER ReaScript FX parameter APIs: <https://www.reaper.fm/sdk/reascript/reascripthelp.html>

## Execution Handoff

The user previously selected inline execution. After this plan is approved, the next named gate is **inline Task 1 only: seal the local VST3 baseline and identities with no dependency, install, or REAPER action**. Task 1 then stops at Gate T1. A later explicit authorization must name the CMake installation; SDK retrieval remains a separate Gate D2 authorization even after CMake is present.
