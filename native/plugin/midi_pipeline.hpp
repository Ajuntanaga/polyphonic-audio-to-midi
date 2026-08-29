#pragma once

#include <clap/events.h>

#include <cstddef>
#include <cstdint>

#include "m3/generated_note_ledger.hpp"

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

  [[nodiscard]] std::size_t capacity() const noexcept {
    return ledger_.capacity();
  }
  [[nodiscard]] bool is_active(std::uint8_t note) const noexcept;
  [[nodiscard]] bool is_pending_release(std::uint8_t note) const noexcept;
  [[nodiscard]] bool cleanup_pending() const noexcept {
    return channel_panic_required_ || ledger_.release_pending();
  }

 private:
  struct DeliveryContext;
  static bool push_generated(void* context,
                             const VoiceTransition& transition) noexcept;
  bool push_midi(const clap_output_events_t* output, std::uint32_t offset,
                 std::uint8_t status, std::uint8_t data1,
                 std::uint8_t data2) noexcept;
  bool push_input(const clap_output_events_t* output,
                  const clap_event_header_t* event) noexcept;
  bool flush_inputs(DeliveryContext& context, std::uint32_t boundary,
                    bool inclusive, bool final_flush) noexcept;
  void enter_output_blocked() noexcept;
  bool retry_channel_panics(const clap_output_events_t* output,
                            std::uint8_t channel) noexcept;

  GeneratedNoteLedger ledger_{};
  bool invalid_event_{};
  bool channel_panic_required_{};
};

}  // namespace m3
