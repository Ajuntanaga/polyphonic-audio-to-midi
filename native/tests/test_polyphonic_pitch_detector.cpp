#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdint>
#include <limits>

#include "m3/polyphonic_pitch_detector.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"
#include "m3_signal_fixture.hpp"
#include "test_support.hpp"

namespace m3 {

struct PolyphonicPitchDetectorTestAccess final {
  struct RetainedUnisonSelectionProbe final {
    bool retained{};
    bool first_competitor{};
    bool second_competitor{};
  };

  struct AtomicRetainedGroupsProbe final {
    bool first_pair{};
    bool second_pair{};
    bool competitor{};
    std::uint8_t emitted_lanes{};
  };

  struct MixedCompletedRetainedGroupsProbe final {
    bool completed_triple{};
    bool retained_pair{};
    bool competitor{};
    std::uint8_t completed_mask{};
    std::uint8_t emitted_lanes{};
  };

  struct CommittedGroupCapacityProbe final {
    bool committed_group{};
    std::uint8_t selected_competitors{};
    std::uint8_t emitted_lanes{};
  };

  struct CompletionPriorityProbe final {
    bool weaker{};
    bool stronger{};
  };

  struct BeatProbe final {
    double beat_hz{};
    double hold_seconds{};
    bool valid{};
  };

  struct FineProbe final {
    std::uint8_t members{};
    std::uint8_t pending{};
    std::uint16_t pending_count{};
    std::uint16_t history_count{};
    std::array<double, kMaxVoices> component_energy{};
    double frequency_deviation_hz{};
    bool multi_source_observed{};
    bool valid{};
    bool beat_valid{};
  };


  struct PhaseProbe final {
    double cents{};
    std::uint16_t accepted_updates{};
    std::uint8_t assigned_string{};
    bool valid{};
    bool active{};
  };

  struct NoteOffCapacityProbe final {
    std::size_t transition_count{};
    bool queued{};
    bool candidate_active{};
  };

  struct DpReplacementProbe final {
    bool incumbent_selected{};
    bool target_selected{};
    bool target_is_atomic{};
    std::uint8_t target_string{};
  };

  struct DpOutputProjectionProbe final {
    std::array<TransitionKind, 6U> kinds{};
    std::array<std::uint8_t, 6U> notes{};
    std::array<std::uint8_t, 6U> voices{};
    std::size_t transition_count{};
    std::uint8_t base_note{kTunerNoSignalNote};
    std::uint8_t midi_note{kTunerNoSignalNote};
    std::uint8_t projection_note{kTunerNoSignalNote};
    bool incumbent_selected{};
    bool target_selected{};
    bool incumbent_active{};
    bool release_queued{};
  };

  struct AtomicHandoffCapacityProbe final {
    std::size_t transition_count{};
    bool queued{};
    bool incumbent_active{};
    bool target_active{};
    TransitionKind penultimate_kind{TransitionKind::note_on};
    TransitionKind final_kind{TransitionKind::note_off};
  };

  static FineProbe fine_probe(const PolyphonicPitchDetector& detector,
                              std::size_t candidate) noexcept {
    const auto& fine = detector.fine_frequency_evidence_states_[candidate];
    return {fine.member_mask,
            fine.pending_member_mask,
            fine.pending_count,
            fine.count,
            fine.component_energy,
            fine.frequency_deviation_hz,
            fine.multi_source_observed,
            fine.valid,
            detector.beat_evidence_states_[candidate].valid};
  }

  static bool fine_history_retention_probe(
      bool valid, bool multi_source, std::uint8_t members,
      double minimum_beat_coherence, bool robust_connected,
      bool committed_pending) noexcept {
    PolyphonicPitchDetector::FineFrequencyEvidenceState fine;
    fine.valid = valid;
    fine.multi_source_observed = multi_source;
    fine.member_mask = members;
    fine.minimum_pairwise_beat_coherence = minimum_beat_coherence;
    fine.robust_pairwise_beat_connected = robust_connected;
    if (committed_pending) {
      fine.pending_member_mask = members;
      fine.pending_count = 1U;
    }
    return PolyphonicPitchDetector::retain_fine_frequency_history_across_gap(
        fine, 1U);
  }

  static bool committed_fine_group_match_probe(
      bool active, bool valid, bool multi_source, std::uint8_t fine_mask,
      std::uint8_t assigned_mask) noexcept {
    PolyphonicPitchDetector::FineFrequencyEvidenceState fine;
    fine.valid = valid;
    fine.multi_source_observed = multi_source;
    fine.member_mask = fine_mask;
    return PolyphonicPitchDetector::
        committed_fine_group_matches_assignment(fine, active, assigned_mask);
  }

  static std::uint8_t fine_mask_complexity_output_probe(
      bool active, bool selected, bool direct_fundamental, bool quiet,
      double score_threshold_ratio, std::uint8_t current_output_mask,
      std::uint8_t playable_mask, std::uint8_t other_output_mask,
      std::uint8_t maximum_polyphony,
      const std::array<std::uint8_t, 11U>& masks,
      const std::array<double, 11U>& normalized_residual,
      std::size_t count) noexcept {
    return PolyphonicPitchDetector::bounded_fine_mask_complexity_output(
        active, selected, direct_fundamental, quiet, score_threshold_ratio,
        current_output_mask, playable_mask, other_output_mask,
        maximum_polyphony, masks, normalized_residual, count);
  }

  static std::uint8_t fine_beat_pruning_output_probe(
      std::uint8_t midi_note, bool active, bool selected,
      bool direct_fundamental, bool quiet, double score_threshold_ratio,
      std::uint8_t current_output_mask, std::uint8_t playable_mask,
      std::uint8_t other_output_mask, std::uint8_t maximum_polyphony,
      const std::array<std::uint8_t, 10U>& masks,
      const std::array<double, 10U>& normalized_residual,
      const std::array<double, 10U>& minimum_beat_coherence,
      const std::array<bool, 10U>& beat_graph_connected,
      std::size_t count) noexcept {
    return PolyphonicPitchDetector::bounded_fine_beat_pruning_output(
        midi_note, active, selected, direct_fundamental, quiet,
        score_threshold_ratio, current_output_mask, playable_mask,
        other_output_mask, maximum_polyphony, masks, normalized_residual,
        minimum_beat_coherence, beat_graph_connected, count);
  }

  static std::uint8_t fine_beat_projection_probe(
      PolyphonicPitchDetector& detector, bool quiet) noexcept {
    constexpr std::size_t kCandidate = 0U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    auto& candidate = detector.candidate_states_[kCandidate];
    candidate.active = true;
    candidate.assigned_string = 0U;
    candidate.assigned_string_mask = 0x0fU;
    candidate.midi_voice_mask = 0x0fU;
    auto& fine = detector.fine_frequency_evidence_states_[kCandidate];
    fine.beat_pruning_source_mask = 0x0fU;
    fine.beat_pruned_member_mask = 0x07U;
    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    selected[kCandidate] = true;
    scores[kCandidate] = 1.0;
    fundamentals[kCandidate] = 1.0;
    detector.update_fine_beat_pruning_output_projection(
        selected, scores, fundamentals, 0.1, quiet);
    return candidate.fine_beat_pruning_mask;
  }

  static double fine_consensus_seconds(std::uint8_t current,
                                       std::uint8_t proposed,
                                       std::uint8_t playable) noexcept {
    return PolyphonicPitchDetector::fine_frequency_consensus_seconds(
        current, proposed, playable);
  }

  static FineProbe fine_history_after_selector_miss(
      PolyphonicPitchDetector& detector, std::uint8_t assigned_mask,
      std::uint8_t fine_mask, double score, bool quiet) noexcept {
    constexpr std::size_t kCandidate = 1U;
    detector.profile_mode_ = ProfileMode::m3;
    detector.candidate_count_ = 3U;
    detector.fine_frequency_decimation_decisions_ = 1U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    auto& candidate = detector.candidate_states_[kCandidate];
    candidate.active = true;
    candidate.assigned_string = 0U;
    candidate.assigned_string_mask = assigned_mask;
    auto& fine = detector.fine_frequency_evidence_states_[kCandidate];
    fine.valid = true;
    fine.multi_source_observed = true;
    fine.member_mask = fine_mask;
    fine.count = 1U;
    fine.write_index = 1U;
    fine.real[0U] = 1.0;
    fine.decision_ticks[0U] = 0U;
    fine.last_decision_tick = 0U;
    auto& fundamental = detector.cells_[detector.cell_index(kCandidate, 0U)];
    fundamental.enabled = true;
    fundamental.fast_real = 1.0;
    fundamental.fast_imaginary = 0.0;
    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    scores[kCandidate] = score;
    fundamentals[kCandidate] = score;
    const std::uint32_t final_tick = static_cast<std::uint32_t>(std::ceil(
        0.80 * detector.sample_rate_ /
        static_cast<double>(kDecisionQuantum)));
    for (std::uint32_t tick = 1U; tick <= final_tick; ++tick) {
      detector.decision_counter_ = tick;
      detector.update_fine_frequency_evidence(
          selected, scores, fundamentals, 0.05, quiet);
    }
    return fine_probe(detector, kCandidate);
  }

  static std::uint16_t collecting_fine_history_count_after_selector_gap(
      PolyphonicPitchDetector& detector, bool diagnostic_enabled,
      double score, bool quiet) noexcept {
    constexpr std::size_t kCandidate = 1U;
    detector.profile_mode_ = ProfileMode::m3;
    detector.candidate_count_ = 3U;
    detector.fine_frequency_decimation_decisions_ = 1U;
    detector.diagnostic_collecting_fine_history_carry_enabled_ =
        diagnostic_enabled;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    auto& candidate = detector.candidate_states_[kCandidate];
    candidate.active = true;
    candidate.assigned_string = 0U;
    candidate.assigned_string_mask = 0x01U;
    auto& fine = detector.fine_frequency_evidence_states_[kCandidate];
    fine.count = 1U;
    fine.write_index = 1U;
    fine.real[0U] = 1.0;
    fine.decision_ticks[0U] = 0U;
    fine.last_decision_tick = 0U;
    auto& fundamental = detector.cells_[detector.cell_index(kCandidate, 0U)];
    fundamental.enabled = true;
    fundamental.fast_real = 1.0;
    fundamental.fast_imaginary = 0.0;
    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    scores[kCandidate] = score;
    fundamentals[kCandidate] = score;
    const std::uint32_t final_tick = static_cast<std::uint32_t>(std::ceil(
        0.20 * detector.sample_rate_ /
        static_cast<double>(kDecisionQuantum)));
    for (std::uint32_t tick = 1U; tick <= final_tick; ++tick) {
      detector.decision_counter_ = tick;
      detector.update_fine_frequency_evidence(
          selected, scores, fundamentals, 0.05, quiet);
    }
    return fine.count;
  }

  static QuietDisposition quiet_disposition_probe(
      bool minimum_evidence, bool below_signal_floor, bool had_active_voice,
      bool rapid_mute, bool below_slow_energy_ratio,
      bool multi_voice_evidence,
      SignalLossDisposition last_signal_loss =
          SignalLossDisposition::none) noexcept {
    return PolyphonicPitchDetector::classify_quiet_disposition(
        minimum_evidence, below_signal_floor, had_active_voice, rapid_mute,
        below_slow_energy_ratio, multi_voice_evidence, last_signal_loss);
  }

  static bool minimum_signal_evidence_probe(
      std::uint32_t signal_samples, double sample_rate,
      bool had_active_voice) noexcept {
    return PolyphonicPitchDetector::has_minimum_signal_evidence(
        signal_samples, sample_rate, had_active_voice);
  }


  static bool resolved_unison_resume_candidate_probe(
      bool active, std::uint8_t owned_string_mask, bool fine_valid,
      bool fine_multi_source, bool fine_robust_pairwise_beat_connected,
      double fine_minimum_pairwise_beat_coherence,
      std::uint8_t fine_member_mask) noexcept {
    return PolyphonicPitchDetector::is_resolved_unison_resume_candidate(
        active, owned_string_mask, fine_valid, fine_multi_source,
        fine_robust_pairwise_beat_connected,
        fine_minimum_pairwise_beat_coherence, fine_member_mask);
  }

  static std::array<bool, kMaxCandidates> resume_selection_filter_probe(
      bool active_resume,
      const std::array<bool, kMaxCandidates>& active_candidates,
      std::array<bool, kMaxCandidates> selected,
      std::size_t count) noexcept {
    PolyphonicPitchDetector::filter_resume_selection(
        active_resume, active_candidates, selected, count);
    return selected;
  }

  static std::uint8_t spectral_lane_assignment_probe(
      bool active, std::uint8_t current, std::uint8_t playable,
      std::uint8_t occupied, std::uint8_t projected,
      std::uint8_t projected_members, double error, double margin,
      bool polyphonic_context, bool fine_valid, bool fine_multi_source,
      std::uint8_t fine_member_mask, bool valid = true,
      UnisonSpectralPhase phase = UnisonSpectralPhase::settled,
      bool relaxed_onset_allowed = true) noexcept {
    UnisonSpectralClassification classification;
    classification.valid = valid;
    classification.member_mask = projected;
    classification.member_count = projected_members;
    classification.error = error;
    classification.posterior_margin = margin;
    return PolyphonicPitchDetector::bounded_spectral_lane_assignment(
        active, current, playable, occupied, polyphonic_context, fine_valid,
        fine_multi_source, fine_member_mask, phase, relaxed_onset_allowed,
        classification);
  }

  static std::uint8_t adjacent_spectral_duplicate_suppression_probe(
      bool left_active, bool right_active, std::uint8_t left_note,
      std::uint8_t right_note, std::uint8_t left_output_mask,
      std::uint8_t right_output_mask, bool left_spectral_ready,
      bool right_spectral_ready, double left_error,
      double right_error) noexcept {
    return PolyphonicPitchDetector::
        bounded_adjacent_spectral_duplicate_suppression(
            left_active, right_active, left_note, right_note,
            left_output_mask, right_output_mask, left_spectral_ready,
            right_spectral_ready, left_error, right_error);
  }

  static bool spectral_lane_tracker_survives_quiet(
      PolyphonicPitchDetector& detector) noexcept {
    detector.profile_mode_ = ProfileMode::m3;
    detector.candidate_count_ = 2U;
    detector.candidate_states_[0U].active = true;
    detector.spectral_lane_states_[0U].candidate_index = 0U;
    detector.spectral_lane_states_[0U].tracking = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[0U] = true;
    detector.update_spectral_lane_states(selected, true);
    return detector.spectral_lane_states_[0U].candidate_index != 0xffU ||
           detector.spectral_lane_states_[0U].tracking;
  }

  static std::uint8_t projected_output_string_mask_probe(
      std::uint8_t assigned_mask, std::uint8_t assigned_string,
      std::uint8_t spectral_lane_mask,
      std::uint8_t continuity_lane_mask = 0U) noexcept {
    return PolyphonicPitchDetector::projected_output_string_mask(
        assigned_mask, assigned_string, spectral_lane_mask,
        continuity_lane_mask);
  }

  static std::uint8_t group_continuity_projection_probe(
      std::uint8_t current, std::uint8_t cached,
      const UnisonSpectralClassification& classification,
      UnisonSpectralPhase phase, std::uint8_t fine,
      double beat, std::uint8_t profile, std::uint8_t temporal,
      std::uint8_t tier, std::uint8_t other_owned,
      std::uint8_t playable, std::uint8_t maximum_polyphony,
      bool active, bool selected_or_coasting, bool direct,
      bool quiet, double age) noexcept {
    return PolyphonicPitchDetector::bounded_group_continuity_projection(
        current, cached, classification, phase, fine, beat, profile,
        temporal, tier, other_owned, playable, maximum_polyphony, active,
        selected_or_coasting, direct, quiet, age);
  }

  static std::uint8_t articulated_group_continuity_projection_probe(
      std::uint8_t current, std::uint8_t cached, std::uint8_t pending,
      double pending_seconds, double pending_beat, std::uint8_t tier,
      std::uint8_t other_owned, double score_threshold_ratio, bool quiet,
      double age) noexcept {
    return PolyphonicPitchDetector::
        bounded_three_member_articulated_group_continuity_projection(
            current, cached, pending, pending_seconds, pending_beat,
            tier, other_owned, 0xffU, 5U, score_threshold_ratio, true, true,
            quiet, age);
  }

  static std::uint8_t solo_articulated_group_continuity_projection_probe(
      std::uint8_t current, std::uint8_t cached, std::uint8_t pending,
      double pending_seconds, double pending_beat, std::uint8_t tier,
      std::uint8_t other_owned, std::uint8_t playable,
      double score_threshold_ratio, bool quiet, double age) noexcept {
    return PolyphonicPitchDetector::
        bounded_solo_three_member_articulated_group_continuity_projection(
            current, cached, pending, pending_seconds, pending_beat,
            tier, other_owned, playable, 5U, score_threshold_ratio, true, true,
            quiet, age);
  }

  static std::size_t group_continuity_tracker_count_after_update(
      PolyphonicPitchDetector& detector,
      std::uint8_t assigned_member_mask,
      std::uint8_t second_member_mask = 0U,
      std::uint8_t pending_member_mask = 0U) noexcept {
    detector.candidate_states_[0U].active = true;
    detector.candidate_states_[0U].assigned_string = 0U;
    detector.candidate_states_[0U].assigned_string_mask =
        assigned_member_mask;
    detector.candidate_states_[0U].midi_voice_mask = assigned_member_mask;
    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    selected[0U] = true;
    scores[0U] = 1.0;
    fundamentals[0U] = 0.8;
    detector.fine_frequency_evidence_states_[0U].pending_member_mask =
        pending_member_mask;
    if (second_member_mask != 0U) {
      detector.candidate_states_[1U].active = true;
      detector.candidate_states_[1U].assigned_string = 1U;
      detector.candidate_states_[1U].assigned_string_mask =
          second_member_mask;
      detector.candidate_states_[1U].midi_voice_mask = second_member_mask;
      selected[1U] = true;
      scores[1U] = 0.9;
      fundamentals[1U] = 0.7;
    }
    detector.update_group_continuity_trackers(selected, scores, fundamentals,
                                              0.5, false);
    return static_cast<std::size_t>(std::count_if(
        detector.group_continuity_trackers_.begin(),
        detector.group_continuity_trackers_.end(),
        [](const auto& state) noexcept { return state.tracking; }));
  }


  static double candidate_release_hold_seconds(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t member_mask, double beat_hz, bool quiet) noexcept {
    detector.candidate_states_[candidate].assigned_string_mask = member_mask;
    detector.beat_evidence_states_[candidate].beat_hz = beat_hz;
    detector.beat_evidence_states_[candidate].valid = beat_hz > 0.0;
    return static_cast<double>(
               detector.candidate_release_decisions(candidate, quiet)) *
           static_cast<double>(kDecisionQuantum) / detector.sample_rate_;
  }

  static bool adjacent_coasting_handoff_probe(
      PolyphonicPitchDetector& detector, std::uint8_t coasting_member_mask,
      double adjacent_age_seconds, bool coasting_direct, bool adjacent_direct,
      bool quiet) noexcept {
    constexpr std::size_t kCoasting = 1U;
    constexpr std::size_t kAdjacent = 2U;
    detector.sample_rate_ = 48000.0;
    detector.profile_mode_ = ProfileMode::m3;
    detector.candidate_count_ = 4U;
    detector.candidate_states_ = {};
    auto& coasting = detector.candidate_states_[kCoasting];
    coasting.active = true;
    coasting.assigned_string = 0U;
    coasting.assigned_string_mask = coasting_member_mask;
    coasting.midi_voice_mask = coasting_member_mask;
    auto& adjacent = detector.candidate_states_[kAdjacent];
    adjacent.active = true;
    adjacent.assigned_string = 1U;
    adjacent.assigned_string_mask = 1U << 1U;
    adjacent.midi_voice_mask = 1U << 1U;
    adjacent.age_ticks = static_cast<std::uint16_t>(std::ceil(
        adjacent_age_seconds * detector.sample_rate_ /
        static_cast<double>(kDecisionQuantum)));
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<bool, kMaxCandidates> selected{};
    scores[kCoasting] = 0.75;
    fundamentals[kCoasting] = coasting_direct ? 0.60 : 0.05;
    scores[kAdjacent] = 1.0;
    fundamentals[kAdjacent] = adjacent_direct ? 0.50 : 0.10;
    selected[kAdjacent] = true;
    return detector.should_handoff_adjacent_coasting_candidate(
        kCoasting, scores, fundamentals, selected, 1U, quiet);
  }

  static bool inactive_adjacent_coasting_handoff_probe(
      PolyphonicPitchDetector& detector, bool polyphonic_selection,
      bool decisive_calibration, bool same_lane,
      bool adjacent_direct) noexcept {
    constexpr std::size_t kCoasting = 1U;
    constexpr std::size_t kAdjacent = 2U;
    constexpr std::size_t kCompanion = 3U;
    detector.sample_rate_ = 48000.0;
    detector.profile_mode_ = ProfileMode::m3;
    detector.lowest_note_ = 32U;
    detector.candidate_count_ = 4U;
    detector.candidate_states_ = {};
    detector.playable_string_masks_ = {};
    detector.playable_string_masks_[kAdjacent] = 1U << 0U;
    auto& coasting = detector.candidate_states_[kCoasting];
    coasting.active = true;
    coasting.assigned_string = same_lane ? 0U : 1U;
    coasting.assigned_string_mask = static_cast<std::uint8_t>(
        1U << coasting.assigned_string);
    coasting.midi_voice_mask = coasting.assigned_string_mask;

    StringCalibrationBank bank;
    auto& point = bank.points[0U][2U];
    point.harmonic_profile_q15[0U] = 32767U;
    point.confidence_q15 = 32767U;
    point.observation_count = 128U;
    point.quality = decisive_calibration
                        ? CalibrationPointQuality::measured
                        : CalibrationPointQuality::missing;
    bank.calibrated_string_mask = decisive_calibration ? 1U : 0U;
    detector.set_calibration_bank(bank);
    auto& cell = detector.cells_[detector.cell_index(kAdjacent, 0U)];
    cell.enabled = true;
    cell.fast_real = 1.0;
    cell.fast_imaginary = 0.0;

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<bool, kMaxCandidates> selected{};
    scores[kCoasting] = 0.75;
    fundamentals[kCoasting] = 0.05;
    scores[kAdjacent] = 1.0;
    fundamentals[kAdjacent] = adjacent_direct ? 0.50 : 0.05;
    selected[kAdjacent] = true;
    if (polyphonic_selection) {
      selected[kCompanion] = true;
    }
    return detector.should_handoff_adjacent_coasting_candidate(
        kCoasting, scores, fundamentals, selected,
        polyphonic_selection ? 2U : 1U, false);
  }

  static bool resolved_group_coasting_handoff_probe(
      PolyphonicPitchDetector& detector, std::uint8_t coasting_member_mask,
      std::uint8_t resolved_group_mask, bool group_selected) noexcept {
    constexpr std::size_t kCoasting = 1U;
    constexpr std::size_t kGroup = 2U;
    detector.candidate_count_ = 4U;
    detector.candidate_states_ = {};
    detector.selector_group_masks_ = {};
    auto& coasting = detector.candidate_states_[kCoasting];
    coasting.active = true;
    coasting.assigned_string = 0U;
    coasting.assigned_string_mask = coasting_member_mask;
    coasting.midi_voice_mask = coasting_member_mask;
    detector.candidate_states_[kGroup].active = true;
    detector.selector_group_masks_[kGroup] = resolved_group_mask;
    std::array<bool, kMaxCandidates> selected{};
    selected[kGroup] = group_selected;
    return detector.should_handoff_coasting_candidate_to_resolved_group(
        kCoasting, selected);
  }

  static NoteOffCapacityProbe candidate_note_off_capacity_probe(
      PolyphonicPitchDetector& detector, std::size_t free_slots) noexcept {
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = MidiRouting::per_voice;
    detector.lowest_note_ = 40U;
    detector.candidate_count_ = 1U;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[0U];
    state.active = true;
    state.assigned_string = 0U;
    state.assigned_string_mask = 0x03U;
    state.midi_voice_mask = 0x03U;
    state.emitted_note = 40U;

    DetectorDecision decision;
    const std::size_t occupied =
        decision.transitions.capacity() - free_slots;
    for (std::size_t index = 0U; index < occupied; ++index) {
      static_cast<void>(decision.transitions.push_back(VoiceTransition{
          0U, TransitionKind::note_on, 100U, 100U,
          static_cast<std::uint32_t>(index), kUnassignedVoiceId}));
    }
    const bool queued = detector.append_candidate_note_off(decision, 0U);
    if (queued) {
      state = {};
    }
    return {decision.transitions.size(), queued, state.active};
  }

  static DpReplacementProbe calibrated_dp_replacement_probe(
      PolyphonicPitchDetector& detector, bool lane_allowed,
      bool multi_string_context, bool quiet,
      double target_score = 0.15,
      MidiRouting routing = MidiRouting::per_voice,
      std::uint8_t live_group_kind = 0U,
      bool partial_calibration = false,
      bool tied_calibration = false) noexcept {
    constexpr std::uint8_t kIncumbentNote = 44U;
    constexpr std::uint8_t kTargetNote = 52U;
    constexpr std::uint8_t kString = 2U;
    constexpr double kThreshold = 0.05;
    constexpr std::array<double, kCalibrationHarmonicCount> kProfile{
        1.00, 0.20, 0.08, 0.03, 0.01, 0.00};
    const std::size_t incumbent = kIncumbentNote - detector.lowest_note_;
    const std::size_t target = kTargetNote - detector.lowest_note_;
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = routing;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.selector_dp_evicted_candidates_ = {};
    detector.selector_atomic_handoff_targets_ = {};
    detector.selector_atomic_handoff_target_for_incumbent_ = {};
    detector.dp_replacement_allowed_string_mask_ =
        lane_allowed ? static_cast<std::uint8_t>(1U << kString) : 0x01U;
    detector.playable_string_masks_[target] =
        static_cast<std::uint8_t>(1U << kString);
    if (partial_calibration || tied_calibration) {
      detector.playable_string_masks_[target] = static_cast<std::uint8_t>(
          detector.playable_string_masks_[target] | (1U << (kString + 1U)));
    }
    auto& incumbent_state = detector.candidate_states_[incumbent];
    incumbent_state.active = true;
    incumbent_state.assigned_string = kString;
    incumbent_state.assigned_string_mask =
        static_cast<std::uint8_t>(1U << kString);
    incumbent_state.midi_voice_mask =
        routing == MidiRouting::per_voice
            ? incumbent_state.assigned_string_mask
            : 0U;
    detector.selector_dp_evicted_candidates_[target] = true;

    StringCalibrationBank bank;
    StringCalibrationPoint& point =
        bank.points[kString][kTargetNote - kM3OpenNotes[kString]];
    double total = 0.0;
    for (const double value : kProfile) {
      total += value * value;
    }
    for (std::size_t harmonic = 0U; harmonic < kProfile.size(); ++harmonic) {
      point.harmonic_profile_q15[harmonic] =
          static_cast<std::uint16_t>(std::lround(
              32767.0 * kProfile[harmonic] * kProfile[harmonic] / total));
      auto& cell = detector.cells_[detector.cell_index(target, harmonic)];
      cell.enabled = true;
      cell.fast_real = kProfile[harmonic];
      cell.fast_imaginary = 0.0;
    }
    point.confidence_q15 = 32767U;
    point.observation_count = 128U;
    point.quality = CalibrationPointQuality::measured;
    bank.calibrated_string_mask =
        static_cast<std::uint8_t>(1U << kString);
    if (tied_calibration) {
      StringCalibrationPoint& tied =
          bank.points[kString + 1U]
                     [kTargetNote - kM3OpenNotes[kString + 1U]];
      tied = point;
      bank.calibrated_string_mask = static_cast<std::uint8_t>(
          bank.calibrated_string_mask | (1U << (kString + 1U)));
    }
    detector.set_calibration_bank(bank);
    if (multi_string_context) {
      detector.fine_frequency_evidence_states_[target].member_mask = 0x0cU;
    }
    if (live_group_kind == 1U) {
      incumbent_state.midi_voice_mask = 0x0cU;
    } else if (live_group_kind == 2U) {
      detector.candidate_states_[target].spectral_lane_mask = 0x0cU;
    } else if (live_group_kind == 3U) {
      detector.candidate_states_[target].continuity_lane_mask = 0x0cU;
    }

    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    selected[incumbent] = true;
    scores[incumbent] = 0.10;
    fundamentals[incumbent] = 0.08;
    scores[target] = target_score;
    fundamentals[target] = target_score * 0.90;
    detector.apply_calibrated_dp_replacements(
        selected, scores, fundamentals, kThreshold, quiet,
        static_cast<std::size_t>(detector.candidate_count_));
    return {selected[incumbent], selected[target],
            detector.selector_atomic_handoff_targets_[target],
            detector.candidate_states_[target].assigned_string};
  }

  static DpOutputProjectionProbe calibrated_dp_output_projection_probe(
      PolyphonicPitchDetector& detector, std::uint8_t string,
      bool multi_string_context, bool quiet, bool retract,
      bool change_base_note, bool append_release,
      bool quiet_between_observations = false) noexcept {
    constexpr std::uint8_t kIncumbentNote = 44U;
    constexpr std::uint8_t kTargetNote = 52U;
    constexpr double kThreshold = 0.05;
    constexpr std::array<double, kCalibrationHarmonicCount> kProfile{
        1.00, 0.20, 0.08, 0.03, 0.01, 0.00};
    const std::size_t incumbent = kIncumbentNote - detector.lowest_note_;
    const std::size_t target = kTargetNote - detector.lowest_note_;
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = MidiRouting::per_voice;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.selector_dp_evicted_candidates_ = {};
    detector.playable_string_masks_[target] =
        static_cast<std::uint8_t>(1U << string);
    detector.selector_dp_evicted_candidates_[target] = true;
    auto& incumbent_state = detector.candidate_states_[incumbent];
    incumbent_state.active = true;
    incumbent_state.assigned_string = string;
    incumbent_state.assigned_string_mask =
        static_cast<std::uint8_t>(1U << string);
    incumbent_state.midi_voice_mask = incumbent_state.assigned_string_mask;
    incumbent_state.emitted_note = kIncumbentNote;
    StringCalibrationBank bank;
    StringCalibrationPoint& point =
        bank.points[string][kTargetNote - kM3OpenNotes[string]];
    double total = 0.0;
    for (const double value : kProfile) {
      total += value * value;
    }
    for (std::size_t harmonic = 0U; harmonic < kProfile.size(); ++harmonic) {
      point.harmonic_profile_q15[harmonic] =
          static_cast<std::uint16_t>(std::lround(
              32767.0 * kProfile[harmonic] * kProfile[harmonic] / total));
      auto& cell = detector.cells_[detector.cell_index(target, harmonic)];
      cell.enabled = true;
      cell.fast_real = kProfile[harmonic];
      cell.fast_imaginary = 0.0;
    }
    point.confidence_q15 = 32767U;
    point.observation_count = 128U;
    point.quality = CalibrationPointQuality::measured;
    bank.calibrated_string_mask =
        static_cast<std::uint8_t>(1U << string);
    detector.set_calibration_bank(bank);
    if (multi_string_context) {
      detector.fine_frequency_evidence_states_[target].member_mask = 0x03U;
    }

    std::array<bool, kMaxCandidates> selected{};
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    selected[incumbent] = true;
    scores[incumbent] = 0.10;
    fundamentals[incumbent] = 0.08;
    scores[target] = 0.15;
    fundamentals[target] = 0.135;
    DetectorDecision decision;
    detector.update_calibrated_dp_output_projections(
        decision, selected, scores, fundamentals, kThreshold, quiet,
        static_cast<std::size_t>(detector.candidate_count_));
    if (quiet_between_observations) {
      detector.update_calibrated_dp_output_projections(
          decision, selected, scores, fundamentals, kThreshold, true,
          static_cast<std::size_t>(detector.candidate_count_));
    }
    detector.update_calibrated_dp_output_projections(
        decision, selected, scores, fundamentals, kThreshold, quiet,
        static_cast<std::size_t>(detector.candidate_count_));

    if (change_base_note) {
      detector.change_candidate_output_note(
          decision, incumbent,
          static_cast<std::uint8_t>(kIncumbentNote + 1U));
    }
    if (retract) {
      detector.selector_dp_evicted_candidates_[target] = false;
      scores[target] = 0.0;
      fundamentals[target] = 0.0;
      detector.update_calibrated_dp_output_projections(
          decision, selected, scores, fundamentals, kThreshold, false,
          static_cast<std::size_t>(detector.candidate_count_));
      detector.update_calibrated_dp_output_projections(
          decision, selected, scores, fundamentals, kThreshold, false,
          static_cast<std::size_t>(detector.candidate_count_));
    }
    bool release_queued = false;
    if (append_release) {
      detector.update_calibrated_dp_output_projections(
          decision, selected, scores, fundamentals, kThreshold, true,
          static_cast<std::size_t>(detector.candidate_count_));
      release_queued =
          detector.append_candidate_note_off(decision, incumbent);
    }

    DpOutputProjectionProbe result;
    result.transition_count = decision.transitions.size();
    const std::size_t copied = std::min(result.transition_count,
                                        result.kinds.size());
    for (std::size_t index = 0U; index < copied; ++index) {
      result.kinds[index] = decision.transitions[index].kind;
      result.notes[index] = decision.transitions[index].note;
      result.voices[index] = decision.transitions[index].voice_id;
    }
    result.base_note = detector.candidate_output_note(incumbent);
    result.midi_note = detector.candidate_midi_output_note(incumbent);
    result.projection_note =
        detector.candidate_states_[incumbent].dp_output_projection_note;
    result.incumbent_selected = selected[incumbent];
    result.target_selected = selected[target];
    result.incumbent_active = incumbent_state.active;
    result.release_queued = release_queued;
    return result;
  }

