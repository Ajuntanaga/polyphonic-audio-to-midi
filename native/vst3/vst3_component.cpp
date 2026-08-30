#include "vst3_component.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <type_traits>

#include "dry_path.hpp"
#include "m3/constants.hpp"
#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/base/fstrdefs.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"
#include "pluginterfaces/vst/vstspeaker.h"
#include "vst3_event_sink.hpp"
#include "vst3_parameter_bridge.hpp"
#include "vst3_state_stream.hpp"

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

bool same_persistent_config(const PersistentConfig& left,
                            const PersistentConfig& right) noexcept {
  return structural_config_equal(left, right) &&
         left.input_trim_db == right.input_trim_db &&
         left.sensitivity == right.sensitivity &&
         left.response == right.response &&
         left.velocity_mode == right.velocity_mode &&
         left.fixed_velocity == right.fixed_velocity &&
         left.dry_passthrough == right.dry_passthrough;
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
  if (!register_vst3_parameters(parameters)) {
    parameters.removeAll();
    static_cast<void>(removeAllBusses());
    static_cast<void>(SingleComponentEffect::terminate());
    return Steinberg::kOutOfMemory;
  }
  main_config_ = PersistentConfig{};
  controller_config_ = PersistentConfig{};
  audio_requested_config_ = PersistentConfig{};
  active_config_ = PersistentConfig{};
  pending_structural_config_ = PersistentConfig{};
  main_generation_ = 1U;
  setup_generation_ = 0U;
  active_generation_ = 0U;
  config_request_.reset(main_config_, main_generation_);
  setup_prepared_ = {};
  setup_prepared_valid_ = false;
  prepared_exchange_.reset();
  prepared_exchange_initialized_ = false;
  prepared_claim_pending_ = false;
  structural_boundary_pending_ = false;
  release_channel_pending_ = false;
  release_midi_channel_ = 1U;
  generated_notes_.deactivate();
  processing_started_once_ = false;
  decision_phase_ = 0U;
  decision_tick_count_ = 0U;
  detector_reset_count_ = 0U;
  panic_ready_dirty_.store(false, std::memory_order_relaxed);
  panic_requested_.store(false, std::memory_order_relaxed);
  status_dirty_ = false;
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
  if (prepared_claim_pending_) {
    static_cast<void>(prepared_exchange_.cancel(prepared_claim_));
  }
  prepared_exchange_.reset();
  prepared_exchange_initialized_ = false;
  prepared_claim_pending_ = false;
  main_config_ = PersistentConfig{};
  controller_config_ = PersistentConfig{};
  audio_requested_config_ = PersistentConfig{};
  active_config_ = PersistentConfig{};
  pending_structural_config_ = PersistentConfig{};
  generated_notes_.deactivate();
  setup_prepared_ = {};
  setup_prepared_valid_ = false;
  main_generation_ = 0U;
  setup_generation_ = 0U;
  active_generation_ = 0U;
  decision_phase_ = 0U;
  decision_tick_count_ = 0U;
  detector_reset_count_ = 0U;
  structural_boundary_pending_ = false;
  release_channel_pending_ = false;
  processing_started_once_ = false;
  panic_ready_dirty_.store(false, std::memory_order_relaxed);
  panic_requested_.store(false, std::memory_order_relaxed);
  status_dirty_ = false;
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
  ConfigRequestSnapshot snapshot;
  PreparedConfig prepared;
  if (!config_request_.snapshot(snapshot) ||
      !stage_prepared_config(snapshot.config, setup.sampleRate, prepared)) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::tresult result = SingleComponentEffect::setupProcessing(setup);
  if (result == Steinberg::kResultOk) {
    setup_prepared_ = prepared;
    setup_generation_ = snapshot.generation;
    setup_prepared_valid_ = true;
    main_config_ = snapshot.config;
    main_generation_ = snapshot.generation;
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
    ConfigRequestSnapshot snapshot;
    if (!config_request_.snapshot(snapshot)) {
      return Steinberg::kInvalidArgument;
    }
    PreparedConfig prepared = setup_prepared_;
    if (!setup_prepared_valid_ || setup_generation_ != snapshot.generation ||
        prepared.sample_rate != processSetup.sampleRate ||
        !same_persistent_config(prepared.requested, snapshot.config)) {
      if (!stage_prepared_config(snapshot.config, processSetup.sampleRate,
                                 prepared)) {
        return Steinberg::kInvalidArgument;
      }
    }
    if (!generated_notes_.activate_preserving_pending(
            static_cast<std::uint32_t>(processSetup.maxSamplesPerBlock))) {
      return Steinberg::kOutOfMemory;
    }
    if (!prepared_exchange_.initialize(prepared, snapshot.generation)) {
      generated_notes_.release_storage_preserving_pending();
      return Steinberg::kOutOfMemory;
    }
    setup_prepared_ = prepared;
    setup_generation_ = snapshot.generation;
    setup_prepared_valid_ = true;
    prepared_exchange_initialized_ = true;
    active_generation_ = snapshot.generation;
    main_config_ = snapshot.config;
    main_generation_ = snapshot.generation;
    active_config_ = prepared.requested;
    copy_runtime_config(active_config_, snapshot.config);
    audio_requested_config_ = active_config_;
    structural_boundary_pending_ = false;
    prepared_claim_pending_ = false;
    if (!generated_notes_.release_pending()) {
      release_midi_channel_ = active_config_.midi_channel;
      release_channel_pending_ = false;
    }
    active_ = true;
    reset_detector_transients();
    status_ = generated_notes_.panic_hold() ? Status::panic_hold
                                            : Status::ready;
    status_dirty_ = false;
    return Steinberg::kResultOk;
  }
  if (!active_ || processing_) {
    return Steinberg::kResultFalse;
  }
  if (prepared_claim_pending_) {
    static_cast<void>(prepared_exchange_.cancel(prepared_claim_));
  }
  prepared_claim_pending_ = false;
  prepared_exchange_.reset();
  prepared_exchange_initialized_ = false;
  structural_boundary_pending_ = false;
  active_ = false;
  generated_notes_.release_storage_preserving_pending();
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
    reset_detector_transients();
    if (processing_started_once_ || generated_notes_.release_pending()) {
      generated_notes_.request_recovery();
      raise_status(Status::panic_hold);
    }
    processing_ = true;
    processing_started_once_ = true;
    return Steinberg::kResultOk;
  }
  if (!processing_) {
    return Steinberg::kResultFalse;
  }
  generated_notes_.request_release_all();
  if (generated_notes_.release_pending()) {
    if (!release_channel_pending_) {
      release_midi_channel_ = active_config_.midi_channel;
    }
    release_channel_pending_ = true;
  }
  generated_notes_.request_recovery();
  reset_detector_transients();
  raise_status(Status::panic_hold);
  processing_ = false;
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::process(
    Steinberg::Vst::ProcessData& data) {
  if (!processing_ || !is_process_mode(data.processMode) ||
      data.processMode != processSetup.processMode || data.numSamples < 0 ||
      data.numSamples > processSetup.maxSamplesPerBlock ||
      static_cast<std::uint32_t>(data.numSamples) > kMaxHostFrames) {
    raise_status(Status::invalid_input_or_state);
    generated_notes_.report_output_failure();
    publish_parameter_outputs(data.outputParameterChanges);
    return Steinberg::kInvalidArgument;
  }
  if (data.symbolicSampleSize != processSetup.symbolicSampleSize) {
    raise_status(Status::invalid_input_or_state);
    generated_notes_.report_output_failure();
    publish_parameter_outputs(data.outputParameterChanges);
    return Steinberg::kInvalidArgument;
  }
  ParameterBatch parameter_batch;
  if (!read_last_boundary_values(data.inputParameterChanges, data.numSamples,
                                 audio_requested_config_, parameter_batch)) {
    raise_status(Status::invalid_input_or_state);
    generated_notes_.report_output_failure();
    publish_parameter_outputs(data.outputParameterChanges);
    return Steinberg::kInvalidArgument;
  }
  if (parameter_batch.changed) {
    if (parameter_batch.structural) {
      begin_structural_boundary(parameter_batch.candidate);
    } else {
      copy_runtime_config(audio_requested_config_, parameter_batch.candidate);
      copy_runtime_config(active_config_, parameter_batch.candidate);
    }
  }
  if (parameter_batch.panic ||
      panic_requested_.exchange(false, std::memory_order_acq_rel)) {
    panic_ready_dirty_.store(true, std::memory_order_release);
    request_panic_recovery();
  }
  if (data.numSamples == 0) {
    if (structural_boundary_pending_) {
      raise_status(Status::reconfiguring);
    }
    publish_parameter_outputs(data.outputParameterChanges);
    return Steinberg::kResultOk;
  }
  if (data.symbolicSampleSize == Steinberg::Vst::kSample32) {
    const Steinberg::tresult result =
        process_samples<Steinberg::Vst::Sample32>(data);
    publish_parameter_outputs(data.outputParameterChanges);
    return result;
  }
  if (data.symbolicSampleSize == Steinberg::Vst::kSample64) {
    const Steinberg::tresult result =
        process_samples<Steinberg::Vst::Sample64>(data);
    publish_parameter_outputs(data.outputParameterChanges);
    return result;
  }
  raise_status(Status::invalid_input_or_state);
  generated_notes_.report_output_failure();
  publish_parameter_outputs(data.outputParameterChanges);
  return Steinberg::kInvalidArgument;
}

