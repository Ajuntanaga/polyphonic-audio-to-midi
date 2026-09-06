#pragma once

#include "m3/parameter_contract.hpp"
#include "m3_editor_layout.hpp"
#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

namespace m3::vst3 {

struct EditorGesture final {
  ParameterId parameter_id{};
  double normalized_value{};
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
#endif

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept;

}  // namespace m3::vst3
