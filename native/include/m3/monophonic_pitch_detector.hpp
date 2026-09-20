#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/types.hpp"

namespace m3 {

struct DetectorDecision final {
  TickTransitions transitions{};
};

// The historical type name is retained for ABI/source compatibility. The
// implementation now ranks and tracks up to PersistentConfig::max_polyphony
// independent candidates.
class MonophonicPitchDetector final {
 public:
  MonophonicPitchDetector() noexcept = default;
  MonophonicPitchDetector(const MonophonicPitchDetector&) = delete;
  MonophonicPitchDetector& operator=(const MonophonicPitchDetector&) = delete;

  bool configure(double sample_rate, const PersistentConfig& config) noexcept;
  void set_runtime_config(const PersistentConfig& config) noexcept;
  void reset() noexcept;
  [[nodiscard]] DetectorDecision process_sample(double sample) noexcept;

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

  [[nodiscard]] DetectorDecision make_decision() noexcept;
  void update_cell(Cell& cell, double sample) noexcept;
  [[nodiscard]] double candidate_score(std::size_t candidate) const noexcept;
  [[nodiscard]] std::uint8_t dynamic_velocity() const noexcept;
  [[nodiscard]] std::uint8_t attack_decisions() const noexcept;
  [[nodiscard]] std::uint8_t release_decisions() const noexcept;
  [[nodiscard]] double signal_floor() const noexcept;
  void append_transition(DetectorDecision& decision, TransitionKind kind,
                         std::uint8_t note, std::uint8_t velocity) noexcept;
  [[nodiscard]] std::size_t cell_index(std::size_t candidate,
                                       std::size_t harmonic) const noexcept {
    return candidate * kHarmonicCount + harmonic;
  }

  std::array<Cell, kCellCount> cells_{};
  double sample_rate_{};
  double dc_pole{};
  double correlation_decay{};
  double fast_energy_decay{};
  double slow_energy_decay{};
  double previous_input_{};
  double previous_dc_output_{};
  double fast_energy_{};
  double slow_energy_{};
  std::uint32_t decision_phase_{};
  std::uint32_t transition_sequence_{};
  std::uint8_t lowest_note_{};
  std::uint8_t candidate_count_{};
  std::uint8_t sensitivity_{50U};
  std::uint8_t response_{25U};
  std::uint8_t fixed_velocity_{100U};
  VelocityMode velocity_mode_{VelocityMode::dynamic};
  std::uint8_t max_polyphony_{1U};
  std::array<bool, kMaxCandidates> active_{};
  std::array<std::uint8_t, kMaxCandidates> pending_ticks_{};
  std::array<std::uint8_t, kMaxCandidates> quiet_ticks_{};
  bool configured_{};
};

}  // namespace m3