Steinberg::tresult PLUGIN_API M3Component::setState(
    Steinberg::IBStream* state) {
  if (!initialized_) {
    return Steinberg::kInvalidArgument;
  }
  PersistentConfig candidate;
  if (!load_vst3_state(state, candidate)) {
    return Steinberg::kResultFalse;
  }
  return publish_main_config(candidate) ? Steinberg::kResultOk
                                        : Steinberg::kResultFalse;
}

Steinberg::tresult PLUGIN_API M3Component::getState(
    Steinberg::IBStream* state) {
  ConfigRequestSnapshot snapshot;
  return initialized_ && config_request_.snapshot(snapshot) &&
                 save_vst3_state(snapshot.config, state)
             ? Steinberg::kResultOk
             : Steinberg::kResultFalse;
}

Steinberg::tresult PLUGIN_API M3Component::setComponentState(
    Steinberg::IBStream* state) {
  if (!initialized_) {
    return Steinberg::kInvalidArgument;
  }
  PersistentConfig candidate;
  if (!load_vst3_state(state, candidate) ||
      !synchronize_vst3_parameters(parameters, candidate, status_)) {
    return Steinberg::kResultFalse;
  }
  controller_config_ = candidate;
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API M3Component::setEditorState(
    Steinberg::IBStream* state) {
  return setComponentState(state);
}

Steinberg::tresult PLUGIN_API M3Component::getEditorState(
    Steinberg::IBStream* state) {
  return initialized_ && save_vst3_state(controller_config_, state)
             ? Steinberg::kResultOk
             : Steinberg::kResultFalse;
}

Steinberg::tresult PLUGIN_API M3Component::getParamStringByValue(
    Steinberg::Vst::ParamID id, Steinberg::Vst::ParamValue normalized,
    Steinberg::Vst::String128 text) {
  if (text == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  text[0] = 0;
  const ParameterSpec* spec = find_parameter(id);
  double plain = 0.0;
  char ascii[128]{};
  if (spec == nullptr ||
      !canonical_normalized_value(*spec, normalized, plain) ||
      !parameter_value_to_text(id, plain, ascii,
                               static_cast<std::uint32_t>(sizeof(ascii)))) {
    return Steinberg::kResultFalse;
  }
  Steinberg::UString(text, 128).fromAscii(ascii);
  return Steinberg::kResultTrue;
}

Steinberg::tresult PLUGIN_API M3Component::getParamValueByString(
    Steinberg::Vst::ParamID id, Steinberg::Vst::TChar* text,
    Steinberg::Vst::ParamValue& normalized) {
  const ParameterSpec* spec = find_parameter(id);
  if (spec == nullptr || text == nullptr) {
    return Steinberg::kResultFalse;
  }
  char ascii[128]{};
  Steinberg::UString(text, 128).toAscii(
      ascii, static_cast<Steinberg::int32>(sizeof(ascii)));
  double plain = 0.0;
  double candidate = 0.0;
  if (!parameter_text_to_value(id, ascii, plain) ||
      !canonical_plain_value(*spec, plain, candidate)) {
    return Steinberg::kResultFalse;
  }
  normalized = candidate;
  return Steinberg::kResultTrue;
}

Steinberg::Vst::ParamValue PLUGIN_API
M3Component::normalizedParamToPlain(
    Steinberg::Vst::ParamID id,
    Steinberg::Vst::ParamValue normalized) {
  const ParameterSpec* spec = find_parameter(id);
  double plain = std::numeric_limits<double>::quiet_NaN();
  if (spec != nullptr) {
    static_cast<void>(canonical_normalized_value(*spec, normalized, plain));
  }
  return plain;
}

Steinberg::Vst::ParamValue PLUGIN_API
M3Component::plainParamToNormalized(Steinberg::Vst::ParamID id,
                                    Steinberg::Vst::ParamValue plain) {
  const ParameterSpec* spec = find_parameter(id);
  double normalized = std::numeric_limits<double>::quiet_NaN();
  if (spec != nullptr) {
    static_cast<void>(canonical_plain_value(*spec, plain, normalized));
  }
  return normalized;
}

Steinberg::tresult PLUGIN_API M3Component::setParamNormalized(
    Steinberg::Vst::ParamID id, Steinberg::Vst::ParamValue normalized) {
  const ParameterSpec* spec = find_parameter(id);
  double plain = 0.0;
  if (!initialized_ || spec == nullptr || spec->read_only ||
      !canonical_normalized_value(*spec, normalized, plain)) {
    return Steinberg::kResultFalse;
  }
  PersistentConfig candidate = main_config_;
  const ParameterApplyResult result = apply_parameter(candidate, id, plain);
  if (result == ParameterApplyResult::rejected) {
    return Steinberg::kResultFalse;
  }
  Steinberg::Vst::Parameter* parameter = parameters.getParameter(id);
  if (parameter == nullptr) {
    return Steinberg::kResultFalse;
  }
  if (result == ParameterApplyResult::panic) {
    panic_ready_dirty_.store(true, std::memory_order_release);
    panic_requested_.store(true, std::memory_order_release);
    static_cast<void>(parameter->setNormalized(0.0));
    return Steinberg::kResultTrue;
  }
  if (!publish_main_config(candidate)) {
    return Steinberg::kResultFalse;
  }
  controller_config_ = candidate;
  static_cast<void>(parameter->setNormalized(normalized));
  return Steinberg::kResultTrue;
}

bool M3Component::publish_main_config(
    const PersistentConfig& config) noexcept {
  if (same_persistent_config(main_config_, config)) {
    main_config_ = config;
    return true;
  }
  const bool structural =
      !structural_config_equal(main_config_, config);
  PreparedConfig prepared;
  if (structural && setup_complete_ &&
      !stage_prepared_config(config, processSetup.sampleRate, prepared)) {
    return false;
  }
  const std::uint64_t generation = main_generation_ + 1U;
  if (structural && active_ && prepared_exchange_initialized_ &&
      !prepared_exchange_.publish(prepared, generation)) {
    return false;
  }
  if (!config_request_.publish(config, generation)) {
    return false;
  }
  main_config_ = config;
  main_generation_ = generation;
  if (structural && setup_complete_) {
    setup_prepared_ = prepared;
    setup_generation_ = generation;
    setup_prepared_valid_ = true;
  }
  return true;
}

void M3Component::begin_structural_boundary(
    const PersistentConfig& config) noexcept {
  if (structural_boundary_pending_ &&
      same_persistent_config(pending_structural_config_, config)) {
    return;
  }
  if (prepared_claim_pending_) {
    static_cast<void>(prepared_exchange_.cancel(prepared_claim_));
    prepared_claim_pending_ = false;
  }
  pending_structural_config_ = config;
  structural_boundary_pending_ = true;
  if (!release_channel_pending_) {
    release_midi_channel_ = active_config_.midi_channel;
  }
  release_channel_pending_ = true;
  generated_notes_.request_release_all();
  reset_detector_transients();
  claim_matching_prepared_config();
}

void M3Component::claim_matching_prepared_config() noexcept {
  if (!structural_boundary_pending_ || prepared_claim_pending_ ||
      !prepared_exchange_initialized_) {
    return;
  }
  PreparedConfigExchange::Claim claim;
  if (!prepared_exchange_.claim_latest(claim)) {
    raise_status(Status::reconfiguring);
    return;
  }
  const bool matches = claim.config != nullptr &&
                       claim.config->sample_rate == processSetup.sampleRate &&
                       structural_config_equal(
                           claim.config->requested,
                           pending_structural_config_);
  if (!matches) {
    static_cast<void>(prepared_exchange_.cancel(claim));
    raise_status(Status::reconfiguring);
    return;
  }
  prepared_claim_ = claim;
  prepared_claim_pending_ = true;
}

void M3Component::retry_pending_releases(
    Steinberg::Vst::ProcessData& data) noexcept {
  const std::uint8_t channel =
      release_channel_pending_ ? release_midi_channel_
                               : active_config_.midi_channel;
  Vst3EventSinkContext context{data.outputEvents, channel};
  if (!generated_notes_.retry_pending_releases(
          NoteEventSink{&context, &push_vst3_note})) {
    raise_status(Status::midi_output_blocked);
  } else if (!structural_boundary_pending_) {
    release_channel_pending_ = false;
  }
}

void M3Component::commit_prepared_config_if_released() noexcept {
  if (!structural_boundary_pending_) {
    return;
  }
  if (!prepared_claim_pending_) {
    claim_matching_prepared_config();
  }
  if (!prepared_claim_pending_ || generated_notes_.release_pending()) {
    raise_status(Status::reconfiguring);
    return;
  }
  const PersistentConfig prepared = prepared_claim_.config->requested;
  const std::uint64_t generation = prepared_claim_.generation;
  if (!prepared_exchange_.commit(prepared_claim_)) {
    static_cast<void>(prepared_exchange_.cancel(prepared_claim_));
    prepared_claim_pending_ = false;
    raise_status(Status::invalid_input_or_state);
    return;
  }
  prepared_claim_pending_ = false;
  active_config_ = prepared;
  copy_runtime_config(active_config_, pending_structural_config_);
  audio_requested_config_ = active_config_;
  active_generation_ = generation;
  structural_boundary_pending_ = false;
  release_channel_pending_ = false;
  if (status_ == Status::reconfiguring) {
    set_status(Status::ready);
  }
}

void M3Component::reset_detector_transients() noexcept {
  decision_phase_ = 0U;
  decision_tick_count_ = 0U;
  ++detector_reset_count_;
}

void M3Component::advance_decision_phase(std::uint32_t frames) noexcept {
  const std::uint64_t total =
      static_cast<std::uint64_t>(decision_phase_) + frames;
  decision_tick_count_ += total / kDecisionQuantum;
  decision_phase_ = static_cast<std::uint32_t>(total % kDecisionQuantum);
}

void M3Component::set_status(Status status) noexcept {
  if (status_ != status) {
    status_ = status;
    status_dirty_ = true;
  }
}

void M3Component::raise_status(Status status) noexcept {
  if (static_cast<std::uint8_t>(status) >
      static_cast<std::uint8_t>(status_)) {
    set_status(status);
  }
}

void M3Component::update_delivery_status(
    const NoteDeliveryResult& result) noexcept {
  if (result.output_blocked) {
    raise_status(Status::midi_output_blocked);
  } else if (result.panic_hold) {
    raise_status(Status::panic_hold);
  } else if (status_ == Status::midi_output_blocked ||
             status_ == Status::panic_hold) {
    set_status(Status::ready);
  }
}

void M3Component::publish_parameter_outputs(
    Steinberg::Vst::IParameterChanges* output) noexcept {
  if (status_dirty_) {
    const ParameterSpec* spec = find_parameter(kStatusParameterId);
    const double normalized =
        spec != nullptr
            ? plain_to_normalized(*spec, static_cast<double>(status_))
            : std::numeric_limits<double>::quiet_NaN();
    if (push_output_value(output, kStatusParameterId, normalized, 0)) {
      status_dirty_ = false;
    }
  }
  if (panic_ready_dirty_.load(std::memory_order_acquire) &&
      push_output_value(output, kPanicParameterId, 0.0, 0)) {
    panic_ready_dirty_.store(false, std::memory_order_release);
  }
}

void M3Component::deliver_generated_notes(
    Steinberg::Vst::ProcessData& data, bool finite_input,
    bool supported_layout, double selected_peak) noexcept {
  Vst3EventSinkContext context{data.outputEvents,
                               active_config_.midi_channel};
  const NoteDeliveryResult result = generated_notes_.deliver_queued(
      static_cast<std::uint32_t>(data.numSamples),
      NoteEventSink{&context, &push_vst3_note}, selected_peak, finite_input,
      supported_layout);
  if (status_ == Status::unsupported_layout ||
      status_ == Status::invalid_input_or_state) {
    return;
  }
  update_delivery_status(result);
}

void M3Component::request_panic_recovery() noexcept {
  generated_notes_.request_release_all();
  generated_notes_.request_recovery();
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
    valid_layout = input.numChannels == 2 && output.numChannels == 2 &&
                   (input.silenceFlags & ~Steinberg::uint64{3}) == 0U;
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
    raise_status(Status::unsupported_layout);
    if (!release_channel_pending_) {
      release_midi_channel_ = active_config_.midi_channel;
    }
    release_channel_pending_ = true;
    generated_notes_.report_output_failure();
    zero_available_output<Sample>(data);
    retry_pending_releases(data);
    deliver_generated_notes(data, true, false, 0.0);
    generated_notes_.begin_block();
    return Steinberg::kResultOk;
  }

  retry_pending_releases(data);
  commit_prepared_config_if_released();

  Steinberg::Vst::AudioBusBuffers& input = data.inputs[0];
  Steinberg::Vst::AudioBusBuffers& output = data.outputs[0];
  const DryPathResult result = process_dry_path(
      input_channels, 2U, output_channels, 2U,
      static_cast<std::uint32_t>(data.numSamples),
      audio_requested_config_.dry_passthrough,
      active_config_.detector_input, input.silenceFlags);
  output.silenceFlags = result.output_silence_flags;
  if (result.nonfinite_input) {
    raise_status(Status::invalid_input_or_state);
    if (!release_channel_pending_) {
      release_midi_channel_ = active_config_.midi_channel;
    }
    release_channel_pending_ = true;
    generated_notes_.report_output_failure();
  }
  const bool detector_allowed =
      !result.nonfinite_input && !structural_boundary_pending_ &&
      !generated_notes_.release_pending() &&
      !generated_notes_.output_blocked() && !generated_notes_.panic_hold();
  if (detector_allowed) {
    advance_decision_phase(static_cast<std::uint32_t>(data.numSamples));
  }
  if (structural_boundary_pending_) {
    generated_notes_.begin_block();
  }
  deliver_generated_notes(data, !result.nonfinite_input, true,
                          result.selected_peak);
  generated_notes_.begin_block();
  return Steinberg::kResultOk;
}

template <typename Sample>
void M3Component::zero_available_output(
    Steinberg::Vst::ProcessData& data) noexcept {
  if (data.numOutputs <= 0 || data.outputs == nullptr) {
    return;
  }
  Steinberg::Vst::AudioBusBuffers& output = data.outputs[0];
  output.silenceFlags = 0U;
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

void begin_generated_note_block_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  if (processor != nullptr) {
    static_cast<M3Component*>(processor)->begin_generated_note_block_for_test();
  }
}

bool queue_generated_note_for_test(
    Steinberg::Vst::IAudioProcessor* processor,
    const VoiceTransition& transition, std::uint32_t frames) noexcept {
  return processor != nullptr &&
         static_cast<M3Component*>(processor)->queue_generated_note_for_test(
             transition, frames);
}

bool generated_note_active_for_test(
    Steinberg::Vst::IAudioProcessor* processor, std::uint8_t note) noexcept {
  return processor != nullptr &&
         static_cast<M3Component*>(processor)->generated_note_active_for_test(
             note);
}

bool generated_note_pending_for_test(
    Steinberg::Vst::IAudioProcessor* processor, std::uint8_t note) noexcept {
  return processor != nullptr &&
         static_cast<M3Component*>(processor)->generated_note_pending_for_test(
             note);
}

double prepared_sample_rate_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->prepared_sample_rate_for_test()
             : 0.0;
}

double prepared_sample_period_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->prepared_sample_period_for_test()
             : 0.0;
}

std::size_t transition_capacity_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->transition_capacity_for_test()
             : 0U;
}

std::uint32_t decision_phase_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)->decision_phase_for_test()
             : 0U;
}

std::uint64_t decision_tick_count_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->decision_tick_count_for_test()
             : 0U;
}

std::uint32_t detector_reset_count_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->detector_reset_count_for_test()
             : 0U;
}

std::uint64_t active_config_generation_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->active_config_generation_for_test()
             : 0U;
}

std::uint8_t active_midi_channel_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept {
  return processor != nullptr
             ? static_cast<M3Component*>(processor)
                   ->active_midi_channel_for_test()
             : 0U;
}
#endif

}  // namespace m3::vst3
