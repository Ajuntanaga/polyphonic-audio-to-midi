#include "clap_adapter.hpp"

#include <clap/ext/audio-ports.h>
#include <clap/ext/latency.h>
#include <clap/ext/note-ports.h>
#include <clap/ext/params.h>
#include <clap/ext/state.h>

#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>

#include "dry_path.hpp"
#include "clap_parameter_bridge.hpp"
#include "m3/constants.hpp"
#include "m3/parameter_contract.hpp"
#include "midi_pipeline.hpp"
#include "prepared_config_exchange.hpp"
#include "state_codec.hpp"
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
#include "probe_processor.hpp"
#endif

namespace {

constexpr const char* kFeatures[] = {
    CLAP_PLUGIN_FEATURE_AUDIO_EFFECT,
    CLAP_PLUGIN_FEATURE_NOTE_EFFECT,
    CLAP_PLUGIN_FEATURE_NOTE_DETECTOR,
    CLAP_PLUGIN_FEATURE_STEREO,
    nullptr,
};

constexpr clap_plugin_descriptor_t kProductionDescriptor{
    CLAP_VERSION,
    "com.ajuntanaga.m3-polyphonic-audio-to-midi",
    "M3 Polyphonic Audio to MIDI",
    "ajuntanaga",
    "",
    "",
    "",
    "0.1.0",
    "Real-time polyphonic audio-to-MIDI effect",
    kFeatures,
};

#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
constexpr clap_plugin_descriptor_t kProbeDescriptor{
    CLAP_VERSION,
    "com.ajuntanaga.m3-polyphonic-audio-to-midi.probe",
    "M3 Polyphonic Audio to MIDI Probe",
    "ajuntanaga",
    "",
    "",
    "",
    "0.1.0",
    "Disposable CLAP capability probe",
    kFeatures,
};
#endif

enum class Lifecycle : std::uint8_t { created, initialized, active, processing };

struct Adapter final {
  explicit Adapter(const clap_host_t* host_pointer) noexcept
      : host(host_pointer), config_request(main_config, 1) {
    plugin.desc = m3::selected_descriptor();
    plugin.plugin_data = this;
    plugin.init = &plugin_init;
    plugin.destroy = &plugin_destroy;
    plugin.activate = &plugin_activate;
    plugin.deactivate = &plugin_deactivate;
    plugin.start_processing = &plugin_start_processing;
    plugin.stop_processing = &plugin_stop_processing;
    plugin.reset = &plugin_reset;
    plugin.process = &plugin_process;
    plugin.get_extension = &plugin_get_extension;
    plugin.on_main_thread = &plugin_on_main_thread;
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
    probe_processor.record_create();
#endif
  }

  static Adapter* from(const clap_plugin_t* plugin_pointer) noexcept {
    if (plugin_pointer == nullptr) {
      return nullptr;
    }
    return static_cast<Adapter*>(plugin_pointer->plugin_data);
  }

  static bool CLAP_ABI plugin_init(const clap_plugin_t* plugin_pointer) noexcept;
  static void CLAP_ABI plugin_destroy(const clap_plugin_t* plugin_pointer) noexcept;
  static bool CLAP_ABI plugin_activate(const clap_plugin_t* plugin_pointer,
                                       double sample_rate,
                                       std::uint32_t min_frames,
                                       std::uint32_t max_frames) noexcept;
  static void CLAP_ABI plugin_deactivate(const clap_plugin_t* plugin_pointer) noexcept;
  static bool CLAP_ABI plugin_start_processing(
      const clap_plugin_t* plugin_pointer) noexcept;
  static void CLAP_ABI plugin_stop_processing(
      const clap_plugin_t* plugin_pointer) noexcept;
  static void CLAP_ABI plugin_reset(const clap_plugin_t* plugin_pointer) noexcept;
  static clap_process_status CLAP_ABI plugin_process(
      const clap_plugin_t* plugin_pointer, const clap_process_t* process) noexcept;
  static const void* CLAP_ABI plugin_get_extension(
      const clap_plugin_t* plugin_pointer, const char* id) noexcept;
  static void CLAP_ABI plugin_on_main_thread(
      const clap_plugin_t* plugin_pointer) noexcept;

