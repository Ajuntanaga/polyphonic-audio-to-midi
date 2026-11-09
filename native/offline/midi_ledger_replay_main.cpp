// Offline, open-loop replay of saved detector events through the production
// ledger. The file sink accepts callbacks; it is not a VST3 host or MIDI device.
#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "m3/generated_note_ledger.hpp"

namespace {

struct Event {
  std::uint64_t sample{};
  m3::VoiceTransition transition{};
};

bool number(std::string_view text, std::uint64_t& value) {
  if (text.empty() || text.front() < '0' || text.front() > '9') return false;
  const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
  return result.ec == std::errc{} && result.ptr == text.data() + text.size();
}

bool read_events(const char* path, std::uint64_t samples, std::uint64_t expected,
                 std::vector<Event>& events) {
  std::ifstream input(path);
  std::string line;
  if (!std::getline(input, line) || line != "# m3_midi_events_v1" ||
      !std::getline(input, line) ||
      line != "sample\tkind\tnote\tvelocity\tvoice_id\tsequence") return false;
  while (std::getline(input, line)) {
    if (line.size() > 256U || events.size() >= expected) return false;
    std::array<std::string_view, 6> fields{};
    std::size_t start = 0;
    for (std::size_t index = 0; index < fields.size(); ++index) {
      const auto end = line.find('\t', start);
      if ((index + 1U < fields.size()) != (end != std::string::npos)) return false;
      fields[index] = std::string_view(line).substr(start,
          end == std::string::npos ? line.size() - start : end - start);
      start = end == std::string::npos ? line.size() : end + 1U;
    }
    std::uint64_t sample{}, note{}, velocity{}, voice{}, sequence{};
    if (!number(fields[0], sample) || !number(fields[2], note) ||
        !number(fields[3], velocity) || !number(fields[4], voice) ||
        !number(fields[5], sequence) || sample >= samples || note > 127U ||
        velocity > 127U || (voice >= m3::kMaxVoices && voice != 255U) ||
        sequence > std::numeric_limits<std::uint32_t>::max() ||
        (fields[1] != "on" && fields[1] != "off") ||
        (!events.empty() && (sample < events.back().sample ||
                            sequence <= events.back().transition.sequence))) return false;
    events.push_back(Event{sample, m3::VoiceTransition{0U,
        fields[1] == "on" ? m3::TransitionKind::note_on : m3::TransitionKind::note_off,
        static_cast<std::uint8_t>(note), static_cast<std::uint8_t>(velocity),
        static_cast<std::uint32_t>(sequence), static_cast<std::uint8_t>(voice)}});
  }
  return input.eof() && events.size() == expected;
}

void event_json(std::ostream& output, const Event& event) {
  const auto& t = event.transition;
  output << "{\"sample\":" << event.sample << ",\"kind\":\""
         << (t.kind == m3::TransitionKind::note_on ? "on" : "off")
         << "\",\"note\":" << unsigned(t.note) << ",\"velocity\":" << unsigned(t.velocity)
         << ",\"voice_id\":" << unsigned(t.voice_id) << ",\"sequence\":" << t.sequence << '}';
}

struct Capture {
  std::ofstream output;
  std::uint64_t block_start{}, source_callbacks{}, cleanup_callbacks{}, pairing_errors{};
  bool cleanup{};
  // Separate assigned identities even when they share a pitch and channel.
  std::array<std::array<std::uint8_t, 128>, m3::kMaxVoices + 1U> channels{};

  static bool push(void* context, const m3::VoiceTransition& event,
                   std::uint8_t channel) noexcept {
    auto& capture = *static_cast<Capture*>(context);
    const bool on = event.kind == m3::TransitionKind::note_on;
    capture.output << capture.block_start + event.sample_offset << '\t'
        << (capture.cleanup ? "cleanup" : "source") << '\t' << (on ? "on" : "off")
        << '\t' << unsigned(event.note) << '\t' << unsigned(event.velocity)
        << '\t' << unsigned(event.voice_id) << '\t' << unsigned(channel) << '\t';
    if (!capture.cleanup) capture.output << event.sequence;
    capture.output << '\n';
    if (!capture.output) return false;
    const std::size_t identity = event.voice_id == 255U ? m3::kMaxVoices : event.voice_id;
    auto& active = capture.channels[identity][event.note];
    if ((on && active != 0U) || (!on && active != channel)) ++capture.pairing_errors;
    active = on ? channel : 0U;
    if (capture.cleanup) ++capture.cleanup_callbacks;
    else ++capture.source_callbacks;
    return true;
  }
};

}  // namespace

