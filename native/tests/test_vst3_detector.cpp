#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "fake_vst3_host.hpp"
#include "m3/pitch_math.hpp"
#include "m3/tuner_telemetry.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
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

template <std::size_t Capacity>
void capture_events(const m3::test::FakeVst3EventList& source,
                    std::array<Steinberg::Vst::Event, Capacity>& captured,
                    std::size_t& count) noexcept {
  for (std::size_t index = 0; index < source.stored_event_count(); ++index) {
    if (count < captured.size()) {
      captured[count++] = source.stored_event(index);
    }
  }
}

bool is_note_event_for(const Steinberg::Vst::Event& event,
                       Steinberg::Vst::Event::EventTypes type,
                       std::int16_t note) noexcept {
  if (event.type != type) {
    return false;
  }
  return type == Steinberg::Vst::Event::kNoteOnEvent
             ? event.noteOn.pitch == note
             : type == Steinberg::Vst::Event::kNoteOffEvent &&
                   event.noteOff.pitch == note;
}

}  // namespace

M3_TEST(vst3_audio_path_keeps_one_low_string_tone_single_at_default_polyphony) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }
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

M3_TEST(vst3_audio_path_tracks_two_chord_voices_when_max_polyphony_is_two) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_active(instance);
    return;
  }

  constexpr std::uint32_t kFrames = 256U;
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.16;
  constexpr std::uint8_t kLowNote = 40U;
  constexpr std::uint8_t kHighNote = 47U;
  constexpr double kTwoVoicesNormalized = 1.0 / 7.0;
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330009U,
                                                        kTwoVoicesNormalized),
               Steinberg::kResultTrue);

  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges config_changes;
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330005U, 0, 0.75));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330009U, 0,
                                              kTwoVoicesNormalized));
  std::array<Steinberg::Vst::Event, 8> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;
  const double low_frequency =
      m3::midi_to_frequency(static_cast<double>(kLowNote), 440.0);
  const double high_frequency =
      m3::midi_to_frequency(static_cast<double>(kHighNote), 440.0);

  for (std::uint32_t block_index = 0; block_index < 128U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double time =
          static_cast<double>(absolute_sample + frame) / kSampleRate;
      block.input_left()[frame] = static_cast<float>(
          kAmplitude * (std::sin(6.28318530717958647692 * low_frequency * time) +
                        std::sin(6.28318530717958647692 * high_frequency * time)));
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
  m3::TunerSnapshot tracking_snapshot;
  M3_EXPECT_TRUE(
      m3::vst3::read_tuner_snapshot_for_test(instance.processor,
                                              tracking_snapshot));
  M3_EXPECT_EQ(tracking_snapshot.state, m3::TunerFrameState::tracking);
  M3_EXPECT_EQ(tracking_snapshot.voice_count, 2U);
  M3_EXPECT_EQ(tracking_snapshot.max_polyphony, 2U);
  if (tracking_snapshot.voice_count == 2U) {
    M3_EXPECT_EQ(tracking_snapshot.voices[0].midi_note, kLowNote);
    M3_EXPECT_EQ(tracking_snapshot.voices[1].midi_note, kHighNote);
    M3_EXPECT_TRUE(tracking_snapshot.voices[0].cents_valid);
    M3_EXPECT_TRUE(tracking_snapshot.voices[1].cents_valid);
  }
  for (std::uint32_t block_index = 0; block_index < 64U; ++block_index) {
    block.configure(kFrames, false);
    block.fill_silence();
    block.data().outputEvents = &events;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    events.reset();
  }
  m3::TunerSnapshot released_snapshot;
  M3_EXPECT_TRUE(
      m3::vst3::read_tuner_snapshot_for_test(instance.processor,
                                              released_snapshot));
  M3_EXPECT_EQ(released_snapshot.state, m3::TunerFrameState::no_signal);
  M3_EXPECT_EQ(released_snapshot.voice_count, 0U);

  std::uint32_t low_on{};
  std::uint32_t high_on{};
  std::uint32_t low_off{};
  std::uint32_t high_off{};
  std::uint32_t unexpected_on{};
  for (std::size_t index = 0U; index < captured_count; ++index) {
    const Steinberg::Vst::Event& event = captured[index];
    low_on += is_note_event_for(event, Steinberg::Vst::Event::kNoteOnEvent,
                                static_cast<std::int16_t>(kLowNote))
                  ? 1U
                  : 0U;
    high_on += is_note_event_for(event, Steinberg::Vst::Event::kNoteOnEvent,
                                 static_cast<std::int16_t>(kHighNote))
                   ? 1U
                   : 0U;
    low_off += is_note_event_for(event, Steinberg::Vst::Event::kNoteOffEvent,
                                 static_cast<std::int16_t>(kLowNote))
                   ? 1U
                   : 0U;
    high_off += is_note_event_for(event, Steinberg::Vst::Event::kNoteOffEvent,
                                  static_cast<std::int16_t>(kHighNote))
                    ? 1U
                    : 0U;
    if (event.type == Steinberg::Vst::Event::kNoteOnEvent &&
        event.noteOn.pitch != static_cast<std::int16_t>(kLowNote) &&
        event.noteOn.pitch != static_cast<std::int16_t>(kHighNote)) {
      ++unexpected_on;
    }
  }
  M3_EXPECT_EQ(low_on, 1U);
  M3_EXPECT_EQ(high_on, 1U);
  M3_EXPECT_EQ(low_off, 1U);
  M3_EXPECT_EQ(high_off, 1U);
  M3_EXPECT_EQ(unexpected_on, 0U);
  close_active(instance);
}
