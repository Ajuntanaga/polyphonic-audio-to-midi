#include <algorithm>
#include <cmath>
#include <cstddef>
#include <sstream>
#include <string>

#include "m3/pitch_math.hpp"
#include "test_support.hpp"
#include "unison_spectral_shadow.hpp"

namespace {

constexpr double kTwoPi = 6.28318530717958647692;

m3::UnisonSpectralFingerprint run_tone(double amplitude) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 69U;
  m3::offline::UnisonSpectralCorridorTracker tracker;
  if (!tracker.configure(kSampleRate, kNote)) {
    return {};
  }
  const double frequency = m3::midi_to_frequency(kNote, 440.0);
  for (std::size_t sample = 0U;
       sample < static_cast<std::size_t>(0.60 * kSampleRate); ++sample) {
    tracker.observe(amplitude * std::sin(
        kTwoPi * frequency * static_cast<double>(sample) / kSampleRate));
  }
  return tracker.fingerprint();
}

}  // namespace

M3_TEST(unison_spectral_shadow_parses_closed_template_banks) {
  std::ostringstream text;
  text << "phase\tmidi_note\tstring_index\tfingerprint\n";
  for (const char* phase : {"corridor", "onset", "settled"}) {
    text << phase << "\t56\t2\t";
    for (std::size_t feature = 0U;
         feature < m3::kUnisonSpectralFeatureCount; ++feature) {
      text << (feature == 0U ? "" : ",")
           << (feature == 1U ? 1.0 : 0.0);
    }
    text << "\n";
  }
  const std::string valid = text.str();
  m3::offline::UnisonSpectralShadowTemplateBank templates;
  M3_EXPECT_TRUE(m3::offline::parse_unison_spectral_shadow_templates(
      valid.data(), valid.size(), templates));
  for (std::size_t phase = 0U; phase < 3U; ++phase) {
    M3_EXPECT_EQ(templates.by_phase[phase][56U].valid_mask, 0x04U);
    M3_EXPECT_NEAR(
        templates.by_phase[phase][56U].fingerprint[2U][1U], 1.0,
        1.0e-12);
  }

  const std::size_t first_row = valid.find('\n') + 1U;
  const std::size_t first_row_end = valid.find('\n', first_row) + 1U;
  const std::string duplicate =
      valid + valid.substr(first_row, first_row_end - first_row);
  M3_EXPECT_FALSE(m3::offline::parse_unison_spectral_shadow_templates(
      duplicate.data(), duplicate.size(), templates));
  const std::string malformed =
      "phase\tmidi_note\tstring_index\tfingerprint\n"
      "corridor\t56\t2\t1,0\n";
  M3_EXPECT_FALSE(m3::offline::parse_unison_spectral_shadow_templates(
      malformed.data(), malformed.size(), templates));
}

M3_TEST(unison_spectral_shadow_fingerprint_is_scale_invariant) {
  const auto quiet = run_tone(0.20);
  const auto loud = run_tone(0.80);
  double quiet_norm = 0.0;
  double loud_norm = 0.0;
  double dot = 0.0;
  for (std::size_t feature = 0U; feature < quiet.size(); ++feature) {
    quiet_norm += quiet[feature] * quiet[feature];
    loud_norm += loud[feature] * loud[feature];
    dot += quiet[feature] * loud[feature];
  }
  M3_EXPECT_NEAR(quiet_norm, 1.0, 1.0e-10);
  M3_EXPECT_NEAR(loud_norm, 1.0, 1.0e-10);
  M3_EXPECT_TRUE(dot > 0.999999);
}

