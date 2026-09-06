# M3 VST3 Live Editor Design

Date: 2026-09-05  
Architecture approved in chat: 2026-09-05  
Document status: approved design; implementation plan and source work follow
only after this document is reviewed

## 1. Outcome

Replace REAPER's generic VST3 parameter page with a premium, musician-facing
editor for **M3 Polyphonic Audio to MIDI**. The quality bar is a modern,
well-made channel-strip plug-in: strong hierarchy, tactile controls, immediate
readability, and no duplicated wall of sliders. It takes inspiration from the
clarity and modular organization of professional rack plug-ins, without using
another product's branding, artwork, assets, or trade dress.

The editor is for the practical live path: a Revelator at 96 kHz, a low-register
eight-string guitar, and a downstream VSTi. It must make the important controls
fast to find while preserving every existing VST3 parameter and host automation
contract.

## 2. Current state and scope

`M3Component::createView()` currently returns `nullptr`, so REAPER supplies a
generic parameter interface. The audio processor is a VST3
`SingleComponentEffect`; it remains the single owner of the audio and parameter
contract.

This change adds an editor only. It does not change:

- detector DSP, note selection, MIDI event generation, or the audio thread;
- host sample-rate ownership, including the staged 96 kHz profile;
- parameter IDs, ranges, defaults, persistence, normalized/plain conversion,
  or host automation behavior;
- the one-to-eight note capability claim or the current eight-open-string live
  setup; or
- the generic parameter surface available to hosts that do not open an editor.

It also does not fake unavailable telemetry. The editor may show the existing
`Status` parameter, but it does not draw an input meter, current-note display,
or tracking certainty until the processor exposes truthful, bounded telemetry
for it.

## 3. Alternatives considered

### Selected: bespoke VSTGUI editor

Add the exact VSTGUI revision paired with the retained VST3 SDK as a pinned,
reviewed third-party source and enable the SDK's VSTGUI support target. Build a
small code-drawn editor rather than a bitmap skin. A VSTGUI editor gives REAPER
a normal VST3 `IPlugView`, host-managed edit gestures, Linux/X11 support, and
HiDPI-aware drawing without adding an audio-path dependency.

This is the selected route because it can look finished and remain maintainable:
the surface is vector-drawn, text-led, scalable, and deliberately smaller than
a separate desktop application.

### Rejected: retain or restyle REAPER's generic parameter page

It cannot change the hierarchy, grouping, conditional controls, or visual
identity of the actual plug-in. It would leave the user with the same wall of
controls that motivated this work.

### Rejected: a hand-written X11 editor

The current build does not carry the X11 development surface, and a custom
embedding/event/rendering implementation would create more platform lifecycle
code than the editor itself. It is a poor trade for the Linux VST3 product.

### Rejected: browser, ReaScript, or external-control application

Those approaches introduce a second UI/process/control channel, do not create
a normal VST3 editor, and work against the low-latency live workflow.

## 4. Visual and interaction direction

The editor is a dark graphite performance deck, not a literal guitar amp or a
copy of an analog rack. Accent colors are restrained: electric cyan denotes
active state and MIDI flow, warm amber marks configuration requiring attention,
and red is reserved for Panic or failure. High-contrast typography and generous
spacing make it readable at a glance in a dark DAW.

The initial logical canvas is `1024 x 620`, with VSTGUI content scaling and a
constrained resizable layout. It has four areas:

1. **Header / live state** — product identity, a concise causal-live label,
   a read-only status chip, and a clearly separated Panic button.
2. **Tracking** — the three routinely adjusted detector controls: Input Trim,
   Sensitivity, and Response. They use large rotary controls with direct numeric
   readouts and reset-to-default behavior.
3. **Performance range** — an immediately legible low/high MIDI-note pair,
   M3 Eight-String versus General Tonal selector, channel, and the core live
   configuration. The note range is rendered as one band/range visual but is
   still backed by the existing two exact host parameters.
4. **Routing and advanced settings** — detector input, Dry Audio, velocity
   mode, fixed velocity when applicable, A4 reference, maximum polyphony, and
   maximum fret. This area is compact and uses a disclosure panel rather than
   permanently competing with performance controls.

### 4.1 No redundant slider rule

The editor does not use a slider simply because a value is automatable.

| Parameter type | UI treatment |
| --- | --- |
| Continuous musical values | One rotary control plus a precise value readout |
| Bounded note range | One linked range visual backed by Low and High controls |
| Lists / binary modes | Segmented choices or a toggle, never a slider |
| Momentary action | One guarded, immediately visible Panic button |
| Read-only telemetry | Status chip / text only |
| Dependent parameter | Hidden or recessed until its controlling mode makes it relevant |

