#include "m3/monophonic_pitch_detector.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "m3/pitch_math.hpp"

namespace m3 {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
constexpr double kFastEnergySeconds = 0.008;
constexpr double kSlowEnergySeconds = 0.100;
constexpr double kDcCutoffHz = 15.0;
constexpr double kMinimumA4Hz = 400.0;
constexpr double kMaximumA4Hz = 480.0;
constexpr std::uint8_t kMinimumMidiNote = 24U;
constexpr std::uint8_t kMaximumMidiNote = 108U;
constexpr std::array<double, 6> kHarmonicWeights{
    1.00, 0.72, 0.55, 0.42, 0.34, 0.28};

bool valid_config(double sample_rate, const PersistentConfig& config) noexcept {
  return std::isfinite(sample_rate) && sample_rate > 0.0 &&
         std::isfinite(config.a4_hz) && config.a4_hz >= kMinimumA4Hz &&
         config.a4_hz <= kMaximumA4Hz &&
         config.lowest_note >= kMinimumMidiNote &&
         config.highest_note >= config.lowest_note &&
         config.highest_note <= kMaximumMidiNote &&
         static_cast<std::size_t>(config.highest_note - config.lowest_note) +
                 1U <=
             kMaxCandidates;
}

std::uint8_t harmonic_limit(std::uint8_t note) noexcept {
  return note <= 52U ? 6U : (note >= 76U ? 3U : 4U);
}

}  // namespace

bool MonophonicPitchDetector::configure(double sample_rate,
                                        const PersistentConfig& config) noexcept {
  configured_ = false;
  cells_ = {};
  if (!valid_config(sample_rate, config)) {
    reset();
    return false;
  }

  sample_rate_ = sample_rate;
  dc_pole = std::exp(-kTwoPi * kDcCutoffHz / sample_rate_);
  correlation_decay = std::exp(-1.0 / (kFastEnergySeconds * sample_rate_));
  slow_energy_decay =
      std::exp(-1.0 / (kSlowEnergySeconds * sample_rate_));
  lowest_note_ = config.lowest_note;
  candidate_count_ = static_cast<std::uint8_t>(
      static_cast<std::uint32_t>(config.highest_note) - lowest_note_ + 1U);
  set_runtime_config(config);

  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    const std::uint8_t partials = harmonic_limit(note);
    for (std::size_t harmonic = 0; harmonic < partials; ++harmonic) {
      const double frequency =
          midi_to_frequency(static_cast<double>(note), config.a4_hz) *
          static_cast<double>(harmonic + 1U);
      if (!std::isfinite(frequency) || frequency <= 0.0 ||
          frequency > 0.45 * sample_rate_) {
        continue;
      }
      const double rotation = kTwoPi * frequency / sample_rate_;
      Cell& cell = cells_[cell_index(candidate, harmonic)];
      cell.cosine_step = std::cos(rotation);
      cell.sine_step = std::sin(rotation);
      cell.enabled = std::isfinite(cell.cosine_step) &&
                     std::isfinite(cell.sine_step);
    }
  }
  configured_ = true;
  reset();
  return true;
}

void MonophonicPitchDetector::set_runtime_config(
    const PersistentConfig& config) noexcept {
  sensitivity_ = std::min<std::uint8_t>(config.sensitivity, 100U);
  response_ = std::min<std::uint8_t>(config.response, 100U);
  fixed_velocity_ = std::clamp<std::uint8_t>(config.fixed_velocity, 1U, 127U);
  velocity_mode_ = config.velocity_mode;
}

void MonophonicPitchDetector::reset() noexcept {
  previous_input_ = 0.0;
  previous_dc_output_ = 0.0;
  fast_energy_ = 0.0;
  slow_energy_ = 0.0;
  decision_phase_ = 0U;
  transition_sequence_ = 0U;
  active_note_ = kNoNote;
  pending_note_ = kNoNote;
  pending_ticks_ = 0U;
  quiet_ticks_ = 0U;
  for (Cell& cell : cells_) {
    cell.cosine = 1.0;
    cell.sine = 0.0;
    cell.fast_real = 0.0;
    cell.fast_imaginary = 0.0;
  }
}

void MonophonicPitchDetector::update_cell(Cell& cell, double sample) noexcept {
  const double next_cosine =
      cell.cosine * cell.cosine_step - cell.sine * cell.sine_step;
  const double next_sine =
      cell.sine * cell.cosine_step + cell.cosine * cell.sine_step;
  cell.cosine = next_cosine;
  cell.sine = next_sine;
  const double mix = 1.0 - correlation_decay;
  cell.fast_real = correlation_decay * cell.fast_real +
                   mix * sample * next_cosine;
  cell.fast_imaginary = correlation_decay * cell.fast_imaginary -
                        mix * sample * next_sine;
}

