#include "m3/monophonic_pitch_detector.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "m3/pitch_math.hpp"

namespace m3 {
namespace {

constexpr double kTwoPi = 6.28318530717958647692;
// A 40 ms causal correlation window is long enough to separate neighbouring
// guitar fundamentals without introducing look-ahead. The previous 8 ms
// window blurred low fundamentals together, which made a bounded multi-voice
// selector prefer subharmonic candidates during attack.
constexpr double kFastEnergySeconds = 0.040;
constexpr double kSlowEnergySeconds = 0.100;
constexpr double kNarrowFundamentalSeconds = 0.250;
// A per-note harmonic envelope longer than the pitch-selection window smooths
// the slow beating of two nearly-unison strings. It is evidence memory only:
// pitch admission and MIDI onset remain on the causal 40/50 ms path.
constexpr double kHarmonicMemorySeconds = 0.350;
// A fixed-frequency correlation cell loses progressively more energy at its
// upper harmonics when a string is slightly detuned.  Undo that known filter
// response only after the causal phase estimator has settled, and keep a hard
// ceiling so attack/noise cannot turn the correction into uncontrolled gain.
constexpr double kMaximumHarmonicEnergyCorrection = 8.0;
constexpr double kNarrowFundamentalRelativeFloor = 0.12;
// A single causal voice reaches stable selection after the 40 ms correlation
// window. A multi-voice selection needs one additional 10 ms settle interval
// so a startup subharmonic cannot be admitted as a chord voice. These are
// admission gates, not look-ahead: every decision uses samples already seen.
constexpr double kSingleVoiceEvidenceSeconds = 0.040;
constexpr double kMultiVoiceEvidenceSeconds = 0.050;
constexpr double kSilenceEnergyRatio = 0.50;
// A naturally ringing string can decay quickly without becoming silence.  A
// hard mute instead leaves the 40 ms energy follower to fall at roughly
// 109 dB/s.  Keep the boundary between the fastest deterministic decay case
// and that follower-only fall; physical recordings can tune it later.
constexpr double kRapidMuteEnergySlopeDbPerSecond = -80.0;
constexpr double kAttackEnergyRatio = 0.95;
constexpr double kDcCutoffHz = 15.0;
constexpr double kMinimumA4Hz = 400.0;
constexpr double kMaximumA4Hz = 480.0;
constexpr std::uint8_t kMinimumMidiNote = 24U;
constexpr std::uint8_t kMaximumMidiNote = 108U;
constexpr std::array<double, 6> kHarmonicWeights{
    1.00, 0.72, 0.55, 0.42, 0.34, 0.28};
constexpr double kCandidateCoherenceRatio = 0.05;
constexpr double kScoreEpsilon = 1.0e-15;
constexpr double kHarmonicFundamentalRatio = 0.70;
constexpr std::array<int, 5> kHarmonicIntervals{12, 19, 24, 28, 31};
// A resonator below a real note can also line up through ratios between two
// non-fundamental partials (3:2, 5:2, 5:3, and neighbours). This M3-only set
// rejects those lower aliases when they have no independent fundamental;
// the direct-fundamental branch still preserves a real musical interval.
constexpr std::array<int, 6> kM3LowerCrossHarmonicIntervals{3, 4, 5, 7, 9, 16};
constexpr std::size_t kM3StringMaskCount = 1U << kM3OpenNotes.size();
constexpr std::size_t kM3OpenChordMinimum = 2U;
constexpr double kM3FrettedNotePenalty = 0.60;
constexpr double kM3FretPenalty = 0.005;
// A full eight-string assignment has the same summed linear fret count under
// many cyclic permutations. A small convex position prior rejects those
// implausible high-fret rotations while leaving a learned string fingerprint
// enough authority to identify a genuinely high fretted string.
constexpr double kM3AssignmentFretShapePenalty = 0.50;
constexpr double kM3ProvisionalStringRetentionBonus = 4.0;
// A sounding per-voice note owns its exposed string/channel until note-off.
// This is larger than the maximum supported 36-fret position prior, while
// feasibility can still override it when that string is unavailable.
constexpr double kM3ExposedStringRetentionBonus = 1024.0;
constexpr double kM3UnisonMinimumComponent = 0.15;
constexpr double kM3UnisonMinimumTemplateDistance = 0.0025;
constexpr double kM3UnisonMinimumErrorImprovement = 0.010;
constexpr double kM3UnisonMaximumErrorRatio = 0.55;
constexpr double kM3UnisonMinimumObservationSeconds = 0.250;
constexpr double kM3UnisonDropoutSeconds = 0.450;
constexpr double kM3UnisonEvidenceSeconds =
    8.0 * static_cast<double>(kDecisionQuantum) / 48000.0;
constexpr std::uint8_t kCandidateEvidenceDropoutDecisions = 2U;
constexpr std::size_t kCandidateMigrationSemitones = 2U;
constexpr double kMinimumReleaseSeconds = 0.050;
constexpr double kMaximumReleaseSeconds = 0.220;
constexpr double kAttackReferenceSampleRate = 48000.0;

bool valid_config(double sample_rate, const PersistentConfig& config) noexcept {
  return std::isfinite(sample_rate) && sample_rate > 0.0 &&
         std::isfinite(config.a4_hz) && config.a4_hz >= kMinimumA4Hz &&
         config.a4_hz <= kMaximumA4Hz &&
         config.lowest_note >= kMinimumMidiNote &&
         config.highest_note >= config.lowest_note &&
         config.highest_note <= kMaximumMidiNote &&
         config.max_polyphony >= 1U && config.max_polyphony <= kMaxVoices &&
         config.max_fret <= 36U &&
         (config.profile_mode == ProfileMode::m3 ||
          config.profile_mode == ProfileMode::general) &&
         static_cast<std::size_t>(config.highest_note - config.lowest_note) +
                 1U <=
             kMaxCandidates;
}

std::uint8_t harmonic_limit(std::uint8_t note) noexcept {
  return note <= 52U ? 6U : (note >= 76U ? 3U : 4U);
}

bool is_local_peak(const std::array<double, kMaxCandidates>& scores,
                   std::size_t candidate, std::size_t count) noexcept {
  if (candidate >= count || scores[candidate] <= kScoreEpsilon) {
    return false;
  }
  if (candidate > 0U && scores[candidate] < scores[candidate - 1U]) {
    return false;
  }
  return candidate + 1U >= count || scores[candidate] > scores[candidate + 1U];
}

bool is_m3_open_note(std::uint8_t note) noexcept {
  for (const std::uint8_t open : kM3OpenNotes) {
    if (note == open) {
      return true;
    }
  }
  return false;
}

bool has_m3_candidate_evidence(
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    std::size_t candidate, std::size_t count) noexcept {
  if (candidate >= count || scores[candidate] <= kScoreEpsilon) {
    return false;
  }
  const double previous_score = candidate > 0U ? scores[candidate - 1U] : 0.0;
  const double next_score = candidate + 1U < count ? scores[candidate + 1U] : 0.0;
  const double previous_fundamental =
      candidate > 0U ? fundamentals[candidate - 1U] : 0.0;
  const double next_fundamental =
      candidate + 1U < count ? fundamentals[candidate + 1U] : 0.0;
  const bool fundamental_peak =
      fundamentals[candidate] >= previous_fundamental &&
      fundamentals[candidate] > next_fundamental;
  const bool energy_plateau = scores[candidate] >= 0.85 * previous_score &&
                              scores[candidate] >= 0.85 * next_score;
  const bool local_energy_peak =
      scores[candidate] >= 1.05 * previous_score &&
      scores[candidate] >= 1.05 * next_score;
  const bool missing_fundamental =
      fundamentals[candidate] <= 0.15 * scores[candidate];
  return (fundamental_peak && energy_plateau) ||
         (missing_fundamental && local_energy_peak) ||
         (candidate == 0U && is_local_peak(scores, candidate, count));
}

bool has_direct_fundamental_peak(
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    std::size_t candidate, std::size_t count) noexcept {
  if (candidate >= count || scores[candidate] <= kScoreEpsilon ||
      fundamentals[candidate] < 0.20 * scores[candidate]) {
    return false;
  }
  if (candidate > 0U && fundamentals[candidate] < fundamentals[candidate - 1U]) {
    return false;
  }
  return candidate + 1U >= count ||
         fundamentals[candidate] > fundamentals[candidate + 1U];
}

bool is_m3_lower_cross_harmonic_shadow(
    std::size_t candidate, std::size_t selected_candidate,
    const std::array<double, kMaxCandidates>& fundamentals) noexcept {
  if (candidate >= selected_candidate ||
      fundamentals[selected_candidate] <= kScoreEpsilon) {
    return false;
  }
  const int interval = static_cast<int>(selected_candidate - candidate);
  for (const int harmonic_interval : kM3LowerCrossHarmonicIntervals) {
    if (interval == harmonic_interval) {
      return fundamentals[candidate] <
             fundamentals[selected_candidate] * kHarmonicFundamentalRatio;
    }
  }
  return false;
}

void assignment_add(std::array<std::uint8_t, kM3StringMaskCount>& reachable,
                    std::uint8_t playable) noexcept {
  std::array<std::uint8_t, kM3StringMaskCount> next{};
  for (std::size_t used = 0U; used < reachable.size(); ++used) {
    if (reachable[used] == 0U) {
      continue;
    }
    const std::uint8_t unused = static_cast<std::uint8_t>(
        playable & ~static_cast<std::uint8_t>(used));
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      if ((unused & bit) != 0U) {
        next[used | bit] = 1U;
      }
    }
  }
  reachable = next;
}

}  // namespace

