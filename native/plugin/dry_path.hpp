#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

#include "m3/types.hpp"

namespace m3 {

struct DryPathResult final {
  bool nonfinite_input{};
  std::uint32_t channels_processed{};
  double selected_peak{};
};

template <typename Sample>
DryPathResult process_dry_path(Sample* const* input, std::uint32_t input_channels,
                               Sample* const* output, std::uint32_t output_channels,
                               std::uint32_t frames, bool passthrough,
                               DetectorInput detector_input) noexcept {
  DryPathResult result;
  if (input == nullptr || output == nullptr) {
    return result;
  }
  const std::uint32_t channel_count =
      std::min<std::uint32_t>(2U, std::min(input_channels, output_channels));
  bool available[2]{};
  for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
    available[channel] = input[channel] != nullptr && output[channel] != nullptr;
    if (available[channel]) {
      ++result.channels_processed;
    }
  }
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    Sample samples[2]{};
    for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
      if (!available[channel]) {
        continue;
      }
      samples[channel] = input[channel][frame];
      if (!std::isfinite(samples[channel])) {
        samples[channel] = static_cast<Sample>(0);
        result.nonfinite_input = true;
      }
    }
    double selected = 0.0;
    if (detector_input == DetectorInput::left && available[0]) {
      selected = static_cast<double>(samples[0]);
    } else if (detector_input == DetectorInput::right && available[1]) {
      selected = static_cast<double>(samples[1]);
    } else if (detector_input == DetectorInput::downmix && available[0] &&
               available[1]) {
      selected = (static_cast<double>(samples[0]) +
                  static_cast<double>(samples[1])) *
                 0.7071067811865476;
    }
    result.selected_peak = std::max(result.selected_peak, std::abs(selected));
    for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
      if (available[channel]) {
        output[channel][frame] =
            passthrough ? samples[channel] : static_cast<Sample>(0);
      }
    }
  }
  return result;
}

}  // namespace m3
