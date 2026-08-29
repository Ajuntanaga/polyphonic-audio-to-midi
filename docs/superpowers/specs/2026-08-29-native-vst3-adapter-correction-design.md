# Native VST3 Adapter Correction: Real-Time Polyphonic Audio-to-MIDI for REAPER

Date: 2026-08-29
Architecture approved in chat: 2026-08-29
Written specification review: pending user review
Document status: design-only amendment; implementation remains separately gated

## 1. Authority and amendment boundary

This document is the approved design correction required by the failed CLAP
capability gate. It amends only the plug-in format, external event contract,
adapter architecture, dependency/build boundary, and capability-host gate in
`2026-08-28-native-clap-polyphonic-audio-to-midi-design.md`.

The following approved product contracts remain unchanged:

- a source-editable Linux x86-64 track effect before a downstream VSTi;
- a format-neutral C++17 detector core;
- one through eight simultaneous discrete notes;
- M3 Eight-String tuning `G#1 C2 E2 G#2 C3 E3 G#3 C4` plus General Tonal mode;
- a fixed 64-sample decision cadence independent of host block size;
- zero lookahead and zero declared latency;
- the existing fifteen writable controls plus read-only Status;
- versioned fourteen-value persistent state;
- no custom GUI, model runtime, helper process, or plug-in-owned thread;
- no allocation, locking, file I/O, logging, sleeping, or unbounded work in
  the audio callback; and
- the existing accuracy, latency, deadline, stability, clean-DI, installation,
  and live-project gates.

This design selects one VST3 production path. It does not authorize SDK
retrieval, CMake or package installation, source implementation, a REAPER
launch, detector porting, hardware input, a persistent plug-in installation,
or changes to a live project. The prior CLAP adapter and its failed evidence
remain preserved; they are not retried or developed in parallel.

## 2. Trigger evidence and correction scope

The first guarded CLAP capability row at 48 kHz/block 32 failed and was sealed
at commit `6a74b9f`. The immutable evidence directory is
`build/test-results/native-clap-probe/batches/32.invalid-20260829T074326Z`,
and its seven-file manifest digest is
`12abeeb42c9cf3bf9293540ed952951bfcbeeeaf1e22139af380ac527c837d51`.

That row proved bounded discovery, lifecycle entry/exit, float32 processing,
separate buffers, and dry-path self-tests. It did not prove the required
parameter writes, state/Status behavior, complete scripted event phase, or
reset behavior. The evidence does not distinguish a CLAP adapter defect from
a REAPER/ReaScript exposure mismatch. This correction therefore makes no
claim about the general quality of CLAP; it follows the already approved
format-fallback rule and redesigns the host contract around VST3 semantics.

## 3. Adapter alternatives and selected form

### 3.1 Selected: official C++ SDK `SingleComponentEffect`

Use Steinberg's supported non-distributable `SingleComponentEffect` helper so
one host object owns audio processing, generic parameters, component state,
and prepared-configuration publication. The plug-in does not advertise
`kDistributable` and does not create a custom editor view.

This choice is specific to the first REAPER/Linux revision. It removes a
processor/controller message channel, permits structural settings received on
the UI thread to be prepared outside `process()`, and keeps one bounded state
owner. The capability gate must still prove that current REAPER accepts this
official combined form before any detector code is ported.

### 3.2 Rejected for this revision: separate processor and controller

Separate `IComponent`/`IAudioProcessor` and `IEditController` classes are the
general VST3 architecture, but they require host-mediated state and private
configuration synchronization. That extra channel is not useful for a local,
generic-UI, non-distributable REAPER effect and creates more states to prove.
It may be reconsidered only if the minimal capability probe rejects the
combined component.

### 3.3 Rejected for this revision: VST3 C API or hand-written ABI shim

The official generated C API has a small header surface but supplies fewer
helper implementations. Recreating the factory, reference counting, busses,
parameters, streams, and lifecycle manually would increase first-adapter code
and validation risk. A private ABI copy is also excluded because it would
create a maintenance and provenance burden without improving runtime latency.

### 3.4 Rejected: parallel CLAP repair

The CLAP adapter stays buildable as historical/offline evidence only until a
later cleanup decision. No release build includes both formats, and the failed
CLAP row is not retried under the VST3 design.

## 4. External VST3 contract

### 4.1 Identity and category

- Product name: `M3 Polyphonic Audio to MIDI`.
- Vendor namespace: `ajuntanaga`.
- Descriptive stable identity:
  `com.ajuntanaga.m3-polyphonic-audio-to-midi`.
