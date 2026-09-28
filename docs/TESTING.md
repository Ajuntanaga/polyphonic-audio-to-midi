# Isolated testing boundary

All automated REAPER work uses a disposable profile under `build/`. Never point
these tools at `~/.config/REAPER`, a live project, or a user Effects/Scripts
tree. The staging tool rejects a destination at, below, or above the live
profile and copies only repository Effects, Scripts, the synthetic manifest,
and disposable result directories.

## Source checks

Run the complete local source suite and standalone contract validator from the
repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/validate_source.py .
git diff --check
```

These checks do not open REAPER and should run before any guarded host launch.

## Native pre-live checks and recording replay

The native suite includes the four supported rates (44.1, 48, 88.2, and
96 kHz) and 17 host partitions from 16 through 4096 samples. Build and run it
without opening a DAW:

```sh
cmake -S . -B build/vst3/release -DCMAKE_BUILD_TYPE=Release
cmake --build build/vst3/release --target m3_native_tests -j2
build/vst3/release/m3_native_tests
```

`m3_replay` is the offline bridge for recorded strings. It accepts mono or
stereo RIFF/WAVE PCM16, PCM24, PCM32, or float32, converts stereo to the same
mono detector input used by the plug-in, and reports a deterministic result
fingerprint and labeled-frame metrics:

```sh
cmake --build build/vst3/release --target m3_replay -j2
build/vst3/release/m3_replay \
  --wav recordings/string-1.wav \
  --labels recordings/string-1.tsv \
  --calibration recordings/m3-calibration.bin \
  --block 512
```

The optional calibration input may be either the exact `M3CB` calibration
image or the raw combined VST3 state image (persistent settings followed by
`M3CB`). Labels use exact sample indices and this header:

```text
start_sample	end_sample	midi_note	string_mask
```

Rows may overlap for chords. `string_mask=0` scores only the MIDI note; a
nonzero decimal bit mask scores exact physical tuner lanes and is preferred
for isolated-string and same-note recordings. The replay engine is verified
invariant at partitions 1, 17, 64, 128, 511, and 4096. The completed sanitized
A4=440 physical calibration bank is retained at
`tests/fixtures/m3_physical_a440/calibration-v1.m3cb`; its manifest records the
eight source hashes without publishing workstation paths or raw recordings.
Offline replay remains complementary to, not a substitute for, live DAW use.

For a physical string recorded as stable individual frets rather than a
continuous glide, the same tool can derive an `M3CB` map from two labeled
passes over every fret. The single-bit `string_mask` must identify one physical
lane, and `--a4` must match the reference used while recording:

```sh
build/vst3/release/m3_replay \
  --wav recordings/string-8.wav \
  --labels recordings/string-8-primary.tsv \
  --a4 440 \
  --derive-calibration-string 0 \
  --calibration-output recordings/string-8.m3cb \
  --block 512
```

The derivation accepts stable offsets strictly inside the nearest-semitone
boundary, requires at least two consistent observations for all 25 frets, and
uses the generated map immediately for the reported replay result. It does not
modify the real-time double-click glide workflow.

An optional fifth TSV column, `calibration_pass`, makes three-pass physical
captures explicit. Pass `1` is the ascending walk, pass `2` is the descending
walk, and pass `3` (or a later ID) contains isolated-note checks. Each pass has
equal influence on a fretted pitch center regardless of repeated holds inside
that pass. When one of three pass means is outside the 24-cent repeatability
corridor, the closest consistent pair is retained; two disagreeing passes
still fail closed. The bidirectional walk remains the harmonic fingerprint,
while isolated notes refine pitch only. Fret zero remains anchored to the two
walk passes so later open-string attacks cannot move the instrument reference.
Four-column label files retain the prior observation-weighted behavior.

Pass an existing `M3CB` with `--calibration` while deriving the next string to
preserve its measured lanes and replace only the requested string. This builds
the comparison bank needed for physical-lane assignment without replaying or
re-estimating earlier recordings.

Add `--label-details` to print one result row per labeled hold. This separates
a weak fret, attack window, or physical-lane assignment from the aggregate
replay score while calibrating real strings.

The software-only detector benchmark is:

```sh
cmake --build build/vst3/release --target m3_vst3_benchmark -j1
```

It prints deadline ratios for dense eight-pitch and calibrated four-string
unison workloads at every supported sample rate and block sizes 32–1024. Its
scope is explicitly `detector_core`; it does not claim DAW, driver, or hardware
round-trip performance.

## Disposable profile

Stage only the repository-owned test environment:

```sh
python3 tools/stage_reaper_test_env.py \
  --reaper "${M3_REAPER:-$HOME/opt/REAPER/reaper}" \
  --output build/reaper-test
