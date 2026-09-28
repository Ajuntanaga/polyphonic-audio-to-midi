#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <vector>

#include "m3/constants.hpp"
#include "m3/pitch_math.hpp"
#include "m3/polyphonic_pitch_detector.hpp"

namespace {

constexpr double kTwoPi = 6.28318530717958647692;
constexpr std::array<double, 4U> kSampleRates{
    44100.0, 48000.0, 88200.0, 96000.0};
constexpr std::array<std::size_t, 6U> kBlockSizes{
    32U, 64U, 128U, 256U, 512U, 1024U};
constexpr std::array<double, m3::kMaxVoices> kDetuneCents{
    -7.0, -5.0, -3.0, -1.0, 1.0, 3.0, 5.0, 7.0};

enum class Scenario : std::uint8_t { dense_eight, calibrated_unison_four };

const char* scenario_name(Scenario scenario) noexcept {
  return scenario == Scenario::dense_eight ? "dense_eight"
                                            : "calibrated_unison_four";
}

m3::StringCalibrationBank calibration_bank() noexcept {
  m3::StringCalibrationBank bank;
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
      m3::StringCalibrationPoint& point = bank.points[string][fret];
      point.cents_offset_q8 = static_cast<std::int16_t>(
          std::lround(kDetuneCents[string] * 256.0));
      const std::array<double, m3::kCalibrationHarmonicCount> shape{
          1.0,
          0.16 + 0.025 * static_cast<double>(string),
          0.08 + 0.013 * static_cast<double>((string + 3U) % 5U),
          0.04 + 0.011 * static_cast<double>((string + 1U) % 4U),
          0.02 + 0.007 * static_cast<double>((string + 2U) % 3U),
          0.01 + 0.004 * static_cast<double>(string % 3U)};
      double energy = 0.0;
      for (const double value : shape) {
        energy += value * value;
      }
      for (std::size_t harmonic = 0U; harmonic < shape.size(); ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                32767.0 * shape[harmonic] * shape[harmonic] / energy));
      }
      point.confidence_q15 = 32767U;
      point.observation_count = 128U;
      point.quality = m3::CalibrationPointQuality::measured;
    }
    bank.calibrated_string_mask = static_cast<std::uint8_t>(
        bank.calibrated_string_mask | (1U << string));
  }
  return bank;
}

double source_sample(Scenario scenario, std::uint64_t sample_index,
                     double sample_rate) noexcept {
  const double time = static_cast<double>(sample_index) / sample_rate;
  double value = 0.0;
  if (scenario == Scenario::dense_eight) {
    for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
      const double string_number = static_cast<double>(string);
      const double pitch = static_cast<double>(m3::kM3OpenNotes[string]) +
                           kDetuneCents[string] / 100.0;
      const double phase = kTwoPi * m3::midi_to_frequency(pitch, 440.0) * time +
                           0.37 * static_cast<double>(string);
      value += 0.018 *
               (std::sin(phase) +
                0.24 * std::sin(2.0 * phase + 0.11 * string_number) +
                0.10 * std::sin(3.0 * phase - 0.07 * string_number));
    }
    return value;
  }
  constexpr std::uint8_t kSharedNote = 60U;
  for (std::size_t string = 4U; string < 8U; ++string) {
    const double string_number = static_cast<double>(string);
    const double pitch = static_cast<double>(kSharedNote) +
                         kDetuneCents[string] / 100.0;
    const double phase = kTwoPi * m3::midi_to_frequency(pitch, 440.0) * time +
                         0.43 * static_cast<double>(string);
    value += 0.030 *
             (std::sin(phase) +
              (0.16 + 0.025 * string_number) *
                  std::sin(2.0 * phase + 0.17 * string_number) +
              (0.08 + 0.013 * static_cast<double>((string + 3U) % 5U)) *
                  std::sin(3.0 * phase - 0.09 * string_number));
  }
  return value;
}

