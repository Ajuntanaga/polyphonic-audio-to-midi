# Native CLAP Amendment: Real-Time Polyphonic Audio-to-MIDI for REAPER

Date: 2026-08-28
Architecture approved in chat: 2026-08-28
Document status: written specification awaiting user review

## 1. Authority and amendment boundary

This document amends the approved JSFX-first design at
`/home/ajuntanaga/Documents/Codex/2026-08-25/c/outputs/2026-08-25-realtime-polyphonic-audio-to-midi-design.md`.
It replaces only the production runtime, host adapter, processing cadence, and
first-native UI decision. The musical contract, detector model, validation
thresholds, safety gates, and separately authorized actions remain in force.

The approved native architecture is:

- a Linux x86-64 CLAP audio effect placed before a downstream VSTi;
- a format-neutral C++17 detector core with no external DSP or model runtime;
- ordinary discrete MIDI 1.0 output on one configurable channel;
- a fixed 64-sample decision cadence independent of the host block size;
- REAPER's generic parameter interface for the first native revision; and
- no plug-in-owned worker thread, helper process, lookahead, or declared
  latency.

The existing JSFX checkpoint remains frozen as a behavioral oracle and usable
experimental fallback. This amendment does not authorize a native port,
dependency retrieval, installation, a REAPER launch, clean-DI or hardware
input, live-project changes, or REAPER MCP.

## 2. Reason for the amendment

The JSFX experiment reached its approved hard stop:

- At 48 kHz with a 128-sample block, all 45 M3 cases and 124 expected notes
  passed with precision, recall, and F1 of `1.0` and no duplicate or hanging
  notes.
- Single-open latency passed at `21.333 ms` median and `40.133 ms` P95.
- Three/four-note chord completion failed at `78.667 ms` median and
  `99.600 ms` P95 against the `40/65 ms` limits.
- Two independent 10,000-block dense-M3 runs had median deadline fractions of
  `0.588229` and `0.594384`; every block exceeded the `0.50` hard limit.
- The 96 kHz 32+56 regression emitted a false MIDI 44.

The detector logic is accurate enough to preserve and port, but the JSFX
runtime is not performance-ready. Native execution is intended to recover CPU
headroom and permit a host-block-independent decision schedule. It must not
hide the failure by adding buffering or relaxing the existing gates.

## 3. Runtime choice and rejected alternatives

### 3.1 Selected: CLAP effect plus format-neutral core

REAPER supports CLAP audio/MIDI plug-ins. CLAP exposes audio buffers, sorted
input events, timestamped output events, note/MIDI ports, parameters, state,
latency reporting, and a small stable C ABI. This gives the project a narrow
adapter while keeping the detector independent of any plug-in format.

The implementation must first prove REAPER's exact outbound raw-MIDI behavior
with a disposable minimal plug-in. The detector is not ported until that probe
passes.

### 3.2 Fallback: VST3 adapter over the same core

VST3 can carry sample-offset output events and its current SDK is MIT-licensed,
but it has a larger object model, SDK surface, and packaging burden. It is the
fallback only if the minimal CLAP capability probe fails. Switching adapters
requires a separately approved short design correction before implementation
continues; it does not permit two parallel production formats.

### 3.3 Rejected: REAPER extension, ReaScript detector, or external worker

A REAPER extension is not a conventional track effect. ReaScript does not run
inside the audio callback. An external detector or helper thread adds
scheduling jitter, communication latency, state synchronization, and another
failure boundary. These choices conflict with the minimum-reliable-latency
goal and are excluded from the first native revision.

LV2 is technically viable, but its bundle metadata and Atom/MIDI integration
would add more first-port surface than CLAP without improving this design's
latency model.

## 4. Product scope

### Included

- One native CLAP audio effect for Linux x86-64.
- Stereo input and output with Left, Right, or equal-power Downmix detector
  selection.
- Unmodified dry passthrough or explicit dry mute.
- M3 Eight-String mode for `G#1 C2 E2 G#2 C3 E3 G#3 C4` and General Tonal
  mode.
