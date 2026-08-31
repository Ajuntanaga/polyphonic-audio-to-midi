#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

#include "vst3_component.hpp"

namespace m3::vst3 {

inline constexpr std::uint32_t kProbeDecisionFrames = 64U;
inline constexpr std::uint8_t kProbeFirstPitch = 60U;
inline constexpr std::uint8_t kProbeFirstVelocity = 101U;
inline constexpr std::uint8_t kProbeSecondPitch = 64U;
inline constexpr std::uint8_t kProbeSecondVelocity = 111U;
inline constexpr Steinberg::Vst::ParamID kProbeDiagnosticBaseId =
    0x4D33F000U;

struct ProbeStereoCode final {
  double left{};
  double right{};
};

inline constexpr std::array<ProbeStereoCode, 3> kProbeFirstCode{{
    {0.25, -0.25},
    {-0.5, 0.5},
    {0.75, 0.75},
}};
inline constexpr std::array<ProbeStereoCode, 3> kProbeSecondCode{{
    {-0.25, 0.25},
    {0.5, -0.5},
    {-0.75, -0.75},
}};

struct ProbeDiagnosticsSnapshot final {
  std::uint64_t create{};
  std::uint64_t initialize{};
  std::uint64_t setup{};
  std::uint64_t activate{};
  std::uint64_t start{};
  std::uint64_t process{};
  std::uint64_t stop{};
  std::uint64_t deactivate{};
  std::uint64_t terminate{};
  std::uint64_t destroy{};
  std::uint64_t reset{};
  std::uint64_t float32_seen{};
  std::uint64_t float64_seen{};
  std::uint64_t alias_seen{};
  std::uint64_t separate_seen{};
  double sample_rate{};
  std::uint32_t maximum_block{};
  std::uint64_t trigger_one{};
  std::uint64_t trigger_two{};
  std::uint64_t trigger_overflow{};
  std::uint64_t trigger_fault{};
};

class M3ProbeProcessor final : public M3Component {
 public:
  M3ProbeProcessor() noexcept;
  ~M3ProbeProcessor() override;

  static Steinberg::FUnknown* createInstance(void* context) noexcept;

  Steinberg::tresult PLUGIN_API initialize(
      Steinberg::FUnknown* context) override;
  Steinberg::tresult PLUGIN_API terminate() override;
  Steinberg::tresult PLUGIN_API setupProcessing(
      Steinberg::Vst::ProcessSetup& setup) override;
  Steinberg::tresult PLUGIN_API setActive(Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API setProcessing(
      Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API process(
      Steinberg::Vst::ProcessData& data) override;

 private:
  template <typename Sample>
  void inspect_audio(Steinberg::Vst::ProcessData& data) noexcept;
  void accept_selected_sample(double left, double right,
                              std::uint32_t offset,
                              std::uint32_t frames) noexcept;
  bool commit_code(std::uint32_t offset, std::uint32_t frames) noexcept;
  bool queue_probe_note(std::uint32_t offset, TransitionKind kind,
                        std::uint8_t pitch, std::uint8_t velocity,
                        std::uint32_t frames) noexcept;
  void reset_trigger_state(bool clear_fault) noexcept;
  void latch_fault(bool overflow) noexcept;
  bool publish_diagnostics(
      Steinberg::Vst::IParameterChanges* output) noexcept;
  bool register_diagnostic_parameters() noexcept;

  std::array<ProbeStereoCode, 3> code_{};
  std::size_t code_size_{};
  std::uint32_t decision_phase_{};
  std::uint32_t transition_sequence_{};
  bool phase_one_active_{};
  bool trigger_one_seen_{};
  bool trigger_two_seen_{};
  bool fault_latched_{};
  bool diagnostics_published_{};
  bool probe_setup_complete_{};
  bool probe_processing_{};
  std::uint8_t diagnostic_publish_attempts_{};
  Steinberg::int32 probe_process_mode_{};
  Steinberg::int32 probe_sample_size_{};
  std::uint32_t probe_maximum_block_{};
};

void reset_probe_diagnostics_for_test() noexcept;
[[nodiscard]] ProbeDiagnosticsSnapshot
probe_diagnostics_snapshot_for_test() noexcept;
[[nodiscard]] ProbeDiagnosticsSnapshot probe_diagnostics_for_test(
    const M3ProbeProcessor* processor) noexcept;

}  // namespace m3::vst3
