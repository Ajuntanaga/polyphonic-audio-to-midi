#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "m3/constants.hpp"

namespace m3 {

inline constexpr std::size_t kCalibrationFretCount = 25U;
inline constexpr std::size_t kCalibrationHarmonicCount = 6U;

enum class CalibrationPointQuality : std::uint8_t {
  missing,
  measured,
  interpolated,
};

struct StringCalibrationPoint final {
  std::int16_t cents_offset_q8{};
  std::array<std::uint16_t, kCalibrationHarmonicCount> harmonic_profile_q15{};
  std::uint16_t confidence_q15{};
  std::uint16_t observation_count{};
  CalibrationPointQuality quality{CalibrationPointQuality::missing};
};

struct StringCalibrationBank final {
  std::array<std::array<StringCalibrationPoint, kCalibrationFretCount>,
             kMaxVoices>
      points{};
  std::uint8_t calibrated_string_mask{};

  [[nodiscard]] const StringCalibrationPoint* point(
      std::size_t string_index, std::size_t fret) const noexcept;
  [[nodiscard]] bool string_calibrated(std::size_t string_index) const noexcept;
  void clear_string(std::size_t string_index) noexcept;
  void clear() noexcept;
};

struct CalibrationObservation final {
  double midi_pitch{};
  std::array<double, kCalibrationHarmonicCount> harmonic_energy{};
  double confidence{};
};

enum class CalibrationSweepPhase : std::uint8_t {
  idle,
  waiting_open,
  ascending,
  descending,
  complete,
  insufficient,
};

struct CalibrationSweepStatus final {
  CalibrationSweepPhase phase{CalibrationSweepPhase::idle};
  std::uint8_t string_index{};
  std::uint8_t highest_fret{};
  std::uint8_t measured_frets{};
  std::uint8_t interpolated_frets{};
  std::uint32_t accepted_observations{};
  std::uint32_t rejected_observations{};
};

// Learns one physical string from a continuous open -> fret 24 -> open sweep.
// The audio thread supplies bounded spectral observations; no allocation,
// locks, file access, or look-ahead occurs here.
class StringSweepCalibrator final {
 public:
  bool begin(std::uint8_t string_index) noexcept;
  bool observe(const CalibrationObservation& observation) noexcept;
  void cancel() noexcept;
  void clear() noexcept;

  [[nodiscard]] bool active() const noexcept;
  [[nodiscard]] CalibrationSweepStatus status() const noexcept;
  [[nodiscard]] const StringCalibrationBank& bank() const noexcept;
  void set_bank(const StringCalibrationBank& bank) noexcept;

 private:
  struct Accumulator final {
    double cents_sum{};
    double cents_square_sum{};
    double confidence_sum{};
    std::array<double, kCalibrationHarmonicCount> harmonic_sum{};
    std::uint16_t count{};
  };

  void finalize() noexcept;
  static bool normalized_profile(
      const CalibrationObservation& observation,
      std::array<double, kCalibrationHarmonicCount>& profile) noexcept;
  static double profile_similarity(const Accumulator& left,
                                   const Accumulator& right) noexcept;

  StringCalibrationBank bank_{};
  std::array<Accumulator, kCalibrationFretCount> ascending_{};
  std::array<Accumulator, kCalibrationFretCount> descending_{};
  CalibrationSweepStatus status_{};
};

}  // namespace m3
