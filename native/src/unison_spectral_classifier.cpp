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
  UnisonSpectralFingerprint prepared_observed{};
  if (templates.prepared) {
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      prepared_observed[feature] = observed[feature] / observed_norm;
    }
  }

  const std::uint8_t available = static_cast<std::uint8_t>(
      playable_mask & templates.valid_mask);
  std::array<double, kMaxVoices> template_norms{};
  std::array<double, kMaxVoices> observed_correlations{};
  std::array<std::array<double, kMaxVoices>, kMaxVoices> template_gram{};
  std::uint8_t normalized_available = available;
  if (templates.prepared) {
    template_norms = templates.prepared_norm;
    template_gram = templates.prepared_gram;
  }
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((normalized_available & bit) == 0U) {
      continue;
    }
    const UnisonSpectralFingerprint& fingerprint =
        templates.fingerprint[string];
    if (!templates.prepared) {
      template_norms[string] = stable_l2_norm(fingerprint);
      if (!finite_nonnegative(fingerprint) ||
          template_norms[string] <= 0.0) {
        normalized_available = static_cast<std::uint8_t>(
            normalized_available & static_cast<std::uint8_t>(~bit));
        continue;
      }
    }
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      observed_correlations[string] += templates.prepared
          ? templates.fingerprint[string][feature] *
                prepared_observed[feature]
          : (fingerprint[feature] / template_norms[string]) *
                (observed[feature] / observed_norm);
    }
  }
  if (!templates.prepared) {
    for (std::size_t left = 0U; left < kMaxVoices; ++left) {
      if ((normalized_available & (1U << left)) == 0U) {
        continue;
      }
      for (std::size_t right = left; right < kMaxVoices; ++right) {
        if ((normalized_available & (1U << right)) == 0U) {
          continue;
        }
        double value = 0.0;
        for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
          value +=
              (templates.fingerprint[left][feature] / template_norms[left]) *
              (templates.fingerprint[right][feature] /
               template_norms[right]);
        }
        template_gram[left][right] = value;
        template_gram[right][left] = value;
      }
    }
  }
  for (std::uint16_t wide_mask = 1U;
       wide_mask < static_cast<std::uint16_t>(1U << kMaxVoices);
       ++wide_mask) {
    const std::uint8_t mask = static_cast<std::uint8_t>(wide_mask);
    const std::size_t count = member_count(mask);
    if (count < minimum_member_count || count > maximum_member_count ||
        (normalized_available & mask) != mask ||
        (consecutive_only && !consecutive_mask(mask, count))) {
      continue;
    }
    std::array<std::size_t, kMaximumUnisonMembers> members{};
    std::size_t member_index = 0U;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((mask & (1U << string)) == 0U) {
        continue;
      }
      members[member_index] = string;
      ++member_index;
    }
    if (member_index != count) {
      continue;
    }

    std::array<std::array<double, kMaximumUnisonMembers>,
               kMaximumUnisonMembers>
        gram{};
    std::array<double, kMaximumUnisonMembers> correlation{};
    for (std::size_t left = 0U; left < count; ++left) {
      correlation[left] = observed_correlations[members[left]];
      for (std::size_t right = 0U; right < count; ++right) {
        gram[left][right] =
            template_gram[members[left]][members[right]];
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
    double error = 1.0;
    for (std::size_t left = 0U; left < count; ++left) {
      error -= 2.0 * normalized_weights[left] * correlation[left];
      for (std::size_t right = 0U; right < count; ++right) {
        error += normalized_weights[left] * normalized_weights[right] *
                 gram[left][right];
      }
    }
    error = std::max(0.0, error);
    if (error < 1.0e-15) {
      error = 0.0;
    }
    // The Gram identity avoids repeating 102-bin dot products for every
    // mask, but its subtractive form can lose a few ulps for nearly identical
    // fits. Re-evaluate only candidates capable of becoming the winner using
    // the original nonnegative residual sum. This preserves classification
    // decisions while keeping the common path bounded and cheap.
    if (!best.valid || error <= best.error + 1.0e-12) {
      double exact_error = 0.0;
      for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
        double fitted = 0.0;
        for (std::size_t component = 0U; component < count; ++component) {
          fitted += normalized_weights[component] *
                    (templates.prepared
                         ? templates.fingerprint[members[component]][feature]
                         : templates.fingerprint[members[component]][feature] /
                               template_norms[members[component]]);
        }
        const double residual =
            (templates.prepared ? prepared_observed[feature]
                                : observed[feature] / observed_norm) -
            fitted;
        exact_error += residual * residual;
      }
      error = exact_error;
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
                                template_norms[members[component]];
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

UnisonSpectralClassification classify_prepared_single(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask) noexcept {
  if (!templates.prepared || !finite_nonnegative(observed)) {
    return {};
  }
  const double observed_norm = stable_l2_norm(observed);
  if (observed_norm == 0.0) {
    return {};
  }
  UnisonSpectralFingerprint normalized_observed{};
  for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
    normalized_observed[feature] = observed[feature] / observed_norm;
  }

  UnisonSpectralClassification best;
  best.error = std::numeric_limits<double>::infinity();
  best.runner_up_error = std::numeric_limits<double>::infinity();
  best.posterior_margin = std::numeric_limits<double>::infinity();
  const std::uint8_t available =
      static_cast<std::uint8_t>(playable_mask & templates.valid_mask);
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((available & bit) == 0U) {
      continue;
    }
    double correlation = 0.0;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      correlation += templates.fingerprint[string][feature] *
                     normalized_observed[feature];
    }
    const double gram = templates.prepared_gram[string][string];
    if (!std::isfinite(correlation) || !std::isfinite(gram) ||
        std::abs(gram) <= kPivotFloor) {
      continue;
    }
    const double normalized_weight = correlation / gram;
    if (!std::isfinite(normalized_weight) ||
        normalized_weight <= kPositiveWeightFloor) {
      continue;
    }
    double error = std::max(
        0.0, 1.0 - 2.0 * normalized_weight * correlation +
                 normalized_weight * normalized_weight * gram);
    if (error < 1.0e-15) {
      error = 0.0;
    }
    if (!best.valid || error <= best.error + 1.0e-12) {
      double exact_error = 0.0;
      for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
        const double residual =
            normalized_observed[feature] -
            normalized_weight * templates.fingerprint[string][feature];
        exact_error += residual * residual;
      }
      error = exact_error;
    }
    if (!std::isfinite(error)) {
      continue;
    }
    if (best.valid &&
        !(error < best.error ||
          (error == best.error && bit < best.member_mask))) {
      best.runner_up_error = std::min(best.runner_up_error, error);
      continue;
    }
    const double raw_weight = normalized_weight * observed_norm /
                              templates.prepared_norm[string];
    if (!std::isfinite(raw_weight)) {
      continue;
    }
    const double previous_best_error = best.error;
    UnisonSpectralClassification candidate;
    candidate.valid = true;
    candidate.error = error;
    candidate.runner_up_error =
        std::min(best.runner_up_error, previous_best_error);
    candidate.member_mask = bit;
    candidate.member_count = 1U;
    candidate.weights[string] = raw_weight;
    best = candidate;
  }
  if (!best.valid) {
    return {};
  }
  best.posterior_margin = best.runner_up_error - best.error;
  return best;
}

}  // namespace