  static AtomicHandoffCapacityProbe atomic_handoff_capacity_probe(
      PolyphonicPitchDetector& detector, MidiRouting routing,
      std::size_t free_slots) noexcept {
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = routing;
    detector.lowest_note_ = 40U;
    detector.candidate_count_ = 2U;
    detector.candidate_states_ = {};
    auto& incumbent = detector.candidate_states_[0U];
    incumbent.active = true;
    incumbent.assigned_string = 2U;
    incumbent.assigned_string_mask = 0x04U;
    incumbent.midi_voice_mask = routing == MidiRouting::per_voice ? 0x04U : 0U;
    incumbent.emitted_note = 40U;
    auto& target = detector.candidate_states_[1U];
    target.assigned_string = 2U;
    target.assigned_string_mask = 0x04U;

    DetectorDecision decision;
    const std::size_t occupied =
        decision.transitions.capacity() - free_slots;
    for (std::size_t index = 0U; index < occupied; ++index) {
      static_cast<void>(decision.transitions.push_back(VoiceTransition{
          0U, TransitionKind::note_on, 100U, 100U,
          static_cast<std::uint32_t>(index), kUnassignedVoiceId}));
    }
    const bool queued = detector.append_atomic_candidate_handoff(
        decision, 0U, 1U, 100U);
    const std::size_t size = decision.transitions.size();
    const TransitionKind penultimate =
        size >= 2U ? decision.transitions[size - 2U].kind
                   : TransitionKind::note_on;
    const TransitionKind final =
        size >= 1U ? decision.transitions[size - 1U].kind
                   : TransitionKind::note_off;
    return {size, queued, detector.candidate_states_[0U].active,
            detector.candidate_states_[1U].active, penultimate, final};
  }

  static PhaseProbe phase_probe(const PolyphonicPitchDetector& detector,
                                std::size_t candidate) noexcept {
    const auto& phase = detector.phase_cents_states_[candidate];
    const auto& state = detector.candidate_states_[candidate];
    return {phase.cents, phase.accepted_updates, state.assigned_string,
            phase.valid, state.active};
  }

  static BeatProbe beat_probe_for_interference(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t source_count) noexcept {
    detector.candidate_states_[candidate].active = true;
    detector.candidate_states_[candidate].assigned_string = 0U;
    detector.cells_[detector.cell_index(candidate, 0U)].enabled = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    const double decisions_per_second =
        detector.sample_rate_ / static_cast<double>(kDecisionQuantum);
    const std::uint32_t decisions =
        static_cast<std::uint32_t>(std::ceil(4.0 * decisions_per_second));
    for (std::uint32_t tick = 0U; tick < decisions; ++tick) {
      const double time = static_cast<double>(tick) / decisions_per_second;
      double real = std::cos(2.0 * 3.14159265358979323846 * -0.8 * time);
      double imaginary =
          std::sin(2.0 * 3.14159265358979323846 * -0.8 * time);
      if (source_count >= 2U) {
        real += 0.82 *
                std::cos(2.0 * 3.14159265358979323846 * 1.2 * time + 0.37);
        imaginary +=
            0.82 *
            std::sin(2.0 * 3.14159265358979323846 * 1.2 * time + 0.37);
      }
      if (source_count >= 3U) {
        real += 0.63 *
                std::cos(2.0 * 3.14159265358979323846 * 2.7 * time - 0.61);
        imaginary +=
            0.63 *
            std::sin(2.0 * 3.14159265358979323846 * 2.7 * time - 0.61);
      }
      auto& fundamental = detector.cells_[detector.cell_index(candidate, 0U)];
      fundamental.fast_real = real;
      fundamental.fast_imaginary = imaginary;
      detector.update_beat_evidence(selected);
    }
    const auto& beat = detector.beat_evidence_states_[candidate];
    return BeatProbe{
        beat.beat_hz,
        static_cast<double>(detector.unison_dropout_decisions(candidate)) /
            decisions_per_second,
        beat.valid};
  }

  static double harmonic_memory_after_note_on(
      PolyphonicPitchDetector& detector, std::size_t candidate) noexcept {
    for (double& energy : detector.harmonic_energy_memory_[candidate]) {
      energy = 1.0;
    }
    DetectorDecision decision;
    static_cast<void>(
        detector.append_candidate_note_on(decision, candidate, 100U));
    double total = 0.0;
    for (const double energy : detector.harmonic_energy_memory_[candidate]) {
      total += energy;
    }
    return total;
  }

  static std::array<double, 2U>
  selector_and_profile_energy_with_partial_detuning(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kCandidate = 0U;
    constexpr std::size_t kPartial = 1U;
    constexpr double kDecisionRate = 100.0;
    constexpr double kTwoPi = 6.28318530717958647692;
    detector.candidate_count_ = 1U;
    detector.correlation_decay = 0.999;
    auto& phase = detector.phase_cents_states_[kCandidate];
    phase.cents = 5.0;
    phase.valid = true;
    auto& cell = detector.cells_[detector.cell_index(kCandidate, kPartial)];
    cell.enabled = true;
    cell.fast_real = 1.0;
    cell.fast_imaginary = 0.0;
    cell.cosine_step = std::cos(0.075);
    cell.sine_step = std::sin(0.075);
    for (std::size_t tick = 0U; tick < 160U; ++tick) {
      PartialDetuningFrame frame{};
      const double time = static_cast<double>(tick) / kDecisionRate;
      for (std::size_t partial = 0U; partial < kPartialDetuningCount;
           ++partial) {
        frame.center_hz[partial] =
            100.0 * static_cast<double>(partial + 1U);
        const double cents = partial == kPartial ? 23.0 : 5.0;
        const double measured_hz =
            frame.center_hz[partial] * std::exp2(cents / 1200.0);
        const double phase_radians =
            kTwoPi * (measured_hz - frame.center_hz[partial]) * time;
        frame.real[partial] = std::cos(phase_radians);
        frame.imaginary[partial] = std::sin(phase_radians);
        frame.energy[partial] = 1.0;
      }
      detector.partial_detuning_trackers_[kCandidate].update(frame,
                                                              kDecisionRate);
    }
    return {detector.corrected_harmonic_energy(kCandidate, kPartial),
            detector.profile_harmonic_energy(kCandidate, kPartial)};
  }

  static std::uint8_t fresh_candidate_unison_mask(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t second) noexcept {
    detector.max_polyphony_ = 2U;
    detector.signal_samples_ = static_cast<std::uint32_t>(detector.sample_rate_);
    auto& state = detector.candidate_states_[candidate];
    state = {};
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    const auto& bank = detector.calibrator_.bank();
    const std::size_t note = detector.lowest_note_ + candidate;
    const auto* primary_point = bank.point(primary, note - kM3OpenNotes[primary]);
    const auto* second_point = bank.point(second, note - kM3OpenNotes[second]);
    if (primary_point == nullptr || second_point == nullptr) {
      return 0U;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      detector.harmonic_energy_memory_[candidate][harmonic] =
          0.5 * static_cast<double>(primary_point->harmonic_profile_q15[harmonic]) +
          0.5 * static_cast<double>(second_point->harmonic_profile_q15[harmonic]);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 8U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    return state.assigned_string_mask;
  }

  // Runs unison inference for an established calibrated unison candidate
  // while another voice is (optionally) coasting through its release hold on
  // `coasting_string`. Returns the unison candidate's string mask and the
  // resulting tuner snapshot.
  static std::uint8_t unison_mask_beside_coasting_voice(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t second, std::size_t coasting,
      std::uint8_t coasting_string, bool coasting_active,
      std::uint8_t max_polyphony, TunerSnapshot* snapshot = nullptr) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = static_cast<std::uint8_t>(1U << primary);
    auto& coast = detector.candidate_states_[coasting];
    coast.active = coasting_active;
    coast.release_ticks =
        static_cast<std::uint16_t>(coasting_active ? 1U : 0U);
    coast.assigned_string = coasting_string;
    coast.assigned_string_mask =
        static_cast<std::uint8_t>(1U << coasting_string);
    coast.midi_voice_mask = static_cast<std::uint8_t>(1U << coasting_string);
    const auto& bank = detector.calibrator_.bank();
    const std::size_t note = detector.lowest_note_ + candidate;
    const auto* primary_point = bank.point(primary, note - kM3OpenNotes[primary]);
    const auto* second_point = bank.point(second, note - kM3OpenNotes[second]);
    if (primary_point == nullptr || second_point == nullptr) {
      return 0U;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      detector.harmonic_energy_memory_[candidate][harmonic] =
          0.5 * static_cast<double>(primary_point->harmonic_profile_q15[harmonic]) +
          0.5 * static_cast<double>(second_point->harmonic_profile_q15[harmonic]);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    if (snapshot != nullptr) {
      std::array<double, kMaxCandidates> scores{};
      scores[candidate] = 1.0;
      DetectorDecision decision;
      detector.write_snapshot(decision, scores, selected, false);
      *snapshot = decision.tuner_snapshot;
    }
    return state.assigned_string_mask;
  }

  static TunerSnapshot snapshot_for_assigned_string_group(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t member_mask,
      std::uint8_t max_polyphony) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = 32U;
    state.assigned_string = primary;
    state.assigned_string_mask = member_mask;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    std::array<double, kMaxCandidates> scores{};
    scores[candidate] = 1.0;
    DetectorDecision decision;
    detector.write_snapshot(decision, scores, selected, false);
    return decision.tuner_snapshot;
  }

  static TunerSnapshot snapshot_for_diagnostic_emitted_string_group(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t assigned_member_mask,
      std::uint8_t emitted_member_mask,
      std::uint8_t max_polyphony) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.diagnostic_fine_mask_pruning_enabled_ = true;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = 32U;
    state.assigned_string = primary;
    state.assigned_string_mask = assigned_member_mask;
    state.midi_voice_mask = emitted_member_mask;
    state.diagnostic_fine_mask_pruning_mask = emitted_member_mask;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    std::array<double, kMaxCandidates> scores{};
    scores[candidate] = 1.0;
    DetectorDecision decision;
    detector.write_snapshot(decision, scores, selected, false);
    return decision.tuner_snapshot;
  }

