#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <vector>

#include "fake_vst3_host.hpp"
#include "m3/calibration_state_image.hpp"
#include "m3/factory_calibration.hpp"
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
            int sample_bits, std::uint32_t frames) {
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

template <typename Sample>
int replay(Instance& instance, const m3::offline::WaveData& wave,
           const m3::StringCalibrationBank& calibration, std::uint32_t block_size,
           bool trial, const char* events_path) {
  auto* component = static_cast<m3::vst3::M3Component*>(instance.processor);
  component->enable_corpus_ownership_trial(trial);
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
    if (instance.processor->process(block.data()) != Steinberg::kResultOk) {
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
      "\"processed_samples\":%llu,\"blocks\":%llu,"
      "\"detector_samples\":%llu,\"detector_transitions\":%llu,"
      "\"queue_rejections\":%llu,\"event_add_attempts\":%llu,"
      "\"accepted_events\":%llu,\"output_blocked_blocks\":%llu,"
      "\"dry_audio_mismatches\":%llu,\"process_failures\":%llu,"
      "\"output_blocked_at_eof\":%s,\"calibration_merge_matches\":%s,"
      "\"invalid_event\":%s,\"trace_write_failed\":%s,\"first_blocked_sample\":",
      static_cast<unsigned long long>(wave.mono_samples.size()), wave.sample_rate,
      sizeof(Sample) * 8U, block_size, trial ? "true" : "false",
      static_cast<unsigned long long>(processed), static_cast<unsigned long long>(blocks),
      static_cast<unsigned long long>(component->corpus_detector_samples()),
      static_cast<unsigned long long>(component->corpus_detector_transitions()),
      static_cast<unsigned long long>(component->corpus_queue_rejections()),
      static_cast<unsigned long long>(attempts), static_cast<unsigned long long>(accepted),
      static_cast<unsigned long long>(blocked_blocks), static_cast<unsigned long long>(dry_mismatches),
      static_cast<unsigned long long>(process_failures), component->corpus_output_blocked() ? "true" : "false",
      calibration_matches ? "true" : "false", invalid_event ? "true" : "false",
      write_failed || close_failed ? "true" : "false");
  if (first_blocked == std::numeric_limits<std::uint64_t>::max()) std::printf("null}");
  else std::printf("%llu}", static_cast<unsigned long long>(first_blocked));
  std::printf("\n");
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
  constexpr std::uint32_t block_size = 512U;
  for (int index = 1; index < argc; index += 2) {
    if (index + 1 >= argc) return 2;
    const char* value = argv[index + 1];
    if (std::strcmp(argv[index], "--wav") == 0) wav_path = value;
    else if (std::strcmp(argv[index], "--calibration") == 0) calibration_path = value;
    else if (std::strcmp(argv[index], "--events") == 0) events_path = value;
    else if (std::strcmp(argv[index], "--sample-bits") == 0 && std::strcmp(value, "32") == 0) sample_bits = 32;
    else if (std::strcmp(argv[index], "--sample-bits") == 0 && std::strcmp(value, "64") == 0) sample_bits = 64;
    else if (std::strcmp(argv[index], "--trial") == 0 && (std::strcmp(value, "0") == 0 || std::strcmp(value, "1") == 0)) {
      trial = std::strcmp(value, "1") == 0;
      trial_given = true;
    } else return 2;
  }
  if (wav_path == nullptr || calibration_path == nullptr || events_path == nullptr ||
      sample_bits == 0 || !trial_given) return 2;
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
  if (!instance.open(config, calibration, wave.sample_rate, sample_bits, block_size)) {
    std::fprintf(stderr, "VST3 component initialization or state restore failed.\n");
    return 2;
  }
  return sample_bits == 32 ? replay<float>(instance, wave, calibration, block_size, trial, events_path)
                           : replay<double>(instance, wave, calibration, block_size, trial, events_path);
}
