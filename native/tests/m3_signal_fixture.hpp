#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/pitch_math.hpp"
#include "m3/string_calibration.hpp"

namespace m3::test_signal {

inline constexpr double kTwoPi = 6.28318530717958647692;

struct PluckedStringModel final {
  double detune_cents{};
  double phase{};
  double level{};
  double decay_seconds{};
  double onset_seconds{};
  std::array<double, kCalibrationHarmonicCount> harmonics{};
};

// Deterministic, deliberately non-identical string models. They complement the
// retained physical calibration fixture with a repeatable causal stress corpus
// whose phases, levels, detuning, decay, and harmonic fingerprints are fully
// controlled in tests; they are not substitutes for the recorded waveforms.
inline constexpr std::array<PluckedStringModel, kMaxVoices> kM3PluckedStrings{{
    {-7.0, 0.11, 0.020, 5.8, 0.000,
     {1.00, 0.14, 0.060, 0.025, 0.010, 0.004}},
    {-5.0, 0.47, 0.019, 6.1, 0.003,
     {0.78, 0.30, 0.120, 0.050, 0.020, 0.008}},
    {-3.0, 0.93, 0.022, 5.5, 0.006,
     {0.55, 0.24, 0.610, 0.150, 0.060, 0.020}},
    {-1.0, 1.41, 0.018, 6.4, 0.009,
     {0.40, 0.68, 0.210, 0.100, 0.040, 0.015}},
    {1.0, 1.97, 0.021, 5.9, 0.012,
     {0.65, 0.50, 0.280, 0.320, 0.080, 0.025}},
    {3.0, 2.53, 0.020, 6.3, 0.015,
     {0.32, 0.42, 0.180, 0.600, 0.200, 0.050}},
    {5.0, 3.07, 0.019, 5.6, 0.018,
     {0.50, 0.58, 0.380, 0.160, 0.450, 0.120}},
    {7.0, 3.71, 0.021, 6.0, 0.021,
     {0.44, 0.26, 0.520, 0.240, 0.110, 0.390}},
}};

inline double normalized_level(const PluckedStringModel& model) noexcept {
  double energy = 0.0;
  for (const double harmonic : model.harmonics) {
    energy += harmonic * harmonic;
  }
  return energy > 0.0 ? model.level / std::sqrt(energy) : 0.0;
}

inline double plucked_string_sample(std::size_t string_index,
                                    std::uint8_t midi_note,
                                    std::uint64_t sample_index,
                                    double sample_rate,
                                    double level_scale = 1.0) noexcept {
  if (string_index >= kM3PluckedStrings.size() || sample_rate <= 0.0) {
    return 0.0;
  }
  const PluckedStringModel& model = kM3PluckedStrings[string_index];
  const double absolute_time =
      static_cast<double>(sample_index) / sample_rate;
  const double time = absolute_time - model.onset_seconds;
  if (time < 0.0) {
    return 0.0;
  }
  const double attack = 1.0 - std::exp(-time / 0.0025);
  const double body = std::exp(-time / model.decay_seconds);
  const double frequency = midi_to_frequency(
      static_cast<double>(midi_note) + model.detune_cents / 100.0, 440.0);
  const double fundamental_phase =
      model.phase + kTwoPi * frequency * time;
  double value = 0.0;
  for (std::size_t harmonic = 0U; harmonic < model.harmonics.size();
       ++harmonic) {
    const double partial = static_cast<double>(harmonic + 1U);
    const double differential_decay =
        std::exp(-time * 0.025 * static_cast<double>(harmonic));
    const double dispersion =
        0.017 * partial * partial * static_cast<double>(string_index + 1U);
    value += model.harmonics[harmonic] * differential_decay *
             std::sin(partial * fundamental_phase + dispersion);
  }
  // A short deterministic broadband-ish pick component stresses attack
  // rejection without making the fixture random or non-repeatable.
  const double pick =
      0.08 * std::exp(-time / 0.008) *
      (std::sin(kTwoPi * 3911.0 * time + model.phase) +
       0.5 * std::sin(kTwoPi * 6173.0 * time + 0.7 * model.phase));
  return level_scale * normalized_level(model) * attack * body *
         (value + pick);
}

inline std::uint8_t playable_member_mask(std::uint8_t midi_note,
                                         std::size_t member_count) noexcept {
  std::uint8_t mask = 0U;
  std::size_t accepted = 0U;
  for (std::size_t reverse = kM3OpenNotes.size();
       reverse-- > 0U && accepted < member_count;) {
    const std::uint8_t open = kM3OpenNotes[reverse];
    if (midi_note >= open &&
        static_cast<std::uint16_t>(midi_note - open) <= 24U) {
      mask = static_cast<std::uint8_t>(mask | (1U << reverse));
      ++accepted;
    }
  }
  return accepted == member_count ? mask : 0U;
}

inline void set_calibration_point(StringCalibrationBank& bank,
                                  std::size_t string_index,
                                  std::uint8_t midi_note) noexcept {
  if (string_index >= kM3PluckedStrings.size() ||
      midi_note < kM3OpenNotes[string_index] ||
      static_cast<std::size_t>(midi_note - kM3OpenNotes[string_index]) >=
          kCalibrationFretCount) {
    return;
  }
  const PluckedStringModel& model = kM3PluckedStrings[string_index];
  const std::size_t fret = midi_note - kM3OpenNotes[string_index];
  StringCalibrationPoint& point = bank.points[string_index][fret];
  // Match what the detector can actually observe at this pitch. Its bounded
  // filter bank intentionally drops upper partials as fundamentals rise, and
  // the slow identity profile represents the ringing body rather than the
  // pick transient. A test calibration that retained inaudible filter-bank
  // rows would be internally inconsistent and could reward the wrong lane.
  const std::size_t harmonic_count =
      midi_note <= 52U ? 6U : (midi_note >= 76U ? 3U : 4U);
  constexpr double kReferenceSeconds = 1.5;
  double total_energy = 0.0;
  std::array<double, kCalibrationHarmonicCount> energy{};
  for (std::size_t harmonic = 0U; harmonic < harmonic_count; ++harmonic) {
    const double amplitude =
        model.harmonics[harmonic] *
        std::exp(-kReferenceSeconds * 0.025 *
                 static_cast<double>(harmonic));
    energy[harmonic] = amplitude * amplitude;
    total_energy += energy[harmonic];
  }
  for (std::size_t harmonic = 0U; harmonic < model.harmonics.size();
       ++harmonic) {
    point.harmonic_profile_q15[harmonic] =
        static_cast<std::uint16_t>(std::lround(
            32767.0 * energy[harmonic] / total_energy));
  }
  point.cents_offset_q8 = static_cast<std::int16_t>(
      std::lround(model.detune_cents * 256.0));
  point.confidence_q15 = 32767U;
  point.observation_count = 128U;
  point.quality = CalibrationPointQuality::measured;
  bank.calibrated_string_mask = static_cast<std::uint8_t>(
      bank.calibrated_string_mask | (1U << string_index));
}

inline StringCalibrationBank calibration_bank_for_note(
    std::uint8_t midi_note) noexcept {
  StringCalibrationBank bank;
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    set_calibration_point(bank, string, midi_note);
  }
  return bank;
}

inline double unison_sample(std::uint8_t midi_note, std::uint8_t member_mask,
                            std::uint64_t sample_index, double sample_rate,
                            double level_scale = 1.0) noexcept {
  double result = 0.0;
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    if ((member_mask & (1U << string)) != 0U) {
      result += plucked_string_sample(string, midi_note, sample_index,
                                      sample_rate, level_scale);
    }
  }
  return result;
}

}  // namespace m3::test_signal
