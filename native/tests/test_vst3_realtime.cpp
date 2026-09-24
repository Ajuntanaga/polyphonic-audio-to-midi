#include <dirent.h>
#include <time.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdint>

#include "fake_vst3_host.hpp"
#include "m3/pitch_math.hpp"
#include "m3/tuner_telemetry.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct RealtimeInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  m3::test::FakeVst3Host host{};
};

std::size_t current_task_count() noexcept {
  DIR* directory = opendir("/proc/self/task");
  if (directory == nullptr) {
    return 0U;
  }
  std::size_t count = 0U;
  while (const dirent* entry = readdir(directory)) {
    if (entry->d_name[0] != '.') {
      ++count;
    }
  }
  static_cast<void>(closedir(directory));
  return count;
}

bool open_instance(RealtimeInstance& instance, double sample_rate = 48000.0,
                   Steinberg::int32 maximum_block_size = 1) noexcept {
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
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = maximum_block_size;
  setup.sampleRate = sample_rate;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_instance(RealtimeInstance& instance) noexcept {
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

}  // namespace

M3_TEST(vst3_realtime_calls_allocate_zero_and_create_no_threads_100000) {
  RealtimeInstance instance;
  M3_EXPECT_TRUE(open_instance(instance));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }

  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(1U, true);
  block.fill_silence();
  const std::size_t tasks_before = current_task_count();
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  bool valid = tasks_before > 0U;
  for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
    valid = instance.processor->process(block.data()) ==
                Steinberg::kResultOk &&
            instance.processor->setProcessing(Steinberg::TBool{0}) ==
                Steinberg::kResultOk &&
            instance.processor->setProcessing(Steinberg::TBool{1}) ==
                Steinberg::kResultOk &&
            valid;
  }
  const std::size_t tasks_after = current_task_count();
  M3_EXPECT_TRUE(valid);
  M3_EXPECT_EQ(tasks_after, tasks_before);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_instance(instance);
}

