#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/harmonic_evidence.hpp"
#include "m3/unison_spectral_classifier.hpp"
#include "m3/unison_spectral_tracker.hpp"

namespace m3::offline {

using SpectralShadowPhase = UnisonSpectralPhase;

inline constexpr std::size_t kSpectralShadowTemplatePhaseCount = 3U;
inline constexpr std::array<double, 7U> kSpectralShadowMarginThresholds{
    0.0, 0.00025, 0.0005, 0.001, 0.002, 0.005, 0.01};
inline constexpr std::size_t kCandidateSpectralIntervalRadius = 48U;
inline constexpr std::size_t kCandidateSpectralIntervalBucketCount =
    kCandidateSpectralIntervalRadius * 2U + 1U;

// Candidate-level evidence used only by offline admission experiments. The
// detector already computes these quantities for every playable pitch; the
// shadow combines them with an independently fitted string/fret corridor so
// a weak fundamental can be distinguished from a strong harmonic before any
// production selector behavior is changed.
struct CandidateSpectralAdmissionEvidence final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
  bool direct_fundamental_peak{};
  bool local_peak{};
  bool candidate_evidence{};
};

struct CandidateSpectralAdmissionLimits final {
  double minimum_score_ratio{};
  double minimum_fundamental_ratio{};
  double maximum_error{};
  double minimum_margin{};
};

struct CombinedCandidateAdmissionEvidence final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
  double pitch_band_score_peak_ratio{};
  double pitch_band_fundamental_peak_ratio{};
  double best_calibration_similarity{};
  double calibration_margin{};
  std::uint8_t best_calibrated_string{0xffU};
  bool direct_fundamental_peak{};
  bool local_or_candidate_peak{};
};

struct CombinedCandidateAdmissionLimits final {
  double minimum_score_ratio{};
  std::uint8_t minimum_string{};
  double maximum_spectral_error{};
  double minimum_spectral_margin{};
};

// Returns the one free physical-string bit supported by all evidence, or zero
// when the candidate is ambiguous, infeasible, or would exceed voice capacity.
// This function is a counterfactual gate only; it emits no MIDI and cannot
// create or retain detector state.
[[nodiscard]] std::uint8_t bounded_candidate_spectral_admission(
    const CandidateSpectralAdmissionEvidence& evidence,
    const UnisonSpectralClassification& classification,
    std::uint8_t playable_mask, std::uint8_t occupied_mask,
    std::uint8_t current_voice_count, std::uint8_t maximum_polyphony,
    const CandidateSpectralAdmissionLimits& limits) noexcept;

// Requires a direct local fundamental, decisive measured string/fret
// calibration, and the independent 102-feature classifier to name the same
// one free physical string. This counterfactual emits no MIDI.
[[nodiscard]] std::uint8_t bounded_combined_candidate_admission(
    const CombinedCandidateAdmissionEvidence& evidence,
    const UnisonSpectralClassification& classification,
    std::uint8_t playable_mask, std::uint8_t occupied_mask,
    std::uint8_t current_voice_count, std::uint8_t maximum_polyphony,
    const CombinedCandidateAdmissionLimits& limits) noexcept;

// Maps a candidate to its signed semitone distance from the nearest active
// labeled pitch. Values outside +/-48 are clamped; BucketCount is returned
// when no reference pitch is active. This is offline audit data only.
[[nodiscard]] std::size_t candidate_spectral_interval_bucket(
    std::uint8_t candidate_note,
    const std::array<std::uint32_t, 128U>& active_references) noexcept;

// Closed offline template bank. Phase zero is the all-frame corridor,
// phase one onset, and phase two settled evidence.
struct UnisonSpectralShadowTemplateBank final {
  std::array<std::array<UnisonSpectralTemplateSet, 128U>,
             kSpectralShadowTemplatePhaseCount>
      by_phase{};
};

// Parses phase<TAB>midi_note<TAB>string_index<TAB>102 comma-separated
// nonnegative features. Rows are unique by phase/note/string.
bool parse_unison_spectral_shadow_templates(
    const char* text, std::size_t size,
    UnisonSpectralShadowTemplateBank& output) noexcept;

