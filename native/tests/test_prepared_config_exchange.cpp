#include <clap/clap.h>
#include <clap/ext/params.h>
#include <clap/factory/plugin-factory.h>

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdio>
#include <cstdint>
#include <limits>
#include <thread>

#include "clap_adapter.hpp"
#include "fake_clap_host.hpp"
#include "prepared_config_exchange.hpp"
#include "test_support.hpp"

namespace {

constexpr std::uint64_t coherence_word(std::uint64_t generation,
                                       std::size_t index) noexcept {
  return (generation * 0x9E3779B97F4A7C15ULL) ^
         (static_cast<std::uint64_t>(index) * 0xD1B54A32D192ED03ULL);
}

m3::PersistentConfig config_for(std::uint64_t generation) noexcept {
  m3::PersistentConfig config;
  config.detector_input =
      static_cast<m3::DetectorInput>(generation % 3U);
  config.profile_mode = static_cast<m3::ProfileMode>(generation % 2U);
  config.a4_hz = 400.0 + static_cast<double>(generation % 801U) * 0.1;
  config.input_trim_db =
      -24.0 + static_cast<double>(generation % 481U) * 0.1;
  config.sensitivity = static_cast<std::uint8_t>(generation % 101U);
  config.response = static_cast<std::uint8_t>((generation * 3U) % 101U);
  config.lowest_note = static_cast<std::uint8_t>(24U + generation % 43U);
  config.highest_note = static_cast<std::uint8_t>(66U + generation % 43U);
  config.max_polyphony = static_cast<std::uint8_t>(1U + generation % 8U);
  config.max_fret = static_cast<std::uint8_t>(generation % 37U);
  config.velocity_mode = static_cast<m3::VelocityMode>(generation % 2U);
  config.fixed_velocity = static_cast<std::uint8_t>(1U + generation % 127U);
  config.midi_channel = static_cast<std::uint8_t>(1U + generation % 16U);
  config.dry_passthrough = (generation & 1U) != 0U;
  return config;
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

m3::PreparedConfig prepared_for(std::uint64_t generation) noexcept {
  m3::PreparedConfig prepared;
  prepared.requested = config_for(generation);
  prepared.sample_rate = 8000.0 + static_cast<double>(generation % 376001U);
#if defined(M3_TESTING)
  for (std::size_t index = 0; index < prepared.coherence_words.size(); ++index) {
    prepared.coherence_words[index] = coherence_word(generation, index);
  }
#endif
  return prepared;
}

bool coherent(const m3::PreparedConfig& prepared,
              std::uint64_t generation) noexcept {
  if (!same_config(prepared.requested, config_for(generation)) ||
      prepared.sample_rate !=
          8000.0 + static_cast<double>(generation % 376001U)) {
    return false;
  }
#if defined(M3_TESTING)
  for (std::size_t index = 0; index < prepared.coherence_words.size(); ++index) {
    if (prepared.coherence_words[index] != coherence_word(generation, index)) {
      return false;
    }
  }
#endif
  return true;
}

class ParamEvents final {
 public:
  ParamEvents() noexcept {
    list_.ctx = this;
    list_.size = &size;
    list_.get = &get;
  }

  bool push(clap_id id, double value) noexcept {
    if (count_ >= events_.size()) {
      return false;
    }
    clap_event_param_value_t& event = events_[count_++];
    event = {};
    event.header.size = sizeof(event);
    event.header.space_id = CLAP_CORE_EVENT_SPACE_ID;
    event.header.type = CLAP_EVENT_PARAM_VALUE;
    event.param_id = id;
    event.note_id = -1;
    event.port_index = -1;
    event.channel = -1;
    event.key = -1;
    event.value = value;
    return true;
  }

  const clap_input_events_t* list() const noexcept { return &list_; }

 private:
  static std::uint32_t CLAP_ABI size(const clap_input_events_t* list) noexcept {
    return static_cast<const ParamEvents*>(list->ctx)->count_;
  }
  static const clap_event_header_t* CLAP_ABI get(const clap_input_events_t* list,
                                                 std::uint32_t index) noexcept {
    const auto* self = static_cast<const ParamEvents*>(list->ctx);
    return index < self->count_ ? &self->events_[index].header : nullptr;
  }

  clap_input_events_t list_{};
  std::array<clap_event_param_value_t, 4> events_{};
  std::uint32_t count_{};
};

class MidiOutputs final {
 public:
  MidiOutputs() noexcept {
    list_.ctx = this;
    list_.try_push = &try_push;
  }

  void clear() noexcept { count_ = 0; }
  const clap_output_events_t* list() const noexcept { return &list_; }
  std::size_t size() const noexcept { return count_; }
  const clap_event_midi_t& operator[](std::size_t index) const noexcept {
    return events_[index];
  }

 private:
  static bool CLAP_ABI try_push(const clap_output_events_t* list,
                                const clap_event_header_t* header) noexcept {
    auto* self = static_cast<MidiOutputs*>(list->ctx);
    if (header == nullptr || header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
        header->type != CLAP_EVENT_MIDI ||
        header->size < sizeof(clap_event_midi_t) ||
        self->count_ >= self->events_.size()) {
      return false;
    }
    self->events_[self->count_++] =
        *reinterpret_cast<const clap_event_midi_t*>(header);
    return true;
  }

  clap_output_events_t list_{};
  std::array<clap_event_midi_t, 32> events_{};
  std::size_t count_{};
};

const clap_plugin_t* create_adapter(m3::test::FakeClapHost& host) noexcept {
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

M3_TEST(atomic_config_request_is_coherent_bounded_and_monotonic) {
  const m3::PersistentConfig initial = config_for(1);
  m3::AtomicConfigRequest request(initial, 1);
  m3::ConfigRequestSnapshot snapshot;
  M3_EXPECT_TRUE(request.snapshot(snapshot));
  M3_EXPECT_EQ(snapshot.generation, 1U);
  M3_EXPECT_TRUE(same_config(snapshot.config, initial));

  M3_EXPECT_TRUE(request.publish(config_for(2), 2));
  M3_EXPECT_FALSE(request.publish(config_for(1), 1));
  M3_EXPECT_TRUE(request.snapshot(snapshot));
  M3_EXPECT_EQ(snapshot.generation, 2U);
  M3_EXPECT_TRUE(same_config(snapshot.config, config_for(2)));

#if defined(M3_TESTING)
  M3_EXPECT_TRUE(request.hold_writer_for_test());
  M3_EXPECT_FALSE(request.snapshot(snapshot));
  request.release_writer_for_test();
  M3_EXPECT_TRUE(request.snapshot(snapshot));
#endif
}

M3_TEST(prepared_exchange_deterministic_interleavings_keep_owned_slots_safe) {
  m3::PreparedConfigExchange exchange;
  M3_EXPECT_TRUE(exchange.initialize(prepared_for(1), 1));
  M3_EXPECT_EQ(exchange.active_generation(), 1U);
  M3_EXPECT_TRUE(coherent(exchange.active(), 1));

  M3_EXPECT_TRUE(exchange.publish(prepared_for(2), 2));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(3), 3));
  m3::PreparedConfigExchange::Claim claim_three;
  M3_EXPECT_TRUE(exchange.claim_latest(claim_three));
  M3_EXPECT_EQ(claim_three.generation, 3U);
  M3_EXPECT_TRUE(coherent(*claim_three.config, 3));
  M3_EXPECT_EQ(exchange.active_generation(), 1U);
  M3_EXPECT_TRUE(coherent(exchange.active(), 1));

  M3_EXPECT_TRUE(exchange.publish(prepared_for(4), 4));
  M3_EXPECT_TRUE(coherent(*claim_three.config, 3));
  M3_EXPECT_TRUE(exchange.cancel(claim_three));
  m3::PreparedConfigExchange::Claim claim_four;
  M3_EXPECT_TRUE(exchange.claim_latest(claim_four));
  M3_EXPECT_EQ(claim_four.generation, 4U);
  M3_EXPECT_TRUE(exchange.commit(claim_four));
  M3_EXPECT_EQ(exchange.active_generation(), 4U);
  M3_EXPECT_TRUE(coherent(exchange.active(), 4));
  m3::PreparedConfigExchange::Claim stale;
  M3_EXPECT_FALSE(exchange.claim_latest(stale));
}

M3_TEST(prepared_exchange_reports_no_slot_without_overwriting_active_or_claimed) {
  m3::PreparedConfigExchange exchange;
  M3_EXPECT_TRUE(exchange.initialize(prepared_for(10), 10));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(11), 11));
  m3::PreparedConfigExchange::Claim first;
  M3_EXPECT_TRUE(exchange.claim_latest(first));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(12), 12));
  m3::PreparedConfigExchange::Claim second;
  M3_EXPECT_TRUE(exchange.claim_latest(second));
  M3_EXPECT_FALSE(exchange.publish(prepared_for(13), 13));
  M3_EXPECT_TRUE(coherent(exchange.active(), 10));
  M3_EXPECT_TRUE(coherent(*first.config, 11));
  M3_EXPECT_TRUE(coherent(*second.config, 12));
  M3_EXPECT_TRUE(exchange.cancel(second));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(13), 13));
  M3_EXPECT_TRUE(exchange.cancel(first));
  m3::PreparedConfigExchange::Claim latest;
  M3_EXPECT_TRUE(exchange.claim_latest(latest));
  M3_EXPECT_EQ(latest.generation, 13U);
  M3_EXPECT_TRUE(exchange.commit(latest));
}

