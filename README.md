# M3 Polyphonic Audio to MIDI

Status: the JSFX detector is retained as a behavioral oracle; a native Linux
x86-64 VST3 effect now provides the practical low-register live-MIDI path.
It is built and staged in a disposable REAPER profile, not installed into the
user's persistent VST3 directory. The production VST3 now includes a custom,
resizable performance editor. Its attachment and presentation are verified;
the final physical-mouse gesture check remains manual on this rootless
Xwayland workstation.

M3 is a source-editable, causal audio-to-MIDI effect for REAPER and a
downstream VSTi. The practical native path is a C++17 VST3 effect with a
single audio-thread detector. Lua only creates the disposable REAPER track;
it does not perform detection or MIDI generation. The M3 profile maps the
eight open strings to MIDI `32,36,40,44,48,52,56,60` (`G# C E G# C E G# C`,
low to high) and emits ordinary discrete MIDI rather than MPE.

## Use now: low-string live MIDI

The staged native profile creates one armed, monitored track:

```text
Revelator input 1 -> M3 Polyphonic Audio to MIDI (VST3) -> ReaSynth
```

The default disposable profile is configured for 48 kHz and 256 samples. For
the Revelator's 96 kHz mode, stage the dedicated profile below. Both profiles
use MIDI notes `32..60`—the eight open strings—muted dry audio, and one
detected note at a time. That makes it
appropriate for clean low-register eight-string lines and single-note playing;
it is **not yet a polyphonic chord transcriber or a full-fretboard tracker**.
The native detector and its MIDI note-on/off path have been verified with an
audio-driven REAPER/VST3 probe. Final guitar calibration remains physical-input
work: plug the guitar into Revelator input 1, arm/monitor the staged track,
then adjust input gain or detector sensitivity only if needed.

To prepare another disposable profile without touching the live REAPER setup:

```bash
python3 tools/stage_live_midi_env.py \
  --output build/m3-native-live-midi \
  --detector native
```

For the 96 kHz Revelator profile used for live guitar, stage it separately:

```bash
python3 tools/stage_live_midi_env.py \
  --output build/m3-native-live-midi-8open-96k \
  --detector native \
  --sample-rate 96000
```

The native bundle stays under `build/`; staging copies it only into that
disposable profile. No persistent plug-in installation is required.

### Build and validate the editor bundle

The M3 editor release was produced with serial, low-priority commands:

```bash
ionice -c 3 nice -n 10 cmake -S . -B build/vst3/release \
  -DCMAKE_BUILD_TYPE=Release
ionice -c 3 nice -n 10 cmake --build build/vst3/release \
  --target m3_vst3_production -j1
ionice -c 3 nice -n 10 cmake --build build/vst3/release \
  --target m3_validate_production -j1
ionice -c 3 nice -n 10 python3 -B -m unittest \
  tests.test_vst3_build_contract tests.test_vst3_validator_runner -q
python3 -B tools/validate_native_source.py .
ionice -c 3 nice -n 10 python3 -B tools/run_vst3_validator.py \
  --kind production \
  --bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
```

The official validator result is `47 tests passed, 0 tests failed`. The custom
editor opens at `1024 x 620` and can be resized. Its visible groups are Header
and live state, Source + Tuning, Tracking, Performance Range, and Advanced ·
Live Routing. `Ready` is truthful text from the existing Status parameter; the
editor does not fabricate an input meter, detected-note display, tuner, or
confidence indicator. A host that cannot attach the custom editor can still
use the unchanged generic VST3 parameter surface.

### Start the live chain

On the desktop that has the Revelator attached, launch the prepared 96 kHz
eight-open-string profile without touching the normal REAPER profile:

```bash
/home/ajuntanaga/opt/REAPER/reaper -newinst -noactivate \
  -cfgfile "$PWD/build/m3-native-live-midi-8open-96k/reaper.ini" -nosplash \
  "$PWD/build/m3-native-live-midi-8open-96k/Scripts/ajuntanaga_M3 Live Guitar to MIDI.lua"
```

REAPER accepts a Lua script as a command-line argument, so that command creates
one armed, monitored `M3 Native 8-String Guitar to MIDI` track automatically:

