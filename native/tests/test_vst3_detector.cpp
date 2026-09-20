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
#include "vst3_parameter_bridge.hpp"

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
                 std::uint32_t max_samples_per_block = 256U,
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
  setup.maxSamplesPerBlock = max_samples_per_block;
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

void capture_events(const m3::test::FakeVst3EventList& source,
                    std::array<Steinberg::Vst::Event, 4>& captured,
                    std::size_t& count) noexcept {
  for (std::size_t index = 0; index < source.stored_event_count(); ++index) {
    if (count < captured.size()) {
      captured[count++] = source.stored_event(index);
    }
  }
}

void capture_tuner_outputs(m3::test::FakeVst3ParameterChanges& source,
                           double& note, bool& note_seen, double& cents,
                           bool& cents_seen) noexcept {
  for (std::size_t index = 0; index < source.stored_queue_count(); ++index) {
    auto* queue = source.stored_queue(index);
    if (queue == nullptr || queue->stored_point_count() == 0U) {
      continue;
    }
    const m3::ParameterId id = queue->getParameterId();
    if (id != m3::vst3::kTunerNoteParameterId &&
        id != m3::vst3::kTunerCentsParameterId) {
      continue;
    }
    const m3::ParameterSpec* spec = m3::vst3::find_vst3_parameter(id);
    M3_EXPECT_TRUE(spec != nullptr);
    if (spec == nullptr) {
      continue;
    }
    const double plain = m3::normalized_to_plain(
        *spec, queue->stored_point(queue->stored_point_count() - 1U).value);
    if (id == m3::vst3::kTunerNoteParameterId) {
      note = plain;
      note_seen = true;
    } else {
      cents = plain;
      cents_seen = true;
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

M3_TEST(vst3_audio_path_emits_and_releases_a_two_note_chord) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }

  constexpr std::uint32_t kFrames = 256U;
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.15;
  constexpr std::uint8_t kFirstNote = 32U;
  constexpr std::uint8_t kSecondNote = 40U;
  const double first_frequency =
      m3::midi_to_frequency(static_cast<double>(kFirstNote), 440.0);
  const double second_frequency =
      m3::midi_to_frequency(static_cast<double>(kSecondNote), 440.0);
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  std::array<Steinberg::Vst::Event, 4> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;

  for (std::uint32_t block_index = 0; block_index < 96U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double phase = 6.28318530717958647692 *
                           static_cast<double>(absolute_sample + frame) /
                           kSampleRate;
      block.input_left()[frame] = static_cast<float>(
          kAmplitude * (std::sin(phase * first_frequency) +
                        std::sin(phase * second_frequency)));
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
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

  M3_EXPECT_EQ(captured_count, 4U);
  if (captured_count == 4U) {
    M3_EXPECT_EQ(captured[0].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[0].noteOn.pitch, 32);
    M3_EXPECT_EQ(captured[1].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[1].noteOn.pitch, 40);
    M3_EXPECT_EQ(captured[2].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[2].noteOff.pitch, 32);
    M3_EXPECT_EQ(captured[3].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[3].noteOff.pitch, 40);
  }
  close_active(instance);
}

M3_TEST(vst3_audio_path_tracks_a_two_note_chord_at_96khz_512_frames) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance, 512U, 96000.0));
  if (instance.processor == nullptr) {
    close_active(instance);
    return;
  }

  constexpr std::uint32_t kFrames = 512U;
  constexpr double kSampleRate = 96000.0;
  constexpr double kAmplitude = 0.15;
  constexpr std::uint8_t kFirstNote = 32U;
  constexpr std::uint8_t kSecondNote = 40U;
  const double first_frequency =
      m3::midi_to_frequency(static_cast<double>(kFirstNote), 440.0);
  const double second_frequency =
      m3::midi_to_frequency(static_cast<double>(kSecondNote), 440.0);
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  std::array<Steinberg::Vst::Event, 4> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;

  for (std::uint32_t block_index = 0; block_index < 192U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double phase = 6.28318530717958647692 *
                           static_cast<double>(absolute_sample + frame) /
                           kSampleRate;
      block.input_left()[frame] = static_cast<float>(
          kAmplitude * (std::sin(phase * first_frequency) +
                        std::sin(phase * second_frequency)));
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
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

  M3_EXPECT_EQ(captured_count, 4U);
  if (captured_count == 4U) {
    M3_EXPECT_EQ(captured[0].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[0].noteOn.pitch, 32);
    M3_EXPECT_EQ(captured[1].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[1].noteOn.pitch, 40);
    M3_EXPECT_EQ(captured[2].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[2].noteOff.pitch, 32);
    M3_EXPECT_EQ(captured[3].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[3].noteOff.pitch, 40);
  }
  close_active(instance);
}

