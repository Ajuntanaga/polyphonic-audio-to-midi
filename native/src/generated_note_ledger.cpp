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
  voices_ = {};
  active_count_ = 0U;
  invalid_transition_ = false;
  output_blocked_ = false;
  cleanup_complete_ = false;
  panic_hold_ = false;
  recovery_requested_ = false;
  hold_calls_remaining_ = 0;
  transferred_pairs_ = 0U;
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
  const bool valid_voice = transition.voice_id == kUnassignedVoiceId ||
                           transition.voice_id < kMaxVoices;
  if (!storage_ || size_ >= capacity_ || frames == 0 || frames > max_frames_ ||
      transition.sample_offset >= frames || (!note_off && !note_on) ||
      transition.note > 127U || !valid_velocity || !valid_voice) {
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

bool GeneratedNoteLedger::queue_active_releases(
    std::uint32_t sample_offset, std::uint32_t frames) noexcept {
  bool complete = true;
  std::uint32_t sequence = 0U;
  for (const ActiveVoice& voice : voices_) {
    if (!voice.active) {
      continue;
    }
    complete = queue_transition(
                   VoiceTransition{sample_offset, TransitionKind::note_off,
                                   voice.note, 0U, sequence++, voice.voice_id},
                   frames) &&
               complete;
  }
  return complete;
}

std::size_t GeneratedNoteLedger::find_voice(
    const VoiceTransition& transition) const noexcept {
  for (std::size_t slot = 0U; slot < voices_.size(); ++slot) {
    const ActiveVoice& voice = voices_[slot];
    if ((!voice.active && !voice.pending_release) ||
        voice.note != transition.note) {
      continue;
    }
    if (transition.voice_id < kMaxVoices) {
      if (voice.voice_id == transition.voice_id) {
        return slot;
      }
    } else if (voice.voice_id == kUnassignedVoiceId) {
      return slot;
    }
  }
  return voices_.size();
}

std::size_t GeneratedNoteLedger::find_free_voice() const noexcept {
  for (std::size_t slot = 0U; slot < voices_.size(); ++slot) {
    if (!voices_[slot].active && !voices_[slot].pending_release) {
      return slot;
    }
  }
  return voices_.size();
}

bool GeneratedNoteLedger::is_active(std::uint8_t note) const noexcept {
  if (note > 127U) {
    return false;
  }
  for (const ActiveVoice& voice : voices_) {
    if (voice.active && voice.note == note) {
      return true;
    }
  }
  return false;
}

bool GeneratedNoteLedger::is_pending_release(
    std::uint8_t note) const noexcept {
  if (note > 127U) {
    return false;
  }
  for (const ActiveVoice& voice : voices_) {
    if (voice.pending_release && voice.note == note) {
      return true;
    }
  }
  return false;
}

bool GeneratedNoteLedger::release_pending() const noexcept {
  for (const ActiveVoice& voice : voices_) {
    if (voice.pending_release) {
      return true;
    }
  }
  return false;
}

bool GeneratedNoteLedger::push(
    NoteEventSink sink, const VoiceTransition& transition,
    std::uint8_t one_based_channel) noexcept {
  return sink.push != nullptr && one_based_channel >= 1U &&
         one_based_channel <= 16U &&
         sink.push(sink.context, transition, one_based_channel);
}

std::uint8_t GeneratedNoteLedger::allocate_channel(
    MidiRouting routing, std::uint8_t start_channel,
    const VoiceTransition& transition, NoteIdentityMode identity_mode) const noexcept {
  if (start_channel < 1U || start_channel > 16U) {
    return 0U;
  }
  if (routing == MidiRouting::single) {
    return start_channel;
  }
  if (routing != MidiRouting::per_voice) {
    return 0U;
  }
  if (transition.voice_id < kMaxVoices &&
      identity_mode == NoteIdentityMode::physical_string) {
    const std::uint8_t channel = static_cast<std::uint8_t>(
        ((static_cast<std::uint16_t>(start_channel) - 1U +
          transition.voice_id) %
         16U) +
        1U);
    for (const ActiveVoice& voice : voices_) {
      if ((voice.active || voice.pending_release) &&
          voice.channel == channel) {
        return 0U;
      }
    }
    return channel;
  }
  for (std::uint8_t slot = 0U; slot < kMaxVoices; ++slot) {
    const std::uint8_t channel = static_cast<std::uint8_t>(
        ((static_cast<std::uint16_t>(start_channel) - 1U + slot) % 16U) + 1U);
    bool used = false;
    for (const ActiveVoice& voice : voices_) {
      if ((voice.active || voice.pending_release) &&
          voice.channel == channel) {
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

std::size_t GeneratedNoteLedger::continuation_partner(
    std::size_t index, std::size_t slot) const noexcept {
  const auto& event = storage_[index];
  const auto target = event.continuation_voice_id;
  if (event.voice_id >= kMaxVoices || target >= kMaxVoices ||
      target == event.voice_id || !voices_[slot].active ||
      voices_[slot].pending_release || panic_hold_) return size_;
  // A single owner only. An unison, occupied destination or ambiguous batch
  // falls back to the original release/attack path.
  for (std::size_t other = 0U; other < voices_.size(); ++other) {
    const auto& voice = voices_[other];
    if (other != slot && (voice.active || voice.pending_release) &&
        (voice.note == event.note || voice.voice_id == target)) return size_;
  }
  std::size_t partner = size_;
  for (std::size_t other = 0U; other < size_; ++other) {
    const auto& next = storage_[other];
    if (other == index || next.sample_offset != event.sample_offset) continue;
    if (next.kind == TransitionKind::note_on && next.note == event.note &&
        next.voice_id == target && next.continuation_voice_id == event.voice_id &&
        partner == size_) {
      partner = other;
    } else if (next.note == event.note || next.voice_id == target ||
               next.voice_id == event.voice_id) {
      return size_;
    }
  }
  return partner;
}

void GeneratedNoteLedger::request_release_all() noexcept {
  bool any = false;
  for (ActiveVoice& voice : voices_) {
    if (voice.active) {
      voice.pending_release = true;
      any = true;
    }
  }
  if (any) {
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
  for (std::uint16_t note = 0U; note < 128U; ++note) {
    for (ActiveVoice& voice : voices_) {
      if (!voice.pending_release || voice.note != note) {
        continue;
      }
      const VoiceTransition release{
          0U, TransitionKind::note_off, voice.note, 0U,
          static_cast<std::uint32_t>(note), voice.output_voice_id};
      if (!push(sink, release, voice.channel)) {
        enter_blocked();
        return false;
      }
      if (voice.active && active_count_ > 0U) {
        --active_count_;
      }
      voice = {};
    }
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
    std::uint8_t start_channel, NoteIdentityMode identity_mode) noexcept {
  static_cast<void>(retry_pending_releases(sink));
  return deliver_queued(frames, sink, selected_peak, finite_input,
                        supported_layout, routing, start_channel, identity_mode);
}

NoteDeliveryResult GeneratedNoteLedger::deliver_queued(
    std::uint32_t frames, NoteEventSink sink, double selected_peak,
    bool finite_input, bool supported_layout, MidiRouting routing,
    std::uint8_t start_channel, NoteIdentityMode identity_mode) noexcept {
  if (!storage_ || frames == 0 || frames > max_frames_) {
    invalid_transition_ = true;
    return NoteDeliveryResult{output_blocked_, panic_hold_, false};
  }
  if (start_channel < 1U || start_channel > 16U ||
      (routing != MidiRouting::single && routing != MidiRouting::per_voice)) {
    // Preserve legacy release/cleanup handling even with invalid routing.
    invalid_transition_ = true;
  }
  if ((identity_mode != NoteIdentityMode::physical_string &&
       identity_mode != NoteIdentityMode::stable_note) ||
      (identity_mode == NoteIdentityMode::stable_note && routing != MidiRouting::per_voice)) {
    invalid_transition_ = true;
    return NoteDeliveryResult{output_blocked_, panic_hold_, false};
  }
  for (std::size_t index = 0; index < size_; ++index) {
    if (storage_[index].sample_offset >= frames) {
      invalid_transition_ = true;
      break;
    }
  }

  if (!release_pending() && !output_blocked_) {
    std::array<std::size_t, kMaxVoices> consumed{};
    std::size_t consumed_count = 0U;
    for (std::size_t index = 0; index < size_; ++index) {
      const VoiceTransition& event = storage_[index];
      if (index == 0U || event.sample_offset != storage_[index - 1U].sample_offset)
        consumed_count = 0U;
      bool skip = false;
      for (std::size_t item = 0U; item < consumed_count; ++item)
        skip = skip || consumed[item] == index;
      if (skip) continue;
      if (event.sample_offset >= frames) {
        continue;
      }
      if (event.kind == TransitionKind::note_off) {
        const std::size_t slot = find_voice(event);
        if (slot >= voices_.size()) {
          enter_blocked();
          break;
        }
        ActiveVoice& voice = voices_[slot];
        if (identity_mode == NoteIdentityMode::stable_note && consumed_count < consumed.size()) {
          const auto partner = continuation_partner(index, slot);
          if (partner < size_) {
            voice.voice_id = event.continuation_voice_id;
            consumed[consumed_count++] = partner;
            ++transferred_pairs_;
            continue;
          }
        }
        auto delivered = event;
        delivered.voice_id = voice.output_voice_id;
        delivered.continuation_voice_id = kUnassignedVoiceId;
        if (!push(sink, delivered, voice.channel)) {
          voice.pending_release = true;
          enter_blocked();
          break;
        }
        if (voice.active && active_count_ > 0U) {
          --active_count_;
        }
        voice = {};
        continue;
      }
      if (panic_hold_) {
        continue;
      }
      bool identity_in_use = find_voice(event) < voices_.size();
      if (event.voice_id < kMaxVoices) {
        for (const ActiveVoice& voice : voices_) {
          identity_in_use =
              identity_in_use ||
              ((voice.active || voice.pending_release) &&
               voice.voice_id == event.voice_id);
        }
      }
      if (identity_in_use) {
        enter_blocked();
        break;
      }
      if (active_count_ >= kMaxVoices) {
        enter_blocked();
        break;
      }
      const std::uint8_t channel =
          allocate_channel(routing, start_channel, event, identity_mode);
      const std::size_t slot = find_free_voice();
      auto delivered = event;
      if (identity_mode == NoteIdentityMode::stable_note)
        delivered.voice_id = static_cast<std::uint8_t>(slot);
      delivered.continuation_voice_id = kUnassignedVoiceId;
      if (channel == 0U || slot >= voices_.size() ||
          !push(sink, delivered, channel)) {
        enter_blocked();
        break;
      }
      voices_[slot] = ActiveVoice{true, false, event.note, channel,
                                  event.voice_id, delivered.voice_id};
      ++active_count_;
    }
  }

  finish_hold(selected_peak, finite_input, supported_layout);
  return NoteDeliveryResult{
      output_blocked_, panic_hold_,
      !invalid_transition_ && !output_blocked_ && !panic_hold_};
}

}  // namespace m3