  clap_plugin_t plugin{};
  const clap_host_t* host{};
  Lifecycle lifecycle{Lifecycle::created};
  std::atomic<m3::Status> status{m3::Status::ready};
  std::atomic<bool> values_dirty{false};
  const clap_host_params_t* host_params{};
  m3::PersistentConfig main_config{};
  m3::AtomicConfigRequest config_request;
  std::atomic<std::uint64_t> generation_counter{1};
  std::atomic<std::uint64_t> requested_structural_generation{1};
  std::atomic<bool> reconfiguration_pending{false};
  std::uint64_t main_generation{1};
  m3::PersistentConfig audio_requested_config{};
  std::uint64_t audio_request_generation{1};
  m3::PersistentConfig active_config{};
  m3::PreparedConfigExchange prepared_exchange{};
  m3::PreparedConfig pending_prepared{};
  std::uint64_t pending_prepared_generation{};
  bool prepared_publication_pending{};
  bool audio_publication_pending{};
  bool pending_audio_structural{};
  m3::MidiPipeline midi_pipeline{};
  std::uint8_t release_midi_channel{1};
  bool release_channel_pending{};
  double sample_rate{};
  std::uint32_t min_frames{};
  std::uint32_t max_frames{};
  std::atomic<bool> panic_requested{false};
  std::atomic<std::uint32_t> panic_offset{0};
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  m3::ProbeProcessor probe_processor{};
#endif
#if defined(M3_TESTING)
  m3::VoiceTransition test_transition{};
  std::uint32_t test_transition_frames{};
  bool test_transition_pending{};
#endif
};

void copy_name(char* destination, std::size_t capacity, const char* source) noexcept {
  if (capacity == 0) {
    return;
  }
  std::size_t index = 0;
  while (index + 1 < capacity && source[index] != '\0') {
    destination[index] = source[index];
    ++index;
  }
  destination[index] = '\0';
}

std::uint32_t CLAP_ABI audio_port_count(const clap_plugin_t*, bool) noexcept {
  return 1;
}

bool CLAP_ABI audio_port_get(const clap_plugin_t*, std::uint32_t index,
                             bool is_input,
                             clap_audio_port_info_t* info) noexcept {
  if (index != 0 || info == nullptr) {
    return false;
  }
  *info = {};
  info->id = 0;
  copy_name(info->name, sizeof(info->name), is_input ? "Stereo Input" : "Stereo Output");
  info->flags = CLAP_AUDIO_PORT_IS_MAIN | CLAP_AUDIO_PORT_SUPPORTS_64BITS |
                CLAP_AUDIO_PORT_REQUIRES_COMMON_SAMPLE_SIZE;
  info->channel_count = 2;
  info->port_type = CLAP_PORT_STEREO;
  info->in_place_pair = 0;
  return true;
}

std::uint32_t CLAP_ABI note_port_count(const clap_plugin_t*, bool) noexcept {
  return 1;
}

bool CLAP_ABI note_port_get(const clap_plugin_t*, std::uint32_t index,
                            bool is_input,
                            clap_note_port_info_t* info) noexcept {
  if (index != 0 || info == nullptr) {
    return false;
  }
  *info = {};
  info->id = 0;
  info->supported_dialects = CLAP_NOTE_DIALECT_MIDI;
  info->preferred_dialect = CLAP_NOTE_DIALECT_MIDI;
  copy_name(info->name, sizeof(info->name), is_input ? "MIDI Input" : "MIDI Output");
  return true;
}

std::uint32_t CLAP_ABI latency_get(const clap_plugin_t*) noexcept { return 0; }

const clap_plugin_audio_ports_t kAudioPorts{&audio_port_count, &audio_port_get};
const clap_plugin_note_ports_t kNotePorts{&note_port_count, &note_port_get};
const clap_plugin_latency_t kLatency{&latency_get};

void mark_values_dirty(Adapter& adapter) noexcept {
  if (!adapter.values_dirty.exchange(true, std::memory_order_acq_rel) &&
      adapter.host != nullptr && adapter.host->request_callback != nullptr) {
    adapter.host->request_callback(adapter.host);
  }
}

void latch_status(Adapter& adapter, m3::Status status) noexcept {
  m3::Status current = adapter.status.load(std::memory_order_relaxed);
  while (static_cast<std::uint8_t>(status) > static_cast<std::uint8_t>(current)) {
    if (adapter.status.compare_exchange_weak(current, status,
                                             std::memory_order_release,
                                             std::memory_order_relaxed)) {
      mark_values_dirty(adapter);
      return;
    }
  }
}

void publish_runtime_status(Adapter& adapter,
                            const m3::MidiProcessResult& midi) noexcept {
  const m3::Status current = adapter.status.load(std::memory_order_acquire);
  if (current == m3::Status::invalid_input_or_state ||
      current == m3::Status::unsupported_layout) {
    return;
  }
  const m3::Status target =
      midi.output_blocked
          ? m3::Status::midi_output_blocked
          : (adapter.reconfiguration_pending.load(std::memory_order_acquire)
                 ? m3::Status::reconfiguring
                 : (midi.panic_hold ? m3::Status::panic_hold
                                    : m3::Status::ready));
  if (adapter.status.exchange(target, std::memory_order_acq_rel) != target) {
    mark_values_dirty(adapter);
  }
}

struct ParameterBatchResult final {
  bool changed{};
  bool structural{};
  bool panic{};
  std::uint32_t panic_offset{};
};

std::uint64_t next_generation(Adapter& adapter) noexcept {
  return adapter.generation_counter.fetch_add(1, std::memory_order_relaxed) + 1U;
}

ParameterBatchResult apply_parameter_events_to(
    m3::PersistentConfig& config, const clap_input_events_t* input,
    std::uint32_t frames_count) noexcept {
  ParameterBatchResult batch;
  if (input == nullptr || input->size == nullptr || input->get == nullptr) {
    return batch;
  }
  const std::uint32_t count = input->size(input);
  for (std::uint32_t index = 0; index < count; ++index) {
    const clap_event_header_t* header = input->get(input, index);
    if (header == nullptr || header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
        header->type != CLAP_EVENT_PARAM_VALUE ||
        header->size < sizeof(clap_event_param_value_t)) {
      continue;
    }
    const auto* event = reinterpret_cast<const clap_event_param_value_t*>(header);
    if (event->note_id != -1 || event->port_index != -1 || event->channel != -1 ||
        event->key != -1) {
      continue;
    }
    const m3::ParameterApplyResult result =
        m3::apply_parameter(config, event->param_id, event->value);
    if (result == m3::ParameterApplyResult::panic) {
      batch.panic = true;
      batch.panic_offset =
          frames_count == 0 ? 0 : std::min(header->time, frames_count - 1U);
    } else if (result == m3::ParameterApplyResult::changed) {
      batch.changed = true;
      const m3::ParameterSpec* record =
          m3::find_parameter(event->param_id);
      batch.structural =
          batch.structural ||
          (record != nullptr &&
           record->update_class == m3::ParameterUpdateClass::structural);
    }
  }
  return batch;
}

void accept_panic(Adapter& adapter,
                  const ParameterBatchResult& batch) noexcept {
  if (batch.panic) {
    adapter.panic_offset.store(batch.panic_offset, std::memory_order_relaxed);
    adapter.panic_requested.store(true, std::memory_order_release);
    mark_values_dirty(adapter);
  }
}

bool publish_audio_config(Adapter& adapter, bool structural) noexcept {
  const std::uint64_t generation = next_generation(adapter);
  if (!adapter.config_request.publish(adapter.audio_requested_config,
                                      generation)) {
    adapter.audio_publication_pending = true;
    adapter.pending_audio_structural =
        adapter.pending_audio_structural || structural;
    return false;
  }
  adapter.audio_request_generation = generation;
  adapter.audio_publication_pending = false;
  if (structural || adapter.pending_audio_structural) {
    adapter.requested_structural_generation.store(generation,
                                                  std::memory_order_release);
    adapter.reconfiguration_pending.store(true, std::memory_order_release);
    adapter.pending_audio_structural = false;
    latch_status(adapter, m3::Status::reconfiguring);
  }
  mark_values_dirty(adapter);
  return true;
}

void synchronize_audio_request(Adapter& adapter) noexcept {
  if (adapter.audio_publication_pending) {
    static_cast<void>(publish_audio_config(adapter,
                                           adapter.pending_audio_structural));
    if (adapter.audio_publication_pending) {
      return;
    }
  }
  m3::ConfigRequestSnapshot snapshot;
  if (adapter.config_request.snapshot(snapshot) &&
      m3::generation_newer(snapshot.generation,
                           adapter.audio_request_generation)) {
    adapter.audio_requested_config = snapshot.config;
    adapter.audio_request_generation = snapshot.generation;
  }
}

void apply_audio_parameter_events(Adapter& adapter,
                                  const clap_input_events_t* input,
                                  std::uint32_t frames_count) noexcept {
  const ParameterBatchResult batch = apply_parameter_events_to(
      adapter.audio_requested_config, input, frames_count);
  accept_panic(adapter, batch);
  if (batch.changed) {
    static_cast<void>(publish_audio_config(adapter, batch.structural));
  }
}

void apply_inactive_parameter_events(Adapter& adapter,
                                     const clap_input_events_t* input) noexcept {
  m3::PersistentConfig candidate = adapter.main_config;
  const ParameterBatchResult batch =
      apply_parameter_events_to(candidate, input, 0);
  accept_panic(adapter, batch);
  if (!batch.changed) {
    return;
  }
  const std::uint64_t generation = next_generation(adapter);
  if (!adapter.config_request.publish(candidate, generation)) {
    latch_status(adapter, m3::Status::invalid_input_or_state);
    return;
  }
  adapter.main_config = candidate;
  adapter.main_generation = generation;
}

bool stage_for_publication(Adapter& adapter,
                           const m3::PersistentConfig& config,
                           std::uint64_t generation) noexcept {
  if (!m3::stage_prepared_config(config, adapter.sample_rate,
                                 adapter.pending_prepared)) {
    latch_status(adapter, m3::Status::invalid_input_or_state);
    return false;
  }
  adapter.pending_prepared_generation = generation;
  adapter.prepared_publication_pending = true;
  if (adapter.prepared_exchange.publish(adapter.pending_prepared, generation)) {
    adapter.prepared_publication_pending = false;
    return true;
  }
  return false;
}

std::uint32_t CLAP_ABI params_count(const clap_plugin_t*) noexcept {
  return static_cast<std::uint32_t>(m3::kParameterCount);
}

bool CLAP_ABI params_get_info(const clap_plugin_t*, std::uint32_t index,
                              clap_param_info_t* info) noexcept {
  return info != nullptr && m3::clap_parameter_info(index, *info);
}

bool CLAP_ABI params_get_value(const clap_plugin_t* plugin, clap_id id,
                               double* value) noexcept {
  const Adapter* adapter = Adapter::from(plugin);
  return adapter != nullptr && value != nullptr &&
         m3::parameter_value(adapter->main_config,
                             adapter->status.load(std::memory_order_acquire), id,
                             *value);
}

bool CLAP_ABI params_value_to_text(const clap_plugin_t*, clap_id id, double value,
                                   char* output,
                                   std::uint32_t capacity) noexcept {
  return m3::parameter_value_to_text(id, value, output, capacity);
}

bool CLAP_ABI params_text_to_value(const clap_plugin_t*, clap_id id,
                                   const char* text, double* value) noexcept {
  return value != nullptr && m3::parameter_text_to_value(id, text, *value);
}

void CLAP_ABI params_flush(const clap_plugin_t* plugin,
                           const clap_input_events_t* input,
                           const clap_output_events_t*) noexcept {
  Adapter* adapter = Adapter::from(plugin);
  if (adapter != nullptr) {
    if (adapter->lifecycle == Lifecycle::active ||
        adapter->lifecycle == Lifecycle::processing) {
      synchronize_audio_request(*adapter);
      apply_audio_parameter_events(*adapter, input, 0);
    } else {
      apply_inactive_parameter_events(*adapter, input);
    }
  }
}

bool CLAP_ABI state_save(const clap_plugin_t* plugin,
                         const clap_ostream_t* stream) noexcept {
  const Adapter* adapter = Adapter::from(plugin);
  return adapter != nullptr && m3::save_state(adapter->main_config, stream);
}

bool CLAP_ABI state_load(const clap_plugin_t* plugin,
                         const clap_istream_t* stream) noexcept {
  Adapter* adapter = Adapter::from(plugin);
  if (adapter == nullptr) {
    return false;
  }
  m3::PersistentConfig candidate;
  if (!m3::load_state(stream, candidate)) {
    return false;
  }
  bool published = false;
  std::uint64_t generation = 0;
  for (std::uint32_t attempt = 0; attempt < 3U && !published; ++attempt) {
    generation = next_generation(*adapter);
    published = adapter->config_request.publish(candidate, generation);
  }
  if (!published) {
    return false;
  }
  adapter->main_config = candidate;
  adapter->main_generation = generation;
  adapter->panic_requested.store(false, std::memory_order_release);
  if (adapter->lifecycle == Lifecycle::active ||
      adapter->lifecycle == Lifecycle::processing) {
    adapter->requested_structural_generation.store(
        generation, std::memory_order_release);
    adapter->reconfiguration_pending.store(true, std::memory_order_release);
    static_cast<void>(stage_for_publication(*adapter, candidate, generation));
    latch_status(*adapter, m3::Status::reconfiguring);
    if (adapter->prepared_publication_pending) {
      mark_values_dirty(*adapter);
    }
  } else {
    adapter->status.store(m3::Status::ready, std::memory_order_release);
  }
  if (adapter->host_params != nullptr && adapter->host_params->rescan != nullptr) {
    adapter->host_params->rescan(adapter->host, CLAP_PARAM_RESCAN_VALUES);
  }
  return true;
}

const clap_plugin_params_t kParams{
    &params_count,
    &params_get_info,
    &params_get_value,
    &params_value_to_text,
    &params_text_to_value,
    &params_flush,
};
const clap_plugin_state_t kState{&state_save, &state_load};

template <typename Sample>
m3::DryPathResult process_typed(const clap_audio_buffer_t& input,
                                clap_audio_buffer_t& output,
                                std::uint32_t frames,
                                bool passthrough,
                                m3::DetectorInput detector_input) noexcept {
  if constexpr (sizeof(Sample) == sizeof(float)) {
    return m3::process_dry_path(input.data32, input.channel_count, output.data32,
                                output.channel_count, frames, passthrough,
                                detector_input);
  } else {
    return m3::process_dry_path(input.data64, input.channel_count, output.data64,
                                output.channel_count, frames, passthrough,
                                detector_input);
  }
}

bool exact_float32_layout(const clap_audio_buffer_t& input,
                          const clap_audio_buffer_t& output) noexcept {
  return input.data32 != nullptr && input.data64 == nullptr &&
         output.data32 != nullptr && output.data64 == nullptr;
}

bool exact_float64_layout(const clap_audio_buffer_t& input,
                          const clap_audio_buffer_t& output) noexcept {
  return input.data64 != nullptr && input.data32 == nullptr &&
         output.data64 != nullptr && output.data32 == nullptr;
}

bool Adapter::plugin_init(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr || self->lifecycle != Lifecycle::created) {
    return false;
  }
  if (self->host->get_extension != nullptr) {
    self->host_params = static_cast<const clap_host_params_t*>(
        self->host->get_extension(self->host, CLAP_EXT_PARAMS));
  }
  self->lifecycle = Lifecycle::initialized;
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  self->probe_processor.record_init();
#endif
  return true;
}

