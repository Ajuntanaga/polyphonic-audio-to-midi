#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/unison_spectral_classifier.hpp"

namespace m3 {

// Fixed-memory, allocation-free corridor analyzer. Callers may feed a
// decimated stream as long as configure() receives the corresponding effective
// sample rate.
class UnisonSpectralCorridorTracker final {
 public:
  bool configure(double sample_rate, std::uint8_t midi_note) noexcept;
  void observe(double sample) noexcept;
  void reset() noexcept;

  [[nodiscard]] bool ready() const noexcept;
  [[nodiscard]] bool ready_with_lead(
      std::uint64_t lead_samples) const noexcept;
  [[nodiscard]] UnisonSpectralPhase phase() const noexcept;
  [[nodiscard]] UnisonSpectralPhase phase_with_lead(
      std::uint64_t lead_samples) const noexcept;
  [[nodiscard]] UnisonSpectralFingerprint fingerprint() const noexcept;
  [[nodiscard]] UnisonSpectralFingerprint fingerprint_with_lead(
      std::uint64_t lead_samples) const noexcept;
  [[nodiscard]] std::uint64_t sample_count() const noexcept;

 private:
  std::array<double, kUnisonSpectralFeatureCount> cosine_step_{};
  std::array<double, kUnisonSpectralFeatureCount> sine_step_{};
  std::array<double, kUnisonSpectralFeatureCount> oscillator_real_{};
  std::array<double, kUnisonSpectralFeatureCount> oscillator_imaginary_{};
  std::array<double, kUnisonSpectralFeatureCount> correlation_real_{};
  std::array<double, kUnisonSpectralFeatureCount> correlation_imaginary_{};
  double decay_{};
  std::uint64_t ready_samples_{};
  std::uint64_t settled_samples_{};
  std::uint64_t sample_count_{};
  bool configured_{};
};

}  // namespace m3
