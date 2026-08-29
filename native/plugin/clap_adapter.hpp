#pragma once

#include <clap/clap.h>

#include "m3/types.hpp"

namespace m3 {

const clap_plugin_descriptor_t* selected_descriptor() noexcept;
const clap_plugin_t* create_adapter(const clap_host_t* host) noexcept;

#if defined(M3_TESTING)
const clap_plugin_descriptor_t* probe_descriptor_for_test() noexcept;
void set_dry_passthrough_for_test(const clap_plugin_t* plugin, bool enabled) noexcept;
Status adapter_status_for_test(const clap_plugin_t* plugin) noexcept;
bool queue_transition_for_test(const clap_plugin_t* plugin,
                               const VoiceTransition& transition,
                               std::uint32_t frames_count) noexcept;
#endif

}  // namespace m3