M3_TEST(candidate_spectral_admission_requires_independent_bounded_evidence) {
  m3::offline::CandidateSpectralAdmissionEvidence evidence;
  evidence.score_threshold_ratio = 0.82;
  evidence.fundamental_score_ratio = 0.91;
  evidence.direct_fundamental_peak = true;
  evidence.local_peak = true;

  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x04U;
  classification.member_count = 1U;
  classification.error = 0.08;
  classification.runner_up_error = 0.20;
  classification.posterior_margin = 0.12;

  const m3::offline::CandidateSpectralAdmissionLimits limits{
      0.80, 0.60, 0.10, 0.10};
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, classification, 0x0cU, 0x01U, 3U, 5U, limits),
               0x04U);

  auto rejected = evidence;
  rejected.direct_fundamental_peak = false;
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   rejected, classification, 0x0cU, 0x01U, 3U, 5U, limits),
               0U);
  rejected = evidence;
  rejected.score_threshold_ratio = 0.79;
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   rejected, classification, 0x0cU, 0x01U, 3U, 5U, limits),
               0U);

  auto ambiguous = classification;
  ambiguous.posterior_margin = 0.09;
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, ambiguous, 0x0cU, 0x01U, 3U, 5U, limits),
               0U);
  auto poor_fit = classification;
  poor_fit.error = 0.11;
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, poor_fit, 0x0cU, 0x01U, 3U, 5U, limits),
               0U);

  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, classification, 0x02U, 0x01U, 3U, 5U, limits),
               0U);
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, classification, 0x0cU, 0x05U, 3U, 5U, limits),
               0U);
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, classification, 0x0cU, 0x01U, 5U, 5U, limits),
               0U);

  auto group = classification;
  group.member_mask = 0x0cU;
  group.member_count = 2U;
  M3_EXPECT_EQ(m3::offline::bounded_candidate_spectral_admission(
                   evidence, group, 0x0cU, 0x01U, 3U, 5U, limits),
               0U);
}

M3_TEST(combined_candidate_admission_requires_calibration_and_spectral_agreement) {
  m3::offline::CombinedCandidateAdmissionEvidence evidence;
  evidence.score_threshold_ratio = 0.12;
  evidence.fundamental_score_ratio = 0.90;
  evidence.pitch_band_score_peak_ratio = 0.95;
  evidence.pitch_band_fundamental_peak_ratio = 0.90;
  evidence.best_calibration_similarity = 0.985;
  evidence.calibration_margin = 0.035;
  evidence.best_calibrated_string = 6U;
  evidence.direct_fundamental_peak = true;
  evidence.local_or_candidate_peak = true;

  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x40U;
  classification.member_count = 1U;
  classification.error = 0.08;
  classification.posterior_margin = 0.05;

  const m3::offline::CombinedCandidateAdmissionLimits limits{
      0.10, 6U, 0.10, 0.04};
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   evidence, classification, 0xc0U, 0x01U, 3U, 5U,
                   limits),
               0x40U);

  auto mismatch = classification;
  mismatch.member_mask = 0x80U;
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   evidence, mismatch, 0xc0U, 0x01U, 3U, 5U, limits),
               0U);
  auto weak_calibration = evidence;
  weak_calibration.calibration_margin = 0.019;
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   weak_calibration, classification, 0xc0U, 0x01U, 3U, 5U,
                   limits),
               0U);
  auto weak_score = evidence;
  weak_score.score_threshold_ratio = 0.09;
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   weak_score, classification, 0xc0U, 0x01U, 3U, 5U,
                   limits),
               0U);
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   evidence, classification, 0xc0U, 0x41U, 3U, 5U,
                   limits),
               0U);
  const m3::offline::CombinedCandidateAdmissionLimits invalid_limits{
      -0.01, 6U, 0.10, 0.04};
  M3_EXPECT_EQ(m3::offline::bounded_combined_candidate_admission(
                   evidence, classification, 0xc0U, 0x01U, 3U, 5U,
                   invalid_limits),
               0U);
}

M3_TEST(candidate_spectral_false_interval_bucket_finds_nearest_active_pitch) {
  std::array<std::uint32_t, 128U> active{};
  M3_EXPECT_EQ(m3::offline::candidate_spectral_interval_bucket(64U, active),
               m3::offline::kCandidateSpectralIntervalBucketCount);
  active[40U] = 1U;
  active[52U] = 1U;
  M3_EXPECT_EQ(m3::offline::candidate_spectral_interval_bucket(64U, active),
               m3::offline::kCandidateSpectralIntervalRadius + 12U);
  M3_EXPECT_EQ(m3::offline::candidate_spectral_interval_bucket(28U, active),
               m3::offline::kCandidateSpectralIntervalRadius - 12U);
  M3_EXPECT_EQ(m3::offline::candidate_spectral_interval_bucket(127U, active),
               m3::offline::kCandidateSpectralIntervalBucketCount - 1U);
}