For example, Fixed Velocity is shown only in Fixed mode; in Dynamic mode it is
not an active redundant control. Detector Input, Mode, Velocity Mode, and Dry
Audio become readable choices/toggles. Every treatment drives the same original
parameter ID, normalised value, begin-edit, perform-edit, and end-edit sequence
that a host automation lane uses.

## 5. Technical architecture

### 5.1 Build and dependency boundary

- Add the exact VSTGUI source paired with VST3 SDK `v3.8.1_build_84` at its
  recorded Git link `5db272256172557818b6158cf0bb2c4410bddb25`.
- Store the reviewed source at the SDK's native path
  `third_party/vst3sdk/vstgui4` and record its exact Git link in the retained
  SDK provenance; do not rely on the ignored, partial `build/vendor` checkout.
- Enable `SMTG_ENABLE_VSTGUI_SUPPORT` only after its source path is explicit.
  Link `vstgui_support` only to the native test and production VST3 targets
  that compile the editor.
- Use vector drawing and bundled fonts available through VSTGUI; do not add
  network-loaded assets, runtime file I/O, third-party telemetry, or a browser
  runtime.

### 5.2 Editor objects

Add a narrow editor layer beneath `native/vst3/`:

- `m3_editor.hpp/.cpp` creates the VST3 editor view and owns its UI lifetime.
- `m3_editor_layout.hpp/.cpp` owns pure layout, control grouping, state-to-label
  mapping, and adaptive visibility rules. It is independent of X11 and can be
  tested without an attached host window.
- `m3_editor_surface.hpp/.cpp` owns vector rendering and pointer/keyboard
  interaction. It has no detector or audio-thread access.

`M3Component::createView(ViewType::kEditor)` returns exactly this editor; any
other name remains unsupported. The existing `SingleComponentEffect` handles
the editor's host edit gesture calls (`beginEdit`, `performEdit`, and
`endEdit`). No second controller, worker thread, message channel, or private
audio-to-UI path is introduced.

### 5.3 Parameter synchronization

- A control derives its displayed value from the existing parameter container,
  never from a duplicate UI configuration.
- Pointer gestures issue an ordinary VST3 begin/perform/end edit sequence;
  keyboard and reset interactions use the same route.
- Host automation and state restore propagate back to the editor through the
  VSTGUI parameter mechanism; display values are canonicalized with the
  existing parameter contract.
- The status chip uses only the existing read-only Status parameter and maps
  the six declared statuses to text/colors. It never invents a healthy state.
- UI construction and destruction occur on the host's UI lifecycle. The audio
  callback neither reads editor objects nor waits on them.

## 6. Reliability and accessibility

- Minimum text contrast is designed for dark REAPER themes; color is never the
  only source of state.
- All actionable controls expose text labels, current values, and tooltips.
- Focus and keyboard stepping follow VST3-host forwarding rules.
- The editor is safe to open/close repeatedly, decline unsupported platforms,
  and survive state restoration without modifying audio operation.
- If a host cannot attach the custom editor, the VST3 remains usable through
  its unchanged generic controls.

## 7. Verification plan

The implementation is test-first and proceeds in slices:

1. A source/build contract first proves the pinned VSTGUI dependency, editor
   sources, editor resource boundary, and lack of audio-thread UI edges.
2. Pure layout tests prove control grouping, visibility rules, status mapping,
   range layout, and every no-redundant-slider rule.
3. Fake-host lifecycle tests prove `createView(kEditor)` returns a view,
   unsupported names do not, and attach/resize/remove safely preserve the
   fixed host contract.
4. Gesture tests prove each on-screen control maps to the original parameter
   ID and emits exactly one begin/perform/end gesture; Panic remains momentary
   and Status remains read-only.
5. Existing parameter/state/audio/realtime tests remain green. The production
   bundle then builds and the official VST3 validator runs before REAPER is
   asked to reload it.
6. Only after those gates is the new bundle copied into the disposable 96 kHz
   profile and visually checked in REAPER. That check validates the editor
   presentation and host attachment; it is not a claim about guitar tracking
   accuracy.

## 8. Acceptance criteria

- Opening M3 in REAPER shows a polished custom editor rather than the generic
  parameter list.
- The main screen makes the live tracking controls, MIDI range, mode, channel,
  status, and Panic action visible without scrolling.
- Lists, booleans, action, telemetry, and dependent values are not presented as
  redundant sliders.
- Every existing VST3 parameter keeps its ID, range, default, state behavior,
  normalized/plain mapping, and host automation behavior.
- The editor introduces no audio-thread work, allocation, file I/O, new
  process, network, or sample-rate behavior.
- Native tests, the production build, and VST3 validation pass before the
  staged live profile is updated.

## 9. Explicit non-goals

- No copied Slate Digital branding, visual assets, or module model.
- No false input meter, note readout, tuner, or performance-score claim.
- No rework of REAPER's overall application theme.
- No persistent installation or alteration of the user's normal REAPER
  profile.
- No change to the detector's present one-note live calibration workflow.