  static std::uint8_t inferred_group_mask(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t source_members,
      std::uint8_t max_polyphony, TunerSnapshot* snapshot = nullptr,
      bool use_fine_frequency_evidence = true) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = static_cast<std::uint8_t>(1U << primary);
    const auto& bank = detector.calibrator_.bank();
    const std::uint8_t note =
        static_cast<std::uint8_t>(detector.lowest_note_ + candidate);
    std::size_t source_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((source_members & (1U << string)) != 0U) {
        ++source_count;
      }
    }
    if (source_count == 0U) {
      return 0U;
    }
    detector.beat_evidence_states_[candidate] = {};
    if (source_count >= 2U) {
      detector.beat_evidence_states_[candidate].beat_hz = 2.0;
      detector.beat_evidence_states_[candidate].accepted_cycles = 3U;
      detector.beat_evidence_states_[candidate].valid = true;
    }
    if (use_fine_frequency_evidence && source_count >= 3U &&
        source_count <= 4U) {
      detector.fine_frequency_evidence_states_[candidate].member_mask =
          source_members;
      detector.fine_frequency_evidence_states_[candidate].valid = true;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      double energy = 0.0;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if ((source_members & (1U << string)) == 0U ||
            note < kM3OpenNotes[string]) {
          continue;
        }
        const auto* point = bank.point(string, note - kM3OpenNotes[string]);
        if (point == nullptr) {
          return 0U;
        }
        energy += static_cast<double>(point->harmonic_profile_q15[harmonic]);
      }
      detector.harmonic_energy_memory_[candidate][harmonic] =
          energy / static_cast<double>(source_count);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    if (snapshot != nullptr) {
      std::array<double, kMaxCandidates> scores{};
      scores[candidate] = 1.0;
      DetectorDecision decision;
      detector.write_snapshot(decision, scores, selected, false);
      *snapshot = decision.tuner_snapshot;
    }
    return state.assigned_string_mask;
  }

  static FineGroupDisposition fine_group_disposition_beside_owner(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t source_members,
      std::size_t owner_candidate, std::uint8_t owner_string,
      std::uint8_t max_polyphony) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = state.assigned_string_mask;
    auto& owner = detector.candidate_states_[owner_candidate];
    owner.active = true;
    owner.assigned_string = owner_string;
    owner.assigned_string_mask =
        static_cast<std::uint8_t>(1U << owner_string);
    owner.midi_voice_mask = owner.assigned_string_mask;
    auto& fine = detector.fine_frequency_evidence_states_[candidate];
    fine = {};
    fine.member_mask = source_members;
    fine.multi_source_observed = true;
    fine.valid = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    detector.infer_m3_unison_strings(selected);
    return detector.fine_group_disposition(
        static_cast<std::uint8_t>(detector.lowest_note_ + candidate));
  }

  static std::uint8_t profile_only_group_mask(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary,
      const std::array<double, kCalibrationHarmonicCount>& observed,
      std::uint8_t max_polyphony, std::uint16_t observation_updates) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = observation_updates;
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = state.assigned_string_mask;
    detector.beat_evidence_states_[candidate] = {};
    detector.fine_frequency_evidence_states_[candidate] = {};
    detector.harmonic_energy_memory_[candidate] = observed;
    detector.long_harmonic_energy_memory_[candidate] = {};
    detector.harmonic_memory_updates_[candidate] = observation_updates;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    return state.assigned_string_mask;
  }

  static bool calibrated_direct_support_for_profile(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      const std::array<double, kCalibrationHarmonicCount>& profile,
      double score_to_threshold_ratio) noexcept {
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    constexpr double kThreshold = 1.0;
    scores[candidate] = score_to_threshold_ratio * kThreshold;
    fundamentals[candidate] = 0.95 * scores[candidate];
    if (candidate > 0U) {
      fundamentals[candidate - 1U] = 0.25 * fundamentals[candidate];
    }
    if (candidate + 1U < static_cast<std::size_t>(detector.candidate_count_)) {
      fundamentals[candidate + 1U] = 0.20 * fundamentals[candidate];
    }
    for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = std::sqrt(profile[harmonic]);
      cell.fast_imaginary = 0.0;
    }
    return detector.has_calibrated_direct_support(
        scores, fundamentals, candidate,
        static_cast<std::size_t>(detector.candidate_count_), kThreshold);
  }

  static bool decisive_calibrated_shape_for_profile(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      const std::array<double, kCalibrationHarmonicCount>& profile) noexcept {
    for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = std::sqrt(std::max(0.0, profile[harmonic]));
      cell.fast_imaginary = 0.0;
    }
    return detector.has_decisive_calibrated_shape(
        candidate, static_cast<std::size_t>(detector.candidate_count_));
  }

  static bool isolated_shadow_context(
      bool other_eligible, bool other_active,
      bool sole_other_is_harmonic = false) noexcept {
    return PolyphonicPitchDetector::has_isolated_shadow_context(
        other_eligible ? 1U : 0U, other_active ? 1U : 0U,
        sole_other_is_harmonic);
  }

  static bool isolated_third_partial_context(
      std::size_t candidate, std::size_t strongest_other,
      std::uint8_t other_eligible, std::uint8_t other_active,
      bool strongest_other_has_decisive_shape) noexcept {
    return PolyphonicPitchDetector::has_isolated_third_partial_context(
        candidate, strongest_other, other_eligible, other_active,
        strongest_other_has_decisive_shape);
  }

  static bool decisive_calibrated_shape_thresholds(
      std::size_t playable_count, std::size_t measured_count,
      double best_similarity, double second_similarity,
      double minimum_similarity = 0.96,
      double minimum_margin = 0.50) noexcept {
    return PolyphonicPitchDetector::has_decisive_calibrated_shape_thresholds(
        playable_count, measured_count, best_similarity, second_similarity,
        minimum_similarity, minimum_margin);
  }


  static std::array<std::uint8_t, 2U> legato_assignment_sequence(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kReleasingCandidate = 12U;  // E3, string 3 open.
    constexpr std::size_t kReplacementCandidate = 13U;  // F3, fret 1.
    detector.candidate_states_ = {};
    detector.candidate_states_[kReleasingCandidate].active = true;
    detector.candidate_states_[kReleasingCandidate].assigned_string = 3U;
    detector.candidate_states_[kReleasingCandidate].assigned_string_mask =
        static_cast<std::uint8_t>(1U << 3U);

    std::array<bool, kMaxCandidates> selected{};
    selected[kReplacementCandidate] = true;
    detector.assign_m3_strings(selected);
    const std::uint8_t initial =
        detector.candidate_states_[kReplacementCandidate].assigned_string;

    detector.candidate_states_[kReleasingCandidate] = {};
    detector.candidate_states_[kReplacementCandidate].active = true;
    detector.candidate_states_[kReplacementCandidate].age_ticks =
        std::numeric_limits<std::uint16_t>::max();
    detector.candidate_states_[kReplacementCandidate].assigned_string_mask =
        static_cast<std::uint8_t>(1U << initial);
    detector.candidate_states_[kReplacementCandidate].midi_voice_mask =
        static_cast<std::uint8_t>(1U << initial);
    detector.assign_m3_strings(selected);
    return {initial,
            detector.candidate_states_[kReplacementCandidate].assigned_string};
  }

  static std::uint8_t assignment_beside_committed_unison_lane(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kNewCandidate = 52U - 32U;
    constexpr std::size_t kUnisonCandidate = 56U - 32U;
    detector.candidate_states_ = {};
    auto& group = detector.candidate_states_[kUnisonCandidate];
    group.active = true;
    group.assigned_string = 6U;
    group.assigned_string_mask =
        static_cast<std::uint8_t>((1U << 6U) | (1U << 5U));
    group.midi_voice_mask = group.assigned_string_mask;

    std::array<bool, kMaxCandidates> selected{};
    selected[kNewCandidate] = true;
    selected[kUnisonCandidate] = true;
    detector.assign_m3_strings(selected);
    return detector.candidate_states_[kNewCandidate].assigned_string;
  }

  static std::uint8_t assignment_with_single_source_fine_fit(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kCandidate = 56U - 32U;
    constexpr std::uint8_t kStartedString = 6U;
    constexpr std::uint8_t kNearbyTemplateString = 5U;
    detector.candidate_states_ = {};
    auto& voice = detector.candidate_states_[kCandidate];
    voice.active = true;
    voice.age_ticks = std::numeric_limits<std::uint16_t>::max();
    voice.assigned_string = kStartedString;
    voice.assigned_string_mask =
        static_cast<std::uint8_t>(1U << kStartedString);
    voice.midi_voice_mask = voice.assigned_string_mask;
    auto& fine = detector.fine_frequency_evidence_states_[kCandidate];
    fine.valid = true;
    // A transient may make the multi-source hypothesis plausible before the
    // residual test collapses its retained member mask back to one template.
    // That single retained bit is not enough to overrule the started lane.
    fine.multi_source_observed = true;
    fine.member_mask =
        static_cast<std::uint8_t>(1U << kNearbyTemplateString);
    std::array<bool, kMaxCandidates> selected{};
    selected[kCandidate] = true;
    detector.assign_m3_strings(selected);
    return voice.assigned_string;
  }

  static bool selects_direct_high_fret_candidate(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kNote = 75U;
    const std::size_t candidate = kNote - detector.lowest_note_;
    detector.fast_energy_ = 1.0;
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    // Mirrors the physical string-2 fret-15 attack: a clear local
    // fundamental well above the coherence threshold, but only about one
    // quarter of the broadband input energy.
    scores[candidate] = 0.26;
    fundamentals[candidate] = 0.25;
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        static_cast<std::size_t>(detector.candidate_count_));
    return selected[candidate];
  }

  static bool selects_calibrated_high_fret_candidate_below_global_threshold(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kLowerNote = 68U;
    constexpr std::uint8_t kNote = 80U;
    const std::size_t lower = kLowerNote - detector.lowest_note_;
    const std::size_t candidate = kNote - detector.lowest_note_;
    detector.fast_energy_ = 1.0;
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[lower] = 0.10;
    fundamentals[lower] = 0.10;
    scores[candidate] = 0.020;
    fundamentals[candidate] = 0.019;
    auto& fundamental =
        detector.cells_[detector.cell_index(candidate, 0U)];
    fundamental.fast_real = std::sqrt(0.019);
    fundamental.fast_imaginary = 0.0;
    auto& second = detector.cells_[detector.cell_index(candidate, 1U)];
    second.fast_real = std::sqrt(0.001 / 0.72);
    second.fast_imaginary = 0.0;
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        static_cast<std::size_t>(detector.candidate_count_));
    return selected[candidate];
  }

  static bool selects_calibrated_band_rescue_beside_a_stronger_chord_tone(
      PolyphonicPitchDetector& detector, bool decisive_identity) noexcept {
    constexpr std::uint8_t kLowerNote = 40U;
    constexpr std::uint8_t kRescueNote = 72U;
    constexpr std::uint8_t kRescueString = 6U;
    constexpr std::uint8_t kCompetitorString = 7U;
    constexpr std::array<double, kCalibrationHarmonicCount> kRescueProfile{
        1.00, 0.06, 0.02, 0.00, 0.00, 0.00};
    constexpr std::array<double, kCalibrationHarmonicCount> kOtherProfile{
        0.18, 1.00, 0.03, 0.00, 0.00, 0.00};
    const std::size_t lower = kLowerNote - detector.lowest_note_;
    const std::size_t rescue = kRescueNote - detector.lowest_note_;
    detector.fast_energy_ = 1.0;
    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[lower] = 0.10;
    fundamentals[lower] = 0.095;
    scores[rescue] = 0.020;
    fundamentals[rescue] = 0.018;
    fundamentals[rescue - 1U] = 0.001;
    fundamentals[rescue + 1U] = 0.001;

    StringCalibrationBank bank;
    const auto set_profile = [&bank](std::uint8_t string, std::uint8_t note,
                                     const auto& profile) noexcept {
      StringCalibrationPoint& point =
          bank.points[string][note - kM3OpenNotes[string]];
      double total = 0.0;
      for (const double amplitude : profile) {
        total += amplitude * amplitude;
      }
      for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                32767.0 * profile[harmonic] * profile[harmonic] / total));
      }
      point.confidence_q15 = 32767U;
      point.observation_count = 128U;
      point.quality = CalibrationPointQuality::measured;
      bank.calibrated_string_mask = static_cast<std::uint8_t>(
          bank.calibrated_string_mask | (1U << string));
    };
    set_profile(kRescueString, kRescueNote, kRescueProfile);
    set_profile(kCompetitorString, kRescueNote,
                decisive_identity ? kOtherProfile : kRescueProfile);
    detector.set_calibration_bank(bank);
    for (std::size_t harmonic = 0U; harmonic < kRescueProfile.size();
         ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(rescue, harmonic)];
      cell.enabled = true;
      cell.fast_real = kRescueProfile[harmonic];
      cell.fast_imaginary = 0.0;
    }
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        static_cast<std::size_t>(detector.candidate_count_));
    return selected[rescue];
  }

  static RetainedUnisonSelectionProbe retained_unison_selection_probe(
      PolyphonicPitchDetector& detector, std::uint8_t committed_mask,
      std::uint8_t fine_mask, double retained_score,
      double beat_coherence = 1.0,
      bool robust_beat_connected = false,
      bool robust_confirmation_mature = false) noexcept {
    constexpr std::size_t kRetainedCandidate = 0U;
    constexpr std::size_t kFirstCompetitor = 1U;
    constexpr std::size_t kSecondCompetitor = 2U;
    constexpr double kThreshold = 0.05;
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 4U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.playable_string_masks_[kRetainedCandidate] = 0x07U;
    detector.playable_string_masks_[kFirstCompetitor] = 0x08U;
    detector.playable_string_masks_[kSecondCompetitor] = 0x10U;
    auto& state = detector.candidate_states_[kRetainedCandidate];
    state.active = true;
    state.assigned_string = 0U;
    state.assigned_string_mask = committed_mask;
    state.midi_voice_mask = committed_mask;
    state.committed_unison_confirmed_ticks =
        robust_confirmation_mature
            ? std::numeric_limits<std::uint16_t>::max()
            : 0U;
    auto& fine =
        detector.fine_frequency_evidence_states_[kRetainedCandidate];
    fine.valid = true;
    fine.multi_source_observed = true;
    fine.member_mask = fine_mask;
    fine.minimum_pairwise_beat_coherence = beat_coherence;
    fine.robust_pairwise_beat_connected = robust_beat_connected;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((fine_mask & (1U << string)) != 0U) {
        fine.component_energy[string] = 1.0;
      }
    }

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kRetainedCandidate] = retained_score;
    fundamentals[kRetainedCandidate] = retained_score;
    scores[kFirstCompetitor] = 0.10;
    fundamentals[kFirstCompetitor] = 0.10;
    scores[kSecondCompetitor] = 0.09;
    fundamentals[kSecondCompetitor] = 0.09;
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, kThreshold, selected, 3U);
    return {selected[kRetainedCandidate], selected[kFirstCompetitor],
            selected[kSecondCompetitor]};
  }

  static AtomicRetainedGroupsProbe atomic_retained_groups_probe(
      PolyphonicPitchDetector& detector) noexcept {
    // Notes 36, 44, and 48 keep every artificial mask fret-feasible. The two
    // retained pairs are disjoint; the last candidate is a one-lane open note.
    constexpr std::size_t kFirstPair = 4U;
    constexpr std::size_t kSecondPair = 12U;
    constexpr std::size_t kCompetitor = 16U;
    constexpr double kThreshold = 0.05;
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 4U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.playable_string_masks_[kFirstPair] = 0x03U;
    detector.playable_string_masks_[kSecondPair] = 0x0CU;
    detector.playable_string_masks_[kCompetitor] = 0x10U;

    const auto configure_pair = [&](std::size_t candidate,
                                    std::uint8_t mask,
                                    std::uint8_t primary) noexcept {
      auto& state = detector.candidate_states_[candidate];
      state.active = true;
      state.assigned_string = primary;
      state.assigned_string_mask = mask;
      state.midi_voice_mask = mask;
      auto& fine = detector.fine_frequency_evidence_states_[candidate];
      fine.valid = true;
      fine.multi_source_observed = true;
      fine.member_mask = mask;
      fine.minimum_pairwise_beat_coherence = 1.0;
      for (std::size_t string = 0U; string < kMaxVoices; ++string) {
        if ((mask & (1U << string)) != 0U) {
          fine.component_energy[string] = 1.0;
        }
      }
    };
    configure_pair(kFirstPair, 0x03U, 0U);
    configure_pair(kSecondPair, 0x0CU, 2U);

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kFirstPair] = 0.11;
    fundamentals[kFirstPair] = 0.11;
    scores[kSecondPair] = 0.10;
    fundamentals[kSecondPair] = 0.10;
    scores[kCompetitor] = 0.09;
    fundamentals[kCompetitor] = 0.09;

    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, kThreshold, selected, 17U);
    std::uint8_t emitted_lanes = 0U;
    for (std::size_t candidate = 0U; candidate < 17U; ++candidate) {
      if (!selected[candidate]) {
        continue;
      }
      const std::uint8_t mask =
          detector.candidate_states_[candidate].assigned_string_mask != 0U
              ? detector.candidate_states_[candidate].assigned_string_mask
              : detector.playable_string_masks_[candidate];
      for (std::size_t string = 0U; string < kMaxVoices; ++string) {
        emitted_lanes = static_cast<std::uint8_t>(
            emitted_lanes + ((mask & (1U << string)) != 0U ? 1U : 0U));
      }
    }
    return {selected[kFirstPair], selected[kSecondPair],
            selected[kCompetitor], emitted_lanes};
  }

  static CommittedGroupCapacityProbe
  committed_group_capacity_probe(PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kCommitted = 4U;
    constexpr std::array<std::size_t, 3U> kCompetitors{9U, 14U, 19U};
    constexpr std::array<std::uint8_t, 3U> kCompetitorMasks{0x08U, 0x10U,
                                                            0x20U};
    constexpr double kThreshold = 0.05;
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 5U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.playable_string_masks_[kCommitted] = 0x07U;
    auto& committed = detector.candidate_states_[kCommitted];
    committed.active = true;
    committed.assigned_string = 0U;
    committed.assigned_string_mask = 0x07U;
    committed.midi_voice_mask = 0x07U;
    auto& fine = detector.fine_frequency_evidence_states_[kCommitted];
    fine.valid = true;
    fine.multi_source_observed = true;
    fine.member_mask = 0x07U;
    fine.component_energy[0U] = 1.0;
    fine.component_energy[1U] = 0.8;
    fine.component_energy[2U] = 0.7;

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kCommitted] = 0.13;
    fundamentals[kCommitted] = 0.13;
    for (std::size_t index = 0U; index < kCompetitors.size(); ++index) {
      const std::size_t candidate = kCompetitors[index];
      detector.playable_string_masks_[candidate] = kCompetitorMasks[index];
      scores[candidate] = 0.12 - 0.01 * static_cast<double>(index);
      fundamentals[candidate] = scores[candidate];
    }

    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, kThreshold, selected,
        kCompetitors.back() + 1U);
    std::uint8_t selected_competitors = 0U;
    std::uint8_t emitted_lanes = selected[kCommitted] ? 3U : 0U;
    for (const std::size_t candidate : kCompetitors) {
      if (selected[candidate]) {
        ++selected_competitors;
        ++emitted_lanes;
      }
    }
    return {selected[kCommitted], selected_competitors, emitted_lanes};
  }

  static MixedCompletedRetainedGroupsProbe
  mixed_completed_and_retained_groups_probe(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kCompletedNote = 40U;
    constexpr std::size_t kCompleted = kCompletedNote - 32U;
    constexpr std::size_t kRetainedPair = 52U - 32U;
    constexpr std::size_t kCompetitor = 56U - 32U;
    constexpr std::array<std::array<double, kCalibrationHarmonicCount>, 3U>
        kProfiles{{
            {1.00, 0.52, 0.21, 0.08, 0.03, 0.01},
            {0.18, 1.00, 0.31, 0.12, 0.05, 0.02},
            {0.10, 0.24, 1.00, 0.39, 0.14, 0.05},
        }};
    StringCalibrationBank bank;
    for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
      StringCalibrationPoint& point =
          bank.points[string][kCompletedNote - kM3OpenNotes[string]];
      double total = 0.0;
      for (const double value : kProfiles[string]) {
        total += value;
      }
      for (std::size_t harmonic = 0U; harmonic < kProfiles[string].size();
           ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                32767.0 * kProfiles[string][harmonic] / total));
      }
      point.confidence_q15 = 32767U;
      point.observation_count = 128U;
      point.quality = CalibrationPointQuality::measured;
      bank.calibrated_string_mask = static_cast<std::uint8_t>(
          bank.calibrated_string_mask | (1U << string));
    }
    detector.set_calibration_bank(bank);
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 5U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};
    detector.playable_string_masks_[kCompleted] = 0x07U;
    detector.playable_string_masks_[kRetainedPair] = 0x18U;
    detector.playable_string_masks_[kCompetitor] = 0x20U;

    auto& completed = detector.candidate_states_[kCompleted];
    completed.active = true;
    completed.assigned_string = 1U;
    completed.assigned_string_mask = 0x07U;
    completed.midi_voice_mask = 0x07U;
    auto& completed_fine =
        detector.fine_frequency_evidence_states_[kCompleted];
    completed_fine.valid = true;
    completed_fine.multi_source_observed = true;
    completed_fine.member_mask = 0x06U;
    completed_fine.minimum_pairwise_beat_coherence = 0.25;
    completed_fine.added_member_beat_coherence[0U] = 0.25;
    completed_fine.component_energy[1U] = 1.0;
    completed_fine.component_energy[2U] = 0.8;
    for (std::size_t harmonic = 0U; harmonic < kProfiles[0U].size();
         ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(kCompleted, harmonic)];
      cell.fast_real = std::sqrt(kProfiles[0U][harmonic]);
      cell.fast_imaginary = 0.0;
    }

    auto& retained = detector.candidate_states_[kRetainedPair];
    retained.active = true;
    retained.assigned_string = 3U;
    retained.assigned_string_mask = 0x18U;
    retained.midi_voice_mask = 0x18U;
    auto& retained_fine =
        detector.fine_frequency_evidence_states_[kRetainedPair];
    retained_fine.valid = true;
    retained_fine.multi_source_observed = true;
    retained_fine.member_mask = 0x18U;
    retained_fine.minimum_pairwise_beat_coherence = 1.0;
    retained_fine.component_energy[3U] = 1.0;
    retained_fine.component_energy[4U] = 0.8;

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kCompleted] = 0.11;
    fundamentals[kCompleted] = 0.11;
    scores[kRetainedPair] = 0.12;
    fundamentals[kRetainedPair] = 0.12;
    scores[kCompetitor] = 0.10;
    fundamentals[kCompetitor] = 0.10;

    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        kCompetitor + 1U);
    std::uint8_t emitted_lanes = 0U;
    for (std::size_t candidate = 0U; candidate <= kCompetitor; ++candidate) {
      if (!selected[candidate]) {
        continue;
      }
      std::uint8_t mask = detector.selector_group_masks_[candidate];
      if (mask == 0U) {
        mask = detector.candidate_states_[candidate].assigned_string_mask;
      }
      if (mask == 0U) {
        mask = detector.playable_string_masks_[candidate];
      }
      for (std::size_t string = 0U; string < kMaxVoices; ++string) {
        emitted_lanes = static_cast<std::uint8_t>(
            emitted_lanes + ((mask & (1U << string)) != 0U ? 1U : 0U));
      }
    }
    return {selected[kCompleted], selected[kRetainedPair],
            selected[kCompetitor], detector.selector_group_masks_[kCompleted],
            emitted_lanes};
  }

  static std::uint8_t spectral_tier_completion_probe(
      bool active, std::uint8_t current_assignment_mask,
      std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
      const std::array<std::uint8_t, kSpectralTierCount + 1U>& heads,
      const std::array<double, kSpectralTierCount + 1U>& margins,
      const std::array<double, kMaxVoices>& beat_coherence,
      double added_member_ratio = 1.0,
      std::uint8_t added_string = 0U) noexcept {
    PolyphonicPitchDetector::SpectralHeadEvidence spectral;
    spectral.best_string = heads;
    spectral.margin = margins;
    std::array<double, kMaxVoices> component_energy{};
    component_energy.fill(1.0);
    component_energy[added_string] =
        added_member_ratio * added_member_ratio;
    return PolyphonicPitchDetector::bounded_spectral_tier_completion(
        active, current_assignment_mask, fine_frequency_mask, playable_mask,
        spectral, beat_coherence, component_energy);
  }

  static std::uint8_t retained_unison_completion_selector_probe(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kNote = 40U;
    constexpr std::size_t kCandidate = kNote - 32U;
    constexpr std::array<std::array<double, kCalibrationHarmonicCount>, 3U>
        kProfiles{{
            {1.00, 0.52, 0.21, 0.08, 0.03, 0.01},
            {0.18, 1.00, 0.31, 0.12, 0.05, 0.02},
            {0.10, 0.24, 1.00, 0.39, 0.14, 0.05},
        }};
    StringCalibrationBank bank;
    for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
      const std::size_t fret = kNote - kM3OpenNotes[string];
      StringCalibrationPoint& point = bank.points[string][fret];
      double total = 0.0;
      for (const double value : kProfiles[string]) {
        total += value;
      }
      for (std::size_t harmonic = 0U; harmonic < kProfiles[string].size();
           ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                32767.0 * kProfiles[string][harmonic] / total));
      }
      point.confidence_q15 = 32767U;
      point.observation_count = 128U;
      point.quality = CalibrationPointQuality::measured;
      bank.calibrated_string_mask = static_cast<std::uint8_t>(
          bank.calibrated_string_mask | (1U << string));
    }
    detector.set_calibration_bank(bank);
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 4U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_[kCandidate] = 0x07U;
    auto& state = detector.candidate_states_[kCandidate];
    state.active = true;
    state.assigned_string = 1U;
    state.assigned_string_mask = 0x06U;
    state.midi_voice_mask = 0x06U;
    auto& fine = detector.fine_frequency_evidence_states_[kCandidate];
    fine.valid = true;
    fine.multi_source_observed = true;
    fine.member_mask = 0x06U;
    fine.minimum_pairwise_beat_coherence = 0.25;
    fine.added_member_beat_coherence[0U] = 0.25;
    fine.component_energy[0U] = 0.10 * 0.10;
    fine.component_energy[1U] = 1.0;
    fine.component_energy[2U] = 0.8;
    for (std::size_t harmonic = 0U; harmonic < kProfiles[0U].size();
         ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(kCandidate, harmonic)];
      cell.fast_real = std::sqrt(kProfiles[0U][harmonic]);
      cell.fast_imaginary = 0.0;
    }

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kCandidate] = 0.03;
    fundamentals[kCandidate] = 0.03;
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        static_cast<std::size_t>(detector.candidate_count_));
    return selected[kCandidate] ? detector.selector_group_masks_[kCandidate]
                                : 0U;
  }

  static std::uint8_t fresh_fine_pair_completion_inference_probe(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kNote = 40U;
    constexpr std::size_t kCandidate = kNote - 32U;
    (void)retained_unison_completion_selector_probe(detector);
    auto& state = detector.candidate_states_[kCandidate];
    state.active = false;
    state.assigned_string = 1U;
    state.assigned_string_mask = 0x02U;
    state.midi_voice_mask = 0U;
    state.pending_unison_mask = 0U;
    state.unison_evidence_ticks = 0U;
    detector.selector_group_masks_ = {};
    std::array<bool, kMaxCandidates> selected{};
    selected[kCandidate] = true;
    detector.infer_m3_unison_strings(selected);
    return state.assigned_string_mask;
  }

  static CompletionPriorityProbe stronger_completion_priority_probe(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::uint8_t kWeakerNote = 40U;
    constexpr std::uint8_t kStrongerNote = 44U;
    constexpr std::size_t kWeaker = kWeakerNote - 32U;
    constexpr std::size_t kStronger = kStrongerNote - 32U;
    constexpr std::array<std::array<double, kCalibrationHarmonicCount>, 3U>
        kProfiles{{
            {1.00, 0.52, 0.21, 0.08, 0.03, 0.01},
            {0.18, 1.00, 0.31, 0.12, 0.05, 0.02},
            {0.10, 0.24, 1.00, 0.39, 0.14, 0.05},
        }};
    StringCalibrationBank bank;
    for (const std::uint8_t note : {kWeakerNote, kStrongerNote}) {
      for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
        StringCalibrationPoint& point =
            bank.points[string][note - kM3OpenNotes[string]];
        double total = 0.0;
        for (const double value : kProfiles[string]) {
          total += value;
        }
        for (std::size_t harmonic = 0U; harmonic < kProfiles[string].size();
             ++harmonic) {
          point.harmonic_profile_q15[harmonic] =
              static_cast<std::uint16_t>(std::lround(
                  32767.0 * kProfiles[string][harmonic] / total));
        }
        point.confidence_q15 = 32767U;
        point.observation_count = 128U;
        point.quality = CalibrationPointQuality::measured;
        bank.calibrated_string_mask = static_cast<std::uint8_t>(
            bank.calibrated_string_mask | (1U << string));
      }
    }
    detector.set_calibration_bank(bank);
    detector.fast_energy_ = 1.0;
    detector.max_polyphony_ = 3U;
    detector.candidate_states_ = {};
    detector.fine_frequency_evidence_states_ = {};
    detector.playable_string_masks_ = {};

    const auto configure_completion = [&](std::size_t candidate) noexcept {
      detector.playable_string_masks_[candidate] = 0x07U;
      auto& state = detector.candidate_states_[candidate];
      state.active = true;
      state.assigned_string = 1U;
      state.assigned_string_mask = 0x02U;
      state.midi_voice_mask = 0x02U;
      auto& fine = detector.fine_frequency_evidence_states_[candidate];
      fine.valid = true;
      fine.multi_source_observed = true;
      fine.member_mask = 0x06U;
      fine.minimum_pairwise_beat_coherence = 0.25;
      fine.added_member_beat_coherence[0U] = 0.25;
      fine.component_energy[0U] = 0.10 * 0.10;
      fine.component_energy[1U] = 1.0;
      fine.component_energy[2U] = 0.8;
      for (std::size_t harmonic = 0U; harmonic < kProfiles[0U].size();
           ++harmonic) {
        auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
        cell.fast_real = std::sqrt(kProfiles[0U][harmonic]);
        cell.fast_imaginary = 0.0;
      }
    };
    configure_completion(kWeaker);
    configure_completion(kStronger);

    std::array<double, kMaxCandidates> scores{};
    std::array<double, kMaxCandidates> fundamentals{};
    std::array<double, kMaxCandidates> narrow_fundamentals{};
    scores[kWeaker] = 0.026;
    fundamentals[kWeaker] = 0.026;
    scores[kStronger] = 0.049;
    fundamentals[kStronger] = 0.049;
    std::array<bool, kMaxCandidates> selected{};
    detector.select_m3_feasible_candidates(
        scores, fundamentals, narrow_fundamentals, 0.05, selected,
        kStronger + 1U);
    return {selected[kWeaker], selected[kStronger]};
  }

  static std::array<std::uint8_t, 2U>
  inference_beside_committed_unison_group(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kLowerCandidate = 52U - 32U;
    constexpr std::size_t kHigherCandidate = 56U - 32U;
    constexpr std::uint8_t kLowerPrimary = 4U;
    constexpr std::uint8_t kSharedExtra = 5U;
    constexpr std::uint8_t kHigherPrimary = 6U;
    constexpr std::array<double, kCalibrationHarmonicCount> kLowerProfile{
        1.00, 0.14, 0.04, 0.02, 0.01, 0.005};
    constexpr std::array<double, kCalibrationHarmonicCount> kExtraProfile{
        0.25, 0.90, 0.15, 0.06, 0.02, 0.010};
    constexpr std::array<double, kCalibrationHarmonicCount> kHigherProfile{
        0.40, 0.20, 0.82, 0.09, 0.03, 0.015};
    auto set_profile = [](StringCalibrationBank& bank, std::size_t string,
                          std::size_t fret,
                          const auto& amplitudes) noexcept {
      StringCalibrationPoint& point = bank.points[string][fret];
      double total = 0.0;
      for (const double amplitude : amplitudes) {
        total += amplitude * amplitude;
      }
      for (std::size_t harmonic = 0U; harmonic < amplitudes.size();
           ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                32767.0 * amplitudes[harmonic] * amplitudes[harmonic] /
                total));
      }
      point.confidence_q15 = 32767U;
      point.observation_count = 128U;
      point.quality = CalibrationPointQuality::measured;
      bank.calibrated_string_mask = static_cast<std::uint8_t>(
          bank.calibrated_string_mask | (1U << string));
    };
    StringCalibrationBank bank;
    set_profile(bank, kLowerPrimary, 4U, kLowerProfile);
    set_profile(bank, kSharedExtra, 0U, kExtraProfile);
    set_profile(bank, kSharedExtra, 4U, kExtraProfile);
    set_profile(bank, kHigherPrimary, 0U, kHigherProfile);
    detector.set_calibration_bank(bank);
    detector.max_polyphony_ = 4U;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& lower = detector.candidate_states_[kLowerCandidate];
    lower.active = true;
    lower.age_ticks = std::numeric_limits<std::uint16_t>::max();
    lower.assigned_string = kLowerPrimary;
    lower.assigned_string_mask =
        static_cast<std::uint8_t>(1U << kLowerPrimary);
    auto& higher = detector.candidate_states_[kHigherCandidate];
    higher.active = true;
    higher.age_ticks = std::numeric_limits<std::uint16_t>::max();
    higher.assigned_string = kHigherPrimary;
    higher.assigned_string_mask = static_cast<std::uint8_t>(
        (1U << kHigherPrimary) | (1U << kSharedExtra));
    higher.midi_voice_mask = higher.assigned_string_mask;

    const auto& learned = detector.calibrator_.bank();
    const auto* lower_point = learned.point(kLowerPrimary, 4U);
    const auto* extra_point = learned.point(kSharedExtra, 0U);
    for (std::size_t harmonic = 0U;
         harmonic < PolyphonicPitchDetector::kHarmonicCount; ++harmonic) {
      detector.harmonic_energy_memory_[kLowerCandidate][harmonic] =
          0.5 * static_cast<double>(
                    lower_point->harmonic_profile_q15[harmonic]) +
          0.5 * static_cast<double>(
                    extra_point->harmonic_profile_q15[harmonic]);
    }
    detector.beat_evidence_states_[kLowerCandidate].beat_hz = 2.0;
    detector.beat_evidence_states_[kLowerCandidate].accepted_cycles = 3U;
    detector.beat_evidence_states_[kLowerCandidate].valid = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[kLowerCandidate] = true;
    selected[kHigherCandidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    return {lower.assigned_string_mask, higher.assigned_string_mask};
  }

  static std::uint8_t assigned_string_for_profile(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes) noexcept {
    if (note < detector.lowest_note_) {
      return kUnassignedTunerString;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return kUnassignedTunerString;
    }
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = amplitudes[harmonic];
      cell.fast_imaginary = 0.0;
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    detector.assign_m3_strings(selected);
    return detector.candidate_states_[candidate].assigned_string;
  }

  static std::array<std::uint8_t, 3U> string_posterior_sequence(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      const std::array<double, kCalibrationHarmonicCount>& first,
      const std::array<double, kCalibrationHarmonicCount>& second) noexcept {
    std::array<std::uint8_t, 3U> result{kUnassignedTunerString,
                                       kUnassignedTunerString,
                                       kUnassignedTunerString};
    if (note < detector.lowest_note_) {
      return result;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return result;
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    const auto feed = [&detector, candidate, &selected](
                          const auto& profile, bool active,
                          bool settle_profile) noexcept {
      double total = 0.0;
      for (const double amplitude : profile) {
        total += amplitude * amplitude;
      }
      for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
        auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
        cell.enabled = true;
        cell.fast_real = profile[harmonic] / std::sqrt(total);
        cell.fast_imaginary = 0.0;
        if (settle_profile) {
          const double energy = cell.fast_real * cell.fast_real;
          detector.harmonic_energy_memory_[candidate][harmonic] = energy;
          detector.long_harmonic_energy_memory_[candidate][harmonic] = energy;
        }
      }
      detector.candidate_states_[candidate].active = active;
      detector.assign_m3_strings(selected);
      return detector.string_fret_posteriors_.best_string(candidate);
    };
    result[0U] = feed(first, false, true);
    detector.candidate_states_[candidate].assigned_string = result[0U];
    result[1U] = feed(second, true, false);
    result[2U] = feed(second, false, true);
    return result;
  }

  static double settled_calibration_similarity_for_profile(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      std::uint8_t string,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes) noexcept {
    if (note < detector.lowest_note_ || string >= kM3OpenNotes.size()) {
      return 0.0;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return 0.0;
    }
    detector.harmonic_energy_memory_[candidate] = {};
    detector.long_harmonic_energy_memory_[candidate] = {};
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      const double energy = amplitudes[harmonic] * amplitudes[harmonic];
      detector.harmonic_energy_memory_[candidate][harmonic] = energy;
      detector.long_harmonic_energy_memory_[candidate][harmonic] = energy;
    }
    return detector.settled_calibration_similarity(candidate, string);
  }

  static std::uint8_t assigned_string_for_profile_and_cents(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes,
      double cents) noexcept {
    if (note < detector.lowest_note_) {
      return kUnassignedTunerString;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return kUnassignedTunerString;
    }
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = amplitudes[harmonic];
      cell.fast_imaginary = 0.0;
    }
    detector.phase_cents_states_[candidate].cents = cents;
    detector.phase_cents_states_[candidate].valid = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    detector.assign_m3_strings(selected);
    return detector.candidate_states_[candidate].assigned_string;
  }

  static double learned_common_tuning_offset_for_profile_and_cents(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes,
      double cents, std::uint16_t observations) noexcept {
    if (note < detector.lowest_note_) {
      return 0.0;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return 0.0;
    }
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = amplitudes[harmonic];
      cell.fast_imaginary = 0.0;
    }
    detector.phase_cents_states_[candidate].cents = cents;
    detector.phase_cents_states_[candidate].valid = true;
    double best_similarity = -1.0;
    std::size_t best_string = kMaxVoices;
    const std::uint8_t playable = detector.playable_string_mask(candidate);
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((playable & static_cast<std::uint8_t>(1U << string)) == 0U) {
        continue;
      }
      const double similarity =
          detector.calibration_similarity(candidate, string);
      if (similarity > best_similarity) {
        best_similarity = similarity;
        best_string = string;
      }
    }
    if (best_string >= kM3OpenNotes.size()) {
      return 0.0;
    }
    detector.candidate_states_[candidate].active = true;
    detector.candidate_states_[candidate].assigned_string =
        static_cast<std::uint8_t>(best_string);
    detector.candidate_states_[candidate].assigned_string_mask =
        static_cast<std::uint8_t>(1U << best_string);
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint16_t observation = 0U; observation < observations;
         ++observation) {
      detector.update_calibration_tuning_offset(selected);
    }
    return detector.calibration_tuning_offset_cents_;
  }

  static std::uint8_t reassigned_settled_string_for_profile_and_cents(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      std::uint8_t initial_string,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes,
      double cents, bool polyphonic_context = false,
      bool harmonic_overlap = false,
      bool active_harmonic = false) noexcept {
    if (note < detector.lowest_note_ ||
        initial_string >= kM3OpenNotes.size()) {
      return kUnassignedTunerString;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return kUnassignedTunerString;
    }
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = amplitudes[harmonic];
      cell.fast_imaginary = 0.0;
    }
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = initial_string;
    state.assigned_string_mask =
        static_cast<std::uint8_t>(1U << initial_string);
    state.midi_voice_mask = state.assigned_string_mask;
    state.polyphonic_context = polyphonic_context;
    detector.phase_cents_states_[candidate].cents = cents;
    detector.phase_cents_states_[candidate].valid = true;
    if (harmonic_overlap) {
      std::array<bool, kMaxCandidates> overlap{};
      overlap[candidate] = true;
      const std::size_t harmonic = std::min(
          candidate + 19U,
          static_cast<std::size_t>(detector.candidate_count_ - 1U));
      overlap[harmonic] = true;
      detector.candidate_states_[harmonic].active = active_harmonic;
      detector.assign_m3_strings(overlap);
      detector.candidate_states_[harmonic] = {};
      state.assigned_string = initial_string;
      state.assigned_string_mask =
          static_cast<std::uint8_t>(1U << initial_string);
      state.midi_voice_mask = state.assigned_string_mask;
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    detector.assign_m3_strings(selected);
    return state.assigned_string;
  }

  static std::array<TunerVoice, 3U> snapshot_retention_sequence(
      PolyphonicPitchDetector& detector) noexcept {
    detector.candidate_count_ = 3U;
    detector.lowest_note_ = 39U;
    detector.max_polyphony_ = 1U;
    detector.profile_mode_ = ProfileMode::general;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    detector.candidate_states_[1U].active = true;
    detector.phase_cents_states_[1U].cents = 7.5;
    detector.phase_cents_states_[1U].valid = true;

    std::array<double, kMaxCandidates> scores{};
    std::array<bool, kMaxCandidates> selected{};
    selected[1U] = true;
    scores[0U] = 0.60;
    scores[1U] = 1.00;
    scores[2U] = 0.40;
    DetectorDecision valid;
    detector.write_snapshot(valid, scores, selected, false);

    detector.phase_cents_states_[1U].valid = false;
    scores[0U] = 1.00;
    scores[1U] = 0.60;
    scores[2U] = 0.60;
    DetectorDecision invalid;
    detector.write_snapshot(invalid, scores, selected, false);

    selected[1U] = false;
    detector.candidate_states_[1U].release_ticks = 1U;
    DetectorDecision coast;
    detector.write_snapshot(coast, scores, selected, false);
    return {valid.tuner_snapshot.voices[0U],
            invalid.tuner_snapshot.voices[0U],
            coast.tuner_snapshot.voices[0U]};
  }

  static DetectorDecision attempt_reserved_string_activation(
      PolyphonicPitchDetector& detector) noexcept {
    detector.candidate_count_ = 2U;
    detector.lowest_note_ = 32U;
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = MidiRouting::per_voice;
    detector.max_fret_ = 1U;
    detector.refresh_m3_playable_string_masks();

    detector.candidate_states_ = {};
    detector.candidate_states_[0U].active = true;
    detector.candidate_states_[0U].assigned_string = 0U;
    detector.candidate_states_[0U].assigned_string_mask = 1U;
    detector.candidate_states_[0U].midi_voice_mask = 1U;

    std::array<bool, kMaxCandidates> selected{};
    selected[1U] = true;
    detector.assign_m3_strings(selected);

    DetectorDecision decision;
    const bool activated = detector.append_candidate_note_on(
        decision, 1U, 100U);
    if (activated) {
      detector.candidate_states_[1U].active = true;
    }
    static_cast<void>(detector.append_candidate_note_off(decision, 1U));
    return decision;
  }

  static CalibrationSweepStatus observe_requested_high_fret_beside_a_louder_neighbor(
      PolyphonicPitchDetector& detector) noexcept {
    CalibrationObservation observation;
    observation.confidence = 0.95;
    observation.harmonic_energy = {1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125};

    const double open = static_cast<double>(kM3OpenNotes[0U]);
    observation.midi_pitch = open;
    for (std::size_t sample = 0U; sample < 80U; ++sample) {
      static_cast<void>(detector.calibrator_.observe(observation));
    }
    for (std::size_t fret = 1U; fret <= 22U; ++fret) {
      observation.midi_pitch = open + static_cast<double>(fret);
      for (std::size_t sample = 0U; sample < 64U; ++sample) {
        static_cast<void>(detector.calibrator_.observe(observation));
      }
    }

    const CalibrationSweepStatus before = detector.calibrator_.status();
    if (before.phase != CalibrationSweepPhase::ascending ||
        before.requested_fret != 23U) {
      return before;
    }

    const std::size_t first =
        static_cast<std::size_t>(kM3OpenNotes[0U] - detector.lowest_note_);
    const std::size_t neighbor = first + 22U;
    const std::size_t requested = first + 23U;
    detector.fast_energy_ = 1.0;
    std::array<double, kMaxCandidates> scores{};
    scores[neighbor] = 2.0;
    scores[requested] = 1.0;
    detector.phase_cents_states_[requested].cents = 0.0;
    detector.phase_cents_states_[requested].valid = true;
    for (std::size_t harmonic = 0U; harmonic < kCalibrationHarmonicCount;
         ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(requested, harmonic)];
      cell.enabled = true;
      cell.fast_real = 1.0 / static_cast<double>(harmonic + 1U);
      cell.fast_imaginary = 0.0;
    }
    for (std::size_t sample = 0U; sample < 64U; ++sample) {
      detector.observe_calibration(scores, 0.0, 0.0, false);
    }
    return detector.calibrator_.status();
  }

  static DetectorDecision calibrated_output_note_probe(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t string, std::uint8_t member_mask, double cents,
      bool occupy_projected_note, bool append_release) noexcept {
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = string;
    state.assigned_string_mask = member_mask;
    state.midi_voice_mask = member_mask;
    state.emitted_note = static_cast<std::uint8_t>(detector.lowest_note_ +
                                                   candidate);
    detector.phase_cents_states_[candidate].cents = cents;
    detector.phase_cents_states_[candidate].valid =
        cents >= -50.0 && cents <= 50.0;
    detector.phase_cents_states_[candidate].output_projection_valid =
        cents >= -60.0 && cents <= 60.0;

    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    const std::size_t context_candidate = candidate + 4U;
    selected[context_candidate] = true;
    if (occupy_projected_note) {
      auto& collision = detector.candidate_states_[candidate + 1U];
      collision.active = true;
      collision.assigned_string = static_cast<std::uint8_t>(string + 1U);
      collision.assigned_string_mask = static_cast<std::uint8_t>(
          1U << collision.assigned_string);
      collision.midi_voice_mask = collision.assigned_string_mask;
      collision.emitted_note = static_cast<std::uint8_t>(
          detector.lowest_note_ + candidate + 1U);
    }

    DetectorDecision decision;
    detector.update_calibrated_output_notes(decision, selected, 2U);
    detector.update_calibrated_output_notes(decision, selected, 2U);
    std::array<double, kMaxCandidates> scores{};
    scores[candidate] = 1.0;
    detector.fast_energy_ = 1.0;
    detector.write_snapshot(decision, scores, selected, false);
    if (append_release) {
      static_cast<void>(
          detector.append_candidate_note_off(decision, candidate));
    }
    return decision;
  }

  static DetectorDecision calibrated_output_late_collision_probe(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t string, double cents) noexcept {
    DetectorDecision decision = calibrated_output_note_probe(
        detector, candidate, string,
        static_cast<std::uint8_t>(1U << string), cents, false, false);
    const std::size_t collision_candidate = candidate + 1U;
    auto& collision = detector.candidate_states_[collision_candidate];
    collision.active = true;
    collision.age_ticks = std::numeric_limits<std::uint16_t>::max();
    collision.assigned_string = static_cast<std::uint8_t>(string + 1U);
    collision.assigned_string_mask = static_cast<std::uint8_t>(
        1U << collision.assigned_string);
    collision.midi_voice_mask = collision.assigned_string_mask;
    collision.emitted_note = static_cast<std::uint8_t>(
        detector.lowest_note_ + collision_candidate);

    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    selected[collision_candidate] = true;
    selected[candidate + 4U] = true;
    detector.update_calibrated_output_notes(decision, selected, 3U);
    return decision;
  }

  static DetectorDecision calibrated_output_evidence_retraction_probe(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t string, double initial_cents,
      double settled_cents) noexcept {
    DetectorDecision decision = calibrated_output_note_probe(
        detector, candidate, string,
        static_cast<std::uint8_t>(1U << string), initial_cents, false, false);
    detector.phase_cents_states_[candidate].cents = settled_cents;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    selected[candidate + 4U] = true;
    detector.update_calibrated_output_notes(decision, selected, 2U);
    detector.update_calibrated_output_notes(decision, selected, 2U);
    return decision;
  }

};

}  // namespace m3

M3_TEST(native_detector_quiet_diagnostics_identify_the_first_causal_gate) {
  using m3::PolyphonicPitchDetectorTestAccess;
  using m3::QuietDisposition;
  using m3::SignalLossDisposition;
  const auto classify =
      [](bool minimum_evidence, bool below_signal_floor,
         bool had_active_voice, bool rapid_mute, bool below_slow_energy_ratio,
         bool multi_voice_evidence,
         SignalLossDisposition last_signal_loss =
             SignalLossDisposition::none) {
        return PolyphonicPitchDetectorTestAccess::quiet_disposition_probe(
            minimum_evidence, below_signal_floor, had_active_voice, rapid_mute,
            below_slow_energy_ratio, multi_voice_evidence, last_signal_loss);
      };

  M3_EXPECT_EQ(classify(false, true, false, true, true, false),
               QuietDisposition::minimum_evidence_startup);
  M3_EXPECT_EQ(
      classify(false, true, false, true, true, false,
               SignalLossDisposition::signal_floor),
      QuietDisposition::minimum_evidence_after_signal_floor);
  M3_EXPECT_EQ(
      classify(false, false, false, false, true, false,
               SignalLossDisposition::inactive_energy_ratio),
      QuietDisposition::minimum_evidence_after_inactive_energy_ratio);
  M3_EXPECT_EQ(classify(true, true, false, true, true, false),
               QuietDisposition::below_signal_floor);
  M3_EXPECT_EQ(classify(true, false, true, true, true, true),
               QuietDisposition::rapid_mute_ratio);
  M3_EXPECT_EQ(classify(true, false, false, false, true, true),
               QuietDisposition::inactive_energy_ratio);
  M3_EXPECT_EQ(classify(true, false, true, false, false, false),
               QuietDisposition::multi_voice_evidence);
  M3_EXPECT_EQ(classify(true, false, true, false, false, true),
               QuietDisposition::not_quiet);
}

M3_TEST(native_detector_resolved_unison_resumes_without_repaying_startup_gate) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr double kSampleRate = 96000.0;
  constexpr std::uint32_t kStartupSamples = 3840U;
  M3_EXPECT_FALSE(
      Access::minimum_signal_evidence_probe(0U, kSampleRate, true));
  M3_EXPECT_TRUE(
      Access::minimum_signal_evidence_probe(1U, kSampleRate, true));
  M3_EXPECT_FALSE(Access::minimum_signal_evidence_probe(
      kStartupSamples - 1U, kSampleRate, false));
  M3_EXPECT_TRUE(Access::minimum_signal_evidence_probe(
      kStartupSamples, kSampleRate, false));

  M3_EXPECT_TRUE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000111U, true, true, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000111U, false, true, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000111U, true, false, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000111U, true, true, false, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000111U, true, true, true, 0.19, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000011U, true, true, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00001001U, true, true, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000001U, true, true, true, 0.20, 0b00000111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      true, 0b00000001U, true, true, true, 0.20, 0b00000001U));
  // A retained robust three- or four-string fit may re-enter after its MIDI
  // assignment released; the selector still has to find current audio. Pairs
  // remain on the ordinary startup path because they are much more common
  // harmonic ambiguities.
  M3_EXPECT_TRUE(Access::resolved_unison_resume_candidate_probe(
      false, 0U, true, true, true, 0.20, 0b00000111U));
  M3_EXPECT_TRUE(Access::resolved_unison_resume_candidate_probe(
      false, 0U, true, true, true, 0.20, 0b00001111U));
  M3_EXPECT_FALSE(Access::resolved_unison_resume_candidate_probe(
      false, 0U, true, true, true, 0.20, 0b00000011U));

  std::array<bool, m3::kMaxCandidates> active{};
  std::array<bool, m3::kMaxCandidates> selected{};
  active[2U] = true;
  selected[2U] = true;
  selected[4U] = true;
  const auto resumed = Access::resume_selection_filter_probe(
      true, active, selected, 6U);
  M3_EXPECT_TRUE(resumed[2U]);
  M3_EXPECT_FALSE(resumed[4U]);
  const auto ordinary = Access::resume_selection_filter_probe(
      false, active, selected, 6U);
  M3_EXPECT_TRUE(ordinary[2U]);
  M3_EXPECT_TRUE(ordinary[4U]);
}

M3_TEST(native_detector_rebins_a_stable_single_string_output_and_releases_it) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  auto& current = bank.points[0U][8U];
  current.quality = m3::CalibrationPointQuality::measured;
  current.cents_offset_q8 = static_cast<std::int16_t>(-40 * 256);
  auto& upper = bank.points[0U][9U];
  upper.quality = m3::CalibrationPointQuality::measured;
  upper.cents_offset_q8 = static_cast<std::int16_t>(-40 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x01U, 48.0, false, true);
  M3_EXPECT_EQ(decision.transitions.size(), 3U);
  if (decision.transitions.size() == 3U) {
    M3_EXPECT_EQ(decision.transitions[0U].kind,
                 m3::TransitionKind::note_off);
    M3_EXPECT_EQ(decision.transitions[0U].note, 40U);
    M3_EXPECT_EQ(decision.transitions[1U].kind,
                 m3::TransitionKind::note_on);
    M3_EXPECT_EQ(decision.transitions[1U].note, 41U);
    M3_EXPECT_EQ(decision.transitions[2U].kind,
                 m3::TransitionKind::note_off);
    M3_EXPECT_EQ(decision.transitions[2U].note, 41U);
  }
  M3_EXPECT_EQ(decision.tuner_snapshot.voice_count, 1U);
  if (decision.tuner_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].midi_note, 41U);
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].cents_q8,
                 static_cast<std::int16_t>(-52 * 256));
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].detected_midi_note, 40U);
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].detected_cents_q8,
                 static_cast<std::int16_t>(48 * 256));
    M3_EXPECT_TRUE(
        decision.tuner_snapshot.voices[0U].detected_cents_valid);
#endif
  }
}

M3_TEST(native_detector_rebins_a_just_over_boundary_phase_measurement) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-43 * 256);
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-43 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x01U, 57.0, false, false);
  M3_EXPECT_EQ(decision.transitions.size(), 2U);
  M3_EXPECT_EQ(decision.tuner_snapshot.voice_count, 1U);
  if (decision.tuner_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].midi_note, 41U);
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].cents_q8,
                 static_cast<std::int16_t>(-43 * 256));
    M3_EXPECT_TRUE(decision.tuner_snapshot.voices[0U].cents_valid);
  }
}

M3_TEST(native_detector_does_not_project_beyond_the_bounded_phase_shoulder) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-39 * 256);
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-39 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x01U, 61.0, false, false);
  M3_EXPECT_EQ(decision.transitions.size(), 0U);
  M3_EXPECT_EQ(decision.tuner_snapshot.voice_count, 1U);
  if (decision.tuner_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].midi_note, 40U);
    M3_EXPECT_FALSE(decision.tuner_snapshot.voices[0U].cents_valid);
  }
}

M3_TEST(native_detector_requires_the_shoulder_to_land_near_the_measured_fret) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-20 * 256);
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-20 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x01U, 57.0, false, false);
  M3_EXPECT_EQ(decision.transitions.size(), 0U);
  M3_EXPECT_EQ(decision.tuner_snapshot.voice_count, 1U);
  if (decision.tuner_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(decision.tuner_snapshot.voices[0U].midi_note, 40U);
    M3_EXPECT_FALSE(decision.tuner_snapshot.voices[0U].cents_valid);
  }
}

M3_TEST(native_detector_does_not_rebin_unisons_or_collide_with_live_notes) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 0x03U;
  for (std::size_t string = 0U; string < 2U; ++string) {
    const std::size_t fret = 40U - m3::kM3OpenNotes[string];
    bank.points[string][fret].quality =
        m3::CalibrationPointQuality::measured;
    bank.points[string][fret].cents_offset_q8 =
        static_cast<std::int16_t>(-40 * 256);
    bank.points[string][fret + 1U].quality =
        m3::CalibrationPointQuality::measured;
    bank.points[string][fret + 1U].cents_offset_q8 =
        static_cast<std::int16_t>(-40 * 256);
  }
  detector.set_calibration_bank(bank);

  const auto unison =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x03U, 48.0, false, false);
  M3_EXPECT_EQ(unison.transitions.size(), 0U);
  const auto collision =
      m3::PolyphonicPitchDetectorTestAccess::calibrated_output_note_probe(
          detector, 8U, 0U, 0x01U, 48.0, true, false);
  M3_EXPECT_EQ(collision.transitions.size(), 0U);
}

