#include <clap/clap.h>
#include <clap/ext/params.h>
#include <clap/ext/state.h>
#include <clap/factory/plugin-factory.h>
#include <clap/stream.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#include "fake_clap_host.hpp"
#include "parameter_contract.hpp"
#include "state_codec.hpp"
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

class MemoryOutput final {
 public:
  explicit MemoryOutput(std::uint64_t chunk) noexcept : chunk_(chunk) {
    stream_.ctx = this;
    stream_.write = &write;
  }
  const clap_ostream_t* stream() const noexcept { return &stream_; }
  const m3::StateImage& bytes() const noexcept { return bytes_; }
  std::size_t size() const noexcept { return size_; }
  void fail_with(std::int64_t result) noexcept { failure_ = result; }

 private:
  static std::int64_t CLAP_ABI write(const clap_ostream_t* stream,
                                     const void* source,
                                     std::uint64_t size) noexcept {
    auto* self = static_cast<MemoryOutput*>(stream->ctx);
    if (self->failure_ <= 0) {
      return self->failure_;
    }
    const std::size_t amount = std::min<std::size_t>(
        {static_cast<std::size_t>(size), static_cast<std::size_t>(self->chunk_),
         self->bytes_.size() - self->size_});
    std::memcpy(self->bytes_.data() + self->size_, source, amount);
    self->size_ += amount;
    return static_cast<std::int64_t>(amount);
  }

  clap_ostream_t stream_{};
  m3::StateImage bytes_{};
  std::uint64_t chunk_{};
  std::size_t size_{};
  std::int64_t failure_{1};
};

class MemoryInput final {
 public:
  MemoryInput(const std::uint8_t* bytes, std::size_t size,
              std::uint64_t chunk) noexcept
      : bytes_(bytes), size_(size), chunk_(chunk) {
    stream_.ctx = this;
    stream_.read = &read;
  }
  const clap_istream_t* stream() const noexcept { return &stream_; }
  void fail_with(std::int64_t result) noexcept { failure_ = result; }

 private:
  static std::int64_t CLAP_ABI read(const clap_istream_t* stream, void* destination,
                                    std::uint64_t size) noexcept {
    auto* self = static_cast<MemoryInput*>(stream->ctx);
    if (self->failure_ <= 0) {
      return self->failure_;
    }
    if (self->position_ == self->size_) {
      return 0;
    }
    const std::size_t amount = std::min<std::size_t>(
        {static_cast<std::size_t>(size), static_cast<std::size_t>(self->chunk_),
         self->size_ - self->position_});
    std::memcpy(destination, self->bytes_ + self->position_, amount);
    self->position_ += amount;
    return static_cast<std::int64_t>(amount);
  }

  clap_istream_t stream_{};
  const std::uint8_t* bytes_{};
  std::size_t size_{};
  std::uint64_t chunk_{};
  std::size_t position_{};
  std::int64_t failure_{1};
};

const clap_plugin_t* create_state_plugin(m3::test::FakeClapHost& host) noexcept {
  M3_EXPECT_TRUE(clap_entry.init("/build/test/M3.clap"));
  const auto* factory = static_cast<const clap_plugin_factory_t*>(
      clap_entry.get_factory(CLAP_PLUGIN_FACTORY_ID));
  M3_EXPECT_TRUE(factory != nullptr);
  const clap_plugin_descriptor_t* descriptor =
      factory->get_plugin_descriptor(factory, 0);
  M3_EXPECT_TRUE(descriptor != nullptr);
  const clap_plugin_t* plugin =
      factory->create_plugin(factory, host.host(), descriptor->id);
  M3_EXPECT_TRUE(plugin != nullptr);
  M3_EXPECT_TRUE(plugin->init(plugin));
  return plugin;
}

}  // namespace

M3_TEST(state_default_encoding_is_byte_exact_and_fixed_size) {
  m3::StateImage actual{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, actual));
  M3_EXPECT_EQ(actual.size(), 184U);
  for (std::size_t index = 0; index < actual.size(); ++index) {
    M3_EXPECT_EQ(actual[index], kExpectedDefaultState[index]);
  }
}

M3_TEST(state_round_trips_all_fourteen_nondefault_values) {
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
  M3_EXPECT_EQ(decoded.detector_input, source.detector_input);
  M3_EXPECT_EQ(decoded.profile_mode, source.profile_mode);
  M3_EXPECT_NEAR(decoded.a4_hz, source.a4_hz, 0.0);
  M3_EXPECT_NEAR(decoded.input_trim_db, source.input_trim_db, 0.0);
  M3_EXPECT_EQ(decoded.sensitivity, source.sensitivity);
  M3_EXPECT_EQ(decoded.response, source.response);
  M3_EXPECT_EQ(decoded.lowest_note, source.lowest_note);
  M3_EXPECT_EQ(decoded.highest_note, source.highest_note);
  M3_EXPECT_EQ(decoded.max_polyphony, source.max_polyphony);
  M3_EXPECT_EQ(decoded.max_fret, source.max_fret);
  M3_EXPECT_EQ(decoded.velocity_mode, source.velocity_mode);
  M3_EXPECT_EQ(decoded.fixed_velocity, source.fixed_velocity);
  M3_EXPECT_EQ(decoded.midi_channel, source.midi_channel);
  M3_EXPECT_EQ(decoded.dry_passthrough, source.dry_passthrough);
}

