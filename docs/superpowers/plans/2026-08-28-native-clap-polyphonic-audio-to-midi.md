# Native CLAP Polyphonic Audio-to-MIDI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a source-editable Linux x86-64 CLAP effect that converts an isolated tonal audio input into one-to-eight discrete MIDI notes in real time, preserves the frozen JSFX detector's accuracy, improves chord latency with a fixed 64-sample decision cadence, and passes the approved correctness, lifecycle, deadline, and host-stability gates before any installation or live-input use.

**Architecture:** Keep the detector as a format-neutral, fixed-capacity C++17 core and put all CLAP, REAPER, parameter, state, buffer, and MIDI-queue behavior in a narrow adapter. Prove the adapter first with a disposable capability plug-in; only after that gate passes, port the frozen JSFX modules one at a time under offline tests, then assemble the production effect. All REAPER work uses the existing guarded launcher, disposable profile, build-local CLAP path, background workspace 5 placement, and serial resumable runs.

**Tech Stack:** GNU C++ 15 in C++17 mode, GNU Make 4.4, official CLAP headers pinned to tag `1.2.10` / commit `195b42a004144fab0b3cf95e9c067187d15365b7`, Python 3 standard-library `unittest`, Lua ReaScript, existing JSFX test sources, AddressSanitizer/UndefinedBehaviorSanitizer, and REAPER 7.79 only through `tools/run_guarded_reaper.py`.

**Spec:** `docs/superpowers/specs/2026-08-28-native-clap-polyphonic-audio-to-midi-design.md`

## Global Constraints

- This document is a plan, not implementation authorization. Execution begins only after the user authorizes the next named gate. The user's word `Proceed` authorizes that clearly stated gate and nothing beyond it.
- Once execution is authorized, work inline and continuously between the hard gates below. Do not delegate or spawn workers unless the user explicitly asks.
- Dependency retrieval, each REAPER launch phase, clean-DI or hardware input, persistent installation, live-project use, and REAPER MCP remain separately gated.
- Do not edit the production JSFX effect or any file under `Effects/m3_poly_midi/`; treat commit `0be04d3` and the recorded Task 13 evidence as a frozen behavioral oracle.
- Do not copy ReaTune, NeuralNote, Basic Pitch, or other third-party detector code. The only vendored code allowed by this plan is the approved official CLAP header tree and its MIT notice.
- The production plug-in owns no thread and performs no allocation, deallocation, file or console I/O, locking, sleep, unbounded work, or normal-build clock sampling in `process()`.
- Production cadence is exactly 64 processed samples at every sample rate and is not exposed as a parameter. A 128-sample schedule exists only in offline test code for JSFX parity.
- No adaptive fallback may raise cadence, add lookahead/buffering, reduce the 24-108 supported pitch envelope, reduce M3 bounds 32-84, relax metrics, or move work to another thread.
- Every REAPER process is serial, disposable, nonactivating, hidden on workspace 5, limited to 50% of one logical CPU and 512 MiB, and launched only by `tools/run_guarded_reaper.py`. Refusal, pressure, a crash, or an unexplained spike stops the run; it does not trigger an automatic retry.
- Build products and host evidence stay below `build/`. Nothing is copied into `~/.clap`, `~/.vst3`, `~/.config/REAPER`, or a live project.
- Commit only the files belonging to the current task. Preserve unrelated user changes and stop if they overlap this plan.

## File Structure Snapshot

Before any task begins, use this ownership map: `third_party/clap/` contains only the pinned official ABI headers/license; `native/include/m3/` and `native/src/` contain the format-neutral detector; `native/plugin/` contains CLAP/state/MIDI/config adapters; `native/tests/` and `native/bench/` contain test-only hosts, fixtures, fuzzing, and timing; `Effects/tests/` and `Scripts/tests/` contain disposable REAPER stimuli/assertions; `tools/` contains validators and serial guarded runners; `tests/fixtures/native/` contains frozen oracle data; `docs/` and `RESUME.md` contain evidence-backed status. All generated objects, plug-ins, projects, profiles, and results stay under ignored `build/` paths. The later detailed map and shared contracts are authoritative for exact file and interface ownership.

Gate order is P0 plan approval -> D1 exact CLAP headers -> offline adapter -> C2 four-row REAPER capability probe -> detector port/offline gates -> N3 production REAPER correctness -> P4 performance. D5 clean DI and I6 installation remain outside implementation.

---

## Task 1: Seal the Native Baseline and Frozen Oracle

**Files:**

- Create: `tests/test_native_build_contract.py`
- Create: `tools/validate_native_source.py`
- Create: `tests/fixtures/native/jsfx-48k128/ORIGIN.md`
- Create: `tests/fixtures/native/jsfx-48k128/SHA256SUMS`
- Create from frozen evidence: `tests/fixtures/native/jsfx-48k128/{cases.tsv,events.tsv,summary.tsv,safety.tsv}`
- Verify only: `Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx`
- Verify only: `Effects/m3_poly_midi/**`

- [ ] **Step 1: Record the untouched JSFX tree before native work.**

  Run:

  ```bash
  git diff --exit-code 0be04d3 -- Effects/ajuntanaga_M3\ Polyphonic\ Audio\ to\ MIDI.jsfx Effects/m3_poly_midi
  git status --short
  ```

  Expected: no production-JSFX difference and no unrelated worktree change. Stop if either condition is false.

- [ ] **Step 2: Write the failing native-boundary tests.**

  Add `NativeBuildContractTests` assertions that:

  - the four frozen fixture TSVs and provenance files exist;
  - the copied `cases.tsv` hash is `5a2d0b4c9ced2f8f97248bdf164118ed3882307adcc41c976f429b363ff88dd3`;
  - the copied `events.tsv` hash is `a695ebdc5ac641bf3f51b16cfd0f48dca08f3723f717e296bde003bb437c2f2a`;
  - no production native source includes `NeuralNote`, `Basic Pitch`, `ReaTune`, ONNX, Torch, TensorFlow, a networking API, or a model file;
  - no build rule contains `-march=native`, CMake, Ninja, JUCE, or iPlug2; and
  - the production JSFX paths still match commit `0be04d3`.

  Run:

  ```bash
  python3 -m unittest tests.test_native_build_contract -v
  ```

  Expected RED: missing frozen native fixture/provenance files.

- [ ] **Step 3: Freeze the exact accepted evidence without regenerating it.**

  Copy only from `build/test-results/task13-v232-final-jsfx-48k128-slice/`. Keep all four TSVs byte-identical, write their hashes in lexical filename order, and record source checkpoint `0be04d3`, source directory, capture date, runtime fingerprint `7f2724003de54d623b434abf263e6dae3e571d4064194440094ed4367aa29ac4`, and the rule that the 45 `mode=m3` rows are the parity cohort.

  Run:

  ```bash
  sha256sum tests/fixtures/native/jsfx-48k128/cases.tsv tests/fixtures/native/jsfx-48k128/events.tsv
  cmp build/test-results/task13-v232-final-jsfx-48k128-slice/cases.tsv tests/fixtures/native/jsfx-48k128/cases.tsv
  cmp build/test-results/task13-v232-final-jsfx-48k128-slice/events.tsv tests/fixtures/native/jsfx-48k128/events.tsv
  ```

  Expected: the two specified hashes and byte-identical comparisons.

- [ ] **Step 4: Implement the initial native source validator.**

  `tools/validate_native_source.py ROOT` must return `0` with `native source contract: ok`, return `1` with one diagnostic per violation, ignore `build/`, and inspect only tracked project/native/dependency text. Keep checks deterministic and standard-library-only.

