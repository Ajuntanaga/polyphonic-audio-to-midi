#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <type_traits>

#include "fake_vst3_host.hpp"
#include "../plugin/dry_path.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct ActiveInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  m3::test::FakeVst3Host host{};
};

bool open_active(ActiveInstance& instance, Steinberg::int32 sample_size,
                 Steinberg::int32 max_frames = 16384,
                 bool mono = false) noexcept {
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
  if (mono) {
    Steinberg::Vst::SpeakerArrangement input =
        Steinberg::Vst::SpeakerArr::kMono;
    Steinberg::Vst::SpeakerArrangement output =
        Steinberg::Vst::SpeakerArr::kMono;
    if (instance.processor->setBusArrangements(&input, 1, &output, 1) !=
        Steinberg::kResultTrue) {
      return false;
    }
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = sample_size;
  setup.maxSamplesPerBlock = max_frames;
  setup.sampleRate = 48000.0;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_active(ActiveInstance& instance) noexcept {
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
void exercise_dry_modes() noexcept {
  ActiveInstance instance;
  constexpr Steinberg::int32 sample_size =
      std::is_same_v<Sample, Steinberg::Vst::Sample32>
          ? Steinberg::Vst::kSample32
          : Steinberg::Vst::kSample64;
  M3_EXPECT_TRUE(open_active(instance, sample_size));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }
  constexpr std::uint32_t kFrames[]{1, 32, 64, 128, 256, 512, 16384};
  m3::test::FakeVst3ProcessBlock<Sample> block;
  for (const std::uint32_t frames : kFrames) {
    for (const bool in_place : {false, true}) {
      block.configure(frames, in_place);
      block.fill_finite();
      m3::vst3::set_dry_passthrough_for_test(instance.processor, true);
      const std::size_t allocations_before = m3::test::allocation_count();
      const std::size_t deallocations_before = m3::test::deallocation_count();
      M3_EXPECT_EQ(instance.processor->process(block.data()),
                   Steinberg::kResultOk);
      M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
      M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
      for (std::uint32_t frame = 0; frame < frames; ++frame) {
        M3_EXPECT_EQ(block.output_left()[frame],
                     decltype(block)::expected_input_left(frame));
        M3_EXPECT_EQ(block.output_right()[frame],
                     decltype(block)::expected_input_right(frame));
      }

      block.configure(frames, in_place);
      block.fill_finite();
      m3::vst3::set_dry_passthrough_for_test(instance.processor, false);
      M3_EXPECT_EQ(instance.processor->process(block.data()),
                   Steinberg::kResultOk);
      for (std::uint32_t frame = 0; frame < frames; ++frame) {
        M3_EXPECT_EQ(block.output_left()[frame], static_cast<Sample>(0));
        M3_EXPECT_EQ(block.output_right()[frame], static_cast<Sample>(0));
      }
    }
  }
  Steinberg::Vst::ProcessData flush{};
  flush.symbolicSampleSize = sample_size;
  flush.numSamples = 0;
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_active(instance);
}

}  // namespace

M3_TEST(vst3_host_layout_auto_input_is_unity_for_mono_dual_mono_and_one_side) {
  std::array<float, 4> left{{0.25F, -0.5F, 0.75F, -1.0F}};
  std::array<float, 4> right = left;
  std::array<float*, 2> stereo{{left.data(), right.data()}};
  const m3::DryPathResult dual =
      m3::analyze_detector_input(stereo.data(), 2U, 4U);
  M3_EXPECT_NEAR(dual.detector_left_gain, 0.5, 0.0);
  M3_EXPECT_NEAR(dual.detector_right_gain, 0.5, 0.0);
  M3_EXPECT_NEAR(dual.selected_peak, 1.0, 0.0);

  left.fill(0.0F);
  const m3::DryPathResult right_only =
      m3::analyze_detector_input(stereo.data(), 2U, 4U);
  M3_EXPECT_NEAR(right_only.detector_left_gain, 0.0, 0.0);
  M3_EXPECT_NEAR(right_only.detector_right_gain, 1.0, 0.0);
  M3_EXPECT_NEAR(right_only.selected_peak, 1.0, 0.0);

  left = right;
  const m3::DryPathResult flagged_left =
      m3::analyze_detector_input(stereo.data(), 2U, 4U, 1U);
  M3_EXPECT_NEAR(flagged_left.detector_left_gain, 0.0, 0.0);
  M3_EXPECT_NEAR(flagged_left.detector_right_gain, 1.0, 0.0);

  std::array<float*, 1> mono{{left.data()}};
  const m3::DryPathResult mono_analysis =
      m3::analyze_detector_input(mono.data(), 1U, 4U);
  M3_EXPECT_NEAR(mono_analysis.detector_left_gain, 1.0, 0.0);
  M3_EXPECT_NEAR(mono_analysis.detector_right_gain, 0.0, 0.0);
  M3_EXPECT_NEAR(mono_analysis.selected_peak, 1.0, 0.0);
}

M3_TEST(vst3_negotiated_mono_processes_and_passes_dry_audio_at_unity) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance, Steinberg::Vst::kSample32, 128, true));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }
  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(64, false);
  block.fill_finite();
  block.input_bus().numChannels = 1;
  block.output_bus().numChannels = 1;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_TRUE(m3::vst3::status_for_test(instance.processor) !=
                 m3::Status::unsupported_layout);
  for (std::uint32_t frame = 0U; frame < 64U; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
  }
  close_active(instance);
}

M3_TEST(vst3_dry_path_is_exact_for_float32_float64_and_all_block_sizes) {
  exercise_dry_modes<Steinberg::Vst::Sample32>();
  exercise_dry_modes<Steinberg::Vst::Sample64>();
}

M3_TEST(vst3_nonfinite_null_shared_and_invalid_layouts_fail_closed_safely) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance, Steinberg::Vst::kSample64, 512));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }
  m3::test::FakeVst3ProcessBlock<Steinberg::Vst::Sample64> block;
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  block.configure(32, false);
  block.fill_finite();
  block.input_left()[3] = std::numeric_limits<double>::infinity();
  block.input_right()[7] = std::numeric_limits<double>::quiet_NaN();
  m3::vst3::set_dry_passthrough_for_test(instance.processor, true);
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(block.output_left()[3], 0.0);
  M3_EXPECT_EQ(block.output_right()[7], 0.0);
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::invalid_input_or_state);

  block.configure(32, false);
  block.fill_finite();
  block.data().numInputs = 0;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0);
  }
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::unsupported_layout);

  block.configure(32, false);
  block.fill_finite();
  block.data().inputs = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0);
  }

  block.configure(32, false);
  block.fill_finite();
  block.input_channel(0) = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0);
  }

  block.configure(32, false);
  block.fill_finite();
  block.share_input_channels();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0);
  }

  block.configure(32, false);
  block.fill_finite();
  block.output_channel(1) = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
  }

  block.configure(32, false);
  block.fill_finite();
  block.share_output_channels();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0);
  }

  block.configure(32, false);
  block.fill_finite();
  block.data().outputs = nullptr;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);

  block.configure(32, false);
  block.fill_finite();
  block.data().symbolicSampleSize = 9;
  M3_EXPECT_TRUE(instance.processor->process(block.data()) !=
                 Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_active(instance);
}