void Adapter::plugin_destroy(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  if (self != nullptr) {
    self->probe_processor.record_destroy();
    static_cast<void>(self->probe_processor.write_report());
  }
#endif
  delete self;
}

bool Adapter::plugin_activate(const clap_plugin_t* plugin_pointer,
                              double requested_sample_rate,
                              std::uint32_t requested_min_frames,
                              std::uint32_t requested_max_frames) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr || self->lifecycle != Lifecycle::initialized ||
      !std::isfinite(requested_sample_rate) || requested_sample_rate <= 0.0 ||
      requested_min_frames == 0 || requested_max_frames == 0 ||
      requested_min_frames > requested_max_frames ||
      requested_max_frames > m3::kMaxHostFrames) {
    return false;
  }
  m3::ConfigRequestSnapshot snapshot;
  m3::PreparedConfig prepared;
  if (!self->config_request.snapshot(snapshot) ||
      !m3::stage_prepared_config(snapshot.config, requested_sample_rate,
                                 prepared)) {
    return false;
  }
  if (!self->midi_pipeline.activate(requested_max_frames)) {
    return false;
  }
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  if (!self->probe_processor.record_activate()) {
    self->midi_pipeline.deactivate();
    return false;
  }
#endif
  self->sample_rate = requested_sample_rate;
  self->min_frames = requested_min_frames;
  self->max_frames = requested_max_frames;
  self->main_config = snapshot.config;
  self->main_generation = snapshot.generation;
  self->audio_requested_config = snapshot.config;
  self->audio_request_generation = snapshot.generation;
  self->active_config = snapshot.config;
  static_cast<void>(self->prepared_exchange.initialize(prepared,
                                                       snapshot.generation));
  self->requested_structural_generation.store(snapshot.generation,
                                              std::memory_order_release);
  self->reconfiguration_pending.store(false, std::memory_order_release);
  self->prepared_publication_pending = false;
  self->audio_publication_pending = false;
  self->pending_audio_structural = false;
  self->release_midi_channel = snapshot.config.midi_channel;
  self->release_channel_pending = false;
  self->status.store(m3::Status::ready, std::memory_order_release);
  self->lifecycle = Lifecycle::active;
  return true;
}

