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
  double detector_left_gain{};
  double detector_right_gain{};
  std::uint64_t output_silence_flags{};
};

template <typename Sample>
DryPathResult analyze_detector_input(
    Sample* const* input, std::uint32_t input_channels, std::uint32_t frames,
    std::uint64_t input_silence_flags = 0U) noexcept {
  DryPathResult result;
  if (input == nullptr) {
    return result;
  }
  const std::uint32_t channel_count = std::min<std::uint32_t>(2U, input_channels);
  bool available[2]{};
  bool audible[2]{};
  for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
    available[channel] = input[channel] != nullptr;
    if (available[channel]) {
      ++result.channels_processed;
    }
  }
  for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
    if (!available[channel] ||
        (input_silence_flags & (std::uint64_t{1} << channel)) != 0U) {
      continue;
    }
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      const Sample sample = input[channel][frame];
      if (!std::isfinite(sample)) {
        result.nonfinite_input = true;
      } else if (sample != static_cast<Sample>(0)) {
        audible[channel] = true;
      }
    }
  }
  if (channel_count == 1U && available[0]) {
    result.detector_left_gain = 1.0;
  } else if (channel_count == 2U && available[0] && available[1]) {
    if (audible[0] && audible[1]) {
      result.detector_left_gain = 0.5;
      result.detector_right_gain = 0.5;
    } else if (audible[1]) {
      result.detector_right_gain = 1.0;
    } else {
      result.detector_left_gain = 1.0;
    }
  }
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    double samples[2]{};
    for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
      if (!available[channel] ||
          (input_silence_flags & (std::uint64_t{1} << channel)) != 0U) {
        continue;
      }
      const Sample sample = input[channel][frame];
      if (std::isfinite(sample)) {
        samples[channel] = static_cast<double>(sample);
      }
    }
    result.selected_peak = std::max(
        result.selected_peak,
        std::abs(samples[0] * result.detector_left_gain +
                 samples[1] * result.detector_right_gain));
  }
  return result;
}

template <typename Sample>
DryPathResult process_dry_path(Sample* const* input, std::uint32_t input_channels,
                               Sample* const* output, std::uint32_t output_channels,
                               std::uint32_t frames, bool passthrough,
                               std::uint64_t input_silence_flags = 0U) noexcept {
  DryPathResult result = analyze_detector_input(
      input, input_channels, frames, input_silence_flags);
  if (input == nullptr || output == nullptr) {
    return result;
  }
  const std::uint32_t channel_count =
      std::min<std::uint32_t>(2U, std::min(input_channels, output_channels));
  bool available[2]{};
  bool nonzero_output[2]{};
  result.channels_processed = 0U;
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
      const bool silent =
          (input_silence_flags & (std::uint64_t{1} << channel)) != 0U;
      samples[channel] =
          silent ? static_cast<Sample>(0) : input[channel][frame];
      if (!std::isfinite(samples[channel])) {
        samples[channel] = static_cast<Sample>(0);
        result.nonfinite_input = true;
      }
    }
    for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
      if (available[channel]) {
        output[channel][frame] =
            passthrough ? samples[channel] : static_cast<Sample>(0);
        nonzero_output[channel] =
            nonzero_output[channel] ||
            (passthrough && samples[channel] != static_cast<Sample>(0));
      }
    }
  }
  for (std::uint32_t channel = 0; channel < channel_count; ++channel) {
    if (available[channel] && !nonzero_output[channel]) {
      result.output_silence_flags |= std::uint64_t{1} << channel;
    }
  }
  return result;
}

}  // namespace m3