- One through eight simultaneous MIDI notes.
- Raw MIDI 1.0 input passthrough and generated raw MIDI 1.0 output.
- Fixed or input-derived velocity.
- Versioned configuration state, Panic, bounded telemetry, and fail-closed
  detector behavior.
- Deterministic offline tests and guarded disposable-REAPER validation.

### Excluded

- MPE, per-string channels, bends, vibrato, slides, and exact string identity.
- Pitch correction, chord naming, tablature, score generation, or MIDI-file
  export.
- Full-mix or multi-instrument transcription.
- NeuralNote, Basic Pitch, a neural model, GPU inference, or model downloads.
- Windows or macOS packaging.
- A custom graphical interface in the first native revision.
- Persistent installation, live projects, live guitar/interface input, or an
  MCP bridge without separate approval.

## 5. External plug-in contract

### 5.1 Identity and ports

- Stable CLAP plug-in ID:
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`.
- Display name: `M3 Polyphonic Audio to MIDI`.
- One main two-channel audio input and one paired two-channel audio output.
- In-place and out-of-place processing are supported.
- Float32 audio is mandatory; float64 is accepted when the host supplies it.
- One note input port and one note output port support raw MIDI 1.0. Raw MIDI
  is the preferred dialect. CLAP note events and MPE are not emitted in this
  revision.
- Reported plug-in latency is always zero samples.

Unsupported audio layouts must be refused at activation when possible. If an
unexpected buffer layout reaches processing, the adapter preserves any safely
available dry channels, disables detection, schedules reachable note cleanup,
and latches an Unsupported Layout status.

For supported layouts, every finite dry sample is bit-identical in Pass
through mode. A non-finite input is the sole safety exception: it is replaced
with zero in both detector input and dry output so invalid data cannot reach the
downstream instrument or audio device.

### 5.2 Stable writable parameters

The first native revision preserves the existing fifteen controls, ranges,
meanings, and defaults. Parameter IDs are permanent once implementation begins.

| ID | Name | Range or values | Default |
| --- | --- | --- | --- |
| `0x4D330001` | Detector input | Left, Right, Downmix | Left |
| `0x4D330002` | Mode | M3 Eight-String, General Tonal | M3 Eight-String |
| `0x4D330003` | A4 reference | 400.0-480.0 Hz, 0.1-Hz steps | 440.0 Hz |
| `0x4D330004` | Input trim | -24.0 to +24.0 dB, 0.1-dB steps | 0.0 dB |
| `0x4D330005` | Sensitivity | 0-100 | 50 |
| `0x4D330006` | Response | Fast 0 through Stable 100 | 25 |
| `0x4D330007` | Lowest MIDI note | 24-108 | 32 |
| `0x4D330008` | Highest MIDI note | 24-108 | 84 |
| `0x4D330009` | Maximum polyphony | 1-8 | 8 |
| `0x4D33000A` | M3 maximum fret | 0-36 | 24 |
| `0x4D33000B` | Velocity mode | Fixed, Dynamic | Dynamic |
| `0x4D33000C` | Fixed velocity | 1-127 | 100 |
| `0x4D33000D` | MIDI channel | 1-16 | 1 |
| `0x4D33000E` | Panic | Ready, Panic | Ready |
| `0x4D33000F` | Dry audio | Muted, Pass through | Pass through |

M3 mode fixes the effective detection bounds at MIDI 32 through 84, matching
the JSFX behavior. General Tonal mode uses the ordered, clamped Lowest and
Highest values. Maximum polyphony remains capped at eight in both modes.

Discrete and integer controls are stepped. Panic is non-automatable and is not
saved as active state. A transition to Panic releases generated notes, blocks
new note-ons, and returns the parameter to Ready through the normal host
parameter protocol. Detection remains in Panic Hold until a complete processed
interval is below the existing `0.0001` peak threshold, preventing a ringing
input from immediately retriggering. The capability probe must verify that this
momentary behavior is usable in REAPER's generic interface.

The adapter also exposes one non-writable, non-persistent Status value using the
reserved ID `0x4D33FF01`. Its stepped values are `0` Ready, `1` Panic Hold,
`2` Reconfiguring, `3` MIDI Output Blocked, `4` Invalid Input or State, and `5`
Unsupported Layout. It is telemetry, not a sixteenth control. Its visibility
and refresh behavior are part of the minimal host probe.

No parameter is advertised as automatable in the first native revision. Host
UI edits still arrive through the normal parameter protocol, but they are
staged at process boundaries. Adding sample-accurate automation is outside this
amendment and must not complicate the first real-time path.

### 5.3 State

Saved state contains a schema version and the fourteen persistent parameter
values. Panic, Status, active notes, resonator history, noise estimates,
pending MIDI, and overload measurements are never restored.

Loaded values are validated and clamped before publication. Applying state or
a structural parameter change releases notes on the old MIDI channel before
the new prepared configuration becomes active.

## 6. Component architecture

```text
REAPER process call
  -> CLAP adapter
       -> parameter/event parser
       -> stereo dry path
       -> mono detector-input selector
       -> format-neutral M3 detector core
            -> conditioning and noise tracking
            -> multi-rate harmonic resonator bank
            -> salience and bounded voice selection
            -> M3 distinct-string feasibility filter
            -> per-note lifecycle state machines
       -> bounded generated-event queue
       -> ordered input/generated MIDI merger
       -> CLAP output events

