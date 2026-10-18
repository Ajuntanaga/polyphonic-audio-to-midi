#include <cmath>
#include <limits>

#include "m3/unison_spectral_classifier.hpp"
#include "m3/unison_spectral_templates.hpp"
#include "test_support.hpp"

namespace {

m3::UnisonSpectralFingerprint fingerprint(
    std::initializer_list<std::pair<std::size_t, double>> values) noexcept {
  m3::UnisonSpectralFingerprint result{};
  for (const auto& value : values) {
    result[value.first] = value.second;
  }
  return result;
}

}  // namespace

M3_TEST(unison_spectral_classifier_finds_the_joint_consecutive_triple) {
  m3::UnisonSpectralTemplateSet templates;
  templates.valid_mask = 0x0FU;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}, {3U, 0.2}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}, {3U, 0.2}});
  templates.fingerprint[2U] = fingerprint({{2U, 1.0}, {3U, 0.2}});
  templates.fingerprint[3U] = fingerprint(
      {{0U, 0.42}, {1U, 0.48}, {2U, 0.10}, {3U, 0.2}, {4U, 1.0}});
  const auto observed =
      fingerprint({{0U, 0.7}, {1U, 0.9}, {2U, 0.6}, {3U, 0.44}});

  const m3::UnisonSpectralClassification result =
      m3::classify_consecutive_unison(observed, templates, 0x0FU, 3U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x07U);
  M3_EXPECT_TRUE(result.error < 1.0e-20);
  M3_EXPECT_TRUE(result.weights[0U] > 0.69);
  M3_EXPECT_TRUE(result.weights[1U] > 0.89);
  M3_EXPECT_TRUE(result.weights[2U] > 0.59);
  M3_EXPECT_NEAR(result.weights[3U], 0.0, 0.0);
}

M3_TEST(unison_spectral_classifier_never_selects_a_nonconsecutive_shape) {
  m3::UnisonSpectralTemplateSet templates;
  templates.valid_mask = 0x0FU;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{2U, 1.0}});
  templates.fingerprint[3U] = fingerprint({{3U, 1.0}});
  const auto observed =
      fingerprint({{0U, 1.0}, {1U, 0.1}, {2U, 1.0}, {3U, 1.0}});

  const m3::UnisonSpectralClassification result =
      m3::classify_consecutive_unison(observed, templates, 0x0FU, 3U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_TRUE(result.member_mask == 0x07U || result.member_mask == 0x0EU);
  M3_EXPECT_FALSE(result.member_mask == 0x0DU);
}

M3_TEST(unison_spectral_classifier_rejects_invalid_or_incomplete_evidence) {
  m3::UnisonSpectralTemplateSet templates;
  templates.valid_mask = 0x07U;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{2U, 1.0}});
  auto observed = fingerprint({{0U, 1.0}, {1U, 1.0}, {2U, 1.0}});

  M3_EXPECT_FALSE(
      m3::classify_consecutive_unison(observed, templates, 0x03U, 3U).valid);
  M3_EXPECT_FALSE(
      m3::classify_consecutive_unison(observed, templates, 0x07U, 1U).valid);
  observed[5U] = std::numeric_limits<double>::quiet_NaN();
  M3_EXPECT_FALSE(
      m3::classify_consecutive_unison(observed, templates, 0x07U, 3U).valid);
}

M3_TEST(unison_spectral_classifier_is_invariant_to_uniform_signal_scale) {
  m3::UnisonSpectralTemplateSet templates;
  templates.valid_mask = 0x07U;
  constexpr double scale = 1.0e-20;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0 * scale}});
  templates.fingerprint[1U] = fingerprint({{1U, 2.0 * scale}});
  templates.fingerprint[2U] = fingerprint({{2U, 3.0 * scale}});
  const auto observed = fingerprint(
      {{0U, 0.5 * scale}, {1U, 1.5 * scale}, {2U, 0.75 * scale}});

  const m3::UnisonSpectralClassification result =
      m3::classify_consecutive_unison(observed, templates, 0x07U, 3U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x07U);
  M3_EXPECT_TRUE(result.error < 1.0e-20);
  M3_EXPECT_NEAR(result.weights[0U], 0.5, 1.0e-12);
  M3_EXPECT_NEAR(result.weights[1U], 0.75, 1.0e-12);
  M3_EXPECT_NEAR(result.weights[2U], 0.25, 1.0e-12);
}

M3_TEST(unison_spectral_classifier_finds_the_joint_consecutive_quadruple) {
  m3::UnisonSpectralTemplateSet templates;
  templates.valid_mask = 0x1FU;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{2U, 1.0}});
  templates.fingerprint[3U] = fingerprint({{3U, 1.0}});
  templates.fingerprint[4U] = fingerprint({{4U, 1.0}});
  const auto observed = fingerprint(
      {{0U, 0.8}, {1U, 0.7}, {2U, 0.6}, {3U, 0.5}, {4U, 0.02}});

  const m3::UnisonSpectralClassification result =
      m3::classify_consecutive_unison(observed, templates, 0x1FU, 4U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x0FU);
  M3_EXPECT_TRUE(result.error < 1.0e-3);
}

