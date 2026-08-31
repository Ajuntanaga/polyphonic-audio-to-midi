# Native VST3 Testing

Updated: 2026-08-30T16:14:41-07:00

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
  2026-08-29, then separately opened Gate T1 with the exact instruction
  `Authorize Gate T1: install CMake 4.2.3-2ubuntu2 with
  --no-install-recommends for Task 2 only`.
- Immediately after the sealed Task 2 checkpoint, the user explicitly said
  `Authorize all`. As recorded in `RESUME.md`, this opens every remaining
  named gate and action in the approved 24-task plan while preserving its
  ordering, pressure limits, stop-on-first-failure rules, and evidence gates.
- Tasks 1-11 are sealed. This document records the Task 12 offline adapter,
  bundle, reproducibility, and official-validator seal. No REAPER launch is
  part of Task 12.

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

## Task 2 CMake tool-gate evidence

1. Before installation, the package candidate remained exactly
   `4.2.3-2ubuntu2`, CMake was absent, the Git tree was clean, and Task 1's
   four recorded hashes matched. The guarded preflight observed 32466 MiB
   available, load 4.38, both full-PSI values 0.00, and maximum readable
   temperature 64 C.
2. Noninteractive `sudo` correctly refused without local authentication; no
   mutation occurred in that attempt. The user then ran the approved command
   locally. `/var/log/apt/history.log` records exactly
   `apt-get install --no-install-recommends cmake=4.2.3-2ubuntu2` from
   04:35:35 through 04:35:42 PDT on 2026-08-29.
3. The transaction installed `cmake=4.2.3-2ubuntu2` and only its required
   automatic dependencies: `cmake-data=4.2.3-2ubuntu2`,
   `libjsoncpp26=1.9.6-5`, and `librhash1=1.4.6-1.1`. No recommended package,
   compiler, Ninja, Qt, VST package, or SDK was installed by this transaction.
4. Post-install verification reports `cmake version 4.2.3` and dpkg status
   `install ok installed 4.2.3-2ubuntu2`. Available memory was 32529 MiB,
   swap use was zero, load was 0.41, both full-PSI values were 0.00, and the
   maximum readable temperature was 45 C.
5. The new prerequisite test has a controlled RED: with `PATH=/nonexistent`,
   it fails only with `CMake executable is required after Gate T1`. Against
   the installed environment it passes by executing the real
   `cmake --version`, parsing the semantic version, and requiring at least 3.25.
   The existing real source validator and controlled build-rule cases continue
   to reject downloaders.
6. Final targeted result: 11 tests, 0 failures. Final regression result: 44
   native tests and 125 Python tests, 0 failures.

## Task 12 offline adapter seal

### TDD and adversarial evidence

1. The fixed-seed adversarial RED used seed `0x4D335633` and 100,000 bounded
   operations. It initially proved that a malformed producer could deliver a
   ninth generated note-on before the ledger rejected the over-polyphony
   state. The neutral ledger now reserves the active-voice count before host
   delivery, fails the ninth on closed, retains every possibly active pitch
   for cleanup, and decrements only on confirmed releases. A focused neutral
   regression protects that boundary.
2. The completed adversarial case covers parameter queue counts, offsets and
   values; state images of 0-256 bytes; bus/layout/sample formats and frame
   counts; every generated-event rejection position; configuration
   generations; process modes; start/stop/active sequences; and non-finite
   samples. It requires no crash, hang, out-of-bounds access, duplicate on,
   more than eight active notes, or retained note after successful cleanup.
3. The real-time RED added fifteen controlled forbidden-source cases before
   implementing the production-source policy. The final policy excludes
   threads, locks, conditions, futures, filesystem and stream/stdio access,
   networking, sleeping/waiting, exceptions, RTTI, recursive core functions,
   growable process containers, CLAP symbols, probe/benchmark identities,
   report environment variables, and test schedules from the production
   graph. Tests and the retained historical CLAP implementation are outside
   that scan by design.
4. The real-time executable performs 100,000 `process()` calls and 100,000
   `setProcessing(false/true)` cycles after activation. Allocation and
   deallocation counters remain unchanged, and `/proc/self/task` has the same
   entry count before and after.
5. The production-target RED found the old reservation target instead of a
   real bundle. Production and probe now use the same explicit neutral/VST3
   source graph and differ only by their locked build identity. Neither graph
   contains a CLAP source, CLAP include, test define, or the other build's
   identity.
6. The validator-runner RED began with the required module absent. Its final
   five tests require an exact kind, canonical bundle, FUID, name, category,
   subcategories, two-file bundle layout, official build-local validator,
   complete SDK manifest, pressure guard, atomic evidence, explicit
   pass/fail/infrastructure-invalid classification, and no automatic retry.