```

The profile selects dummy audio at 48 kHz with a 128-sample block. Staging
removes disposable REAPER keyboard/JSFX cache files so no persistent action or
cache state is imported.

## Guarded host integration

Every GUI launch must go through the guard and explicitly target workspace 5:

```sh
python3 tools/run_guarded_reaper.py --gui --workspace 5 \
  --profile build/reaper-test/reaper.ini \
  --completion-file build/reaper-test/test-results/phase.log \
  --timeout-seconds 60 -- \
  build/host-integration.RPP \
  'build/reaper-test/Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua'
```

The guard starts a nonactivating new REAPER instance and keeps its window on
workspace 5. It limits the process to one logical CPU at 50%, uses nice 10 and
idle I/O, caps memory at 512 MiB with a 384 MiB high watermark, caps swap at
64 MiB, caps tasks at 64, disables core dumps and real-time priority, and
enforces a hard wall timeout. It restores only a focus steal caused by the test;
it does not move the user's current work to workspace 5.

The integration runner creates one temporary track and the chain Signal Source
-> production detector -> MIDI Capture -> ReaSynth -> Synth Output Probe. It
does not touch an existing track or save a live project. Failure leaves the
detector intact. Deletion is allowed only in the final disposable trial after
all ten Panic trials pass and the actual Safe Bypass file has disabled that
detector.

## Accepted Task 11 result

The accepted run is preserved under `build/evidence/task-11-results/`. Success
requires all of the following, not merely REAPER exit status:

- `phase.log` ends in `suite-finish` and contains exactly one
  `safe-bypass-inline-start`;
- `summary.tsv` has 13 passing case rows, exact event counts, zero overflow,
  no missing/unexpected/hanging notes, and nonzero synth output;
- `safety.tsv` has trials 1 through 10 in order, every trial passes, all eight
  note-offs arrive within 500 ms, and synth output remains present;
- only trial 10 reports detector disabled/deleted, after the Safe Bypass action;
- no REAPER process remains after the guarded instance exits.

The preserved SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `events.tsv` | `cf3a128ab1442055039bb39eeef434a50630cd30c7ee8b32a5242d20194d987a` |
| `summary.tsv` | `96fbad6c2e175ecfc7060b96c9a69aa0e34c9c9e4edc7f692f7d870ba45db2d2` |
| `safety.tsv` | `1eedf2e3deb52f54687dbe9ebd50f762f543be84bdb1c164c2de467d83e0e92d` |
| `phase.log` | `e616554dbe23678dcc3b3426a506e195b1875c5ed7e57c2d81b3900278decd30` |

A launcher exit status of 124 can mean the hard timeout closed a still-open
disposable instance; it is not a test pass by itself. Accept a core-harness run
only when its expected result file has a fresh timestamp, suite state `2`, and
failed assertion ID `0`. Accept the host integration only from the full result
assertions above.

This procedure proves synthetic dummy-audio behavior. It does not authorize or
prove persistent installation, live guitar/audio-interface input, clean-DI
metrics, live-project modification, audible monitoring, or REAPER MCP use.

## Task 13 terminal evidence

The current JSFX is accuracy-green at 48 kHz/128 samples but is not eligible for
installation. The authoritative synthetic slice is
`build/test-results/task13-v232-final-jsfx-48k128-slice`. Repeated 10,000-block
deadline tables are under
`build/test-results/task13-performance-48k128-10000/`. Exact metrics and hashes
are in `docs/PERFORMANCE.md`.

Do not continue JSFX tuning, run live input, install persistently, or begin a
native port from this checkpoint. The next allowed technical action is a new
native-design amendment after explicit user approval.
