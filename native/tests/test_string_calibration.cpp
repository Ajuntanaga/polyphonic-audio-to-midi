#include <array>
#include <cmath>
#include <cstddef>

#include "m3/string_calibration.hpp"
#include "test_support.hpp"

namespace {

m3::CalibrationObservation observation(std::size_t string_index,
                                       std::size_t fret,
                                       double cents) noexcept {
  m3::CalibrationObservation value;
  value.midi_pitch = static_cast<double>(m3::kM3OpenNotes[string_index]) +
                     static_cast<double>(fret) + cents / 100.0;
  value.confidence = 0.92;
  const double string_value = static_cast<double>(string_index);
  const double fret_value = static_cast<double>(fret);
  value.harmonic_energy = {
      1.0 + 0.03 * string_value,
      0.48 + 0.01 * fret_value,
      0.25 + 0.005 * string_value,
      0.14,
      0.08,
      0.04,
  };
  return value;
}

void feed_fret(m3::StringSweepCalibrator& calibrator,
               std::size_t string_index, std::size_t fret,
               double cents) noexcept {
  for (std::size_t repeat = 0U; repeat < 5U; ++repeat) {
    if (calibrator.active()) {
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, cents)));
    }
  }
}

void feed_complete_sweep(m3::StringSweepCalibrator& calibrator,
                         std::size_t string_index,
                         std::size_t skipped_fret = 99U) noexcept {
  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(
        calibrator.observe(observation(string_index, 0U, 3.0)));
  }
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::ascending);
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    if (fret != skipped_fret) {
      feed_fret(calibrator, string_index, fret,
                3.0 + 0.1 * static_cast<double>(fret));
    }
  }
  // Four initial descending observations establish direction. Keeping the
  // top point in both passes also makes ascent/descent agreement explicit.
  for (std::size_t fret = m3::kCalibrationFretCount; fret-- > 0U;) {
    if (fret != skipped_fret) {
      feed_fret(calibrator, string_index, fret,
                4.0 + 0.1 * static_cast<double>(fret));
    }
  }
}

}  // namespace

M3_TEST(string_calibration_learns_an_open_to_24_and_back_sweep) {
  m3::StringSweepCalibrator calibrator;
  M3_EXPECT_TRUE(calibrator.begin(3U));
  feed_complete_sweep(calibrator, 3U);

  const auto status = calibrator.status();
  M3_EXPECT_EQ(status.phase, m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(status.string_index, 3U);
  M3_EXPECT_EQ(status.highest_fret, 24U);
  M3_EXPECT_EQ(status.measured_frets, 25U);
  M3_EXPECT_EQ(status.interpolated_frets, 0U);
  M3_EXPECT_TRUE(calibrator.bank().string_calibrated(3U));
  const auto* middle = calibrator.bank().point(3U, 12U);
  M3_EXPECT_TRUE(middle != nullptr);
  if (middle != nullptr) {
    M3_EXPECT_EQ(middle->quality, m3::CalibrationPointQuality::measured);
    M3_EXPECT_NEAR(static_cast<double>(middle->cents_offset_q8) / 256.0,
                   4.7, 0.3);
    M3_EXPECT_EQ(middle->observation_count, 10U);
    M3_EXPECT_TRUE(middle->harmonic_profile_q15[0] >
                   middle->harmonic_profile_q15[1]);
  }
}

M3_TEST(string_calibration_interpolates_only_a_missing_interior_fret) {
  m3::StringSweepCalibrator calibrator;
  M3_EXPECT_TRUE(calibrator.begin(0U));
  feed_complete_sweep(calibrator, 0U, 12U);

  const auto status = calibrator.status();
  M3_EXPECT_EQ(status.phase, m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(status.measured_frets, 24U);
  M3_EXPECT_EQ(status.interpolated_frets, 1U);
  const auto* missing = calibrator.bank().point(0U, 12U);
  M3_EXPECT_TRUE(missing != nullptr);
  if (missing != nullptr) {
    M3_EXPECT_EQ(missing->quality,
                 m3::CalibrationPointQuality::interpolated);
    M3_EXPECT_EQ(missing->observation_count, 0U);
    M3_EXPECT_NEAR(static_cast<double>(missing->cents_offset_q8) / 256.0,
                   4.7, 0.4);
  }
}

M3_TEST(string_calibration_rejects_bad_frames_without_overwriting_a_bank) {
  m3::StringSweepCalibrator calibrator;
  M3_EXPECT_FALSE(calibrator.begin(8U));
  M3_EXPECT_TRUE(calibrator.begin(2U));
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::waiting_open);
  auto bad = observation(2U, 0U, 0.0);
  bad.confidence = 0.1;
  M3_EXPECT_FALSE(calibrator.observe(bad));
  bad = observation(2U, 0U, 49.0);
  M3_EXPECT_FALSE(calibrator.observe(bad));
  bad = observation(2U, 0U, 0.0);
  bad.harmonic_energy[2] = -1.0;
  M3_EXPECT_FALSE(calibrator.observe(bad));
  M3_EXPECT_EQ(calibrator.status().rejected_observations, 3U);
  calibrator.cancel();
  M3_EXPECT_EQ(calibrator.status().phase, m3::CalibrationSweepPhase::idle);
  M3_EXPECT_FALSE(calibrator.bank().string_calibrated(2U));
}

M3_TEST(string_calibration_does_not_turn_around_before_fret_24) {
  m3::StringSweepCalibrator calibrator;
  M3_EXPECT_TRUE(calibrator.begin(0U));
  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(calibrator.observe(observation(0U, 0U, 2.0)));
  }
  for (std::size_t fret = 0U; fret < 24U; ++fret) {
    feed_fret(calibrator, 0U, fret, 2.0);
  }
  feed_fret(calibrator, 0U, 22U, 2.0);
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::ascending);
  feed_fret(calibrator, 0U, 24U, 2.0);
  feed_fret(calibrator, 0U, 23U, 2.0);
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::descending);
}

M3_TEST(string_calibration_keeps_all_eight_string_maps_independent) {
  m3::StringSweepCalibrator calibrator;
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    M3_EXPECT_TRUE(calibrator.begin(static_cast<std::uint8_t>(string)));
    feed_complete_sweep(calibrator, string);
    M3_EXPECT_EQ(calibrator.status().phase,
                 m3::CalibrationSweepPhase::complete);
  }
  M3_EXPECT_EQ(calibrator.bank().calibrated_string_mask, 0xFFU);
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    M3_EXPECT_TRUE(calibrator.bank().string_calibrated(string));
    const auto* point = calibrator.bank().point(string, 8U);
    M3_EXPECT_TRUE(point != nullptr);
    if (point != nullptr && string > 0U) {
      const auto* previous = calibrator.bank().point(string - 1U, 8U);
      M3_EXPECT_TRUE(previous != nullptr);
      if (previous != nullptr) {
        M3_EXPECT_TRUE(point->harmonic_profile_q15[0] !=
                       previous->harmonic_profile_q15[0]);
      }
    }
  }
}
