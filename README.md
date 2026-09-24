# M3 Polyphonic Audio to MIDI

Status: the JSFX detector is retained as a behavioral oracle; a native Linux
x86-64 VST3 effect now provides the practical low-register live-MIDI path.
It is built, validated, and installed in the user's VST3 directory, with the
previous bundle retained as a recoverable backup. The production VST3 includes
a custom, resizable performance editor. Its attachment and presentation are
verified; musical tracking from the physical instrument remains the final
player-generated validation step.

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
use MIDI notes `32..60`—the eight open strings—and muted dry audio. The native
detector now selects a bounded set of up to the configured Maximum Polyphony
(1–8) rather than disabling detection above one voice. Synthetic native and
VST3 tests cover a single tone at the default limit and an independent two-tone
dyad at a limit of two; they do not constitute a physical guitar chord-quality
claim. Final guitar calibration remains physical-input work: plug the guitar
into Revelator input 1, arm/monitor the staged track, then adjust input gain or
detector sensitivity only if needed.

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

If the io24/Revelator is in use elsewhere, stage a separate profile against
the computer's normal stereo audio system. This leaves both the interface and
the normal REAPER profile untouched:

```bash
python3 tools/stage_live_midi_env.py \
  --output build/m3-native-live-midi-system \
  --input-device plughw:Generic_1,0 --output-device plughw:Generic_1,0 \
  --input-channels 2 --output-channels 2 \
  --sample-rate 96000 --block-size 512 \
  --detector native \
  --native-bundle build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI.vst3
```

The native bundle stays under `build/`; staging copies it only into that
disposable profile. No persistent plug-in installation is required.
On the validation workstation, `Generic_1` is the built-in ALC257 codec and is
distinct from the `R24` io24. Its capture stream runs natively at 96 kHz/512;
the ALSA `plughw` layer keeps REAPER's processing graph at 96 kHz/512 while
converting the built-in playback stream to the codec's 48 kHz hardware rate.

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

The recorded production validator result is `47 tests passed, 0 tests failed`.
The native VST3 host matrix also exercises 44.1, 48, 88.2, and 96 kHz with
buffer sizes `16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1000,
1024, 1536, 2048, 4096`. It verifies exact dry-audio passthrough, in-range MIDI
event offsets, and identical absolute note-on/note-off sample positions across
every partition at a given rate. A separate timing regression keeps detector
attack timing within 2 ms across those four rates. These are deterministic
in-process VST3 host tests; the physical interface and DAW still determine which
rate/buffer combinations their audio driver can sustain without dropouts.
The current custom editor opens at `1024 x 468` and can be resized. Its live
surface follows the selected Mechanical Night Arc reference: a wide header,
one eight-voice ivory meter bank, and a compact row of performance controls.
Each read-only circular meter shows a detector estimate's note and signed
cents; the header reports the bounded live voice count. The separate Settings
page exposes the complete parameter surface. The VST3 host owns the input bus
layout: mono is analyzed directly, while stereo is averaged when both sides
carry signal and uses the active side at unity when the other side is silent.
There is no plug-in mono/stereo or L/R selector.

In M3 mode, double-click any tuner meter to calibrate its physical string.
Tune and hold the named open string until it locks, slide steadily to fret 24
and back to open, then hold the returned open note briefly. The learned
25-fret cents/timbre map is saved with the VST3 project state and helps keep
that string on its corresponding tuner lane. The fixed instrument prior is the
D'Addario NYXL0980 set in thick-to-thin order: `.080, .060, .044, .032, .024,
.016, .012, .009`, tuned `G# C E G# C E G# C`. Calibration supplies the final
per-string harmonic fingerprint; the gauge, tuning, and playable fret ranges
provide the bounded assignment prior. Synthetic calibrated detuned-unison
tests keep two same-note sources on their distinct physical tuner lanes at
44.1, 48, 88.2, and 96 kHz, while a single source remains one lane.

`MIDI Routing` selects either `Single`, which sends every note on `MIDI Ch`,
or `Per Voice`. In M3 mode, tuner/string lane 1 uses `MIDI Ch`, lane 2 uses the
next channel, and so on through all eight lanes, wrapping after channel 16;
this mapping does not depend on note attack order. General mode assigns its
active voices to the same bounded channel range dynamically. A voice retains
its assigned channel through note-off, retry, and panic cleanup. Calibrated
same-pitch strings carry distinct real-time voice identities, so they remain
independent on their per-lane channels. This is standard channelized MIDI
routing rather than MPE. `Ready` remains truthful
text from the existing Status parameter, and no displayed voice is claimed to
have been delivered as a host MIDI event. A host that cannot attach the custom
editor can still use the unchanged generic VST3 parameter surface.

The host's generic parameter list also exposes a read-only strongest-voice
projection as `Tuner note` and `Tuner cents`. This is a compatibility view for
hosts that do not open the editor. It does not reduce the eight-voice editor
stack or the polyphonic MIDI output to monophonic operation.

### Start the live chain

To test while the io24 is reserved by another session, launch the prepared
96 kHz / 512-sample profile for the computer's normal ALSA device without
touching the normal REAPER profile:

```bash
/home/ajuntanaga/opt/REAPER/reaper -newinst -noactivate \
  -cfgfile "$PWD/build/m3-native-live-midi-system-routing-96k-512/reaper.ini" -nosplash \
  "$PWD/build/m3-native-live-midi-system-routing-96k-512/Scripts/ajuntanaga_M3 Live Guitar to MIDI.lua"
```

REAPER accepts a Lua script as a command-line argument, so that command creates
one armed, monitored `M3 Native 8-String Guitar to MIDI` track automatically:

```text
System audio input → M3 Polyphonic Audio to MIDI → ReaSynth
```

Play clean single-note lines first. The profile is deliberately limited to the
eight open-string range (MIDI 32–60), uses muted dry audio, and sends the
detected note to ReaSynth. If there is no REAPER track-meter activity, choose
the intended system input in REAPER's track input menu; if there is input but
no synth note, lower the guitar/interface gain before increasing detector
sensitivity.

For the remaining manual 96 kHz editor check, use a physical mouse in only
this disposable instance:

1. Confirm REAPER reports `96000 Hz` without changing the interface or normal
   REAPER configuration.
2. Open the staged M3 FX. Confirm the custom editor is `1024 x 468`, resize it,
   and check that the controls reflow without overlap.
3. Note that Dry Audio is `OFF` in the live-chain preset. Click it once, then
   use REAPER's `Param` menu to confirm `Dry audio` is the last-touched host
   parameter. Click it once more to restore `OFF`.
4. Play clean notes from the low strings and confirm that the staged track
   produces downstream MIDI/ReaSynth output. Treat chord and cents display
   quality as a separate physical-input calibration exercise; the Voice Stack
   reports detector estimates, not a global in-tune verdict.
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
matters for music quality is physical 8-string calibration and broader
polyphonic chord-quality and latency qualification across pickups, tunings, and
playing techniques.

The probe evidence is not a substitute for a guitar performance test. It proves
the native effect can turn audio into downstream MIDI in REAPER; it does not
prove tracking quality for a particular instrument, pickup, tuning, or playing
style. See [docs/TESTING.md](docs/TESTING.md) for the isolated verification
boundary and [docs/MIDI-LIFECYCLE.md](docs/MIDI-LIFECYCLE.md) for cleanup
behavior.