M3_TEST(config_generation_comparison_is_wrap_safe) {
  const std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max();
  M3_EXPECT_TRUE(m3::generation_newer(maximum, maximum - 1U));
  M3_EXPECT_TRUE(m3::generation_newer(0, maximum));
  M3_EXPECT_FALSE(m3::generation_newer(maximum, 0));
  M3_EXPECT_FALSE(m3::generation_newer(7, 7));

  m3::PreparedConfigExchange exchange;
  M3_EXPECT_TRUE(exchange.initialize(prepared_for(maximum - 1U), maximum - 1U));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(maximum), maximum));
  M3_EXPECT_TRUE(exchange.publish(prepared_for(0), 0));
  m3::PreparedConfigExchange::Claim claim;
  M3_EXPECT_TRUE(exchange.claim_latest(claim));
  M3_EXPECT_EQ(claim.generation, 0U);
  M3_EXPECT_TRUE(exchange.commit(claim));
  M3_EXPECT_EQ(exchange.active_generation(), 0U);
}

M3_TEST(config_exchange_concurrent_100000_generation_stress_is_coherent) {
  constexpr std::uint64_t kFinalGeneration = 100000;
  m3::AtomicConfigRequest request(config_for(1), 1);
  std::atomic<bool> request_done{false};
  std::atomic<bool> request_ok{true};
  std::thread request_publisher([&]() noexcept {
    for (std::uint64_t generation = 2; generation <= kFinalGeneration;
         ++generation) {
      if (!request.publish(config_for(generation), generation)) {
        request_ok.store(false, std::memory_order_relaxed);
        break;
      }
    }
    request_done.store(true, std::memory_order_release);
  });
  std::uint64_t last_snapshot = 1;
  while (!request_done.load(std::memory_order_acquire)) {
    m3::ConfigRequestSnapshot snapshot;
    if (request.snapshot(snapshot)) {
      if (!same_config(snapshot.config, config_for(snapshot.generation)) ||
          (snapshot.generation != last_snapshot &&
           !m3::generation_newer(snapshot.generation, last_snapshot))) {
        request_ok.store(false, std::memory_order_relaxed);
      }
      last_snapshot = snapshot.generation;
    }
  }
  request_publisher.join();
  m3::ConfigRequestSnapshot final_snapshot;
  M3_EXPECT_TRUE(request.snapshot(final_snapshot));
  M3_EXPECT_TRUE(request_ok.load(std::memory_order_relaxed));
  M3_EXPECT_EQ(final_snapshot.generation, kFinalGeneration);
  M3_EXPECT_TRUE(same_config(final_snapshot.config,
                             config_for(kFinalGeneration)));

  m3::PreparedConfigExchange exchange;
  M3_EXPECT_TRUE(exchange.initialize(prepared_for(1), 1));
  std::atomic<bool> exchange_done{false};
  std::atomic<bool> exchange_ok{true};
  std::atomic<std::uint32_t> exchange_failure{0};
  std::atomic<std::uint64_t> exchange_failure_generation{0};
  std::thread prepared_publisher([&]() noexcept {
    for (std::uint64_t generation = 2; generation <= kFinalGeneration;
         ++generation) {
      bool published = false;
      for (std::uint32_t attempt = 0; attempt < 10000U && !published; ++attempt) {
        published = exchange.publish(prepared_for(generation), generation);
        if (!published) {
          std::this_thread::yield();
        }
      }
      if (!published) {
        exchange_ok.store(false, std::memory_order_relaxed);
        std::uint32_t expected = 0;
        if (exchange_failure.compare_exchange_strong(
                expected, 1, std::memory_order_relaxed)) {
          exchange_failure_generation.store(generation,
                                            std::memory_order_relaxed);
        }
        break;
      }
    }
    exchange_done.store(true, std::memory_order_release);
  });
  std::uint64_t last_adopted = 1;
  do {
    m3::PreparedConfigExchange::Claim claim;
    if (exchange.claim_latest(claim)) {
      const bool claim_coherent = coherent(*claim.config, claim.generation);
      const bool claim_newer =
          m3::generation_newer(claim.generation, last_adopted);
      const bool claim_committed =
          claim_coherent && claim_newer && exchange.commit(claim);
      if (!claim_committed) {
        exchange_ok.store(false, std::memory_order_relaxed);
        std::uint32_t expected = 0;
        if (exchange_failure.compare_exchange_strong(
                expected, claim_coherent ? (claim_newer ? 4U : 3U) : 2U,
                std::memory_order_relaxed)) {
          exchange_failure_generation.store(claim.generation,
                                            std::memory_order_relaxed);
        }
        static_cast<void>(exchange.cancel(claim));
      } else {
        last_adopted = exchange.active_generation();
      }
    } else if (!exchange_done.load(std::memory_order_acquire)) {
      std::this_thread::yield();
    }
  } while (!exchange_done.load(std::memory_order_acquire));
  for (;;) {
    m3::PreparedConfigExchange::Claim claim;
    if (!exchange.claim_latest(claim)) {
      break;
    }
    if (!coherent(*claim.config, claim.generation) ||
        !m3::generation_newer(claim.generation, last_adopted) ||
        !exchange.commit(claim)) {
      exchange_ok.store(false, std::memory_order_relaxed);
      std::uint32_t expected = 0;
      if (exchange_failure.compare_exchange_strong(
              expected, 3, std::memory_order_relaxed)) {
        exchange_failure_generation.store(claim.generation,
                                          std::memory_order_relaxed);
      }
      static_cast<void>(exchange.cancel(claim));
      break;
    }
    last_adopted = exchange.active_generation();
  }
  prepared_publisher.join();
  if (exchange_failure.load(std::memory_order_relaxed) != 0U) {
    std::fprintf(stderr, "exchange failure %u at generation %llu\n",
                 exchange_failure.load(std::memory_order_relaxed),
                 static_cast<unsigned long long>(
                     exchange_failure_generation.load(std::memory_order_relaxed)));
  }
  M3_EXPECT_TRUE(exchange_ok.load(std::memory_order_relaxed));
  M3_EXPECT_EQ(exchange.active_generation(), kFinalGeneration);
  M3_EXPECT_TRUE(coherent(exchange.active(), kFinalGeneration));
}

