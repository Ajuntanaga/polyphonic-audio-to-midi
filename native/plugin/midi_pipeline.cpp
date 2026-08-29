#include "midi_pipeline.hpp"

#include <cstdint>

namespace m3 {

struct MidiPipeline::DeliveryContext final {
  MidiPipeline* pipeline{};
  const clap_input_events_t* input{};
  const clap_output_events_t* output{};
  std::uint32_t frames{};
  std::uint32_t input_count{};
  std::uint32_t input_index{};
  std::uint32_t last_input_offset{};
  std::uint8_t channel{};
  bool have_last_input{};
};

bool MidiPipeline::activate(std::uint32_t max_frames) noexcept {
  deactivate();
  return ledger_.activate(max_frames);
}

void MidiPipeline::deactivate() noexcept {
  ledger_.deactivate();
  invalid_event_ = false;
  channel_panic_required_ = false;
}

void MidiPipeline::begin_block() noexcept {
  ledger_.begin_block();
  invalid_event_ = false;
}

bool MidiPipeline::queue_transition(const VoiceTransition& transition,
                                    std::uint32_t frames_count) noexcept {
  if (!ledger_.queue_transition(transition, frames_count)) {
    invalid_event_ = true;
    return false;
  }
  return true;
}

bool MidiPipeline::is_active(std::uint8_t note) const noexcept {
  return ledger_.is_active(note);
}

bool MidiPipeline::is_pending_release(std::uint8_t note) const noexcept {
  return ledger_.is_pending_release(note);
}

bool MidiPipeline::request_panic(std::uint32_t offset,
                                 std::uint32_t frames_count) noexcept {
  ledger_.request_recovery();
  bool complete = true;
  std::uint32_t sequence = 0;
  for (std::uint16_t note = 0; note < 128; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (ledger_.is_active(midi_note) &&
        !queue_transition(VoiceTransition{offset, TransitionKind::note_off,
                                          midi_note, 0, sequence++},
                          frames_count)) {
      complete = false;
    }
  }
  if (!complete) {
    enter_output_blocked();
  }
  return complete;
}

void MidiPipeline::request_reset() noexcept {
  ledger_.request_release_all();
  ledger_.request_recovery();
}

bool MidiPipeline::push_midi(const clap_output_events_t* output,
                             std::uint32_t offset, std::uint8_t status,
                             std::uint8_t data1,
                             std::uint8_t data2) noexcept {
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

void MidiPipeline::enter_output_blocked() noexcept {
  ledger_.report_output_failure();
  channel_panic_required_ = true;
}

bool MidiPipeline::flush_inputs(DeliveryContext& context,
                                std::uint32_t boundary, bool inclusive,
                                bool final_flush) noexcept {
  bool accepted = true;
  while (context.input_index < context.input_count) {
    const clap_event_header_t* header =
        context.input != nullptr && context.input->get != nullptr
            ? context.input->get(context.input, context.input_index)
            : nullptr;
    if (header == nullptr) {
      invalid_event_ = true;
      ++context.input_index;
      continue;
    }
    const bool due = final_flush || header->time < boundary ||
                     (inclusive && header->time == boundary);
    if (!due) {
      break;
    }
    ++context.input_index;
    if (header->time >= context.frames ||
        (context.have_last_input &&
         header->time < context.last_input_offset)) {
      invalid_event_ = true;
      continue;
    }
    context.last_input_offset = header->time;
    context.have_last_input = true;
    if (header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
        header->type != CLAP_EVENT_MIDI) {
      continue;
    }
    if (header->size < sizeof(clap_event_midi_t)) {
      invalid_event_ = true;
      continue;
    }
    if (!push_input(context.output, header)) {
      enter_output_blocked();
      accepted = false;
    }
  }
  return accepted;
}

bool MidiPipeline::push_generated(
    void* raw_context, const VoiceTransition& transition) noexcept {
  auto* context = static_cast<DeliveryContext*>(raw_context);
  if (context == nullptr || context->pipeline == nullptr) {
    return false;
  }
  MidiPipeline& pipeline = *context->pipeline;
  const bool include_equal = transition.kind == TransitionKind::note_on;
  if (!pipeline.flush_inputs(*context, transition.sample_offset, include_equal,
                             false)) {
    return false;
  }
  const std::uint8_t status = static_cast<std::uint8_t>(
      (transition.kind == TransitionKind::note_off ? 0x80U : 0x90U) |
      (context->channel - 1U));
  const std::uint8_t velocity =
      transition.kind == TransitionKind::note_off ? 0U : transition.velocity;
  if (!pipeline.push_midi(context->output, transition.sample_offset, status,
                          transition.note, velocity)) {
    pipeline.enter_output_blocked();
    return false;
  }
  return true;
}

bool MidiPipeline::retry_channel_panics(const clap_output_events_t* output,
                                        std::uint8_t channel) noexcept {
  if (!channel_panic_required_ || ledger_.release_pending()) {
    return !channel_panic_required_;
  }
  const std::uint8_t status =
      static_cast<std::uint8_t>(0xB0U | (channel - 1U));
  if (!push_midi(output, 0, status, 123, 0) ||
      !push_midi(output, 0, status, 120, 0)) {
    enter_output_blocked();
    return false;
  }
  channel_panic_required_ = false;
  return true;
}

MidiProcessResult MidiPipeline::process(
    std::uint32_t frames_count, std::uint8_t one_based_channel,
    const clap_input_events_t* input, const clap_output_events_t* output,
    double selected_input_peak, bool finite_input,
    bool supported_layout) noexcept {
  if (frames_count == 0 || frames_count > kMaxHostFrames ||
      one_based_channel == 0 || one_based_channel > 16) {
    invalid_event_ = true;
    return MidiProcessResult{true, ledger_.output_blocked(),
                             ledger_.panic_hold(), false};
  }

  DeliveryContext context{};
  context.pipeline = this;
  context.input = input;
  context.output = output;
  context.frames = frames_count;
  context.input_count =
      input != nullptr && input->size != nullptr ? input->size(input) : 0U;
  context.channel = one_based_channel;

  const bool retry_channel_this_call = channel_panic_required_;
  const NoteDeliveryResult generated = ledger_.deliver(
      frames_count, NoteEventSink{&context, &push_generated},
      selected_input_peak, finite_input, supported_layout);
  if (!generated.detection_allowed && !generated.output_blocked &&
      !generated.panic_hold) {
    invalid_event_ = true;
  }
  if (generated.output_blocked && !channel_panic_required_) {
    channel_panic_required_ = true;
  }
  if (retry_channel_this_call) {
    static_cast<void>(retry_channel_panics(output, one_based_channel));
  }
  static_cast<void>(flush_inputs(context, frames_count, false, true));

  const bool output_blocked = ledger_.output_blocked();
  const bool panic_hold = ledger_.panic_hold();
  return MidiProcessResult{
      invalid_event_, output_blocked, panic_hold,
      !invalid_event_ && !output_blocked && !panic_hold};
}

}  // namespace m3
