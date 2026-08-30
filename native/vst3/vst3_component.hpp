#pragma once

#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

#include <cstdint>

#include "m3/generated_note_ledger.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/types.hpp"

namespace m3::vst3 {

class M3Component final : public Steinberg::Vst::SingleComponentEffect {
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
      Steinberg::FIDString) override {
    return nullptr;
  }

#if defined(M3_TESTING)
  void set_dry_passthrough_for_test(bool enabled) noexcept {
    dry_passthrough_ = enabled;
    requested_config_.dry_passthrough = enabled;
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
#endif

 private:
  template <typename Sample>
  Steinberg::tresult process_samples(
      Steinberg::Vst::ProcessData& data) noexcept;

  template <typename Sample>
  static void zero_available_output(
      Steinberg::Vst::ProcessData& data) noexcept;

  void apply_requested_config(const PersistentConfig& config) noexcept;
  void publish_parameter_outputs(
      Steinberg::Vst::IParameterChanges* output) noexcept;
  void deliver_generated_notes(Steinberg::Vst::ProcessData& data,
                               bool finite_input,
                               bool supported_layout) noexcept;
  void request_panic_recovery() noexcept;

  bool initialized_{};
  bool setup_complete_{};
  bool active_{};
  bool processing_{};
  bool dry_passthrough_{true};
  Status status_{Status::ready};
  PersistentConfig requested_config_{};
  PersistentConfig controller_config_{};
  GeneratedNoteLedger generated_notes_{};
  bool panic_ready_dirty_{};
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
#endif

}  // namespace m3::vst3
