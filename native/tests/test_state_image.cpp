#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#include "m3/parameter_contract.hpp"
#include "m3/state_image.hpp"
#include "test_support.hpp"

namespace {

constexpr m3::StateImage kExpectedDefaultState{
    0x4D, 0x33, 0x50, 0x41, 0x01, 0x00, 0x0E, 0x00, 0xA8, 0x00, 0x00, 0x00, 0x0C, 0xCF, 0x81, 0x59,
    0x01, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x33, 0x4D,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x80, 0x7B, 0x40, 0x04, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x05, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x49, 0x40, 0x06, 0x00, 0x33, 0x4D,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x39, 0x40, 0x07, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x40, 0x40, 0x08, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x55, 0x40,
    0x09, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x40, 0x0A, 0x00, 0x33, 0x4D,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x38, 0x40, 0x0B, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xF0, 0x3F, 0x0C, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x59, 0x40,
    0x0D, 0x00, 0x33, 0x4D, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF0, 0x3F, 0x0F, 0x00, 0x33, 0x4D,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF0, 0x3F,
};

constexpr std::array<std::uint8_t, 32> kExpectedDefaultSha256{{
    0xF2, 0x9E, 0x4E, 0xF0, 0x9A, 0xAF, 0x4A, 0x5B,
    0xFD, 0x47, 0x19, 0xEF, 0xBE, 0x96, 0xD4, 0x37,
    0x0A, 0x31, 0xDA, 0x4B, 0xE4, 0x04, 0x51, 0x03,
    0x29, 0xE2, 0xC2, 0x7F, 0xEE, 0x21, 0xA4, 0x75,
}};

constexpr std::array<m3::ParameterId, m3::kPersistentParameterCount>
    kExpectedIds{{
        0x4D330001U, 0x4D330002U, 0x4D330003U, 0x4D330004U,
        0x4D330005U, 0x4D330006U, 0x4D330007U, 0x4D330008U,
        0x4D330009U, 0x4D33000AU, 0x4D33000BU, 0x4D33000CU,
        0x4D33000DU, 0x4D33000FU,
    }};

constexpr std::array<std::uint32_t, 64> kSha256Constants{{
    0x428A2F98U, 0x71374491U, 0xB5C0FBCFU, 0xE9B5DBA5U,
    0x3956C25BU, 0x59F111F1U, 0x923F82A4U, 0xAB1C5ED5U,
    0xD807AA98U, 0x12835B01U, 0x243185BEU, 0x550C7DC3U,
    0x72BE5D74U, 0x80DEB1FEU, 0x9BDC06A7U, 0xC19BF174U,
    0xE49B69C1U, 0xEFBE4786U, 0x0FC19DC6U, 0x240CA1CCU,
    0x2DE92C6FU, 0x4A7484AAU, 0x5CB0A9DCU, 0x76F988DAU,
    0x983E5152U, 0xA831C66DU, 0xB00327C8U, 0xBF597FC7U,
    0xC6E00BF3U, 0xD5A79147U, 0x06CA6351U, 0x14292967U,
    0x27B70A85U, 0x2E1B2138U, 0x4D2C6DFCU, 0x53380D13U,
    0x650A7354U, 0x766A0ABBU, 0x81C2C92EU, 0x92722C85U,
    0xA2BFE8A1U, 0xA81A664BU, 0xC24B8B70U, 0xC76C51A3U,
    0xD192E819U, 0xD6990624U, 0xF40E3585U, 0x106AA070U,
    0x19A4C116U, 0x1E376C08U, 0x2748774CU, 0x34B0BCB5U,
    0x391C0CB3U, 0x4ED8AA4AU, 0x5B9CCA4FU, 0x682E6FF3U,
    0x748F82EEU, 0x78A5636FU, 0x84C87814U, 0x8CC70208U,
    0x90BEFFFAU, 0xA4506CEBU, 0xBEF9A3F7U, 0xC67178F2U,
}};

std::uint32_t rotate_right(std::uint32_t value,
                           std::uint32_t count) noexcept {
  return (value >> count) | (value << (32U - count));
}

std::array<std::uint8_t, 32> sha256(const std::uint8_t* data,
                                    std::size_t size) noexcept {
  constexpr std::size_t kBlockSize = 64;
  constexpr std::size_t kPaddedSize =
      ((m3::kStateSize + 9U + kBlockSize - 1U) / kBlockSize) * kBlockSize;
  std::array<std::uint8_t, kPaddedSize> padded{};
  std::copy_n(data, size, padded.data());
  padded[size] = 0x80U;
  const std::uint64_t bit_size = static_cast<std::uint64_t>(size) * 8U;
  for (std::size_t index = 0; index < 8; ++index) {
    padded[padded.size() - 1U - index] =
        static_cast<std::uint8_t>(bit_size >> (index * 8U));
  }

  std::array<std::uint32_t, 8> state{{
      0x6A09E667U, 0xBB67AE85U, 0x3C6EF372U, 0xA54FF53AU,
      0x510E527FU, 0x9B05688CU, 0x1F83D9ABU, 0x5BE0CD19U,
  }};
  for (std::size_t block = 0; block < padded.size(); block += kBlockSize) {
    std::array<std::uint32_t, 64> words{};
    for (std::size_t index = 0; index < 16; ++index) {
      const std::uint8_t* input = padded.data() + block + index * 4U;
      words[index] = (static_cast<std::uint32_t>(input[0]) << 24U) |
                     (static_cast<std::uint32_t>(input[1]) << 16U) |
                     (static_cast<std::uint32_t>(input[2]) << 8U) |
                     static_cast<std::uint32_t>(input[3]);
    }
    for (std::size_t index = 16; index < words.size(); ++index) {
      const std::uint32_t s0 =
          rotate_right(words[index - 15U], 7U) ^
          rotate_right(words[index - 15U], 18U) ^
          (words[index - 15U] >> 3U);
      const std::uint32_t s1 =
          rotate_right(words[index - 2U], 17U) ^
          rotate_right(words[index - 2U], 19U) ^
          (words[index - 2U] >> 10U);
      words[index] = words[index - 16U] + s0 + words[index - 7U] + s1;
    }

    std::array<std::uint32_t, 8> working = state;
    for (std::size_t index = 0; index < words.size(); ++index) {
      const std::uint32_t sum1 = rotate_right(working[4], 6U) ^
                                 rotate_right(working[4], 11U) ^
                                 rotate_right(working[4], 25U);
      const std::uint32_t choose =
          (working[4] & working[5]) ^ (~working[4] & working[6]);
      const std::uint32_t temporary1 =
          working[7] + sum1 + choose + kSha256Constants[index] + words[index];
      const std::uint32_t sum0 = rotate_right(working[0], 2U) ^
                                 rotate_right(working[0], 13U) ^
                                 rotate_right(working[0], 22U);
      const std::uint32_t majority =
          (working[0] & working[1]) ^ (working[0] & working[2]) ^
          (working[1] & working[2]);
      const std::uint32_t temporary2 = sum0 + majority;
      working[7] = working[6];
      working[6] = working[5];
      working[5] = working[4];
      working[4] = working[3] + temporary1;
      working[3] = working[2];
      working[2] = working[1];
      working[1] = working[0];
      working[0] = temporary1 + temporary2;
    }
    for (std::size_t index = 0; index < state.size(); ++index) {
      state[index] += working[index];
    }
  }

  std::array<std::uint8_t, 32> digest{};
  for (std::size_t index = 0; index < state.size(); ++index) {
    digest[index * 4U] = static_cast<std::uint8_t>(state[index] >> 24U);
    digest[index * 4U + 1U] = static_cast<std::uint8_t>(state[index] >> 16U);
    digest[index * 4U + 2U] = static_cast<std::uint8_t>(state[index] >> 8U);
    digest[index * 4U + 3U] = static_cast<std::uint8_t>(state[index]);
  }
  return digest;
}

std::uint32_t test_crc32(const std::uint8_t* data, std::size_t size) noexcept {
  std::uint32_t crc = 0xFFFFFFFFU;
  for (std::size_t index = 0; index < size; ++index) {
    crc ^= data[index];
    for (int bit = 0; bit < 8; ++bit) {
      crc = (crc >> 1U) ^ ((crc & 1U) != 0U ? 0xEDB88320U : 0U);
    }
  }
  return crc ^ 0xFFFFFFFFU;
}

void put_u32(std::uint8_t* bytes, std::uint32_t value) noexcept {
  for (std::size_t index = 0; index < 4; ++index) {
    bytes[index] = static_cast<std::uint8_t>(value >> (index * 8U));
  }
}

std::uint32_t get_u32(const std::uint8_t* bytes) noexcept {
  std::uint32_t value = 0;
  for (std::size_t index = 0; index < 4; ++index) {
    value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8U);
  }
  return value;
}

