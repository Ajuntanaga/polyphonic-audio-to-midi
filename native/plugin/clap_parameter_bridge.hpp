#pragma once

#include <clap/ext/params.h>

#include <cstddef>

#include "m3/parameter_contract.hpp"

namespace m3 {

clap_param_info_flags clap_parameter_flags(const ParameterSpec& spec) noexcept;
bool clap_parameter_info(std::size_t index, clap_param_info_t& info) noexcept;

}  // namespace m3
