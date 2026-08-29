#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/types.hpp"

namespace m3 {

inline constexpr std::size_t kStateSize = 184;
using StateImage = std::array<std::uint8_t, kStateSize>;

bool encode_state(const PersistentConfig& config, StateImage& output) noexcept;
bool decode_state(const std::uint8_t* bytes, std::size_t size,
                  PersistentConfig& output) noexcept;

}  // namespace m3