bool MonophonicPitchDetector::configure(double sample_rate,
                                        const PersistentConfig& config) noexcept {
  configured_ = false;
  cells_ = {};
  lower_cents_guard_cells_ = {};
  upper_cents_guard_cells_ = {};
  if (!valid_config(sample_rate, config)) {
    reset();
    return false;
  }

  sample_rate_ = sample_rate;
  dc_pole = std::exp(-kTwoPi * kDcCutoffHz / sample_rate_);
  correlation_decay = std::exp(-1.0 / (kFastEnergySeconds * sample_rate_));
  narrow_correlation_decay =
      std::exp(-1.0 / (kNarrowFundamentalSeconds * sample_rate_));
  harmonic_memory_decay = std::exp(
      -static_cast<double>(kDecisionQuantum) /
      (kHarmonicMemorySeconds * sample_rate_));
  unison_dropout_decisions_ = static_cast<std::uint16_t>(std::clamp(
      std::ceil(kM3UnisonDropoutSeconds * sample_rate_ /
                static_cast<double>(kDecisionQuantum)),
      1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
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
  const auto configure_guard = [this, &config](
                                   std::array<Cell, kHarmonicCount>& cells,
                                   std::uint8_t note) noexcept {
    const std::uint8_t partials = harmonic_limit(note);
    for (std::size_t harmonic = 0U; harmonic < partials; ++harmonic) {
      const double frequency =
          midi_to_frequency(static_cast<double>(note), config.a4_hz) *
          static_cast<double>(harmonic + 1U);
      if (!std::isfinite(frequency) || frequency <= 0.0 ||
          frequency > 0.45 * sample_rate_) {
        continue;
      }
      const double rotation = kTwoPi * frequency / sample_rate_;
      Cell& cell = cells[harmonic];
      cell.cosine_step = std::cos(rotation);
      cell.sine_step = std::sin(rotation);
      cell.enabled = std::isfinite(cell.cosine_step) &&
                     std::isfinite(cell.sine_step);
    }
  };
  configure_guard(lower_cents_guard_cells_,
                  static_cast<std::uint8_t>(config.lowest_note - 1U));
  configure_guard(upper_cents_guard_cells_,
                  static_cast<std::uint8_t>(config.highest_note + 1U));
  configured_ = true;
  reset();
  return true;
}

void MonophonicPitchDetector::set_runtime_config(
    const PersistentConfig& config) noexcept {
  midi_routing_ = config.midi_routing;
  profile_mode_ = config.profile_mode;
  sensitivity_ = std::min<std::uint8_t>(config.sensitivity, 100U);
  const double energy_db =
      -70.0 + 0.20 * static_cast<double>(100U - sensitivity_);
  signal_floor_ = std::pow(10.0, energy_db / 10.0);
  response_ = std::min<std::uint8_t>(config.response, 100U);
  fixed_velocity_ = std::clamp<std::uint8_t>(config.fixed_velocity, 1U, 127U);
  velocity_mode_ = config.velocity_mode;
  max_polyphony_ = std::clamp<std::uint8_t>(config.max_polyphony, 1U,
                                             static_cast<std::uint8_t>(kMaxVoices));
  max_fret_ = std::min<std::uint8_t>(config.max_fret, 36U);
  refresh_m3_playable_string_masks();
}

void MonophonicPitchDetector::reset() noexcept {
  previous_input_ = 0.0;
  previous_dc_output_ = 0.0;
  fast_energy_ = 0.0;
  slow_energy_ = 0.0;
  previous_decision_energy_ = 0.0;
  decision_phase_ = 0U;
  transition_sequence_ = 0U;
  snapshot_generation_ = 0U;
  signal_samples_ = 0U;
  narrow_signal_samples_ = 0U;
  signal_present_ = false;
  candidate_states_ = {};
  narrow_fundamental_real_ = {};
  narrow_fundamental_imaginary_ = {};
  harmonic_energy_memory_ = {};
  phase_cents_states_ = {};
#if defined(M3_TESTING)
  selection_work_ = {};
#endif
  for (Cell& cell : cells_) {
    cell.cosine = 1.0;
    cell.sine = 0.0;
    cell.fast_real = 0.0;
    cell.fast_imaginary = 0.0;
  }
  const auto reset_guard = [](auto& cells) noexcept {
    for (Cell& cell : cells) {
      cell.cosine = 1.0;
      cell.sine = 0.0;
      cell.fast_real = 0.0;
      cell.fast_imaginary = 0.0;
    }
  };
  reset_guard(lower_cents_guard_cells_);
  reset_guard(upper_cents_guard_cells_);
}

bool MonophonicPitchDetector::begin_string_calibration(
    std::uint8_t string_index) noexcept {
  if (!configured_ || profile_mode_ != ProfileMode::m3 ||
      string_index >= kM3OpenNotes.size()) {
    return false;
  }
  const std::uint16_t highest =
      static_cast<std::uint16_t>(kM3OpenNotes[string_index]) +
      kCalibrationFretCount - 1U;
  const std::uint16_t configured_highest = static_cast<std::uint16_t>(
      static_cast<std::uint16_t>(lowest_note_) +
      static_cast<std::uint16_t>(candidate_count_) - 1U);
  if (kM3OpenNotes[string_index] < lowest_note_ ||
      highest > configured_highest) {
    return false;
  }
  return calibrator_.begin(
      string_index,
      sample_rate_ / static_cast<double>(kDecisionQuantum));
}

void MonophonicPitchDetector::cancel_string_calibration() noexcept {
  calibrator_.cancel();
}

void MonophonicPitchDetector::clear_string_calibration() noexcept {
  calibrator_.clear();
}

CalibrationSweepStatus MonophonicPitchDetector::calibration_status()
    const noexcept {
  return calibrator_.status();
}

const StringCalibrationBank& MonophonicPitchDetector::calibration_bank()
    const noexcept {
  return calibrator_.bank();
}

void MonophonicPitchDetector::set_calibration_bank(
    const StringCalibrationBank& bank) noexcept {
  calibrator_.set_bank(bank);
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
  const double reference_decisions =
      static_cast<double>(2U + response_ / 20U);
  const double seconds = reference_decisions *
                         static_cast<double>(kDecisionQuantum) /
                         kAttackReferenceSampleRate;
  const double decisions = std::ceil(
      seconds * sample_rate_ / static_cast<double>(kDecisionQuantum));
  return static_cast<std::uint8_t>(std::clamp(
      decisions, 1.0,
      static_cast<double>(std::numeric_limits<std::uint8_t>::max())));
}

std::uint16_t MonophonicPitchDetector::release_decisions() const noexcept {
  const double normalized = static_cast<double>(response_) / 100.0;
  const double seconds = kMinimumReleaseSeconds +
                         normalized *
                             (kMaximumReleaseSeconds - kMinimumReleaseSeconds);
  const double decisions = std::ceil(
      seconds * sample_rate_ / static_cast<double>(kDecisionQuantum));
  return static_cast<std::uint16_t>(std::clamp(
      decisions, 1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
}

std::uint8_t MonophonicPitchDetector::candidate_evidence_decisions(
    bool multi_voice) const noexcept {
  const double seconds = multi_voice ? kMultiVoiceEvidenceSeconds
                                     : kSingleVoiceEvidenceSeconds;
  const double decisions = std::ceil(seconds * sample_rate_ /
                                     static_cast<double>(kDecisionQuantum));
  return static_cast<std::uint8_t>(std::clamp(
      decisions, 1.0, static_cast<double>(std::numeric_limits<std::uint8_t>::max())));
}

double MonophonicPitchDetector::signal_floor() const noexcept {
  return signal_floor_;
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
    std::uint8_t velocity, std::uint8_t voice_id) noexcept {
  const VoiceTransition transition{
      0U, kind, note, velocity, transition_sequence_++, voice_id};
  static_cast<void>(decision.transitions.push_back(transition));
}

bool MonophonicPitchDetector::append_candidate_note_on(
    DetectorDecision& decision, std::size_t candidate,
    std::uint8_t velocity) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  CandidateState& state = candidate_states_[candidate];
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  if (profile_mode_ == ProfileMode::m3 &&
      midi_routing_ == MidiRouting::per_voice) {
    std::uint8_t desired = state.assigned_string_mask;
    if (desired == 0U && state.assigned_string < kM3OpenNotes.size()) {
      desired = static_cast<std::uint8_t>(1U << state.assigned_string);
    }
    // A selected pitch is not a MIDI voice until it owns at least one
    // physical string lane.  Activating an unassigned candidate would later
    // emit a generic note-off that can cancel another string's live note.
    if (desired == 0U) {
      return false;
    }
    for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((desired & (1U << string)) != 0U) {
        append_transition(decision, TransitionKind::note_on, note, velocity,
                          string);
      }
    }
    state.midi_voice_mask = desired;
    harmonic_energy_memory_[candidate] = {};
    return true;
  }
  append_transition(decision, TransitionKind::note_on, note, velocity);
  harmonic_energy_memory_[candidate] = {};
  return true;
}

void MonophonicPitchDetector::append_candidate_note_off(
    DetectorDecision& decision, std::size_t candidate) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return;
  }
  CandidateState& state = candidate_states_[candidate];
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  if (profile_mode_ == ProfileMode::m3 &&
      midi_routing_ == MidiRouting::per_voice) {
    for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((state.midi_voice_mask & (1U << string)) != 0U) {
        append_transition(decision, TransitionKind::note_off, note, 0U,
                          string);
      }
    }
    return;
  }
  append_transition(decision, TransitionKind::note_off, note, 0U);
}