M3_TEST(state_streams_support_partial_progress_and_reject_zero_or_negative) {
  MemoryOutput output(7);
  M3_EXPECT_TRUE(m3::save_state(m3::PersistentConfig{}, output.stream()));
  M3_EXPECT_EQ(output.size(), 184U);
  MemoryInput input(output.bytes().data(), output.size(), 5);
  m3::PersistentConfig decoded;
  M3_EXPECT_TRUE(m3::load_state(input.stream(), decoded));

  MemoryOutput zero_output(7);
  zero_output.fail_with(0);
  M3_EXPECT_FALSE(m3::save_state(m3::PersistentConfig{}, zero_output.stream()));
  MemoryOutput negative_output(7);
  negative_output.fail_with(-1);
  M3_EXPECT_FALSE(m3::save_state(m3::PersistentConfig{}, negative_output.stream()));
  MemoryInput negative_input(kExpectedDefaultState.data(),
                             kExpectedDefaultState.size(), 5);
  negative_input.fail_with(-1);
  M3_EXPECT_FALSE(m3::load_state(negative_input.stream(), decoded));
  MemoryInput zero_input(kExpectedDefaultState.data(),
                         kExpectedDefaultState.size(), 5);
  zero_input.fail_with(0);
  M3_EXPECT_FALSE(m3::load_state(zero_input.stream(), decoded));
}

M3_TEST(state_rejects_every_truncation_and_trailing_bytes) {
  m3::PersistentConfig config;
  for (std::size_t size = 0; size < kExpectedDefaultState.size(); ++size) {
    M3_EXPECT_FALSE(m3::decode_state(kExpectedDefaultState.data(), size, config));
  }
  std::array<std::uint8_t, 185> trailing{};
  std::copy(kExpectedDefaultState.begin(), kExpectedDefaultState.end(), trailing.begin());
  trailing.back() = 0x5A;
  M3_EXPECT_FALSE(m3::decode_state(trailing.data(), trailing.size(), config));
}

M3_TEST(state_rejects_bad_header_crc_ids_order_and_nonfinite_values) {
  m3::PersistentConfig config;
  m3::StateImage image = kExpectedDefaultState;
  image[0] = 'X';
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  image[4] = 2;
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  image[8] = 0xA7;
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  image[16] ^= 1U;
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));

  image = kExpectedDefaultState;
  put_u32(image.data() + 28, 0x4D330001U);
  refresh_crc(image);
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  put_u32(image.data() + 16, 0xDEADBEEFU);
  refresh_crc(image);
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  std::array<std::uint8_t, 12> record{};
  std::copy_n(image.data() + 16, 12, record.data());
  std::copy_n(image.data() + 28, 12, image.data() + 16);
  std::copy_n(record.data(), 12, image.data() + 28);
  refresh_crc(image);
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));

  image = kExpectedDefaultState;
  put_double(image.data() + 16 + 2 * 12 + 4,
             std::numeric_limits<double>::quiet_NaN());
  refresh_crc(image);
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
  image = kExpectedDefaultState;
  put_double(image.data() + 16 + 2 * 12 + 4,
             std::numeric_limits<double>::infinity());
  refresh_crc(image);
  M3_EXPECT_FALSE(m3::decode_state(image.data(), image.size(), config));
}

M3_TEST(state_clamps_finite_out_of_range_values_with_common_validation) {
  m3::StateImage image = kExpectedDefaultState;
  put_double(image.data() + 16 + 0 * 12 + 4, 99.0);
  put_double(image.data() + 16 + 2 * 12 + 4, 999.0);
  put_double(image.data() + 16 + 12 * 12 + 4, -9.0);
  refresh_crc(image);
  m3::PersistentConfig config;
  M3_EXPECT_TRUE(m3::decode_state(image.data(), image.size(), config));
  M3_EXPECT_EQ(config.detector_input, m3::DetectorInput::downmix);
  M3_EXPECT_NEAR(config.a4_hz, 480.0, 0.0);
  M3_EXPECT_EQ(config.midi_channel, 1U);
}

M3_TEST(clap_state_extension_loads_atomically_and_saves_the_same_image) {
  m3::PersistentConfig config;
  config.detector_input = m3::DetectorInput::right;
  config.a4_hz = 432.5;
  config.midi_channel = 16;
  config.dry_passthrough = false;
  m3::StateImage expected{};
  M3_EXPECT_TRUE(m3::encode_state(config, expected));

  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_state_plugin(host);
  const auto* state = static_cast<const clap_plugin_state_t*>(
      plugin->get_extension(plugin, CLAP_EXT_STATE));
  const auto* params = static_cast<const clap_plugin_params_t*>(
      plugin->get_extension(plugin, CLAP_EXT_PARAMS));
  M3_EXPECT_TRUE(state != nullptr);
  M3_EXPECT_TRUE(params != nullptr);
  MemoryInput input(expected.data(), expected.size(), 9);
  M3_EXPECT_TRUE(state->load(plugin, input.stream()));
  M3_EXPECT_EQ(host.param_rescans(), 1U);
  double value = 0.0;
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D330003U, &value));
  M3_EXPECT_NEAR(value, 432.5, 0.0);
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D33000DU, &value));
  M3_EXPECT_NEAR(value, 16.0, 0.0);
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D33000FU, &value));
  M3_EXPECT_NEAR(value, 0.0, 0.0);
  M3_EXPECT_TRUE(params->get_value(plugin, m3::kPanicParameterId, &value));
  M3_EXPECT_NEAR(value, 0.0, 0.0);

  MemoryOutput output(11);
  M3_EXPECT_TRUE(state->save(plugin, output.stream()));
  M3_EXPECT_EQ(output.size(), expected.size());
  for (std::size_t index = 0; index < expected.size(); ++index) {
    M3_EXPECT_EQ(output.bytes()[index], expected[index]);
  }
  plugin->destroy(plugin);
  clap_entry.deinit();
}
