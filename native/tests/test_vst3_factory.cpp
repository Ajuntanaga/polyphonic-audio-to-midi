#include <cstring>

#include "vst3_component.hpp"

#include "fake_vst3_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

void expected_probe_id(Steinberg::TUID output) noexcept {
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  id.toTUID(output);
}

}  // namespace

M3_TEST(vst3_factory_exposes_one_exact_nondistributable_probe_class) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  M3_EXPECT_TRUE(factory != nullptr);
  if (factory == nullptr) {
    return;
  }
  Steinberg::PFactoryInfo factory_info{};
  M3_EXPECT_EQ(factory->getFactoryInfo(&factory_info), Steinberg::kResultOk);
  M3_EXPECT_TRUE(std::strcmp(factory_info.vendor, m3::vst3::kVendorName) == 0);
  M3_EXPECT_EQ(factory->countClasses(), 1);

  Steinberg::IPluginFactory2* factory2 = nullptr;
  M3_EXPECT_EQ(factory->queryInterface(
                   Steinberg::IPluginFactory2::iid,
                   reinterpret_cast<void**>(&factory2)),
               Steinberg::kResultOk);
  M3_EXPECT_TRUE(factory2 != nullptr);
  if (factory2 != nullptr) {
    Steinberg::PClassInfo2 info{};
    M3_EXPECT_EQ(factory2->getClassInfo2(0, &info), Steinberg::kResultOk);
    Steinberg::TUID expected{};
    expected_probe_id(expected);
    M3_EXPECT_TRUE(std::memcmp(info.cid, expected, sizeof(expected)) == 0);
    M3_EXPECT_EQ(info.cardinality, Steinberg::PClassInfo::kManyInstances);
    M3_EXPECT_TRUE(std::strcmp(info.category, kVstAudioEffectClass) == 0);
    M3_EXPECT_TRUE(std::strcmp(info.name, m3::vst3::kProbeProductName) == 0);
    M3_EXPECT_TRUE((info.classFlags & Steinberg::Vst::kDistributable) == 0U);
    M3_EXPECT_TRUE(
        std::strcmp(info.subCategories,
                    m3::vst3::kProductionSubcategories) == 0);
    M3_EXPECT_TRUE(std::strcmp(info.version, m3::vst3::kVersionString) == 0);
    M3_EXPECT_TRUE(factory2->getClassInfo2(1, &info) != Steinberg::kResultOk);
    factory2->release();
  }
  factory->release();
}

M3_TEST(vst3_factory_returns_one_combined_component_identity) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  M3_EXPECT_TRUE(factory != nullptr);
  if (factory == nullptr) {
    return;
  }
  Steinberg::TUID class_id{};
  expected_probe_id(class_id);
  Steinberg::Vst::IComponent* component = nullptr;
  M3_EXPECT_EQ(factory->createInstance(
                   class_id, Steinberg::Vst::IComponent::iid,
                   reinterpret_cast<void**>(&component)),
               Steinberg::kResultOk);
  M3_EXPECT_TRUE(component != nullptr);
  if (component != nullptr) {
    Steinberg::Vst::IAudioProcessor* processor = nullptr;
    Steinberg::Vst::IEditController* controller = nullptr;
    M3_EXPECT_EQ(component->queryInterface(
                     Steinberg::Vst::IAudioProcessor::iid,
                     reinterpret_cast<void**>(&processor)),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(component->queryInterface(
                     Steinberg::Vst::IEditController::iid,
                     reinterpret_cast<void**>(&controller)),
                 Steinberg::kResultOk);
    M3_EXPECT_TRUE(processor != nullptr);
    M3_EXPECT_TRUE(controller != nullptr);
    Steinberg::FUnknown* component_identity = nullptr;
    Steinberg::FUnknown* processor_identity = nullptr;
    Steinberg::FUnknown* controller_identity = nullptr;
    component->queryInterface(Steinberg::FUnknown::iid,
                              reinterpret_cast<void**>(&component_identity));
    if (processor != nullptr) {
      processor->queryInterface(
          Steinberg::FUnknown::iid,
          reinterpret_cast<void**>(&processor_identity));
    }
    if (controller != nullptr) {
      controller->queryInterface(
          Steinberg::FUnknown::iid,
          reinterpret_cast<void**>(&controller_identity));
    }
    M3_EXPECT_TRUE(component_identity == processor_identity);
    M3_EXPECT_TRUE(component_identity == controller_identity);
    if (component_identity != nullptr) {
      component_identity->release();
    }
    if (processor_identity != nullptr) {
      processor_identity->release();
    }
    if (controller_identity != nullptr) {
      controller_identity->release();
    }
    if (processor != nullptr) {
      processor->release();
    }
    if (controller != nullptr) {
      controller->release();
    }
    component->release();
  }
  factory->release();
}
