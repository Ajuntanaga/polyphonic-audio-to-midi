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

## Disposable profile

Stage only the repository-owned test environment:

```sh
python3 tools/stage_reaper_test_env.py \
  --reaper /home/ajuntanaga/opt/REAPER/reaper \
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
