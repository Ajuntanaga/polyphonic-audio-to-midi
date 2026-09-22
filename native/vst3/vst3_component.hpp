#pragma once

#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

#include <atomic>
#include <cstddef>
#include <cstdint>

#include "m3/generated_note_ledger.hpp"
#include "m3/monophonic_pitch_detector.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/types.hpp"
#include "prepared_config_exchange.hpp"

namespace m3::vst3 {

class M3Component : public Steinberg::Vst::SingleComponentEffect {
 public:
  M3Component() noexcept;
  ~M3Component() override;

  static Steinberg::FUnknown* createInstance(void* context) noexcept;

  Steinberg::tresult PLUGIN_API initialize(
      Steinberg::FUnknown* context) override;
  Steinberg::tresult PLUGIN_API terminate() override;
  Steinberg::tresult PLUGIN_API setBusArrangements(
      Steinberg::Vst::SpeakerArrangement* inputs, Steinberg::int32 num_inputs,
      Steinberg::Vst::SpeakerArrangement* outputs,
      Steinberg::int32 num_outputs) override;
  Steinberg::tresult PLUGIN_API canProcessSampleSize(
      Steinberg::int32 symbolic_sample_size) override;
  Steinberg::tresult PLUGIN_API setupProcessing(
      Steinberg::Vst::ProcessSetup& setup) override;
  Steinberg::tresult PLUGIN_API setActive(Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API setProcessing(
      Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API process(
      Steinberg::Vst::ProcessData& data) override;
  Steinberg::tresult PLUGIN_API setState(Steinberg::IBStream* state) override;
  Steinberg::tresult PLUGIN_API getState(Steinberg::IBStream* state) override;
  Steinberg::tresult PLUGIN_API setComponentState(
      Steinberg::IBStream* state) override;
  Steinberg::tresult PLUGIN_API setEditorState(
      Steinberg::IBStream* state) override;
  Steinberg::tresult PLUGIN_API getEditorState(
      Steinberg::IBStream* state) override;
  Steinberg::tresult PLUGIN_API getParamStringByValue(
      Steinberg::Vst::ParamID id, Steinberg::Vst::ParamValue normalized,
      Steinberg::Vst::String128 text) override;
  Steinberg::tresult PLUGIN_API getParamValueByString(
      Steinberg::Vst::ParamID id, Steinberg::Vst::TChar* text,
      Steinberg::Vst::ParamValue& normalized) override;
  Steinberg::Vst::ParamValue PLUGIN_API normalizedParamToPlain(
      Steinberg::Vst::ParamID id,
      Steinberg::Vst::ParamValue normalized) override;
  Steinberg::Vst::ParamValue PLUGIN_API plainParamToNormalized(
      Steinberg::Vst::ParamID id, Steinberg::Vst::ParamValue plain) override;
  Steinberg::tresult PLUGIN_API setParamNormalized(
      Steinberg::Vst::ParamID id,
      Steinberg::Vst::ParamValue normalized) override;
  Steinberg::uint32 PLUGIN_API getLatencySamples() override { return 0U; }
  Steinberg::uint32 PLUGIN_API getTailSamples() override {
    return Steinberg::Vst::kNoTail;
  }
  Steinberg::IPlugView* PLUGIN_API createView(
      Steinberg::FIDString name) override;

  // Read-only detector evidence for the editor. This is deliberately not a
  // VST parameter: it neither changes persistent state nor implies MIDI
  // delivery succeeded.
  [[nodiscard]] const TunerTelemetry& tuner_telemetry() const noexcept {
    return tuner_telemetry_;
  }

#if defined(M3_TESTING)
  void set_dry_passthrough_for_test(bool enabled) noexcept {
    audio_requested_config_.dry_passthrough = enabled;
  }
  [[nodiscard]] Status status_for_test() const noexcept { return status_; }
  void begin_generated_note_block_for_test() noexcept {
    generated_notes_.begin_block();
  }
  bool queue_generated_note_for_test(const VoiceTransition& transition,
                                     std::uint32_t frames) noexcept {
    return generated_notes_.queue_transition(transition, frames);
  }
  [[nodiscard]] bool generated_note_active_for_test(
      std::uint8_t note) const noexcept {
    return generated_notes_.is_active(note);
  }
  [[nodiscard]] bool generated_note_pending_for_test(
      std::uint8_t note) const noexcept {
    return generated_notes_.is_pending_release(note);
  }
  [[nodiscard]] double prepared_sample_rate_for_test() const noexcept {
    return setup_prepared_.sample_rate;
  }
  [[nodiscard]] double prepared_sample_period_for_test() const noexcept {
    return setup_prepared_.sample_period;
  }
  [[nodiscard]] std::size_t transition_capacity_for_test() const noexcept {
    return generated_notes_.capacity();
  }
  [[nodiscard]] std::uint32_t decision_phase_for_test() const noexcept {
    return decision_phase_;
  }
  [[nodiscard]] std::uint64_t decision_tick_count_for_test() const noexcept {
    return decision_tick_count_;
  }
  [[nodiscard]] std::uint32_t detector_reset_count_for_test() const noexcept {
    return detector_reset_count_;
  }
  [[nodiscard]] std::uint64_t active_config_generation_for_test()
      const noexcept {
    return active_generation_;
  }
  [[nodiscard]] std::uint8_t active_midi_channel_for_test() const noexcept {
    return active_config_.midi_channel;
  }
  [[nodiscard]] MonophonicPitchDetector::SelectionWork
  detector_selection_work_for_test() const noexcept {
    return detector_.selection_work_for_test();
  }
  [[nodiscard]] bool read_tuner_snapshot_for_test(
      TunerSnapshot& snapshot) const noexcept {
    return tuner_telemetry_.read_latest(snapshot);
  }
  void publish_tuner_snapshot_for_test(const TunerSnapshot& snapshot) noexcept {
    tuner_telemetry_.publish(snapshot);
  }
#endif

 protected:
  bool queue_generated_transition(const VoiceTransition& transition,
                                  std::uint32_t frames) noexcept;

 private:
  template <typename Sample>
  Steinberg::tresult process_samples(
      Steinberg::Vst::ProcessData& data) noexcept;

  template <typename Sample>
  static void zero_available_output(
      Steinberg::Vst::ProcessData& data) noexcept;

  bool publish_main_config(const PersistentConfig& config) noexcept;
  void begin_structural_boundary(const PersistentConfig& config) noexcept;
  void claim_matching_prepared_config() noexcept;
  void retry_pending_releases(Steinberg::Vst::ProcessData& data) noexcept;
  void commit_prepared_config_if_released() noexcept;
  void reset_detector_transients() noexcept;
  void update_tuner(const TunerEstimate& estimate) noexcept;
  void advance_decision_phase(std::uint32_t frames) noexcept;
  void set_status(Status status) noexcept;
  void raise_status(Status status) noexcept;
  void update_delivery_status(const NoteDeliveryResult& result) noexcept;
  void publish_parameter_outputs(
      Steinberg::Vst::IParameterChanges* output) noexcept;
  void deliver_generated_notes(Steinberg::Vst::ProcessData& data,
                               bool finite_input,
                               bool supported_layout,
                               double selected_peak) noexcept;
  void request_panic_recovery() noexcept;

  bool initialized_{};
  bool setup_complete_{};
  bool active_{};
  bool processing_{};
  bool processing_started_once_{};
  Status status_{Status::ready};
  PersistentConfig main_config_{};
  PersistentConfig controller_config_{};
  PersistentConfig audio_requested_config_{};
  PersistentConfig active_config_{};
  PersistentConfig pending_structural_config_{};
  AtomicConfigRequest config_request_{};
  PreparedConfig setup_prepared_{};
  PreparedConfigExchange prepared_exchange_{};
  PreparedConfigExchange::Claim prepared_claim_{};
  GeneratedNoteLedger generated_notes_{};
  MonophonicPitchDetector detector_{};
  TunerTelemetry tuner_telemetry_{};
  std::uint64_t main_generation_{};
  std::uint64_t setup_generation_{};
  std::uint64_t active_generation_{};
  std::uint64_t decision_tick_count_{};
  std::uint32_t decision_phase_{};
  std::uint32_t detector_reset_count_{};
  std::uint8_t release_midi_channel_{1};
  std::uint8_t tuner_note_{kTunerNoSignalNote};
  double tuner_cents_{};
  bool setup_prepared_valid_{};
  bool prepared_exchange_initialized_{};
  bool prepared_claim_pending_{};
  bool structural_boundary_pending_{};
  bool release_channel_pending_{};
  bool status_dirty_{};
  bool tuner_note_dirty_{};
  bool tuner_cents_dirty_{};
  std::atomic<bool> panic_ready_dirty_{false};
  std::atomic<bool> panic_requested_{false};
};

#if defined(M3_TESTING)
struct LifecycleCounters final {
  std::uint32_t constructed{};
  std::uint32_t initialized{};
  std::uint32_t terminated{};
  std::uint32_t destroyed{};
};

void reset_lifecycle_counters_for_test() noexcept;
[[nodiscard]] LifecycleCounters lifecycle_counters_for_test() noexcept;
void set_dry_passthrough_for_test(
    Steinberg::Vst::IAudioProcessor* processor, bool enabled) noexcept;
[[nodiscard]] Status status_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
void begin_generated_note_block_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
bool queue_generated_note_for_test(
    Steinberg::Vst::IAudioProcessor* processor,
    const VoiceTransition& transition, std::uint32_t frames) noexcept;
[[nodiscard]] bool generated_note_active_for_test(
    Steinberg::Vst::IAudioProcessor* processor, std::uint8_t note) noexcept;
[[nodiscard]] bool generated_note_pending_for_test(
    Steinberg::Vst::IAudioProcessor* processor, std::uint8_t note) noexcept;
[[nodiscard]] double prepared_sample_rate_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] double prepared_sample_period_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::size_t transition_capacity_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::uint32_t decision_phase_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::uint64_t decision_tick_count_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::uint32_t detector_reset_count_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::uint64_t active_config_generation_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] std::uint8_t active_midi_channel_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] MonophonicPitchDetector::SelectionWork
detector_selection_work_for_test(
    Steinberg::Vst::IAudioProcessor* processor) noexcept;
[[nodiscard]] bool read_tuner_snapshot_for_test(
    Steinberg::Vst::IAudioProcessor* processor,
    TunerSnapshot& snapshot) noexcept;
void publish_tuner_snapshot_for_test(
    Steinberg::Vst::IAudioProcessor* processor,
    const TunerSnapshot& snapshot) noexcept;
#endif

}  // namespace m3::vst3