bool prepare_unison_spectral_templates(
    UnisonSpectralTemplateSet& templates) noexcept {
  if (templates.prepared) {
    return templates.valid_mask != 0U;
  }
  templates.prepared = false;
  templates.prepared_norm = {};
  templates.prepared_gram = {};
  if (templates.valid_mask == 0U) {
    return false;
  }
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((templates.valid_mask & bit) == 0U) {
      continue;
    }
    const auto& value = templates.fingerprint[string];
    if (!finite_nonnegative(value)) {
      return false;
    }
    templates.prepared_norm[string] = stable_l2_norm(value);
    if (templates.prepared_norm[string] <= 0.0) {
      return false;
    }
    for (std::size_t feature = 0U;
         feature < kUnisonSpectralFeatureCount; ++feature) {
      templates.fingerprint[string][feature] /=
          templates.prepared_norm[string];
    }
  }
  for (std::size_t left = 0U; left < kMaxVoices; ++left) {
    if ((templates.valid_mask & (1U << left)) == 0U) {
      continue;
    }
    for (std::size_t right = left; right < kMaxVoices; ++right) {
      if ((templates.valid_mask & (1U << right)) == 0U) {
        continue;
      }
      double value = 0.0;
      for (std::size_t feature = 0U;
           feature < kUnisonSpectralFeatureCount; ++feature) {
        value +=
            templates.fingerprint[left][feature] *
            templates.fingerprint[right][feature];
      }
      templates.prepared_gram[left][right] = value;
      templates.prepared_gram[right][left] = value;
    }
  }
  templates.prepared = true;
  return true;
}

