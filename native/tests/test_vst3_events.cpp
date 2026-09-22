#include <cstddef>
#include <cstdint>
#include <limits>

#include "fake_vst3_host.hpp"
#include "m3/generated_note_ledger.hpp"
#include "m3/parameter_contract.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_event_sink.hpp"
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
                 Steinberg::int32 max_frames = 192) noexcept {
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

m3::VoiceTransition transition(std::uint32_t offset,
                               m3::TransitionKind kind,
                               std::uint8_t note,
                               std::uint8_t velocity,
                               std::uint32_t sequence) noexcept {
  return m3::VoiceTransition{offset, kind, note, velocity, sequence};
}

void expect_common_event(const Steinberg::Vst::Event& event,
                         Steinberg::int32 offset) noexcept {
  M3_EXPECT_EQ(event.busIndex, 0);
  M3_EXPECT_EQ(event.sampleOffset, offset);
  M3_EXPECT_EQ(event.ppqPosition, 0.0);
  M3_EXPECT_EQ(event.flags, 0U);
}

void expect_dry(m3::test::FakeVst3ProcessBlock<float>& block,
                std::uint32_t frames) noexcept {
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame],
                 m3::test::FakeVst3ProcessBlock<float>::expected_input_left(
                     frame));
    M3_EXPECT_EQ(block.output_right()[frame],
                 m3::test::FakeVst3ProcessBlock<float>::expected_input_right(
                     frame));
  }
}

bool queue_note(ActiveInstance& instance,
                const m3::VoiceTransition& event,
                std::uint32_t frames) noexcept {
  return m3::vst3::queue_generated_note_for_test(instance.processor, event,
                                                  frames);
}

void begin_notes(ActiveInstance& instance) noexcept {
  m3::vst3::begin_generated_note_block_for_test(instance.processor);
}

}  // namespace