bool MonophonicPitchDetector::is_harmonic_shadow(
    std::size_t candidate, std::size_t selected_candidate,
    const std::array<double, kMaxCandidates>& fundamentals) const noexcept {
  if (candidate == selected_candidate ||
      fundamentals[selected_candidate] <= kScoreEpsilon) {
    return false;
  }
  const int interval = std::abs(static_cast<int>(candidate) -
                                static_cast<int>(selected_candidate));
  for (const int harmonic_interval : kHarmonicIntervals) {
    if (interval == harmonic_interval) {
      return fundamentals[candidate] <
             fundamentals[selected_candidate] * kHarmonicFundamentalRatio;
    }
  }
  return false;
}

void MonophonicPitchDetector::refresh_m3_playable_string_masks() noexcept {
  playable_string_masks_ = {};
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t open = kM3OpenNotes[string];
      const std::uint16_t highest =
          static_cast<std::uint16_t>(open) + max_fret_;
      if (note >= open && static_cast<std::uint16_t>(note) <= highest) {
        playable_string_masks_[candidate] = static_cast<std::uint8_t>(
            playable_string_masks_[candidate] | (1U << string));
      }
    }
  }
}

std::uint8_t MonophonicPitchDetector::playable_string_mask(
    std::size_t candidate) const noexcept {
  if (profile_mode_ != ProfileMode::m3 ||
      candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  return playable_string_masks_[candidate];
}

std::size_t MonophonicPitchDetector::m3_assignment_state_count(
    const std::array<bool, kMaxCandidates>& selected) const noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return 1U;
  }
  std::array<std::uint8_t, kM3StringMaskCount> reachable{};
  reachable[0U] = 1U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (!selected[candidate]) {
      continue;
    }
    const std::uint8_t playable = playable_string_mask(candidate);
    if (playable == 0U) {
      return 0U;
    }
    assignment_add(reachable, playable);
    bool any_assignment = false;
    for (const std::uint8_t state : reachable) {
      any_assignment = any_assignment || state != 0U;
    }
    if (!any_assignment) {
      return 0U;
    }
  }
  std::size_t count = 0U;
  for (const std::uint8_t state : reachable) {
    count += state != 0U ? 1U : 0U;
  }
  return count;
}

bool MonophonicPitchDetector::selection_has_distinct_m3_strings(
    const std::array<bool, kMaxCandidates>& selected) const noexcept {
  return m3_assignment_state_count(selected) != 0U;
}

void MonophonicPitchDetector::enforce_m3_feasibility(
    std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals) const noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }
  for (std::size_t pass = 0U; pass < kMaxVoices; ++pass) {
    if (selection_has_distinct_m3_strings(selected)) {
      return;
    }
    std::size_t removal = static_cast<std::size_t>(candidate_count_);
    double lowest_score = std::numeric_limits<double>::infinity();
    // Prefer a removal that immediately restores an assignment. This only
    // removes a member of the actual conflict, never an unrelated low-score
    // voice that already has its own string.
    for (std::size_t candidate = 0U; candidate <
                                    static_cast<std::size_t>(candidate_count_);
         ++candidate) {
      if (!selected[candidate]) {
        continue;
      }
      std::array<bool, kMaxCandidates> without = selected;
      without[candidate] = false;
      if (!selection_has_distinct_m3_strings(without)) {
        continue;
      }
      const double candidate_rank =
          has_direct_fundamental_peak(
              scores, fundamentals, candidate,
              static_cast<std::size_t>(candidate_count_))
              ? fundamentals[candidate]
              : scores[candidate];
      if (candidate_rank < lowest_score ||
          (candidate_rank == lowest_score && candidate > removal)) {
        lowest_score = candidate_rank;
        removal = candidate;
      }
    }
    if (removal >= static_cast<std::size_t>(candidate_count_)) {
      std::size_t best_states = 0U;
      for (std::size_t candidate = 0U; candidate <
                                      static_cast<std::size_t>(candidate_count_);
           ++candidate) {
        if (!selected[candidate]) {
          continue;
        }
        std::array<bool, kMaxCandidates> without = selected;
        without[candidate] = false;
        const std::size_t states = m3_assignment_state_count(without);
        const double candidate_rank =
            has_direct_fundamental_peak(
                scores, fundamentals, candidate,
                static_cast<std::size_t>(candidate_count_))
                ? fundamentals[candidate]
                : scores[candidate];
        if (states > best_states ||
            (states == best_states &&
             (candidate_rank < lowest_score ||
              (candidate_rank == lowest_score && candidate > removal)))) {
          best_states = states;
          lowest_score = candidate_rank;
          removal = candidate;
        }
      }
    }
    if (removal >= static_cast<std::size_t>(candidate_count_)) {
      return;
    }
    selected[removal] = false;
  }
}

void MonophonicPitchDetector::select_m3_feasible_candidates(
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    const std::array<double, kMaxCandidates>& narrow_fundamentals,
    double threshold,
    std::array<bool, kMaxCandidates>& selected, std::size_t count) noexcept {
  selected = {};
  m3_pool_ = {};
  m3_dp_states_ = {};
#if defined(M3_TESTING)
  selection_work_ = {};
#endif

  std::array<bool, kMaxCandidates> raw_eligible{};
  std::array<double, kMaxCandidates> selection_scores{};
  const bool narrow_profile = max_fret_ <= 2U;
  const bool narrow_ready =
      !narrow_profile ||
      static_cast<double>(narrow_signal_samples_) >=
          sample_rate_ * kNarrowFundamentalSeconds;
  if (!narrow_ready) {
    return;
  }
  double maximum_narrow_fundamental = 0.0;
  if (narrow_profile) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      maximum_narrow_fundamental =
          std::max(maximum_narrow_fundamental, narrow_fundamentals[candidate]);
    }
  }
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (playable_string_mask(candidate) == 0U) {
      continue;
    }
    if (narrow_profile) {
      const double narrow_floor = std::max(
          kScoreEpsilon,
          maximum_narrow_fundamental * kNarrowFundamentalRelativeFloor);
      raw_eligible[candidate] =
          narrow_fundamentals[candidate] >= narrow_floor;
      selection_scores[candidate] =
          narrow_fundamentals[candidate] /
          std::max(maximum_narrow_fundamental, kScoreEpsilon);
    } else {
      if (scores[candidate] <= threshold) {
        continue;
      }
      raw_eligible[candidate] = candidate_states_[candidate].active ||
                                is_local_peak(scores, candidate, count) ||
                                has_m3_candidate_evidence(
                                    scores, fundamentals, candidate, count);
      selection_scores[candidate] =
          scores[candidate] / std::max(fast_energy_, kScoreEpsilon);
    }
  }

  // Classify harmonic shadows in descending spectral rank before considering
  // physical strings. A feasibility decision must never turn a spectral
  // subharmonic into a separate voice merely because a stronger candidate
  // happens to occupy the same string.
  std::array<bool, kMaxCandidates> processed{};
  std::array<bool, kMaxCandidates> spectral_eligible{};
  for (std::size_t rank = 0U; rank < count; ++rank) {
    std::size_t candidate = count;
    for (std::size_t probe = 0U; probe < count; ++probe) {
      if (!raw_eligible[probe] || processed[probe] ||
          (candidate != count &&
           (scores[probe] < scores[candidate] ||
            (scores[probe] == scores[candidate] && probe > candidate)))) {
        continue;
      }
      candidate = probe;
    }
    if (candidate == count) {
      break;
    }
    processed[candidate] = true;
    bool shadowed = false;
    for (std::size_t stronger = 0U; stronger < count; ++stronger) {
      if (!spectral_eligible[stronger]) {
        continue;
      }
      const bool distinct_lower_peak =
          candidate < stronger &&
          is_local_peak(scores, candidate, count) &&
          fundamentals[candidate] >= 0.20 * scores[candidate];
      // A higher octave is a real independent string only when its own
      // fundamental dominates its score and is independently comparable to
      // the lower fundamental. A bright lower string's second harmonic can
      // dominate the octave bin without being a second physical voice.
      const bool distinct_higher_peak =
          candidate > stronger && is_local_peak(scores, candidate, count) &&
          fundamentals[candidate] >= 0.85 * scores[candidate] &&
          fundamentals[candidate] >= 0.85 * fundamentals[stronger];
      if ((is_harmonic_shadow(candidate, stronger, fundamentals) ||
           is_m3_lower_cross_harmonic_shadow(candidate, stronger,
                                              fundamentals)) &&
          !distinct_lower_peak && !distinct_higher_peak) {
        shadowed = true;
        break;
      }
    }
    spectral_eligible[candidate] = !shadowed;
  }

  std::array<bool, kMaxCandidates> in_pool{};
  std::size_t pool_count = 0U;
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    const std::uint8_t string_bit = static_cast<std::uint8_t>(1U << string);
    std::array<bool, kMaxCandidates> selected_for_string{};
    for (std::size_t rank = 0U;
         rank < static_cast<std::size_t>(max_polyphony_); ++rank) {
      std::size_t best = count;
      for (std::size_t candidate = 0U; candidate < count; ++candidate) {
        if (!spectral_eligible[candidate] || selected_for_string[candidate] ||
            (playable_string_mask(candidate) & string_bit) == 0U) {
          continue;
        }
        const CandidateState& state = candidate_states_[candidate];
        if (best == count ||
            (state.active && !candidate_states_[best].active) ||
            (state.active == candidate_states_[best].active &&
             (selection_scores[candidate] > selection_scores[best] ||
              (selection_scores[candidate] == selection_scores[best] &&
               candidate < best)))) {
          best = candidate;
        }
      }
      if (best == count) {
        break;
      }
      selected_for_string[best] = true;
      if (in_pool[best]) {
        continue;
      }
      if (pool_count >= m3_pool_.size()) {
        break;
      }
      in_pool[best] = true;
      m3_pool_[pool_count++] = M3PoolCandidate{
          static_cast<std::uint8_t>(best), playable_string_mask(best),
          selection_scores[best], candidate_states_[best].active};
    }
  }

