#pragma once

#include <cstddef>
#include <cstdint>

#include "m3/types.hpp"

namespace m3 {

using ParameterId = std::uint32_t;

inline constexpr ParameterId kPanicParameterId = 0x4D33000EU;
inline constexpr ParameterId kStatusParameterId = 0x4D33FF01U;
inline constexpr std::size_t kParameterCount = 16;
inline constexpr std::size_t kPersistentParameterCount = 14;

enum class ParameterUpdateClass : std::uint8_t {
  structural,
  runtime,
  action,
  telemetry,
};

enum class ParameterApplyResult : std::uint8_t {
  rejected,
  unchanged,
  changed,
  panic,
};

struct ParameterSpec final {
  ParameterId id;
  const char* name;
  double minimum;
  double maximum;
  double increment;
  double default_value;
  std::int32_t step_count;
  ParameterUpdateClass update_class;
  bool persistent;
  bool list;
  bool read_only;
};

std::size_t parameter_count() noexcept;
const ParameterSpec* parameter_spec(std::size_t index) noexcept;
const ParameterSpec* find_parameter(ParameterId id) noexcept;
double canonical_plain(const ParameterSpec& spec, double value) noexcept;
double plain_to_normalized(const ParameterSpec& spec, double value) noexcept;
double normalized_to_plain(const ParameterSpec& spec, double value) noexcept;
bool parameter_value(const PersistentConfig& config, Status status,
                     ParameterId id, double& value) noexcept;
ParameterApplyResult apply_parameter(PersistentConfig& config, ParameterId id,
                                     double plain_value) noexcept;
bool parameter_value_to_text(ParameterId id, double value, char* output,
                             std::uint32_t capacity) noexcept;
bool parameter_text_to_value(ParameterId id, const char* text,
                             double& value) noexcept;
const ParameterId* persistent_parameter_ids() noexcept;

}  // namespace m3
