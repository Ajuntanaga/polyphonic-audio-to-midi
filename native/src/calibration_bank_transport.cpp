#include "m3/calibration_bank_transport.hpp"

#include <algorithm>

namespace m3 {
namespace {

static_assert(std::atomic<std::uint32_t>::is_always_lock_free,
              "M3 calibration transport requires lock-free 32-bit atomics");

std::uint32_t pair_u16(std::uint16_t low, std::uint16_t high) noexcept {
  return static_cast<std::uint32_t>(low) |
         (static_cast<std::uint32_t>(high) << 16U);
}

std::uint16_t low_u16(std::uint32_t value) noexcept {
  return static_cast<std::uint16_t>(value & 0xFFFFU);
}

std::uint16_t high_u16(std::uint32_t value) noexcept {
  return static_cast<std::uint16_t>(value >> 16U);
}

}  // namespace

void CalibrationBankTransport::reset() noexcept {
  sequence_.store(0U, std::memory_order_seq_cst);
  generation_.store(0U, std::memory_order_seq_cst);
  calibrated_mask_.store(0U, std::memory_order_seq_cst);
  for (auto& word : words_) {
    word.store(0U, std::memory_order_seq_cst);
  }
}

void CalibrationBankTransport::publish(const StringCalibrationBank& bank,
                                       std::uint32_t generation) noexcept {
  const std::uint32_t before = sequence_.load(std::memory_order_seq_cst);
  const std::uint32_t writing = before | 1U;
  sequence_.store(writing, std::memory_order_seq_cst);
  calibrated_mask_.store(bank.calibrated_string_mask,
                         std::memory_order_seq_cst);
  std::size_t word_index = 0U;
  for (const auto& string : bank.points) {
    for (const StringCalibrationPoint& point : string) {
      words_[word_index++].store(
          pair_u16(static_cast<std::uint16_t>(point.cents_offset_q8),
                   point.confidence_q15),
          std::memory_order_seq_cst);
      words_[word_index++].store(
          static_cast<std::uint32_t>(point.observation_count) |
              (static_cast<std::uint32_t>(point.quality) << 16U),
          std::memory_order_seq_cst);
      for (std::size_t harmonic = 0U;
           harmonic < kCalibrationHarmonicCount; harmonic += 2U) {
        words_[word_index++].store(
            pair_u16(point.harmonic_profile_q15[harmonic],
                     point.harmonic_profile_q15[harmonic + 1U]),
            std::memory_order_seq_cst);
      }
    }
  }
  generation_.store(generation, std::memory_order_seq_cst);
  sequence_.store(writing + 1U, std::memory_order_seq_cst);
}

bool CalibrationBankTransport::read_latest(
    CalibrationBankSnapshot& snapshot) const noexcept {
  for (std::size_t attempt = 0U; attempt < kReadAttempts; ++attempt) {
    const std::uint32_t before = sequence_.load(std::memory_order_seq_cst);
    if (before == 0U || (before & 1U) != 0U) {
      continue;
    }
    CalibrationBankSnapshot candidate;
    candidate.generation = generation_.load(std::memory_order_seq_cst);
    candidate.bank.calibrated_string_mask = static_cast<std::uint8_t>(
        calibrated_mask_.load(std::memory_order_seq_cst) & 0xFFU);
    std::size_t word_index = 0U;
    for (auto& string : candidate.bank.points) {
      for (StringCalibrationPoint& point : string) {
        const std::uint32_t first =
            words_[word_index++].load(std::memory_order_seq_cst);
        const std::uint32_t second =
            words_[word_index++].load(std::memory_order_seq_cst);
        point.cents_offset_q8 = static_cast<std::int16_t>(low_u16(first));
        point.confidence_q15 = high_u16(first);
        point.observation_count = low_u16(second);
        const std::uint32_t raw_quality = (second >> 16U) & 0xFFU;
        point.quality =
            raw_quality <=
                    static_cast<std::uint32_t>(
                        CalibrationPointQuality::interpolated)
                ? static_cast<CalibrationPointQuality>(raw_quality)
                : CalibrationPointQuality::missing;
        for (std::size_t harmonic = 0U;
             harmonic < kCalibrationHarmonicCount; harmonic += 2U) {
          const std::uint32_t pair =
              words_[word_index++].load(std::memory_order_seq_cst);
          point.harmonic_profile_q15[harmonic] = low_u16(pair);
          point.harmonic_profile_q15[harmonic + 1U] = high_u16(pair);
        }
      }
    }
    const std::uint32_t after = sequence_.load(std::memory_order_seq_cst);
    if (before == after && (after & 1U) == 0U) {
      snapshot = candidate;
      return true;
    }
  }
  return false;
}

}  // namespace m3
