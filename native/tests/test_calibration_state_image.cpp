#include "m3/calibration_state_image.hpp"

#include "test_support.hpp"

namespace {

m3::StringCalibrationBank state_test_bank() noexcept {
  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = static_cast<std::uint8_t>(1U << 4U);
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    m3::StringCalibrationPoint& point = bank.points[4U][fret];
    point.cents_offset_q8 = static_cast<std::int16_t>(fret * 8U);
    point.harmonic_profile_q15 = {14000U, 7000U, 4000U,
                                  3000U, 2000U, 1000U};
    point.confidence_q15 = 29000U;
    point.observation_count = 8U;
    point.quality = m3::CalibrationPointQuality::measured;
  }
  return bank;
}

void expect_same(const m3::StringCalibrationBank& left,
                 const m3::StringCalibrationBank& right) noexcept {
  M3_EXPECT_EQ(left.calibrated_string_mask,
               right.calibrated_string_mask);
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
      const auto& a = left.points[string][fret];
      const auto& b = right.points[string][fret];
      M3_EXPECT_EQ(a.cents_offset_q8, b.cents_offset_q8);
      M3_EXPECT_EQ(a.harmonic_profile_q15, b.harmonic_profile_q15);
      M3_EXPECT_EQ(a.confidence_q15, b.confidence_q15);
      M3_EXPECT_EQ(a.observation_count, b.observation_count);
      M3_EXPECT_EQ(a.quality, b.quality);
    }
  }
}

}  // namespace

M3_TEST(calibration_state_image_round_trips_empty_and_learned_banks) {
  for (const m3::StringCalibrationBank& bank :
       {m3::StringCalibrationBank{}, state_test_bank()}) {
    m3::CalibrationStateImage image{};
    M3_EXPECT_TRUE(m3::encode_calibration_state(bank, image));
    m3::StringCalibrationBank decoded;
    M3_EXPECT_TRUE(m3::decode_calibration_state(
        image.data(), image.size(), decoded));
    expect_same(decoded, bank);
  }
}

M3_TEST(calibration_state_image_rejects_invalid_banks_and_corruption) {
  m3::StringCalibrationBank inconsistent = state_test_bank();
  inconsistent.calibrated_string_mask = 0U;
  m3::CalibrationStateImage image{};
  M3_EXPECT_FALSE(m3::encode_calibration_state(inconsistent, image));

  const m3::StringCalibrationBank bank = state_test_bank();
  M3_EXPECT_TRUE(m3::encode_calibration_state(bank, image));
  image.back() ^= 1U;
  m3::StringCalibrationBank unchanged = bank;
  M3_EXPECT_FALSE(m3::decode_calibration_state(
      image.data(), image.size(), unchanged));
  expect_same(unchanged, bank);
  M3_EXPECT_FALSE(m3::decode_calibration_state(nullptr, image.size(),
                                                unchanged));
  M3_EXPECT_FALSE(m3::decode_calibration_state(
      image.data(), image.size() - 1U, unchanged));
}
