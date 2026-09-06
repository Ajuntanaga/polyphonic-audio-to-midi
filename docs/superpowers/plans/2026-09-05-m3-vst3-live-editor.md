# M3 VST3 Live Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a polished, vector-drawn VST3 editor for M3 that replaces
REAPER's generic parameter wall without changing the live detector or its
96 kHz audio path.

**Architecture:** Add the VSTGUI revision paired with the pinned VST3 SDK,
then create a pure C++ layout/presentation model and a thin VSTGUI editor that
binds it to the original VST3 parameter contract. The editor is code-drawn,
uses one combined VST3 controller/processor as today, and is tested first with
the existing fake host before it is opened in the disposable REAPER profile.

**Tech Stack:** C++17, Steinberg VST3 SDK `v3.8.1_build_84`, VSTGUI commit
`5db272256172557818b6158cf0bb2c4410bddb25`, CMake, the existing native test
runner, Python `unittest`, and REAPER only through the staged 96 kHz profile.

**Spec:** `docs/superpowers/specs/2026-09-05-m3-vst3-editor-design.md`

## Global Constraints

- The editor design supersedes only the prior documents' “no custom GUI” and
  “VSTGUI disabled” restrictions. All detector, note-output, state, parameter,
  host-rate, and live-profile contracts remain fixed.
- Add VSTGUI solely as the exact official source at
  `third_party/vst3sdk/vstgui4`; no network fetch occurs during CMake configure
  or normal build.
- VSTGUI is a UI-thread dependency. No audio callback, detector, prepared
  configuration exchange, or generated-note code includes or calls it.
- Keep every existing parameter ID, range, default, state encoding,
  normalized/plain conversion, and host-automation route byte-for-byte stable.
- Initial editor geometry is `1024 x 620` logical pixels. Render vectors and
  text; use no copied brand assets, no raster skin, and no network/runtime file
  I/O.
- The main surface uses knobs for continuous musical values, segmented choices
  for lists, toggles for booleans, a linked visual for the MIDI range, a
  momentary Panic action, and a read-only status chip. Fixed Velocity is only
  interactive in Fixed Velocity mode.
- Retain REAPER's generic parameter interface as the host fallback when an
  editor cannot attach. Do not modify the user's normal REAPER profile.
- Build and test serially with the existing guard. A VSTGUI build, validator,
  or host-attachment failure stops the current task before the disposable
  profile is refreshed.

## File Map

| Path | Responsibility |
| --- | --- |
| `.gitmodules` | Exact VSTGUI source location and URL |
| `third_party/vst3sdk/vstgui4` | Exact VSTGUI Git link required by the retained SDK |
| `third_party/vst3sdk/UPSTREAM.md` | Extend third-party provenance with the VSTGUI Git-link revision and source boundary |
| `CMakeLists.txt` / `cmake/M3Vst3Sdk.cmake` | Enable VSTGUI only from the pinned local tree; link only editor-containing targets |
| `tools/validate_native_source.py` | Permit VSTGUI only under the audited UI/build paths; keep all other UI frameworks forbidden |
| `native/vst3/m3_editor_layout.hpp/.cpp` | Pure control presentation, layout, visibility, and status mapping |
| `native/vst3/m3_editor.hpp/.cpp` | VST3 editor lifetime, VSTGUI surface, host parameter gestures, and code-drawn controls |
| `native/vst3/vst3_component.hpp/.cpp` | Return the M3 editor only for `ViewType::kEditor` |
| `native/tests/test_m3_editor_layout.cpp` | Pure no-redundancy, geometry, status, and visibility tests |
| `native/tests/test_vst3_editor.cpp` | Editor lifecycle, parameter-gesture, resize, and read-only tests |
| `native/tests/fake_vst3_host.hpp/.cpp` | Component-handler gesture recorder required by editor tests |
| `native/tests/test_vst3_lifecycle.cpp` | Replace the null-editor assertion with the actual VST3 editor contract |
| `tests/test_vst3_build_contract.py` | Pin the VSTGUI source/build graph and UI-source boundary |
| `README.md` / `docs/VST3-TESTING.md` | Updated editor usage, build evidence, and disposable 96 kHz visual-check record |

---

### Task 1: Pin the local VSTGUI build boundary

**Files:**
- Create: `.gitmodules`
- Add: `third_party/vst3sdk/vstgui4` at commit
  `5db272256172557818b6158cf0bb2c4410bddb25`