M3_TEST(native_detector_retracts_a_rebin_when_the_real_adjacent_note_arrives) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_output_late_collision_probe(detector, 8U, 0U, 48.0);
  M3_EXPECT_EQ(decision.transitions.size(), 4U);
  if (decision.transitions.size() == 4U) {
    M3_EXPECT_EQ(decision.transitions[0U].note, 40U);
    M3_EXPECT_EQ(decision.transitions[0U].kind,
                 m3::TransitionKind::note_off);
    M3_EXPECT_EQ(decision.transitions[1U].note, 41U);
    M3_EXPECT_EQ(decision.transitions[1U].kind,
                 m3::TransitionKind::note_on);
    M3_EXPECT_EQ(decision.transitions[2U].note, 41U);
    M3_EXPECT_EQ(decision.transitions[2U].kind,
                 m3::TransitionKind::note_off);
    M3_EXPECT_EQ(decision.transitions[3U].note, 40U);
    M3_EXPECT_EQ(decision.transitions[3U].kind,
                 m3::TransitionKind::note_on);
  }
}

M3_TEST(native_detector_retracts_a_rebin_after_stable_in_range_evidence) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  detector.set_calibration_bank(bank);

  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_output_evidence_retraction_probe(
              detector, 8U, 0U, 48.0, -40.0);
  M3_EXPECT_EQ(decision.transitions.size(), 4U);
  if (decision.transitions.size() == 4U) {
    M3_EXPECT_EQ(decision.transitions[2U].note, 41U);
    M3_EXPECT_EQ(decision.transitions[2U].kind,
                 m3::TransitionKind::note_off);
    M3_EXPECT_EQ(decision.transitions[3U].note, 40U);
    M3_EXPECT_EQ(decision.transitions[3U].kind,
                 m3::TransitionKind::note_on);
  }
}

M3_TEST(native_detector_estimates_two_string_beat_period_from_long_envelope) {
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                                96000.0};
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));

    const auto beat =
        m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
            detector, 16U, 2U);
    M3_EXPECT_TRUE(beat.valid);
    M3_EXPECT_NEAR(beat.beat_hz, 2.0, 0.15);
    M3_EXPECT_TRUE(beat.hold_seconds >= 0.70);
  }
}

M3_TEST(native_detector_retains_beat_evidence_for_three_string_interference) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto beat =
      m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
          detector, 16U, 3U);
  M3_EXPECT_TRUE(beat.valid);
  M3_EXPECT_TRUE(beat.beat_hz >= 0.25);
  M3_EXPECT_TRUE(beat.beat_hz <= 12.0);
  M3_EXPECT_TRUE(beat.hold_seconds > 0.45);
}

M3_TEST(native_detector_does_not_invent_beat_evidence_for_one_steady_string) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto beat =
      m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
          detector, 16U, 1U);
  M3_EXPECT_FALSE(beat.valid);
  M3_EXPECT_NEAR(beat.beat_hz, 0.0, 0.0);
  M3_EXPECT_NEAR(beat.hold_seconds, 0.45, 0.002);
}

M3_TEST(native_detector_fine_mask_complexity_only_prunes_bounded_upper_groups) {
  constexpr std::array<std::uint8_t, 11U> kMasks{
      0x0fU, 0x07U, 0x0bU, 0x0dU, 0x0eU, 0x03U,
      0x05U, 0x06U, 0x09U, 0x0aU, 0x0cU};
  constexpr std::array<double, 11U> kResiduals{
      0.10, 0.11, 0.18, 0.19, 0.20, 0.22,
      0.23, 0.24, 0.25, 0.26, 0.27};
  using Access = m3::PolyphonicPitchDetectorTestAccess;

  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x0fU, 0xffU, 0x00U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x07U);
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x03U, 0xffU, 0x00U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x03U);
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, true, 0.80, 0x0fU, 0xffU, 0x00U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.49, 0x0fU, 0xffU, 0x00U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x0fU, 0xffU, 0x02U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x0fU, 0xffU, 0x10U,
                   5U, kMasks, kResiduals, kMasks.size()),
               0x0fU);

  auto tied = kResiduals;
  tied[2U] = tied[1U];
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x0fU, 0xffU, 0x00U,
                   5U, kMasks, tied, kMasks.size()),
               0x0fU);

  auto pair_biased = kResiduals;
  pair_biased[5U] = 0.0;
  M3_EXPECT_EQ(Access::fine_mask_complexity_output_probe(
                   true, true, true, false, 0.80, 0x0fU, 0xffU, 0x00U,
                   5U, kMasks, pair_biased, kMasks.size()),
               0x07U);
}

M3_TEST(native_detector_fine_beat_pruning_only_removes_a_unique_supported_subset) {
  constexpr std::array<std::uint8_t, 10U> kMasks{
      0x07U, 0x0bU, 0x0dU, 0x0eU, 0x03U,
      0x05U, 0x06U, 0x09U, 0x0aU, 0x0cU};
  constexpr std::array<double, 10U> kResiduals{
      0.10, 0.12, 0.18, 0.19, 0.22,
      0.23, 0.24, 0.25, 0.26, 0.27};
  constexpr std::array<double, 10U> kCoherence{
      0.31, 0.29, 0.27, 0.26, 0.25,
      0.24, 0.23, 0.22, 0.21, 0.20};
  constexpr std::array<bool, 10U> kConnected{
      true, true, true, true, true, true, true, true, true, true};
  using Access = m3::PolyphonicPitchDetectorTestAccess;

  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, false, 0.80, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, kResiduals, kCoherence, kConnected,
                   kMasks.size()),
               0x07U);

  auto disconnected = kConnected;
  disconnected[0U] = false;
  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, false, 0.80, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, kResiduals, kCoherence, disconnected,
                   kMasks.size()),
               0x0bU);

  auto tied = kResiduals;
  tied[1U] = tied[0U];
  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, false, 0.80, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, tied, kCoherence, kConnected,
                   kMasks.size()),
               0x0fU);

  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   55U, true, true, true, false, 0.80, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, kResiduals, kCoherence, kConnected,
                   kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, true, 0.80, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, kResiduals, kCoherence, kConnected,
                   kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, false, 0.49, 0x0fU, 0xffU,
                   0x00U, 5U, kMasks, kResiduals, kCoherence, kConnected,
                   kMasks.size()),
               0x0fU);
  M3_EXPECT_EQ(Access::fine_beat_pruning_output_probe(
                   56U, true, true, true, false, 0.80, 0x0fU, 0xffU,
                   0x01U, 5U, kMasks, kResiduals, kCoherence, kConnected,
                   kMasks.size()),
               0x0fU);
}

M3_TEST(native_detector_production_fine_beat_projection_requires_live_signal) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 56U;
  config.highest_note = 56U;
  config.max_polyphony = 5U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_EQ(Access::fine_beat_projection_probe(detector, false), 0x07U);
  M3_EXPECT_EQ(Access::fine_beat_projection_probe(detector, true), 0U);
}

M3_TEST(native_detector_fine_mask_diagnostic_snapshot_matches_emitted_lanes) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 52U;
  config.highest_note = 52U;
  config.max_polyphony = 5U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  const m3::TunerSnapshot snapshot =
      m3::PolyphonicPitchDetectorTestAccess::
          snapshot_for_diagnostic_emitted_string_group(
              detector, 0U, 0U, 0x0fU, 0x07U, 5U);
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  std::uint8_t observed_mask = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    observed_mask = static_cast<std::uint8_t>(
        observed_mask | (1U << snapshot.voices[voice].string_index));
  }
  M3_EXPECT_EQ(observed_mask, 0x07U);
}

M3_TEST(native_detector_collecting_fine_history_only_crosses_nonquiet_gaps) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 34U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(Access::collecting_fine_history_count_after_selector_gap(
                     detector, true, 0.10, false) > 1U);
  M3_EXPECT_EQ(Access::collecting_fine_history_count_after_selector_gap(
                   detector, false, 0.10, false),
               1U);
  M3_EXPECT_EQ(Access::collecting_fine_history_count_after_selector_gap(
                   detector, true, 0.02, false),
               1U);
  M3_EXPECT_EQ(Access::collecting_fine_history_count_after_selector_gap(
                   detector, true, 0.10, true),
               1U);
}

namespace {

void feed_tone(m3::PolyphonicPitchDetector& detector, std::uint8_t note,
               std::uint32_t samples, m3::TickTransitions& transitions,
               std::uint32_t* first_note_on_sample = nullptr) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  const double frequency =
      m3::midi_to_frequency(static_cast<double>(note), 440.0);
  for (std::uint32_t index = 0; index < samples; ++index) {
    const double phase =
        6.28318530717958647692 * frequency * static_cast<double>(index) /
        kSampleRate;
    const m3::DetectorDecision decision =
        detector.process_sample(kAmplitude * std::sin(phase));
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
      if (first_note_on_sample != nullptr &&
          decision.transitions[event].kind == m3::TransitionKind::note_on &&
          decision.transitions[event].note == note &&
          *first_note_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        *first_note_on_sample = index;
      }
    }
  }
}

void feed_silence(m3::PolyphonicPitchDetector& detector,
                  std::uint32_t samples,
                  m3::TickTransitions& transitions) noexcept {
  for (std::uint32_t index = 0; index < samples; ++index) {
    const m3::DetectorDecision decision = detector.process_sample(0.0);
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
    }
  }
}

void feed_calibration_pitch(m3::PolyphonicPitchDetector& detector,
                            double midi_pitch,
                            std::uint32_t samples,
                            double* oscillator_phase = nullptr) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  const double frequency = m3::midi_to_frequency(midi_pitch, 440.0);
  double phase = oscillator_phase != nullptr ? *oscillator_phase : 0.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const m3::DetectorDecision decision =
        detector.process_sample(kAmplitude * std::sin(phase));
    phase = std::fmod(phase + 6.28318530717958647692 * frequency / kSampleRate,
                      6.28318530717958647692);
    static_cast<void>(decision);
  }
  if (oscillator_phase != nullptr) {
    *oscillator_phase = phase;
  }
}

void feed_calibration_frets(m3::PolyphonicPitchDetector& detector,
                            double open_midi_pitch,
                            double& oscillator_phase) noexcept {
  constexpr std::uint32_t kSamplesPerFret = 24000U;
  for (std::size_t fret = 1U; fret < m3::kCalibrationFretCount; ++fret) {
    feed_calibration_pitch(detector, open_midi_pitch + static_cast<double>(fret),
                           kSamplesPerFret, &oscillator_phase);
  }
  for (std::size_t fret = m3::kCalibrationFretCount - 1U; fret-- > 0U;) {
    feed_calibration_pitch(detector, open_midi_pitch + static_cast<double>(fret),
                           kSamplesPerFret, &oscillator_phase);
  }
  // The low open string needs an additional correlation-settling hold after
  // the fret-1 transition; the UI keeps requesting OPEN until this locks.
  feed_calibration_pitch(detector, open_midi_pitch, 24000U,
                         &oscillator_phase);
}

struct DyadLifecycle final {
  std::uint8_t low_note{};
  std::uint8_t high_note{};
  bool low_on{};
  bool high_on{};
  bool low_off{};
  bool high_off{};
  bool unexpected_on{};
  std::uint32_t low_on_sample{std::numeric_limits<std::uint32_t>::max()};
  std::uint32_t high_on_sample{std::numeric_limits<std::uint32_t>::max()};
};

void observe_dyad(const m3::DetectorDecision& decision,
                  DyadLifecycle& lifecycle, std::uint32_t sample) noexcept {
  for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
    const m3::VoiceTransition& transition = decision.transitions[event];
    if (transition.note == lifecycle.low_note) {
      lifecycle.low_on = lifecycle.low_on ||
                         transition.kind == m3::TransitionKind::note_on;
      if (transition.kind == m3::TransitionKind::note_on &&
          lifecycle.low_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        lifecycle.low_on_sample = sample;
      }
      lifecycle.low_off = lifecycle.low_off ||
                          transition.kind == m3::TransitionKind::note_off;
    }
    if (transition.note == lifecycle.high_note) {
      lifecycle.high_on = lifecycle.high_on ||
                          transition.kind == m3::TransitionKind::note_on;
      if (transition.kind == m3::TransitionKind::note_on &&
          lifecycle.high_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        lifecycle.high_on_sample = sample;
      }
      lifecycle.high_off = lifecycle.high_off ||
                           transition.kind == m3::TransitionKind::note_off;
    }
    if (transition.kind == m3::TransitionKind::note_on &&
        transition.note != lifecycle.low_note &&
        transition.note != lifecycle.high_note) {
      lifecycle.unexpected_on = true;
    }
  }
}

void feed_dyad(m3::PolyphonicPitchDetector& detector, std::uint8_t low_note,
               std::uint8_t high_note, double low_amplitude,
               double high_amplitude, std::uint32_t samples,
               DyadLifecycle& lifecycle,
               std::uint64_t starting_sample = 0U) noexcept {
  constexpr double kSampleRate = 48000.0;
  const double low_frequency =
      m3::midi_to_frequency(static_cast<double>(low_note), 440.0);
  const double high_frequency =
      m3::midi_to_frequency(static_cast<double>(high_note), 440.0);
  for (std::uint32_t index = 0; index < samples; ++index) {
    const double time =
        static_cast<double>(starting_sample + index) / kSampleRate;
    const double sample =
        low_amplitude * std::sin(6.28318530717958647692 * low_frequency * time) +
        high_amplitude * std::sin(6.28318530717958647692 * high_frequency * time);
    observe_dyad(detector.process_sample(sample), lifecycle, index);
  }
}

void release_dyad(m3::PolyphonicPitchDetector& detector,
                  std::uint32_t samples, DyadLifecycle& lifecycle) noexcept {
  for (std::uint32_t index = 0; index < samples; ++index) {
    observe_dyad(detector.process_sample(0.0), lifecycle, index);
  }
}

struct ChordLifecycle final {
  std::array<std::uint8_t, m3::kMaxVoices> notes{};
  std::array<bool, m3::kMaxVoices> note_on{};
  std::array<bool, m3::kMaxVoices> note_off{};
  std::array<std::uint32_t, m3::kMaxVoices> first_on_sample{};
  std::size_t voice_count{};
  bool unexpected_on{};
};

void observe_chord(const m3::DetectorDecision& decision,
                   ChordLifecycle& lifecycle,
                   std::uint32_t sample) noexcept;

struct RealisticStringModel final {
  double detune_cents{};
  double amplitude{};
  double initial_phase{};
  double fundamental{};
  double second_harmonic{};
  double third_harmonic{};
  double fourth_harmonic{};
};

// A deterministic eight-string source model. Real strings never begin at the
// same phase, land at exactly zero cents, or share one harmonic envelope. Keep
// those differences in simultaneous-note tests so string assignment is not
// accidentally validated only against phase-aligned laboratory sines.
constexpr std::array<RealisticStringModel, m3::kMaxVoices>
    kRealisticM3Strings{{
        {-3.8, 0.021, 0.07, 1.0, 0.23, 0.10, 0.040},
        {2.6, 0.019, 0.41, 1.0, 0.29, 0.07, 0.055},
        {-1.4, 0.023, 0.89, 1.0, 0.18, 0.13, 0.035},
        {4.1, 0.020, 1.37, 1.0, 0.32, 0.05, 0.060},
        {-2.7, 0.022, 1.93, 1.0, 0.21, 0.11, 0.045},
        {1.8, 0.018, 2.51, 1.0, 0.27, 0.08, 0.030},
        {3.2, 0.021, 3.14, 1.0, 0.16, 0.14, 0.050},
        {-2.2, 0.020, 3.73, 1.0, 0.25, 0.06, 0.040},
    }};

double realistic_string_sample(std::uint8_t note, std::size_t string_index,
                               double time) noexcept {
  constexpr double kTwoPi = 6.28318530717958647692;
  const RealisticStringModel& model = kRealisticM3Strings[string_index];
  const double pitch =
      static_cast<double>(note) + model.detune_cents / 100.0;
  const double frequency = m3::midi_to_frequency(pitch, 440.0);
  const double phase = model.initial_phase + kTwoPi * frequency * time;
  const double string_phase = 0.13 * static_cast<double>(string_index + 1U);
  return model.amplitude *
         (model.fundamental * std::sin(phase) +
          model.second_harmonic * std::sin(2.0 * phase + string_phase) +
          model.third_harmonic * std::sin(3.0 * phase - 0.7 * string_phase) +
          model.fourth_harmonic * std::sin(4.0 * phase + 1.3 * string_phase));
}

void feed_realistic_string_chord(
    m3::PolyphonicPitchDetector& detector,
    const std::array<std::uint8_t, m3::kMaxVoices>& notes,
    std::uint32_t samples, ChordLifecycle* lifecycle = nullptr,
    m3::TunerSnapshot* final_snapshot = nullptr) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t string = 0U; string < notes.size(); ++string) {
      sample += realistic_string_sample(notes[string], string, time);
    }
    const m3::DetectorDecision decision = detector.process_sample(sample);
    if (lifecycle != nullptr) {
      observe_chord(decision, *lifecycle, index);
    }
    if (final_snapshot != nullptr && decision.tuner_snapshot_ready) {
      *final_snapshot = decision.tuner_snapshot;
    }
  }
}

void set_measured_string_profile(
    m3::StringCalibrationBank& bank, std::size_t string, std::size_t fret,
    double cents,
    const std::array<double, m3::kCalibrationHarmonicCount>& amplitudes) noexcept {
  m3::StringCalibrationPoint& point = bank.points[string][fret];
  double total_energy = 0.0;
  for (const double amplitude : amplitudes) {
    total_energy += amplitude * amplitude;
  }
  for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
    point.harmonic_profile_q15[harmonic] =
        static_cast<std::uint16_t>(std::lround(
            32767.0 * amplitudes[harmonic] * amplitudes[harmonic] /
            total_energy));
  }
  point.cents_offset_q8 =
      static_cast<std::int16_t>(std::lround(cents * 256.0));
  point.confidence_q15 = 32767U;
  point.observation_count = 128U;
  point.quality = m3::CalibrationPointQuality::measured;
  bank.calibrated_string_mask = static_cast<std::uint8_t>(
      bank.calibrated_string_mask | (1U << string));
}

void observe_chord(const m3::DetectorDecision& decision,
                   ChordLifecycle& lifecycle,
                   std::uint32_t sample) noexcept {
  for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
    const m3::VoiceTransition& transition = decision.transitions[event];
    bool known_note = false;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      if (transition.note != lifecycle.notes[voice]) {
        continue;
      }
      known_note = true;
      if (transition.kind == m3::TransitionKind::note_on) {
        lifecycle.note_on[voice] = true;
        if (lifecycle.first_on_sample[voice] ==
            std::numeric_limits<std::uint32_t>::max()) {
          lifecycle.first_on_sample[voice] = sample;
        }
      } else {
        lifecycle.note_off[voice] = true;
      }
      break;
    }
    if (!known_note && transition.kind == m3::TransitionKind::note_on) {
      lifecycle.unexpected_on = true;
    }
  }
}

void feed_chord(m3::PolyphonicPitchDetector& detector,
                double amplitude, std::uint32_t samples,
                ChordLifecycle& lifecycle) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(lifecycle.notes[voice]), 440.0);
      sample += amplitude * std::sin(6.28318530717958647692 * frequency * time);
    }
    observe_chord(detector.process_sample(sample), lifecycle, index);
  }
}

void feed_weighted_chord(
    m3::PolyphonicPitchDetector& detector,
    const std::array<double, m3::kMaxVoices>& amplitudes,
    std::uint32_t samples, ChordLifecycle& lifecycle) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(lifecycle.notes[voice]), 440.0);
      sample += amplitudes[voice] *
                std::sin(6.28318530717958647692 * frequency * time);
    }
    observe_chord(detector.process_sample(sample), lifecycle, index);
  }
}

void release_chord(m3::PolyphonicPitchDetector& detector,
                   std::uint32_t samples, ChordLifecycle& lifecycle) noexcept {
  for (std::uint32_t index = 0U; index < samples; ++index) {
    observe_chord(detector.process_sample(0.0), lifecycle, index);
  }
}

struct AudioUnisonMetrics final {
  std::uint32_t evaluation_frames{};
  std::uint32_t correct_frames{};
  std::uint32_t stable_event_churn{};
  std::uint8_t final_member_mask{};
  std::uint32_t last_incorrect_sample{};
  std::uint32_t last_transition_sample{};
  std::uint16_t maximum_beat_hz_q8{};
  bool shared_pitch_fields{true};
  m3::PolyphonicPitchDetectorTestAccess::FineProbe fine{};
};

AudioUnisonMetrics run_plucked_unison_case(std::uint8_t note,
                                           std::size_t member_count) noexcept {
  constexpr double kSampleRate = 48000.0;
  // The closest modeled pair is two cents apart. At these pitches that is a
  // roughly three-second beat cycle, so the acceptance window deliberately
  // begins after one causal beat-time observation rather than pretending a
  // static spectrum can identify every lane instantly.
  constexpr double kDurationSeconds = 5.5;
  // The slowest two-cent pair takes roughly one 3.3-second beat cycle, then
  // the staggered background fit needs a bounded consensus interval. Judge
  // stability after four seconds rather than inside that causal observation.
  constexpr double kEvaluationStartSeconds = 4.0;
  const std::uint8_t members =
      m3::test_signal::playable_member_mask(note, member_count);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = static_cast<std::uint8_t>(note - 1U);
  config.highest_note = static_cast<std::uint8_t>(note + 1U);
  config.max_polyphony = static_cast<std::uint8_t>(member_count);
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  detector.set_calibration_bank(
      m3::test_signal::calibration_bank_for_note(note));

  AudioUnisonMetrics metrics;
  const std::uint32_t sample_count = static_cast<std::uint32_t>(
      std::lround(kDurationSeconds * kSampleRate));
  const std::uint32_t evaluation_start = static_cast<std::uint32_t>(
      std::lround(kEvaluationStartSeconds * kSampleRate));
  for (std::uint32_t sample = 0U; sample < sample_count; ++sample) {
    const m3::DetectorDecision decision = detector.process_sample(
        m3::test_signal::unison_sample(note, members, sample, kSampleRate));
    if (sample >= evaluation_start) {
      metrics.stable_event_churn +=
          static_cast<std::uint32_t>(decision.transitions.size());
      if (decision.transitions.size() != 0U) {
        metrics.last_transition_sample = sample;
      }
    }
    if (!decision.tuner_snapshot_ready || sample < evaluation_start) {
      continue;
    }
    ++metrics.evaluation_frames;
    const m3::TunerSnapshot& snapshot = decision.tuner_snapshot;
    std::uint8_t observed_members = 0U;
    bool correct = snapshot.voice_count == member_count;
    const m3::TunerVoice* shared =
        snapshot.voice_count == 0U ? nullptr : &snapshot.voices[0U];
    for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = snapshot.voices[voice];
      correct = correct && observed.midi_note == note &&
                observed.string_index < m3::kMaxVoices &&
                observed.pitch_evidence_member_mask == members;
      if (observed.string_index < m3::kMaxVoices) {
        observed_members = static_cast<std::uint8_t>(
            observed_members | (1U << observed.string_index));
      }
      metrics.maximum_beat_hz_q8 =
          std::max(metrics.maximum_beat_hz_q8, observed.beat_hz_q8);
      if (shared != nullptr) {
        metrics.shared_pitch_fields =
            metrics.shared_pitch_fields &&
            observed.cents_q8 == shared->cents_q8 &&
            observed.cents_valid == shared->cents_valid &&
            observed.confidence_q15 == shared->confidence_q15 &&
            observed.beat_hz_q8 == shared->beat_hz_q8;
      }
    }
    correct = correct && observed_members == members;
    metrics.correct_frames += correct ? 1U : 0U;
    if (!correct) {
      metrics.last_incorrect_sample = sample;
    }
    metrics.final_member_mask = observed_members;
  }
  metrics.fine = m3::PolyphonicPitchDetectorTestAccess::fine_probe(
      detector, 1U);
  return metrics;
}

struct SingleStringMetrics final {
  std::uint8_t maximum_voices{};
  std::uint8_t final_string{m3::kUnassignedTunerString};
  std::uint32_t tracked_frames{};
  m3::PolyphonicPitchDetectorTestAccess::FineProbe fine{};
};

SingleStringMetrics run_single_plucked_string_case(std::size_t string,
                                                    std::uint8_t fret,
                                                    double level) noexcept {
  constexpr double kSampleRate = 48000.0;
  const std::uint8_t note =
      static_cast<std::uint8_t>(m3::kM3OpenNotes[string] + fret);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = static_cast<std::uint8_t>(note - 1U);
  config.highest_note = static_cast<std::uint8_t>(note + 1U);
  config.max_polyphony = 7U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  detector.set_calibration_bank(
      m3::test_signal::calibration_bank_for_note(note));

  SingleStringMetrics metrics;
  constexpr std::uint32_t kSamples = 240000U;
  constexpr std::uint32_t kEvaluationStart = 168000U;
  for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
    const m3::DetectorDecision decision = detector.process_sample(
        m3::test_signal::plucked_string_sample(
            string, note, sample, kSampleRate, level));
    if (!decision.tuner_snapshot_ready) {
      continue;
    }
    metrics.maximum_voices = std::max(
        metrics.maximum_voices, decision.tuner_snapshot.voice_count);
    if (sample < kEvaluationStart) {
      continue;
    }
    if (decision.tuner_snapshot.voice_count == 1U) {
      ++metrics.tracked_frames;
      metrics.final_string =
          decision.tuner_snapshot.voices[0U].string_index;
    }
  }
  metrics.fine = m3::PolyphonicPitchDetectorTestAccess::fine_probe(
      detector, 1U);
  return metrics;
}

}  // namespace

M3_TEST(native_detector_tracks_audio_derived_two_through_four_string_unisons) {
  constexpr std::array<std::uint8_t, 2U> kSharedPitchNotes{56U, 60U};
  for (const std::uint8_t note : kSharedPitchNotes) {
    for (std::size_t members = 2U; members <= 4U; ++members) {
      const AudioUnisonMetrics metrics =
          run_plucked_unison_case(note, members);
      if (metrics.correct_frames * 10U < metrics.evaluation_frames * 9U ||
          metrics.stable_event_churn != 0U) {
        std::fprintf(stderr,
                     "unison note=%u members=%zu frames=%u correct=%u churn=%u mask=%u expected=%u last_bad=%.3f last_event=%.3f fine=%u pending=%u/%u dev=%.4f multi=%d beat=%d\n",
                     note, members, metrics.evaluation_frames,
                     metrics.correct_frames, metrics.stable_event_churn,
                     metrics.final_member_mask,
                     m3::test_signal::playable_member_mask(note, members),
                     static_cast<double>(metrics.last_incorrect_sample) /
                         48000.0,
                     static_cast<double>(metrics.last_transition_sample) /
                     48000.0, metrics.fine.members,
                     metrics.fine.pending, metrics.fine.pending_count,
                     metrics.fine.frequency_deviation_hz,
                     metrics.fine.multi_source_observed ? 1 : 0,
                     metrics.fine.beat_valid ? 1 : 0);
        std::fprintf(stderr,
                     " unison energies=%.4g,%.4g,%.4g,%.4g,%.4g,%.4g,%.4g,%.4g\n",
                     metrics.fine.component_energy[0U],
                     metrics.fine.component_energy[1U],
                     metrics.fine.component_energy[2U],
                     metrics.fine.component_energy[3U],
                     metrics.fine.component_energy[4U],
                     metrics.fine.component_energy[5U],
                     metrics.fine.component_energy[6U],
                     metrics.fine.component_energy[7U]);
      }
      M3_EXPECT_TRUE(metrics.evaluation_frames > 0U);
      M3_EXPECT_TRUE(metrics.correct_frames * 10U >=
                     metrics.evaluation_frames * 9U);
      M3_EXPECT_EQ(metrics.stable_event_churn, 0U);
      M3_EXPECT_TRUE(metrics.shared_pitch_fields);
      M3_EXPECT_EQ(metrics.final_member_mask,
                   m3::test_signal::playable_member_mask(note, members));
      if (note == 60U) {
        M3_EXPECT_TRUE(metrics.maximum_beat_hz_q8 > 0U);
      }
    }
  }
}

M3_TEST(native_detector_waits_three_seconds_before_resolving_a_close_unison) {
  constexpr std::uint8_t kNote = 60U;
  constexpr std::size_t kMemberCount = 4U;
  constexpr std::array<double, 4U> kSampleRates{
      44100.0, 48000.0, 88200.0, 96000.0};
  const std::uint8_t members =
      m3::test_signal::playable_member_mask(kNote, kMemberCount);
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = kNote - 1U;
    config.highest_note = kNote + 1U;
    config.max_polyphony = kMemberCount;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    detector.set_calibration_bank(
        m3::test_signal::calibration_bank_for_note(kNote));

    const auto early_samples = static_cast<std::uint32_t>(
        std::lround(2.75 * sample_rate));
    for (std::uint32_t sample = 0U; sample < early_samples; ++sample) {
      static_cast<void>(detector.process_sample(
          m3::test_signal::unison_sample(
              kNote, members, sample, sample_rate)));
    }
    const auto early =
        m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
    M3_EXPECT_FALSE(early.valid);

    const auto late_samples = static_cast<std::uint32_t>(
        std::lround(5.5 * sample_rate));
    for (std::uint32_t sample = early_samples; sample < late_samples;
         ++sample) {
      static_cast<void>(detector.process_sample(
          m3::test_signal::unison_sample(
              kNote, members, sample, sample_rate)));
    }
    const auto late =
        m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
    M3_EXPECT_TRUE(late.valid);
    M3_EXPECT_EQ(late.members, members);
  }
}

M3_TEST(native_detector_retains_unison_evidence_across_one_short_articulation_gap) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::size_t kMemberCount = 3U;
  const std::uint8_t members =
      m3::test_signal::playable_member_mask(kNote, kMemberCount);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = kNote - 1U;
  config.highest_note = kNote + 1U;
  config.max_polyphony = kMemberCount;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  detector.set_calibration_bank(
      m3::test_signal::calibration_bank_for_note(kNote));

  constexpr std::uint32_t kEvidenceSamples = 264000U;
  for (std::uint32_t sample = 0U; sample < kEvidenceSamples; ++sample) {
    static_cast<void>(detector.process_sample(
        m3::test_signal::unison_sample(
            kNote, members, sample, kSampleRate)));
  }
  constexpr std::uint32_t kFreshArticulationSamples = 4800U;
  for (std::uint32_t sample = 0U; sample < kFreshArticulationSamples;
       ++sample) {
    static_cast<void>(detector.process_sample(
        m3::test_signal::unison_sample(
            kNote, members, sample, kSampleRate)));
  }
  const auto before_gap =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_TRUE(before_gap.valid);

  constexpr std::uint32_t kShortGapSamples = 4800U;
  for (std::uint32_t sample = 0U; sample < kShortGapSamples; ++sample) {
    static_cast<void>(detector.process_sample(0.0));
  }
  const auto after_short =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_TRUE(after_short.valid);

  constexpr std::uint32_t kMediumGapSamples = 21600U;
  for (std::uint32_t sample = 0U; sample < kMediumGapSamples; ++sample) {
    static_cast<void>(detector.process_sample(0.0));
  }
  const auto after_medium =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_TRUE(after_medium.valid);

  constexpr std::uint32_t kLongGapSamples = 7200U;
  for (std::uint32_t sample = 0U; sample < kLongGapSamples; ++sample) {
    static_cast<void>(detector.process_sample(0.0));
  }
  const auto after_long =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_FALSE(after_long.valid);
}

M3_TEST(native_detector_clears_collecting_unison_evidence_at_articulation_silence) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::size_t kMemberCount = 3U;
  const std::uint8_t members =
      m3::test_signal::playable_member_mask(kNote, kMemberCount);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = kNote - 1U;
  config.highest_note = kNote + 1U;
  config.max_polyphony = kMemberCount;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  detector.set_calibration_bank(
      m3::test_signal::calibration_bank_for_note(kNote));

  constexpr std::uint32_t kCollectingSamples = 120000U;
  for (std::uint32_t sample = 0U; sample < kCollectingSamples; ++sample) {
    static_cast<void>(detector.process_sample(
        m3::test_signal::unison_sample(
            kNote, members, sample, kSampleRate)));
  }
  const auto before_gap =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_FALSE(before_gap.valid);
  M3_EXPECT_TRUE(before_gap.history_count > 0U);

  constexpr std::uint32_t kArticulationGapSamples = 14400U;
  for (std::uint32_t sample = 0U; sample < kArticulationGapSamples;
       ++sample) {
    static_cast<void>(detector.process_sample(0.0));
  }
  const auto after_gap =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 1U);
  M3_EXPECT_FALSE(after_gap.valid);
  M3_EXPECT_EQ(after_gap.history_count, 0U);
}

M3_TEST(native_detector_retains_only_committed_or_robust_triple_history_across_silence) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(Access::fine_history_retention_probe(
      true, true, 0x07U, 0.10, true, false));
  M3_EXPECT_FALSE(Access::fine_history_retention_probe(
      true, true, 0x03U, 0.20, false, false));
  M3_EXPECT_TRUE(Access::fine_history_retention_probe(
      true, true, 0x07U, 0.0, false, true));
  M3_EXPECT_FALSE(Access::fine_history_retention_probe(
      true, true, 0x07U, 0.09, true, false));
  M3_EXPECT_FALSE(Access::fine_history_retention_probe(
      true, true, 0x01U, 1.0, true, false));
  M3_EXPECT_FALSE(Access::fine_history_retention_probe(
      false, true, 0x07U, 1.0, true, false));
}

