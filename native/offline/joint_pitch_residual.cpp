#include "joint_pitch_residual.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3::offline {
namespace {
constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kRidge = 1.0e-8;

// Sum (1-a) a^k exp(i*w*k), k >= 0. This is the exact infinite-history
// response of the same exponential window used by the detector's cells.
std::complex<double> window_response(double radians, double decay) noexcept {
  const double one_minus = 1.0 - decay;
  const double real = one_minus + decay * (1.0 - std::cos(radians));
  const double imaginary = decay * std::sin(radians);
  const double denominator = real * real + imaginary * imaginary;
  return {one_minus * real / denominator,
          one_minus * imaginary / denominator};
}
}  // namespace

void JointPitchResidual::rebuild(std::size_t count, double sample_rate,
                                 double decay) noexcept {
  pitch_count_ = count;
  sample_rate_ = sample_rate;
  decay_ = decay;
  std::array<double, kMaxDimensions * kMaxDimensions> gram{};
  for (std::size_t i = 0U; i < partial_count_; ++i) {
    for (std::size_t j = 0U; j < partial_count_; ++j) {
      const auto difference = window_response(
          kTwoPi * (frequencies_[i] - frequencies_[j]) / sample_rate, decay);
      const auto sum = window_response(
          kTwoPi * (frequencies_[i] + frequencies_[j]) / sample_rate, decay);
      gram[(2U * i) * kMaxDimensions + 2U * j] =
          0.5 * (difference.real() + sum.real());
      gram[(2U * i + 1U) * kMaxDimensions + 2U * j + 1U] =
          0.5 * (difference.real() - sum.real());
      gram[(2U * i) * kMaxDimensions + 2U * j + 1U] =
          0.5 * (sum.imag() - difference.imag());
      gram[(2U * i + 1U) * kMaxDimensions + 2U * j] =
          0.5 * (sum.imag() + difference.imag());
    }
  }
  for (std::size_t omission = 0U; omission <= count; ++omission) {
    Model& model = models_[omission];
    model.size = 0U;
    model.valid = true;
    const auto omitted_owner = omission == 0U
        ? static_cast<std::uint8_t>(0U)
        : static_cast<std::uint8_t>(1U << (omission - 1U));
    for (std::size_t partial = 0U; partial < partial_count_; ++partial) {
      if ((owners_[partial] & static_cast<std::uint8_t>(~omitted_owner)) == 0U) {
        continue;
      }
      model.indices[model.size++] = 2U * partial;
      model.indices[model.size++] = 2U * partial + 1U;
    }
    for (std::size_t row = 0U; row < model.size; ++row) {
      for (std::size_t column = 0U; column <= row; ++column) {
        double value = gram[model.indices[row] * kMaxDimensions +
                            model.indices[column]];
        if (row == column) {
          value += kRidge;
        }
        for (std::size_t k = 0U; k < column; ++k) {
          value -= model.lower[row * kMaxDimensions + k] *
                   model.lower[column * kMaxDimensions + k];
        }
        if (!std::isfinite(value) || (row == column && value <= 1.0e-12)) {
          model.valid = false;
          break;
        }
        model.lower[row * kMaxDimensions + column] = row == column
            ? std::sqrt(value)
            : value / model.lower[column * kMaxDimensions + column];
      }
      if (!model.valid) {
        break;
      }
    }
  }
}

double JointPitchResidual::explained_energy(
    const Model& model,
    const std::array<double, kMaxDimensions>& observation) const noexcept {
  if (!model.valid) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  // b^T (L L^T)^-1 b = ||L^-1 b||^2; no second triangular solve is needed.
  std::array<double, kMaxDimensions> whitened{};
  double energy = 0.0;
  for (std::size_t row = 0U; row < model.size; ++row) {
    double value = observation[model.indices[row]];
    for (std::size_t column = 0U; column < row; ++column) {
      value -= model.lower[row * kMaxDimensions + column] * whitened[column];
    }
    value /= model.lower[row * kMaxDimensions + row];
    whitened[row] = value;
    energy += value * value;
  }
  return energy;
}

JointPitchResidualResult JointPitchResidual::evaluate(
    const std::array<JointPitchObservation, kMaxVoices>& observations,
    std::size_t count, double sample_rate, double decay,
    double signal_energy) noexcept {
  JointPitchResidualResult result;
  if (count == 0U || count > kMaxVoices || !std::isfinite(sample_rate) ||
      sample_rate <= 0.0 || !std::isfinite(decay) || decay <= 0.0 ||
      decay >= 1.0 || !std::isfinite(signal_energy) || signal_energy <= 1.0e-20) {
    return result;
  }
  std::array<double, kMaxPartials> frequencies{};
  std::array<std::uint8_t, kMaxPartials> owners{};
  std::array<double, kMaxDimensions> values{};
  std::size_t partial_count = 0U;
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    for (std::size_t h = 0U; h < kJointPitchHarmonics; ++h) {
      const double frequency = observations[pitch].frequency_hz[h];
      if (frequency == 0.0) {
        continue;
      }
      const auto observed = observations[pitch].correlation[h];
      if (!std::isfinite(frequency) || frequency <= 0.0 ||
          frequency >= 0.5 * sample_rate || !std::isfinite(observed.real()) ||
          !std::isfinite(observed.imag())) {
        return result;
      }
      std::size_t partial = 0U;
      for (; partial < partial_count; ++partial) {
        if (std::abs(frequencies[partial] - frequency) <= 1.0e-9 * frequency) {
          break;
        }
      }
      if (partial == partial_count) {
        frequencies[partial] = frequency;
        values[2U * partial] = observed.real();
        values[2U * partial + 1U] = observed.imag();
        ++partial_count;
      }
      owners[partial] = static_cast<std::uint8_t>(owners[partial] | (1U << pitch));
    }
  }
  if (partial_count == 0U) {
    return result;
  }
  if (partial_count != partial_count_ || count != pitch_count_ ||
      sample_rate != sample_rate_ || decay != decay_ ||
      frequencies != frequencies_ || owners != owners_) {
    frequencies_ = frequencies;
    owners_ = owners;
    partial_count_ = partial_count;
    rebuild(count, sample_rate, decay);
  }
  const double full = explained_energy(models_[0U], values);
  if (!std::isfinite(full) || full < 0.0 || full > signal_energy * 1.00001) {
    return result;
  }
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    const double omitted = explained_energy(models_[pitch + 1U], values);
    if (!std::isfinite(omitted) || omitted > full + signal_energy * 1.0e-7) {
      return result;
    }
    result.independent_energy_fraction[pitch] =
        std::max(0.0, full - omitted) / signal_energy;
    const double fundamental = observations[pitch].frequency_hz[0U];
    for (std::size_t partial = 0U; partial < partial_count_; ++partial) {
      if (fundamental > 0.0 &&
          (owners_[partial] & static_cast<std::uint8_t>(~(1U << pitch))) != 0U) {
        const double overlap = std::norm(window_response(
            kTwoPi * (frequencies_[partial] - fundamental) / sample_rate,
            decay));
        result.fundamental_overlap[pitch] = std::max(
            result.fundamental_overlap[pitch], overlap);
      }
      if (fundamental > 0.0 &&
          std::abs(frequencies_[partial] - fundamental) <=
              1.0e-9 * fundamental &&
          (owners_[partial] & static_cast<std::uint8_t>(~(1U << pitch))) != 0U) {
        result.shared_fundamental[pitch] = true;
      }
    }
  }
  result.residual_fraction = std::max(0.0, signal_energy - full) / signal_energy;
  result.valid = true;
  return result;
}

}  // namespace m3::offline
