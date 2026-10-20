#include "m3/unison_spectral_tracker.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "m3/pitch_math.hpp"

namespace m3 {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kNaturalLogTwo = 0.69314718055994530942;
constexpr double kMemorySeconds = 0.150;
constexpr double kReadySeconds = 0.200;
constexpr double kSettledSeconds = 0.350;
constexpr double kMinimumSampleRate = 8000.0;
constexpr double kMaximumSampleRate = 384000.0;

std::uint64_t seconds_to_samples(double seconds, double sample_rate) noexcept {
  const double samples = std::ceil(seconds * sample_rate);
  return static_cast<std::uint64_t>(
      std::clamp(samples, 1.0,
                 static_cast<double>(std::numeric_limits<std::uint64_t>::max())));
}

}  // namespace

bool UnisonSpectralCorridorTracker::configure(
    double sample_rate, std::uint8_t midi_note) noexcept {
  if (!std::isfinite(sample_rate) || sample_rate < kMinimumSampleRate ||
      sample_rate > kMaximumSampleRate || midi_note > 127U) {
    return false;
  }
  const double center = midi_to_frequency(midi_note, 440.0);
  if (!std::isfinite(center) || center <= 0.0) {
    return false;
  }
  for (std::size_t harmonic = 0U;
       harmonic < kUnisonSpectralHarmonicCount; ++harmonic) {
    for (std::size_t offset = 0U;
         offset < kUnisonSpectralOffsetsPerHarmonic; ++offset) {
      const double fraction =
          static_cast<double>(offset) /
          static_cast<double>(kUnisonSpectralOffsetsPerHarmonic - 1U);
      const double cents = -100.0 + 200.0 * fraction;
      const double frequency = static_cast<double>(harmonic + 1U) * center *
                               std::exp(kNaturalLogTwo * cents / 1200.0);
      if (!std::isfinite(frequency) || frequency >= 0.5 * sample_rate) {
        configured_ = false;
        return false;
      }
      const std::size_t feature =
          harmonic * kUnisonSpectralOffsetsPerHarmonic + offset;
      const double radians = kTwoPi * frequency / sample_rate;
      cosine_step_[feature] = std::cos(radians);
      sine_step_[feature] = std::sin(radians);
    }
  }
  decay_ = std::exp(-1.0 / (kMemorySeconds * sample_rate));
  ready_samples_ = seconds_to_samples(kReadySeconds, sample_rate);
  settled_samples_ = seconds_to_samples(kSettledSeconds, sample_rate);
  configured_ = true;
  reset();
  return true;
}

void UnisonSpectralCorridorTracker::observe(double sample) noexcept {
  if (!configured_ || !std::isfinite(sample)) {
    return;
  }
  for (std::size_t feature = 0U; feature < kUnisonSpectralFeatureCount;
       ++feature) {
    correlation_real_[feature] =
        decay_ * correlation_real_[feature] + sample * oscillator_real_[feature];
    correlation_imaginary_[feature] =
        decay_ * correlation_imaginary_[feature] -
        sample * oscillator_imaginary_[feature];
    const double next_real =
        oscillator_real_[feature] * cosine_step_[feature] -
        oscillator_imaginary_[feature] * sine_step_[feature];
    const double next_imaginary =
        oscillator_imaginary_[feature] * cosine_step_[feature] +
        oscillator_real_[feature] * sine_step_[feature];
    oscillator_real_[feature] = next_real;
    oscillator_imaginary_[feature] = next_imaginary;
  }
  ++sample_count_;
  if ((sample_count_ & 4095U) == 0U) {
    for (std::size_t feature = 0U; feature < kUnisonSpectralFeatureCount;
         ++feature) {
      const double norm = std::hypot(oscillator_real_[feature],
                                     oscillator_imaginary_[feature]);
      if (norm > 0.0 && std::isfinite(norm)) {
        oscillator_real_[feature] /= norm;
        oscillator_imaginary_[feature] /= norm;
      }
    }
  }
}

void UnisonSpectralCorridorTracker::reset() noexcept {
  correlation_real_.fill(0.0);
  correlation_imaginary_.fill(0.0);
  oscillator_real_.fill(1.0);
  oscillator_imaginary_.fill(0.0);
  sample_count_ = 0U;
}

bool UnisonSpectralCorridorTracker::ready() const noexcept {
  return ready_with_lead(0U);
}

bool UnisonSpectralCorridorTracker::ready_with_lead(
    std::uint64_t lead_samples) const noexcept {
  return configured_ &&
         (sample_count_ >= ready_samples_ ||
          lead_samples >= ready_samples_ - sample_count_);
}

UnisonSpectralPhase UnisonSpectralCorridorTracker::phase() const noexcept {
  return phase_with_lead(0U);
}

UnisonSpectralPhase UnisonSpectralCorridorTracker::phase_with_lead(
    std::uint64_t lead_samples) const noexcept {
  if (!ready_with_lead(lead_samples)) {
    return UnisonSpectralPhase::unready;
  }
  return sample_count_ < settled_samples_ ? UnisonSpectralPhase::onset
                                          : UnisonSpectralPhase::settled;
}

UnisonSpectralFingerprint
UnisonSpectralCorridorTracker::fingerprint() const noexcept {
  return fingerprint_with_lead(0U);
}

UnisonSpectralFingerprint
UnisonSpectralCorridorTracker::fingerprint_with_lead(
    std::uint64_t lead_samples) const noexcept {
  UnisonSpectralFingerprint result{};
  if (!ready_with_lead(lead_samples)) {
    return result;
  }
  double scale = 0.0;
  double sum = 1.0;
  for (std::size_t feature = 0U; feature < result.size(); ++feature) {
    result[feature] = std::hypot(correlation_real_[feature],
                                correlation_imaginary_[feature]);
    if (result[feature] == 0.0) {
      continue;
    }
    if (scale < result[feature]) {
      const double ratio = scale / result[feature];
      sum = 1.0 + sum * ratio * ratio;
      scale = result[feature];
    } else {
      const double ratio = result[feature] / scale;
      sum += ratio * ratio;
    }
  }
  const double norm = scale == 0.0 ? 0.0 : scale * std::sqrt(sum);
  if (!std::isfinite(norm) || norm <= 0.0) {
    return {};
  }
  for (double& feature : result) {
    feature /= norm;
  }
  return result;
}

std::uint64_t UnisonSpectralCorridorTracker::sample_count() const noexcept {
  return sample_count_;
}

}  // namespace m3
