#include <algorithm>
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

bool open_active(ActiveInstance& instance,
                 Steinberg::int32 max_frames = 256,
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
  setup.maxSamplesPerBlock = max_frames;
  setup.sampleRate = sample_rate;
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

M3_TEST(vst3_panic_discards_detector_voice_state_before_midi_recovery) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_active(instance);
    return;
  }

  constexpr std::uint32_t kFrames = 256U;
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 32U;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges parameters;
  M3_EXPECT_TRUE(parameters.append_input(0x4D330005U, 0, 0.75));
  std::uint64_t absolute_sample = 0U;
  std::uint32_t note_on_count = 0U;
  std::uint32_t note_off_count = 0U;

  const auto feed_tone = [&](bool apply_parameters) noexcept {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0U; frame < kFrames; ++frame) {
      const double time =
          static_cast<double>(absolute_sample + frame) / kSampleRate;
      block.input_left()[frame] = static_cast<float>(
          0.20 * std::sin(6.28318530717958647692 * frequency * time));
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
    block.data().inputParameterChanges = apply_parameters ? &parameters : nullptr;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    for (std::size_t index = 0U; index < events.stored_event_count(); ++index) {
      const Steinberg::Vst::Event& event = events.stored_event(index);
      note_on_count +=
          is_note_event_for(event, Steinberg::Vst::Event::kNoteOnEvent, kNote)
              ? 1U
              : 0U;
      note_off_count +=
          is_note_event_for(event, Steinberg::Vst::Event::kNoteOffEvent, kNote)
              ? 1U
              : 0U;
    }
    events.reset();
    absolute_sample += kFrames;
  };

  for (std::uint32_t block_index = 0U; block_index < 96U; ++block_index) {
    feed_tone(block_index == 0U);
  }
  M3_EXPECT_EQ(note_on_count, 1U);
  M3_EXPECT_TRUE(
      m3::vst3::generated_note_active_for_test(instance.processor, kNote));

  M3_EXPECT_EQ(instance.controller->setParamNormalized(
                   m3::kPanicParameterId, 1.0),
               Steinberg::kResultTrue);
  for (std::uint32_t block_index = 0U; block_index < 96U; ++block_index) {
    block.configure(kFrames, false);
    block.fill_silence();
    block.data().inputParameterChanges = nullptr;
    block.data().outputEvents = &events;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    for (std::size_t index = 0U; index < events.stored_event_count(); ++index) {
      note_off_count += is_note_event_for(
                            events.stored_event(index),
                            Steinberg::Vst::Event::kNoteOffEvent, kNote)
                            ? 1U
                            : 0U;
    }
    events.reset();
    M3_EXPECT_TRUE(m3::vst3::status_for_test(instance.processor) !=
                   m3::Status::midi_output_blocked);
  }
  M3_EXPECT_EQ(note_off_count, 1U);
  M3_EXPECT_FALSE(
      m3::vst3::generated_note_active_for_test(instance.processor, kNote));

  for (std::uint32_t block_index = 0U; block_index < 96U; ++block_index) {
    feed_tone(false);
  }
  M3_EXPECT_EQ(note_on_count, 2U);
  M3_EXPECT_TRUE(
      m3::vst3::generated_note_active_for_test(instance.processor, kNote));
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

