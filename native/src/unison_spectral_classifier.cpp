#include "m3/unison_spectral_classifier.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3 {
namespace {

constexpr double kPivotFloor = 1.0e-12;
constexpr double kPositiveWeightFloor = 1.0e-9;
constexpr std::size_t kMaximumUnisonMembers = 4U;

bool finite_nonnegative(const UnisonSpectralFingerprint& value) noexcept {
  for (const double feature : value) {
    if (!std::isfinite(feature) || feature < 0.0) {
      return false;
    }
  }
  return true;
}

double stable_l2_norm(const UnisonSpectralFingerprint& value) noexcept {
  double scale = 0.0;
  double sum = 1.0;
  for (const double feature : value) {
    if (feature == 0.0) {
      continue;
    }
    if (scale < feature) {
      const double ratio = scale / feature;
      sum = 1.0 + sum * ratio * ratio;
      scale = feature;
    } else {
      const double ratio = feature / scale;
      sum += ratio * ratio;
    }
  }
  const double norm = scale == 0.0 ? 0.0 : scale * std::sqrt(sum);
  return std::isfinite(norm) ? norm : 0.0;
}

bool solve(
    std::array<std::array<double, kMaximumUnisonMembers>,
               kMaximumUnisonMembers>
        matrix,
    std::array<double, kMaximumUnisonMembers> right, std::size_t size,
    std::array<double, kMaximumUnisonMembers>& output) noexcept {
  for (std::size_t column = 0U; column < size; ++column) {
    std::size_t pivot = column;
    for (std::size_t row = column + 1U; row < size; ++row) {
      if (std::abs(matrix[row][column]) >
          std::abs(matrix[pivot][column])) {
        pivot = row;
      }
    }
    if (std::abs(matrix[pivot][column]) <= kPivotFloor) {
      return false;
    }
    std::swap(matrix[column], matrix[pivot]);
    std::swap(right[column], right[pivot]);
    const double divisor = matrix[column][column];
    for (std::size_t item = column; item < size; ++item) {
      matrix[column][item] /= divisor;
    }
    right[column] /= divisor;
    for (std::size_t row = 0U; row < size; ++row) {
      if (row == column) {
        continue;
      }
      const double multiplier = matrix[row][column];
      for (std::size_t item = column; item < size; ++item) {
        matrix[row][item] -= multiplier * matrix[column][item];
      }
      right[row] -= multiplier * right[column];
    }
  }
  output = {};
  for (std::size_t index = 0U; index < size; ++index) {
    output[index] = right[index];
  }
  return true;
}

std::size_t member_count(std::uint8_t mask) noexcept {
  std::size_t count = 0U;
  while (mask != 0U) {
    count += mask & 1U;
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return count;
}

bool consecutive_mask(std::uint8_t mask, std::size_t count) noexcept {
  if (count == 0U) {
    return false;
  }
  while ((mask & 1U) == 0U) {
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return mask == static_cast<std::uint8_t>((1U << count) - 1U);
}

UnisonSpectralClassification classify(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t minimum_member_count,
    std::size_t maximum_member_count, bool consecutive_only) noexcept {
  UnisonSpectralClassification best;
  best.error = std::numeric_limits<double>::infinity();
  best.runner_up_error = std::numeric_limits<double>::infinity();
  best.posterior_margin = std::numeric_limits<double>::infinity();
  if (minimum_member_count < 1U ||
      minimum_member_count > maximum_member_count ||
      maximum_member_count > kMaximumUnisonMembers ||
      maximum_member_count > kMaxVoices || !finite_nonnegative(observed)) {
    return {};
  }
  const double observed_norm = stable_l2_norm(observed);
  if (observed_norm == 0.0) {
    return {};
  }

  const std::uint8_t available = static_cast<std::uint8_t>(
      playable_mask & templates.valid_mask);
  for (std::uint16_t wide_mask = 1U;
       wide_mask < static_cast<std::uint16_t>(1U << kMaxVoices);
       ++wide_mask) {
    const std::uint8_t mask = static_cast<std::uint8_t>(wide_mask);
    const std::size_t count = member_count(mask);
    if (count < minimum_member_count || count > maximum_member_count ||
        (available & mask) != mask ||
        (consecutive_only && !consecutive_mask(mask, count))) {
      continue;
    }
    std::array<std::size_t, kMaximumUnisonMembers> members{};
    std::array<double, kMaximumUnisonMembers> template_norms{};
    std::size_t member_index = 0U;
    bool valid = true;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((mask & (1U << string)) == 0U) {
        continue;
      }
      members[member_index] = string;
      valid = valid && finite_nonnegative(templates.fingerprint[string]);
      template_norms[member_index] =
          stable_l2_norm(templates.fingerprint[string]);
      valid = valid && template_norms[member_index] > 0.0;
      ++member_index;
    }
    if (!valid || member_index != count) {
      continue;
    }

    std::array<std::array<double, kMaximumUnisonMembers>,
               kMaximumUnisonMembers>
        gram{};
    std::array<double, kMaximumUnisonMembers> correlation{};
    for (std::size_t left = 0U; left < count; ++left) {
      for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
        correlation[left] +=
            (templates.fingerprint[members[left]][feature] /
             template_norms[left]) *
            (observed[feature] / observed_norm);
      }
      for (std::size_t right = 0U; right < count; ++right) {
        for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
          gram[left][right] +=
              (templates.fingerprint[members[left]][feature] /
               template_norms[left]) *
              (templates.fingerprint[members[right]][feature] /
               template_norms[right]);
        }
      }
    }
    std::array<double, kMaximumUnisonMembers> normalized_weights{};
    if (!solve(gram, correlation, count, normalized_weights) ||
        std::any_of(normalized_weights.begin(),
                    normalized_weights.begin() + count, [](double value) {
                      return !std::isfinite(value) ||
                             value <= kPositiveWeightFloor;
                    })) {
      continue;
    }
    double error = 0.0;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      double fitted = 0.0;
      for (std::size_t component = 0U; component < count; ++component) {
        fitted += normalized_weights[component] *
                  (templates.fingerprint[members[component]][feature] /
                   template_norms[component]);
      }
      const double residual = observed[feature] / observed_norm - fitted;
      error += residual * residual;
    }
    if (!std::isfinite(error)) {
      continue;
    }
    const bool becomes_best =
        !best.valid || error < best.error ||
        (error == best.error && mask < best.member_mask);
    if (!becomes_best) {
      best.runner_up_error = std::min(best.runner_up_error, error);
      continue;
    }