### Exact release bundles

The canonical release root contains exactly these bundle files:

```text
M3_Polyphonic_Audio_to_MIDI.vst3/Contents/Resources/moduleinfo.json
M3_Polyphonic_Audio_to_MIDI.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so
M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/Resources/moduleinfo.json
M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so
```

- Production module-info reports FUID
  `4A1BA42F6D7046098B52450C3842F11F`, name
  `M3 Polyphonic Audio to MIDI`, category `Audio Module Class`, and
  subcategories `Fx` and `Tools`.
- Probe module-info reports FUID `6F62F8B1B8A14872A0D92C3C274421D8`
  and name `M3 Polyphonic Audio to MIDI Probe` with the same category and
  subcategories.
- The production binary is a stripped x86-64 ELF shared object. It exports
  `GetPluginFactory`, `ModuleEntry`, and `ModuleExit`, has no exported
  `clap_` symbol, and contains no probe, benchmark, or report marker.

The full lexical manifests and their aggregate digests are:

```text
# production
7a6247b9d1ccd815c0bf6ff0821a906168e2bb48d755f0e22cd60450734e8738  Contents/Resources/moduleinfo.json
e6f6ebfbe522a1eb3a785db97902296931d8f57c0083904f9b656b770302e37d  Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so
bundle digest: fed1e4062ba5f29511df2c4b9f430ed3fe0d70172d897ec91dacdc5d2a9e1eaa

# probe
85b8bb18526e8f4ec4744e27069551741b01a8268efb3d97d8ab985e59fec24f  Contents/Resources/moduleinfo.json
c6be9fe2fea32ae61e4f3e1afe08a5dc77c4e09428f34fce67bb1e8a046cda0f  Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so
bundle digest: 2438e058defc21a34445dc8db6ce177ad34a098abef37d9b7c254331d22b249d
```

The bundle digest is SHA-256 over the UTF-8 concatenation of every lexical
manifest row in the form `<file-sha256>  <bundle-relative-path>\n`.

### Official validator Gate O4

- The official Steinberg validator ran exactly once against the canonical
  production bundle at `2026-08-30T23:07:10.472+00:00`. It was invoked only
  through the native pressure guard with a 300-second timeout.
- Classification is `pass`; return code is zero; the final result is exactly
  `47 tests passed, 0 tests failed`; and `automatic_retry` is `false`.
  Factory, class, bus, parameter, state, 32/64-bit process, variable-block,
  and sample-rate checks passed. The validator successfully processed 22050,
  32000, 44100, 48000, 88200, 96000, 192000, and 384000 Hz plus its four
  nonstandard positive-rate probes.
- The immutable record is
  `build/test-results/vst3-validator/production/result.json`, with adjacent
  `stdout.txt` and `stderr.txt`. Run-time input hashes are:

```text
bundle             fed1e4062ba5f29511df2c4b9f430ed3fe0d70172d897ec91dacdc5d2a9e1eaa
bundle binary      e6f6ebfbe522a1eb3a785db97902296931d8f57c0083904f9b656b770302e37d
module-info        7a6247b9d1ccd815c0bf6ff0821a906168e2bb48d755f0e22cd60450734e8738
SDK manifest       4d5b8c240b842a85b39b97ccc8b69e3bb7ed6b000709e62c07a3e41c855063f0
validator          643b9b9aa6514838bca12c981b0f62f9a634e3660a8edb812a8d858485b927f2
runner             c9d12a670b387395a331a76e5674fddc706c84fde069e70827de2c8596e1cbe1
guard              d692a90741353d44883bfc406e34599d8eb543b946f229d92d680b2203d16b53
stdout             2f8c962d8fa7df7e0d70e88dafdc71aa8e633ff73332f09d8e8027c04972e64d
stderr             e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

No second validator invocation was made during final verification.

### Reproducibility and toolchain

- `SOURCE_DATE_EPOCH=1788129797` (the latest sealed checkpoint commit time,
  `2026-08-30T22:43:17+00:00`) was used for two independent, serial,
  pressure-guarded production builds under `build/repro-a/release` and
  `build/repro-b/release`.
- Recursive comparison found no difference between A and B or between either
  reproducibility bundle and the canonical release bundle. All three complete
  manifests and aggregate bundle digests are the production values recorded
  above.
- Compiler: `g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0`; language and production
  flags: `-O3 -DNDEBUG -std=c++17 -fPIC -Wall -Wextra -Wpedantic
  -Wconversion -Wshadow -Werror -fno-exceptions -fno-rtti
  -fstack-protector-strong -fvisibility=hidden`, plus source/macro prefix maps
  from the repository root to `.` and `-DRELEASE=1`.
- Production definitions are exactly `M3_VST3_PRODUCTION_BUILD` plus CMake's
  export definition. Link hardening includes `-z relro`, `-z now`,
  `--no-undefined`, and `--build-id=none`.
- SDK source manifest SHA-256 is
  `4d5b8c240b842a85b39b97ccc8b69e3bb7ed6b000709e62c07a3e41c855063f0`.
- One earlier production-build preflight refused before starting a compiler
  because memory-full PSI was `1.49`, above the fixed `0.25` ceiling. No limit
  was loosened. Passive readings fell to `0.01`, and the later guarded build
  proceeded normally. This was not a validator invocation or retry.

### Final Task 12 verification

- Native debug: 95/95 passed.
- ASan/UBSan: the complete native suite passed with no sanitizer finding.
- TSan: the complete native suite passed in 49.90 seconds with no race report.
- Python: 142/142 passed, including the five validator-runner tests and the
  controlled forbidden-source subtests.
- Production and probe targets rebuilt serially; the source validator passed;
  the retained historical CLAP target still linked; and the final Git
  whitespace validation passed.

## Tool and containment state

- Compiler: `g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0`.
- CMake executable: `/usr/bin/cmake`, version `4.2.3`.
- CMake package state: `install ok installed 4.2.3-2ubuntu2`; the package
  candidate remains the same exact version.
- Failed CLAP capability evidence remains immutable with manifest digest
  `12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.