M3_TEST(unison_spectral_classifier_finds_a_nonconsecutive_feasible_group) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[5U] = fingerprint({{2U, 1.0}});
  templates.valid_mask = 0x25U;
  const auto observed =
      fingerprint({{0U, 0.8}, {1U, 0.6}, {2U, 0.4}});

  const m3::UnisonSpectralClassification result =
      m3::classify_feasible_unison(observed, templates, 0x25U, 3U, 3U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x25U);
  M3_EXPECT_EQ(result.member_count, 3U);
  M3_EXPECT_TRUE(result.posterior_margin > 0.0);
}

M3_TEST(unison_spectral_classifier_reports_runner_up_margin) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{2U, 1.0}});
  templates.valid_mask = 0x07U;
  const auto observed =
      fingerprint({{0U, 0.9}, {1U, 0.8}, {2U, 0.05}});

  const m3::UnisonSpectralClassification result =
      m3::classify_feasible_unison(observed, templates, 0x07U, 2U, 2U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x03U);
  M3_EXPECT_EQ(result.member_count, 2U);
  M3_EXPECT_TRUE(result.runner_up_error > result.error);
  M3_EXPECT_NEAR(result.posterior_margin,
                 result.runner_up_error - result.error, 1.0e-12);
}

M3_TEST(single_spectral_source_selects_the_closest_feasible_string) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}, {1U, 0.1}});
  templates.fingerprint[1U] = fingerprint({{0U, 0.1}, {1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{0U, 0.7}, {1U, 0.7}});
  templates.valid_mask = 0x07U;
  const auto observed = fingerprint({{0U, 0.2}, {1U, 0.9}});

  const m3::UnisonSpectralClassification result =
      m3::classify_single_spectral_source(observed, templates, 0x07U);

  M3_EXPECT_TRUE(result.valid);
  M3_EXPECT_EQ(result.member_mask, 0x02U);
  M3_EXPECT_EQ(result.member_count, 1U);
  M3_EXPECT_TRUE(result.posterior_margin > 0.0);
}

M3_TEST(single_spectral_source_scores_expose_every_feasible_string) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.fingerprint[2U] = fingerprint({{0U, 0.7}, {1U, 0.7}});
  templates.fingerprint[3U] = fingerprint({{2U, 1.0}});
  templates.valid_mask = 0x0FU;
  const auto observed = fingerprint({{0U, 0.3}, {1U, 0.9}});

  const m3::UnisonSpectralSingleScores result =
      m3::score_single_spectral_sources(observed, templates, 0x07U);

  M3_EXPECT_EQ(result.valid_mask, 0x07U);
  M3_EXPECT_TRUE(std::isfinite(result.error[0U]));
  M3_EXPECT_TRUE(std::isfinite(result.error[1U]));
  M3_EXPECT_TRUE(std::isfinite(result.error[2U]));
  M3_EXPECT_TRUE(result.error[1U] < result.error[2U]);
  M3_EXPECT_TRUE(result.error[2U] < result.error[0U]);
  M3_EXPECT_TRUE(std::isinf(result.error[3U]));
}

M3_TEST(single_spectral_source_scores_are_scale_invariant_and_fail_closed) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}, {1U, 0.25}});
  templates.fingerprint[1U] = fingerprint({{0U, 0.1}, {1U, 1.0}});
  templates.valid_mask = 0x03U;
  const auto observed = fingerprint({{0U, 0.4}, {1U, 0.8}});
  auto scaled = observed;
  for (double& feature : scaled) {
    feature *= 1.0e-18;
  }

  const m3::UnisonSpectralSingleScores normal =
      m3::score_single_spectral_sources(observed, templates, 0x03U);
  const m3::UnisonSpectralSingleScores tiny =
      m3::score_single_spectral_sources(scaled, templates, 0x03U);

  M3_EXPECT_EQ(normal.valid_mask, 0x03U);
  M3_EXPECT_EQ(tiny.valid_mask, normal.valid_mask);
  M3_EXPECT_NEAR(tiny.error[0U], normal.error[0U], 1.0e-12);
  M3_EXPECT_NEAR(tiny.error[1U], normal.error[1U], 1.0e-12);

  auto invalid = observed;
  invalid[4U] = std::numeric_limits<double>::quiet_NaN();
  const m3::UnisonSpectralSingleScores rejected =
      m3::score_single_spectral_sources(invalid, templates, 0x03U);
  M3_EXPECT_EQ(rejected.valid_mask, 0U);
  for (const double error : rejected.error) {
    M3_EXPECT_TRUE(std::isinf(error));
  }
}

M3_TEST(unison_spectral_classifier_rejects_infeasible_member_ranges) {
  m3::UnisonSpectralTemplateSet templates;
  templates.fingerprint[0U] = fingerprint({{0U, 1.0}});
  templates.fingerprint[1U] = fingerprint({{1U, 1.0}});
  templates.valid_mask = 0x03U;
  const auto observed = fingerprint({{0U, 1.0}, {1U, 1.0}});

  M3_EXPECT_FALSE(m3::classify_feasible_unison(
      observed, templates, 0x03U, 1U, 2U).valid);
  M3_EXPECT_FALSE(m3::classify_feasible_unison(
      observed, templates, 0x03U, 3U, 2U).valid);
  M3_EXPECT_FALSE(m3::classify_feasible_unison(
      observed, templates, 0x03U, 2U, 5U).valid);
}

