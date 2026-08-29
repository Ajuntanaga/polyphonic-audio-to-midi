# Native CLAP Testing

This file records reproducible native-only evidence and the separately
authorized disposable Task 10 host gate. It does not authorize another REAPER
launch, a persistent plug-in install, detector-core porting beyond the current
gate, or clean-DI/hardware work.

## Toolchain

- Date: 2026-08-28
- Compiler: `g++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0`
- Build tool: `GNU Make 4.4.1`
- Kernel: `Linux 7.0.0-30-generic x86_64 GNU/Linux`
- Language mode: C++17, exceptions and RTTI disabled for native targets
- CLAP headers: official 1.2.10 at commit
  `195b42a004144fab0b3cf95e9c067187d15365b7`

## Reproduction

From the repository root:

```bash
make -C native test
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  make -C native sanitize
make -C native tsan
make -C native production
python3 tools/validate_native_source.py .
git diff --check
```

These commands are offline and do not start REAPER.

## Prepared-configuration exchange evidence

The Task 7 suite runs 39 native tests. Its exchange test covers one initial
generation plus generations 2 through 100,000 for both the atomic request
snapshot and the three-slot prepared publication path. Every claimed test
payload contains 64 generation-derived coherence words. The consumer checks
payload coherence before commit and requires adopted generations never to
regress.

Covered deterministic states:

- initial active generation;
- highest-ready selection and stale-ready reclamation;
- active/claimed slot protection and no-slot retry;
- claim, commit, and cancel;
- wrap-safe unsigned generation order;
- a three-attempt bounded atomic snapshot;
- structural versus runtime parameter handling; and
- old-channel note release before a prepared MIDI-channel change is exposed.

The first concurrent implementation produced a real test failure: a slot could
complete a `ready -> writing -> ready` cycle between scan and claim, pairing an
old generation tag with a new payload. The corrected implementation acquires
the slot before re-reading its generation, including the stale-reclamation
path.

Results on the toolchain above:

- normal strict-warning build: 39 tests, 0 failures;
- AddressSanitizer plus UndefinedBehaviorSanitizer: 39 tests, 0 failures;
- GCC ThreadSanitizer: supported, 39 tests, 0 failures and no race report;
- optimized production shared-object link: pass; and
- native source-boundary validator: pass.

No REAPER process was started for this evidence.

## Task 10 minimal CLAP capability gate — failed

The user explicitly authorized Gate C2 on 2026-08-29. A fresh non-launching
preflight passed, and the runner emitted exactly four serial workspace-5 rows
at 48 kHz for block sizes 32, 64, 128, and 256. The real matrix then ran once.
Block 32 completed its guarded host process but failed the capability contract,
so the fail-closed runner archived the row and did not launch 64, 128, or 256.
No retry occurred.

Preserved directory:

`build/test-results/native-clap-probe/batches/32.invalid-20260829T074326Z`

The guard return code was zero and `phase.log` reached `suite-finish`.
`capability.tsv` records:

- status `fail` and 19 failure labels;
- sample rate 48000 and block size 32;
- dry-error sentinel `inf` because the scripted completion condition timed out;
- positive ReaSynth peak `0.43603515625000033`;
- zero source fault and zero capture overflow;
- non-exact total parameter count;
- all fourteen persistent parameters unwritable through the tested ReaScript
  surface, with attempted mutations and restores remaining at defaults;
- Status not restored to Ready;
- scripted-phase timeout;
- no host `reset` callback; and
- no second CC119 trigger, because the held-note phase was never entered.

The same evidence positively records one create/init/activate/start and one
stop/deactivate/destroy, float32 processing, separate host buffers, passing
alias and separate dry-path self-tests, the first CC119 trigger reaching the
plug-in, finite positive synth output, and no probe overflow. The first sixteen
parameter names/ranges/defaults produced no failure labels. The capture is not
sufficient to attribute the parameter-write failure to REAPER, ReaScript, or
the CLAP adapter, and no corrective change was attempted.

Pressure remained inside every stability stop:

| Snapshot | Available MiB | Load 1 | Temp C | Memory full PSI | I/O full PSI |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before | 29982.57 | 2.12 | 50 | 0.00 | 0.05 |
| After | 29808.68 | 2.67 | 49 | 0.00 | 0.03 |

No REAPER application process remained after cleanup. The only
`pgrep -a reaper` result was Linux kernel thread `118 [oom_reaper]`.

Evidence hashes:

| File | SHA-256 |
| --- | --- |
| `capability.tsv` | `b1479cfc7ff7271fac8b47585fad6a0868c677b54942145c9b71ef1d214a579c` |
| `events.tsv` | `46b4558584b343ad30470d99a629c45fcaa99a609e829b6bb689b32dd080fe7e` |
| `metadata.json` | `c4121cd9b867187dcf63a2fd43ec75cb276e1f1e4c28e8f6bd128e41a03182d7` |
| `phase.log` | `5da9ddc89b73baf5cdf87edabbe673ccb611ca11593b085b6d9d8d8e144a6d19` |
| `pressure.json` | `8e182654f53f286e6800dc944b0da5e476cce49e97fc90223b1e0abe040f7973` |
| `probe-native.tsv` | `8561781da9b1e2231ea6e162a61865b0a8b25f3fad78af4054d805e0148da61d` |
| `state.tsv` | `152bee454f6ce1d18957dba528927ca622a50cca923dbaca58a07fa7df57ffd4` |

The SHA-256 of the lexically ordered seven `sha256sum` rows is
`12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.

Gate C2 is failed. Per the approved plan, Task 11 and all detector-port work
stop here. The remaining CLAP rows, any retry, VST3 SDK retrieval, and a VST3
adapter correction each require new explicit authorization; the next allowed
design action is a separately approved VST3 adapter correction.
