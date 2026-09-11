#include <cstdint>
#include <limits>
#include <type_traits>

#include "fake_vst3_host.hpp"
#include "m3/parameter_contract.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct ProcessInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  m3::test::FakeVst3Host host{};
};

bool open_instance(ProcessInstance& instance, Steinberg::int32 mode,
                   Steinberg::int32 sample_size,
                   Steinberg::int32 max_frames = 16384,
                   double sample_rate = 48000.0) noexcept {
  instance.factory = GetPluginFactory();
  if (instance.factory == nullptr) {
    return false;
  }
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  if (instance.factory->createInstance(
          class_id, Steinberg::Vst::IComponent::iid,
          reinterpret_cast<void**>(&instance.component)) !=
          Steinberg::kResultOk ||
      instance.component == nullptr ||
      instance.component->initialize(&instance.host) != Steinberg::kResultOk ||
      instance.component->queryInterface(
          Steinberg::Vst::IAudioProcessor::iid,
          reinterpret_cast<void**>(&instance.processor)) !=
          Steinberg::kResultOk ||
      instance.processor == nullptr) {
    return false;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = mode;
  setup.symbolicSampleSize = sample_size;
  setup.maxSamplesPerBlock = max_frames;
  setup.sampleRate = sample_rate;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_instance(ProcessInstance& instance) noexcept {
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

template <typename Sample>
void exercise_mode_and_phase(Steinberg::int32 mode) noexcept {
  constexpr Steinberg::int32 kSampleSize =
      std::is_same_v<Sample, Steinberg::Vst::Sample32>
          ? Steinberg::Vst::kSample32
          : Steinberg::Vst::kSample64;
  ProcessInstance instance;
  M3_EXPECT_TRUE(open_instance(instance, mode, kSampleSize));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  constexpr std::uint32_t kFrames[]{0, 1, 32, 64, 128,
                                    256, 512, 16384};
  std::uint64_t total = 0;
  m3::test::FakeVst3ProcessBlock<Sample> block;
  for (const std::uint32_t frames : kFrames) {
    if (frames == 0U) {
      Steinberg::Vst::ProcessData flush{};
      flush.processMode = mode;
      flush.symbolicSampleSize = kSampleSize;
      M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
      continue;
    }
    block.configure(frames, (frames & 1U) != 0U);
    block.fill_finite();
    block.data().processMode = mode;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    total += frames;
    M3_EXPECT_EQ(m3::vst3::decision_tick_count_for_test(instance.processor),
                 total / 64U);
    M3_EXPECT_EQ(m3::vst3::decision_phase_for_test(instance.processor),
                 total % 64U);
  }
  M3_EXPECT_TRUE(m3::vst3::decision_tick_count_for_test(instance.processor) >
                 1U);
  close_instance(instance);
}

}  // namespace

M3_TEST(vst3_process_modes_formats_blocks_and_phase_are_host_independent) {
  for (const Steinberg::int32 mode : {Steinberg::Vst::kRealtime,
                                      Steinberg::Vst::kPrefetch,
                                      Steinberg::Vst::kOffline}) {
    exercise_mode_and_phase<Steinberg::Vst::Sample32>(mode);
    exercise_mode_and_phase<Steinberg::Vst::Sample64>(mode);
  }
}

M3_TEST(vst3_realtime_and_prefetch_switch_without_reconfiguration) {
  constexpr Steinberg::int32 kModePairs[][2]{
      {Steinberg::Vst::kRealtime, Steinberg::Vst::kPrefetch},
      {Steinberg::Vst::kPrefetch, Steinberg::Vst::kRealtime},
  };
  for (const auto& pair : kModePairs) {
    ProcessInstance instance;
    M3_EXPECT_TRUE(open_instance(instance, pair[0],
                                 Steinberg::Vst::kSample32, 128));
    if (instance.processor == nullptr) {
      close_instance(instance);
      continue;
    }
    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(128, false);
    block.fill_finite();
    block.data().processMode = pair[1];
    const Steinberg::tresult result = instance.processor->process(block.data());
    M3_EXPECT_EQ(result, Steinberg::kResultOk);
    if (result == Steinberg::kResultOk) {
      for (std::uint32_t frame = 0; frame < 128U; ++frame) {
        M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
        M3_EXPECT_EQ(block.output_right()[frame], block.input_right()[frame]);
      }
    }
    close_instance(instance);
  }

  ProcessInstance offline_instance;
  M3_EXPECT_TRUE(open_instance(offline_instance, Steinberg::Vst::kOffline,
                               Steinberg::Vst::kSample32, 128));
  if (offline_instance.processor != nullptr) {
    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(128, false);
    block.fill_finite();
    block.data().processMode = Steinberg::Vst::kRealtime;
    M3_EXPECT_TRUE(offline_instance.processor->process(block.data()) !=
                   Steinberg::kResultOk);
  }
  close_instance(offline_instance);
}

M3_TEST(vst3_process_parameter_flush_silence_alias_and_dirty_outputs_are_safe) {
  ProcessInstance instance;
  M3_EXPECT_TRUE(open_instance(instance, Steinberg::Vst::kRealtime,
                               Steinberg::Vst::kSample32, 512));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }

  m3::test::FakeVst3ParameterChanges dry_changes;
  M3_EXPECT_TRUE(dry_changes.append_input(0x4D33000FU, 0, 0.0));
  Steinberg::Vst::ProcessData flush{};
  flush.processMode = Steinberg::Vst::kRealtime;
  flush.symbolicSampleSize = Steinberg::Vst::kSample32;
  flush.numSamples = 0;
  flush.inputParameterChanges = &dry_changes;
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);

  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(32, true);
  block.fill_finite();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32U; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0F);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0F);
  }

  m3::vst3::set_dry_passthrough_for_test(instance.processor, true);
  block.configure(32, false);
  block.fill_finite();
  block.input_bus().silenceFlags = 3U;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(block.output_bus().silenceFlags, 3U);
  for (std::uint32_t frame = 0; frame < 32U; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0F);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0F);
  }

  block.configure(32, false);
  block.fill_finite();
  block.data().outputEvents = nullptr;
  block.data().outputParameterChanges = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);

  m3::test::FakeVst3ParameterChanges rejected;
  rejected.reject_output_points(true);
  block.configure(32, false);
  block.fill_finite();
  block.input_left()[0] = std::numeric_limits<float>::infinity();
  block.data().outputParameterChanges = &rejected;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::invalid_input_or_state);

  m3::test::FakeVst3ParameterChanges accepted;
  block.configure(32, false);
  block.fill_finite();
  block.data().outputParameterChanges = &accepted;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(accepted.stored_queue_count(), 1U);
  if (accepted.stored_queue_count() == 1U) {
    M3_EXPECT_EQ(accepted.stored_queue(0)->getParameterId(),
                 m3::kStatusParameterId);
  }
  close_instance(instance);
}