- [ ] **Step 5: Run the baseline gate.**

  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_source.py .
  python3 tools/validate_native_source.py .
  git diff --check
  ```

  Expected GREEN: the existing 90 tests plus new tests pass; both source contracts are clean.

- [ ] **Step 6: Commit the sealed baseline.**

  ```bash
  git add tests/fixtures/native tests/test_native_build_contract.py tools/validate_native_source.py
  git commit -m "test: seal native port oracle and boundaries"
  ```

## Task 2: Vendor the Exact Official CLAP Headers

**Gate D1:** Stop here until the user explicitly authorizes retrieval and vendoring of CLAP tag `1.2.10` at commit `195b42a004144fab0b3cf95e9c067187d15365b7`.

**Files:**

- Create: `third_party/clap/include/clap/**`
- Create: `third_party/clap/LICENSE`
- Create: `third_party/clap/UPSTREAM.md`
- Create: `third_party/clap/SHA256SUMS`
- Modify: `tests/test_native_build_contract.py`

- [ ] **Step 1: Extend the contract test before retrieval.**

  Require the upstream record to name exactly tag `1.2.10`, commit `195b42a004144fab0b3cf95e9c067187d15365b7`, source `https://github.com/free-audio/clap`, copied subtree `include/clap`, and `LICENSE`; require every vendored file to match `SHA256SUMS` and forbid any other subtree.

  Run:

  ```bash
  python3 -m unittest tests.test_native_build_contract -v
  ```

  Expected RED: the approved dependency is absent.

- [ ] **Step 2: Reverify the remote tag before copying bytes.**

  Run only after approval:

  ```bash
  git ls-remote https://github.com/free-audio/clap.git 'refs/tags/1.2.10*'
  ```

  Expected: the peeled tag resolves to `195b42a004144fab0b3cf95e9c067187d15365b7`. Stop on any mismatch.

- [ ] **Step 3: Retrieve into ignored build storage and verify the checkout.**

  ```bash
  git clone --filter=blob:none --no-checkout https://github.com/free-audio/clap.git build/vendor/clap-src
  git -C build/vendor/clap-src fetch --depth 1 origin 195b42a004144fab0b3cf95e9c067187d15365b7
  git -C build/vendor/clap-src checkout --detach 195b42a004144fab0b3cf95e9c067187d15365b7
  test "$(git -C build/vendor/clap-src rev-parse HEAD)" = 195b42a004144fab0b3cf95e9c067187d15365b7
  ```

  Do not install anything and do not use a package manager.

- [ ] **Step 4: Copy only the approved header tree and license.**

  Use a bulk exact copy from the verified checkout, then generate hashes with `LC_ALL=C` lexical ordering. `UPSTREAM.md` must include the commands above, the UTC retrieval date, and state that upstream examples, helpers, CMake files, and source implementations were not vendored.

- [ ] **Step 5: Validate provenance and license.**

  ```bash
  python3 -m unittest tests.test_native_build_contract -v
  python3 tools/validate_native_source.py .
  git diff --check
  ```

  Expected GREEN: exact revision, complete hashes, MIT notice present, no extra dependency content.

- [ ] **Step 6: Commit the dependency as one provenance unit.**

  ```bash
  git add third_party/clap tests/test_native_build_contract.py
  git commit -m "build: vendor pinned CLAP 1.2.10 headers"
  ```

## Task 3: Establish the C++17 Build and Allocation-Free Test Harness

**Files:**

- Create: `native/Makefile`
- Create: `native/include/m3/{constants.hpp,fixed_vector.hpp,types.hpp,pitch_math.hpp}`
- Create: `native/tests/{test_main.cpp,test_support.hpp,test_support.cpp,test_fixed_vector.cpp,test_pitch_math.cpp}`
- Modify: `tests/test_native_build_contract.py`
- Modify: `tools/validate_native_source.py`

- [ ] **Step 1: Write failing build-contract and bounded-container tests.**

  Cover zero/full capacity, insertion order, checked index access, explicit `false` on overflow, `clear()` without deallocation, finite detection, clamp edge cases, A4 conversion (`69 -> 440 Hz`), and M3 constants. Assert `kMaxCandidates=87`, `kMaxHarmonics=8`, `kMaxVoices=8`, and open notes `32,36,40,44,48,52,56,60`.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: target or source files do not exist.

- [ ] **Step 2: Add the explicit Makefile.**

  Required common flags:

  ```make
  -std=c++17 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
  -fno-exceptions -fno-rtti -fstack-protector-strong
  -ffile-prefix-map=$(ROOT)=. -fmacro-prefix-map=$(ROOT)=.
  ```

  Production adds `-O3 -DNDEBUG -fPIC -fvisibility=hidden`; shared linking adds `-shared -Wl,-z,relro,-z,now -Wl,--no-undefined -Wl,--build-id=none`. Sanitizers use `-O1 -g3 -fsanitize=address,undefined -fno-omit-frame-pointer`. Support `BUILD_DIR ?= $(ROOT)/build/native` and targets `test`, `sanitize`, `tsan`, `probe`, `production`, and `benchmark`. Never use `-march=native` or link a DSP/model library.

- [ ] **Step 3: Implement the smallest fixed-capacity contracts.**

  `FixedVector<T,N>` owns `std::array<T,N>` and a size, exposes only bounded `push_back`, `clear`, `size`, `capacity`, `operator[]`, `begin`, and `end`, and never throws. The test support defines a minimal registration/assertion framework and test-only global `operator new/delete` counters; production sources never include test support.

- [ ] **Step 4: Run normal and sanitizer tests.**

  ```bash
  make -C native test
  ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 make -C native sanitize
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: both executables exit `0`; no sanitizer or source-contract diagnostic.

- [ ] **Step 5: Commit the native foundation.**

  ```bash
  git add native tests/test_native_build_contract.py tools/validate_native_source.py
  git commit -m "build: add bounded native core foundation"
  ```

## Task 4: Prove CLAP Entry, Lifecycle, Ports, and Zero Latency Offline

**Files:**

- Create: `native/tests/{fake_clap_host.hpp,fake_clap_host.cpp,test_clap_lifecycle.cpp}`
- Create: `native/plugin/{dry_path.hpp,clap_adapter.hpp,clap_adapter.cpp,clap_entry.cpp}`
- Modify: `native/Makefile`
- Modify: `tests/test_native_build_contract.py`

- [ ] **Step 1: Write the fake-host RED.**

  Through the exported `clap_entry`, assert:

  - exactly one descriptor per build;
  - production ID `com.ajuntanaga.m3-polyphonic-audio-to-midi` and probe ID `com.ajuntanaga.m3-polyphonic-audio-to-midi.probe`;
  - clean `init -> create -> init -> activate -> start_processing -> reset -> stop_processing -> deactivate -> destroy -> deinit` sequencing;
  - refusal of invalid sample rates, `max_frames == 0`, `min_frames > max_frames`, and `max_frames > 16384`;
  - one main stereo input and output, one raw-MIDI input and output, preferred/supported dialect `CLAP_NOTE_DIALECT_MIDI`; and
  - latency extension value exactly zero.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: no CLAP entry or adapter exists.

- [ ] **Step 2: Implement lifecycle and extension dispatch only.**

  Provide the CLAP plug-in factory, descriptors, lifecycle callbacks, `audio-ports`, `note-ports`, and `latency` extensions. Advertise `audio-effect` and `note-effect`, not instrument or synthesizer. Require exactly two audio channels at activation and check port/buffer counts again in every process call.

- [ ] **Step 3: Implement dry audio templates and layout failure.**

  For float32 and float64, support aliasing and separate buffers. Finite pass-through values must retain identical bits; mute writes zero. Any non-finite input becomes zero in detector input and dry output and latches invalid state. Unexpected buffers preserve only safely addressable dry channels, emit no new generated notes, and latch Unsupported Layout.

- [ ] **Step 4: Prove no process allocation.**

  Activate first, arm the test allocation counter, call the adapter with float32/float64, in-place/out-of-place, pass/mute, finite/non-finite, zero-event blocks at frame counts `1,32,64,128,256,16384`, then assert no `new` or `delete` occurred.

- [ ] **Step 5: Build and inspect the probe artifact.**

  ```bash
  make -C native test probe
  nm -D build/native/clap/M3_Polyphonic_Audio_to_MIDI_Probe.clap | grep 'clap_entry'
  readelf -d build/native/clap/M3_Polyphonic_Audio_to_MIDI_Probe.clap
  ```

  Expected: one exported `clap_entry`, no unresolved project symbol, no dependency outside the normal C/C++/math runtime.

- [ ] **Step 6: Commit the lifecycle slice.**

  ```bash
  git add native tests/test_native_build_contract.py
  git commit -m "feat: add minimal CLAP lifecycle and port adapter"
  ```

## Task 5: Implement the Stable Parameter and State Contract

**Files:**

- Create: `native/plugin/{parameter_contract.hpp,parameter_contract.cpp,state_codec.hpp,state_codec.cpp}`
- Create: `native/tests/{test_parameter_contract.cpp,test_state_codec.cpp}`
- Modify: `native/plugin/clap_adapter.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write the parameter-table RED.**

  Require IDs and order `0x4D330001` through `0x4D33000F`, then Status `0x4D33FF01`; exact names/ranges/defaults from the approved spec; stepped flags only where appropriate; Status read-only and stepped; no parameter with `CLAP_PARAM_IS_AUTOMATABLE`; and exactly sixteen visible parameter records.

- [ ] **Step 2: Write state and malformed-stream RED cases.**

  Test a byte-exact default encoding, all fourteen nondefault persistent values, partial stream reads/writes, unknown schema, bad magic, bad CRC, wrong payload length, duplicate/missing/unknown IDs, trailing bytes, NaN/Inf, truncation at every byte, and out-of-range values clamped through the common validator. Assert Panic, Status, notes, telemetry, and transients never appear.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: parameter/state modules are missing.

- [ ] **Step 3: Implement one constexpr parameter table.**

  Use it for `count`, `get_info`, `get_value`, `value_to_text`, `text_to_value`, default construction, and validation so IDs/ranges cannot drift. External MIDI channel remains one-based; encoding subtracts one only at the MIDI boundary. Panic is an action flag and immediately reports Ready after it has been accepted.

- [ ] **Step 4: Implement the exact state codec.**

  Encode/decode the wire format above with explicit little-endian helpers and a bounded IEEE CRC-32 implementation. Loop over CLAP streams only until the fixed 184-byte state is complete; treat zero/negative progress as failure. Decode into a temporary config, validate completely, then publish—never partially mutate live state.

- [ ] **Step 5: Wire parameter flush and main-thread refresh.**

  Accept inactive/main-thread `params.flush` and active process parameter events. Coalesce latest values at a process boundary. Audio-side status changes set an atomic dirty bit and call `host->request_callback()`; `on_main_thread()` performs `CLAP_PARAM_RESCAN_VALUES`. Use the same path to return Panic to Ready. Never call host UI/rescan methods directly from `process()`.

- [ ] **Step 6: Run and commit.**

  ```bash
  make -C native test sanitize probe
  python3 tools/validate_native_source.py .
  git diff --check
  git add native
  git commit -m "feat: define CLAP parameters and versioned state"
  ```

  Expected GREEN: byte-exact state tests and all malformed inputs pass without sanitizer findings.


## Hard Gates and Stop Conditions

| Gate | Authorization or evidence required | Allowed after pass | Failure action |
| --- | --- | --- | --- |
| P0 Plan | User accepts this implementation plan | Begin local native source work | Amend the plan only |
| D1 Dependency | Explicit approval to retrieve and vendor the exact CLAP header revision | Run Task 2 retrieval commands | Stop; do not substitute another SDK |
| C2 Capability | Offline probe green, then explicit approval for four guarded disposable REAPER launches | Port detector core | Preserve evidence and request a CLAP/VST3 design correction if any required capability fails |
| N3 Native host | Offline native gates green, then explicit approval for guarded production-host validation | Run correctness and lifecycle host matrix | Return to the smallest responsible adapter/core task; no heavy retry |
| P4 Performance | Native host correctness green, then explicit approval for guarded benchmark matrix | Assess performance-ready state | Any callback at or above 50% of deadline stops the experiment and requires amendment |
| D5 Clean DI | Separate approval and source material | Measure the already-approved 90%/85% F1 thresholds | Synthetic success remains experimental |
| I6 Install | All prior gates green plus explicit installation approval | Copy one production artifact to a persistent plug-in path | Leave build-local artifact uninstalled |

The implementation covered here ends at a sealed build-local artifact and verified synthetic/host evidence. Gates D5 and I6 are deliberately not execution tasks in this plan.

## Planned File Map

### Third-party provenance

| Path | Responsibility |
| --- | --- |
| `third_party/clap/include/clap/**` | Unmodified official CLAP 1.2.10 headers |
| `third_party/clap/LICENSE` | Upstream MIT license |
| `third_party/clap/UPSTREAM.md` | Tag, commit, URL, copied subtree, retrieval command, and date |
| `third_party/clap/SHA256SUMS` | Lexically ordered hashes of every vendored file |

### Format-neutral native core

| Path | Responsibility |
| --- | --- |
| `native/include/m3/constants.hpp` | Stable capacities, M3 tuning, thresholds, and supported host bounds |
| `native/include/m3/fixed_vector.hpp` | Allocation-free bounded sequence with explicit overflow result |
| `native/include/m3/types.hpp` | Configuration, status, selection, transition, and telemetry value types |
| `native/include/m3/pitch_math.hpp` | Finite checks, clamping, MIDI/frequency conversion |
| `native/include/m3/conditioning.hpp` / `native/src/conditioning.cpp` | DC blocking, energy/noise/peak/clip tracking |
| `native/include/m3/resonator_bank.hpp` / `native/src/resonator_bank.cpp` | Prepared multi-rate harmonic resonators and per-sample updates |
| `native/include/m3/salience_selector.hpp` / `native/src/salience_selector.cpp` | Salience, explain-away, bounded candidate ranking |
| `native/include/m3/m3_profile.hpp` / `native/src/m3_profile.cpp` | Eight-string tuning masks and distinct-string feasibility filter |
| `native/include/m3/lifecycle.hpp` / `native/src/lifecycle.cpp` | Per-note attack/on/release state machines and velocity |
| `native/include/m3/detector_core.hpp` / `native/src/detector_core.cpp` | Module composition and phase-continuous decision scheduler |

### Adapter and plug-ins

| Path | Responsibility |
| --- | --- |
| `native/plugin/parameter_contract.hpp` / `.cpp` | Sixteen visible parameter records: fifteen writable controls plus read-only Status |
| `native/plugin/state_codec.hpp` / `.cpp` | Versioned, checksummed fourteen-value persistent state |
| `native/plugin/prepared_config_exchange.hpp` / `.cpp` | Atomic request snapshot and fixed generation-tagged prepared slots |
| `native/plugin/midi_pipeline.hpp` / `.cpp` | Raw MIDI passthrough, generated-event ordering, output-failure cleanup state |
| `native/plugin/dry_path.hpp` | Float32/float64 stereo copy/mute/input selection templates |
| `native/plugin/clap_adapter.hpp` / `.cpp` | CLAP lifecycle, ports, processing, callbacks, and status publication |
| `native/plugin/clap_entry.cpp` | Exported `clap_entry` and production descriptor |
| `native/plugin/probe_processor.hpp` / `.cpp` | Test-only deterministic generated-MIDI behavior and lifecycle report |
| `native/Makefile` | Explicit production, probe, test, sanitizer, and benchmark targets |

### Tests, fixtures, and guarded host tooling

| Path | Responsibility |
| --- | --- |
| `native/tests/test_main.cpp` / `test_support.hpp` / `.cpp` | Dependency-free test runner, allocation counter, assertions, TSV helpers |
| `native/tests/fake_clap_host.hpp` / `.cpp` | Bounded CLAP host/event/state doubles and controllable output rejection |
| `native/tests/synthetic_source.hpp` / `.cpp` | Deterministic audio generator matching the existing JSFX harness formulas |
| `native/tests/test_*.cpp` | Unit, contract, parity, fault, and adapter tests grouped by component |
| `native/bench/benchmark_main.cpp` | Offline bounded timing runner; never linked into production |
| `tests/fixtures/native/jsfx-48k128/**` | Frozen Task 13 cases/events/summary/safety files plus provenance and hashes |
| `tests/test_native_build_contract.py` | Toolchain, artifact, provenance, and production-symbol checks |
| `tests/test_native_clap_probe_runner.py` | Build-local path, staging, checkpoint, process, and guard refusal tests |
| `tests/test_native_results.py` | Native TSV schema, accuracy, latency, deadline, and stale-evidence tests |
| `Effects/tests/ajuntanaga_M3 Native CLAP Capability Source.jsfx` | Deterministic stereo and raw-MIDI input for the capability probe |
| `Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua` | Probe discovery/ports/parameters/state/Panic/MIDI/audio/lifecycle assertions |
| `Scripts/tests/ajuntanaga_M3 Native Test Wrapper.lua` | Selects the native effect and invokes the unchanged shared synthetic runner |
| `tools/validate_native_source.py` | Native-only source/real-time/dependency/build boundary validator |
| `tools/run_native_clap_probe.py` | Four-row serial guarded capability runner with immutable checkpoints |
| `tools/run_native_matrix.py` | Resumable native synthetic/host matrix using the existing guard |
| `tools/summarize_native_results.py` | Exact correctness, latency, safety, and deadline acceptance calculations |
| `docs/NATIVE-TESTING.md` | Reproduction commands, evidence schemas, and authorization boundaries |
| `docs/NATIVE-PERFORMANCE.md` | Measured results, hashes, failures, and final native decision |

Generated-only paths are `build/native/{obj,bin,clap}`, `build/reaper-test`, and `build/test-results/native-*`; they remain ignored.

## Shared Native Contracts

Create these contracts before translating algorithms so every later task uses the same types and capacities:

```cpp
namespace m3 {

inline constexpr std::uint32_t kDecisionQuantum = 64;
#if defined(M3_TESTING)
inline constexpr std::uint32_t kLegacyTestQuantum = 128;
#endif
inline constexpr std::uint32_t kMaxHostFrames = 16384;
inline constexpr std::size_t kMaxCandidates = 87;
inline constexpr std::size_t kMaxHarmonics = 8;
inline constexpr std::size_t kMaxVoices = 8;
inline constexpr std::size_t kMaxInternalSelections = 16;
inline constexpr std::size_t kMaxTickTransitions = 16;
inline constexpr std::array<std::uint8_t, 8> kM3OpenNotes{
    32, 36, 40, 44, 48, 52, 56, 60};

enum class DetectorInput : std::uint8_t { left, right, downmix };
enum class ProfileMode : std::uint8_t { m3, general };
enum class VelocityMode : std::uint8_t { fixed, dynamic };
enum class Status : std::uint8_t {
  ready, panic_hold, reconfiguring, midi_output_blocked,
  invalid_input_or_state, unsupported_layout
};
enum class TransitionKind : std::uint8_t { note_off, note_on };

struct PersistentConfig final {
  DetectorInput detector_input{DetectorInput::left};
  ProfileMode profile_mode{ProfileMode::m3};
  double a4_hz{440.0};
  double input_trim_db{0.0};
  std::uint8_t sensitivity{50};
  std::uint8_t response{25};
  std::uint8_t lowest_note{32};
  std::uint8_t highest_note{84};
  std::uint8_t max_polyphony{8};
  std::uint8_t max_fret{24};
  VelocityMode velocity_mode{VelocityMode::dynamic};
  std::uint8_t fixed_velocity{100};
  std::uint8_t midi_channel{1};  // External one-based value.
  bool dry_passthrough{true};
};

struct VoiceTransition final {
  std::uint32_t sample_offset{};
  TransitionKind kind{};
  std::uint8_t note{};
  std::uint8_t velocity{};
  std::uint32_t sequence{};
};

using TickTransitions = FixedVector<VoiceTransition, kMaxTickTransitions>;

enum class PrepareError : std::uint8_t {
  none, invalid_sample_rate, invalid_config, unsafe_frame_count
};

PrepareError prepare_config(const PersistentConfig& requested,
                            double sample_rate,
                            PreparedConfig& destination) noexcept;

class DetectorCore final {
 public:
  DetectorCore() noexcept;
#if defined(M3_TESTING)
  explicit DetectorCore(TestDecisionSchedule schedule) noexcept;
#endif
  void reset(const PreparedConfig& prepared) noexcept;
  bool process_sample(double mono_sample, std::uint32_t block_offset,
                      TickTransitions& output) noexcept;
  bool release_all(std::uint32_t block_offset,
                   TickTransitions& output) noexcept;
  void apply_runtime_controls(const RuntimeControls& controls) noexcept;
  const TelemetrySnapshot& telemetry() const noexcept;
};

}  // namespace m3
```

The production adapter constructs `DetectorCore{}` only. `TestDecisionSchedule` and `kLegacyTestQuantum` exist only when compiling `native/tests` with `M3_TESTING`; `tools/validate_native_source.py` rejects them from production objects.

The generated block buffer capacity is computed during activation with checked arithmetic:

```text
max_ticks = ceil(max_frames / 64)
capacity = max_ticks * 16 + 8 boundary note-offs + 2 channel panic messages
```

Activation rejects `max_frames == 0`, `max_frames > 16384`, or any overflow before allocating the buffer.

## Exact Parameter Matrix

| ID | Name | Values/range; default | Update class | Saved |
| --- | --- | --- | --- | --- |
| `0x4D330001` | Detector input | Left=0, Right=1, Downmix=2; 0 | Structural | Yes |
| `0x4D330002` | Mode | M3 Eight-String=0, General Tonal=1; 0 | Structural | Yes |
| `0x4D330003` | A4 reference | 400.0-480.0 by 0.1 Hz; 440.0 | Structural | Yes |
| `0x4D330004` | Input trim | -24.0 to +24.0 by 0.1 dB; 0.0 | Runtime | Yes |
| `0x4D330005` | Sensitivity | 0-100; 50 | Runtime | Yes |
| `0x4D330006` | Response | Fast 0 through Stable 100; 25 | Runtime | Yes |
| `0x4D330007` | Lowest MIDI note | 24-108; 32 | Structural | Yes |
| `0x4D330008` | Highest MIDI note | 24-108; 84 | Structural | Yes |
| `0x4D330009` | Maximum polyphony | 1-8; 8 | Structural | Yes |
| `0x4D33000A` | M3 maximum fret | 0-36; 24 | Structural | Yes |
| `0x4D33000B` | Velocity mode | Fixed=0, Dynamic=1; 1 | Runtime | Yes |
| `0x4D33000C` | Fixed velocity | 1-127; 100 | Runtime | Yes |
| `0x4D33000D` | MIDI channel | 1-16; 1 | Structural | Yes |
| `0x4D33000E` | Panic | Ready=0, Panic=1; 0 | Momentary action | No |
| `0x4D33000F` | Dry audio | Muted=0, Pass through=1; 1 | Runtime | Yes |
| `0x4D33FF01` | Status | Ready=0, Panic Hold=1, Reconfiguring=2, MIDI Output Blocked=3, Invalid Input or State=4, Unsupported Layout=5; 0 | Read-only telemetry | No |

All discrete rows are stepped. Status is read-only. No row advertises `CLAP_PARAM_IS_AUTOMATABLE` in this revision.

## Persistent State Wire Format

Use one deterministic little-endian format rather than serializing C++ structs:

```text
bytes 0..3    ASCII "M3PA"
bytes 4..5    uint16 schema = 1
bytes 6..7    uint16 field_count = 14
bytes 8..11   uint32 payload_bytes = 168
bytes 12..15  uint32 IEEE CRC-32 of payload
payload       14 records in ascending parameter-ID order:
              uint32 parameter_id + uint64 IEEE-754 double bits
```

The loader requires the exact magic, schema, byte count, CRC, known IDs, and one copy of every persistent field. It rejects trailing bytes, duplicate/missing IDs, NaN/Inf, or short reads; numeric out-of-range values are clamped by the same validator used for host edits. Panic, Status, active notes, resonator history, telemetry, and pending MIDI are absent.

## Prepared-Configuration Publication Contract

- `AtomicConfigRequest` stores the fourteen values in atomic 64-bit words plus a monotonically increasing generation. The audio side stores fields relaxed, then publishes the generation with release ordering. The main thread loads generation/fields/generation with acquire ordering and retries only its bounded snapshot if the generations differ.
- `PreparedConfigExchange` owns three preallocated slots with atomic states `free`, `writing`, `ready`, `audio_claimed`, and `active`. The main thread may claim a free slot or replace the oldest still-ready slot, but never touches active or audio-claimed storage.
- The audio thread claims only the highest ready generation at a process boundary. It releases active notes under the old channel, resets the core, switches to the claimed slot, then marks the old slot free and the new slot active.
- If no writable slot exists, the main thread keeps the latest request generation pending and asks for another callback; the audio thread never waits.
- `static_assert(std::atomic<std::uint64_t>::is_always_lock_free)` and the corresponding 32-bit assertion are build requirements on the target.

## MIDI Merge and Failure Contract

Represent incoming raw MIDI and generated transitions in neutral fixed-size views. For each timestamp, emit:

1. generated individual note-offs;
2. generated cleanup CC123 (All Notes Off) then CC120 (All Sound Off), when pending;
3. incoming raw MIDI in original order; and
4. generated note-ons.

On any `try_push()` failure, latch `midi_output_blocked`, suppress all later generated note-ons, retain a 128-bit pending-release set for every generated pitch that may have reached the host, and retry individual note-offs plus both channel panic messages at offset zero of the next process call. A successfully pushed note-on becomes active; a rejected note-on does not. Incoming events are not replayed. Detection stays inhibited after cleanup succeeds until explicit Panic or reset reinitializes the detector into Panic Hold.

---

## Task 6: Implement MIDI Ordering, Panic, and Output-Failure Recovery

**Files:**

- Create: `native/plugin/{midi_pipeline.hpp,midi_pipeline.cpp}`
- Create: `native/tests/test_midi_pipeline.cpp`
- Modify: `native/plugin/clap_adapter.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write the deterministic merge RED.**

  Cover offsets `0`, `frames-1`, multiple decision ticks, empty input, maximum input, and equal-offset ordering. Assert generated note-off before CC123/CC120 before original-order input before generated note-on. Reject any generated offset outside `[0, frames_count)` and any note/channel/velocity outside MIDI bounds.

- [ ] **Step 2: Write every queue-failure transition before implementation.**

  Configure the fake output list to reject each push position in turn. Verify:

  - rejected note-ons never become active;
  - already accepted note-ons become pending releases after a later failure;
  - rejected note-offs remain pending;
  - all new generated note-ons are suppressed while blocked;
  - individual note-offs retry at next offset zero;
  - CC123 and CC120 both must succeed in the same complete cleanup call;
  - input events are not replayed;
  - dry audio continues; and
  - explicit Panic/reset is required after cleanup before detection can resume.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: merge and recovery types are undefined.

- [ ] **Step 3: Implement fixed storage and checked activation sizing.**

  Allocate the generated block buffer only in `activate()` using the checked capacity formula, then retain a raw pointer, size, and immutable capacity for processing. Keep per-pitch active and pending-release state in two `std::array<std::uint64_t,2>` bitsets. Do not use a container operation in `process()` that can grow or throw.

- [ ] **Step 4: Implement Panic Hold exactly.**

  Panic queues all active note-offs at the current reachable offset, blocks new note-ons, and immediately returns the parameter value to Ready. Hold cannot clear in the same process call that accepted Panic; it clears only after one subsequent complete call has a finite selected-input peak below `0.0001`. Loud, invalid, or unsupported input extends hold.

- [ ] **Step 5: Run allocation, sanitizer, and source checks.**

  ```bash
  make -C native test sanitize
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: exhaustive rejection-position tests pass, and the armed process allocation counter remains unchanged.

- [ ] **Step 6: Commit the MIDI safety slice.**

  ```bash
  git add native
  git commit -m "feat: add ordered MIDI and fail-closed cleanup"
  ```

## Task 7: Implement Main-to-Audio Prepared Configuration Exchange

**Files:**

- Create: `native/plugin/{prepared_config_exchange.hpp,prepared_config_exchange.cpp}`
- Create: `native/tests/test_prepared_config_exchange.cpp`
- Create: `docs/NATIVE-TESTING.md`
- Modify: `native/plugin/clap_adapter.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write deterministic slot-state RED tests.**

  Test initial active generation, latest-ready-wins, stale-ready reclamation, no-slot retry, wrap-safe monotonic generation comparison, claim/commit/cancel, old slot not writable before commit, and no partial `PreparedConfig` observation. Drive main/audio roles with a deterministic interleaving table rather than timing sleeps.

- [ ] **Step 2: Write bounded concurrent stress RED.**

  In an offline test only, use one publisher thread and one consumer thread for a fixed 100,000-generation sequence. Fill every coefficient with its generation-derived checksum and assert every adopted slot is internally coherent and generations never regress. The production plug-in still creates no thread.

- [ ] **Step 3: Implement `AtomicConfigRequest`.**

  Encode each field into a lock-free atomic word and use the acquire/release generation protocol defined above. Reader retry count is bounded to three in a single main callback; if publication is racing longer, call `request_callback()` again instead of spinning.

- [ ] **Step 4: Implement the three-slot state machine.**

  Only the main thread transitions `free/ready -> writing -> ready`. Only audio transitions `ready -> audio_claimed -> active` and prior `active -> free`. Every transition uses compare/exchange with documented memory ordering. The latest requested generation may replace the oldest ready slot; active and claimed slots are never overwritten.

- [ ] **Step 5: Wire structural versus lightweight edits.**

  Structural fields are detector input, profile, A4, bounds, maximum polyphony, maximum fret, and MIDI channel. They publish a preparation request and expose Reconfiguring while the old valid generation continues. Trim, sensitivity, response, velocity mode/fixed velocity, and dry mode update bounded runtime controls only at a process boundary. Adoption emits old-channel note-offs before switching.

- [ ] **Step 6: Run ThreadSanitizer if supported, then the mandatory gates.**

  ```bash
  make -C native test sanitize
  make -C native tsan
  python3 tools/validate_native_source.py .
  ```

  Always record the exchange stress count and toolchain result in `docs/NATIVE-TESTING.md`. Normal and ASan/UBSan tests must pass. If GCC ThreadSanitizer is unavailable or fails before the test body because of host/toolchain infrastructure, record that exact limitation; a real data-race report is a hard failure.

- [ ] **Step 7: Commit the exchange.**

  ```bash
  git add native docs/NATIVE-TESTING.md
  git commit -m "feat: publish prepared detector configurations safely"
  ```

## Task 8: Extend the Existing REAPER Guard for a Build-Local CLAP Path

**Files:**

- Modify: `tools/run_guarded_reaper.py`
- Modify: `tests/test_guarded_reaper.py`
- Create: `tests/test_native_clap_probe_runner.py`
- Create: `tools/run_native_clap_probe.py` (initial guard/staging shell only)

- [ ] **Step 1: Write guard refusal RED tests.**

  Require rejection of:

  - any CLAP path except resolved `ROOT/build/native/clap`;
  - a symlink escaping that directory;
  - a missing probe artifact;
  - a probe report path except resolved `ROOT/build/reaper-test/test-results/probe-native.tsv`;
  - `--clap-path` without a disposable profile;
  - any pre-existing REAPER PID for native probe/matrix runners; and
  - any caller attempt to override `-cfgfile` or `-nonewinst`.

  Run:

  ```bash
  python3 tools/stage_reaper_test_env.py --reaper /home/ajuntanaga/opt/REAPER/reaper --output build/reaper-test --case-set host
  python3 -m unittest tests.test_guarded_reaper tests.test_native_clap_probe_runner -v
  ```

  Expected RED: the new flags and refusal paths do not exist.

- [ ] **Step 2: Add exact optional environment injection to the one launcher.**

  Add `--clap-path` and `--probe-report` arguments. After resolution and exact-boundary checks, add these before the `systemd-run` command separator:

  ```text
  --setenv=CLAP_PATH=/absolute/repository/build/native/clap
  --setenv=M3_CLAP_PROBE_REPORT=/absolute/repository/build/reaper-test/test-results/probe-native.tsv
  ```

  Do not alter `HOME`, XDG config paths, REAPER's live profile, or the parent process environment. Keep `-newinst -noactivate -cfgfile <exact disposable reaper.ini> -nosplash`, workspace default 5, hidden window placement, completion sentinel, CPU/memory/swap/task limits, nice/idle-I/O/one-core limits, and timeouts unchanged.

- [ ] **Step 3: Make dry-run evidence explicit.**

  A dry run with CLAP must print the build-local path, workspace 5, exact disposable profile, `MemoryMax=512M`, `CPUQuota=50%`, `TasksMax=64`, `-noactivate`, and no live path. It must not start REAPER.

- [ ] **Step 4: Add the native runner's no-existing-REAPER and pressure checks.**

  Before every launch, enumerate `/proc/*/exe` for `reaper`, snapshot available memory/load/temperature plus `/proc/pressure/{memory,io}` full `avg10`, and refuse if any REAPER exists, memory is below 4 GiB, load exceeds 12, temperature is at least 90 C, memory pressure is at least `0.25`, or I/O pressure is at least `2.0`. Take the same snapshot after the launch and preserve it with results.

- [ ] **Step 5: Run the guard tests without launching REAPER.**

  ```bash
  python3 -m unittest tests.test_guarded_reaper tests.test_native_clap_probe_runner -v
  python3 tools/run_guarded_reaper.py --check-only --available-mib 32000 --load-one 2 --temperature-c 70
  python3 tools/run_guarded_reaper.py --dry-run --gui --workspace 5 --profile build/reaper-test/reaper.ini --clap-path build/native/clap --probe-report build/reaper-test/test-results/probe-native.tsv --available-mib 32000 --load-one 2 --temperature-c 70 -- -new
  ```

  Expected GREEN: test suite passes; dry-run shows only the guarded command. If the disposable profile has not yet been staged, use a test fixture profile for the unit test and do not weaken the exact-path check.

- [ ] **Step 6: Commit the guard extension.**

  ```bash
  git add tools/run_guarded_reaper.py tools/run_native_clap_probe.py tests/test_guarded_reaper.py tests/test_native_clap_probe_runner.py
  git commit -m "test: guard build-local CLAP host launches"
  ```

## Task 9: Build the Disposable CLAP Capability Probe

**Files:**

- Create: `native/plugin/{probe_processor.hpp,probe_processor.cpp}`
- Create: `native/tests/test_probe_processor.cpp`
- Create: `Effects/tests/ajuntanaga_M3 Native CLAP Capability Source.jsfx`
- Create: `Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua`
- Modify: `tools/run_native_clap_probe.py`
- Modify: `native/Makefile`
- Modify: `tests/test_source_contract.py`
- Modify: `tests/test_native_clap_probe_runner.py`

- [ ] **Step 1: Write offline probe behavior RED tests.**

  Test-only raw MIDI CC119 value 1 passes through and additionally produces note 60 on at `trigger+1` and off at `trigger+3`. CC119 value 2 produces a held note 61 that Panic releases. All other input remains byte-identical. Test equal-offset ordering with input at the generated offsets. This behavior is compiled only into the `.probe` descriptor.

- [ ] **Step 2: Add lifecycle diagnostics that cannot enter production.**

  The probe records atomic counters/bits for create/init/activate/start/reset/stop/deactivate/destroy, float32/float64, actual alias/separate host buffers, and activation-time dry-path self-tests for both alias modes. `process()` only updates atomics. On the main thread during destroy, the probe writes one bounded TSV report to `M3_CLAP_PROBE_REPORT`. If the environment value is absent, it writes nothing. The production build must not contain the environment string, report writer, trigger CC, or probe descriptor.

- [ ] **Step 3: Write the deterministic JSFX source.**

  Produce finite, asymmetric stereo samples and publish the expected dry samples through the existing `m3_poly_midi_tests_v1` gmem contract. In the scripted MIDI phase, emit note 67 on at offset 4, CC119/1 at 8, note 65 on at 9, CC1/64 at 11, note 67 off at 20, and note 65 off at 21. Require block size at least 32 and fail closed otherwise.

- [ ] **Step 4: Write the ReaScript assertions.**

  In a blank disposable project, create one track with capability source -> probe CLAP -> existing MIDI capture -> ReaSynth -> existing synth-output probe. Assert:

  - discovery by exact probe name and CLAP format;
  - sixteen parameters with exact names, ranges/defaults, writable/read-only behavior, momentary Panic, and visible Status transitions;
  - `TrackFX_GetNamedConfigParm(..., "pdc")` returns zero;
  - track-state-chunk save/mutate/restore round-trips all fourteen persistent values while Panic/Status return to runtime defaults;
  - finite dry error is zero, source and probe report no overflow, and ReaSynth output is nonzero;
  - exact input/generated event bytes and ordering at offsets 4,8,9,11,20,21;
  - held note 61 is released by Panic and no note remains active; and
  - deleting the probe yields its lifecycle report before the script writes final `suite-finish`.

  Write results atomically only under the disposable `test-results` directory.

- [ ] **Step 5: Make the runner fully resumable and serial.**

  Stage through `stage_reaper_test_env.stage`, create a blank `build/native-probe.RPP`, run block sizes `32,64,128,256` one at a time, and save each completed row below `build/test-results/native-clap-probe/batches/<block>/`. A batch is adoptable only when `phase.log` ends in `suite-finish`, all expected files exist, actual rate/block match, and metadata hashes the probe artifact, scripts, Effects test files, disposable project, and runner. Preserve invalid/partial batches with an `.invalid-<timestamp>` suffix.

- [ ] **Step 6: Run offline tests only.**

  ```bash
  make -C native test sanitize probe
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_source.py .
  python3 tools/validate_native_source.py .
  strings build/native/clap/M3_Polyphonic_Audio_to_MIDI.clap 2>/dev/null | grep -E 'M3_CLAP_PROBE_REPORT|CC119' && exit 1 || true
  ```

  Expected GREEN: probe artifact and all offline contracts pass; no REAPER process is started; production artifact may not exist yet, and the final strings check is repeated when it does.

- [ ] **Step 7: Commit the complete unlaunched probe.**

  ```bash
  git add native/plugin/probe_processor.hpp native/plugin/probe_processor.cpp native/tests/test_probe_processor.cpp native/Makefile 'Effects/tests/ajuntanaga_M3 Native CLAP Capability Source.jsfx' 'Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua' tools/run_native_clap_probe.py tests/test_source_contract.py tests/test_native_clap_probe_runner.py
  git commit -m "test: add disposable CLAP capability probe"
  ```

## Task 10: Execute and Seal the Minimal CLAP Capability Gate

**Gate C2:** Stop here until Tasks 1-9 are green and the user explicitly authorizes the four guarded disposable REAPER launches. This is not permission for detector porting if the probe fails.

**Files:**

- Modify after evidence: `docs/NATIVE-TESTING.md`
- Modify after evidence: `RESUME.md`
- Evidence only: `build/test-results/native-clap-probe/**`

- [ ] **Step 1: Run a fresh non-launching preflight.**

  ```bash
  pgrep -a reaper || true
  python3 tools/run_guarded_reaper.py --check-only
  python3 tools/run_native_clap_probe.py --dry-run
  ```

  Expected: no REAPER PID; host and pressure gates healthy; exactly four serial workspace-5 commands, no execution. Stop on any refusal.

- [ ] **Step 2: Run the capability matrix once.**

  ```bash
  python3 tools/run_native_clap_probe.py
  ```

  The runner, not the operator, launches each process. Never parallelize or manually reopen a failed row.

- [ ] **Step 3: Verify cleanup before reading results.**

  ```bash
  pgrep -a reaper || true
  python3 tools/run_native_clap_probe.py --check
  ```

  Expected: no new REAPER PID; four immutable complete batches; discovery/lifecycle/reset/unload, float32 stereo dry identity and both alias-mode self-tests, zero PDC, raw-MIDI ports/passthrough/generated notes/VSTi output, exact offsets, parameters/Panic/Status/state, and no live-profile/project mutation all pass.

- [ ] **Step 4: Apply the binary stop decision.**

  If any required assertion fails, archive hashes/logs and stop the CLAP implementation before Task 11. The only next design action is a separately approved VST3 adapter correction. Do not download a VST3 SDK or continue core porting.

- [ ] **Step 5: Record and commit a passing gate.**

  Add exact artifact/runtime/result hashes, four rate/block rows, pressure extrema, and the no-process/no-live-mutation result to `docs/NATIVE-TESTING.md` and `RESUME.md`.

  ```bash
  git add docs/NATIVE-TESTING.md RESUME.md
  git commit -m "test: seal CLAP capability gate"
  ```

## Task 11: Port Configuration, Pitch Math, and Input Conditioning

**Files:**

- Modify: `native/include/m3/{types.hpp,pitch_math.hpp}`
- Create: `native/include/m3/conditioning.hpp`
- Create: `native/src/conditioning.cpp`
- Create: `native/tests/{test_config.cpp,test_conditioning.cpp}`
- Modify: `native/Makefile`

- [ ] **Step 1: Write configuration and numeric RED tests.**

  Cover every exact endpoint/default/step, reversed General bounds, M3 effective bounds fixed to 32-84, maximum eight voices, A4 values 400/440/480, MIDI channel 1/16, representative finite positive sample rates from 8 kHz through 384 kHz, and rejection of zero, negative, NaN, Inf, or any rate whose coefficient preparation becomes non-finite. Test equal-power downmix as `(left + right) * 0.7071067811865476`.

- [ ] **Step 2: Write conditioner vector RED tests from the frozen JSFX formulas.**

  Use fixed sequences for silence, DC, impulse, sine, clipping, denormally small values, and NaN/Inf. Compare DC-block output, fast/slow energy, noise floor, peak, and clip envelope at every sample with absolute tolerance `1e-12` and relative tolerance `1e-9` against values calculated by the existing EEL2 equations.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: config preparation and conditioner types are missing.

- [ ] **Step 3: Implement validation as a pure function.**

  Keep requested persistent values and derived `RuntimeControls` separate from `PreparedConfig`. Clamp only documented numeric ranges, order General bounds, override effective M3 bounds, compute trim gain, and return a typed error for invalid enum encodings, non-finite values, or unsupported sample rate. A trim change linearly reaches its new detector-only gain over exactly 64 processed samples; it never alters dry audio.

- [ ] **Step 4: Port conditioning without structural changes.**

  Preserve the JSFX coefficients: 15 Hz DC pole, 5 ms fast energy, 100 ms slow energy, 2 s noise rise, 250 ms peak/clip release, `1e-12` noise floor, and `0.999` clip threshold. Non-finite input is replaced with zero and latches invalid input.

- [ ] **Step 5: Run and commit.**

  ```bash
  make -C native test sanitize
  python3 tools/validate_native_source.py .
  git add native
  git commit -m "feat: port native configuration and conditioning"
  ```

## Task 12: Port the Prepared Multi-Rate Resonator Bank

**Files:**

- Create: `native/include/m3/resonator_bank.hpp`
- Create: `native/src/resonator_bank.cpp`
- Create: `native/tests/{test_resonator_bank.cpp,resonator_reference.hpp}`
- Modify: `native/Makefile`

- [ ] **Step 1: Write preparation RED tests.**

  Assert one guard semitone per available edge within the 87-candidate cap, harmonic counts by pitch, Nyquist/cutoff exclusions, four rate levels, exact Butterworth stage coefficients, enabled-cell counts, and finite unit rotations at 44.1/48/96 kHz across A4 400/440/480.

- [ ] **Step 2: Write full-rate reference and multi-rate parity RED tests.**

  Put the full-rate reference bank in test code only. Recreate JSFX Task 4/6 intent for cases 4101-4106 and 6101-6106: guard-edge tuning, open-string local peaks, cell update counters, renormalization, and worst open-string salience delta no greater than `0.03` at all three rates.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: resonator bank is absent.

- [ ] **Step 3: Prepare every coefficient off the audio thread.**

  `PreparedConfig` owns immutable enabled masks, rate assignments, rotations, decays, and filter coefficients. `ResonatorBank` owns only mutable cos/sin/fast/slow/filter state. Candidate/harmonic loops have compile-time maxima and no indirect allocation.

- [ ] **Step 4: Port per-sample updates exactly.**

  Preserve the existing four-level decimation filters, low-rate special cases, partial limits, fast/slow energy updates, and bounded periodic renormalization. Do not vectorize yet.

- [ ] **Step 5: Prove bounded work and parity.**

  ```bash
  make -C native test sanitize
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: all rate/tuning/reference cases pass; the test counter shows no more enabled-cell updates than the JSFX multi-rate contract and no process allocation.

- [ ] **Step 6: Commit the bank.**

  ```bash
  git add native
  git commit -m "feat: port multi-rate harmonic resonator bank"
  ```

## Task 13: Port Salience and Harmonic Explain-Away

**Files:**

- Create: `native/include/m3/salience_selector.hpp`
- Create: `native/src/salience_selector.cpp`
- Create: `native/tests/test_salience.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write salience RED cases before selector logic.**

  Cover harmonic weights, candidate energy, fundamental contribution, noise-adaptive threshold, clipped input, missing fundamentals, shared partials, octave/fifth parents, quiet low notes, and edge candidates. Use explicit fixed energy arrays so failures identify formula drift rather than signal generation.

- [ ] **Step 2: Assert the safety bounds.**

  For candidate counts `0,1,53,85,87`, test every parent/root probe at notes 0 and 127 and verify no index outside prepared candidate/harmonic storage. Invalid energy or score must fail closed to zero confidence and an invalid-state flag.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED: salience functions are undefined.

- [ ] **Step 3: Port the scoring pipeline in source order.**

  Preserve the constants and order from `salience_selector.jsfx-inc`: harmonic accumulation, effective threshold, smoothed/raw energy, shared-partial downweighting, General octave aliases, missing-fundamental lower aliases, and missing-fundamental parents. Use structure-of-arrays fixed storage sized 87.

- [ ] **Step 4: Verify numeric parity.**

  ```bash
  make -C native test sanitize
  ```

  Expected GREEN: fixed vectors match the JSFX equations at `1e-12` absolute / `1e-9` relative tolerance; no invalid index or sanitizer finding.

- [ ] **Step 5: Commit salience separately from selection.**

  ```bash
  git add native
  git commit -m "feat: port harmonic salience scoring"
  ```

## Task 14: Port Bounded Polyphonic Selection

**Files:**

- Modify: `native/include/m3/salience_selector.hpp`
- Modify: `native/src/salience_selector.cpp`
- Create: `native/tests/test_selector.cpp`

- [ ] **Step 1: Write selector RED cases matching JSFX cases 5101-5106.**

  Include one fundamental, octave competition, missing fundamental, shared fifth, eight M3 opens, and candidate-limit behavior. Add ties that require deterministic ascending-note resolution, sixteen internal candidates, an eight-voice public cap, and zero candidates.

- [ ] **Step 2: Write adversarial residual tests.**

  Feed negative, zero, subnormal, huge finite, NaN, and Inf scores/energies. Require bounded iterations, no duplicate selected note, no more than sixteen internal candidates, and invalid-state fail-closed behavior.

- [ ] **Step 3: Port selection and stable ordering.**

  Use fixed residual/rank arrays. Preserve JSFX explain-away order and acquisition smoothing. Implement explicit insertion ordering by score then pitch so compiler/library sort differences cannot alter output.

- [ ] **Step 4: Run cross-layer regression.**

  ```bash
  make -C native test sanitize
  ```

  Expected GREEN: conditioner, bank, salience, and selector suites all pass; no allocation occurs while selecting.

- [ ] **Step 5: Commit the selector.**

  ```bash
  git add native
  git commit -m "feat: port bounded polyphonic selector"
  ```

## Task 15: Port the M3 Eight-String Feasibility Filter

**Files:**

- Create: `native/include/m3/m3_profile.hpp`
- Create: `native/src/m3_profile.cpp`
- Create: `native/tests/test_m3_profile.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write tuning and string-mask RED tests.**

  For opens `32,36,40,44,48,52,56,60` and maximum fret `0,1,12,24,36`, assert exact playable-string masks. Include duplicate pitch classes, unplayable notes, the 32/84 boundaries, and all eight open strings simultaneously.

- [ ] **Step 2: Write distinct-string feasibility RED tests matching cases 7101-7106.**

  Require at most one selected note per physical string, maximum-weight feasible subset, deterministic ties, open-chord preference, fret penalties, empty input, and 16-to-8 reduction without heap work.

- [ ] **Step 3: Implement the fixed dynamic program.**

  Use two fixed 256-state rows keyed by the eight-bit used-string mask, fixed predecessor codes, and no recursion. General mode bypasses only the string-feasibility filter; it retains the same eight-voice cap.

- [ ] **Step 4: Run and commit.**

  ```bash
  make -C native test sanitize
  git add native
  git commit -m "feat: port M3 distinct-string feasibility"
  ```

## Task 16: Port Generic Voice Lifecycle and Velocity

**Files:**

- Create: `native/include/m3/lifecycle.hpp`
- Create: `native/src/lifecycle.cpp`
- Create: `native/tests/test_lifecycle_generic.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write coefficient/velocity RED tests.**

  Test response 0/25/50/100 at all three rates, rounding to nearest sample, attack/release/dropout thresholds, fixed velocity 1/100/127, dynamic floor/ceiling mapping, and exact note-off velocity zero.

- [ ] **Step 2: Write the generic state-machine RED.**

  Exercise `off -> attack -> on -> release -> off`, attack interruption, dropout bridging, reacquisition, replacement off-before-on, maximum active voices, duplicate prevention, release-all, event overflow, absolute sample wrap protection, and General octave/harmonic alias guards.

  Use host block partitions `32,64,128,256` over the same evidence timeline and require identical absolute transition samples.

- [ ] **Step 3: Implement fixed per-pitch state.**

  Own 128 `VoiceState` cells rather than a map. All time fields are `uint64_t` absolute processed-sample counts; subtract only after ordered checks. Emit into `TickTransitions` with explicit overflow failure. Keep state transitions source-equivalent to the JSFX lifecycle.

- [ ] **Step 4: Run and commit the generic slice.**

  ```bash
  make -C native test sanitize
  git add native
  git commit -m "feat: port generic note lifecycle"
  ```

## Task 17: Port M3-Specific Lifecycle Guards

**Files:**

- Modify: `native/src/lifecycle.cpp`
- Create: `native/tests/test_lifecycle_m3.cpp`

- [ ] **Step 1: Translate JSFX cases 8101-8111 into RED tests.**

  Cover low G-sharp admission, fast/guarded/high open attacks, low-chord delay, octave confirmation, parent confirmation, mature/multiple-parent alias blocking, adjacent-open chromatic shadows, low-string conflicts, high-open context, stale attacks, and attack-energy admission.

- [ ] **Step 2: Add exhaustive M3 boundary combinations.**

  For every M3 open note, test its adjacent semitones, octave/fifth parents, maximum-fret edge, single note, dyad, four-note chord, and full eight-note chord. Require no more than eight active notes and no duplicate transition.

- [ ] **Step 3: Port constants and guards without retuning.**

  Copy the current project-owned JSFX constants/formulas exactly into named C++ constants. Do not tune thresholds during the port. Any parity failure is fixed as a translation error first; threshold changes require evidence and a separate task amendment.

- [ ] **Step 4: Run the complete lifecycle suite.**

  ```bash
  make -C native test sanitize
  ```

  Expected GREEN: all generic/M3 lifecycle cases pass at block partitions 32/64/128/256 with no hanging active bit after release/Panic.

- [ ] **Step 5: Commit M3 lifecycle.**

  ```bash
  git add native
  git commit -m "feat: port M3 lifecycle guards"
  ```

## Task 18: Assemble the Phase-Continuous Detector Core

**Files:**

- Create: `native/include/m3/detector_core.hpp`
- Create: `native/src/detector_core.cpp`
- Create: `native/tests/test_detector_core.cpp`
- Modify: `native/Makefile`

- [ ] **Step 1: Write scheduling RED tests independent of pitch accuracy.**

  With a test seam that substitutes a counting decision function, prove:

  - reset starts phase zero;
  - production decisions occur after samples 64,128,... and attach to the current zero-based offsets 63,127,...;
  - phase continues across arbitrary host partitions, including `1x128`, `2x64`, `4x32`, `17+47+3+61`;
  - a short block never forces an early tick;
  - a long block can contain multiple ticks; and
  - maximum ticks/events stay within activation capacity.

- [ ] **Step 2: Restrict legacy scheduling to the test build.**

  In `M3_TESTING` only, provide `TestDecisionSchedule::jsfx_block_boundary_128`, which consumes each 128-sample interval and evaluates at the following block boundary/offset zero. The normal header/binary expose only `DetectorCore()` with fixed 64-sample cadence. The source validator and production symbol test reject `TestDecisionSchedule` and `kLegacyTestQuantum` from the production artifact.

- [ ] **Step 3: Compose the real modules.**

  Per sample: validate/select mono input in adapter, apply trim, condition, update bank, and track interval peak. Per tick: update salience, select bounded voices, apply M3 filter, update lifecycle, append transitions. Silence clears selection/smoothed energy and drives normal release. Any internal overflow/non-finite invariant latches invalid state and schedules release.

- [ ] **Step 4: Prove block segmentation invariance.**

  Feed identical generated audio under all supported block partitions and compare absolute note/type/velocity sequences. Production 64-sample output must be byte-identical across partitions; only per-block offsets differ by `absolute_sample % block_size`.

- [ ] **Step 5: Run and commit.**

  ```bash
  make -C native test sanitize
  python3 tools/validate_native_source.py .
  git add native
  git commit -m "feat: assemble fixed-cadence detector core"
  ```

## Task 19: Establish JSFX Parity and Production-64 Offline Correctness

**Files:**

- Create: `native/tests/{synthetic_source.hpp,synthetic_source.cpp,test_jsfx_parity.cpp,test_native_synthetic.cpp}`
- Create: `tools/run_native_matrix.py` (offline mode)
- Create: `tools/summarize_native_results.py`
- Create: `tests/test_native_results.py`
- Modify: `native/Makefile`

- [ ] **Step 1: Write TSV/source/parser RED tests.**

  Require exact headers, ordered unique case IDs, supported sample rates/blocks, bounded note/gain lists, immutable manifest hash, stale runtime rejection, atomic checkpoint writes, and an error for any missing/trailing malformed field.

- [ ] **Step 2: Reproduce the deterministic synthetic audio formulas in test code.**

  Match the existing JSFX signal source's phase, harmonic amplitudes, detune, missing-fundamental, gain, noise, hum, clipping, stagger, note-on duration, and release duration. Use a fixed PRNG seed/algorithm written into result metadata. Compare selected waveform checkpoints to the existing source formulas before using them for detector metrics.

- [ ] **Step 3: Run the legacy-128 parity RED.**

  For the 45 frozen M3 rows, require exact note-on/off pitch/type order, no duplicate/hanging note, velocity difference at most one, and onset/release within one 128-sample decision interval of the frozen events. At module checkpoints, retain `1e-12` absolute / `1e-9` relative tolerance.

  Run:

  ```bash
  make -C native test
  ```

  Expected RED until the translated core is source-equivalent.

- [ ] **Step 4: Fix translation defects only until legacy parity is green.**

  Do not change thresholds to improve production metrics in this step. For each failure, reduce to the responsible module test and commit only after the fixed fixture cohort passes.

- [ ] **Step 5: Run production-64 offline acceptance.**

  ```bash
  make -C native test
  python3 tools/run_native_matrix.py --offline --output build/test-results/native-offline
  python3 tools/summarize_native_results.py --input build/test-results/native-offline --check
  ```

  Require all 45 M3 cases/124 expected notes at precision=recall=F1 `1.0`, no duplicate/hanging note; broader clean synthetic precision/recall at least `0.98`; no silence events; all module/lifecycle regressions at applicable 44.1/48/96 kHz; and no false MIDI 44 for the 96 kHz 32+56 case.

- [ ] **Step 6: Enforce offline latency limits before host integration.**

  At 48 kHz require open-string median/P95 no more than `25/45 ms` and three/four-note completion median/P95 no more than `40/65 ms`, calculated from causal source onset to first complete correct active set. A failure stops before production assembly; do not raise cadence or relax metrics.

- [ ] **Step 7: Run the full offline gate and commit.**

  ```bash
  make -C native test sanitize
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_native_source.py .
  git add native/tests/synthetic_source.hpp native/tests/synthetic_source.cpp native/tests/test_jsfx_parity.cpp native/tests/test_native_synthetic.cpp native/Makefile tools/run_native_matrix.py tools/summarize_native_results.py tests/test_native_results.py
  git commit -m "test: establish native detector parity and accuracy"
  ```

## Task 20: Assemble the Production CLAP Adapter

**Files:**

- Modify: `native/plugin/{clap_adapter.hpp,clap_adapter.cpp,clap_entry.cpp}`
- Create: `native/tests/test_production_adapter.cpp`
- Modify: `native/Makefile`
- Modify: `tools/validate_native_source.py`
- Modify: `tests/test_native_build_contract.py`

- [ ] **Step 1: Write the end-to-end fake-host RED.**

  Instantiate the production descriptor through `clap_entry`, activate, feed stereo audio plus parameter/raw-MIDI/transport events, and verify dry samples, generated MIDI, passthrough, parameter/status values, state, reconfiguration, Panic, reset, and deactivation. Repeat with float32/float64 and alias/separate buffers at frames `1,32,64,128,256,16384`.

- [ ] **Step 2: Write status-priority and recovery RED tests.**

  When multiple conditions coexist, require this visible priority: Unsupported Layout, Invalid Input or State, MIDI Output Blocked, Reconfiguring, Panic Hold, Ready. Verify a lower-priority recovery cannot clear a higher-priority latch.

- [ ] **Step 3: Implement process-call sequencing exactly once.**

  At each call:

  1. validate frame/port/buffer bounds;
  2. retry pending generated cleanup at offset zero;
  3. claim a complete prepared generation, release under the old channel, reset, then adopt;
  4. parse parameter events into one boundary update and retain raw MIDI views in host order;
  5. copy/mute dry audio and select/condition/process detector samples;
  6. append every 64-sample core transition into activation-sized storage;
  7. merge input/generated raw MIDI through the failure state machine; and
  8. publish bounded atomic status/telemetry.

  Return `CLAP_PROCESS_CONTINUE`; report zero latency and no tail. Never call preparation or a UI callback inline.

- [ ] **Step 4: Implement observable transport/reset cleanup.**

  On a CLAP transport playing-to-stopped transition, configuration/channel adoption, explicit Panic, invalid state, or reachable fault, schedule all active releases. `reset()` clears detector transients and moves active notes to the pending-release set for the next reachable process call; document that no plug-in can guarantee delivery if the host never calls process again.

- [ ] **Step 5: Build the production artifact and prove probe isolation.**

  ```bash
  make -C native test sanitize probe benchmark production
  nm -D build/native/clap/M3_Polyphonic_Audio_to_MIDI.clap
  strings build/native/clap/M3_Polyphonic_Audio_to_MIDI.clap | grep -E 'M3_CLAP_PROBE_REPORT|com\.ajuntanaga\.m3-polyphonic-audio-to-midi\.probe|CC119' && exit 1 || true
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: one production descriptor/entry; no probe/report/benchmark seam; all process calls allocate zero bytes.

- [ ] **Step 6: Commit production assembly.**

  ```bash
  git add native tools/validate_native_source.py tests/test_native_build_contract.py
  git commit -m "feat: assemble native CLAP audio-to-MIDI effect"
  ```

## Task 21: Adversarial, Sanitizer, Real-Time, and Reproducibility Gates

**Files:**

- Create: `native/tests/{test_adversarial.cpp,test_realtime_contract.cpp}`
- Modify: `tests/test_native_build_contract.py`
- Modify: `tools/validate_native_source.py`
- Create: `docs/NATIVE-TESTING.md` if not already created

- [ ] **Step 1: Write deterministic adversarial RED tests.**

  For five fixed seeds, run 100,000 bounded operations covering arbitrary parameter doubles, state byte strings length 0-256, audio frames/layouts, event headers/types/ports/offsets, queue rejection positions, config generations, reset/Panic/transport sequences, and non-finite samples. Assert no crash, hang, out-of-bounds access, duplicate generated on, more than eight generated active notes, or unreleased active note after successful cleanup.

- [ ] **Step 2: Enforce the process real-time contract dynamically.**

  After activation, arm allocation/deallocation counters and call at least 100,000 process blocks; assert zero changes. Count `/proc/self/task` before create and after activate/process/destroy; assert the plug-in created no thread. Use fake host callbacks that fail the test if process calls rescan, logging, GUI, or main-thread-only operations.

- [ ] **Step 3: Enforce the source/binary contract statically.**

  Reject production use of `<thread>`, `<mutex>`, `<condition_variable>`, `<future>`, `<filesystem>`, iostreams, `printf`, file/network APIs, sleep/wait, exceptions, RTTI, recursion in core modules, model files, and any process-time operation that can grow a container. Verify activation-sized storage has immutable process capacity, build commands contain `-fno-exceptions -fno-rtti`, no `-march=native`, and no benchmark/probe macro for production.

- [ ] **Step 4: Run all sanitizers in bounded offline processes.**

  ```bash
  make -C native test
  ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 make -C native sanitize
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_source.py .
  python3 tools/validate_native_source.py .
  ```

  Expected GREEN: no finding. A sanitizer crash before test entry is recorded as tooling-invalid and retried only with a smaller offline invocation; a real report is a hard failure.

- [ ] **Step 5: Prove byte-reproducible production builds.**

  ```bash
  epoch="$(git log -1 --format=%ct)"
  SOURCE_DATE_EPOCH="$epoch" make -C native BUILD_DIR="$PWD/build/repro-a" production
  SOURCE_DATE_EPOCH="$epoch" make -C native BUILD_DIR="$PWD/build/repro-b" production
  cmp build/repro-a/clap/M3_Polyphonic_Audio_to_MIDI.clap build/repro-b/clap/M3_Polyphonic_Audio_to_MIDI.clap
  sha256sum build/repro-a/clap/M3_Polyphonic_Audio_to_MIDI.clap build/repro-b/clap/M3_Polyphonic_Audio_to_MIDI.clap
  ```

  Expected: byte-identical files. Record compiler/linker versions, flags, artifact hash, and dependency hash in `docs/NATIVE-TESTING.md`.

- [ ] **Step 6: Commit the offline safety seal.**

  ```bash
  git add native/tests/test_adversarial.cpp native/tests/test_realtime_contract.cpp tests/test_native_build_contract.py tools/validate_native_source.py docs/NATIVE-TESTING.md
  git commit -m "test: seal native real-time and robustness contracts"
  ```

## Task 22: Run Native Correctness and Lifecycle in Guarded REAPER

**Gate N3:** Stop here until all offline tasks are green and the user explicitly authorizes the guarded production-effect REAPER validation. Passing the capability probe does not authorize this heavier matrix.

**Files:**

- Modify minimally: `Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua`
- Create: `Scripts/tests/ajuntanaga_M3 Native Test Wrapper.lua`
- Modify: `tools/run_native_matrix.py` (guarded host mode)
- Modify: `tests/test_run_synthetic_matrix.py`
- Modify: `tests/test_native_results.py`
- Modify after evidence: `docs/NATIVE-TESTING.md`
- Modify after evidence: `RESUME.md`
- Evidence only: `build/test-results/native-host/**`

- [ ] **Step 1: Make the shared runner select an effect without changing its default.**

  Replace the one hard-coded detector name with:

  ```lua
  local detector_fx_name = rawget(_G, "M3_TEST_DETECTOR_FX_NAME") or
    "JS: ajuntanaga_M3 Polyphonic Audio to MIDI"
  ```

  The native wrapper sets the global to `CLAP: M3 Polyphonic Audio to MIDI` and `dofile`s the shared runner. Add a regression that the unwrapped JSFX runner still chooses the exact original name. Do not edit any production JSFX file.

- [ ] **Step 2: Extend the native runner with immutable host batches.**

  Use the same manifests, maximum eight cases per launch, validation schemas, atomic checkpointing, invalid-batch archival, process cleanup, pressure snapshots, and completion sentinel as the existing matrix. Add the production `.clap` SHA-256 and native source fingerprint to every batch. Pass only the build-local `CLAP_PATH` through the existing guard.

- [ ] **Step 3: Run all non-launching tests and dry runs.**

  ```bash
  make -C native test production
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/run_native_matrix.py --host --dry-run --output build/test-results/native-host
  pgrep -a reaper || true
  ```

  Expected: exact serial command schedule for 44.1/48/96 kHz and blocks 32/64/128/256, no process started, no existing REAPER PID.

- [ ] **Step 4: Execute the guarded matrix once after approval.**

  ```bash
  python3 tools/run_native_matrix.py --host --output build/test-results/native-host
  ```

  The runner stops on pressure, guard refusal, crash, result corruption, unexpected process, or hard correctness failure. It never retries automatically and never attaches to an existing REAPER instance.

- [ ] **Step 5: Validate native host acceptance.**

  Require the final 48 kHz M3 slice at 45/124 and precision=recall=F1 `1.0`, broader precision/recall at least `0.98`, no duplicates/hangs, no silence event, the 96 kHz 32+56 regression without MIDI 44, and 48 kHz open/chord latency within `25/45` and `40/65 ms`. Require exact input MIDI passthrough, generated ordering, Panic trials, transport-stop cleanup when observable, dry identity, nonzero ReaSynth output, and zero PDC.

- [ ] **Step 6: Verify host/system cleanup and record evidence.**

  ```bash
  pgrep -a reaper || true
  python3 tools/run_native_matrix.py --host --check --output build/test-results/native-host
  ```

  Record exact batch/artifact/runtime hashes, pressure extrema, workspace restoration, and no remaining REAPER process in `docs/NATIVE-TESTING.md` and `RESUME.md`. If a correctness gate fails, return to its smallest module; do not continue to Task 23.

- [ ] **Step 7: Commit only the harness and evidence summary.**

  ```bash
  git add 'Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua' 'Scripts/tests/ajuntanaga_M3 Native Test Wrapper.lua' tools/run_native_matrix.py tests/test_run_synthetic_matrix.py tests/test_native_results.py docs/NATIVE-TESTING.md RESUME.md
  git commit -m "test: verify native effect in guarded REAPER"
  ```

## Task 23: Measure and Seal Native Deadline Performance

**Gate P4:** Stop here until Task 22 is green and the user explicitly authorizes the guarded benchmark matrix. This build has timing instrumentation; it is never the production artifact.

**Files:**

- Create: `native/bench/benchmark_main.cpp`
- Create: `native/plugin/benchmark_recorder.hpp` / `.cpp`
- Create: `Scripts/tests/ajuntanaga_M3 Native Benchmark.lua`
- Create: `tools/run_native_benchmarks.py`
- Modify: `native/Makefile`
- Modify: `tools/run_guarded_reaper.py`
- Modify: `tests/test_guarded_reaper.py`
- Modify: `tests/test_native_results.py`
- Create or modify: `docs/NATIVE-PERFORMANCE.md`
- Modify after evidence: `RESUME.md`

- [ ] **Step 1: Build a separate bounded timing seam.**

  `M3_BENCHMARKING` enables monotonic samples around the complete adapter `process()` call and stores durations in activation-sized memory. It never prints/writes in process; the main thread writes results after the FX is deleted. The benchmark descriptor ID is `com.ajuntanaga.m3-polyphonic-audio-to-midi.benchmark`. Add a guarded `--benchmark-report` option that accepts only resolved `ROOT/build/reaper-test/test-results/benchmark-native.tsv` and injects only `M3_CLAP_BENCHMARK_REPORT` through `systemd-run --setenv`. Production source/binary tests reject that ID, the clock seam, and report environment string.

- [ ] **Step 2: Run the offline benchmark before any host launch.**

  Feed the dense eight-note M3 source for 256 warm-up plus 10,000 measured blocks at each rate/block. Require bounded storage and calculate median/P95/P99/max deadline fractions. If profiling suggests a scalar hot loop, an optional vector kernel may be added only behind the identical resonator/core tests and byte-identical MIDI output. Do not run the official host gate until the scalar or parity-proven vector build is selected and frozen.

- [ ] **Step 3: Write result-validator RED tests.**

  Reject missing rows, wrong rate/block/view, fewer than requested blocks, NaN/Inf/negative durations, unordered timestamps, stale artifact hashes, P99 at or above `0.25`, any block at or above `0.50`, dry discontinuity, or an out-of-block MIDI offset.

- [ ] **Step 4: Dry-run the exact guarded schedule.**

  One launch per rate/block records two segments: generic parameter view closed, then open. Each ordinary segment has 2,000 measured blocks after 256 warm-up blocks. Two independent final 48 kHz/128 launches each record 10,000 total measured blocks split equally closed/open. All launches remain serial and use workspace 5/background/noactivate/build-local rules.

  ```bash
  make -C native benchmark
  python3 tools/run_native_benchmarks.py --dry-run
  pgrep -a reaper || true
  ```

- [ ] **Step 5: Execute once after approval and stop on a hard failure.**

  ```bash
  python3 tools/run_native_benchmarks.py
  ```

  Any observed block at or above 50% immediately terminates the current run, preserves its partial evidence, and stops the native experiment for design review. Do not automatically optimize/retry, enlarge the block, increase cadence, hide the UI, or exclude the row.

- [ ] **Step 6: Apply the complete performance gate.**

  Require every closed/open 44.1/48/96 kHz x 32/64/128/256 row to have P99 below 25%, no block at/above 50%, no added dry delay/discontinuity/channel corruption, and ordered in-block MIDI timestamps. Require both independent final 48/128 captures to pass. Re-run the full offline correctness hash after the benchmark build choice.

- [ ] **Step 7: Record and commit the result, pass or fail.**

  `docs/NATIVE-PERFORMANCE.md` must report exact distributions, counts, hashes, pressure extrema, UI state, failures, and one explicit decision: `performance-ready pending clean DI`, `native amendment required`, or `unavailable due to infrastructure`. Never describe a failed or incomplete matrix as passing.

  ```bash
  pgrep -a reaper || true
  git add native/bench/benchmark_main.cpp native/plugin/benchmark_recorder.hpp native/plugin/benchmark_recorder.cpp 'Scripts/tests/ajuntanaga_M3 Native Benchmark.lua' tools/run_native_benchmarks.py tools/run_guarded_reaper.py tests/test_guarded_reaper.py tests/test_native_results.py docs/NATIVE-PERFORMANCE.md RESUME.md native/Makefile
  git commit -m "test: record native deadline gate"
  ```

## Task 24: Final Source Seal, Documentation, and Vault Synchronization

**Files:**

- Modify: `README.md`
- Modify: `RESUME.md`
- Modify: `NOTICE`
- Modify: `docs/NATIVE-TESTING.md`
- Modify: `docs/NATIVE-PERFORMANCE.md`
- Modify: `tools/validate_native_source.py`
- Modify outside Git: `/home/ajuntanaga/Documents/Obsidian/ResearchOS/Systems/REAPER/Polyphonic Audio to MIDI/Polyphonic Audio to MIDI.md`
- Create or modify outside Git: `/home/ajuntanaga/Documents/Obsidian/ResearchOS/Systems/REAPER/Polyphonic Audio to MIDI/Native CLAP Implementation Plan.md`

- [ ] **Step 1: Make documentation state evidence, not aspiration.**

  Record the stable ID, M3 tuning, discrete MIDI, zero latency, parameter/state contract, source/build commands, exact artifact hash, dependency revision/license, passed/failed/unavailable gates, and remaining separate clean-DI/install decisions. If Task 23 failed, keep the artifact experimental and say why.

- [ ] **Step 2: Run the complete final source gate from a clean build.**

  ```bash
  make -C native clean
  make -C native test sanitize production
  python3 -m unittest discover -s tests -p 'test_*.py' -v
  python3 tools/validate_source.py .
  python3 tools/validate_native_source.py .
  git diff --check
  pgrep -a reaper || true
  ```

  Expected: all authorized completed gates green, no source-contract issue, no REAPER process, and no file outside repository/build/vault documentation touched.

- [ ] **Step 3: Inspect the final worktree and artifact boundary.**

  ```bash
  git status --short
  git diff --stat
  find build/native/clap -maxdepth 1 -type f -printf '%f\n' | sort
  ```

  Expected: one production `.clap` plus explicitly named test-only probe/benchmark artifacts in build storage; only intended documentation/source changes are tracked; no persistent plug-in copy exists.

- [ ] **Step 4: Commit the final repository seal.**

  ```bash
  git add README.md RESUME.md NOTICE docs/NATIVE-TESTING.md docs/NATIVE-PERFORMANCE.md tools/validate_native_source.py
  git commit -m "docs: seal native CLAP implementation state"
  ```

- [ ] **Step 5: Synchronize the organized ResearchOS vault.**

  Follow the Obsidian integration rule: run `obsidian help` first and target `vault="ResearchOS"` explicitly if the app is open; otherwise edit the canonical Markdown directly. Keep the task-local `RESUME.md` authoritative. Put the implementation-plan note in the existing `Systems/REAPER/Polyphonic Audio to MIDI` group, with YAML fields for `type`, `status`, `project`, `repository`, `source`, `spec`, `created`, `updated`, and tags `system/reaper`, `project/audio-to-midi`, `format/clap`, `topic/polyphonic-pitch`, `workflow/implementation-plan`. Link it from the project dashboard and link back to the design amendment and authoritative plan.

- [ ] **Step 6: Verify vault links without adding a service.**

  Confirm both Markdown files parse, all referenced local paths exist, the dashboard status matches `RESUME.md`, and no Obsidian MCP server, daemon, autostart item, or vault Git repository was added.

## Final Acceptance Checklist

- [ ] Capability probe passed all four host blocks before detector porting.
- [ ] Production artifact exposes the exact stable ID, 15 controls, Status, ports, state, and zero latency.
- [ ] Production process has fixed 64-sample phase, bounded storage, zero allocation, no owned thread, and no normal timing/file/log calls.
- [ ] Raw input MIDI and generated output obey exact ordering and output-failure recovery.
- [ ] Frozen legacy parity distinguishes translation correctness from the approved cadence change.
- [ ] 45/124 M3 accuracy is 1.0; broader precision/recall is at least 0.98; silence and 96 kHz 32+56 regressions pass.
- [ ] Open/chord latency meets 25/45 and 40/65 ms at 48 kHz.
- [ ] Every deadline row meets P99 below 25% and no block at/above 50%, including two long 48/128 captures and open/closed generic UI.
- [ ] All host evidence came from serial disposable background workspace-5 runs with no remaining REAPER process or live-profile mutation.
- [ ] Final build is reproducible, source/provenance documented, and artifact remains build-local.
- [ ] Clean DI, live input/project use, REAPER MCP, and persistent installation remain unclaimed and separately authorized.

## Execution Handoff

The user previously selected inline execution. After this plan is reviewed, the next named gate is: **authorize inline Tasks 1-9, including the one-time retrieval and vendoring of the exact CLAP 1.2.10 header tree at commit `195b42a004144fab0b3cf95e9c067187d15365b7`; stop before every REAPER launch.** A subsequent `Proceed` authorizes exactly that gate. Task 10 will still pause for explicit guarded-REAPER authorization.