M3_TEST(vst3_event_sink_encodes_exact_notes_and_rejects_invalid_values) {
  constexpr std::uint8_t kPitches[]{0, 32, 60, 84, 127};
  constexpr std::uint8_t kChannels[]{1, 16};
  constexpr std::uint8_t kVelocities[]{1, 64, 127};
  constexpr std::uint32_t kFrames = 512;
  constexpr std::uint32_t kOffsets[]{0, kFrames - 1U};
  m3::test::FakeVst3EventList events;

  for (const std::uint8_t pitch : kPitches) {
    for (const std::uint8_t channel : kChannels) {
      for (const std::uint8_t velocity : kVelocities) {
        for (const std::uint32_t offset : kOffsets) {
          events.reset();
          m3::vst3::Vst3EventSinkContext context{&events};
          const m3::VoiceTransition note_on = transition(
              offset, m3::TransitionKind::note_on, pitch, velocity, 9);
          M3_EXPECT_TRUE(
              m3::vst3::push_vst3_note(&context, note_on, channel));
          M3_EXPECT_EQ(events.stored_event_count(), 1U);
          const Steinberg::Vst::Event& encoded_on = events.stored_event(0);
          expect_common_event(encoded_on,
                              static_cast<Steinberg::int32>(offset));
          M3_EXPECT_EQ(encoded_on.type,
                       Steinberg::Vst::Event::kNoteOnEvent);
          M3_EXPECT_EQ(encoded_on.noteOn.channel,
                       static_cast<Steinberg::int16>(channel - 1U));
          M3_EXPECT_EQ(encoded_on.noteOn.pitch,
                       static_cast<Steinberg::int16>(pitch));
          M3_EXPECT_EQ(encoded_on.noteOn.tuning, 0.0F);
          M3_EXPECT_EQ(encoded_on.noteOn.velocity,
                       static_cast<float>(velocity) / 127.0F);
          M3_EXPECT_EQ(encoded_on.noteOn.length, 0);
          M3_EXPECT_EQ(encoded_on.noteOn.noteId,
                       -1000 - static_cast<Steinberg::int32>(pitch));

          events.reset();
          const m3::VoiceTransition note_off = transition(
              offset, m3::TransitionKind::note_off, pitch, 0, 10);
          M3_EXPECT_TRUE(
              m3::vst3::push_vst3_note(&context, note_off, channel));
          M3_EXPECT_EQ(events.stored_event_count(), 1U);
          const Steinberg::Vst::Event& encoded_off = events.stored_event(0);
          expect_common_event(encoded_off,
                              static_cast<Steinberg::int32>(offset));
          M3_EXPECT_EQ(encoded_off.type,
                       Steinberg::Vst::Event::kNoteOffEvent);
          M3_EXPECT_EQ(encoded_off.noteOff.channel,
                       static_cast<Steinberg::int16>(channel - 1U));
          M3_EXPECT_EQ(encoded_off.noteOff.pitch,
                       static_cast<Steinberg::int16>(pitch));
          M3_EXPECT_EQ(encoded_off.noteOff.tuning, 0.0F);
          M3_EXPECT_EQ(encoded_off.noteOff.velocity, 0.0F);
          M3_EXPECT_EQ(encoded_off.noteOff.noteId,
                       -1000 - static_cast<Steinberg::int32>(pitch));
        }
      }
    }
  }

  m3::vst3::Vst3EventSinkContext context{&events};
  const m3::VoiceTransition valid =
      transition(0, m3::TransitionKind::note_on, 60, 100, 1);
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(nullptr, valid, 1U));
  context.events = nullptr;
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, valid, 1U));
  context.events = &events;
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, valid, 0U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, valid, 17U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(0, static_cast<m3::TransitionKind>(2), 60, 100, 1),
      1U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(0, m3::TransitionKind::note_on, 255, 100, 1), 1U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(0, m3::TransitionKind::note_on, 60, 0, 1), 1U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(0, m3::TransitionKind::note_on, 60, 128, 1), 1U));
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(0, m3::TransitionKind::note_off, 60, 1, 1), 1U));
  const std::uint32_t excessive_offset =
      static_cast<std::uint32_t>(std::numeric_limits<Steinberg::int32>::max()) +
      1U;
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(
      &context, transition(excessive_offset, m3::TransitionKind::note_on, 60,
                           100, 1), 1U));
  events.reset();
  events.reject_attempt(0);
  M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, valid, 1U));
  M3_EXPECT_EQ(events.stored_event_count(), 0U);

  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(kFrames));
  ledger.begin_block();
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(kFrames, m3::TransitionKind::note_on, 60, 100, 1), kFrames));
}

