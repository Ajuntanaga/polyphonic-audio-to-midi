# Native VST3 Testing

Updated: 2026-08-29T03:14:08-07:00

## Authority and current gate

- Authoritative recovery record: `RESUME.md`.
- Approved specification:
  `docs/superpowers/specs/2026-08-29-native-vst3-adapter-correction-design.md`.
- Approved inline plan:
  `docs/superpowers/plans/2026-08-29-native-vst3-polyphonic-audio-to-midi.md`.
- Planning commit: `9390763`; pre-Task-1 checkpoint: `eb5e19e`.
- Specification SHA-256:
  `bf27a627432bb360b7e123300e01edb80228b1de0d71331d5d5e968f6d43e4d5`.
- Plan SHA-256:
  `b7dbe1a7eb3a93ba4e06575dc88c45f800191adc5e6e6ef530a7bdc51e768de3`.
- The user approved exact-plan execution with `Proceed --continuous` on
  2026-08-29. That opens Task 1 only. Gate T1 still requires separately
  explicit authority before a CMake package installation.

## Locked identities

| Build | Canonical UUID | Four 32-bit words |
| --- | --- | --- |
| Production | `4A1BA42F-6D70-4609-8B52-450C3842F11F` | `4A1BA42F 6D704609 8B52450C 3842F11F` |
| Capability probe | `6F62F8B1-B8A1-4872-A0D9-2C3C274421D8` | `6F62F8B1 B8A14872 A0D92C3C 274421D8` |
| Benchmark-only | `28713895-1CCA-47EC-919F-6CC1BCB88A8F` | `28713895 1CCA47EC 919F6CC1 BCB88A8F` |

- Descriptive ID: `com.ajuntanaga.m3-polyphonic-audio-to-midi`.
- Vendor: `ajuntanaga`.
- Product: `M3 Polyphonic Audio to MIDI`.
- Probe product: `M3 Polyphonic Audio to MIDI Probe`.
- Benchmark product: `M3 Polyphonic Audio to MIDI Benchmark`.
- Version: `0.1.0`; production subcategories: `Fx|Tools`.

## Task 1 TDD evidence

1. The untouched baseline passed with 44 native tests and 114 Python tests.
   The frozen JSFX diff against `0be04d3` was empty and the specification hash
   matched `RESUME.md`.
2. Identity RED: `python3 -m unittest tests.test_vst3_build_contract -v`
   exited 1. The dependency boundary passed; the identity test failed only
   with `vst3_ids.hpp is absent`.
3. The SDK-independent header was added with standard-library includes only.
   A first compile check exposed a C++17 test portability error in constexpr
   `std::array` equality; the test was corrected to literal per-word constexpr
   assertions without changing production code.
4. Source-validator RED: the targeted suite failed because the planned
   `validate_entries()` boundary seam was absent. The implemented seam is used
   by the real validator and is exercised with controlled source/build inputs.
5. Final targeted result: 10 tests, 0 failures. Covered exact/nonzero identity
   values, names/category/version, pre-D2 emptiness, forbidden frameworks and
   copied ABI declarations, networked build rules, misplaced SDK includes,
   VST3 code under `native/plugin`, raw/duplicate FUID tuples, and production
   references to probe/benchmark identities.
6. Final regression result: 44 native tests, 0 failures; 124 Python tests,
   0 failures. `validate_native_source.py`, Python bytecode compilation, and
   Git whitespace validation also passed.

The test commands ran serially with `nice 15` and idle I/O priority. Preflight
observed 32447 MiB available memory, load 0.54, memory-full PSI 0.00, I/O-full
PSI 0.00, and maximum readable temperature 52 C. The final exact-state
regression preflight observed 32747 MiB available, load 0.62, both full-PSI
values 0.00, and maximum readable temperature 45 C.

## Tool and containment state

- Compiler: `g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0`.
- CMake executable: absent.
- Read-only CMake package state: not installed; candidate
  `4.2.3-2ubuntu2`.
- Failed CLAP capability evidence remains immutable with manifest digest
  `12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.
- No Steinberg SDK tree was retrieved, no SDK-dependent VST3 `.cpp` source or
  `.vst3` bundle exists, and no persistent plug-in path was touched.
- No REAPER process was launched or left running. No live profile, project,
  hardware input, or Obsidian integration was changed.

## Decision

Task 1 is locally green and ready to seal. Task 2 is not entered. Stop at Gate
T1 before installing CMake; approval of Task 1 or continuous local execution
does not authorize that host-package mutation. Gate D2 remains separately
closed even after CMake is present.