M3_TEST(unison_spectral_shadow_tracks_onset_and_settled_phases) {
  constexpr double kSampleRate = 48000.0;
  m3::offline::UnisonSpectralCorridorTracker tracker;
  M3_EXPECT_FALSE(tracker.configure(0.0, 69U));
  M3_EXPECT_FALSE(tracker.configure(kSampleRate, 128U));
  M3_EXPECT_TRUE(tracker.configure(kSampleRate, 69U));
  M3_EXPECT_EQ(tracker.phase(), m3::offline::SpectralShadowPhase::unready);

  for (std::size_t sample = 0U;
       sample < static_cast<std::size_t>(0.24 * kSampleRate); ++sample) {
    tracker.observe(std::sin(kTwoPi * 440.0 *
                            static_cast<double>(sample) / kSampleRate));
  }
  M3_EXPECT_TRUE(tracker.ready());
  M3_EXPECT_EQ(tracker.phase(), m3::offline::SpectralShadowPhase::onset);

  for (std::size_t sample = static_cast<std::size_t>(0.24 * kSampleRate);
       sample < static_cast<std::size_t>(0.50 * kSampleRate); ++sample) {
    tracker.observe(std::sin(kTwoPi * 440.0 *
                            static_cast<double>(sample) / kSampleRate));
  }
  M3_EXPECT_EQ(tracker.phase(), m3::offline::SpectralShadowPhase::settled);
  tracker.reset();
  M3_EXPECT_FALSE(tracker.ready());
  M3_EXPECT_EQ(tracker.phase(), m3::offline::SpectralShadowPhase::unready);
}

M3_TEST(unison_spectral_shadow_centers_a_matching_fundamental) {
  const auto observed = run_tone(0.5);
  const auto first_begin = observed.begin();
  const auto first_end = first_begin +
                         static_cast<std::ptrdiff_t>(
                             m3::kUnisonSpectralOffsetsPerHarmonic);
  const std::size_t peak = static_cast<std::size_t>(
      std::max_element(first_begin, first_end) - first_begin);
  M3_EXPECT_TRUE(peak == 16U || peak == 17U);
  M3_EXPECT_TRUE(observed[peak] > observed[0U]);
  M3_EXPECT_TRUE(observed[peak] >
                 observed[m3::kUnisonSpectralOffsetsPerHarmonic - 1U]);
}

M3_TEST(unison_spectral_shadow_bounded_proposal_requires_active_multi_evidence) {
  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x07U;
  classification.member_count = 3U;
  classification.posterior_margin = 0.004;

  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.25, 0x07U, 0U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.10, 0x07U, 0U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x03U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x03U, 0x01U, 0.90, 0x07U, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x03U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0U, 0x03U, 0.90, 0x07U, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x01U, 0x03U, 0.90, 0x07U, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x01U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x09U, 0x03U, 0.90, 0x07U, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x09U);
}

M3_TEST(unison_spectral_shadow_bounded_proposal_is_onset_aware) {
  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x07U;
  classification.member_count = 3U;
  classification.posterior_margin = 0.0015;

  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.30, 0x07U, 0U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.30, 0x07U, 0U,
                   m3::offline::SpectralShadowPhase::onset,
                   classification, 0.001),
               0x03U);
}

