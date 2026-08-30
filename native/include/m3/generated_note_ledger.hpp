#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

#include "m3/types.hpp"

namespace m3 {

struct NoteEventSink final {
  void* context{};
  bool (*push)(void*, const VoiceTransition&) noexcept = nullptr;
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
  void request_release_all() noexcept;
  void report_output_failure() noexcept;
  void request_recovery() noexcept;
  bool retry_pending_releases(NoteEventSink sink) noexcept;
  NoteDeliveryResult deliver_queued(std::uint32_t frames, NoteEventSink sink,
                                    double selected_peak, bool finite_input,
                                    bool supported_layout) noexcept;
  NoteDeliveryResult deliver(std::uint32_t frames, NoteEventSink sink,
                             double selected_peak, bool finite_input,
                             bool supported_layout) noexcept;
  [[nodiscard]] bool is_active(std::uint8_t note) const noexcept;
  [[nodiscard]] bool is_pending_release(std::uint8_t note) const noexcept;
  [[nodiscard]] bool release_pending() const noexcept {
    return pending_release_[0] != 0U || pending_release_[1] != 0U;
  }
  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] bool output_blocked() const noexcept { return output_blocked_; }
  [[nodiscard]] bool panic_hold() const noexcept { return panic_hold_; }

 private:
  static bool transition_before(const VoiceTransition& left,
                                const VoiceTransition& right) noexcept;
  static bool bit(const std::array<std::uint64_t, 2>& bits,
                  std::uint8_t note) noexcept;
  static void set_bit(std::array<std::uint64_t, 2>& bits,
                      std::uint8_t note) noexcept;
  static void clear_bit(std::array<std::uint64_t, 2>& bits,
                        std::uint8_t note) noexcept;
  static bool push(NoteEventSink sink,
                   const VoiceTransition& transition) noexcept;
  void enter_blocked() noexcept;
  void finish_hold(double selected_peak, bool finite_input,
                   bool supported_layout) noexcept;
  bool allocate_storage(std::uint32_t max_frames) noexcept;

  std::unique_ptr<VoiceTransition[]> storage_{};
  std::size_t capacity_{};
  std::size_t size_{};
  std::uint32_t max_frames_{};
  std::array<std::uint64_t, 2> active_{};
  std::array<std::uint64_t, 2> pending_release_{};
  bool invalid_transition_{};
  bool output_blocked_{};
  bool cleanup_complete_{};
  bool panic_hold_{};
  bool recovery_requested_{};
  std::uint8_t hold_calls_remaining_{};
};

}  // namespace m3