// Models the narrowest production-eligible use of the classifier without
// changing MIDI. It can only refine an already-active multi-string pitch,
// requires either exact fine-frequency agreement or a beat-coherent fine-mask
// subset corroborated by the profile/temporal proposal, and is stricter during
// onset. A rejection returns the current assignment unchanged.
[[nodiscard]] std::uint8_t bounded_spectral_shadow_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double minimum_beat_coherence, std::uint8_t profile_mask,
    std::uint8_t temporal_mask, SpectralShadowPhase phase,
    const UnisonSpectralClassification& classification,
    double minimum_margin) noexcept;

// Offline counterfactual: an expansion must agree with temporal evidence.
// Exact fine agreement alone is intentionally insufficient; this separates
// new temporal corroboration from merely repeating the fitter's own mask.
[[nodiscard]] std::uint8_t bounded_temporal_spectral_shadow_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double minimum_beat_coherence, std::uint8_t temporal_mask,
    SpectralShadowPhase phase,
    const UnisonSpectralClassification& classification,
    double minimum_margin) noexcept;

// Offline-only causal memory for a same-note onset. Qualified 2-4 member
// classifications vote while the corridor is in its onset phase. The first
// settled observation closes voting and commits only a unique winner with at
// least three fifths of all qualified votes. A committed mask is immutable
// until reset, so later harmonic drift cannot rewrite the onset evidence.
class SpectralOnsetMaskLatch final {
 public:
  void observe(SpectralShadowPhase phase,
               const UnisonSpectralClassification& classification,
               double minimum_margin) noexcept;
  void reset() noexcept;

  [[nodiscard]] bool committed() const noexcept;
  [[nodiscard]] std::uint8_t committed_mask() const noexcept;
  [[nodiscard]] std::uint32_t qualified_votes() const noexcept;
  [[nodiscard]] std::uint32_t winner_votes() const noexcept;

 private:
  void settle() noexcept;

  std::array<std::uint32_t, 1U << kMaxVoices> votes_{};
  std::uint32_t qualified_votes_{};
  std::uint32_t winner_votes_{};
  std::uint8_t committed_mask_{};
  bool settled_{};
};

// Counterfactual projection guard for a committed onset mask. The latch may
// only refine an already-active pitch, must remain fret/playability feasible,
// cannot steal a physical string owned by another pitch, and cannot exceed
// the configured total voice capacity.
[[nodiscard]] std::uint8_t bounded_spectral_onset_latch_projection(
    std::uint8_t current_assignment_mask, std::uint8_t committed_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony) noexcept;

// Shadow-only articulation reacquisition. A previously resolved physical
// group may complete a live multi-member subset, but cannot start a pitch,
// survive quiet, steal a string, or exceed physical/polyphony limits.
[[nodiscard]] std::uint8_t bounded_unison_reacquisition_cache_mask(
    std::uint8_t cached_group_mask, std::uint8_t current_assignment_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t committed_mask,
    bool quiet) noexcept;

[[nodiscard]] std::uint8_t bounded_unison_reacquisition_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t committed_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double beat_coherence, bool spectral_group_agreement,
    bool quiet) noexcept;

enum class ArticulatedUnisonReacquisitionDisposition : std::uint8_t {
  accepted,
  quiet,
  no_cache,
  cache_expired,
  current_mask_invalid,
  no_direct_fundamental,
  pending_mask_invalid,
  pending_insufficient,
  beat_below_gate,
  tier_mismatch,
  unplayable,
  ownership_conflict,
  over_capacity,
  count,
};

struct ArticulatedUnisonReacquisitionResult final {
  std::uint8_t projected_mask{};
  ArticulatedUnisonReacquisitionDisposition disposition{
      ArticulatedUnisonReacquisitionDisposition::no_cache};
};

// Counterfactual for a returning articulation of a previously resolved
// three- or four-string unison.  Fresh pending fine/beat/tier evidence must
// revalidate the cached physical group; this cannot create a pitch, survive
// quiet, add an unseen member, steal a string, or exceed voice capacity.
[[nodiscard]] ArticulatedUnisonReacquisitionResult
bounded_articulated_unison_reacquisition_projection(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t pending_fine_mask, double pending_evidence_seconds,
    double pending_beat_coherence, std::uint8_t spectral_tier_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental, bool quiet,
    double cache_age_seconds, double maximum_gap_seconds,
    double minimum_revalidation_seconds) noexcept;