M3_TEST(native_detector_bridges_signal_floor_only_for_the_committed_fine_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(
      Access::committed_fine_group_match_probe(true, true, true, 0x03U, 0x03U));
  M3_EXPECT_TRUE(
      Access::committed_fine_group_match_probe(true, true, true, 0x0fU, 0x0fU));
  M3_EXPECT_FALSE(
      Access::committed_fine_group_match_probe(true, true, true, 0x03U, 0x07U));
  M3_EXPECT_FALSE(
      Access::committed_fine_group_match_probe(true, true, true, 0x01U, 0x01U));
  M3_EXPECT_FALSE(
      Access::committed_fine_group_match_probe(true, false, true, 0x03U, 0x03U));
  M3_EXPECT_FALSE(
      Access::committed_fine_group_match_probe(true, true, false, 0x03U, 0x03U));
  M3_EXPECT_FALSE(
      Access::committed_fine_group_match_probe(false, true, true, 0x03U, 0x03U));
}

M3_TEST(native_detector_carries_only_an_established_direct_group_across_selector_misses) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  const auto retained = Access::fine_history_after_selector_miss(
      detector, 0x07U, 0x07U, 0.03, false);
  M3_EXPECT_TRUE(retained.valid);
  M3_EXPECT_TRUE(retained.history_count > 1U);

  const auto single = Access::fine_history_after_selector_miss(
      detector, 0x01U, 0x01U, 0.03, false);
  M3_EXPECT_FALSE(single.valid);
  M3_EXPECT_EQ(single.history_count, 0U);
  const auto mismatch = Access::fine_history_after_selector_miss(
      detector, 0x03U, 0x07U, 0.03, false);
  M3_EXPECT_FALSE(mismatch.valid);
  M3_EXPECT_EQ(mismatch.history_count, 0U);
  const auto below_floor = Access::fine_history_after_selector_miss(
      detector, 0x07U, 0x07U, 0.024, false);
  M3_EXPECT_FALSE(below_floor.valid);
  M3_EXPECT_EQ(below_floor.history_count, 0U);
  const auto quiet = Access::fine_history_after_selector_miss(
      detector, 0x07U, 0x07U, 0.03, true);
  M3_EXPECT_FALSE(quiet.valid);
  M3_EXPECT_EQ(quiet.history_count, 0U);
}

M3_TEST(native_detector_fast_confirms_only_the_complete_bounded_playable_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0U, 0x03U, 0x1fU) -
                          0.20) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x01U, 0x03U, 0x1fU) -
                          0.20) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x03U, 0x07U, 0x07U) -
                          0.0) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x07U, 0x0fU, 0x0fU) -
                          0.0) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x03U, 0x07U, 0x0fU) -
                          2.25) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x0fU, 0x1fU, 0x1fU) -
                          2.25) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x03U, 0x06U, 0x07U) -
                          2.25) < 1.0e-12);
  M3_EXPECT_TRUE(std::abs(Access::fine_consensus_seconds(0x07U, 0x03U, 0x07U) -
                          2.25) < 1.0e-12);
}

M3_TEST(native_detector_only_extends_resolved_unison_release_while_signal_remains) {
  constexpr double kSampleRate = 48000.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  constexpr std::size_t kCandidate = 8U;
  constexpr std::uint8_t kTriple = 0x07U;

  const double ordinary =
      m3::PolyphonicPitchDetectorTestAccess::candidate_release_hold_seconds(
          detector, kCandidate, 0x01U, 3.0, false);
  const double nonquiet_unison =
      m3::PolyphonicPitchDetectorTestAccess::candidate_release_hold_seconds(
          detector, kCandidate, kTriple, 3.0, false);
  const double quiet_unison =
      m3::PolyphonicPitchDetectorTestAccess::candidate_release_hold_seconds(
          detector, kCandidate, kTriple, 3.0, true);

  M3_EXPECT_TRUE(nonquiet_unison >= 0.49);
  M3_EXPECT_TRUE(nonquiet_unison > ordinary);
  M3_EXPECT_TRUE(std::abs(quiet_unison - ordinary) <= 0.002);
}

M3_TEST(native_detector_locks_each_recorded_low_string_to_its_tuner_lane) {
  constexpr std::array<std::uint8_t, 3U> kFrets{0U, 12U, 24U};
  constexpr std::array<double, 2U> kLevels{0.65, 1.0};
  // Exercise the three heaviest synthetic models over complete 0--24 fret
  // ranges; the all-string open-note test below protects all eight lane
  // identities and the offline fixture tests cover the physical bank itself.
  constexpr std::size_t kRecordedStringCount = 3U;
  for (std::size_t string = 0U; string < kRecordedStringCount; ++string) {
    for (const std::uint8_t fret : kFrets) {
      for (const double level : kLevels) {
        const SingleStringMetrics metrics =
            run_single_plucked_string_case(string, fret, level);
        if (metrics.maximum_voices > 1U || metrics.tracked_frames == 0U ||
            metrics.final_string != static_cast<std::uint8_t>(string)) {
          std::fprintf(stderr,
                       "single string=%zu fret=%u level=%.2f max=%u frames=%u final=%u dev=%.4f multi=%d beat=%d fine=%u energies=%.4g,%.4g,%.4g,%.4g\n",
                       string, fret, level, metrics.maximum_voices,
                       metrics.tracked_frames, metrics.final_string,
                       metrics.fine.frequency_deviation_hz,
                       metrics.fine.multi_source_observed ? 1 : 0,
                       metrics.fine.beat_valid ? 1 : 0,
                       metrics.fine.members,
                       metrics.fine.component_energy[0U],
                       metrics.fine.component_energy[1U],
                       metrics.fine.component_energy[2U],
                       metrics.fine.component_energy[3U]);
        }
        M3_EXPECT_TRUE(metrics.maximum_voices <= 1U);
        M3_EXPECT_TRUE(metrics.tracked_frames > 0U);
        M3_EXPECT_EQ(metrics.final_string,
                     static_cast<std::uint8_t>(string));
      }
    }
  }
}

M3_TEST(native_detector_maps_each_open_plucked_string_to_its_tuner_lane) {
  constexpr std::array<double, 2U> kLevels{0.65, 1.0};
  for (std::size_t string = 0U; string < m3::kM3OpenNotes.size(); ++string) {
    for (const double level : kLevels) {
      const SingleStringMetrics metrics =
          run_single_plucked_string_case(string, 0U, level);
      M3_EXPECT_TRUE(metrics.maximum_voices <= 1U);
      M3_EXPECT_TRUE(metrics.tracked_frames > 0U);
      M3_EXPECT_EQ(metrics.final_string,
                   static_cast<std::uint8_t>(string));
    }
  }
}

M3_TEST(native_polyphonic_detector_tracks_low_eight_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 48U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 32U, 24000U, transitions);
  feed_silence(detector, 16000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 32U);
    M3_EXPECT_TRUE(transitions[0].velocity > 0U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 32U);
    M3_EXPECT_EQ(transitions[1].velocity, 0U);
  }
}

M3_TEST(native_detector_reports_cents_for_the_low_g_sharp_range_boundary) {
  constexpr double kSampleRate = 96000.0;
  constexpr double kDetuneCents = 12.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 1U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  const double frequency = m3::midi_to_frequency(
      32.0 + kDetuneCents / 100.0, config.a4_hz);
  bool found_valid_cents = false;
  double observed_cents = 0.0;
  for (std::uint32_t index = 0U; index < 24000U; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    const m3::DetectorDecision decision = detector.process_sample(
        0.08 * std::sin(6.28318530717958647692 * frequency * time));
    if (!decision.tuner_snapshot_ready) {
      continue;
    }
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& estimate = decision.tuner_snapshot.voices[voice];
      if (estimate.midi_note == 32U && estimate.cents_valid) {
        found_valid_cents = true;
        observed_cents = static_cast<double>(estimate.cents_q8) / 256.0;
      }
    }
  }
  M3_EXPECT_TRUE(found_valid_cents);
  M3_EXPECT_NEAR(observed_cents, kDetuneCents, 6.0);
}

M3_TEST(native_detector_reports_settled_cents_within_one_cent_at_48_and_96khz) {
  constexpr std::array<double, 2U> kSampleRates{48000.0, 96000.0};
  constexpr std::array<std::uint8_t, 4U> kNotes{32U, 40U, 48U, 60U};
  constexpr std::array<double, 5U> kOffsets{-40.0, -20.0, 0.0, 20.0, 40.0};
  double worst_error = 0.0;
  double worst_rate = 0.0;
  double worst_offset = 0.0;
  std::uint8_t worst_note = 0U;
  bool observed_every_case = true;

  for (const double sample_rate : kSampleRates) {
    for (const std::uint8_t note : kNotes) {
      for (const double offset : kOffsets) {
        m3::PersistentConfig config;
        config.profile_mode = m3::ProfileMode::m3;
        config.lowest_note = 32U;
        config.highest_note = 60U;
        config.max_polyphony = 1U;
        config.max_fret = 24U;
        config.sensitivity = 69U;
        config.response = 81U;

        m3::PolyphonicPitchDetector detector;
        M3_EXPECT_TRUE(detector.configure(sample_rate, config));
        const double frequency = m3::midi_to_frequency(
            static_cast<double>(note) + offset / 100.0, config.a4_hz);
        const std::uint32_t samples = static_cast<std::uint32_t>(
            std::lround(0.25 * sample_rate));
        bool observed = false;
        double measured = 0.0;
        for (std::uint32_t sample = 0U; sample < samples; ++sample) {
          const double time = static_cast<double>(sample) / sample_rate;
          const m3::DetectorDecision decision = detector.process_sample(
              0.12 * std::sin(6.28318530717958647692 * frequency * time));
          for (std::size_t voice = 0U;
               decision.tuner_snapshot_ready &&
               voice < decision.tuner_snapshot.voice_count;
               ++voice) {
            const m3::TunerVoice& estimate =
                decision.tuner_snapshot.voices[voice];
            if (estimate.midi_note == note && estimate.cents_valid &&
                estimate.state == m3::TunerVoiceState::tracking) {
              observed = true;
              measured = static_cast<double>(estimate.cents_q8) / 256.0;
            }
          }
        }
        observed_every_case = observed_every_case && observed;
        if (observed) {
          const double error = std::abs(measured - offset);
          if (error > worst_error) {
            worst_error = error;
            worst_rate = sample_rate;
            worst_note = note;
            worst_offset = offset;
          }
        }
      }
    }
  }

  if (worst_error > 1.0) {
    std::fprintf(stderr,
                 "worst settled cents error %.3f at %.0f Hz note %u offset %.1f\n",
                 worst_error, worst_rate, static_cast<unsigned>(worst_note),
                 worst_offset);
  }
  M3_EXPECT_TRUE(observed_every_case);
  M3_EXPECT_NEAR(worst_error, 0.0, 1.0);
}

M3_TEST(native_detector_never_labels_an_inaccurate_attack_cents_value_valid) {
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<std::uint8_t, 3U> kNotes{32U, 48U, 60U};
  constexpr std::array<double, 3U> kOffsets{-20.0, 0.0, 20.0};
  double worst_valid_error = 0.0;
  double worst_rate = 0.0;
  double worst_offset = 0.0;
  double worst_measured = 0.0;
  std::uint8_t worst_note = 0U;
  std::uint32_t worst_sample = 0U;
  bool observed_every_case = true;

  for (const double sample_rate : kSampleRates) {
    for (const std::uint8_t note : kNotes) {
      for (const double offset : kOffsets) {
        m3::PersistentConfig config;
        config.profile_mode = m3::ProfileMode::m3;
        config.lowest_note = 32U;
        config.highest_note = 60U;
        config.max_polyphony = 1U;
        config.max_fret = 24U;
        config.sensitivity = 69U;
        config.response = 81U;

        m3::PolyphonicPitchDetector detector;
        M3_EXPECT_TRUE(detector.configure(sample_rate, config));
        const double frequency = m3::midi_to_frequency(
            static_cast<double>(note) + offset / 100.0, config.a4_hz);
        const std::uint32_t samples = static_cast<std::uint32_t>(
            std::lround(0.22 * sample_rate));
        bool observed_valid = false;
        for (std::uint32_t sample = 0U; sample < samples; ++sample) {
          const double time = static_cast<double>(sample) / sample_rate;
          const m3::DetectorDecision decision = detector.process_sample(
              0.12 * std::sin(6.28318530717958647692 * frequency * time));
          for (std::size_t voice = 0U;
               decision.tuner_snapshot_ready &&
               voice < decision.tuner_snapshot.voice_count;
               ++voice) {
            const m3::TunerVoice& estimate =
                decision.tuner_snapshot.voices[voice];
            if (estimate.midi_note != note || !estimate.cents_valid ||
                estimate.state != m3::TunerVoiceState::tracking) {
              continue;
            }
            observed_valid = true;
            const double measured =
                static_cast<double>(estimate.cents_q8) / 256.0;
            const double error = std::abs(measured - offset);
            if (error > worst_valid_error) {
              worst_valid_error = error;
              worst_rate = sample_rate;
              worst_note = note;
              worst_offset = offset;
              worst_measured = measured;
              worst_sample = sample;
            }
          }
        }
        observed_every_case = observed_every_case && observed_valid;
      }
    }
  }

  if (worst_valid_error > 2.0) {
    std::fprintf(stderr,
                 "worst attack cents error %.3f at %.0f Hz note %u "
                 "offset %.1f measured %.3f sample %u\n",
                 worst_valid_error, worst_rate,
                 static_cast<unsigned>(worst_note), worst_offset,
                 worst_measured, static_cast<unsigned>(worst_sample));
  }
  M3_EXPECT_TRUE(observed_every_case);
  M3_EXPECT_NEAR(worst_valid_error, 0.0, 2.0);
}

M3_TEST(native_detector_calibration_does_not_redefine_tuner_zero_cents) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kDetuneCents = 12.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 32U;
  config.max_polyphony = 1U;
  config.max_fret = 0U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(
      bank, 0U, 0U, kDetuneCents,
      {1.0, 0.02, 0.01, 0.0, 0.0, 0.0});
  detector.set_calibration_bank(bank);

  const double frequency = m3::midi_to_frequency(
      32.0 + kDetuneCents / 100.0, config.a4_hz);
  bool found_valid_cents = false;
  double observed_cents = 0.0;
  for (std::uint32_t sample = 0U; sample < 24000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const m3::DetectorDecision decision = detector.process_sample(
        0.08 * std::sin(6.28318530717958647692 * frequency * time));
    for (std::size_t voice = 0U;
         decision.tuner_snapshot_ready &&
         voice < decision.tuner_snapshot.voice_count;
         ++voice) {
      const m3::TunerVoice& estimate = decision.tuner_snapshot.voices[voice];
      if (estimate.midi_note == 32U && estimate.string_index == 0U &&
          estimate.cents_valid) {
        found_valid_cents = true;
        observed_cents = static_cast<double>(estimate.cents_q8) / 256.0;
      }
    }
  }

  M3_EXPECT_TRUE(found_valid_cents);
  M3_EXPECT_NEAR(observed_cents, kDetuneCents, 6.0);
}

M3_TEST(native_polyphonic_detector_tracks_highest_open_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 60U, 24000U, transitions);
  feed_silence(detector, 16000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 60U);
    M3_EXPECT_TRUE(transitions[0].velocity > 0U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 60U);
    M3_EXPECT_EQ(transitions[1].velocity, 0U);
  }
}

M3_TEST(native_detector_tracks_the_twenty_fourth_fret_c6_range_boundary) {
  constexpr std::uint8_t kNote = 84U;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = kNote;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, config.a4_hz);
    bool note_on = false;
    bool tracked = false;
    const std::uint32_t samples = static_cast<std::uint32_t>(
        std::lround(0.30 * sample_rate));
    for (std::uint32_t sample = 0U; sample < samples; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const m3::DetectorDecision decision = detector.process_sample(
          0.12 * std::sin(6.28318530717958647692 * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        note_on = note_on ||
                  (decision.transitions[event].kind ==
                       m3::TransitionKind::note_on &&
                   decision.transitions[event].note == kNote);
      }
      for (std::size_t voice = 0U;
           decision.tuner_snapshot_ready &&
           voice < decision.tuner_snapshot.voice_count;
           ++voice) {
        const m3::TunerVoice& estimate =
            decision.tuner_snapshot.voices[voice];
        tracked = tracked ||
                  (estimate.state == m3::TunerVoiceState::tracking &&
                   estimate.midi_note == kNote && estimate.string_index == 7U);
      }
    }
    M3_EXPECT_TRUE(note_on);
    M3_EXPECT_TRUE(tracked);
  }
}

M3_TEST(native_detector_does_not_expand_one_tone_into_the_polyphony_limit) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 40U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 40U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 40U);
  }
}

M3_TEST(native_detector_rejects_octave_and_fifth_subharmonics_at_default_range) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 52U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 52U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 52U);
  }
}

M3_TEST(native_detector_tracks_two_independent_chord_voices_and_releases_each) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.low_on_sample <= 3120U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_distinguishes_a_bright_low_string_from_a_real_octave) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kLowNote = 40U;
  constexpr std::uint8_t kOctaveNote = 52U;
  const double low_frequency = m3::midi_to_frequency(kLowNote, 440.0);
  const double octave_frequency =
      m3::midi_to_frequency(static_cast<double>(kOctaveNote) + 0.04, 440.0);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  const auto exercise = [&](bool add_independent_octave) noexcept {
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    bool low_on = false;
    bool octave_on = false;
    bool unexpected = false;
    for (std::uint32_t sample = 0U; sample < 36000U; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      const double phase = 6.28318530717958647692 * low_frequency * time;
      double value = 0.10 * std::sin(phase + 0.13) +
                     0.075 * std::sin(2.0 * phase - 0.31) +
                     0.045 * std::sin(3.0 * phase + 0.47) +
                     0.025 * std::sin(4.0 * phase - 0.19);
      if (add_independent_octave) {
        const double octave_phase =
            6.28318530717958647692 * octave_frequency * time;
        value += 0.070 * std::sin(octave_phase + 1.17) +
                 0.030 * std::sin(2.0 * octave_phase - 0.83) +
                 0.015 * std::sin(3.0 * octave_phase + 0.62);
      }
      const m3::DetectorDecision decision = detector.process_sample(value);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        if (decision.transitions[event].kind !=
            m3::TransitionKind::note_on) {
          continue;
        }
        low_on = low_on || decision.transitions[event].note == kLowNote;
        octave_on = octave_on ||
                    decision.transitions[event].note == kOctaveNote;
        unexpected = unexpected ||
                     (decision.transitions[event].note != kLowNote &&
                      decision.transitions[event].note != kOctaveNote);
      }
    }
    return std::array<bool, 3U>{low_on, octave_on, unexpected};
  };

  const auto bright_low = exercise(false);
  M3_EXPECT_TRUE(bright_low[0U]);
  M3_EXPECT_FALSE(bright_low[1U]);
  M3_EXPECT_FALSE(bright_low[2U]);

  const auto real_octave = exercise(true);
  M3_EXPECT_TRUE(real_octave[0U]);
  M3_EXPECT_TRUE(real_octave[1U]);
  M3_EXPECT_FALSE(real_octave[2U]);
}

M3_TEST(native_detector_keeps_an_uneven_major_seventh_as_two_voices) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  DyadLifecycle lifecycle{32U, 43U};
  feed_dyad(detector, 32U, 43U, 0.15, 0.20, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_honors_m3_maximum_fret_without_limiting_general_mode) {
  m3::PersistentConfig m3_config;
  m3_config.profile_mode = m3::ProfileMode::m3;
  m3_config.lowest_note = 32U;
  m3_config.highest_note = 84U;
  m3_config.max_polyphony = 1U;
  m3_config.max_fret = 0U;
  m3_config.sensitivity = 75U;
  m3_config.response = 25U;

  m3::PolyphonicPitchDetector m3_detector;
  M3_EXPECT_TRUE(m3_detector.configure(48000.0, m3_config));
  m3::TickTransitions m3_transitions;
  feed_tone(m3_detector, 33U, 30000U, m3_transitions);
  feed_silence(m3_detector, 8000U, m3_transitions);
  M3_EXPECT_EQ(m3_transitions.size(), 0U);

  m3::PersistentConfig general_config = m3_config;
  general_config.profile_mode = m3::ProfileMode::general;
  m3::PolyphonicPitchDetector general_detector;
  M3_EXPECT_TRUE(general_detector.configure(48000.0, general_config));
  m3::TickTransitions general_transitions;
  feed_tone(general_detector, 33U, 30000U, general_transitions);
  feed_silence(general_detector, 8000U, general_transitions);
  M3_EXPECT_EQ(general_transitions.size(), 2U);
  if (general_transitions.size() == 2U) {
    M3_EXPECT_EQ(general_transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(general_transitions[0U].note, 33U);
    M3_EXPECT_EQ(general_transitions[1U].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(general_transitions[1U].note, 33U);
  }
}

M3_TEST(native_detector_keeps_a_clear_m3_fretted_fundamental_over_the_open_prior) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions transitions;
  feed_tone(detector, 41U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0U].note, 41U);
    M3_EXPECT_EQ(transitions[1U].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1U].note, 41U);
  }
}

M3_TEST(native_detector_single_voice_onset_meets_the_causal_45ms_gate) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions transitions;
  std::uint32_t first_note_on_sample =
      std::numeric_limits<std::uint32_t>::max();
  feed_tone(detector, 40U, 6000U, transitions, &first_note_on_sample);
  M3_EXPECT_TRUE(first_note_on_sample <= 2160U);
  M3_EXPECT_EQ(transitions.size(), 1U);
  if (transitions.size() == 1U) {
    M3_EXPECT_EQ(transitions[0U].note, 40U);
  }
}

M3_TEST(native_detector_restarts_the_single_voice_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  m3::TickTransitions transitions;
  std::uint32_t first_note_on_sample =
      std::numeric_limits<std::uint32_t>::max();
  feed_tone(detector, 52U, 6000U, transitions, &first_note_on_sample);
  M3_EXPECT_TRUE(first_note_on_sample <= 2160U);
  M3_EXPECT_EQ(transitions.size(), 1U);
  if (transitions.size() == 1U) {
    M3_EXPECT_EQ(transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0U].note, 52U);
  }
}

M3_TEST(native_detector_restarts_the_chord_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 6000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.low_on_sample <= 3120U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_requires_fresh_evidence_for_a_legato_added_voice) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.0, 6000U, lifecycle);
  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_FALSE(lifecycle.high_on);

  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 6000U, lifecycle, 6000U);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.high_on_sample >= 2304U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_requires_fresh_evidence_for_a_legato_replacement) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.0, 6000U, lifecycle);
  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_FALSE(lifecycle.high_on);

  feed_dyad(detector, 40U, 47U, 0.0, 0.16, 6000U, lifecycle, 6000U);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.high_on_sample >= 1792U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 2640U);
}

M3_TEST(native_detector_keeps_a_live_legato_replacement_on_its_started_string) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const auto assignments =
      m3::PolyphonicPitchDetectorTestAccess::legato_assignment_sequence(
          detector);
  M3_EXPECT_EQ(assignments[0U], 2U);
  M3_EXPECT_EQ(assignments[1U], assignments[0U]);
}

M3_TEST(native_detector_keeps_a_single_routing_tuner_lane_on_its_started_string) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::single;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const auto assignments =
      m3::PolyphonicPitchDetectorTestAccess::legato_assignment_sequence(
          detector);
  M3_EXPECT_EQ(assignments[0U], 2U);
  M3_EXPECT_EQ(assignments[1U], assignments[0U]);
}

M3_TEST(native_detector_reserves_every_committed_unison_lane_across_pitch_groups) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 3U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   assignment_beside_committed_unison_lane(detector),
               4U);
}

M3_TEST(native_detector_retains_a_resolved_unison_before_pitch_competition) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.030);
  M3_EXPECT_TRUE(result.retained);
  M3_EXPECT_TRUE(result.first_competitor || result.second_competitor);
  M3_EXPECT_FALSE(result.first_competitor && result.second_competitor);
}

M3_TEST(native_detector_does_not_reserve_a_single_string_candidate) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x01U, 0x01U, 0.030);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_drops_a_resolved_unison_below_the_decay_floor) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.024);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_does_not_reserve_a_group_without_pairwise_beats) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.030, 0.19);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_retains_an_established_triple_with_a_strong_beat_spanning_tree) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.030, 0.19,
                                      true, true);
  M3_EXPECT_TRUE(result.retained);
}

M3_TEST(native_detector_does_not_relax_the_pairwise_gate_for_two_strings) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x03U, 0x03U, 0.030, 0.19,
                                      true);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_connected_triple_still_needs_a_bounded_weak_pair_floor) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.030, 0.09,
                                      true, true);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_does_not_relax_beats_for_an_unconfirmed_triple) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      retained_unison_selection_probe(detector, 0x07U, 0x07U, 0.030, 0.19,
                                      true, false);
  M3_EXPECT_FALSE(result.retained);
}

M3_TEST(native_detector_spectral_tiers_complete_one_settled_unison_lane) {
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kHeads{
      0U, 1U, 2U, 1U, 2U};
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.004, 0.008, 0.007, 0.006, 0.005};
  std::array<double, m3::kMaxVoices> coherence{};
  coherence[0U] = 0.25;

  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x07U);
  // An already-retained two-string group may still acquire the one
  // independently corroborated missing lane. Retention must not freeze the
  // group at its previous size before the joint selector runs.
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x06U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x07U);
  // Once the completed lane is committed, the same still-valid spectral and
  // beat evidence must keep the group intact on the following decision.
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x07U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x07U);
}

M3_TEST(native_detector_joint_selector_reserves_measured_tier_completion_atomically) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 4U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          retained_unison_completion_selector_probe(detector),
      0x07U);
}

M3_TEST(native_detector_completes_a_fresh_resolved_pair_before_activation) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 4U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          fresh_fine_pair_completion_inference_probe(detector),
      0x07U);
}

M3_TEST(native_detector_joint_selector_selects_stronger_bounded_tier_completion) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 3U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      stronger_completion_priority_probe(detector);
  M3_EXPECT_FALSE(result.weaker);
  M3_EXPECT_TRUE(result.stronger);
}

M3_TEST(native_detector_joint_selector_charges_every_retained_group_by_lane) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 4U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result =
      m3::PolyphonicPitchDetectorTestAccess::atomic_retained_groups_probe(
          detector);
  M3_EXPECT_TRUE(result.first_pair);
  M3_EXPECT_TRUE(result.second_pair);
  M3_EXPECT_FALSE(result.competitor);
  M3_EXPECT_EQ(result.emitted_lanes, 4U);
}

M3_TEST(
    native_detector_joint_selector_charges_committed_group_without_resolved_mask) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 5U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      committed_group_capacity_probe(detector);
  M3_EXPECT_TRUE(result.committed_group);
  M3_EXPECT_EQ(result.selected_competitors, 2U);
  M3_EXPECT_EQ(result.emitted_lanes, 5U);
}

M3_TEST(
    native_detector_joint_selector_does_not_apply_shadow_tier_completion) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_fret = 24U;
  config.max_polyphony = 5U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  const auto result = m3::PolyphonicPitchDetectorTestAccess::
      mixed_completed_and_retained_groups_probe(detector);
  M3_EXPECT_TRUE(result.completed_triple);
  M3_EXPECT_TRUE(result.retained_pair);
  M3_EXPECT_FALSE(result.competitor);
  M3_EXPECT_EQ(result.completed_mask, 0U);
  M3_EXPECT_EQ(result.emitted_lanes, 5U);
}

M3_TEST(native_detector_spectral_tiers_cannot_create_or_overexpand_a_group) {
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.004, 0.008, 0.007, 0.006, 0.005};
  std::array<double, m3::kMaxVoices> coherence{};
  coherence[0U] = 0.25;

  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kOneExtra{
      0U, 1U, 2U, 1U, 2U};
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x02U, 0x07U, kOneExtra, kMargins, coherence),
      0x02U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          false, 0x02U, 0x06U, 0x07U, kOneExtra, kMargins, coherence),
      0x06U);

  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kTwoExtra{
      0U, 3U, 1U, 2U, 3U};
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x0FU, kTwoExtra, kMargins, coherence),
      0x06U);
}

M3_TEST(native_detector_spectral_tier_completion_requires_measured_beat_window) {
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kHeads{
      0U, 1U, 2U, 1U, 2U};
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.004, 0.008, 0.007, 0.006, 0.005};
  std::array<double, m3::kMaxVoices> coherence{};
  coherence[0U] = 0.19;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x06U);
  coherence[0U] = 0.30;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x07U);
  coherence[0U] = 0.35;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kHeads, kMargins, coherence),
      0x06U);
  coherence[0U] = 0.25;
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kWeakMargins{
      0.0005, 0.0005, 0.0005, 0.0005, 0.0005};
  // The measured beat window and the separate component-energy floor now
  // carry this bounded one-lane completion; a small non-negative head margin
  // is no longer an independent rejection reason.
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kHeads, kWeakMargins, coherence),
      0x07U);
}

M3_TEST(
    native_detector_spectral_tier_completion_trades_head_margin_for_component_energy) {
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U> kHeads{
      0U, 1U, 2U, 1U, 2U};
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kTiedMargins{
      0.0, 0.0, 0.0, 0.0, 0.0};
  std::array<double, m3::kMaxVoices> coherence{};
  coherence[2U] = 0.25;

  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x01U, 0x03U, 0x07U, kHeads, kTiedMargins, coherence, 0.10,
          2U),
      0x07U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x01U, 0x03U, 0x07U, kHeads, kTiedMargins, coherence, 0.09,
          2U),
      0x03U);
}

M3_TEST(
    native_detector_spectral_tier_completion_uses_measured_thickest_string_floor) {
  constexpr std::array<double, m3::kSpectralTierCount + 1U> kMargins{
      0.004, 0.008, 0.007, 0.006, 0.005};
  std::array<double, m3::kMaxVoices> coherence{};

  // The physical long-unison replay measured a useful weaker component only
  // when completing the 80-gauge thickest-string lane.
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U>
      kAddThickest{0U, 1U, 2U, 1U, 2U};
  coherence[0U] = 0.25;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kAddThickest, kMargins, coherence, 0.06,
          0U),
      0x07U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x02U, 0x06U, 0x07U, kAddThickest, kMargins, coherence, 0.059,
          0U),
      0x06U);

  // An otherwise identical weak completion of another physical string keeps
  // the established 0.10 floor; the broad low-band trial falsely expanded a
  // real two-string interval through this path.
  constexpr std::array<std::uint8_t, m3::kSpectralTierCount + 1U>
      kAddThirdString{0U, 1U, 2U, 1U, 2U};
  coherence = {};
  coherence[2U] = 0.25;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x01U, 0x03U, 0x07U, kAddThirdString, kMargins, coherence,
          0.06, 2U),
      0x03U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_tier_completion_probe(
          true, 0x01U, 0x03U, 0x07U, kAddThirdString, kMargins, coherence,
          0.10, 2U),
      0x07U);
}

M3_TEST(native_detector_does_not_move_a_settled_lane_for_a_single_source_fine_fit) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   assignment_with_single_source_fine_fit(detector),
               6U);
}

M3_TEST(native_detector_does_not_prefer_silence_to_a_direct_high_fret_candidate) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     selects_direct_high_fret_candidate(detector));
}

M3_TEST(native_detector_uses_calibrated_identity_for_a_weak_high_fret_attack) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kPhysicalProfile{
      1.00, 0.05, 0.00, 0.00, 0.00, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOtherProfile{
      0.20, 1.00, 0.00, 0.00, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 6U, 24U, 0.0, kPhysicalProfile);
  set_measured_string_profile(bank, 7U, 20U, 0.0, kOtherProfile);
  detector.set_calibration_bank(bank);
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     selects_calibrated_high_fret_candidate_below_global_threshold(
                         detector));
}

M3_TEST(native_detector_adds_one_decisive_calibrated_upper_chord_tone) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     selects_calibrated_band_rescue_beside_a_stronger_chord_tone(
                         detector, true));
}

M3_TEST(native_detector_rejects_ambiguous_calibrated_upper_chord_tone) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  M3_EXPECT_FALSE(m3::PolyphonicPitchDetectorTestAccess::
                      selects_calibrated_band_rescue_beside_a_stronger_chord_tone(
                          detector, false));
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
M3_TEST(native_detector_pitch_band_admission_diagnostics_are_scale_invariant) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kLowNote = 40U;
  constexpr std::uint8_t kHighNote = 72U;
  const auto observe = [](double scale) noexcept {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 84U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    config.sensitivity = 60U;
    config.response = 75U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    const double low_hz = m3::midi_to_frequency(kLowNote, 440.0);
    const double high_hz = m3::midi_to_frequency(kHighNote, 440.0);
    constexpr std::uint32_t kSamples = 96000U;
    for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      static_cast<void>(detector.process_sample(
          scale * (0.20 * std::sin(kTwoPi * low_hz * time) +
                   0.012 * std::sin(kTwoPi * high_hz * time + 0.31))));
    }
    return detector.candidate_admission_diagnostics(kHighNote);
  };

  const auto full = observe(1.0);
  const auto half = observe(0.5);
  M3_EXPECT_TRUE(full.pitch_band_score_peak_ratio > 0.0);
  M3_EXPECT_TRUE(full.pitch_band_fundamental_peak_ratio > 0.0);
  M3_EXPECT_NEAR(full.pitch_band_score_peak_ratio,
                 half.pitch_band_score_peak_ratio, 1.0e-9);
  M3_EXPECT_NEAR(full.pitch_band_fundamental_peak_ratio,
                 half.pitch_band_fundamental_peak_ratio, 1.0e-9);
}
#endif