std::uint8_t MonophonicPitchDetector::attack_decisions() const noexcept {
  return static_cast<std::uint8_t>(2U + response_ / 20U);
}

std::uint8_t MonophonicPitchDetector::release_decisions() const noexcept {
  return static_cast<std::uint8_t>(30U + response_ / 5U);
}

double MonophonicPitchDetector::signal_floor() const noexcept {
  const double energy_db = -70.0 +
                           0.20 * static_cast<double>(100U - sensitivity_);
  return std::pow(10.0, energy_db / 10.0);
}

std::uint8_t MonophonicPitchDetector::dynamic_velocity() const noexcept {
  if (velocity_mode_ == VelocityMode::fixed) {
    return fixed_velocity_;
  }
  const double amplitude = std::sqrt(std::max(0.0, fast_energy_));
  const double db = 20.0 * std::log10(std::max(amplitude, 1.0e-12));
  const double normalized = std::clamp((db + 60.0) / 54.0, 0.0, 1.0);
  const double velocity = 1.0 + normalized * 126.0;
  return static_cast<std::uint8_t>(std::lround(velocity));
}

void MonophonicPitchDetector::append_transition(
    DetectorDecision& decision, TransitionKind kind, std::uint8_t note,
    std::uint8_t velocity) noexcept {
  const VoiceTransition transition{
      0U, kind, note, velocity, transition_sequence_++};
  static_cast<void>(decision.transitions.push_back(transition));
}

DetectorDecision MonophonicPitchDetector::make_decision() noexcept {
  DetectorDecision decision;
  const bool quiet = fast_energy_ < signal_floor() ||
                     fast_energy_ < slow_energy_ * 0.05;
  if (quiet) {
    pending_note_ = kNoNote;
    pending_ticks_ = 0U;
    if (active_note_ != kNoNote && quiet_ticks_ < 255U) {
      ++quiet_ticks_;
      if (quiet_ticks_ >= release_decisions()) {
        append_transition(decision, TransitionKind::note_off, active_note_, 0U);
        active_note_ = kNoNote;
        quiet_ticks_ = 0U;
      }
    }
    return decision;
  }

  quiet_ticks_ = 0U;
  double best_score = 0.0;
  std::uint8_t best_note = kNoNote;
  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    double score = 0.0;
    for (std::size_t harmonic = 0; harmonic < kHarmonicCount; ++harmonic) {
      const Cell& cell = cells_[cell_index(candidate, harmonic)];
      if (!cell.enabled) {
        continue;
      }
      const double energy = cell.fast_real * cell.fast_real +
                            cell.fast_imaginary * cell.fast_imaginary;
      score += kHarmonicWeights[harmonic] * energy;
    }
    if (score > best_score) {
      best_score = score;
      best_note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    }
  }

  const bool candidate_is_coherent =
      best_note != kNoNote && best_score > fast_energy_ * 0.05;
  if (!candidate_is_coherent) {
    pending_note_ = kNoNote;
    pending_ticks_ = 0U;
    return decision;
  }
  if (best_note == active_note_) {
    pending_note_ = kNoNote;
    pending_ticks_ = 0U;
    return decision;
  }
  if (best_note != pending_note_) {
    pending_note_ = best_note;
    pending_ticks_ = 1U;
  } else if (pending_ticks_ < 255U) {
    ++pending_ticks_;
  }
  if (pending_ticks_ < attack_decisions()) {
    return decision;
  }
  if (active_note_ != kNoNote) {
    append_transition(decision, TransitionKind::note_off, active_note_, 0U);
  }
  active_note_ = best_note;
  append_transition(decision, TransitionKind::note_on, active_note_,
                    dynamic_velocity());
  pending_note_ = kNoNote;
  pending_ticks_ = 0U;
  return decision;
}

DetectorDecision MonophonicPitchDetector::process_sample(double sample) noexcept {
  if (!configured_ || !std::isfinite(sample)) {
    return {};
  }
  const double dc_blocked = sample - previous_input_ + dc_pole * previous_dc_output_;
  previous_input_ = sample;
  previous_dc_output_ = dc_blocked;
  const double power = dc_blocked * dc_blocked;
  const double energy_mix = 1.0 - correlation_decay;
  fast_energy_ = correlation_decay * fast_energy_ + energy_mix * power;
  const double slow_energy_mix = 1.0 - slow_energy_decay;
  slow_energy_ = slow_energy_decay * slow_energy_ + slow_energy_mix * power;
  for (Cell& cell : cells_) {
    if (cell.enabled) {
      update_cell(cell, dc_blocked);
    }
  }
  ++decision_phase_;
  if (decision_phase_ < kDecisionQuantum) {
    return {};
  }
  decision_phase_ = 0U;
  return make_decision();
}

}  // namespace m3