- VST3 category: audio effect, `Fx|Tools`; never instrument or synthesizer.
- Exactly one nonzero 128-bit component class ID is generated once, recorded
  in the implementation plan, and locked by a source test before the first
  artifact is built. Changing it afterward is a breaking identity change.
- The product name does not include Steinberg's VST trademark or logo.

### 4.2 Audio and event busses

- One main stereo audio input, active by default.
- One main stereo audio output, active by default.
- Zero event input busses.
- One main event output bus with sixteen channels, active by default.
- The adapter accepts only paired stereo input/output arrangements.
- Float32 processing is mandatory; float64 is supported when supplied.
- In-place and out-of-place audio buffers are supported.
- Reported latency is zero samples and reported tail is zero.

There is intentionally no incoming MIDI or VST3 event path. The product is
guitar-audio to generated notes to a downstream VSTi. Keyboards, pedals, CC,
SysEx, raw MIDI passthrough, and event merging are outside this plug-in.

### 4.3 Generated note output

- Emit only VST3 `NoteOnEvent` and `NoteOffEvent` records.
- Emit on event bus zero and the configured channel, converting the external
  one-based channel `1..16` to VST3's zero-based `0..15`.
- Preserve the core transition's block-relative sample offset.
- Convert MIDI velocity `1..127` to `velocity / 127.0f`; note-off velocity is
  zero in this revision.
- Set tuning to zero cents and note length to zero/unknown.
- Because the detector permits at most one active voice per MIDI pitch, use
  deterministic plug-in-owned note ID `-1000 - pitch` for both the note-on and
  matching note-off. These values remain inside VST3's reserved plug-in note-ID
  range for pitches `0..127`.
- At an equal sample offset, generated note-offs precede generated note-ons.
- No MPE, note expression, pitch-bend event, legacy CC output, or DataEvent is
  emitted.

## 5. Component architecture

```text
REAPER process call
  -> VST3 SingleComponentEffect adapter
       -> parameter-queue validation and boundary coalescing
       -> stereo dry path
       -> mono detector-input selector
       -> format-neutral M3 detector core
            -> conditioning and noise tracking
            -> multi-rate harmonic resonator bank
            -> salience and bounded voice selection
            -> M3 distinct-string feasibility filter
            -> per-note lifecycle state machines
       -> bounded generated-note delivery ledger
       -> VST3 output event list

REAPER UI/main-thread calls
  -> generic VST3 parameters and state
  -> structural configuration preparation
  -> generation-tagged bounded publication

Audio-thread status
  -> bounded atomic snapshot
  -> VST3 read-only Status output parameter
```

### 5.1 Format-neutral extraction

Before a VST3 adapter is written, reusable modules must stop exposing CLAP
types:

- parameter IDs become `std::uint32_t` in the neutral contract;
- byte-exact state image encoding/decoding is separated from CLAP/VST3 stream
  adapters;
- generated note transitions and the active/pending note ledger are neutral;
- raw-MIDI passthrough and CLAP event copying remain only in the frozen CLAP
  adapter; and
- dry-path and prepared-configuration code remain host-format independent.

The extraction must retain the existing unit-test behavior before any new
VST3 class is introduced. The production VST3 build never links the CLAP
entry point, probe processor, or raw-MIDI merger.

### 5.2 Single component and generic interface

The combined component derives from the official SDK helper, registers the
audio/event busses and sixteen parameters during initialization, and returns
no custom editor view. REAPER therefore supplies the visible generic controls.

`setParamNormalized()` and state loading run outside the audio callback. They
validate the complete requested configuration and prepare structural data into
the existing bounded exchange. `process()` still treats the host's
`inputParameterChanges` as authoritative for when a change becomes active.

If a structural value reaches `process()` without a matching prepared
generation, the adapter releases reachable active notes, latches
`Reconfiguring`, keeps dry audio available, and retains the prior detector
configuration. It never computes structural coefficients on the audio thread.
Because parameters are non-automatable in this revision, such a mismatch is a
host/contract fault rather than a supported automation path.

## 6. VST3 lifecycle and processing contract

### 6.1 Setup and activation

- `initialize()` registers busses and parameter metadata only.
- `setupProcessing()` accepts 44.1, 48, and 96 kHz as release-qualified rates,
  validates a finite positive rate, and rejects a zero or greater-than-16384
  maximum block size.
- Realtime, prefetch, and offline modes use the same bounded algorithm; offline
  mode does not enable a slower or higher-quality path.
- `setActive(true)` allocates all detector, transition, and configuration
  storage needed up to the declared maximum block size.
- `setProcessing(false)` moves every possibly active pitch into the fixed
  pending-release set, resets detector transients, blocks new note-ons, and
  performs no host-event emission.