double normalized_spectral_fingerprint_squared_distance(
    const UnisonSpectralFingerprint& left,
    const UnisonSpectralFingerprint& right) noexcept {
  if (!finite_nonnegative(left) || !finite_nonnegative(right)) {
    return std::numeric_limits<double>::infinity();
  }
  const double left_norm = stable_l2_norm(left);
  const double right_norm = stable_l2_norm(right);
  if (left_norm <= 0.0 || right_norm <= 0.0) {
    return std::numeric_limits<double>::infinity();
  }
  double distance = 0.0;
  for (std::size_t feature = 0U; feature < left.size(); ++feature) {
    const double difference =
        left[feature] / left_norm - right[feature] / right_norm;
    distance += difference * difference;
  }
  return std::isfinite(distance) ? distance
                                 : std::numeric_limits<double>::infinity();
}

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
    if ((available & bit) == 0U ||
        (!templates.prepared && !finite_nonnegative(candidate))) {
      continue;
    }
    const double candidate_norm =
        templates.prepared ? templates.prepared_norm[string]
                           : stable_l2_norm(candidate);
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
    if (templates.prepared) {
      // Both vectors are normalized and the positive scalar fit is their dot
      // product, so the least-squares residual is exactly 1-correlation^2.
      // Factory templates cache their norms; avoiding a second 102-feature
      // residual pass keeps the production audio callback bounded.
      error = std::max(0.0, 1.0 - correlation * correlation);
    } else {
      for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
        const double fitted =
            correlation * candidate[feature] / candidate_norm;
        const double residual = observed[feature] / observed_norm - fitted;
        error += residual * residual;
      }
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
  if (templates.prepared) {
    return classify_prepared_single(observed, templates, playable_mask);
  }
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

