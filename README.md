# M3 Polyphonic Audio to MIDI

Status: Tasks 1–11 verified; Task 12 synthetic metrics next; not installed.

Source-editable, causal, real-time polyphonic audio-to-MIDI for REAPER and a
downstream VSTi. Production detection and MIDI generation are JSFX/EEL2. Lua is
used only for disposable host testing and the guarded Safe Bypass action. The
M3 profile maps the eight open strings to MIDI `32,36,40,44,48,52,56,60`
(`G# C E G# C E G# C`, low to high) and emits ordinary discrete MIDI rather
than MPE.

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

This is synthetic dummy-audio evidence, not a live-guitar or audible hardware
claim. Persistent installation, live projects, audio-interface input, clean-DI
metrics, and long-run deadline/latency measurements remain gated. Do not treat
the current build as performance-ready. The fresh local source gate is 53 tests
plus a clean standalone contract. See [docs/TESTING.md](docs/TESTING.md) for the
isolated verification boundary and
[docs/MIDI-LIFECYCLE.md](docs/MIDI-LIFECYCLE.md) for cleanup behavior.
