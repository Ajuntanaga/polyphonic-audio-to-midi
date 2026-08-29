#pragma once

#include <clap/ext/params.h>

#include <cstddef>
#include <cstdint>

#include "m3/types.hpp"

namespace m3 {

inline constexpr clap_id kPanicParameterId = 0x4D33000EU;
inline constexpr clap_id kStatusParameterId = 0x4D33FF01U;

enum class ParameterUpdateClass : std::uint8_t {
  structural,
  runtime,
  action,
  telemetry,
};

struct ParameterRecord final {
  clap_id id;
  const char* name;
  double minimum;
  double maximum;
  double default_value;
  clap_param_info_flags flags;
  ParameterUpdateClass update_class;
  bool persistent;
};

enum class ParameterApplyResult : std::uint8_t {
  rejected,
  unchanged,
  changed,
  panic,
};

std::size_t parameter_count() noexcept;
const ParameterRecord* parameter_record(std::size_t index) noexcept;
const ParameterRecord* find_parameter(clap_id id) noexcept;
bool parameter_value(const PersistentConfig& config, Status status, clap_id id,
                     double& value) noexcept;
ParameterApplyResult apply_parameter(PersistentConfig& config, clap_id id,
                                     double value) noexcept;
bool parameter_value_to_text(clap_id id, double value, char* output,
                             std::uint32_t capacity) noexcept;
bool parameter_text_to_value(clap_id id, const char* text,
                             double& value) noexcept;

inline constexpr std::size_t kPersistentParameterCount = 14;
const clap_id* persistent_parameter_ids() noexcept;

}  // namespace m3
