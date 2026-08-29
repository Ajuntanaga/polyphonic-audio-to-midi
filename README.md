# M3 Polyphonic Audio to MIDI

Status: terminal JSFX experiment; native CLAP design approved; native
implementation plan prepared; not implemented or installed.

Source-editable, causal, real-time polyphonic audio-to-MIDI for REAPER and a
downstream VSTi. The current experimental detector is JSFX/EEL2. The approved
next runtime is a CLAP effect with a format-neutral C++17 core; its detailed
[native implementation plan](docs/superpowers/plans/2026-08-28-native-clap-polyphonic-audio-to-midi.md)
is written, but no native code or dependency has been added yet. Lua remains
limited to disposable host testing and the guarded Safe Bypass action. The M3
profile maps the eight open
strings to MIDI `32,36,40,44,48,52,56,60` (`G# C E G# C E G# C`, low to high)
and emits ordinary discrete MIDI rather than MPE.

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

The approved native amendment selects a Linux x86-64 CLAP track effect, raw
MIDI 1.0, a single audio-thread detector, a fixed 64-sample decision cadence,
and REAPER's generic parameter view for the first revision. The committed
[native CLAP design](docs/superpowers/specs/2026-08-28-native-clap-polyphonic-audio-to-midi-design.md)
was introduced at design checkpoint `3ac7dcb`; the written specification was
approved on 2026-08-28. The native implementation plan was prepared on
2026-08-28. Dependency retrieval, native source work, and every REAPER launch
remain gated exactly as stated in that plan.

This remains synthetic dummy-audio evidence, not a live-guitar or audible
hardware claim. Persistent installation, live projects, audio-interface input,
clean-DI metrics, and native implementation remain separately gated. The fresh
local source gate is 90 tests plus a clean
standalone contract. See
[docs/TESTING.md](docs/TESTING.md) for the isolated verification boundary and
[docs/MIDI-LIFECYCLE.md](docs/MIDI-LIFECYCLE.md) for cleanup behavior.
