#include "m3/joint_pitch_residual.hpp"

#include <algorithm>
#include <cmath>

namespace m3 {
namespace {
constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kRidge = 1.0e-8;

std::complex<double> window_response(double radians, double decay) noexcept {
  const double one_minus = 1.0 - decay;
  const double real = one_minus + decay * (1.0 - std::cos(radians));
  const double imaginary = decay * std::sin(radians);
  const double denominator = real * real + imaginary * imaginary;
  return {one_minus * real / denominator, one_minus * imaginary / denominator};
}
}  // namespace

void JointPitchResidual::rebuild(std::size_t count, double sample_rate,
                                 double decay) noexcept {
  pitch_count_ = count;
  sample_rate_ = sample_rate;
  decay_ = decay;
  valid_ = false;
  const std::size_t dimensions = 2U * partial_count_;
  // Fill the lower triangle in place; no second full matrix is needed.
  for (std::size_t i = 0U; i < partial_count_; ++i) {
    for (std::size_t j = 0U; j <= i; ++j) {
      const auto difference = window_response(
          kTwoPi * (frequencies_[i] - frequencies_[j]) / sample_rate, decay);
      const auto sum = window_response(
          kTwoPi * (frequencies_[i] + frequencies_[j]) / sample_rate, decay);
      lower_[packed(2U * i, 2U * j)] = 0.5 * (difference.real() + sum.real());
      lower_[packed(2U * i + 1U, 2U * j + 1U)] = 0.5 * (difference.real() - sum.real());
      lower_[packed(2U * i + 1U, 2U * j)] = 0.5 * (sum.imag() + difference.imag());
      if (i != j) {
        lower_[packed(2U * i, 2U * j + 1U)] = 0.5 * (sum.imag() - difference.imag());
      }
    }
  }
  for (std::size_t row = 0U; row < dimensions; ++row) {
    lower_[packed(row, row)] += kRidge;
    for (std::size_t column = 0U; column <= row; ++column) {
      double value = lower_[packed(row, column)];
      for (std::size_t k = 0U; k < column; ++k) {
        value -= lower_[packed(row, k)] * lower_[packed(column, k)];
      }
      if (!std::isfinite(value) || (row == column && value <= 1.0e-12)) {
        return;
      }
      lower_[packed(row, column)] = row == column
          ? std::sqrt(value) : value / lower_[packed(column, column)];
    }
  }
  // For deleted columns U, full - omitted = beta_U^T (G^-1_UU)^-1 beta_U,
  // with G including the same ridge as each reference deletion model.
  // G^-1_UU = (L^-1 E_U)^T (L^-1 E_U). Only <=12 unit solves and one small
  // factor are retained for each pitch; the temporary unit solves are reused.
  std::array<double, kPitchDimensions * kMaxDimensions> units{};
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    auto& deletion = deletions_[pitch];
    deletion.size = 0U;
    const auto owner = static_cast<std::uint8_t>(1U << pitch);
    for (std::size_t partial = 0U; partial < partial_count_; ++partial) {
      if (owners_[partial] == owner) {
        deletion.indices[deletion.size++] = 2U * partial;
        deletion.indices[deletion.size++] = 2U * partial + 1U;
      }
    }
    units.fill(0.0);
    for (std::size_t j = 0U; j < deletion.size; ++j) {
      const auto index = deletion.indices[j];
      for (std::size_t row = index; row < dimensions; ++row) {
        double value = row == index ? 1.0 : 0.0;
        for (std::size_t k = index; k < row; ++k) {
          value -= lower_[packed(row, k)] * units[j * kMaxDimensions + k];
        }
        units[j * kMaxDimensions + row] = value / lower_[packed(row, row)];
      }
    }
    for (std::size_t row = 0U; row < deletion.size; ++row) {
      for (std::size_t column = 0U; column <= row; ++column) {
        double value = 0.0;
        for (std::size_t k = std::max(deletion.indices[row], deletion.indices[column]);
             k < dimensions; ++k) {
          value += units[row * kMaxDimensions + k] * units[column * kMaxDimensions + k];
        }
        for (std::size_t k = 0U; k < column; ++k) {
          value -= deletion.lower[packed(row, k)] * deletion.lower[packed(column, k)];
        }
        if (!std::isfinite(value) || (row == column && value <= 1.0e-12)) {
          return;
        }
        deletion.lower[packed(row, column)] = row == column
            ? std::sqrt(value) : value / deletion.lower[packed(column, column)];
      }
    }
  }
  fundamental_overlap_.fill(0.0);
  shared_fundamental_.fill(false);
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    const double fundamental = fundamentals_[pitch];
    for (std::size_t partial = 0U; partial < partial_count_; ++partial) {
      if (fundamental > 0.0 &&
          (owners_[partial] & static_cast<std::uint8_t>(~(1U << pitch))) != 0U) {
        const double overlap = std::norm(window_response(
            kTwoPi * (frequencies_[partial] - fundamental) / sample_rate, decay));
        fundamental_overlap_[pitch] = std::max(fundamental_overlap_[pitch], overlap);
        if (std::abs(frequencies_[partial] - fundamental) <= 1.0e-9 * fundamental) {
          shared_fundamental_[pitch] = true;
        }
      }
    }
  }
  valid_ = true;
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
  std::array<double, kMaxVoices> fundamentals{};
  std::array<double, kMaxDimensions> values{};
  std::size_t partial_count = 0U;
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    fundamentals[pitch] = observations[pitch].frequency_hz[0U];
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
      frequencies != frequencies_ || owners != owners_ || fundamentals != fundamentals_) {
    frequencies_ = frequencies;
    owners_ = owners;
    fundamentals_ = fundamentals;
    partial_count_ = partial_count;
    rebuild(count, sample_rate, decay);
  }
  if (!valid_) {
    return result;
  }
  const auto dimensions = 2U * partial_count_;
  std::array<double, kMaxDimensions> whitened{}, coefficients{};
  double full = 0.0;
  for (std::size_t row = 0U; row < dimensions; ++row) {
    double value = values[row];
    for (std::size_t column = 0U; column < row; ++column) {
      value -= lower_[packed(row, column)] * whitened[column];
    }
    whitened[row] = value / lower_[packed(row, row)];
    full += whitened[row] * whitened[row];
  }
  if (!std::isfinite(full) || full < 0.0 || full > signal_energy * 1.00001) {
    return result;
  }
  for (std::size_t row = dimensions; row-- > 0U;) {
    double value = whitened[row];
    for (std::size_t column = row + 1U; column < dimensions; ++column) {
      value -= lower_[packed(column, row)] * coefficients[column];
    }
    coefficients[row] = value / lower_[packed(row, row)];
  }
  for (std::size_t pitch = 0U; pitch < count; ++pitch) {
    const auto& deletion = deletions_[pitch];
    std::array<double, kPitchDimensions> contribution{};
    double independent = 0.0;
    for (std::size_t row = 0U; row < deletion.size; ++row) {
      double value = coefficients[deletion.indices[row]];
      for (std::size_t column = 0U; column < row; ++column) {
        value -= deletion.lower[packed(row, column)] * contribution[column];
      }
      contribution[row] = value / deletion.lower[packed(row, row)];
      independent += contribution[row] * contribution[row];
    }
    if (!std::isfinite(independent) || independent > full + signal_energy * 1.0e-7) {
      return result;
    }
    result.independent_energy_fraction[pitch] = std::min(full, independent) / signal_energy;
  }
  result.fundamental_overlap = fundamental_overlap_;
  result.shared_fundamental = shared_fundamental_;
  result.residual_fraction = std::max(0.0, signal_energy - full) / signal_energy;
  result.valid = true;
  return result;
}

}  // namespace m3
