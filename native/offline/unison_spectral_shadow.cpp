#include "unison_spectral_shadow.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>
#include <string_view>

#include "m3/pitch_math.hpp"

namespace m3::offline {
namespace {

std::uint8_t popcount(std::uint8_t mask) noexcept {
  std::uint8_t count = 0U;
  while (mask != 0U) {
    count = static_cast<std::uint8_t>(count + (mask & 1U));
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return count;
}

}  // namespace

std::uint8_t bounded_candidate_spectral_admission(
    const CandidateSpectralAdmissionEvidence& evidence,
    const UnisonSpectralClassification& classification,
    std::uint8_t playable_mask, std::uint8_t occupied_mask,
    std::uint8_t current_voice_count, std::uint8_t maximum_polyphony,
    const CandidateSpectralAdmissionLimits& limits) noexcept {
  const std::uint8_t member = classification.member_mask;
  const bool one_member =
      member != 0U && (member & static_cast<std::uint8_t>(member - 1U)) == 0U;
  if (!std::isfinite(evidence.score_threshold_ratio) ||
      !std::isfinite(evidence.fundamental_score_ratio) ||
      !std::isfinite(limits.minimum_score_ratio) ||
      !std::isfinite(limits.minimum_fundamental_ratio) ||
      !std::isfinite(limits.maximum_error) ||
      !std::isfinite(limits.minimum_margin) ||
      limits.minimum_score_ratio < 0.0 ||
      limits.minimum_fundamental_ratio < 0.0 ||
      limits.maximum_error < 0.0 || limits.minimum_margin < 0.0 ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      current_voice_count >= maximum_polyphony ||
      !evidence.direct_fundamental_peak ||
      (!evidence.local_peak && !evidence.candidate_evidence) ||
      evidence.score_threshold_ratio < limits.minimum_score_ratio ||
      evidence.fundamental_score_ratio < limits.minimum_fundamental_ratio ||
      !classification.valid || classification.member_count != 1U ||
      !one_member || !std::isfinite(classification.error) ||
      classification.error < 0.0 ||
      classification.error > limits.maximum_error ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < limits.minimum_margin ||
      (member & playable_mask) != member || (member & occupied_mask) != 0U) {
    return 0U;
  }
  return member;
}

std::uint8_t bounded_combined_candidate_admission(
    const CombinedCandidateAdmissionEvidence& evidence,
    const UnisonSpectralClassification& classification,
    std::uint8_t playable_mask, std::uint8_t occupied_mask,
    std::uint8_t current_voice_count, std::uint8_t maximum_polyphony,
    const CombinedCandidateAdmissionLimits& limits) noexcept {
  if (!std::isfinite(evidence.score_threshold_ratio) ||
      !std::isfinite(evidence.fundamental_score_ratio) ||
      !std::isfinite(evidence.pitch_band_score_peak_ratio) ||
      !std::isfinite(evidence.pitch_band_fundamental_peak_ratio) ||
      !std::isfinite(evidence.best_calibration_similarity) ||
      !std::isfinite(evidence.calibration_margin) ||
      !std::isfinite(limits.minimum_score_ratio) ||
      !std::isfinite(limits.maximum_spectral_error) ||
      !std::isfinite(limits.minimum_spectral_margin) ||
      limits.minimum_score_ratio < 0.0 ||
      limits.maximum_spectral_error < 0.0 ||
      limits.minimum_spectral_margin < 0.0 ||
      evidence.score_threshold_ratio < limits.minimum_score_ratio ||
      evidence.fundamental_score_ratio < 0.80 ||
      evidence.pitch_band_score_peak_ratio < 0.90 ||
      evidence.pitch_band_fundamental_peak_ratio < 0.80 ||
      evidence.best_calibration_similarity < 0.97 ||
      evidence.calibration_margin < 0.02 ||
      evidence.best_calibrated_string < limits.minimum_string ||
      evidence.best_calibrated_string >= kMaxVoices ||
      !evidence.direct_fundamental_peak ||
      !evidence.local_or_candidate_peak || !classification.valid ||
      classification.member_count != 1U ||
      !std::isfinite(classification.error) ||
      classification.error > limits.maximum_spectral_error ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < limits.minimum_spectral_margin ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      current_voice_count >= maximum_polyphony) {
    return 0U;
  }
  const std::uint8_t calibrated_bit = static_cast<std::uint8_t>(
      1U << evidence.best_calibrated_string);
  if (classification.member_mask != calibrated_bit ||
      (classification.member_mask & playable_mask) == 0U ||
      (classification.member_mask & occupied_mask) != 0U) {
    return 0U;
  }
  return classification.member_mask;
}

std::size_t candidate_spectral_interval_bucket(
    std::uint8_t candidate_note,
    const std::array<std::uint32_t, 128U>& active_references) noexcept {
  bool found = false;
  int nearest = 0;
  for (std::size_t note = 0U; note < active_references.size(); ++note) {
    if (active_references[note] == 0U) {
      continue;
    }
    const int delta = static_cast<int>(candidate_note) -
                      static_cast<int>(note);
    if (!found || std::abs(delta) < std::abs(nearest) ||
        (std::abs(delta) == std::abs(nearest) && delta < nearest)) {
      nearest = delta;
      found = true;
    }
  }
  if (!found) {
    return kCandidateSpectralIntervalBucketCount;
  }
  const int radius = static_cast<int>(kCandidateSpectralIntervalRadius);
  return static_cast<std::size_t>(std::clamp(nearest, -radius, radius) +
                                  radius);
}

std::uint8_t bounded_spectral_shadow_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double minimum_beat_coherence, std::uint8_t profile_mask,
    std::uint8_t temporal_mask, SpectralShadowPhase phase,
    const UnisonSpectralClassification& classification,
    double minimum_margin) noexcept {
  const std::uint8_t fine_members = popcount(fine_frequency_mask);
  const std::uint8_t current_members = popcount(current_assignment_mask);
  const std::uint8_t spectral_members = popcount(classification.member_mask);
  const double phase_multiplier =
      phase == SpectralShadowPhase::onset ? 2.0 : 1.0;
  if (current_members < 2U || current_members > 4U || fine_members < 2U ||
      fine_members > 4U ||
      !classification.valid || spectral_members < 2U || spectral_members > 4U ||
      classification.member_count != spectral_members ||
      (classification.member_mask & current_assignment_mask) !=
          current_assignment_mask ||
      !std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < minimum_margin * phase_multiplier) {
    return current_assignment_mask;
  }
  const bool exact_fine_agreement =
      classification.member_mask == fine_frequency_mask;
  const bool corroborated_expansion =
      std::isfinite(minimum_beat_coherence) &&
      minimum_beat_coherence >= 0.20 &&
      (classification.member_mask & fine_frequency_mask) ==
          fine_frequency_mask &&
      (classification.member_mask == profile_mask ||
       classification.member_mask == temporal_mask);
  return exact_fine_agreement || corroborated_expansion
             ? classification.member_mask
             : current_assignment_mask;
}

std::uint8_t bounded_temporal_spectral_shadow_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double minimum_beat_coherence, std::uint8_t temporal_mask,
    SpectralShadowPhase phase,
    const UnisonSpectralClassification& classification,
    double minimum_margin) noexcept {
  const std::uint8_t fine_members = popcount(fine_frequency_mask);
  const std::uint8_t current_members = popcount(current_assignment_mask);
  const std::uint8_t spectral_members = popcount(classification.member_mask);
  const double phase_multiplier =
      phase == SpectralShadowPhase::onset ? 2.0 : 1.0;
  if (current_members < 2U || current_members > 4U || fine_members < 2U ||
      fine_members > 4U ||
      !classification.valid || spectral_members < 2U || spectral_members > 4U ||
      classification.member_count != spectral_members ||
      (classification.member_mask & current_assignment_mask) !=
          current_assignment_mask ||
      !std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < minimum_margin * phase_multiplier) {
    return current_assignment_mask;
  }
  const bool temporally_corroborated_expansion =
      std::isfinite(minimum_beat_coherence) &&
      minimum_beat_coherence >= 0.20 &&
      (classification.member_mask & fine_frequency_mask) ==
          fine_frequency_mask &&
      classification.member_mask == temporal_mask;
  return temporally_corroborated_expansion ? classification.member_mask
                                            : current_assignment_mask;
}

