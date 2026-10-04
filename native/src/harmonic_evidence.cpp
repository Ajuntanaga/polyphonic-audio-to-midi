#include "m3/harmonic_evidence.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3 {
namespace {

constexpr double kLogFloor = 1.0 / 32767.0;

double square(double value) noexcept { return value * value; }

}  // namespace

HarmonicEvidence make_harmonic_evidence(
    const std::array<double, kHarmonicEvidenceCount>& energy) noexcept {
  HarmonicEvidence result;
  double total = 0.0;
  for (const double value : energy) {
    if (!std::isfinite(value) || value < 0.0) {
      return result;
    }
    total += value;
  }
  if (!std::isfinite(total) || total <= std::numeric_limits<double>::epsilon()) {
    return result;
  }
  for (std::size_t harmonic = 0U; harmonic < energy.size(); ++harmonic) {
    result.normalized_energy[harmonic] = energy[harmonic] / total;
    result.centroid += static_cast<double>(harmonic) *
                       result.normalized_energy[harmonic];
    if (harmonic >= 3U) {
      result.upper_share += result.normalized_energy[harmonic];
    }
  }
  result.centroid /= static_cast<double>(energy.size() - 1U);
  for (std::size_t harmonic = 1U; harmonic < energy.size(); ++harmonic) {
    result.adjacent_log_ratio[harmonic - 1U] =
        std::log(std::max(result.normalized_energy[harmonic], kLogFloor)) -
        std::log(std::max(result.normalized_energy[harmonic - 1U],
                          kLogFloor));
  }
  result.valid = true;
  return result;
}

HarmonicEvidenceComparison compare_harmonic_evidence(
    const HarmonicEvidence& observed,
    const HarmonicEvidence& reference) noexcept {
  HarmonicEvidenceComparison result;
  if (!observed.valid || !reference.valid) {
    result.lower_log_likelihood = -64.0;
    result.upper_log_likelihood = -64.0;
    result.balance_log_likelihood = -64.0;
    return result;
  }
  double lower_error = 0.0;
  for (std::size_t ratio = 0U; ratio < 2U; ++ratio) {
    lower_error += square(observed.adjacent_log_ratio[ratio] -
                          reference.adjacent_log_ratio[ratio]);
  }
  double upper_error = 0.0;
  for (std::size_t ratio = 3U;
       ratio < observed.adjacent_log_ratio.size(); ++ratio) {
    upper_error += square(observed.adjacent_log_ratio[ratio] -
                          reference.adjacent_log_ratio[ratio]);
  }
  result.lower_log_likelihood = -0.75 * lower_error;
  result.upper_log_likelihood = -0.75 * upper_error;
  result.balance_log_likelihood =
      -8.0 * square(observed.upper_share - reference.upper_share) -
      4.0 * square(observed.centroid - reference.centroid);
  return result;
}

double harmonic_transient_strength(const HarmonicEvidence& fast,
                                   const HarmonicEvidence& settled) noexcept {
  if (!fast.valid || !settled.valid) {
    return 1.0;
  }
  double distance = 0.0;
  for (std::size_t harmonic = 0U; harmonic < kHarmonicEvidenceCount;
       ++harmonic) {
    distance += std::abs(fast.normalized_energy[harmonic] -
                         settled.normalized_energy[harmonic]);
  }
  return std::clamp(0.5 * distance, 0.0, 1.0);
}

}  // namespace m3
