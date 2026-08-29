#include "clap_parameter_bridge.hpp"

#include <cstring>

namespace m3 {

clap_param_info_flags clap_parameter_flags(const ParameterSpec& spec) noexcept {
  clap_param_info_flags flags = 0U;
  if (spec.step_count != 0) {
    flags |= CLAP_PARAM_IS_STEPPED;
  }
  if (spec.list) {
    flags |= CLAP_PARAM_IS_ENUM;
  }
  if (spec.read_only) {
    flags |= CLAP_PARAM_IS_READONLY;
  } else {
    flags |= CLAP_PARAM_REQUIRES_PROCESS;
  }
  return flags;
}

bool clap_parameter_info(std::size_t index, clap_param_info_t& info) noexcept {
  const ParameterSpec* spec = parameter_spec(index);
  if (spec == nullptr || spec->name == nullptr) {
    return false;
  }
  const std::size_t length = std::strlen(spec->name);
  if (length >= sizeof(info.name)) {
    return false;
  }
  info = {};
  info.id = static_cast<clap_id>(spec->id);
  info.flags = clap_parameter_flags(*spec);
  std::memcpy(info.name, spec->name, length + 1U);
  info.module[0] = '\0';
  info.min_value = spec->minimum;
  info.max_value = spec->maximum;
  info.default_value = spec->default_value;
  return true;
}

}  // namespace m3
