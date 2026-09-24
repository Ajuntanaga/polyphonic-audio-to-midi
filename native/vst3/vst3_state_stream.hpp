#pragma once

#include "m3/string_calibration.hpp"
#include "m3/state_image.hpp"
#include "pluginterfaces/base/ibstream.h"

namespace m3::vst3 {

bool save_vst3_state(const PersistentConfig& config,
                     Steinberg::IBStream* stream) noexcept;
bool load_vst3_state(Steinberg::IBStream* stream,
                     PersistentConfig& output) noexcept;
bool save_vst3_state_with_calibration(
    const PersistentConfig& config, const StringCalibrationBank& calibration,
    Steinberg::IBStream* stream) noexcept;
bool load_vst3_state_with_calibration(
    Steinberg::IBStream* stream, PersistentConfig& config,
    StringCalibrationBank& calibration) noexcept;

}  // namespace m3::vst3
