#include "frozen_partial_cue.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <vector>
#if defined(M3_FROZEN_CUE_PFFFT)
#include "pffft_double.h"
#endif
#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
#include "offline_c_allocation_guard.hpp"
#include "test_support.hpp"
#endif

namespace {
using Cue = m3::offline::FrozenPartialCue;
using Clock = std::chrono::steady_clock;
constexpr std::size_t kBlock = 32U;
constexpr long kMaximumBytes = 128L * 1024L * 1024L;

void write_peak(std::ostream& output, const Cue::Peak& peak) {
  if (!peak.found) {
    output << "\t\t\t\t\t\t";
    return;
  }
  output << '\t' << peak.bin << '\t' << peak.frequency_hz << '\t' << peak.cents
         << '\t' << peak.power << '\t';
  if (peak.reference_available) output << peak.reference_power;
  output << '\t';
  if (peak.reference_available) output << peak.prominence_db;
}

std::uint64_t percentile(const std::vector<std::uint64_t>& sorted, double fraction) {
  if (sorted.empty()) return 0U;
  const auto index = static_cast<std::size_t>(std::ceil(fraction * static_cast<double>(sorted.size()))) - 1U;
  return sorted[std::min(index, sorted.size() - 1U)];
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: m3_frozen_cue_probe raw-float32le-96k observations.tsv cues.tsv timing.json\n");
    return 1;
  }
  const std::uint32_t endian = 1U;
  if (*reinterpret_cast<const unsigned char*>(&endian) != 1U || sizeof(float) != 4U) return 1;
  auto* input = std::fopen(argv[1], "rb");
  if (!input) return 1;
  if (std::fseek(input, 0L, SEEK_END) != 0) { std::fclose(input); return 1; }
  const long bytes = std::ftell(input);
  if (bytes <= 0L || bytes > kMaximumBytes || bytes % 4L != 0L ||
      std::fseek(input, 0L, SEEK_SET) != 0) { std::fclose(input); return 1; }
  std::vector<float> samples(static_cast<std::size_t>(bytes) / sizeof(float));
  const auto read = std::fread(samples.data(), sizeof(float), samples.size(), input);
  std::fclose(input);
  if (read != samples.size() || std::any_of(samples.begin(), samples.end(),
        [](float value) { return !std::isfinite(value); })) return 1;

