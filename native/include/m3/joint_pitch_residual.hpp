#pragma once

#include <array>
#include <complex>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"

namespace m3 {

inline constexpr std::size_t kJointPitchHarmonics = 6U;

struct JointPitchObservation final {
  std::uint8_t note{};
  std::array<double, kJointPitchHarmonics> frequency_hz{};
  // Relative to the current sample, rather than the cell's oscillator phase.
  std::array<std::complex<double>, kJointPitchHarmonics> correlation{};
};

struct JointPitchResidualResult final {
  bool valid{};
  double residual_fraction{};
  std::array<double, kMaxVoices> independent_energy_fraction{};
  std::array<bool, kMaxVoices> shared_fundamental{};
  std::array<double, kMaxVoices> fundamental_overlap{};
};

// Allocation-free fit of an emitted pitch set. A single factorization supplies
// all one-pitch deletions through Schur complements. Identical partials remain
// shared; omitting a pitch removes only the columns that it owns exclusively.
// The bounded entry point spreads rebuilding over calls and returns invalid
// until the current model is complete. No previous model is used as a fallback.
class JointPitchResidual final {
 public:
  static constexpr std::size_t kMaxRebuildWorkPerCall = 4U;

  // Synchronous numerical reference path for offline replay.
  [[nodiscard]] JointPitchResidualResult evaluate(
      const std::array<JointPitchObservation, kMaxVoices>& observations,
      std::size_t count, double sample_rate, double decay,
      double signal_energy) noexcept;

  [[nodiscard]] JointPitchResidualResult evaluate_bounded(
      const std::array<JointPitchObservation, kMaxVoices>& observations,
      std::size_t count, double sample_rate, double decay, double signal_energy,
      std::size_t work_budget = kMaxRebuildWorkPerCall) noexcept;

  void reset() noexcept;
  [[nodiscard]] std::size_t last_rebuild_work_units() const noexcept {
    return last_rebuild_work_units_;
  }
  [[nodiscard]] bool rebuild_pending() const noexcept;

 private:
  static constexpr std::size_t kMaxPartials = kMaxVoices * kJointPitchHarmonics;
  static constexpr std::size_t kMaxDimensions = 2U * kMaxPartials;
  static constexpr std::size_t kPitchDimensions = 2U * kJointPitchHarmonics;
  static constexpr std::size_t packed(std::size_t row, std::size_t column) noexcept {
    return row * (row + 1U) / 2U + column;
  }
  struct Deletion final {
    std::size_t size{};
    std::array<std::size_t, kPitchDimensions> indices{};
    // Cholesky factor of the corresponding block of the full Gram inverse.
    std::array<double, kPitchDimensions * (kPitchDimensions + 1U) / 2U> lower{};
  };
  enum class BuildStage : std::uint8_t {
    idle, gram, full_factor, deletion_setup, unit_solve, deletion_factor,
    overlap, ready, failed
  };
  void start_rebuild(std::size_t count, double sample_rate, double decay) noexcept;
  void advance_rebuild() noexcept;
  [[nodiscard]] JointPitchResidualResult evaluate_impl(
      const std::array<JointPitchObservation, kMaxVoices>& observations,
      std::size_t count, double sample_rate, double decay, double signal_energy,
      std::size_t work_budget, bool synchronous) noexcept;

  std::array<double, kMaxPartials> frequencies_{};
  std::array<std::uint8_t, kMaxPartials> owners_{};
  std::array<double, kMaxVoices> fundamentals_{};
  std::array<double, kMaxVoices> fundamental_overlap_{};
  std::array<bool, kMaxVoices> shared_fundamental_{};
  std::size_t partial_count_{};
  std::size_t pitch_count_{};
  double sample_rate_{};
  double decay_{};
  bool valid_{};
  BuildStage stage_{BuildStage::idle};
  std::size_t build_index_{};
  std::size_t build_pitch_{};
  std::size_t last_rebuild_work_units_{};
  std::array<double, kMaxDimensions * (kMaxDimensions + 1U) / 2U> lower_{};
  std::array<Deletion, kMaxVoices> deletions_{};
  std::array<double, kPitchDimensions * kMaxDimensions> units_{};
};

}  // namespace m3
