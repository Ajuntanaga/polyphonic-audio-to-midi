#include "frozen_cue_worker.hpp"
#include "offline_c_allocation_guard.hpp"
#include "test_support.hpp"

#include <chrono>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <thread>
#include <vector>

#if defined(__linux__)
#include <sys/prctl.h>
#endif

namespace {
using namespace m3::offline;
using Clock = std::chrono::steady_clock;
using Nanoseconds = std::chrono::nanoseconds;
constexpr std::uint64_t kHybridPollLead = 384U;
static_assert(kHybridPollLead < FrozenPartialCue::kHop);
long timer_slack() noexcept {
#if defined(__linux__)
  return ::prctl(PR_GET_TIMERSLACK, 0UL, 0UL, 0UL, 0UL);
#else
  return -1L;
#endif
}
bool set_timer_slack(unsigned long value) noexcept {
#if defined(__linux__)
  if (::prctl(PR_SET_TIMERSLACK, value, 0UL, 0UL, 0UL) != 0) return false;
  const auto actual = timer_slack();
  return actual > 0L && static_cast<unsigned long>(actual) == value;
#else
  (void)value;
  return false;
#endif
}
bool parse_slack(const char* text, unsigned long& value) noexcept {
  if (!text || *text == '\0' || *text == '-') return false;
  char* end = nullptr;
  errno = 0;
  value = std::strtoul(text, &end, 10);
  return errno != ERANGE && end && *end == '\0' &&
      value <= static_cast<unsigned long>(std::numeric_limits<int>::max());
}
struct Observation final {
  std::uint64_t begin{};
  std::array<std::uint64_t, 2U> mask{};
  bool operator==(const Observation& other) const noexcept {
    return begin == other.begin && mask == other.mask;
  }
};
struct StepTiming final {
  std::uint64_t start{}, finish{}, samples{};
};
std::uint64_t ns(Clock::duration value) noexcept {
  const auto count = std::chrono::duration_cast<Nanoseconds>(value).count();
  return count > 0 ? static_cast<std::uint64_t>(count) : 0U;
}
std::uint64_t sample_time(std::size_t sample) noexcept {
  return static_cast<std::uint64_t>(sample) * 1000000000ULL / 96000ULL;
}
std::uint64_t tick(Clock::time_point value) noexcept { return ns(value.time_since_epoch()); }
std::int64_t relative_ns(std::uint64_t value, std::uint64_t origin) noexcept {
  return value >= origin ? static_cast<std::int64_t>(value - origin)
                         : -static_cast<std::int64_t>(origin - value);
}
std::uint64_t percentile(std::vector<std::uint64_t>& values, double fraction) {
  if (values.empty()) return 0U;
  std::sort(values.begin(), values.end());
  const auto index = static_cast<std::size_t>(std::ceil(fraction * static_cast<double>(values.size()))) - 1U;
  return values[std::min(index, values.size() - 1U)];
}
void write_timing(std::ostream& out, const char* label, std::vector<std::uint64_t>& values) {
  out << ",\"" << label << "_p50_ns\":" << percentile(values, 0.5)
      << ",\"" << label << "_p99_ns\":" << percentile(values, 0.99)
      << ",\"" << label << "_max_ns\":" << percentile(values, 1.0);
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 4 && argc != 6 && argc != 8) {
    std::fprintf(stderr, "usage: m3_frozen_cue_worker_probe raw-float32le-96k block-size report.json [pace-slack-ns worker-slack-ns [pace-poll worker-wait-mode(0=sleep,1=poll,2=hybrid)]]\n");
    return 1;
  }
  unsigned long pace_slack = 0UL, worker_slack = 0UL;
  if (argc >= 6 && (!parse_slack(argv[4], pace_slack) || !parse_slack(argv[5], worker_slack))) return 1;
  unsigned long pace_poll = 0UL, worker_wait_mode = 0UL;
  if (argc == 8 && (!parse_slack(argv[6], pace_poll) || !parse_slack(argv[7], worker_wait_mode) ||
                   pace_poll > 1UL || worker_wait_mode > 2UL)) return 1;
  char* end = nullptr;
  const auto parsed = std::strtoul(argv[2], &end, 10);
  if (*argv[2] == '\0' || !end || *end != '\0' ||
      (parsed != 32UL && parsed != 512UL && parsed != 1024UL)) return 1;
  const auto block_size = static_cast<std::size_t>(parsed);
  const std::uint32_t endian = 1U;
  if (*reinterpret_cast<const unsigned char*>(&endian) != 1U || sizeof(float) != 4U) return 1;
  auto* file = std::fopen(argv[1], "rb");
  if (!file) return 1;
  if (std::fseek(file, 0L, SEEK_END) != 0) { std::fclose(file); return 1; }
  const auto bytes = std::ftell(file);
  if (bytes <= 0L || bytes > 128L * 1024L * 1024L || bytes % 4L != 0L ||
      std::fseek(file, 0L, SEEK_SET) != 0) { std::fclose(file); return 1; }
  std::vector<float> samples(static_cast<std::size_t>(bytes) / sizeof(float));
  const auto read = std::fread(samples.data(), sizeof(float), samples.size(), file);
  std::fclose(file);
  if (read != samples.size() || std::any_of(samples.begin(), samples.end(),
        [](float value) { return !std::isfinite(value); })) return 1;

