#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"

namespace m3 {

// Tuner data is intentionally separate from persistent parameters and MIDI
// delivery. It describes detector evidence only, so the editor never implies
// that an observed voice was necessarily delivered to a host event sink.
enum class TunerFrameState : std::uint8_t {
  unavailable,
  no_signal,
  tracking,
};

enum class TunerVoiceState : std::uint8_t {
  settling,
  tracking,
};

inline constexpr std::uint8_t kUnassignedTunerString = 0xFFU;

struct TunerVoice final {
  std::uint8_t midi_note{};
  std::int16_t cents_q8{};
  std::uint16_t confidence_q15{};
  std::uint16_t age_ticks{};
  TunerVoiceState state{TunerVoiceState::settling};
  bool cents_valid{};
  // Zero-based physical M3 string/lane identity. General mode and legacy
  // producers leave this unassigned. Keeping identity in the evidence frame
  // prevents the editor from reordering a sustained string when spectral
  // rank changes.
  std::uint8_t string_index{kUnassignedTunerString};
};

struct TunerSnapshot final {
  std::uint32_t generation{};
  TunerFrameState state{TunerFrameState::unavailable};
  std::uint8_t voice_count{};
  std::uint8_t max_polyphony{1U};
  std::array<TunerVoice, kMaxVoices> voices{};
};

// Single audio-thread writer / UI-thread reader transport. All shared words
// participate in one sequentially consistent odd/even sequence: a reader only
// accepts payload between equal even sequence values. This prevents a UI frame
// from combining detector ticks on every supported CPU without a lock, a wait,
// or an audio-thread allocation. Tuner data remains separate from host
// parameter automation.
class TunerTelemetry final {
 public:
  TunerTelemetry() noexcept = default;
  TunerTelemetry(const TunerTelemetry&) = delete;
  TunerTelemetry& operator=(const TunerTelemetry&) = delete;

  void publish(const TunerSnapshot& snapshot) noexcept;
  void clear(TunerFrameState state = TunerFrameState::unavailable) noexcept;
 [[nodiscard]] bool read_latest(TunerSnapshot& snapshot) const noexcept;

 private:
  static constexpr std::size_t kReadAttempts = 3U;

  std::atomic<std::uint32_t> sequence_{};
  std::atomic<std::uint32_t> generation_{};
  std::atomic<std::uint32_t> header_{};
  std::array<std::atomic<std::uint32_t>, kMaxVoices> voice_words_a_{};
  std::array<std::atomic<std::uint32_t>, kMaxVoices> voice_words_b_{};
};

}  // namespace m3
