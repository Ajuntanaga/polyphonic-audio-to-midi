#include <dirent.h>
#include <sched.h>
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
  const bool ready =
      instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
      instance.component->setActive(Steinberg::TBool{1}) ==
          Steinberg::kResultOk &&
      instance.processor->setProcessing(Steinberg::TBool{1}) ==
          Steinberg::kResultOk;
#if defined(M3_JOINT_RESIDUAL_SHADOW)
  if (ready) {
    m3::vst3::enable_joint_residual_output_for_test(instance.processor, true);
  }
#endif
  return ready;
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

// Register the deadline test only when its assertions actually execute.
// Instrumented/debug native-suite success must never look like a timing pass.
// The dedicated Release m3_vst3_realtime_tests target owns this check.
#if defined(NDEBUG) && !defined(M3_TSAN_ENABLED) && \
    !defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
M3_TEST(vst3_realtime_release_96khz_max8_p99_stays_within_block_budget) {
  constexpr std::uint32_t kFrames = 32U;
  constexpr double kSampleRate = 96000.0;
  // Warm for two seconds so CPU-frequency governors reach their sustained
  // audio-load state before the deadline sample. The former 171 ms warmup was
  // order-dependent under powersave: it passed after a build and failed when
  // reached after low-load functional tests despite identical callback work.
  constexpr std::size_t kWarmupBlocks = 6000U;
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

#if defined(M3_JOINT_RESIDUAL_SHADOW)
  const auto residual_warmup =
      m3::vst3::joint_residual_shadow_work_for_test(instance.processor);
  M3_EXPECT_TRUE(residual_warmup.valid_frames > 0U);
  m3::vst3::clear_joint_residual_shadow_metrics_for_test(instance.processor);
  const auto residual_before =
      m3::vst3::joint_residual_shadow_work_for_test(instance.processor);
  M3_EXPECT_EQ(residual_before.evaluated_frames, 0U);
  M3_EXPECT_EQ(residual_before.max_pitch_count, 0U);
#endif

  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  struct CallbackTiming final {
    std::uint64_t wall_ns{};
    std::uint64_t cpu_ns{};
    int cpu_before{-1};
    int cpu_after{-1};
    m3::PolyphonicPitchDetector::SelectionWork selection{};
  };
  // Preserve paired observations: separately sorted percentiles cannot tell
  // whether a slow wall sample also consumed more detector CPU time. Read CPU
  // placement outside the timed region and print only after measurements.
  std::array<CallbackTiming, kMeasuredBlocks> callback_timings{};
  std::array<std::uint64_t, kMeasuredBlocks> wall_durations{};
  std::array<std::uint64_t, kMeasuredBlocks> cpu_durations{};
  m3::PolyphonicPitchDetector::SelectionWork maximum_selection_work{};
  for (std::size_t iteration = 0U; iteration < kMeasuredBlocks; ++iteration) {
    fill_input();
#if defined(M3_JOINT_RESIDUAL_SHADOW)
    // Force repeated rebuilds during the measured callbacks. Reset only the
    // shadow factor cache, never the detector or MIDI state. At 32 frames per
    // block, 192 blocks allow the worst 88-decision rebuild to finish.
    if (iteration % 192U == 0U) {
      m3::vst3::reset_joint_residual_shadow_for_test(instance.processor);
    }
#endif
    timespec cpu_begin{};
    timespec cpu_end{};
    const int cpu_before = sched_getcpu();
    const auto wall_begin = std::chrono::steady_clock::now();
    M3_EXPECT_EQ(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_begin), 0);
    const Steinberg::tresult result = instance.processor->process(block.data());
    M3_EXPECT_EQ(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_end), 0);
    const auto wall_end = std::chrono::steady_clock::now();
    const int cpu_after = sched_getcpu();
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
    callback_timings[iteration] = {
        wall_durations[iteration], cpu_durations[iteration],
        cpu_before, cpu_after, selection_work};
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
  // Keep successful measurements visible for controlled performance comparisons;
  // a passing assertion alone does not show whether an optimization helped.
  std::fprintf(stderr,
               "96 kHz callback timing: wall-p99=%llu ns wall-max=%llu ns "
               "cpu-max=%llu ns budgets=%llu/%llu ns "
               "pool=%u edges=%u transitions=%u\n",
               static_cast<unsigned long long>(wall_durations[p99_index]),
               static_cast<unsigned long long>(wall_durations.back()),
               static_cast<unsigned long long>(cpu_durations.back()),
               static_cast<unsigned long long>(kP99BudgetNanoseconds),
               static_cast<unsigned long long>(kMaximumBudgetNanoseconds),
               maximum_selection_work.pool_candidates,
               maximum_selection_work.assignment_edges,
               maximum_selection_work.state_transitions);
  std::size_t wall_over_p99 = 0U;
  std::size_t cpu_over_p99 = 0U;
  std::size_t wall_over_deadline = 0U;
  std::size_t cpu_over_deadline = 0U;
  std::size_t migrated_callbacks = 0U;
  std::size_t migrated_between_callbacks = 0U;
  std::size_t placement_unavailable = 0U;
  struct CoreTiming final {
    std::size_t callbacks{};
    std::size_t wall_over_p99{};
    std::size_t cpu_over_p99{};
    std::uint64_t cpu_max_ns{};
  };
  std::array<CoreTiming, CPU_SETSIZE> core_timings{};
  std::array<std::size_t, kMeasuredBlocks> timing_order{};
  for (std::size_t index = 0U; index < callback_timings.size(); ++index) {
    const auto& timing = callback_timings[index];
    timing_order[index] = index;
    wall_over_p99 += timing.wall_ns >= kP99BudgetNanoseconds ? 1U : 0U;
    cpu_over_p99 += timing.cpu_ns >= kP99BudgetNanoseconds ? 1U : 0U;
    wall_over_deadline +=
        timing.wall_ns >= kMaximumBudgetNanoseconds ? 1U : 0U;
    cpu_over_deadline +=
        timing.cpu_ns >= kMaximumBudgetNanoseconds ? 1U : 0U;
    if (timing.cpu_before < 0 || timing.cpu_after < 0) {
      ++placement_unavailable;
      continue;
    }
    migrated_callbacks += timing.cpu_before != timing.cpu_after ? 1U : 0U;
    if (index > 0U && callback_timings[index - 1U].cpu_after >= 0) {
      migrated_between_callbacks +=
          timing.cpu_before != callback_timings[index - 1U].cpu_after ? 1U : 0U;
    }
    if (timing.cpu_before == timing.cpu_after &&
        timing.cpu_before < CPU_SETSIZE) {
      auto& core = core_timings[static_cast<std::size_t>(timing.cpu_before)];
      ++core.callbacks;
      core.wall_over_p99 += timing.wall_ns >= kP99BudgetNanoseconds ? 1U : 0U;
      core.cpu_over_p99 += timing.cpu_ns >= kP99BudgetNanoseconds ? 1U : 0U;
      core.cpu_max_ns = std::max(core.cpu_max_ns, timing.cpu_ns);
    }
  }
  std::fprintf(stderr,
      "Paired callback timing: samples=%zu cpu-p99=%llu ns "
      "wall-over-p99=%zu cpu-over-p99=%zu wall-over-deadline=%zu "
      "cpu-over-deadline=%zu migrated-callbacks=%zu "
      "migrated-between=%zu placement-unavailable=%zu\n",
      kMeasuredBlocks,
      static_cast<unsigned long long>(cpu_durations[p99_index]),
      wall_over_p99, cpu_over_p99, wall_over_deadline, cpu_over_deadline,
      migrated_callbacks, migrated_between_callbacks, placement_unavailable);
  for (std::size_t core = 0U; core < core_timings.size(); ++core) {
    const auto& timing = core_timings[core];
    if (timing.callbacks == 0U) {
      continue;
    }
    std::fprintf(stderr,
        "Callback CPU %zu: samples=%zu wall-over-p99=%zu cpu-over-p99=%zu "
        "cpu-max=%llu ns\n",
        core, timing.callbacks, timing.wall_over_p99, timing.cpu_over_p99,
        static_cast<unsigned long long>(timing.cpu_max_ns));
  }
  const auto print_slowest = [&](const char* label, bool by_cpu) {
    std::sort(timing_order.begin(), timing_order.end(),
        [&](std::size_t left, std::size_t right) {
          const auto left_ns = by_cpu ? callback_timings[left].cpu_ns
                                      : callback_timings[left].wall_ns;
          const auto right_ns = by_cpu ? callback_timings[right].cpu_ns
                                       : callback_timings[right].wall_ns;
          return left_ns != right_ns ? left_ns > right_ns : left < right;
        });
    for (std::size_t rank = 0U; rank < 8U; ++rank) {
      const std::size_t index = timing_order[rank];
      const auto& timing = callback_timings[index];
      std::fprintf(stderr,
          "Slow callback %s: rank=%zu block=%zu wall=%llu ns cpu=%llu ns "
          "cpu-placement=%d/%d pool=%u edges=%u transitions=%u\n",
          label, rank, index,
          static_cast<unsigned long long>(timing.wall_ns),
          static_cast<unsigned long long>(timing.cpu_ns),
          timing.cpu_before, timing.cpu_after,
          timing.selection.pool_candidates, timing.selection.assignment_edges,
          timing.selection.state_transitions);
    }
  };
  print_slowest("wall", false);
  print_slowest("cpu", true);
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
#if defined(M3_JOINT_RESIDUAL_SHADOW)
  const auto residual_after =
      m3::vst3::joint_residual_shadow_work_for_test(instance.processor);
  M3_EXPECT_TRUE(residual_after.valid_frames > residual_before.valid_frames);
  M3_EXPECT_TRUE(residual_after.pending_frames > residual_before.pending_frames);
  M3_EXPECT_EQ(residual_after.max_rebuild_work, 4U);
  M3_EXPECT_EQ(residual_after.max_pitch_count, 8U);
  std::fprintf(stderr,
      "Residual shadow: evaluated=%llu valid=%llu pending=%llu work-max=%u pitches-max=%u\n",
      static_cast<unsigned long long>(residual_after.evaluated_frames - residual_before.evaluated_frames),
      static_cast<unsigned long long>(residual_after.valid_frames - residual_before.valid_frames),
      static_cast<unsigned long long>(residual_after.pending_frames - residual_before.pending_frames),
      residual_after.max_rebuild_work, residual_after.max_pitch_count);
#endif
  close_instance(instance);
}
#endif