  // Reference work, allocations and thread startup are outside the paced run.
  std::vector<Observation> expected(samples.size()), observed(samples.size());
  FrozenPartialCue reference;
  if (!reference.prepare(96000U)) return 1;
  std::uint64_t expected_frames = 0U, cue_samples = 0U;
  for (std::size_t i = 0U; i < samples.size(); ++i) {
    if (!reference.push(samples[i])) continue;
    const auto& frame = reference.frame();
    const auto begin = frame.end_sample + kCueWorkerDelay;
    if (begin >= samples.size()) continue;
    ++expected_frames;
    const auto stop = std::min<std::uint64_t>(samples.size(), begin + FrozenPartialCue::kHop);
    for (auto j = begin; j < stop; ++j) {
      expected[static_cast<std::size_t>(j)] = {begin, frame.mask};
      if (frame.mask[0U] || frame.mask[1U]) ++cue_samples;
    }
  }
  const auto block_count = (samples.size() + block_size - 1U) / block_size;
  std::vector<std::uint64_t> callbacks(block_count), wake_late(block_count), worker_times(block_count);
  // Store the timestamps already taken by the timing probe. Diagnosis is
  // performed after joining, without adding clock calls or allocations to
  // either measured path.
  std::vector<std::uint64_t> callback_starts(block_count), callback_finishes(block_count);
  std::vector<StepTiming> worker_steps(block_count);
  FrozenCueInputQueue input;
  FrozenCueOutputQueue output;
  FrozenCueClient client(input, output);
  FrozenCueWorker worker(input, output);
  if (!worker.prepare()) return 1;
  // Process-local diagnostic only. Zero preserves the original setting on
  // each thread, even when its creating thread has a diagnostic override.
  const auto original_slack = timer_slack();
  if ((pace_slack || worker_slack) && original_slack <= 0L) return 1;
  if (pace_slack && !set_timer_slack(pace_slack)) return 1;
  const auto pace_effective_slack = timer_slack();
  long worker_inherited_slack = -1L, worker_effective_slack = -1L;
  bool worker_slack_ok = true;
  std::atomic<bool> stop{false}, ready{false};
  static_assert(std::atomic<bool>::is_always_lock_free);
  std::size_t worker_count = 0U;
  std::thread background([&]() {
    worker_inherited_slack = timer_slack();
    if (pace_slack || worker_slack) {
      worker_slack_ok = set_timer_slack(worker_slack ? worker_slack : static_cast<unsigned long>(original_slack));
    }
    worker_effective_slack = timer_slack();
    ready.store(true, std::memory_order_release);
    if (!worker_slack_ok) return;
    while (true) {
      const auto start = Clock::now();
      if (worker.step()) {
        const auto finish = Clock::now();
        if (worker_count < worker_times.size()) {
          worker_times[worker_count] = ns(finish - start);
          worker_steps[worker_count] = {tick(start), tick(finish), worker.stats().samples};
          ++worker_count;
        }
      } else {
        if (stop.load(std::memory_order_acquire)) break;
        // Both polling policies are standalone diagnostics, outside the
        // measured callback. This uninterrupted recording has no resets;
        // worker-owned sample progress locates its next calculation hop.
        const bool near_hop = worker.stats().samples % FrozenPartialCue::kHop >=
            FrozenPartialCue::kHop - kHybridPollLead;
        if (worker_wait_mode == 1UL || (worker_wait_mode == 2UL && near_hop))
          std::atomic_signal_fence(std::memory_order_seq_cst);
        else std::this_thread::sleep_for(std::chrono::microseconds(25));
      }
    }
  });
  while (!ready.load(std::memory_order_acquire)) std::this_thread::yield();
  if (!worker_slack_ok) { background.join(); return 1; }
  const auto wall_before = Clock::now();
  const auto cpu_before = std::clock();
  const auto start = Clock::now() + std::chrono::milliseconds(10);
  const auto cpp_before = m3::test::allocation_count(), cpp_free_before = m3::test::deallocation_count();
  const auto c_before = m3::test::c_allocation_count(), c_free_before = m3::test::c_deallocation_count();
  std::uint64_t callback_overruns = 0U, wake_missed_periods = 0U;
  const auto deadline = sample_time(block_size);
  for (std::size_t block = 0U, begin = 0U; begin < samples.size(); ++block, begin += block_size) {
    const auto scheduled = start + Nanoseconds(sample_time(begin));
    // Busy pacing removes the test driver's sleep as one possible cause of
    // lateness. It is outside callback timing and recorded as CPU cost.
    if (pace_poll) {
      while (Clock::now() < scheduled) std::atomic_signal_fence(std::memory_order_seq_cst);
    } else std::this_thread::sleep_until(scheduled);
    const auto entered = Clock::now();
    wake_late[block] = ns(entered - scheduled);
    if (wake_late[block] > deadline) ++wake_missed_periods;
    const auto count = std::min(block_size, samples.size() - begin);
    const auto callback_start = Clock::now();
    client.submit(samples.data() + begin, count, begin);
    for (std::size_t i = 0U; i < count; ++i) {
      const auto& frame = client.advance(begin + i);
      observed[begin + i] = {frame.begin, frame.mask};
    }
    const auto callback_finish = Clock::now();
    callbacks[block] = ns(callback_finish - callback_start);
    callback_starts[block] = tick(callback_start);
    callback_finishes[block] = tick(callback_finish);
    if (callbacks[block] > sample_time(count)) ++callback_overruns;
  }
  const auto cpp_allocations = m3::test::allocation_count() - cpp_before;
  const auto cpp_deallocations = m3::test::deallocation_count() - cpp_free_before;
  const auto c_allocations = m3::test::c_allocation_count() - c_before;
  const auto c_deallocations = m3::test::c_deallocation_count() - c_free_before;
  stop.store(true, std::memory_order_release);
  background.join();
  const auto cpu_after = std::clock();
  const auto elapsed_ns = ns(Clock::now() - wall_before);
  const auto process_cpu_ns = cpu_before != static_cast<std::clock_t>(-1) &&
      cpu_after != static_cast<std::clock_t>(-1) && cpu_after >= cpu_before
      ? static_cast<long long>(static_cast<double>(cpu_after - cpu_before) *
                               1.0e9 / static_cast<double>(CLOCKS_PER_SEC)) : -1LL;
  worker_times.resize(worker_count);

