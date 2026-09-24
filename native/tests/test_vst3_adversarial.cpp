#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#include "fake_vst3_host.hpp"
#include "m3/calibration_state_image.hpp"
#include "m3/constants.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/state_image.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct AdversarialInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  Steinberg::Vst::IEditController* controller{};
  m3::test::FakeVst3Host host{};
};

class FixedPrng final {
 public:
  explicit FixedPrng(std::uint32_t seed) noexcept : state_(seed) {}

  std::uint32_t next() noexcept {
    state_ ^= state_ << 13U;
    state_ ^= state_ >> 17U;
    state_ ^= state_ << 5U;
    return state_;
  }

 private:
  std::uint32_t state_;
};

bool create_instance(AdversarialInstance& instance) noexcept {
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

bool setup_and_start(AdversarialInstance& instance,
                     double sample_rate = 48000.0) noexcept {
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 512;
  setup.sampleRate = sample_rate;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_instance(AdversarialInstance& instance) noexcept {
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

std::size_t active_count(Steinberg::Vst::IAudioProcessor* processor) noexcept {
  std::size_t count = 0;
  for (std::uint16_t note = 0; note < 128U; ++note) {
    if (m3::vst3::generated_note_active_for_test(
            processor, static_cast<std::uint8_t>(note))) {
      ++count;
    }
  }
  return count;
}

std::size_t pending_count(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  std::size_t count = 0;
  for (std::uint16_t note = 0; note < 128U; ++note) {
    if (m3::vst3::generated_note_pending_for_test(
            processor, static_cast<std::uint8_t>(note))) {
      ++count;
    }
  }
  return count;
}

bool observe_events(const m3::test::FakeVst3EventList& events,
                    std::array<bool, 128>& host_active) noexcept {
  bool valid = true;
  for (std::size_t index = 0; index < events.stored_event_count(); ++index) {
    const Steinberg::Vst::Event& event = events.stored_event(index);
    if (event.type == Steinberg::Vst::Event::kNoteOnEvent) {
      const Steinberg::int16 pitch = event.noteOn.pitch;
      if (pitch < 0 || pitch > 127 ||
          host_active[static_cast<std::size_t>(pitch)]) {
        valid = false;
      } else {
        host_active[static_cast<std::size_t>(pitch)] = true;
      }
    } else if (event.type == Steinberg::Vst::Event::kNoteOffEvent) {
      const Steinberg::int16 pitch = event.noteOff.pitch;
      if (pitch < 0 || pitch > 127 ||
          !host_active[static_cast<std::size_t>(pitch)]) {
        valid = false;
      } else {
        host_active[static_cast<std::size_t>(pitch)] = false;
      }
    } else {
      valid = false;
    }
  }
  return valid;
}

std::size_t host_active_count(
    const std::array<bool, 128>& host_active) noexcept {
  std::size_t count = 0;
  for (const bool active : host_active) {
    count += active ? 1U : 0U;
  }
  return count;
}

m3::VoiceTransition note_on(std::uint8_t pitch,
                            std::uint32_t sequence) noexcept {
  return m3::VoiceTransition{sequence % 32U, m3::TransitionKind::note_on,
                             pitch, 100U, sequence};
}

bool process_quiet_cleanup(AdversarialInstance& instance,
                           std::array<bool, 128>& host_active) noexcept {
  if (instance.processor->setProcessing(Steinberg::TBool{0}) !=
          Steinberg::kResultOk ||
      instance.processor->setProcessing(Steinberg::TBool{1}) !=
          Steinberg::kResultOk) {
    return false;
  }
  m3::test::FakeVst3ProcessBlock<float> block;
  m3::test::FakeVst3EventList events;
  for (std::size_t call = 0; call < 2U; ++call) {
    events.reset();
    block.configure(32U, false);
    block.fill_silence();
    block.data().outputEvents = &events;
    if (instance.processor->process(block.data()) != Steinberg::kResultOk ||
        !observe_events(events, host_active)) {
      return false;
    }
  }
  return active_count(instance.processor) == 0U &&
         pending_count(instance.processor) == 0U &&
         host_active_count(host_active) == 0U;
}

}  // namespace

M3_TEST(vst3_adversarial_fixed_seed_100000_operations_fail_closed) {
  AdversarialInstance instance;
  M3_EXPECT_TRUE(create_instance(instance));
  M3_EXPECT_TRUE(setup_and_start(instance));
  if (instance.processor == nullptr || instance.component == nullptr ||
      instance.controller == nullptr) {
    close_instance(instance);
    return;
  }

  std::array<bool, 128> host_active{};
  bool safe = true;

  // A malformed producer must not make a ninth voice active.
  m3::test::FakeVst3ProcessBlock<float> voice_block;
  m3::test::FakeVst3EventList voice_events;
  voice_block.configure(32U, false);
  voice_block.fill_finite();
  voice_block.data().outputEvents = &voice_events;
  m3::vst3::begin_generated_note_block_for_test(instance.processor);
  for (std::uint8_t voice = 0; voice < 9U; ++voice) {
    safe = m3::vst3::queue_generated_note_for_test(
               instance.processor,
               note_on(static_cast<std::uint8_t>(40U + voice), voice), 32U) &&
           safe;
  }
  safe = instance.processor->process(voice_block.data()) ==
             Steinberg::kResultOk &&
         safe;
  safe = observe_events(voice_events, host_active) && safe;
  const std::size_t initial_active = active_count(instance.processor);
  const std::size_t initial_host_active = host_active_count(host_active);
  M3_EXPECT_TRUE(initial_active <= m3::kMaxVoices);
  M3_EXPECT_TRUE(initial_host_active <= m3::kMaxVoices);
  safe = initial_active <= m3::kMaxVoices && safe;
  safe = initial_host_active <= m3::kMaxVoices && safe;
  safe = process_quiet_cleanup(instance, host_active) && safe;

  m3::test::FakeVst3Stream saved_state;
  saved_state.reset_output(37);
  safe = instance.component->getState(&saved_state) == Steinberg::kResultOk &&
         saved_state.size() ==
             m3::kStateSize + m3::kCalibrationStateSize &&
         safe;
  std::array<std::uint8_t,
             m3::kStateSize + m3::kCalibrationStateSize + 1U>
      state_bytes{};
  std::memcpy(state_bytes.data(), saved_state.bytes(), saved_state.size());

  FixedPrng random{0x4D335633U};
  constexpr std::size_t kOperationCount = 100000U;
  constexpr std::array<double, 7> kRates{44100.0, 48000.0, 88200.0, 96000.0,
                                         32000.0, 50000.0, 192000.0};
  for (std::size_t operation = 0; operation < kOperationCount; ++operation) {
    const std::uint32_t value = random.next();
    const std::size_t kind = operation % 10U;

    if (kind == 0U) {
      m3::test::FakeVst3ParameterChanges changes;
      const std::size_t queue_total = value % 5U;
      for (std::size_t queue = 0; queue < queue_total; ++queue) {
        const std::size_t parameter_index =
            (static_cast<std::size_t>(value) + queue) %
            (m3::parameter_count() + 1U);
        const m3::ParameterSpec* spec =
            parameter_index < m3::parameter_count()
                ? m3::parameter_spec(parameter_index)
                : nullptr;
        const Steinberg::Vst::ParamID id =
            spec != nullptr ? spec->id : Steinberg::Vst::ParamID{0xDEADBEEFU};
        const Steinberg::int32 offset =
            (value & 1U) != 0U
                ? static_cast<Steinberg::int32>(value % 32U)
                : static_cast<Steinberg::int32>(32U + (value % 3U));
        const double normalized =
            (value & 4U) != 0U
                ? static_cast<double>(value % 1001U) / 1000.0
                : std::numeric_limits<double>::quiet_NaN();
        static_cast<void>(changes.append_input(id, offset, normalized));
      }
      if ((value & 8U) != 0U) {
        changes.override_parameter_count(
            (value & 16U) != 0U ? -1 : 33);
      }
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(32U, false);
      block.fill_finite();
      block.data().inputParameterChanges = &changes;
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 1U) {
      const std::size_t length = (operation / 10U) % state_bytes.size();
      for (std::size_t index = 0; index < state_bytes.size(); ++index) {
        state_bytes[index] = static_cast<std::uint8_t>(random.next());
      }
      if ((value & 31U) == 0U) {
        std::memcpy(state_bytes.data(), saved_state.bytes(), saved_state.size());
      }
      m3::test::FakeVst3Stream stream;
      safe = stream.set_input(state_bytes.data(), length,
                              static_cast<Steinberg::int32>(1U + value % 37U)) &&
             safe;
      static_cast<void>(instance.component->setState(&stream));
    } else if (kind == 2U) {
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      constexpr std::array<Steinberg::int32, 8> kFrames{
          -1, 0, 1, 32, 64, 128, 512, 513};
      const Steinberg::int32 frames = kFrames[value % kFrames.size()];
      block.configure(frames > 0 ? static_cast<std::uint32_t>(frames) : 1U,
                      (value & 1U) != 0U);
      block.fill_finite();
      block.data().numSamples = frames;
      constexpr std::array<Steinberg::int32, 4> kModes{
          Steinberg::Vst::kRealtime, Steinberg::Vst::kPrefetch,
          Steinberg::Vst::kOffline, 99};
      block.data().processMode = kModes[(value >> 3U) % kModes.size()];
      constexpr std::array<Steinberg::int32, 3> kFormats{
          Steinberg::Vst::kSample32, Steinberg::Vst::kSample64, 99};
      block.data().symbolicSampleSize =
          kFormats[(value >> 5U) % kFormats.size()];
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 3U) {
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(32U, false);
      block.fill_finite();
      switch (value % 6U) {
        case 0U:
          block.data().numInputs = 2;
          break;
        case 1U:
          block.data().numOutputs = 0;
          break;
        case 2U:
          block.input_bus().numChannels = 1;
          break;
        case 3U:
          block.output_bus().numChannels = 3;
          break;
        case 4U:
          block.share_input_channels();
          break;
        default:
          block.share_output_channels();
          break;
      }
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 4U) {
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(32U, false);
      block.fill_finite();
      block.input_left()[value % 32U] =
          (value & 1U) != 0U
              ? std::numeric_limits<float>::infinity()
              : std::numeric_limits<float>::quiet_NaN();
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 5U) {
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(32U, false);
      block.fill_finite();
      events.reject_attempt(value % 12U);
      m3::vst3::begin_generated_note_block_for_test(instance.processor);
      static_cast<void>(m3::vst3::queue_generated_note_for_test(
          instance.processor,
          note_on(static_cast<std::uint8_t>(36U + value % 48U), value), 32U));
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 6U) {
      const double channel = static_cast<double>(value % 16U) / 15.0;
      safe = instance.controller->setParamNormalized(0x4D33000DU, channel) ==
                 Steinberg::kResultTrue &&
             safe;
      m3::test::FakeVst3ParameterChanges changes;
      static_cast<void>(changes.append_input(0x4D33000DU, 0, channel));
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(32U, false);
      block.fill_finite();
      block.data().inputParameterChanges = &changes;
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    } else if (kind == 7U) {
      safe = instance.processor->setProcessing(Steinberg::TBool{0}) ==
                 Steinberg::kResultOk &&
             safe;
      if ((operation & 255U) == 7U) {
        safe = instance.component->setActive(Steinberg::TBool{0}) ==
                   Steinberg::kResultOk &&
               safe;
        Steinberg::Vst::ProcessSetup setup{};
        setup.processMode = Steinberg::Vst::kRealtime;
        setup.symbolicSampleSize = Steinberg::Vst::kSample32;
        setup.maxSamplesPerBlock = 512;
        setup.sampleRate = kRates[(operation / 10U) % kRates.size()];
        safe = instance.processor->setupProcessing(setup) ==
                   Steinberg::kResultOk &&
               instance.component->setActive(Steinberg::TBool{1}) ==
                   Steinberg::kResultOk &&
               safe;
      }
      safe = instance.processor->setProcessing(Steinberg::TBool{1}) ==
                 Steinberg::kResultOk &&
             safe;
    } else if (kind == 8U) {
      safe = process_quiet_cleanup(instance, host_active) && safe;
    } else {
      m3::test::FakeVst3ProcessBlock<float> block;
      m3::test::FakeVst3EventList events;
      block.configure(static_cast<std::uint32_t>(1U + value % 512U), false);
      if ((value & 1U) != 0U) {
        block.fill_silence();
        block.input_bus().silenceFlags = 3U;
      } else {
        block.fill_finite();
      }
      block.data().outputEvents = &events;
      static_cast<void>(instance.processor->process(block.data()));
      safe = observe_events(events, host_active) && safe;
    }

    safe = active_count(instance.processor) <= m3::kMaxVoices && safe;
    safe = host_active_count(host_active) <= m3::kMaxVoices && safe;
  }

  safe = process_quiet_cleanup(instance, host_active) && safe;
  M3_EXPECT_TRUE(safe);
  M3_EXPECT_EQ(active_count(instance.processor), 0U);
  M3_EXPECT_EQ(pending_count(instance.processor), 0U);
  M3_EXPECT_EQ(host_active_count(host_active), 0U);
  close_instance(instance);
}
