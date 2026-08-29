#pragma once

#include <clap/stream.h>

#include "m3/state_image.hpp"

namespace m3 {

bool save_clap_state(const PersistentConfig& config,
                     const clap_ostream_t* stream) noexcept;
bool load_clap_state(const clap_istream_t* stream,
                     PersistentConfig& output) noexcept;

}  // namespace m3
