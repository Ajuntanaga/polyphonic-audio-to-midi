#pragma once

#include <cstdint>

#include "m3/types.hpp"
#include "pluginterfaces/vst/ivstevents.h"

namespace m3::vst3 {

struct Vst3EventSinkContext final {
  Steinberg::Vst::IEventList* events{};
  std::uint8_t one_based_channel{1};
};

bool push_vst3_note(void* context,
                    const VoiceTransition& transition) noexcept;

}  // namespace m3::vst3
