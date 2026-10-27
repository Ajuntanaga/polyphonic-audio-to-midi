#pragma once

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)

#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <cstddef>

namespace m3::diagnostics {

// Upper triangle of the eight physical strings, in string order.
constexpr std::size_t beat_pair_index(std::size_t first,
                                     std::size_t second) noexcept {
  return first * (15U - first) / 2U + second - first - 1U;
}

// Offline comparison only. The fitted nuisance trend and subsequent beat
// correlation use the same supplied Hann weights. Frequency, history and
// coherence thresholds remain the production caller's responsibility.
template <std::size_t Capacity>
struct HannDetrendedBeatShadow final {
  std::array<double, Capacity> seconds{};
  std::array<double, Capacity> weighted_residual{};
  double absolute_sum{};
  double duration_seconds{};
  std::size_t count{};
  bool uniform{};

  bool prepare(const std::array<double, Capacity>& sample_seconds,
               const std::array<double, Capacity>& energy,
               const std::array<double, Capacity>& weights,
               std::size_t samples) noexcept {
    count = 0U;
    absolute_sum = 0.0;
    duration_seconds = 0.0;
    if (samples < 3U || samples > Capacity) {
      return false;
    }
    double weight_sum = 0.0;
    double mean_time = 0.0;
    double mean_energy = 0.0;
    for (std::size_t i = 0U; i < samples; ++i) {
      if (!std::isfinite(sample_seconds[i]) || !std::isfinite(energy[i]) ||
          !std::isfinite(weights[i]) || weights[i] < 0.0 ||
          (i != 0U && sample_seconds[i] <= sample_seconds[i - 1U])) {
        return false;
      }
      seconds[i] = sample_seconds[i] - sample_seconds[0U];
      weight_sum += weights[i];
      mean_time += weights[i] * seconds[i];
      mean_energy += weights[i] * energy[i];
    }
    if (!std::isfinite(weight_sum) || weight_sum <= 1.0e-15) {
      return false;
    }
    mean_time /= weight_sum;
    mean_energy /= weight_sum;
    double covariance = 0.0;
    double variance = 0.0;
    for (std::size_t i = 0U; i < samples; ++i) {
      const double centered_time = seconds[i] - mean_time;
      covariance += weights[i] * centered_time * (energy[i] - mean_energy);
      variance += weights[i] * centered_time * centered_time;
    }
    if (!std::isfinite(covariance) || !std::isfinite(variance) ||
        variance <= 1.0e-15) {
      return false;
    }
    const double slope = covariance / variance;
    uniform = true;
    for (std::size_t i = 0U; i < samples; ++i) {
      const double residual =
          energy[i] - (mean_energy + slope * (seconds[i] - mean_time));
      weighted_residual[i] = weights[i] * residual;
      absolute_sum += weights[i] * std::abs(residual);
      uniform = uniform &&
          std::abs(seconds[i] - static_cast<double>(i) * seconds[1U]) <=
              1.0e-12;
    }
    if (!std::isfinite(absolute_sum)) {
      return false;
    }
    duration_seconds = seconds[samples - 1U];
    count = samples;
    return true;
  }

  [[nodiscard]] double coherence(double beat_hz) const noexcept {
    constexpr double kTwoPi = 6.28318530717958647692;
    if (count < 3U || !std::isfinite(beat_hz) || beat_hz <= 0.0 ||
        absolute_sum <= 1.0e-15) {
      return 0.0;
    }
    std::complex<double> correlation{};
    if (uniform) {
      const auto step = std::polar(1.0, -kTwoPi * beat_hz * seconds[1U]);
      std::complex<double> phase{1.0, 0.0};
      for (std::size_t i = 0U; i < count; ++i) {
        correlation += weighted_residual[i] * phase;
        phase *= step;
      }
    } else {
      for (std::size_t i = 0U; i < count; ++i) {
        correlation += weighted_residual[i] *
            std::polar(1.0, -kTwoPi * beat_hz * seconds[i]);
      }
    }
    return std::clamp(std::abs(correlation) / absolute_sum, 0.0, 1.0);
  }
};

}  // namespace m3::diagnostics

#endif