void SpectralOnsetMaskLatch::observe(
    SpectralShadowPhase phase,
    const UnisonSpectralClassification& classification,
    double minimum_margin) noexcept {
  if (settled_) {
    return;
  }
  if (phase == SpectralShadowPhase::settled) {
    settle();
    return;
  }
  if (phase != SpectralShadowPhase::onset || !classification.valid ||
      !std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < minimum_margin) {
    return;
  }
  const std::uint8_t members = popcount(classification.member_mask);
  if (members < 2U || members > 4U ||
      classification.member_count != members) {
    return;
  }
  std::uint32_t& votes = votes_[classification.member_mask];
  if (votes != std::numeric_limits<std::uint32_t>::max()) {
    ++votes;
  }
  if (qualified_votes_ != std::numeric_limits<std::uint32_t>::max()) {
    ++qualified_votes_;
  }
}

void SpectralOnsetMaskLatch::reset() noexcept {
  votes_.fill(0U);
  qualified_votes_ = 0U;
  winner_votes_ = 0U;
  committed_mask_ = 0U;
  settled_ = false;
}

bool SpectralOnsetMaskLatch::committed() const noexcept {
  return committed_mask_ != 0U;
}

std::uint8_t SpectralOnsetMaskLatch::committed_mask() const noexcept {
  return committed_mask_;
}

std::uint32_t SpectralOnsetMaskLatch::qualified_votes() const noexcept {
  return qualified_votes_;
}

std::uint32_t SpectralOnsetMaskLatch::winner_votes() const noexcept {
  return winner_votes_;
}

void SpectralOnsetMaskLatch::settle() noexcept {
  settled_ = true;
  std::uint32_t best = 0U;
  std::uint32_t second = 0U;
  std::uint8_t best_mask = 0U;
  for (std::size_t mask = 0U; mask < votes_.size(); ++mask) {
    const std::uint32_t count = votes_[mask];
    if (count > best) {
      second = best;
      best = count;
      best_mask = static_cast<std::uint8_t>(mask);
    } else if (count > second) {
      second = count;
    }
  }
  winner_votes_ = best;
  if (best == 0U || best == second ||
      static_cast<std::uint64_t>(best) * 5U <
          static_cast<std::uint64_t>(qualified_votes_) * 3U) {
    return;
  }
  committed_mask_ = best_mask;
}

