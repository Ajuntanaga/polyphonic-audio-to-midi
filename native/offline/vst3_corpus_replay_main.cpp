#include <algorithm>
#include <array>
#include <cstdint>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <vector>

#include "fake_vst3_host.hpp"
#include "test_support.hpp"
#include "offline_c_allocation_guard.hpp"
#include "m3/calibration_state_image.hpp"
#include "m3/factory_calibration.hpp"
#include "m3/parameter_contract.hpp"
#include "replay.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"
#include "vst3_state_stream.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct Instance final {
  m3::test::FakeVst3Host host;
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};

  ~Instance() {
    if (processor != nullptr) {
      static_cast<void>(processor->setProcessing(Steinberg::TBool{0}));
    }
    if (component != nullptr) {
      static_cast<void>(component->setActive(Steinberg::TBool{0}));
      static_cast<void>(component->terminate());
    }
    if (processor != nullptr) processor->release();
    if (component != nullptr) component->release();
    if (factory != nullptr) factory->release();
  }

  bool open(const m3::PersistentConfig& config,
            const m3::StringCalibrationBank& calibration, double sample_rate,
            int sample_bits, std::uint32_t frames, bool stable_note_identity) {
    factory = GetPluginFactory();
    if (factory == nullptr) return false;
    const auto& words = m3::vst3::kProbeClassIdWords;
    const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
    Steinberg::TUID class_id{};
    id.toTUID(class_id);
    if (factory->createInstance(class_id, Steinberg::Vst::IComponent::iid,
            reinterpret_cast<void**>(&component)) != Steinberg::kResultOk ||
        component == nullptr || component->initialize(&host) != Steinberg::kResultOk ||
        component->queryInterface(Steinberg::Vst::IAudioProcessor::iid,
            reinterpret_cast<void**>(&processor)) != Steinberg::kResultOk ||
        processor == nullptr) return false;
    if (!static_cast<m3::vst3::M3Component*>(processor)->
            enable_stable_note_identity_for_test(stable_note_identity)) return false;
    m3::test::FakeVst3Stream state;
    state.reset_output(8192);
    if (!m3::vst3::save_vst3_state_with_calibration(config, calibration, &state) ||
        state.seek(0, Steinberg::IBStream::kIBSeekSet, nullptr) != Steinberg::kResultOk ||
        component->setState(&state) != Steinberg::kResultOk) return false;
    Steinberg::Vst::SpeakerArrangement input_arrangement = Steinberg::Vst::SpeakerArr::kMono;
    Steinberg::Vst::SpeakerArrangement output_arrangement = Steinberg::Vst::SpeakerArr::kMono;
    if (processor->setBusArrangements(&input_arrangement, 1, &output_arrangement, 1) !=
        Steinberg::kResultOk) return false;
    Steinberg::Vst::ProcessSetup setup{};
    setup.processMode = Steinberg::Vst::kRealtime;
    setup.symbolicSampleSize = sample_bits == 32 ? Steinberg::Vst::kSample32
                                                : Steinberg::Vst::kSample64;
    setup.maxSamplesPerBlock = static_cast<Steinberg::int32>(frames);
    setup.sampleRate = sample_rate;
    return processor->setupProcessing(setup) == Steinberg::kResultOk &&
        component->setActive(Steinberg::TBool{1}) == Steinberg::kResultOk &&
        processor->setProcessing(Steinberg::TBool{1}) == Steinberg::kResultOk;
  }
};

bool read_bytes(const char* path, std::vector<std::uint8_t>& bytes) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input || input.tellg() <= 0 || input.tellg() > 512 * 1024 * 1024) return false;
  input.seekg(0);
  bytes.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
  return !input.bad();
}

