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
constexpr double kNarrowFundamentalRelativeFloor = 0.12;
// A single causal voice reaches stable selection after the 40 ms correlation
// window. A multi-voice selection needs one additional 10 ms settle interval
// so a startup subharmonic cannot be admitted as a chord voice. These are
// admission gates, not look-ahead: every decision uses samples already seen.
constexpr double kSingleVoiceEvidenceSeconds = 0.040;
constexpr double kMultiVoiceEvidenceSeconds = 0.050;
constexpr double kSilenceEnergyRatio = 0.50;
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
constexpr std::size_t kM3StringMaskCount = 1U << kM3OpenNotes.size();
constexpr std::size_t kM3OpenChordMinimum = 2U;
constexpr double kM3FrettedNotePenalty = 0.60;
constexpr double kM3FretPenalty = 0.005;
constexpr std::uint8_t kCandidateEvidenceDropoutDecisions = 2U;
constexpr std::size_t kCandidateMigrationSemitones = 2U;

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
  if (!valid_config(sample_rate, config)) {
    reset();
    return false;
  }

  sample_rate_ = sample_rate;
  dc_pole = std::exp(-kTwoPi * kDcCutoffHz / sample_rate_);
  correlation_decay = std::exp(-1.0 / (kFastEnergySeconds * sample_rate_));
  narrow_correlation_decay =
      std::exp(-1.0 / (kNarrowFundamentalSeconds * sample_rate_));
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
  decision_phase_ = 0U;
  transition_sequence_ = 0U;
  snapshot_generation_ = 0U;
  signal_samples_ = 0U;
  narrow_signal_samples_ = 0U;
  signal_present_ = false;
  candidate_states_ = {};
  narrow_fundamental_real_ = {};
  narrow_fundamental_imaginary_ = {};
#if defined(M3_TESTING)
  selection_work_ = {};
#endif
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
    std::uint8_t velocity) noexcept {
  const VoiceTransition transition{
      0U, kind, note, velocity, transition_sequence_++};
  static_cast<void>(decision.transitions.push_back(transition));
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
      // fundamental dominates its score. This keeps the intended octave
      // shadow rejection for a single tone while retaining an actual weaker
      // octave from another string.
      const bool distinct_higher_peak =
          candidate > stronger && is_local_peak(scores, candidate, count) &&
          fundamentals[candidate] >= 0.85 * scores[candidate];
      if (is_harmonic_shadow(candidate, stronger, fundamentals) &&
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

void MonophonicPitchDetector::write_snapshot(
    DetectorDecision& decision,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<bool, kMaxCandidates>& selected, bool quiet) noexcept {
  TunerSnapshot& snapshot = decision.tuner_snapshot;
  snapshot.generation = ++snapshot_generation_;
  snapshot.max_polyphony = max_polyphony_;
  std::size_t voice_count = 0U;
  const double threshold = std::max(fast_energy_ * kCandidateCoherenceRatio,
                                    kScoreEpsilon);
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_) &&
       voice_count < kMaxVoices;
       ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    if (!state.active && !selected[candidate]) {
      continue;
    }
    TunerVoice voice;
    voice.midi_note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    voice.age_ticks = state.age_ticks;
    voice.state = state.active && selected[candidate]
                      ? TunerVoiceState::tracking
                      : TunerVoiceState::settling;
    const double normalized = std::clamp(
        (scores[candidate] - threshold) / (scores[candidate] + threshold),
        0.0, 1.0);
    voice.confidence_q15 = static_cast<std::uint16_t>(std::lround(
        normalized * 32767.0));
    if (candidate > 0U && candidate + 1U <
                              static_cast<std::size_t>(candidate_count_)) {
      const double left = std::log(std::max(scores[candidate - 1U],
                                             kScoreEpsilon));
      const double center = std::log(std::max(scores[candidate],
                                               kScoreEpsilon));
      const double right = std::log(std::max(scores[candidate + 1U],
                                              kScoreEpsilon));
      const double denominator = left - 2.0 * center + right;
      if (std::isfinite(denominator) && denominator < -kScoreEpsilon) {
        const double semitone_offset = std::clamp(
            0.5 * (left - right) / denominator, -0.5, 0.5);
        if (std::isfinite(semitone_offset)) {
          voice.cents_q8 = static_cast<std::int16_t>(std::lround(
              semitone_offset * 100.0 * 256.0));
          voice.cents_valid = true;
        }
      }
    }
    snapshot.voices[voice_count++] = voice;
  }
  snapshot.voice_count = static_cast<std::uint8_t>(voice_count);
  snapshot.state = voice_count == 0U ? TunerFrameState::no_signal
                                     : TunerFrameState::tracking;
  if (quiet && voice_count == 0U) {
    snapshot.state = TunerFrameState::no_signal;
  }
  decision.tuner_snapshot_ready = true;
}

DetectorDecision MonophonicPitchDetector::make_decision() noexcept {
  DetectorDecision decision;
  std::array<double, kMaxCandidates> scores{};
  std::array<double, kMaxCandidates> fundamentals{};
  std::array<double, kMaxCandidates> narrow_fundamentals{};
  std::array<bool, kMaxCandidates> selected{};
  const bool minimum_evidence =
      static_cast<double>(signal_samples_) >=
      sample_rate_ * kSingleVoiceEvidenceSeconds;
  bool quiet = !minimum_evidence || fast_energy_ < signal_floor() ||
               fast_energy_ < slow_energy_ * kSilenceEnergyRatio;
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
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

  bool had_active_voice = false;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    had_active_voice = had_active_voice || candidate_states_[candidate].active;
  }
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
      ++active_count;
      continue;
    }
    if (state.release_ticks < 255U) {
      ++state.release_ticks;
    }
    if (state.release_ticks >= release_decisions()) {
      append_transition(decision, TransitionKind::note_off,
                        static_cast<std::uint8_t>(lowest_note_ + candidate), 0U);
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
      append_transition(decision, TransitionKind::note_on,
                        static_cast<std::uint8_t>(lowest_note_ + candidate),
                        dynamic_velocity());
      state.active = true;
      state.attack_ticks = 0U;
      state.evidence_ticks = 0U;
      ++active_count;
    }
  }
  write_snapshot(decision, scores, selected, quiet);
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
  const bool signal_present =
      fast_energy_ >= signal_floor() &&
      fast_energy_ >= slow_energy_ * kSilenceEnergyRatio;
  if (!signal_present) {
    if (signal_present_) {
      for (CandidateState& state : candidate_states_) {
        state.evidence_ticks = 0U;
      }
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
