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
// Rebuild cost still requires a callback-budget measurement before integration.
class JointPitchResidual final {
 public:
  [[nodiscard]] JointPitchResidualResult evaluate(
      const std::array<JointPitchObservation, kMaxVoices>& observations,
      std::size_t count, double sample_rate, double decay,
      double signal_energy) noexcept;

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
  void rebuild(std::size_t count, double sample_rate, double decay) noexcept;

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
  std::array<double, kMaxDimensions * (kMaxDimensions + 1U) / 2U> lower_{};
  std::array<Deletion, kMaxVoices> deletions_{};
};

}  // namespace m3
