#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace m3 {

inline constexpr std::size_t kPartialDetuningCount = 6U;

struct PartialDetuningFrame final {
  std::array<double, kPartialDetuningCount> real{};
  std::array<double, kPartialDetuningCount> imaginary{};
  std::array<double, kPartialDetuningCount> center_hz{};
  std::array<double, kPartialDetuningCount> energy{};
};

struct PartialDetuningEvidence final {
  std::array<double, kPartialDetuningCount> residual_cents{};
  std::uint8_t valid_mask{};
  double upper_mean_cents{};
  bool valid{};
};

struct PartialDetuningComparison final {
  double log_likelihood{};
  std::uint8_t common_partials{};
  bool valid{};
};

[[nodiscard]] PartialDetuningComparison compare_partial_detuning(
    const PartialDetuningEvidence& observed,
    const std::array<double, kPartialDetuningCount>& reference_cents,
    std::uint8_t reference_valid_mask,
    double scale_cents = 3.0) noexcept;

// Causal fixed-storage estimator for the frequency displacement of each
// partial relative to the fundamental. Subtracting the fundamental's measured
// cents displacement rejects global tuning offset while retaining string
// stretch and other stable partial-frequency structure.
class PartialDetuningTracker final {
 public:
  void reset() noexcept;
  void update(const PartialDetuningFrame& frame,
              double decisions_per_second) noexcept;
  [[nodiscard]] PartialDetuningEvidence evidence() const noexcept;

 private:
  std::array<double, kPartialDetuningCount> previous_real_{};
  std::array<double, kPartialDetuningCount> previous_imaginary_{};
  std::array<double, kPartialDetuningCount> filtered_real_{};
  std::array<double, kPartialDetuningCount> filtered_imaginary_{};
  std::array<double, kPartialDetuningCount> filtered_twice_real_{};
  std::array<double, kPartialDetuningCount> filtered_twice_imaginary_{};
  std::array<double, kPartialDetuningCount> filtered_cents_{};
  std::array<std::uint16_t, kPartialDetuningCount> accepted_updates_{};
  std::uint8_t previous_mask_{};
};

}  // namespace m3
