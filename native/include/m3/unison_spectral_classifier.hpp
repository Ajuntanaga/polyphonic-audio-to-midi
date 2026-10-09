#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"

namespace m3 {

// Three harmonics sampled across a +/-100-cent corridor at roughly six-cent
// spacing, including both exact corridor boundaries.
inline constexpr std::size_t kUnisonSpectralHarmonicCount = 3U;
inline constexpr std::size_t kUnisonSpectralOffsetsPerHarmonic = 34U;
inline constexpr std::size_t kUnisonSpectralFeatureCount =
    kUnisonSpectralHarmonicCount * kUnisonSpectralOffsetsPerHarmonic;

using UnisonSpectralFingerprint =
    std::array<double, kUnisonSpectralFeatureCount>;

struct UnisonSpectralTemplateSet final {
  std::array<UnisonSpectralFingerprint, kMaxVoices> fingerprint{};
  std::uint8_t valid_mask{};
};

struct UnisonSpectralClassification final {
  std::array<double, kMaxVoices> weights{};
  double error{};
  std::uint8_t member_mask{};
  bool valid{};
};

// Fits only adjacent physical-string groups. It performs no allocation and
// examines at most seven pairs, six triples, or five quadruples for the
// eight-string M3. A returned group contains exactly member_count positive
// components. Error is measured after L2 normalization, while returned
// weights retain the input amplitude units.
[[nodiscard]] UnisonSpectralClassification classify_consecutive_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t member_count) noexcept;

}  // namespace m3
