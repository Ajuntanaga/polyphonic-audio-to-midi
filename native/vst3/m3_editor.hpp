#pragma once

#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

namespace m3::vst3 {

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept;

}  // namespace m3::vst3