#if defined(M3_TESTING)
  selection_work_.pool_candidates = static_cast<std::uint32_t>(pool_count);
#endif
  std::size_t open_candidate_count = 0U;
  if (narrow_profile) {
    for (std::size_t option_index = 0U; option_index < pool_count;
         ++option_index) {
      const std::size_t candidate = m3_pool_[option_index].detector_index;
      const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
      open_candidate_count += is_m3_open_note(note) ? 1U : 0U;
    }
  } else {
    for (std::size_t option_index = 0U; option_index < pool_count;
         ++option_index) {
      const std::size_t candidate = m3_pool_[option_index].detector_index;
      const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
      const bool direct_open_candidate =
          is_m3_open_note(note) &&
          fundamentals[candidate] >= 0.50 * scores[candidate];
      open_candidate_count += direct_open_candidate ? 1U : 0U;
    }
  }
  m3_dp_states_[0U].valid = true;
  for (std::size_t option_index = 0U; option_index < pool_count; ++option_index) {
    const M3PoolCandidate& option = m3_pool_[option_index];
    for (std::size_t used = kM3StringMaskCount; used-- > 0U;) {
      const M3DpState state = m3_dp_states_[used];
      if (!state.valid ||
          state.voice_count >= static_cast<std::uint8_t>(max_polyphony_)) {
        continue;
      }
      const std::uint8_t available = static_cast<std::uint8_t>(
          option.string_mask & ~static_cast<std::uint8_t>(used));
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        const std::uint8_t string_bit = static_cast<std::uint8_t>(1U << string);
        if ((available & string_bit) == 0U) {
          continue;
        }
#if defined(M3_TESTING)
        ++selection_work_.assignment_edges;
#endif
        const std::size_t next = used | string_bit;
        M3DpState proposal = state;
        proposal.valid = true;
        const auto note = static_cast<std::uint8_t>(
            lowest_note_ + option.detector_index);
        const std::uint8_t fret =
            static_cast<std::uint8_t>(note - kM3OpenNotes[string]);
        const double assignment_penalty =
            (open_candidate_count >= kM3OpenChordMinimum ||
             note > kM3OpenNotes.back()) &&
                    fret > 0U
                ? kM3FrettedNotePenalty +
                      kM3FretPenalty * static_cast<double>(fret)
                : 0.0;
        proposal.score_sum += option.score - assignment_penalty;
        proposal.chosen |= (std::uint64_t{1U} << option_index);
        ++proposal.voice_count;
        proposal.retained_active = static_cast<std::uint8_t>(
            proposal.retained_active + (option.active ? 1U : 0U));
        const M3DpState& current = m3_dp_states_[next];
        const bool better =
            !current.valid || proposal.score_sum > current.score_sum ||
            (proposal.score_sum == current.score_sum &&
             (proposal.retained_active > current.retained_active ||
              (proposal.retained_active == current.retained_active &&
               proposal.voice_count > current.voice_count)));
        if (better) {
          m3_dp_states_[next] = proposal;
        }
#if defined(M3_TESTING)
        ++selection_work_.state_transitions;
#endif
      }
    }
  }

  M3DpState best{};
  for (const M3DpState& state : m3_dp_states_) {
    const bool better =
        state.valid &&
        (!best.valid || state.score_sum > best.score_sum ||
         (state.score_sum == best.score_sum &&
          (state.retained_active > best.retained_active ||
           (state.retained_active == best.retained_active &&
            state.voice_count > best.voice_count))));
    if (better) {
      best = state;
    }
  }
  for (std::size_t option_index = 0U; option_index < pool_count; ++option_index) {
    if ((best.chosen & (std::uint64_t{1U} << option_index)) != 0U) {
      selected[m3_pool_[option_index].detector_index] = true;
    }
  }
}

void MonophonicPitchDetector::assign_m3_strings(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    for (std::size_t candidate = 0U;
         candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
      if (selected[candidate]) {
        candidate_states_[candidate].assigned_string =
            kUnassignedTunerString;
      }
    }
    return;
  }

  std::array<std::size_t, kMaxVoices> candidates{};
  std::size_t selected_count = 0U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_) &&
       selected_count < candidates.size();
       ++candidate) {
    if (selected[candidate]) {
      candidates[selected_count++] = candidate;
    }
  }
  if (selected_count == 0U) {
    return;
  }

  struct Assignment final {
    double cost{};
    std::uint32_t strings{};
    bool valid{};
  };
  std::array<Assignment, kM3StringMaskCount> current{};
  // A briefly unselected active voice is still visible during its release
  // hold. Reserve its physical lane so another candidate cannot steal that
  // tuner for one decision quantum and force the whole chord to reshuffle.
  std::uint8_t reserved_strings = 0U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    if (selected[candidate] || !state.active ||
        state.assigned_string >= kM3OpenNotes.size()) {
      continue;
    }
    const std::uint8_t reserved =
        state.assigned_string_mask != 0U
            ? state.assigned_string_mask
            : static_cast<std::uint8_t>(1U << state.assigned_string);
    reserved_strings =
        static_cast<std::uint8_t>(reserved_strings | reserved);
  }
  current[reserved_strings].valid = true;
  for (std::size_t voice = 0U; voice < selected_count; ++voice) {
    std::array<Assignment, kM3StringMaskCount> next{};
    const std::size_t candidate = candidates[voice];
    const std::uint8_t playable = playable_string_mask(candidate);
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    std::array<double, kMaxVoices> learned_similarities{};
    std::array<bool, kMaxVoices> has_learned_profile{};
    double learned_sum = 0.0;
    std::size_t learned_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      if ((playable & bit) == 0U) {
        continue;
      }
      const std::size_t fret = note - kM3OpenNotes[string];
      const StringCalibrationPoint* point =
          calibrator_.bank().point(string, fret);
      if (point == nullptr ||
          point->quality == CalibrationPointQuality::missing) {
        continue;
      }
      has_learned_profile[string] = true;
      learned_similarities[string] =
          calibration_similarity(candidate, string);
      learned_sum += learned_similarities[string];
      ++learned_count;
    }
    const double learned_center =
        learned_count > 0U
            ? learned_sum / static_cast<double>(learned_count)
            : 0.0;
    for (std::size_t used = 0U; used < current.size(); ++used) {
      if (!current[used].valid) {
        continue;
      }
      const std::uint8_t available = static_cast<std::uint8_t>(
          playable & ~static_cast<std::uint8_t>(used));
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
        if ((available & bit) == 0U) {
          continue;
        }
        const std::size_t mask = used | bit;
        Assignment proposal = current[used];
        proposal.valid = true;
        const auto fret = static_cast<std::uint8_t>(
            note - kM3OpenNotes[string]);
        // A retained active string wins first; otherwise prefer the lowest
        // physical fret. This makes the identity stable across spectral-rank
        // changes and deterministic for ambiguous pitches.
        const double fret_position = static_cast<double>(fret);
        const double gauge_ratio =
            static_cast<double>(kM3StringGaugeMils[string]) /
            static_cast<double>(kM3StringGaugeMils.front());
        const double stiffness_prior = 0.75 + 0.25 * gauge_ratio;
        proposal.cost += fret_position +
                         kM3AssignmentFretShapePenalty * stiffness_prior *
                             fret_position * fret_position;
        if (has_learned_profile[string]) {
          // Calibration is comparative evidence, not an absolute prior. A
          // lone learned lane therefore stays neutral instead of stealing an
          // otherwise ambiguous note from an uncalibrated lower-fret lane.
          proposal.cost -=
              30.0 * (learned_similarities[string] - learned_center);
        }
        if (candidate_states_[candidate].active &&
            candidate_states_[candidate].assigned_string == string) {
          const bool exposed_per_voice_lane =
              midi_routing_ == MidiRouting::per_voice &&
              (candidate_states_[candidate].midi_voice_mask & bit) != 0U;
          // A provisional single-channel chord may still correct its physical
          // fingering as evidence arrives. Once note-on exposes a per-voice
          // lane, however, keep it until note-off so a released reservation
          // cannot cause a mid-note tuner/channel flip.
          proposal.cost -= exposed_per_voice_lane
                               ? kM3ExposedStringRetentionBonus
                               : kM3ProvisionalStringRetentionBonus;
        }
        const std::uint32_t shift = static_cast<std::uint32_t>(voice * 3U);
        proposal.strings =
            (proposal.strings & ~(0x07U << shift)) |
            (static_cast<std::uint32_t>(string) << shift);
        if (!next[mask].valid || proposal.cost < next[mask].cost ||
            (proposal.cost == next[mask].cost &&
             proposal.strings < next[mask].strings)) {
          next[mask] = proposal;
        }
      }
    }
    current = next;
  }

  Assignment best{};
  for (const Assignment& assignment : current) {
    if (assignment.valid &&
        (!best.valid || assignment.cost < best.cost ||
         (assignment.cost == best.cost &&
          assignment.strings < best.strings))) {
      best = assignment;
    }
  }
  if (!best.valid) {
    return;
  }
  for (std::size_t voice = 0U; voice < selected_count; ++voice) {
    candidate_states_[candidates[voice]].assigned_string =
        static_cast<std::uint8_t>((best.strings >> (voice * 3U)) & 0x07U);
  }
}