M3_TEST(vst3_detector_is_invariant_across_host_rates_and_block_partitions) {
  constexpr std::array<double, 4> kSampleRates{
      44100.0, 48000.0, 88200.0, 96000.0};
  constexpr std::array<std::uint32_t, 17> kBlockSizes{
      16U,  24U,  32U,   48U,   64U,   96U,   128U, 192U, 256U,
      384U, 512U, 768U,  1000U, 1024U, 1536U, 2048U, 4096U};
  constexpr std::uint8_t kNote = 40U;
  constexpr double kAmplitude = 0.30;
  constexpr double kTrimNormalized = 12.4 / 48.0;  // -11.6 dB

  for (const double sample_rate : kSampleRates) {
    std::uint64_t baseline_note_on_sample = 0U;
    std::uint64_t baseline_note_off_sample = 0U;
    bool baseline_set = false;
    for (const std::uint32_t block_size : kBlockSizes) {
      ActiveInstance instance;
      M3_EXPECT_TRUE(open_active(
          instance, static_cast<Steinberg::int32>(block_size), sample_rate));
      if (instance.processor == nullptr) {
        close_active(instance);
        continue;
      }

      const double frequency = m3::midi_to_frequency(kNote, 440.0);
      const std::uint64_t tone_samples =
          static_cast<std::uint64_t>(std::ceil(sample_rate * 0.18));
      const std::uint64_t release_samples =
          static_cast<std::uint64_t>(std::ceil(sample_rate * 0.30));
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      m3::test::FakeVst3ParameterChanges calibration;
      M3_EXPECT_TRUE(
          calibration.append_input(0x4D330004U, 0, kTrimNormalized));
      M3_EXPECT_TRUE(calibration.append_input(0x4D330005U, 0, 0.69));
      M3_EXPECT_TRUE(calibration.append_input(0x4D330006U, 0, 0.81));

      std::uint32_t note_on_count = 0U;
      std::uint32_t note_off_count = 0U;
      std::uint32_t unexpected_note_on_count = 0U;
      std::uint64_t note_on_sample = 0U;
      std::uint64_t note_off_sample = 0U;
      std::uint64_t absolute_sample = 0U;
      bool first_block = true;
      const auto capture = [&](std::uint32_t frames,
                               std::uint64_t block_start) noexcept {
        for (std::size_t index = 0U; index < events.stored_event_count();
             ++index) {
          const Steinberg::Vst::Event& event = events.stored_event(index);
          M3_EXPECT_TRUE(event.sampleOffset >= 0);
          M3_EXPECT_TRUE(
              static_cast<std::uint32_t>(event.sampleOffset) < frames);
          const bool note_on =
              is_note_event_for(event, Steinberg::Vst::Event::kNoteOnEvent,
                                static_cast<std::int16_t>(kNote));
          const bool note_off =
              is_note_event_for(event, Steinberg::Vst::Event::kNoteOffEvent,
                                static_cast<std::int16_t>(kNote));
          if (note_on && note_on_count == 0U) {
            note_on_sample = block_start +
                             static_cast<std::uint32_t>(event.sampleOffset);
          }
          if (note_off && note_off_count == 0U) {
            note_off_sample = block_start +
                              static_cast<std::uint32_t>(event.sampleOffset);
          }
          note_on_count += note_on ? 1U : 0U;
          note_off_count += note_off ? 1U : 0U;
          unexpected_note_on_count +=
              event.type == Steinberg::Vst::Event::kNoteOnEvent &&
                      event.noteOn.pitch != static_cast<std::int16_t>(kNote)
                  ? 1U
                  : 0U;
        }
        events.reset();
      };

      while (absolute_sample < tone_samples) {
        const std::uint32_t frames = static_cast<std::uint32_t>(std::min<
            std::uint64_t>(block_size, tone_samples - absolute_sample));
        block.configure(frames, false);
        for (std::uint32_t frame = 0U; frame < frames; ++frame) {
          const double time =
              static_cast<double>(absolute_sample + frame) / sample_rate;
          block.input_left()[frame] = static_cast<float>(
              kAmplitude * std::sin(6.28318530717958647692 * frequency * time));
          block.input_right()[frame] = 0.0F;
        }
        block.data().outputEvents = &events;
        block.data().inputParameterChanges = first_block ? &calibration : nullptr;
        M3_EXPECT_EQ(instance.processor->process(block.data()),
                     Steinberg::kResultOk);
        for (std::uint32_t frame = 0U; frame < frames; ++frame) {
          M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
          M3_EXPECT_EQ(block.output_right()[frame], 0.0F);
        }
        capture(frames, absolute_sample);
        first_block = false;
        absolute_sample += frames;
      }

      std::uint64_t released = 0U;
      while (released < release_samples) {
        const std::uint32_t frames = static_cast<std::uint32_t>(std::min<
            std::uint64_t>(block_size, release_samples - released));
        block.configure(frames, false);
        block.fill_silence();
        block.data().outputEvents = &events;
        M3_EXPECT_EQ(instance.processor->process(block.data()),
                     Steinberg::kResultOk);
        for (std::uint32_t frame = 0U; frame < frames; ++frame) {
          M3_EXPECT_EQ(block.output_left()[frame], 0.0F);
          M3_EXPECT_EQ(block.output_right()[frame], 0.0F);
        }
        capture(frames, tone_samples + released);
        released += frames;
      }

      M3_EXPECT_EQ(note_on_count, 1U);
      M3_EXPECT_EQ(note_off_count, 1U);
      M3_EXPECT_EQ(unexpected_note_on_count, 0U);
      if (!baseline_set) {
        baseline_note_on_sample = note_on_sample;
        baseline_note_off_sample = note_off_sample;
        baseline_set = true;
      } else {
        M3_EXPECT_EQ(note_on_sample, baseline_note_on_sample);
        M3_EXPECT_EQ(note_off_sample, baseline_note_off_sample);
      }
      close_active(instance);
    }
  }
}
