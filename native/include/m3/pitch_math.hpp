#pragma once

#include <cmath>

namespace m3 {

inline bool is_finite(double value) noexcept { return std::isfinite(value); }

template <typename T>
constexpr T clamp_value(T value, T minimum, T maximum) noexcept {
  return value < minimum ? minimum : (value > maximum ? maximum : value);
}

inline double midi_to_frequency(double midi_note, double a4_hz) noexcept {
  return a4_hz * std::exp2((midi_note - 69.0) / 12.0);
}

}  // namespace m3
