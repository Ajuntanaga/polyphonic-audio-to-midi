#include "m3/calibration_state_image.hpp"

#include <algorithm>

namespace m3 {
namespace {

constexpr std::int16_t kMinimumCentsQ8 = -50 * 256;
constexpr std::int16_t kMaximumCentsQ8 = 50 * 256;
constexpr std::uint16_t kMaximumQ15 = 32767U;

void put_u16(std::uint8_t* output, std::uint16_t value) noexcept {
  output[0] = static_cast<std::uint8_t>(value);
  output[1] = static_cast<std::uint8_t>(value >> 8U);
}

void put_u32(std::uint8_t* output, std::uint32_t value) noexcept {
  for (std::size_t index = 0U; index < 4U; ++index) {
    output[index] =
        static_cast<std::uint8_t>(value >> (index * 8U));
  }
}

std::uint16_t get_u16(const std::uint8_t* input) noexcept {
  return static_cast<std::uint16_t>(input[0]) |
         static_cast<std::uint16_t>(
             static_cast<std::uint16_t>(input[1]) << 8U);
}

std::uint32_t get_u32(const std::uint8_t* input) noexcept {
  std::uint32_t value = 0U;
  for (std::size_t index = 0U; index < 4U; ++index) {
    value |= static_cast<std::uint32_t>(input[index]) << (index * 8U);
  }
  return value;
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) noexcept {
  std::uint32_t crc = 0xFFFFFFFFU;
  for (std::size_t index = 0U; index < size; ++index) {
    crc ^= data[index];
    for (std::uint8_t bit = 0U; bit < 8U; ++bit) {
      const std::uint32_t mask = 0U - (crc & 1U);
      crc = (crc >> 1U) ^ (0xEDB88320U & mask);
    }
  }
  return crc ^ 0xFFFFFFFFU;
}

bool valid_point(const StringCalibrationPoint& point) noexcept {
  if (point.cents_offset_q8 < kMinimumCentsQ8 ||
      point.cents_offset_q8 > kMaximumCentsQ8 ||
      point.confidence_q15 > kMaximumQ15) {
    return false;
  }
  for (const std::uint16_t harmonic : point.harmonic_profile_q15) {
    if (harmonic > kMaximumQ15) {
      return false;
    }
  }
  switch (point.quality) {
    case CalibrationPointQuality::missing:
      if (point.cents_offset_q8 != 0 || point.confidence_q15 != 0U ||
          point.observation_count != 0U) {
        return false;
      }
      return std::all_of(point.harmonic_profile_q15.begin(),
                         point.harmonic_profile_q15.end(),
                         [](std::uint16_t value) { return value == 0U; });
    case CalibrationPointQuality::measured:
      return point.observation_count != 0U;
    case CalibrationPointQuality::interpolated:
      return point.observation_count == 0U;
  }
  return false;
}

bool valid_bank(const StringCalibrationBank& bank) noexcept {
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const bool calibrated = bank.string_calibrated(string);
    for (const StringCalibrationPoint& point : bank.points[string]) {
      if (!valid_point(point) ||
          (calibrated &&
           point.quality == CalibrationPointQuality::missing) ||
          (!calibrated &&
           point.quality != CalibrationPointQuality::missing)) {
        return false;
      }
    }
  }
  return true;
}

}  // namespace

bool encode_calibration_state(const StringCalibrationBank& bank,
                              CalibrationStateImage& output) noexcept {
  if (!valid_bank(bank)) {
    return false;
  }
  output = {};
  output[0] = 'M';
  output[1] = '3';
  output[2] = 'C';
  output[3] = 'B';
  put_u16(output.data() + 4U, 1U);
  put_u16(output.data() + 6U, static_cast<std::uint16_t>(kMaxVoices));
  put_u16(output.data() + 8U,
          static_cast<std::uint16_t>(kCalibrationFretCount));
  put_u16(output.data() + 10U,
          static_cast<std::uint16_t>(kCalibrationHarmonicCount));
  put_u32(output.data() + 12U,
          static_cast<std::uint32_t>(kCalibrationStatePayloadSize));

  std::size_t offset = kCalibrationStateHeaderSize;
  output[offset++] = bank.calibrated_string_mask;
  for (const auto& string : bank.points) {
    for (const StringCalibrationPoint& point : string) {
      put_u16(output.data() + offset,
              static_cast<std::uint16_t>(point.cents_offset_q8));
      offset += 2U;
      for (const std::uint16_t harmonic : point.harmonic_profile_q15) {
        put_u16(output.data() + offset, harmonic);
        offset += 2U;
      }
      put_u16(output.data() + offset, point.confidence_q15);
      offset += 2U;
      put_u16(output.data() + offset, point.observation_count);
      offset += 2U;
      output[offset++] = static_cast<std::uint8_t>(point.quality);
    }
  }
  put_u32(output.data() + 16U,
          crc32(output.data() + kCalibrationStateHeaderSize,
                kCalibrationStatePayloadSize));
  return offset == output.size();
}

bool decode_calibration_state(const std::uint8_t* bytes, std::size_t size,
                              StringCalibrationBank& output) noexcept {
  if (bytes == nullptr || size != kCalibrationStateSize || bytes[0] != 'M' ||
      bytes[1] != '3' || bytes[2] != 'C' || bytes[3] != 'B' ||
      get_u16(bytes + 4U) != 1U ||
      get_u16(bytes + 6U) != kMaxVoices ||
      get_u16(bytes + 8U) != kCalibrationFretCount ||
      get_u16(bytes + 10U) != kCalibrationHarmonicCount ||
      get_u32(bytes + 12U) != kCalibrationStatePayloadSize ||
      get_u32(bytes + 20U) != 0U ||
      get_u32(bytes + 16U) !=
          crc32(bytes + kCalibrationStateHeaderSize,
                kCalibrationStatePayloadSize)) {
    return false;
  }
  StringCalibrationBank candidate;
  std::size_t offset = kCalibrationStateHeaderSize;
  candidate.calibrated_string_mask = bytes[offset++];
  for (auto& string : candidate.points) {
    for (StringCalibrationPoint& point : string) {
      point.cents_offset_q8 =
          static_cast<std::int16_t>(get_u16(bytes + offset));
      offset += 2U;
      for (std::uint16_t& harmonic : point.harmonic_profile_q15) {
        harmonic = get_u16(bytes + offset);
        offset += 2U;
      }
      point.confidence_q15 = get_u16(bytes + offset);
      offset += 2U;
      point.observation_count = get_u16(bytes + offset);
      offset += 2U;
      const std::uint8_t raw_quality = bytes[offset++];
      if (raw_quality >
          static_cast<std::uint8_t>(
              CalibrationPointQuality::interpolated)) {
        return false;
      }
      point.quality = static_cast<CalibrationPointQuality>(raw_quality);
    }
  }
  if (offset != size || !valid_bank(candidate)) {
    return false;
  }
  output = candidate;
  return true;
}

}  // namespace m3
