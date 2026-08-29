#include <clap/clap.h>
#include <clap/ext/audio-ports.h>
#include <clap/ext/latency.h>
#include <clap/ext/note-ports.h>
#include <clap/factory/plugin-factory.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>

#include "clap_adapter.hpp"
#include "fake_clap_host.hpp"
#include "test_support.hpp"

namespace {

const clap_plugin_factory_t* open_factory() noexcept {
  M3_EXPECT_TRUE(clap_entry.init("/build/test/M3.clap"));
  const void* raw = clap_entry.get_factory(CLAP_PLUGIN_FACTORY_ID);
  M3_EXPECT_TRUE(raw != nullptr);
  return static_cast<const clap_plugin_factory_t*>(raw);
}

const clap_plugin_t* create_initialized(const clap_plugin_factory_t* factory,
                                        m3::test::FakeClapHost& host) noexcept {
  const clap_plugin_descriptor_t* descriptor = factory->get_plugin_descriptor(factory, 0);
  M3_EXPECT_TRUE(descriptor != nullptr);
  const clap_plugin_t* plugin =
      factory->create_plugin(factory, host.host(), descriptor->id);
  M3_EXPECT_TRUE(plugin != nullptr);
  M3_EXPECT_TRUE(plugin->init(plugin));
  return plugin;
}

bool has_feature(const clap_plugin_descriptor_t* descriptor,
                 const char* wanted) noexcept {
  for (const char* const* feature = descriptor->features;
       feature != nullptr && *feature != nullptr; ++feature) {
    if (std::strcmp(*feature, wanted) == 0) {
      return true;
    }
  }
  return false;
}

template <typename Sample>
void expect_dry_modes_and_allocation_contract(const clap_plugin_t* plugin) noexcept {
  m3::test::FakeProcessBlock<Sample> block;
  constexpr std::uint32_t frame_counts[] = {1, 32, 64, 128, 256, 16384};
  for (const std::uint32_t frames : frame_counts) {
    for (const bool alias : {false, true}) {
      block.configure(frames, alias);
      block.fill_finite();
      m3::set_dry_passthrough_for_test(plugin, true);
      const std::size_t allocations_before = m3::test::allocation_count();
      const std::size_t deallocations_before = m3::test::deallocation_count();
      M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
      M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
      M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
      for (std::uint32_t frame = 0; frame < frames; ++frame) {
        M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
        M3_EXPECT_EQ(block.output_right()[frame], block.input_right()[frame]);
      }

      block.configure(frames, alias);
      block.fill_finite();
      m3::set_dry_passthrough_for_test(plugin, false);
      const std::size_t mute_allocations_before = m3::test::allocation_count();
      const std::size_t mute_deallocations_before = m3::test::deallocation_count();
      M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
      M3_EXPECT_EQ(m3::test::allocation_count(), mute_allocations_before);
      M3_EXPECT_EQ(m3::test::deallocation_count(), mute_deallocations_before);
      for (std::uint32_t frame = 0; frame < frames; ++frame) {
        M3_EXPECT_EQ(block.output_left()[frame], static_cast<Sample>(0));
        M3_EXPECT_EQ(block.output_right()[frame], static_cast<Sample>(0));
      }
    }
  }
}

}  // namespace

M3_TEST(clap_entry_exposes_exactly_one_descriptor_for_each_build_kind) {
  const clap_plugin_factory_t* factory = open_factory();
  M3_EXPECT_EQ(factory->get_plugin_count(factory), 1U);
  M3_EXPECT_TRUE(factory->get_plugin_descriptor(factory, 1) == nullptr);
  const clap_plugin_descriptor_t* descriptor = factory->get_plugin_descriptor(factory, 0);
  M3_EXPECT_TRUE(descriptor != nullptr);
  M3_EXPECT_TRUE(std::strcmp(descriptor->id,
                             "com.ajuntanaga.m3-polyphonic-audio-to-midi") == 0);
  M3_EXPECT_TRUE(std::strcmp(m3::probe_descriptor_for_test()->id,
                             "com.ajuntanaga.m3-polyphonic-audio-to-midi.probe") == 0);
  M3_EXPECT_TRUE(has_feature(descriptor, CLAP_PLUGIN_FEATURE_AUDIO_EFFECT));
  M3_EXPECT_TRUE(has_feature(descriptor, CLAP_PLUGIN_FEATURE_NOTE_EFFECT));
  M3_EXPECT_FALSE(has_feature(descriptor, CLAP_PLUGIN_FEATURE_INSTRUMENT));
  M3_EXPECT_FALSE(has_feature(descriptor, CLAP_PLUGIN_FEATURE_SYNTHESIZER));
  M3_EXPECT_TRUE(clap_entry.get_factory("not-a-clap-factory") == nullptr);
  clap_entry.deinit();
}

