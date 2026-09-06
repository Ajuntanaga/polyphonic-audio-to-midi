#include <cstring>
#include <limits>

#include "vst3_component.hpp"

#include "fake_vst3_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/gui/iplugview.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

Steinberg::Vst::IComponent* create_component(
    Steinberg::IPluginFactory* factory) noexcept {
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  Steinberg::Vst::IComponent* component = nullptr;
  if (factory == nullptr ||
      factory->createInstance(class_id, Steinberg::Vst::IComponent::iid,
                              reinterpret_cast<void**>(&component)) !=
          Steinberg::kResultOk) {
    return nullptr;
  }
  return component;
}

}  // namespace

M3_TEST(vst3_combined_lifecycle_is_exactly_once_and_balances_host_reference) {
  m3::vst3::reset_lifecycle_counters_for_test();
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = create_component(factory);
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_EQ(m3::vst3::lifecycle_counters_for_test().constructed, 1U);
  if (component != nullptr) {
    m3::test::FakeVst3Host host;
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_TRUE(component->initialize(&host) != Steinberg::kResultOk);
    M3_EXPECT_EQ(host.reference_count(), 2U);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    M3_EXPECT_TRUE(component->terminate() != Steinberg::kResultOk);
    M3_EXPECT_EQ(host.reference_count(), 1U);
    component->release();
  }
  const m3::vst3::LifecycleCounters counters =
      m3::vst3::lifecycle_counters_for_test();
  M3_EXPECT_EQ(counters.constructed, 1U);
  M3_EXPECT_EQ(counters.initialized, 1U);
  M3_EXPECT_EQ(counters.terminated, 1U);
  M3_EXPECT_EQ(counters.destroyed, 1U);
  if (factory != nullptr) {
    factory->release();
  }
}

