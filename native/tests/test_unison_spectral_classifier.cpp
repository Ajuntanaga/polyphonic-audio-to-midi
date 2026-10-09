#include <cmath>
#include <limits>

#include "m3/unison_spectral_classifier.hpp"
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
