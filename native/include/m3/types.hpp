#pragma once

#include <cstdint>

#include "m3/constants.hpp"
#include "m3/fixed_vector.hpp"

namespace m3 {

enum class MidiRouting : std::uint8_t { single, per_voice };
enum class ProfileMode : std::uint8_t { m3, general };
enum class VelocityMode : std::uint8_t { fixed, dynamic };
enum class Status : std::uint8_t {
  ready,
  panic_hold,
  reconfiguring,
  midi_output_blocked,
  invalid_input_or_state,
  unsupported_layout,
};
enum class TransitionKind : std::uint8_t { note_off, note_on };

inline constexpr std::uint8_t kTunerNoSignalNote = 128U;

struct TunerEstimate final {
  bool updated{};
  bool signal{};
  std::uint8_t note{kTunerNoSignalNote};
  double cents{};
};

struct PersistentConfig final {
  MidiRouting midi_routing{MidiRouting::single};
  ProfileMode profile_mode{ProfileMode::m3};
  double a4_hz{440.0};
  double input_trim_db{0.0};
  std::uint8_t sensitivity{50};
  std::uint8_t response{25};
  std::uint8_t lowest_note{32};
  std::uint8_t highest_note{84};
  std::uint8_t max_polyphony{8};
  std::uint8_t max_fret{24};
  VelocityMode velocity_mode{VelocityMode::dynamic};
  std::uint8_t fixed_velocity{100};
  std::uint8_t midi_channel{1};
  bool dry_passthrough{true};
};

struct VoiceTransition final {
  std::uint32_t sample_offset{};
  TransitionKind kind{};
  std::uint8_t note{};
  std::uint8_t velocity{};
  std::uint32_t sequence{};
};

using TickTransitions = FixedVector<VoiceTransition, kMaxTickTransitions>;

enum class PrepareError : std::uint8_t {
  none,
  invalid_sample_rate,
  invalid_config,
  unsafe_frame_count,
};

}  // namespace m3