// Reject one naturally generated note-off, then accept every later callback.
// The retained test event list supplies bounded storage; rejection state spans
// process blocks. This sink never inserts a detector transition itself.
class RejectFirstOff final : public Steinberg::Vst::IEventList {
 public:
  m3::test::FakeVst3EventList accepted;
  Steinberg::Vst::Event rejected_event{};
  bool rejected{};
  std::uint64_t attempts{};

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID interface_id, void** object) override {
    if (object == nullptr) return Steinberg::kInvalidArgument;
    *object = nullptr;
    if (Steinberg::FUnknownPrivate::iidEqual(interface_id, Steinberg::FUnknown::iid) ||
        Steinberg::FUnknownPrivate::iidEqual(interface_id, Steinberg::Vst::IEventList::iid)) {
      *object = static_cast<Steinberg::Vst::IEventList*>(this);
      addRef();
      return Steinberg::kResultOk;
    }
    return Steinberg::kNoInterface;
  }
  Steinberg::uint32 PLUGIN_API addRef() override { return ++references_; }
  Steinberg::uint32 PLUGIN_API release() override {
    if (references_ > 0U) --references_;
    return references_;
  }
  Steinberg::int32 PLUGIN_API getEventCount() override { return accepted.getEventCount(); }
  Steinberg::tresult PLUGIN_API getEvent(
      Steinberg::int32 index, Steinberg::Vst::Event& event) override {
    return accepted.getEvent(index, event);
  }
  Steinberg::tresult PLUGIN_API addEvent(Steinberg::Vst::Event& event) override {
    ++attempts;
    if (!rejected && event.type == Steinberg::Vst::Event::kNoteOffEvent) {
      rejected = true;
      rejected_event = event;
      return Steinberg::kResultFalse;
    }
    return accepted.addEvent(event);
  }

 private:
  Steinberg::uint32 references_{1};
};

struct RecoveryBoundary final {
  const char* name{};
  std::uint64_t timeline{}, recording{}, detector{}, transitions{}, accepted{}, attempts{}, transfers{};
  bool blocked{}, hold{};
};

