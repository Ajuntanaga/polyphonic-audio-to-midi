#include "m3_editor_layout.hpp"

#include <algorithm>
#include <array>
#include <cmath>

namespace m3::vst3 {
namespace {

constexpr ParameterId kMidiRoutingId = 0x4D330001U;
constexpr ParameterId kProfileModeId = 0x4D330002U;
constexpr ParameterId kA4ReferenceId = 0x4D330003U;
constexpr ParameterId kInputTrimId = 0x4D330004U;
constexpr ParameterId kSensitivityId = 0x4D330005U;
constexpr ParameterId kResponseId = 0x4D330006U;
constexpr ParameterId kLowestMidiNoteId = 0x4D330007U;
constexpr ParameterId kHighestMidiNoteId = 0x4D330008U;
constexpr ParameterId kMaximumPolyphonyId = 0x4D330009U;
constexpr ParameterId kMaximumFretId = 0x4D33000AU;
constexpr ParameterId kVelocityModeId = 0x4D33000BU;
constexpr ParameterId kFixedVelocityId = 0x4D33000CU;
constexpr ParameterId kMidiChannelId = 0x4D33000DU;
constexpr ParameterId kDryAudioId = 0x4D33000FU;

constexpr EditorRect kTunerDisplayBounds{16.0, 108.0, 1008.0, 332.0};
constexpr EditorRect kSettingsButtonBounds{878.0, 352.0, 1004.0, 426.0};
constexpr EditorRect kSettingsPanelBounds{16.0, 108.0, 1008.0, 438.0};
constexpr EditorRect kSettingsDoneButtonBounds{874.0, 114.0, 994.0, 150.0};

constexpr std::array<EditorControlLayout, kEditorControlCount> kTunerControls = {{
    {kStatusParameterId, EditorPresentation::status, {16.0, 16.0, 552.0, 100.0},
     true, false},
    {kPanicParameterId, EditorPresentation::momentary,
     {868.0, 28.0, 1008.0, 98.0}, true, true},
    {kMidiRoutingId, EditorPresentation::segment,
     {20.0, 356.0, 152.0, 426.0}, true, true},
    {kProfileModeId, EditorPresentation::segment,
     {160.0, 356.0, 280.0, 426.0}, true, true},
    {kA4ReferenceId, EditorPresentation::compact_value,
     {288.0, 356.0, 396.0, 426.0}, true, true},
    {kInputTrimId, EditorPresentation::knob, {440.0, 122.0, 574.0, 242.0}, false,
     true},
    {kSensitivityId, EditorPresentation::knob,
     {404.0, 356.0, 526.0, 426.0}, true, true},
    {kResponseId, EditorPresentation::knob, {534.0, 356.0, 650.0, 426.0}, true,
     true},
    {kLowestMidiNoteId, EditorPresentation::note_range,
     {860.0, 122.0, 1004.0, 242.0}, false, true},
    {kHighestMidiNoteId, EditorPresentation::note_range,
     {20.0, 254.0, 154.0, 374.0}, false, true},
    {kMaximumPolyphonyId, EditorPresentation::knob,
     {160.0, 254.0, 294.0, 374.0}, false, true},
    {kMaximumFretId, EditorPresentation::knob, {300.0, 254.0, 434.0, 374.0},
     false, true},
    {kVelocityModeId, EditorPresentation::segment,
     {440.0, 254.0, 574.0, 374.0}, false, true},
    {kFixedVelocityId, EditorPresentation::knob, {580.0, 254.0, 714.0, 374.0},
     false, true},
    {kMidiChannelId, EditorPresentation::compact_value,
     {658.0, 356.0, 750.0, 426.0}, true, true},
    {kDryAudioId, EditorPresentation::toggle, {758.0, 356.0, 868.0, 426.0}, true,
     true},
}};

constexpr std::array<EditorControlLayout, kEditorControlCount>
    kSettingsControls = {{
        {kStatusParameterId, EditorPresentation::status,
         {16.0, 16.0, 552.0, 100.0}, true, false},
        {kPanicParameterId, EditorPresentation::momentary,
         {868.0, 28.0, 1008.0, 98.0}, true, true},
        {kMidiRoutingId, EditorPresentation::segment,
         {20.0, 158.0, 154.0, 278.0}, true, true},
        {kProfileModeId, EditorPresentation::segment,
         {160.0, 158.0, 294.0, 278.0}, true, true},
        {kA4ReferenceId, EditorPresentation::knob,
         {300.0, 158.0, 434.0, 278.0}, true, true},
        {kInputTrimId, EditorPresentation::knob,
         {440.0, 158.0, 574.0, 278.0}, true, true},
        {kSensitivityId, EditorPresentation::knob,
         {580.0, 158.0, 714.0, 278.0}, true, true},
        {kResponseId, EditorPresentation::knob,
         {720.0, 158.0, 854.0, 278.0}, true, true},
        {kLowestMidiNoteId, EditorPresentation::note_range,
         {860.0, 158.0, 1004.0, 278.0}, true, true},
        {kHighestMidiNoteId, EditorPresentation::note_range,
         {20.0, 294.0, 154.0, 414.0}, true, true},
        {kMaximumPolyphonyId, EditorPresentation::knob,
         {160.0, 294.0, 294.0, 414.0}, true, true},
        {kMaximumFretId, EditorPresentation::knob,
         {300.0, 294.0, 434.0, 414.0}, true, true},
        {kVelocityModeId, EditorPresentation::segment,
         {440.0, 294.0, 574.0, 414.0}, true, true},
        {kFixedVelocityId, EditorPresentation::knob,
         {580.0, 294.0, 714.0, 414.0}, true, true},
        {kMidiChannelId, EditorPresentation::knob,
         {720.0, 294.0, 854.0, 414.0}, true, true},
        {kDryAudioId, EditorPresentation::toggle,
         {860.0, 294.0, 1004.0, 414.0}, true, true},
}};

}  // namespace

EditorControlLayout editor_control_layout(std::size_t index,
                                          const PersistentConfig& config,
                                          Status status,
                                          EditorSurfacePage page) noexcept {
  static_cast<void>(status);
  const auto& controls = page == EditorSurfacePage::tuner ? kTunerControls
                                                          : kSettingsControls;
  EditorControlLayout control =
      index < controls.size() ? controls[index] : controls[0];
  if (control.parameter_id == kFixedVelocityId &&
      config.velocity_mode != VelocityMode::fixed) {
    control.visible = false;
    control.enabled = false;
  }
  return control;
}

EditorRect editor_tuner_display_bounds() noexcept {
  return kTunerDisplayBounds;
}

EditorRect editor_settings_button_bounds() noexcept {
  return kSettingsButtonBounds;
}

EditorRect editor_settings_panel_bounds() noexcept {
  return kSettingsPanelBounds;
}

EditorRect editor_settings_done_button_bounds() noexcept {
  return kSettingsDoneButtonBounds;
}

EditorRect editor_tuner_meter_arc_bounds(const EditorRect& lane) noexcept {
  const double lane_width = std::max(0.0, lane.right - lane.left);
  const double inset = lane_width * 0.055;
  const double arc_width = std::max(0.0, lane_width - inset * 2.0);
  const double arc_height = arc_width;
  const double arc_top = lane.top + 16.0;
  return EditorRect{lane.left + inset, arc_top, lane.right - inset,
                    arc_top + arc_height};
}

double advance_tuner_needle(double displayed_cents, double target_cents,
                            double elapsed_seconds) noexcept {
  const double target =
      std::clamp(std::isfinite(target_cents) ? target_cents : 0.0, -50.0, 50.0);
  if (!std::isfinite(displayed_cents)) {
    return target;
  }
  const double displayed = std::clamp(displayed_cents, -50.0, 50.0);
  if (!std::isfinite(elapsed_seconds) || elapsed_seconds <= 0.0) {
    return displayed;
  }
  if (elapsed_seconds >= 0.25) {
    return target;
  }
  const double delta = target - displayed;
  if (std::abs(delta) <= 0.08) {
    return target;
  }
  constexpr double kResponseSeconds = 0.055;
  const double alpha = 1.0 - std::exp(-elapsed_seconds / kResponseSeconds);
  const double next = displayed + delta * alpha;
  return std::abs(target - next) <= 0.08 ? target : next;
}

const char* status_label(Status status) noexcept {
  switch (status) {
    case Status::ready:
      return "Ready";
    case Status::panic_hold:
      return "Panic hold";
    case Status::reconfiguring:
      return "Reconfiguring";
    case Status::midi_output_blocked:
      return "MIDI output blocked";
    case Status::invalid_input_or_state:
      return "Invalid input or state";
    case Status::unsupported_layout:
      return "Unsupported layout";
  }
  return "Invalid status";
}

std::uint32_t status_color(Status status) noexcept {
  switch (status) {
    case Status::ready:
      return 0x2E8B57U;
    case Status::panic_hold:
      return 0xE0A000U;
    case Status::reconfiguring:
      return 0x3A78C2U;
    case Status::midi_output_blocked:
      return 0xCC6B00U;
    case Status::invalid_input_or_state:
      return 0xC62828U;
    case Status::unsupported_layout:
      return 0x7B1FA2U;
  }
  return 0x404040U;
}

}  // namespace m3::vst3