UnisonSpectralClassification classify_consecutive_unison_range(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t minimum_member_count,
    std::size_t maximum_member_count) noexcept {
  if (minimum_member_count < 2U ||
      minimum_member_count > maximum_member_count ||
      maximum_member_count > kMaximumUnisonMembers) {
    return {};
  }
  UnisonSpectralClassification best;
  best.error = std::numeric_limits<double>::infinity();
  best.runner_up_error = std::numeric_limits<double>::infinity();
  for (std::size_t members = minimum_member_count;
       members <= maximum_member_count; ++members) {
    UnisonSpectralClassification candidate =
        classify_consecutive_unison(observed, templates, playable_mask,
                                    members);
    if (!candidate.valid) {
      continue;
    }
    const bool becomes_best =
        !best.valid || candidate.error < best.error ||
        (candidate.error == best.error &&
         candidate.member_mask < best.member_mask);
    if (!becomes_best) {
      best.runner_up_error =
          std::min({best.runner_up_error, candidate.error,
                    candidate.runner_up_error});
      best.posterior_margin = best.runner_up_error - best.error;
      continue;
    }
    const double runner_up =
        std::min({candidate.runner_up_error, best.error,
                  best.runner_up_error});
    best = candidate;
    best.runner_up_error = runner_up;
    best.posterior_margin = best.runner_up_error - best.error;
  }
  return best.valid ? best : UnisonSpectralClassification{};
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

ObservedUnisonReacquisitionResult diagnose_observed_unison_reacquisition(
    const ObservedUnisonReacquisitionEvidence& evidence) noexcept {
  using Disposition = ObservedUnisonReacquisitionDisposition;
  const auto reject = [&evidence](Disposition disposition) noexcept {
    return ObservedUnisonReacquisitionResult{
        evidence.current_assignment_mask, disposition};
  };
  const auto members = [](std::uint8_t mask) noexcept {
    std::uint8_t count = 0U;
    for (; mask != 0U; mask = static_cast<std::uint8_t>(mask & (mask - 1U))) {
      ++count;
    }
    return count;
  };
  const std::uint8_t cached_members = members(evidence.cached_group_mask);
  const std::uint8_t current_members =
      members(evidence.current_assignment_mask);
  const std::uint8_t pending_members = members(evidence.pending_fine_mask);
  if (evidence.quiet) {
    return reject(Disposition::quiet);
  }
  if (cached_members < 3U || cached_members > 4U) {
    return reject(Disposition::no_cache);
  }
  if (!evidence.direct_fundamental) {
    return reject(Disposition::no_direct_fundamental);
  }
  if (current_members < 2U || current_members >= cached_members ||
      (evidence.current_assignment_mask &
       static_cast<std::uint8_t>(~evidence.cached_group_mask)) != 0U) {
    return reject(Disposition::current_group_invalid);
  }
  if (pending_members < 2U || pending_members > cached_members ||
      (evidence.pending_fine_mask &
       static_cast<std::uint8_t>(~evidence.cached_group_mask)) != 0U) {
    return reject(Disposition::pending_group_invalid);
  }
  if (evidence.spectral_tier_mask != evidence.cached_group_mask) {
    return reject(Disposition::tier_mismatch);
  }
  if (
      (evidence.cached_group_mask &
       static_cast<std::uint8_t>(~evidence.playable_mask)) != 0U) {
    return reject(Disposition::unplayable);
  }
  if ((evidence.cached_group_mask & evidence.other_owned_mask) != 0U) {
    return reject(Disposition::ownership_conflict);
  }
  if (evidence.maximum_polyphony == 0U ||
      evidence.maximum_polyphony > kMaxVoices ||
      members(static_cast<std::uint8_t>(evidence.cached_group_mask |
                                        evidence.other_owned_mask)) >
          evidence.maximum_polyphony) {
    return reject(Disposition::over_capacity);
  }
  if (!std::isfinite(evidence.cache_age_seconds) ||
      !std::isfinite(evidence.maximum_cache_age_seconds) ||
      evidence.maximum_cache_age_seconds < 0.0 ||
      evidence.cache_age_seconds < 0.0 ||
      evidence.cache_age_seconds > evidence.maximum_cache_age_seconds) {
    return reject(Disposition::cache_expired);
  }
  if (!std::isfinite(evidence.pending_evidence_seconds) ||
      !std::isfinite(evidence.minimum_revalidation_seconds) ||
      evidence.minimum_revalidation_seconds < 0.0 ||
      evidence.pending_evidence_seconds <
          evidence.minimum_revalidation_seconds) {
    return reject(Disposition::pending_insufficient);
  }
  if (!std::isfinite(evidence.pending_beat_coherence) ||
      evidence.pending_beat_coherence < 0.20) {
    return reject(Disposition::beat_below_gate);
  }
  if (!evidence.cached_fingerprint_valid ||
      !evidence.current_fingerprint_valid ||
      !std::isfinite(evidence.fingerprint_squared_distance)) {
    return reject(Disposition::fingerprint_unavailable);
  }
  if (
      !std::isfinite(evidence.fingerprint_squared_distance) ||
      !std::isfinite(evidence.maximum_fingerprint_squared_distance) ||
      evidence.maximum_fingerprint_squared_distance < 0.0 ||
      evidence.fingerprint_squared_distance >
          evidence.maximum_fingerprint_squared_distance) {
    return reject(Disposition::fingerprint_mismatch);
  }
  return {evidence.cached_group_mask, Disposition::accepted};
}

std::uint8_t bounded_observed_unison_reacquisition(
    const ObservedUnisonReacquisitionEvidence& evidence) noexcept {
  return diagnose_observed_unison_reacquisition(evidence).projected_mask;
}

bool bounded_observed_unison_cache_refresh(
    bool active, bool selected, bool above_decay_floor, bool quiet,
    std::uint8_t current_assignment_mask,
    std::uint8_t fine_frequency_mask) noexcept {
  const std::size_t members = member_count(current_assignment_mask);
  return !quiet && active && (selected || above_decay_floor) &&
         members >= 3U && members <= 4U &&
         current_assignment_mask == fine_frequency_mask;
}

}  // namespace m3