M3_TEST(native_detector_does_not_steal_an_extra_lane_from_another_pitch_group) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto masks = m3::PolyphonicPitchDetectorTestAccess::
      inference_beside_committed_unison_group(detector);
  M3_EXPECT_EQ(masks[0U], static_cast<std::uint8_t>(1U << 4U));
  M3_EXPECT_EQ(masks[1U],
               static_cast<std::uint8_t>((1U << 6U) | (1U << 5U)));
}

M3_TEST(native_detector_restarts_the_four_voice_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 4U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 40U, 48U, 56U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 4U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_chord(detector, 0.04, 6000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
    M3_EXPECT_TRUE(lifecycle.first_on_sample[voice] <= 3120U);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_completes_a_four_note_m3_chord_within_65ms) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 4U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 40U, 48U, 56U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 4U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_chord(detector, 0.04, 36000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
    M3_EXPECT_TRUE(lifecycle.first_on_sample[voice] <= 3120U);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_holds_a_96khz_fingerstyle_m3_triad_at_the_live_calibration) {
  constexpr double kSampleRate = 96000.0;
  constexpr std::array<std::uint8_t, 3> kNotes{32U, 40U, 48U};
  // These post-trim amplitudes model the user's current -11.6 dB input trim
  // and an uneven three-string fingerstyle attack.
  constexpr std::array<double, 3> kAmplitudes{0.070, 0.054, 0.043};
  constexpr std::uint32_t kSustainSamples = 67200U;  // 700 ms

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 3U;
  config.max_fret = 24U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {kNotes[0], kNotes[1], kNotes[2], 0U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = kNotes.size();
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());

  std::size_t stable_snapshot_count = 0U;
  std::size_t minimum_known_voices = kNotes.size();
  for (std::uint32_t index = 0U; index < kSustainSamples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    const double attack = std::min(1.0, time / 0.004);
    const double decay = std::exp(-1.1 * time);
    const double dropout = time >= 0.350 && time < 0.365 ? 0.08 : 1.0;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(kNotes[voice]), 440.0);
      const double phase = 6.28318530717958647692 * frequency * time;
      const double string = std::sin(phase) + 0.28 * std::sin(2.0 * phase) +
                            0.12 * std::sin(3.0 * phase);
      sample += kAmplitudes[voice] * attack * decay * dropout * string;
    }
    const m3::DetectorDecision decision = detector.process_sample(sample);
    observe_chord(decision, lifecycle, index);
    if (!decision.tuner_snapshot_ready || time < 0.150) {
      continue;
    }
    std::size_t known_voices = 0U;
    for (std::size_t candidate = 0U;
         candidate < decision.tuner_snapshot.voice_count; ++candidate) {
      const m3::TunerVoice& voice =
          decision.tuner_snapshot.voices[candidate];
      const std::uint8_t note =
          voice.midi_note;
      bool known = false;
      for (const std::uint8_t expected : kNotes) {
        known = known || note == expected;
      }
      // Settling candidates are deliberately exposed for continuity but are
      // not allowed to create a new display lane. Only confirmed tracking
      // voices must belong to the played chord.
      if (voice.state == m3::TunerVoiceState::tracking) {
        M3_EXPECT_TRUE(known);
      }
      known_voices += known ? 1U : 0U;
    }
    minimum_known_voices = std::min(minimum_known_voices, known_voices);
    ++stable_snapshot_count;
  }

  M3_EXPECT_TRUE(stable_snapshot_count > 0U);
  M3_EXPECT_EQ(minimum_known_voices, kNotes.size());
  for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_FALSE(lifecycle.note_off[voice]);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);

  release_chord(detector, 36000U, lifecycle);
  for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
  }
}

M3_TEST(native_detector_tracks_all_eight_m3_open_strings_at_capacity) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 36U, 40U, 44U, 48U, 52U, 56U, 60U};
  lifecycle.voice_count = lifecycle.notes.size();
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_realistic_string_chord(detector, lifecycle.notes, 36000U, &lifecycle);
  // Response 81 deliberately holds vanished voices through brief fingerstyle
  // dropouts. Give the release path its full time-domain budget here.
  release_chord(detector, 16000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_does_not_invent_highest_open_from_lower_string_harmonics) {
  constexpr double kSampleRate = 96000.0;
  constexpr std::uint8_t kHighestOpen = 60U;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank =
      m3::test_signal::calibration_bank_for_note(kHighestOpen);
  for (std::size_t string = 0U; string < m3::kM3OpenNotes.size(); ++string) {
    m3::test_signal::set_calibration_point(
        bank, string, m3::kM3OpenNotes[string]);
  }
  detector.set_calibration_bank(bank);

  bool note_on = false;
  std::uint32_t tracked_frames = 0U;
  constexpr std::uint32_t kSamples = 288000U;
  for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
    double mixed = 0.0;
    for (std::size_t string = 0U; string + 1U < m3::kM3OpenNotes.size();
         ++string) {
      mixed += m3::test_signal::plucked_string_sample(
          string, m3::kM3OpenNotes[string], sample, kSampleRate);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    for (const m3::VoiceTransition& transition : decision.transitions) {
      note_on = note_on ||
                (transition.kind == m3::TransitionKind::note_on &&
                 transition.note == kHighestOpen);
    }
    if (!decision.tuner_snapshot_ready || sample < 96000U) {
      continue;
    }
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = decision.tuner_snapshot.voices[voice];
      tracked_frames +=
          observed.state == m3::TunerVoiceState::tracking &&
                  observed.midi_note == kHighestOpen
              ? 1U
              : 0U;
    }
  }
  M3_EXPECT_FALSE(note_on);
  M3_EXPECT_EQ(tracked_frames, 0U);
}

M3_TEST(native_detector_release_hold_is_time_based_at_supported_sample_rates) {
  constexpr std::array<double, 4> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::uint8_t kNote = 40U;
  constexpr double kTwoPi = 6.28318530717958647692;
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, 440.0);
    bool note_on = false;
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.60));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const auto decision = detector.process_sample(
          0.12 * std::sin(kTwoPi * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        note_on = note_on ||
                  (decision.transitions[event].kind ==
                       m3::TransitionKind::note_on &&
                   decision.transitions[event].note == kNote);
      }
    }
    M3_EXPECT_TRUE(note_on);

    std::uint32_t note_off_sample = std::numeric_limits<std::uint32_t>::max();
    bool saw_coasting = false;
    const std::uint32_t silence =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.50));
    for (std::uint32_t sample = 0U; sample < silence; ++sample) {
      const auto decision = detector.process_sample(0.0);
      if (decision.tuner_snapshot_ready &&
          decision.tuner_snapshot.voice_count == 1U &&
          decision.tuner_snapshot.voices[0U].state ==
              m3::TunerVoiceState::coasting) {
        saw_coasting = true;
        M3_EXPECT_TRUE(decision.tuner_snapshot.voices[0U].cents_valid);
      }
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        if (decision.transitions[event].kind == m3::TransitionKind::note_off &&
            decision.transitions[event].note == kNote &&
            note_off_sample == std::numeric_limits<std::uint32_t>::max()) {
          note_off_sample = sample;
        }
      }
    }
    M3_EXPECT_TRUE(saw_coasting);
    M3_EXPECT_TRUE(note_off_sample != std::numeric_limits<std::uint32_t>::max());
    if (note_off_sample != std::numeric_limits<std::uint32_t>::max()) {
      const double hold_seconds =
          static_cast<double>(note_off_sample) / sample_rate;
      M3_EXPECT_TRUE(hold_seconds >= 0.12);
      M3_EXPECT_TRUE(hold_seconds <= 0.45);
    }
  }
}

M3_TEST(native_detector_handoffs_a_single_coasting_lane_to_a_fresh_adjacent_fundamental) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 1U << 0U, 0.050, false, true, false));
}

M3_TEST(native_detector_adjacent_handoff_preserves_groups_old_notes_and_silence) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, (1U << 0U) | (1U << 1U), 0.050, true, true, false));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 1U << 0U, 0.150, false, true, false));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 1U << 0U, 0.050, false, false, false));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 1U << 0U, 0.050, false, true, true));
}

M3_TEST(native_detector_releases_a_coasting_lane_for_a_decisive_polyphonic_attack) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     inactive_adjacent_coasting_handoff_probe(
                         detector, true, true, true, true));
}

M3_TEST(native_detector_does_not_preempt_a_coasting_lane_for_ambiguous_or_isolated_attacks) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_FALSE(Access::inactive_adjacent_coasting_handoff_probe(
      detector, false, true, true, true));
  M3_EXPECT_FALSE(Access::inactive_adjacent_coasting_handoff_probe(
      detector, true, false, true, true));
  M3_EXPECT_FALSE(Access::inactive_adjacent_coasting_handoff_probe(
      detector, true, true, false, true));
  M3_EXPECT_FALSE(Access::inactive_adjacent_coasting_handoff_probe(
      detector, true, true, true, false));
}

M3_TEST(native_detector_handoffs_a_stale_multistring_group_to_a_fresh_adjacent_fundamental) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, (1U << 0U) | (1U << 1U), 0.050, false, true, false));
}

M3_TEST(native_detector_preserves_stale_three_and_four_string_groups_for_signal_aware_release) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 0x07U, 0.050, false, true, false));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::adjacent_coasting_handoff_probe(
          detector, 0x0FU, 0.050, false, true, false));
}

M3_TEST(native_detector_handoffs_a_coasting_lane_to_an_atomic_resolved_group) {
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(
      m3::PolyphonicPitchDetectorTestAccess::
          resolved_group_coasting_handoff_probe(detector, 0x01U, 0x07U,
                                                true));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::
          resolved_group_coasting_handoff_probe(detector, 0x08U, 0x07U,
                                                true));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::
          resolved_group_coasting_handoff_probe(detector, 0x01U, 0x01U,
                                                true));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::
          resolved_group_coasting_handoff_probe(detector, 0x01U, 0x07U,
                                                false));
}

M3_TEST(native_detector_keeps_a_candidate_live_until_all_note_offs_fit) {
  m3::PolyphonicPitchDetector detector;
  const auto insufficient =
      m3::PolyphonicPitchDetectorTestAccess::candidate_note_off_capacity_probe(
          detector, 1U);
  M3_EXPECT_FALSE(insufficient.queued);
  M3_EXPECT_TRUE(insufficient.candidate_active);
  M3_EXPECT_EQ(insufficient.transition_count,
               m3::TickTransitions::capacity() - 1U);

  const auto sufficient =
      m3::PolyphonicPitchDetectorTestAccess::candidate_note_off_capacity_probe(
          detector, 2U);
  M3_EXPECT_TRUE(sufficient.queued);
  M3_EXPECT_FALSE(sufficient.candidate_active);
  M3_EXPECT_EQ(sufficient.transition_count,
               m3::TickTransitions::capacity());
}

M3_TEST(native_detector_does_not_release_a_naturally_decaying_note_above_the_floor) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr double kInitialAmplitude = 0.20;
  constexpr std::uint8_t kSensitivity = 69U;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<double, 4U> kDecayRatesDbPerSecond{20.0, 30.0, 40.0,
                                                         60.0};
  const double floor_db =
      -70.0 + 0.20 * static_cast<double>(100U - kSensitivity);
  const double floor_amplitude = std::pow(10.0, floor_db / 20.0);

  for (const double sample_rate : kSampleRates) {
    for (const double decay_rate : kDecayRatesDbPerSecond) {
      m3::PersistentConfig config;
      config.profile_mode = m3::ProfileMode::m3;
      config.lowest_note = 32U;
      config.highest_note = 84U;
      config.max_polyphony = 1U;
      config.max_fret = 24U;
      config.sensitivity = kSensitivity;
      config.response = 81U;

      m3::PolyphonicPitchDetector detector;
      M3_EXPECT_TRUE(detector.configure(sample_rate, config));
      const double frequency = m3::midi_to_frequency(kNote, 440.0);
      double phase = 0.0;
      const double phase_step = kTwoPi * frequency / sample_rate;
      bool note_on = false;
      bool early_note_off = false;
      const std::uint32_t settle_samples =
          static_cast<std::uint32_t>(0.30 * sample_rate);
      for (std::uint32_t sample = 0U; sample < settle_samples; ++sample) {
        const auto decision =
            detector.process_sample(kInitialAmplitude * std::sin(phase));
        phase = std::fmod(phase + phase_step, kTwoPi);
        for (std::size_t event = 0U; event < decision.transitions.size();
             ++event) {
          note_on = note_on ||
                    (decision.transitions[event].kind ==
                         m3::TransitionKind::note_on &&
                     decision.transitions[event].note == kNote);
        }
      }
      M3_EXPECT_TRUE(note_on);

      for (std::uint32_t sample = 0U;; ++sample) {
        const double time = static_cast<double>(sample) / sample_rate;
        const double amplitude =
            kInitialAmplitude * std::pow(10.0, -decay_rate * time / 20.0);
        if (amplitude < 4.0 * floor_amplitude) {
          break;
        }
        const auto decision = detector.process_sample(amplitude * std::sin(phase));
        phase = std::fmod(phase + phase_step, kTwoPi);
        for (std::size_t event = 0U; event < decision.transitions.size();
             ++event) {
          early_note_off = early_note_off ||
                           (decision.transitions[event].kind ==
                                m3::TransitionKind::note_off &&
                            decision.transitions[event].note == kNote);
        }
      }
      M3_EXPECT_FALSE(early_note_off);
    }
  }
}

M3_TEST(native_detector_coasts_the_last_valid_tuner_pitch_through_a_short_dropout) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 40U;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  const double frequency = m3::midi_to_frequency(kNote + 0.07, 440.0);
  m3::TunerVoice last_tracking;
  bool tracked = false;
  for (std::uint32_t sample = 0U; sample < 24000U; ++sample) {
    const double value = 0.20 * std::sin(
        6.28318530717958647692 * frequency * sample / kSampleRate);
    const m3::DetectorDecision decision = detector.process_sample(value);
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::tracking &&
        decision.tuner_snapshot.voices[0U].cents_valid) {
      last_tracking = decision.tuner_snapshot.voices[0U];
      tracked = true;
    }
  }
  M3_EXPECT_TRUE(tracked);

  bool coasted = false;
  bool note_off = false;
  for (std::uint32_t sample = 0U; sample < 12000U && !coasted; ++sample) {
    const m3::DetectorDecision decision = detector.process_sample(0.0);
    for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
      note_off = note_off ||
                 decision.transitions[event].kind ==
                     m3::TransitionKind::note_off;
    }
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::tracking &&
        decision.tuner_snapshot.voices[0U].cents_valid) {
      last_tracking = decision.tuner_snapshot.voices[0U];
    }
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::coasting) {
      const m3::TunerVoice& coast = decision.tuner_snapshot.voices[0U];
      coasted = true;
      M3_EXPECT_EQ(coast.midi_note, last_tracking.midi_note);
      M3_EXPECT_TRUE(coast.cents_valid);
      M3_EXPECT_EQ(coast.cents_q8, last_tracking.cents_q8);
      M3_EXPECT_TRUE(coast.confidence_q15 <= last_tracking.confidence_q15);
    }
  }
  M3_EXPECT_TRUE(coasted);
  M3_EXPECT_FALSE(note_off);
}

M3_TEST(native_detector_does_not_overwrite_retained_cents_with_an_invalid_frame) {
  m3::PolyphonicPitchDetector detector;
  const auto voices =
      m3::PolyphonicPitchDetectorTestAccess::snapshot_retention_sequence(
          detector);
  M3_EXPECT_TRUE(voices[0U].cents_valid);
  M3_EXPECT_EQ(voices[0U].state, m3::TunerVoiceState::tracking);
  M3_EXPECT_TRUE(voices[1U].cents_valid);
  M3_EXPECT_EQ(voices[1U].state, m3::TunerVoiceState::tracking);
  M3_EXPECT_EQ(voices[1U].cents_q8, voices[0U].cents_q8);
  M3_EXPECT_TRUE(voices[2U].cents_valid);
  M3_EXPECT_EQ(voices[2U].state, m3::TunerVoiceState::coasting);
  M3_EXPECT_EQ(voices[2U].cents_q8, voices[0U].cents_q8);
}

M3_TEST(native_detector_attack_hold_is_time_based_at_supported_sample_rates) {
  constexpr std::array<double, 4> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::uint8_t kNote = 40U;
  constexpr double kTwoPi = 6.28318530717958647692;
  double minimum_onset_seconds = std::numeric_limits<double>::max();
  double maximum_onset_seconds = 0.0;

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, 440.0);
    std::uint32_t note_on_sample = std::numeric_limits<std::uint32_t>::max();
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.12));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const auto decision = detector.process_sample(
          0.20 * std::sin(kTwoPi * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        if (decision.transitions[event].kind == m3::TransitionKind::note_on &&
            decision.transitions[event].note == kNote &&
            note_on_sample == std::numeric_limits<std::uint32_t>::max()) {
          note_on_sample = sample;
        }
      }
    }
    M3_EXPECT_TRUE(note_on_sample != std::numeric_limits<std::uint32_t>::max());
    if (note_on_sample != std::numeric_limits<std::uint32_t>::max()) {
      const double onset_seconds =
          static_cast<double>(note_on_sample) / sample_rate;
      minimum_onset_seconds = std::min(minimum_onset_seconds, onset_seconds);
      maximum_onset_seconds = std::max(maximum_onset_seconds, onset_seconds);
    }
  }

  M3_EXPECT_TRUE(maximum_onset_seconds - minimum_onset_seconds <= 0.002);
}

M3_TEST(native_detector_tracks_a_stiff_string_chord_through_sympathetic_leakage) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<std::uint8_t, 4U> kNotes{32U, 40U, 48U, 60U};
  constexpr std::array<double, 4U> kCents{-3.8, 2.1, -1.7, 4.4};
  constexpr std::array<double, 4U> kInharmonicity{0.00004, 0.00007, 0.00011,
                                                 0.00016};
  constexpr std::array<double, 4U> kAmplitude{0.034, 0.031, 0.029, 0.026};
  constexpr std::array<double, 6U> kPartialAmplitude{1.0, 0.31, 0.17, 0.10,
                                                     0.06, 0.035};

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 84U;
    config.max_polyphony = 4U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    std::array<bool, kNotes.size()> note_on{};
    bool unexpected_on = false;
    std::size_t stable_frames = 0U;
    std::size_t evaluated_frames = 0U;
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.65));
    const std::uint32_t stable_start =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.35));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const double attack = std::min(1.0, time / 0.006);
      const double decay = std::exp(-0.45 * time);
      double mixed = 0.0;
      for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
        const double fundamental = m3::midi_to_frequency(
            static_cast<double>(kNotes[voice]) + kCents[voice] / 100.0,
            440.0);
        const double base_stretch = std::sqrt(1.0 + kInharmonicity[voice]);
        for (std::size_t partial = 0U; partial < kPartialAmplitude.size();
             ++partial) {
          const double order = static_cast<double>(partial + 1U);
          const double stretch =
              std::sqrt(1.0 + kInharmonicity[voice] * order * order) /
              base_stretch;
          const double phase =
              0.29 * static_cast<double>(voice + 1U) +
              0.11 * order + kTwoPi * fundamental * order * stretch * time;
          mixed += kAmplitude[voice] * kPartialAmplitude[partial] * attack *
                   decay * std::sin(phase);
        }
      }
      // Weak resonances from two unsounded strings model body/pickup leakage.
      // They are real energy, but not strong independent note evidence.
      mixed += 0.0025 * attack *
               std::sin(kTwoPi * m3::midi_to_frequency(36.0, 440.0) * time +
                        0.83);
      mixed += 0.0020 * attack *
               std::sin(kTwoPi * m3::midi_to_frequency(56.0, 440.0) * time +
                        1.37);

      const m3::DetectorDecision decision = detector.process_sample(mixed);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.kind != m3::TransitionKind::note_on) {
          continue;
        }
        bool expected = false;
        for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
          if (transition.note == kNotes[voice]) {
            note_on[voice] = true;
            expected = true;
          }
        }
        unexpected_on = unexpected_on || !expected;
      }
      if (!decision.tuner_snapshot_ready || sample < stable_start) {
        continue;
      }
      ++evaluated_frames;
      std::array<bool, kNotes.size()> found{};
      bool only_expected = true;
      for (std::size_t observed = 0U;
           observed < decision.tuner_snapshot.voice_count; ++observed) {
        const std::uint8_t note =
            decision.tuner_snapshot.voices[observed].midi_note;
        bool expected = false;
        for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
          if (note == kNotes[voice]) {
            found[voice] = true;
            expected = true;
          }
        }
        only_expected = only_expected && expected;
      }
      if (only_expected &&
          std::all_of(found.begin(), found.end(), [](bool value) {
            return value;
          })) {
        ++stable_frames;
      }
    }
    for (const bool started : note_on) {
      M3_EXPECT_TRUE(started);
    }
    M3_EXPECT_FALSE(unexpected_on);
    M3_EXPECT_TRUE(evaluated_frames > 0U);
    M3_EXPECT_TRUE(stable_frames * 10U >= evaluated_frames * 9U);
  }
}

M3_TEST(native_detector_publishes_one_stable_physical_lane_per_m3_string) {
  constexpr double kSampleRate = 48000.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::TunerSnapshot final_snapshot;
  feed_realistic_string_chord(detector, m3::kM3OpenNotes, 36000U, nullptr,
                              &final_snapshot);

  std::array<bool, m3::kMaxVoices> found{};
  for (std::size_t voice = 0U; voice < final_snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = final_snapshot.voices[voice];
    M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
    if (observed.string_index < m3::kMaxVoices) {
      M3_EXPECT_FALSE(found[observed.string_index]);
      found[observed.string_index] = true;
      M3_EXPECT_EQ(observed.midi_note,
                   m3::kM3OpenNotes[observed.string_index]);
    }
  }
  for (const bool present : found) {
    M3_EXPECT_TRUE(present);
  }
}

M3_TEST(native_detector_keeps_realistic_fretted_chord_inside_each_string_range) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::array<std::uint8_t, m3::kMaxVoices> kFrettedNotes{
      39U, 42U, 45U, 48U, 51U, 54U, 57U, 60U};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  std::array<bool, m3::kMaxVoices> observed_string{};
  std::size_t checked_snapshots = 0U;
  for (std::uint32_t sample = 0U; sample < 48000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    double mixed = 0.0;
    for (std::size_t string = 0U; string < kFrettedNotes.size(); ++string) {
      mixed += realistic_string_sample(kFrettedNotes[string], string, time);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (!decision.tuner_snapshot_ready || sample < 24000U) {
      continue;
    }
    std::array<bool, m3::kMaxVoices> used_in_snapshot{};
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = decision.tuner_snapshot.voices[voice];
      if (observed.state != m3::TunerVoiceState::tracking) {
        continue;
      }
      M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
      if (observed.string_index >= m3::kMaxVoices) {
        continue;
      }
      M3_EXPECT_FALSE(used_in_snapshot[observed.string_index]);
      used_in_snapshot[observed.string_index] = true;
      observed_string[observed.string_index] = true;
      const std::uint8_t open = m3::kM3OpenNotes[observed.string_index];
      M3_EXPECT_TRUE(observed.midi_note >= open);
      M3_EXPECT_TRUE(static_cast<std::uint16_t>(observed.midi_note) <=
                     static_cast<std::uint16_t>(open) + config.max_fret);
      // This staircase chord gives each modeled physical string one distinct
      // fret. Its lane must not migrate as relative phase and beating evolve.
      M3_EXPECT_EQ(observed.midi_note,
                   kFrettedNotes[observed.string_index]);
    }
    ++checked_snapshots;
  }

  M3_EXPECT_TRUE(checked_snapshots > 0U);
  for (const bool present : observed_string) {
    M3_EXPECT_TRUE(present);
  }
}

M3_TEST(native_detector_separates_a_calibrated_detuned_unison_into_string_lanes) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kUnisonNote = 48U;
  constexpr double kLowStringCents = -3.5;
  constexpr double kOpenStringCents = 4.2;
  constexpr std::array<double, 4> kSampleRates{
      44100.0, 48000.0, 88200.0, 96000.0};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 59U;
    config.max_polyphony = 2U;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    m3::StringCalibrationBank bank;
    set_measured_string_profile(bank, 0U, 16U, kLowStringCents, kLowProfile);
    set_measured_string_profile(bank, 4U, 0U, kOpenStringCents, kOpenProfile);
    detector.set_calibration_bank(bank);

    m3::TunerSnapshot final_snapshot;
    std::array<bool, m3::kMaxVoices> midi_note_on{};
    std::array<bool, m3::kMaxVoices> midi_note_off{};
    std::size_t evaluated_frames = 0U;
    std::size_t stable_frames = 0U;
    const double low_frequency =
        m3::midi_to_frequency(kUnisonNote + kLowStringCents / 100.0, 440.0);
    const double open_frequency =
        m3::midi_to_frequency(kUnisonNote + kOpenStringCents / 100.0, 440.0);
    const std::uint32_t sample_count =
        static_cast<std::uint32_t>(std::lround(1.5 * sample_rate));
    const std::uint32_t stable_start =
        static_cast<std::uint32_t>(std::lround(0.75 * sample_rate));
    for (std::uint32_t sample = 0U; sample < sample_count; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const double low_phase = 0.17 + kTwoPi * low_frequency * time;
      const double open_phase = 1.03 + kTwoPi * open_frequency * time;
      double mixed = 0.0;
      for (std::size_t harmonic = 0U; harmonic < kLowProfile.size();
           ++harmonic) {
        const double partial = static_cast<double>(harmonic + 1U);
        mixed += 0.055 * kLowProfile[harmonic] *
                 std::sin(partial * low_phase + 0.11 * partial);
        mixed += 0.050 * kOpenProfile[harmonic] *
                 std::sin(partial * open_phase - 0.07 * partial);
      }
      const m3::DetectorDecision decision = detector.process_sample(mixed);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.note != kUnisonNote ||
            transition.voice_id >= m3::kMaxVoices) {
          continue;
        }
        if (transition.kind == m3::TransitionKind::note_on) {
          midi_note_on[transition.voice_id] = true;
        }
      }
      if (!decision.tuner_snapshot_ready) {
        continue;
      }
      final_snapshot = decision.tuner_snapshot;
      if (sample < stable_start) {
        continue;
      }
      ++evaluated_frames;
      bool low_string = false;
      bool open_string = false;
      bool only_unison_note = true;
      for (std::size_t voice = 0U;
           voice < decision.tuner_snapshot.voice_count; ++voice) {
        const m3::TunerVoice& observed =
            decision.tuner_snapshot.voices[voice];
        only_unison_note =
            only_unison_note && observed.midi_note == kUnisonNote;
        low_string = low_string || observed.string_index == 0U;
        open_string = open_string || observed.string_index == 4U;
      }
      if (decision.tuner_snapshot.voice_count == 2U && only_unison_note &&
          low_string && open_string) {
        ++stable_frames;
      }
    }

    std::array<bool, m3::kMaxVoices> found{};
    for (std::size_t voice = 0U; voice < final_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = final_snapshot.voices[voice];
      M3_EXPECT_EQ(observed.midi_note, kUnisonNote);
      M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
      if (observed.string_index < m3::kMaxVoices) {
        found[observed.string_index] = true;
      }
    }
    M3_EXPECT_EQ(final_snapshot.voice_count, 2U);
    M3_EXPECT_TRUE(found[0U]);
    M3_EXPECT_TRUE(found[4U]);
    M3_EXPECT_TRUE(evaluated_frames > 0U);
    M3_EXPECT_TRUE(stable_frames * 10U >= evaluated_frames * 9U);
    M3_EXPECT_TRUE(midi_note_on[0U]);
    M3_EXPECT_TRUE(midi_note_on[4U]);

    const std::uint32_t release_samples =
        static_cast<std::uint32_t>(std::lround(0.60 * sample_rate));
    for (std::uint32_t sample = 0U; sample < release_samples; ++sample) {
      const m3::DetectorDecision decision = detector.process_sample(0.0);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.kind == m3::TransitionKind::note_off &&
            transition.note == kUnisonNote &&
            transition.voice_id < m3::kMaxVoices) {
          midi_note_off[transition.voice_id] = true;
        }
      }
    }
    M3_EXPECT_TRUE(midi_note_off[0U]);
    M3_EXPECT_TRUE(midi_note_off[4U]);
  }
}

M3_TEST(native_detector_separates_calibrated_unison_frequencies_when_timbre_matches_one_string) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 40U;
  constexpr double kString8Cents = -42.0;
  constexpr double kString7Cents = -23.0;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      1.00, 0.20, 0.05, 0.01, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 38U;
  config.highest_note = 42U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 8U, kString8Cents, kProfile);
  set_measured_string_profile(bank, 1U, 4U, kString7Cents, kProfile);
  detector.set_calibration_bank(bank);

  const double frequency8 =
      m3::midi_to_frequency(kNote + kString8Cents / 100.0, 440.0);
  const double frequency7 =
      m3::midi_to_frequency(kNote + kString7Cents / 100.0, 440.0);
  std::uint32_t evaluated = 0U;
  std::uint32_t correct = 0U;
  std::array<std::array<std::uint32_t, 256U>, 5U> observed_masks{};
  constexpr std::uint32_t kSamples = 264000U;
  constexpr std::uint32_t kEvaluationStart = 192000U;
  for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double phase8 = kTwoPi * frequency8 * time + 0.17;
    const double phase7 = kTwoPi * frequency7 * time + 1.03;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kProfile.size(); ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      mixed += 0.050 * kProfile[harmonic] *
               std::sin(partial * phase8 + 0.07 * partial);
      mixed += 0.045 * kProfile[harmonic] *
               std::sin(partial * phase7 - 0.11 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (!decision.tuner_snapshot_ready || sample < kEvaluationStart) {
      continue;
    }
    ++evaluated;
    std::uint8_t lanes = 0U;
    bool only_note = decision.tuner_snapshot.voice_count == 2U;
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = decision.tuner_snapshot.voices[voice];
      only_note = only_note && observed.midi_note == kNote;
      if (observed.string_index < m3::kMaxVoices) {
        lanes = static_cast<std::uint8_t>(
            lanes | static_cast<std::uint8_t>(1U << observed.string_index));
      }
    }
    if (only_note && lanes == 3U) {
      ++correct;
    }
    for (std::uint8_t note = config.lowest_note;
         note <= config.highest_note; ++note) {
      std::uint8_t note_lanes = 0U;
      for (std::size_t voice = 0U;
           voice < decision.tuner_snapshot.voice_count; ++voice) {
        const m3::TunerVoice& observed = decision.tuner_snapshot.voices[voice];
        if (observed.midi_note == note &&
            observed.string_index < m3::kMaxVoices) {
          note_lanes = static_cast<std::uint8_t>(
              note_lanes | static_cast<std::uint8_t>(
                               1U << observed.string_index));
        }
      }
      ++observed_masks[note - config.lowest_note][note_lanes];
    }
  }
  const m3::PolyphonicPitchDetectorTestAccess::FineProbe fine =
      m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 2U);
  if (correct * 10U < evaluated * 9U) {
    std::fprintf(stderr,
                 "identical-timbre unison evaluated=%u correct=%u fine=%u "
                 "pending=%u/%u dev=%.4f multi=%d beat=%d\n",
                 evaluated, correct, fine.members, fine.pending,
                 fine.pending_count, fine.frequency_deviation_hz,
                 fine.multi_source_observed ? 1 : 0,
                 fine.beat_valid ? 1 : 0);
    for (std::size_t candidate = 0U; candidate < observed_masks.size();
         ++candidate) {
      const m3::PolyphonicPitchDetectorTestAccess::PhaseProbe phase =
          m3::PolyphonicPitchDetectorTestAccess::phase_probe(detector,
                                                              candidate);
      const m3::PolyphonicPitchDetectorTestAccess::FineProbe candidate_fine =
          m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector,
                                                             candidate);
      std::fprintf(stderr,
                   " candidate=%zu cents=%.3f valid=%d updates=%u active=%d "
                   "string=%u fine=%u pending=%u/%u history=%u multi=%d beat=%d\n",
                   candidate + config.lowest_note, phase.cents,
                   phase.valid ? 1 : 0, phase.accepted_updates,
                   phase.active ? 1 : 0, phase.assigned_string,
                   candidate_fine.members, candidate_fine.pending,
                   candidate_fine.pending_count,
                   candidate_fine.history_count,
                   candidate_fine.multi_source_observed ? 1 : 0,
                   candidate_fine.beat_valid ? 1 : 0);
      for (std::size_t mask = 1U; mask < observed_masks[candidate].size();
           ++mask) {
        if (observed_masks[candidate][mask] != 0U) {
          std::fprintf(stderr, " note=%zu mask=%zu frames=%u\n",
                       candidate + config.lowest_note, mask,
                       observed_masks[candidate][mask]);
        }
      }
    }
  }
  M3_EXPECT_TRUE(evaluated > 0U);
  M3_EXPECT_TRUE(correct * 10U >= evaluated * 9U);
}