void Adapter::plugin_deactivate(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr && self->lifecycle == Lifecycle::active) {
    m3::ConfigRequestSnapshot snapshot;
    if (self->config_request.snapshot(snapshot) &&
        m3::generation_newer(snapshot.generation, self->main_generation)) {
      self->main_config = snapshot.config;
      self->main_generation = snapshot.generation;
    }
    self->lifecycle = Lifecycle::initialized;
    self->sample_rate = 0.0;
    self->min_frames = 0;
    self->max_frames = 0;
    self->midi_pipeline.deactivate();
    self->prepared_exchange.reset();
    self->prepared_publication_pending = false;
    self->audio_publication_pending = false;
    self->pending_audio_structural = false;
    self->release_channel_pending = false;
    self->reconfiguration_pending.store(false, std::memory_order_release);
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
    self->probe_processor.record_deactivate();
#endif
  }
}

bool Adapter::plugin_start_processing(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr || self->lifecycle != Lifecycle::active) {
    return false;
  }
  self->lifecycle = Lifecycle::processing;
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  self->probe_processor.record_start();
#endif
  return true;
}

void Adapter::plugin_stop_processing(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr && self->lifecycle == Lifecycle::processing) {
    self->lifecycle = Lifecycle::active;
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
    self->probe_processor.record_stop();
#endif
  }
}