M3_TEST(clap_lifecycle_rejects_invalid_activation_and_completes_cleanly) {
  const clap_plugin_factory_t* factory = open_factory();
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_initialized(factory, host);
  M3_EXPECT_TRUE(factory->create_plugin(factory, host.host(), "wrong.id") == nullptr);
  M3_EXPECT_FALSE(plugin->activate(plugin, 0.0, 1, 128));
  M3_EXPECT_FALSE(plugin->activate(
      plugin, std::numeric_limits<double>::quiet_NaN(), 1, 128));
  M3_EXPECT_FALSE(plugin->activate(plugin, 48000.0, 0, 128));
  M3_EXPECT_FALSE(plugin->activate(plugin, 48000.0, 129, 128));
  M3_EXPECT_FALSE(plugin->activate(plugin, 48000.0, 1, 0));
  M3_EXPECT_FALSE(plugin->activate(plugin, 48000.0, 1, 16385));
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 16384));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));
  plugin->reset(plugin);
  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}

M3_TEST(clap_audio_note_ports_and_latency_are_fixed) {
  const clap_plugin_factory_t* factory = open_factory();
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_initialized(factory, host);
  const auto* audio_ports = static_cast<const clap_plugin_audio_ports_t*>(
      plugin->get_extension(plugin, CLAP_EXT_AUDIO_PORTS));
  const auto* note_ports = static_cast<const clap_plugin_note_ports_t*>(
      plugin->get_extension(plugin, CLAP_EXT_NOTE_PORTS));
  const auto* latency = static_cast<const clap_plugin_latency_t*>(
      plugin->get_extension(plugin, CLAP_EXT_LATENCY));
  M3_EXPECT_TRUE(audio_ports != nullptr);
  M3_EXPECT_TRUE(note_ports != nullptr);
  M3_EXPECT_TRUE(latency != nullptr);
  M3_EXPECT_EQ(audio_ports->count(plugin, true), 1U);
  M3_EXPECT_EQ(audio_ports->count(plugin, false), 1U);
  clap_audio_port_info_t audio_info{};
  M3_EXPECT_TRUE(audio_ports->get(plugin, 0, true, &audio_info));
  M3_EXPECT_EQ(audio_info.channel_count, 2U);
  M3_EXPECT_TRUE(std::strcmp(audio_info.port_type, CLAP_PORT_STEREO) == 0);
  M3_EXPECT_TRUE((audio_info.flags & CLAP_AUDIO_PORT_IS_MAIN) != 0U);
  M3_EXPECT_TRUE((audio_info.flags & CLAP_AUDIO_PORT_SUPPORTS_64BITS) != 0U);
  M3_EXPECT_FALSE(audio_ports->get(plugin, 1, true, &audio_info));
  for (const bool is_input : {true, false}) {
    clap_note_port_info_t note_info{};
    M3_EXPECT_EQ(note_ports->count(plugin, is_input), 1U);
    M3_EXPECT_TRUE(note_ports->get(plugin, 0, is_input, &note_info));
    M3_EXPECT_EQ(note_info.supported_dialects,
                 static_cast<std::uint32_t>(CLAP_NOTE_DIALECT_MIDI));
    M3_EXPECT_EQ(note_info.preferred_dialect,
                 static_cast<std::uint32_t>(CLAP_NOTE_DIALECT_MIDI));
  }
  M3_EXPECT_EQ(latency->get(plugin), 0U);
  plugin->destroy(plugin);
  clap_entry.deinit();
}

M3_TEST(clap_dry_path_is_bit_exact_mutable_and_allocation_free) {
  const clap_plugin_factory_t* factory = open_factory();
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_initialized(factory, host);
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 16384));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));
  expect_dry_modes_and_allocation_contract<float>(plugin);
  expect_dry_modes_and_allocation_contract<double>(plugin);
  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}

M3_TEST(clap_nonfinite_audio_fails_closed_and_partial_layout_stays_safe) {
  const clap_plugin_factory_t* factory = open_factory();
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_initialized(factory, host);
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 128));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));

  m3::test::FakeProcessBlock<double> block;
  block.configure(32, false);
  block.fill_finite();
  block.input_left()[3] = std::numeric_limits<double>::infinity();
  block.input_right()[7] = std::numeric_limits<double>::quiet_NaN();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(block.output_left()[3], 0.0);
  M3_EXPECT_EQ(block.output_right()[7], 0.0);
  M3_EXPECT_EQ(m3::adapter_status_for_test(plugin), m3::Status::invalid_input_or_state);

  plugin->reset(plugin);
  block.configure(32, false);
  block.fill_finite();
  block.input_buffer().channel_count = 1;
  block.output_buffer().channel_count = 1;
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
  }
  M3_EXPECT_EQ(m3::adapter_status_for_test(plugin), m3::Status::unsupported_layout);

  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}
