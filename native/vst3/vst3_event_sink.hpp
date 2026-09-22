#pragma once

#include <cstdint>

#include "m3/types.hpp"
#include "pluginterfaces/vst/ivstevents.h"

namespace m3::vst3 {

struct Vst3EventSinkContext final {
  Steinberg::Vst::IEventList* events{};
};

bool push_vst3_note(void* context,
                    const VoiceTransition& transition,
                    std::uint8_t one_based_channel) noexcept;

}  // namespace m3::vst3