M3_TEST(native_detector_separates_recorded_c3_calibration_members) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 52U;
  struct RecordedSource final {
    std::size_t string{};
    std::size_t fret{};
    double cents{};
    double phase{};
    std::array<double, m3::kCalibrationHarmonicCount> profile{};
  };
  // These are the measured E3 members from the physical NYXL 9--80 bank:
  // string 5 fret 8, string 4 fret 4, and string 3 open.  In particular,
  // strings 5 and 3 are only 0.399 Hz apart, so this guards the closest real
  // pair rather than a conveniently separated synthetic pair.
  constexpr std::array<RecordedSource, 3U> kSources{{
      {3U, 8U, 0.63671875, 0.31,
       {1.0, 0.2409, 0.0180, 0.0057, 0.0, 0.0}},
      {4U, 4U, 15.99609375, 1.17,
       {1.0, 0.4874, 0.1966, 0.0153, 0.0, 0.0}},
      {5U, 0U, 4.81640625, 2.09,
       {1.0, 0.4142, 0.1791, 0.0446, 0.0, 0.0384}},
  }};
  constexpr std::array<std::uint8_t, 4U> kMemberMasks{
      static_cast<std::uint8_t>((1U << 3U) | (1U << 5U)),
      static_cast<std::uint8_t>((1U << 4U) | (1U << 5U)),
      static_cast<std::uint8_t>((1U << 3U) | (1U << 4U)),
      static_cast<std::uint8_t>((1U << 3U) | (1U << 4U) | (1U << 5U)),
  };

  for (const std::uint8_t member_mask : kMemberMasks) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 50U;
    config.highest_note = 54U;
    config.max_polyphony = member_mask == 56U ? 3U : 2U;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    m3::StringCalibrationBank bank;
    for (const RecordedSource& source : kSources) {
      set_measured_string_profile(bank, source.string, source.fret,
                                  source.cents, source.profile);
    }
    detector.set_calibration_bank(bank);

    std::uint32_t evaluated = 0U;
    std::uint32_t correct = 0U;
    constexpr std::uint32_t kSamples = 336000U;
    constexpr std::uint32_t kEvaluationStart = 216000U;
    for (std::uint32_t sample = 0U; sample < kSamples; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      double mixed = 0.0;
      for (const RecordedSource& source : kSources) {
        if ((member_mask & (1U << source.string)) == 0U) {
          continue;
        }
        const double frequency = m3::midi_to_frequency(
            kNote + source.cents / 100.0, 440.0);
        const double phase = kTwoPi * frequency * time + source.phase;
        for (std::size_t harmonic = 0U;
             harmonic < source.profile.size(); ++harmonic) {
          const double partial = static_cast<double>(harmonic + 1U);
          mixed += 0.035 * source.profile[harmonic] *
                   std::sin(partial * phase +
                            0.09 * partial * source.phase);
        }
      }
      const m3::DetectorDecision decision = detector.process_sample(mixed);
      if (!decision.tuner_snapshot_ready || sample < kEvaluationStart) {
        continue;
      }
      ++evaluated;
      std::uint8_t observed_mask = 0U;
      bool only_note = true;
      for (std::size_t voice_index = 0U;
           voice_index < decision.tuner_snapshot.voice_count;
           ++voice_index) {
        const m3::TunerVoice& voice =
            decision.tuner_snapshot.voices[voice_index];
        only_note = only_note && voice.midi_note == kNote;
        if (voice.string_index < m3::kMaxVoices) {
          observed_mask = static_cast<std::uint8_t>(
              observed_mask | (1U << voice.string_index));
        }
      }
      if (only_note && observed_mask == member_mask) {
        ++correct;
      }
    }
    const m3::PolyphonicPitchDetectorTestAccess::FineProbe fine =
        m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 2U);
    if (correct * 10U < evaluated * 9U) {
      std::fprintf(stderr,
                   "recorded-c3 mask=%u evaluated=%u correct=%u fine=%u "
                   "pending=%u/%u dev=%.4f multi=%d beat=%d energies="
                   "%.4g,%.4g,%.4g\n",
                   member_mask, evaluated, correct, fine.members,
                   fine.pending, fine.pending_count,
                   fine.frequency_deviation_hz,
                   fine.multi_source_observed ? 1 : 0,
                   fine.beat_valid ? 1 : 0, fine.component_energy[3U],
                   fine.component_energy[4U],
                   fine.component_energy[5U]);
    }
    M3_EXPECT_TRUE(evaluated > 0U);
    M3_EXPECT_TRUE(correct * 10U >= evaluated * 9U);
  }
}

M3_TEST(native_detector_keeps_a_calibrated_harmonic_fingerprint_when_detuned) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::array<double, 3U> kOffsetsCents{0.0, -10.0, 10.0};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kBrightProfile{
      1.00, 1.00, 1.00, 1.00, 0.00, 0.00};
  // This darker lane closely matches the uncorrected fixed-Hz resonator
  // response of the same bright source at ten cents off centre.
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kDarkProfile{
      1.00, 0.00, 0.00, 0.00, 0.00, 0.00};

  for (const double cents : kOffsetsCents) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 84U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    m3::StringCalibrationBank bank;
    // Cover every physical lane that can play C4. The test is specifically
    // about choosing the calibrated bright fingerprint from a complete set,
    // not about allowing a partial session to bias a fresh assignment.
    set_measured_string_profile(bank, 1U, 24U, 0.0, kDarkProfile);
    set_measured_string_profile(bank, 2U, 20U, 0.0, kDarkProfile);
    set_measured_string_profile(bank, 3U, 16U, 0.0, kDarkProfile);
    set_measured_string_profile(bank, 4U, 12U, 0.0, kDarkProfile);
    set_measured_string_profile(bank, 5U, 8U, 0.0, kDarkProfile);
    set_measured_string_profile(bank, 6U, 4U, 0.0, kBrightProfile);
    set_measured_string_profile(bank, 7U, 0U, 0.0, kDarkProfile);
    detector.set_calibration_bank(bank);

    const double frequency =
        m3::midi_to_frequency(static_cast<double>(kNote) + cents / 100.0,
                              440.0);
    std::uint8_t observed_string = m3::kUnassignedTunerString;
    bool tracked = false;
    std::uint32_t settled_tracking_frames = 0U;
    std::uint32_t settled_correct_frames = 0U;
    for (std::uint32_t sample = 0U; sample < 48000U; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      const double phase = kTwoPi * frequency * time;
      const double value =
          0.050 * (std::sin(phase) + std::sin(2.0 * phase + 0.23) +
                   std::sin(3.0 * phase - 0.41) +
                   std::sin(4.0 * phase + 0.67));
      const m3::DetectorDecision decision = detector.process_sample(value);
      if (!decision.tuner_snapshot_ready) {
        continue;
      }
      for (std::size_t voice = 0U;
           voice < decision.tuner_snapshot.voice_count; ++voice) {
        const m3::TunerVoice& observed =
            decision.tuner_snapshot.voices[voice];
        if (observed.state == m3::TunerVoiceState::tracking &&
            observed.midi_note == kNote) {
          tracked = true;
          observed_string = observed.string_index;
          if (sample >= 12000U) {
            ++settled_tracking_frames;
            if (observed.string_index == 6U) {
              ++settled_correct_frames;
            }
          }
        }
      }
    }
    M3_EXPECT_TRUE(tracked);
    M3_EXPECT_EQ(observed_string, 6U);
    M3_EXPECT_TRUE(settled_tracking_frames > 0U);
    M3_EXPECT_TRUE(settled_correct_frames * 10U >=
                   settled_tracking_frames * 9U);
  }
}

M3_TEST(native_detector_clears_prior_harmonic_memory_when_a_note_activates) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const double remaining =
      m3::PolyphonicPitchDetectorTestAccess::harmonic_memory_after_note_on(
          detector, 8U);
  M3_EXPECT_NEAR(remaining, 0.0, 0.0);
}

M3_TEST(native_detector_partial_detuning_changes_profile_not_selector_energy) {
  m3::PolyphonicPitchDetector detector;
  const auto energies = m3::PolyphonicPitchDetectorTestAccess::
      selector_and_profile_energy_with_partial_detuning(detector);
  M3_EXPECT_TRUE(energies[0U] > 1.0);
  M3_EXPECT_TRUE(energies[1U] > energies[0U]);
}

M3_TEST(native_detector_does_not_prearm_a_fresh_unison_from_global_signal_age) {
  constexpr std::uint8_t kNote = 48U;
  constexpr std::uint8_t kPrimaryString = 4U;
  constexpr std::uint8_t kSecondString = 0U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, kPrimaryString, 0U, 4.2, kOpenProfile);
  set_measured_string_profile(bank, kSecondString, 16U, -3.5, kLowProfile);
  detector.set_calibration_bank(bank);

  const std::uint8_t mask =
      m3::PolyphonicPitchDetectorTestAccess::fresh_candidate_unison_mask(
          detector, kNote - config.lowest_note, kPrimaryString,
          kSecondString);
  M3_EXPECT_EQ(mask, static_cast<std::uint8_t>(1U << kPrimaryString));
}

namespace {

constexpr std::uint8_t kSharedUnisonNote = 48U;
constexpr std::uint8_t kSharedUnisonPrimary = 4U;  // C3 open.
constexpr std::uint8_t kSharedUnisonSecond = 0U;   // G#1 string, fret 16.

void configure_calibrated_unison(m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 3U;
  config.max_fret = 24U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, kSharedUnisonPrimary, 0U, 4.2,
                              kOpenProfile);
  set_measured_string_profile(bank, kSharedUnisonSecond, 16U, -3.5,
                              kLowProfile);
  detector.set_calibration_bank(bank);
}

void add_third_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kMiddleProfile{
      0.42, 0.31, 0.68, 0.19, 0.07, 0.03};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kThirdString = 2U;  // E2 string, fret 8 => C3.
  set_measured_string_profile(bank, kThirdString, 8U, 1.1, kMiddleProfile);
  detector.set_calibration_bank(bank);
}

void add_fourth_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      0.55, 0.18, 0.22, 0.58, 0.10, 0.04};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kFourthString = 1U;  // C2 string, fret 12 => C3.
  set_measured_string_profile(bank, kFourthString, 12U, -0.8, kProfile);
  detector.set_calibration_bank(bank);
}

void add_fifth_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      0.36, 0.55, 0.17, 0.24, 0.49, 0.08};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kFifthString = 3U;  // G#2 string, fret 4 => C3.
  set_measured_string_profile(bank, kFifthString, 4U, 2.0, kProfile);
  detector.set_calibration_bank(bank);
}

void configure_calibrated_high_unison(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::uint8_t kNote = 56U;  // G#3, playable on strings 0..6.
  constexpr std::array<std::array<double, m3::kCalibrationHarmonicCount>, 7U>
      kProfiles{{
          {{1.00, 0.14, 0.06, 0.025, 0.010, 0.004}},
          {{0.78, 0.30, 0.12, 0.050, 0.020, 0.008}},
          {{0.55, 0.24, 0.61, 0.150, 0.060, 0.020}},
          {{0.40, 0.68, 0.21, 0.100, 0.040, 0.015}},
          {{0.65, 0.50, 0.28, 0.320, 0.080, 0.025}},
          {{0.32, 0.42, 0.18, 0.600, 0.200, 0.050}},
          {{0.50, 0.58, 0.38, 0.160, 0.450, 0.120}},
      }};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 7U;
  config.max_fret = 24U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
    const std::size_t fret = kNote - m3::kM3OpenNotes[string];
    set_measured_string_profile(bank, string, fret,
                                static_cast<double>(string) - 3.0,
                                kProfiles[string]);
  }
  detector.set_calibration_bank(bank);
}

}  // namespace

M3_TEST(native_detector_never_infers_a_unison_lane_owned_by_a_coasting_voice) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 0U;  // G#1, open on the second string.
  constexpr std::uint8_t kBoth = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  // Control: without a live owner, the calibrated mixture is a unison.
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kSharedUnisonSecond,
                   false, 3U),
               kBoth);

  // A coasting voice still owns its string lane and per-voice MIDI channel
  // until note-off. The inferred unison must not claim that lane: a second
  // note-on on a live voice identity makes the ledger block all output.
  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kSharedUnisonSecond,
                   true, 3U, &snapshot),
               static_cast<std::uint8_t>(1U << kSharedUnisonPrimary));
  std::uint8_t published_lanes = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const std::uint8_t bit = static_cast<std::uint8_t>(
        1U << snapshot.voices[voice].string_index);
    M3_EXPECT_TRUE((published_lanes & bit) == 0);
    published_lanes = static_cast<std::uint8_t>(published_lanes | bit);
  }
  M3_EXPECT_EQ(snapshot.voice_count, 2U);
}

M3_TEST(native_detector_reports_when_a_valid_fine_group_conflicts_with_an_owner) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kOwner = 0U;
  constexpr std::uint8_t kThirdString = 2U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << kThirdString));
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);

  M3_EXPECT_EQ(Access::fine_group_disposition_beside_owner(
                   detector, kUnison, kSharedUnisonPrimary, kMembers, kOwner,
                   kThirdString, 5U),
               m3::FineGroupDisposition::conflicts_other_owned);
}

M3_TEST(native_detector_counts_coasting_lanes_against_the_unison_budget) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 8U;         // E2, open on string 2.
  constexpr std::uint8_t kCoastingString = 2U;  // Not the unison lane.
  constexpr std::uint8_t kBoth = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  // One selected voice plus one coasting voice already fill a two-voice
  // limit, so an inferred third lane would push a live voice out of the
  // bounded tuner snapshot.
  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kCoastingString, true, 2U,
                   &snapshot),
               static_cast<std::uint8_t>(1U << kSharedUnisonPrimary));
  M3_EXPECT_EQ(snapshot.voice_count, 2U);
  bool coasting_published = false;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    coasting_published = coasting_published ||
                         snapshot.voices[voice].string_index == kCoastingString;
  }
  M3_EXPECT_TRUE(coasting_published);

  // With room for a third lane the same evidence is still a unison.
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kCoastingString, true, 3U),
               kBoth);
}

M3_TEST(native_detector_groups_inferred_unison_lanes_under_one_pitch_estimate) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 8U;
  constexpr std::uint8_t kCoastingString = 2U;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  m3::TunerSnapshot snapshot;
  static_cast<void>(Access::unison_mask_beside_coasting_voice(
      detector, kUnison, kSharedUnisonPrimary, kSharedUnisonSecond, kCoasting,
      kCoastingString, true, 3U, &snapshot));
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  std::size_t shared = 0U;
  std::uint8_t shared_group = m3::kUnassignedPitchEvidenceGroup;
  constexpr std::uint8_t kUnisonMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = snapshot.voices[voice];
    // Both unison lanes carry one merged pitch estimate. The frame must say
    // so rather than implying two independent per-string measurements; the
    // independent coasting string is not shared.
    const bool unison_lane = observed.midi_note == kSharedUnisonNote;
    M3_EXPECT_EQ(observed.shares_pitch_evidence(), unison_lane);
    if (unison_lane) {
      M3_EXPECT_EQ(observed.pitch_evidence_member_mask, kUnisonMembers);
      if (shared_group == m3::kUnassignedPitchEvidenceGroup) {
        shared_group = observed.pitch_evidence_group_id;
      }
      M3_EXPECT_EQ(observed.pitch_evidence_group_id, shared_group);
    } else {
      M3_EXPECT_EQ(observed.pitch_evidence_member_mask,
                   static_cast<std::uint8_t>(1U << kCoastingString));
      M3_EXPECT_TRUE(observed.pitch_evidence_group_id != shared_group);
    }
    shared += observed.shares_pitch_evidence() ? 1U : 0U;
  }
  M3_EXPECT_EQ(shared, 2U);
  M3_EXPECT_TRUE(shared_group != m3::kUnassignedPitchEvidenceGroup);
}

M3_TEST(native_detector_pitch_evidence_group_represents_three_string_unison) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kMembers =
      static_cast<std::uint8_t>((1U << 0U) | (1U << 4U) | (1U << 7U));

  const m3::TunerSnapshot snapshot =
      Access::snapshot_for_assigned_string_group(
          detector, kCandidate, kSharedUnisonPrimary, kMembers, 3U);
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  const std::uint8_t group = snapshot.voices[0].pitch_evidence_group_id;
  M3_EXPECT_TRUE(group != m3::kUnassignedPitchEvidenceGroup);
  std::uint8_t published_members = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = snapshot.voices[voice];
    M3_EXPECT_TRUE(observed.shares_pitch_evidence());
    M3_EXPECT_EQ(observed.pitch_evidence_group_id, group);
    M3_EXPECT_EQ(observed.pitch_evidence_member_mask, kMembers);
    published_members = static_cast<std::uint8_t>(
        published_members | (1U << observed.string_index));
  }
  M3_EXPECT_EQ(published_members, kMembers);
}

M3_TEST(native_detector_infers_three_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kThirdString = 2U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << kThirdString));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kSharedUnisonPrimary, kMembers, 3U,
                   &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_infers_three_calibrated_strings_from_profile_and_beat_evidence) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kThirdString = 2U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << kThirdString));

  const std::uint8_t inferred = Access::inferred_group_mask(
      detector, kCandidate, kSharedUnisonPrimary, kMembers, 3U, nullptr,
      false);
  if (inferred != kMembers) {
    std::fprintf(stderr, "profile+beat group inferred=%u expected=%u\n",
                 inferred, kMembers);
  }
  M3_EXPECT_EQ(inferred, kMembers);
}

M3_TEST(native_detector_infers_four_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  add_fourth_calibrated_unison_string(detector);
  // Keep a fifth, distinct template available so this also proves the fitter
  // does not increase the group merely because another calibrated lane exists.
  add_fifth_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << 2U) | (1U << 1U));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kSharedUnisonPrimary, kMembers, 4U,
                   &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 4U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_does_not_expand_one_high_calibrated_string_beyond_the_supported_unison_limit) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_high_unison(detector);
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kCandidate = kNote - 32U;
  constexpr std::uint8_t kPrimary = 6U;
  constexpr std::uint8_t kMember = static_cast<std::uint8_t>(1U << kPrimary);

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kPrimary, kMember, 7U, &snapshot),
               kMember);
  M3_EXPECT_EQ(snapshot.voice_count, 1U);
  M3_EXPECT_EQ(snapshot.voices[0].pitch_evidence_member_mask, kMember);
  M3_EXPECT_FALSE(snapshot.voices[0].shares_pitch_evidence());
}

M3_TEST(native_detector_does_not_bias_assignment_toward_a_lone_calibrated_lane) {
  constexpr std::uint8_t kNote = 40U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      1.00, 0.20, 0.08, 0.03, 0.01, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector baseline;
  M3_EXPECT_TRUE(baseline.configure(48000.0, config));
  const std::uint8_t baseline_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          baseline, kNote, kProfile);
  M3_EXPECT_EQ(baseline_string, 2U);

  m3::PolyphonicPitchDetector partially_calibrated;
  M3_EXPECT_TRUE(partially_calibrated.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 1U, 4U, 0.0, kProfile);
  partially_calibrated.set_calibration_bank(bank);
  const std::uint8_t calibrated_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          partially_calibrated, kNote, kProfile);

  M3_EXPECT_EQ(calibrated_string, baseline_string);
}

M3_TEST(native_detector_incomplete_two_string_calibration_does_not_override_range_assignment) {
  constexpr std::uint8_t kNote = 40U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kObserved{
      1.00, 0.20, 0.08, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kDifferent{
      0.05, 0.10, 0.20, 0.40, 0.80, 1.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector baseline;
  M3_EXPECT_TRUE(baseline.configure(48000.0, config));
  const std::uint8_t baseline_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          baseline, kNote, kObserved);
  M3_EXPECT_EQ(baseline_string, 2U);

  m3::PolyphonicPitchDetector partially_calibrated;
  M3_EXPECT_TRUE(partially_calibrated.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 8U, 0.0, kDifferent);
  set_measured_string_profile(bank, 1U, 4U, 0.0, kObserved);
  partially_calibrated.set_calibration_bank(bank);
  const std::uint8_t calibrated_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          partially_calibrated, kNote, kObserved);

  M3_EXPECT_EQ(calibrated_string, baseline_string);
}

M3_TEST(native_detector_uses_a_complete_calibration_to_identify_a_high_fret_lane) {
  constexpr std::uint8_t kNote = 70U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      1.00, 0.00, 0.00, 0.00, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 4U, 22U, -3.94, kProfile);
  set_measured_string_profile(bank, 5U, 18U, 1.53, kProfile);
  set_measured_string_profile(bank, 6U, 14U, 1.87, kProfile);
  set_measured_string_profile(bank, 7U, 10U, 5.41, kProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   assigned_string_for_profile_and_cents(
                       detector, kNote, kProfile, 2.89),
               6U);
}

M3_TEST(native_detector_settled_calibration_uses_stable_harmonic_shape) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kDistractor{
      0.224063897, 0.488057200, 0.263422171,
      0.707378011, 0.117363964, 0.357835647};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kTrueString{
      0.367280411, 0.620195905, 0.202189861,
      0.584716949, 0.133286571, 0.282705129};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kObserved{
      0.304041132, 0.553912096, 0.166730321,
      0.674453571, 0.145136281, 0.311430923};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, 0.0, kDistractor);
  set_measured_string_profile(bank, 1U, 0U, 0.0, kTrueString);
  bank.points[0U][4U].confidence_q15 = 26214U;
  bank.points[1U][0U].confidence_q15 = 26214U;
  detector.set_calibration_bank(bank);

  const double distractor = m3::PolyphonicPitchDetectorTestAccess::
      settled_calibration_similarity_for_profile(detector, kNote, 0U,
                                                 kObserved);
  const double true_string = m3::PolyphonicPitchDetectorTestAccess::
      settled_calibration_similarity_for_profile(detector, kNote, 1U,
                                                 kObserved);
  M3_EXPECT_TRUE(true_string > distractor);
}

M3_TEST(native_detector_string_posterior_retains_alternatives_until_onset) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kFretted{
      1.00, 0.18, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpen{
      0.66, 0.62, 0.31, 0.15, 0.06, 0.02};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, 0.0, kFretted);
  set_measured_string_profile(bank, 1U, 0U, 0.0, kOpen);
  detector.set_calibration_bank(bank);

  const auto sequence =
      m3::PolyphonicPitchDetectorTestAccess::string_posterior_sequence(
          detector, kNote, kFretted, kOpen);
  M3_EXPECT_EQ(sequence[0U], 0U);
  M3_EXPECT_EQ(sequence[1U], 0U);
  M3_EXPECT_EQ(sequence[2U], 1U);
}

M3_TEST(native_detector_complete_calibration_does_not_force_a_fresh_note_onto_a_mismatched_open_string) {
  // Physical walk regression: C2 plucked at string 8 fret 4 was routed for
  // whole holds to the open C2 lane because the open-string prior ignored a
  // complete calibration whose fingerprints identified the fretted string.
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kFrettedProfile{
      0.91, 0.31, 0.14, 0.05, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.72, 0.50, 0.31, 0.18, 0.09, 0.04};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, 0.0, kFrettedProfile);
  set_measured_string_profile(bank, 1U, 0U, 0.0, kOpenProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   assigned_string_for_profile_and_cents(
                       detector, kNote, kFrettedProfile, 0.0),
               0U);
  // The open-string prior still identifies an open string whose own
  // calibrated fingerprint matches.
  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   assigned_string_for_profile_and_cents(
                       detector, kNote, kOpenProfile, 0.0),
               1U);
}

M3_TEST(native_detector_learns_one_shared_tuning_offset_from_distinctive_string_timbre) {
  constexpr std::array<std::size_t, 3U> kStrings{4U, 5U, 6U};
  constexpr std::array<double, 3U> kLearnedCents{-2.0, 1.0, 6.0};
  constexpr std::array<std::array<double, m3::kCalibrationHarmonicCount>, 3U>
      kProfiles{{
          {0.91, 0.31, 0.14, 0.05, 0.01, 0.00},
          {0.81, 0.42, 0.24, 0.08, 0.02, 0.01},
          {0.72, 0.50, 0.31, 0.18, 0.09, 0.04},
      }};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  m3::StringCalibrationBank bank;
  for (std::size_t index = 0U; index < kStrings.size(); ++index) {
    set_measured_string_profile(bank, kStrings[index], 0U,
                                kLearnedCents[index], kProfiles[index]);
  }
  detector.set_calibration_bank(bank);

  double learned = 0.0;
  for (std::size_t index = 0U; index < kStrings.size(); ++index) {
    learned = m3::PolyphonicPitchDetectorTestAccess::
        learned_common_tuning_offset_for_profile_and_cents(
            detector, m3::kM3OpenNotes[kStrings[index]], kProfiles[index],
            kLearnedCents[index] + 3.0, 1200U);
    if (index + 1U < kStrings.size()) {
      M3_EXPECT_NEAR(learned, 0.0, 0.01);
    }
  }
  M3_EXPECT_NEAR(learned, 3.0, 0.10);
}

M3_TEST(native_detector_does_not_learn_global_tuning_from_fretted_intonation) {
  constexpr std::array<std::size_t, 3U> kStrings{3U, 4U, 5U};
  constexpr std::size_t kFret = 4U;
  constexpr std::array<std::array<double, m3::kCalibrationHarmonicCount>, 3U>
      kProfiles{{
          {0.91, 0.31, 0.14, 0.05, 0.01, 0.00},
          {0.81, 0.42, 0.24, 0.08, 0.02, 0.01},
          {0.72, 0.50, 0.31, 0.18, 0.09, 0.04},
      }};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  m3::StringCalibrationBank bank;
  for (std::size_t index = 0U; index < kStrings.size(); ++index) {
    set_measured_string_profile(bank, kStrings[index], kFret, 6.0,
                                kProfiles[index]);
  }
  detector.set_calibration_bank(bank);

  double learned = 0.0;
  for (std::size_t index = 0U; index < kStrings.size(); ++index) {
    learned = m3::PolyphonicPitchDetectorTestAccess::
        learned_common_tuning_offset_for_profile_and_cents(
            detector,
            static_cast<std::uint8_t>(m3::kM3OpenNotes[kStrings[index]] +
                                      kFret),
            kProfiles[index], 9.0, 1200U);
  }
  M3_EXPECT_NEAR(learned, 0.0, 0.01);
}

M3_TEST(native_detector_releases_a_stale_lane_when_physical_fret_evidence_disagrees) {
  constexpr std::uint8_t kNote = 56U;
  struct RecordedPoint final {
    std::size_t string{};
    std::size_t fret{};
    double cents{};
    std::array<double, m3::kCalibrationHarmonicCount> profile{};
  };
  // Exact note-56 rows from the physical A4=440 calibration. The thickest
  // string's 24th fret and the seventh string's open note are both musically
  // legal, but their measured pitch/timbre corridors are not interchangeable.
  constexpr std::array<RecordedPoint, 7U> kPoints{{
      {0U, 24U, 6.11328125, {0.999985, 0.005524, 0.0, 0.0, 0.0, 0.0}},
      {1U, 20U, -17.1796875, {0.999802, 0.019918, 0.0, 0.0, 0.0, 0.0}},
      {2U, 16U, -17.21875,
       {0.999756, 0.021396, 0.005524, 0.0, 0.0, 0.0}},
      {3U, 12U, -5.40234375, {0.999542, 0.029750, 0.0, 0.0, 0.0, 0.0}},
      {4U, 8U, 11.5703125,
       {0.992172, 0.124144, 0.007813, 0.011049, 0.0, 0.0}},
      {5U, 4U, 3.73828125,
       {0.975593, 0.218055, 0.025912, 0.0, 0.0, 0.0}},
      {6U, 0U, 4.8046875,
       {0.941461, 0.161629, 0.292739, 0.042433, 0.0, 0.005524}},
  }};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 54U;
  config.highest_note = 58U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  for (const RecordedPoint& point : kPoints) {
    set_measured_string_profile(bank, point.string, point.fret, point.cents,
                                point.profile);
  }
  detector.set_calibration_bank(bank);

  const std::uint8_t assigned =
      m3::PolyphonicPitchDetectorTestAccess::
          reassigned_settled_string_for_profile_and_cents(
              detector, kNote, 6U, kPoints[0U].profile,
              kPoints[0U].cents);
  M3_EXPECT_EQ(assigned, 0U);
}

M3_TEST(native_detector_does_not_reassign_a_lane_after_polyphonic_context) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kFrettedProfile{
      1.00, 0.05, 0.01, 0.00, 0.00, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.72, 0.66, 0.20, 0.03, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, -8.0, kFrettedProfile);
  set_measured_string_profile(bank, 1U, 0U, 8.0, kOpenProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   reassigned_settled_string_for_profile_and_cents(
                       detector, kNote, 1U, kFrettedProfile, -8.0, true),
               1U);
}

M3_TEST(native_detector_inactive_harmonic_does_not_block_lane_correction) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kFrettedProfile{
      1.00, 0.05, 0.01, 0.00, 0.00, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.72, 0.66, 0.20, 0.03, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, -8.0, kFrettedProfile);
  set_measured_string_profile(bank, 1U, 0U, 8.0, kOpenProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   reassigned_settled_string_for_profile_and_cents(
                       detector, kNote, 1U, kFrettedProfile, -8.0, false,
                       true),
               0U);
}

M3_TEST(native_detector_upper_harmonic_voice_does_not_block_lower_lane_correction) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kFrettedProfile{
      1.00, 0.05, 0.01, 0.00, 0.00, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.72, 0.66, 0.20, 0.03, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, -8.0, kFrettedProfile);
  set_measured_string_profile(bank, 1U, 0U, 8.0, kOpenProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   reassigned_settled_string_for_profile_and_cents(
                       detector, kNote, 1U, kFrettedProfile, -8.0, false,
                       true, true),
               0U);
}

M3_TEST(native_detector_physical_cents_override_articulation_timbre_drift) {
  constexpr std::uint8_t kNote = 61U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kObserved{
      0.004483896, 0.004454124, 0.001050133, 0.000370557, 0.0, 0.0};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(
      bank, 2U, 21U, -13.402,
      {0.996694537, 0.081240384, 0.0, 0.0, 0.0, 0.0});
  set_measured_string_profile(
      bank, 3U, 17U, -8.840,
      {0.999899995, 0.014142136, 0.0, 0.0, 0.0, 0.0});
  set_measured_string_profile(
      bank, 4U, 13U, 3.766,
      {0.993629710, 0.112694277, 0.0, 0.0, 0.0, 0.0});
  set_measured_string_profile(
      bank, 5U, 9U, -0.844,
      {0.999649939, 0.026457513, 0.0, 0.0, 0.0, 0.0});
  set_measured_string_profile(
      bank, 6U, 5U, 6.551,
      {0.831985577, 0.535537114, 0.144568323, 0.010000000, 0.010000000,
       0.0});
  set_measured_string_profile(
      bank, 7U, 1U, 14.336,
      {0.995690715, 0.051961524, 0.074833148, 0.017320508, 0.0, 0.0});
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   reassigned_settled_string_for_profile_and_cents(
                       detector, kNote, 6U, kObserved, 15.503),
               7U);
}

M3_TEST(native_detector_uses_measured_cents_to_stabilize_nearby_string_profiles) {
  constexpr std::uint8_t kNote = 36U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kTrueProfile{
      1.00, 0.20, 0.00, 0.00, 0.00, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kNearbyProfile{
      1.00, 0.29, 0.00, 0.00, 0.00, 0.00};
  // A different pick position can temporarily resemble the neighbouring
  // string even though the stable measured pitch remains in this string's
  // per-fret corridor.
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kObserved{
      1.00, 0.60, 0.00, 0.00, 0.00, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 4U, 0.0, kTrueProfile);
  set_measured_string_profile(bank, 1U, 0U, 1.2, kNearbyProfile);
  detector.set_calibration_bank(bank);

  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::
                   reassigned_settled_string_for_profile_and_cents(
                       detector, kNote, 1U, kObserved, 0.0),
               0U);
}

M3_TEST(native_detector_does_not_split_one_calibrated_string_into_a_unison) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 48U;
  constexpr double kCents = 4.2;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 59U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 16U, -3.5, kLowProfile);
  set_measured_string_profile(bank, 4U, 0U, kCents, kOpenProfile);
  detector.set_calibration_bank(bank);

  m3::TunerSnapshot final_snapshot;
  const double frequency =
      m3::midi_to_frequency(kNote + kCents / 100.0, 440.0);
  for (std::uint32_t sample = 0U; sample < 72000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double phase = 1.03 + kTwoPi * frequency * time;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kOpenProfile.size();
         ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      mixed += 0.050 * kOpenProfile[harmonic] *
               std::sin(partial * phase - 0.07 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (decision.tuner_snapshot_ready) {
      final_snapshot = decision.tuner_snapshot;
    }
  }

  M3_EXPECT_EQ(final_snapshot.voice_count, 1U);
  if (final_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(final_snapshot.voices[0U].midi_note, kNote);
    M3_EXPECT_EQ(final_snapshot.voices[0U].string_index, 4U);
  }
}