void MonophonicPitchDetector::update_harmonic_profile_memory(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double mix = 1.0 - harmonic_memory_decay;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (!selected[candidate]) {
      if (!candidate_states_[candidate].active) {
        for (double& energy : harmonic_energy_memory_[candidate]) {
          energy *= harmonic_memory_decay;
        }
      }
      continue;
    }
    for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
      const double instantaneous =
          corrected_harmonic_energy(candidate, harmonic);
      harmonic_energy_memory_[candidate][harmonic] =
          harmonic_memory_decay *
              harmonic_energy_memory_[candidate][harmonic] +
          mix * instantaneous;
    }
  }
}

double MonophonicPitchDetector::corrected_harmonic_energy(
    std::size_t candidate, std::size_t harmonic) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      harmonic >= kHarmonicCount) {
    return 0.0;
  }
  const Cell& cell = cells_[cell_index(candidate, harmonic)];
  if (!cell.enabled) {
    return 0.0;
  }
  const double raw = cell.fast_real * cell.fast_real +
                     cell.fast_imaginary * cell.fast_imaginary;
  const PhaseCentsState& phase = phase_cents_states_[candidate];
  if (!phase.valid || raw <= kScoreEpsilon) {
    return raw;
  }

  constexpr double kNaturalLogTwo = 0.69314718055994530942;
  const double fractional_offset =
      std::expm1(kNaturalLogTwo * phase.cents / 1200.0);
  const double center_radians =
      std::atan2(cell.sine_step, cell.cosine_step);
  const double delta = center_radians * fractional_offset;
  const double one_minus_decay = 1.0 - correlation_decay;
  const double base = one_minus_decay * one_minus_decay;
  if (base <= 0.0) {
    return raw;
  }
  // Reciprocal squared magnitude of the one-pole correlation response,
  // written in a cancellation-resistant form for delta close to zero.
  const double correction =
      1.0 + 2.0 * correlation_decay * (1.0 - std::cos(delta)) / base;
  return raw * std::clamp(correction, 1.0,
                          kMaximumHarmonicEnergyCorrection);
}

void MonophonicPitchDetector::update_phase_cents_estimates(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double decisions_per_second =
      sample_rate_ / static_cast<double>(kDecisionQuantum);
  const double phasor_mix =
      1.0 - std::exp(-1.0 / (0.015 * decisions_per_second));
  const double cents_mix =
      1.0 - std::exp(-1.0 / (0.010 * decisions_per_second));
  const std::uint16_t required_updates = static_cast<std::uint16_t>(
      std::clamp(std::ceil(0.060 * decisions_per_second), 1.0,
                 static_cast<double>(
                     std::numeric_limits<std::uint16_t>::max())));
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (!selected[candidate] && !candidate_states_[candidate].active) {
      phase_cents_states_[candidate] = {};
      continue;
    }
    const Cell& fundamental = cells_[cell_index(candidate, 0U)];
    PhaseCentsState& state = phase_cents_states_[candidate];
    state.filtered_real +=
        phasor_mix * (fundamental.fast_real - state.filtered_real);
    state.filtered_imaginary += phasor_mix *
                                  (fundamental.fast_imaginary -
                                   state.filtered_imaginary);
    state.filtered_twice_real +=
        phasor_mix * (state.filtered_real - state.filtered_twice_real);
    state.filtered_twice_imaginary +=
        phasor_mix *
        (state.filtered_imaginary - state.filtered_twice_imaginary);
    const double current_energy =
        state.filtered_twice_real * state.filtered_twice_real +
        state.filtered_twice_imaginary * state.filtered_twice_imaginary;
    state.valid = false;
    bool accepted = false;
    if (fundamental.enabled && current_energy > kScoreEpsilon &&
        state.has_previous) {
      const double dot =
          state.previous_real * state.filtered_twice_real +
          state.previous_imaginary * state.filtered_twice_imaginary;
      const double cross =
          state.previous_real * state.filtered_twice_imaginary -
          state.previous_imaginary * state.filtered_twice_real;
      const double phase_delta = std::atan2(cross, dot);
      const double center_radians =
          std::atan2(fundamental.sine_step, fundamental.cosine_step);
      const double center_frequency =
          center_radians * sample_rate_ / kTwoPi;
      const double frequency_offset =
          phase_delta * decisions_per_second / kTwoPi;
      if (std::isfinite(frequency_offset) && center_frequency > 0.0) {
        if (state.accepted_updates == 0U) {
          state.frequency_offset = frequency_offset;
        } else {
          state.frequency_offset +=
              cents_mix * (frequency_offset - state.frequency_offset);
        }
        const double measured_frequency =
            center_frequency + state.frequency_offset;
        if (measured_frequency > 0.0) {
          state.cents =
              1200.0 * std::log2(measured_frequency / center_frequency);
          if (state.accepted_updates <
              std::numeric_limits<std::uint16_t>::max()) {
            ++state.accepted_updates;
          }
          accepted = true;
        }
      }
    }
    if (current_energy <= kScoreEpsilon) {
      state.accepted_updates = 0U;
      state.has_previous = false;
    } else {
      state.has_previous = true;
    }
    state.valid = accepted && state.accepted_updates >= required_updates &&
                  state.cents >= -50.0 && state.cents <= 50.0;
    state.previous_real = state.filtered_twice_real;
    state.previous_imaginary = state.filtered_twice_imaginary;
  }
}