template <typename Sample>
int replay_recovery(Instance& instance, const m3::offline::WaveData& wave,
                    const m3::StringCalibrationBank& calibration,
                    std::uint32_t block_size, bool stable_note_identity, const char* events_path) {
  auto* component = static_cast<m3::vst3::M3Component*>(instance.processor);
  component->enable_corpus_ownership_trial(true);
  m3::CalibrationStateImage restored_image{}, expected_image{};
  const bool calibration_matches = m3::encode_calibration_state(
      component->detector_calibration_bank_for_test(), restored_image) &&
      m3::encode_calibration_state(m3::merge_m3_factory_calibration(calibration), expected_image) &&
      restored_image == expected_image;
  std::FILE* events = std::fopen(events_path, "wb");
  if (events == nullptr) return 2;
  std::fprintf(events, "# m3_vst3_corpus_events_v1\nsample\tkind\tnote\tvelocity\tnote_id\tchannel\n");
  m3::test::FakeVst3ProcessBlock<Sample> block;
  m3::test::FakeVst3ParameterChanges parameters;
  RejectFirstOff output;
  std::uint64_t recording = 0, timeline = 0, accepted = 0, dry_mismatches = 0;
  std::uint64_t process_failures = 0, rejected_sample = 0, blocked_blocks = 0;
  bool invalid_event = false, unexpected_early_block = false;
  std::array<RecoveryBoundary, 5> boundaries{};
  std::size_t boundary_count = 0;
  const auto boundary = [&](const char* name) {
    boundaries[boundary_count++] = RecoveryBoundary{name, timeline, recording,
        component->corpus_detector_samples(), component->corpus_detector_transitions(),
        accepted, output.attempts, component->stable_note_transfers_for_test(),
        component->corpus_output_blocked(), component->corpus_panic_hold()};
  };
  const auto process = [&](bool silence, bool panic) {
    const auto frames = silence ? block_size : static_cast<std::uint32_t>(
        std::min<std::uint64_t>(block_size, wave.mono_samples.size() - recording));
    block.configure(frames, false);
    block.data().inputs[0].numChannels = 1;
    block.data().outputs[0].numChannels = 1;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      block.input_left()[frame] = silence ? Sample{} :
          static_cast<Sample>(wave.mono_samples[recording + frame]);
    }
    parameters.reset();
    if (panic && !parameters.append_input(m3::kPanicParameterId, 0, 1.0)) {
      ++process_failures;
      return false;
    }
    block.data().inputParameterChanges = panic ? &parameters : nullptr;
    output.accepted.reset();
    block.data().outputEvents = &output;
    const bool was_rejected = output.rejected;
    if (instance.processor->process(block.data()) != Steinberg::kResultOk) {
      ++process_failures;
      return false;
    }
    if (output.rejected && !was_rejected) {
      if (output.rejected_event.sampleOffset < 0 ||
          output.rejected_event.sampleOffset >= static_cast<Steinberg::int32>(frames)) {
        invalid_event = true;
      } else {
        rejected_sample = timeline + static_cast<std::uint32_t>(output.rejected_event.sampleOffset);
      }
    }
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      if (block.output_left()[frame] != block.input_left()[frame]) ++dry_mismatches;
    }
    for (std::size_t index = 0; index < output.accepted.stored_event_count(); ++index) {
      const auto& event = output.accepted.stored_event(index);
      const bool on = event.type == Steinberg::Vst::Event::kNoteOnEvent;
      if ((!on && event.type != Steinberg::Vst::Event::kNoteOffEvent) ||
          event.sampleOffset < 0 || event.sampleOffset >= static_cast<Steinberg::int32>(frames) ||
          event.busIndex != 0) {
        invalid_event = true;
        continue;
      }
      std::fprintf(events, "%llu\t%s\t%d\t%.9g\t%d\t%d\n",
          static_cast<unsigned long long>(timeline + static_cast<std::uint32_t>(event.sampleOffset)),
          on ? "on" : "off", static_cast<int>(on ? event.noteOn.pitch : event.noteOff.pitch),
          static_cast<double>(on ? event.noteOn.velocity : event.noteOff.velocity),
          static_cast<int>(on ? event.noteOn.noteId : event.noteOff.noteId),
          static_cast<int>(on ? event.noteOn.channel : event.noteOff.channel));
      ++accepted;
    }
    if (component->corpus_output_blocked()) ++blocked_blocks;
    timeline += frames;
    if (!silence) recording += frames;
    return true;
  };
  while (recording < wave.mono_samples.size() && !output.rejected) {
    if (!process(false, false)) break;
    if (component->corpus_output_blocked() && !output.rejected) {
      unexpected_early_block = true;
      break;
    }
  }
  boundary("fault");
  // Insert, rather than replace, three silent blocks. First observe cleanup
  // without recovery. Then request the real Panic parameter and allow its
  // mandatory quiet hold to finish. Resume the next untouched recording sample.
  if (output.rejected && process_failures == 0) {
    if (process(true, false)) boundary("cleanup");
    if (process_failures == 0 && process(true, true)) boundary("panic");
    if (process_failures == 0 && process(true, false)) boundary("ready");
    while (process_failures == 0 && recording < wave.mono_samples.size()) {
      if (!process(false, false)) break;
    }
  }
  boundary("end");
  const bool write_failed = std::ferror(events) != 0;
  const bool close_failed = std::fclose(events) != 0;
  std::printf("{\"schema\":\"m3_vst3_recovery_native_v1\","
      "\"scenario\":\"reject-off-panic\",\"trial\":true,\"routing\":\"per_voice\","
      "\"stable_note_identity\":%s,"
      "\"sample_count\":%llu,\"sample_rate\":%u,\"sample_bits\":%zu,\"block_samples\":%u,"
      "\"queue_rejections\":%llu,\"output_blocked_blocks\":%llu,"
      "\"dry_audio_mismatches\":%llu,\"process_failures\":%llu,"
      "\"rejection_injected\":%s,\"unexpected_early_block\":%s,"
      "\"calibration_merge_matches\":%s,\"invalid_event\":%s,\"trace_write_failed\":%s,"
      "\"rejected_event\":{\"sample\":%llu,\"note\":%d,\"note_id\":%d,\"channel\":%d},"
      "\"boundaries\":[",
      stable_note_identity ? "true" : "false",
      static_cast<unsigned long long>(wave.mono_samples.size()), wave.sample_rate,
      sizeof(Sample) * 8U, block_size,
      static_cast<unsigned long long>(component->corpus_queue_rejections()),
      static_cast<unsigned long long>(blocked_blocks),
      static_cast<unsigned long long>(dry_mismatches), static_cast<unsigned long long>(process_failures),
      output.rejected ? "true" : "false", unexpected_early_block ? "true" : "false",
      calibration_matches ? "true" : "false", invalid_event ? "true" : "false",
      write_failed || close_failed ? "true" : "false",
      static_cast<unsigned long long>(rejected_sample), static_cast<int>(output.rejected_event.noteOff.pitch),
      static_cast<int>(output.rejected_event.noteOff.noteId), static_cast<int>(output.rejected_event.noteOff.channel));
  for (std::size_t index = 0; index < boundary_count; ++index) {
    const auto& value = boundaries[index];
    std::printf("%s{\"name\":\"%s\",\"timeline_samples\":%llu,\"recording_samples\":%llu,"
        "\"detector_samples\":%llu,\"detector_transitions\":%llu,"
        "\"accepted_events\":%llu,\"event_add_attempts\":%llu,\"transferred_pairs\":%llu,"
        "\"output_blocked\":%s,\"panic_hold\":%s}", index == 0 ? "" : ",", value.name,
        static_cast<unsigned long long>(value.timeline), static_cast<unsigned long long>(value.recording),
        static_cast<unsigned long long>(value.detector), static_cast<unsigned long long>(value.transitions),
        static_cast<unsigned long long>(value.accepted), static_cast<unsigned long long>(value.attempts),
        static_cast<unsigned long long>(value.transfers),
        value.blocked ? "true" : "false", value.hold ? "true" : "false");
  }
  std::printf("]}\n");
  return process_failures != 0 || invalid_event || write_failed || close_failed ||
      !calibration_matches ? 2 : 0;
}

