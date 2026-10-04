#pragma once

#include <array>
#include <cstddef>

namespace m3 {

inline constexpr std::size_t kHarmonicEvidenceCount = 6U;

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

HarmonicEvidence make_harmonic_evidence(
    const std::array<double, kHarmonicEvidenceCount>& energy) noexcept;
HarmonicEvidenceComparison compare_harmonic_evidence(
    const HarmonicEvidence& observed,
    const HarmonicEvidence& reference) noexcept;
double harmonic_transient_strength(const HarmonicEvidence& fast,
                                   const HarmonicEvidence& settled) noexcept;

}  // namespace m3
