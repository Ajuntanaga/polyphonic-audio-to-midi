#include <cmath>
#include <limits>

#include "m3/string_fret_posterior.hpp"
#include "test_support.hpp"

namespace {

m3::StringFretLikelihoodFrame two_string_frame(double first, double second,
                                                double onset) noexcept {
  m3::StringFretLikelihoodFrame frame;
  frame.playable_mask = 0x03U;
  frame.log_likelihood[0U] = first;
  frame.log_likelihood[1U] = second;
  frame.onset_strength = onset;
  return frame;
}

}  // namespace

M3_TEST(string_fret_posterior_retains_alternatives_and_accumulates_evidence) {
  m3::StringFretPosteriorBank posterior;
  M3_EXPECT_TRUE(posterior.update(7U, two_string_frame(3.0, 0.0, 1.0)));
  const double initial_first = posterior.probability(7U, 0U);
  const double initial_second = posterior.probability(7U, 1U);
  M3_EXPECT_TRUE(initial_first > initial_second);
  M3_EXPECT_TRUE(initial_second > 0.0);

  M3_EXPECT_TRUE(posterior.update(7U, two_string_frame(0.0, 1.0, 0.0)));
  M3_EXPECT_TRUE(posterior.probability(7U, 0U) >
                 posterior.probability(7U, 1U));
  for (std::size_t frame = 0U; frame < 16U; ++frame) {
    M3_EXPECT_TRUE(posterior.update(7U, two_string_frame(0.0, 1.0, 0.0)));
  }
  M3_EXPECT_TRUE(posterior.probability(7U, 1U) >
                 posterior.probability(7U, 0U));
}

M3_TEST(string_fret_posterior_weakens_history_at_a_new_onset) {
  m3::StringFretPosteriorBank posterior;
  for (std::size_t frame = 0U; frame < 12U; ++frame) {
    M3_EXPECT_TRUE(posterior.update(3U, two_string_frame(2.0, 0.0, 0.0)));
  }
  M3_EXPECT_TRUE(posterior.probability(3U, 0U) > 0.95);

  M3_EXPECT_TRUE(posterior.update(3U, two_string_frame(0.0, 3.0, 1.0)));
  M3_EXPECT_TRUE(posterior.probability(3U, 1U) >
                 posterior.probability(3U, 0U));
}

M3_TEST(string_fret_posterior_is_bounded_and_rejects_invalid_frames) {
  m3::StringFretPosteriorBank posterior;
  auto frame = two_string_frame(1.0, 0.0, 0.0);
  M3_EXPECT_FALSE(posterior.update(m3::kMaxCandidates, frame));
  frame.onset_strength = 1.1;
  M3_EXPECT_FALSE(posterior.update(0U, frame));
  frame = two_string_frame(1.0, 0.0, 0.0);
  frame.log_likelihood[1U] = std::numeric_limits<double>::infinity();
  M3_EXPECT_FALSE(posterior.update(0U, frame));

  frame = two_string_frame(1.0, 0.0, 0.0);
  M3_EXPECT_TRUE(posterior.update(0U, frame));
  M3_EXPECT_EQ(posterior.best_string(0U), 0U);
  M3_EXPECT_NEAR(posterior.probability(0U, 0U) +
                     posterior.probability(0U, 1U),
                 1.0, 1.0e-12);
  M3_EXPECT_NEAR(posterior.probability(0U, 2U), 0.0, 0.0);
  M3_EXPECT_TRUE(std::isfinite(posterior.negative_log_probability(0U, 0U)));

  posterior.reset(0U);
  M3_EXPECT_EQ(posterior.best_string(0U), m3::kUnassignedTunerString);
  M3_EXPECT_NEAR(posterior.probability(0U, 0U), 0.0, 0.0);
}