void MonophonicPitchDetector::infer_m3_unison_strings(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }

  std::size_t selected_count = 0U;
  std::uint8_t primary_strings = 0U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (!selected[candidate]) {
      continue;
    }
    ++selected_count;
    const std::uint8_t primary = candidate_states_[candidate].assigned_string;
    if (primary < kM3OpenNotes.size()) {
      primary_strings = static_cast<std::uint8_t>(
          primary_strings | (1U << primary));
    }
  }
  std::size_t remaining_extra =
      max_polyphony_ > selected_count ? max_polyphony_ - selected_count : 0U;
  std::uint8_t allocated_extra_strings = 0U;
  const std::uint16_t profile_ready_ticks = static_cast<std::uint16_t>(
      std::clamp(std::ceil(kM3UnisonMinimumObservationSeconds * sample_rate_ /
                          static_cast<double>(kDecisionQuantum)),
                 1.0,
                 static_cast<double>(
                     std::numeric_limits<std::uint16_t>::max())));
  const std::uint8_t unison_evidence_ticks = static_cast<std::uint8_t>(
      std::clamp(std::ceil(kM3UnisonEvidenceSeconds * sample_rate_ /
                          static_cast<double>(kDecisionQuantum)),
                 1.0,
                 static_cast<double>(
                     std::numeric_limits<std::uint8_t>::max())));

  const auto load_template = [this](
                                 std::size_t candidate, std::size_t string,
                                 std::array<double, kHarmonicCount>& result)
      noexcept {
        if (string >= kM3OpenNotes.size() ||
            !calibrator_.bank().string_calibrated(string)) {
          return false;
        }
        const std::uint8_t note =
            static_cast<std::uint8_t>(lowest_note_ + candidate);
        if (note < kM3OpenNotes[string]) {
          return false;
        }
        const std::size_t fret = note - kM3OpenNotes[string];
        const StringCalibrationPoint* point =
            calibrator_.bank().point(string, fret);
        if (point == nullptr ||
            point->quality == CalibrationPointQuality::missing) {
          return false;
        }
        double total = 0.0;
        for (const std::uint16_t value : point->harmonic_profile_q15) {
          total += static_cast<double>(value);
        }
        if (total <= kScoreEpsilon) {
          return false;
        }
        for (std::size_t harmonic = 0U; harmonic < result.size(); ++harmonic) {
          result[harmonic] =
              static_cast<double>(point->harmonic_profile_q15[harmonic]) /
              total;
        }
        return true;
      };

  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (!selected[candidate] ||
        state.assigned_string >= kM3OpenNotes.size()) {
      continue;
    }
    const std::uint8_t primary = state.assigned_string;
    const std::uint8_t primary_bit =
        static_cast<std::uint8_t>(1U << primary);
    if (state.assigned_string_mask == 0U ||
        (state.assigned_string_mask & primary_bit) == 0U) {
      state.assigned_string_mask = primary_bit;
      state.unison_evidence_ticks = 0U;
      state.unison_gap_ticks = 0U;
      state.pending_unison_string = kUnassignedTunerString;
    }

    std::uint8_t proposed_second = kUnassignedTunerString;
    double proposed_improvement = 0.0;
    if (state.age_ticks >= profile_ready_ticks && remaining_extra > 0U) {
      double observed_total = 0.0;
      for (const double energy : harmonic_energy_memory_[candidate]) {
        observed_total += energy;
      }
      std::array<double, kHarmonicCount> observed{};
      if (observed_total > kScoreEpsilon) {
        for (std::size_t harmonic = 0U; harmonic < observed.size(); ++harmonic) {
          observed[harmonic] =
              harmonic_energy_memory_[candidate][harmonic] / observed_total;
        }

        std::array<double, kHarmonicCount> primary_template{};
        if (load_template(candidate, primary, primary_template)) {
          double best_single_error =
              std::numeric_limits<double>::infinity();
          const std::uint8_t playable = playable_string_mask(candidate);
          for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
            const std::uint8_t bit =
                static_cast<std::uint8_t>(1U << string);
            if ((playable & bit) == 0U) {
              continue;
            }
            std::array<double, kHarmonicCount> single{};
            if (!load_template(candidate, string, single)) {
              continue;
            }
            double error = 0.0;
            for (std::size_t harmonic = 0U; harmonic < observed.size();
                 ++harmonic) {
              const double difference = observed[harmonic] - single[harmonic];
              error += difference * difference;
            }
            best_single_error = std::min(best_single_error, error);
          }

          for (std::size_t second = 0U; second < kM3OpenNotes.size();
               ++second) {
            const std::uint8_t second_bit =
                static_cast<std::uint8_t>(1U << second);
            if (second == primary || (playable & second_bit) == 0U ||
                (primary_strings & second_bit) != 0U ||
                (allocated_extra_strings & second_bit) != 0U) {
              continue;
            }
            std::array<double, kHarmonicCount> second_template{};
            if (!load_template(candidate, second, second_template)) {
              continue;
            }
            double delta_norm = 0.0;
            double projection = 0.0;
            for (std::size_t harmonic = 0U; harmonic < observed.size();
                 ++harmonic) {
              const double delta =
                  primary_template[harmonic] - second_template[harmonic];
              delta_norm += delta * delta;
              projection +=
                  (observed[harmonic] - second_template[harmonic]) * delta;
            }
            if (delta_norm < kM3UnisonMinimumTemplateDistance) {
              continue;
            }
            const double primary_weight =
                std::clamp(projection / delta_norm, 0.0, 1.0);
            const double second_weight = 1.0 - primary_weight;
            if (primary_weight < kM3UnisonMinimumComponent ||
                second_weight < kM3UnisonMinimumComponent) {
              continue;
            }
            double pair_error = 0.0;
            for (std::size_t harmonic = 0U; harmonic < observed.size();
                 ++harmonic) {
              const double fitted =
                  primary_weight * primary_template[harmonic] +
                  second_weight * second_template[harmonic];
              const double difference = observed[harmonic] - fitted;
              pair_error += difference * difference;
            }
            const double improvement = best_single_error - pair_error;
            if (improvement < kM3UnisonMinimumErrorImprovement ||
                pair_error > best_single_error *
                                 kM3UnisonMaximumErrorRatio ||
                improvement <= proposed_improvement) {
              continue;
            }
            proposed_improvement = improvement;
            proposed_second = static_cast<std::uint8_t>(second);
          }
        }
      }
    }

    if (proposed_second < kM3OpenNotes.size()) {
      if (state.pending_unison_string == proposed_second) {
        if (state.unison_evidence_ticks <
            std::numeric_limits<std::uint8_t>::max()) {
          ++state.unison_evidence_ticks;
        }
      } else {
        state.pending_unison_string = proposed_second;
        state.unison_evidence_ticks = 1U;
      }
      state.unison_gap_ticks = 0U;
      if (state.unison_evidence_ticks >= unison_evidence_ticks) {
        state.assigned_string_mask = static_cast<std::uint8_t>(
            primary_bit | (1U << proposed_second));
      }
    } else {
      state.pending_unison_string = kUnassignedTunerString;
      state.unison_evidence_ticks = 0U;
      if (state.assigned_string_mask != primary_bit &&
          state.unison_gap_ticks <
              std::numeric_limits<std::uint16_t>::max()) {
        ++state.unison_gap_ticks;
      }
      if (state.unison_gap_ticks >= unison_dropout_decisions_) {
        state.assigned_string_mask = primary_bit;
        state.unison_gap_ticks = 0U;
      }
    }

    const std::uint8_t extra = static_cast<std::uint8_t>(
        state.assigned_string_mask & ~primary_bit);
    if (extra != 0U && remaining_extra > 0U &&
        (extra & primary_strings) == 0U &&
        (extra & allocated_extra_strings) == 0U) {
      allocated_extra_strings = static_cast<std::uint8_t>(
          allocated_extra_strings | extra);
      --remaining_extra;
    } else if (extra != 0U) {
      state.assigned_string_mask = primary_bit;
    }
  }
}

double MonophonicPitchDetector::calibration_similarity(
    std::size_t candidate, std::size_t string) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      string >= kM3OpenNotes.size()) {
    return 0.0;
  }
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  if (note < kM3OpenNotes[string]) {
    return 0.0;
  }
  const std::size_t fret = note - kM3OpenNotes[string];
  const StringCalibrationPoint* point =
      calibrator_.bank().point(string, fret);
  if (point == nullptr ||
      point->quality == CalibrationPointQuality::missing) {
    return 0.0;
  }
  double total = 0.0;
  std::array<double, kCalibrationHarmonicCount> current{};
  for (std::size_t harmonic = 0U; harmonic < current.size(); ++harmonic) {
    current[harmonic] = corrected_harmonic_energy(candidate, harmonic);
    total += current[harmonic];
  }
  if (total <= kScoreEpsilon) {
    return 0.0;
  }
  double dot = 0.0;
  double current_norm = 0.0;
  double learned_norm = 0.0;
  for (std::size_t harmonic = 0U; harmonic < current.size(); ++harmonic) {
    const double observed = current[harmonic] / total;
    const double learned =
        static_cast<double>(point->harmonic_profile_q15[harmonic]) / 32767.0;
    dot += observed * learned;
    current_norm += observed * observed;
    learned_norm += learned * learned;
  }
  const double denominator = std::sqrt(current_norm * learned_norm);
  if (denominator <= kScoreEpsilon) {
    return 0.0;
  }
  const double quality = point->quality == CalibrationPointQuality::measured
                             ? 1.0
                             : 0.55;
  const double learned_confidence =
      static_cast<double>(point->confidence_q15) / 32767.0;
  return std::clamp(dot / denominator, 0.0, 1.0) * quality *
         learned_confidence;
}

void MonophonicPitchDetector::observe_calibration(
    const std::array<double, kMaxCandidates>& scores,
    double lower_guard_score, double upper_guard_score, bool quiet) noexcept {
  if (!calibrator_.active() || quiet) {
    return;
  }
  const CalibrationSweepStatus sweep = calibrator_.status();
  const std::size_t first =
      static_cast<std::size_t>(kM3OpenNotes[sweep.string_index] - lowest_note_);
  const std::size_t last = first + kCalibrationFretCount - 1U;
  if (last >= static_cast<std::size_t>(candidate_count_)) {
    return;
  }
  std::size_t best = first;
  for (std::size_t candidate = first + 1U; candidate <= last; ++candidate) {
    if (scores[candidate] > scores[best]) {
      best = candidate;
    }
  }
  const double threshold = std::max(fast_energy_ * kCandidateCoherenceRatio,
                                    kScoreEpsilon);
  if (scores[best] <= threshold) {
    return;
  }

  const double left_score = best > 0U ? scores[best - 1U] : lower_guard_score;
  const double right_score =
      best + 1U < static_cast<std::size_t>(candidate_count_)
          ? scores[best + 1U]
          : upper_guard_score;
  const double left = std::log(std::max(left_score, kScoreEpsilon));
  const double center = std::log(std::max(scores[best], kScoreEpsilon));
  const double right = std::log(std::max(right_score, kScoreEpsilon));
  const double denominator = left - 2.0 * center + right;
  double semitone_offset = 0.0;
  const PhaseCentsState& phase_cents = phase_cents_states_[best];
  if (phase_cents.valid) {
    // Calibration must learn the same settled pitch estimate that drives the
    // tuner display.  The neighbouring-bin parabola remains a startup
    // fallback while phase evidence is still accumulating.
    semitone_offset = phase_cents.cents / 100.0;
  } else if (std::isfinite(denominator) && denominator < -kScoreEpsilon) {
    semitone_offset = std::clamp(
        0.5 * (left - right) / denominator, -0.5, 0.5);
  }

  CalibrationObservation observation;
  observation.midi_pitch = static_cast<double>(lowest_note_ + best) +
                           semitone_offset;
  observation.confidence = std::clamp(
      (scores[best] - threshold) / (scores[best] + threshold), 0.0, 1.0);
  for (std::size_t harmonic = 0U;
       harmonic < observation.harmonic_energy.size(); ++harmonic) {
    observation.harmonic_energy[harmonic] =
        corrected_harmonic_energy(best, harmonic);
  }
  static_cast<void>(calibrator_.observe(observation));
}

