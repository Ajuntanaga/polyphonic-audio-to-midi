#include <array>

#include "m3/harmonic_evidence.hpp"
#include "test_support.hpp"

M3_TEST(harmonic_evidence_has_distinct_lower_and_upper_partial_heads) {
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kReference{
      1.0, 0.55, 0.32, 0.18, 0.10, 0.06};
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kLowerChanged{
      1.0, 0.18, 0.10, 0.18, 0.10, 0.06};
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kUpperChanged{
      1.0, 0.55, 0.32, 0.04, 0.02, 0.01};

  const auto reference = m3::make_harmonic_evidence(kReference);
  const auto lower = m3::make_harmonic_evidence(kLowerChanged);
  const auto upper = m3::make_harmonic_evidence(kUpperChanged);
  M3_EXPECT_TRUE(reference.valid && lower.valid && upper.valid);

  const auto exact = m3::compare_spectral_tiers(reference, reference);
  const auto lower_difference = m3::compare_spectral_tiers(reference, lower);
  const auto upper_difference = m3::compare_spectral_tiers(reference, upper);
  for (const double tier : exact.tier_log_likelihood) {
    M3_EXPECT_NEAR(tier, 0.0, 1.0e-12);
  }
  const double lower_tiers =
      lower_difference.tier_log_likelihood[0U] +
      lower_difference.tier_log_likelihood[1U];
  const double upper_tiers =
      upper_difference.tier_log_likelihood[2U] +
      upper_difference.tier_log_likelihood[3U];
  M3_EXPECT_TRUE(lower_tiers <
                 lower_difference.tier_log_likelihood[2U] +
                     lower_difference.tier_log_likelihood[3U]);
  M3_EXPECT_TRUE(upper_tiers <
                 upper_difference.tier_log_likelihood[0U] +
                     upper_difference.tier_log_likelihood[1U]);
}

M3_TEST(harmonic_evidence_keeps_overtone_crossover_separate_from_tiers) {
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kReference{
      1.0, 0.50, 0.25, 0.12, 0.06, 0.03};
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kCrossoverChanged{
      1.0, 0.50, 0.25, 0.03, 0.015, 0.0075};
  const auto comparison = m3::compare_spectral_tiers(
      m3::make_harmonic_evidence(kReference),
      m3::make_harmonic_evidence(kCrossoverChanged));
  M3_EXPECT_TRUE(comparison.overtone_separation_log_likelihood < 0.0);
  for (const double tier : comparison.tier_log_likelihood) {
    M3_EXPECT_NEAR(tier, 0.0, 1.0e-12);
  }
}

M3_TEST(harmonic_evidence_marks_attack_decay_change_without_lookahead) {
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kSettled{
      1.0, 0.50, 0.25, 0.12, 0.06, 0.03};
  constexpr std::array<double, m3::kHarmonicEvidenceCount> kAttack{
      0.30, 0.42, 0.38, 0.31, 0.24, 0.18};
  const auto settled = m3::make_harmonic_evidence(kSettled);
  const auto attack = m3::make_harmonic_evidence(kAttack);
  M3_EXPECT_NEAR(m3::harmonic_transient_strength(settled, settled),
                 0.0, 1.0e-12);
  M3_EXPECT_TRUE(m3::harmonic_transient_strength(attack, settled) > 0.25);
}


M3_TEST(harmonic_evidence_rejects_empty_or_nonfinite_energy) {
  std::array<double, m3::kHarmonicEvidenceCount> empty{};
  M3_EXPECT_FALSE(m3::make_harmonic_evidence(empty).valid);
  empty[0U] = 1.0;
  empty[3U] = -0.1;
  M3_EXPECT_FALSE(m3::make_harmonic_evidence(empty).valid);
}

M3_TEST(harmonic_ratio_weight_ignores_absent_observed_partials) {
  const auto observed = m3::make_harmonic_evidence({1, 0, 0, 0, 0, 0});
  const auto reference = m3::make_harmonic_evidence({1, .1, .01, .001, .01, .1});
  const auto weighted = m3::compare_harmonic_evidence(observed, reference, true);
  const auto original = m3::compare_harmonic_evidence(observed, reference);
  M3_EXPECT_NEAR(weighted.lower_log_likelihood, 0.0, 1e-12);
  M3_EXPECT_NEAR(weighted.upper_log_likelihood, 0.0, 1e-12);
  M3_EXPECT_TRUE(original.lower_log_likelihood < 0.0);
  M3_EXPECT_NEAR(weighted.balance_log_likelihood,
                 original.balance_log_likelihood, 1e-12);
}

M3_TEST(harmonic_ratio_weight_preserves_supported_and_scale_invariant_evidence) {
  const auto observed = m3::make_harmonic_evidence({1, 1, 1, 1, 1, 1});
  const auto scaled = m3::make_harmonic_evidence({10, 10, 10, 10, 10, 10});
  const auto reference = m3::make_harmonic_evidence({1, .5, .25, .125, .0625, .03125});
  const auto original = m3::compare_harmonic_evidence(observed, reference);
  const auto weighted = m3::compare_harmonic_evidence(observed, reference, true);
  const auto scaled_result = m3::compare_harmonic_evidence(scaled, reference, true);
  M3_EXPECT_NEAR(weighted.combined_log_likelihood(), original.combined_log_likelihood(), 1e-12);
  M3_EXPECT_NEAR(weighted.combined_log_likelihood(), scaled_result.combined_log_likelihood(), 1e-12);
}

M3_TEST(harmonic_ratio_weight_limits_tiny_upper_partial_influence) {
  const auto observed = m3::make_harmonic_evidence({32747, 18, 2, 4, 1, 1});
  const auto reference = m3::make_harmonic_evidence({32547, 214, 2, 4, 0, 0});
  const auto original = m3::compare_harmonic_evidence(observed, reference);
  const auto weighted = m3::compare_harmonic_evidence(observed, reference, true);
  M3_EXPECT_TRUE(original.upper_log_likelihood < 0.0);
  M3_EXPECT_TRUE(weighted.upper_log_likelihood > original.upper_log_likelihood * .001);
  const auto exact = m3::compare_harmonic_evidence(observed, observed, true);
  M3_EXPECT_NEAR(exact.combined_log_likelihood(), 0.0, 1e-12);
}
