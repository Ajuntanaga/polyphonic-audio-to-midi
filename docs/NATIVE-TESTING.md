# Native CLAP Offline Testing

This file records reproducible native-only evidence. It does not authorize a
REAPER launch, a persistent plug-in install, detector-core porting beyond the
current gate, or clean-DI/hardware work.

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