REAPER main-thread callback
  -> structural configuration preparation
  -> generation-tagged lock-free publication

Audio-thread status snapshot
  -> atomic bounded telemetry
  -> generic read-only Status parameter
```

### 6.1 Format-neutral detector core

The detector core has no CLAP, REAPER, UI, file, logging, or routing calls. It
owns fixed-capacity state and presents four conceptual operations:

1. prepare immutable coefficients from sample rate and validated settings;
2. reset all transient detector and voice state;
3. consume one selected mono sample; and
4. at a decision tick, return a bounded ordered span of note transitions.

The core retains the existing JSFX boundaries: conditioning, resonator bank,
salience/selector, M3 profile, lifecycle, MIDI-neutral voice events, and
telemetry snapshot. Internal storage is structure-of-arrays where it materially
improves cache or vector access, but correctness is established first with a
scalar double-precision implementation.

An optional vectorized kernel may be introduced only after scalar parity and
only behind identical tests. Reduced numerical precision, hidden candidate
pruning, or a smaller pitch range is not an acceptable performance shortcut.

### 6.2 CLAP adapter

The adapter owns plug-in identity, ports, parameters, state, activation,
process-call segmentation, sample-offset conversion, MIDI passthrough and
merge, and host notifications. It translates CLAP events into configuration
changes and translates core voice transitions into raw MIDI messages.

The adapter never exposes CLAP types to the detector core. A later VST3
fallback therefore replaces only this adapter and its adapter tests.

### 6.3 Prepared configuration

Coefficient construction and structural validation are separated from active
detector state. The plug-in keeps a fixed set of preallocated,
generation-tagged prepared-configuration slots.

- Lightweight changes such as trim, sensitivity, response, velocity mode,
  fixed velocity, and dry mode are bounded and take effect at a safe process
  boundary.
- Structural changes such as detector input, mode, A4 reference, pitch bounds,
  polyphony, fret limit, or MIDI channel request preparation on the host main
  thread. Sample-rate changes occur only through host deactivation and a new
  activation, where the initial configuration is prepared synchronously.
- The latest structural request wins; redundant intermediate requests may be
  coalesced.
- The audio thread continues with the old valid configuration while a new one
  is prepared.
- At the start of a process call, the audio thread atomically adopts a complete
  generation, emits reachable note-offs under the old channel/configuration,
  resets transient detector state, and then resumes detection.

The plug-in creates no thread. It uses the host's main-thread callback for
preparation and bounded atomics for publication. The audio callback never
waits for preparation and never observes a partially built configuration.

## 7. Real-time processing and latency

### 7.1 Activation

Activation validates sample rate and maximum frame count, allocates or sizes
all fixed-capacity storage, prepares the initial coefficients, and clears
voice/event state. Work that can allocate or fail belongs here or on the main
thread, never in `process()`.

Deactivation and reset clear detector state and pending generated events. Any
cleanup MIDI that must reach a downstream instrument must be emitted while the
host is still calling `process()`; the plug-in cannot promise cleanup after an
abrupt callback stop.

### 7.2 Process call

For every host process call, the adapter:

1. validates the fixed port/buffer assumptions without allocating;
2. adopts any completely prepared configuration at the call boundary;
3. collects parameter edits into bounded latest-value staging and walks MIDI
   input events in timestamp order;
4. copies or mutes dry audio while selecting the detector's mono sample;
5. updates conditioning and resonators for every input sample;
6. runs salience, selection, M3 filtering, and lifecycle after every 64
   processed samples;
7. records generated transitions with the actual current sample offset; and
8. merges input MIDI and generated events into the host output queue.

The 64-sample phase continues across host calls. A block shorter than 64
samples does not force an early decision; a block longer than 64 may contain
multiple decisions. Reset begins a new phase. The production cadence is fixed
at 64 samples at every supported sample rate and is not a user parameter.

There is no lookahead, analysis worker, IPC, sleep, retry loop, or plug-in delay
compensation. All detector work remains on the host audio thread. The native
implementation must pass the existing CPU gate at this cadence. If it cannot,
work stops for another amendment rather than silently increasing the cadence
or adding buffering.

### 7.3 Audio-thread prohibitions

The active processing path performs no:

- heap allocation or deallocation;
- exceptions or RTTI-dependent control flow;
- mutex, condition variable, blocking atomic wait, or system call that may
  sleep;
- file, console, network, model, or device I/O;
- host UI or main-thread callback execution;
- unbounded loop, recursion, or collection growth; or
- wall-clock measurement in the normal performance build.

A benchmark build may take bounded monotonic-clock samples into preallocated
memory. It never prints or writes files from the audio thread; results are
drained only after processing stops.

## 8. MIDI ordering and lifecycle

The core emits MIDI-neutral note-on and note-off transitions. The adapter
encodes them as raw MIDI 1.0 on the selected channel.

- One active flag per MIDI pitch prevents duplicate generated note-ons.
- Maximum generated active notes is eight.
- Generated event storage is allocated during activation from the host's
  maximum frame count: at most sixteen transitions per 64-sample tick, plus
  one boundary cleanup and Panic reserve. An excessive or arithmetically unsafe
  maximum frame count is rejected before processing begins.
- Events are ordered first by sample offset. At the same offset, generated
  note-offs come first, incoming events retain their original order, and
  generated note-ons come last.
- Incoming MIDI is not interpreted or rewritten. The generated channel should
  be kept distinct if upstream MIDI notes could conflict with detector notes.
- Pitch replacement always ends the old generated note before beginning the
  new one.
- Sample-rate/configuration adoption, observable transport stop, reset,
  explicit Panic, invalid detector state, or reachable fault schedules every
  active generated note-off.

If the host output queue rejects an event, the adapter cannot undo events
already delivered. It therefore:

1. latches MIDI Output Blocked;
2. suppresses all new generated note-ons;
3. retains a fixed pending-release bitset for every active generated pitch;
4. retries those note-offs at offset zero on the next process call; and
5. appends channel All Notes Off/All Sound Off when capacity permits.

Dry audio and incoming MIDI continue when safely possible. Detection remains
inhibited until one complete process call accepts all pending individual
releases and both channel panic messages. A subsequent explicit Panic or host
reset reinitializes the detector, which then remains in Panic Hold until the
input is quiet. No claim is made that the plug-in can clean up after REAPER
stops invoking it, crashes, or destroys the downstream VSTi. The verified Safe
Bypass workflow remains the deliberate host-side cleanup path until a native
integration test proves an equivalent.

## 9. Fault behavior

| Condition | Audio | Generated MIDI | Recovery |
| --- | --- | --- | --- |
| Silence or low confidence | Preserve selected dry mode | Release by normal dropout policy; no new notes | Automatic when evidence returns |
| Non-finite input sample | Replace invalid detector and dry values with zero | Fail closed and schedule releases | Explicit reset/Panic after valid input |
| Unsupported layout | Preserve safely addressable dry channels | Disabled; schedule reachable releases | Correct layout and reactivate |
| Corrupt configuration/state | Preserve dry path | Disabled; schedule releases | Validated state load or reset |
| Output event rejection | Preserve dry path | Block note-ons; retry releases and panic messages | Clear only after accepted cleanup and explicit recovery |
| Reconfiguration pending | Preserve dry path | Existing valid detector continues | Atomic adoption when preparation completes |
| Measured CPU overrun | No adaptive audio degradation | No silent algorithm simplification | Fail validation; stop and amend |

All array indices, MIDI values, candidate ranges, port counts, frame counts, and
event offsets are checked or structurally bounded. An internal invariant
failure latches rather than continuing with uncertain detector state.

## 10. Interface strategy

The first native gate deliberately uses REAPER's generic CLAP parameter view.
This removes graphics, font, windowing, and GPU work from the initial plug-in
and keeps UI activity off the detector path. The fifteen controls remain fully
available, and the read-only Status value exposes the bounded fault state.

A custom compact note/confidence display is a later optional amendment. It may
begin only after native accuracy, latency, deadline, MIDI-lifecycle, and host
stability gates pass. If later authorized, it must run on the main thread and
read a generation-checked telemetry snapshot without blocking the audio
thread.

## 11. Build, dependency, and licensing boundary

- Use C++17 and the already available GNU C++ compiler.
- Use a small explicit Makefile; CMake, Ninja, JUCE, iPlug2, and DSP libraries
  are not required for the first port.
- Build one local `.clap` artifact and separate offline test executables.
- Compile the real-time core without exceptions and RTTI. Enable strict
  warnings, stack protection, and release optimization without
  machine-specific behavior that invalidates reproducibility.
- Pin one exact released revision of the official CLAP headers and preserve its
  MIT notice. Retrieving or vendoring those headers requires separate user
  approval.
- Continue releasing original project source under Apache-2.0. Do not copy
  ReaTune, NeuralNote, Basic Pitch, or other reference source without a new
  provenance and licensing review.
- Do not copy the artifact into a persistent REAPER plug-in directory during
  implementation or validation. Use only a build-local path exposed to the
  disposable profile after that action is separately authorized.

## 12. Verification gates

### 12.1 Source and offline core gate

- Unit-test configuration validation, pitch math, input conditioning,
  resonator updates, selector bounds, M3 feasibility, lifecycle, event ordering,
  state validation, and every fault transition without REAPER.
- Run sanitizers and adversarial/fuzzed parameter, state, buffer, and event
  sequences in bounded offline processes.
- Establish module-level numeric tolerances against frozen JSFX fixtures.
- Provide a test-only legacy decision schedule matching the JSFX 128-sample
  evidence capture so porting errors can be separated from the approved
  production change to 64 samples. The production binary exposes no cadence
  control.
- Under the production 64-sample schedule, require the expected note sets and
  lifecycle invariants; timestamp identity with the 128-sample JSFX oracle is
  not required.

### 12.2 Minimal CLAP capability probe

Before porting the detector, a disposable minimal plug-in must prove in guarded
REAPER:

- discovery, instantiation, activation, reset, deactivation, and clean unload;
- float32 stereo in-place and out-of-place dry identity;
- declared zero latency;
- one raw-MIDI input and output port;
- raw MIDI passthrough and exact generated note-on/note-off delivery to MIDI
  capture and a downstream test VSTi;
- chronological sample offsets at block sizes 32, 64, 128, and 256;
- all fifteen writable parameters, momentary Panic, read-only Status, and
  versioned state round-trip; and
- no persistent REAPER profile or project mutation.

Failure stops the CLAP path before detector code is ported. The next action is
a separately approved short VST3-adapter design correction, not an automatic
SDK download or parallel implementation.

### 12.3 Native detector correctness

- The final 45-case M3 slice must retain all 124 expected notes with precision,
  recall, and F1 `1.0`, no duplicate notes, and no hanging notes.
- The broader synthetic clean-note corpus must retain at least 98% precision
  and recall.
- Every existing module and lifecycle regression must pass at 44.1, 48, and
  96 kHz where applicable.
- The 96 kHz 32+56 regression must no longer emit false MIDI 44.
- Digital silence must emit no note event.

Synthetic success remains insufficient for a musical-readiness claim. Clean-DI
targets remain at least 90% note F1 for single notes and 85% for dyads through
four-note chords, but recording or using clean DI requires separate approval.

### 12.4 Latency and deadline gates

At 48 kHz:

- single M3 open strings: median no more than 25 ms and P95 no more than 45 ms;
- three/four-note chord completion: median no more than 40 ms and P95 no more
  than 65 ms; and
- no deliberate latency beyond causal evidence and the fixed 64-sample
  decision schedule.

At 44.1, 48, and 96 kHz with host blocks of 32, 64, 128, and 256:

- audio-thread P99 must remain below 25% of the block deadline;
- any block at or above 50% is a hard failure;
- dry audio must have no added delay, discontinuity, or channel corruption;
  and
- output event timestamps must remain ordered and inside their host block.

Measure both closed and open generic parameter views. Run at least two
independent long deadline captures for the final 48 kHz/128 row. Do not proceed
to live input or installation after any hard failure.

### 12.5 Host and system-stability gate

Any future REAPER process remains serial, disposable, nonactivating, and hidden
on workspace 5. It must use only `build/reaper-test/reaper.ini` and the existing
guarded launcher, which enforces:

- 50% of one logical CPU;
- `MemoryHigh=384 MiB` and `MemoryMax=512 MiB`;
- no more than 64 MiB swap;
- no more than 64 tasks;
- `nice 10`, idle I/O priority, and one-core affinity;
- a hard timeout and clean interrupt handling;
- refusal below 4 GiB available memory, above one-minute load 12, or at a
  readable temperature of 90 C or higher;
- exclusion of pre-existing REAPER windows; and
- restoration of the user's workspace if a test launch steals focus.

No test may attach the native artifact to the user's existing REAPER process.
No daemon or persistent helper is introduced. Pressure, a guard refusal, a
crash, or an unexplained spike ends the current run; it does not trigger an
automatic heavy retry.

## 13. Rollback and stop rules

- The frozen JSFX source and evidence are never overwritten by the native port.
- A failed CLAP capability probe stops before detector implementation and
  returns to adapter design.
- A native correctness regression returns to the smallest responsible core
  component.
- A native latency or CPU hard failure stops the native experiment. It does not
  authorize a larger block, hidden buffering, a worker thread, GPU inference,
  a reduced pitch range, or relaxed thresholds.
- A plug-in or host crash preserves all available logs and the disposable test
  profile, verifies that no REAPER process remains, and requires recovery
  review before another launch.
- Passing synthetic and disposable-host gates does not authorize installation,
  live guitar/interface input, or live-project use.

## 14. Completion definition

This design amendment is complete when it is written, self-reviewed, committed,
indexed in the ResearchOS vault, and accepted by the user as the written
specification. That is not native-tool completion.

A future native implementation may be called performance-ready only after the
capability, offline, correctness, latency, deadline, lifecycle, and guarded-host
gates above pass, followed by the separately authorized clean-DI gate. A
persistent installation remains a final explicit decision.

## 15. Primary references

- REAPER supported plug-in formats: <https://www.reaper.fm/about.php>
- REAPER extension plug-in boundary: <https://www.reaper.fm/sdk/plugin/plugin.php>
- Official CLAP repository and ABI headers: <https://github.com/free-audio/clap>
- CLAP process contract: <https://github.com/free-audio/clap/blob/main/include/clap/process.h>
- CLAP event contract: <https://github.com/free-audio/clap/blob/main/include/clap/events.h>
- CLAP note-port contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/note-ports.h>
- CLAP audio-port contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/audio-ports.h>
- CLAP parameter contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/params.h>
- CLAP state contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/state.h>
- CLAP latency contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/latency.h>
- CLAP thread-check contract: <https://github.com/free-audio/clap/blob/main/include/clap/ext/thread-check.h>
- VST3 ProcessData event boundary: <https://steinbergmedia.github.io/vst3_doc/vstinterfaces/structSteinberg_1_1Vst_1_1ProcessData.html>
- VST3 SDK licensing: <https://steinbergmedia.github.io/vst3_dev_portal/pages/VST%2B3%2BLicensing/VST3%2BLicense.html>
