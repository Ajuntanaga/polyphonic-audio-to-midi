#pragma once

#include "m3/parameter_contract.hpp"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "public.sdk/source/vst/vstparameters.h"

namespace m3::vst3 {

inline constexpr ParameterId kTunerNoteParameterId = 0x4D33FF02U;
inline constexpr ParameterId kTunerCentsParameterId = 0x4D33FF03U;
inline constexpr std::size_t kVst3ParameterCount = kParameterCount + 2U;
inline constexpr Steinberg::int32 kMaxParameterQueues =
    static_cast<Steinberg::int32>(kVst3ParameterCount);
inline constexpr Steinberg::int32 kMaxParameterPointsPerQueue = 64;

struct ParameterBatch final {
  PersistentConfig candidate{};
  bool changed{};
  bool structural{};
  bool panic{};
};

bool canonical_normalized_value(const ParameterSpec& spec, double normalized,
                                double& plain) noexcept;
bool canonical_plain_value(const ParameterSpec& spec, double plain,
                           double& normalized) noexcept;
const ParameterSpec* vst3_parameter_spec(std::size_t index) noexcept;
const ParameterSpec* find_vst3_parameter(ParameterId id) noexcept;
bool vst3_parameter_value_to_text(ParameterId id, double value, char* output,
                                  std::uint32_t capacity) noexcept;

bool register_vst3_parameters(
    Steinberg::Vst::ParameterContainer& container) noexcept;
bool synchronize_vst3_parameters(
    Steinberg::Vst::ParameterContainer& container,
    const PersistentConfig& config, Status status) noexcept;

bool read_last_boundary_values(
    Steinberg::Vst::IParameterChanges* changes, Steinberg::int32 num_samples,
    const PersistentConfig& current, ParameterBatch& output) noexcept;
bool push_output_value(Steinberg::Vst::IParameterChanges* changes,
                       ParameterId id, double normalized,
                       Steinberg::int32 offset) noexcept;

}  // namespace m3::vst3
