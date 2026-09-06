#pragma once

#include "m3/parameter_contract.hpp"
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

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept;

}  // namespace m3::vst3