// Tests whether the already-resolved fine-frequency group is missing exactly
// one physical member that the independent spectral tier heads support. This
// is an offline counterfactual only: it cannot start a group, replace a fine
// member, add more than one lane, or bypass the pairwise-beat gate.
[[nodiscard]] std::uint8_t spectral_tier_completion_candidate(
    std::uint8_t fine_frequency_mask, SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    double minimum_margin) noexcept;

[[nodiscard]] std::uint8_t bounded_spectral_tier_completion_proposal(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double completion_beat_coherence, double completion_added_member_ratio,
    SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    double minimum_margin,
    double minimum_added_member_ratio = 0.10,
    double minimum_beat_coherence = 0.20,
    double maximum_beat_coherence = 0.35) noexcept;

// Production-shaped replay projection for the measured spectral-tier repair.
// In addition to the tier/beat gate above, the pitch must already own a live
// assignment and the one-lane completion must fit the current physical
// ownership, fret, and total-polyphony constraints. This cannot create a
// pitch; it can only refine an existing non-quiet fine group.
[[nodiscard]] std::uint8_t bounded_physical_tier_completion_projection(
    std::uint8_t current_assignment_mask, std::uint8_t fine_frequency_mask,
    double completion_beat_coherence, double completion_added_member_ratio,
    SpectralShadowPhase phase,
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& best_string,
    const std::array<double, kSpectralTierCount + 1U>& margin,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool quiet) noexcept;

// Replay-only consensus experiment for the remaining selected-but-incomplete
// physical-unison frames. Every nonzero evidence mask casts one vote. A
// projection is possible only when one unique mask wins by the requested
// support floor, adds exactly one physical member to the live assignment, and
// passes the same playability, ownership, polyphony, direct-fundamental, and
// pairwise-beat boundaries used by the production detector. This helper does
// not create a pitch or mutate detector state.
[[nodiscard]] std::uint8_t bounded_selected_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const std::array<std::uint8_t, 6U>& evidence_masks,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, std::uint8_t minimum_support,
    bool direct_fundamental, double pairwise_beat_coherence,
    bool robust_pairwise_beat_connected, bool quiet) noexcept;

// Narrow classifier-only variant for replay measurement. It can complete one
// physical lane of an already-selected subset but cannot create a pitch,
// replace a lane, or bypass the detector's physical and beat boundaries.
[[nodiscard]] std::uint8_t bounded_classifier_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const UnisonSpectralClassification& classification,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double pairwise_beat_coherence, bool robust_pairwise_beat_connected,
    double maximum_error, double minimum_margin, bool quiet) noexcept;

enum class ClassifierSubsetDisposition : std::uint8_t {
  accepted,
  quiet,
  no_direct_fundamental,
  empty_assignment,
  invalid_classification,
  invalid_member_count,
  not_single_member_completion,
  not_assignment_superset,
  invalid_polyphony,
  invalid_metrics,
  error_above_limit,
  margin_below_limit,
  unplayable,
  ownership_conflict,
  over_capacity,
  beat_below_gate,
  count,
};

struct ClassifierSubsetProjectionResult final {
  std::uint8_t projected_mask{};
  ClassifierSubsetDisposition disposition{
      ClassifierSubsetDisposition::invalid_classification};
};

// Diagnostic form of the bounded classifier completion. It returns the first
// causal rejection without changing the production projection policy.
[[nodiscard]] ClassifierSubsetProjectionResult
diagnose_classifier_subset_completion_projection(
    std::uint8_t current_assignment_mask,
    const UnisonSpectralClassification& classification,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double pairwise_beat_coherence, bool robust_pairwise_beat_connected,
    double maximum_error, double minimum_margin, bool quiet) noexcept;

// Combines two independently bounded counterfactuals without resolving a
// disagreement optimistically. Agreement wins, one changed proposal wins when
// the other remains unchanged, and conflicting changes preserve the live mask.
[[nodiscard]] std::uint8_t bounded_projection_union(
    std::uint8_t current_assignment_mask, std::uint8_t first_projection,
    std::uint8_t second_projection) noexcept;

using UnisonSpectralCorridorTracker = m3::UnisonSpectralCorridorTracker;

}  // namespace m3::offline