M3_TEST(native_detector_does_not_split_recorded_string2_profile_across_nearby_calibrations) {
  constexpr double kSampleRate = 96000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 56U;
  struct RecordedPoint final {
    std::size_t string{};
    std::size_t fret{};
    double cents{};
    std::array<double, m3::kCalibrationHarmonicCount> profile{};
  };
  constexpr std::array<RecordedPoint, 7U> kPoints{{
      {0U, 24U, 6.11328125, {1.0, 0.0055, 0.0, 0.0, 0.0, 0.0}},
      {1U, 20U, -17.1796875, {1.0, 0.0199, 0.0, 0.0, 0.0, 0.0}},
      {2U, 16U, -17.21875, {1.0, 0.0214, 0.0055, 0.0, 0.0, 0.0}},
      {3U, 12U, -5.40234375, {1.0, 0.0298, 0.0, 0.0, 0.0, 0.0}},
      {4U, 8U, 11.5703125, {1.0, 0.1251, 0.0079, 0.0111, 0.0, 0.0}},
      {5U, 4U, 3.73828125, {1.0, 0.2235, 0.0266, 0.0, 0.0, 0.0}},
      {6U, 0U, 4.8046875, {1.0, 0.1717, 0.3109, 0.0451, 0.0, 0.0059}},
  }};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 54U;
  config.highest_note = 58U;
  config.max_polyphony = 4U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  for (const RecordedPoint& point : kPoints) {
    set_measured_string_profile(bank, point.string, point.fret,
                                point.cents, point.profile);
  }
  detector.set_calibration_bank(bank);

  // A single real string drifts slightly and its harmonic balance evolves
  // after the pick.  Neither effect is independent same-note evidence.
  const double base_frequency =
      m3::midi_to_frequency(kNote + kPoints[6U].cents / 100.0, 440.0);
  m3::TunerSnapshot final_snapshot;
  std::uint8_t maximum_voice_count = 0U;
  for (std::uint32_t sample = 0U; sample < 576000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double phase =
        kTwoPi * base_frequency * time -
        (0.08 / 0.70) * std::cos(kTwoPi * 0.70 * time) + 0.73;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U;
         harmonic < kPoints[6U].profile.size(); ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      const double evolving =
          std::exp(-time * (0.012 + 0.008 * partial));
      mixed += 0.050 * kPoints[6U].profile[harmonic] * evolving *
               std::sin(partial * phase - 0.05 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (decision.tuner_snapshot_ready) {
      final_snapshot = decision.tuner_snapshot;
      maximum_voice_count = std::max(
          maximum_voice_count, decision.tuner_snapshot.voice_count);
    }
  }
  if (maximum_voice_count > 1U || final_snapshot.voice_count != 1U ||
      final_snapshot.voices[0U].string_index != 6U) {
    const m3::PolyphonicPitchDetectorTestAccess::FineProbe fine =
        m3::PolyphonicPitchDetectorTestAccess::fine_probe(detector, 2U);
    std::fprintf(stderr,
                 "recorded-string2 single max=%u final=%u lane=%u fine=%u "
                 "pending=%u/%u dev=%.4f multi=%d beat=%d\n",
                 maximum_voice_count, final_snapshot.voice_count,
                 final_snapshot.voice_count == 0U
                     ? 255U
                     : final_snapshot.voices[0U].string_index,
                 fine.members, fine.pending, fine.pending_count,
                 fine.frequency_deviation_hz,
                 fine.multi_source_observed ? 1 : 0,
                 fine.beat_valid ? 1 : 0);
  }
  M3_EXPECT_TRUE(maximum_voice_count <= 1U);
  M3_EXPECT_EQ(final_snapshot.voice_count, 1U);
  if (final_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(final_snapshot.voices[0U].midi_note, kNote);
    M3_EXPECT_EQ(final_snapshot.voices[0U].string_index, 6U);
  }
}

M3_TEST(native_detector_does_not_split_physical_open_c4_pick_transient) {
  constexpr double kSampleRate = 96000.0;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::uint8_t kFrettedString = 6U;
  constexpr std::uint8_t kOpenString = 7U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount>
      kFrettedProfile{{
          0.782030, 0.602103, 0.158490, 0.012353, 0.016571, 0.012353}};
  constexpr std::array<double, m3::kCalibrationHarmonicCount>
      kOpenProfile{{0.998656, 0.050970, 0.009568, 0.0, 0.0, 0.0}};
  // Measured 260 ms after the pick in the physical string-1 recording. The
  // transient is spectrally between the neighbouring C4 calibrations, but it
  // is still one string: there is no fine-frequency or beat evidence for a
  // second physical source.
  constexpr std::array<double, m3::kCalibrationHarmonicCount>
      kObservedPickTransient{{
          0.800507383, 0.175311084, 0.022085956, 0.002095577, 0.0, 0.0}};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 58U;
  config.highest_note = 62U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, kFrettedString, 4U, 7.988,
                              kFrettedProfile);
  set_measured_string_profile(bank, kOpenString, 0U, 8.762, kOpenProfile);
  detector.set_calibration_bank(bank);

  constexpr std::size_t kCandidate = kNote - 58U;
  constexpr std::uint8_t kOpenOnly =
      static_cast<std::uint8_t>(1U << kOpenString);
  M3_EXPECT_EQ(m3::PolyphonicPitchDetectorTestAccess::profile_only_group_mask(
                   detector, kCandidate, kOpenString,
                   kObservedPickTransient, 8U, 416U),
               kOpenOnly);
}

M3_TEST(native_detector_uses_complete_physical_calibration_to_rescue_weak_open_c4) {
  constexpr std::uint8_t kNote = 60U;
  constexpr std::array<std::array<std::uint16_t,
                                  m3::kCalibrationHarmonicCount>,
                       7U>
      kPhysicalProfiles{{
          {{32767U, 0U, 0U, 0U, 0U, 0U}},
          {{32633U, 134U, 0U, 0U, 0U, 0U}},
          {{32758U, 9U, 0U, 0U, 0U, 0U}},
          {{32385U, 382U, 0U, 0U, 0U, 0U}},
          {{32657U, 110U, 0U, 0U, 0U, 0U}},
          {{20046U, 11879U, 823U, 5U, 9U, 5U}},
          {{32679U, 85U, 3U, 0U, 0U, 0U}},
      }};
  // Measured from the first all-open hold. It is an unambiguous direct C4
  // peak, but its mostly-fundamental spectrum is necessarily close to several
  // high-fret calibration profiles. The exact open-string profile remains an
  // excellent match even though another lane wins the raw cosine by 0.5%.
  constexpr std::array<double, m3::kCalibrationHarmonicCount>
      kObservedPhysicalProfile{{0.994432256, 0.004831460, 0.000476871,
                                0.000259413, 0.0, 0.0}};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 58U;
  config.highest_note = 62U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));
  m3::StringCalibrationBank bank;
  for (std::size_t string = 1U; string < m3::kM3OpenNotes.size(); ++string) {
    auto& point = bank.points[string][kNote - m3::kM3OpenNotes[string]];
    point.harmonic_profile_q15 = kPhysicalProfiles[string - 1U];
    point.confidence_q15 = 32767U;
    point.observation_count = 128U;
    point.quality = m3::CalibrationPointQuality::measured;
    bank.calibrated_string_mask = static_cast<std::uint8_t>(
        bank.calibrated_string_mask | (1U << string));
  }
  detector.set_calibration_bank(bank);

  // The physical all-open recording presents C4 below the normal global
  // threshold while its direct fundamental and exact open-string fingerprint
  // remain strong.
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     calibrated_direct_support_for_profile(
                         detector, kNote - 58U, kObservedPhysicalProfile,
                         0.086));
}

M3_TEST(native_detector_lower_octave_rescue_requires_decisive_shape_and_isolation) {
  constexpr std::uint8_t kNote = 45U;
  constexpr std::size_t kString = 3U;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 72U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(96000.0, config));

  m3::StringCalibrationBank bank =
      m3::test_signal::calibration_bank_for_note(kNote);
  const auto* point =
      bank.point(kString, kNote - m3::kM3OpenNotes[kString]);
  M3_EXPECT_TRUE(point != nullptr);
  std::array<double, m3::kCalibrationHarmonicCount> profile{};
  if (point != nullptr) {
    for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
      profile[harmonic] = static_cast<double>(
          point->harmonic_profile_q15[harmonic]) /
          32767.0;
    }
  }
  detector.set_calibration_bank(bank);
  const std::size_t candidate = kNote - config.lowest_note;
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     decisive_calibrated_shape_for_profile(
                         detector, candidate, profile));
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     isolated_shadow_context(false, false));
  M3_EXPECT_FALSE(m3::PolyphonicPitchDetectorTestAccess::
                      isolated_shadow_context(true, false));
  M3_EXPECT_TRUE(m3::PolyphonicPitchDetectorTestAccess::
                     isolated_shadow_context(true, false, true));
  M3_EXPECT_FALSE(m3::PolyphonicPitchDetectorTestAccess::
                      isolated_shadow_context(true, true, true));
  M3_EXPECT_FALSE(m3::PolyphonicPitchDetectorTestAccess::
                      isolated_shadow_context(false, true));

  m3::StringCalibrationBank ambiguous = bank;
  for (std::size_t string = 0U; string <= kString; ++string) {
    auto& candidate_point =
        ambiguous.points[string][kNote - m3::kM3OpenNotes[string]];
    candidate_point.harmonic_profile_q15 = point->harmonic_profile_q15;
  }
  detector.set_calibration_bank(ambiguous);
  M3_EXPECT_FALSE(m3::PolyphonicPitchDetectorTestAccess::
                      decisive_calibrated_shape_for_profile(
                          detector, candidate, profile));
}

M3_TEST(native_detector_lower_octave_shape_accepts_the_measured_point_ninety_six_floor) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(Access::decisive_calibrated_shape_thresholds(
      2U, 2U, 0.96, 0.45));
  M3_EXPECT_FALSE(Access::decisive_calibrated_shape_thresholds(
      2U, 2U, 0.959, 0.44));
  M3_EXPECT_FALSE(Access::decisive_calibrated_shape_thresholds(
      2U, 2U, 0.96, 0.461));
  M3_EXPECT_FALSE(Access::decisive_calibrated_shape_thresholds(
      2U, 1U, 0.99, 0.10));
  M3_EXPECT_FALSE(Access::decisive_calibrated_shape_thresholds(
      2U, 2U, 0.90, 0.39));
  M3_EXPECT_TRUE(Access::decisive_calibrated_shape_thresholds(
      2U, 2U, 0.90, 0.69, 0.90, 0.20));
}

M3_TEST(native_detector_isolated_third_partial_context_is_exact_and_inactive) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  M3_EXPECT_TRUE(Access::isolated_third_partial_context(
      12U, 31U, 1U, 0U, false));
  M3_EXPECT_FALSE(Access::isolated_third_partial_context(
      12U, 30U, 1U, 0U, false));
  M3_EXPECT_FALSE(Access::isolated_third_partial_context(
      12U, 32U, 1U, 0U, false));
  M3_EXPECT_FALSE(Access::isolated_third_partial_context(
      12U, 31U, 2U, 0U, false));
  M3_EXPECT_FALSE(Access::isolated_third_partial_context(
      12U, 31U, 1U, 1U, false));
  M3_EXPECT_FALSE(Access::isolated_third_partial_context(
      12U, 31U, 1U, 0U, true));
}

M3_TEST(native_detector_single_routing_collapses_a_calibrated_unison_to_one_midi_note) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 48U;
  constexpr double kLowCents = -3.5;
  constexpr double kOpenCents = 4.2;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::single;
  config.lowest_note = 32U;
  config.highest_note = 59U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 16U, kLowCents, kLowProfile);
  set_measured_string_profile(bank, 4U, 0U, kOpenCents, kOpenProfile);
  detector.set_calibration_bank(bank);

  std::size_t note_ons = 0U;
  m3::TunerSnapshot final_snapshot;
  const double low_frequency =
      m3::midi_to_frequency(kNote + kLowCents / 100.0, 440.0);
  const double open_frequency =
      m3::midi_to_frequency(kNote + kOpenCents / 100.0, 440.0);
  for (std::uint32_t sample = 0U; sample < 72000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double low_phase = 0.17 + kTwoPi * low_frequency * time;
    const double open_phase = 1.03 + kTwoPi * open_frequency * time;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kLowProfile.size();
         ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      mixed += 0.055 * kLowProfile[harmonic] *
               std::sin(partial * low_phase + 0.11 * partial);
      mixed += 0.050 * kOpenProfile[harmonic] *
               std::sin(partial * open_phase - 0.07 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
      const m3::VoiceTransition& transition = decision.transitions[event];
      if (transition.kind == m3::TransitionKind::note_on &&
          transition.note == kNote) {
        ++note_ons;
        M3_EXPECT_EQ(transition.voice_id, m3::kUnassignedVoiceId);
      }
    }
    if (decision.tuner_snapshot_ready) {
      final_snapshot = decision.tuner_snapshot;
    }
  }
  M3_EXPECT_EQ(note_ons, 1U);
  M3_EXPECT_EQ(final_snapshot.voice_count, 2U);
}

M3_TEST(native_detector_learns_individually_held_frets_up_and_back_down) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_TRUE(detector.begin_string_calibration(0U));
  double oscillator_phase = 0.0;
  feed_calibration_pitch(detector, m3::kM3OpenNotes[0U], 16000U,
                         &oscillator_phase);
  M3_EXPECT_EQ(detector.calibration_status().phase,
               m3::CalibrationSweepPhase::ascending);

  const double open_pitch = static_cast<double>(m3::kM3OpenNotes[0U]);
  feed_calibration_frets(detector, open_pitch, oscillator_phase);

  const m3::CalibrationSweepStatus status = detector.calibration_status();
  M3_EXPECT_EQ(status.phase, m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(status.highest_fret, 24U);
  M3_EXPECT_TRUE(status.measured_frets >= 18U);
  M3_EXPECT_TRUE(detector.calibration_bank().string_calibrated(0U));
}

M3_TEST(native_detector_calibration_tracks_the_requested_high_fret_when_a_neighbor_is_louder) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_TRUE(detector.begin_string_calibration(0U));
  const m3::CalibrationSweepStatus status =
      m3::PolyphonicPitchDetectorTestAccess::
          observe_requested_high_fret_beside_a_louder_neighbor(detector);

  M3_EXPECT_EQ(status.phase, m3::CalibrationSweepPhase::ascending);
  M3_EXPECT_EQ(status.requested_fret, 24U);
  M3_EXPECT_EQ(status.highest_fret, 23U);
}

M3_TEST(native_detector_calibration_retains_a_detuned_strings_cents_offset) {
  // Calibration intentionally requires the open string to be tuned first;
  // verify a realistic residual offset inside that admission window.
  constexpr double kDetuneCents = 6.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_TRUE(detector.begin_string_calibration(0U));
  double oscillator_phase = 0.0;
  const double open_pitch =
      static_cast<double>(m3::kM3OpenNotes[0U]) + kDetuneCents / 100.0;
  feed_calibration_pitch(detector, open_pitch, 16000U, &oscillator_phase);
  feed_calibration_frets(detector, open_pitch, oscillator_phase);

  M3_EXPECT_EQ(detector.calibration_status().phase,
               m3::CalibrationSweepPhase::complete);
  const m3::StringCalibrationPoint* open =
      detector.calibration_bank().point(0U, 0U);
  M3_EXPECT_TRUE(open != nullptr);
  if (open != nullptr) {
    M3_EXPECT_NEAR(static_cast<double>(open->cents_offset_q8) / 256.0,
                   kDetuneCents, 4.0);
  }
}

M3_TEST(native_detector_backfills_a_valid_open_string_after_an_unplayable_peak) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 1U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{32U, 34U};
  feed_dyad(detector, 32U, 34U, 0.20, 0.24, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_FALSE(lifecycle.high_on);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_does_not_activate_without_an_owned_m3_string_lane) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 33U;
  config.max_polyphony = 2U;
  config.max_fret = 1U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::
          attempt_reserved_string_activation(detector);

  M3_EXPECT_EQ(decision.transitions.size(), 0U);
}

M3_TEST(native_detector_keeps_an_independent_open_string_when_fret_masks_conflict) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 3U;
  config.max_fret = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 34U, 36U, 0U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 3U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_weighted_chord(detector,
                      {0.20, 0.18, 0.08, 0.0, 0.0, 0.0, 0.0, 0.0},
                      36000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.note_on[0U]);
  M3_EXPECT_TRUE(lifecycle.note_on[2U]);
  M3_EXPECT_TRUE(lifecycle.note_off[0U]);
  M3_EXPECT_TRUE(lifecycle.note_off[2U]);
  M3_EXPECT_FALSE(lifecycle.note_on[1U]);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_spectral_lane_evidence_only_reassigns_one_active_free_lane) {
  constexpr std::uint8_t kCurrent = 0x01U;
  constexpr std::uint8_t kProjected = 0x08U;
  constexpr std::uint8_t kPlayable = 0x0fU;
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.05, 0.02,
          true, false, false, 0U),
      kProjected);
  // The replay-safe relaxed policy is onset-only. It catches the physical
  // articulation before a wrong lane settles, while the settled classifier
  // keeps its original strict thresholds for isolated-string stability.
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.15, 0.005,
          true, false, false, 0U, true,
          m3::UnisonSpectralPhase::onset),
      kProjected);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.15, 0.005,
          true, false, false, 0U, true,
          m3::UnisonSpectralPhase::settled),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.15, 0.005,
          true, false, false, 0U, true,
          m3::UnisonSpectralPhase::onset, false),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          false, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, 0x03U, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, kProjected, kProjected, 1U, 0.01, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, 0x03U, 0U, kProjected, 1U, 0.01, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, 0x0cU, 2U, 0.01, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.051, 0.2,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.0199,
          true, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          false, false, false, 0U),
      kProjected);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.0199,
          false, false, false, 0U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          false, true, true, kProjected),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          false, true, false, 0x02U),
      0U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::spectral_lane_assignment_probe(
          true, kCurrent, kPlayable, 0U, kProjected, 1U, 0.01, 0.2,
          false, true, false, kProjected),
      kProjected);
}

M3_TEST(native_detector_spectral_lane_history_clears_on_true_silence) {
  m3::PolyphonicPitchDetector detector;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 33U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_FALSE(
      m3::PolyphonicPitchDetectorTestAccess::
          spectral_lane_tracker_survives_quiet(detector));
}

M3_TEST(native_detector_adjacent_spectral_duplicate_suppression_is_bounded) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::uint8_t kSuppressLeft = 0x01U;
  constexpr std::uint8_t kSuppressRight = 0x02U;
  constexpr std::uint8_t kKeepBoth = 0U;

  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x01U, 0x02U, true, true,
                   0.70, 0.20),
               kSuppressLeft);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x01U, 0x02U, true, true,
                   0.20, 0.70),
               kSuppressRight);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x01U, 0x02U, true, true,
                   0.64, 0.20),
               kKeepBoth);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 62U, 0x01U, 0x02U, true, true,
                   0.70, 0.20),
               kKeepBoth);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x03U, 0x04U, true, true,
                   0.70, 0.20),
               kKeepBoth);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x01U, 0x01U, true, true,
                   0.70, 0.20),
               kKeepBoth);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   false, true, 60U, 61U, 0x01U, 0x02U, true, true,
                   0.70, 0.20),
               kKeepBoth);
  M3_EXPECT_EQ(Access::adjacent_spectral_duplicate_suppression_probe(
                   true, true, 60U, 61U, 0x01U, 0x02U, false, true,
                   0.70, 0.20),
               kKeepBoth);
}

M3_TEST(native_detector_spectral_lane_projection_never_splits_a_physical_group) {
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          projected_output_string_mask_probe(0U, 2U, 0x08U),
      0x08U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          projected_output_string_mask_probe(0x01U, 0U, 0x04U),
      0x04U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          projected_output_string_mask_probe(0x03U, 0U, 0x04U),
      0x03U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          projected_output_string_mask_probe(0x01U, 0U, 0U),
      0x01U);
}

M3_TEST(native_detector_group_continuity_is_output_only_and_physically_bounded) {
  m3::UnisonSpectralClassification classification;
  classification.valid = true;
  classification.member_mask = 0x07U;
  classification.member_count = 3U;
  classification.posterior_margin = 0.001;
  const auto project = [&](std::uint8_t current, std::uint8_t cached,
                           std::uint8_t other_owned, bool quiet,
                           double age) noexcept {
    return m3::PolyphonicPitchDetectorTestAccess::
        group_continuity_projection_probe(
            current, cached, classification,
            m3::UnisonSpectralPhase::settled, 0x03U, 0.20, 0x07U,
            0U, current, other_owned, 0xffU, 5U, true, true, true,
            quiet, age);
  };

  M3_EXPECT_EQ(project(0x03U, 0x07U, 0U, false, 0.20), 0x07U);
  M3_EXPECT_EQ(project(0U, 0x07U, 0U, false, 0.20), 0U);
  M3_EXPECT_EQ(project(0x03U, 0x07U, 0x04U, false, 0.20), 0x03U);
  M3_EXPECT_EQ(project(0x03U, 0x07U, 0U, true, 0.20), 0x03U);
  M3_EXPECT_EQ(project(0x03U, 0x07U, 0U, false, 0.51), 0x03U);

  // No cache means no restoration, even if the tier path has a wider mask.
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_projection_probe(
              0x03U, 0U, classification,
              m3::UnisonSpectralPhase::settled, 0x03U, 0.20, 0U, 0U,
              0x07U, 0U, 0xffU, 5U, true, true, true, false,
              std::numeric_limits<double>::infinity()),
      0x03U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_projection_probe(
              0x03U, 0U, classification,
              m3::UnisonSpectralPhase::settled, 0x03U, 0.20, 0U, 0U,
              0x03U, 0U, 0xffU, 5U, true, true, true, false,
              std::numeric_limits<double>::infinity()),
      0x03U);
  classification.member_mask = 0x0bU;
  M3_EXPECT_EQ(project(0x03U, 0x07U, 0U, false, 0.20), 0x03U);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          projected_output_string_mask_probe(0x03U, 0U, 0U, 0x07U),
      0x07U);
}

M3_TEST(native_detector_articulated_continuity_restores_only_a_fresh_bounded_triple) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  const auto project = [](std::uint8_t cached, double seconds, double beat,
                          std::uint8_t tier, std::uint8_t other_owned,
                          double score_threshold_ratio, bool quiet,
                          double age) noexcept {
    return Access::articulated_group_continuity_projection_probe(
        0x03U, cached, 0x03U, seconds, beat, tier, other_owned,
        score_threshold_ratio, quiet, age);
  };
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x07U, 0U, 0.50, false, 0.25),
               0x07U);
  M3_EXPECT_EQ(project(0x0fU, 0.20, 0.20, 0x0fU, 0U, 0.50, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.19, 0.20, 0x07U, 0U, 0.50, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.19, 0x07U, 0U, 0.50, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x03U, 0U, 0.50, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x07U, 0x04U, 0.50, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x07U, 0U, 0.49, false, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x07U, 0U, 0.50, true, 0.25),
               0x03U);
  M3_EXPECT_EQ(project(0x07U, 0.20, 0.20, 0x07U, 0U, 0.50, false, 0.251),
               0x03U);
}

M3_TEST(native_detector_early_articulated_continuity_requires_a_complete_exclusive_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  const auto project = [](std::uint8_t other_owned,
                          std::uint8_t playable = 0x07U) noexcept {
    return Access::solo_articulated_group_continuity_projection_probe(
        0x03U, 0x07U, 0x03U, 0.20, 0.20, 0x07U, other_owned,
        playable, 0.50, false, 0.25);
  };

  M3_EXPECT_EQ(project(0x00U), 0x07U);
  // A disjoint fourth lane is safe for the ordinary late projection, but the
  // early replay experiment must not alter a mixed-pitch chord decision.
  M3_EXPECT_EQ(project(0x08U), 0x03U);
  M3_EXPECT_EQ(project(0x04U), 0x03U);
  // Do not complete a proper subset when another physical string could also
  // play the pitch; this is where the broader early policy fed back into
  // ordinary chords and synthetic groups.
  M3_EXPECT_EQ(project(0x00U, 0x0fU), 0x03U);
}

M3_TEST(native_detector_bounds_continuity_corridors_to_ranked_candidates) {
  const auto configure_detector = [](m3::PolyphonicPitchDetector& detector) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 33U;
    config.max_polyphony = 4U;
    config.max_fret = 24U;
    M3_EXPECT_TRUE(detector.configure(96000.0, config));
  };

  m3::PolyphonicPitchDetector single;
  configure_detector(single);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_tracker_count_after_update(single, 0x01U),
      1U);

  m3::PolyphonicPitchDetector group;
  configure_detector(group);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_tracker_count_after_update(group, 0x03U),
      1U);

  m3::PolyphonicPitchDetector competing;
  configure_detector(competing);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_tracker_count_after_update(competing, 0x01U,
                                                       0x02U),
      2U);

  m3::PolyphonicPitchDetector pending;
  configure_detector(pending);
  M3_EXPECT_EQ(
      m3::PolyphonicPitchDetectorTestAccess::
          group_continuity_tracker_count_after_update(pending, 0x01U, 0U,
                                                       0x07U),
      1U);
}

M3_TEST(native_detector_diagnostic_selector_requires_a_nonempty_lane_mask) {
  m3::PolyphonicPitchDetector detector;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 96U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_FALSE(
      detector.set_decisive_calibrated_selector_for_diagnostics(0.02, 0U));
  M3_EXPECT_TRUE(detector.set_decisive_calibrated_selector_for_diagnostics(
      0.02, static_cast<std::uint8_t>(0x54U)));
  M3_EXPECT_TRUE(
      detector.set_calibrated_dp_replacement_lane_mask_for_diagnostics(0U));
  M3_EXPECT_TRUE(
      detector.set_calibrated_dp_replacement_lane_mask_for_diagnostics(
          static_cast<std::uint8_t>(0x54U)));
}

M3_TEST(native_detector_atomically_replaces_a_weaker_single_lane_candidate) {
  for (const auto routing : {m3::MidiRouting::single,
                             m3::MidiRouting::per_voice}) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = routing;
    config.lowest_note = 32U;
    config.highest_note = 96U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));

    const auto result =
        m3::PolyphonicPitchDetectorTestAccess::calibrated_dp_replacement_probe(
            detector, true, false, false, 0.15, routing);
    M3_EXPECT_FALSE(result.incumbent_selected);
    M3_EXPECT_TRUE(result.target_selected);
    M3_EXPECT_TRUE(result.target_is_atomic);
    M3_EXPECT_EQ(result.target_string, 2U);
  }
}

M3_TEST(native_detector_atomic_replacement_reserves_note_off_and_note_on) {
  for (const auto routing : {m3::MidiRouting::single,
                             m3::MidiRouting::per_voice}) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = routing;
    config.lowest_note = 40U;
    config.highest_note = 41U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));

    const auto blocked =
        m3::PolyphonicPitchDetectorTestAccess::atomic_handoff_capacity_probe(
            detector, routing, 1U);
    M3_EXPECT_FALSE(blocked.queued);
    M3_EXPECT_EQ(blocked.transition_count,
                 m3::TickTransitions::capacity() - 1U);
    M3_EXPECT_TRUE(blocked.incumbent_active);
    M3_EXPECT_FALSE(blocked.target_active);

    const auto committed =
        m3::PolyphonicPitchDetectorTestAccess::atomic_handoff_capacity_probe(
            detector, routing, 2U);
    M3_EXPECT_TRUE(committed.queued);
    M3_EXPECT_EQ(committed.transition_count,
                 m3::TickTransitions::capacity());
    M3_EXPECT_FALSE(committed.incumbent_active);
    M3_EXPECT_TRUE(committed.target_active);
    M3_EXPECT_EQ(committed.penultimate_kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(committed.final_kind, m3::TransitionKind::note_on);
  }
}

M3_TEST(native_detector_dp_replacement_respects_context_lane_score_and_silence) {
  const auto run = [](bool lane_allowed, bool multi_string_context,
                      bool quiet, double target_score) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 96U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));
    return m3::PolyphonicPitchDetectorTestAccess::
        calibrated_dp_replacement_probe(detector, lane_allowed,
                                        multi_string_context, quiet,
                                        target_score);
  };

  for (const auto result : {
           run(false, false, false, 0.15),
           run(true, true, false, 0.15),
           run(true, false, false, 0.12),
           run(true, false, true, 0.15),
       }) {
    M3_EXPECT_TRUE(result.incumbent_selected);
    M3_EXPECT_FALSE(result.target_selected);
    M3_EXPECT_FALSE(result.target_is_atomic);
  }
}

M3_TEST(native_detector_dp_replacement_rejects_every_live_group_projection) {
  for (std::uint8_t kind = 1U; kind <= 3U; ++kind) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 96U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));
    const auto result =
        m3::PolyphonicPitchDetectorTestAccess::calibrated_dp_replacement_probe(
            detector, true, false, false, 0.15,
            m3::MidiRouting::per_voice, kind);
    M3_EXPECT_TRUE(result.incumbent_selected);
    M3_EXPECT_FALSE(result.target_selected);
  }
}

M3_TEST(native_detector_dp_replacement_requires_complete_decisive_calibration) {
  const auto run = [](bool partial, bool tied) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 96U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));
    return m3::PolyphonicPitchDetectorTestAccess::
        calibrated_dp_replacement_probe(
            detector, true, false, false, 0.15,
            m3::MidiRouting::per_voice, 0U, partial, tied);
  };

  for (const auto result : {run(true, false), run(false, true)}) {
    M3_EXPECT_TRUE(result.incumbent_selected);
    M3_EXPECT_FALSE(result.target_selected);
    M3_EXPECT_FALSE(result.target_is_atomic);
  }
}

M3_TEST(native_detector_dp_output_projection_preserves_selector_history) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 96U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto result =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_dp_output_projection_probe(
              detector, 0U, false, false, false, false, false);
  M3_EXPECT_TRUE(result.incumbent_selected);
  M3_EXPECT_FALSE(result.target_selected);
  M3_EXPECT_TRUE(result.incumbent_active);
  M3_EXPECT_EQ(result.base_note, 44U);
  M3_EXPECT_EQ(result.midi_note, 52U);
  M3_EXPECT_EQ(result.projection_note, 52U);
  M3_EXPECT_EQ(result.transition_count, 2U);
  M3_EXPECT_EQ(result.kinds[0U], m3::TransitionKind::note_off);
  M3_EXPECT_EQ(result.notes[0U], 44U);
  M3_EXPECT_EQ(result.voices[0U], 0U);
  M3_EXPECT_EQ(result.kinds[1U], m3::TransitionKind::note_on);
  M3_EXPECT_EQ(result.notes[1U], 52U);
  M3_EXPECT_EQ(result.voices[1U], 0U);
}

M3_TEST(native_detector_dp_output_projection_is_bounded_to_lane_zero_solos) {
  const auto run = [](std::uint8_t string, bool grouped, bool quiet) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 96U;
    config.max_polyphony = 5U;
    config.max_fret = 24U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(48000.0, config));
    return m3::PolyphonicPitchDetectorTestAccess::
        calibrated_dp_output_projection_probe(
            detector, string, grouped, quiet, false, false, false);
  };

  for (const auto result : {
           run(1U, false, false),
           run(0U, true, false),
           run(0U, false, true),
       }) {
    M3_EXPECT_EQ(result.transition_count, 0U);
    M3_EXPECT_EQ(result.projection_note, m3::kTunerNoSignalNote);
    M3_EXPECT_EQ(result.midi_note, 44U);
    M3_EXPECT_TRUE(result.incumbent_selected);
    M3_EXPECT_FALSE(result.target_selected);
  }
}

M3_TEST(native_detector_dp_output_projection_does_not_bridge_true_silence) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 96U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto result =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_dp_output_projection_probe(
              detector, 0U, false, false, false, false, false, true);
  M3_EXPECT_EQ(result.transition_count, 0U);
  M3_EXPECT_EQ(result.projection_note, m3::kTunerNoSignalNote);
  M3_EXPECT_EQ(result.base_note, 44U);
  M3_EXPECT_EQ(result.midi_note, 44U);
  M3_EXPECT_TRUE(result.incumbent_selected);
  M3_EXPECT_FALSE(result.target_selected);
  M3_EXPECT_TRUE(result.incumbent_active);
}

M3_TEST(native_detector_dp_output_projection_retracts_without_replacing_state) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 96U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto result =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_dp_output_projection_probe(
              detector, 0U, false, false, true, true, false);
  M3_EXPECT_EQ(result.transition_count, 4U);
  M3_EXPECT_EQ(result.notes[0U], 44U);
  M3_EXPECT_EQ(result.notes[1U], 52U);
  M3_EXPECT_EQ(result.notes[2U], 52U);
  M3_EXPECT_EQ(result.notes[3U], 45U);
  M3_EXPECT_EQ(result.base_note, 45U);
  M3_EXPECT_EQ(result.midi_note, 45U);
  M3_EXPECT_EQ(result.projection_note, m3::kTunerNoSignalNote);
  M3_EXPECT_TRUE(result.incumbent_selected);
  M3_EXPECT_FALSE(result.target_selected);
  M3_EXPECT_TRUE(result.incumbent_active);
}

M3_TEST(native_detector_dp_output_projection_releases_the_rendered_note) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 96U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto result =
      m3::PolyphonicPitchDetectorTestAccess::
          calibrated_dp_output_projection_probe(
              detector, 0U, false, false, false, false, true);
  M3_EXPECT_TRUE(result.release_queued);
  M3_EXPECT_EQ(result.transition_count, 3U);
  M3_EXPECT_EQ(result.kinds[2U], m3::TransitionKind::note_off);
  M3_EXPECT_EQ(result.notes[2U], 52U);
  M3_EXPECT_EQ(result.voices[2U], 0U);
}
