#pragma once

#include <array>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "m3/constants.hpp"
#include "m3/harmonic_evidence.hpp"
#include "m3/hann_beat_shadow.hpp"
#include "m3/frequency_refinement_observer.hpp"
#include "m3/partial_detuning_evidence.hpp"
#include "m3/string_fret_posterior.hpp"
#include "m3/string_calibration.hpp"
#include "m3/tuner_telemetry.hpp"
#include "m3/types.hpp"
#include "m3/unison_spectral_classifier.hpp"
#include "m3/unison_spectral_tracker.hpp"
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS) || defined(M3_JOINT_RESIDUAL_SHADOW)
#include <memory>
#include <new>
#endif
#if defined(M3_JOINT_RESIDUAL_SHADOW)
#include "m3/joint_pitch_residual.hpp"
#endif

namespace m3 {

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
enum class SelectionDisposition : std::uint8_t {
  quiet,
  below_threshold,
  spectral_rejected,
  dp_evicted,
  selected,
  coasting,
  count,
};

// Identifies the first causal gate that suppresses a detector decision. This
// exists only in replay/test builds so production VST3 state and timing remain
// unchanged.
enum class QuietDisposition : std::uint8_t {
  not_quiet,
  minimum_evidence_startup,
  minimum_evidence_after_signal_floor,
  minimum_evidence_after_inactive_energy_ratio,
  below_signal_floor,
  rapid_mute_ratio,
  inactive_energy_ratio,
  multi_voice_evidence,
  count,
};

enum class SignalLossDisposition : std::uint8_t {
  none,
  signal_floor,
  inactive_energy_ratio,
};

enum class FineFrequencyDisposition : std::uint8_t {
  unresolved,
  amplitude_single,
  source_evidence_rejected,
  residual_rejected,
  multi_source_candidate,
  count,
};

enum class FineFrequencyUnresolvedReason : std::uint8_t {
  none,
  no_history,
  collecting,
  analysis_wait,
  no_calibration_components,
  fit_failure,
  zero_solution,
  count,
};

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
struct FineFrequencyMaskResidualTable final {
  std::array<double, 1U << kMaxVoices> normalized_residual{};
  std::array<double, 1U << kMaxVoices> minimum_beat_coherence{};
  std::array<bool, 1U << kMaxVoices> valid{};
  std::array<bool, 1U << kMaxVoices> beat_graph_connected{};
};

// Caller-owned replay storage avoids growing every detector's stack state.
struct HannBeatShadowTable final {
  std::array<double, 28U> hann_detrended_pair_coherence{};
  std::array<double, 28U> pair_difference_hz{};
  double beat_window_seconds{};
  bool hann_detrending_valid{};
};
using HannBeatShadowBuffer = std::array<HannBeatShadowTable, kMaxCandidates>;
#endif

// Explains why an already-committed physical unison did or did not receive
// the selector's reserved slot. This is replay-only evidence; production
// builds neither expose nor store it.
enum class RetainedUnisonDisposition : std::uint8_t {
  not_applicable,
  fine_unavailable,
  fine_mask_mismatch,
  beat_below_gate,
  unplayable,
  below_decay_floor,
  superseded,
  retained,
  count,
};

// Classifies the exact point at which a fine-frequency physical-string group
// is admitted to or rejected from unison inference. Replay diagnostics use
// this to distinguish evidence failure from sequential ownership/capacity
// loss without changing production decisions.
enum class FineGroupDisposition : std::uint8_t {
  unresolved,
  missing_primary,
  invalid_size,
  conflicts_other_owned,
  conflicts_allocated,
  over_capacity,
  accepted,
  count,
};

// Ownership at entry to unison inference, before any candidate changes its
// group. One record per pitch preserves multiple owners of the same lane.
// Group fields record the actual gate inputs; owner fields are never rebuilt
// from the final tuner snapshot.
struct FineGroupOwnershipDiagnostics final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
  std::uint16_t age_ticks{};
  std::uint8_t primary{kUnassignedTunerString};
  std::uint8_t assigned_mask{};
  std::uint8_t midi_mask{};
  std::uint8_t owned_mask{};
  std::uint8_t fine_mask{};
  std::uint8_t group_mask{};
  std::uint8_t other_owned_mask{};
  std::uint8_t overlap_mask{};
  std::uint8_t allocated_mask{};
  std::uint8_t extra_capacity{};
  bool observed{};
  bool selected{};
  bool active{};
  bool direct_fundamental{};
  bool fine_valid{};
  bool group_evaluated{};
};

enum class TierCompletionDisposition : std::uint8_t {
  unavailable,
  missing_primary,
  conflicts_other_owned,
  conflicts_allocated,
  over_capacity,
  accepted,
  count,
};

// Explains why the replay-only physical-group cache did or did not refresh
// on the current decision. This state is absent from production builds.
enum class UnisonCacheRefreshDisposition : std::uint8_t {
  quiet,
  inactive,
  below_decay_floor,
  fine_invalid,
  invalid_member_count,
  assignment_fine_mismatch,
  refreshed,
  count,
};

// Snapshot of the selector's pre-admission evidence for one pitch. This is
// deliberately replay-only: it lets offline audits distinguish a weak but
// direct fundamental from a harmonic or an unplayable candidate without
// adding state or branches to production plugin builds.
struct CandidateAdmissionDiagnostics final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
  // Existing causal string/fret-posterior onset evidence. Replay exposes it
  // to test articulation boundaries; production builds omit this structure.
  double string_fret_onset_strength{};
  // Scale-invariant evidence relative to the strongest playable candidate in
  // the same one-octave pitch band. This is replay-only: it measures whether
  // a quiet upper-string fundamental is locally strong even when a louder low
  // string dominates the broadband input threshold.
  double pitch_band_score_peak_ratio{};
  double pitch_band_fundamental_peak_ratio{};
  double best_calibration_similarity{};
  double second_calibration_similarity{};
  std::uint8_t pitch_band{};
  std::uint8_t playable_string_mask{};
  std::uint8_t calibrated_string_mask{};
  std::uint8_t best_calibrated_string{kUnassignedTunerString};
  // Populated only when the candidate clears raw admission but the harmonic
  // shadow pass rejects it.  The signed interval is stronger-candidate minus
  // candidate in semitones; 127 means no rejecting candidate was recorded.
  std::int8_t spectral_shadow_interval{127};
  double spectral_shadow_fundamental_ratio{};
  std::uint8_t spectral_shadow_kind{};
  std::uint8_t spectral_shadow_other_eligible_count{};
  std::uint8_t spectral_shadow_other_active_count{};
  // Signed pitch distance from this rejected candidate to the strongest
  // otherwise eligible candidate, or 127 when no such candidate exists.
  // Replay uses this to distinguish a consistent same-source subharmonic
  // blocker from a genuine competing chord voice.
  std::int8_t spectral_shadow_strongest_other_interval{127};
  // Bit 0: direct fundamental, bit 1: local peak, bit 2: candidate evidence,
  // bit 3: already active, bit 4: decisive calibrated shape. Zero also
  // represents the no-other case.
  std::uint8_t spectral_shadow_strongest_other_evidence{};
  bool active{};
  bool direct_fundamental_peak{};
  bool local_peak{};
  bool candidate_evidence{};
  bool calibrated_direct_support{};
  // Selector-local evidence, captured before fallback and additive rescue.
  // A positive feasible lane may still lose to a more valuable assignment.
  bool selector_pool_member{};
  double selector_raw_score{};
  double selector_best_adjusted_score{};
  std::uint8_t selector_option_mask{};
  std::uint8_t selector_positive_mask{};
  std::uint8_t selector_used_mask{};
  std::uint8_t selector_voice_count{};
  std::uint8_t selector_open_count{};
};

enum class FineHistoryResetReason : std::uint8_t {
  none = 0U,
  unselected_gap,
  invalid_fundamental,
  selected_gap,
  signal_floor_loss,
  inactive_energy_loss,
};

struct FineHistoryResetDiagnostics final {
  std::uint32_t serial{};
  std::uint32_t decision_tick{};
  std::uint32_t prior_last_tick{};
  std::uint16_t prior_count{};
  FineHistoryResetReason reason{FineHistoryResetReason::none};
};

enum class CalibratedOutputReason : std::uint8_t {
  not_observed,
  ineligible,
  nonfinite_cents,
  untrusted_original,
  untrusted_start,
  untrusted_wait,
  untrusted_revert,
  collision_reset,
  projection_start,
  projection_wait,
  projection_apply,
  diagnostic_collision_reset,
  count,
};