std::uint8_t bounded_spectral_onset_latch_projection(
    std::uint8_t current_assignment_mask, std::uint8_t committed_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony) noexcept {
  const std::uint8_t members = popcount(committed_mask);
  if (current_assignment_mask == 0U || members < 2U || members > 4U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~committed_mask)) != 0U ||
      (committed_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (committed_mask & other_owned_mask) != 0U ||
      popcount(static_cast<std::uint8_t>(committed_mask | other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  return committed_mask;
}

std::uint8_t bounded_spectral_onset_latch_contraction_projection(
    std::uint8_t current_assignment_mask, std::uint8_t committed_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t other_owned_mask,
    std::uint8_t playable_mask, std::uint8_t maximum_polyphony,
    bool direct_fundamental, bool quiet) noexcept {
  const std::uint8_t current_members = popcount(current_assignment_mask);
  const std::uint8_t committed_members = popcount(committed_mask);
  if (quiet || !direct_fundamental || current_members < 3U ||
      current_members > 4U || committed_members != 2U ||
      fine_frequency_mask != current_assignment_mask ||
      (committed_mask & static_cast<std::uint8_t>(~current_assignment_mask)) !=
          0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      (committed_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (committed_mask & other_owned_mask) != 0U ||
      popcount(static_cast<std::uint8_t>(committed_mask | other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  return committed_mask;
}

std::uint8_t bounded_unison_reacquisition_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t committed_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double beat_coherence, bool spectral_group_agreement,
    bool quiet) noexcept {
  const std::uint8_t cached_members = popcount(cached_group_mask);
  const std::uint8_t fine_members = popcount(fine_frequency_mask);
  const std::uint8_t committed_members = popcount(committed_mask);
  const bool restarted_primary_lane =
      committed_members == 1U && current_assignment_mask == committed_mask;
  if (quiet || !direct_fundamental || !spectral_group_agreement ||
      !std::isfinite(beat_coherence) ||
      beat_coherence < 0.20 || current_assignment_mask == 0U ||
      cached_members < 3U || cached_members > 4U || fine_members < 2U ||
      committed_members == 0U || committed_members > 4U ||
      (committed_members == 1U && !restarted_primary_lane) ||
      maximum_polyphony == 0U ||
      maximum_polyphony > kMaxVoices ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) != 0U ||
      (fine_frequency_mask & static_cast<std::uint8_t>(~cached_group_mask)) !=
          0U ||
      (committed_mask & static_cast<std::uint8_t>(~cached_group_mask)) != 0U ||
      (cached_group_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (cached_group_mask & other_owned_mask) != 0U ||
      popcount(static_cast<std::uint8_t>(cached_group_mask |
                                         other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  return cached_group_mask;
}

ArticulatedUnisonReacquisitionResult
bounded_articulated_unison_reacquisition_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t pending_fine_mask, double pending_evidence_seconds,
    double pending_beat_coherence, std::uint8_t spectral_tier_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental, bool quiet,
    double cache_age_seconds, double maximum_gap_seconds,
    double minimum_revalidation_seconds) noexcept {
  using Disposition = ArticulatedUnisonReacquisitionDisposition;
  const auto reject = [current_assignment_mask](Disposition disposition) {
    return ArticulatedUnisonReacquisitionResult{current_assignment_mask,
                                                disposition};
  };
  if (quiet) {
    return reject(Disposition::quiet);
  }
  const std::uint8_t cached_members = popcount(cached_group_mask);
  if (cached_members < 3U || cached_members > 4U) {
    return reject(Disposition::no_cache);
  }
  if (!std::isfinite(cache_age_seconds) ||
      !std::isfinite(maximum_gap_seconds) || maximum_gap_seconds < 0.0 ||
      cache_age_seconds < 0.0 || cache_age_seconds > maximum_gap_seconds) {
    return reject(Disposition::cache_expired);
  }
  const std::uint8_t current_members = popcount(current_assignment_mask);
  if (current_members == 0U || current_members > 4U ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) != 0U) {
    return reject(Disposition::current_mask_invalid);
  }
  if (!direct_fundamental) {
    return reject(Disposition::no_direct_fundamental);
  }
  const std::uint8_t pending_members = popcount(pending_fine_mask);
  if (pending_members < 2U || pending_members > 4U ||
      (pending_fine_mask & static_cast<std::uint8_t>(~cached_group_mask)) !=
          0U) {
    return reject(Disposition::pending_mask_invalid);
  }
  if (!std::isfinite(pending_evidence_seconds) ||
      !std::isfinite(minimum_revalidation_seconds) ||
      minimum_revalidation_seconds < 0.0 ||
      pending_evidence_seconds < minimum_revalidation_seconds) {
    return reject(Disposition::pending_insufficient);
  }
  if (!std::isfinite(pending_beat_coherence) ||
      pending_beat_coherence < 0.20) {
    return reject(Disposition::beat_below_gate);
  }
  if (spectral_tier_mask != cached_group_mask) {
    return reject(Disposition::tier_mismatch);
  }
  if ((cached_group_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U) {
    return reject(Disposition::unplayable);
  }
  if ((cached_group_mask & other_owned_mask) != 0U) {
    return reject(Disposition::ownership_conflict);
  }
  if (maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      popcount(static_cast<std::uint8_t>(cached_group_mask |
                                         other_owned_mask)) >
          maximum_polyphony) {
    return reject(Disposition::over_capacity);
  }
  return {cached_group_mask, Disposition::accepted};
}

ArticulatedUnisonReacquisitionCounterfactual
articulated_reacquisition_counterfactual(
    std::uint8_t observed_mask, std::uint8_t cached_group_mask,
    std::uint8_t label_string_mask, std::uint8_t expected_group_mask,
    bool group_leader) noexcept {
  const bool observed_matches = (observed_mask & label_string_mask) != 0U;
  const bool cached_matches =
      (cached_group_mask & label_string_mask) != 0U;
  const bool observed_exact =
      group_leader && observed_mask == expected_group_mask;
  const bool cached_exact =
      group_leader && cached_group_mask == expected_group_mask;
  const std::int32_t observed_wrong =
      group_leader
          ? static_cast<std::int32_t>(popcount(static_cast<std::uint8_t>(
                observed_mask & static_cast<std::uint8_t>(~expected_group_mask))))
          : 0;
  const std::int32_t cached_wrong =
      group_leader
          ? static_cast<std::int32_t>(popcount(static_cast<std::uint8_t>(
                cached_group_mask &
                static_cast<std::uint8_t>(~expected_group_mask))))
          : 0;
  return {
      static_cast<std::int32_t>(cached_matches) -
          static_cast<std::int32_t>(observed_matches),
      static_cast<std::int32_t>(cached_exact) -
          static_cast<std::int32_t>(observed_exact),
      cached_wrong - observed_wrong,
  };
}

ArticulatedUnisonReacquisitionResult
bounded_three_member_articulated_unison_reacquisition_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t pending_fine_mask, double pending_evidence_seconds,
    double pending_beat_coherence, std::uint8_t spectral_tier_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental, bool quiet,
    double cache_age_seconds, double maximum_gap_seconds,
    double minimum_revalidation_seconds) noexcept {
  if (popcount(cached_group_mask) != 3U) {
    return {current_assignment_mask,
            ArticulatedUnisonReacquisitionDisposition::no_cache};
  }
  return bounded_articulated_unison_reacquisition_projection(
      current_assignment_mask, cached_group_mask, pending_fine_mask,
      pending_evidence_seconds, pending_beat_coherence, spectral_tier_mask,
      other_owned_mask, playable_mask, maximum_polyphony,
      direct_fundamental, quiet, cache_age_seconds, maximum_gap_seconds,
      minimum_revalidation_seconds);
}

ArticulatedUnisonReacquisitionResult
bounded_observed_fingerprint_reacquisition_projection(
    ArticulatedUnisonReacquisitionResult base,
    std::uint8_t fallback_assignment_mask,
    const UnisonSpectralFingerprint& cached_fingerprint,
    bool cached_fingerprint_valid,
    const UnisonSpectralFingerprint& current_fingerprint,
    bool current_fingerprint_valid,
    double maximum_squared_distance) noexcept {
  using Disposition = ArticulatedUnisonReacquisitionDisposition;
  if (base.disposition != Disposition::accepted) {
    return base;
  }
  if (!cached_fingerprint_valid || !current_fingerprint_valid) {
    return {fallback_assignment_mask, Disposition::fingerprint_unavailable};
  }
  const double distance = normalized_spectral_fingerprint_squared_distance(
      cached_fingerprint, current_fingerprint);
  if (!std::isfinite(maximum_squared_distance) ||
      maximum_squared_distance < 0.0 || !std::isfinite(distance) ||
      distance > maximum_squared_distance) {
    return {fallback_assignment_mask, Disposition::fingerprint_mismatch};
  }
  return base;
}

std::uint8_t bounded_unison_reacquisition_cache_mask(
    std::uint8_t cached_group_mask, std::uint8_t current_assignment_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t committed_mask,
    bool quiet) noexcept {
  const std::uint8_t committed_members = popcount(committed_mask);
  if (quiet || committed_members < 2U || committed_members > 4U ||
      current_assignment_mask != committed_mask ||
      fine_frequency_mask != committed_mask) {
    return cached_group_mask;
  }
  if (cached_group_mask == 0U ||
      committed_members >= popcount(cached_group_mask)) {
    return committed_mask;
  }
  return cached_group_mask;
}

std::uint8_t spectral_tier_completion_candidate(
    std::uint8_t fine_frequency_mask, SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    double minimum_margin) noexcept {
  const std::uint8_t fine_members = popcount(fine_frequency_mask);
  if (fine_members < 2U || fine_members >= 4U ||
      !std::isfinite(minimum_margin) ||
      minimum_margin < 0.0 || phase == SpectralShadowPhase::unready) {
    return fine_frequency_mask;
  }
  const double phase_multiplier =
      phase == SpectralShadowPhase::onset ? 2.0 : 1.0;
  std::uint8_t qualified = fine_frequency_mask;
  for (std::size_t head = 0U; head < best_string.size(); ++head) {
    if (best_string[head] >= kMaxVoices || !std::isfinite(margin[head]) ||
        margin[head] < minimum_margin * phase_multiplier) {
      continue;
    }
    qualified = static_cast<std::uint8_t>(
        qualified | (1U << best_string[head]));
  }
  return popcount(qualified) == static_cast<std::uint8_t>(fine_members + 1U)
             ? qualified
             : fine_frequency_mask;
}

std::uint8_t bounded_spectral_tier_completion_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double completion_beat_coherence, double completion_added_member_ratio,
    SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    double minimum_margin, double minimum_added_member_ratio,
    double minimum_beat_coherence, double maximum_beat_coherence) noexcept {
  if (current_assignment_mask == 0U ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~fine_frequency_mask)) != 0U ||
      !std::isfinite(completion_beat_coherence) ||
      !std::isfinite(minimum_beat_coherence) ||
      !std::isfinite(maximum_beat_coherence) ||
      minimum_beat_coherence < 0.0 ||
      maximum_beat_coherence <= minimum_beat_coherence ||
      completion_beat_coherence < minimum_beat_coherence ||
      completion_beat_coherence >= maximum_beat_coherence ||
      !std::isfinite(completion_added_member_ratio) ||
      !std::isfinite(minimum_added_member_ratio) ||
      minimum_added_member_ratio < 0.0 ||
      completion_added_member_ratio < minimum_added_member_ratio) {
    return current_assignment_mask;
  }
  const std::uint8_t completion = spectral_tier_completion_candidate(
      fine_frequency_mask, phase, best_string, margin, minimum_margin);
  return completion != fine_frequency_mask ? completion
                                           : current_assignment_mask;
}

std::uint8_t bounded_fine_unique_member_pruning_projection(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    const std::array<double, kMaxVoices>& unique_member_improvement,
    double minimum_unique_improvement) noexcept {
  const std::uint8_t members = popcount(fine_frequency_mask);
  if (current_assignment_mask != fine_frequency_mask || members < 3U ||
      members > 4U || !std::isfinite(minimum_unique_improvement) ||
      minimum_unique_improvement < 0.0) {
    return current_assignment_mask;
  }
  double weakest = std::numeric_limits<double>::infinity();
  std::uint8_t weakest_bit = 0U;
  bool tied = false;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((fine_frequency_mask & bit) == 0U) {
      continue;
    }
    const double contribution = unique_member_improvement[string];
    if (!std::isfinite(contribution) || contribution < 0.0) {
      return current_assignment_mask;
    }
    if (contribution < weakest) {
      weakest = contribution;
      weakest_bit = bit;
      tied = false;
    } else if (contribution == weakest) {
      tied = true;
    }
  }
  return !tied && weakest_bit != 0U &&
                 weakest < minimum_unique_improvement
             ? static_cast<std::uint8_t>(fine_frequency_mask &
                                         static_cast<std::uint8_t>(
                                             ~weakest_bit))
             : current_assignment_mask;
}

std::uint8_t bounded_fine_mask_complexity_projection(
    const FineMaskComplexityEvidence& evidence,
    const std::array<double, 1U << kMaxVoices>& normalized_residual,
    const std::array<bool, 1U << kMaxVoices>& residual_valid,
    double member_penalty, std::uint8_t maximum_polyphony) noexcept {
  if (!evidence.active || !evidence.selected ||
      !evidence.direct_fundamental || evidence.quiet ||
      evidence.current_assignment_mask == 0U ||
      !std::isfinite(evidence.score_threshold_ratio) ||
      evidence.score_threshold_ratio < 0.50 ||
      !std::isfinite(member_penalty) || member_penalty < 0.0 ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices) {
    return evidence.current_assignment_mask;
  }
  double best_score = std::numeric_limits<double>::infinity();
  std::uint8_t best_mask = 0U;
  bool tied = false;
  for (std::size_t index = 0U; index < residual_valid.size(); ++index) {
    if (!residual_valid[index]) {
      continue;
    }
    const std::uint8_t mask = static_cast<std::uint8_t>(index);
    const std::uint8_t members = popcount(mask);
    if (members < 2U || members > 4U ||
        (mask & static_cast<std::uint8_t>(~evidence.playable_mask)) != 0U ||
        (mask & evidence.other_owned_mask) != 0U ||
        (mask & static_cast<std::uint8_t>(
                    ~evidence.current_assignment_mask)) != 0U ||
        popcount(static_cast<std::uint8_t>(mask |
                                           evidence.other_owned_mask)) >
            maximum_polyphony) {
      continue;
    }
    const double residual = normalized_residual[index];
    if (!std::isfinite(residual) || residual < 0.0) {
      continue;
    }
    const double score =
        residual + member_penalty * static_cast<double>(members - 2U);
    constexpr double kTieEpsilon = 1.0e-12;
    if (score + kTieEpsilon < best_score) {
      best_score = score;
      best_mask = mask;
      tied = false;
    } else if (std::abs(score - best_score) <= kTieEpsilon) {
      tied = true;
    }
  }
  return !tied && best_mask != 0U ? best_mask
                                  : evidence.current_assignment_mask;
}

FineMaskModelRanking rank_fine_masks_by_complexity(
    const std::array<double, 1U << kMaxVoices>& normalized_residual,
    const std::array<bool, 1U << kMaxVoices>& residual_valid,
    std::uint8_t playable_mask, std::uint8_t maximum_member_count,
    std::uint8_t expected_mask, double member_penalty) noexcept {
  return rank_fine_masks_with_string_posterior(
      normalized_residual, residual_valid, {}, playable_mask,
      maximum_member_count, expected_mask, member_penalty, 0.0);
}

FineMaskModelRanking rank_fine_masks_with_string_posterior(
    const std::array<double, 1U << kMaxVoices>& normalized_residual,
    const std::array<bool, 1U << kMaxVoices>& residual_valid,
    const std::array<double, kMaxVoices>& string_probability,
    std::uint8_t playable_mask, std::uint8_t maximum_member_count,
    std::uint8_t expected_mask, double member_penalty,
    double posterior_weight) noexcept {
  FineMaskModelRanking result{};
  if (maximum_member_count < 2U || maximum_member_count > 4U ||
      !std::isfinite(member_penalty) || member_penalty < 0.0 ||
      !std::isfinite(posterior_weight) || posterior_weight < 0.0) {
    return result;
  }

  if (posterior_weight > 0.0) {
    double posterior_total = 0.0;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      const double probability = string_probability[string];
      if (!std::isfinite(probability) || probability < 0.0 ||
          probability > 1.0) {
        return result;
      }
      if ((playable_mask & (1U << string)) != 0U) {
        posterior_total += probability;
      }
    }
    if (!std::isfinite(posterior_total) || posterior_total <= 0.0) {
      return result;
    }
  }

  constexpr double kTieEpsilon = 1.0e-12;
  constexpr double kProbabilityFloor = 1.0e-12;
  std::array<double, 1U << kMaxVoices> scores{};
  scores.fill(std::numeric_limits<double>::infinity());
  double best_score = std::numeric_limits<double>::infinity();
  for (std::size_t physical_mask = 1U;
       physical_mask < residual_valid.size(); ++physical_mask) {
    if (!residual_valid[physical_mask]) {
      continue;
    }
    const auto mask = static_cast<std::uint8_t>(physical_mask);
    const std::uint8_t members = popcount(mask);
    const double residual = normalized_residual[physical_mask];
    if (members < 2U || members > maximum_member_count ||
        (mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
        !std::isfinite(residual) || residual < 0.0) {
      continue;
    }
    double posterior_cost = 0.0;
    if (posterior_weight > 0.0) {
      for (std::size_t string = 0U; string < kMaxVoices; ++string) {
        if ((mask & (1U << string)) != 0U) {
          posterior_cost -= std::log(
              std::max(kProbabilityFloor, string_probability[string]));
        }
      }
      posterior_cost /= static_cast<double>(members);
    }
    const double score =
        residual + member_penalty * static_cast<double>(members - 2U) +
        posterior_weight * posterior_cost;
    scores[physical_mask] = score;
    if (result.feasible_count != std::numeric_limits<std::uint8_t>::max()) {
      ++result.feasible_count;
    }
    if (score + kTieEpsilon < best_score) {
      best_score = score;
      result.best_mask = mask;
      result.tied = false;
    } else if (std::abs(score - best_score) <= kTieEpsilon) {
      result.tied = true;
    }
  }

  if (result.tied) {
    result.best_mask = 0U;
  }
  const double expected_score = scores[expected_mask];
  result.expected_available = std::isfinite(expected_score);
  if (!result.expected_available) {
    return result;
  }
  std::uint16_t rank = 1U;
  for (const double score : scores) {
    if (std::isfinite(score) && score + kTieEpsilon < expected_score) {
      ++rank;
    }
  }
  result.expected_rank = static_cast<std::uint8_t>(
      std::min<std::uint16_t>(rank,
                              std::numeric_limits<std::uint8_t>::max()));
  return result;
}

FineMaskModelRanking rank_fine_masks_with_beat_graph(
    const std::array<double, 1U << kMaxVoices>& normalized_residual,
    const std::array<bool, 1U << kMaxVoices>& residual_valid,
    const std::array<double, 1U << kMaxVoices>& minimum_beat_coherence,
    const std::array<bool, 1U << kMaxVoices>& beat_graph_connected,
    std::uint8_t playable_mask, std::uint8_t maximum_member_count,
    std::uint8_t expected_mask, double member_penalty,
    double minimum_coherence) noexcept {
  FineMaskModelRanking result{};
  if (maximum_member_count < 2U || maximum_member_count > 4U ||
      !std::isfinite(member_penalty) || member_penalty < 0.0 ||
      !std::isfinite(minimum_coherence) || minimum_coherence < 0.0 ||
      minimum_coherence > 1.0) {
    return result;
  }

  constexpr double kTieEpsilon = 1.0e-12;
  std::array<double, 1U << kMaxVoices> scores{};
  scores.fill(std::numeric_limits<double>::infinity());
  double best_score = std::numeric_limits<double>::infinity();
  for (std::size_t physical_mask = 1U;
       physical_mask < residual_valid.size(); ++physical_mask) {
    if (!residual_valid[physical_mask]) {
      continue;
    }
    const auto mask = static_cast<std::uint8_t>(physical_mask);
    const std::uint8_t members = popcount(mask);
    const double residual = normalized_residual[physical_mask];
    const double coherence = minimum_beat_coherence[physical_mask];
    if (members < 2U || members > maximum_member_count ||
        (mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
        !std::isfinite(residual) || residual < 0.0 ||
        !std::isfinite(coherence) || coherence < minimum_coherence ||
        !beat_graph_connected[physical_mask]) {
      continue;
    }
    const double score =
        residual + member_penalty * static_cast<double>(members - 2U);
    scores[physical_mask] = score;
    if (result.feasible_count != std::numeric_limits<std::uint8_t>::max()) {
      ++result.feasible_count;
    }
    if (score + kTieEpsilon < best_score) {
      best_score = score;
      result.best_mask = mask;
      result.tied = false;
    } else if (std::abs(score - best_score) <= kTieEpsilon) {
      result.tied = true;
    }
  }

  if (result.tied) {
    result.best_mask = 0U;
  }
  const double expected_score = scores[expected_mask];
  result.expected_available = std::isfinite(expected_score);
  if (!result.expected_available) {
    return result;
  }
  std::uint16_t rank = 1U;
  for (const double score : scores) {
    if (std::isfinite(score) && score + kTieEpsilon < expected_score) {
      ++rank;
    }
  }
  result.expected_rank = static_cast<std::uint8_t>(
      std::min<std::uint16_t>(rank,
                              std::numeric_limits<std::uint8_t>::max()));
  return result;
}

std::uint8_t bounded_fine_beat_graph_pruning_projection(
    const FineMaskComplexityEvidence& evidence,
    const std::array<double, 1U << kMaxVoices>& normalized_residual,
    const std::array<bool, 1U << kMaxVoices>& residual_valid,
    const std::array<double, 1U << kMaxVoices>& minimum_beat_coherence,
    const std::array<bool, 1U << kMaxVoices>& beat_graph_connected,
    double member_penalty, double minimum_coherence,
    std::uint8_t maximum_polyphony) noexcept {
  const std::uint8_t current = evidence.current_assignment_mask;
  const std::uint8_t current_members = popcount(current);
  if (!evidence.active || !evidence.selected ||
      !evidence.direct_fundamental || evidence.quiet ||
      !std::isfinite(evidence.score_threshold_ratio) ||
      evidence.score_threshold_ratio < 0.50 || current_members < 3U ||
      current_members > 4U ||
      (current & static_cast<std::uint8_t>(~evidence.playable_mask)) != 0U ||
      (current & evidence.other_owned_mask) != 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      popcount(static_cast<std::uint8_t>(current |
                                         evidence.other_owned_mask)) >
          maximum_polyphony ||
      !std::isfinite(member_penalty) || member_penalty < 0.0 ||
      !std::isfinite(minimum_coherence) || minimum_coherence < 0.0 ||
      minimum_coherence > 1.0) {
    return current;
  }

  constexpr double kTieEpsilon = 1.0e-12;
  double best_score = std::numeric_limits<double>::infinity();
  std::uint8_t best_mask = 0U;
  bool tied = false;
  for (std::size_t physical_mask = 1U;
       physical_mask < residual_valid.size(); ++physical_mask) {
    if (!residual_valid[physical_mask]) {
      continue;
    }
    const auto mask = static_cast<std::uint8_t>(physical_mask);
    const std::uint8_t members = popcount(mask);
    const double residual = normalized_residual[physical_mask];
    const double coherence = minimum_beat_coherence[physical_mask];
    if (members < 2U || members >= current_members ||
        (mask & static_cast<std::uint8_t>(~current)) != 0U ||
        (mask & evidence.other_owned_mask) != 0U ||
        popcount(static_cast<std::uint8_t>(mask |
                                           evidence.other_owned_mask)) >
            maximum_polyphony ||
        !std::isfinite(residual) || residual < 0.0 ||
        !std::isfinite(coherence) || coherence < minimum_coherence ||
        !beat_graph_connected[physical_mask]) {
      continue;
    }
    const double score =
        residual + member_penalty * static_cast<double>(members - 2U);
    if (score + kTieEpsilon < best_score) {
      best_score = score;
      best_mask = mask;
      tied = false;
    } else if (std::abs(score - best_score) <= kTieEpsilon) {
      tied = true;
    }
  }
  return !tied && best_mask != 0U ? best_mask : current;
}

std::uint8_t bounded_physical_tier_completion_projection(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double completion_beat_coherence, double completion_added_member_ratio,
    SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool quiet) noexcept {
  if (quiet || maximum_polyphony == 0U || maximum_polyphony > kMaxVoices) {
    return current_assignment_mask;
  }
  const std::uint8_t projected = bounded_spectral_tier_completion_proposal(
      current_assignment_mask, fine_frequency_mask,
      completion_beat_coherence, completion_added_member_ratio, phase,
      best_string, margin, 0.0, 0.08, 0.20, 0.30);
  if (projected == current_assignment_mask ||
      (projected & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (projected & other_owned_mask) != 0U ||
      popcount(static_cast<std::uint8_t>(projected | other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  return projected;
}

std::uint8_t bounded_selected_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const std::array<std::uint8_t, 6U>& evidence_masks,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, std::uint8_t minimum_support,
    bool direct_fundamental, double pairwise_beat_coherence,
    bool robust_pairwise_beat_connected, bool quiet) noexcept {
  if (quiet || !direct_fundamental || current_assignment_mask == 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      minimum_support < 2U || minimum_support > evidence_masks.size() ||
      !std::isfinite(pairwise_beat_coherence)) {
    return current_assignment_mask;
  }

  std::array<std::uint8_t, 1U << kMaxVoices> votes{};
  for (const std::uint8_t mask : evidence_masks) {
    const std::uint8_t members = popcount(mask);
    if (members < 2U || members > 4U ||
        (current_assignment_mask & static_cast<std::uint8_t>(~mask)) != 0U ||
        popcount(static_cast<std::uint8_t>(
            mask & static_cast<std::uint8_t>(~current_assignment_mask))) !=
            1U) {
      continue;
    }
    if (votes[mask] != std::numeric_limits<std::uint8_t>::max()) {
      ++votes[mask];
    }
  }

  std::uint8_t winner = current_assignment_mask;
  std::uint8_t best = 0U;
  bool tied = false;
  for (std::size_t mask = 0U; mask < votes.size(); ++mask) {
    if (votes[mask] > best) {
      best = votes[mask];
      winner = static_cast<std::uint8_t>(mask);
      tied = false;
    } else if (votes[mask] != 0U && votes[mask] == best) {
      tied = true;
    }
  }
  if (tied || best < minimum_support ||
      (winner & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (winner & other_owned_mask) != 0U ||
      popcount(static_cast<std::uint8_t>(winner | other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  const std::uint8_t winner_members = popcount(winner);
  const bool ordinary_beat_supported = pairwise_beat_coherence >= 0.20;
  const bool robust_connected_supported =
      winner_members >= 3U && robust_pairwise_beat_connected &&
      pairwise_beat_coherence >= 0.10;
  if (!ordinary_beat_supported && !robust_connected_supported) {
    return current_assignment_mask;
  }
  return winner;
}

std::uint8_t bounded_classifier_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const UnisonSpectralClassification& classification,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double pairwise_beat_coherence, bool robust_pairwise_beat_connected,
    double maximum_error, double minimum_margin, bool quiet) noexcept {
  return diagnose_classifier_subset_completion_projection(
             current_assignment_mask, classification, other_owned_mask,
             playable_mask, maximum_polyphony, direct_fundamental,
             pairwise_beat_coherence, robust_pairwise_beat_connected,
             maximum_error, minimum_margin, quiet)
      .projected_mask;
}

ClassifierSubsetProjectionResult
diagnose_classifier_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const UnisonSpectralClassification& classification,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double pairwise_beat_coherence, bool robust_pairwise_beat_connected,
    double maximum_error, double minimum_margin, bool quiet) noexcept {
  using Disposition = ClassifierSubsetDisposition;
  const auto reject = [current_assignment_mask](Disposition disposition) {
    return ClassifierSubsetProjectionResult{current_assignment_mask,
                                            disposition};
  };
  if (quiet) {
    return reject(Disposition::quiet);
  }
  if (!direct_fundamental) {
    return reject(Disposition::no_direct_fundamental);
  }
  if (current_assignment_mask == 0U) {
    return reject(Disposition::empty_assignment);
  }
  if (!classification.valid) {
    return reject(Disposition::invalid_classification);
  }
  const std::uint8_t proposed = classification.member_mask;
  const std::uint8_t proposed_members = popcount(proposed);
  if (classification.member_count != proposed_members ||
      proposed_members < 2U || proposed_members > 4U) {
    return reject(Disposition::invalid_member_count);
  }
  const std::uint8_t added = static_cast<std::uint8_t>(
      proposed & static_cast<std::uint8_t>(~current_assignment_mask));
  if (added == 0U || (added & static_cast<std::uint8_t>(added - 1U)) != 0U) {
    return reject(Disposition::not_single_member_completion);
  }
  if ((current_assignment_mask & static_cast<std::uint8_t>(~proposed)) != 0U) {
    return reject(Disposition::not_assignment_superset);
  }
  if (maximum_polyphony == 0U || maximum_polyphony > kMaxVoices) {
    return reject(Disposition::invalid_polyphony);
  }
  if (!std::isfinite(classification.error) || classification.error < 0.0 ||
      !std::isfinite(classification.posterior_margin) ||
      !std::isfinite(maximum_error) || maximum_error < 0.0 ||
      !std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      !std::isfinite(pairwise_beat_coherence)) {
    return reject(Disposition::invalid_metrics);
  }
  if (classification.error > maximum_error) {
    return reject(Disposition::error_above_limit);
  }
  if (classification.posterior_margin < minimum_margin) {
    return reject(Disposition::margin_below_limit);
  }
  if ((proposed & static_cast<std::uint8_t>(~playable_mask)) != 0U) {
    return reject(Disposition::unplayable);
  }
  if ((proposed & other_owned_mask) != 0U) {
    return reject(Disposition::ownership_conflict);
  }
  if (popcount(static_cast<std::uint8_t>(proposed | other_owned_mask)) >
      maximum_polyphony) {
    return reject(Disposition::over_capacity);
  }
  const bool ordinary_beat_supported = pairwise_beat_coherence >= 0.20;
  const bool robust_connected_supported =
      proposed_members >= 3U && robust_pairwise_beat_connected &&
      pairwise_beat_coherence >= 0.10;
  if (!ordinary_beat_supported && !robust_connected_supported) {
    return reject(Disposition::beat_below_gate);
  }
  return {proposed, Disposition::accepted};
}

std::uint8_t bounded_projection_union(
    std::uint8_t current_assignment_mask, std::uint8_t first_projection,
    std::uint8_t second_projection) noexcept {
  if (first_projection == second_projection) {
    return first_projection;
  }
  if (first_projection == current_assignment_mask) {
    return second_projection;
  }
  if (second_projection == current_assignment_mask) {
    return first_projection;
  }
  return current_assignment_mask;
}

std::uint8_t bounded_three_four_member_projection_union(
    std::uint8_t current_assignment_mask, std::uint8_t established_group_mask,
    std::uint8_t first_projection, std::uint8_t second_projection) noexcept {
  const std::uint8_t members = popcount(established_group_mask);
  if (members < 3U || members > 4U) {
    return current_assignment_mask;
  }
  return bounded_projection_union(current_assignment_mask, first_projection,
                                  second_projection);
}

std::uint8_t bounded_cached_classifier_continuity_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    const UnisonSpectralClassification& classification,
    SpectralShadowPhase phase, std::uint8_t other_owned_mask,
    std::uint8_t playable_mask, std::uint8_t maximum_polyphony,
    bool active_candidate, bool selected_or_coasting,
    bool direct_fundamental, bool quiet, double cache_age_seconds,
    double maximum_cache_age_seconds, double minimum_margin) noexcept {
  const std::uint8_t cached_members = popcount(cached_group_mask);
  const std::uint8_t current_members = popcount(current_assignment_mask);
  if (phase == SpectralShadowPhase::unready || quiet || !active_candidate ||
      !selected_or_coasting || !direct_fundamental || current_members == 0U ||
      current_members >= cached_members || cached_members < 3U ||
      cached_members > 4U ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) != 0U ||
      (cached_group_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (cached_group_mask & other_owned_mask) != 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      popcount(static_cast<std::uint8_t>(cached_group_mask |
                                         other_owned_mask)) >
          maximum_polyphony ||
      !classification.valid ||
      classification.member_mask != cached_group_mask ||
      classification.member_count != cached_members ||
      !std::isfinite(classification.posterior_margin) ||
      !std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      classification.posterior_margin < minimum_margin ||
      !std::isfinite(cache_age_seconds) ||
      !std::isfinite(maximum_cache_age_seconds) || cache_age_seconds < 0.0 ||
      maximum_cache_age_seconds < 0.0 ||
      cache_age_seconds > maximum_cache_age_seconds) {
    return current_assignment_mask;
  }
  return cached_group_mask;
}

bool parse_unison_spectral_shadow_templates(
    const char* text, std::size_t size,
    UnisonSpectralShadowTemplateBank& output) noexcept {
  output = {};
  if (text == nullptr && size != 0U) {
    return false;
  }
  const std::string_view input{text == nullptr ? "" : text, size};
  constexpr std::string_view kHeader =
      "phase\tmidi_note\tstring_index\tfingerprint";
  std::size_t position = 0U;
  std::size_t row_count = 0U;
  bool header_seen = false;
  while (position < input.size()) {
    const std::size_t newline = input.find('\n', position);
    const std::size_t end =
        newline == std::string_view::npos ? input.size() : newline;
    std::string_view line = input.substr(position, end - position);
    if (!line.empty() && line.back() == '\r') {
      line.remove_suffix(1U);
    }
    position = newline == std::string_view::npos ? input.size() : newline + 1U;
    if (line.empty()) {
      continue;
    }
    if (!header_seen) {
      if (line != kHeader) {
        return false;
      }
      header_seen = true;
      continue;
    }
    std::array<std::string_view, 4U> fields{};
    std::size_t field_start = 0U;
    for (std::size_t field = 0U; field < fields.size(); ++field) {
      const std::size_t tab = line.find('\t', field_start);
      const bool last = field + 1U == fields.size();
      if ((!last && tab == std::string_view::npos) ||
          (last && tab != std::string_view::npos)) {
        return false;
      }
      const std::size_t field_end = last ? line.size() : tab;
      fields[field] = line.substr(field_start, field_end - field_start);
      field_start = last ? line.size() : tab + 1U;
    }
    std::size_t phase = 0U;
    if (fields[0] == "corridor") {
      phase = 0U;
    } else if (fields[0] == "onset") {
      phase = 1U;
    } else if (fields[0] == "settled") {
      phase = 2U;
    } else {
      return false;
    }
    std::uint64_t note = 0U;
    std::uint64_t string = 0U;
    const auto parse_integer = [](std::string_view field,
                                  std::uint64_t& value) noexcept {
      if (field.empty()) {
        return false;
      }
      const char* begin = field.data();
      const char* field_end = begin + field.size();
      const auto [parsed, error] =
          std::from_chars(begin, field_end, value, 10);
      return error == std::errc{} && parsed == field_end;
    };
    if (!parse_integer(fields[1], note) || note > 127U ||
        !parse_integer(fields[2], string) || string >= kMaxVoices) {
      return false;
    }
    UnisonSpectralTemplateSet& set = output.by_phase[phase][note];
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((set.valid_mask & bit) != 0U) {
      return false;
    }
    UnisonSpectralFingerprint fingerprint{};
    std::size_t feature_start = 0U;
    double norm_square = 0.0;
    for (std::size_t feature = 0U; feature < fingerprint.size(); ++feature) {
      const std::size_t comma = fields[3].find(',', feature_start);
      const bool last = feature + 1U == fingerprint.size();
      if ((!last && comma == std::string_view::npos) ||
          (last && comma != std::string_view::npos)) {
        return false;
      }
      const std::size_t feature_end = last ? fields[3].size() : comma;
      const std::string_view value =
          fields[3].substr(feature_start, feature_end - feature_start);
      if (value.empty()) {
        return false;
      }
      const char* begin = value.data();
      const char* value_end = begin + value.size();
      const auto [parsed, error] =
          std::from_chars(begin, value_end, fingerprint[feature]);
      if (error != std::errc{} || parsed != value_end ||
          !std::isfinite(fingerprint[feature]) || fingerprint[feature] < 0.0) {
        return false;
      }
      norm_square += fingerprint[feature] * fingerprint[feature];
      feature_start = last ? fields[3].size() : comma + 1U;
    }
    const double norm = std::sqrt(norm_square);
    if (!std::isfinite(norm) || norm <= 0.0) {
      return false;
    }
    for (double& feature : fingerprint) {
      feature /= norm;
    }
    set.fingerprint[string] = fingerprint;
    set.valid_mask = static_cast<std::uint8_t>(set.valid_mask | bit);
    if (++row_count > kSpectralShadowTemplatePhaseCount * 128U * kMaxVoices) {
      return false;
    }
  }
  return header_seen && row_count != 0U;
}

}  // namespace m3::offline
