#include "probe_processor.hpp"

#include <array>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <unistd.h>

#include "dry_path.hpp"

namespace {

constexpr std::uint8_t kTriggerController = 119;
constexpr std::uint8_t kGeneratedVelocity = 100;
constexpr std::uint32_t kMaxProbeInputEvents = 256;
constexpr std::size_t kMaxReportPath = 3072;

bool is_trigger(const clap_event_header_t* header,
                const clap_event_midi_t*& midi) noexcept {
  if (header == nullptr || header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
      header->type != CLAP_EVENT_MIDI ||
      header->size < sizeof(clap_event_midi_t)) {
    return false;
  }
  midi = reinterpret_cast<const clap_event_midi_t*>(header);
  return midi->port_index == 0 && (midi->data[0] & 0xF0U) == 0xB0U &&
         midi->data[1] == kTriggerController &&
         (midi->data[2] == 1U || midi->data[2] == 2U);
}

bool write_metric(FILE* output, const char* name,
                  std::uint32_t value) noexcept {
  return std::fprintf(output, "%s\t%u\n", name, value) >= 0;
}

}  // namespace

namespace m3 {

void ProbeProcessor::record_create() noexcept {
  create_.fetch_add(1, std::memory_order_relaxed);
}

void ProbeProcessor::record_init() noexcept {
  init_.fetch_add(1, std::memory_order_relaxed);
}

bool ProbeProcessor::record_activate() noexcept {
  activate_.fetch_add(1, std::memory_order_relaxed);
  const bool alias_passed = dry_path_self_test(true);
  const bool separate_passed = dry_path_self_test(false);
  self_test_alias_passed_.store(alias_passed, std::memory_order_relaxed);
  self_test_separate_passed_.store(separate_passed, std::memory_order_relaxed);
  return alias_passed && separate_passed;
}

void ProbeProcessor::record_start() noexcept {
  start_.fetch_add(1, std::memory_order_relaxed);
}

void ProbeProcessor::record_reset() noexcept {
  reset_.fetch_add(1, std::memory_order_relaxed);
}

void ProbeProcessor::record_stop() noexcept {
  stop_.fetch_add(1, std::memory_order_relaxed);
}

void ProbeProcessor::record_deactivate() noexcept {
  deactivate_.fetch_add(1, std::memory_order_relaxed);
}

void ProbeProcessor::record_destroy() noexcept {
  destroy_.fetch_add(1, std::memory_order_relaxed);
}

bool ProbeProcessor::buffers_alias(const clap_audio_buffer_t& input,
                                   const clap_audio_buffer_t& output,
                                   bool float32) noexcept {
  if (input.channel_count != 2 || output.channel_count != 2) {
    return false;
  }
  if (float32) {
    return input.data32 != nullptr && output.data32 != nullptr &&
           input.data32[0] != nullptr && input.data32[1] != nullptr &&
           input.data32[0] == output.data32[0] &&
           input.data32[1] == output.data32[1];
  }
  return input.data64 != nullptr && output.data64 != nullptr &&
         input.data64[0] != nullptr && input.data64[1] != nullptr &&
         input.data64[0] == output.data64[0] &&
         input.data64[1] == output.data64[1];
}

void ProbeProcessor::record_process(const clap_process_t& process) noexcept {
  if (process.audio_inputs == nullptr || process.audio_outputs == nullptr ||
      process.audio_inputs_count != 1 || process.audio_outputs_count != 1) {
    return;
  }
  const clap_audio_buffer_t& input = process.audio_inputs[0];
  const clap_audio_buffer_t& output = process.audio_outputs[0];
  const bool float32 = input.data32 != nullptr && input.data64 == nullptr &&
                       output.data32 != nullptr && output.data64 == nullptr;
  const bool float64 = input.data64 != nullptr && input.data32 == nullptr &&
                       output.data64 != nullptr && output.data32 == nullptr;
  if (!float32 && !float64) {
    return;
  }
  if (input.channel_count != 2 || output.channel_count != 2 ||
      (float32 &&
       (input.data32[0] == nullptr || input.data32[1] == nullptr ||
        output.data32[0] == nullptr || output.data32[1] == nullptr)) ||
      (float64 &&
       (input.data64[0] == nullptr || input.data64[1] == nullptr ||
        output.data64[0] == nullptr || output.data64[1] == nullptr))) {
    return;
  }
  if (float32) {
    float32_seen_.store(true, std::memory_order_relaxed);
  }
  if (float64) {
    float64_seen_.store(true, std::memory_order_relaxed);
  }
  const bool alias = buffers_alias(input, output, float32);
  if (alias) {
    alias_seen_.store(true, std::memory_order_relaxed);
  } else {
    separate_seen_.store(true, std::memory_order_relaxed);
  }
}

bool ProbeProcessor::queue_trigger_transitions(
    MidiPipeline& pipeline, const clap_input_events_t* input,
    std::uint32_t frames_count) noexcept {
  if (input == nullptr || input->size == nullptr || input->get == nullptr) {
    return true;
  }
  const std::uint32_t count = input->size(input);
  if (count > kMaxProbeInputEvents || frames_count == 0) {
    trigger_overflow_.fetch_add(1, std::memory_order_relaxed);
    return false;
  }

  std::size_t generated_count = 0;
  for (std::uint32_t index = 0; index < count; ++index) {
    const clap_event_midi_t* midi = nullptr;
    if (!is_trigger(input->get(input, index), midi)) {
      continue;
    }
    const std::uint32_t required_tail = midi->data[2] == 1U ? 3U : 1U;
    if (midi->header.time >= frames_count ||
        required_tail >= frames_count - midi->header.time) {
      trigger_overflow_.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    generated_count += midi->data[2] == 1U ? 2U : 1U;
    if (generated_count > pipeline.capacity()) {
      trigger_overflow_.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
  }

  for (std::uint32_t index = 0; index < count; ++index) {
    const clap_event_midi_t* midi = nullptr;
    if (!is_trigger(input->get(input, index), midi)) {
      continue;
    }
    const std::uint32_t time = midi->header.time;
    if (midi->data[2] == 1U) {
      trigger_one_.fetch_add(1, std::memory_order_relaxed);
      if (!pipeline.queue_transition(
              VoiceTransition{time + 1U, TransitionKind::note_on, 60,
                              kGeneratedVelocity, next_sequence_++},
              frames_count) ||
          !pipeline.queue_transition(
              VoiceTransition{time + 3U, TransitionKind::note_off, 60, 0,
                              next_sequence_++},
              frames_count)) {
        trigger_overflow_.fetch_add(1, std::memory_order_relaxed);
        return false;
      }
    } else {
      trigger_two_.fetch_add(1, std::memory_order_relaxed);
      if (!pipeline.queue_transition(
              VoiceTransition{time + 1U, TransitionKind::note_on, 61,
                              kGeneratedVelocity, next_sequence_++},
              frames_count)) {
        trigger_overflow_.fetch_add(1, std::memory_order_relaxed);
        return false;
      }
    }
  }
  return true;
}

bool ProbeProcessor::dry_path_self_test(bool alias) noexcept {
  std::array<float, 4> left{{-0.75F, -0.25F, 0.25F, 0.75F}};
  std::array<float, 4> right{{0.5F, 0.125F, -0.375F, -0.875F}};
  const std::array<float, 4> expected_left = left;
  const std::array<float, 4> expected_right = right;
  std::array<float, 4> output_left{};
  std::array<float, 4> output_right{};
  std::array<float*, 2> input{{left.data(), right.data()}};
  std::array<float*, 2> output{{alias ? left.data() : output_left.data(),
                               alias ? right.data() : output_right.data()}};
  const DryPathResult result = process_dry_path(
      input.data(), 2, output.data(), 2, 4, true);
  if (result.nonfinite_input || result.channels_processed != 2) {
    return false;
  }
  for (std::size_t frame = 0; frame < left.size(); ++frame) {
    if (output[0][frame] != expected_left[frame] ||
        output[1][frame] != expected_right[frame]) {
      return false;
    }
  }
  return true;
}

ProbeDiagnosticsSnapshot ProbeProcessor::snapshot() const noexcept {
  ProbeDiagnosticsSnapshot result;
  result.create = create_.load(std::memory_order_relaxed);
  result.init = init_.load(std::memory_order_relaxed);
  result.activate = activate_.load(std::memory_order_relaxed);
  result.start = start_.load(std::memory_order_relaxed);
  result.reset = reset_.load(std::memory_order_relaxed);
  result.stop = stop_.load(std::memory_order_relaxed);
  result.deactivate = deactivate_.load(std::memory_order_relaxed);
  result.destroy = destroy_.load(std::memory_order_relaxed);
  result.trigger_one = trigger_one_.load(std::memory_order_relaxed);
  result.trigger_two = trigger_two_.load(std::memory_order_relaxed);
  result.trigger_overflow = trigger_overflow_.load(std::memory_order_relaxed);
  result.float32_seen = float32_seen_.load(std::memory_order_relaxed);
  result.float64_seen = float64_seen_.load(std::memory_order_relaxed);
  result.alias_seen = alias_seen_.load(std::memory_order_relaxed);
  result.separate_seen = separate_seen_.load(std::memory_order_relaxed);
  result.self_test_alias_passed =
      self_test_alias_passed_.load(std::memory_order_relaxed);
  result.self_test_separate_passed =
      self_test_separate_passed_.load(std::memory_order_relaxed);
  return result;
}

bool ProbeProcessor::write_report() const noexcept {
  const char* report_path = std::getenv("M3_CLAP_PROBE_REPORT");
  if (report_path == nullptr || report_path[0] == '\0') {
    return true;
  }
  const std::size_t length = strnlen(report_path, kMaxReportPath + 1U);
  if (length == 0 || length > kMaxReportPath) {
    return false;
  }
  std::array<char, kMaxReportPath + 64U> temporary{};
  const int temporary_length = std::snprintf(
      temporary.data(), temporary.size(), "%s.tmp.%ld", report_path,
      static_cast<long>(getpid()));
  if (temporary_length < 0 ||
      static_cast<std::size_t>(temporary_length) >= temporary.size()) {
    return false;
  }

  FILE* output = std::fopen(temporary.data(), "wb");
  if (output == nullptr) {
    return false;
  }
  const ProbeDiagnosticsSnapshot value = snapshot();
  bool ok = std::fputs("metric\tvalue\n", output) >= 0;
  ok = write_metric(output, "schema", 1) && ok;
  ok = write_metric(output, "create", value.create) && ok;
  ok = write_metric(output, "init", value.init) && ok;
  ok = write_metric(output, "activate", value.activate) && ok;
  ok = write_metric(output, "start", value.start) && ok;
  ok = write_metric(output, "reset", value.reset) && ok;
  ok = write_metric(output, "stop", value.stop) && ok;
  ok = write_metric(output, "deactivate", value.deactivate) && ok;
  ok = write_metric(output, "destroy", value.destroy) && ok;
  ok = write_metric(output, "CC119_trigger_one", value.trigger_one) && ok;
  ok = write_metric(output, "CC119_trigger_two", value.trigger_two) && ok;
  ok = write_metric(output, "trigger_overflow", value.trigger_overflow) && ok;
  ok = write_metric(output, "float32_seen", value.float32_seen ? 1U : 0U) && ok;
  ok = write_metric(output, "float64_seen", value.float64_seen ? 1U : 0U) && ok;
  ok = write_metric(output, "alias_seen", value.alias_seen ? 1U : 0U) && ok;
  ok = write_metric(output, "separate_seen", value.separate_seen ? 1U : 0U) && ok;
  ok = write_metric(output, "self_test_alias_passed",
                    value.self_test_alias_passed ? 1U : 0U) && ok;
  ok = write_metric(output, "self_test_separate_passed",
                    value.self_test_separate_passed ? 1U : 0U) && ok;
  ok = std::fflush(output) == 0 && ok;
  ok = fsync(fileno(output)) == 0 && ok;
  ok = std::fclose(output) == 0 && ok;
  if (!ok || std::rename(temporary.data(), report_path) != 0) {
    static_cast<void>(std::remove(temporary.data()));
    return false;
  }
  return true;
}

}  // namespace m3