M3_TEST(vst3_realtime_release_96khz_max8_p99_stays_within_block_budget) {
#if !defined(NDEBUG) || defined(M3_TSAN_ENABLED)
  // Wall-clock budgets are meaningful only for the optimized production
  // configuration without sanitizer instrumentation. The release native-test
  // job runs this exact same path.
  M3_EXPECT_TRUE(true);
#else
  constexpr std::uint32_t kFrames = 32U;
  constexpr double kSampleRate = 96000.0;
  constexpr std::size_t kWarmupBlocks = 512U;
  constexpr std::size_t kMeasuredBlocks = 12000U;
  constexpr std::uint64_t kBlockDeadlineNanoseconds =
      1000000000ULL * kFrames / 96000ULL;
  constexpr std::uint64_t kP99BudgetNanoseconds =
      kBlockDeadlineNanoseconds / 2U;
  constexpr std::uint64_t kMaximumBudgetNanoseconds =
      kBlockDeadlineNanoseconds;
  constexpr double kAmplitude = 0.025;

  RealtimeInstance instance;
  M3_EXPECT_TRUE(open_instance(instance, kSampleRate,
                               static_cast<Steinberg::int32>(kFrames)));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }

  const std::array<std::uint8_t, m3::kMaxVoices> notes{
      32U, 36U, 40U, 44U, 48U, 52U, 56U, 60U};
  std::array<double, m3::kMaxVoices> frequencies{};
  for (std::size_t voice = 0U; voice < notes.size(); ++voice) {
    frequencies[voice] =
        m3::midi_to_frequency(static_cast<double>(notes[voice]), 440.0);
  }

  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(kFrames, false);
  m3::test::FakeVst3EventList events;
  block.data().outputEvents = &events;
  std::uint64_t absolute_sample = 0U;
  const auto fill_input = [&]() noexcept {
    for (std::uint32_t frame = 0U; frame < kFrames; ++frame) {
      const double time = static_cast<double>(absolute_sample + frame) /
                          kSampleRate;
      double sample = 0.0;
      for (const double frequency : frequencies) {
        sample += kAmplitude *
                  std::sin(6.28318530717958647692 * frequency * time);
      }
      block.input_left()[frame] = static_cast<float>(sample);
      block.input_right()[frame] = 0.0F;
    }
  };

  for (std::size_t warmup = 0U; warmup < kWarmupBlocks; ++warmup) {
    fill_input();
    M3_EXPECT_EQ(instance.processor->process(block.data()),
                 Steinberg::kResultOk);
    events.reset();
    absolute_sample += kFrames;
  }

  m3::TunerSnapshot snapshot;
  M3_EXPECT_TRUE(
      m3::vst3::read_tuner_snapshot_for_test(instance.processor, snapshot));
  M3_EXPECT_EQ(snapshot.max_polyphony, 8U);
  M3_EXPECT_EQ(snapshot.voice_count, 8U);

  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  std::array<std::uint64_t, kMeasuredBlocks> wall_durations{};
  std::array<std::uint64_t, kMeasuredBlocks> cpu_durations{};
  m3::MonophonicPitchDetector::SelectionWork maximum_selection_work{};
  for (std::size_t iteration = 0U; iteration < kMeasuredBlocks; ++iteration) {
    fill_input();
    timespec cpu_begin{};
    timespec cpu_end{};
    const auto wall_begin = std::chrono::steady_clock::now();
    M3_EXPECT_EQ(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_begin), 0);
    const Steinberg::tresult result = instance.processor->process(block.data());
    M3_EXPECT_EQ(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_end), 0);
    const auto wall_end = std::chrono::steady_clock::now();
    M3_EXPECT_EQ(result, Steinberg::kResultOk);
    const auto wall_duration =
        std::chrono::duration_cast<std::chrono::nanoseconds>(wall_end - wall_begin)
            .count();
    const auto cpu_duration =
        static_cast<std::int64_t>(cpu_end.tv_sec - cpu_begin.tv_sec) *
            1000000000LL +
        static_cast<std::int64_t>(cpu_end.tv_nsec - cpu_begin.tv_nsec);
    M3_EXPECT_TRUE(wall_duration >= 0);
    M3_EXPECT_TRUE(cpu_duration >= 0);
    wall_durations[iteration] =
        static_cast<std::uint64_t>(wall_duration);
    cpu_durations[iteration] = static_cast<std::uint64_t>(cpu_duration);
    const auto selection_work =
        m3::vst3::detector_selection_work_for_test(instance.processor);
    maximum_selection_work.pool_candidates =
        std::max(maximum_selection_work.pool_candidates,
                 selection_work.pool_candidates);
    maximum_selection_work.state_transitions =
        std::max(maximum_selection_work.state_transitions,
                 selection_work.state_transitions);
    maximum_selection_work.assignment_edges =
        std::max(maximum_selection_work.assignment_edges,
                 selection_work.assignment_edges);
    events.reset();
    absolute_sample += kFrames;
  }
  std::sort(wall_durations.begin(), wall_durations.end());
  std::sort(cpu_durations.begin(), cpu_durations.end());
  const std::size_t p99_index = kMeasuredBlocks * 99U / 100U;
  // P99 retains two-times wall-clock headroom at the smallest supported
  // 96 kHz block. The single-call ceiling is the actual host-block deadline
  // and uses thread CPU time so an unrelated scheduler preemption cannot
  // masquerade as detector work; the isolated host matrix owns end-to-end
  // wall maxima.
  if (wall_durations[p99_index] >= kP99BudgetNanoseconds ||
      cpu_durations.back() >= kMaximumBudgetNanoseconds) {
    std::fprintf(stderr,
                 "96 kHz callback timing: wall-p99=%llu ns wall-max=%llu ns "
                 "cpu-max=%llu ns budgets=%llu/%llu ns\n",
                 static_cast<unsigned long long>(wall_durations[p99_index]),
                 static_cast<unsigned long long>(wall_durations.back()),
                 static_cast<unsigned long long>(cpu_durations.back()),
                 static_cast<unsigned long long>(kP99BudgetNanoseconds),
                 static_cast<unsigned long long>(kMaximumBudgetNanoseconds));
  }
  M3_EXPECT_TRUE(wall_durations[p99_index] < kP99BudgetNanoseconds);
  M3_EXPECT_TRUE(cpu_durations.back() < kMaximumBudgetNanoseconds);
  // The timing sample must include the dense/conflicting selector path, not
  // only an already-settled eight-note lifecycle fast path.
  M3_EXPECT_TRUE(maximum_selection_work.pool_candidates > m3::kMaxVoices);
  M3_EXPECT_TRUE(maximum_selection_work.assignment_edges >= 512U);
  M3_EXPECT_EQ(maximum_selection_work.state_transitions,
               maximum_selection_work.assignment_edges);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_instance(instance);
#endif
}
