#include "midi_pipeline.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <new>
#include <utility>

#include "m3/constants.hpp"

namespace {

constexpr double kQuietPeak = 0.0001;

}  // namespace

namespace m3 {

bool MidiPipeline::activate(std::uint32_t max_frames) noexcept {
  deactivate();
  if (max_frames == 0 || max_frames > kMaxHostFrames) {
    return false;
  }
  const std::size_t ticks =
      (static_cast<std::size_t>(max_frames) + kDecisionQuantum - 1U) /
      kDecisionQuantum;
  if (ticks > (std::numeric_limits<std::size_t>::max() - 10U) /
                  kMaxTickTransitions) {
    return false;
  }
  const std::size_t requested_capacity =
      ticks * kMaxTickTransitions + kMaxVoices + 2U;
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

void MidiPipeline::deactivate() noexcept {
  storage_.reset();
  capacity_ = 0;
  size_ = 0;
  max_frames_ = 0;
  active_ = {};
  pending_release_ = {};
  invalid_event_ = false;
  blocked_ = false;
  cleanup_requested_ = false;
  channel_panic_required_ = false;
  cleanup_complete_ = false;
  panic_hold_ = false;
  explicit_recovery_ = false;
  hold_calls_remaining_ = 0;
}

void MidiPipeline::begin_block() noexcept {
  size_ = 0;
  invalid_event_ = false;
}

bool MidiPipeline::transition_before(const VoiceTransition& left,
                                     const VoiceTransition& right) noexcept {
  if (left.sample_offset != right.sample_offset) {
    return left.sample_offset < right.sample_offset;
  }
  if (left.kind != right.kind) {
    return left.kind == TransitionKind::note_off;
  }
  return left.sequence < right.sequence;
}

bool MidiPipeline::queue_transition(const VoiceTransition& transition,
                                    std::uint32_t frames_count) noexcept {
  const bool valid_kind = transition.kind == TransitionKind::note_off ||
                          transition.kind == TransitionKind::note_on;
  if (!storage_ || size_ >= capacity_ || frames_count == 0 ||
      frames_count > max_frames_ || transition.sample_offset >= frames_count ||
      !valid_kind || transition.note > 127U || transition.velocity > 127U) {
    invalid_event_ = true;
    return false;
  }
  std::size_t position = size_;
  while (position > 0 && transition_before(transition, storage_[position - 1U])) {
    storage_[position] = storage_[position - 1U];
    --position;
  }
  storage_[position] = transition;
  ++size_;
  return true;
}

bool MidiPipeline::bit(const std::array<std::uint64_t, 2>& bits,
                       std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  return (bits[word] & (std::uint64_t{1} << shift)) != 0U;
}

void MidiPipeline::set_bit(std::array<std::uint64_t, 2>& bits,
                           std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  bits[word] |= std::uint64_t{1} << shift;
}

void MidiPipeline::clear_bit(std::array<std::uint64_t, 2>& bits,
                             std::uint8_t note) noexcept {
  const std::size_t word = note / 64U;
  const std::uint32_t shift = note % 64U;
  bits[word] &= ~(std::uint64_t{1} << shift);
}

bool MidiPipeline::is_active(std::uint8_t note) const noexcept {
  return note <= 127U && bit(active_, note);
}

bool MidiPipeline::is_pending_release(std::uint8_t note) const noexcept {
  return note <= 127U && bit(pending_release_, note);
}

bool MidiPipeline::request_panic(std::uint32_t offset,
                                 std::uint32_t frames_count) noexcept {
  panic_hold_ = true;
  explicit_recovery_ = true;
  hold_calls_remaining_ = 1;
  bool complete = true;
  std::uint32_t sequence = 0;
  for (std::uint16_t note = 0; note < 128; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (is_active(midi_note) &&
        !queue_transition(VoiceTransition{offset, TransitionKind::note_off,
                                          midi_note, 0, sequence++},
                          frames_count)) {
      complete = false;
    }
  }
  if (!complete) {
    enter_blocked();
  }
  return complete;
}

void MidiPipeline::request_reset() noexcept {
  panic_hold_ = true;
  explicit_recovery_ = true;
  hold_calls_remaining_ = 1;
  pending_release_[0] |= active_[0];
  pending_release_[1] |= active_[1];
  if (pending_release_[0] != 0U || pending_release_[1] != 0U) {
    cleanup_requested_ = true;
  }
}

bool MidiPipeline::push_midi(const clap_output_events_t* output,
                             std::uint32_t offset, std::uint8_t status,
                             std::uint8_t data1, std::uint8_t data2) noexcept {
  if (output == nullptr || output->try_push == nullptr) {
    return false;
  }
  clap_event_midi_t event{};
  event.header.size = sizeof(event);
  event.header.time = offset;
  event.header.space_id = CLAP_CORE_EVENT_SPACE_ID;
  event.header.type = CLAP_EVENT_MIDI;
  event.port_index = 0;
  event.data[0] = status;
  event.data[1] = data1;
  event.data[2] = data2;
  return output->try_push(output, &event.header);
}

bool MidiPipeline::push_input(const clap_output_events_t* output,
                              const clap_event_header_t* event) noexcept {
  return output != nullptr && output->try_push != nullptr && event != nullptr &&
         output->try_push(output, event);
}

void MidiPipeline::enter_blocked() noexcept {
  blocked_ = true;
  cleanup_requested_ = true;
  cleanup_complete_ = false;
  channel_panic_required_ = true;
  pending_release_[0] |= active_[0];
  pending_release_[1] |= active_[1];
}

bool MidiPipeline::retry_cleanup(const clap_output_events_t* output,
                                 std::uint8_t channel) noexcept {
  if (!cleanup_requested_) {
    return true;
  }
  for (std::uint16_t note = 0; note < 128; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (!is_pending_release(midi_note)) {
      continue;
    }
    if (!push_midi(output, 0, static_cast<std::uint8_t>(0x80U | (channel - 1U)),
                   midi_note, 0)) {
      enter_blocked();
      return false;
    }
    clear_bit(pending_release_, midi_note);
    clear_bit(active_, midi_note);
  }
  if (channel_panic_required_) {
    const std::uint8_t status =
        static_cast<std::uint8_t>(0xB0U | (channel - 1U));
    if (!push_midi(output, 0, status, 123, 0) ||
        !push_midi(output, 0, status, 120, 0)) {
      enter_blocked();
      return false;
    }
    channel_panic_required_ = false;
  }
  cleanup_requested_ = false;
  cleanup_complete_ = true;
  return true;
}

void MidiPipeline::finish_hold(double selected_input_peak, bool finite_input,
                               bool supported_layout) noexcept {
  if (!panic_hold_) {
    return;
  }
  if (hold_calls_remaining_ > 0) {
    --hold_calls_remaining_;
    return;
  }
  if (explicit_recovery_ && !cleanup_requested_ &&
      (!blocked_ || cleanup_complete_) && finite_input && supported_layout &&
      std::isfinite(selected_input_peak) && selected_input_peak < kQuietPeak) {
    panic_hold_ = false;
    explicit_recovery_ = false;
    if (blocked_ && cleanup_complete_) {
      blocked_ = false;
      cleanup_complete_ = false;
    }
  }
}

MidiProcessResult MidiPipeline::process(
    std::uint32_t frames_count, std::uint8_t one_based_channel,
    const clap_input_events_t* input, const clap_output_events_t* output,
    double selected_input_peak, bool finite_input,
    bool supported_layout) noexcept {
  if (!storage_ || frames_count == 0 || frames_count > max_frames_ ||
      one_based_channel == 0 || one_based_channel > 16) {
    invalid_event_ = true;
    return MidiProcessResult{true, blocked_, panic_hold_, false};
  }

  static_cast<void>(retry_cleanup(output, one_based_channel));
  std::size_t generated_index = 0;
  std::uint32_t input_index = 0;
  const std::uint32_t input_count =
      input != nullptr && input->size != nullptr ? input->size(input) : 0U;

  for (std::uint32_t offset = 0; offset < frames_count; ++offset) {
    while (generated_index < size_ &&
           storage_[generated_index].sample_offset == offset &&
           storage_[generated_index].kind == TransitionKind::note_off) {
      const VoiceTransition& generated = storage_[generated_index++];
      if (!blocked_) {
        const bool pushed = push_midi(
            output, offset,
            static_cast<std::uint8_t>(0x80U | (one_based_channel - 1U)),
            generated.note, 0);
        if (pushed) {
          clear_bit(active_, generated.note);
          clear_bit(pending_release_, generated.note);
        } else {
          set_bit(pending_release_, generated.note);
          enter_blocked();
        }
      }
    }

    while (input_index < input_count) {
      const clap_event_header_t* header =
          input != nullptr && input->get != nullptr ? input->get(input, input_index)
                                                   : nullptr;
      if (header == nullptr) {
        invalid_event_ = true;
        ++input_index;
        continue;
      }
      if (header->time > offset) {
        break;
      }
      ++input_index;
      if (header->time < offset || header->time >= frames_count) {
        invalid_event_ = true;
        continue;
      }
      if (header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
          header->type != CLAP_EVENT_MIDI) {
        continue;
      }
      if (header->size < sizeof(clap_event_midi_t)) {
        invalid_event_ = true;
        continue;
      }
      if (!push_input(output, header)) {
        enter_blocked();
      }
    }

    while (generated_index < size_ &&
           storage_[generated_index].sample_offset == offset) {
      const VoiceTransition& generated = storage_[generated_index++];
      if (generated.kind != TransitionKind::note_on) {
        invalid_event_ = true;
        continue;
      }
      if (blocked_ || panic_hold_) {
        continue;
      }
      const bool pushed = push_midi(
          output, offset,
          static_cast<std::uint8_t>(0x90U | (one_based_channel - 1U)),
          generated.note, generated.velocity);
      if (pushed) {
        set_bit(active_, generated.note);
      } else {
        enter_blocked();
      }
    }
  }

  finish_hold(selected_input_peak, finite_input, supported_layout);
  return MidiProcessResult{invalid_event_, blocked_, panic_hold_,
                           !invalid_event_ && !blocked_ && !panic_hold_};
}

}  // namespace m3
