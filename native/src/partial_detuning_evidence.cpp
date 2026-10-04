#include "m3/partial_detuning_evidence.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3 {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kEnergyFloor = 1.0e-12;
constexpr double kMaximumOffsetFraction = 0.45;
constexpr double kFilterMix = 0.18;
constexpr double kPhasorSmoothingSeconds = 0.030;
constexpr std::uint16_t kRequiredUpdates = 4U;

bool usable(const PartialDetuningFrame& frame, std::size_t partial) noexcept {
  return std::isfinite(frame.real[partial]) &&
         std::isfinite(frame.imaginary[partial]) &&
         std::isfinite(frame.center_hz[partial]) &&
         std::isfinite(frame.energy[partial]) && frame.center_hz[partial] > 0.0 &&
         frame.energy[partial] > kEnergyFloor;
}

}  // namespace

PartialDetuningComparison compare_partial_detuning(
    const PartialDetuningEvidence& observed,
    const std::array<double, kPartialDetuningCount>& reference_cents,
    std::uint8_t reference_valid_mask, double scale_cents) noexcept {
  PartialDetuningComparison result{};
  if (!std::isfinite(scale_cents) || scale_cents <= 0.0 ||
      (reference_valid_mask & 0xC0U) != 0U) {
    return result;
  }
  double squared_error = 0.0;
  for (std::size_t partial = 1U; partial < kPartialDetuningCount; ++partial) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << partial);
    if ((observed.valid_mask & reference_valid_mask & bit) == 0U ||
        !std::isfinite(observed.residual_cents[partial]) ||
        !std::isfinite(reference_cents[partial])) {
      continue;
    }
    const double normalized =
        (observed.residual_cents[partial] - reference_cents[partial]) /
        scale_cents;
    squared_error += std::min(64.0, normalized * normalized);
    ++result.common_partials;
  }
  if (result.common_partials == 0U) {
    return result;
  }
  result.log_likelihood =
      -0.5 * squared_error / static_cast<double>(result.common_partials);
  result.valid = true;
  return result;
}

void PartialDetuningTracker::reset() noexcept { *this = {}; }

void PartialDetuningTracker::update(const PartialDetuningFrame& frame,
                                    double decisions_per_second) noexcept {
  if (!std::isfinite(decisions_per_second) || decisions_per_second <= 0.0) {
    reset();
    return;
  }

  std::uint8_t current_mask = 0U;
  const double phasor_mix =
      1.0 - std::exp(-1.0 /
                     (kPhasorSmoothingSeconds * decisions_per_second));
  for (std::size_t partial = 0U; partial < kPartialDetuningCount; ++partial) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << partial);
    if (!usable(frame, partial)) {
      accepted_updates_[partial] = 0U;
      continue;
    }
    current_mask = static_cast<std::uint8_t>(current_mask | bit);
    filtered_real_[partial] +=
        phasor_mix * (frame.real[partial] - filtered_real_[partial]);
    filtered_imaginary_[partial] +=
        phasor_mix * (frame.imaginary[partial] - filtered_imaginary_[partial]);
    filtered_twice_real_[partial] +=
        phasor_mix *
        (filtered_real_[partial] - filtered_twice_real_[partial]);
    filtered_twice_imaginary_[partial] +=
        phasor_mix *
        (filtered_imaginary_[partial] - filtered_twice_imaginary_[partial]);
    if ((previous_mask_ & bit) != 0U) {
      const double dot =
          previous_real_[partial] * filtered_twice_real_[partial] +
          previous_imaginary_[partial] * filtered_twice_imaginary_[partial];
      const double cross =
          previous_real_[partial] * filtered_twice_imaginary_[partial] -
          previous_imaginary_[partial] * filtered_twice_real_[partial];
      const double phase_delta = std::atan2(cross, dot);
      const double offset_hz =
          phase_delta * decisions_per_second / kTwoPi;
      const double measured_hz = frame.center_hz[partial] + offset_hz;
      const bool bounded =
          std::abs(offset_hz) <= decisions_per_second * kMaximumOffsetFraction;
      if (bounded && measured_hz > 0.0 && std::isfinite(measured_hz)) {
        const double cents =
            1200.0 * std::log2(measured_hz / frame.center_hz[partial]);
        if (std::isfinite(cents)) {
          if (accepted_updates_[partial] == 0U) {
            filtered_cents_[partial] = cents;
          } else {
            filtered_cents_[partial] +=
                kFilterMix * (cents - filtered_cents_[partial]);
          }
          if (accepted_updates_[partial] <
              std::numeric_limits<std::uint16_t>::max()) {
            ++accepted_updates_[partial];
          }
        }
      }
    }
    previous_real_[partial] = filtered_twice_real_[partial];
    previous_imaginary_[partial] = filtered_twice_imaginary_[partial];
  }
  previous_mask_ = current_mask;
}

PartialDetuningEvidence PartialDetuningTracker::evidence() const noexcept {
  PartialDetuningEvidence result{};
  if (accepted_updates_[0U] < kRequiredUpdates) {
    return result;
  }

  double upper_sum = 0.0;
  std::size_t upper_count = 0U;
  for (std::size_t partial = 0U; partial < kPartialDetuningCount; ++partial) {
    if (accepted_updates_[partial] < kRequiredUpdates) {
      continue;
    }
    result.residual_cents[partial] =
        filtered_cents_[partial] - filtered_cents_[0U];
    result.valid_mask = static_cast<std::uint8_t>(
        result.valid_mask | static_cast<std::uint8_t>(1U << partial));
    if (partial >= 3U) {
      upper_sum += result.residual_cents[partial];
      ++upper_count;
    }
  }
  if (upper_count == 0U) {
    return result;
  }
  result.upper_mean_cents = upper_sum / static_cast<double>(upper_count);
  result.valid = true;
  return result;
}

}  // namespace m3
