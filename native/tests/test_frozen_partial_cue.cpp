#include "frozen_partial_cue.hpp"
#include "test_support.hpp"

#include <cmath>
#include <limits>
#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
#include "offline_c_allocation_guard.hpp"
#endif

namespace {
using Cue = m3::offline::FrozenPartialCue;

Cue::Peak supported(double cents = 0.0) noexcept {
  Cue::Peak value{};
  value.found = value.reference_available = true;
  value.cents = cents;
  value.prominence_db = 20.0;
  return value;
}

float tone(std::size_t sample) noexcept {
  constexpr double kPi = 3.141592653589793238462643383279502884;
  const double phase = 2.0 * kPi * 65.40639132514966 * static_cast<double>(sample) / 96000.0;
  return static_cast<float>(0.2 * std::cos(3.0 * phase) + 0.15 * std::cos(5.0 * phase));
}
}  // namespace

M3_TEST(frozen_partial_cue_strict_prominence_and_inclusive_agreement) {
  auto third = supported();
  auto fifth = supported(25.0);
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::cue);
  fifth.cents = std::nextafter(25.0, 26.0);
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::pitch_disagreement);
  fifth.cents = -25.0;
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::cue);
  third.prominence_db = Cue::kProminence;
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::below_prominence);
  third.prominence_db = std::nextafter(Cue::kProminence, 20.0);
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::cue);
}

M3_TEST(frozen_partial_cue_missing_and_nonfinite_evidence_abstains) {
  auto third = supported(), fifth = supported();
  third.found = false;
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::missing_peak);
  third = supported(); fifth.reference_available = false;
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::missing_reference);
  fifth = supported(); fifth.prominence_db = std::numeric_limits<double>::infinity();
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::missing_reference);
  fifth = supported(); fifth.cents = std::numeric_limits<double>::quiet_NaN();
  M3_EXPECT_EQ(Cue::screen(third, fifth), Cue::Reason::missing_agreement);
}

M3_TEST(frozen_partial_cue_clock_warmup_and_reset) {
  Cue cue;
  M3_EXPECT_FALSE(cue.push(0.0F));
  M3_EXPECT_FALSE(cue.prepare(48000U));
  M3_EXPECT_TRUE(cue.prepare(96000U));
  for (std::size_t sample = 0U; sample < Cue::kWindow; ++sample) {
    const bool emitted = cue.push(0.0F);
    M3_EXPECT_EQ(emitted, (sample + 1U) % Cue::kHop == 0U);
    if (emitted) {
      M3_EXPECT_EQ(cue.frame().end_sample, sample + 1U);
      M3_EXPECT_EQ(cue.frame().valid, sample + 1U == Cue::kWindow);
      M3_EXPECT_EQ(cue.frame().mask[0U], 0U);
      M3_EXPECT_EQ(cue.frame().mask[1U], 0U);
    }
  }
  cue.reset();
  M3_EXPECT_EQ(cue.frame().end_sample, 0U);
  M3_EXPECT_FALSE(cue.frame().history_available);
  for (std::size_t sample = 0U; sample < Cue::kHop; ++sample) cue.push(0.0F);
  M3_EXPECT_EQ(cue.frame().end_sample, Cue::kHop);
  M3_EXPECT_FALSE(cue.frame().valid);
}

M3_TEST(frozen_partial_cue_recovers_after_invalid_window_without_processing_allocations) {
  Cue cue;
  M3_EXPECT_TRUE(cue.prepare(96000U));
  const auto allocations = m3::test::allocation_count();
  const auto frees = m3::test::deallocation_count();
  for (std::size_t sample = 0U; sample < Cue::kWindow; ++sample) cue.push(tone(sample));
  M3_EXPECT_TRUE(cue.frame().valid);
  M3_EXPECT_EQ(cue.frame().notes[36U - Cue::kFirstNote].reason, Cue::Reason::cue);
  cue.push(std::numeric_limits<float>::quiet_NaN());
  for (std::size_t count = 1U; count < Cue::kWindow; ++count) cue.push(0.0F);
  M3_EXPECT_FALSE(cue.frame().valid);
  M3_EXPECT_EQ(cue.frame().mask[0U], 0U);
  M3_EXPECT_EQ(cue.frame().mask[1U], 0U);
  for (std::size_t count = 0U; count < Cue::kHop; ++count) cue.push(0.0F);
  M3_EXPECT_TRUE(cue.frame().valid);
  M3_EXPECT_EQ(cue.frame().notes[36U - Cue::kFirstNote].reason, Cue::Reason::missing_peak);
  cue.reset();
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations);
  M3_EXPECT_EQ(m3::test::deallocation_count(), frees);
}

#if defined(M3_OFFLINE_C_ALLOCATION_GUARD)
M3_TEST(frozen_partial_cue_c_allocations_are_confined_to_preparation) {
  Cue cue;
  const auto before_prepare = m3::test::c_allocation_count();
  M3_EXPECT_TRUE(cue.prepare(96000U));
  // Prove that the linked wrappers observe allocation before testing absence.
  M3_EXPECT_TRUE(m3::test::c_allocation_count() > before_prepare);
  const auto allocations = m3::test::c_allocation_count();
  const auto frees = m3::test::c_deallocation_count();
  for (std::size_t sample = 0U; sample < Cue::kWindow + 4U * Cue::kHop; ++sample) {
    cue.push(tone(sample));
  }
  M3_EXPECT_EQ(cue.frame().notes[36U - Cue::kFirstNote].reason, Cue::Reason::cue);
  cue.reset();
  M3_EXPECT_EQ(m3::test::c_allocation_count(), allocations);
  M3_EXPECT_EQ(m3::test::c_deallocation_count(), frees);
}
#endif
