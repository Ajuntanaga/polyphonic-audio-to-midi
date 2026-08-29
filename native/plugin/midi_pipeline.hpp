#pragma once

#include <clap/events.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

#include "m3/types.hpp"

namespace m3 {

struct MidiProcessResult final {
  bool invalid_event{};
  bool output_blocked{};
  bool panic_hold{};
  bool detection_allowed{};
};

class MidiPipeline final {
 public:
  MidiPipeline() noexcept = default;
  MidiPipeline(const MidiPipeline&) = delete;
  MidiPipeline& operator=(const MidiPipeline&) = delete;

  bool activate(std::uint32_t max_frames) noexcept;
  void deactivate() noexcept;
  void begin_block() noexcept;
  bool queue_transition(const VoiceTransition& transition,
                        std::uint32_t frames_count) noexcept;
  bool request_panic(std::uint32_t offset,
                     std::uint32_t frames_count) noexcept;
  void request_reset() noexcept;
  MidiProcessResult process(std::uint32_t frames_count,
                            std::uint8_t one_based_channel,
                            const clap_input_events_t* input,
                            const clap_output_events_t* output,
                            double selected_input_peak,
                            bool finite_input,
                            bool supported_layout) noexcept;

  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] bool is_active(std::uint8_t note) const noexcept;
  [[nodiscard]] bool is_pending_release(std::uint8_t note) const noexcept;

 private:
  static bool transition_before(const VoiceTransition& left,
                                const VoiceTransition& right) noexcept;
  static bool bit(const std::array<std::uint64_t, 2>& bits,
                  std::uint8_t note) noexcept;
  static void set_bit(std::array<std::uint64_t, 2>& bits,
                      std::uint8_t note) noexcept;
  static void clear_bit(std::array<std::uint64_t, 2>& bits,
                        std::uint8_t note) noexcept;
  bool push_midi(const clap_output_events_t* output, std::uint32_t offset,
                 std::uint8_t status, std::uint8_t data1,
                 std::uint8_t data2) noexcept;
  bool push_input(const clap_output_events_t* output,
                  const clap_event_header_t* event) noexcept;
  void enter_blocked() noexcept;
  bool retry_cleanup(const clap_output_events_t* output,
                     std::uint8_t channel) noexcept;
  void finish_hold(double selected_input_peak, bool finite_input,
                   bool supported_layout) noexcept;

  std::unique_ptr<VoiceTransition[]> storage_{};
  std::size_t capacity_{};
  std::size_t size_{};
  std::uint32_t max_frames_{};
  std::array<std::uint64_t, 2> active_{};
  std::array<std::uint64_t, 2> pending_release_{};
  bool invalid_event_{};
  bool blocked_{};
  bool cleanup_requested_{};
  bool channel_panic_required_{};
  bool cleanup_complete_{};
  bool panic_hold_{};
  bool explicit_recovery_{};
  std::uint8_t hold_calls_remaining_{};
};

}  // namespace m3
