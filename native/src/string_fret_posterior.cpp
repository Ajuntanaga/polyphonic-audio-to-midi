#include "m3/string_fret_posterior.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3 {
namespace {

constexpr double kSustainStayProbability = 0.985;
constexpr double kProbabilityFloor = 1.0e-12;

std::size_t member_count(std::uint8_t mask) noexcept {
  std::size_t count = 0U;
  while (mask != 0U) {
    count += (mask & 1U) != 0U ? 1U : 0U;
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return count;
}

}  // namespace

bool StringFretPosteriorBank::update(
    std::size_t candidate, const StringFretLikelihoodFrame& frame) noexcept {
  if (candidate >= states_.size() || frame.playable_mask == 0U ||
      !std::isfinite(frame.onset_strength) || frame.onset_strength < 0.0 ||
      frame.onset_strength > 1.0) {
    return false;
  }
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((frame.playable_mask & (1U << string)) != 0U &&
        !std::isfinite(frame.log_likelihood[string])) {
      return false;
    }
  }

  State& state = states_[candidate];
  const std::size_t count = member_count(frame.playable_mask);
  std::array<double, kMaxVoices> predicted{};
  const bool continuing = state.initialized &&
                          state.playable_mask == frame.playable_mask;
  if (!continuing || count == 1U) {
    const double uniform = 1.0 / static_cast<double>(count);
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((frame.playable_mask & (1U << string)) != 0U) {
        predicted[string] = uniform;
      }
    }
  } else {
    const double uniform = 1.0 / static_cast<double>(count);
    const double stay =
        (1.0 - frame.onset_strength) * kSustainStayProbability +
        frame.onset_strength * uniform;
    const double change = count > 1U
                              ? (1.0 - stay) /
                                    static_cast<double>(count - 1U)
                              : 0.0;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((frame.playable_mask & (1U << string)) == 0U) {
        continue;
      }
      predicted[string] =
          stay * state.probability[string] +
          change * (1.0 - state.probability[string]);
    }
  }

  double maximum_log = -std::numeric_limits<double>::infinity();
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((frame.playable_mask & (1U << string)) != 0U) {
      maximum_log = std::max(maximum_log, frame.log_likelihood[string]);
    }
  }
  std::array<double, kMaxVoices> posterior{};
  double total = 0.0;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((frame.playable_mask & (1U << string)) == 0U) {
      continue;
    }
    posterior[string] = std::max(
        kProbabilityFloor,
        predicted[string] *
            std::exp(std::clamp(frame.log_likelihood[string] - maximum_log,
                                -60.0, 0.0)));
    total += posterior[string];
  }
  if (!std::isfinite(total) || total <= 0.0) {
    return false;
  }
  state = {};
  state.playable_mask = frame.playable_mask;
  state.initialized = true;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((frame.playable_mask & (1U << string)) != 0U) {
      state.probability[string] = posterior[string] / total;
    }
  }
  return true;
}

void StringFretPosteriorBank::reset(std::size_t candidate) noexcept {
  if (candidate < states_.size()) {
    states_[candidate] = {};
  }
}

void StringFretPosteriorBank::reset() noexcept { states_ = {}; }

double StringFretPosteriorBank::probability(std::size_t candidate,
                                           std::size_t string) const noexcept {
  return candidate < states_.size() && string < kMaxVoices
             ? states_[candidate].probability[string]
             : 0.0;
}

double StringFretPosteriorBank::negative_log_probability(
    std::size_t candidate, std::size_t string) const noexcept {
  const double value = probability(candidate, string);
  return value > 0.0 ? -std::log(std::max(value, kProbabilityFloor)) : 64.0;
}

std::uint8_t StringFretPosteriorBank::best_string(
    std::size_t candidate) const noexcept {
  if (candidate >= states_.size() || !states_[candidate].initialized) {
    return kUnassignedTunerString;
  }
  std::size_t best = kMaxVoices;
  double best_probability = -1.0;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((states_[candidate].playable_mask & (1U << string)) != 0U &&
        states_[candidate].probability[string] > best_probability) {
      best = string;
      best_probability = states_[candidate].probability[string];
    }
  }
  return best < kMaxVoices ? static_cast<std::uint8_t>(best)
                           : kUnassignedTunerString;
}

}  // namespace m3
