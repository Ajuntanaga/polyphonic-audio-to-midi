#include "m3/calibration_bank_transport.hpp"

#include "test_support.hpp"

namespace {

m3::StringCalibrationBank one_string_bank() noexcept {
  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    m3::StringCalibrationPoint& point = bank.points[0U][fret];
    point.cents_offset_q8 = static_cast<std::int16_t>(
        (static_cast<int>(fret) - 12) * 32);
    point.harmonic_profile_q15 = {12000U, 8000U, 5000U,
                                  3500U, 2500U, 1500U};
    point.confidence_q15 = 30000U;
    point.observation_count = 6U;
    point.quality = m3::CalibrationPointQuality::measured;
  }
  return bank;
}

void expect_same_bank(const m3::StringCalibrationBank& left,
                      const m3::StringCalibrationBank& right) noexcept {
  M3_EXPECT_EQ(left.calibrated_string_mask,
               right.calibrated_string_mask);
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
      const m3::StringCalibrationPoint& a = left.points[string][fret];
      const m3::StringCalibrationPoint& b = right.points[string][fret];
      M3_EXPECT_EQ(a.cents_offset_q8, b.cents_offset_q8);
      M3_EXPECT_EQ(a.harmonic_profile_q15, b.harmonic_profile_q15);
      M3_EXPECT_EQ(a.confidence_q15, b.confidence_q15);
      M3_EXPECT_EQ(a.observation_count, b.observation_count);
      M3_EXPECT_EQ(a.quality, b.quality);
    }
  }
}

}  // namespace

M3_TEST(calibration_bank_transport_publishes_one_coherent_generation) {
  m3::CalibrationBankTransport transport;
  m3::CalibrationBankSnapshot snapshot;
  M3_EXPECT_FALSE(transport.read_latest(snapshot));

  const m3::StringCalibrationBank bank = one_string_bank();
  transport.publish(bank, 7U);
  M3_EXPECT_TRUE(transport.read_latest(snapshot));
  M3_EXPECT_EQ(snapshot.generation, 7U);
  expect_same_bank(snapshot.bank, bank);

  m3::StringCalibrationBank empty;
  transport.publish(empty, 8U);
  M3_EXPECT_TRUE(transport.read_latest(snapshot));
  M3_EXPECT_EQ(snapshot.generation, 8U);
  expect_same_bank(snapshot.bank, empty);
}

M3_TEST(calibration_bank_transport_reset_removes_the_published_bank) {
  m3::CalibrationBankTransport transport;
  transport.publish(one_string_bank(), 2U);
  transport.reset();
  m3::CalibrationBankSnapshot snapshot;
  M3_EXPECT_FALSE(transport.read_latest(snapshot));
}