M3_TEST(vst3_component_orders_generated_events_and_never_reads_input_events) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr || instance.component == nullptr) {
    close_active(instance);
    return;
  }
  M3_EXPECT_EQ(instance.component->getBusCount(Steinberg::Vst::kEvent,
                                               Steinberg::Vst::kInput),
               0);
  const m3::ParameterSpec* channel_spec = m3::parameter_spec(12);
  M3_EXPECT_TRUE(channel_spec != nullptr);
  if (channel_spec != nullptr) {
    M3_EXPECT_EQ(instance.controller->setParamNormalized(channel_spec->id, 1.0),
                 Steinberg::kResultTrue);
  }

  constexpr std::uint32_t kFrames = 192;
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList input_events;
  m3::test::FakeVst3EventList output_events;
  Steinberg::Vst::Event ignored_input{};
  ignored_input.type = Steinberg::Vst::Event::kLegacyMIDICCOutEvent;
  M3_EXPECT_EQ(input_events.addEvent(ignored_input), Steinberg::kResultOk);

  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputEvents = &input_events;
  block.data().outputEvents = &output_events;
  m3::test::FakeVst3ParameterChanges channel_changes;
  M3_EXPECT_TRUE(channel_changes.append_input(0x4D33000DU, 0, 1.0));
  block.data().inputParameterChanges = &channel_changes;
  begin_notes(instance);
  M3_EXPECT_TRUE(queue_note(
      instance,
      transition(0, m3::TransitionKind::note_on, 60, 100, 1), kFrames));
  M3_EXPECT_EQ(instance.processor->process(block.data()),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(output_events.stored_event_count(), 1U);

  output_events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputEvents = &input_events;
  block.data().outputEvents = &output_events;
  begin_notes(instance);
  M3_EXPECT_TRUE(queue_note(
      instance,
      transition(191, m3::TransitionKind::note_on, 64, 70, 4), kFrames));
  M3_EXPECT_TRUE(queue_note(
      instance,
      transition(64, m3::TransitionKind::note_on, 62, 80, 3), kFrames));
  M3_EXPECT_TRUE(queue_note(
      instance,
      transition(64, m3::TransitionKind::note_off, 60, 0, 2), kFrames));
  M3_EXPECT_TRUE(queue_note(
      instance,
      transition(128, m3::TransitionKind::note_on, 63, 90, 1), kFrames));
  M3_EXPECT_EQ(instance.processor->process(block.data()),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(output_events.stored_event_count(), 4U);
  const Steinberg::Vst::Event& first = output_events.stored_event(0);
  const Steinberg::Vst::Event& second = output_events.stored_event(1);
  const Steinberg::Vst::Event& third = output_events.stored_event(2);
  const Steinberg::Vst::Event& fourth = output_events.stored_event(3);
  M3_EXPECT_EQ(first.type, Steinberg::Vst::Event::kNoteOffEvent);
  M3_EXPECT_EQ(first.sampleOffset, 64);
  M3_EXPECT_EQ(first.noteOff.pitch, 60);
  M3_EXPECT_EQ(first.noteOff.channel, 15);
  M3_EXPECT_EQ(second.type, Steinberg::Vst::Event::kNoteOnEvent);
  M3_EXPECT_EQ(second.sampleOffset, 64);
  M3_EXPECT_EQ(second.noteOn.pitch, 62);
  M3_EXPECT_EQ(second.noteOn.channel, 15);
  M3_EXPECT_EQ(third.type, Steinberg::Vst::Event::kNoteOnEvent);
  M3_EXPECT_EQ(third.sampleOffset, 128);
  M3_EXPECT_EQ(third.noteOn.pitch, 63);
  M3_EXPECT_EQ(third.noteOn.channel, 15);
  M3_EXPECT_EQ(fourth.type, Steinberg::Vst::Event::kNoteOnEvent);
  M3_EXPECT_EQ(fourth.sampleOffset, 191);
  M3_EXPECT_EQ(fourth.noteOn.pitch, 64);
  M3_EXPECT_EQ(fourth.noteOn.channel, 15);
  for (std::size_t index = 0; index < output_events.stored_event_count();
       ++index) {
    const Steinberg::uint16 type = output_events.stored_event(index).type;
    M3_EXPECT_TRUE(type == Steinberg::Vst::Event::kNoteOnEvent ||
                   type == Steinberg::Vst::Event::kNoteOffEvent);
  }
  M3_EXPECT_EQ(input_events.get_count_call_count(), 0U);
  M3_EXPECT_EQ(input_events.get_event_call_count(), 0U);
  close_active(instance);
}

M3_TEST(vst3_per_voice_routing_emits_simultaneous_notes_on_distinct_channels) {
  ActiveInstance instance;
  M3_EXPECT_TRUE(open_active(instance));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_active(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330001U, 1.0),
               Steinberg::kResultTrue);

  constexpr std::uint32_t kFrames = 64U;
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  m3::test::FakeVst3ParameterChanges routing;
  M3_EXPECT_TRUE(routing.append_input(0x4D330001U, 0, 1.0));
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputParameterChanges = &routing;
  block.data().outputEvents = &events;
  begin_notes(instance);
  M3_EXPECT_TRUE(queue_note(
      instance, transition(0, m3::TransitionKind::note_on, 60, 100, 1),
      kFrames));
  M3_EXPECT_TRUE(queue_note(
      instance, transition(1, m3::TransitionKind::note_on, 64, 100, 2),
      kFrames));
  M3_EXPECT_TRUE(queue_note(
      instance, transition(2, m3::TransitionKind::note_on, 67, 100, 3),
      kFrames));
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(events.stored_event_count(), 3U);
  for (std::size_t index = 0U; index < 3U; ++index) {
    M3_EXPECT_EQ(events.stored_event(index).type,
                 Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(events.stored_event(index).noteOn.channel,
                 static_cast<Steinberg::int16>(index));
  }
  close_active(instance);
}

M3_TEST(vst3_output_rejection_blocks_ons_retries_offs_and_preserves_dry_audio) {
  constexpr std::uint32_t kFrames = 64;
  for (std::size_t rejected = 0; rejected < 3; ++rejected) {
    ActiveInstance instance;
    M3_EXPECT_TRUE(open_active(instance, static_cast<Steinberg::int32>(kFrames)));
    if (instance.processor == nullptr) {
      close_active(instance);
      continue;
    }
    m3::test::FakeVst3ProcessBlock<float> block;
    m3::test::FakeVst3EventList output_events;
    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    output_events.reject_attempt(rejected);
    begin_notes(instance);
    for (std::uint8_t index = 0; index < 3; ++index) {
      M3_EXPECT_TRUE(queue_note(
          instance,
          transition(index, m3::TransitionKind::note_on,
                     static_cast<std::uint8_t>(60U + index), 100, index),
          kFrames));
    }
    const std::size_t allocations_before = m3::test::allocation_count();
    const std::size_t deallocations_before = m3::test::deallocation_count();
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
    M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
    M3_EXPECT_EQ(output_events.add_attempt_count(), rejected + 1U);
    M3_EXPECT_EQ(output_events.stored_event_count(), rejected);
    M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
                 m3::Status::midi_output_blocked);
    expect_dry(block, kFrames);
    for (std::size_t index = 0; index < 3; ++index) {
      const auto note = static_cast<std::uint8_t>(60U + index);
      M3_EXPECT_EQ(m3::vst3::generated_note_active_for_test(instance.processor,
                                                            note),
                   index < rejected);
      M3_EXPECT_EQ(m3::vst3::generated_note_pending_for_test(instance.processor,
                                                             note),
                   index < rejected);
    }

    output_events.reset();
    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    begin_notes(instance);
    M3_EXPECT_TRUE(queue_note(
        instance,
        transition(1, m3::TransitionKind::note_on, 70, 100, 4), kFrames));
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(output_events.stored_event_count(), rejected);
    M3_EXPECT_TRUE(output_events.add_attempt_count() <= 128U);
    for (std::size_t index = 0; index < output_events.stored_event_count();
         ++index) {
      const Steinberg::Vst::Event& event = output_events.stored_event(index);
      M3_EXPECT_EQ(event.type, Steinberg::Vst::Event::kNoteOffEvent);
      M3_EXPECT_EQ(event.sampleOffset, 0);
      M3_EXPECT_EQ(event.noteOff.pitch,
                   static_cast<Steinberg::int16>(60U + index));
    }
    M3_EXPECT_FALSE(
        m3::vst3::generated_note_active_for_test(instance.processor, 70));
    M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
                 m3::Status::midi_output_blocked);
    expect_dry(block, kFrames);

    M3_EXPECT_EQ(instance.controller->setParamNormalized(
                     m3::kPanicParameterId, 1.0),
                 Steinberg::kResultTrue);
    for (std::size_t hold_call = 0; hold_call < 2; ++hold_call) {
      output_events.reset();
      block.configure(kFrames, false);
      block.fill_silence();
      block.data().outputEvents = &output_events;
      begin_notes(instance);
      M3_EXPECT_EQ(instance.processor->process(block.data()),
                   Steinberg::kResultOk);
      M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
                   hold_call == 0U ? m3::Status::midi_output_blocked
                                   : m3::Status::ready);
    }
    output_events.reset();
    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    begin_notes(instance);
    M3_EXPECT_TRUE(queue_note(
        instance,
        transition(1, m3::TransitionKind::note_on, 70, 100, 5), kFrames));
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(output_events.stored_event_count(), 1U);
    M3_EXPECT_EQ(output_events.stored_event(0).type,
                 Steinberg::Vst::Event::kNoteOnEvent);
    M3_EXPECT_EQ(output_events.stored_event(0).noteOn.pitch, 70);
    close_active(instance);
  }

  ActiveInstance null_output;
  M3_EXPECT_TRUE(
      open_active(null_output, static_cast<Steinberg::int32>(kFrames)));
  if (null_output.processor != nullptr) {
    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(kFrames, false);
    block.fill_finite();
    begin_notes(null_output);
    M3_EXPECT_TRUE(queue_note(
        null_output,
        transition(0, m3::TransitionKind::note_on, 60, 100, 1), kFrames));
    const std::size_t allocations_before = m3::test::allocation_count();
    const std::size_t deallocations_before = m3::test::deallocation_count();
    M3_EXPECT_EQ(null_output.processor->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
    M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
    M3_EXPECT_EQ(m3::vst3::status_for_test(null_output.processor),
                 m3::Status::midi_output_blocked);
    M3_EXPECT_FALSE(
        m3::vst3::generated_note_active_for_test(null_output.processor, 60));
    expect_dry(block, kFrames);
  }
  close_active(null_output);
}

