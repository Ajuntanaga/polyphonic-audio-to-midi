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

#include "clap_state_stream.hpp"
#include "fake_clap_host.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/state_image.hpp"
#include "test_support.hpp"

namespace {

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

class MemoryOutput final {
 public:
  explicit MemoryOutput(std::uint64_t chunk) noexcept : chunk_(chunk) {
    stream_.ctx = this;
    stream_.write = &write;
  }

  const clap_ostream_t* stream() const noexcept { return &stream_; }
  const m3::StateImage& bytes() const noexcept { return bytes_; }
  std::size_t size() const noexcept { return size_; }
  void return_override(std::int64_t value) noexcept {
    override_enabled_ = true;
    override_value_ = value;
  }

 private:
  static std::int64_t CLAP_ABI write(const clap_ostream_t* stream,
                                     const void* source,
                                     std::uint64_t size) noexcept {
    auto* self = static_cast<MemoryOutput*>(stream->ctx);
    if (self->override_enabled_) {
      return self->override_value_;
    }
    const std::size_t amount = std::min<std::size_t>(
        {static_cast<std::size_t>(size), static_cast<std::size_t>(self->chunk_),
         self->bytes_.size() - self->size_});
    if (amount > 0) {
      std::memcpy(self->bytes_.data() + self->size_, source, amount);
      self->size_ += amount;
    }
    return static_cast<std::int64_t>(amount);
  }

  clap_ostream_t stream_{};
  m3::StateImage bytes_{};
  std::uint64_t chunk_{};
  std::size_t size_{};
  bool override_enabled_{};
  std::int64_t override_value_{};
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
  void return_override(std::int64_t value) noexcept {
    override_enabled_ = true;
    override_value_ = value;
  }

 private:
  static std::int64_t CLAP_ABI read(const clap_istream_t* stream,
                                    void* destination,
                                    std::uint64_t size) noexcept {
    auto* self = static_cast<MemoryInput*>(stream->ctx);
    if (self->override_enabled_) {
      return self->override_value_;
    }
    if (self->position_ == self->size_) {
      return 0;
    }
    const std::size_t amount = std::min<std::size_t>(
        {static_cast<std::size_t>(size), static_cast<std::size_t>(self->chunk_),
         self->size_ - self->position_});
    if (amount > 0) {
      std::memcpy(destination, self->bytes_ + self->position_, amount);
      self->position_ += amount;
    }
    return static_cast<std::int64_t>(amount);
  }

  clap_istream_t stream_{};
  const std::uint8_t* bytes_{};
  std::size_t size_{};
  std::uint64_t chunk_{};
  std::size_t position_{};
  bool override_enabled_{};
  std::int64_t override_value_{};
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

M3_TEST(clap_state_stream_completes_partial_reads_and_writes_exactly) {
  m3::StateImage expected{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, expected));
  MemoryOutput output(7);
  M3_EXPECT_TRUE(m3::save_clap_state(m3::PersistentConfig{}, output.stream()));
  M3_EXPECT_EQ(output.size(), m3::kStateSize);
  for (std::size_t index = 0; index < expected.size(); ++index) {
    M3_EXPECT_EQ(output.bytes()[index], expected[index]);
  }

  MemoryInput input(output.bytes().data(), output.size(), 5);
  m3::PersistentConfig decoded;
  M3_EXPECT_TRUE(m3::load_clap_state(input.stream(), decoded));
  M3_EXPECT_TRUE(same_config(decoded, m3::PersistentConfig{}));
}

M3_TEST(clap_state_stream_rejects_null_zero_negative_and_overreported_progress) {
  m3::PersistentConfig decoded;
  M3_EXPECT_FALSE(m3::save_clap_state(m3::PersistentConfig{}, nullptr));
  M3_EXPECT_FALSE(m3::load_clap_state(nullptr, decoded));
  clap_ostream_t null_output{};
  clap_istream_t null_input{};
  M3_EXPECT_FALSE(m3::save_clap_state(m3::PersistentConfig{}, &null_output));
  M3_EXPECT_FALSE(m3::load_clap_state(&null_input, decoded));

  for (const std::int64_t result : {0, -1, 185}) {
    MemoryOutput output(7);
    output.return_override(result);
    M3_EXPECT_FALSE(m3::save_clap_state(m3::PersistentConfig{}, output.stream()));

    m3::StateImage image{};
    M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, image));
    MemoryInput input(image.data(), image.size(), 5);
    input.return_override(result);
    M3_EXPECT_FALSE(m3::load_clap_state(input.stream(), decoded));
  }
}

M3_TEST(clap_state_stream_rejects_premature_trailing_and_invalid_without_mutation) {
  m3::StateImage image{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, image));
  m3::PersistentConfig destination;
  destination.detector_input = m3::DetectorInput::right;
  destination.a4_hz = 432.5;
  destination.midi_channel = 16;
  destination.dry_passthrough = false;
  const m3::PersistentConfig before = destination;

  MemoryInput premature(image.data(), image.size() - 1U, 11);
  M3_EXPECT_FALSE(m3::load_clap_state(premature.stream(), destination));
  M3_EXPECT_TRUE(same_config(destination, before));

  std::array<std::uint8_t, m3::kStateSize + 1U> trailing{};
  std::copy(image.begin(), image.end(), trailing.begin());
  trailing.back() = 0x5AU;
  MemoryInput extra(trailing.data(), trailing.size(), 13);
  M3_EXPECT_FALSE(m3::load_clap_state(extra.stream(), destination));
  M3_EXPECT_TRUE(same_config(destination, before));

  image[0] = 'X';
  MemoryInput invalid(image.data(), image.size(), 17);
  M3_EXPECT_FALSE(m3::load_clap_state(invalid.stream(), destination));
  M3_EXPECT_TRUE(same_config(destination, before));
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
