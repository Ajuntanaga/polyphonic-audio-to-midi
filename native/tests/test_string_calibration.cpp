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
  for (std::size_t repeat = 0U;
       repeat < 160U && calibrator.active() &&
       calibrator.status().requested_fret == fret;
       ++repeat) {
    M3_EXPECT_TRUE(calibrator.observe(observation(string_index, fret, cents)));
  }
}

void feed_complete_sweep(m3::StringSweepCalibrator& calibrator,
                         std::size_t string_index) noexcept {
  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(
        calibrator.observe(observation(string_index, 0U, 3.0)));
  }
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::ascending);
  for (std::size_t fret = 1U; fret < m3::kCalibrationFretCount; ++fret) {
    feed_fret(calibrator, string_index, fret,
              3.0 + 0.1 * static_cast<double>(fret));
  }
  for (std::size_t fret = m3::kCalibrationFretCount - 1U; fret-- > 0U;) {
    feed_fret(calibrator, string_index, fret,
              4.0 + 0.1 * static_cast<double>(fret));
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
    M3_EXPECT_EQ(middle->observation_count, 120U);
    M3_EXPECT_TRUE(middle->harmonic_profile_q15[0] >
                   middle->harmonic_profile_q15[1]);
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
  for (std::size_t fret = 1U; fret < 24U; ++fret) {
    feed_fret(calibrator, 0U, fret, 2.0);
  }
  M3_EXPECT_FALSE(calibrator.observe(observation(0U, 22U, 2.0)));
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::ascending);
  feed_fret(calibrator, 0U, 24U, 2.0);
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::descending);
}

M3_TEST(string_calibration_requests_each_fret_in_order_and_ignores_skips) {
  m3::StringSweepCalibrator calibrator;
  constexpr std::size_t kString = 2U;
  M3_EXPECT_TRUE(calibrator.begin(kString));
  M3_EXPECT_EQ(calibrator.status().requested_fret, 0U);

  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(calibrator.observe(observation(kString, 0U, 2.0)));
  }
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::ascending);
  M3_EXPECT_EQ(calibrator.status().requested_fret, 1U);

  // A slide or accidental jump cannot silently satisfy a later fret.
  for (std::size_t repeat = 0U; repeat < 8U; ++repeat) {
    M3_EXPECT_FALSE(calibrator.observe(observation(kString, 2U, 2.0)));
  }
  M3_EXPECT_EQ(calibrator.status().requested_fret, 1U);

  for (std::size_t fret = 1U; fret < m3::kCalibrationFretCount; ++fret) {
    while (calibrator.status().phase ==
               m3::CalibrationSweepPhase::ascending &&
           calibrator.status().requested_fret == fret) {
      M3_EXPECT_TRUE(calibrator.observe(observation(kString, fret, 2.0)));
    }
  }
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::descending);
  M3_EXPECT_EQ(calibrator.status().requested_fret, 23U);

  for (std::size_t fret = 24U; fret-- > 0U;) {
    while (calibrator.active() &&
           calibrator.status().requested_fret == fret) {
      M3_EXPECT_TRUE(calibrator.observe(observation(kString, fret, 3.0)));
    }
  }
  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(calibrator.status().highest_fret, 24U);
  M3_EXPECT_EQ(calibrator.status().measured_frets, 25U);
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

M3_TEST(string_calibration_waits_for_a_clean_hold_after_transition_frames) {
  m3::StringSweepCalibrator calibrator;
  constexpr std::size_t string_index = 4U;
  constexpr std::size_t transition_fret = 12U;
  M3_EXPECT_TRUE(calibrator.begin(static_cast<std::uint8_t>(string_index)));

  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(
        calibrator.observe(observation(string_index, 0U, 2.0)));
  }
  for (std::size_t fret = 1U; fret < m3::kCalibrationFretCount; ++fret) {
    if (fret == transition_fret) {
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, -30.0)));
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, 0.0)));
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, 30.0)));
      M3_EXPECT_EQ(calibrator.status().requested_fret, transition_fret);
      feed_fret(calibrator, string_index, fret, 2.0);
    } else {
      feed_fret(calibrator, string_index, fret, 2.0);
    }
  }
  for (std::size_t fret = m3::kCalibrationFretCount - 1U; fret-- > 0U;) {
    if (fret == transition_fret) {
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, 30.0)));
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, 0.0)));
      M3_EXPECT_TRUE(
          calibrator.observe(observation(string_index, fret, -30.0)));
      M3_EXPECT_EQ(calibrator.status().requested_fret, transition_fret);
      feed_fret(calibrator, string_index, fret, 3.0);
    } else {
      feed_fret(calibrator, string_index, fret, 3.0);
    }
  }

  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(calibrator.status().measured_frets, 25U);
  M3_EXPECT_EQ(calibrator.status().interpolated_frets, 0U);
  const auto* point =
      calibrator.bank().point(string_index, transition_fret);
  M3_EXPECT_TRUE(point != nullptr);
  if (point != nullptr) {
    M3_EXPECT_EQ(point->quality, m3::CalibrationPointQuality::measured);
  }
}

