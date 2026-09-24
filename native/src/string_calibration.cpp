#include "m3/string_calibration.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace m3 {
namespace {

constexpr double kMaximumCenterErrorCents = 35.0;
constexpr double kMinimumConfidence = 0.45;
constexpr double kMaximumOpenTuneErrorCents = 8.0;
constexpr double kMaximumOpenDeviationCents = 6.0;
constexpr std::uint16_t kOpenLockObservations = 64U;
constexpr std::uint16_t kMinimumObservationsPerDirection = 3U;
constexpr std::uint8_t kMinimumMeasuredFrets = 18U;
constexpr double kMaximumDirectionOffsetDifferenceCents = 24.0;
constexpr double kMinimumDirectionProfileSimilarity = 0.72;
constexpr double kQ15Scale = 32767.0;

bool finite_nonnegative(double value) noexcept {
  return std::isfinite(value) && value >= 0.0;
}

std::uint16_t q15(double value) noexcept {
  return static_cast<std::uint16_t>(std::lround(
      std::clamp(value, 0.0, 1.0) * kQ15Scale));
}

}  // namespace

const StringCalibrationPoint* StringCalibrationBank::point(
    std::size_t string_index, std::size_t fret) const noexcept {
  return string_index < points.size() && fret < points[string_index].size()
             ? &points[string_index][fret]
             : nullptr;
}

bool StringCalibrationBank::string_calibrated(
    std::size_t string_index) const noexcept {
  return string_index < kMaxVoices &&
         (calibrated_string_mask & (1U << string_index)) != 0U;
}

void StringCalibrationBank::clear_string(std::size_t string_index) noexcept {
  if (string_index >= points.size()) {
    return;
  }
  points[string_index] = {};
  calibrated_string_mask = static_cast<std::uint8_t>(
      calibrated_string_mask & ~(1U << string_index));
}

void StringCalibrationBank::clear() noexcept {
  points = {};
  calibrated_string_mask = 0U;
}

bool StringSweepCalibrator::begin(std::uint8_t string_index) noexcept {
  if (string_index >= kMaxVoices || active()) {
    return false;
  }
  ascending_ = {};
  descending_ = {};
  status_ = {};
  status_.phase = CalibrationSweepPhase::waiting_open;
  status_.string_index = string_index;
  return true;
}

bool StringSweepCalibrator::normalized_profile(
    const CalibrationObservation& observation,
    std::array<double, kCalibrationHarmonicCount>& profile) noexcept {
  double total = 0.0;
  for (const double energy : observation.harmonic_energy) {
    if (!finite_nonnegative(energy)) {
      return false;
    }
    total += energy;
  }
  if (!std::isfinite(total) || total <= std::numeric_limits<double>::epsilon()) {
    return false;
  }
  for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
    profile[harmonic] = observation.harmonic_energy[harmonic] / total;
  }
  return true;
}

