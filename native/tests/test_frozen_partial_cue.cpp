#include "frozen_partial_cue.hpp"
#include "test_support.hpp"
#if defined(M3_FROZEN_CUE_COOPERATIVE)
#include "frozen_note_cues.hpp"
#endif

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

#if !defined(M3_FROZEN_CUE_COOPERATIVE)
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
#else
M3_TEST(frozen_native_cue_adapter_delays_expires_and_clears_without_allocations) {
  m3::offline::FrozenNoteCues cues;
  constexpr std::size_t count = 19000U;
  constexpr std::size_t available = Cue::kWindow + Cue::kAvailabilityDelay;
  constexpr std::uint64_t note = std::uint64_t{1} << 36U;
  M3_EXPECT_TRUE(cues.prepare_native(96000U, count));
  const auto cpp_alloc = m3::test::allocation_count(), cpp_free = m3::test::deallocation_count();
  const auto c_alloc = m3::test::c_allocation_count(), c_free = m3::test::c_deallocation_count();
  for (std::size_t sample = 0U; sample <= available + Cue::kHop; ++sample) {
    cues.advance(sample);
    M3_EXPECT_EQ((cues.mask()[0U] & note) != 0U,
                 sample >= available && sample < available + Cue::kHop);
    cues.observe(sample == available ? std::numeric_limits<float>::quiet_NaN() : tone(sample));
  }
  cues.reset();
  for (std::size_t sample = 0U; sample <= available; ++sample) {
    cues.advance(sample); cues.observe(0.0F);
    M3_EXPECT_EQ(cues.mask()[0U], 0U);
    M3_EXPECT_EQ(cues.mask()[1U], 0U);
  }
  cues.reset();
  for (std::size_t sample = 0U; sample < count; ++sample) {
    cues.advance(sample); cues.observe(tone(sample));
  }
  M3_EXPECT_TRUE((cues.mask()[0U] & note) != 0U);
  cues.advance(count);
  M3_EXPECT_EQ(cues.mask()[0U], 0U);
  M3_EXPECT_EQ(cues.mask()[1U], 0U);
  M3_EXPECT_EQ(m3::test::allocation_count(), cpp_alloc);
  M3_EXPECT_EQ(m3::test::deallocation_count(), cpp_free);
  M3_EXPECT_EQ(m3::test::c_allocation_count(), c_alloc);
  M3_EXPECT_EQ(m3::test::c_deallocation_count(), c_free);
}

M3_TEST(frozen_cooperative_delayed_clock_and_mid_calculation_reset) {
  Cue cue;
  M3_EXPECT_FALSE(cue.push(0.0F));
  M3_EXPECT_FALSE(cue.prepare(48000U));
  M3_EXPECT_TRUE(cue.prepare(96000U));
  for (std::size_t count = 1U; count <= Cue::kWindow + Cue::kAvailabilityDelay; ++count) {
    const bool emitted = cue.push(0.0F);
    const bool expected = count > Cue::kHop && count % Cue::kHop == Cue::kAvailabilityDelay;
    M3_EXPECT_EQ(emitted, expected);
    if (emitted) {
      M3_EXPECT_EQ(cue.frame().end_sample, count - Cue::kAvailabilityDelay);
      M3_EXPECT_EQ(cue.frame().valid, cue.frame().end_sample >= Cue::kWindow);
      M3_EXPECT_EQ(cue.frame().mask[0U], 0U);
      M3_EXPECT_EQ(cue.frame().mask[1U], 0U);
    }
  }
  // Cancel in the middle of a valid transform, then require fresh warmup.
  for (std::size_t count = Cue::kAvailabilityDelay; count < Cue::kHop + 64U; ++count) cue.push(0.0F);
  cue.reset();
  M3_EXPECT_EQ(cue.frame().end_sample, 0U);
  for (std::size_t count = 1U; count < Cue::kHop + Cue::kAvailabilityDelay; ++count) {
    M3_EXPECT_FALSE(cue.push(0.0F));
  }
  M3_EXPECT_TRUE(cue.push(0.0F));
  M3_EXPECT_EQ(cue.frame().end_sample, Cue::kHop);
  M3_EXPECT_FALSE(cue.frame().valid);
}

M3_TEST(frozen_cooperative_snapshot_ignores_samples_after_evidence_end) {
  Cue first, second;
  M3_EXPECT_TRUE(first.prepare(96000U));
  M3_EXPECT_TRUE(second.prepare(96000U));
  for (std::size_t sample = 0U; sample < Cue::kWindow; ++sample) {
    first.push(tone(sample)); second.push(tone(sample));
  }
  for (std::size_t sample = 0U; sample < Cue::kAvailabilityDelay; ++sample) {
    first.push(0.0F);
    second.push(sample == 0U ? std::numeric_limits<float>::quiet_NaN() : 20.0F);
  }
  M3_EXPECT_TRUE(first.frame().valid);
  M3_EXPECT_TRUE(second.frame().valid);
  M3_EXPECT_EQ(first.frame().end_sample, Cue::kWindow);
  M3_EXPECT_EQ(first.frame().notes[36U - Cue::kFirstNote].reason, Cue::Reason::cue);
  M3_EXPECT_EQ(first.frame().mask, second.frame().mask);
  for (std::size_t note = 0U; note < Cue::kNotes; ++note) {
    M3_EXPECT_EQ(first.frame().notes[note].reason, second.frame().notes[note].reason);
    M3_EXPECT_EQ(first.frame().notes[note].third.power, second.frame().notes[note].third.power);
    M3_EXPECT_EQ(first.frame().notes[note].fifth.power, second.frame().notes[note].fifth.power);
  }
}

M3_TEST(frozen_cooperative_invalid_window_recovers_without_allocations) {
  Cue cue;
  const auto before_prepare = m3::test::c_allocation_count();
  M3_EXPECT_TRUE(cue.prepare(96000U));
  M3_EXPECT_TRUE(m3::test::c_allocation_count() > before_prepare);
  const auto cpp_alloc = m3::test::allocation_count(), cpp_free = m3::test::deallocation_count();
  const auto c_alloc = m3::test::c_allocation_count(), c_free = m3::test::c_deallocation_count();
  for (std::size_t sample = 0U; sample < 2U * Cue::kWindow + Cue::kHop + Cue::kAvailabilityDelay; ++sample) {
    const bool emitted = cue.push(sample == Cue::kWindow - 64U
        ? std::numeric_limits<float>::quiet_NaN() : tone(sample));
    if (!emitted || !cue.frame().history_available) continue;
    const bool expected_valid = cue.frame().end_sample >= 2U * Cue::kWindow;
    M3_EXPECT_EQ(cue.frame().valid, expected_valid);
    if (!expected_valid) {
      M3_EXPECT_EQ(cue.frame().mask[0U], 0U);
      M3_EXPECT_EQ(cue.frame().mask[1U], 0U);
    }
  }
  M3_EXPECT_EQ(cue.frame().notes[36U - Cue::kFirstNote].reason, Cue::Reason::cue);
  cue.reset();
  M3_EXPECT_EQ(m3::test::allocation_count(), cpp_alloc);
  M3_EXPECT_EQ(m3::test::deallocation_count(), cpp_free);
  M3_EXPECT_EQ(m3::test::c_allocation_count(), c_alloc);
  M3_EXPECT_EQ(m3::test::c_deallocation_count(), c_free);
}
#endif