void Adapter::plugin_reset(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr &&
      (self->lifecycle == Lifecycle::active ||
       self->lifecycle == Lifecycle::processing)) {
    self->midi_pipeline.request_reset();
    latch_status(*self, m3::Status::panic_hold);
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
    self->probe_processor.record_reset();
#endif
  }
}

clap_process_status Adapter::plugin_process(const clap_plugin_t* plugin_pointer,
                                            const clap_process_t* process) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr || self->lifecycle != Lifecycle::processing ||
      process == nullptr || process->frames_count == 0 ||
      process->frames_count > self->max_frames) {
    return CLAP_PROCESS_ERROR;
  }

  self->midi_pipeline.begin_block();
#if defined(M3_PROBE_BUILD) || defined(M3_TESTING)
  self->probe_processor.record_process(*process);
  if (!self->probe_processor.queue_trigger_transitions(
          self->midi_pipeline, process->in_events, process->frames_count)) {
    latch_status(*self, m3::Status::invalid_input_or_state);
  }
#endif
  synchronize_audio_request(*self);

  if (!self->release_channel_pending) {
    m3::PreparedConfigExchange::Claim claim;
    if (self->prepared_exchange.claim_latest(claim)) {
      const m3::PersistentConfig adopted = claim.config->requested;
      const std::uint64_t adopted_generation = claim.generation;
      self->release_midi_channel = self->active_config.midi_channel;
      self->midi_pipeline.request_reset();
      self->release_channel_pending = true;
      if (self->prepared_exchange.commit(claim)) {
        m3::copy_structural_config(self->active_config, adopted);
        const std::uint64_t requested_generation =
            self->requested_structural_generation.load(
                std::memory_order_acquire);
        if (!m3::generation_newer(requested_generation,
                                  adopted_generation)) {
          self->reconfiguration_pending.store(false,
                                              std::memory_order_release);
        }
      } else {
        static_cast<void>(self->prepared_exchange.cancel(claim));
        self->release_channel_pending = false;
        latch_status(*self, m3::Status::invalid_input_or_state);
      }
    }
  }

  apply_audio_parameter_events(*self, process->in_events,
                               process->frames_count);
  if (self->panic_requested.exchange(false, std::memory_order_acq_rel)) {
    static_cast<void>(self->midi_pipeline.request_panic(
        self->panic_offset.load(std::memory_order_relaxed),
        process->frames_count));
  }
