#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <new>
#include <type_traits>

#include "fake_vst3_host.hpp"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_probe_processor.hpp"

namespace {

struct ProbeInstance final {
  m3::vst3::M3ProbeProcessor* object{};
  m3::test::FakeVst3Host host{};
  bool initialized{};
  bool active{};
  bool processing{};
};

bool open_probe(ProbeInstance& instance, double sample_rate,
                Steinberg::int32 sample_size,
                std::uint32_t max_frames) noexcept {
  instance.object = new (std::nothrow) m3::vst3::M3ProbeProcessor;
  if (instance.object == nullptr ||
      instance.object->initialize(&instance.host) != Steinberg::kResultOk) {
    return false;
  }
  instance.initialized = true;
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = sample_size;
  setup.maxSamplesPerBlock = static_cast<Steinberg::int32>(max_frames);
  setup.sampleRate = sample_rate;
  if (instance.object->setupProcessing(setup) != Steinberg::kResultOk ||
      instance.object->setActive(Steinberg::TBool{1}) != Steinberg::kResultOk) {
    return false;
  }
  instance.active = true;
  if (instance.object->setProcessing(Steinberg::TBool{1}) !=
      Steinberg::kResultOk) {
    return false;
  }
  instance.processing = true;
  return true;
}

void close_probe(ProbeInstance& instance) noexcept {
  if (instance.object == nullptr) {
    return;
  }
  if (instance.processing) {
    static_cast<void>(
        instance.object->setProcessing(Steinberg::TBool{0}));
    instance.processing = false;
  }
  if (instance.active) {
    static_cast<void>(instance.object->setActive(Steinberg::TBool{0}));
    instance.active = false;
  }
  if (instance.initialized) {
    static_cast<void>(instance.object->terminate());
    instance.initialized = false;
  }
  delete instance.object;
  instance.object = nullptr;
}

template <typename Sample>
std::array<Sample, 2> timeline_sample(std::uint64_t absolute_sample) noexcept {
  if (absolute_sample == 64U || absolute_sample == 128U ||
      absolute_sample == 192U) {
    const std::size_t index =
        static_cast<std::size_t>(absolute_sample / 64U - 1U);
    return {
        static_cast<Sample>(m3::vst3::kProbeFirstCode[index].left),
        static_cast<Sample>(m3::vst3::kProbeFirstCode[index].right),
    };
  }
  if (absolute_sample == 384U || absolute_sample == 448U ||
      absolute_sample == 512U) {
    const std::size_t index =
        static_cast<std::size_t>(absolute_sample / 64U - 6U);
    return {
        static_cast<Sample>(m3::vst3::kProbeSecondCode[index].left),
        static_cast<Sample>(m3::vst3::kProbeSecondCode[index].right),
    };
  }
  if ((absolute_sample % m3::vst3::kProbeDecisionFrames) == 0U) {
    return {static_cast<Sample>(0), static_cast<Sample>(0)};
  }
  const double dry =
      (static_cast<double>(absolute_sample % 31U) - 15.0) / 1024.0;
  return {static_cast<Sample>(dry), static_cast<Sample>(-dry)};
}

template <typename Sample>
void fill_timeline(m3::test::FakeVst3ProcessBlock<Sample>& block,
                   std::uint64_t absolute_start,
                   std::uint32_t frames) noexcept {
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    const auto sample = timeline_sample<Sample>(absolute_start + frame);
    block.input_left()[frame] = sample[0];
    block.input_right()[frame] = sample[1];
    block.output_left()[frame] = static_cast<Sample>(-0.75);
    block.output_right()[frame] = static_cast<Sample>(0.75);
  }
}

template <typename Sample>
void expect_dry(m3::test::FakeVst3ProcessBlock<Sample>& block,
                std::uint64_t absolute_start,
                std::uint32_t frames) noexcept {
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    const auto expected = timeline_sample<Sample>(absolute_start + frame);
    M3_EXPECT_EQ(block.output_left()[frame], expected[0]);
    M3_EXPECT_EQ(block.output_right()[frame], expected[1]);
  }
}

