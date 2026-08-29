#pragma once

#include "public.sdk/source/vst/vstsinglecomponenteffect.h"

#include <cstdint>

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
  }
  [[nodiscard]] Status status_for_test() const noexcept { return status_; }
#endif

 private:
  template <typename Sample>
  Steinberg::tresult process_samples(
      Steinberg::Vst::ProcessData& data) noexcept;

  template <typename Sample>
  static void zero_available_output(
      Steinberg::Vst::ProcessData& data) noexcept;

  bool initialized_{};
  bool setup_complete_{};
  bool active_{};
  bool processing_{};
  bool dry_passthrough_{true};
  Status status_{Status::ready};
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
#endif

}  // namespace m3::vst3
