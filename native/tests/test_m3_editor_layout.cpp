#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "m3/parameter_contract.hpp"
#include "m3_editor_layout.hpp"
#include "test_support.hpp"

namespace {

constexpr m3::ParameterId kDetectorInputId = 0x4D330001U;
constexpr m3::ParameterId kDryAudioId = 0x4D33000FU;
constexpr m3::ParameterId kFixedVelocityId = 0x4D33000CU;

const m3::vst3::EditorControlLayout& layout_for(
    const std::array<m3::vst3::EditorControlLayout,
                     m3::vst3::kEditorControlCount>& layouts,
    m3::ParameterId id) noexcept {
  for (const auto& control : layouts) {
    if (control.parameter_id == id) {
      return control;
    }
  }
  return layouts[0];
}

bool intersects(const m3::vst3::EditorRect& first,
                const m3::vst3::EditorRect& second) noexcept {
  return first.left < second.right && second.left < first.right &&
         first.top < second.bottom && second.top < first.bottom;
}

}  // namespace

M3_TEST(editor_layout_preserves_the_parameter_contract_and_presentations) {
  m3::PersistentConfig fixed_config;
  fixed_config.velocity_mode = m3::VelocityMode::fixed;
  std::array<m3::vst3::EditorControlLayout, m3::vst3::kEditorControlCount>
      layouts{};
  for (std::size_t index = 0; index < layouts.size(); ++index) {
    layouts[index] = m3::vst3::editor_control_layout(
        index, fixed_config, m3::Status::ready);
    M3_EXPECT_TRUE(m3::find_parameter(layouts[index].parameter_id) != nullptr);
    for (std::size_t previous = 0; previous < index; ++previous) {
      M3_EXPECT_TRUE(layouts[previous].parameter_id != layouts[index].parameter_id);
    }
  }
  M3_EXPECT_EQ(layout_for(layouts, m3::kPanicParameterId).presentation,
               m3::vst3::EditorPresentation::momentary);
  M3_EXPECT_EQ(layout_for(layouts, m3::kStatusParameterId).presentation,
               m3::vst3::EditorPresentation::status);
  M3_EXPECT_EQ(layout_for(layouts, kDetectorInputId).presentation,
               m3::vst3::EditorPresentation::segment);
  M3_EXPECT_EQ(layout_for(layouts, kDryAudioId).presentation,
               m3::vst3::EditorPresentation::toggle);
}

M3_TEST(editor_layout_updates_fixed_velocity_visibility_without_overlaps) {
  m3::PersistentConfig dynamic_config;
  dynamic_config.velocity_mode = m3::VelocityMode::dynamic;
  m3::PersistentConfig fixed_config;
  fixed_config.velocity_mode = m3::VelocityMode::fixed;
  std::array<m3::vst3::EditorControlLayout, m3::vst3::kEditorControlCount>
      fixed_layouts{};
  for (std::size_t index = 0; index < fixed_layouts.size(); ++index) {
    const auto dynamic_layout = m3::vst3::editor_control_layout(
        index, dynamic_config, m3::Status::ready);
    fixed_layouts[index] = m3::vst3::editor_control_layout(
        index, fixed_config, m3::Status::ready);
    if (dynamic_layout.parameter_id == kFixedVelocityId) {
      M3_EXPECT_FALSE(dynamic_layout.visible);
      M3_EXPECT_FALSE(dynamic_layout.enabled);
      M3_EXPECT_TRUE(fixed_layouts[index].visible);
      M3_EXPECT_TRUE(fixed_layouts[index].enabled);
    }
    const auto& bounds = dynamic_layout.bounds;
    M3_EXPECT_TRUE(bounds.left >= 0.0 && bounds.top >= 0.0);
    M3_EXPECT_TRUE(bounds.right <= 1024.0 && bounds.bottom <= 620.0);
    M3_EXPECT_TRUE(bounds.left < bounds.right && bounds.top < bounds.bottom);
  }
  for (std::size_t first = 0; first < fixed_layouts.size(); ++first) {
    if (!fixed_layouts[first].visible) {
      continue;
    }
    for (std::size_t second = first + 1; second < fixed_layouts.size(); ++second) {
      if (fixed_layouts[second].visible) {
        M3_EXPECT_FALSE(
            intersects(fixed_layouts[first].bounds, fixed_layouts[second].bounds));
      }
    }
  }
}

M3_TEST(editor_layout_gives_every_status_a_truthful_distinct_display) {
  constexpr std::array<m3::Status, 6> kStatuses = {
      m3::Status::ready,
      m3::Status::panic_hold,
      m3::Status::reconfiguring,
      m3::Status::midi_output_blocked,
      m3::Status::invalid_input_or_state,
      m3::Status::unsupported_layout,
  };
  for (std::size_t index = 0; index < kStatuses.size(); ++index) {
    const char* label = m3::vst3::status_label(kStatuses[index]);
    const std::uint32_t color = m3::vst3::status_color(kStatuses[index]);
    M3_EXPECT_TRUE(label != nullptr && std::strlen(label) != 0U);
    M3_EXPECT_TRUE(color != 0U);
    for (std::size_t previous = 0; previous < index; ++previous) {
      M3_EXPECT_TRUE(color != m3::vst3::status_color(kStatuses[previous]));
    }
  }
}
