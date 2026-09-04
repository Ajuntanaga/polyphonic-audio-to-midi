#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "fake_vst3_host.hpp"
#include "m3/pitch_math.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct ActiveInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  Steinberg::Vst::IEditController* controller{};
  m3::test::FakeVst3Host host{};
};

bool open_active(ActiveInstance& instance) noexcept {
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
      instance.processor == nullptr ||
      instance.component->queryInterface(
          Steinberg::Vst::IEditController::iid,
          reinterpret_cast<void**>(&instance.controller)) !=
          Steinberg::kResultOk ||
      instance.controller == nullptr) {
    return false;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 256;
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
  if (instance.controller != nullptr) {
    instance.controller->release();
  }
  if (instance.component != nullptr) {
    instance.component->release();
  }
  if (instance.factory != nullptr) {
    instance.factory->release();
  }
}

void capture_events(const m3::test::FakeVst3EventList& source,
                    std::array<Steinberg::Vst::Event, 4>& captured,
                    std::size_t& count) noexcept {
  for (std::size_t index = 0; index < source.stored_event_count(); ++index) {
    if (count < captured.size()) {
      captured[count++] = source.stored_event(index);
    }
  }
}

}  // namespace

M3_TEST(vst3_audio_path_emits_low_string_note_and_release_from_input_signal) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330009U, 0.0),
               Steinberg::kResultTrue);

  constexpr std::uint32_t kFrames = 256U;
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  constexpr std::uint8_t kNote = 32U;
  const double frequency =
      m3::midi_to_frequency(static_cast<double>(kNote), 440.0);
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges config_changes;
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330005U, 0, 0.75));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330009U, 0, 0.0));
  std::array<Steinberg::Vst::Event, 4> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;

  for (std::uint32_t block_index = 0; block_index < 96U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double phase = kAmplitude * std::sin(
          6.28318530717958647692 * frequency *
          static_cast<double>(absolute_sample + frame) / kSampleRate);
      block.input_left()[frame] = static_cast<float>(phase);
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
    block.data().inputParameterChanges =
        block_index == 0U ? &config_changes : nullptr;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    events.reset();
    absolute_sample += kFrames;
  }
  for (std::uint32_t block_index = 0; block_index < 48U; ++block_index) {
    block.configure(kFrames, false);
    block.fill_silence();
    block.data().outputEvents = &events;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    events.reset();
  }

  M3_EXPECT_EQ(captured_count, 2U);
  if (captured_count == 2U) {
    M3_EXPECT_EQ(captured[0].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[0].noteOn.pitch, 32);
    M3_EXPECT_EQ(captured[1].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[1].noteOff.pitch, 32);
  }
  close_active(instance);
}

M3_TEST(vst3_audio_path_tracks_the_highest_open_string_with_profile_range) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_active(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330007U,
                                                        0.095238095238),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330008U,
                                                        0.428571428571),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330009U, 0.0),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D33000AU,
                                                        0.333333333333),
               Steinberg::kResultTrue);

  constexpr std::uint32_t kFrames = 256U;
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  constexpr std::uint8_t kNote = 60U;
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges config_changes;
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330005U, 0, 0.75));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330007U, 0,
                                              0.095238095238));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330008U, 0,
                                              0.428571428571));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330009U, 0, 0.0));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D33000AU, 0,
                                              0.333333333333));
  std::array<Steinberg::Vst::Event, 4> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;
  const double frequency =
      m3::midi_to_frequency(static_cast<double>(kNote), 440.0);

  for (std::uint32_t block_index = 0; block_index < 96U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double phase = kAmplitude * std::sin(
          6.28318530717958647692 * frequency *
          static_cast<double>(absolute_sample + frame) / kSampleRate);
      block.input_left()[frame] = static_cast<float>(phase);
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
    block.data().inputParameterChanges =
        block_index == 0U ? &config_changes : nullptr;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    events.reset();
    absolute_sample += kFrames;
  }
  for (std::uint32_t block_index = 0; block_index < 48U; ++block_index) {
    block.configure(kFrames, false);
    block.fill_silence();
    block.data().outputEvents = &events;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    events.reset();
  }

  M3_EXPECT_EQ(captured_count, 2U);
  if (captured_count == 2U) {
    M3_EXPECT_EQ(captured[0].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[0].noteOn.pitch, 60);
    M3_EXPECT_EQ(captured[1].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[1].noteOff.pitch, 60);
  }
  close_active(instance);
}