- Modify: `third_party/vst3sdk/UPSTREAM.md`,
  `cmake/M3Vst3Sdk.cmake`, `CMakeLists.txt`,
  `tools/validate_native_source.py`, `tests/test_vst3_build_contract.py`

**Interfaces:**
- Consumes: the retained VST3 SDK root and its matching VSTGUI Git link.
- Produces: a completely local CMake VSTGUI target named `vstgui_support` and
  a build contract that rejects any other UI framework, network build step, or
  UI reference in the audio path.

- [ ] **Step 1: Write the VSTGUI source/build-contract RED**

  Add a focused `test_vstgui_editor_dependency_is_exact_and_local` assertion to
  `tests/test_vst3_build_contract.py`:

  ```python
  VSTGUI_PATH = VST3_SDK_ROOT / "vstgui4"
  VSTGUI_REVISION = "5db272256172557818b6158cf0bb2c4410bddb25"

  self.assertTrue(VSTGUI_PATH.is_dir(), "VSTGUI source is absent")
  self.assertTrue((VSTGUI_PATH / "CMakeLists.txt").is_file())
  self.assertIn("SMTG_ENABLE_VSTGUI_SUPPORT ON", build_text)
  self.assertIn("vstgui_support", build_text)
  ```

  Require the checked-in Git link to equal `VSTGUI_REVISION`, require the SDK
  provenance record to name the VSTGUI repository/revision/license, and narrow
  `validate_native_source.py` so `vstgui` is legal only in the VSTGUI tree,
  `CMakeLists.txt`, `cmake/M3Vst3Sdk.cmake`, and `native/vst3/m3_editor*`.

- [ ] **Step 2: Run the source/build-contract RED**

  Run:

  ```bash
  python3 -B -m unittest tests.test_vst3_build_contract.Vst3BuildContractTests.test_vstgui_editor_dependency_is_exact_and_local -v
  ```

  Expected: FAIL with `VSTGUI source is absent` or a missing VSTGUI build
  setting; no build or REAPER process starts.

- [ ] **Step 3: Add only the matched local VSTGUI source and CMake wiring**

  Add the official source as the SDK's expected child, never through CMake:

  ```bash
  git submodule add --force https://github.com/steinbergmedia/vstgui.git \
    third_party/vst3sdk/vstgui4
  git -C third_party/vst3sdk/vstgui4 checkout --detach \
    5db272256172557818b6158cf0bb2c4410bddb25
  ```

  Replace the current forced VSTGUI-off setting with:

  ```cmake
  set(SMTG_ENABLE_VSTGUI_SUPPORT ON CACHE BOOL "" FORCE)
  ```

  Add `vstgui4/CMakeLists.txt` to the required pinned SDK paths. Extend the
  explicit adapter-source graph and link `vstgui_support` only after Task 3
  adds the editor source; do not add FetchContent, a download command, JUCE,
  iPlug2, or an additional plug-in target.

- [ ] **Step 4: Verify configuration and provenance are green**

  Run:

  ```bash
  python3 -B -m unittest tests.test_vst3_build_contract.Vst3BuildContractTests.test_vstgui_editor_dependency_is_exact_and_local -v
  python3 -B -m unittest tests.test_vst3_build_contract.Vst3BuildContractTests.test_cmake_build_graph_is_explicit_offline_and_hardened -v
  ```

  Expected: PASS. CMake creates `vstgui_support` from the local pinned source;
  its cache contains `SMTG_ENABLE_VSTGUI_SUPPORT:BOOL=ON` and no network build
  construct appears in authored CMake.

- [ ] **Step 5: Commit the audited dependency boundary**

  ```bash
  git add .gitmodules third_party/vst3sdk/vstgui4 third_party/vst3sdk/UPSTREAM.md \
    cmake/M3Vst3Sdk.cmake CMakeLists.txt \
    tools/validate_native_source.py tests/test_vst3_build_contract.py
  git commit -m "build: pin VSTGUI editor dependency"
  ```

### Task 2: Build the pure live-editor layout model

**Files:**
- Create: `native/vst3/m3_editor_layout.hpp`, `native/vst3/m3_editor_layout.cpp`,
  `native/tests/test_m3_editor_layout.cpp`
- Modify: `CMakeLists.txt`, `tests/test_vst3_build_contract.py`

**Interfaces:**
- Consumes: `m3::ParameterId`, `PersistentConfig`, and `Status` from the
  existing parameter contract.