bool StringSweepCalibrator::observe(
    const CalibrationObservation& observation) noexcept {
  const auto reject = [this]() noexcept {
    if (active()) {
      ++status_.rejected_observations;
    }
    return false;
  };
  if (!active() || !std::isfinite(observation.midi_pitch) ||
      !std::isfinite(observation.confidence) ||
      observation.confidence < kMinimumConfidence ||
      observation.confidence > 1.0) {
    return reject();
  }
  std::array<double, kCalibrationHarmonicCount> profile{};
  if (!normalized_profile(observation, profile)) {
    return reject();
  }

  const double relative =
      observation.midi_pitch -
      static_cast<double>(kM3OpenNotes[status_.string_index]);
  const long rounded = std::lround(relative);
  const double cents = (relative - static_cast<double>(rounded)) * 100.0;
  if (rounded < 0L || rounded >= static_cast<long>(kCalibrationFretCount) ||
      std::abs(cents) > kMaximumCenterErrorCents) {
    return reject();
  }
  const auto fret = static_cast<std::uint8_t>(rounded);

  if (status_.phase == CalibrationSweepPhase::waiting_open) {
    if (fret != 0U || std::abs(cents) > kMaximumOpenTuneErrorCents) {
      // Treat isolated estimator excursions as outliers, not as proof that
      // the player released or retuned the string.  The detector's initial
      // correlation settling can interleave centered observations with wide
      // cents excursions even for a steady, correctly tuned sine.  Only
      // centered observations contribute to the lock statistics; a string
      // that remains out of tune therefore cannot accumulate lock evidence.
      return reject();
    }
    Accumulator& open = ascending_[0U];
    open.cents_sum += cents;
    open.cents_square_sum += cents * cents;
    open.confidence_sum += observation.confidence;
    for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
      open.harmonic_sum[harmonic] += profile[harmonic];
    }
    if (open.count < std::numeric_limits<std::uint16_t>::max()) {
      ++open.count;
    }
    ++status_.accepted_observations;
    if (open.count >= kOpenLockObservations) {
      const double mean = open.cents_sum / open.count;
      const double variance = std::max(
          0.0, open.cents_square_sum / open.count - mean * mean);
      if (std::sqrt(variance) <= kMaximumOpenDeviationCents) {
        status_.phase = CalibrationSweepPhase::ascending;
      } else {
        // Startup correlation settling must not poison the entire open-string
        // hold. Require a fresh complete stable window before locking.
        open = {};
      }
    }
    return true;
  }
  status_.highest_fret = std::max(status_.highest_fret, fret);

  if (status_.phase == CalibrationSweepPhase::ascending &&
      status_.highest_fret >= kCalibrationFretCount - 1U &&
      fret + 1U <= status_.highest_fret) {
    status_.phase = CalibrationSweepPhase::descending;
  }

  // The downward glide enters the open-note bin from above, so its early
  // estimates are intentionally not representative of the tuned endpoint.
  // Complete only from a brief centered open-string hold after the return.
  if (status_.phase == CalibrationSweepPhase::descending && fret == 0U &&
      std::abs(cents) > kMaximumOpenTuneErrorCents) {
    return reject();
  }

  Accumulator& accumulator =
      status_.phase == CalibrationSweepPhase::descending
          ? descending_[fret]
          : ascending_[fret];
  if (accumulator.count < std::numeric_limits<std::uint16_t>::max()) {
    accumulator.cents_sum += cents;
    accumulator.cents_square_sum += cents * cents;
    accumulator.confidence_sum += observation.confidence;
    for (std::size_t harmonic = 0U; harmonic < profile.size(); ++harmonic) {
      accumulator.harmonic_sum[harmonic] += profile[harmonic];
    }
    ++accumulator.count;
  }
  // The turnaround sample belongs to both traversals. Copying the top-fret
  // plateau into the descending pass avoids asking the player to lift and
  // re-fret 24 merely to mark a direction change.
  if (status_.phase == CalibrationSweepPhase::ascending &&
      fret == kCalibrationFretCount - 1U) {
    descending_[fret] = accumulator;
  }
  ++status_.accepted_observations;

  if (status_.phase == CalibrationSweepPhase::descending && fret == 0U &&
      descending_[0U].count >= kMinimumObservationsPerDirection) {
    finalize();
  }
  return true;
}

double StringSweepCalibrator::profile_similarity(
    const Accumulator& left, const Accumulator& right) noexcept {
  if (left.count == 0U || right.count == 0U) {
    return 0.0;
  }
  double dot = 0.0;
  double left_norm = 0.0;
  double right_norm = 0.0;
  for (std::size_t harmonic = 0U; harmonic < kCalibrationHarmonicCount;
       ++harmonic) {
    const double a = left.harmonic_sum[harmonic] / left.count;
    const double b = right.harmonic_sum[harmonic] / right.count;
    dot += a * b;
    left_norm += a * a;
    right_norm += b * b;
  }
  const double denominator = std::sqrt(left_norm * right_norm);
  return denominator > 0.0 ? dot / denominator : 0.0;
}

