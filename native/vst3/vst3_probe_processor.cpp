#include "vst3_probe_processor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <limits>
#include <new>
#include <type_traits>

#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "public.sdk/source/vst/vstparameters.h"

namespace m3::vst3 {
namespace {

enum class ProbeMetric : std::size_t {
  create,
  initialize,
  setup,
  activate,
  start,
  process,
  stop,
  deactivate,
  terminate,
  destroy,
  reset,
  float32_seen,
  float64_seen,
  alias_seen,
  separate_seen,
  sample_rate_bits,
  maximum_block,
  trigger_one,
  trigger_two,
  trigger_overflow,
  trigger_fault,
  count,
};

constexpr std::size_t kMetricCount =
    static_cast<std::size_t>(ProbeMetric::count);
constexpr double kCounterMaximum = 1048576.0;
constexpr double kSampleRateMaximum = 384000.0;
constexpr double kBlockMaximum = 16384.0;
constexpr double kCodeTolerance = 1.0e-6;
constexpr std::uint8_t kDiagnosticPublishAttemptLimit = 4U;

struct MetricParameterSpec final {
  ProbeMetric metric;
  const char* name;
  double maximum;
};

constexpr std::array<MetricParameterSpec, kMetricCount>
    kMetricParameters{{
        {ProbeMetric::create, "Probe create", kCounterMaximum},
        {ProbeMetric::initialize, "Probe initialize", kCounterMaximum},
        {ProbeMetric::setup, "Probe setup", kCounterMaximum},
        {ProbeMetric::activate, "Probe activate", kCounterMaximum},
        {ProbeMetric::start, "Probe start", kCounterMaximum},
        {ProbeMetric::process, "Probe process", kCounterMaximum},
        {ProbeMetric::stop, "Probe stop", kCounterMaximum},
        {ProbeMetric::deactivate, "Probe deactivate", kCounterMaximum},
        {ProbeMetric::terminate, "Probe terminate", kCounterMaximum},
        {ProbeMetric::destroy, "Probe destroy", kCounterMaximum},
        {ProbeMetric::reset, "Probe reset", kCounterMaximum},
        {ProbeMetric::float32_seen, "Probe float32", kCounterMaximum},
        {ProbeMetric::float64_seen, "Probe float64", kCounterMaximum},
        {ProbeMetric::alias_seen, "Probe alias", kCounterMaximum},
        {ProbeMetric::separate_seen, "Probe separate", kCounterMaximum},
        {ProbeMetric::sample_rate_bits, "Probe sample rate",
         kSampleRateMaximum},
        {ProbeMetric::maximum_block, "Probe maximum block", kBlockMaximum},
        {ProbeMetric::trigger_one, "Probe trigger one", kCounterMaximum},
        {ProbeMetric::trigger_two, "Probe trigger two", kCounterMaximum},
        {ProbeMetric::trigger_overflow, "Probe trigger overflow",
         kCounterMaximum},
        {ProbeMetric::trigger_fault, "Probe trigger fault", kCounterMaximum},
    }};

std::array<std::atomic<std::uint64_t>, kMetricCount> diagnostics{};

constexpr std::size_t metric_index(ProbeMetric metric) noexcept {
  return static_cast<std::size_t>(metric);
}

void increment(ProbeMetric metric) noexcept {
  diagnostics[metric_index(metric)].fetch_add(1U,
                                               std::memory_order_relaxed);
}

std::uint64_t load(ProbeMetric metric) noexcept {
  return diagnostics[metric_index(metric)].load(std::memory_order_relaxed);
}

std::uint64_t double_bits(double value) noexcept {
  std::uint64_t bits = 0U;
  static_assert(sizeof(bits) == sizeof(value));
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

double bits_double(std::uint64_t bits) noexcept {
  double value = 0.0;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

void store_sample_rate(double sample_rate) noexcept {
  diagnostics[metric_index(ProbeMetric::sample_rate_bits)]
      .store(double_bits(sample_rate), std::memory_order_relaxed);
}

void store_maximum_block(std::uint32_t frames) noexcept {
  diagnostics[metric_index(ProbeMetric::maximum_block)]
      .store(frames, std::memory_order_relaxed);
}

bool same_code(double actual, double expected) noexcept {
  return std::isfinite(actual) && std::abs(actual - expected) <= kCodeTolerance;
}

bool code_matches(const std::array<ProbeStereoCode, 3>& actual,
                  const std::array<ProbeStereoCode, 3>& expected) noexcept {
  for (std::size_t index = 0; index < actual.size(); ++index) {
    if (!same_code(actual[index].left, expected[index].left) ||
        !same_code(actual[index].right, expected[index].right)) {
      return false;
    }
  }
  return true;
}

bool result_ok(Steinberg::tresult result) noexcept {
  return result == Steinberg::kResultOk ||
         result == Steinberg::kResultTrue;
}

bool push_diagnostic_value(Steinberg::Vst::IParameterChanges* output,
                           Steinberg::Vst::ParamID id,
                           double normalized) noexcept {
  if (output == nullptr || !std::isfinite(normalized) || normalized < 0.0 ||
      normalized > 1.0) {
    return false;
  }
  Steinberg::int32 queue_index = -1;
  Steinberg::Vst::IParamValueQueue* queue =
      output->addParameterData(id, queue_index);
  if (queue == nullptr || queue_index < 0) {
    return false;
  }
  Steinberg::int32 point_index = -1;
  return result_ok(queue->addPoint(0, normalized, point_index)) &&
         point_index >= 0;
}

double metric_plain_value(ProbeMetric metric) noexcept {
  if (metric == ProbeMetric::sample_rate_bits) {
    return bits_double(load(metric));
  }
  return static_cast<double>(load(metric));
}

ProbeDiagnosticsSnapshot snapshot() noexcept {
  return ProbeDiagnosticsSnapshot{
      load(ProbeMetric::create),
      load(ProbeMetric::initialize),
      load(ProbeMetric::setup),
      load(ProbeMetric::activate),
      load(ProbeMetric::start),
      load(ProbeMetric::process),
      load(ProbeMetric::stop),
      load(ProbeMetric::deactivate),
      load(ProbeMetric::terminate),
      load(ProbeMetric::destroy),
      load(ProbeMetric::reset),
      load(ProbeMetric::float32_seen),
      load(ProbeMetric::float64_seen),
      load(ProbeMetric::alias_seen),
      load(ProbeMetric::separate_seen),
      bits_double(load(ProbeMetric::sample_rate_bits)),
      static_cast<std::uint32_t>(load(ProbeMetric::maximum_block)),
      load(ProbeMetric::trigger_one),
      load(ProbeMetric::trigger_two),
      load(ProbeMetric::trigger_overflow),
      load(ProbeMetric::trigger_fault),
  };
}

}  // namespace

M3ProbeProcessor::M3ProbeProcessor() noexcept { increment(ProbeMetric::create); }

M3ProbeProcessor::~M3ProbeProcessor() { increment(ProbeMetric::destroy); }

Steinberg::FUnknown* M3ProbeProcessor::createInstance(void*) noexcept {
  M3ProbeProcessor* component = new (std::nothrow) M3ProbeProcessor;
  return static_cast<Steinberg::Vst::IAudioProcessor*>(component);
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::initialize(
    Steinberg::FUnknown* context) {
  const Steinberg::tresult result = M3Component::initialize(context);
  if (result != Steinberg::kResultOk) {
    return result;
  }
  if (!register_diagnostic_parameters()) {
    static_cast<void>(M3Component::terminate());
    return Steinberg::kOutOfMemory;
  }
  reset_trigger_state(true);
  diagnostics_published_ = false;
  probe_setup_complete_ = false;
  probe_processing_ = false;
  diagnostic_publish_attempts_ = 0U;
  probe_process_mode_ = 0;
  probe_sample_size_ = 0;
  probe_maximum_block_ = 0U;
  increment(ProbeMetric::initialize);
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::terminate() {
  const Steinberg::tresult result = M3Component::terminate();
  if (result == Steinberg::kResultOk) {
    probe_setup_complete_ = false;
    probe_processing_ = false;
    probe_maximum_block_ = 0U;
    increment(ProbeMetric::terminate);
  }
  return result;
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::setupProcessing(
    Steinberg::Vst::ProcessSetup& setup) {
  const Steinberg::tresult result = M3Component::setupProcessing(setup);
  if (result == Steinberg::kResultOk) {
    increment(ProbeMetric::setup);
    store_sample_rate(setup.sampleRate);
    store_maximum_block(static_cast<std::uint32_t>(setup.maxSamplesPerBlock));
    probe_setup_complete_ = true;
    probe_process_mode_ = setup.processMode;
    probe_sample_size_ = setup.symbolicSampleSize;
    probe_maximum_block_ =
        static_cast<std::uint32_t>(setup.maxSamplesPerBlock);
  }
  return result;
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::setActive(
    Steinberg::TBool state) {
  const Steinberg::tresult result = M3Component::setActive(state);
  if (result == Steinberg::kResultOk) {
    increment(state == Steinberg::TBool{1} ? ProbeMetric::activate
                                           : ProbeMetric::deactivate);
  }
  return result;
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::setProcessing(
    Steinberg::TBool state) {
  const Steinberg::tresult result = M3Component::setProcessing(state);
  if (result == Steinberg::kResultOk) {
    if (state == Steinberg::TBool{1}) {
      probe_processing_ = true;
      diagnostics_published_ = false;
      diagnostic_publish_attempts_ = 0U;
      increment(ProbeMetric::start);
      increment(ProbeMetric::reset);
      reset_trigger_state(false);
    } else {
      probe_processing_ = false;
      increment(ProbeMetric::stop);
      code_size_ = 0U;
      decision_phase_ = 0U;
      phase_one_active_ = false;
      trigger_one_seen_ = false;
      trigger_two_seen_ = false;
    }
  }
  return result;
}

Steinberg::tresult PLUGIN_API M3ProbeProcessor::process(
    Steinberg::Vst::ProcessData& data) {
  increment(ProbeMetric::process);
  if (data.symbolicSampleSize == Steinberg::Vst::kSample32) {
    inspect_audio<Steinberg::Vst::Sample32>(data);
  } else if (data.symbolicSampleSize == Steinberg::Vst::kSample64) {
    inspect_audio<Steinberg::Vst::Sample64>(data);
  }
  const Steinberg::tresult result = M3Component::process(data);
  if (!diagnostics_published_ &&
      diagnostic_publish_attempts_ < kDiagnosticPublishAttemptLimit) {
    ++diagnostic_publish_attempts_;
    diagnostics_published_ =
        publish_diagnostics(data.outputParameterChanges);
  }
  return result;
}

template <typename Sample>
void M3ProbeProcessor::inspect_audio(
    Steinberg::Vst::ProcessData& data) noexcept {
  constexpr Steinberg::int32 kExpectedSampleSize =
      std::is_same_v<Sample, Steinberg::Vst::Sample32>
          ? Steinberg::Vst::kSample32
          : Steinberg::Vst::kSample64;
  if (fault_latched_ || !probe_setup_complete_ || !probe_processing_ ||
      data.processMode != probe_process_mode_ ||
      data.symbolicSampleSize != probe_sample_size_ ||
      data.symbolicSampleSize != kExpectedSampleSize ||
      data.numSamples <= 0 ||
      static_cast<std::uint32_t>(data.numSamples) > probe_maximum_block_ ||
      data.numInputs != 1 || data.numOutputs != 1 || data.inputs == nullptr ||
      data.outputs == nullptr) {
    return;
  }
  Steinberg::Vst::AudioBusBuffers& input = data.inputs[0];
  Steinberg::Vst::AudioBusBuffers& output = data.outputs[0];
  if (input.numChannels != 2 || output.numChannels != 2 ||
      (input.silenceFlags & ~Steinberg::uint64{3}) != 0U) {
    return;
  }
  Sample** inputs = nullptr;
  Sample** outputs = nullptr;
  if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
    inputs = input.channelBuffers32;
    outputs = output.channelBuffers32;
  } else {
    inputs = input.channelBuffers64;
    outputs = output.channelBuffers64;
  }
  if (inputs == nullptr || outputs == nullptr || inputs[0] == nullptr ||
      inputs[1] == nullptr || outputs[0] == nullptr || outputs[1] == nullptr ||
      inputs[0] == inputs[1] || outputs[0] == outputs[1]) {
    return;
  }
  if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
    increment(ProbeMetric::float32_seen);
  } else {
    increment(ProbeMetric::float64_seen);
  }
  if (inputs[0] == outputs[0] && inputs[1] == outputs[1]) {
    increment(ProbeMetric::alias_seen);
  } else {
    increment(ProbeMetric::separate_seen);
  }
  const std::uint32_t frames = static_cast<std::uint32_t>(data.numSamples);
  const bool left_silent = (input.silenceFlags & Steinberg::uint64{1}) != 0U;
  const bool right_silent = (input.silenceFlags & Steinberg::uint64{2}) != 0U;
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    const double left =
        left_silent ? 0.0 : static_cast<double>(inputs[0][frame]);
    const double right =
        right_silent ? 0.0 : static_cast<double>(inputs[1][frame]);
    if (!std::isfinite(left) || !std::isfinite(right)) {
      latch_fault(false);
      return;
    }
  }
  for (std::uint32_t frame = 0; frame < frames; ++frame) {
    if (decision_phase_ == 0U) {
      const double left =
          left_silent ? 0.0 : static_cast<double>(inputs[0][frame]);
      const double right =
          right_silent ? 0.0 : static_cast<double>(inputs[1][frame]);
      accept_selected_sample(left, right, frame, frames);
      if (fault_latched_) {
        return;
      }
    }
    decision_phase_ = (decision_phase_ + 1U) % kProbeDecisionFrames;
  }
}

void M3ProbeProcessor::accept_selected_sample(
    double left, double right, std::uint32_t offset,
    std::uint32_t frames) noexcept {
  if (!std::isfinite(left) || !std::isfinite(right)) {
    latch_fault(false);
    return;
  }
  const bool silence = same_code(left, 0.0) && same_code(right, 0.0);
  if (silence) {
    if (code_size_ != 0U) {
      static_cast<void>(commit_code(offset, frames));
      code_size_ = 0U;
      return;
    }
    if (phase_one_active_) {
      if (queue_probe_note(offset, TransitionKind::note_off, kProbeFirstPitch,
                           0U, frames)) {
        phase_one_active_ = false;
      }
    }
    return;
  }
  if (phase_one_active_ || code_size_ >= code_.size()) {
    latch_fault(true);
    return;
  }
  code_[code_size_++] = ProbeStereoCode{left, right};
}

bool M3ProbeProcessor::commit_code(std::uint32_t offset,
                                   std::uint32_t frames) noexcept {
  if (code_size_ != code_.size()) {
    latch_fault(false);
    return false;
  }
  if (code_matches(code_, kProbeFirstCode) && !trigger_one_seen_) {
    if (!queue_probe_note(offset, TransitionKind::note_on, kProbeFirstPitch,
                          kProbeFirstVelocity, frames)) {
      return false;
    }
    trigger_one_seen_ = true;
    phase_one_active_ = true;
    increment(ProbeMetric::trigger_one);
    return true;
  }
  if (code_matches(code_, kProbeSecondCode) && !trigger_two_seen_) {
    if (!queue_probe_note(offset, TransitionKind::note_on, kProbeSecondPitch,
                          kProbeSecondVelocity, frames)) {
      return false;
    }
    trigger_two_seen_ = true;
    increment(ProbeMetric::trigger_two);
    return true;
  }
  latch_fault(true);
  return false;
}

bool M3ProbeProcessor::queue_probe_note(
    std::uint32_t offset, TransitionKind kind, std::uint8_t pitch,
    std::uint8_t velocity, std::uint32_t frames) noexcept {
  const VoiceTransition transition{offset, kind, pitch, velocity,
                                   ++transition_sequence_};
  if (queue_generated_transition(transition, frames)) {
    return true;
  }
  latch_fault(true);
  return false;
}

void M3ProbeProcessor::reset_trigger_state(bool clear_fault) noexcept {
  code_ = {};
  code_size_ = 0U;
  decision_phase_ = 0U;
  transition_sequence_ = 0U;
  phase_one_active_ = false;
  trigger_one_seen_ = false;
  trigger_two_seen_ = false;
  if (clear_fault) {
    fault_latched_ = false;
  }
}

void M3ProbeProcessor::latch_fault(bool overflow) noexcept {
  if (!fault_latched_) {
    increment(ProbeMetric::trigger_fault);
  }
  if (overflow) {
    increment(ProbeMetric::trigger_overflow);
  }
  fault_latched_ = true;
  code_size_ = 0U;
}

bool M3ProbeProcessor::publish_diagnostics(
    Steinberg::Vst::IParameterChanges* output) noexcept {
  bool complete = true;
  for (std::size_t index = 0; index < kMetricParameters.size(); ++index) {
    const MetricParameterSpec& spec = kMetricParameters[index];
    const double plain = metric_plain_value(spec.metric);
    const double normalized =
        std::clamp(plain / spec.maximum, 0.0, 1.0);
    if (!push_diagnostic_value(
            output,
            kProbeDiagnosticBaseId +
                static_cast<Steinberg::Vst::ParamID>(index),
            normalized)) {
      complete = false;
    }
  }
  return complete;
}

bool M3ProbeProcessor::register_diagnostic_parameters() noexcept {
  for (std::size_t index = 0; index < kMetricParameters.size(); ++index) {
    const MetricParameterSpec& spec = kMetricParameters[index];
    Steinberg::Vst::ParameterInfo info{};
    Steinberg::UString(info.title, 128).fromAscii(spec.name);
    info.id =
        kProbeDiagnosticBaseId + static_cast<Steinberg::Vst::ParamID>(index);
    info.stepCount = Steinberg::Vst::kStepCountContinuous;
    info.defaultNormalizedValue = 0.0;
    info.unitId = Steinberg::Vst::kRootUnitId;
    info.flags = Steinberg::Vst::ParameterInfo::kIsReadOnly;
    auto* parameter = new (std::nothrow)
        Steinberg::Vst::RangeParameter(info, 0.0, spec.maximum);
    if (parameter == nullptr || parameters.addParameter(parameter) == nullptr) {
      if (parameter != nullptr) {
        parameter->release();
      }
      return false;
    }
  }
  return true;
}

void reset_probe_diagnostics_for_test() noexcept {
  for (auto& value : diagnostics) {
    value.store(0U, std::memory_order_relaxed);
  }
}

ProbeDiagnosticsSnapshot probe_diagnostics_snapshot_for_test() noexcept {
  return snapshot();
}

ProbeDiagnosticsSnapshot probe_diagnostics_for_test(
    const M3ProbeProcessor* processor) noexcept {
  return processor != nullptr ? snapshot() : ProbeDiagnosticsSnapshot{};
}

}  // namespace m3::vst3
