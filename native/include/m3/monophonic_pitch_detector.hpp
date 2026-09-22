#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/tuner_telemetry.hpp"
#include "m3/types.hpp"

namespace m3 {

struct DetectorDecision final {
  TickTransitions transitions{};
  TunerSnapshot tuner_snapshot{};
  // A host-readable strongest-voice projection accompanies the full
  // polyphonic editor snapshot. It does not replace or limit MIDI polyphony.
  TunerEstimate tuner{};
  bool tuner_snapshot_ready{};
};

// The established source path and type name are retained for build
// compatibility. The detector itself now selects a bounded polyphonic voice
// set and emits one lifecycle stream per selected note.
class MonophonicPitchDetector final {
 public:
  MonophonicPitchDetector() noexcept = default;
  MonophonicPitchDetector(const MonophonicPitchDetector&) = delete;
  MonophonicPitchDetector& operator=(const MonophonicPitchDetector&) = delete;

  bool configure(double sample_rate, const PersistentConfig& config) noexcept;
  void set_runtime_config(const PersistentConfig& config) noexcept;
  void reset() noexcept;
  [[nodiscard]] DetectorDecision process_sample(double sample) noexcept;

#if defined(M3_TESTING)
  struct SelectionWork final {
    std::uint32_t pool_candidates{};
    std::uint32_t state_transitions{};
    std::uint32_t assignment_edges{};
  };

  [[nodiscard]] SelectionWork selection_work_for_test() const noexcept {
    return selection_work_;
  }
#endif

 private:
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
    std::uint8_t release_ticks{};
    std::uint8_t evidence_ticks{};
    std::uint8_t evidence_gap_ticks{};
    std::uint16_t age_ticks{};
    bool active{};
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

  [[nodiscard]] DetectorDecision make_decision() noexcept;
  void update_cell(Cell& cell, double sample) noexcept;
  [[nodiscard]] std::uint8_t dynamic_velocity() const noexcept;
  [[nodiscard]] std::uint8_t attack_decisions() const noexcept;
  [[nodiscard]] std::uint8_t release_decisions() const noexcept;
  [[nodiscard]] std::uint8_t candidate_evidence_decisions(
      bool multi_voice) const noexcept;
  [[nodiscard]] double signal_floor() const noexcept;
  void append_transition(DetectorDecision& decision, TransitionKind kind,
                         std::uint8_t note, std::uint8_t velocity) noexcept;
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
  [[nodiscard]] std::size_t m3_assignment_state_count(
      const std::array<bool, kMaxCandidates>& selected) const noexcept;
  [[nodiscard]] bool selection_has_distinct_m3_strings(
      const std::array<bool, kMaxCandidates>& selected) const noexcept;
  void enforce_m3_feasibility(
      std::array<bool, kMaxCandidates>& selected,
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals) const noexcept;
  void select_m3_feasible_candidates(
      const std::array<double, kMaxCandidates>& scores,
      const std::array<double, kMaxCandidates>& fundamentals,
      const std::array<double, kMaxCandidates>& narrow_fundamentals,
      double threshold,
      std::array<bool, kMaxCandidates>& selected,
      std::size_t count) noexcept;
  [[nodiscard]] std::size_t cell_index(std::size_t candidate,
                                       std::size_t harmonic) const noexcept {
    return candidate * kHarmonicCount + harmonic;
  }

  std::array<Cell, kCellCount> cells_{};
  std::array<CandidateState, kMaxCandidates> candidate_states_{};
  std::array<std::uint8_t, kMaxCandidates> playable_string_masks_{};
  std::array<double, kMaxCandidates> narrow_fundamental_real_{};
  std::array<double, kMaxCandidates> narrow_fundamental_imaginary_{};
  std::array<M3PoolCandidate, kMaxVoices * kMaxVoices> m3_pool_{};
  std::array<M3DpState, 1U << kMaxVoices> m3_dp_states_{};
  double sample_rate_{};
  double dc_pole{};
  double correlation_decay{};
  double narrow_correlation_decay{};
  double slow_energy_decay{};
  double previous_input_{};
  double previous_dc_output_{};
  double fast_energy_{};
  double slow_energy_{};
  double signal_floor_{};
  std::uint32_t decision_phase_{};
  std::uint32_t transition_sequence_{};
  std::uint8_t lowest_note_{};
  std::uint8_t candidate_count_{};
  std::uint8_t max_polyphony_{1U};
  std::uint8_t max_fret_{24U};
  std::uint8_t sensitivity_{50U};
  std::uint8_t response_{25U};
  std::uint8_t fixed_velocity_{100U};
  VelocityMode velocity_mode_{VelocityMode::dynamic};
  std::uint32_t snapshot_generation_{};
  std::uint32_t signal_samples_{};
  std::uint32_t narrow_signal_samples_{};
  ProfileMode profile_mode_{ProfileMode::m3};
  bool signal_present_{};
  bool configured_{};

#if defined(M3_TESTING)
  SelectionWork selection_work_{};
#endif
};

}  // namespace m3