void expect_note(const Steinberg::Vst::Event& event,
                 Steinberg::Vst::Event::EventTypes type,
                 std::uint8_t pitch, std::uint8_t velocity) noexcept {
  M3_EXPECT_EQ(event.type, type);
  if (type == Steinberg::Vst::Event::kNoteOnEvent) {
    M3_EXPECT_EQ(event.noteOn.channel, 0);
    M3_EXPECT_EQ(event.noteOn.pitch,
                 static_cast<Steinberg::int16>(pitch));
    M3_EXPECT_NEAR(event.noteOn.velocity,
                   static_cast<double>(velocity) / 127.0, 1.0e-7);
  } else {
    M3_EXPECT_EQ(event.noteOff.channel, 0);
    M3_EXPECT_EQ(event.noteOff.pitch,
                 static_cast<Steinberg::int16>(pitch));
    M3_EXPECT_EQ(event.noteOff.velocity, 0.0F);
  }
}

template <typename Sample>
void exercise_rate_and_partition(double sample_rate,
                                 std::uint32_t block_size) noexcept {
  constexpr Steinberg::int32 kSampleSize =
      std::is_same_v<Sample, Steinberg::Vst::Sample32>
          ? Steinberg::Vst::kSample32
          : Steinberg::Vst::kSample64;
  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance instance;
  M3_EXPECT_TRUE(open_probe(instance, sample_rate, kSampleSize, block_size));
  if (instance.object == nullptr || !instance.processing) {
    close_probe(instance);
    return;
  }

  m3::test::FakeVst3EventList ignored_input;
  Steinberg::Vst::Event ignored{};
  ignored.type = Steinberg::Vst::Event::kLegacyMIDICCOutEvent;
  M3_EXPECT_EQ(ignored_input.addEvent(ignored), Steinberg::kResultOk);
  m3::test::FakeVst3EventList output;
  m3::test::FakeVst3ProcessBlock<Sample> block;
  constexpr std::uint64_t kTimelineFrames = 640U;
  std::uint64_t cursor = 0U;
  while (cursor < kTimelineFrames) {
    const std::uint32_t frames = static_cast<std::uint32_t>(std::min(
        static_cast<std::uint64_t>(block_size), kTimelineFrames - cursor));
    block.configure(frames, false);
    fill_timeline(block, cursor, frames);
    block.data().inputEvents = &ignored_input;
    block.data().outputEvents = &output;
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
    expect_dry(block, cursor, frames);
    cursor += frames;
  }

  M3_EXPECT_EQ(ignored_input.get_count_call_count(), 0U);
  M3_EXPECT_EQ(ignored_input.get_event_call_count(), 0U);
  M3_EXPECT_EQ(output.stored_event_count(), 3U);
  if (output.stored_event_count() == 3U) {
    expect_note(output.stored_event(0), Steinberg::Vst::Event::kNoteOnEvent,
                m3::vst3::kProbeFirstPitch,
                m3::vst3::kProbeFirstVelocity);
    expect_note(output.stored_event(1), Steinberg::Vst::Event::kNoteOffEvent,
                m3::vst3::kProbeFirstPitch, 0U);
    expect_note(output.stored_event(2), Steinberg::Vst::Event::kNoteOnEvent,
                m3::vst3::kProbeSecondPitch,
                m3::vst3::kProbeSecondVelocity);
  }

  M3_EXPECT_EQ(instance.object->setProcessing(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  instance.processing = false;
  M3_EXPECT_EQ(instance.object->setProcessing(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  instance.processing = true;
  block.configure(std::min(block_size, 64U), true);
  block.fill_silence();
  block.data().inputEvents = &ignored_input;
  block.data().outputEvents = &output;
  M3_EXPECT_EQ(instance.object->process(block.data()), Steinberg::kResultOk);
  M3_EXPECT_EQ(output.stored_event_count(), 4U);
  if (output.stored_event_count() == 4U) {
    expect_note(output.stored_event(3), Steinberg::Vst::Event::kNoteOffEvent,
                m3::vst3::kProbeSecondPitch, 0U);
    M3_EXPECT_EQ(output.stored_event(3).sampleOffset, 0);
  }

  const m3::vst3::ProbeDiagnosticsSnapshot diagnostics =
      m3::vst3::probe_diagnostics_for_test(instance.object);
  M3_EXPECT_EQ(diagnostics.sample_rate, sample_rate);
  M3_EXPECT_EQ(diagnostics.maximum_block, block_size);
  M3_EXPECT_EQ(diagnostics.trigger_one, 1U);
  M3_EXPECT_EQ(diagnostics.trigger_two, 1U);
  M3_EXPECT_EQ(diagnostics.trigger_overflow, 0U);
  M3_EXPECT_EQ(diagnostics.trigger_fault, 0U);
  M3_EXPECT_TRUE(diagnostics.separate_seen >= 1U);
  if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
    M3_EXPECT_TRUE(diagnostics.float32_seen >= 1U);
  } else {
    M3_EXPECT_TRUE(diagnostics.float64_seen >= 1U);
  }
  close_probe(instance);
}

template <typename Sample>
void feed_selected_samples(ProbeInstance& instance,
                           const std::array<m3::vst3::ProbeStereoCode, 5>& code,
                           std::size_t count,
                           m3::test::FakeVst3EventList& output) noexcept {
  m3::test::FakeVst3ProcessBlock<Sample> block;
  for (std::size_t index = 0; index < count; ++index) {
    block.configure(64U, false);
    block.fill_silence();
    block.input_left()[0] = static_cast<Sample>(code[index].left);
    block.input_right()[0] = static_cast<Sample>(code[index].right);
    block.data().outputEvents = &output;
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
  }
}

}  // namespace

M3_TEST(vst3_probe_audio_codes_are_rate_partition_and_format_invariant) {
  constexpr double kRates[]{44100.0, 48000.0, 88200.0, 96000.0};
  constexpr std::uint32_t kBlocks[]{32U, 64U, 128U, 256U, 512U};
  for (const double rate : kRates) {
    for (const std::uint32_t block : kBlocks) {
      exercise_rate_and_partition<float>(rate, block);
      exercise_rate_and_partition<double>(rate, block);
    }
  }
}

M3_TEST(vst3_probe_malformed_and_overflow_codes_latch_without_events) {
  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance malformed;
  M3_EXPECT_TRUE(open_probe(malformed, 48000.0, Steinberg::Vst::kSample32,
                            64U));
  m3::test::FakeVst3EventList malformed_events;
  const std::array<m3::vst3::ProbeStereoCode, 5> malformed_code{{
      {0.333, -0.125},
      {0.0, 0.0},
      m3::vst3::kProbeFirstCode[0],
      m3::vst3::kProbeFirstCode[1],
      m3::vst3::kProbeFirstCode[2],
  }};
  feed_selected_samples<float>(malformed, malformed_code,
                               malformed_code.size(), malformed_events);
  M3_EXPECT_EQ(malformed_events.stored_event_count(), 0U);
  const auto malformed_diagnostics =
      m3::vst3::probe_diagnostics_for_test(malformed.object);
  M3_EXPECT_EQ(malformed_diagnostics.trigger_fault, 1U);
  M3_EXPECT_EQ(malformed_diagnostics.trigger_one, 0U);
  M3_EXPECT_EQ(malformed_diagnostics.trigger_two, 0U);
  close_probe(malformed);

  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance overflow;
  M3_EXPECT_TRUE(open_probe(overflow, 96000.0, Steinberg::Vst::kSample64,
                            64U));
  m3::test::FakeVst3EventList overflow_events;
  const std::array<m3::vst3::ProbeStereoCode, 5> overflow_code{{
      m3::vst3::kProbeFirstCode[0],
      m3::vst3::kProbeFirstCode[1],
      m3::vst3::kProbeFirstCode[2],
      m3::vst3::kProbeFirstCode[0],
      {0.0, 0.0},
  }};
  feed_selected_samples<double>(overflow, overflow_code,
                                overflow_code.size(), overflow_events);
  M3_EXPECT_EQ(overflow_events.stored_event_count(), 0U);
  const auto overflow_diagnostics =
      m3::vst3::probe_diagnostics_for_test(overflow.object);
  M3_EXPECT_EQ(overflow_diagnostics.trigger_overflow, 1U);
  M3_EXPECT_EQ(overflow_diagnostics.trigger_fault, 1U);
  M3_EXPECT_EQ(overflow_diagnostics.trigger_one, 0U);
  close_probe(overflow);
}

M3_TEST(vst3_probe_invalid_process_contract_cannot_arm_a_trigger) {
  const std::array<m3::vst3::ProbeStereoCode, 5> first_code{ {
      m3::vst3::kProbeFirstCode[0],
      m3::vst3::kProbeFirstCode[1],
      m3::vst3::kProbeFirstCode[2],
      {0.0, 0.0},
      {0.0, 0.0},
  } };

  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance oversized;
  M3_EXPECT_TRUE(open_probe(oversized, 48000.0,
                            Steinberg::Vst::kSample32, 64U));
  m3::test::FakeVst3EventList oversized_events;
  feed_selected_samples<float>(oversized, first_code, 3U,
                               oversized_events);
  m3::test::FakeVst3ProcessBlock<float> oversized_block;
  oversized_block.configure(65U, false);
  oversized_block.fill_silence();
  oversized_block.data().outputEvents = &oversized_events;
  M3_EXPECT_EQ(oversized.object->process(oversized_block.data()),
               Steinberg::kInvalidArgument);
  const auto oversized_diagnostics =
      m3::vst3::probe_diagnostics_for_test(oversized.object);
  M3_EXPECT_EQ(oversized_diagnostics.trigger_one, 0U);
  M3_EXPECT_EQ(oversized_events.stored_event_count(), 0U);
  close_probe(oversized);

  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance nonfinite;
  M3_EXPECT_TRUE(open_probe(nonfinite, 48000.0,
                            Steinberg::Vst::kSample32, 64U));
  m3::test::FakeVst3EventList nonfinite_events;
  feed_selected_samples<float>(nonfinite, first_code, 3U,
                               nonfinite_events);
  m3::test::FakeVst3ProcessBlock<float> nonfinite_block;
  nonfinite_block.configure(64U, false);
  nonfinite_block.fill_silence();
  nonfinite_block.input_left()[1] =
      std::numeric_limits<float>::quiet_NaN();
  nonfinite_block.data().outputEvents = &nonfinite_events;
  M3_EXPECT_EQ(nonfinite.object->process(nonfinite_block.data()),
               Steinberg::kResultOk);
  const auto nonfinite_diagnostics =
      m3::vst3::probe_diagnostics_for_test(nonfinite.object);
  M3_EXPECT_EQ(nonfinite_diagnostics.trigger_one, 0U);
  M3_EXPECT_EQ(nonfinite_events.stored_event_count(), 0U);
  close_probe(nonfinite);
}

M3_TEST(vst3_probe_lifecycle_diagnostics_are_atomic_and_complete) {
  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance instance;
  M3_EXPECT_TRUE(open_probe(instance, 88200.0, Steinberg::Vst::kSample32,
                            128U));
  if (instance.object != nullptr) {
    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(64U, true);
    block.fill_silence();
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
    const auto active =
        m3::vst3::probe_diagnostics_for_test(instance.object);
    M3_EXPECT_EQ(active.create, 1U);
    M3_EXPECT_EQ(active.initialize, 1U);
    M3_EXPECT_EQ(active.setup, 1U);
    M3_EXPECT_EQ(active.activate, 1U);
    M3_EXPECT_EQ(active.start, 1U);
    M3_EXPECT_EQ(active.process, 1U);
    M3_EXPECT_EQ(active.alias_seen, 1U);
    M3_EXPECT_EQ(active.destroy, 0U);
  }
  close_probe(instance);
  const auto closed = m3::vst3::probe_diagnostics_snapshot_for_test();
  M3_EXPECT_EQ(closed.stop, 1U);
  M3_EXPECT_EQ(closed.deactivate, 1U);
  M3_EXPECT_EQ(closed.terminate, 1U);
  M3_EXPECT_EQ(closed.destroy, 1U);
}

M3_TEST(vst3_probe_silence_processing_is_allocation_free_after_activation) {
  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance instance;
  M3_EXPECT_TRUE(open_probe(instance, 48000.0, Steinberg::Vst::kSample32,
                            64U));
  if (instance.object != nullptr && instance.processing) {
    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(64U, true);
    block.fill_silence();
    const std::size_t allocations_before = m3::test::allocation_count();
    const std::size_t deallocations_before = m3::test::deallocation_count();
    for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
      M3_EXPECT_EQ(instance.object->process(block.data()),
                   Steinberg::kResultOk);
    }
    M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
    M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  }
  close_probe(instance);
}

M3_TEST(vst3_probe_diagnostics_publish_once_per_processing_start) {
  m3::vst3::reset_probe_diagnostics_for_test();
  ProbeInstance instance;
  M3_EXPECT_TRUE(open_probe(instance, 96000.0, Steinberg::Vst::kSample32,
                            512U));
  if (instance.object != nullptr && instance.processing) {
    constexpr Steinberg::int32 kProductionParameterCount = 18;
    constexpr Steinberg::int32 kDiagnosticParameterCount = 21;
    M3_EXPECT_EQ(instance.object->getParameterCount(),
                 kProductionParameterCount + kDiagnosticParameterCount);
    for (Steinberg::int32 index = 0; index < kDiagnosticParameterCount;
         ++index) {
      Steinberg::Vst::ParameterInfo info{};
      M3_EXPECT_EQ(instance.object->getParameterInfo(
                       kProductionParameterCount + index, info),
                   Steinberg::kResultOk);
      M3_EXPECT_EQ(info.id, m3::vst3::kProbeDiagnosticBaseId +
                                static_cast<Steinberg::Vst::ParamID>(index));
      M3_EXPECT_TRUE(
          (info.flags & Steinberg::Vst::ParameterInfo::kIsReadOnly) != 0);
    }

    m3::test::FakeVst3ProcessBlock<float> block;
    block.configure(64U, true);
    block.fill_silence();
    m3::test::FakeVst3ParameterChanges output;
    block.data().outputParameterChanges = &output;
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(output.stored_queue_count(),
                 static_cast<std::size_t>(kDiagnosticParameterCount));

    output.reset();
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(output.stored_queue_count(), 0U);

    M3_EXPECT_EQ(instance.object->setProcessing(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    instance.processing = false;
    M3_EXPECT_EQ(instance.object->setProcessing(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    instance.processing = true;
    output.reset();
    M3_EXPECT_EQ(instance.object->process(block.data()),
                 Steinberg::kResultOk);
    std::size_t diagnostic_queue_count = 0U;
    for (std::size_t index = 0; index < output.stored_queue_count(); ++index) {
      m3::test::FakeVst3ParamValueQueue* queue = output.stored_queue(index);
      if (queue != nullptr &&
          queue->getParameterId() >= m3::vst3::kProbeDiagnosticBaseId &&
          queue->getParameterId() < m3::vst3::kProbeDiagnosticBaseId +
                                        static_cast<Steinberg::Vst::ParamID>(
                                            kDiagnosticParameterCount)) {
        ++diagnostic_queue_count;
      }
    }
    M3_EXPECT_EQ(diagnostic_queue_count,
                 static_cast<std::size_t>(kDiagnosticParameterCount));
  }
  close_probe(instance);
}
