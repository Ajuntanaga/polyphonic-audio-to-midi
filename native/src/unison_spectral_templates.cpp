#include "m3/unison_spectral_templates.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace m3 {
namespace {

struct FactorySpectralRow final {
  std::uint8_t phase{};
  std::uint8_t note{};
  std::uint8_t string{};
  std::array<std::uint16_t, kUnisonSpectralFeatureCount> fingerprint{};
};

#include "../assets/m3_unison_spectral_templates_v1.inc"

}  // namespace

bool factory_unison_spectral_templates(
    UnisonSpectralPhase phase, std::uint8_t midi_note,
    UnisonSpectralTemplateSet& output) noexcept {
  output = {};
  const std::size_t phase_index = static_cast<std::size_t>(phase);
  if (phase_index > static_cast<std::size_t>(UnisonSpectralPhase::settled) ||
      midi_note > 127U) {
    return false;
  }
  constexpr double kScale = 1.0 / 65535.0;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::size_t key = (phase_index * 128U + midi_note) * kMaxVoices +
                            string;
    const std::int16_t row_index = kFactorySpectralIndex[key];
    if (row_index < 0) {
      continue;
    }
    const FactorySpectralRow& row =
        kFactorySpectralRows[static_cast<std::size_t>(row_index)];
    if (row.phase != phase_index || row.note != midi_note ||
        row.string != string) {
      output = {};
      return false;
    }
    for (std::size_t feature = 0U;
         feature < kUnisonSpectralFeatureCount; ++feature) {
      output.fingerprint[string][feature] =
          static_cast<double>(row.fingerprint[feature]) * kScale;
    }
    output.valid_mask = static_cast<std::uint8_t>(
        output.valid_mask | (std::uint8_t{1U} << string));
  }
  return output.valid_mask != 0U;
}

}  // namespace m3