void MonophonicPitchDetector::write_snapshot(
    DetectorDecision& decision,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<bool, kMaxCandidates>& selected,
    double lower_guard_score, double upper_guard_score, bool quiet) noexcept {
  TunerSnapshot& snapshot = decision.tuner_snapshot;
  snapshot.generation = ++snapshot_generation_;
  snapshot.max_polyphony = max_polyphony_;
  std::size_t voice_count = 0U;
  const double threshold = std::max(fast_energy_ * kCandidateCoherenceRatio,
                                    kScoreEpsilon);
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_) &&
       voice_count < static_cast<std::size_t>(max_polyphony_);
       ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (!state.active && !selected[candidate]) {
      continue;
    }
    TunerVoice base_voice;
    base_voice.midi_note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
    base_voice.age_ticks = state.age_ticks;
    const bool tracking = state.active && selected[candidate];
    const bool coasting = state.active && !selected[candidate];
    base_voice.state = tracking
                           ? TunerVoiceState::tracking
                           : (coasting ? TunerVoiceState::coasting
                                      : TunerVoiceState::settling);
    if (coasting) {
      base_voice.cents_q8 = state.retained_cents_q8;
      base_voice.cents_valid = state.retained_cents_valid;
      const std::uint16_t release = release_decisions();
      const double remaining = release > state.release_ticks
                                   ? static_cast<double>(release -
                                                         state.release_ticks) /
                                         static_cast<double>(release)
                                   : 0.0;
      base_voice.confidence_q15 = static_cast<std::uint16_t>(std::lround(
          static_cast<double>(state.retained_confidence_q15) * remaining));
    } else {
      const double normalized = std::clamp(
          (scores[candidate] - threshold) / (scores[candidate] + threshold),
          0.0, 1.0);
      base_voice.confidence_q15 = static_cast<std::uint16_t>(std::lround(
          normalized * 32767.0));
      const PhaseCentsState& phase_cents = phase_cents_states_[candidate];
      if (phase_cents.valid) {
        base_voice.cents_q8 = static_cast<std::int16_t>(std::lround(
            phase_cents.cents * 256.0));
        base_voice.cents_valid = true;
      } else {
        const double left_score =
            candidate > 0U ? scores[candidate - 1U] : lower_guard_score;
        const double right_score =
            candidate + 1U < static_cast<std::size_t>(candidate_count_)
                ? scores[candidate + 1U]
                : upper_guard_score;
        const double left = std::log(std::max(left_score, kScoreEpsilon));
        const double center =
            std::log(std::max(scores[candidate], kScoreEpsilon));
        const double right = std::log(std::max(right_score, kScoreEpsilon));
        const double denominator = left - 2.0 * center + right;
        if (std::isfinite(denominator) && denominator < -kScoreEpsilon) {
          const double semitone_offset = std::clamp(
              0.5 * (left - right) / denominator, -0.5, 0.5);
          if (std::isfinite(semitone_offset)) {
            base_voice.cents_q8 = static_cast<std::int16_t>(std::lround(
                semitone_offset * 100.0 * 256.0));
            base_voice.cents_valid = true;
          }
        }
      }
      if (tracking) {
        if (base_voice.cents_valid) {
          state.retained_cents_q8 = base_voice.cents_q8;
          state.retained_cents_valid = true;
          state.retained_confidence_q15 = base_voice.confidence_q15;
        } else if (state.retained_cents_valid) {
          base_voice.cents_q8 = state.retained_cents_q8;
          base_voice.cents_valid = true;
        }
      }
    }

    const auto append_voice = [this, &snapshot, &voice_count, &base_voice](
                                  std::uint8_t string) noexcept {
      if (voice_count >= static_cast<std::size_t>(max_polyphony_) ||
          voice_count >= kMaxVoices) {
        return;
      }
      TunerVoice voice = base_voice;
      voice.string_index = string;
      // Calibration teaches string identity and timbre.  It must not move the
      // musical zero of the tuner: cents remain relative to the configured
      // equal-tempered note and A4 reference.
      snapshot.voices[voice_count++] = voice;
    };
    if (profile_mode_ != ProfileMode::m3) {
      append_voice(kUnassignedTunerString);
      continue;
    }
    std::uint8_t strings = state.assigned_string_mask;
    if (strings == 0U && state.assigned_string < kM3OpenNotes.size()) {
      strings = static_cast<std::uint8_t>(1U << state.assigned_string);
    }
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      if ((strings & bit) != 0U) {
        append_voice(static_cast<std::uint8_t>(string));
      }
    }
  }
  snapshot.voice_count = static_cast<std::uint8_t>(voice_count);
  snapshot.state = voice_count == 0U ? TunerFrameState::no_signal
                                     : TunerFrameState::tracking;
  if (quiet && voice_count == 0U) {
    snapshot.state = TunerFrameState::no_signal;
  }
  decision.tuner.updated = true;
  if (voice_count != 0U) {
    std::size_t strongest = 0U;
    for (std::size_t index = 1U; index < voice_count; ++index) {
      if (snapshot.voices[index].confidence_q15 >
          snapshot.voices[strongest].confidence_q15) {
        strongest = index;
      }
    }
    const TunerVoice& voice = snapshot.voices[strongest];
    decision.tuner.signal = true;
    decision.tuner.note = voice.midi_note;
    decision.tuner.cents = voice.cents_valid
                               ? static_cast<double>(voice.cents_q8) / 256.0
                               : 0.0;
  }
  decision.tuner_snapshot_ready = true;
}

