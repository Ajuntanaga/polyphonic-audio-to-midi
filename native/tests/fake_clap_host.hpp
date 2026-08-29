#pragma once

#include <array>
#include <cstdint>
#include <type_traits>

#include <clap/clap.h>
#include <clap/ext/params.h>

#include "m3/constants.hpp"

namespace m3::test {

class FakeClapHost final {
 public:
  FakeClapHost() noexcept;

  const clap_host_t* host() const noexcept { return &host_; }
  std::uint32_t restart_requests() const noexcept { return restart_requests_; }
  std::uint32_t process_requests() const noexcept { return process_requests_; }
  std::uint32_t callback_requests() const noexcept { return callback_requests_; }
  std::uint32_t param_rescans() const noexcept { return param_rescans_; }
  clap_param_rescan_flags param_rescan_flags() const noexcept {
    return param_rescan_flags_;
  }
  std::uint32_t flush_requests() const noexcept { return flush_requests_; }

  static const clap_input_events_t* empty_input_events() noexcept;
  static const clap_output_events_t* accepting_output_events() noexcept;

 private:
  static const void* CLAP_ABI get_extension(const clap_host_t*, const char*) noexcept;
  static void CLAP_ABI request_restart(const clap_host_t*) noexcept;
  static void CLAP_ABI request_process(const clap_host_t*) noexcept;
  static void CLAP_ABI request_callback(const clap_host_t*) noexcept;
  static void CLAP_ABI params_rescan(const clap_host_t*,
                                     clap_param_rescan_flags) noexcept;
  static void CLAP_ABI params_clear(const clap_host_t*, clap_id,
                                    clap_param_clear_flags) noexcept;
  static void CLAP_ABI params_request_flush(const clap_host_t*) noexcept;

  clap_host_t host_{};
  std::uint32_t restart_requests_{};
  std::uint32_t process_requests_{};
  std::uint32_t callback_requests_{};
  std::uint32_t param_rescans_{};
  clap_param_rescan_flags param_rescan_flags_{};
  std::uint32_t flush_requests_{};
};

template <typename Sample>
class FakeProcessBlock final {
 public:
  FakeProcessBlock() noexcept { configure(1, false); }

  void configure(std::uint32_t frames, bool alias) noexcept {
    frames_ = frames;
    input_channels_[0] = input_left_.data();
    input_channels_[1] = input_right_.data();
    output_channels_[0] = alias ? input_left_.data() : output_left_.data();
    output_channels_[1] = alias ? input_right_.data() : output_right_.data();

    input_buffer_ = {};
    output_buffer_ = {};
    if constexpr (std::is_same_v<Sample, float>) {
      input_buffer_.data32 = input_channels_.data();
      output_buffer_.data32 = output_channels_.data();
    } else {
      static_assert(std::is_same_v<Sample, double>);
      input_buffer_.data64 = input_channels_.data();
      output_buffer_.data64 = output_channels_.data();
    }
    input_buffer_.channel_count = 2;
    output_buffer_.channel_count = 2;

    process_ = {};
    process_.steady_time = -1;
    process_.frames_count = frames;
    process_.audio_inputs = &input_buffer_;
    process_.audio_outputs = &output_buffer_;
    process_.audio_inputs_count = 1;
    process_.audio_outputs_count = 1;
    process_.in_events = FakeClapHost::empty_input_events();
    process_.out_events = FakeClapHost::accepting_output_events();
  }

  void fill_finite() noexcept {
    for (std::uint32_t frame = 0; frame < frames_; ++frame) {
      const double phase = static_cast<double>(frame % 17U) * 0.03125;
      input_left_[frame] = static_cast<Sample>(phase - 0.25);
      input_right_[frame] = static_cast<Sample>(0.5 - phase);
      output_left_[frame] = static_cast<Sample>(9.0);
      output_right_[frame] = static_cast<Sample>(-9.0);
    }
  }

  clap_process_t* process() noexcept { return &process_; }
  clap_audio_buffer_t& input_buffer() noexcept { return input_buffer_; }
  clap_audio_buffer_t& output_buffer() noexcept { return output_buffer_; }
  Sample* input_left() noexcept { return input_left_.data(); }
  Sample* input_right() noexcept { return input_right_.data(); }
  Sample* output_left() noexcept { return output_channels_[0]; }
  Sample* output_right() noexcept { return output_channels_[1]; }

 private:
  std::uint32_t frames_{};
  std::array<Sample, kMaxHostFrames> input_left_{};
  std::array<Sample, kMaxHostFrames> input_right_{};
  std::array<Sample, kMaxHostFrames> output_left_{};
  std::array<Sample, kMaxHostFrames> output_right_{};
  std::array<Sample*, 2> input_channels_{};
  std::array<Sample*, 2> output_channels_{};
  clap_audio_buffer_t input_buffer_{};
  clap_audio_buffer_t output_buffer_{};
  clap_process_t process_{};
};

}  // namespace m3::test
