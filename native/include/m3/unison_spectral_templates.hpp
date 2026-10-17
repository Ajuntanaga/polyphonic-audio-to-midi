#pragma once

#include <cstdint>

#include "m3/unison_spectral_classifier.hpp"
#include "m3/unison_spectral_tracker.hpp"

namespace m3 {

// Expands the embedded Q16 factory bank into a normalized template set. The
// bank is generated from the audited blended physical-string corpus.
[[nodiscard]] bool factory_unison_spectral_templates(
    UnisonSpectralPhase phase, std::uint8_t midi_note,
    UnisonSpectralTemplateSet& output) noexcept;

}  // namespace m3
