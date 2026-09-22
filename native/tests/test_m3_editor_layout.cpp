#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "m3/parameter_contract.hpp"
#include "m3_editor_layout.hpp"
#include "test_support.hpp"

namespace {

constexpr m3::ParameterId kMidiRoutingId = 0x4D330001U;
constexpr m3::ParameterId kProfileModeId = 0x4D330002U;
constexpr m3::ParameterId kA4ReferenceId = 0x4D330003U;
constexpr m3::ParameterId kInputTrimId = 0x4D330004U;
constexpr m3::ParameterId kSensitivityId = 0x4D330005U;
constexpr m3::ParameterId kResponseId = 0x4D330006U;
constexpr m3::ParameterId kLowestMidiNoteId = 0x4D330007U;
constexpr m3::ParameterId kHighestMidiNoteId = 0x4D330008U;
constexpr m3::ParameterId kMaximumPolyphonyId = 0x4D330009U;
constexpr m3::ParameterId kMaximumFretId = 0x4D33000AU;
constexpr m3::ParameterId kVelocityModeId = 0x4D33000BU;
constexpr m3::ParameterId kDryAudioId = 0x4D33000FU;
constexpr m3::ParameterId kFixedVelocityId = 0x4D33000CU;
constexpr m3::ParameterId kMidiChannelId = 0x4D33000DU;

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
  M3_EXPECT_EQ(layout_for(layouts, kMidiRoutingId).presentation,
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
    M3_EXPECT_TRUE(
        bounds.right <= static_cast<double>(m3::vst3::kEditorWidth) &&
        bounds.bottom <= static_cast<double>(m3::vst3::kEditorHeight));
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

M3_TEST(editor_layout_e8_tuner_page_keeps_the_meter_bank_primary) {
  M3_EXPECT_EQ(m3::vst3::kEditorWidth, 1024);
  M3_EXPECT_EQ(m3::vst3::kEditorHeight, 468);
  M3_EXPECT_NEAR(static_cast<double>(m3::vst3::kEditorWidth) /
                     static_cast<double>(m3::vst3::kEditorHeight),
                 1860.0 / 846.0, 0.02);

  m3::PersistentConfig config;
  config.velocity_mode = m3::VelocityMode::fixed;
  std::array<m3::vst3::EditorControlLayout, m3::vst3::kEditorControlCount>
      layouts{};
  for (std::size_t index = 0; index < layouts.size(); ++index) {
    layouts[index] = m3::vst3::editor_control_layout(
        index, config, m3::Status::ready,
        m3::vst3::EditorSurfacePage::tuner);
  }

  constexpr std::array<m3::ParameterId, 9> kVisibleEssentials = {
      m3::kStatusParameterId, m3::kPanicParameterId, kMidiRoutingId,
      kProfileModeId, kA4ReferenceId, kSensitivityId, kResponseId,
      kMidiChannelId, kDryAudioId};
  for (const auto& layout : layouts) {
    bool expected_visible = false;
    for (const m3::ParameterId id : kVisibleEssentials) {
      expected_visible = expected_visible || layout.parameter_id == id;
    }
    M3_EXPECT_EQ(layout.visible, expected_visible);
  }
  M3_EXPECT_EQ(layout_for(layouts, kA4ReferenceId).presentation,
               m3::vst3::EditorPresentation::compact_value);
  M3_EXPECT_EQ(layout_for(layouts, kMidiChannelId).presentation,
               m3::vst3::EditorPresentation::compact_value);

  const auto tuner = m3::vst3::editor_tuner_display_bounds();
  const auto settings = m3::vst3::editor_settings_button_bounds();
  M3_EXPECT_TRUE(tuner.left >= 0.0 && tuner.top >= 0.0);
  M3_EXPECT_TRUE(tuner.right <= m3::vst3::kEditorWidth &&
                 tuner.bottom <= m3::vst3::kEditorHeight);
  M3_EXPECT_TRUE(tuner.right - tuner.left >= 980.0);
  M3_EXPECT_TRUE(tuner.bottom - tuner.top >= 216.0);
  M3_EXPECT_TRUE(tuner.bottom - tuner.top <= 232.0);
  M3_EXPECT_TRUE(tuner.top >= 104.0 && tuner.bottom <= 336.0);
  M3_EXPECT_FALSE(intersects(tuner, settings));
  for (std::size_t first = 0; first < layouts.size(); ++first) {
    if (!layouts[first].visible) {
      continue;
    }
    M3_EXPECT_FALSE(intersects(layouts[first].bounds, tuner));
    M3_EXPECT_FALSE(intersects(layouts[first].bounds, settings));
    for (std::size_t second = first + 1; second < layouts.size(); ++second) {
      if (layouts[second].visible) {
        M3_EXPECT_FALSE(
            intersects(layouts[first].bounds, layouts[second].bounds));
      }
    }
  }
}

M3_TEST(editor_chrome_matches_the_e8_dimensional_type_and_button_system) {
  const auto chrome = m3::vst3::editor_chrome_metrics();

  M3_EXPECT_TRUE(std::strcmp(m3::vst3::editor_instrument_font_family(),
                             "Liberation Sans Narrow") == 0);
  M3_EXPECT_TRUE(chrome.header_logo_font_size >= 52.0);
  M3_EXPECT_TRUE(chrome.header_title_font_size >= 25.0);
  M3_EXPECT_TRUE(chrome.header_title_tracking >= 1.5 &&
                 chrome.header_title_tracking <= 2.5);
  M3_EXPECT_TRUE(chrome.header_title_top_offset >= 8.0 &&
                 chrome.header_title_top_offset <= 12.0);
  M3_EXPECT_TRUE(chrome.control_caption_font_size >= 13.0);
  M3_EXPECT_TRUE(chrome.control_value_font_size >= 18.0);
  M3_EXPECT_TRUE(chrome.surface_shadow_offset >= 2.0);
  M3_EXPECT_TRUE(chrome.button_shadow_offset >= 2.0);
  M3_EXPECT_TRUE(chrome.button_glow_spread >= 8.0);
  M3_EXPECT_TRUE(chrome.button_face_inset <= 0.5);
  M3_EXPECT_TRUE(chrome.surface_corner_radius >= 5.0 &&
                 chrome.surface_corner_radius <= 7.0);
  M3_EXPECT_TRUE(chrome.control_corner_radius >= 3.0 &&
                 chrome.control_corner_radius <= 4.0);
  M3_EXPECT_TRUE(chrome.glow_outer_alpha <= 16U);
  M3_EXPECT_TRUE(chrome.glow_inner_alpha >= 28U &&
                 chrome.glow_inner_alpha <= 56U);
  M3_EXPECT_TRUE(chrome.momentary_face_inset >= 5.0 &&
                 chrome.momentary_face_inset <= 7.0);
  M3_EXPECT_TRUE(chrome.chassis_vignette_alpha >= 20U &&
                 chrome.chassis_vignette_alpha <= 40U);
  M3_EXPECT_TRUE(m3::vst3::editor_input_meter_bar_count() >= 32U);
  M3_EXPECT_TRUE(m3::vst3::editor_input_meter_bar_count() <= 36U);

  m3::PersistentConfig config;
  const auto panic = m3::vst3::editor_control_layout(
      1U, config, m3::Status::ready, m3::vst3::EditorSurfacePage::tuner);
  M3_EXPECT_EQ(panic.parameter_id, m3::kPanicParameterId);
  M3_EXPECT_TRUE(panic.bounds.left <= 868.0);
  M3_EXPECT_TRUE(panic.bounds.top <= 30.0);
  M3_EXPECT_TRUE(panic.bounds.right >= 1008.0);
  M3_EXPECT_TRUE(panic.bounds.bottom - panic.bounds.top >= 68.0);
  M3_EXPECT_TRUE(panic.bounds.bottom - panic.bounds.top <= 72.0);
}

M3_TEST(editor_layout_settings_page_exposes_every_parameter_without_overlap) {
  m3::PersistentConfig config;
  config.velocity_mode = m3::VelocityMode::fixed;
  std::array<m3::vst3::EditorControlLayout, m3::vst3::kEditorControlCount>
      layouts{};
  for (std::size_t index = 0; index < layouts.size(); ++index) {
    layouts[index] = m3::vst3::editor_control_layout(
        index, config, m3::Status::ready,
        m3::vst3::EditorSurfacePage::settings);
    M3_EXPECT_TRUE(layouts[index].visible);
    M3_EXPECT_TRUE(layouts[index].bounds.left < layouts[index].bounds.right);
    M3_EXPECT_TRUE(layouts[index].bounds.top < layouts[index].bounds.bottom);
  }
  for (std::size_t first = 0; first < layouts.size(); ++first) {
    for (std::size_t second = first + 1; second < layouts.size(); ++second) {
      M3_EXPECT_FALSE(
          intersects(layouts[first].bounds, layouts[second].bounds));
    }
  }
  M3_EXPECT_EQ(layout_for(layouts, kA4ReferenceId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kMidiChannelId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kInputTrimId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kSensitivityId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kResponseId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kLowestMidiNoteId).presentation,
               m3::vst3::EditorPresentation::note_range);
  M3_EXPECT_EQ(layout_for(layouts, kHighestMidiNoteId).presentation,
               m3::vst3::EditorPresentation::note_range);
  M3_EXPECT_EQ(layout_for(layouts, kMaximumPolyphonyId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kMaximumFretId).presentation,
               m3::vst3::EditorPresentation::knob);
  M3_EXPECT_EQ(layout_for(layouts, kVelocityModeId).presentation,
               m3::vst3::EditorPresentation::segment);
}

M3_TEST(editor_settings_page_uses_two_balanced_instrument_rows_and_compact_done) {
  const auto panel = m3::vst3::editor_settings_panel_bounds();
  const auto done = m3::vst3::editor_settings_done_button_bounds();
  M3_EXPECT_TRUE(panel.left >= 16.0 && panel.right <= 1008.0);
  M3_EXPECT_TRUE(panel.top >= 106.0 && panel.top <= 110.0);
  M3_EXPECT_TRUE(panel.bottom >= 432.0 && panel.bottom <= 442.0);
  M3_EXPECT_TRUE(done.left >= 850.0 && done.right <= panel.right - 12.0);
  M3_EXPECT_TRUE(done.top >= panel.top + 4.0);
  M3_EXPECT_TRUE(done.bottom <= panel.top + 50.0);
  M3_EXPECT_TRUE(done.bottom - done.top >= 36.0);

  m3::PersistentConfig config;
  config.velocity_mode = m3::VelocityMode::fixed;
  std::array<m3::vst3::EditorControlLayout, m3::vst3::kEditorControlCount>
      layouts{};
  std::size_t top_row = 0U;
  std::size_t bottom_row = 0U;
  for (std::size_t index = 0U; index < layouts.size(); ++index) {
    layouts[index] = m3::vst3::editor_control_layout(
        index, config, m3::Status::ready,
        m3::vst3::EditorSurfacePage::settings);
    if (layouts[index].parameter_id == m3::kStatusParameterId ||
        layouts[index].parameter_id == m3::kPanicParameterId) {
      continue;
    }
    const auto& bounds = layouts[index].bounds;
    M3_EXPECT_TRUE(bounds.left >= panel.left + 4.0);
    M3_EXPECT_TRUE(bounds.right <= panel.right - 4.0);
    M3_EXPECT_TRUE(bounds.top >= panel.top + 48.0);
    M3_EXPECT_TRUE(bounds.bottom <= panel.bottom - 10.0);
    M3_EXPECT_TRUE(bounds.bottom - bounds.top >= 112.0);
    M3_EXPECT_FALSE(intersects(bounds, done));
    if (bounds.top < 280.0) {
      ++top_row;
    } else {
      ++bottom_row;
    }
  }
  M3_EXPECT_EQ(top_row, 7U);
  M3_EXPECT_EQ(bottom_row, 7U);
}

M3_TEST(editor_tuner_needle_motion_is_snappy_monotonic_and_bounded) {
  double displayed = -40.0;
  const double first =
      m3::vst3::advance_tuner_needle(displayed, 30.0, 1.0 / 60.0);
  M3_EXPECT_TRUE(first > displayed && first < 30.0);
  displayed = first;
  for (std::size_t frame = 0; frame < 60U; ++frame) {
    const double next =
        m3::vst3::advance_tuner_needle(displayed, 30.0, 1.0 / 60.0);
    M3_EXPECT_TRUE(next >= displayed && next <= 30.0);
    displayed = next;
  }
  M3_EXPECT_NEAR(displayed, 30.0, 0.08);
  M3_EXPECT_NEAR(m3::vst3::advance_tuner_needle(12.0, 90.0, 1.0),
                 50.0, 1.0e-12);
  M3_EXPECT_NEAR(m3::vst3::advance_tuner_needle(12.0, -90.0, 1.0),
                 -50.0, 1.0e-12);
  M3_EXPECT_NEAR(m3::vst3::advance_tuner_needle(12.0, 30.0, 0.0),
                 12.0, 1.0e-12);
}

M3_TEST(editor_tuner_meter_arc_is_wide_and_mechanical_not_oval) {
  const m3::vst3::EditorRect lane{0.0, 0.0, 120.0, 166.0};
  const auto arc = m3::vst3::editor_tuner_meter_arc_bounds(lane);
  const double width = arc.right - arc.left;
  const double height = arc.bottom - arc.top;

  M3_EXPECT_TRUE(arc.left >= lane.left && arc.right <= lane.right);
  M3_EXPECT_TRUE(arc.top >= lane.top && arc.bottom <= lane.bottom);
  M3_EXPECT_TRUE(width >= 104.0);
  M3_EXPECT_NEAR(height, width, 1.0e-12);
  M3_EXPECT_TRUE((arc.top + arc.bottom) * 0.5 <= lane.top + 70.0);
}