  std::uint64_t differing_samples = 0U, mask_differences = 0U, lost_cue_samples = 0U, extra_cue_samples = 0U;
  for (std::size_t i = 0U; i < samples.size(); ++i) {
    if (!(observed[i] == expected[i])) ++differing_samples;
    if (observed[i].mask != expected[i].mask) ++mask_differences;
    if ((expected[i].mask[0U] & ~observed[i].mask[0U]) ||
        (expected[i].mask[1U] & ~observed[i].mask[1U])) ++lost_cue_samples;
    if ((observed[i].mask[0U] & ~expected[i].mask[0U]) ||
        (observed[i].mask[1U] & ~expected[i].mask[1U])) ++extra_cue_samples;
  }
  const auto& audio = client.stats();
  const auto& work = worker.stats();
  const bool delivery_pass = differing_samples == 0U && audio.accepted == expected_frames &&
      audio.late == 0U && audio.stale == 0U && audio.input_drops == 0U && work.output_drops == 0U &&
      work.samples == samples.size() && work.discontinuities == 0U;
  const bool allocation_pass = cpp_allocations == 0U && cpp_deallocations == 0U &&
      c_allocations == 0U && c_deallocations == 0U;
  const bool callback_pass = percentile(callbacks, 0.99) <= deadline / 2U && callback_overruns == 0U;
  std::ofstream report(argv[3]);
  report << std::boolalpha << "{\"sample_rate\":96000,\"sample_count\":" << samples.size()
         << ",\"block_size\":" << block_size << ",\"blocks\":" << block_count
         << ",\"timer_slack_original_ns\":" << original_slack
         << ",\"pace_slack_requested_ns\":" << pace_slack
         << ",\"pace_slack_effective_ns\":" << pace_effective_slack
         << ",\"worker_slack_requested_ns\":" << worker_slack
         << ",\"worker_slack_inherited_ns\":" << worker_inherited_slack
         << ",\"worker_slack_effective_ns\":" << worker_effective_slack
         << ",\"pace_poll\":" << (pace_poll != 0UL)
         << ",\"worker_poll\":" << (worker_wait_mode == 1UL)
         << ",\"worker_wait_mode\":" << worker_wait_mode
         << ",\"worker_poll_lead_samples\":" << (worker_wait_mode == 2UL ? kHybridPollLead : 0U)
         << ",\"elapsed_ns\":" << elapsed_ns << ",\"process_cpu_ns\":" << process_cpu_ns
         << ",\"delay_samples\":" << kCueWorkerDelay << ",\"queue_capacity\":" << kCueQueueCapacity
         << ",\"expected_frames\":" << expected_frames << ",\"delivered_frames\":" << audio.accepted
         << ",\"late_frames\":" << audio.late << ",\"stale_frames\":" << audio.stale
         << ",\"input_drops\":" << audio.input_drops << ",\"output_drops\":" << work.output_drops
         << ",\"worker_samples\":" << work.samples << ",\"worker_frames\":" << work.frames
         << ",\"worker_discontinuities\":" << work.discontinuities
         << ",\"differing_samples\":" << differing_samples << ",\"mask_differences\":" << mask_differences
         << ",\"expected_cue_samples\":" << cue_samples << ",\"lost_cue_samples\":" << lost_cue_samples
         << ",\"extra_cue_samples\":" << extra_cue_samples << ",\"callback_overruns\":" << callback_overruns
         << ",\"wake_missed_periods\":" << wake_missed_periods
         << ",\"cpp_allocations\":" << cpp_allocations << ",\"cpp_deallocations\":" << cpp_deallocations
         << ",\"c_allocations\":" << c_allocations << ",\"c_deallocations\":" << c_deallocations
         << ",\"callback_deadline_ns\":" << deadline << ",\"callback_p99_budget_ns\":" << deadline / 2U
         << ",\"delivery_pass\":" << delivery_pass << ",\"allocation_pass\":" << allocation_pass
         << ",\"callback_pass\":" << callback_pass;
  std::uint64_t missing_frames = 0U, missing_empty_frames = 0U;
  std::uint64_t worker_not_started_before_deadline = 0U, worker_finished_after_deadline = 0U;
  std::uint64_t minimum_available_ns = std::numeric_limits<std::uint64_t>::max();
  std::size_t emitted = 0U;
  report << ",\"missed_frame_trace\":[";
  for (std::size_t begin = FrozenPartialCue::kHop + kCueWorkerDelay;
       begin < samples.size(); begin += FrozenPartialCue::kHop) {
    const auto end_sample = begin - kCueWorkerDelay;
    const auto producer = (end_sample - 1U) / block_size;
    const auto target = begin / block_size;
    const auto available = callback_starts[target] - callback_starts[producer];
    minimum_available_ns = std::min(minimum_available_ns, available);
    if (observed[begin].begin == expected[begin].begin) continue;
    ++missing_frames;
    const bool empty = expected[begin].mask[0U] == 0U && expected[begin].mask[1U] == 0U;
    if (empty) ++missing_empty_frames;
    const auto last = worker_steps.begin() + static_cast<std::ptrdiff_t>(worker_count);
    const auto step = std::lower_bound(worker_steps.begin(), last, end_sample,
        [](const StepTiming& value, std::size_t sample) { return value.samples < sample; });
    if (step == last) continue;
    if (step->start > callback_finishes[target]) ++worker_not_started_before_deadline;
    if (step->finish > callback_finishes[target]) ++worker_finished_after_deadline;
    if (emitted >= 32U) continue;
    if (emitted++) report << ',';
    const auto origin = callback_starts[producer];
    report << "{\"cue_begin_sample\":" << begin << ",\"empty_mask\":" << empty
           << ",\"input_block_begin_sample\":" << producer * block_size
           << ",\"input_callback_duration_ns\":" << callback_finishes[producer] - origin
           << ",\"input_wake_lateness_ns\":" << wake_late[producer]
           << ",\"target_callback_start_after_input_ns\":" << available
           << ",\"target_callback_finish_after_input_ns\":" << callback_finishes[target] - origin
           << ",\"worker_start_after_input_ns\":" << relative_ns(step->start, origin)
           << ",\"worker_finish_after_input_ns\":" << relative_ns(step->finish, origin)
           << ",\"worker_step_duration_ns\":" << step->finish - step->start << '}';
  }
  report << "],\"trace_missing_frames\":" << missing_frames
         << ",\"trace_missing_empty_frames\":" << missing_empty_frames
         << ",\"trace_worker_not_started_before_deadline\":" << worker_not_started_before_deadline
         << ",\"trace_worker_finished_after_deadline\":" << worker_finished_after_deadline
         << ",\"minimum_input_to_target_callback_ns\":"
         << (expected_frames ? minimum_available_ns : 0U);
  write_timing(report, "callback", callbacks);
  write_timing(report, "wake_late", wake_late);
  write_timing(report, "worker_step", worker_times);
  report << "}\n";
  report.flush();
  return report ? 0 : 1;
}
