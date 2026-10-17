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
  double runner_up_error{};
  double posterior_margin{};
  std::uint8_t member_mask{};
  std::uint8_t member_count{};
  bool valid{};
};

// Allocation-free per-string fit errors for the single-source model. Invalid,
// unavailable, or physically infeasible lanes remain +infinity and are absent
// from valid_mask. This preserves evidence for quieter plausible members that
// do not win the ordinary best/runner-up classification.
struct UnisonSpectralSingleScores final {
  std::array<double, kMaxVoices> error{};
  std::uint8_t valid_mask{};
};

[[nodiscard]] UnisonSpectralSingleScores score_single_spectral_sources(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask) noexcept;

// Fits exactly one physically feasible string template. This is the
// single-source companion to the 2-4 member unison classifier and is useful
// for deciding whether a weak candidate has an independently plausible
// string/fret spectrum. It does not decide that the pitch exists.
[[nodiscard]] UnisonSpectralClassification classify_single_spectral_source(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask) noexcept;

// Fits only adjacent physical-string groups. It performs no allocation and
// examines at most seven pairs, six triples, or five quadruples for the
// eight-string M3. A returned group contains exactly member_count positive
// components. Error is measured after L2 normalization, while returned
// weights retain the input amplitude units.
[[nodiscard]] UnisonSpectralClassification classify_consecutive_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t member_count) noexcept;

// Evaluates every physically feasible two- through four-string subset. This
// is the offline shadow-classifier surface; production code must not use its
// result until replay evidence clears the project acceptance gates.
[[nodiscard]] UnisonSpectralClassification classify_feasible_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t minimum_member_count,
    std::size_t maximum_member_count) noexcept;

// A cached three- or four-string group may fill a brief selector dropout only
// while independent live evidence still describes a multi-string subset of
// that exact group. This is deliberately a projection, not a detector: it
// cannot create a pitch, add an unplayable string, survive silence, or exceed
// the configured physical voice limit.
[[nodiscard]] std::uint8_t bounded_cached_unison_reacquisition(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double beat_coherence, bool cache_live, bool spectral_group_agreement,
    bool quiet) noexcept;

}  // namespace m3
