#include "m3/factory_calibration.hpp"

#include <cmath>
#include <array>
#include <cstdint>

#include "m3/calibration_state_image.hpp"

namespace m3 {
namespace {

constexpr std::array<std::uint8_t, kCalibrationStateSize>
    kFactoryCalibrationImage{{
#include "../assets/m3_factory_calibration_v2.inc"
    }};

StringCalibrationBank decode_factory_bank() noexcept {
  StringCalibrationBank bank;
  if (!decode_calibration_state(kFactoryCalibrationImage.data(),
                                kFactoryCalibrationImage.size(), bank)) {
    bank.clear();
  }
  return bank;
}

}  // namespace

const StringCalibrationBank& factory_m3_calibration_bank() noexcept {
  static const StringCalibrationBank bank = decode_factory_bank();
  return bank;
}

StringCalibrationBank merge_m3_factory_calibration(
    const StringCalibrationBank& overrides) noexcept {
  StringCalibrationBank merged = factory_m3_calibration_bank();
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if (!overrides.string_calibrated(string)) {
      continue;
    }
    merged.points[string] = overrides.points[string];
    merged.calibrated_string_mask = static_cast<std::uint8_t>(
        merged.calibrated_string_mask | (1U << string));
  }
  return merged;
}

CalibratedNoteProjection project_calibrated_note(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret,
    double minimum_error_improvement_cents) noexcept {
  CalibratedNoteProjection result{note, 0, 0.0, false};
  if (!cents_valid || string_index >= kM3OpenNotes.size() ||
      !bank.string_calibrated(string_index) ||
      !std::isfinite(minimum_error_improvement_cents) ||
      minimum_error_improvement_cents < 0.0 ||
      note < kM3OpenNotes[string_index]) {
    return result;
  }
  const std::size_t fret = note - kM3OpenNotes[string_index];
  if (fret >= kCalibrationFretCount || fret > maximum_fret) {
    return result;
  }
  const StringCalibrationPoint* current = bank.point(string_index, fret);
  if (current == nullptr ||
      current->quality == CalibrationPointQuality::missing) {
    return result;
  }
  const double observed =
      100.0 * static_cast<double>(note) +
      static_cast<double>(cents_q8) / 256.0;
  const auto center = [](std::uint8_t candidate_note,
                         const StringCalibrationPoint& point) noexcept {
    return 100.0 * static_cast<double>(candidate_note) +
           static_cast<double>(point.cents_offset_q8) / 256.0;
  };
  const double current_error = std::abs(observed - center(note, *current));
  double best_error = current_error;
  std::uint8_t best_note = note;
  for (const int direction : {-1, 1}) {
    const int adjacent_note = static_cast<int>(note) + direction;
    const int adjacent_fret = static_cast<int>(fret) + direction;
    if (adjacent_note < 0 || adjacent_note > 127 || adjacent_fret < 0 ||
        adjacent_fret >= static_cast<int>(kCalibrationFretCount) ||
        adjacent_fret > static_cast<int>(maximum_fret)) {
      continue;
    }
    const StringCalibrationPoint* adjacent = bank.point(
        string_index, static_cast<std::size_t>(adjacent_fret));
    if (adjacent == nullptr ||
        adjacent->quality == CalibrationPointQuality::missing) {
      continue;
    }
    const double error = std::abs(
        observed - center(static_cast<std::uint8_t>(adjacent_note),
                          *adjacent));
    if (error + 1.0e-9 < best_error) {
      best_error = error;
      best_note = static_cast<std::uint8_t>(adjacent_note);
    }
  }
  const double improvement = current_error - best_error;
  if (best_note != note && improvement + 1.0e-9 >=
                               minimum_error_improvement_cents) {
    result.note = best_note;
    result.fret_delta = best_note > note ? 1 : -1;
    result.error_improvement_cents = improvement;
    result.changed = true;
  }
  return result;
}

}  // namespace m3