M3_TEST(unison_spectral_temporal_proposal_excludes_profile_only_expansion) {
  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x07U;
  classification.member_count = 3U;
  classification.posterior_margin = 0.004;

  M3_EXPECT_EQ(m3::offline::bounded_temporal_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.30, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_temporal_spectral_shadow_proposal(
                   0x03U, 0x03U, 0.30, 0x03U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x03U);
  M3_EXPECT_EQ(m3::offline::bounded_temporal_spectral_shadow_proposal(
                   0x03U, 0x07U, 0.0, 0x00U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x03U);
  M3_EXPECT_EQ(m3::offline::bounded_temporal_spectral_shadow_proposal(
                   0x09U, 0x03U, 0.30, 0x07U,
                   m3::offline::SpectralShadowPhase::settled,
                   classification, 0.001),
               0x09U);
}

M3_TEST(unison_spectral_onset_latch_commits_a_strict_majority_once) {
  m3::offline::SpectralOnsetMaskLatch latch;
  m3::UnisonSpectralClassification expected;
  expected.valid = true;
  expected.member_mask = 0x07U;
  expected.member_count = 3U;
  expected.posterior_margin = 0.004;
  m3::UnisonSpectralClassification harmonic = expected;
  harmonic.member_mask = 0x0eU;

  for (std::size_t vote = 0U; vote < 3U; ++vote) {
    latch.observe(m3::offline::SpectralShadowPhase::onset, expected, 0.001);
  }
  latch.observe(m3::offline::SpectralShadowPhase::onset, harmonic, 0.001);
  M3_EXPECT_FALSE(latch.committed());

  latch.observe(m3::offline::SpectralShadowPhase::settled, harmonic, 0.001);
  M3_EXPECT_TRUE(latch.committed());
  M3_EXPECT_EQ(latch.committed_mask(), 0x07U);
  M3_EXPECT_EQ(latch.qualified_votes(), 4U);
  M3_EXPECT_EQ(latch.winner_votes(), 3U);

  for (std::size_t frame = 0U; frame < 8U; ++frame) {
    latch.observe(m3::offline::SpectralShadowPhase::settled, harmonic, 0.001);
  }
  M3_EXPECT_EQ(latch.committed_mask(), 0x07U);
  M3_EXPECT_EQ(latch.qualified_votes(), 4U);
}

M3_TEST(unison_spectral_onset_latch_refuses_ties_weak_votes_and_singletons) {
  const auto classification = [](std::uint8_t mask, std::uint8_t members,
                                 double margin) {
    m3::UnisonSpectralClassification value;
    value.valid = true;
    value.member_mask = mask;
    value.member_count = members;
    value.posterior_margin = margin;
    return value;
  };

  m3::offline::SpectralOnsetMaskLatch tie;
  tie.observe(m3::offline::SpectralShadowPhase::onset,
              classification(0x03U, 2U, 0.01), 0.001);
  tie.observe(m3::offline::SpectralShadowPhase::onset,
              classification(0x0cU, 2U, 0.01), 0.001);
  tie.observe(m3::offline::SpectralShadowPhase::settled,
              classification(0x03U, 2U, 0.01), 0.001);
  M3_EXPECT_FALSE(tie.committed());

  m3::offline::SpectralOnsetMaskLatch weak;
  for (std::size_t vote = 0U; vote < 3U; ++vote) {
    weak.observe(m3::offline::SpectralShadowPhase::onset,
                 classification(0x03U, 2U, 0.01), 0.001);
  }
  for (std::size_t vote = 0U; vote < 2U; ++vote) {
    weak.observe(m3::offline::SpectralShadowPhase::onset,
                 classification(0x0cU, 2U, 0.01), 0.001);
  }
  weak.observe(m3::offline::SpectralShadowPhase::onset,
               classification(0x30U, 2U, 0.01), 0.001);
  weak.observe(m3::offline::SpectralShadowPhase::settled,
               classification(0x03U, 2U, 0.01), 0.001);
  M3_EXPECT_FALSE(weak.committed());
  M3_EXPECT_EQ(weak.qualified_votes(), 6U);

  m3::offline::SpectralOnsetMaskLatch ignored;
  ignored.observe(m3::offline::SpectralShadowPhase::onset,
                  classification(0x01U, 1U, 0.01), 0.001);
  ignored.observe(m3::offline::SpectralShadowPhase::onset,
                  classification(0x03U, 2U, 0.0005), 0.001);
  ignored.observe(m3::offline::SpectralShadowPhase::settled,
                  classification(0x03U, 2U, 0.01), 0.001);
  M3_EXPECT_FALSE(ignored.committed());
  M3_EXPECT_EQ(ignored.qualified_votes(), 0U);
}

M3_TEST(unison_spectral_onset_latch_reset_starts_a_new_note_interval) {
  m3::offline::SpectralOnsetMaskLatch latch;
  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x0bU;
  classification.member_count = 3U;
  classification.posterior_margin = 0.01;
  latch.observe(m3::offline::SpectralShadowPhase::onset, classification, 0.001);
  latch.observe(m3::offline::SpectralShadowPhase::settled, classification,
                0.001);
  M3_EXPECT_TRUE(latch.committed());

  latch.reset();
  M3_EXPECT_FALSE(latch.committed());
  M3_EXPECT_EQ(latch.committed_mask(), 0U);
  M3_EXPECT_EQ(latch.qualified_votes(), 0U);
}

M3_TEST(unison_spectral_onset_projection_respects_physical_constraints) {
  using m3::offline::bounded_spectral_onset_latch_projection;
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x07U, 0x80U, 0xffU, 5U),
      0x07U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x08U, 0x07U, 0x80U, 0xffU, 5U),
      0x08U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0U, 0x07U, 0x80U, 0xffU, 5U),
      0U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x01U, 0x80U, 0xffU, 5U),
      0x01U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x07U, 0x04U, 0xffU, 5U),
      0x01U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x07U, 0x80U, 0x03U, 5U),
      0x01U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x07U, 0x70U, 0xffU, 5U),
      0x01U);
  M3_EXPECT_EQ(
      bounded_spectral_onset_latch_projection(0x01U, 0x07U, 0x80U, 0xffU, 0U),
      0x01U);
}