M3_TEST(factory_unison_spectral_templates_are_closed_and_normalized) {
  m3::UnisonSpectralTemplateSet templates;
  M3_EXPECT_TRUE(m3::factory_unison_spectral_templates(
      m3::UnisonSpectralPhase::settled, 40U, templates));
  M3_EXPECT_TRUE(templates.valid_mask != 0U);
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((templates.valid_mask & bit) == 0U) {
      continue;
    }
    double norm = 0.0;
    for (const double feature : templates.fingerprint[string]) {
      M3_EXPECT_TRUE(feature >= 0.0);
      norm += feature * feature;
    }
    M3_EXPECT_NEAR(norm, 1.0, 2.0e-4);
  }

  M3_EXPECT_FALSE(m3::factory_unison_spectral_templates(
      m3::UnisonSpectralPhase::settled, 127U, templates));
  M3_EXPECT_EQ(templates.valid_mask, 0U);
}

M3_TEST(cached_unison_reacquisition_is_bounded_by_live_physical_evidence) {
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 5U, true, 0.25, true,
                   true, false),
               0x07U);
  // A single surviving lane cannot receive multi-string privilege.
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x02U, 0x07U, 0x02U, 0xffU, 5U, true, 0.25, true,
                   true, false),
               0x02U);
  // Expired cache, silence, weak beat evidence, and a classifier mismatch
  // each preserve the ordinary current assignment.
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 5U, true, 0.25, false,
                   true, false),
               0x06U);
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 5U, true, 0.25, true,
                   true, true),
               0x06U);
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 5U, true, 0.19, true,
                   true, false),
               0x06U);
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 5U, true, 0.25, true,
                   false, false),
               0x06U);
  // Physical playability and the configured voice ceiling stay authoritative.
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0x03U, 5U, true, 0.25, true,
                   true, false),
               0x06U);
  M3_EXPECT_EQ(m3::bounded_cached_unison_reacquisition(
                   0x06U, 0x07U, 0x06U, 0xffU, 2U, true, 0.25, true,
                   true, false),
               0x06U);
}

M3_TEST(observed_unison_reacquisition_requires_complete_live_revalidation) {
  m3::ObservedUnisonReacquisitionEvidence evidence;
  evidence.current_assignment_mask = 0x06U;
  evidence.cached_group_mask = 0x07U;
  evidence.pending_fine_mask = 0x06U;
  evidence.spectral_tier_mask = 0x07U;
  evidence.playable_mask = 0xffU;
  evidence.maximum_polyphony = 5U;
  evidence.direct_fundamental = true;
  evidence.cache_age_seconds = 0.30;
  evidence.maximum_cache_age_seconds = 0.50;
  evidence.pending_evidence_seconds = 0.25;
  evidence.minimum_revalidation_seconds = 0.20;
  evidence.pending_beat_coherence = 0.25;
  evidence.cached_fingerprint_valid = true;
  evidence.current_fingerprint_valid = true;
  evidence.fingerprint_squared_distance = 0.004;
  evidence.maximum_fingerprint_squared_distance = 0.005;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x07U);

  evidence.current_assignment_mask = 0x02U;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x02U);
  evidence.current_assignment_mask = 0x06U;
  evidence.pending_evidence_seconds = 0.19;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x06U);
  evidence.pending_evidence_seconds = 0.25;
  evidence.fingerprint_squared_distance = 0.006;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x06U);
  evidence.fingerprint_squared_distance = 0.004;
  evidence.other_owned_mask = 0x01U;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x06U);
  evidence.other_owned_mask = 0U;
  evidence.quiet = true;
  M3_EXPECT_EQ(m3::bounded_observed_unison_reacquisition(evidence), 0x06U);
}

M3_TEST(observed_unison_cache_refresh_requires_live_exact_group_evidence) {
  M3_EXPECT_TRUE(m3::bounded_observed_unison_cache_refresh(
      true, true, false, false, 0x07U, 0x07U));
  M3_EXPECT_TRUE(m3::bounded_observed_unison_cache_refresh(
      true, false, true, false, 0x07U, 0x07U));
  M3_EXPECT_FALSE(m3::bounded_observed_unison_cache_refresh(
      true, false, false, false, 0x07U, 0x07U));
  M3_EXPECT_FALSE(m3::bounded_observed_unison_cache_refresh(
      true, false, true, true, 0x07U, 0x07U));
  M3_EXPECT_FALSE(m3::bounded_observed_unison_cache_refresh(
      true, false, true, false, 0x07U, 0x03U));
  M3_EXPECT_FALSE(m3::bounded_observed_unison_cache_refresh(
      true, false, true, false, 0x03U, 0x03U));
}
