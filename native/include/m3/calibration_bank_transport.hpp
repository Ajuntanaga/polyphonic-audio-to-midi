#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

#include "m3/string_calibration.hpp"

namespace m3 {

struct CalibrationBankSnapshot final {
  StringCalibrationBank bank{};
  std::uint32_t generation{};
};

// Single-writer/single-reader lock-free transport for the 8 x 25 calibration
// bank. Every payload word is atomic; an odd/even sequence prevents a reader
// from accepting a bank assembled from two audio blocks.
class CalibrationBankTransport final {
 public:
  CalibrationBankTransport() noexcept = default;
  CalibrationBankTransport(const CalibrationBankTransport&) = delete;
  CalibrationBankTransport& operator=(const CalibrationBankTransport&) =
      delete;

  void reset() noexcept;
  void publish(const StringCalibrationBank& bank,
               std::uint32_t generation) noexcept;
  [[nodiscard]] bool read_latest(CalibrationBankSnapshot& snapshot)
      const noexcept;

 private:
  static constexpr std::size_t kWordsPerPoint = 5U;
  static constexpr std::size_t kPointCount =
      kMaxVoices * kCalibrationFretCount;
  static constexpr std::size_t kWordCount = kPointCount * kWordsPerPoint;
  static constexpr std::size_t kReadAttempts = 3U;

  std::atomic<std::uint32_t> sequence_{};
  std::atomic<std::uint32_t> generation_{};
  std::atomic<std::uint32_t> calibrated_mask_{};
  std::array<std::atomic<std::uint32_t>, kWordCount> words_{};
};

}  // namespace m3