// The executed branch and state at the calibrated-output stage, before later
// DP projection and voice/lane lifecycle work. Capture never changes a decision.
struct CalibratedOutputDiagnostics final {
  std::uint32_t decision_tick{};
  double phase_cents{};
  double projected_error_cents{std::numeric_limits<double>::quiet_NaN()};
  std::uint16_t age_ticks{};
  std::uint16_t minimum_age_ticks{};
  std::uint16_t transitions_added{};
  std::uint8_t selected_count{};
  std::uint8_t member_mask{};
  // Bits: unselected, inactive, fewer than two notes, young, nonsingle member,
  // invalid phase projection (1, 2, 4, 8, 16, 32 respectively).
  std::uint8_t eligibility_failures{};
  std::uint8_t output_before{kTunerNoSignalNote};
  std::uint8_t output_after{kTunerNoSignalNote};
  std::uint8_t midi_before{kTunerNoSignalNote};
  std::uint8_t midi_after{kTunerNoSignalNote};
  std::uint8_t target_before{kTunerNoSignalNote};
  std::uint8_t target_after{kTunerNoSignalNote};
  std::uint8_t ticks_before{};
  std::uint8_t ticks_after{};
  std::uint8_t projected_note{kTunerNoSignalNote};
  std::uint8_t collision_note{kTunerNoSignalNote};
  // First colliding candidate: selected logical pitch (1), active output (2).
  std::uint8_t collision_kind{};
  bool observed{};
  bool projection_changed{};
  bool projection_trusted{};
  CalibratedOutputReason reason{CalibratedOutputReason::not_observed};
};

// Read-only timeline snapshot for bounded offline causal comparisons.
struct CandidateTrackingDiagnostics final {
  std::uint32_t decision_tick{};
  std::uint32_t signal_samples{};
  double phase_cents{};
  std::uint16_t phase_updates{};
  std::uint16_t age_ticks{};
  std::uint16_t release_ticks{};
  std::uint8_t attack_ticks{};
  std::uint8_t evidence_ticks{};
  std::uint8_t evidence_gap_ticks{};
  std::uint32_t fine_last_tick{};
  std::uint32_t fine_oldest_tick{};
  std::uint16_t fine_count{};
  std::uint16_t fine_pending_count{};
  std::uint8_t assigned_mask{};
  std::uint8_t rescue_mask{};
  bool active{};
  bool phase_valid{};
  bool fine_valid{};
  bool multi_source{};
  bool fine_update_scheduled{};
  FineHistoryResetDiagnostics fine_reset{};
  CalibratedOutputDiagnostics calibrated_output{};
};

// Fixed two-template fit of one independently normalized observation window.
// Missing/quiet energy is invalid, rather than evidence for a single string.
struct ProfilePairWindowDiagnostics final {
  bool valid{};
  double energy{};
  double primary_error{};
  double best_single_error{};
  double pair_error{};
  double secondary_weight{};
  std::array<double, kCalibrationHarmonicCount> observed{};
};

// First greedy addition to the primary template only. Later additions and the
// joint complement search cannot overwrite this observation. Values are part
// of the offline assignment TSV format, not detector policy.
enum class ProfileAdditionReason : std::uint8_t {
  not_observed = 0U,
  already_member = 1U,
  template_unavailable = 2U,
  owned_by_other = 3U,
  extra_allocated = 4U,
  independently_unresolved = 5U,
  template_too_close = 6U,
  added_component_too_small = 7U,
  retained_component_too_small = 8U,
  insufficient_improvement = 9U,
  error_ratio = 10U,
  not_best = 11U,
  accepted = 12U,
};

struct ProfileAdditionDiagnostics final {
  ProfileAdditionReason reason{};
  // -1 means the rejecting branch was reached before this value was computed.
  double alpha{-1.0};
  double candidate_error{-1.0};
};

// One assignment decision, with costs before any later output projection.
// This is observational state and is absent from production builds.
struct StringAssignmentDiagnostics final {
  std::array<std::array<double, 7U>, kMaxVoices> lane_terms{};
  std::array<double, kMaxVoices> lane_totals{};
  double joint_cost{};
  std::uint32_t joint_strings{};
  std::uint8_t selected_count{};
  std::uint8_t ordinal{};
  std::uint8_t playable{};
  std::uint8_t reserved_coasting{};
  std::uint8_t reserved_extras{};
  std::uint8_t prior_primary{255U};
  std::uint8_t prior_mask{};
  std::uint8_t dp_primary{255U};
  std::uint8_t spectral_proposal{};
  std::uint8_t final_primary{255U};
  std::uint8_t final_mask{};
  std::uint8_t final_spectral{};
  std::uint8_t final_continuity{};
  bool observed{};
  // Costs for an inactive selector miss, holding the selected context fixed.
  // This does not simulate admitting the note or assigning it a string.
  bool fixed_context{};
  bool phase_shadow{};
  bool valid{};
  bool isolated{};
  bool reassignment_ready{};
  bool prior_committed{};
  bool use_posterior{};
  bool calibrated_replacement{};
  double phase_cents{};
  double phase_raw_cents{};
  double phase_previous_cents{};
  double assignment_cents{};
  std::array<double, kMaxVoices> learned_cents{};
  std::uint16_t phase_updates{};
  std::uint8_t group_before{};
  std::uint8_t group_proposal{};
  // 0 primary, 1 fine, 2 tier, 3 profile, 4 profile complement.
  std::uint8_t group_origin{};
  // 0 unchanged, 1 evidence commit, 2 joint commit, 3 dropout hold,
  // 4 primary reset, 5 capacity reset, 6 pending evidence.
  std::uint8_t group_transition{};
  std::uint8_t group_after{};
  std::uint8_t fine_mask{};
  std::uint8_t fine_pending_mask{};
  std::uint8_t continuity_at_render{};
  std::uint8_t primary_only_render{};
  std::uint8_t primary_only_snapshot{};
  bool phase_accepted{};
  bool phase_valid{};
  bool complete_calibration{};
  bool beat_valid{};
  bool fine_valid{};
  bool render_observed{};
  bool profile_fit_observed{};
  bool profile_uses_long_memory{};
  double profile_primary_error{};
  double profile_best_single_error{};
  double profile_mixture_error{};
  std::array<double, kMaxVoices> profile_weights{};
  std::array<double, kCalibrationHarmonicCount> profile_observed{};
  // -1 means that a string has no playable calibrated template.
  std::array<double, kMaxVoices> profile_single_errors{};
  std::array<ProfileAdditionDiagnostics, kMaxVoices> profile_first_pass{};
  std::uint8_t profile_pair_primary{0xffU};
  std::uint8_t profile_pair_mask{};
  // Current correlation energy, 350ms memory, then 1.5s memory. These fits
  // measure recency disagreement without changing the chosen/blended fit.
  std::array<ProfilePairWindowDiagnostics, 3U> profile_pair_windows{};
  std::uint16_t candidate_age_ticks{};
  std::uint8_t midi_mask{};
  // Current update likelihood (already causally filtered), cached state before
  // the update, and state immediately afterward. The cached prior is not the
  // transition-predicted prior. Fixed-context rows never update this bank.
  bool posterior_observation_available{};
  bool posterior_updated{};
  double posterior_onset_strength{};
  std::array<double, kMaxVoices> posterior_log_likelihood{};
  std::array<double, kMaxVoices> posterior_prior{};
  std::array<double, kMaxVoices> posterior_probability{};
  // The weighted, centered detuning term actually added to the likelihood.
  // A valid comparison can contribute zero; keep availability separate.
  std::uint8_t posterior_detuning_valid_mask{};
  std::array<double, kMaxVoices> posterior_detuning_log_likelihood{};
  // Exact inputs after the current phase update, at the optional cue decision.
  // Admission snapshots precede that update and can use different energies.
  bool cue_evaluated{};
  bool cue_protected_group{};
  std::uint8_t cue_occupied_mask{};
  std::uint8_t cue_calibrated_mask{};
  std::uint8_t cue_primary_mask{};
  std::uint8_t cue_proposal_mask{};
  bool cue_applied{};
  bool cue_tuning_valid{};
  double cue_assignment_cents{};
  std::array<double, kMaxVoices> cue_similarities{};
  std::array<double, kMaxVoices> cue_cents_errors{};
};
#endif

#if defined(M3_TESTING)
struct PolyphonicPitchDetectorTestAccess;
#endif

struct DetectorDecision final {
  TickTransitions transitions{};
  TunerSnapshot tuner_snapshot{};
  // A host-readable strongest-voice projection accompanies the full
  // polyphonic editor snapshot. It does not replace or limit MIDI polyphony.
  TunerEstimate tuner{};
  bool tuner_snapshot_ready{};
};

// Selects a bounded polyphonic voice set and emits one lifecycle stream per
// selected note.
class PolyphonicPitchDetector final {
 public:
  PolyphonicPitchDetector() noexcept = default;
  PolyphonicPitchDetector(const PolyphonicPitchDetector&) = delete;
  PolyphonicPitchDetector& operator=(const PolyphonicPitchDetector&) = delete;