template <typename Sample>
int replay(Instance& instance, const m3::offline::WaveData& wave,
           const m3::StringCalibrationBank& calibration, std::uint32_t block_size,
           bool trial, bool completion_midi_retention, bool stable_note_identity, bool measure_process, const char* events_path) {
  auto* component = static_cast<m3::vst3::M3Component*>(instance.processor);
  component->enable_corpus_ownership_trial(trial);
  component->enable_corpus_completion_midi_retention(completion_midi_retention);
  const auto restored = component->detector_calibration_bank_for_test();
  m3::CalibrationStateImage restored_image{}, expected_image{};
  const bool calibration_matches = m3::encode_calibration_state(restored, restored_image) &&
      m3::encode_calibration_state(m3::merge_m3_factory_calibration(calibration), expected_image) &&
      restored_image == expected_image;
  std::FILE* events = std::fopen(events_path, "wb");
  if (events == nullptr) return 2;
  std::fprintf(events, "# m3_vst3_corpus_events_v1\nsample\tkind\tnote\tvelocity\tnote_id\tchannel\n");
  m3::test::FakeVst3ProcessBlock<Sample> block;
  m3::test::FakeVst3EventList output;
  std::uint64_t processed = 0, blocks = 0, accepted = 0, attempts = 0;
  std::uint64_t blocked_blocks = 0, dry_mismatches = 0, process_failures = 0;
  std::uint64_t first_blocked = std::numeric_limits<std::uint64_t>::max();
  bool invalid_event = false;
  // Storage, trace serialization and input copying are outside process().
  // Include cold blocks and the final partial block; no timing warmup is hidden.
  std::vector<std::uint64_t> durations(measure_process ?
      (wave.mono_samples.size() + block_size - 1U) / block_size : 0U);
  std::uint64_t measured_blocks = 0, deadline_overruns = 0;
  std::uint64_t cpp_allocations = 0, cpp_frees = 0, c_allocations = 0, c_frees = 0;
  while (processed < wave.mono_samples.size()) {
    const auto frames = static_cast<std::uint32_t>(std::min<std::uint64_t>(
        block_size, wave.mono_samples.size() - processed));
    block.configure(frames, false);
    // One mono bus avoids stereo summing or channel-selection differences.
    block.data().inputs[0].numChannels = 1;
    block.data().outputs[0].numChannels = 1;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      block.input_left()[frame] = static_cast<Sample>(wave.mono_samples[processed + frame]);
    }
    output.reset();
    block.data().outputEvents = &output;
    Steinberg::tresult process_result;
    if (measure_process) {
      const auto cpp_before = m3::test::allocation_count();
      const auto cpp_free_before = m3::test::deallocation_count();
      const auto c_before = m3::test::c_allocation_count();
      const auto c_free_before = m3::test::c_deallocation_count();
      const auto start = std::chrono::steady_clock::now();
      process_result = instance.processor->process(block.data());
      const auto elapsed = static_cast<std::uint64_t>(std::chrono::duration_cast<
          std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count());
      cpp_allocations += m3::test::allocation_count() - cpp_before;
      cpp_frees += m3::test::deallocation_count() - cpp_free_before;
      c_allocations += m3::test::c_allocation_count() - c_before;
      c_frees += m3::test::c_deallocation_count() - c_free_before;
      durations[measured_blocks++] = elapsed;
      deadline_overruns += elapsed > static_cast<std::uint64_t>(frames) *
          1000000000ULL / wave.sample_rate ? 1U : 0U;
    } else {
      process_result = instance.processor->process(block.data());
    }
    if (process_result != Steinberg::kResultOk) {
      ++process_failures;
      break;
    }
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      if (block.output_left()[frame] != block.input_left()[frame]) ++dry_mismatches;
    }
    attempts += output.add_attempt_count();
    for (std::size_t index = 0; index < output.stored_event_count(); ++index) {
      const auto& event = output.stored_event(index);
      const bool on = event.type == Steinberg::Vst::Event::kNoteOnEvent;
      if ((!on && event.type != Steinberg::Vst::Event::kNoteOffEvent) ||
          event.sampleOffset < 0 || event.sampleOffset >= static_cast<Steinberg::int32>(frames) ||
          event.busIndex != 0) {
        invalid_event = true;
        continue;
      }
      const auto note = on ? event.noteOn.pitch : event.noteOff.pitch;
      const auto velocity = on ? event.noteOn.velocity : event.noteOff.velocity;
      const auto note_id = on ? event.noteOn.noteId : event.noteOff.noteId;
      const auto channel = on ? event.noteOn.channel : event.noteOff.channel;
      std::fprintf(events, "%llu\t%s\t%d\t%.9g\t%d\t%d\n",
          static_cast<unsigned long long>(processed + static_cast<std::uint32_t>(event.sampleOffset)),
          on ? "on" : "off", static_cast<int>(note), static_cast<double>(velocity),
          static_cast<int>(note_id), static_cast<int>(channel));
      ++accepted;
    }
    if (component->corpus_output_blocked()) {
      ++blocked_blocks;
      if (first_blocked == std::numeric_limits<std::uint64_t>::max()) first_blocked = processed;
    }
    ++blocks;
    processed += frames;
  }
  const bool write_failed = std::ferror(events) != 0;
  const bool close_failed = std::fclose(events) != 0;
  std::printf("{\"schema\":\"m3_vst3_corpus_native_v1\","
      "\"sample_count\":%llu,\"sample_rate\":%u,\"sample_bits\":%zu,"
      "\"block_samples\":%u,\"trial\":%s,\"routing\":\"per_voice\","
      "\"completion_midi_retention\":%s,\"stable_note_identity\":%s,\"transferred_pairs\":%llu,"
      "\"processed_samples\":%llu,\"blocks\":%llu,"
      "\"detector_samples\":%llu,\"detector_transitions\":%llu,"
      "\"queue_rejections\":%llu,\"event_add_attempts\":%llu,"
      "\"accepted_events\":%llu,\"output_blocked_blocks\":%llu,"
      "\"dry_audio_mismatches\":%llu,\"process_failures\":%llu,"
      "\"output_blocked_at_eof\":%s,\"calibration_merge_matches\":%s,"
      "\"invalid_event\":%s,\"trace_write_failed\":%s,\"first_blocked_sample\":",
      static_cast<unsigned long long>(wave.mono_samples.size()), wave.sample_rate,
      sizeof(Sample) * 8U, block_size, trial ? "true" : "false",
      completion_midi_retention ? "true" : "false", stable_note_identity ? "true" : "false",
      static_cast<unsigned long long>(component->stable_note_transfers_for_test()),
      static_cast<unsigned long long>(processed), static_cast<unsigned long long>(blocks),
      static_cast<unsigned long long>(component->corpus_detector_samples()),
      static_cast<unsigned long long>(component->corpus_detector_transitions()),
      static_cast<unsigned long long>(component->corpus_queue_rejections()),
      static_cast<unsigned long long>(attempts), static_cast<unsigned long long>(accepted),
      static_cast<unsigned long long>(blocked_blocks), static_cast<unsigned long long>(dry_mismatches),
      static_cast<unsigned long long>(process_failures), component->corpus_output_blocked() ? "true" : "false",
      calibration_matches ? "true" : "false", invalid_event ? "true" : "false",
      write_failed || close_failed ? "true" : "false");
  if (first_blocked == std::numeric_limits<std::uint64_t>::max()) std::printf("null");
  else std::printf("%llu", static_cast<unsigned long long>(first_blocked));
  std::printf(",\"process_measurement\":");
  if (!measure_process) std::printf("null");
  else {
    durations.resize(static_cast<std::size_t>(measured_blocks));
    std::sort(durations.begin(), durations.end());
    const auto p99 = durations.empty() ? 0U : durations[(durations.size() * 99U + 99U) / 100U - 1U];
    const auto maximum = durations.empty() ? 0U : durations.back();
    std::printf("{\"scope\":\"instrumented_vst3_process_with_accepting_test_sink\","
        "\"clock\":\"steady_clock\",\"cold_blocks_included\":true,\"blocks\":%llu,"
        "\"p99_ns\":%llu,\"max_ns\":%llu,\"deadline_overruns\":%llu,"
        "\"allocation_guard\":true,\"cpp_allocations\":%llu,\"cpp_frees\":%llu,"
        "\"c_allocations\":%llu,\"c_frees\":%llu}",
        static_cast<unsigned long long>(measured_blocks), static_cast<unsigned long long>(p99),
        static_cast<unsigned long long>(maximum), static_cast<unsigned long long>(deadline_overruns),
        static_cast<unsigned long long>(cpp_allocations), static_cast<unsigned long long>(cpp_frees),
        static_cast<unsigned long long>(c_allocations), static_cast<unsigned long long>(c_frees));
  }
  std::printf("}\n");
  // EOF is observed before teardown. No silence, panic or forced release is injected.
  return process_failures != 0 || invalid_event || write_failed || close_failed ||
      !calibration_matches ? 2 : 0;
}

}  // namespace

