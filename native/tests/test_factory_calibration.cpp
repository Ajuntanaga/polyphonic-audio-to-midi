#include <cstdint>

#include "m3/factory_calibration.hpp"
#include "test_support.hpp"

M3_TEST(factory_m3_calibration_has_the_measured_eight_string_prior) {
  const m3::StringCalibrationBank& bank =
      m3::factory_m3_calibration_bank();
  M3_EXPECT_EQ(bank.calibrated_string_mask, 0xFFU);
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    M3_EXPECT_TRUE(bank.string_calibrated(string));
    for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
      const m3::StringCalibrationPoint* point = bank.point(string, fret);
      M3_EXPECT_TRUE(point != nullptr);
      if (point != nullptr) {
        M3_EXPECT_EQ(point->quality,
                     m3::CalibrationPointQuality::measured);
      }
    }
  }

  const m3::StringCalibrationPoint* open = bank.point(6U, 0U);
  const m3::StringCalibrationPoint* first = bank.point(6U, 1U);
  const m3::StringCalibrationPoint* twelfth = bank.point(6U, 12U);
  M3_EXPECT_TRUE(open != nullptr && first != nullptr && twelfth != nullptr);
  if (open != nullptr && first != nullptr && twelfth != nullptr) {
    // The open row retains the current three-unison-safe profile. Frets 1--24
    // use the older measured fingerprint that cleared the replay gates.
    M3_EXPECT_EQ(open->harmonic_profile_q15[0U], 26600U);
    M3_EXPECT_EQ(open->harmonic_profile_q15[1U], 3086U);
    M3_EXPECT_EQ(first->harmonic_profile_q15[0U], 28284U);
    M3_EXPECT_EQ(first->harmonic_profile_q15[1U], 1456U);
    M3_EXPECT_EQ(twelfth->harmonic_profile_q15[0U], 32741U);
    M3_EXPECT_EQ(twelfth->harmonic_profile_q15[1U], 26U);
  }
}

M3_TEST(factory_m3_calibration_merges_explicit_string_overrides) {
  const m3::StringCalibrationBank& factory =
      m3::factory_m3_calibration_bank();
  m3::StringCalibrationBank overrides;
  constexpr std::size_t kOverrideString = 3U;
  overrides.points[kOverrideString] = factory.points[kOverrideString];
  overrides.points[kOverrideString][7U].cents_offset_q8 = 1234;
  overrides.calibrated_string_mask =
      static_cast<std::uint8_t>(1U << kOverrideString);

  const m3::StringCalibrationBank merged =
      m3::merge_m3_factory_calibration(overrides);
  M3_EXPECT_EQ(merged.calibrated_string_mask, 0xFFU);
  M3_EXPECT_EQ(merged.points[kOverrideString][7U].cents_offset_q8, 1234);
  M3_EXPECT_EQ(merged.points[6U][1U].harmonic_profile_q15[0U],
               factory.points[6U][1U].harmonic_profile_q15[0U]);

  const m3::StringCalibrationBank empty;
  const m3::StringCalibrationBank defaulted =
      m3::merge_m3_factory_calibration(empty);
  M3_EXPECT_EQ(defaulted.calibrated_string_mask, 0xFFU);
  M3_EXPECT_EQ(defaulted.points[0U][0U].cents_offset_q8,
               factory.points[0U][0U].cents_offset_q8);
}
