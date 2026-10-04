#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"
#include "m3/tuner_telemetry.hpp"

namespace m3 {

// One bounded observation for the physical-string states that can produce a
// detected pitch. Log likelihoods are relative: adding the same finite value
// to every playable state leaves the posterior unchanged. onset_strength is
// zero for a stable sustain and one for a fresh articulation.
struct StringFretLikelihoodFrame final {
  std::array<double, kMaxVoices> log_likelihood{};
  std::uint8_t playable_mask{};
  double onset_strength{};
};

// Fixed-size causal posterior bank. Each pitch candidate retains every
// playable physical-string alternative; no state is allocated or shared with
// another audio callback. The joint assignment consumes its negative-log
// costs after the update.
class StringFretPosteriorBank final {
 public:
  bool update(std::size_t candidate,
              const StringFretLikelihoodFrame& frame) noexcept;
  void reset(std::size_t candidate) noexcept;
  void reset() noexcept;

  [[nodiscard]] double probability(std::size_t candidate,
                                   std::size_t string) const noexcept;
  [[nodiscard]] double negative_log_probability(
      std::size_t candidate, std::size_t string) const noexcept;
  [[nodiscard]] std::uint8_t best_string(
      std::size_t candidate) const noexcept;

 private:
  struct State final {
    std::array<double, kMaxVoices> probability{};
    std::uint8_t playable_mask{};
    bool initialized{};
  };

  std::array<State, kMaxCandidates> states_{};
};

}  // namespace m3