void put_double(std::uint8_t* bytes, double value) noexcept {
  std::uint64_t bits = 0;
  std::memcpy(&bits, &value, sizeof(bits));
  for (std::size_t index = 0; index < 8; ++index) {
    bytes[index] = static_cast<std::uint8_t>(bits >> (index * 8U));
  }
}

void refresh_crc(m3::StateImage& image) noexcept {
  put_u32(image.data() + 12, test_crc32(image.data() + 16, 168));
}

bool same_config(const m3::PersistentConfig& left,
                 const m3::PersistentConfig& right) noexcept {
  return left.detector_input == right.detector_input &&
         left.profile_mode == right.profile_mode && left.a4_hz == right.a4_hz &&
         left.input_trim_db == right.input_trim_db &&
         left.sensitivity == right.sensitivity && left.response == right.response &&
         left.lowest_note == right.lowest_note &&
         left.highest_note == right.highest_note &&
         left.max_polyphony == right.max_polyphony &&
         left.max_fret == right.max_fret &&
         left.velocity_mode == right.velocity_mode &&
         left.fixed_velocity == right.fixed_velocity &&
         left.midi_channel == right.midi_channel &&
         left.dry_passthrough == right.dry_passthrough;
}

}  // namespace

M3_TEST(state_image_default_bytes_and_sha256_are_exact) {
  m3::StateImage actual{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, actual));
  M3_EXPECT_EQ(actual.size(), 184U);
  for (std::size_t index = 0; index < actual.size(); ++index) {
    M3_EXPECT_EQ(actual[index], kExpectedDefaultState[index]);
  }
  const std::array<std::uint8_t, 32> digest =
      sha256(actual.data(), actual.size());
  for (std::size_t index = 0; index < digest.size(); ++index) {
    M3_EXPECT_EQ(digest[index], kExpectedDefaultSha256[index]);
  }
}