M3_TEST(unison_reacquisition_shadow_requires_live_subset_evidence) {
  using m3::offline::bounded_unison_reacquisition_cache_mask;
  using m3::offline::bounded_unison_reacquisition_projection;
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0U, 0x07U, 0x07U, 0x07U,
                                              false),
      0x07U);
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0x07U, 0x03U, 0x07U, 0x07U,
                                              false),
      0x07U);
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0x07U, 0x06U, 0x06U, 0x06U,
                                              false),
      0x07U);
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0x03U, 0x07U, 0x07U, 0x07U,
                                              false),
      0x07U);
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0x07U, 0x07U, 0x07U, 0x07U,
                                              true),
      0x07U);
  M3_EXPECT_EQ(
      bounded_unison_reacquisition_cache_mask(0U, 0x07U, 0x03U, 0x07U,
                                              false),
      0U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, true,
                   0.25, true, false),
               0x07U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x02U, 0x07U, 0x06U, 0x02U, 0x80U, 0xffU, 5U, true,
                   0.25, true, false),
               0x07U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x02U, 0x07U, 0x06U, 0x01U, 0x80U, 0xffU, 5U, true,
                   0.25, true, false),
               0x02U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, true, 0.25,
                   true, false),
               0U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0U, 0x06U, 0x80U, 0xffU, 5U, true, 0.25,
                   true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0U, 0x80U, 0xffU, 5U, true, 0.25,
                   true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, false,
                   0.25, true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, true,
                   0.25, true, true),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x01U, 0xffU, 5U, true,
                   0.25, true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0x03U, 5U, true,
                   0.25, true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, true,
                   0.19, true, false),
               0x06U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x01U, 0x03U, 0x03U, 0x03U, 0x80U, 0xffU, 5U, true,
                   0.25, true, false),
               0x01U);
  M3_EXPECT_EQ(bounded_unison_reacquisition_projection(
                   0x06U, 0x07U, 0x06U, 0x06U, 0x80U, 0xffU, 5U, true,
                   0.25, false, false),
               0x06U);
}

