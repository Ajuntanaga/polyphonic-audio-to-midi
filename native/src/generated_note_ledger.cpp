#include "m3/generated_note_ledger.hpp"

#include <cmath>
#include <limits>
#include <new>
#include <utility>

#include "m3/constants.hpp"

namespace {

constexpr double kQuietPeak = 0.0001;

}  // namespace

namespace m3 {

bool GeneratedNoteLedger::activate(std::uint32_t max_frames) noexcept {
  deactivate();
  return allocate_storage(max_frames);
}

bool GeneratedNoteLedger::activate_preserving_pending(
    std::uint32_t max_frames) noexcept {
  storage_.reset();
  capacity_ = 0;
  size_ = 0;
  max_frames_ = 0;
  invalid_transition_ = false;
  return allocate_storage(max_frames);
}

bool GeneratedNoteLedger::allocate_storage(std::uint32_t max_frames) noexcept {
  if (max_frames == 0 || max_frames > kMaxHostFrames) {
    return false;
  }
  const std::size_t ticks =
      (static_cast<std::size_t>(max_frames) + kDecisionQuantum - 1U) /
      kDecisionQuantum;
  if (ticks > (std::numeric_limits<std::size_t>::max() - kMaxVoices) /
                  kMaxTickTransitions) {
    return false;
  }
  const std::size_t requested_capacity =
      ticks * kMaxTickTransitions + kMaxVoices;
  std::unique_ptr<VoiceTransition[]> storage{
      new (std::nothrow) VoiceTransition[requested_capacity]};
  if (!storage) {
    return false;
  }
  storage_ = std::move(storage);
  capacity_ = requested_capacity;
  max_frames_ = max_frames;
  return true;
}

void GeneratedNoteLedger::release_storage_preserving_pending() noexcept {
  request_release_all();
  storage_.reset();
  capacity_ = 0;
  size_ = 0;
  max_frames_ = 0;
  invalid_transition_ = false;
}

void GeneratedNoteLedger::deactivate() noexcept {
  storage_.reset();
  capacity_ = 0;
  size_ = 0;
  max_frames_ = 0;
  active_ = {};
  pending_release_ = {};
  note_channels_ = {};
  active_count_ = 0U;
  invalid_transition_ = false;
  output_blocked_ = false;
  cleanup_complete_ = false;
  panic_hold_ = false;
  recovery_requested_ = false;
  hold_calls_remaining_ = 0;
}

void GeneratedNoteLedger::begin_block() noexcept {
  size_ = 0;
  invalid_transition_ = false;
}

bool GeneratedNoteLedger::transition_before(
    const VoiceTransition& left, const VoiceTransition& right) noexcept {
  if (left.sample_offset != right.sample_offset) {
    return left.sample_offset < right.sample_offset;
  }
  if (left.kind != right.kind) {
    return left.kind == TransitionKind::note_off;
  }
  return left.sequence < right.sequence;
}

bool GeneratedNoteLedger::queue_transition(
    const VoiceTransition& transition, std::uint32_t frames) noexcept {
  const bool note_off = transition.kind == TransitionKind::note_off;
  const bool note_on = transition.kind == TransitionKind::note_on;
  const bool valid_velocity =
      (note_off && transition.velocity == 0U) ||
      (note_on && transition.velocity > 0U && transition.velocity <= 127U);
  if (!storage_ || size_ >= capacity_ || frames == 0 || frames > max_frames_ ||
      transition.sample_offset >= frames || (!note_off && !note_on) ||
      transition.note > 127U || !valid_velocity) {
    invalid_transition_ = true;
    return false;
  }
  std::size_t position = size_;
  while (position > 0 &&
         transition_before(transition, storage_[position - 1U])) {
    storage_[position] = storage_[position - 1U];
    --position;
  }
  storage_[position] = transition;
  ++size_;
  return true;
}

bool GeneratedNoteLedger::bit(const std::array<std::uint64_t, 2>& bits,
                              std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  return (bits[word] & (std::uint64_t{1} << shift)) != 0U;
}

void GeneratedNoteLedger::set_bit(std::array<std::uint64_t, 2>& bits,
                                  std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  bits[word] |= std::uint64_t{1} << shift;
}

void GeneratedNoteLedger::clear_bit(std::array<std::uint64_t, 2>& bits,
                                    std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  bits[word] &= ~(std::uint64_t{1} << shift);
}

bool GeneratedNoteLedger::is_active(std::uint8_t note) const noexcept {
  return note <= 127U && bit(active_, note);
}

bool GeneratedNoteLedger::is_pending_release(
    std::uint8_t note) const noexcept {
  return note <= 127U && bit(pending_release_, note);
}

bool GeneratedNoteLedger::push(
    NoteEventSink sink, const VoiceTransition& transition,
    std::uint8_t one_based_channel) noexcept {
  return sink.push != nullptr && one_based_channel >= 1U &&
         one_based_channel <= 16U &&
         sink.push(sink.context, transition, one_based_channel);
}

std::uint8_t GeneratedNoteLedger::allocate_channel(
    MidiRouting routing, std::uint8_t start_channel) const noexcept {
  if (start_channel < 1U || start_channel > 16U) {
    return 0U;
  }
  if (routing == MidiRouting::single) {
    return start_channel;
  }
  if (routing != MidiRouting::per_voice) {
    return 0U;
  }
  for (std::uint8_t slot = 0U; slot < kMaxVoices; ++slot) {
    const std::uint8_t channel = static_cast<std::uint8_t>(
        ((static_cast<std::uint16_t>(start_channel) - 1U + slot) % 16U) + 1U);
    bool used = false;
    for (std::uint16_t note = 0U; note < 128U; ++note) {
      const auto midi_note = static_cast<std::uint8_t>(note);
      if ((is_active(midi_note) || is_pending_release(midi_note)) &&
          note_channels_[note] == channel) {
        used = true;
        break;
      }
    }
    if (!used) {
      return channel;
    }
  }
  return 0U;
}

void GeneratedNoteLedger::request_release_all() noexcept {
  pending_release_[0] |= active_[0];
  pending_release_[1] |= active_[1];
  if (pending_release_[0] != 0U || pending_release_[1] != 0U) {
    cleanup_complete_ = false;
  }
}

void GeneratedNoteLedger::report_output_failure() noexcept {
  enter_blocked();
}

void GeneratedNoteLedger::request_recovery() noexcept {
  panic_hold_ = true;
  recovery_requested_ = true;
  hold_calls_remaining_ = 1;
}

void GeneratedNoteLedger::enter_blocked() noexcept {
  output_blocked_ = true;
  cleanup_complete_ = false;
  request_release_all();
}

bool GeneratedNoteLedger::retry_pending_releases(NoteEventSink sink) noexcept {
  if (!release_pending()) {
    cleanup_complete_ = true;
    return true;
  }
  for (std::uint16_t note = 0; note < 128; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (!is_pending_release(midi_note)) {
      continue;
    }
    const VoiceTransition release{0, TransitionKind::note_off, midi_note, 0,
                                  static_cast<std::uint32_t>(note)};
    if (!push(sink, release, note_channels_[midi_note])) {
      enter_blocked();
      return false;
    }
    if (is_active(midi_note) && active_count_ > 0U) {
      --active_count_;
    }
    clear_bit(pending_release_, midi_note);
    clear_bit(active_, midi_note);
    note_channels_[midi_note] = 0U;
  }
  cleanup_complete_ = true;
  return true;
}

void GeneratedNoteLedger::finish_hold(double selected_peak, bool finite_input,
                                      bool supported_layout) noexcept {
  if (!panic_hold_) {
    return;
  }
  if (hold_calls_remaining_ > 0) {
    --hold_calls_remaining_;
    return;
  }
  if (recovery_requested_ && cleanup_complete_ && finite_input &&
      supported_layout && std::isfinite(selected_peak) &&
      selected_peak < kQuietPeak) {
    panic_hold_ = false;
    recovery_requested_ = false;
    output_blocked_ = false;
    cleanup_complete_ = false;
  }
}

NoteDeliveryResult GeneratedNoteLedger::deliver(
    std::uint32_t frames, NoteEventSink sink, double selected_peak,
    bool finite_input, bool supported_layout, MidiRouting routing,
    std::uint8_t start_channel) noexcept {
  static_cast<void>(retry_pending_releases(sink));
  return deliver_queued(frames, sink, selected_peak, finite_input,
                        supported_layout, routing, start_channel);
}

NoteDeliveryResult GeneratedNoteLedger::deliver_queued(
    std::uint32_t frames, NoteEventSink sink, double selected_peak,
    bool finite_input, bool supported_layout, MidiRouting routing,
    std::uint8_t start_channel) noexcept {
  if (!storage_ || frames == 0 || frames > max_frames_) {
    invalid_transition_ = true;
    return NoteDeliveryResult{output_blocked_, panic_hold_, false};
  }
  if (start_channel < 1U || start_channel > 16U ||
      (routing != MidiRouting::single && routing != MidiRouting::per_voice)) {
    invalid_transition_ = true;
  }
  for (std::size_t index = 0; index < size_; ++index) {
    if (storage_[index].sample_offset >= frames) {
      invalid_transition_ = true;
      break;
    }
  }

  if (!release_pending() && !output_blocked_) {
    for (std::size_t index = 0; index < size_; ++index) {
      const VoiceTransition& event = storage_[index];
      if (event.sample_offset >= frames) {
        continue;
      }
      if (event.kind == TransitionKind::note_off) {
        if (!is_active(event.note) && !is_pending_release(event.note)) {
          enter_blocked();
          break;
        }
        if (!push(sink, event, note_channels_[event.note])) {
          set_bit(pending_release_, event.note);
          enter_blocked();
          break;
        }
        if (is_active(event.note) && active_count_ > 0U) {
          --active_count_;
        }
        clear_bit(active_, event.note);
        clear_bit(pending_release_, event.note);
        note_channels_[event.note] = 0U;
        continue;
      }
      if (panic_hold_) {
        continue;
      }
      if (is_active(event.note) || is_pending_release(event.note)) {
        enter_blocked();
        break;
      }
      if (active_count_ >= kMaxVoices) {
        enter_blocked();
        break;
      }
      const std::uint8_t channel = allocate_channel(routing, start_channel);
      if (channel == 0U || !push(sink, event, channel)) {
        enter_blocked();
        break;
      }
      note_channels_[event.note] = channel;
      set_bit(active_, event.note);
      ++active_count_;
    }
  }

  finish_hold(selected_peak, finite_input, supported_layout);
  return NoteDeliveryResult{
      output_blocked_, panic_hold_,
      !invalid_transition_ && !output_blocked_ && !panic_hold_};
}

}  // namespace m3
