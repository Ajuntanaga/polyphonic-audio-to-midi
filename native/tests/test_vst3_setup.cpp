#include <cmath>
#include <cstring>
#include <limits>

#include "fake_vst3_host.hpp"
#include "m3/parameter_contract.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct SetupInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  m3::test::FakeVst3Host host{};
};

bool open_instance(SetupInstance& instance) noexcept {
  instance.factory = GetPluginFactory();
  if (instance.factory == nullptr) {
    return false;
  }
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  return instance.factory->createInstance(
             class_id, Steinberg::Vst::IComponent::iid,
             reinterpret_cast<void**>(&instance.component)) ==
             Steinberg::kResultOk &&
         instance.component != nullptr &&
         instance.component->initialize(&instance.host) ==
             Steinberg::kResultOk &&
         instance.component->queryInterface(
             Steinberg::Vst::IAudioProcessor::iid,
             reinterpret_cast<void**>(&instance.processor)) ==
             Steinberg::kResultOk &&
         instance.processor != nullptr;
}

Steinberg::tresult setup(SetupInstance& instance, double sample_rate,
                         Steinberg::int32 max_frames = 512,
                         Steinberg::int32 mode = Steinberg::Vst::kRealtime,
                         Steinberg::int32 sample_size =
                             Steinberg::Vst::kSample32) noexcept {
  Steinberg::Vst::ProcessSetup process_setup{};
  process_setup.processMode = mode;
  process_setup.symbolicSampleSize = sample_size;
  process_setup.maxSamplesPerBlock = max_frames;
  process_setup.sampleRate = sample_rate;
  return instance.processor->setupProcessing(process_setup);
}

void close_instance(SetupInstance& instance) noexcept {
  if (instance.processor != nullptr) {
    static_cast<void>(instance.processor->setProcessing(Steinberg::TBool{0}));
  }
  if (instance.component != nullptr) {
    static_cast<void>(instance.component->setActive(Steinberg::TBool{0}));
    static_cast<void>(instance.component->terminate());
  }
  if (instance.processor != nullptr) {
    instance.processor->release();
  }
  if (instance.component != nullptr) {
    instance.component->release();
  }
  if (instance.factory != nullptr) {
    instance.factory->release();
  }
}

}  // namespace

M3_TEST(vst3_setup_uses_each_exact_host_rate_without_a_rate_control) {
  SetupInstance instance;
  M3_EXPECT_TRUE(open_instance(instance));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }

  constexpr double kRates[]{44100.0, 48000.0, 88200.0, 96000.0,
                            32000.0, 50000.0, 192000.0};
  for (const double rate : kRates) {
    M3_EXPECT_EQ(setup(instance, rate), Steinberg::kResultOk);
    M3_EXPECT_EQ(m3::vst3::prepared_sample_rate_for_test(instance.processor),
                 rate);
    M3_EXPECT_EQ(m3::vst3::prepared_sample_period_for_test(instance.processor),
                 1.0 / rate);
  }

  M3_EXPECT_EQ(m3::parameter_count(), 16U);
  for (std::size_t index = 0; index < m3::parameter_count(); ++index) {
    const m3::ParameterSpec* spec = m3::parameter_spec(index);
    M3_EXPECT_TRUE(spec != nullptr);
    if (spec != nullptr) {
      M3_EXPECT_TRUE(std::strstr(spec->name, "Sample rate") == nullptr);
      M3_EXPECT_TRUE(std::strstr(spec->name, "Resample") == nullptr);
    }
  }
  close_instance(instance);
}

M3_TEST(vst3_setup_rejects_invalid_or_numerically_unsafe_preparation) {
  SetupInstance instance;
  M3_EXPECT_TRUE(open_instance(instance));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  constexpr double kGoodRate = 48000.0;
  M3_EXPECT_EQ(setup(instance, kGoodRate), Steinberg::kResultOk);
  const double before =
      m3::vst3::prepared_sample_rate_for_test(instance.processor);
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double infinity = std::numeric_limits<double>::infinity();
  const double unsafe = std::numeric_limits<double>::min();
  for (const double rate : {0.0, -1.0, nan, infinity, -infinity, unsafe}) {
    M3_EXPECT_TRUE(setup(instance, rate) != Steinberg::kResultOk);
    M3_EXPECT_EQ(m3::vst3::prepared_sample_rate_for_test(instance.processor),
                 before);
  }
  M3_EXPECT_TRUE(setup(instance, kGoodRate, 0) != Steinberg::kResultOk);
  M3_EXPECT_TRUE(setup(instance, kGoodRate, 16385) != Steinberg::kResultOk);
  M3_EXPECT_TRUE(setup(instance, kGoodRate, 512, 99) !=
                 Steinberg::kResultOk);
  M3_EXPECT_TRUE(setup(instance, kGoodRate, 512,
                       Steinberg::Vst::kRealtime, 99) !=
                 Steinberg::kResultOk);

  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  M3_EXPECT_TRUE(setup(instance, 96000.0) != Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::prepared_sample_rate_for_test(instance.processor),
               kGoodRate);
  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  close_instance(instance);
}
