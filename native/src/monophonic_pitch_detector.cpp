#include "m3/monophonic_pitch_detector.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "m3/pitch_math.hpp"

namespace m3 {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
// At the lowest supported pitches, a very short correlator cannot distinguish
// neighboring semitones. This remains causal, but retains enough history to
// rank independent low-string fundamentals instead of adjacent-bin leakage.
constexpr double kCorrelationSeconds = 0.080;
constexpr double kFastEnergySeconds = 0.008;
constexpr double kSlowEnergySeconds = 0.100;
constexpr double kTunerSmoothingSeconds = 0.075;
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
         config.max_polyphony >= 1U && config.max_polyphony <= kMaxVoices &&
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
  a4_hz_ = config.a4_hz;
  dc_pole = std::exp(-kTwoPi * kDcCutoffHz / sample_rate_);
  correlation_decay = std::exp(-1.0 / (kCorrelationSeconds * sample_rate_));
  fast_energy_decay =
      std::exp(-1.0 / (kFastEnergySeconds * sample_rate_));
  slow_energy_decay =
      std::exp(-1.0 / (kSlowEnergySeconds * sample_rate_));
  lowest_note_ = config.lowest_note;
  candidate_count_ = static_cast<std::uint8_t>(
      static_cast<std::uint32_t>(config.highest_note) - lowest_note_ + 1U);
  max_polyphony_ = config.max_polyphony;
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
  active_ = {};
  pending_ticks_ = {};
  quiet_ticks_ = {};
  previous_fundamental_real_ = {};
  previous_fundamental_imaginary_ = {};
  smoothed_phase_delta_ = {};
  previous_fundamental_valid_ = {};
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
  const std::uint32_t response_ticks = 2U + response_ / 20U;
  const std::uint32_t settling_ticks = static_cast<std::uint32_t>(std::ceil(
      kCorrelationSeconds * sample_rate_ /
      static_cast<double>(kDecisionQuantum)));
  return static_cast<std::uint8_t>(
      std::min<std::uint32_t>(255U, std::max(response_ticks, settling_ticks)));
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

double MonophonicPitchDetector::candidate_score(
    std::size_t candidate) const noexcept {
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
  return score;
}

DetectorDecision MonophonicPitchDetector::make_decision() noexcept {
  DetectorDecision decision;
  decision.tuner.updated = true;
  const bool quiet = fast_energy_ < signal_floor() ||
                     fast_energy_ < slow_energy_ * 0.05;
  std::array<double, kMaxCandidates> scores{};
  std::array<bool, kMaxCandidates> selected{};
  const double admission_floor = quiet ? std::numeric_limits<double>::infinity()
                                       : fast_energy_ * 0.015;
  std::size_t selected_count = 0U;

  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    scores[candidate] = candidate_score(candidate);
  }
  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    if (active_[candidate] && scores[candidate] > admission_floor * 0.35 &&
        selected_count < max_polyphony_) {
      selected[candidate] = true;
      ++selected_count;
    }
  }
  while (selected_count < max_polyphony_) {
    std::size_t best_candidate = kMaxCandidates;
    double best_score = admission_floor;
    for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
      const bool exceeds_lower_neighbor =
          candidate == 0U || scores[candidate] > scores[candidate - 1U];
      const bool meets_upper_neighbor =
          candidate + 1U == candidate_count_ ||
          scores[candidate] >= scores[candidate + 1U];
      if (!selected[candidate] && exceeds_lower_neighbor &&
          meets_upper_neighbor && scores[candidate] > best_score) {
        best_score = scores[candidate];
        best_candidate = candidate;
      }
    }
    if (best_candidate == kMaxCandidates) {
      break;
    }
    selected[best_candidate] = true;
    ++selected_count;
  }

  const double tuner_smoothing =
      1.0 - std::exp(-static_cast<double>(kDecisionQuantum) /
                     (kTunerSmoothingSeconds * sample_rate_));
  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    const Cell& fundamental = cells_[cell_index(candidate, 0U)];
    const double current_magnitude =
        fundamental.fast_real * fundamental.fast_real +
        fundamental.fast_imaginary * fundamental.fast_imaginary;
    const double previous_real = previous_fundamental_real_[candidate];
    const double previous_imaginary =
        previous_fundamental_imaginary_[candidate];
    const double previous_magnitude =
        previous_real * previous_real + previous_imaginary * previous_imaginary;
    if (!quiet && previous_fundamental_valid_[candidate] &&
        current_magnitude > std::numeric_limits<double>::epsilon() &&
        previous_magnitude > std::numeric_limits<double>::epsilon()) {
      const double cross = previous_real * fundamental.fast_imaginary -
                           previous_imaginary * fundamental.fast_real;
      const double dot = previous_real * fundamental.fast_real +
                         previous_imaginary * fundamental.fast_imaginary;
      const double phase_delta = std::atan2(cross, dot);
      smoothed_phase_delta_[candidate] +=
          tuner_smoothing *
          (phase_delta - smoothed_phase_delta_[candidate]);
    } else if (quiet) {
      smoothed_phase_delta_[candidate] = 0.0;
    }
    previous_fundamental_real_[candidate] = fundamental.fast_real;
    previous_fundamental_imaginary_[candidate] = fundamental.fast_imaginary;
    previous_fundamental_valid_[candidate] = !quiet && fundamental.enabled;
  }

  std::size_t tuner_candidate = kMaxCandidates;
  double tuner_score = admission_floor;
  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    if (selected[candidate] && scores[candidate] > tuner_score) {
      tuner_candidate = candidate;
      tuner_score = scores[candidate];
    }
  }
  if (tuner_candidate != kMaxCandidates &&
      previous_fundamental_valid_[tuner_candidate]) {
    const double center_note =
        static_cast<double>(lowest_note_ + tuner_candidate);
    const double center_frequency = midi_to_frequency(center_note, a4_hz_);
    const double frequency = center_frequency +
        smoothed_phase_delta_[tuner_candidate] * sample_rate_ /
            (kTwoPi * static_cast<double>(kDecisionQuantum));
    if (std::isfinite(frequency) && frequency > 0.0) {
      const double fractional_note =
          69.0 + 12.0 * std::log2(frequency / a4_hz_);
      const double nearest_note = std::round(fractional_note);
      const double cents = 100.0 * (fractional_note - nearest_note);
      if (std::isfinite(fractional_note) && std::isfinite(cents) &&
          nearest_note >= 0.0 && nearest_note <= 127.0 && cents >= -50.0 &&
          cents <= 50.0) {
        decision.tuner.signal = true;
        decision.tuner.note = static_cast<std::uint8_t>(nearest_note);
        decision.tuner.cents = cents;
      }
    }
  }

  std::size_t active_count = 0U;
  for (bool is_active : active_) {
    if (is_active) {
      ++active_count;
    }
  }
  for (std::size_t candidate = 0; candidate < candidate_count_; ++candidate) {
    const std::uint8_t note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    if (selected[candidate]) {
      quiet_ticks_[candidate] = 0U;
      if (active_[candidate]) {
        pending_ticks_[candidate] = 0U;
        continue;
      }
      if (pending_ticks_[candidate] < 255U) {
        ++pending_ticks_[candidate];
      }
      if (pending_ticks_[candidate] >= attack_decisions() &&
          active_count < max_polyphony_) {
        append_transition(decision, TransitionKind::note_on, note,
                          dynamic_velocity());
        active_[candidate] = true;
        ++active_count;
        pending_ticks_[candidate] = 0U;
      }
      continue;
    }

    pending_ticks_[candidate] = 0U;
    if (!active_[candidate]) {
      continue;
    }
    if (quiet_ticks_[candidate] < 255U) {
      ++quiet_ticks_[candidate];
    }
    if (quiet_ticks_[candidate] >= release_decisions()) {
      append_transition(decision, TransitionKind::note_off, note, 0U);
      active_[candidate] = false;
      --active_count;
      quiet_ticks_[candidate] = 0U;
    }
  }
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
  const double energy_mix = 1.0 - fast_energy_decay;
  fast_energy_ = fast_energy_decay * fast_energy_ + energy_mix * power;
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
