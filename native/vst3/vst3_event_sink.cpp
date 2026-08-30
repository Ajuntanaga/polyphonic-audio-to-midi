#include "vst3_event_sink.hpp"

#include <limits>

#include "pluginterfaces/vst/ivstevents.h"

namespace m3::vst3 {

bool push_vst3_note(void* raw_context,
                    const VoiceTransition& transition) noexcept {
  auto* context = static_cast<Vst3EventSinkContext*>(raw_context);
  const bool note_on = transition.kind == TransitionKind::note_on;
  const bool note_off = transition.kind == TransitionKind::note_off;
  const bool valid_velocity =
      (note_on && transition.velocity > 0U && transition.velocity <= 127U) ||
      (note_off && transition.velocity == 0U);
  if (context == nullptr || context->events == nullptr ||
      context->one_based_channel < 1U || context->one_based_channel > 16U ||
      transition.note > 127U || !valid_velocity || (!note_on && !note_off) ||
      transition.sample_offset >
          static_cast<std::uint32_t>(
              std::numeric_limits<Steinberg::int32>::max())) {
    return false;
  }

  Steinberg::Vst::Event event{};
  event.busIndex = 0;
  event.sampleOffset =
      static_cast<Steinberg::int32>(transition.sample_offset);
  const Steinberg::int16 channel = static_cast<Steinberg::int16>(
      context->one_based_channel - 1U);
  const Steinberg::int16 pitch =
      static_cast<Steinberg::int16>(transition.note);
  const Steinberg::int32 note_id =
      -1000 - static_cast<Steinberg::int32>(transition.note);
  if (note_on) {
    event.type = Steinberg::Vst::Event::kNoteOnEvent;
    event.noteOn.channel = channel;
    event.noteOn.pitch = pitch;
    event.noteOn.tuning = 0.0F;
    event.noteOn.velocity = static_cast<float>(transition.velocity) / 127.0F;
    event.noteOn.length = 0;
    event.noteOn.noteId = note_id;
  } else {
    event.type = Steinberg::Vst::Event::kNoteOffEvent;
    event.noteOff.channel = channel;
    event.noteOff.pitch = pitch;
    event.noteOff.velocity = 0.0F;
    event.noteOff.noteId = note_id;
    event.noteOff.tuning = 0.0F;
  }
  const Steinberg::tresult result = context->events->addEvent(event);
  return result == Steinberg::kResultOk || result == Steinberg::kResultTrue;
}

}  // namespace m3::vst3
