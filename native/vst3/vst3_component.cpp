#include "vst3_component.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <new>
#include <type_traits>

#include "dry_path.hpp"
#include "m3/constants.hpp"
#include "pluginterfaces/base/fstrdefs.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"
#include "pluginterfaces/vst/vstspeaker.h"

namespace m3::vst3 {
namespace {

constexpr Steinberg::int32 kMidiChannels = 16;

#if defined(M3_TESTING)
std::atomic<std::uint32_t> constructed_count{};
std::atomic<std::uint32_t> initialized_count{};
std::atomic<std::uint32_t> terminated_count{};
std::atomic<std::uint32_t> destroyed_count{};
#endif

bool is_boolean(Steinberg::TBool state) noexcept {
  return state == Steinberg::TBool{0} || state == Steinberg::TBool{1};
}

bool is_process_mode(Steinberg::int32 mode) noexcept {
  return mode == Steinberg::Vst::kRealtime ||
         mode == Steinberg::Vst::kPrefetch || mode == Steinberg::Vst::kOffline;
}

}  // namespace

M3Component::M3Component() noexcept {
#if defined(M3_TESTING)
  constructed_count.fetch_add(1U, std::memory_order_relaxed);
#endif
}

M3Component::~M3Component() {
#if defined(M3_TESTING)
  destroyed_count.fetch_add(1U, std::memory_order_relaxed);
#endif
}

Steinberg::FUnknown* M3Component::createInstance(void*) noexcept {
  M3Component* component = new (std::nothrow) M3Component;
  return static_cast<Steinberg::Vst::IAudioProcessor*>(component);
}

Steinberg::tresult PLUGIN_API M3Component::initialize(
    Steinberg::FUnknown* context) {
  if (initialized_ || context == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::tresult result = SingleComponentEffect::initialize(context);
  if (result != Steinberg::kResultOk) {
    return result;
  }

  addAudioInput(STR16("Stereo Input"), Steinberg::Vst::SpeakerArr::kStereo,
                Steinberg::Vst::kMain,
                Steinberg::Vst::BusInfo::kDefaultActive);
  addAudioOutput(STR16("Stereo Output"), Steinberg::Vst::SpeakerArr::kStereo,
                 Steinberg::Vst::kMain,
                 Steinberg::Vst::BusInfo::kDefaultActive);
  addEventOutput(STR16("MIDI Output"), kMidiChannels, Steinberg::Vst::kMain,
                 Steinberg::Vst::BusInfo::kDefaultActive);
  initialized_ = true;
  status_ = Status::ready;
#if defined(M3_TESTING)
  initialized_count.fetch_add(1U, std::memory_order_relaxed);
#endif
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::terminate() {
  if (!initialized_ || active_ || processing_) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::tresult result = SingleComponentEffect::terminate();
  if (result != Steinberg::kResultOk) {
    return result;
  }
  initialized_ = false;
  setup_complete_ = false;
  status_ = Status::ready;
#if defined(M3_TESTING)
  terminated_count.fetch_add(1U, std::memory_order_relaxed);
#endif
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::setBusArrangements(
    Steinberg::Vst::SpeakerArrangement* inputs, Steinberg::int32 num_inputs,
    Steinberg::Vst::SpeakerArrangement* outputs,
    Steinberg::int32 num_outputs) {
  if (!initialized_ || active_ || inputs == nullptr || outputs == nullptr ||
      num_inputs != 1 || num_outputs != 1 ||
      inputs[0] != Steinberg::Vst::SpeakerArr::kStereo ||
      outputs[0] != Steinberg::Vst::SpeakerArr::kStereo) {
    return Steinberg::kResultFalse;
  }
  return SingleComponentEffect::setBusArrangements(inputs, num_inputs, outputs,
                                                    num_outputs);
}

Steinberg::tresult PLUGIN_API M3Component::canProcessSampleSize(
    Steinberg::int32 symbolic_sample_size) {
  return symbolic_sample_size == Steinberg::Vst::kSample32 ||
                 symbolic_sample_size == Steinberg::Vst::kSample64
             ? Steinberg::kResultTrue
             : Steinberg::kResultFalse;
}

Steinberg::tresult PLUGIN_API M3Component::setupProcessing(
    Steinberg::Vst::ProcessSetup& setup) {
  if (!initialized_ || active_ || processing_ ||
      !is_process_mode(setup.processMode) || !std::isfinite(setup.sampleRate) ||
      setup.sampleRate <= 0.0 || setup.maxSamplesPerBlock <= 0 ||
      static_cast<std::uint32_t>(setup.maxSamplesPerBlock) > kMaxHostFrames ||
      canProcessSampleSize(setup.symbolicSampleSize) != Steinberg::kResultTrue) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::tresult result =
      SingleComponentEffect::setupProcessing(setup);
  if (result == Steinberg::kResultOk) {
    setup_complete_ = true;
  }
  return result;
}

Steinberg::tresult PLUGIN_API M3Component::setActive(Steinberg::TBool state) {
  if (!is_boolean(state) || !initialized_ || !setup_complete_) {
    return Steinberg::kInvalidArgument;
  }
  if (state == Steinberg::TBool{1}) {
    if (active_ || processing_) {
      return Steinberg::kResultFalse;
    }
    active_ = true;
    status_ = Status::ready;
    return Steinberg::kResultOk;
  }
  if (!active_ || processing_) {
    return Steinberg::kResultFalse;
  }
  active_ = false;
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::setProcessing(
    Steinberg::TBool state) {
  if (!is_boolean(state) || !initialized_ || !setup_complete_ || !active_) {
    return Steinberg::kInvalidArgument;
  }
  if (state == Steinberg::TBool{1}) {
    if (processing_) {
      return Steinberg::kResultFalse;
    }
    processing_ = true;
    return Steinberg::kResultOk;
  }
  if (!processing_) {
    return Steinberg::kResultFalse;
  }
  processing_ = false;
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::process(
    Steinberg::Vst::ProcessData& data) {
  if (!processing_ || data.numSamples < 0 ||
      data.numSamples > processSetup.maxSamplesPerBlock ||
      static_cast<std::uint32_t>(data.numSamples) > kMaxHostFrames) {
    status_ = Status::invalid_input_or_state;
    return Steinberg::kInvalidArgument;
  }
  if (data.symbolicSampleSize != processSetup.symbolicSampleSize) {
    status_ = Status::invalid_input_or_state;
    return Steinberg::kInvalidArgument;
  }
  if (data.numSamples == 0) {
    return Steinberg::kResultOk;
  }
  if (data.symbolicSampleSize == Steinberg::Vst::kSample32) {
    return process_samples<Steinberg::Vst::Sample32>(data);
  }
  if (data.symbolicSampleSize == Steinberg::Vst::kSample64) {
    return process_samples<Steinberg::Vst::Sample64>(data);
  }
  status_ = Status::invalid_input_or_state;
  return Steinberg::kInvalidArgument;
}

template <typename Sample>
Steinberg::tresult M3Component::process_samples(
    Steinberg::Vst::ProcessData& data) noexcept {
  bool valid_layout = data.numInputs == 1 && data.numOutputs == 1 &&
                      data.inputs != nullptr && data.outputs != nullptr;
  Sample** input_channels = nullptr;
  Sample** output_channels = nullptr;
  if (valid_layout) {
    Steinberg::Vst::AudioBusBuffers& input = data.inputs[0];
    Steinberg::Vst::AudioBusBuffers& output = data.outputs[0];
    valid_layout = input.numChannels == 2 && output.numChannels == 2;
    if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
      input_channels = input.channelBuffers32;
      output_channels = output.channelBuffers32;
    } else {
      input_channels = input.channelBuffers64;
      output_channels = output.channelBuffers64;
    }
    valid_layout = valid_layout && input_channels != nullptr &&
                   output_channels != nullptr;
  }
  if (valid_layout) {
    valid_layout = input_channels[0] != nullptr && input_channels[1] != nullptr &&
                   output_channels[0] != nullptr &&
                   output_channels[1] != nullptr &&
                   input_channels[0] != input_channels[1] &&
                   output_channels[0] != output_channels[1];
  }
  if (!valid_layout) {
    status_ = Status::unsupported_layout;
    zero_available_output<Sample>(data);
    return Steinberg::kResultOk;
  }

  const DryPathResult result = process_dry_path(
      input_channels, 2U, output_channels, 2U,
      static_cast<std::uint32_t>(data.numSamples), dry_passthrough_,
      DetectorInput::left);
  if (result.nonfinite_input) {
    status_ = Status::invalid_input_or_state;
  }
  return Steinberg::kResultOk;
}

template <typename Sample>
void M3Component::zero_available_output(
    Steinberg::Vst::ProcessData& data) noexcept {
  if (data.numOutputs <= 0 || data.outputs == nullptr) {
    return;
  }
  Steinberg::Vst::AudioBusBuffers& output = data.outputs[0];
  const Steinberg::int32 channel_count =
      std::clamp(output.numChannels, Steinberg::int32{0}, Steinberg::int32{2});
  Sample** channels = nullptr;
  if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
    channels = output.channelBuffers32;
  } else {
    channels = output.channelBuffers64;
  }
  if (channels == nullptr) {
    return;
  }
  for (Steinberg::int32 channel = 0; channel < channel_count; ++channel) {
    if (channels[channel] != nullptr) {
      std::fill_n(channels[channel], data.numSamples, static_cast<Sample>(0));
      output.silenceFlags |= Steinberg::uint64{1} << channel;
    }
  }
}

#if defined(M3_TESTING)
void reset_lifecycle_counters_for_test() noexcept {
  constructed_count.store(0U, std::memory_order_relaxed);
  initialized_count.store(0U, std::memory_order_relaxed);
  terminated_count.store(0U, std::memory_order_relaxed);
  destroyed_count.store(0U, std::memory_order_relaxed);
}

LifecycleCounters lifecycle_counters_for_test() noexcept {
  return LifecycleCounters{
      constructed_count.load(std::memory_order_relaxed),
      initialized_count.load(std::memory_order_relaxed),
      terminated_count.load(std::memory_order_relaxed),
      destroyed_count.load(std::memory_order_relaxed),
  };
}

void set_dry_passthrough_for_test(
    Steinberg::Vst::IAudioProcessor* processor, bool enabled) noexcept {
  if (processor != nullptr) {
    static_cast<M3Component*>(processor)->set_dry_passthrough_for_test(enabled);
  }
}

Status status_for_test(Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)->status_for_test()
             : Status::invalid_input_or_state;
}
#endif

}  // namespace m3::vst3
