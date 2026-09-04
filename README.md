# M3 Polyphonic Audio to MIDI

Status: the JSFX detector is retained as a behavioral oracle; a native Linux
x86-64 VST3 effect now provides the practical low-register live-MIDI path.
It is built and staged in a disposable REAPER profile, not installed into the
user's persistent VST3 directory.

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

It is configured for 48 kHz, 256 samples, MIDI notes `32..60`—the eight open
strings—muted dry audio, and one detected note at a time. That makes it
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

The native bundle stays under `build/`; staging copies it only into that
disposable profile. No persistent plug-in installation is required.

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