int main(int argc, char** argv) {
  const char* wav_path = nullptr;
  const char* calibration_path = nullptr;
  const char* events_path = nullptr;
  int sample_bits = 0;
  bool trial = false, trial_given = false;
  bool completion_midi_retention = false;
  bool stable_note_identity = false;
  bool recovery = false;
  std::uint32_t block_size = 512U;
  bool measure_process = false;
  for (int index = 1; index < argc; index += 2) {
    if (index + 1 >= argc) return 2;
    const char* value = argv[index + 1];
    if (std::strcmp(argv[index], "--wav") == 0) wav_path = value;
    else if (std::strcmp(argv[index], "--calibration") == 0) calibration_path = value;
    else if (std::strcmp(argv[index], "--events") == 0) events_path = value;
    else if (std::strcmp(argv[index], "--sample-bits") == 0 && std::strcmp(value, "32") == 0) sample_bits = 32;
    else if (std::strcmp(argv[index], "--sample-bits") == 0 && std::strcmp(value, "64") == 0) sample_bits = 64;
    else if (std::strcmp(argv[index], "--block") == 0 && std::strcmp(value, "32") == 0) block_size = 32U;
    else if (std::strcmp(argv[index], "--block") == 0 && std::strcmp(value, "512") == 0) block_size = 512U;
    else if (std::strcmp(argv[index], "--block") == 0 && std::strcmp(value, "1024") == 0) block_size = 1024U;
    else if (std::strcmp(argv[index], "--measure-process") == 0 && std::strcmp(value, "1") == 0) measure_process = true;
    else if (std::strcmp(argv[index], "--trial") == 0 && (std::strcmp(value, "0") == 0 || std::strcmp(value, "1") == 0)) {
      trial = std::strcmp(value, "1") == 0;
      trial_given = true;
    } else if (std::strcmp(argv[index], "--completion-midi-retention") == 0 &&
               (std::strcmp(value, "0") == 0 || std::strcmp(value, "1") == 0)) {
      completion_midi_retention = std::strcmp(value, "1") == 0;
    } else if (std::strcmp(argv[index], "--stable-note-identity") == 0 &&
               (std::strcmp(value, "0") == 0 || std::strcmp(value, "1") == 0)) {
      stable_note_identity = std::strcmp(value, "1") == 0;
    } else if (std::strcmp(argv[index], "--scenario") == 0 && std::strcmp(value, "reject-off-panic") == 0) {
      recovery = true;
    } else return 2;
  }
  if (wav_path == nullptr || calibration_path == nullptr || events_path == nullptr ||
      sample_bits == 0 || !trial_given) return 2;
  if (recovery && (measure_process || block_size != 512U)) return 2;
  if ((recovery || stable_note_identity) && !trial) return 2;
  if (stable_note_identity && completion_midi_retention) return 2;
  if (completion_midi_retention && (!trial || recovery)) return 2;
  std::vector<std::uint8_t> bytes;
  m3::offline::WaveData wave;
  m3::offline::ReplayError wave_error{};
  if (!read_bytes(wav_path, bytes) ||
      !m3::offline::decode_wave_bytes(bytes.data(), bytes.size(), wave, wave_error) ||
      wave.source_channels != 1U || wave.mono_samples.empty()) {
    std::fprintf(stderr, "Expected a finite mono WAV.\n");
    return 2;
  }
  m3::PersistentConfig config;
  m3::StringCalibrationBank calibration;
  if (!read_bytes(calibration_path, bytes)) return 2;
  std::size_t offset = 0;
  if (bytes.size() == m3::kStateSize + m3::kCalibrationStateSize ||
      bytes.size() == m3::kStateSize + m3::kCalibrationStateV1Size) {
    if (!m3::decode_state(bytes.data(), m3::kStateSize, config)) return 2;
    offset = m3::kStateSize;
  }
  if (!m3::decode_calibration_state(bytes.data() + offset, bytes.size() - offset, calibration)) return 2;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.midi_channel = 1;
  config.a4_hz = 440.0;
  config.input_trim_db = -9.0;
  config.sensitivity = 60;
  config.response = 75;
  config.max_polyphony = 5;
  config.max_fret = 24;
  config.dry_passthrough = true;
  Instance instance;
  if (!instance.open(config, calibration, wave.sample_rate, sample_bits, block_size, stable_note_identity)) {
    std::fprintf(stderr, "VST3 component initialization or state restore failed.\n");
    return 2;
  }
  if (recovery) {
    return sample_bits == 32 ? replay_recovery<float>(instance, wave, calibration, block_size, stable_note_identity, events_path)
                            : replay_recovery<double>(instance, wave, calibration, block_size, stable_note_identity, events_path);
  }
  return sample_bits == 32 ? replay<float>(instance, wave, calibration, block_size,
                                         trial, completion_midi_retention, stable_note_identity, measure_process, events_path)
                           : replay<double>(instance, wave, calibration, block_size,
                                          trial, completion_midi_retention, stable_note_identity, measure_process, events_path);
}