```text
Revelator input 1 → M3 Polyphonic Audio to MIDI → ReaSynth
```

Play clean single-note lines first. The profile is deliberately limited to the
eight open-string range (MIDI 32–60), uses muted dry audio, and sends the
detected note to ReaSynth. If there is no REAPER track-meter activity, choose
the Revelator's first mono input in REAPER's track input menu; if there is input
but no synth note, lower the guitar/interface gain before increasing detector
sensitivity.

For the remaining manual 96 kHz editor check, use a physical mouse in only
this disposable instance:

1. Confirm REAPER reports `96000 Hz` without changing the interface or normal
   REAPER configuration.
2. Open the staged M3 FX. Confirm the custom editor is `1024 x 620`, resize it,
   and check that the controls reflow without overlap.
3. Note that Dry Audio is `OFF` in the live-chain preset. Click it once, then
   use REAPER's `Param` menu to confirm `Dry audio` is the last-touched host
   parameter. Click it once more to restore `OFF`.
4. Play clean single notes from the low strings and confirm that the staged
   track produces downstream MIDI/ReaSynth output. This is the physical-input
   calibration check; it does not broaden the detector's one-note claim.
5. Close only the disposable REAPER instance without saving the project.

Automated pointer injection is intentionally not part of this procedure. On
the validation workstation, rootless Xwayland exposed a nested VSTGUI event
surface but could not prove that XTest would deliver to it, and no safe
installed `xdotool`, `ydotool`, or `wtype` input path was available. The
final automated attempt therefore injected no Button1 event and made no GUI
parameter claim.

Task 11 passed a disposable REAPER chain containing the synthetic signal
source, the production detector, MIDI capture, ReaSynth, and an audio-output
probe. All 13 cases passed: mono, dyad, one full eight-note chord, and ten
repeated eight-note Panic trials. MIDI note-on/off order was exact, capture had
no overflow or duplicate/unexpected notes, normal dry-path error was at most
`3.33e-16`, and every case produced nonzero ReaSynth output.

All ten Panic trials released the eight active notes in `1.750–5.333 ms`. The
last trial executed the actual Safe Bypass ReaScript inline, verified the
detector was disabled after its 50 ms cleanup delay, then allowed the
disposable test runner to delete only that detector while ReaSynth remained.
The measured synthetic onset evidence ranged from `41.333 ms` for C4 to
`177.333 ms` for G#1/C2; the low notes need more causal evidence than the high
notes. The detector declares no lookahead or plug-in delay compensation.

[NeuralNote](https://github.com/DamRsn/NeuralNote) informed the architectural
comparison, but it is not linked, downloaded, or required. Its published
pipeline is an offline transcription design with a greater-than-one-second
low-bin CQT path and a non-causal event algorithm. This project instead uses a
bounded causal resonator/selector/lifecycle path intended for live playing.

Task 13 reached a terminal JSFX result at 48 kHz/128 samples. The final M3 slice
has 100% precision/recall over 45 cases and 124 notes, and open-string latency
passes. Three/four-note completion is `78.667/99.600 ms` median/P95, however,
and two 10,000-block dense-chord runs consumed about 59% of the deadline at
median with every block above the 50% hard limit. The JSFX is therefore not
performance-ready and must not be installed. See
[docs/PERFORMANCE.md](docs/PERFORMANCE.md) for hashes and the recorded
`native amendment required` decision.

The earlier CLAP experiment remains preserved as historical evidence. The
current implementation uses VST3 because its disposable host probe succeeded
and it integrates directly with the staged REAPER chain. The future work that
matters for music quality is physical 8-string calibration and, separately,
expanding the detector beyond one simultaneous note.

The probe evidence is not a substitute for a guitar performance test. It proves
the native effect can turn audio into downstream MIDI in REAPER; it does not
prove tracking quality for a particular instrument, pickup, tuning, or playing
style. See [docs/TESTING.md](docs/TESTING.md) for the isolated verification
boundary and [docs/MIDI-LIFECYCLE.md](docs/MIDI-LIFECYCLE.md) for cleanup
behavior.
