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
      << "end_sample\tnote\thistory\tvalid\treason"
         "\tthird_bin\tthird_hz\tthird_cents\tthird_power\tthird_reference\tthird_prominence"
         "\tfifth_bin\tfifth_hz\tfifth_cents\tfifth_power\tfifth_reference\tfifth_prominence\n";
  cues << "m3_frozen_note_cues_v1\t96000\t1024\n";
  Cue measurement;
  const auto prepare_start = Clock::now();
  if (!measurement.prepare(96000U)) return 1;
  const auto prepare_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - prepare_start).count();
  std::vector<std::uint64_t> blocks, transforms;
  blocks.reserve((samples.size() + kBlock - 1U) / kBlock);
  transforms.reserve(samples.size() / Cue::kHop);
  std::size_t frames = 0U;
  for (std::size_t begin = 0U; begin < samples.size(); begin += kBlock) {
    const auto end = std::min(begin + kBlock, samples.size());
    bool produced = false;
    const auto start = Clock::now();
    for (auto index = begin; index < end; ++index) produced = measurement.push(samples[index]) || produced;
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    blocks.push_back(static_cast<std::uint64_t>(elapsed));
    if (!produced) continue;
    const auto& frame = measurement.frame();
    if (frame.valid) transforms.push_back(static_cast<std::uint64_t>(elapsed));
    ++frames;
    // Export and timing storage are outside the measured processing block.
    for (std::size_t index = 0U; index < Cue::kNotes; ++index) {
      const auto midi = index + Cue::kFirstNote;
      const auto& note = frame.notes[index];
      observations << frame.end_sample << '\t' << midi << '\t' << frame.history_available
                   << '\t' << frame.valid << '\t' << Cue::reason_name(note.reason);
      write_peak(observations, note.third);
      write_peak(observations, note.fifth);
      observations << '\n';
      if (frame.valid && frame.end_sample < samples.size() && note.reason == Cue::Reason::cue) {
        cues << frame.end_sample << '\t'
             << std::min(frame.end_sample + Cue::kHop, static_cast<std::uint64_t>(samples.size()))
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
         << ",\"blocks\":" << blocks.size() << ",\"analysis_frames\":" << frames
         << ",\"transform_blocks\":" << transforms.size()
         << ",\"prepare_ns\":" << prepare_ns << ",\"storage_bytes\":" << Cue::storage_bytes()
         << ",\"block_p50_ns\":" << percentile(blocks, 0.5)
         << ",\"block_p99_ns\":" << percentile(blocks, 0.99)
         << ",\"block_max_ns\":" << percentile(blocks, 1.0)
         << ",\"transform_p50_ns\":" << percentile(transforms, 0.5)
         << ",\"transform_p99_ns\":" << percentile(transforms, 0.99)
         << ",\"transform_max_ns\":" << percentile(transforms, 1.0)
         << ",\"block_deadline_ns\":333333,\"p99_budget_ns\":166666}\n";
  observations.flush(); cues.flush(); timing.flush();
  return observations && cues && timing ? 0 : 1;
}
