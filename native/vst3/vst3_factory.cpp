#include "vst3_component.hpp"

#include "public.sdk/source/main/pluginfactory.h"
#include "vst3_ids.hpp"
#if defined(M3_VST3_PROBE_BUILD)
#include "vst3_probe_processor.hpp"
#endif

namespace {

#if defined(M3_VST3_PROBE_BUILD) || defined(M3_TESTING)
const auto& selected_class_id_words = m3::vst3::kProbeClassIdWords;
constexpr const char* selected_product_name = m3::vst3::kProbeProductName;
#else
const auto& selected_class_id_words = m3::vst3::kProductionClassIdWords;
constexpr const char* selected_product_name = m3::vst3::kProductName;
#endif

const Steinberg::FUID selected_class_id(selected_class_id_words[0],
                                        selected_class_id_words[1],
                                        selected_class_id_words[2],
                                        selected_class_id_words[3]);

}  // namespace

BEGIN_FACTORY_DEF(m3::vst3::kVendorName, "", "")

#if defined(M3_VST3_PROBE_BUILD)
DEF_CLASS2(INLINE_UID_FROM_FUID(selected_class_id),
           Steinberg::PClassInfo::kManyInstances, kVstAudioEffectClass,
           selected_product_name, 0, m3::vst3::kProductionSubcategories,
           m3::vst3::kVersionString, kVstVersionString,
           m3::vst3::M3ProbeProcessor::createInstance)
#else
DEF_CLASS2(INLINE_UID_FROM_FUID(selected_class_id),
           Steinberg::PClassInfo::kManyInstances, kVstAudioEffectClass,
           selected_product_name, 0, m3::vst3::kProductionSubcategories,
           m3::vst3::kVersionString, kVstVersionString,
           m3::vst3::M3Component::createInstance)
#endif

END_FACTORY