M3_TEST(vst3_busses_layout_sample_sizes_latency_tail_and_view_are_exact) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = create_component(factory);
  M3_EXPECT_TRUE(component != nullptr);
  if (component == nullptr) {
    if (factory != nullptr) {
      factory->release();
    }
    return;
  }
  m3::test::FakeVst3Host host;
  M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
  M3_EXPECT_EQ(component->getBusCount(Steinberg::Vst::kAudio,
                                     Steinberg::Vst::kInput),
               1);
  M3_EXPECT_EQ(component->getBusCount(Steinberg::Vst::kAudio,
                                     Steinberg::Vst::kOutput),
               1);
  M3_EXPECT_EQ(component->getBusCount(Steinberg::Vst::kEvent,
                                     Steinberg::Vst::kInput),
               0);
  M3_EXPECT_EQ(component->getBusCount(Steinberg::Vst::kEvent,
                                     Steinberg::Vst::kOutput),
               1);
  Steinberg::Vst::BusInfo bus{};
  M3_EXPECT_EQ(component->getBusInfo(Steinberg::Vst::kAudio,
                                    Steinberg::Vst::kInput, 0, bus),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(bus.channelCount, 2);
  M3_EXPECT_EQ(bus.busType, Steinberg::Vst::kMain);
  M3_EXPECT_TRUE((bus.flags & Steinberg::Vst::BusInfo::kDefaultActive) != 0U);
  M3_EXPECT_EQ(component->getBusInfo(Steinberg::Vst::kAudio,
                                    Steinberg::Vst::kOutput, 0, bus),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(bus.channelCount, 2);
  M3_EXPECT_EQ(bus.busType, Steinberg::Vst::kMain);
  M3_EXPECT_TRUE((bus.flags & Steinberg::Vst::BusInfo::kDefaultActive) != 0U);
  M3_EXPECT_EQ(component->getBusInfo(Steinberg::Vst::kEvent,
                                    Steinberg::Vst::kOutput, 0, bus),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(bus.channelCount, 16);
  M3_EXPECT_EQ(bus.busType, Steinberg::Vst::kMain);
  M3_EXPECT_TRUE((bus.flags & Steinberg::Vst::BusInfo::kDefaultActive) != 0U);

  Steinberg::Vst::IAudioProcessor* processor = nullptr;
  Steinberg::Vst::IEditController* controller = nullptr;
  component->queryInterface(Steinberg::Vst::IAudioProcessor::iid,
                            reinterpret_cast<void**>(&processor));
  component->queryInterface(Steinberg::Vst::IEditController::iid,
                            reinterpret_cast<void**>(&controller));
  M3_EXPECT_TRUE(processor != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  if (processor != nullptr) {
    Steinberg::Vst::SpeakerArrangement input =
        Steinberg::Vst::SpeakerArr::kStereo;
    Steinberg::Vst::SpeakerArrangement output =
        Steinberg::Vst::SpeakerArr::kStereo;
    M3_EXPECT_EQ(processor->setBusArrangements(&input, 1, &output, 1),
                 Steinberg::kResultTrue);
    input = Steinberg::Vst::SpeakerArr::kMono;
    M3_EXPECT_TRUE(processor->setBusArrangements(&input, 1, &output, 1) !=
                   Steinberg::kResultTrue);
    M3_EXPECT_TRUE(processor->setBusArrangements(nullptr, 0, &output, 1) !=
                   Steinberg::kResultTrue);
    M3_EXPECT_EQ(processor->canProcessSampleSize(Steinberg::Vst::kSample32),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(processor->canProcessSampleSize(Steinberg::Vst::kSample64),
                 Steinberg::kResultTrue);
    M3_EXPECT_TRUE(processor->canProcessSampleSize(9) !=
                   Steinberg::kResultTrue);
    M3_EXPECT_EQ(processor->getLatencySamples(), 0U);
    M3_EXPECT_EQ(processor->getTailSamples(), Steinberg::Vst::kNoTail);
  }
  if (controller != nullptr) {
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      Steinberg::ViewRect rect{};
      M3_EXPECT_EQ(view->getSize(&rect), Steinberg::kResultTrue);
      M3_EXPECT_EQ(rect.right - rect.left, 1024);
      M3_EXPECT_EQ(rect.bottom - rect.top, 620);
      view->release();
    }
    M3_EXPECT_TRUE(controller->createView("unsupported") == nullptr);
    M3_EXPECT_TRUE(controller->createView(nullptr) == nullptr);
  }
  Steinberg::TUID controller_id{};
  M3_EXPECT_TRUE(component->getControllerClassId(controller_id) !=
                 Steinberg::kResultOk);
  if (controller != nullptr) {
    controller->release();
  }
  if (processor != nullptr) {
    processor->release();
  }
  M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
  component->release();
  if (factory != nullptr) {
    factory->release();
  }
}

M3_TEST(vst3_setup_activation_and_processing_state_machine_rejects_bad_inputs) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = create_component(factory);
  M3_EXPECT_TRUE(component != nullptr);
  if (component == nullptr) {
    if (factory != nullptr) {
      factory->release();
    }
    return;
  }
  m3::test::FakeVst3Host host;
  M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
  Steinberg::Vst::IAudioProcessor* processor = nullptr;
  component->queryInterface(Steinberg::Vst::IAudioProcessor::iid,
                            reinterpret_cast<void**>(&processor));
  M3_EXPECT_TRUE(processor != nullptr);
  if (processor != nullptr) {
    Steinberg::Vst::ProcessSetup setup{};
    setup.processMode = Steinberg::Vst::kRealtime;
    setup.symbolicSampleSize = Steinberg::Vst::kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000.0;
    M3_EXPECT_EQ(processor->setupProcessing(setup), Steinberg::kResultOk);
    setup.sampleRate = std::numeric_limits<double>::quiet_NaN();
    M3_EXPECT_TRUE(processor->setupProcessing(setup) != Steinberg::kResultOk);
    setup.sampleRate = 48000.0;
    setup.maxSamplesPerBlock = 0;
    M3_EXPECT_TRUE(processor->setupProcessing(setup) != Steinberg::kResultOk);
    setup.maxSamplesPerBlock = 16385;
    M3_EXPECT_TRUE(processor->setupProcessing(setup) != Steinberg::kResultOk);
    setup.maxSamplesPerBlock = 128;
    M3_EXPECT_EQ(component->setActive(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    M3_EXPECT_TRUE(component->setActive(Steinberg::TBool{1}) !=
                   Steinberg::kResultOk);
    M3_EXPECT_EQ(processor->setProcessing(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    M3_EXPECT_TRUE(processor->setProcessing(Steinberg::TBool{1}) !=
                   Steinberg::kResultOk);
    M3_EXPECT_EQ(processor->setProcessing(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(component->setActive(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    processor->release();
  }
  M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
  component->release();
  if (factory != nullptr) {
    factory->release();
  }
}