  bool configure(double sample_rate, const PersistentConfig& config) noexcept;
  void set_runtime_config(const PersistentConfig& config) noexcept;
  void reset() noexcept;
  [[nodiscard]] DetectorDecision process_sample(double sample) noexcept;
  bool begin_string_calibration(std::uint8_t string_index) noexcept;
  void cancel_string_calibration() noexcept;
  void clear_string_calibration() noexcept;
  [[nodiscard]] CalibrationSweepStatus calibration_status() const noexcept;
  [[nodiscard]] const StringCalibrationBank& calibration_bank() const noexcept;
  [[nodiscard]] std::uint8_t partial_detuning_candidate_count() const noexcept;
  [[nodiscard]] PartialDetuningEvidence partial_detuning_evidence(
      std::uint8_t midi_note) const noexcept;
  void set_calibration_bank(const StringCalibrationBank& bank) noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  [[nodiscard]] PartialAbsoluteCentsEvidence
  partial_absolute_cents_evidence(std::uint8_t midi_note) const noexcept;
  [[nodiscard]] SelectionDisposition selection_disposition(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] QuietDisposition quiet_disposition() const noexcept;
  [[nodiscard]] std::uint8_t selector_group_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] TierCompletionDisposition tier_completion_disposition(
      std::uint8_t midi_note) const noexcept;
  // Bit flags for the active physical-group resume predicate: active, valid
  // fine fit, multi-source, 2-4 members, assignment match, robust beat graph,
  // and minimum beat coherence respectively.
  [[nodiscard]] std::uint8_t fine_resume_evidence_flags(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t fine_frequency_member_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t fine_mask_pruning_output_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t fine_frequency_pending_member_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double fine_frequency_pending_evidence_seconds(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double
  fine_frequency_pending_minimum_pairwise_beat_coherence(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] FineFrequencyDisposition fine_frequency_disposition(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] FineFrequencyUnresolvedReason
  fine_frequency_unresolved_reason(std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t fine_frequency_fit_member_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double fine_frequency_residual_improvement(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double fine_frequency_minimum_member_ratio(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::array<double, kMaxVoices>
  fine_frequency_unique_member_improvement(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] const FineFrequencyMaskResidualTable&
  fine_frequency_mask_residuals(std::uint8_t midi_note) const noexcept;
  void set_hann_beat_shadow_buffer(HannBeatShadowBuffer* buffer) noexcept {
    hann_beat_shadow_buffer_ = buffer;
    if (buffer != nullptr) {
      *buffer = {};
    }
  }
  [[nodiscard]] const HannBeatShadowTable& hann_beat_shadow(
      std::uint8_t midi_note) const noexcept;
  void set_fine_mask_complexity_diagnostics_enabled(bool enabled) noexcept {
    fine_mask_complexity_diagnostics_enabled_ = enabled;
  }
  // Timed replay can omit report tables without changing decision policy.
  // Explicit diagnostic pruning still computes the tables it consumes.
  void set_fine_frequency_reporting_enabled(bool enabled) noexcept {
    fine_frequency_reporting_enabled_ = enabled;
  }
  void set_frequency_refinement_observer(
      diagnostics::FrequencyRefinementObserver observer, void* context) noexcept {
    frequency_refinement_observer_ = observer;
    frequency_refinement_context_ = context;
    if (observer != nullptr) {
      observer(context, {});
    }
  }
  void set_fine_mask_pruning_for_diagnostics(bool enabled) noexcept {
    diagnostic_fine_mask_pruning_enabled_ = enabled;
  }
  void set_fine_beat_pruning_for_diagnostics(bool enabled) noexcept {
    diagnostic_fine_beat_pruning_enabled_ = enabled;
  }
  void set_collecting_fine_history_carry_for_diagnostics(
      bool enabled) noexcept {
    diagnostic_collecting_fine_history_carry_enabled_ = enabled;
  }
  void set_skip_empty_fine_reset_for_diagnostics(bool enabled) noexcept {
    diagnostic_skip_empty_fine_reset_enabled_ = enabled;
  }
  [[nodiscard]] double fine_frequency_minimum_pairwise_beat_coherence(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double fine_frequency_pairwise_beat_coherence(
      std::uint8_t midi_note, std::uint8_t member_mask) const noexcept;
  [[nodiscard]] double fine_frequency_added_member_beat_coherence(
      std::uint8_t midi_note, std::uint8_t completion_mask) const noexcept;
  [[nodiscard]] double fine_frequency_added_member_ratio(
      std::uint8_t midi_note, std::uint8_t completion_mask) const noexcept;
  [[nodiscard]] std::uint8_t string_fret_posterior_best(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double string_fret_posterior_best_probability(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double string_fret_posterior_margin(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::array<double, kMaxVoices>
  string_fret_posterior_probabilities(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t string_fret_posterior_playable_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t profile_unison_proposal_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t temporal_unison_proposal_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t committed_unison_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint16_t committed_unison_gap_ticks(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] RetainedUnisonDisposition retained_unison_disposition(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] FineGroupDisposition fine_group_disposition(
      std::uint8_t midi_note) const noexcept;
  bool set_fine_group_ownership_diagnostics_enabled(bool enabled) noexcept {
    fine_group_ownership_diagnostics_enabled_ =
        enabled && fine_group_ownership_diagnostics_ != nullptr;
    return !enabled || fine_group_ownership_diagnostics_enabled_;
  }
  [[nodiscard]] FineGroupOwnershipDiagnostics fine_group_ownership_diagnostics(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] CandidateAdmissionDiagnostics candidate_admission_diagnostics(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] CandidateTrackingDiagnostics candidate_tracking_diagnostics(
      std::uint8_t midi_note) const noexcept;
  void set_calibrated_output_diagnostics_enabled(bool enabled) noexcept {
    calibrated_output_diagnostics_enabled_ = enabled;
    if (!enabled) calibrated_output_diagnostics_ = {};
  }
  void set_assignment_diagnostics_enabled(bool enabled) noexcept {
    assignment_diagnostics_enabled_ = enabled && assignment_diagnostics_ != nullptr;
    if (!assignment_diagnostics_enabled_) diagnostic_discarded_phase_states_ = {};
  }
  static constexpr std::uint32_t kResidualAssignmentDiagnosticDecimation = 16U;
  void set_residual_assignment_diagnostics_enabled(bool enabled) noexcept {
    residual_assignment_diagnostics_enabled_ = enabled;
    if (!enabled) diagnostic_discarded_phase_states_ = {};
  }
  [[nodiscard]] StringAssignmentDiagnostics string_assignment_diagnostics(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t group_continuity_diagnostic_flags(
      std::uint8_t midi_note) const noexcept;
  bool set_candidate_admission_rescue_for_diagnostics(
      double score_threshold_ratio,
      double fundamental_score_ratio) noexcept;
  void set_calibrated_collision_revalidation_for_diagnostics(
      bool enabled) noexcept {
    diagnostic_calibrated_collision_revalidation_ = enabled;
  }
  void set_polyphonic_posterior_assignment_for_diagnostics(
      bool enabled) noexcept {
    diagnostic_polyphonic_posterior_assignment_ = enabled;
  }
  void set_profile_pair_corroboration_for_diagnostics(bool enabled) noexcept {
    diagnostic_profile_pair_corroboration_ = enabled;
  }
  void set_profile_memory_partial_correction_for_diagnostics(bool enabled) noexcept {
    diagnostic_profile_memory_partial_correction_ = enabled;
  }
  void set_assignment_partial_correction_for_diagnostics(bool enabled) noexcept {
    diagnostic_assignment_partial_correction_ = enabled;
  }
  bool set_state_local_open_prior_for_diagnostics(bool enabled) noexcept {
    diagnostic_state_local_open_prior_ =
        enabled && diagnostic_open_prior_states_ != nullptr;
    return !enabled || diagnostic_state_local_open_prior_;
  }
  void set_coasting_harmonic_handoff_for_diagnostics(bool enabled) noexcept {
    diagnostic_coasting_harmonic_handoff_ = enabled;
  }
  void set_calibrated_harmonic_admission_guard_for_diagnostics(bool enabled) noexcept {
    diagnostic_calibrated_harmonic_admission_guard_ = enabled;
  }
  void set_fundamental_admission_for_diagnostics(bool enabled) noexcept {
    diagnostic_fundamental_admission_ = enabled;
  }
  void set_direct_evidence_retention_for_diagnostics(bool enabled) noexcept {
    diagnostic_direct_evidence_retention_ = enabled;
  }
  void set_odd_partial_cue_mask_for_diagnostics(
      const std::array<std::uint64_t, 2U>& mask) noexcept {
    diagnostic_odd_partial_cue_mask_ = mask;
  }
  void set_cue_free_lane_reassignment_for_diagnostics(bool enabled) noexcept {
    // Use frozen cues for string assignment only. Explicit fundamental admission
    // remains a separate opt-in diagnostic.
    diagnostic_cue_free_lane_reassignment_ = enabled;
  }
  [[nodiscard]] static std::uint8_t bounded_cue_free_lane_reassignment(
      bool pitch_confirmed, std::uint8_t current_mask,
      std::uint8_t playable_mask, std::uint8_t calibrated_mask,
      const std::array<double, kMaxVoices>& similarities,
      bool tuning_valid, const std::array<double, kMaxVoices>& cents_errors,
      std::uint8_t occupied_mask, bool protected_group,
      bool tuning_required = false, bool established_assignment = false) noexcept;
  void set_provisional_open_retention_guard_for_diagnostics(bool enabled) noexcept {
    diagnostic_provisional_open_retention_guard_ = enabled;
  }
  void set_joint_spectral_ownership_for_diagnostics(bool enabled) noexcept {
    diagnostic_joint_spectral_ownership_ = enabled;
    diagnostic_joint_midi_owner_guard_ = enabled;
  }
  void set_joint_spectral_ownership_for_diagnostics(
      bool solver, bool midi_guard) noexcept {
    diagnostic_joint_spectral_ownership_ = solver;
    diagnostic_joint_midi_owner_guard_ = midi_guard;
  }
  struct ResidualRecoveryStats final {
    std::uint32_t proposals{};
    std::uint32_t selected_ticks{};
    std::uint32_t note_ons{};
  };
  void set_residual_pitch_recovery_for_diagnostics(
      bool enabled, bool continuity = false) noexcept {
    diagnostic_residual_pitch_recovery_ = enabled;
    diagnostic_residual_recovery_continuity_ = enabled && continuity;
    diagnostic_residual_recovery_lease_ = {};
    diagnostic_residual_recovery_owners_.fill(kMaxVoices);
  }
  void submit_residual_recovery_for_diagnostics(
      std::uint32_t tick, std::uint8_t note, std::uint8_t string) noexcept;
  [[nodiscard]] std::uint8_t residual_recovery_owner_for_diagnostics(
      std::uint8_t note) const noexcept;
  [[nodiscard]] ResidualRecoveryStats residual_recovery_stats() const noexcept {
    return diagnostic_residual_recovery_stats_;
  }
  void set_profile_pair_output_filter_for_diagnostics(
      bool enabled, bool continuity_echo = false) noexcept {
    diagnostic_profile_pair_output_filter_ = enabled;
    diagnostic_profile_pair_continuity_echo_ = continuity_echo;
  }
  // Replay experiment only: vary pitch resolution while keeping the input
  // energy meter and silence threshold on their production time constant.
  bool set_correlation_window_for_diagnostics(
      double seconds, bool selection_only = false,
      bool shadow_only = false) noexcept;
  [[nodiscard]] bool correlation_window_energy_ratio_for_diagnostics(
      std::uint8_t midi_note, bool fundamental_only,
      double& ratio) const noexcept;
  [[nodiscard]] bool harmonic_correlations_for_diagnostics(
      std::uint8_t midi_note, std::array<double, 6U>& frequencies,
      std::array<std::complex<double>, 6U>& correlations,
      double& signal_energy, double& decay) const noexcept;
  // Measured baseband mixture tracks, without the carrier rotation used by
  // the residual solver. Reading them does not refresh or mutate any state.
  [[nodiscard]] bool demodulated_harmonic_tracks_for_diagnostics(
      std::uint8_t midi_note, std::array<double, 6U>& frequencies,
      std::array<std::complex<double>, 6U>& tracks,
      double& signal_energy, double& decay) const noexcept;
  bool set_fretted_position_prior_for_diagnostics(
      double fixed_penalty, double per_fret_penalty) noexcept;
  bool set_decisive_calibrated_selector_for_diagnostics(
      double minimum_margin, std::uint8_t allowed_string_mask) noexcept;
  bool set_calibrated_dp_replacement_lane_mask_for_diagnostics(
      std::uint8_t allowed_string_mask) noexcept;
  bool set_calibrated_selector_rescue_for_diagnostics(
      double minimum_similarity, double minimum_margin) noexcept;
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  [[nodiscard]] std::uint8_t group_continuity_cached_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double group_continuity_cache_age_seconds(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] bool observed_spectral_lane_fingerprint(
      std::uint8_t midi_note,
      UnisonSpectralFingerprint& fingerprint) const noexcept;
  [[nodiscard]] bool spectral_single_source_best_error(
      std::uint8_t midi_note, double& error) const noexcept;
  [[nodiscard]] std::uint8_t spectral_tier_completion_proposal_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] ObservedUnisonReacquisitionDisposition
  spectral_reacquisition_disposition(std::uint8_t midi_note) const noexcept;
  [[nodiscard]] UnisonCacheRefreshDisposition
  unison_cache_refresh_disposition(std::uint8_t midi_note) const noexcept;
  [[nodiscard]] double unison_reacquisition_cache_age_seconds(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] std::uint8_t unison_reacquisition_cache_mask(
      std::uint8_t midi_note) const noexcept;
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  struct SpectralHeadDiagnostics final {
    std::array<std::uint8_t, kSpectralTierCount + 1U> best_string{};
    std::array<double, kSpectralTierCount + 1U> margin{};
  };
  [[nodiscard]] SpectralHeadDiagnostics string_fret_spectral_heads(
      std::uint8_t midi_note) const noexcept;
#endif
#endif
#endif

#if defined(M3_JOINT_RESIDUAL_SHADOW)
  struct JointResidualShadowWork final {
    std::uint64_t evaluated_frames{};
    std::uint64_t valid_frames{};
    std::uint64_t pending_frames{};
    std::uint32_t max_rebuild_work{};
    std::uint32_t max_pitch_count{};
    double residual_sum{};
    std::uint64_t output_veto_frames{};
    std::uint64_t output_note_offs{};
    std::uint64_t output_retriggers{};
    std::uint64_t output_joint_restores_valid{};
    std::uint64_t output_joint_restores_pending{};
    std::uint64_t output_joint_restores_unavailable{};
    std::uint64_t output_joint_restores_energy_low{};
    std::uint64_t output_joint_restores_energy_mid{};
    std::uint64_t output_joint_restores_energy_high{};
    std::uint64_t output_joint_restores_safety{};
  };
  // Test/replay opt-in only; this is not a plug-in parameter.
  void enable_joint_residual_output(bool enabled) noexcept;
  [[nodiscard]] JointResidualShadowWork joint_residual_shadow_work() const noexcept {
    return joint_residual_shadow_work_;
  }
#if defined(M3_TESTING)
  void reset_joint_residual_shadow_for_test() noexcept {
    if (joint_residual_shadow_ != nullptr) {
      joint_residual_shadow_->reset();
    }
  }
  void clear_joint_residual_shadow_metrics_for_test() noexcept {
    joint_residual_shadow_work_ = {};
  }
#endif
#endif

#if defined(M3_TESTING)
  struct SelectionWork final {
    std::uint32_t pool_candidates{};
    std::uint32_t state_transitions{};
    std::uint32_t assignment_edges{};
  };

  [[nodiscard]] SelectionWork selection_work_for_test() const noexcept {
    return selection_work_;
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  void set_offline_replay_diagnostics_enabled_for_test(
      bool enabled) noexcept {
    offline_replay_diagnostics_enabled_ = enabled;
  }
#endif
#endif

 private:
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS) || defined(M3_JOINT_RESIDUAL_SHADOW)
  [[nodiscard]] bool read_harmonic_correlations(
      std::uint8_t midi_note, std::array<double, 6U>& frequencies,
      std::array<std::complex<double>, 6U>& correlations,
      double& signal_energy, double& decay) const noexcept;
#endif
#if defined(M3_JOINT_RESIDUAL_SHADOW)
  void observe_joint_residual_shadow(const TunerSnapshot& snapshot) noexcept;
  void evaluate_joint_residual_output(
      const std::array<bool, kMaxCandidates>& selected, bool quiet,
      std::array<bool, kMaxCandidates>& veto) noexcept;
  [[nodiscard]] bool joint_residual_veto_eligible(
      std::size_t candidate, bool selected,
      const JointPitchResidualResult& result, std::size_t pitch,
      bool ignore_energy_ceiling = false) const noexcept;
  void reconcile_joint_residual_output(
      DetectorDecision& decision, std::size_t candidate,
      bool selected, bool spectral_veto, bool joint_veto) noexcept;
  bool joint_residual_output_enabled_{};
  bool joint_residual_output_valid_{};
  bool joint_residual_output_pending_{};
  // Valid-result restore causes: safety=0, energy [0.001,0.002)=1,
  // [0.002,0.005)=2, >=0.005=3. Count only successful MIDI restores.
  std::array<std::uint8_t, kMaxCandidates> joint_residual_restore_reason_{};
  // Allocate once during construction, before configuration or audio calls.
  // Four detectors already nearly fill an 8 MiB caller stack in native tests.
  // The owned solver retains fixed storage; configure/reset/process never grow it.
  std::unique_ptr<JointPitchResidual> joint_residual_shadow_{
      new (std::nothrow) JointPitchResidual{}};
  JointResidualShadowWork joint_residual_shadow_work_{};
#endif
#if defined(M3_TESTING)
  friend struct PolyphonicPitchDetectorTestAccess;
#endif
  static constexpr std::size_t kHarmonicCount = 6U;
  static constexpr std::size_t kCellCount = kMaxCandidates * kHarmonicCount;
  struct Cell final {
    double cosine{1.0};
    double sine{};
    double cosine_step{1.0};
    double sine_step{};
    double fast_real{};
    double fast_imaginary{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    double diagnostic_selection_real{};
    double diagnostic_selection_imaginary{};
#endif
    bool enabled{};
  };

  struct CandidateState final {
    std::uint8_t attack_ticks{};
    std::uint16_t release_ticks{};
    std::uint8_t evidence_ticks{};
    std::uint8_t evidence_gap_ticks{};
    std::uint16_t age_ticks{};
    bool active{};
    std::uint8_t assigned_string{kUnassignedTunerString};
    std::uint8_t assigned_string_mask{};
    std::uint8_t unison_evidence_ticks{};
    std::uint16_t unison_gap_ticks{};
    std::uint16_t committed_unison_confirmed_ticks{};
    std::uint8_t pending_unison_mask{};
    std::uint8_t midi_voice_mask{};
    std::uint8_t emitted_note{kTunerNoSignalNote};
    std::uint8_t calibrated_output_target{kTunerNoSignalNote};
    std::uint8_t calibrated_output_ticks{};
    // A bounded DP correction may change only the note rendered to MIDI for
    // an already-active single physical lane.  Keep it separate from
    // emitted_note so detector continuity, calibration, and string ownership
    // continue to follow the causal pitch candidate that actually survived
    // selection.
    std::uint8_t dp_output_projection_note{kTunerNoSignalNote};
    std::uint8_t dp_output_projection_target{kTunerNoSignalNote};
    std::uint8_t dp_output_projection_ticks{};
    std::int16_t retained_cents_q8{};
    std::uint16_t retained_confidence_q15{};
    bool retained_cents_valid{};
    bool polyphonic_context{};
    bool calibrated_lane_committed{};
    bool spectral_duplicate_output_suppressed{};
#if defined(M3_JOINT_RESIDUAL_SHADOW)
    // Rendering only: selection, string ownership and model membership persist.
    bool joint_residual_output_suppressed{};
#endif
    std::uint8_t spectral_lane_mask{};
    // Output-only restoration of a recently established physical group.
    // This mask never participates in pitch selection or string ownership.
    std::uint8_t continuity_lane_mask{};
    std::uint8_t continuity_cached_group_mask{};
    std::uint32_t continuity_cached_group_tick{};
    std::uint8_t continuity_cached_note{kTunerNoSignalNote};
    std::uint8_t latest_unison_proposal_mask{};
    bool latest_unison_proposal_temporal{};
    // A causal fine-frequency fit may remove unsupported lanes from an
    // already-selected 3/4-string pitch group. It never creates a pitch or
    // adds ownership.
    std::uint8_t fine_beat_pruning_mask{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    std::uint8_t diagnostic_unison_proposal_mask{};
    bool diagnostic_unison_temporal{};
    std::uint8_t group_continuity_diagnostic_flags{};
    // Output-only production-shaped candidate. It can only remove lanes from
    // the currently emitted same-pitch group and never mutates ownership.
    std::uint8_t diagnostic_fine_mask_pruning_mask{};
    std::uint8_t diagnostic_fine_beat_pruning_mask{};
    bool diagnostic_profile_pair_output_filtered{};
#endif
  };

  struct PhaseCentsState final {
    double filtered_real{};
    double filtered_imaginary{};
    double filtered_twice_real{};
    double filtered_twice_imaginary{};
    double previous_real{};
    double previous_imaginary{};
    double frequency_offset{};
    double cents{};
    std::uint16_t accepted_updates{};
    bool has_previous{};
    bool valid{};
    bool output_projection_valid{};
  };

  struct BeatEvidenceState final {
    double envelope_mean{};
    double absolute_deviation{};
    double beat_hz{};
    std::uint32_t decisions_since_crossing{};
    std::uint16_t accepted_cycles{};
    bool initialized{};
    bool below_gate{};
    bool valid{};
  };

  struct SpectralHeadEvidence final {
    std::array<std::uint8_t, kSpectralTierCount + 1U> best_string{};
    std::array<double, kSpectralTierCount + 1U> margin{};
  };

  static constexpr std::size_t kFineFrequencyHistoryCapacity = 512U;
  struct FineFrequencyEvidenceState final {
    std::array<double, kFineFrequencyHistoryCapacity> real{};
    std::array<double, kFineFrequencyHistoryCapacity> imaginary{};
    std::array<std::uint32_t, kFineFrequencyHistoryCapacity> decision_ticks{};
    std::array<double, kMaxVoices> component_energy{};
    // Production keeps only the strongest causal beat corroboration for
    // adding each one physical string. The full 256-mask matrix remains an
    // offline diagnostic, but MIDI inference needs at most eight bounded
    // values and never allocates on the audio thread.
    std::array<double, kMaxVoices> added_member_beat_coherence{};
    double frequency_deviation_hz{};
    double minimum_pairwise_beat_coherence{};
    double pending_minimum_pairwise_beat_coherence{};
    std::uint32_t last_decision_tick{};
    std::uint16_t write_index{};
    std::uint16_t count{};
    std::uint16_t pending_count{};
    std::uint8_t member_mask{};
    std::uint8_t pending_member_mask{};
    std::uint8_t beat_pruning_source_mask{};
    std::uint8_t beat_pruned_member_mask{};
    bool robust_pairwise_beat_connected{};
    bool pending_robust_pairwise_beat_connected{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    std::uint8_t fit_member_mask{};
    double residual_improvement{};
    std::array<double, kMaxVoices> unique_member_improvement{};
    FineFrequencyMaskResidualTable mask_residuals{};
    bool residual_rejected{};
    std::array<double, 1U << kMaxVoices>
        pairwise_beat_coherence_by_mask{};
    std::array<double, 1U << kMaxVoices>
        added_member_beat_coherence_by_completion_mask{};
#endif
    bool multi_source_observed{};
    bool valid{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    FineFrequencyDisposition disposition{FineFrequencyDisposition::unresolved};
    FineFrequencyUnresolvedReason unresolved_reason{
        FineFrequencyUnresolvedReason::no_history};
#endif
  };

  struct FineFrequencyUniformGramCache final {
    std::array<std::array<std::complex<double>, kMaxVoices>, kMaxVoices>
        normalized_gram{};
    std::array<double, kMaxVoices> offsets{};
    std::uint16_t sample_count{};
    std::uint32_t tick_step{};
    std::uint8_t component_count{};
    bool valid{};
  };

  struct M3PoolCandidate final {
    std::uint8_t detector_index{};
    std::uint8_t string_mask{};
    double score{};
    bool active{};
  };

  struct M3DpState final {
    double score_sum{};
    std::uint64_t chosen{};
    std::uint8_t voice_count{};
    std::uint8_t retained_active{};
    bool valid{};
  };

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  M3DpState select_state_local_open_prior(
      std::size_t pool_count,
      const std::array<std::uint8_t, kMaxVoices * kMaxVoices>& atomic_groups,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      std::size_t priority_candidate, std::uint8_t priority_mask,
      double fixed_penalty, double per_fret_penalty,
      std::uint8_t& best_mask, std::uint8_t& selected_open_count) noexcept;
#endif

  struct SpectralLaneState final {
    UnisonSpectralCorridorTracker tracker{};
    UnisonSpectralTemplateSet templates{};
    std::uint8_t candidate_index{0xffU};
    std::uint8_t midi_note{kTunerNoSignalNote};
    std::uint8_t single_source_error_mask{};
    UnisonSpectralPhase template_phase{UnisonSpectralPhase::unready};
    double single_source_best_error{
        std::numeric_limits<double>::infinity()};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    double single_source_posterior_margin{};
#endif
    std::uint32_t single_source_error_tick{};
    bool tracking{};
    bool templates_valid{};
    bool single_source_error_valid{};
  };

  struct GroupContinuityTrackerState final {
    UnisonSpectralCorridorTracker tracker{};
    UnisonSpectralClassification last_classification{};
    UnisonSpectralTemplateSet templates{};
    std::uint8_t candidate_index{0xffU};
    std::uint8_t midi_note{kTunerNoSignalNote};
    UnisonSpectralPhase template_phase{UnisonSpectralPhase::unready};
    bool tracking{};
    bool templates_valid{};
  };

#if defined(M3_UNISON_SPECTRAL_SHADOW)
  struct UnisonReacquisitionState final {
    UnisonSpectralFingerprint confirmed_fingerprint{};
    std::uint32_t last_confirmed_tick{};
    std::uint8_t resolved_mask{};
    std::uint8_t candidate_index{0xffU};
    bool confirmed_fingerprint_valid{};
  };
#endif

  [[nodiscard]] DetectorDecision make_decision() noexcept;
  void update_cell(Cell& cell, double sample) noexcept;
  [[nodiscard]] std::uint8_t dynamic_velocity() const noexcept;
  [[nodiscard]] std::uint8_t attack_decisions() const noexcept;
  [[nodiscard]] std::uint16_t release_decisions() const noexcept;
  [[nodiscard]] std::uint16_t candidate_release_decisions(
      std::size_t candidate, bool quiet) const noexcept;
  [[nodiscard]] bool should_handoff_adjacent_coasting_candidate(
      std::size_t candidate,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      const std::array<bool, kMaxCandidates>& selected,
      std::size_t selected_count,
      bool quiet) const noexcept;
  [[nodiscard]] bool should_handoff_coasting_candidate_to_resolved_group(
      std::size_t candidate,
      const std::array<bool, kMaxCandidates>& selected) const noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  [[nodiscard]] bool reject_calibrated_harmonic_admission_for_diagnostics(
      std::size_t candidate, std::size_t stronger,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      std::size_t count, double threshold) const noexcept;
  [[nodiscard]] bool try_coasting_harmonic_handoff_for_diagnostics(
      DetectorDecision& decision, std::size_t candidate,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      const std::array<bool, kMaxCandidates>& selected, bool quiet) noexcept;
#endif
  [[nodiscard]] std::uint8_t candidate_evidence_decisions(
      bool multi_voice) const noexcept;
  [[nodiscard]] double signal_floor() const noexcept;
  [[nodiscard]] static bool has_minimum_signal_evidence(
      std::uint32_t signal_samples, double sample_rate,
      bool had_active_multi_string_group) noexcept;
  [[nodiscard]] static bool is_resolved_unison_resume_candidate(
      bool active, std::uint8_t owned_string_mask, bool fine_valid,
      bool fine_multi_source, bool fine_robust_pairwise_beat_connected,
      double fine_minimum_pairwise_beat_coherence,
      std::uint8_t fine_member_mask) noexcept;
  static void filter_resume_selection(
      bool active_resume,
      const std::array<bool, kMaxCandidates>& active_candidates,
      std::array<bool, kMaxCandidates>& selected,
      std::size_t count) noexcept;
  [[nodiscard]] bool append_transition(
      DetectorDecision& decision, TransitionKind kind, std::uint8_t note,
      std::uint8_t velocity,
      std::uint8_t voice_id = kUnassignedVoiceId) noexcept;
  [[nodiscard]] static bool output_suppressed(const CandidateState& state) noexcept;
  [[nodiscard]] bool append_candidate_note_on(
      DetectorDecision& decision, std::size_t candidate,
      std::uint8_t velocity
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      , std::size_t releasing_candidate = kMaxCandidates
#endif
      ) noexcept;
  [[nodiscard]] bool append_candidate_note_off(
      DetectorDecision& decision, std::size_t candidate) noexcept;
  [[nodiscard]] bool append_atomic_candidate_handoff(
      DetectorDecision& decision, std::size_t incumbent,
      std::size_t target, std::uint8_t velocity) noexcept;
  void update_calibrated_output_notes(
      DetectorDecision& decision,
      const std::array<bool, kMaxCandidates>& selected,
      std::size_t selected_note_count, bool quiet = false) noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  [[nodiscard]] bool reset_candidate_output_projections(
      DetectorDecision& decision, std::size_t candidate) noexcept;
#endif
  void change_candidate_output_note(DetectorDecision& decision,
                                    std::size_t candidate,
                                    std::uint8_t output_note) noexcept;
  [[nodiscard]] bool change_candidate_dp_output_projection(
      DetectorDecision& decision, std::size_t candidate,
      std::uint8_t output_note) noexcept;
  [[nodiscard]] std::uint8_t candidate_output_note(
      std::size_t candidate) const noexcept;
  [[nodiscard]] std::uint8_t candidate_midi_output_note(
      std::size_t candidate) const noexcept;
  [[nodiscard]] std::int16_t candidate_output_cents_q8(
      std::size_t candidate, std::int16_t detected_cents_q8) const noexcept;
  void write_snapshot(DetectorDecision& decision,
                      const std::array<double, kMaxCandidates>& scores,
                      const std::array<bool, kMaxCandidates>& selected,
                      bool quiet) noexcept;
  [[nodiscard]] bool is_harmonic_shadow(
      std::size_t candidate, std::size_t selected_candidate,
      const std::array<double, kMaxCandidates>& fundamentals) const noexcept;
  void refresh_m3_playable_string_masks() noexcept;
  [[nodiscard]] std::uint8_t playable_string_mask(
      std::size_t candidate) const noexcept;
  [[nodiscard]] bool has_calibrated_direct_support(
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      std::size_t candidate, std::size_t count,
      double threshold) const noexcept;
  [[nodiscard]] bool has_decisive_calibrated_shape(
      std::size_t candidate, std::size_t count) const noexcept;
  [[nodiscard]] bool has_calibrated_shape_thresholds(
      std::size_t candidate, std::size_t count,
      double minimum_similarity, double minimum_margin) const noexcept;
  [[nodiscard]] static bool has_decisive_calibrated_shape_thresholds(
      std::size_t playable_count, std::size_t measured_count,
      double best_similarity, double second_similarity,
      double minimum_similarity, double minimum_margin) noexcept;
  [[nodiscard]] static bool has_isolated_shadow_context(
      std::uint8_t other_eligible,
      std::uint8_t other_active,
      bool sole_other_is_harmonic) noexcept;
  [[nodiscard]] static bool has_isolated_third_partial_context(
      std::size_t candidate, std::size_t strongest_other,
      std::uint8_t other_eligible, std::uint8_t other_active,
      bool strongest_other_has_decisive_shape) noexcept;
  void select_m3_feasible_candidates(
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      const std::array<double, kMaxCandidates>& narrow_fundamentals,
      double threshold,
      std::array<bool, kMaxCandidates>& selected,
      std::size_t count) noexcept;
  void assign_m3_strings(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void apply_calibrated_dp_replacements(
      std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet, std::size_t count) noexcept;
  void update_calibrated_dp_output_projections(
      DetectorDecision& decision,
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet, std::size_t count) noexcept;
  void update_harmonic_profile_memory(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void update_beat_evidence(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  [[nodiscard]] static QuietDisposition classify_quiet_disposition(
      bool minimum_evidence, bool below_signal_floor, bool had_active_voice,
      bool rapid_mute, bool below_slow_energy_ratio,
      bool multi_voice_evidence,
      SignalLossDisposition last_signal_loss) noexcept;
#endif
  [[nodiscard]] static bool retain_fine_frequency_history_across_gap(
      const FineFrequencyEvidenceState& fine,
      std::uint16_t established_group_samples) noexcept;
  [[nodiscard]] static bool committed_fine_group_matches_assignment(
      const FineFrequencyEvidenceState& fine,
      bool candidate_active, std::uint8_t assigned_member_mask) noexcept;
  [[nodiscard]] static double fine_frequency_consensus_seconds(
      std::uint8_t current_member_mask,
      std::uint8_t proposed_member_mask,
      std::uint8_t playable_member_mask) noexcept;
  [[nodiscard]] static std::uint8_t bounded_fine_mask_complexity_output(
      bool active, bool selected, bool direct_fundamental, bool quiet,
      double score_threshold_ratio, std::uint8_t current_output_mask,
      std::uint8_t playable_mask, std::uint8_t other_output_mask,
      std::uint8_t maximum_polyphony,
      const std::array<std::uint8_t, 11U>& masks,
      const std::array<double, 11U>& normalized_residual,
      std::size_t count) noexcept;
  [[nodiscard]] static std::uint8_t bounded_fine_beat_pruning_output(
      std::uint8_t midi_note, bool active, bool selected,
      bool direct_fundamental, bool quiet, double score_threshold_ratio,
      std::uint8_t current_output_mask, std::uint8_t playable_mask,
      std::uint8_t other_output_mask, std::uint8_t maximum_polyphony,
      const std::array<std::uint8_t, 10U>& masks,
      const std::array<double, 10U>& normalized_residual,
      const std::array<double, 10U>& minimum_beat_coherence,
      const std::array<bool, 10U>& beat_graph_connected,
      std::size_t count) noexcept;
  void update_fine_frequency_evidence(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
  void update_fine_beat_pruning_output_projection(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  void append_joint_candidate_attacks_for_diagnostics(
      DetectorDecision& decision,
      const std::array<bool, kMaxCandidates>& ready,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      std::size_t& active_count) noexcept;
  [[nodiscard]] bool diagnostic_midi_owner_conflict(
      std::size_t candidate, std::uint8_t desired,
      std::size_t releasing_candidate) const noexcept;
  [[nodiscard]] std::uint8_t diagnostic_profile_pair_output_mask(
      std::size_t candidate, std::uint8_t desired) const noexcept;
  void record_fine_history_reset(std::size_t candidate,
                                 FineHistoryResetReason reason) noexcept;
  void update_fine_mask_pruning_output_projection(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
#endif
  void invalidate_fine_frequency_uniform_gram_cache() noexcept;
  [[nodiscard]] SpectralHeadEvidence string_fret_spectral_head_evidence(
      std::size_t candidate) const noexcept;
  [[nodiscard]] static std::uint8_t spectral_tier_completion_candidate(
      std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
      const SpectralHeadEvidence& spectral) noexcept;
  [[nodiscard]] static std::uint8_t bounded_spectral_tier_completion(
      bool active, std::uint8_t current_assignment_mask,
      std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
      const SpectralHeadEvidence& spectral,
      const std::array<double, kMaxVoices>&
          added_member_beat_coherence,
      const std::array<double, kMaxVoices>& component_energy) noexcept;
  [[nodiscard]] std::uint16_t unison_dropout_decisions(
      std::size_t candidate) const noexcept;
  void update_phase_cents_estimates(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void update_partial_detuning_evidence(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void update_calibration_tuning_offset(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void infer_m3_unison_strings(
      const std::array<bool, kMaxCandidates>& selected) noexcept;
  void update_spectral_lane_states(
      const std::array<bool, kMaxCandidates>& selected, bool quiet) noexcept;
  void update_adjacent_spectral_duplicate_suppression() noexcept;
  [[nodiscard]] SpectralLaneState* find_spectral_lane_state(
      std::size_t candidate) noexcept;
  [[nodiscard]] const SpectralLaneState* find_spectral_lane_state(
      std::size_t candidate) const noexcept;
  [[nodiscard]] SpectralLaneState* acquire_spectral_lane_state(
      std::size_t candidate) noexcept;
  [[nodiscard]] std::uint8_t spectral_lane_assignment(
      std::size_t candidate, bool isolated_selected_voice) noexcept;
  [[nodiscard]] static std::uint8_t bounded_spectral_lane_assignment(
      bool active, std::uint8_t current_assignment_mask,
      std::uint8_t playable_mask, std::uint8_t other_owned_mask,
      bool polyphonic_context,
      bool fine_frequency_valid, bool fine_frequency_multi_source,
      std::uint8_t fine_frequency_member_mask,
      UnisonSpectralPhase phase,
      bool relaxed_onset_allowed,
      const UnisonSpectralClassification& classification) noexcept;
  [[nodiscard]] static std::uint8_t
  bounded_adjacent_spectral_duplicate_suppression(
      bool left_active, bool right_active, std::uint8_t left_note,
      std::uint8_t right_note, std::uint8_t left_output_mask,
      std::uint8_t right_output_mask, bool left_spectral_ready,
      bool right_spectral_ready, double left_error,
      double right_error) noexcept;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  [[nodiscard]] static std::array<std::uint8_t, kMaxVoices>
  bounded_joint_spectral_lanes(
      const std::array<std::uint8_t, kMaxVoices>& proposals,
      const std::array<std::uint8_t, kMaxVoices>& primary_masks,
      const std::array<std::uint8_t, kMaxVoices>& playable_masks,
      const std::array<double, kMaxVoices>& posterior_margins,
      const std::array<std::uint8_t, kMaxVoices>& incumbent_masks,
      std::uint8_t reserved_mask, std::size_t count,
      std::uint8_t active_owner_mask) noexcept;
#endif
  [[nodiscard]] static std::uint8_t projected_output_string_mask(
      std::uint8_t assigned_string_mask, std::uint8_t assigned_string,
      std::uint8_t spectral_lane_mask,
      std::uint8_t continuity_lane_mask) noexcept;
  [[nodiscard]] static std::uint8_t bounded_group_continuity_projection(
      std::uint8_t current_assignment_mask,
      std::uint8_t cached_group_mask,
      const UnisonSpectralClassification& classification,
      UnisonSpectralPhase phase, std::uint8_t fine_frequency_mask,
      double minimum_beat_coherence, std::uint8_t profile_mask,
      std::uint8_t temporal_mask, std::uint8_t tier_projection_mask,
      std::uint8_t other_owned_mask, std::uint8_t playable_mask,
      std::uint8_t maximum_polyphony, bool active_candidate,
      bool selected_or_coasting, bool direct_fundamental, bool quiet,
      double cache_age_seconds) noexcept;
  [[nodiscard]] static std::uint8_t
  bounded_three_member_articulated_group_continuity_projection(
      std::uint8_t current_assignment_mask,
      std::uint8_t cached_group_mask,
      std::uint8_t pending_fine_mask,
      double pending_evidence_seconds,
      double pending_beat_coherence,
      std::uint8_t spectral_tier_mask,
      std::uint8_t other_owned_mask,
      std::uint8_t playable_mask,
      std::uint8_t maximum_polyphony,
      double score_threshold_ratio,
      bool active_candidate,
      bool direct_fundamental,
      bool quiet,
      double cache_age_seconds) noexcept;
  [[nodiscard]] static std::uint8_t
  bounded_solo_three_member_articulated_group_continuity_projection(
      std::uint8_t current_assignment_mask,
      std::uint8_t cached_group_mask,
      std::uint8_t pending_fine_mask,
      double pending_evidence_seconds,
      double pending_beat_coherence,
      std::uint8_t spectral_tier_mask,
      std::uint8_t other_owned_mask,
      std::uint8_t playable_mask,
      std::uint8_t maximum_polyphony,
      double score_threshold_ratio,
      bool active_candidate,
      bool direct_fundamental,
      bool quiet,
      double cache_age_seconds) noexcept;
  void update_group_continuity_trackers(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
  [[nodiscard]] GroupContinuityTrackerState*
  find_group_continuity_tracker(std::size_t candidate) noexcept;
  [[nodiscard]] const GroupContinuityTrackerState*
  find_group_continuity_tracker(std::size_t candidate) const noexcept;
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  void update_unison_reacquisition_state(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
  [[nodiscard]] UnisonReacquisitionState* find_unison_reacquisition_state(
      std::size_t candidate) noexcept;
  [[nodiscard]] const UnisonReacquisitionState*
  find_unison_reacquisition_state(std::size_t candidate) const noexcept;
  [[nodiscard]] UnisonReacquisitionState* acquire_unison_reacquisition_state(
      std::size_t candidate) noexcept;
#endif
  void observe_calibration(
      const std::array<double, kMaxCandidates>& scores,
      double lower_guard_score, double upper_guard_score, bool quiet) noexcept;
  [[nodiscard]] double calibration_similarity(
      std::size_t candidate, std::size_t string) const noexcept;
  [[nodiscard]] double calibration_similarity_from_energy_profile(
      std::size_t candidate, std::size_t string,
      const std::array<double, kCalibrationHarmonicCount>& current,
      double total) const noexcept;
  [[nodiscard]] double settled_calibration_similarity(
      std::size_t candidate, std::size_t string) const noexcept;
  [[nodiscard]] double settled_calibration_similarity_from_fast_similarity(
      std::size_t candidate, std::size_t string,
      double fast_similarity) const noexcept;
  [[nodiscard]] double corrected_harmonic_energy(
      std::size_t candidate, std::size_t harmonic) const noexcept;
  [[nodiscard]] double profile_harmonic_energy(
      std::size_t candidate, std::size_t harmonic) const noexcept;
  [[nodiscard]] double harmonic_energy_at_cents(
      std::size_t candidate, std::size_t harmonic, double cents) const noexcept;
  [[nodiscard]] std::size_t cell_index(std::size_t candidate,
                                       std::size_t harmonic) const noexcept {
    return candidate * kHarmonicCount + harmonic;
  }

  std::array<Cell, kCellCount> cells_{};
  std::array<std::uint16_t, kCellCount> enabled_cell_indices_{};
  std::uint16_t enabled_cell_count_{};
  // Boundary-only analysis cells make the configured lowest/highest notes
  // tunable without adding selectable candidates to the pitch set.
  std::array<Cell, kHarmonicCount> lower_cents_guard_cells_{};
  std::array<Cell, kHarmonicCount> upper_cents_guard_cells_{};
  std::array<std::uint8_t, kHarmonicCount> lower_cents_guard_indices_{};
  std::array<std::uint8_t, kHarmonicCount> upper_cents_guard_indices_{};
  std::uint8_t lower_cents_guard_count_{};
  std::uint8_t upper_cents_guard_count_{};
  std::array<CandidateState, kMaxCandidates> candidate_states_{};
  std::array<std::uint8_t, kMaxCandidates> playable_string_masks_{};
  std::array<double, kMaxCandidates> narrow_fundamental_real_{};
  std::array<double, kMaxCandidates> narrow_fundamental_imaginary_{};
  std::array<std::array<double, kHarmonicCount>, kMaxCandidates>
      harmonic_energy_memory_{};
  std::array<std::array<double, kHarmonicCount>, kMaxCandidates>
      long_harmonic_energy_memory_{};
  std::array<std::uint16_t, kMaxCandidates> harmonic_memory_updates_{};
  std::array<PhaseCentsState, kMaxCandidates> phase_cents_states_{};
  std::array<PartialDetuningTracker, kMaxCandidates>
      partial_detuning_trackers_{};
  std::array<std::uint32_t, kMaxCandidates>
      partial_detuning_last_update_ticks_{};
  std::size_t partial_detuning_cursor_{};
  std::array<BeatEvidenceState, kMaxCandidates> beat_evidence_states_{};
  std::array<FineFrequencyEvidenceState, kMaxCandidates>
      fine_frequency_evidence_states_{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  // Fine-pitch evidence for discarded candidates, used only by fixed-context
  // assignment diagnostics. Never transferred to native candidate state.
  std::array<PhaseCentsState, kMaxCandidates> diagnostic_discarded_phase_states_{};
  std::array<FineHistoryResetDiagnostics, kMaxCandidates>
      fine_history_reset_diagnostics_{};
#endif
  std::array<FineFrequencyUniformGramCache, kMaxCandidates>
      fine_frequency_uniform_gram_cache_{};
  std::array<double, kFineFrequencyHistoryCapacity>
      fine_frequency_hann_window_{};
  StringFretPosteriorBank string_fret_posteriors_{};
  std::array<double, kMaxCandidates> string_fret_energy_memory_{};
  std::array<M3PoolCandidate, kMaxVoices * kMaxVoices> m3_pool_{};
  std::array<M3DpState, 1U << kMaxVoices> m3_dp_states_{};
  // Ephemeral masks chosen by the pitch/string joint selector for this
  // decision. assign_m3_strings uses them to keep a corroborated physical
  // group intact without committing MIDI lanes before the ordinary unison
  // evidence gate runs.
  std::array<std::uint8_t, kMaxCandidates> selector_group_masks_{};
  std::array<bool, kMaxCandidates> selector_dp_evicted_candidates_{};
  std::array<bool, kMaxCandidates> selector_atomic_handoff_targets_{};
  std::array<std::uint8_t, kMaxCandidates>
      selector_atomic_handoff_target_for_incumbent_{};
  // The protected corpus admits atomic DP replacement only on the three
  // middle physical lanes. Wider masks improve some chord counts but regress
  // constructed or upper-unison evidence.
  std::uint8_t dp_replacement_allowed_string_mask_{0x38U};
  std::array<SpectralLaneState, kMaxVoices> spectral_lane_states_{};
  // Output-only rejection of an adjacent harmonic duplicate. The selector,
  // pitch evidence, and physical-lane ownership remain unchanged; a bit is
  // set only when two already-active one-lane candidates have settled
  // production spectral fingerprints separated by the protected margin.
  std::array<bool, kMaxCandidates> spectral_duplicate_suppressed_{};
  double spectral_lane_decimation_sum_{};
  std::uint8_t spectral_lane_decimation_count_{};
  std::uint8_t spectral_lane_decimation_{1U};
  // Each corridor costs 102 complex resonators. Keep at most four simultaneous
  // pitch contexts and classify only one per decision in round-robin order.
  // The dedicated production timing test independently enforces the deadline.
  static constexpr std::size_t kMaximumGroupContinuityTrackers = 4U;
  std::array<GroupContinuityTrackerState,
             kMaximumGroupContinuityTrackers>
      group_continuity_trackers_{};
  std::uint8_t group_continuity_classification_cursor_{};
  double group_continuity_decimation_sum_{};
  std::uint8_t group_continuity_decimation_count_{};
  std::uint8_t group_continuity_decimation_{1U};
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  // Offline candidate policy only. Slots bind to at most eight active physical
  // groups so replay can test cache/reacquisition hypotheses without adding
  // state or work to production VST3 builds.
  std::array<UnisonReacquisitionState, kMaxVoices>
      unison_reacquisition_states_{};
#endif
  StringSweepCalibrator calibrator_{};
  double sample_rate_{};
  double dc_pole{};
  double correlation_decay{};
  double narrow_correlation_decay{};
  double harmonic_memory_decay{};
  double long_harmonic_memory_decay{};
  double slow_energy_decay{};
  double previous_input_{};
  double previous_dc_output_{};
  double fast_energy_{};
  double slow_energy_{};
  double previous_decision_energy_{};
  double signal_floor_{};
  double calibration_tuning_offset_cents_{};
  std::array<double, kMaxVoices> calibration_tuning_lane_cents_{};
  std::array<double, kMaxVoices> pending_calibration_tuning_lane_cents_{};
  std::array<std::uint16_t, kMaxVoices>
      pending_calibration_tuning_lane_observations_{};
  std::uint32_t decision_phase_{};
  std::uint32_t transition_sequence_{};
  std::uint8_t lowest_note_{};
  std::uint8_t candidate_count_{};
  std::uint8_t max_polyphony_{1U};
  std::uint8_t max_fret_{24U};
  std::uint8_t sensitivity_{50U};
  std::uint8_t response_{25U};
  std::uint16_t unison_dropout_decisions_{1U};
  std::uint16_t fine_frequency_decimation_decisions_{1U};
  std::uint16_t calibration_tuning_evidence_{};
  std::uint8_t calibration_tuning_lane_mask_{};
  std::uint8_t fixed_velocity_{100U};
  VelocityMode velocity_mode_{VelocityMode::dynamic};
  MidiRouting midi_routing_{MidiRouting::single};
  std::uint32_t snapshot_generation_{};
  std::uint32_t decision_counter_{};
  std::uint32_t signal_samples_{};
  std::uint32_t narrow_signal_samples_{};
  ProfileMode profile_mode_{ProfileMode::m3};
  bool signal_present_{};
  bool configured_{};

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  HannBeatShadowBuffer* hann_beat_shadow_buffer_{};
  diagnostics::FrequencyRefinementObserver frequency_refinement_observer_{};
  void* frequency_refinement_context_{};
  QuietDisposition quiet_disposition_{QuietDisposition::not_quiet};
  SignalLossDisposition last_signal_loss_{SignalLossDisposition::none};
  std::array<SelectionDisposition, kMaxCandidates>
      selection_dispositions_{};
  std::array<RetainedUnisonDisposition, kMaxCandidates>
      retained_unison_dispositions_{};
  std::array<FineGroupDisposition, kMaxCandidates>
      fine_group_dispositions_{};
  std::array<TierCompletionDisposition, kMaxCandidates>
      tier_completion_dispositions_{};
  std::array<CandidateAdmissionDiagnostics, kMaxCandidates>
      candidate_admission_diagnostics_{};
  bool calibrated_output_diagnostics_enabled_{};
  std::array<CalibratedOutputDiagnostics, kMaxCandidates>
      calibrated_output_diagnostics_{};
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  std::array<ObservedUnisonReacquisitionDisposition, kMaxCandidates>
      spectral_reacquisition_dispositions_{};
  std::array<UnisonCacheRefreshDisposition, kMaxCandidates>
      unison_cache_refresh_dispositions_{};
#endif
  bool assignment_diagnostics_enabled_{};
  bool residual_assignment_diagnostics_enabled_{};
  // Replay diagnostics can exceed the remaining stack space when a caller
  // owns several detectors. Allocate once; configuration and processing reuse it.
  std::unique_ptr<StringAssignmentDiagnostics[]> assignment_diagnostics_{
      new (std::nothrow) StringAssignmentDiagnostics[kMaxCandidates]{}};
  bool fine_group_ownership_diagnostics_enabled_{};
  std::unique_ptr<FineGroupOwnershipDiagnostics[]> fine_group_ownership_diagnostics_{
      new (std::nothrow) FineGroupOwnershipDiagnostics[kMaxCandidates]{}};
  double diagnostic_candidate_rescue_score_ratio_{};
  double diagnostic_input_energy_decay_{};
  double diagnostic_selection_decay_{};
  bool diagnostic_selection_window_only_{};
  bool diagnostic_correlation_shadow_only_{};
  double diagnostic_candidate_rescue_fundamental_ratio_{};
  bool diagnostic_candidate_rescue_enabled_{};
  std::array<std::uint8_t, kMaxCandidates>
      diagnostic_candidate_rescue_string_masks_{};
  bool diagnostic_calibrated_collision_revalidation_{};
  bool diagnostic_polyphonic_posterior_assignment_{};
  bool diagnostic_profile_pair_corroboration_{};
  bool diagnostic_profile_memory_partial_correction_{};
  bool diagnostic_assignment_partial_correction_{};
  bool diagnostic_state_local_open_prior_{};
  bool diagnostic_coasting_harmonic_handoff_{};
  bool diagnostic_calibrated_harmonic_admission_guard_{};
  bool diagnostic_fundamental_admission_{};
  bool diagnostic_direct_evidence_retention_{};
  std::array<std::uint64_t, 2U> diagnostic_odd_partial_cue_mask_{};
  bool diagnostic_cue_free_lane_reassignment_{};
  bool diagnostic_provisional_open_retention_guard_{};
  bool diagnostic_joint_spectral_ownership_{};
  bool diagnostic_joint_midi_owner_guard_{};
  bool diagnostic_residual_pitch_recovery_{};
  bool diagnostic_residual_recovery_continuity_{};
  std::array<std::uint8_t, kMaxCandidates> diagnostic_residual_recovery_owners_{};
  struct ResidualRecoveryLease final {
    std::uint32_t tick{};
    std::uint8_t note{};
    std::uint8_t string{8U};
    bool valid{};
  };
  ResidualRecoveryLease diagnostic_residual_recovery_lease_{};
  ResidualRecoveryStats diagnostic_residual_recovery_stats_{};
  void apply_residual_recovery_for_diagnostics(
      std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet, std::size_t count) noexcept;

  std::array<bool, kMaxCandidates>
      diagnostic_calibrated_harmonic_reassignment_candidates_{};
  // Constructor-owned replay workspace; processing never allocates or grows it.
  std::unique_ptr<M3DpState[]> diagnostic_open_prior_states_{
      new (std::nothrow) M3DpState[3U * (1U << kMaxVoices)]{}};
  bool diagnostic_profile_pair_output_filter_{};
  bool diagnostic_profile_pair_continuity_echo_{};
  double diagnostic_fretted_fixed_penalty_{};
  double diagnostic_fretted_per_fret_penalty_{};
  bool diagnostic_fretted_prior_enabled_{};
  double diagnostic_selector_calibration_margin_{};
  std::uint8_t diagnostic_selector_allowed_string_mask_{0xffU};
  bool diagnostic_selector_calibration_enabled_{};
  std::array<std::uint8_t, kMaxCandidates>
      diagnostic_selector_string_masks_{};
  double diagnostic_selector_minimum_similarity_{};
  double diagnostic_selector_minimum_margin_{};
  bool diagnostic_selector_rescue_enabled_{};
  bool offline_replay_diagnostics_enabled_{true};
  bool fine_frequency_reporting_enabled_{true};
  bool fine_mask_complexity_diagnostics_enabled_{};
  bool diagnostic_fine_mask_pruning_enabled_{};
  bool diagnostic_fine_beat_pruning_enabled_{};
  bool diagnostic_collecting_fine_history_carry_enabled_{};
  bool diagnostic_skip_empty_fine_reset_enabled_{};
#endif

#if defined(M3_TESTING)
  SelectionWork selection_work_{};
#endif
};

}  // namespace m3
