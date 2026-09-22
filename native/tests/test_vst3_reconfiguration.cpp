#include <cstdint>

#include "fake_vst3_host.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/state_image.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "prepared_config_exchange.hpp"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct ReconfigInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  Steinberg::Vst::IEditController* controller{};
  m3::test::FakeVst3Host host{};
};

bool create_instance(ReconfigInstance& instance) noexcept {
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
         instance.processor != nullptr &&
         instance.component->queryInterface(
             Steinberg::Vst::IEditController::iid,
             reinterpret_cast<void**>(&instance.controller)) ==
             Steinberg::kResultOk &&
         instance.controller != nullptr;
}

bool setup_and_start(ReconfigInstance& instance, double sample_rate = 48000.0,
                     Steinberg::int32 max_frames = 128) noexcept {
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

void close_instance(ReconfigInstance& instance) noexcept {
  if (instance.processor != nullptr) {
    static_cast<void>(instance.processor->setProcessing(Steinberg::TBool{0}));
  }
  if (instance.component != nullptr) {
    static_cast<void>(instance.component->setActive(Steinberg::TBool{0}));
    static_cast<void>(instance.component->terminate());
  }
  if (instance.controller != nullptr) {
    instance.controller->release();
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

m3::VoiceTransition note_on(std::uint8_t pitch) noexcept {
  return m3::VoiceTransition{0, m3::TransitionKind::note_on, pitch, 100, 0};
}

void queue_note(ReconfigInstance& instance, std::uint8_t pitch,
                std::uint32_t frames) noexcept {
  m3::vst3::begin_generated_note_block_for_test(instance.processor);
  M3_EXPECT_TRUE(m3::vst3::queue_generated_note_for_test(
      instance.processor, note_on(pitch), frames));
}

}  // namespace

M3_TEST(vst3_stop_restart_preserves_pending_releases_and_frees_only_storage) {
  ReconfigInstance instance;
  M3_EXPECT_TRUE(create_instance(instance));
  M3_EXPECT_TRUE(setup_and_start(instance));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  constexpr std::uint32_t kFrames = 64;
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().outputEvents = &events;
  queue_note(instance, 60, kFrames);
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_TRUE(
      m3::vst3::generated_note_active_for_test(instance.processor, 60));
  M3_EXPECT_EQ(m3::vst3::transition_capacity_for_test(instance.processor),
               40U);

  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  const std::uint32_t resets_before =
      m3::vst3::detector_reset_count_for_test(instance.processor);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  M3_EXPECT_TRUE(
      m3::vst3::generated_note_pending_for_test(instance.processor, 60));
  M3_EXPECT_EQ(m3::vst3::decision_phase_for_test(instance.processor), 0U);
  M3_EXPECT_EQ(m3::vst3::detector_reset_count_for_test(instance.processor),
               resets_before + 1U);
  M3_EXPECT_EQ(events.stored_event_count(), 1U);

  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::transition_capacity_for_test(instance.processor), 0U);
  M3_EXPECT_TRUE(
      m3::vst3::generated_note_pending_for_test(instance.processor, 60));
  M3_EXPECT_TRUE(m3::test::deallocation_count() > deallocations_before);

  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 128;
  setup.sampleRate = 96000.0;
  M3_EXPECT_EQ(instance.processor->setupProcessing(setup),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
               Steinberg::kResultOk);

  events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().outputEvents = &events;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(events.stored_event_count(), 1U);
  if (events.stored_event_count() == 1U) {
    M3_EXPECT_EQ(events.stored_event(0).type,
                 Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(events.stored_event(0).sampleOffset, 0);
    M3_EXPECT_EQ(events.stored_event(0).noteOff.pitch, 60);
    M3_EXPECT_EQ(events.stored_event(0).noteOff.channel, 0);
  }
  M3_EXPECT_FALSE(
      m3::vst3::generated_note_pending_for_test(instance.processor, 60));
  M3_EXPECT_EQ(m3::vst3::decision_tick_count_for_test(instance.processor), 0U);
  close_instance(instance);
}

M3_TEST(vst3_matching_preparation_adopts_once_and_missing_preparation_waits) {
  ReconfigInstance instance;
  M3_EXPECT_TRUE(create_instance(instance));
  M3_EXPECT_TRUE(setup_and_start(instance));
  if (instance.processor == nullptr || instance.controller == nullptr) {
    close_instance(instance);
    return;
  }
  constexpr std::uint32_t kFrames = 64;
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().outputEvents = &events;
  queue_note(instance, 60, kFrames);
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);

  const std::size_t preparation_before =
      m3::prepared_config_stage_count_for_test();
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D33000DU, 1.0),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(m3::prepared_config_stage_count_for_test(),
               preparation_before + 1U);
  const std::uint64_t old_generation =
      m3::vst3::active_config_generation_for_test(instance.processor);
  const std::uint32_t resets_before =
      m3::vst3::detector_reset_count_for_test(instance.processor);

  m3::test::FakeVst3ParameterChanges channel_16;
  M3_EXPECT_TRUE(channel_16.append_input(0x4D33000DU, 63, 1.0));
  events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputParameterChanges = &channel_16;
  block.data().outputEvents = &events;
  const std::size_t preparation_at_process =
      m3::prepared_config_stage_count_for_test();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::prepared_config_stage_count_for_test(),
               preparation_at_process);
  M3_EXPECT_EQ(events.stored_event_count(), 1U);
  if (events.stored_event_count() == 1U) {
    M3_EXPECT_EQ(events.stored_event(0).type,
                 Steinberg::Vst::Event::kNoteOffEvent);
    M3_EXPECT_EQ(events.stored_event(0).noteOff.channel, 0);
  }
  M3_EXPECT_EQ(m3::vst3::active_midi_channel_for_test(instance.processor),
               16U);
  M3_EXPECT_TRUE(
      m3::vst3::active_config_generation_for_test(instance.processor) !=
      old_generation);
  M3_EXPECT_EQ(m3::vst3::detector_reset_count_for_test(instance.processor),
               resets_before + 1U);

  const std::uint64_t adopted_generation =
      m3::vst3::active_config_generation_for_test(instance.processor);
  events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputParameterChanges = &channel_16;
  block.data().outputEvents = &events;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::active_config_generation_for_test(instance.processor),
               adopted_generation);

  events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().outputEvents = &events;
  queue_note(instance, 62, kFrames);
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(events.stored_event_count(), 1U);
  if (events.stored_event_count() == 1U) {
    M3_EXPECT_EQ(events.stored_event(0).noteOn.channel, 15);
  }

  m3::test::FakeVst3ParameterChanges missing;
  M3_EXPECT_TRUE(missing.append_input(0x4D33000DU, 0, 7.0 / 15.0));
  M3_EXPECT_TRUE(missing.append_input(0x4D33000FU, 0, 0.0));
  events.reset();
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().inputParameterChanges = &missing;
  block.data().outputEvents = &events;
  const std::size_t missing_before = m3::prepared_config_stage_count_for_test();
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::prepared_config_stage_count_for_test(), missing_before);
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::reconfiguring);
  M3_EXPECT_EQ(m3::vst3::active_midi_channel_for_test(instance.processor),
               16U);
  M3_EXPECT_EQ(m3::vst3::active_config_generation_for_test(instance.processor),
               adopted_generation);
  for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame],
                 m3::test::FakeVst3ProcessBlock<float>::expected_input_left(
                     frame));
  }

  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D33000DU,
                                                        7.0 / 15.0),
               Steinberg::kResultTrue);
  block.configure(kFrames, false);
  block.fill_finite();
  block.data().outputEvents = &events;
  M3_EXPECT_EQ(instance.processor->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::vst3::active_midi_channel_for_test(instance.processor), 8U);
  M3_EXPECT_EQ(m3::vst3::status_for_test(instance.processor),
               m3::Status::ready);
  for (std::uint32_t frame = 0; frame < kFrames; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0F);
  }
  close_instance(instance);
}

M3_TEST(vst3_state_load_prepares_structural_data_outside_processing) {
  ReconfigInstance instance;
  M3_EXPECT_TRUE(create_instance(instance));
  if (instance.component == nullptr || instance.processor == nullptr) {
    close_instance(instance);
    return;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 128;
  setup.sampleRate = 88200.0;
  M3_EXPECT_EQ(instance.processor->setupProcessing(setup),
               Steinberg::kResultOk);

  m3::PersistentConfig config;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.profile_mode = m3::ProfileMode::general;
  config.a4_hz = 432.5;
  config.midi_channel = 4;
  m3::StateImage image{};
  M3_EXPECT_TRUE(m3::encode_state(config, image));
  m3::test::FakeVst3Stream stream;
  M3_EXPECT_TRUE(stream.set_input(image.data(), image.size(), 13));
  const std::size_t before = m3::prepared_config_stage_count_for_test();
  M3_EXPECT_EQ(instance.component->setState(&stream), Steinberg::kResultOk);
  M3_EXPECT_EQ(m3::prepared_config_stage_count_for_test(), before + 1U);
  M3_EXPECT_EQ(m3::vst3::prepared_sample_rate_for_test(instance.processor),
               88200.0);
  close_instance(instance);
}