M3_TEST(vst3_tuner_reports_note_cents_and_no_signal_without_changing_midi) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance, 512U, 96000.0));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_active(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330009U, 0.0),
               Steinberg::kResultTrue);

  constexpr std::uint32_t kFrames = 512U;
  constexpr double kSampleRate = 96000.0;
  constexpr double kMidiNote = 45.23;
  const double frequency = m3::midi_to_frequency(kMidiNote, 440.0);
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges tuner_changes;
  m3::test::FakeVst3ParameterChanges config_changes;
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330005U, 0, 0.75));
  M3_EXPECT_TRUE(config_changes.append_input(0x4D330009U, 0, 0.0));
  std::array<Steinberg::Vst::Event, 4> captured{};
  std::size_t captured_count = 0U;
  std::uint64_t absolute_sample = 0U;
  double tuner_note = -1.0;
  double tuner_cents = -999.0;
  bool note_seen = false;
  bool cents_seen = false;

  for (std::uint32_t block_index = 0; block_index < 192U; ++block_index) {
    block.configure(kFrames, false);
    for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
      const double phase = 6.28318530717958647692 * frequency *
                           static_cast<double>(absolute_sample + frame) /
                           kSampleRate;
      block.input_left()[frame] = static_cast<float>(0.20 * std::sin(phase));
      block.input_right()[frame] = 0.0F;
    }
    block.data().outputEvents = &events;
    block.data().outputParameterChanges = &tuner_changes;
    block.data().inputParameterChanges =
        block_index == 0U ? &config_changes : nullptr;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    capture_tuner_outputs(tuner_changes, tuner_note, note_seen, tuner_cents,
                          cents_seen);
    events.reset();
    tuner_changes.reset();
    absolute_sample += kFrames;
  }

  M3_EXPECT_TRUE(note_seen);
  M3_EXPECT_TRUE(cents_seen);
  M3_EXPECT_NEAR(tuner_note, 45.0, 0.0);
  M3_EXPECT_NEAR(tuner_cents, 23.0, 2.0);

  note_seen = false;
  cents_seen = false;
  for (std::uint32_t block_index = 0; block_index < 48U; ++block_index) {
    block.configure(kFrames, false);
    block.fill_silence();
    block.data().outputEvents = &events;
    block.data().outputParameterChanges = &tuner_changes;
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    capture_events(events, captured, captured_count);
    capture_tuner_outputs(tuner_changes, tuner_note, note_seen, tuner_cents,
                          cents_seen);
    events.reset();
    tuner_changes.reset();
  }

  M3_EXPECT_TRUE(note_seen);
  M3_EXPECT_TRUE(cents_seen);
  M3_EXPECT_NEAR(tuner_note, m3::kTunerNoSignalNote, 0.0);
  M3_EXPECT_NEAR(tuner_cents, 0.0, 0.0);
  M3_EXPECT_EQ(captured_count, 2U);
  if (captured_count == 2U) {
    M3_EXPECT_EQ(captured[0].type, Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(captured[0].noteOn.pitch, 45);
    M3_EXPECT_EQ(captured[1].type, Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(captured[1].noteOff.pitch, 45);
  }
  close_active(instance);
}