#if defined(M3_TESTING)
  if (self->test_transition_pending) {
    static_cast<void>(self->midi_pipeline.queue_transition(
        self->test_transition, self->test_transition_frames));
    self->test_transition_pending = false;
  }
#endif

  m3::DryPathResult result{};
  bool float32 = false;
  bool float64 = false;
  bool exact_layout = false;
  if (process->audio_inputs != nullptr && process->audio_outputs != nullptr &&
      process->audio_inputs_count > 0 && process->audio_outputs_count > 0) {
    const clap_audio_buffer_t& input = process->audio_inputs[0];
    clap_audio_buffer_t& output = process->audio_outputs[0];
    float32 = exact_float32_layout(input, output);
    float64 = exact_float64_layout(input, output);
    if (float32) {
      result = process_typed<float>(input, output, process->frames_count,
                                    self->audio_requested_config.dry_passthrough,
                                    self->active_config.detector_input);
    } else if (float64) {
      result = process_typed<double>(input, output, process->frames_count,
                                     self->audio_requested_config.dry_passthrough,
                                     self->active_config.detector_input);
    }
    exact_layout = process->audio_inputs_count == 1 &&
                   process->audio_outputs_count == 1 &&
                   input.channel_count == 2 && output.channel_count == 2 &&
                   result.channels_processed == 2 && (float32 || float64);
  }

  if (!exact_layout) {
    latch_status(*self, m3::Status::unsupported_layout);
  } else if (result.nonfinite_input) {
    latch_status(*self, m3::Status::invalid_input_or_state);
  }
  const std::uint8_t midi_channel = self->release_channel_pending
                                        ? self->release_midi_channel
                                        : self->active_config.midi_channel;
  const m3::MidiProcessResult midi = self->midi_pipeline.process(
      process->frames_count, midi_channel, process->in_events,
      process->out_events, result.selected_peak, !result.nonfinite_input,
      exact_layout);
  if (self->release_channel_pending &&
      !self->midi_pipeline.cleanup_pending()) {
    self->release_channel_pending = false;
  }
  if (midi.invalid_event) {
    latch_status(*self, m3::Status::invalid_input_or_state);
  }
  publish_runtime_status(*self, midi);
  return CLAP_PROCESS_CONTINUE;
}