DetectorDecision MonophonicPitchDetector::make_decision() noexcept {
  DetectorDecision decision;
  std::array<double, kMaxCandidates> scores{};
  std::array<double, kMaxCandidates> fundamentals{};
  std::array<double, kMaxCandidates> narrow_fundamentals{};
  std::array<bool, kMaxCandidates> selected{};
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  bool had_active_voice = false;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    had_active_voice = had_active_voice || candidate_states_[candidate].active;
  }
  const bool minimum_evidence =
      static_cast<double>(signal_samples_) >=
      sample_rate_ * kSingleVoiceEvidenceSeconds;
  bool rapid_mute = false;
  if (previous_decision_energy_ > kScoreEpsilon &&
      fast_energy_ > kScoreEpsilon) {
    const double decisions_per_second =
        sample_rate_ / static_cast<double>(kDecisionQuantum);
    const double energy_slope_db_per_second =
        10.0 * std::log10(fast_energy_ / previous_decision_energy_) *
        decisions_per_second;
    rapid_mute = std::isfinite(energy_slope_db_per_second) &&
                 energy_slope_db_per_second <
                     kRapidMuteEnergySlopeDbPerSecond;
  }
  previous_decision_energy_ = fast_energy_;
  bool quiet = !minimum_evidence || fast_energy_ < signal_floor() ||
               ((!had_active_voice || rapid_mute) &&
                fast_energy_ < slow_energy_ * kSilenceEnergyRatio);
  if (!quiet) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      double score = 0.0;
      for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
        const Cell& cell = cells_[cell_index(candidate, harmonic)];
        if (!cell.enabled) {
          continue;
        }
        const double energy = cell.fast_real * cell.fast_real +
                              cell.fast_imaginary * cell.fast_imaginary;
        if (harmonic == 0U) {
          fundamentals[candidate] = energy;
        }
        score += kHarmonicWeights[harmonic] * energy;
      }
      scores[candidate] = score;
      narrow_fundamentals[candidate] =
          narrow_fundamental_real_[candidate] *
              narrow_fundamental_real_[candidate] +
          narrow_fundamental_imaginary_[candidate] *
              narrow_fundamental_imaginary_[candidate];
    }
    const double threshold = fast_energy_ * kCandidateCoherenceRatio;
    if (profile_mode_ == ProfileMode::m3) {
      select_m3_feasible_candidates(scores, fundamentals,
                                    narrow_fundamentals, threshold, selected,
                                    count);
    } else {
      std::size_t selected_count = 0U;
      for (std::size_t candidate = 0U; candidate < count; ++candidate) {
        if (candidate_states_[candidate].active && scores[candidate] > threshold &&
            selected_count < static_cast<std::size_t>(max_polyphony_)) {
          selected[candidate] = true;
          ++selected_count;
        }
      }
      while (selected_count < static_cast<std::size_t>(max_polyphony_)) {
        std::size_t best_candidate = count;
        double best_score = threshold;
        for (std::size_t candidate = 0U; candidate < count; ++candidate) {
          if (selected[candidate] || scores[candidate] <= threshold ||
              !is_local_peak(scores, candidate, count) ||
              scores[candidate] <= best_score) {
            continue;
          }
          bool shadowed = false;
          for (std::size_t other = 0U; other < count; ++other) {
            if (selected[other] &&
                is_harmonic_shadow(candidate, other, fundamentals)) {
              shadowed = true;
              break;
            }
          }
          if (!shadowed) {
            best_score = scores[candidate];
            best_candidate = candidate;
          }
        }
        if (best_candidate == count) {
          break;
        }
        selected[best_candidate] = true;
        ++selected_count;
      }
    }
  }

  std::size_t selected_voice_count = 0U;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (selected[candidate]) {
      ++selected_voice_count;
    }
  }
  const bool multi_voice_evidence =
      selected_voice_count <= 1U ||
      static_cast<double>(signal_samples_) >=
          sample_rate_ * kMultiVoiceEvidenceSeconds;
  if (!minimum_evidence || !multi_voice_evidence) {
    selected = {};
    quiet = true;
  }
  update_phase_cents_estimates(selected);
  assign_m3_strings(selected);
  update_harmonic_profile_memory(selected);
  infer_m3_unison_strings(selected);

  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (state.active) {
      continue;
    }
    const bool direct_observation =
        has_direct_fundamental_peak(scores, fundamentals, candidate, count);
    const bool fallback_observation =
        selected[candidate] && profile_mode_ == ProfileMode::m3 &&
        (max_fret_ <= 2U || is_local_peak(scores, candidate, count) ||
         has_m3_candidate_evidence(scores, fundamentals, candidate, count));
    bool migrating_observation = false;
    if (had_active_voice && profile_mode_ == ProfileMode::m3) {
      for (std::size_t probe = 0U; probe < count && !migrating_observation;
           ++probe) {
        if (!selected[probe]) {
          continue;
        }
        bool belongs_to_active_voice = false;
        for (std::size_t active = 0U; active < count; ++active) {
          if (!candidate_states_[active].active) {
            continue;
          }
          const std::size_t distance =
              probe > active ? probe - active : active - probe;
          if (distance <= kCandidateMigrationSemitones) {
            belongs_to_active_voice = true;
            break;
          }
        }
        const std::size_t candidate_distance =
            probe > candidate ? probe - candidate : candidate - probe;
        migrating_observation = !belongs_to_active_voice &&
                                candidate_distance <=
                                    kCandidateMigrationSemitones;
      }
    }
    if (!direct_observation && !fallback_observation &&
        !migrating_observation) {
      if (state.evidence_ticks != 0U &&
          state.evidence_gap_ticks < kCandidateEvidenceDropoutDecisions) {
        ++state.evidence_gap_ticks;
      } else {
        state.evidence_ticks = 0U;
        state.evidence_gap_ticks = 0U;
      }
    } else if (!had_active_voice) {
      // Every voice that is already present during the initial global window
      // inherits that causal evidence. Keeping evidence only for currently
      // selected candidates prevents resonator leakage from pre-arming a
      // voice that is introduced later under an existing sustain.
      state.evidence_ticks = std::numeric_limits<std::uint8_t>::max();
    } else if (state.evidence_ticks < 255U) {
      state.evidence_gap_ticks = 0U;
      ++state.evidence_ticks;
    }
  }

  std::size_t active_count = 0U;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (!state.active) {
      continue;
    }
    if (selected[candidate]) {
      state.release_ticks = 0U;
      if (profile_mode_ == ProfileMode::m3 &&
          midi_routing_ == MidiRouting::per_voice) {
        std::uint8_t desired = state.assigned_string_mask;
        if (desired == 0U && state.assigned_string < kM3OpenNotes.size()) {
          desired = static_cast<std::uint8_t>(1U << state.assigned_string);
        }
        const std::uint8_t removed = static_cast<std::uint8_t>(
            state.midi_voice_mask & ~desired);
        const std::uint8_t added = static_cast<std::uint8_t>(
            desired & ~state.midi_voice_mask);
        const std::uint8_t note =
            static_cast<std::uint8_t>(lowest_note_ + candidate);
        for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          if ((removed & bit) != 0U) {
            append_transition(decision, TransitionKind::note_off, note, 0U,
                              string);
          }
        }
        const std::uint8_t velocity = dynamic_velocity();
        for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          if ((added & bit) != 0U) {
            append_transition(decision, TransitionKind::note_on, note,
                              velocity, string);
          }
        }
        state.midi_voice_mask = desired;
      }
      ++active_count;
      continue;
    }
    if (state.release_ticks < std::numeric_limits<std::uint16_t>::max()) {
      ++state.release_ticks;
    }
    if (state.release_ticks >= release_decisions()) {
      append_candidate_note_off(decision, candidate);
      state = {};
    } else {
      ++active_count;
    }
  }
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (!selected[candidate]) {
      if (!state.active) {
        state.attack_ticks = 0U;
        state.age_ticks = 0U;
      }
      continue;
    }
    state.release_ticks = 0U;
    if (state.active) {
      if (state.age_ticks < std::numeric_limits<std::uint16_t>::max()) {
        ++state.age_ticks;
      }
      continue;
    }
    if (active_count >= static_cast<std::size_t>(max_polyphony_)) {
      state = {};
      continue;
    }
    if (fast_energy_ < slow_energy_ * kAttackEnergyRatio) {
      state.attack_ticks = 0U;
      state.evidence_ticks = 0U;
      state.evidence_gap_ticks = 0U;
      continue;
    }
    if (state.evidence_ticks == 0U) {
      state.attack_ticks = 0U;
      continue;
    }
    if (had_active_voice) {
      const std::uint8_t total_evidence =
          candidate_evidence_decisions(false);
      const std::uint8_t attack = attack_decisions();
      const std::uint8_t pre_attack_evidence =
          total_evidence > attack
              ? static_cast<std::uint8_t>(total_evidence - attack + 1U)
              : 1U;
      if (state.evidence_ticks < pre_attack_evidence) {
        state.attack_ticks = 0U;
        continue;
      }
    }
    if (state.attack_ticks < 255U) {
      ++state.attack_ticks;
    }
    if (state.age_ticks < std::numeric_limits<std::uint16_t>::max()) {
      ++state.age_ticks;
    }
    if (state.attack_ticks >= attack_decisions()) {
      const std::uint8_t velocity = dynamic_velocity();
      if (!append_candidate_note_on(decision, candidate, velocity)) {
        // Preserve the accumulated causal evidence so the candidate can be
        // retried as soon as its playable physical lane is released.
        state.attack_ticks = attack_decisions();
        continue;
      }
      state.active = true;
      state.attack_ticks = 0U;
      state.evidence_ticks = 0U;
      ++active_count;
    }
  }
  const auto guard_score = [](const auto& cells) noexcept {
    double score = 0.0;
    for (std::size_t harmonic = 0U; harmonic < cells.size(); ++harmonic) {
      const Cell& cell = cells[harmonic];
      if (!cell.enabled) {
        continue;
      }
      const double energy = cell.fast_real * cell.fast_real +
                            cell.fast_imaginary * cell.fast_imaginary;
      score += kHarmonicWeights[harmonic] * energy;
    }
    return score;
  };
  const double lower_guard_score = guard_score(lower_cents_guard_cells_);
  const double upper_guard_score = guard_score(upper_cents_guard_cells_);
  observe_calibration(scores, lower_guard_score, upper_guard_score, quiet);
  write_snapshot(decision, scores, selected, lower_guard_score,
                 upper_guard_score, quiet);
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
  for (Cell& cell : lower_cents_guard_cells_) {
    if (cell.enabled) {
      update_cell(cell, dc_blocked);
    }
  }
  for (Cell& cell : upper_cents_guard_cells_) {
    if (cell.enabled) {
      update_cell(cell, dc_blocked);
    }
  }
  if (profile_mode_ == ProfileMode::m3 && max_fret_ <= 2U) {
    const double narrow_mix = 1.0 - narrow_correlation_decay;
    for (std::size_t candidate = 0U;
         candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
      const Cell& fundamental = cells_[cell_index(candidate, 0U)];
      narrow_fundamental_real_[candidate] =
          narrow_correlation_decay * narrow_fundamental_real_[candidate] +
          narrow_mix * dc_blocked * fundamental.cosine;
      narrow_fundamental_imaginary_[candidate] =
          narrow_correlation_decay *
              narrow_fundamental_imaginary_[candidate] -
          narrow_mix * dc_blocked * fundamental.sine;
    }
  }
  bool has_active_voice = false;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    has_active_voice =
        has_active_voice || candidate_states_[candidate].active;
  }
  const bool signal_present =
      fast_energy_ >= signal_floor() &&
      (has_active_voice ||
       fast_energy_ >= slow_energy_ * kSilenceEnergyRatio);
  if (!signal_present) {
    if (signal_present_) {
      for (CandidateState& state : candidate_states_) {
        state.evidence_ticks = 0U;
      }
      harmonic_energy_memory_ = {};
      phase_cents_states_ = {};
    }
    signal_present_ = false;
    signal_samples_ = 0U;
    narrow_signal_samples_ = 0U;
    narrow_fundamental_real_ = {};
    narrow_fundamental_imaginary_ = {};
  } else if (signal_samples_ < std::numeric_limits<std::uint32_t>::max()) {
    signal_present_ = true;
    ++signal_samples_;
    if (narrow_signal_samples_ < std::numeric_limits<std::uint32_t>::max()) {
      ++narrow_signal_samples_;
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