- Produces: a VSTGUI-independent description of every visible editor control:

  ```cpp
  namespace m3::vst3 {
  enum class EditorPresentation : std::uint8_t {
    knob, segment, toggle, note_range, momentary, status
  };
  struct EditorRect final { double left, top, right, bottom; };
  struct EditorControlLayout final {
    ParameterId parameter_id;
    EditorPresentation presentation;
    EditorRect bounds;
    bool visible;
    bool enabled;
  };
  constexpr std::size_t kEditorControlCount = 16;
  EditorControlLayout editor_control_layout(std::size_t index,
                                             const PersistentConfig&,
                                             Status) noexcept;
  const char* status_label(Status) noexcept;
  std::uint32_t status_color(Status) noexcept;
  }
  ```

- [ ] **Step 1: Write pure-layout RED tests**

  Add tests that assert all sixteen parameter IDs appear exactly once, with
  these mandatory presentations:

  ```cpp
  M3_EXPECT_EQ(layout_for(m3::kPanicParameterId).presentation,
               m3::vst3::EditorPresentation::momentary);
  M3_EXPECT_EQ(layout_for(m3::kStatusParameterId).presentation,
               m3::vst3::EditorPresentation::status);
  M3_EXPECT_EQ(layout_for(kDetectorInputId).presentation,
               m3::vst3::EditorPresentation::segment);
  M3_EXPECT_EQ(layout_for(kDryAudioId).presentation,
               m3::vst3::EditorPresentation::toggle);
  ```

  Test that Fixed Velocity is invisible/disabled in Dynamic mode and
  visible/enabled in Fixed mode; every rectangle is inside `1024 x 620`; no two
  visible rectangles overlap; and all six `Status` values have nonempty labels
  and distinct nonzero colors where an error needs distinction.

- [ ] **Step 2: Run the layout RED**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  ```

  Expected: compilation fails because `m3_editor_layout.hpp` is absent.

- [ ] **Step 3: Implement the fixed, vector-ready layout model**

  Use a fixed `std::array<EditorControlLayout, 16>` and the original parameter
  IDs. Partition `1024 x 620` into Header, Tracking, Performance Range, and
  Advanced/Routing regions. Never encode a second parameter value in the
  layout; visibility is derived only from `PersistentConfig::velocity_mode`.

  ```cpp
  if (control.parameter_id == kFixedVelocityId &&
      config.velocity_mode != VelocityMode::fixed) {
    control.visible = false;
    control.enabled = false;
  }
  ```

  Keep this file free of VSTGUI headers, allocations, I/O, host calls, and
  detector references.

- [ ] **Step 4: Run the pure layout suite**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  ```

  Expected: all existing native tests and the new layout tests pass.

- [ ] **Step 5: Commit the no-redundancy model**

  ```bash
  git add native/vst3/m3_editor_layout.hpp native/vst3/m3_editor_layout.cpp \
    native/tests/test_m3_editor_layout.cpp CMakeLists.txt \
    tests/test_vst3_build_contract.py
  git commit -m "feat: define M3 editor layout model"
  ```

### Task 3: Add the VST3 editor shell and host lifecycle

**Files:**
- Create: `native/vst3/m3_editor.hpp`, `native/vst3/m3_editor.cpp`,
  `native/tests/test_vst3_editor.cpp`
- Modify: `native/vst3/vst3_component.hpp`, `native/vst3/vst3_component.cpp`,
  `native/tests/fake_vst3_host.hpp`, `native/tests/fake_vst3_host.cpp`,
  `native/tests/test_vst3_lifecycle.cpp`, `CMakeLists.txt`

**Interfaces:**
- Consumes: the pure layout model, VSTGUI's `VST3Editor`, and the existing
  combined `M3Component`/`EditController`.
- Produces:

  ```cpp
  namespace m3::vst3 {
  Steinberg::IPlugView* create_m3_editor(
      Steinberg::Vst::EditController& controller) noexcept;
  }
  ```

  `M3Component::createView(ViewType::kEditor)` returns that view; a null or
  unsupported view name returns `nullptr`.

- [ ] **Step 1: Write editor-lifecycle RED tests**

  Replace the old assertion that the editor is null with:

  ```cpp
  Steinberg::IPlugView* view = controller->createView(
      Steinberg::Vst::ViewType::kEditor);
  M3_EXPECT_TRUE(view != nullptr);
  Steinberg::ViewRect rect{};
  M3_EXPECT_EQ(view->getSize(&rect), Steinberg::kResultTrue);
  M3_EXPECT_EQ(rect.right - rect.left, 1024);
  M3_EXPECT_EQ(rect.bottom - rect.top, 620);
  M3_EXPECT_TRUE(controller->createView("unsupported") == nullptr);
  view->release();
  ```

  Add an `IComponentHandler` fake that records `beginEdit`, `performEdit`, and
  `endEdit`; it initially proves only construction, view size, and safe remove
  before the later gesture task.