- `setProcessing(true)` resets decision cadence into Panic Hold but does not
  discard pending releases. The first subsequent process call retries their
  note-offs at offset zero before any detector work can resume.
- `setActive(false)` performs no host-event emission and does not erase the
  fixed pending-release ledger. The host capability gate must prove downstream
  behavior at stop/restart, bypass, deactivation, and destruction boundaries.
- Deallocation occurs only while inactive.

### 6.2 Process call

For every call:

1. Validate mode, sample size, sample count, bus counts, channels, and buffer
   pointers before detection.
2. Accept a zero-sample/no-audio call as a parameter flush.
3. Coalesce the last valid value for each parameter queue at the block
   boundary. Sample-accurate parameter automation is not supported.
4. Release notes under the old channel before swapping any newly prepared
   structural configuration.
5. Copy or mute dry audio safely for float32 or float64, supporting aliases.
6. Replace every non-finite input sample with zero in both detector input and
   dry output and latch `Invalid Input or State`.
7. Feed the selected mono sample to the core and run decision work exactly
   every 64 processed samples, carrying cadence across host calls.
8. Validate every returned transition and add note events in deterministic
   offset/order sequence.
9. Publish Status through `outputParameterChanges` when available, retaining a
   dirty snapshot for a later call if the host does not accept it.

No call to `process()` or `setProcessing()` allocates, deallocates, locks,
waits, sleeps, performs file/console I/O, samples a clock in production, calls
an unsafe host interface, or executes unbounded retry work.

## 7. Parameter and state contract

VST3 `ParamID` values remain byte-for-byte equal to the approved 32-bit IDs.
The neutral contract owns plain-value ranges, validation, text conversion, and
plain/normalized conversion.

| ID | Name | Plain values/range; default | Class | Saved |
| --- | --- | --- | --- | --- |
| `0x4D330001` | Detector input | Left=0, Right=1, Downmix=2; 0 | Structural | Yes |
| `0x4D330002` | Mode | M3 Eight-String=0, General Tonal=1; 0 | Structural | Yes |
| `0x4D330003` | A4 reference | 400.0-480.0 by 0.1 Hz; 440.0 | Structural | Yes |
| `0x4D330004` | Input trim | -24.0 to +24.0 by 0.1 dB; 0.0 | Runtime | Yes |
| `0x4D330005` | Sensitivity | 0-100; 50 | Runtime | Yes |
| `0x4D330006` | Response | Fast 0 through Stable 100; 25 | Runtime | Yes |
| `0x4D330007` | Lowest MIDI note | 24-108; 32 | Structural | Yes |
| `0x4D330008` | Highest MIDI note | 24-108; 84 | Structural | Yes |
| `0x4D330009` | Maximum polyphony | 1-8; 8 | Structural | Yes |
| `0x4D33000A` | M3 maximum fret | 0-36; 24 | Structural | Yes |
| `0x4D33000B` | Velocity mode | Fixed=0, Dynamic=1; 1 | Runtime | Yes |
| `0x4D33000C` | Fixed velocity | 1-127; 100 | Runtime | Yes |
| `0x4D33000D` | MIDI channel | 1-16; 1 | Structural | Yes |
| `0x4D33000E` | Panic | Ready=0, Panic=1; 0 | Momentary | No |
| `0x4D33000F` | Dry audio | Muted=0, Pass through=1; 1 | Runtime | Yes |
| `0x4D33FF01` | Status | Ready=0 through Unsupported Layout=5; 0 | Read-only | No |

Discrete/list controls expose exact VST3 step counts. Status is flagged
read-only and not automatable. All other parameters are visible but do not set
`kCanAutomate` in this revision. Panic queues releases, immediately requests
its normalized value return to Ready through `outputParameterChanges`, and
holds detection until a later complete quiet call satisfies the existing
`0.0001` peak rule.

The existing 184-byte state image remains authoritative:

```text
16-byte header: magic, schema=1, field count=14, payload size, payload CRC-32
168-byte payload: 14 ordered records of uint32 ID + uint64 double bits
```

The neutral image codec is unchanged. A narrow `IBStream` adapter loops only
until the fixed image is complete and treats zero/negative progress as failure.
Loading validates the entire candidate before publication. Panic, Status,
active notes, pending releases, detector history, and telemetry are absent.

## 8. Generated-note failure and reset behavior

The VST3 adapter owns fixed active and pending-release bitsets indexed by MIDI
pitch. A note-on becomes active only after `IEventList::addEvent()` succeeds.
A rejected note-on never becomes active.

If any note event is rejected or `outputEvents` is unavailable when a generated
transition must be delivered:

- latch `MIDI Output Blocked`;
- block all later note-ons;
- retain every possibly active pitch in the pending-release set;
- retry individual note-offs at sample offset zero on later calls;
- perform at most one bounded pass over the 128-pitch set per call;
- keep dry audio available; and
- remain inhibited after cleanup until explicit Panic or a processing reset
  enters and then clears Panic Hold.

No CC120/CC123 fallback is emitted because the approved VST3 contract is
generated notes only. The capability and fault-injection tests must therefore
prove individual note-off retry exhaustively.

Unexpected layouts or invalid parameter/state data follow the same cleanup
path and latch their specific Status value. No fault silently reduces pitch
range, polyphony, harmonic work, sample rate, decision frequency, or validation
thresholds.

## 9. 96 kHz and block-size contract

96 kHz is a mandatory operating and release gate, not a best-effort mode.

- Audio and detector input remain at the host's native rate; there is no hidden
  downsampling, resampling, lookahead, or additional buffering.
- Decision cadence remains 64 samples at 44.1, 48, and 96 kHz.
- Adapter unit/fake-host coverage includes 44.1, 48, and 96 kHz.
- The guarded minimal REAPER capability matrix is exactly ten serial rows:
  sample rates `48000` and `96000`, each at block sizes
  `32, 64, 128, 256, 512`.
- Rows run in lexical plan order beginning at 48 kHz/block 32 and stop after
  the first invalid, timed-out, pressure-aborted, or failed row. No automatic
  retry is allowed.
- Block size 512 is a host-test row. Separately, every REAPER child remains
  capped at 512 MiB of memory by the existing stability guard.
- The known 96 kHz `32+56` false MIDI-44 regression is an independent hard
  detector-release blocker. A green adapter capability probe cannot waive it.

The native detector gate must later pass the complete frozen correctness
matrix at 44.1, 48, and 96 kHz. The performance gate must include the strictest
96 kHz/block-32 callback deadline. Any callback at or above 50% of its deadline
stops the experiment and requires another design amendment; no buffering or
quality reduction may conceal the failure.

## 10. Dependency, build, packaging, and licensing

After a separately authorized dependency gate:

- retrieve one exact official `steinbergmedia/vst3sdk` 3.8.x commit and its
  required submodule commits from the official repositories;
- record UTC retrieval time, repository URLs, every commit, licenses, and a
  lexically ordered SHA-256 manifest;
- retain only the official base, pluginterfaces, public SDK, and CMake material
  required to build the effect and offline validator; VSTGUI, wrappers,
  examples, hosts, and unrelated platform material are excluded where the
  supported build permits;
- never download dependencies during configure, build, test, or REAPER launch;
- use the official C++ SDK and CMake integration without VSTGUI;
- make CMake authoritative for native source lists and bundle generation;
- retain `native/Makefile` only as a thin, non-networking convenience wrapper;
  and
- stop for authorization rather than installing a missing compiler, CMake,
  system package, or SDK dependency.

The build-local output is a Linux bundle shaped as:

```text
M3_Polyphonic_Audio_to_MIDI.vst3/
  Contents/
    x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so
    Resources/moduleinfo.json
```

Generated bundles, validators, test hosts, profiles, and results remain under
ignored `build/` paths. Nothing is copied to a user or system VST3 directory
until a separate persistent-installation gate. The official SDK's MIT notice
is preserved. No VST logo or trademark is placed in the product name.

## 11. Corrected capability gate

The detector core remains unported until all earlier rows in this section pass.

### 11.1 Offline adapter proof

A fixed-capacity fake VST3 host must exhaustively prove:

- factory, reference-count, initialization, setup, active, processing,
  stop/deactivate, terminate, and destruction order;
- stereo bus enumeration/activation, zero event inputs, and one event output;
- exact internal count of sixteen plug-in parameters and all IDs/metadata;
- plain/normalized conversions and all fourteen persistent values;
- read-only Status and momentary Panic output-parameter behavior;
- byte-exact state save/load plus malformed/short/zero-progress streams;
- float32/float64, alias/separate, pass/mute, finite/non-finite, zero-sample,
  and variable block processing;
- note-on/off offsets, channels, velocities, deterministic note IDs, equal-time
  ordering, and every output rejection position;
- a held note across `setProcessing(false)`/`true`, with its note-off retried
  before any new note-on after restart;
- no input event bus and no input-event reads;
- no allocation/deallocation in armed `process()` or `setProcessing()` calls;
  and
- sanitizer-clean teardown.

The exact production bundle must then pass Steinberg's offline validator. A
validator crash or environment failure is infrastructure-invalid evidence, not
a plug-in pass or fail.