double percentile(const std::vector<double>& sorted, double fraction) noexcept {
  if (sorted.empty()) {
    return 0.0;
  }
  const double position = fraction * static_cast<double>(sorted.size() - 1U);
  const std::size_t lower = static_cast<std::size_t>(std::floor(position));
  const std::size_t upper = static_cast<std::size_t>(std::ceil(position));
  const double mix = position - static_cast<double>(lower);
  return sorted[lower] + (sorted[upper] - sorted[lower]) * mix;
}

}  // namespace

int main() {
  std::printf(
      "scope\tscenario\tsample_rate\tblock\tblocks\tmedian_ratio\t"
      "p95_ratio\tp99_ratio\tmax_ratio\ttransitions\tchecksum\n");
  const m3::StringCalibrationBank bank = calibration_bank();
  std::uint64_t total_checksum = 0U;
  for (const Scenario scenario :
       {Scenario::dense_eight, Scenario::calibrated_unison_four}) {
    for (const double sample_rate : kSampleRates) {
      m3::PersistentConfig config;
      config.profile_mode = m3::ProfileMode::m3;
      config.midi_routing = m3::MidiRouting::per_voice;
      config.lowest_note = 32U;
      config.highest_note = 84U;
      config.max_polyphony = 8U;
      config.max_fret = 24U;
      config.sensitivity = 70U;
      config.response = 81U;
      m3::PolyphonicPitchDetector detector;
      if (!detector.configure(sample_rate, config)) {
        return 1;
      }
      detector.set_calibration_bank(bank);
      std::uint64_t source_index = 0U;
      const std::uint64_t warmup_samples =
          static_cast<std::uint64_t>(std::ceil(sample_rate * 3.0));
      for (; source_index < warmup_samples; ++source_index) {
        static_cast<void>(detector.process_sample(
            source_sample(scenario, source_index, sample_rate)));
      }
      for (const std::size_t block_size : kBlockSizes) {
        const std::size_t block_count = std::max<std::size_t>(
            128U, static_cast<std::size_t>(
                      std::ceil(sample_rate * 0.75 /
                                static_cast<double>(block_size))));
        std::vector<double> samples(block_count * block_size);
        for (std::size_t index = 0U; index < samples.size(); ++index) {
          samples[index] = source_sample(
              scenario, source_index + index, sample_rate);
        }
        source_index += samples.size();
        std::vector<double> ratios;
        ratios.reserve(block_count);
        std::uint32_t transitions = 0U;
        std::uint64_t row_checksum = 0U;
        for (std::size_t block = 0U; block < block_count; ++block) {
          const auto started = std::chrono::steady_clock::now();
          for (std::size_t frame = 0U; frame < block_size; ++frame) {
            const m3::DetectorDecision decision = detector.process_sample(
                samples[block * block_size + frame]);
            transitions +=
                static_cast<std::uint32_t>(decision.transitions.size());
            row_checksum += decision.tuner_snapshot_ready
                                ? decision.tuner_snapshot.voice_count
                                : 0U;
          }
          const auto stopped = std::chrono::steady_clock::now();
          const double elapsed =
              std::chrono::duration<double>(stopped - started).count();
          const double deadline =
              static_cast<double>(block_size) / sample_rate;
          ratios.push_back(elapsed / deadline);
        }
        std::sort(ratios.begin(), ratios.end());
        total_checksum += row_checksum + transitions;
        std::printf(
            "detector_core\t%s\t%.0f\t%zu\t%zu\t%.9f\t%.9f\t"
            "%.9f\t%.9f\t%u\t%llu\n",
            scenario_name(scenario), sample_rate, block_size, block_count,
            percentile(ratios, 0.50), percentile(ratios, 0.95),
            percentile(ratios, 0.99), ratios.back(), transitions,
            static_cast<unsigned long long>(row_checksum));
      }
    }
  }
  return total_checksum == 0U ? 1 : 0;
}
