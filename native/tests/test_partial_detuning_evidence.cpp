#include <array>
#include <cmath>

#include "m3/partial_detuning_evidence.hpp"
#include "test_support.hpp"

namespace {

constexpr double kPi = 3.14159265358979323846;

m3::PartialDetuningFrame make_frame(
    const std::array<double, m3::kPartialDetuningCount>& offsets_hz,
    std::size_t tick, double decisions_per_second) {
  m3::PartialDetuningFrame frame{};
  for (std::size_t partial = 0U; partial < offsets_hz.size(); ++partial) {
    const double phase = 2.0 * kPi * offsets_hz[partial] *
                         static_cast<double>(tick) / decisions_per_second;
    frame.real[partial] = std::cos(phase);
    frame.imaginary[partial] = std::sin(phase);
    frame.center_hz[partial] = 110.0 * static_cast<double>(partial + 1U);
    frame.energy[partial] = 1.0;
  }
  return frame;
}

}  // namespace

M3_TEST(partial_detuning_cancels_global_tuning_and_retains_stretch) {
  constexpr double kDecisionRate = 750.0;
  // Every partial is globally 8 cents sharp. Partials 4-6 additionally carry
  // 1.5, 2.5, and 4 cents of string-stretch displacement.
  constexpr std::array<double, m3::kPartialDetuningCount> kResidualCents{
      0.0, 0.0, 0.0, 1.5, 2.5, 4.0};
  std::array<double, m3::kPartialDetuningCount> offsets{};
  for (std::size_t partial = 0U; partial < offsets.size(); ++partial) {
    const double center = 110.0 * static_cast<double>(partial + 1U);
    const double cents = 8.0 + kResidualCents[partial];
    offsets[partial] = center * (std::exp2(cents / 1200.0) - 1.0);
  }

  m3::PartialDetuningTracker tracker;
  // The production estimator deliberately uses two 30 ms causal smoothing
  // stages to reject the real-signal image. Give both filters enough time to
  // settle before asserting the steady-state frequency displacement.
  for (std::size_t tick = 0U; tick < 500U; ++tick) {
    tracker.update(make_frame(offsets, tick, kDecisionRate), kDecisionRate);
  }

  const auto evidence = tracker.evidence();
  M3_EXPECT_TRUE(evidence.valid);
  M3_EXPECT_NEAR(evidence.residual_cents[1U], 0.0, 0.08);
  M3_EXPECT_NEAR(evidence.residual_cents[3U], 1.5, 0.08);
  M3_EXPECT_NEAR(evidence.residual_cents[4U], 2.5, 0.08);
  M3_EXPECT_NEAR(evidence.residual_cents[5U], 4.0, 0.08);
  M3_EXPECT_NEAR(evidence.upper_mean_cents, (1.5 + 2.5 + 4.0) / 3.0,
                 0.08);
}

M3_TEST(partial_detuning_rejects_missing_fundamental_and_resets) {
  constexpr double kDecisionRate = 750.0;
  constexpr std::array<double, m3::kPartialDetuningCount> kOffsets{};
  m3::PartialDetuningTracker tracker;
  auto first = make_frame(kOffsets, 0U, kDecisionRate);
  auto second = make_frame(kOffsets, 1U, kDecisionRate);
  first.energy[0U] = 0.0;
  second.energy[0U] = 0.0;
  tracker.update(first, kDecisionRate);
  tracker.update(second, kDecisionRate);
  M3_EXPECT_FALSE(tracker.evidence().valid);

  tracker.reset();
  for (std::size_t tick = 0U; tick < 8U; ++tick) {
    tracker.update(make_frame(kOffsets, tick, kDecisionRate), kDecisionRate);
  }
  M3_EXPECT_TRUE(tracker.evidence().valid);
  tracker.reset();
  M3_EXPECT_FALSE(tracker.evidence().valid);
}

M3_TEST(partial_detuning_comparison_uses_only_shared_nonfundamental_partials) {
  m3::PartialDetuningEvidence observed;
  observed.residual_cents = {0.0, 1.0, 2.0, 3.0, 0.0, 0.0};
  observed.valid_mask = 0x0FU;
  observed.valid = true;
  constexpr std::array<double, m3::kPartialDetuningCount> kMatching{
      0.0, 1.2, 2.1, 3.1, 50.0, 50.0};
  constexpr std::array<double, m3::kPartialDetuningCount> kWrong{
      0.0, 7.0, 8.0, 9.0, 0.0, 0.0};
  const auto matching =
      m3::compare_partial_detuning(observed, kMatching, 0x3FU);
  const auto wrong = m3::compare_partial_detuning(observed, kWrong, 0x0FU);
  M3_EXPECT_TRUE(matching.valid && wrong.valid);
  M3_EXPECT_EQ(matching.common_partials, 3U);
  M3_EXPECT_EQ(wrong.common_partials, 3U);
  M3_EXPECT_TRUE(matching.log_likelihood > wrong.log_likelihood);
}