void StringSweepCalibrator::finalize() noexcept {
  std::array<StringCalibrationPoint, kCalibrationFretCount> result{};
  std::uint8_t measured = 0U;
  for (std::size_t fret = 0U; fret < kCalibrationFretCount; ++fret) {
    const Accumulator& up = ascending_[fret];
    const Accumulator& down = descending_[fret];
    if (up.count < kMinimumObservationsPerDirection ||
        down.count < kMinimumObservationsPerDirection) {
      continue;
    }
    const double up_cents = up.cents_sum / up.count;
    const double down_cents = down.cents_sum / down.count;
    if (std::abs(up_cents - down_cents) >
            kMaximumDirectionOffsetDifferenceCents ||
        profile_similarity(up, down) <
            kMinimumDirectionProfileSimilarity) {
      continue;
    }
    StringCalibrationPoint& point = result[fret];
    point.cents_offset_q8 = static_cast<std::int16_t>(std::lround(
        std::clamp((up_cents + down_cents) * 0.5, -50.0, 50.0) * 256.0));
    const std::uint32_t total_count =
        static_cast<std::uint32_t>(up.count) + down.count;
    for (std::size_t harmonic = 0U; harmonic < kCalibrationHarmonicCount;
         ++harmonic) {
      point.harmonic_profile_q15[harmonic] = q15(
          (up.harmonic_sum[harmonic] + down.harmonic_sum[harmonic]) /
          static_cast<double>(total_count));
    }
    point.confidence_q15 = q15(
        (up.confidence_sum + down.confidence_sum) /
        static_cast<double>(total_count));
    point.observation_count = static_cast<std::uint16_t>(std::min<std::uint32_t>(
        total_count, std::numeric_limits<std::uint16_t>::max()));
    point.quality = CalibrationPointQuality::measured;
    ++measured;
  }

  status_.measured_frets = measured;
  const bool endpoints =
      result.front().quality == CalibrationPointQuality::measured &&
      result.back().quality == CalibrationPointQuality::measured;
  if (!endpoints || measured < kMinimumMeasuredFrets) {
    status_.phase = CalibrationSweepPhase::insufficient;
    return;
  }

  std::uint8_t interpolated = 0U;
  for (std::size_t fret = 1U; fret + 1U < kCalibrationFretCount; ++fret) {
    if (result[fret].quality == CalibrationPointQuality::measured) {
      continue;
    }
    std::size_t left = fret;
    while (left > 0U &&
           result[left].quality != CalibrationPointQuality::measured) {
      --left;
    }
    std::size_t right = fret;
    while (right + 1U < kCalibrationFretCount &&
           result[right].quality != CalibrationPointQuality::measured) {
      ++right;
    }
    if (result[left].quality != CalibrationPointQuality::measured ||
        result[right].quality != CalibrationPointQuality::measured ||
        right <= left) {
      continue;
    }
    const double amount = static_cast<double>(fret - left) /
                          static_cast<double>(right - left);
    StringCalibrationPoint& point = result[fret];
    point.cents_offset_q8 = static_cast<std::int16_t>(std::lround(
        static_cast<double>(result[left].cents_offset_q8) * (1.0 - amount) +
        static_cast<double>(result[right].cents_offset_q8) * amount));
    for (std::size_t harmonic = 0U; harmonic < kCalibrationHarmonicCount;
         ++harmonic) {
      point.harmonic_profile_q15[harmonic] =
          static_cast<std::uint16_t>(std::lround(
              static_cast<double>(result[left].harmonic_profile_q15[harmonic]) *
                  (1.0 - amount) +
              static_cast<double>(result[right].harmonic_profile_q15[harmonic]) *
                  amount));
    }
    point.confidence_q15 = std::min(result[left].confidence_q15,
                                    result[right].confidence_q15);
    point.quality = CalibrationPointQuality::interpolated;
    ++interpolated;
  }

  bank_.points[status_.string_index] = result;
  bank_.calibrated_string_mask = static_cast<std::uint8_t>(
      bank_.calibrated_string_mask | (1U << status_.string_index));
  status_.interpolated_frets = interpolated;
  status_.phase = CalibrationSweepPhase::complete;
}

void StringSweepCalibrator::cancel() noexcept {
  if (active()) {
    status_.phase = CalibrationSweepPhase::idle;
  }
  ascending_ = {};
  descending_ = {};
}

void StringSweepCalibrator::clear() noexcept {
  cancel();
  bank_.clear();
  status_ = {};
}

bool StringSweepCalibrator::active() const noexcept {
  return status_.phase == CalibrationSweepPhase::waiting_open ||
         status_.phase == CalibrationSweepPhase::ascending ||
         status_.phase == CalibrationSweepPhase::descending;
}

CalibrationSweepStatus StringSweepCalibrator::status() const noexcept {
  return status_;
}

const StringCalibrationBank& StringSweepCalibrator::bank() const noexcept {
  return bank_;
}

void StringSweepCalibrator::set_bank(
    const StringCalibrationBank& bank) noexcept {
  if (!active()) {
    bank_ = bank;
  }
}

}  // namespace m3