- [ ] **Step 2: Run the lifecycle RED**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  ```

  Expected: the prior `createView(...) == nullptr` implementation fails the
  new lifecycle test.

- [ ] **Step 3: Implement the VSTGUI shell**

  Add the editor sources to the explicit VST3 adapter list and link
  `vstgui_support` to `m3_native_tests`, `m3_vst3_probe`, and
  `m3_vst3_production`. Implement `M3Editor` as the one VSTGUI editor view,
  with a fixed initial `1024 x 620` size, minimum size constraint, content-scale
  support, and a code-created root surface. Its constructor receives only the
  existing `EditController`; it must not receive or retain an audio processor
  pointer.

  ```cpp
  Steinberg::IPlugView* PLUGIN_API M3Component::createView(
      Steinberg::FIDString name) {
    return name != nullptr &&
                   std::strcmp(name, Steinberg::Vst::ViewType::kEditor) == 0
               ? create_m3_editor(*this)
               : nullptr;
  }
  ```

- [ ] **Step 4: Run lifecycle and regression tests**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  python3 -B -m unittest tests.test_vst3_build_contract -q
  ```

  Expected: custom editor creation and lifecycle tests pass; all existing
  parameter, state, realtime, and build-contract tests remain green.

- [ ] **Step 5: Commit the editor shell**

  ```bash
  git add native/vst3/m3_editor.hpp native/vst3/m3_editor.cpp \
    native/vst3/vst3_component.hpp native/vst3/vst3_component.cpp \
    native/tests/test_vst3_editor.cpp native/tests/fake_vst3_host.hpp \
    native/tests/fake_vst3_host.cpp native/tests/test_vst3_lifecycle.cpp \
    CMakeLists.txt
  git commit -m "feat: add M3 VST3 editor shell"
  ```

### Task 4: Render the performance deck and bind its controls

**Files:**
- Modify: `native/vst3/m3_editor.hpp`, `native/vst3/m3_editor.cpp`,
  `native/tests/test_vst3_editor.cpp`, `native/tests/fake_vst3_host.hpp`,
  `native/tests/fake_vst3_host.cpp`, `native/tests/test_vst3_lifecycle.cpp`

**Interfaces:**
- Consumes: `EditorControlLayout`, all sixteen original parameter IDs, and the
  fake component-handler gesture log.
- Produces: a vector-drawn graphite M3 surface whose interaction route is
  exactly `beginEdit(id) -> setParamNormalized(id, value) ->
  performEdit(id, value) -> endEdit(id)` for writable parameters.

- [ ] **Step 1: Write interaction and read-only RED tests**

  Add a table-driven test over the writable controls:

  ```cpp
  const EditorGesture gesture = editor_gesture_for_test(
      m3::ParameterId{0x4D330005U}, 0.75);
  M3_EXPECT_EQ(gesture.parameter_id, 0x4D330005U);
  M3_EXPECT_NEAR(gesture.normalized_value, 0.75, 1.0e-12);
  M3_EXPECT_EQ(handler.begin_count(gesture.parameter_id), 1U);
  M3_EXPECT_EQ(handler.perform_count(gesture.parameter_id), 1U);
  M3_EXPECT_EQ(handler.end_count(gesture.parameter_id), 1U);
  ```

  Include a negative Status gesture, a Panic press/reset sequence, segment
  selection for Detector Input/Mode/Velocity, toggles for Dry Audio, a linked
  low/high note-range edit, and fixed-velocity suppression in Dynamic mode.

