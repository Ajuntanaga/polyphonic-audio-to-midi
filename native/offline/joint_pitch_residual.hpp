#pragma once

#include <array>
#include <complex>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/joint_pitch_residual.hpp"

namespace m3::offline {

using m3::kJointPitchHarmonics;
using m3::JointPitchObservation;
using m3::JointPitchResidualResult;

// Offline weighted least-squares fit of the emitted pitch set and every
// one-pitch deletion. It reads existing resonator observations only. Each
// sinusoidal partial has independent sine/cosine coefficients; duplicate
// physical frequencies are shared, so the same harmonic is not counted twice.
class JointPitchResidual final {
 public:
  [[nodiscard]] JointPitchResidualResult evaluate(
      const std::array<JointPitchObservation, kMaxVoices>& observations,
      std::size_t count, double sample_rate, double decay,
      double signal_energy) noexcept;

 private:
  static constexpr std::size_t kMaxPartials =
      kMaxVoices * kJointPitchHarmonics;
  static constexpr std::size_t kMaxDimensions = 2U * kMaxPartials;
  struct Model final {
    bool valid{};
    std::size_t size{};
    std::array<std::size_t, kMaxDimensions> indices{};
    std::array<double, kMaxDimensions * kMaxDimensions> lower{};
  };
  void rebuild(std::size_t count, double sample_rate, double decay) noexcept;
  [[nodiscard]] double explained_energy(
      const Model& model,
      const std::array<double, kMaxDimensions>& observation) const noexcept;

  std::array<double, kMaxPartials> frequencies_{};
  std::array<std::uint8_t, kMaxPartials> owners_{};
  std::size_t partial_count_{};
  std::size_t pitch_count_{};
  double sample_rate_{};
  double decay_{};
  std::array<Model, kMaxVoices + 1U> models_{};
};

}  // namespace m3::offline