M3_TEST(state_image_round_trips_all_fourteen_nondefault_values) {
  m3::PersistentConfig source;
  source.detector_input = m3::DetectorInput::downmix;
  source.profile_mode = m3::ProfileMode::general;
  source.a4_hz = 432.5;
  source.input_trim_db = -12.5;
  source.sensitivity = 77;
  source.response = 88;
  source.lowest_note = 24;
  source.highest_note = 108;
  source.max_polyphony = 3;
  source.max_fret = 36;
  source.velocity_mode = m3::VelocityMode::fixed;
  source.fixed_velocity = 1;
  source.midi_channel = 16;
  source.dry_passthrough = false;
  m3::StateImage image{};
  M3_EXPECT_TRUE(m3::encode_state(source, image));
  m3::PersistentConfig decoded;
  M3_EXPECT_TRUE(m3::decode_state(image.data(), image.size(), decoded));
  M3_EXPECT_TRUE(same_config(decoded, source));
}

M3_TEST(state_image_header_crc_and_ordered_ids_are_exact) {
  M3_EXPECT_EQ(kExpectedDefaultState[0], static_cast<std::uint8_t>('M'));
  M3_EXPECT_EQ(kExpectedDefaultState[1], static_cast<std::uint8_t>('3'));
  M3_EXPECT_EQ(kExpectedDefaultState[2], static_cast<std::uint8_t>('P'));
  M3_EXPECT_EQ(kExpectedDefaultState[3], static_cast<std::uint8_t>('A'));
  M3_EXPECT_EQ(kExpectedDefaultState[4], 1U);
  M3_EXPECT_EQ(kExpectedDefaultState[5], 0U);
  M3_EXPECT_EQ(kExpectedDefaultState[6], 14U);
  M3_EXPECT_EQ(kExpectedDefaultState[7], 0U);
  M3_EXPECT_EQ(get_u32(kExpectedDefaultState.data() + 8), 168U);
  M3_EXPECT_EQ(get_u32(kExpectedDefaultState.data() + 12),
               test_crc32(kExpectedDefaultState.data() + 16, 168));
  for (std::size_t index = 0; index < kExpectedIds.size(); ++index) {
    M3_EXPECT_EQ(get_u32(kExpectedDefaultState.data() + 16 + index * 12U),
                 kExpectedIds[index]);
    if (index > 0) {
      M3_EXPECT_TRUE(kExpectedIds[index - 1U] < kExpectedIds[index]);
    }
  }
}

