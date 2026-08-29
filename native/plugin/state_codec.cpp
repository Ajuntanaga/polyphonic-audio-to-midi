#include "state_codec.hpp"

#include <cmath>
#include <cstring>

#include "parameter_contract.hpp"

namespace {

constexpr std::size_t kHeaderSize = 16;
constexpr std::size_t kRecordSize = 12;
constexpr std::size_t kPayloadSize = 168;

void put_u16(std::uint8_t* output, std::uint16_t value) noexcept {
  output[0] = static_cast<std::uint8_t>(value);
  output[1] = static_cast<std::uint8_t>(value >> 8U);
}

void put_u32(std::uint8_t* output, std::uint32_t value) noexcept {
  for (std::size_t index = 0; index < 4; ++index) {
    output[index] = static_cast<std::uint8_t>(value >> (index * 8U));
  }
}

void put_u64(std::uint8_t* output, std::uint64_t value) noexcept {
  for (std::size_t index = 0; index < 8; ++index) {
    output[index] = static_cast<std::uint8_t>(value >> (index * 8U));
  }
}

std::uint16_t get_u16(const std::uint8_t* input) noexcept {
  return static_cast<std::uint16_t>(input[0]) |
         static_cast<std::uint16_t>(static_cast<std::uint16_t>(input[1]) << 8U);
}

std::uint32_t get_u32(const std::uint8_t* input) noexcept {
  std::uint32_t value = 0;
  for (std::size_t index = 0; index < 4; ++index) {
    value |= static_cast<std::uint32_t>(input[index]) << (index * 8U);
  }
  return value;
}

std::uint64_t get_u64(const std::uint8_t* input) noexcept {
  std::uint64_t value = 0;
  for (std::size_t index = 0; index < 8; ++index) {
    value |= static_cast<std::uint64_t>(input[index]) << (index * 8U);
  }
  return value;
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) noexcept {
  std::uint32_t crc = 0xFFFFFFFFU;
  for (std::size_t index = 0; index < size; ++index) {
    crc ^= data[index];
    for (int bit = 0; bit < 8; ++bit) {
      const std::uint32_t mask = 0U - (crc & 1U);
      crc = (crc >> 1U) ^ (0xEDB88320U & mask);
    }
  }
  return crc ^ 0xFFFFFFFFU;
}

}  // namespace

namespace m3 {

bool encode_state(const PersistentConfig& config, StateImage& output) noexcept {
  output = {};
  output[0] = 'M';
  output[1] = '3';
  output[2] = 'P';
  output[3] = 'A';
  put_u16(output.data() + 4, 1);
  put_u16(output.data() + 6,
          static_cast<std::uint16_t>(kPersistentParameterCount));
  put_u32(output.data() + 8, static_cast<std::uint32_t>(kPayloadSize));

  const ParameterId* ids = persistent_parameter_ids();
  for (std::size_t index = 0; index < kPersistentParameterCount; ++index) {
    double value = 0.0;
    if (!parameter_value(config, Status::ready, ids[index], value) ||
        !std::isfinite(value)) {
      return false;
    }
    const ParameterSpec* record = find_parameter(ids[index]);
    if (record == nullptr || value < record->minimum || value > record->maximum) {
      return false;
    }
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    std::uint8_t* destination = output.data() + kHeaderSize + index * kRecordSize;
    put_u32(destination, ids[index]);
    put_u64(destination + 4, bits);
  }
  put_u32(output.data() + 12,
          crc32(output.data() + kHeaderSize, kPayloadSize));
  return true;
}

bool decode_state(const std::uint8_t* bytes, std::size_t size,
                  PersistentConfig& output) noexcept {
  if (bytes == nullptr || size != kStateSize || bytes[0] != 'M' ||
      bytes[1] != '3' || bytes[2] != 'P' || bytes[3] != 'A' ||
      get_u16(bytes + 4) != 1 ||
      get_u16(bytes + 6) != kPersistentParameterCount ||
      get_u32(bytes + 8) != kPayloadSize ||
      get_u32(bytes + 12) != crc32(bytes + kHeaderSize, kPayloadSize)) {
    return false;
  }

  PersistentConfig candidate;
  const ParameterId* ids = persistent_parameter_ids();
  for (std::size_t index = 0; index < kPersistentParameterCount; ++index) {
    const std::uint8_t* source = bytes + kHeaderSize + index * kRecordSize;
    if (get_u32(source) != ids[index]) {
      return false;
    }
    const std::uint64_t bits = get_u64(source + 4);
    double value = 0.0;
    std::memcpy(&value, &bits, sizeof(value));
    if (!std::isfinite(value)) {
      return false;
    }
    const ParameterApplyResult result = apply_parameter(candidate, ids[index], value);
    if (result == ParameterApplyResult::rejected ||
        result == ParameterApplyResult::panic) {
      return false;
    }
  }
  output = candidate;
  return true;
}

bool save_state(const PersistentConfig& config,
                const clap_ostream_t* stream) noexcept {
  if (stream == nullptr || stream->write == nullptr) {
    return false;
  }
  StateImage image{};
  if (!encode_state(config, image)) {
    return false;
  }
  std::size_t position = 0;
  while (position < image.size()) {
    const std::uint64_t remaining = image.size() - position;
    const std::int64_t written =
        stream->write(stream, image.data() + position, remaining);
    if (written <= 0 || static_cast<std::uint64_t>(written) > remaining) {
      return false;
    }
    position += static_cast<std::size_t>(written);
  }
  return true;
}

bool load_state(const clap_istream_t* stream,
                PersistentConfig& output) noexcept {
  if (stream == nullptr || stream->read == nullptr) {
    return false;
  }
  StateImage image{};
  std::size_t position = 0;
  while (position < image.size()) {
    const std::uint64_t remaining = image.size() - position;
    const std::int64_t read = stream->read(stream, image.data() + position, remaining);
    if (read <= 0 || static_cast<std::uint64_t>(read) > remaining) {
      return false;
    }
    position += static_cast<std::size_t>(read);
  }
  std::uint8_t trailing = 0;
  const std::int64_t extra = stream->read(stream, &trailing, 1);
  if (extra != 0) {
    return false;
  }
  PersistentConfig candidate;
  if (!decode_state(image.data(), image.size(), candidate)) {
    return false;
  }
  output = candidate;
  return true;
}

}  // namespace m3
