#pragma once

#include <array>
#include <cstdint>

namespace m3::vst3 {

inline constexpr std::array<std::uint32_t, 4> kProductionClassIdWords{
    0x4A1BA42FU, 0x6D704609U, 0x8B52450CU, 0x3842F11FU};
inline constexpr std::array<std::uint32_t, 4> kProbeClassIdWords{
    0x6F62F8B1U, 0xB8A14872U, 0xA0D92C3CU, 0x274421D8U};
inline constexpr std::array<std::uint32_t, 4> kBenchmarkClassIdWords{
    0x28713895U, 0x1CCA47ECU, 0x919F6CC1U, 0xBCB88A8FU};

inline constexpr char kDescriptiveId[] =
    "com.ajuntanaga.m3-polyphonic-audio-to-midi";
inline constexpr char kVendorName[] = "ajuntanaga";
inline constexpr char kProductName[] = "M3 Polyphonic Audio to MIDI";
inline constexpr char kProbeProductName[] =
    "M3 Polyphonic Audio to MIDI Probe";
inline constexpr char kBenchmarkProductName[] =
    "M3 Polyphonic Audio to MIDI Benchmark";
inline constexpr char kVersionString[] = "0.1.0";
inline constexpr char kProductionSubcategories[] = "Fx|Tools";

}  // namespace m3::vst3