M3_TEST(adapter_reconfiguration_releases_old_channel_and_runtime_is_immediate) {
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_adapter(host);
  const auto* params = static_cast<const clap_plugin_params_t*>(
      plugin->get_extension(plugin, CLAP_EXT_PARAMS));
  M3_EXPECT_TRUE(params != nullptr);
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 128));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));

  m3::test::FakeProcessBlock<float> block;
  MidiOutputs output;
  block.configure(32, false);
  block.fill_finite();
  block.set_output_events(output.list());
  M3_EXPECT_TRUE(m3::queue_transition_for_test(
      plugin, m3::VoiceTransition{0, m3::TransitionKind::note_on, 60, 100, 1},
      32));
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(output.size(), 1U);
  M3_EXPECT_EQ(output[0].data[0], 0x90U);

  ParamEvents structural;
  M3_EXPECT_TRUE(structural.push(0x4D33000DU, 2.0));
  block.configure(32, false);
  block.fill_finite();
  block.set_input_events(structural.list());
  block.set_output_events(output.list());
  output.clear();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(m3::adapter_status_for_test(plugin), m3::Status::reconfiguring);
  M3_EXPECT_TRUE(host.callback_requests() > 0U);
  double channel = 0.0;
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D33000DU, &channel));
  M3_EXPECT_NEAR(channel, 1.0, 0.0);

  plugin->on_main_thread(plugin);
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D33000DU, &channel));
  M3_EXPECT_NEAR(channel, 2.0, 0.0);
  block.configure(32, false);
  block.fill_finite();
  block.set_output_events(output.list());
  output.clear();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(output.size(), 1U);
  M3_EXPECT_EQ(output[0].data[0], 0x80U);
  M3_EXPECT_EQ(output[0].data[1], 60U);
  M3_EXPECT_EQ(m3::adapter_status_for_test(plugin), m3::Status::panic_hold);

  block.configure(32, false);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    block.input_left()[frame] = 0.0F;
    block.input_right()[frame] = 0.0F;
  }
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_TRUE(m3::queue_transition_for_test(
      plugin, m3::VoiceTransition{0, m3::TransitionKind::note_on, 62, 100, 2},
      32));
  block.configure(32, false);
  block.fill_finite();
  block.set_output_events(output.list());
  output.clear();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(output.size(), 1U);
  M3_EXPECT_EQ(output[0].data[0], 0x91U);

  ParamEvents runtime;
  M3_EXPECT_TRUE(runtime.push(0x4D33000FU, 0.0));
  block.configure(32, false);
  block.fill_finite();
  block.set_input_events(runtime.list());
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], 0.0F);
    M3_EXPECT_EQ(block.output_right()[frame], 0.0F);
  }

  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}