- [ ] **Step 2: Run the interaction RED**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  ```

  Expected: the editor shell has no control implementation or gesture log, so
  the new interaction test fails.

- [ ] **Step 3: Implement the code-drawn performance surface**

  Draw the four regions with VSTGUI paths, gradients, text, and focus rings:

  ```text
  Header:      M3 / live status / Panic
  Tracking:    Trim / Sensitivity / Response rotary controls
  Performance: linked Low–High MIDI range / Mode / Channel
  Routing:     Input / Dry Audio / Velocity / Advanced disclosure
  ```

  Use `CControl` subclasses for the rotary, segmented, toggle, linked-range,
  and momentary interactions. All colors and labels are defined locally in the
  editor source; no bitmap skin or external asset is loaded. On every control
  change, canonicalize through the existing parameter contract and make one
  VST3 host edit gesture. The `Status` control only reads the status parameter
  and never emits an edit.

- [ ] **Step 4: Run editor interaction, native, and source-boundary tests**

  Run:

  ```bash
  cmake --build build/vst3/debug --target m3_native_tests -j1
  build/vst3/debug/m3_native_tests
  python3 -B -m unittest tests.test_vst3_build_contract -q
  python3 -B tools/validate_native_source.py --check
  ```

  Expected: every on-screen write maps to its original parameter and one host
  gesture; Status stays read-only; source validation confirms no VSTGUI use in
  audio-thread code.

- [ ] **Step 5: Commit the finished editor surface**

  ```bash
  git add native/vst3/m3_editor.hpp native/vst3/m3_editor.cpp \
    native/tests/test_vst3_editor.cpp native/tests/fake_vst3_host.hpp \
    native/tests/fake_vst3_host.cpp native/tests/test_vst3_lifecycle.cpp
  git commit -m "feat: render M3 live performance editor"
  ```

### Task 5: Validate the production bundle and refresh the disposable 96 kHz profile

**Files:**
- Modify: `README.md`, `docs/VST3-TESTING.md`
- Generated-only: `build/vst3/release/**`,
  `build/m3-native-live-midi-8open-96k/**`

**Interfaces:**
- Consumes: the production VST3 with the custom editor, the current 96 kHz
  staging tool, and REAPER's normal VST3 editor attachment path.
- Produces: a build-local editor bundle and a visually checked disposable
  profile; it never changes the persistent VST3 install or normal REAPER
  configuration.

- [ ] **Step 1: Write the production-resource and editor-bundle RED**

  Extend `tests/test_vst3_build_contract.py` with a production assertion that
  the editor source is in the explicit production graph, that
  `vstgui_support` is linked, and that no VSTGUI test/example/tool target is
  made a production dependency.

- [ ] **Step 2: Run the production-build RED**

  Run:

  ```bash
  python3 -B -m unittest tests.test_vst3_build_contract -q
  ```

  Expected: it fails until the build graph names the editor sources and
  `vstgui_support` exactly.

- [ ] **Step 3: Build and validate the release bundle**

  Run:

  ```bash
  cmake -S . -B build/vst3/release -DCMAKE_BUILD_TYPE=Release
  cmake --build build/vst3/release --target m3_vst3_production -j1
  cmake --build build/vst3/release --target m3_validate_production -j1
  python3 -B -m unittest tests.test_vst3_build_contract tests.test_vst3_validator_runner -q
  ```

  Expected: native tests, source/build contract, the production bundle,
  module-info validation, and the official VST3 validator all pass before any
  REAPER reload.

- [ ] **Step 4: Refresh and visually verify only the disposable profile**

  Run:

  ```bash
  python3 tools/stage_live_midi_env.py \
    --output build/m3-native-live-midi-8open-96k \
    --detector native --sample-rate 96000
  ```

  Open the staged M3 instance in REAPER, confirm the custom `1024 x 620`
  editor attaches, resize it, exercise one non-destructive parameter gesture,
  verify its host parameter changes once, then restore the previous value.
  Confirm the status chip is textual and no unimplemented meter/note display is
  presented. Stop and preserve the failed staged profile if attachment or
  gesture behavior differs from the offline contract.

- [ ] **Step 5: Record the verification and commit**

  Update the README and VST3 testing guide with the editor's control groups,
  generic-host fallback, exact build commands, and the 96 kHz disposable visual
  check. Then commit:

  ```bash
  git add README.md docs/VST3-TESTING.md tests/test_vst3_build_contract.py
  git commit -m "docs: record M3 live editor validation"
  ```

## Plan Self-Review

- **Spec coverage:** Tasks 1–5 respectively cover the pinned UI dependency,
  redundant-control model, VST3 lifecycle, polished interaction surface, and
  production/disposable-host verification. The plan deliberately leaves DSP,
  live tracking-quality claims, and persistent installation untouched.
- **Type consistency:** `EditorControlLayout` is pure C++ and feeds the VSTGUI
  editor; parameter writes retain `ParameterId` and `ParamValue` through the
  existing combined component. No second configuration object appears.
- **Boundary review:** Only Task 5 opens REAPER and only after offline/native
  validation passes. The existing 96 kHz profile is refreshed in place under
  `build/`; no persistent plug-in location or general REAPER configuration is
  changed.
