#include "m3_editor_layout.hpp"

#include <array>

namespace m3::vst3 {
namespace {

constexpr ParameterId kDetectorInputId = 0x4D330001U;
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

constexpr std::array<EditorControlLayout, kEditorControlCount> kControls = {{
    {kStatusParameterId, EditorPresentation::status, {24.0, 20.0, 790.0, 70.0},
     true, false},
    {kPanicParameterId, EditorPresentation::momentary,
     {820.0, 20.0, 1000.0, 70.0}, true, true},
    {kDetectorInputId, EditorPresentation::segment,
     {24.0, 130.0, 170.0, 190.0}, true, true},
    {kProfileModeId, EditorPresentation::segment,
     {190.0, 130.0, 336.0, 190.0}, true, true},
    {kA4ReferenceId, EditorPresentation::knob, {356.0, 130.0, 502.0, 250.0},
     true, true},
    {kInputTrimId, EditorPresentation::knob, {522.0, 130.0, 668.0, 250.0}, true,
     true},
    {kSensitivityId, EditorPresentation::knob, {688.0, 130.0, 834.0, 250.0},
     true, true},
    {kResponseId, EditorPresentation::knob, {854.0, 130.0, 1000.0, 250.0}, true,
     true},
    {kLowestMidiNoteId, EditorPresentation::note_range,
     {24.0, 300.0, 220.0, 380.0}, true, true},
    {kHighestMidiNoteId, EditorPresentation::note_range,
     {240.0, 300.0, 436.0, 380.0}, true, true},
    {kMaximumPolyphonyId, EditorPresentation::knob,
     {456.0, 280.0, 652.0, 400.0}, true, true},
    {kMaximumFretId, EditorPresentation::knob, {672.0, 280.0, 868.0, 400.0}, true,
     true},
    {kVelocityModeId, EditorPresentation::segment,
     {24.0, 460.0, 240.0, 520.0}, true, true},
    {kFixedVelocityId, EditorPresentation::knob, {270.0, 440.0, 466.0, 560.0},
     true, true},
    {kMidiChannelId, EditorPresentation::knob, {496.0, 440.0, 692.0, 560.0}, true,
     true},
    {kDryAudioId, EditorPresentation::toggle, {722.0, 460.0, 920.0, 520.0}, true,
     true},
}};

}  // namespace

EditorControlLayout editor_control_layout(std::size_t index,
                                          const PersistentConfig& config,
                                          Status status) noexcept {
  static_cast<void>(status);
  EditorControlLayout control =
      index < kControls.size() ? kControls[index] : kControls[0];
  if (control.parameter_id == kFixedVelocityId &&
      config.velocity_mode != VelocityMode::fixed) {
    control.visible = false;
    control.enabled = false;
  }
  return control;
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
