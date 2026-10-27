#pragma once

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)

#include <cstddef>
#include <cstdint>

namespace m3::diagnostics {

// Borrowed only during the callback. No labels, output decisions, or mutable
// detector data cross this interface. An empty view invalidates all results.
struct FrequencyRefinementView final {
  std::uint8_t midi_note{};
  const double* real{};
  const double* imaginary{};
  const std::uint32_t* ticks{};
  std::size_t oldest{};
  std::size_t count{};
  std::size_t capacity{};
  double seconds_per_tick{};
  double center_hz{};
  const std::uint8_t* strings{};
  const double* offsets_hz{};
  std::size_t components{};
  const bool* feasible_masks{};
  // Production's full-window, unweighted-trend-removed, Hann-weighted beat
  // samples in chronological order. These are not the rejected weighted fit.
  const double* beat_samples{};
  double beat_absolute_sum{};
  // Assignment entering the current fine-analysis decision, not its eventual
  // frame-end output. Used only to select and interpret diagnostic windows.
  std::uint8_t prior_output_mask{};
};

using FrequencyRefinementObserver =
    void (*)(void*, const FrequencyRefinementView&) noexcept;

}  // namespace m3::diagnostics

#endif
