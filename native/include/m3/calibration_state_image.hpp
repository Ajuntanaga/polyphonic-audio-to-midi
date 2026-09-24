#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/string_calibration.hpp"

namespace m3 {

inline constexpr std::size_t kCalibrationPointStateSize = 19U;
inline constexpr std::size_t kCalibrationStateHeaderSize = 24U;
inline constexpr std::size_t kCalibrationStatePayloadSize =
    1U + kMaxVoices * kCalibrationFretCount * kCalibrationPointStateSize;
inline constexpr std::size_t kCalibrationStateSize =
    kCalibrationStateHeaderSize + kCalibrationStatePayloadSize;
using CalibrationStateImage =
    std::array<std::uint8_t, kCalibrationStateSize>;

bool encode_calibration_state(const StringCalibrationBank& bank,
                              CalibrationStateImage& output) noexcept;
bool decode_calibration_state(const std::uint8_t* bytes, std::size_t size,
                              StringCalibrationBank& output) noexcept;

}  // namespace m3