M3_TEST(vst3_process_rejects_bad_call_contracts_and_contains_bad_layouts) {
  ProcessInstance instance;
  M3_EXPECT_TRUE(open_instance(instance, Steinberg::Vst::kRealtime,
                               Steinberg::Vst::kSample64, 512));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  m3::test::FakeVst3ProcessBlock<double> block;

  block.configure(32, false);
  block.fill_finite();
  block.data().processMode = Steinberg::Vst::kOffline;
  M3_EXPECT_TRUE(instance.processor->process(block.data()) !=
                 Steinberg::kResultOk);

  block.configure(32, false);
  block.fill_finite();
  block.data().symbolicSampleSize = Steinberg::Vst::kSample32;
  M3_EXPECT_TRUE(instance.processor->process(block.data()) !=
                 Steinberg::kResultOk);

  block.configure(513, false);
  block.fill_finite();
  M3_EXPECT_TRUE(instance.processor->process(block.data()) !=
                 Steinberg::kResultOk);

  block.configure(32, false);
  block.fill_finite();
  block.data().numInputs = 2;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::unsupported_layout);

  block.configure(32, false);
  block.fill_finite();
  block.input_bus().numChannels = 1;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);

  block.configure(32, false);
  block.fill_finite();
  block.data().inputs = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);

  block.configure(32, false);
  block.fill_finite();
  block.share_output_channels();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  close_instance(instance);
}

M3_TEST(vst3_process_and_processing_transitions_are_allocation_free_100000) {
  ProcessInstance instance;
  M3_EXPECT_TRUE(open_instance(instance, Steinberg::Vst::kRealtime,
                               Steinberg::Vst::kSample32, 1));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(1, true);
  block.fill_silence();
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
  }
  for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
    M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
  }
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_instance(instance);
}