### 11.2 Disposable REAPER probe

Build a separate probe-only VST3 bundle that uses the production lifecycle,
parameter, state, audio, and note-delivery adapter with a deterministic
audio-triggered test processor. The probe has no event input and does not use
MIDI/CC as a trigger. Its marker and class ID are absent from the production
bundle.

The disposable REAPER chain is:

```text
deterministic audio source
  -> VST3 capability probe
  -> MIDI/event capture
  -> disposable synth/output probe
```

The script verifies discovery, busses, supported sample sizes, dry audio,
two complete audio-triggered note phases, stop/restart with a deliberately held
note, bypass/deactivation cleanup, parameters, fourteen-value state, Panic,
and Status. Internally the plug-in must expose exactly sixteen parameters, but
the REAPER probe identifies those parameters by stable ID/name and does not
require REAPER's total host-facing parameter count to equal sixteen because
the host may add its own controls.

The ten-row 48/96 kHz by 32/64/128/256/512 matrix requires one fresh disposable
profile and one fresh REAPER process per row. Every launch is serial,
backgrounded, non-activating, placed on workspace 5, forbidden from attaching
to an existing REAPER process, and run under the existing low-priority guard:

- 50% of one logical CPU;
- 384 MiB memory-high and 512 MiB memory maximum;
- 64 MiB swap maximum;
- 64 tasks;
- bounded CPU and wall time;
- pre/post memory, load, pressure, temperature, workspace, and lingering-process
  checks; and
- atomic evidence preservation before any subsequent row.

Any failed or invalid row stops the matrix immediately. No remaining row,
retry, adapter modification, or detector port follows without an approved
correction.

## 12. Implementation and validation gates

The old CLAP implementation plan stops at failed Task 10. Its Tasks 11-24 do
not automatically become VST3 work. After this written specification is
approved, the next authorized artifact is a new TDD implementation plan that
maps the preserved core contracts onto the VST3 correction.

That future plan must preserve these gates in order:

1. **Design/specification approval** — this document accepted and sealed.
2. **Implementation-plan approval** — exact TDD files, tests, commits, and stop
   points written before source work.
3. **Dependency gate** — explicit approval before official SDK retrieval; no
   installs.
4. **Neutral-extraction gate** — existing tests green before VST3 classes.
5. **Offline VST3 gate** — fake host, sanitizers, source checks, and Steinberg
   validator green.
6. **Capability-host gate** — explicit approval for the ten guarded disposable
   REAPER rows; stop on first failure.
7. **Detector-port gate** — port modules one at a time only after capability is
   green.
8. **Correctness gate** — frozen oracle plus 44.1/48/96 kHz regression matrix,
   including the known 96 kHz false-note case.
9. **Latency/deadline gate** — existing thresholds unchanged; 96 kHz/block 32
   included and the 50% callback ceiling enforced.
10. **Production-host gate** — guarded disposable REAPER only.
11. **Clean-DI/live-input gate** — separately authorized hardware recording
    and input after every synthetic/host gate is green.
12. **Installation/use gate** — separate approval before persistent copying or
    live-project use.

## 13. Completion definition

This VST3 design correction is complete when:

- its written specification is approved and committed;
- the task-local `RESUME.md` and ResearchOS dashboard point to it;
- no SDK, VST3 source, build artifact, REAPER launch, or installation was
  created under design-only authorization; and
- the exact next action is the separately reviewed TDD implementation plan.

The eventual product is complete only when all future gates pass at 44.1, 48,
and 96 kHz, including block 512 host coverage, 96 kHz/block 32 performance,
clean-DI evidence, and fail-closed lifecycle cleanup. A discoverable or locally
green VST3 bundle alone is not completion.

## 14. Primary references

- Steinberg VST3 API architecture and threading:
  <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/API%2BDocumentation/Index.html>
- Steinberg `SingleComponentEffect` reference:
  <https://steinbergmedia.github.io/vst3_doc/vstsdk/classSteinberg_1_1Vst_1_1SingleComponentEffect.html>
- Steinberg VST3 MIDI/event mapping:
  <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/About%2BMIDI/Index.html>
- Steinberg `ProcessData` reference:
  <https://steinbergmedia.github.io/vst3_doc/vstinterfaces/structSteinberg_1_1Vst_1_1ProcessData.html>
- Steinberg parameter/automation reference:
  <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Parameters%2BAutomation/Index.html>
- Steinberg Linux bundle format:
  <https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Locations%2BFormat/Plugin%2BFormat.html>
- Official VST3 SDK repository and license/build guidance:
  <https://github.com/steinbergmedia/vst3sdk>
