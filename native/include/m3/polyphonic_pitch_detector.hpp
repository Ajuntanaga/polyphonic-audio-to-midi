#pragma once

#include <array>
#include <complex>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/harmonic_evidence.hpp"
#include "m3/partial_detuning_evidence.hpp"
#include "m3/string_fret_posterior.hpp"
#include "m3/string_calibration.hpp"
#include "m3/tuner_telemetry.hpp"
#include "m3/types.hpp"
#include "m3/unison_spectral_classifier.hpp"
#include "m3/unison_spectral_tracker.hpp"

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

// Snapshot of the selector's pre-admission evidence for one pitch. This is
// deliberately replay-only: it lets offline audits distinguish a weak but
// direct fundamental from a harmonic or an unplayable candidate without
// adding state or branches to production plugin builds.
struct CandidateAdmissionDiagnostics final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
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
  [[nodiscard]] std::uint8_t fine_frequency_member_mask(
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
  [[nodiscard]] CandidateAdmissionDiagnostics candidate_admission_diagnostics(
      std::uint8_t midi_note) const noexcept;
  bool set_candidate_admission_rescue_for_diagnostics(
      double score_threshold_ratio,
      double fundamental_score_ratio) noexcept;
  bool set_fretted_position_prior_for_diagnostics(
      double fixed_penalty, double per_fret_penalty) noexcept;
  bool set_decisive_calibrated_selector_for_diagnostics(
      double minimum_margin) noexcept;
  bool set_calibrated_selector_rescue_for_diagnostics(
      double minimum_similarity, double minimum_margin) noexcept;
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  [[nodiscard]] bool observed_spectral_lane_fingerprint(
      std::uint8_t midi_note,
      UnisonSpectralFingerprint& fingerprint) const noexcept;
  [[nodiscard]] std::uint8_t spectral_tier_completion_proposal_mask(
      std::uint8_t midi_note) const noexcept;
  [[nodiscard]] ObservedUnisonReacquisitionDisposition
  spectral_reacquisition_disposition(std::uint8_t midi_note) const noexcept;
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
    std::int16_t retained_cents_q8{};
    std::uint16_t retained_confidence_q15{};
    bool retained_cents_valid{};
    bool polyphonic_context{};
    bool calibrated_lane_committed{};
    std::uint8_t spectral_lane_mask{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    std::uint8_t diagnostic_unison_proposal_mask{};
    bool diagnostic_unison_temporal{};
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
    bool robust_pairwise_beat_connected{};
    bool pending_robust_pairwise_beat_connected{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    std::uint8_t fit_member_mask{};
    double residual_improvement{};
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

  struct SpectralLaneState final {
    UnisonSpectralCorridorTracker tracker{};
    std::uint8_t candidate_index{0xffU};
    bool tracking{};
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
  void append_transition(DetectorDecision& decision, TransitionKind kind,
                         std::uint8_t note, std::uint8_t velocity,
                         std::uint8_t voice_id =
                             kUnassignedVoiceId) noexcept;
  [[nodiscard]] bool append_candidate_note_on(
      DetectorDecision& decision, std::size_t candidate,
      std::uint8_t velocity) noexcept;
  [[nodiscard]] bool append_candidate_note_off(
      DetectorDecision& decision, std::size_t candidate) noexcept;
  void update_calibrated_output_notes(
      DetectorDecision& decision,
      const std::array<bool, kMaxCandidates>& selected,
      std::size_t selected_note_count) noexcept;
  void change_candidate_output_note(DetectorDecision& decision,
                                    std::size_t candidate,
                                    std::uint8_t output_note) noexcept;
  [[nodiscard]] std::uint8_t candidate_output_note(
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
  void update_fine_frequency_evidence(
      const std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      double threshold, bool quiet) noexcept;
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
  [[nodiscard]] SpectralLaneState* find_spectral_lane_state(
      std::size_t candidate) noexcept;
  [[nodiscard]] const SpectralLaneState* find_spectral_lane_state(
      std::size_t candidate) const noexcept;
  [[nodiscard]] SpectralLaneState* acquire_spectral_lane_state(
      std::size_t candidate) noexcept;
  [[nodiscard]] std::uint8_t spectral_lane_assignment(
      std::size_t candidate) const noexcept;
  [[nodiscard]] static std::uint8_t bounded_spectral_lane_assignment(
      bool active, std::uint8_t current_assignment_mask,
      std::uint8_t playable_mask, std::uint8_t other_owned_mask,
      bool polyphonic_context,
      bool fine_frequency_valid, bool fine_frequency_multi_source,
      std::uint8_t fine_frequency_member_mask,
      const UnisonSpectralClassification& classification) noexcept;
  [[nodiscard]] static std::uint8_t projected_output_string_mask(
      std::uint8_t assigned_string_mask, std::uint8_t assigned_string,
      std::uint8_t spectral_lane_mask) noexcept;
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
  [[nodiscard]] double settled_calibration_similarity(
      std::size_t candidate, std::size_t string) const noexcept;
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
  // Boundary-only analysis cells make the configured lowest/highest notes
  // tunable without adding selectable candidates to the pitch set.
  std::array<Cell, kHarmonicCount> lower_cents_guard_cells_{};
  std::array<Cell, kHarmonicCount> upper_cents_guard_cells_{};
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
  std::array<FineFrequencyUniformGramCache, kMaxCandidates>
      fine_frequency_uniform_gram_cache_{};
  StringFretPosteriorBank string_fret_posteriors_{};
  std::array<double, kMaxCandidates> string_fret_energy_memory_{};
  std::array<M3PoolCandidate, kMaxVoices * kMaxVoices> m3_pool_{};
  std::array<M3DpState, 1U << kMaxVoices> m3_dp_states_{};
  // Ephemeral masks chosen by the pitch/string joint selector for this
  // decision. assign_m3_strings uses them to keep a corroborated physical
  // group intact without committing MIDI lanes before the ordinary unison
  // evidence gate runs.
  std::array<std::uint8_t, kMaxCandidates> selector_group_masks_{};
  std::array<SpectralLaneState, kMaxVoices> spectral_lane_states_{};
  double spectral_lane_decimation_sum_{};
  std::uint8_t spectral_lane_decimation_count_{};
  std::uint8_t spectral_lane_decimation_{1U};
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
  QuietDisposition quiet_disposition_{QuietDisposition::not_quiet};
  SignalLossDisposition last_signal_loss_{SignalLossDisposition::none};
  std::array<SelectionDisposition, kMaxCandidates>
      selection_dispositions_{};
  std::array<RetainedUnisonDisposition, kMaxCandidates>
      retained_unison_dispositions_{};
  std::array<FineGroupDisposition, kMaxCandidates>
      fine_group_dispositions_{};
  std::array<CandidateAdmissionDiagnostics, kMaxCandidates>
      candidate_admission_diagnostics_{};
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  std::array<ObservedUnisonReacquisitionDisposition, kMaxCandidates>
      spectral_reacquisition_dispositions_{};
#endif
  double diagnostic_candidate_rescue_score_ratio_{};
  double diagnostic_candidate_rescue_fundamental_ratio_{};
  bool diagnostic_candidate_rescue_enabled_{};
  double diagnostic_fretted_fixed_penalty_{};
  double diagnostic_fretted_per_fret_penalty_{};
  bool diagnostic_fretted_prior_enabled_{};
  double diagnostic_selector_calibration_margin_{};
  bool diagnostic_selector_calibration_enabled_{};
  std::array<std::uint8_t, kMaxCandidates>
      diagnostic_selector_string_masks_{};
  double diagnostic_selector_minimum_similarity_{};
  double diagnostic_selector_minimum_margin_{};
  bool diagnostic_selector_rescue_enabled_{};
  bool offline_replay_diagnostics_enabled_{true};
#endif

#if defined(M3_TESTING)
  SelectionWork selection_work_{};
#endif
};

}  // namespace m3