- The retained official VST3 SDK source tree remains offline and manifest
  verified. Production and probe bundles exist only under ignored build-local
  roots; no persistent plug-in path was touched.
- Through the Task 12 seal, no REAPER process had been launched or left
  running. No live profile, project, hardware input, or Obsidian integration
  was changed. The later authorized Task 15 disposable launch is recorded
  separately below.

## Decision

Tasks 1-11 remain sealed and Task 12's offline gates are green. Gate O4 is
satisfied by the single official-validator pass and reproducible exact bundle.
The next ordered work is Task 13's disposable VST3 staging/guard extension.
It does not authorize attachment to an existing REAPER instance, a live
profile or project, persistent installation, or hardware input.

## Task 15 Gate C5 infrastructure-invalid decision

### Authorization and preflight

- In direct response to the exact Gate C5 request, the user said `Proceed` on
  2026-08-30. That fresh response authorized exactly the presented twenty
  guarded disposable REAPER launches once; it did not weaken the serial,
  workspace-5, stop-on-first-failure, pressure, or no-retry rules.
- Every required non-launching gate passed before authority: 101 native tests
  in debug, ASan/UBSan, and TSan; the release probe build; official probe
  validation; 164 repository Python tests; 48 focused guard/runner tests; the
  native source validator; and the exact twenty-row dry plan.
- Immediately before launch, available memory was 26782.62 MiB, load was
  1.34, maximum readable temperature was 55 C, and memory-full and I/O-full
  PSI were both 0.00. Workspace 5 existed, workspace 1 remained active, and
  no REAPER process or window existed.

### Executed row and sealed evidence

- The runner launched only the first row, 44.1 kHz/block 32, in the fresh
  disposable profile on workspace 5. The guard reached its 45-second timeout
  and returned 124. Per Gate C5, the other nineteen rows were not launched and
  no retry occurred.
- The authoritative decision is `infrastructure-invalid`. The immutable row
  is
  `build/test-results/native-vst3-probe/batches/44100-32.invalid-20260831T004349Z`.
  `metadata.json` records return code 124, the exact eight runtime input
  hashes, and these validation errors: missing terminal `suite-finish`,
  non-pass capability status, nonzero capability/probe failure counts, and
  non-pass return/classification metadata.
- The partial script reached `suite-fail`, reported 77 assertion labels, and
  left every probe lifecycle/format/trigger diagnostic at `-1`. Its dry,
  source, capture, output, and event values are therefore incomplete invalid
  evidence, not measurements of product capability and not an adapter defect
  diagnosis.
- The seven-file lexical evidence manifest is:

```text
f4faaf23493b485ddcc687762c7f1840c6330ba9fa120fdb6b4b33a95b5e1a72  capability.tsv
705c756efc056ed6c05ee802a50711427871b953317ea1dda1566f1e40355a17  events.tsv
2540414e8691440cb06b6bf7e8565b5fcc3f3be9ef4166498b5aa9b5562d2297  metadata.json
1a082d5dad5bf47d299b2db25ca46fa5d3e734483fad25150e67cafcdac4332f  phase.log
e84591d477131c25565b5ab0d96211e16f13f75b396e4d9defa37befc5091f34  pressure.json
76956496d2240ccb78d9d6de6ef0abb6911e13b5a8ec1be86d895eaebaca7dbe  probe-vst3.tsv
02d8646e43cc0ea80b11f2257ca1689fdfcf6fd8494d36973dc967c528287015  state.tsv
manifest digest: 98c48c74eeea2ef8bc962689d210bfc6154cf9069fa7c4dee34ed072a4fa0958
```