    const double previous_best_error = best.error;
    UnisonSpectralClassification candidate;
    candidate.valid = true;
    candidate.error = error;
    candidate.runner_up_error =
        std::min(best.runner_up_error, previous_best_error);
    candidate.member_mask = mask;
    candidate.member_count = static_cast<std::uint8_t>(count);
    bool weights_valid = true;
    for (std::size_t component = 0U; component < count; ++component) {
      const double raw_weight = normalized_weights[component] * observed_norm /
                                template_norms[component];
      if (!std::isfinite(raw_weight)) {
        weights_valid = false;
        break;
      }
      candidate.weights[members[component]] = raw_weight;
    }
    if (weights_valid) {
      best = candidate;
    }
  }
  if (!best.valid) {
    return {};
  }
  best.posterior_margin = best.runner_up_error - best.error;
  return best;
}

}  // namespace

UnisonSpectralSingleScores score_single_spectral_sources(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask) noexcept {
  UnisonSpectralSingleScores result;
  result.error.fill(std::numeric_limits<double>::infinity());
  if (!finite_nonnegative(observed)) {
    return result;
  }
  const double observed_norm = stable_l2_norm(observed);
  if (observed_norm == 0.0) {
    return result;
  }
  const std::uint8_t available = static_cast<std::uint8_t>(
      playable_mask & templates.valid_mask);
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    const UnisonSpectralFingerprint& candidate =
        templates.fingerprint[string];
    if ((available & bit) == 0U || !finite_nonnegative(candidate)) {
      continue;
    }
    const double candidate_norm = stable_l2_norm(candidate);
    if (candidate_norm == 0.0) {
      continue;
    }
    double correlation = 0.0;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      correlation += (candidate[feature] / candidate_norm) *
                     (observed[feature] / observed_norm);
    }
    if (!std::isfinite(correlation) ||
        correlation <= kPositiveWeightFloor) {
      continue;
    }
    double error = 0.0;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      const double fitted = correlation * candidate[feature] / candidate_norm;
      const double residual = observed[feature] / observed_norm - fitted;
      error += residual * residual;
    }
    if (!std::isfinite(error)) {
      continue;
    }
    result.error[string] = error;
    result.valid_mask = static_cast<std::uint8_t>(result.valid_mask | bit);
  }
  return result;
}

UnisonSpectralClassification classify_single_spectral_source(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask) noexcept {
  return classify(observed, templates, playable_mask, 1U, 1U, false);
}

UnisonSpectralClassification classify_consecutive_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t member_count) noexcept {
  if (member_count < 2U) {
    return {};
  }
  return classify(observed, templates, playable_mask, member_count,
                  member_count, true);
}

UnisonSpectralClassification classify_feasible_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t minimum_member_count,
    std::size_t maximum_member_count) noexcept {
  if (minimum_member_count < 2U) {
    return {};
  }
  return classify(observed, templates, playable_mask, minimum_member_count,
                  maximum_member_count, false);
}

std::uint8_t bounded_cached_unison_reacquisition(
    std::uint8_t current_assignment_mask, std::uint8_t cached_group_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool direct_fundamental,
    double beat_coherence, bool cache_live, bool spectral_group_agreement,
    bool quiet) noexcept {
  const auto members = [](std::uint8_t mask) noexcept {
    std::uint8_t count = 0U;
    for (; mask != 0U; mask = static_cast<std::uint8_t>(mask & (mask - 1U))) {
      ++count;
    }
    return count;
  };
  const std::uint8_t cached_members = members(cached_group_mask);
  const std::uint8_t current_members = members(current_assignment_mask);
  const std::uint8_t fine_members = members(fine_frequency_mask);
  if (quiet || !cache_live || !direct_fundamental ||
      !spectral_group_agreement || !std::isfinite(beat_coherence) ||
      beat_coherence < 0.20 || current_members < 2U ||
      current_members > cached_members || fine_members < 2U ||
      fine_members > cached_members || cached_members < 3U ||
      cached_members > 4U || maximum_polyphony == 0U ||
      cached_members > maximum_polyphony ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) != 0U ||
      (fine_frequency_mask & static_cast<std::uint8_t>(~cached_group_mask)) !=
          0U ||
      (cached_group_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U) {
    return current_assignment_mask;
  }
  return cached_group_mask;
}

}  // namespace m3