const void* Adapter::plugin_get_extension(const clap_plugin_t* plugin_pointer,
                                          const char* id) noexcept {
  if (from(plugin_pointer) == nullptr || id == nullptr) {
    return nullptr;
  }
  if (std::strcmp(id, CLAP_EXT_AUDIO_PORTS) == 0) {
    return &kAudioPorts;
  }
  if (std::strcmp(id, CLAP_EXT_NOTE_PORTS) == 0) {
    return &kNotePorts;
  }
  if (std::strcmp(id, CLAP_EXT_LATENCY) == 0) {
    return &kLatency;
  }
  if (std::strcmp(id, CLAP_EXT_PARAMS) == 0) {
    return &kParams;
  }
  if (std::strcmp(id, CLAP_EXT_STATE) == 0) {
    return &kState;
  }
  return nullptr;
}

void Adapter::plugin_on_main_thread(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr) {
    return;
  }

  const bool values_were_dirty =
      self->values_dirty.exchange(false, std::memory_order_acq_rel);
  bool retry_callback = false;
  m3::ConfigRequestSnapshot snapshot;
  if (!self->config_request.snapshot(snapshot)) {
    retry_callback = true;
  } else if (m3::generation_newer(snapshot.generation,
                                  self->main_generation)) {
    const bool structural =
        !m3::structural_config_equal(self->main_config, snapshot.config);
    self->main_config = snapshot.config;
    self->main_generation = snapshot.generation;
    if (structural &&
        (self->lifecycle == Lifecycle::active ||
         self->lifecycle == Lifecycle::processing)) {
      self->requested_structural_generation.store(
          snapshot.generation, std::memory_order_release);
      self->reconfiguration_pending.store(true, std::memory_order_release);
      latch_status(*self, m3::Status::reconfiguring);
      if (!stage_for_publication(*self, snapshot.config,
                                 snapshot.generation)) {
        retry_callback = self->prepared_publication_pending;
      }
    }
  }

  if (self->prepared_publication_pending) {
    if (self->prepared_exchange.publish(self->pending_prepared,
                                        self->pending_prepared_generation)) {
      self->prepared_publication_pending = false;
    } else {
      retry_callback = true;
    }
  }

  if (values_were_dirty && self->host_params != nullptr &&
      self->host_params->rescan != nullptr) {
    self->host_params->rescan(self->host, CLAP_PARAM_RESCAN_VALUES);
  }
  if (retry_callback) {
    mark_values_dirty(*self);
  }
}

}  // namespace

