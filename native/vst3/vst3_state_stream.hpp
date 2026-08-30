#pragma once

#include "m3/state_image.hpp"
#include "pluginterfaces/base/ibstream.h"

namespace m3::vst3 {

bool save_vst3_state(const PersistentConfig& config,
                     Steinberg::IBStream* stream) noexcept;
bool load_vst3_state(Steinberg::IBStream* stream,
                     PersistentConfig& output) noexcept;

}  // namespace m3::vst3