### Post-seal read-only diagnosis

- The 2026-08-31 diagnosis used only the immutable row, staged sources,
  installed REAPER API documentation, prior harness evidence, and local system
  logs. It did not launch REAPER, retry the row, alter the timeout, or edit the
  probe, adapter, runner, profile, or assertion script.
- The parameter assertions use the wrong unit domain for the VST3 host
  surface. The script compares `TrackFX_GetParamEx` values against plain units
  such as A4 `400..480`, trim `-24..24`, and channel `1..16`, then passes plain
  values to `TrackFX_SetParam`. REAPER exposed this VST3 surface in normalized
  `0..1` units. All fourteen `state.tsv` rows exactly match the resulting
  normalized/default pattern, including A4 `0.5`, trim `0.5`, lowest note
  `8/84`, highest note `60/84`, and fixed velocity `99/126`; writes greater
  than one were rejected or left the default. The reporter's diagnostic
  parameters would have the same unit-domain problem if that phase were
  reached.
- The audio/MIDI observer transport was not valid. Five preserved metrics are
  exact cell-address values: source fault `2202`, capture overflow `257`,
  output nonfinite `2051`, synth peak `2100`, and dry error
  `8704 + (32 - 1) = 8735`. Every one of the 96 recorded event rows also
  follows the address formula exactly: offset is `absolute + 1`, pitch is
  `absolute + 3`, and velocity is `absolute + 4`. These values are impossible
  under the JSFX writer ranges and are not plug-in output.
- The assertion script has no shared-memory magic, source-ready generation,
  heartbeat/acknowledgement, reset readback, or observer-range gate. It
  therefore accepted the address value `2049` as `DRY_COUNT >= 320`, accepted
  address value `256` as a full capture count, and cascaded through several
  phases using fabricated events before `bypass-held` finally timed out. The
  established JSFX matrix runner has an init/ready/heartbeat handshake; Task
  14's VST3 capability harness did not carry that protection forward.
- The probe diagnostic report remains all `-1` because the lifecycle reporter
  phase was never reached, not because those diagnostics were proven missing.
  The exact underlying reason that the shared observer segment produced the
  address pattern cannot be recovered from this row because no readiness or
  attachment diagnostic was recorded.
- `suite-fail` is not the guard's exact completion sentinel and the assertion
  script closes REAPER only after `suite-finish`. The failure therefore left
  the disposable process open until the 45-second guard returned 124. The
  journal records 12.207 CPU-seconds over 45.151 seconds and a 122.2 MB memory
  peak; the preserved pressure record and cleanup show no host-pressure or
  crash signature.
- The current lexical source-contract test still passes despite both defects.
  This confirms an offline test gap rather than validating the failed runtime
  path. The sealed row remains `infrastructure-invalid` and proves no
  production-adapter defect or capability result.

### Recovery boundary

No recovery implementation or launch is authorized by this diagnosis. A
separately approved, non-launching TDD amendment should first require:

1. an explicit VST3 normalized/plain conversion layer for parameter writes,
   reads, state assertions, formatted values, and diagnostic counters;
2. a shared-memory magic/generation/heartbeat/ack handshake, reset readback,
   legal-range validation, and immediate fail-closed stop before any plug-in
   assertion when the observer is not ready;
3. a terminal failure path that closes the disposable instance or publishes a
   separately classified failure sentinel, so assertion failures become
   `fail` rather than guard timeouts;
4. offline tests that inject normalized VST3 values and the exact
   `gmem_read(index) == index` pattern and prove that neither can advance an
   audio phase; and
5. a new evidence namespace and fresh authorization for any later real REAPER
   validation. The sealed `44100-32` row is never overwritten or retried.

### Cleanup and decision

- The post-row snapshot recorded 26863.25 MiB available, load 3.16,
  temperature 59 C, and memory-full/I/O-full PSI 0.00. Cleanup left zero
  REAPER processes and windows, workspace 1 active, and workspace 5 present.
- `python3 tools/run_native_vst3_probe.py --check` fails closed on the sealed
  invalid first row and nineteen missing tail rows, as required.
- Gate C5 did not pass. Task 16 and the remaining detector-port/release tasks
  are blocked. The only safe next design action is a separately approved,
  non-launching harness-recovery amendment. This result authorizes neither a
  retry nor an adapter, runner, timeout, profile, or assertion-script edit.