namespace m3 {

const clap_plugin_descriptor_t* selected_descriptor() noexcept {
#if defined(M3_PROBE_BUILD)
  return &kProbeDescriptor;
#else
  return &kProductionDescriptor;
#endif
}

const clap_plugin_t* create_adapter(const clap_host_t* host) noexcept {
  if (host == nullptr || !clap_version_is_compatible(host->clap_version) ||
      host->name == nullptr || host->version == nullptr) {
    return nullptr;
  }
  Adapter* adapter = new (std::nothrow) Adapter(host);
  return adapter == nullptr ? nullptr : &adapter->plugin;
}

#if defined(M3_TESTING)
const clap_plugin_descriptor_t* probe_descriptor_for_test() noexcept {
  return &kProbeDescriptor;
}

void set_dry_passthrough_for_test(const clap_plugin_t* plugin, bool enabled) noexcept {
  Adapter* adapter = Adapter::from(plugin);
  if (adapter != nullptr) {
    adapter->audio_requested_config.dry_passthrough = enabled;
  }
}

Status adapter_status_for_test(const clap_plugin_t* plugin) noexcept {
  const Adapter* adapter = Adapter::from(plugin);
  return adapter == nullptr
             ? Status::invalid_input_or_state
             : adapter->status.load(std::memory_order_acquire);
}

bool queue_transition_for_test(const clap_plugin_t* plugin,
                               const VoiceTransition& transition,
                               std::uint32_t frames_count) noexcept {
  Adapter* adapter = Adapter::from(plugin);
  if (adapter == nullptr || adapter->test_transition_pending) {
    return false;
  }
  adapter->test_transition = transition;
  adapter->test_transition_frames = frames_count;
  adapter->test_transition_pending = true;
  return true;
}
#endif

}  // namespace m3
