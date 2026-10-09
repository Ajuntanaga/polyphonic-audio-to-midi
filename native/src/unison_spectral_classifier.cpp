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

}  // namespace

UnisonSpectralClassification classify_consecutive_unison(
    const UnisonSpectralFingerprint& observed,
    const UnisonSpectralTemplateSet& templates,
    std::uint8_t playable_mask, std::size_t member_count) noexcept {
  UnisonSpectralClassification best;
  best.error = std::numeric_limits<double>::infinity();
  if (member_count < 2U || member_count > kMaximumUnisonMembers ||
      member_count > kMaxVoices || !finite_nonnegative(observed)) {
    return {};
  }
  const double observed_norm = stable_l2_norm(observed);
  if (observed_norm == 0.0) {
    return {};
  }

  const std::uint8_t available = static_cast<std::uint8_t>(
      playable_mask & templates.valid_mask);
  for (std::size_t first = 0U; first + member_count <= kMaxVoices; ++first) {
    const std::uint8_t mask = static_cast<std::uint8_t>(
        ((1U << member_count) - 1U) << first);
    if ((available & mask) != mask) {
      continue;
    }
    std::array<std::size_t, kMaximumUnisonMembers> members{};
    std::array<double, kMaximumUnisonMembers> template_norms{};
    bool valid = true;
    for (std::size_t component = 0U; component < member_count; ++component) {
      members[component] = first + component;
      valid = valid && finite_nonnegative(
                           templates.fingerprint[members[component]]);
      template_norms[component] =
          stable_l2_norm(templates.fingerprint[members[component]]);
      valid = valid && template_norms[component] > 0.0;
    }
    if (!valid) {
      continue;
    }

    std::array<std::array<double, kMaximumUnisonMembers>,
               kMaximumUnisonMembers>
        gram{};
    std::array<double, kMaximumUnisonMembers> correlation{};
    for (std::size_t left = 0U; left < member_count; ++left) {
      for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
        correlation[left] +=
            (templates.fingerprint[members[left]][feature] /
             template_norms[left]) *
            (observed[feature] / observed_norm);
      }
      for (std::size_t right = 0U; right < member_count; ++right) {
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
    if (!solve(gram, correlation, member_count, normalized_weights)) {
      continue;
    }
    if (std::any_of(normalized_weights.begin(),
                    normalized_weights.begin() + member_count,
                    [](double value) {
                      return !std::isfinite(value) ||
                             value <= kPositiveWeightFloor;
                    })) {
      continue;
    }
    double error = 0.0;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      double fitted = 0.0;
      for (std::size_t component = 0U; component < member_count; ++component) {
        fitted += normalized_weights[component] *
                  (templates.fingerprint[members[component]][feature] /
                   template_norms[component]);
      }
      const double residual = observed[feature] / observed_norm - fitted;
      error += residual * residual;
    }
    if (!std::isfinite(error) ||
        (best.valid &&
         !(error < best.error ||
           (error == best.error && mask < best.member_mask)))) {
      continue;
    }
    UnisonSpectralClassification candidate;
    candidate.valid = true;
    candidate.error = error;
    candidate.member_mask = mask;
    bool weights_valid = true;
    for (std::size_t component = 0U; component < member_count; ++component) {
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
  return best.valid ? best : UnisonSpectralClassification{};
}

}  // namespace m3