M3_TEST(vst3_each_cleanup_rejection_retains_unconfirmed_pitches) {
  constexpr std::uint32_t kFrames = 32;
  for (std::size_t rejected = 0; rejected < 3; ++rejected) {
    ActiveInstance instance;
    M3_EXPECT_TRUE(open_active(instance, static_cast<Steinberg::int32>(kFrames)));
    if (instance.processor == nullptr) {
      close_active(instance);
      continue;
    }
    m3::test::FakeVst3ProcessBlock<float> block;
    m3::test::FakeVst3EventList output_events;

    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    begin_notes(instance);
    for (std::uint8_t index = 0; index < 3; ++index) {
      M3_EXPECT_TRUE(queue_note(
          instance,
          transition(index, m3::TransitionKind::note_on,
                     static_cast<std::uint8_t>(60U + index), 100, index),
          kFrames));
    }
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);

    output_events.reset();
    output_events.reject_attempt(0);
    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    begin_notes(instance);
    M3_EXPECT_TRUE(queue_note(
        instance,
        transition(0, m3::TransitionKind::note_on, 70, 100, 4), kFrames));
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);

    output_events.reset();
    output_events.reject_attempt(rejected);
    block.configure(kFrames, false);
    block.fill_finite();
    block.data().outputEvents = &output_events;
    begin_notes(instance);
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(output_events.add_attempt_count(), rejected + 1U);
    M3_EXPECT_EQ(output_events.stored_event_count(), rejected);
    M3_EXPECT_TRUE(output_events.add_attempt_count() <= 128U);
    for (std::size_t index = 0; index < 3; ++index) {
      const auto note = static_cast<std::uint8_t>(60U + index);
      M3_EXPECT_EQ(m3::vst3::generated_note_pending_for_test(instance.processor,
                                                             note),
                   index >= rejected);
      M3_EXPECT_EQ(m3::vst3::generated_note_active_for_test(instance.processor,
                                                            note),
                   index >= rejected);
    }
    close_active(instance);
  }
}

M3_TEST(vst3_event_sink_normal_null_and_rejection_paths_are_allocation_free) {
  m3::test::FakeVst3EventList events;
  m3::vst3::Vst3EventSinkContext context{&events};
  const m3::VoiceTransition note_on =
      transition(31, m3::TransitionKind::note_on, 84, 127, 1);
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
    events.reset();
    context.events = &events;
    M3_EXPECT_TRUE(m3::vst3::push_vst3_note(&context, note_on, 16U));
    context.events = nullptr;
    M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, note_on, 16U));
    events.reset();
    events.reject_attempt(0);
    context.events = &events;
    M3_EXPECT_FALSE(m3::vst3::push_vst3_note(&context, note_on, 16U));
  }
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
}
