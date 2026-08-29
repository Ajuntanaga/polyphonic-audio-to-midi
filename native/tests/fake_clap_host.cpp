#include "fake_clap_host.hpp"

#include <cstddef>
#include <cstring>

namespace {

std::uint32_t CLAP_ABI empty_size(const clap_input_events_t*) noexcept { return 0; }

const clap_event_header_t* CLAP_ABI empty_get(const clap_input_events_t*,
                                              std::uint32_t) noexcept {
  return nullptr;
}

bool CLAP_ABI accept_event(const clap_output_events_t*,
                           const clap_event_header_t*) noexcept {
  return true;
}

const clap_input_events_t kEmptyInputEvents{nullptr, &empty_size, &empty_get};
const clap_output_events_t kAcceptingOutputEvents{nullptr, &accept_event};

}  // namespace

namespace m3::test {

FakeClapHost::FakeClapHost() noexcept {
  host_.clap_version = CLAP_VERSION;
  host_.host_data = this;
  host_.name = "M3 Native Test Host";
  host_.vendor = "ajuntanaga";
  host_.url = "https://example.invalid/m3-test-host";
  host_.version = "1";
  host_.get_extension = &get_extension;
  host_.request_restart = &request_restart;
  host_.request_process = &request_process;
  host_.request_callback = &request_callback;
}

const clap_input_events_t* FakeClapHost::empty_input_events() noexcept {
  return &kEmptyInputEvents;
}

const clap_output_events_t* FakeClapHost::accepting_output_events() noexcept {
  return &kAcceptingOutputEvents;
}

const void* CLAP_ABI FakeClapHost::get_extension(const clap_host_t*,
                                                 const char* id) noexcept {
  if (id != nullptr && std::strcmp(id, CLAP_EXT_PARAMS) == 0) {
    static const clap_host_params_t kHostParams{
        &params_rescan,
        &params_clear,
        &params_request_flush,
    };
    return &kHostParams;
  }
  return nullptr;
}

void CLAP_ABI FakeClapHost::request_restart(const clap_host_t* host) noexcept {
  auto* self = static_cast<FakeClapHost*>(host->host_data);
  ++self->restart_requests_;
}

void CLAP_ABI FakeClapHost::request_process(const clap_host_t* host) noexcept {
  auto* self = static_cast<FakeClapHost*>(host->host_data);
  ++self->process_requests_;
}

void CLAP_ABI FakeClapHost::request_callback(const clap_host_t* host) noexcept {
  auto* self = static_cast<FakeClapHost*>(host->host_data);
  ++self->callback_requests_;
}

void CLAP_ABI FakeClapHost::params_rescan(
    const clap_host_t* host, clap_param_rescan_flags flags) noexcept {
  auto* self = static_cast<FakeClapHost*>(host->host_data);
  ++self->param_rescans_;
  self->param_rescan_flags_ |= flags;
}

void CLAP_ABI FakeClapHost::params_clear(const clap_host_t*, clap_id,
                                         clap_param_clear_flags) noexcept {}

void CLAP_ABI FakeClapHost::params_request_flush(const clap_host_t* host) noexcept {
  auto* self = static_cast<FakeClapHost*>(host->host_data);
  ++self->flush_requests_;
}

}  // namespace m3::test
