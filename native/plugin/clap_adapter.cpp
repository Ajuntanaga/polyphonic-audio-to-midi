#include "clap_adapter.hpp"

#include <clap/ext/audio-ports.h>
#include <clap/ext/latency.h>
#include <clap/ext/note-ports.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>

#include "dry_path.hpp"
#include "m3/constants.hpp"

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
  explicit Adapter(const clap_host_t* host_pointer) noexcept : host(host_pointer) {
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
  m3::Status status{m3::Status::ready};
  double sample_rate{};
  std::uint32_t min_frames{};
  std::uint32_t max_frames{};
  bool dry_passthrough{true};
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

void latch_status(Adapter& adapter, m3::Status status) noexcept {
  if (static_cast<std::uint8_t>(status) >
      static_cast<std::uint8_t>(adapter.status)) {
    adapter.status = status;
  }
}

template <typename Sample>
m3::DryPathResult process_typed(const clap_audio_buffer_t& input,
                                clap_audio_buffer_t& output,
                                std::uint32_t frames,
                                bool passthrough) noexcept {
  if constexpr (sizeof(Sample) == sizeof(float)) {
    return m3::process_dry_path(input.data32, input.channel_count, output.data32,
                                output.channel_count, frames, passthrough);
  } else {
    return m3::process_dry_path(input.data64, input.channel_count, output.data64,
                                output.channel_count, frames, passthrough);
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
  self->lifecycle = Lifecycle::initialized;
  return true;
}

void Adapter::plugin_destroy(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
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
  self->sample_rate = requested_sample_rate;
  self->min_frames = requested_min_frames;
  self->max_frames = requested_max_frames;
  self->status = m3::Status::ready;
  self->lifecycle = Lifecycle::active;
  return true;
}

void Adapter::plugin_deactivate(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr && self->lifecycle == Lifecycle::active) {
    self->lifecycle = Lifecycle::initialized;
    self->sample_rate = 0.0;
    self->min_frames = 0;
    self->max_frames = 0;
  }
}

bool Adapter::plugin_start_processing(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self == nullptr || self->lifecycle != Lifecycle::active) {
    return false;
  }
  self->lifecycle = Lifecycle::processing;
  return true;
}

void Adapter::plugin_stop_processing(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr && self->lifecycle == Lifecycle::processing) {
    self->lifecycle = Lifecycle::active;
  }
}

void Adapter::plugin_reset(const clap_plugin_t* plugin_pointer) noexcept {
  Adapter* self = from(plugin_pointer);
  if (self != nullptr &&
      (self->lifecycle == Lifecycle::active ||
       self->lifecycle == Lifecycle::processing)) {
    self->status = m3::Status::ready;
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

  if (process->audio_inputs == nullptr || process->audio_outputs == nullptr ||
      process->audio_inputs_count == 0 || process->audio_outputs_count == 0) {
    latch_status(*self, m3::Status::unsupported_layout);
    return CLAP_PROCESS_CONTINUE;
  }

  const clap_audio_buffer_t& input = process->audio_inputs[0];
  clap_audio_buffer_t& output = process->audio_outputs[0];
  const bool float32 = exact_float32_layout(input, output);
  const bool float64 = exact_float64_layout(input, output);
  m3::DryPathResult result{};
  if (float32) {
    result = process_typed<float>(input, output, process->frames_count,
                                  self->dry_passthrough);
  } else if (float64) {
    result = process_typed<double>(input, output, process->frames_count,
                                   self->dry_passthrough);
  }

  const bool exact_layout =
      process->audio_inputs_count == 1 && process->audio_outputs_count == 1 &&
      input.channel_count == 2 && output.channel_count == 2 &&
      result.channels_processed == 2 && (float32 || float64);
  if (!exact_layout) {
    latch_status(*self, m3::Status::unsupported_layout);
  } else if (result.nonfinite_input) {
    latch_status(*self, m3::Status::invalid_input_or_state);
  }
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
  return nullptr;
}

void Adapter::plugin_on_main_thread(const clap_plugin_t*) noexcept {}

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
    adapter->dry_passthrough = enabled;
  }
}

Status adapter_status_for_test(const clap_plugin_t* plugin) noexcept {
  const Adapter* adapter = Adapter::from(plugin);
  return adapter == nullptr ? Status::invalid_input_or_state : adapter->status;
}
#endif

}  // namespace m3
