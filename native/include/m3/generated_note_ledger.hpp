#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

#include "m3/types.hpp"

namespace m3 {

struct NoteEventSink final {
  void* context{};
  bool (*push)(void*, const VoiceTransition&, std::uint8_t) noexcept = nullptr;
};

struct NoteDeliveryResult final {
  bool output_blocked{};
  bool panic_hold{};
  bool detection_allowed{};
};

class GeneratedNoteLedger final {
 public:
  GeneratedNoteLedger() noexcept = default;
  GeneratedNoteLedger(const GeneratedNoteLedger&) = delete;
  GeneratedNoteLedger& operator=(const GeneratedNoteLedger&) = delete;

  bool activate(std::uint32_t max_frames) noexcept;
  bool activate_preserving_pending(std::uint32_t max_frames) noexcept;
  void deactivate() noexcept;
  void release_storage_preserving_pending() noexcept;
  void begin_block() noexcept;
  bool queue_transition(const VoiceTransition& transition,
                        std::uint32_t frames) noexcept;
  bool queue_active_releases(std::uint32_t sample_offset,
                             std::uint32_t frames) noexcept;
  void request_release_all() noexcept;
  void report_output_failure() noexcept;
  void request_recovery() noexcept;
  bool retry_pending_releases(NoteEventSink sink) noexcept;
  NoteDeliveryResult deliver_queued(std::uint32_t frames, NoteEventSink sink,
                                    double selected_peak, bool finite_input,
                                    bool supported_layout,
                                    MidiRouting routing = MidiRouting::single,
                                    std::uint8_t start_channel = 1U) noexcept;
  NoteDeliveryResult deliver(std::uint32_t frames, NoteEventSink sink,
                             double selected_peak, bool finite_input,
                             bool supported_layout,
                             MidiRouting routing = MidiRouting::single,
                             std::uint8_t start_channel = 1U) noexcept;
  [[nodiscard]] bool is_active(std::uint8_t note) const noexcept;
  [[nodiscard]] bool is_pending_release(std::uint8_t note) const noexcept;
  [[nodiscard]] bool release_pending() const noexcept;
  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] bool output_blocked() const noexcept { return output_blocked_; }
  [[nodiscard]] bool panic_hold() const noexcept { return panic_hold_; }

 private:
  static bool transition_before(const VoiceTransition& left,
                                const VoiceTransition& right) noexcept;
  struct ActiveVoice final {
    bool active{};
    bool pending_release{};
    std::uint8_t note{};
    std::uint8_t channel{};
    std::uint8_t voice_id{kUnassignedVoiceId};
  };
  [[nodiscard]] std::size_t find_voice(
      const VoiceTransition& transition) const noexcept;
  [[nodiscard]] std::size_t find_free_voice() const noexcept;
  static bool push(NoteEventSink sink,
                   const VoiceTransition& transition,
                   std::uint8_t one_based_channel) noexcept;
  [[nodiscard]] std::uint8_t allocate_channel(
      MidiRouting routing, std::uint8_t start_channel,
      const VoiceTransition& transition) const noexcept;
  void enter_blocked() noexcept;
  void finish_hold(double selected_peak, bool finite_input,
                   bool supported_layout) noexcept;
  bool allocate_storage(std::uint32_t max_frames) noexcept;

  std::unique_ptr<VoiceTransition[]> storage_{};
  std::size_t capacity_{};
  std::size_t size_{};
  std::uint32_t max_frames_{};
  std::array<ActiveVoice, kMaxVoices> voices_{};
  std::uint8_t active_count_{};
  bool invalid_transition_{};
  bool output_blocked_{};
  bool cleanup_complete_{};
  bool panic_hold_{};
  bool recovery_requested_{};
  std::uint8_t hold_calls_remaining_{};
};

}  // namespace m3
