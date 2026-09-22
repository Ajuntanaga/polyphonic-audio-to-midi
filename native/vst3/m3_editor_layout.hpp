#pragma once

#include <cstddef>
#include <cstdint>

#include "m3/parameter_contract.hpp"

namespace m3::vst3 {

enum class EditorPresentation : std::uint8_t {
  knob,
  segment,
  toggle,
  note_range,
  compact_value,
  momentary,
  status,
};

enum class EditorSurfacePage : std::uint8_t {
  tuner,
  settings,
};

struct EditorRect final {
  double left;
  double top;
  double right;
  double bottom;
};

struct EditorControlLayout final {
  ParameterId parameter_id;
  EditorPresentation presentation;
  EditorRect bounds;
  bool visible;
  bool enabled;
};

struct EditorChromeMetrics final {
  double header_logo_font_size;
  double header_title_font_size;
  double header_title_tracking;
  double header_title_top_offset;
  double control_caption_font_size;
  double control_value_font_size;
  double surface_shadow_offset;
  double button_shadow_offset;
  double button_glow_spread;
  double button_face_inset;
  double surface_corner_radius;
  double control_corner_radius;
  std::uint8_t glow_outer_alpha;
  std::uint8_t glow_inner_alpha;
  double momentary_face_inset;
  std::uint8_t chassis_vignette_alpha;
};

inline constexpr std::size_t kEditorControlCount = 16;
inline constexpr std::int32_t kEditorWidth = 1024;
inline constexpr std::int32_t kEditorHeight = 468;
inline constexpr std::int32_t kEditorMaximumWidth = 2048;
inline constexpr std::int32_t kEditorMaximumHeight = 936;

inline constexpr EditorChromeMetrics editor_chrome_metrics() noexcept {
  return EditorChromeMetrics{60.0, 29.0, 1.9, 10.0, 13.0, 20.0, 3.0,
                             2.0,  9.0, 0.0,  6.0,  3.5, 12U, 44U,
                             6.0,  28U};
}

inline constexpr const char* editor_instrument_font_family() noexcept {
  return "Liberation Sans Narrow";
}

inline constexpr std::size_t editor_input_meter_bar_count() noexcept {
  return 34U;
}

EditorControlLayout editor_control_layout(std::size_t index,
                                          const PersistentConfig& config,
                                          Status status,
                                          EditorSurfacePage page =
                                              EditorSurfacePage::settings) noexcept;
EditorRect editor_tuner_display_bounds() noexcept;
EditorRect editor_settings_button_bounds() noexcept;
EditorRect editor_settings_panel_bounds() noexcept;
EditorRect editor_settings_done_button_bounds() noexcept;
EditorRect editor_tuner_meter_arc_bounds(const EditorRect& lane) noexcept;
double advance_tuner_needle(double displayed_cents, double target_cents,
                            double elapsed_seconds) noexcept;
const char* status_label(Status status) noexcept;
std::uint32_t status_color(Status status) noexcept;

}  // namespace m3::vst3
