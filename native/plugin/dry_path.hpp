#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace m3 {

struct DryPathResult final {
  bool nonfinite_input{};
  std::uint32_t channels_processed{};
};

template <typename Sample>
DryPathResult process_dry_path(Sample* const* input, std::uint32_t input_channels,
                               Sample* const* output, std::uint32_t output_channels,
                               std::uint32_t frames, bool passthrough) noexcept {
  DryPathResult result;
  if (input == nullptr || output == nullptr) {
    return result;
  }
  const std::uint32_t channel_count =
      std::min<std::uint32_t>(2U, std::min(input_channels, output_channels));
  for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
    const Sample* source = input[channel];
    Sample* destination = output[channel];
    if (source == nullptr || destination == nullptr) {
      continue;
    }
    ++result.channels_processed;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      Sample sample = source[frame];
      if (!std::isfinite(sample)) {
        sample = static_cast<Sample>(0);
        result.nonfinite_input = true;
      }
      destination[frame] = passthrough ? sample : static_cast<Sample>(0);
    }
  }
  return result;
}

}  // namespace m3
