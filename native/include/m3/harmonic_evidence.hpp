#pragma once

#include <array>
#include <cstddef>

namespace m3 {

inline constexpr std::size_t kHarmonicEvidenceCount = 6U;
inline constexpr std::size_t kSpectralTierCount = 4U;

enum class SpectralTier : std::size_t {
  low = 0U,
  low_mid = 1U,
  high_mid = 2U,
  high = 3U,
};

// A normalized, fixed-size view of one already-observed harmonic frame.
// Lower and upper partial groups remain separate because they answer
// different questions: the lower group anchors the fundamental while the
// upper group carries more physical-string and articulation character.
struct HarmonicEvidence final {
  std::array<double, kHarmonicEvidenceCount> normalized_energy{};
  std::array<double, kHarmonicEvidenceCount - 1U> adjacent_log_ratio{};
  double upper_share{};
  double centroid{};
  bool valid{};
};

struct HarmonicEvidenceComparison final {
  double lower_log_likelihood{};
  double upper_log_likelihood{};
  double balance_log_likelihood{};

  [[nodiscard]] double combined_log_likelihood() const noexcept {
    return lower_log_likelihood + upper_log_likelihood +
           balance_log_likelihood;
  }
};

struct SpectralTierComparison final {
  std::array<double, kSpectralTierCount> tier_log_likelihood{};
  // Transition from the body-dominated third partial into upper overtones.
  double overtone_separation_log_likelihood{};
};

HarmonicEvidence make_harmonic_evidence(
    const std::array<double, kHarmonicEvidenceCount>& energy) noexcept;
HarmonicEvidenceComparison compare_harmonic_evidence(
    const HarmonicEvidence& observed,
    const HarmonicEvidence& reference) noexcept;
SpectralTierComparison compare_spectral_tiers(
    const HarmonicEvidence& observed,
    const HarmonicEvidence& reference) noexcept;
double harmonic_transient_strength(const HarmonicEvidence& fast,
                                   const HarmonicEvidence& settled) noexcept;

}  // namespace m3