int main(int argc, char** argv) {
  std::uint64_t samples{}, expected{}, block{};
  if (argc != 7 || !number(argv[2], samples) || !number(argv[3], expected) ||
      !number(argv[4], block) || samples == 0U ||
      samples > std::numeric_limits<std::uint32_t>::max() || expected > 1000000U ||
      block == 0U || block > m3::kMaxHostFrames ||
      (samples + block - 1U) / block > 1000000U ||
      (std::string_view(argv[5]) != "single" && std::string_view(argv[5]) != "per_voice")) {
    std::cerr << "usage: midi_ledger_replay events samples event_count block_size single|per_voice callbacks\n";
    return 2;
  }
  std::vector<Event> events;
  if (!read_events(argv[1], samples, expected, events)) {
    std::cerr << "Incomplete, invalid or reordered event capture\n";
    return 2;
  }
  m3::GeneratedNoteLedger ledger;
  if (!ledger.activate(static_cast<std::uint32_t>(block))) return 3;
  Capture capture;
  capture.output.open(argv[6]);
  capture.output << "# m3_ledger_callbacks_v1\n"
      << "sample\tphase\tkind\tnote\tvelocity\tvoice_id\tchannel\tsource_sequence\n";
  if (!capture.output) return 3;
  const m3::NoteEventSink sink{&capture, Capture::push};
  const auto routing = std::string_view(argv[5]) == "single"
      ? m3::MidiRouting::single : m3::MidiRouting::per_voice;
  std::uint64_t queued{}, rejected{}, unqueued{}, blocked_blocks{}, disabled_blocks{};
  std::optional<std::uint64_t> first_blocked;
  std::optional<Event> first_blocking_event;
  std::size_t cursor = 0;
  for (std::uint64_t start = 0; start < samples; start += block) {
    const auto frames = static_cast<std::uint32_t>(std::min(block, samples - start));
    capture.block_start = start;
    capture.cleanup = true;
    static_cast<void>(ledger.retry_pending_releases(sink));
    capture.cleanup = false;
    const auto first = cursor;
    while (cursor < events.size() && events[cursor].sample < start + frames) ++cursor;
    const auto callbacks_before = capture.source_callbacks;
    bool queue_failed = false;
    for (auto index = first; index < cursor; ++index) {
      auto transition = events[index].transition;
      transition.sample_offset = static_cast<std::uint32_t>(events[index].sample - start);
      if (!ledger.queue_transition(transition, frames)) {
        ++rejected;
        unqueued += cursor - index - 1U;
        queue_failed = true;
        ledger.report_output_failure();
        if (!first_blocked) first_blocking_event = events[index];
        break;
      }
      ++queued;
    }
    // The constant finite signal only supplies ledger hold state. No waveform,
    // silence-based recovery, detector feedback, controls or host rejection.
    const auto result = ledger.deliver_queued(frames, sink, 0.5, true, true, routing, 1U);
    if (result.output_blocked) {
      ++blocked_blocks;
      if (!first_blocked) {
        first_blocked = start;
        if (!queue_failed) {
          std::vector<Event> ordered(events.begin() + static_cast<std::ptrdiff_t>(first),
                                     events.begin() + static_cast<std::ptrdiff_t>(cursor));
          std::sort(ordered.begin(), ordered.end(), [](const Event& a, const Event& b) {
            if (a.sample != b.sample) return a.sample < b.sample;
            if (a.transition.kind != b.transition.kind)
              return a.transition.kind == m3::TransitionKind::note_off;
            return a.transition.sequence < b.transition.sequence;
          });
          const auto delivered = capture.source_callbacks - callbacks_before;
          if (delivered < ordered.size()) first_blocking_event = ordered[delivered];
        }
      }
    }
    if (!result.detection_allowed) ++disabled_blocks;
    ledger.begin_block();
  }
  capture.output.close();
  if (!capture.output || capture.pairing_errors != 0U) return 3;
  std::cout << "{\"schema\":\"m3_ledger_replay_v1\",\"routing\":\"" << argv[5]
      << "\",\"sample_count\":" << samples << ",\"block_size\":" << block
      << ",\"last_block_frames\":" << ((samples - 1U) % block + 1U)
      << ",\"input_events\":" << events.size() << ",\"queued_events\":" << queued
      << ",\"queue_rejected_events\":" << rejected << ",\"unqueued_after_failure\":" << unqueued
      << ",\"source_callbacks\":" << capture.source_callbacks
      << ",\"suppressed_source_events\":" << events.size() - capture.source_callbacks
      << ",\"cleanup_callbacks\":" << capture.cleanup_callbacks
      << ",\"blocked_blocks\":" << blocked_blocks << ",\"detection_disabled_blocks\":" << disabled_blocks
      << ",\"first_blocked_block_start\":";
  if (first_blocked) std::cout << *first_blocked; else std::cout << "null";
  std::cout << ",\"first_blocking_event\":";
  if (first_blocking_event) event_json(std::cout, *first_blocking_event); else std::cout << "null";
  std::cout << ",\"output_blocked_at_eof\":" << (ledger.output_blocked() ? "true" : "false")
      << ",\"cleanup_pending_at_eof\":" << (ledger.release_pending() ? "true" : "false")
      << ",\"active_identities_at_eof\":[";
  bool comma = false;
  for (std::size_t voice = 0; voice < capture.channels.size(); ++voice) {
    for (std::size_t note = 0; note < capture.channels[voice].size(); ++note) {
      const auto channel = capture.channels[voice][note];
      if (channel == 0U) continue;
      if (comma) std::cout << ',';
      comma = true;
      std::cout << "{\"voice_id\":" << (voice == m3::kMaxVoices ? 255U : voice)
          << ",\"note\":" << note << ",\"channel\":" << unsigned(channel) << '}';
    }
  }
  std::cout << "],\"callback_pairing_errors\":" << capture.pairing_errors
      << ",\"forced_eof_releases\":false,\"host_delivery_verified\":false}\n";
  return std::cout ? 0 : 3;
}
