#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace m3 {

inline constexpr std::uint32_t kDecisionQuantum = 64;
#if defined(M3_TESTING)
inline constexpr std::uint32_t kLegacyTestQuantum = 128;
#endif
inline constexpr std::uint32_t kMaxHostFrames = 16384;
inline constexpr std::size_t kMaxCandidates = 87;
inline constexpr std::size_t kMaxHarmonics = 8;
inline constexpr std::size_t kMaxVoices = 8;
inline constexpr std::size_t kMaxInternalSelections = 16;
inline constexpr std::size_t kMaxTickTransitions = 16;
inline constexpr std::array<std::uint8_t, 8> kM3OpenNotes{
    32, 36, 40, 44, 48, 52, 56, 60};
// D'Addario NYXL0980, ordered with the M3 lanes from the thickest G#1 string
// to the thinnest C4 string. Gauge is stored in thousandths of an inch.
inline constexpr std::array<std::uint8_t, 8> kM3StringGaugeMils{
    80, 60, 44, 32, 24, 16, 12, 9};

}  // namespace m3