M3_TEST(state_image_rejects_every_truncation_and_one_trailing_byte) {
  m3::PersistentConfig config;
  for (std::size_t size = 0; size < kExpectedDefaultState.size(); ++size) {
    M3_EXPECT_FALSE(m3::decode_state(kExpectedDefaultState.data(), size, config));
  }
  std::array<std::uint8_t, 185> trailing{};
  std::copy(kExpectedDefaultState.begin(), kExpectedDefaultState.end(),
            trailing.begin());
  trailing.back() = 0x5AU;
  M3_EXPECT_FALSE(m3::decode_state(trailing.data(), trailing.size(), config));
}

M3_TEST(state_image_rejects_schema_crc_duplicate_missing_unknown_and_nonfinite) {
  m3::PersistentConfig destination;
  destination.a4_hz = 432.5;
  destination.midi_channel = 16;
  const m3::PersistentConfig before = destination;
  const auto rejected = [&](const m3::StateImage& candidate) noexcept {
    M3_EXPECT_FALSE(
        m3::decode_state(candidate.data(), candidate.size(), destination));
    M3_EXPECT_TRUE(same_config(destination, before));
  };

  m3::StateImage image = kExpectedDefaultState;
  image[0] = 'X';
  rejected(image);
  image = kExpectedDefaultState;
  image[4] = 2U;
  rejected(image);
  image = kExpectedDefaultState;
  image[6] = 13U;
  rejected(image);
  image = kExpectedDefaultState;
  image[8] = 0xA7U;
  rejected(image);
  image = kExpectedDefaultState;
  image[16] ^= 1U;
  rejected(image);

  image = kExpectedDefaultState;
  put_u32(image.data() + 28, kExpectedIds[0]);
  refresh_crc(image);
  rejected(image);
  image = kExpectedDefaultState;
  put_u32(image.data() + 16, 0xDEADBEEFU);
  refresh_crc(image);
  rejected(image);
  image = kExpectedDefaultState;
  std::array<std::uint8_t, 12> record{};
  std::copy_n(image.data() + 16, record.size(), record.data());
  std::copy_n(image.data() + 28, record.size(), image.data() + 16);
  std::copy_n(record.data(), record.size(), image.data() + 28);
  refresh_crc(image);
  rejected(image);

  image = kExpectedDefaultState;
  put_double(image.data() + 16 + 2U * 12U + 4U,
             std::numeric_limits<double>::quiet_NaN());
  refresh_crc(image);
  rejected(image);
  image = kExpectedDefaultState;
  put_double(image.data() + 16 + 2U * 12U + 4U,
             std::numeric_limits<double>::infinity());
  refresh_crc(image);
  rejected(image);
}

M3_TEST(state_image_uses_common_canonicalization_and_rejects_invalid_encode) {
  m3::StateImage image = kExpectedDefaultState;
  put_double(image.data() + 16 + 0U * 12U + 4U, 99.0);
  put_double(image.data() + 16 + 2U * 12U + 4U, 432.56);
  put_double(image.data() + 16 + 12U * 12U + 4U, -9.0);
  refresh_crc(image);
  m3::PersistentConfig config;
  M3_EXPECT_TRUE(m3::decode_state(image.data(), image.size(), config));
  M3_EXPECT_EQ(config.detector_input, m3::DetectorInput::downmix);
  M3_EXPECT_NEAR(config.a4_hz, 432.6, 1.0e-12);
  M3_EXPECT_EQ(config.midi_channel, 1U);

  config.a4_hz = std::numeric_limits<double>::quiet_NaN();
  M3_EXPECT_FALSE(m3::encode_state(config, image));
  config.a4_hz = std::numeric_limits<double>::infinity();
  M3_EXPECT_FALSE(m3::encode_state(config, image));
  config.a4_hz = 999.0;
  M3_EXPECT_FALSE(m3::encode_state(config, image));
}
