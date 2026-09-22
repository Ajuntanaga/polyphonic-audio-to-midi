#pragma once

#include <cstddef>
#include <cstdint>

#include "m3/parameter_contract.hpp"
#include "m3/tuner_telemetry.hpp"
#include "m3_editor_layout.hpp"
#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

namespace m3::vst3 {

class M3Component;

struct EditorGesture final {
  ParameterId parameter_id{};
  double normalized_value{};
  bool value_applied{};
  bool accepted{};
};

struct EditorRangeGesture final {
  double low_normalized{};
  double high_normalized{};
  bool accepted{};
};

EditorGesture editor_gesture_for_test(
    Steinberg::Vst::EditController& controller, ParameterId parameter_id,
    double normalized_value, VelocityMode velocity_mode) noexcept;
bool editor_panic_for_test(
    Steinberg::Vst::EditController& controller) noexcept;
EditorRangeGesture editor_range_gesture_for_test(
    Steinberg::Vst::EditController& controller, double low_normalized,
    double high_normalized) noexcept;

#if defined(M3_TESTING)
bool editor_pointer_down_for_test(Steinberg::IPlugView& view,
                                  ParameterId parameter_id,
                                  double x_fraction, double y_fraction,
                                  bool default_reset) noexcept;
bool editor_pointer_drag_for_test(Steinberg::IPlugView& view,
                                  ParameterId parameter_id,
                                  double vertical_delta) noexcept;
bool editor_pointer_up_for_test(Steinberg::IPlugView& view,
                                ParameterId parameter_id) noexcept;
bool editor_pointer_cancel_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id) noexcept;
bool editor_wheel_for_test(Steinberg::IPlugView& view,
                           ParameterId parameter_id,
                           double vertical_delta) noexcept;
bool editor_remove_control_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id) noexcept;
bool editor_control_bounds_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id,
                                    EditorRect& bounds) noexcept;
bool editor_control_visible_for_test(Steinberg::IPlugView& view,
                                     ParameterId parameter_id) noexcept;
bool editor_settings_open_for_test(Steinberg::IPlugView& view) noexcept;
bool editor_toggle_settings_for_test(Steinberg::IPlugView& view) noexcept;
bool editor_render_rgba_for_test(Steinberg::IPlugView& view,
                                 std::uint8_t* rgba,
                                 std::size_t byte_count) noexcept;
std::size_t editor_control_invalidation_count_for_test(
    Steinberg::IPlugView& view, ParameterId parameter_id) noexcept;
double editor_content_scale_factor_for_test(
    Steinberg::IPlugView& view) noexcept;
bool editor_refresh_tuner_for_test(Steinberg::IPlugView& view) noexcept;
bool editor_tuner_snapshot_for_test(Steinberg::IPlugView& view,
                                    TunerSnapshot& snapshot) noexcept;
std::size_t editor_tuner_invalidation_count_for_test(
    Steinberg::IPlugView& view) noexcept;
std::size_t editor_attach_refresh_count_for_test(
    Steinberg::IPlugView& view) noexcept;
#endif

Steinberg::IPlugView* create_m3_editor(
    M3Component& component) noexcept;

}  // namespace m3::vst3