  std::ofstream observations(argv[2]), cues(argv[3]), timing(argv[4]);
  if (!observations || !cues || !timing) return 1;
  observations << std::setprecision(17)
      << "end_sample\tnote\thistory\tvalid\treason\tavailable_sample"
         "\tthird_bin\tthird_hz\tthird_cents\tthird_power\tthird_reference\tthird_prominence"
         "\tfifth_bin\tfifth_hz\tfifth_cents\tfifth_power\tfifth_reference\tfifth_prominence\n";
  cues << "m3_frozen_note_cues_v1\t96000\t1024\n";
  Cue measurement;
  const auto prepare_start = Clock::now();
  if (!measurement.prepare(96000U)) return 1;
  const auto prepare_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - prepare_start).count();
  std::vector<std::uint64_t> blocks, transforms;
  const auto process_samples = samples.size() + Cue::kAvailabilityDelay;
  blocks.reserve((process_samples + kBlock - 1U) / kBlock);
  transforms.reserve(samples.size() / Cue::kHop);
  constexpr std::array<std::size_t, 10U> stage_phases{896U, 928U, 960U, 992U, 0U, 32U, 96U, 160U, 224U, 256U};
  std::array<std::vector<std::uint64_t>, stage_phases.size()> stages;
  for (auto& stage : stages) stage.reserve(process_samples / Cue::kHop + 1U);
  std::size_t frames = 0U, clock_errors = 0U;
  std::uint64_t cpp_allocations = 0U, cpp_frees = 0U, c_allocations = 0U, c_frees = 0U;
  for (std::size_t begin = 0U; begin < process_samples; begin += kBlock) {
    const auto end = std::min(begin + kBlock, process_samples);
    bool produced = false;
    std::size_t available_sample = 0U;
#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
    const auto cpp_alloc_before = m3::test::allocation_count(), cpp_free_before = m3::test::deallocation_count();
    const auto c_alloc_before = m3::test::c_allocation_count(), c_free_before = m3::test::c_deallocation_count();
#endif
    const auto start = Clock::now();
    for (auto index = begin; index < end; ++index) {
      if (measurement.push(index < samples.size() ? samples[index] : 0.0F)) {
        produced = true;
        available_sample = index + 1U;
      }
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
    cpp_allocations += m3::test::allocation_count() - cpp_alloc_before;
    cpp_frees += m3::test::deallocation_count() - cpp_free_before;
    c_allocations += m3::test::c_allocation_count() - c_alloc_before;
    c_frees += m3::test::c_deallocation_count() - c_free_before;
#endif
    blocks.push_back(static_cast<std::uint64_t>(elapsed));
#if defined(M3_FROZEN_CUE_COOPERATIVE)
    const auto phase = end % Cue::kHop;
    if (end >= Cue::kWindow) {
      const auto stage = std::find(stage_phases.begin(), stage_phases.end(), phase);
      if (stage != stage_phases.end()) {
        stages[static_cast<std::size_t>(stage - stage_phases.begin())].push_back(static_cast<std::uint64_t>(elapsed));
      }
    }
#endif
    if (!produced) continue;
    const auto& frame = measurement.frame();
    if (frame.end_sample > samples.size()) continue;
    if (available_sample != frame.end_sample + Cue::kAvailabilityDelay) ++clock_errors;
    if (frame.valid) transforms.push_back(static_cast<std::uint64_t>(elapsed));
    ++frames;
    // Export and timing storage are outside the measured processing block.
    for (std::size_t index = 0U; index < Cue::kNotes; ++index) {
      const auto midi = index + Cue::kFirstNote;
      const auto& note = frame.notes[index];
      observations << frame.end_sample << '\t' << midi << '\t' << frame.history_available
                   << '\t' << frame.valid << '\t' << Cue::reason_name(note.reason)
                   << '\t' << available_sample;
      write_peak(observations, note.third);
      write_peak(observations, note.fifth);
      observations << '\n';
      const auto cue_begin = frame.end_sample + Cue::kAvailabilityDelay;
      if (frame.valid && cue_begin < samples.size() && note.reason == Cue::Reason::cue) {
        cues << cue_begin << '\t'
             << std::min(cue_begin + Cue::kHop, static_cast<std::uint64_t>(samples.size()))
             << '\t' << midi << '\n';
      }
    }
  }
  std::sort(blocks.begin(), blocks.end());
  std::sort(transforms.begin(), transforms.end());
  timing << "{\"fft_backend\":";
#if defined(M3_FROZEN_CUE_PFFFT)
  timing << "\"pffft-double\",\"fft_simd\":\"" << pffftd_simd_arch()
         << "\",\"storage_bytes_excludes_fft_setup\":true";
#else
  timing << "\"reference-radix2\",\"fft_simd\":\"scalar\",\"storage_bytes_excludes_fft_setup\":false";
#endif
  timing << ",\"sample_rate\":96000,\"block_size\":32,\"sample_count\":" << samples.size()
         << ",\"availability_delay_samples\":" << Cue::kAvailabilityDelay
         << ",\"flush_samples\":" << Cue::kAvailabilityDelay
         << ",\"availability_clock_errors\":" << clock_errors
         << ",\"processing_cpp_allocations\":" << cpp_allocations << ",\"processing_cpp_frees\":" << cpp_frees
         << ",\"processing_c_allocations\":" << c_allocations << ",\"processing_c_frees\":" << c_frees
#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
         << ",\"processing_allocation_guarded\":true"
#else
         << ",\"processing_allocation_guarded\":false"
#endif
         << ",\"blocks\":" << blocks.size() << ",\"analysis_frames\":" << frames
         << ",\"transform_blocks\":" << transforms.size()
         << ",\"prepare_ns\":" << prepare_ns << ",\"storage_bytes\":" << Cue::storage_bytes()
         << ",\"block_p50_ns\":" << percentile(blocks, 0.5)
         << ",\"block_p99_ns\":" << percentile(blocks, 0.99)
         << ",\"block_max_ns\":" << percentile(blocks, 1.0)
         << ",\"transform_p50_ns\":" << percentile(transforms, 0.5)
         << ",\"transform_p99_ns\":" << percentile(transforms, 0.99)
         << ",\"transform_max_ns\":" << percentile(transforms, 1.0)
         << ",\"block_deadline_ns\":333333,\"p99_budget_ns\":166666"
         << ",\"overrun_blocks\":" << std::count_if(blocks.begin(), blocks.end(),
              [](std::uint64_t ns) { return ns > 333333U; })
         << ",\"stage_blocks\":[";
  for (std::size_t index = 0U; index < stages.size(); ++index) {
    auto& stage = stages[index];
    std::sort(stage.begin(), stage.end());
    if (index) timing << ',';
    timing << "{\"stage\":" << index << ",\"phase_samples\":" << stage_phases[index]
           << ",\"count\":" << stage.size()
           << ",\"p99_ns\":" << percentile(stage, 0.99) << ",\"max_ns\":" << percentile(stage, 1.0) << '}';
  }
  timing << "]}\n";
  observations.flush(); cues.flush(); timing.flush();
  return observations && cues && timing ? 0 : 1;
}