M3_TEST(string_calibration_windows_are_time_based_across_observation_rates) {
  constexpr std::array<double, 2U> kObservationRates{750.0, 1500.0};
  constexpr std::array<std::size_t, 2U> kOpenObservations{64U, 128U};
  constexpr std::array<std::size_t, 2U> kFretObservations{62U, 122U};
  for (std::size_t rate_index = 0U; rate_index < kObservationRates.size();
       ++rate_index) {
    m3::StringSweepCalibrator calibrator;
    M3_EXPECT_TRUE(calibrator.begin(0U, kObservationRates[rate_index]));
    for (std::size_t repeat = 1U;
         repeat < kOpenObservations[rate_index]; ++repeat) {
      M3_EXPECT_TRUE(calibrator.observe(observation(0U, 0U, 2.0)));
    }
    M3_EXPECT_EQ(calibrator.status().phase,
                 m3::CalibrationSweepPhase::waiting_open);
    M3_EXPECT_TRUE(calibrator.observe(observation(0U, 0U, 2.0)));
    M3_EXPECT_EQ(calibrator.status().phase,
                 m3::CalibrationSweepPhase::ascending);

    const auto feed = [&](std::size_t fret, double cents) noexcept {
      for (std::size_t repeat = 0U;
           repeat < kFretObservations[rate_index] && calibrator.active() &&
           calibrator.status().requested_fret == fret;
           ++repeat) {
          M3_EXPECT_TRUE(calibrator.observe(observation(0U, fret, cents)));
      }
    };
    for (std::size_t fret = 1U; fret < m3::kCalibrationFretCount; ++fret) {
      feed(fret, 2.0);
    }
    for (std::size_t fret = m3::kCalibrationFretCount - 1U; fret-- > 0U;) {
      feed(fret, 3.0);
    }
    M3_EXPECT_EQ(calibrator.status().phase,
                 m3::CalibrationSweepPhase::complete);
    M3_EXPECT_EQ(calibrator.status().measured_frets, 25U);
  }
}

M3_TEST(string_calibration_confidence_records_temporal_harmonic_stability) {
  m3::StringSweepCalibrator calibrator;
  constexpr std::size_t string_index = 5U;
  constexpr std::size_t unstable_fret = 12U;
  M3_EXPECT_TRUE(calibrator.begin(static_cast<std::uint8_t>(string_index)));

  for (std::size_t repeat = 0U; repeat < 64U; ++repeat) {
    M3_EXPECT_TRUE(
        calibrator.observe(observation(string_index, 0U, 2.0)));
  }
  const auto feed_direction = [&](bool descending) noexcept {
    for (std::size_t step = 0U; step < m3::kCalibrationFretCount - 1U; ++step) {
      const std::size_t fret = descending
                                   ? m3::kCalibrationFretCount - 2U - step
                                   : step + 1U;
      if (fret != unstable_fret) {
        feed_fret(calibrator, string_index, fret, 2.0);
        continue;
      }
      for (std::size_t repeat = 0U;
           repeat < 128U && calibrator.status().requested_fret == fret;
           ++repeat) {
        auto frame = observation(string_index, fret, 2.0);
        frame.harmonic_energy = repeat % 2U == 0U
                                    ? std::array<double, 6>{1.0, 0.0, 0.0,
                                                            0.0, 0.0, 0.0}
                                    : std::array<double, 6>{0.0, 1.0, 0.0,
                                                            0.0, 0.0, 0.0};
        M3_EXPECT_TRUE(calibrator.observe(frame));
      }
    }
  };
  feed_direction(false);
  feed_direction(true);

  M3_EXPECT_EQ(calibrator.status().phase,
               m3::CalibrationSweepPhase::complete);
  const auto* stable = calibrator.bank().point(string_index, 11U);
  const auto* unstable = calibrator.bank().point(string_index, unstable_fret);
  M3_EXPECT_TRUE(stable != nullptr);
  M3_EXPECT_TRUE(unstable != nullptr);
  if (stable != nullptr && unstable != nullptr) {
    M3_EXPECT_EQ(stable->quality, m3::CalibrationPointQuality::measured);
    M3_EXPECT_EQ(unstable->quality, m3::CalibrationPointQuality::measured);
    M3_EXPECT_TRUE(unstable->confidence_q15 < stable->confidence_q15 / 2U);
  }
}