M3_TEST(articulated_unison_reacquisition_requires_fresh_bounded_evidence) {
  using m3::offline::ArticulatedUnisonReacquisitionDisposition;
  using m3::offline::bounded_articulated_unison_reacquisition_projection;

  const auto accepted = bounded_articulated_unison_reacquisition_projection(
      0x03U, 0x07U, 0x03U, 0.36, 0.24, 0x07U, 0x80U, 0xffU, 5U,
      true, false, 0.48, 0.50, 0.35);
  M3_EXPECT_EQ(accepted.projected_mask, 0x07U);
  M3_EXPECT_EQ(accepted.disposition,
               ArticulatedUnisonReacquisitionDisposition::accepted);

  const auto insufficient =
      bounded_articulated_unison_reacquisition_projection(
          0x03U, 0x07U, 0x03U, 0.34, 0.24, 0x07U, 0x80U, 0xffU, 5U,
          true, false, 0.48, 0.50, 0.35);
  M3_EXPECT_EQ(insufficient.projected_mask, 0x03U);
  M3_EXPECT_EQ(
      insufficient.disposition,
      ArticulatedUnisonReacquisitionDisposition::pending_insufficient);

  const auto expired = bounded_articulated_unison_reacquisition_projection(
      0x03U, 0x07U, 0x03U, 0.50, 0.24, 0x07U, 0x80U, 0xffU, 5U,
      true, false, 0.51, 0.50, 0.35);
  M3_EXPECT_EQ(expired.projected_mask, 0x03U);
  M3_EXPECT_EQ(expired.disposition,
               ArticulatedUnisonReacquisitionDisposition::cache_expired);

  const auto quiet = bounded_articulated_unison_reacquisition_projection(
      0x03U, 0x07U, 0x03U, 0.50, 0.24, 0x07U, 0x80U, 0xffU, 5U,
      true, true, 0.20, 0.50, 0.35);
  M3_EXPECT_EQ(quiet.projected_mask, 0x03U);
  M3_EXPECT_EQ(quiet.disposition,
               ArticulatedUnisonReacquisitionDisposition::quiet);

  const auto wrong_tier =
      bounded_articulated_unison_reacquisition_projection(
          0x03U, 0x07U, 0x03U, 0.50, 0.24, 0x03U, 0x80U, 0xffU, 5U,
          true, false, 0.20, 0.50, 0.35);
  M3_EXPECT_EQ(wrong_tier.projected_mask, 0x03U);
  M3_EXPECT_EQ(wrong_tier.disposition,
               ArticulatedUnisonReacquisitionDisposition::tier_mismatch);

  const auto wrong_pending =
      bounded_articulated_unison_reacquisition_projection(
          0x03U, 0x07U, 0x0bU, 0.50, 0.24, 0x07U, 0x80U, 0xffU, 5U,
          true, false, 0.20, 0.50, 0.35);
  M3_EXPECT_EQ(wrong_pending.projected_mask, 0x03U);
  M3_EXPECT_EQ(
      wrong_pending.disposition,
      ArticulatedUnisonReacquisitionDisposition::pending_mask_invalid);

  const auto overlap = bounded_articulated_unison_reacquisition_projection(
      0x03U, 0x07U, 0x03U, 0.50, 0.24, 0x07U, 0x04U, 0xffU, 5U,
      true, false, 0.20, 0.50, 0.35);
  M3_EXPECT_EQ(overlap.projected_mask, 0x03U);
  M3_EXPECT_EQ(overlap.disposition,
               ArticulatedUnisonReacquisitionDisposition::ownership_conflict);
}

M3_TEST(unison_spectral_tier_completion_adds_only_one_beat_coherent_member) {
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kHeads{
      0U, 1U, 2U, 1U, 2U};
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.004, 0.008, 0.007, 0.006, 0.005};

  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.25, 0.11,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x02U, 0x06U, 0.25, 0.11,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.10, 0.08,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x06U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.75, 0.08,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x06U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.32, 0.09,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x06U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.32, 0.11,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x07U);
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x02U, 0x02U, 0.90, 0.08,
                   m3::offline::SpectralShadowPhase::settled, kHeads,
                   kMargins, 0.001),
               0x02U);

  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U>
      kTwoExtraHeads{0U, 3U, 1U, 2U, 3U};
  M3_EXPECT_EQ(m3::offline::bounded_spectral_tier_completion_proposal(
                   0x06U, 0x06U, 0.25, 0.08,
                   m3::offline::SpectralShadowPhase::settled, kTwoExtraHeads,
                   kMargins, 0.001),
               0x06U);
}

M3_TEST(selected_subset_completion_requires_unique_bounded_consensus) {
  using m3::offline::bounded_selected_subset_completion_projection;
  const std::array<std::uint8_t, 6U> two_votes{0x07U, 0x07U, 0x03U,
                                                0x00U, 0x00U, 0x00U};
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, two_votes, 0x00U, 0xffU, 5U, 2U, true, 0.20,
                   false, false),
               0x07U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, two_votes, 0x00U, 0xffU, 5U, 3U, true, 0.20,
                   false, false),
               0x03U);

  const std::array<std::uint8_t, 6U> tie{0x07U, 0x07U, 0x0bU,
                                        0x0bU, 0x00U, 0x00U};
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, tie, 0x00U, 0xffU, 5U, 2U, true, 0.20, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, two_votes, 0x00U, 0xffU, 5U, 2U, true, 0.10,
                   true, false),
               0x07U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, two_votes, 0x00U, 0xffU, 5U, 2U, true, 0.099,
                   true, false),
               0x03U);
}

