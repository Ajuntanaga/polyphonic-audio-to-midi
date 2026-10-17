#pragma once

#include <cstdint>

#include "m3/string_calibration.hpp"

namespace m3 {

// Frozen M3-profile prior derived from the annotated 9--80 string corpus.
// It is immutable, allocation-free, and contains no host or device access.
[[nodiscard]] const StringCalibrationBank&
factory_m3_calibration_bank() noexcept;

// A saved or live-calibrated string replaces the corresponding factory row;
// strings absent from the override retain the measured factory prior.
[[nodiscard]] StringCalibrationBank merge_m3_factory_calibration(
    const StringCalibrationBank& overrides) noexcept;

struct CalibratedNoteProjection final {
  std::uint8_t note{};
  std::int8_t fret_delta{};
  double error_improvement_cents{};
  bool changed{};
};

// Projects a continuous detected pitch onto the current or adjacent measured
// fret center for one already-assigned physical string. It never chooses a
// string and cannot move by more than one semitone.
[[nodiscard]] CalibratedNoteProjection project_calibrated_note(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret,
    double minimum_error_improvement_cents) noexcept;

}  // namespace m3
