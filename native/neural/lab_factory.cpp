#include "lab_component.hpp"
#include "public.sdk/source/main/pluginfactory.h"
namespace {
const Steinberg::FUID lab_id(0x4DF13B28,0x9E8349D1,0xB17DA623,0x251F806C);
}
BEGIN_FACTORY_DEF("M3", "", "")
DEF_CLASS2(INLINE_UID_FROM_FUID(lab_id),Steinberg::PClassInfo::kManyInstances,kVstAudioEffectClass,
           "M3 Neural Lab (96 kHz)",0,"Fx|Analyzer","0.1.0",kVstVersionString,
           m3::neural::LabComponent::createInstance)
END_FACTORY