M3_TEST(physical_tier_completion_requires_live_owned_capacity) {
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kHeads{
      0U, 1U, 2U, 2U, 1U};
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.01, 0.01, 0.01, 0.01, 0.01};
  using m3::offline::bounded_physical_tier_completion_projection;
  const auto project = [&](std::uint8_t owned, std::uint8_t playable,
                           std::uint8_t polyphony, bool quiet) {
    return bounded_physical_tier_completion_projection(
        0x03U, 0x03U, 0.25, 0.20,
        m3::offline::SpectralShadowPhase::settled, kHeads, kMargins,
        owned, playable, polyphony, quiet);
  };
  M3_EXPECT_EQ(project(0x00U, 0xffU, 5U, false), 0x07U);
  M3_EXPECT_EQ(project(0x04U, 0xffU, 5U, false), 0x03U);
  M3_EXPECT_EQ(project(0x00U, 0x03U, 5U, false), 0x03U);
  M3_EXPECT_EQ(project(0x18U, 0xffU, 4U, false), 0x03U);
  M3_EXPECT_EQ(project(0x00U, 0xffU, 5U, true), 0x03U);
}

M3_TEST(selected_subset_completion_preserves_physical_and_release_bounds) {
  using m3::offline::bounded_selected_subset_completion_projection;
  const std::array<std::uint8_t, 6U> votes{0x07U, 0x07U, 0x07U,
                                          0x00U, 0x00U, 0x00U};
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x04U, 0xffU, 5U, 2U, true, 0.20, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x00U, 0x03U, 5U, 2U, true, 0.20, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x18U, 0xffU, 4U, 2U, true, 0.20, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x00U, 0xffU, 5U, 2U, false, 0.20, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x00U, 0xffU, 5U, 2U, true, 0.19, false,
                   false),
               0x03U);
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, votes, 0x00U, 0xffU, 5U, 2U, true, 0.20, false,
                   true),
               0x03U);

  const std::array<std::uint8_t, 6U> replaces_lane{0x05U, 0x05U, 0x05U,
                                                  0x00U, 0x00U, 0x00U};
  M3_EXPECT_EQ(bounded_selected_subset_completion_projection(
                   0x03U, replaces_lane, 0x00U, 0xffU, 5U, 2U, true, 0.20,
                   false, false),
               0x03U);
}

M3_TEST(classifier_subset_completion_is_one_lane_and_physically_bounded) {
  using m3::offline::ClassifierSubsetDisposition;
  using m3::offline::bounded_classifier_subset_completion_projection;
  using m3::offline::diagnose_classifier_subset_completion_projection;
  m3::UnisonSpectralClassification classification{};
  classification.valid = true;
  classification.member_mask = 0x07U;
  classification.member_count = 3U;
  classification.error = 0.04;
  classification.posterior_margin = 0.02;
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.20,
                   false, 0.05, 0.01, false),
               0x07U);
  M3_EXPECT_EQ(diagnose_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.20,
                   false, 0.05, 0.01, false)
                   .disposition,
               ClassifierSubsetDisposition::accepted);
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x04U, 0xffU, 5U, true, 0.20,
                   false, 0.05, 0.01, false),
               0x03U);
  M3_EXPECT_EQ(diagnose_classifier_subset_completion_projection(
                   0x03U, classification, 0x04U, 0xffU, 5U, true, 0.20,
                   false, 0.05, 0.01, false)
                   .disposition,
               ClassifierSubsetDisposition::ownership_conflict);
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0x03U, 5U, true, 0.20,
                   false, 0.05, 0.01, false),
               0x03U);
  M3_EXPECT_EQ(diagnose_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.099,
                   true, 0.05, 0.01, false)
                   .disposition,
               ClassifierSubsetDisposition::beat_below_gate);
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.10,
                   true, 0.05, 0.01, false),
               0x07U);
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.099,
                   true, 0.05, 0.01, false),
               0x03U);

  classification.member_mask = 0x0fU;
  classification.member_count = 4U;
  M3_EXPECT_EQ(bounded_classifier_subset_completion_projection(
                   0x03U, classification, 0x00U, 0xffU, 5U, true, 0.20,
                   false, 0.05, 0.01, false),
               0x03U);
}

M3_TEST(projection_union_accepts_agreement_and_refuses_conflicting_changes) {
  using m3::offline::bounded_projection_union;
  M3_EXPECT_EQ(bounded_projection_union(0x03U, 0x07U, 0x07U), 0x07U);
  M3_EXPECT_EQ(bounded_projection_union(0x03U, 0x07U, 0x03U), 0x07U);
  M3_EXPECT_EQ(bounded_projection_union(0x03U, 0x03U, 0x07U), 0x07U);
  M3_EXPECT_EQ(bounded_projection_union(0x03U, 0x07U, 0x0bU), 0x03U);
}
