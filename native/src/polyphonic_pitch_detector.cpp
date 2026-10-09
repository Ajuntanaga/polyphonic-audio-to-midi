#include "m3/polyphonic_pitch_detector.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>

#include "m3/harmonic_evidence.hpp"
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
// The slow profile spans several ordinary guitar beat cycles. It is updated
// incrementally at the existing decision cadence, so it adds neither a worker
// thread nor audio-callback allocation.
constexpr double kLongHarmonicMemorySeconds = 1.500;
constexpr double kLongHarmonicProfileReadySeconds = 0.750;
constexpr double kBeatEnvelopeMeanSeconds = 1.250;
constexpr double kBeatDeviationSeconds = 0.250;
constexpr double kMinimumBeatHz = 0.25;
constexpr double kMaximumBeatHz = 12.0;
constexpr double kMinimumBeatModulationRatio = 0.04;
constexpr double kMinimumBeatAwareHoldSeconds = 0.750;
constexpr double kMaximumBeatAwareHoldSeconds = 3.000;
constexpr double kBeatCyclesToHold = 1.5;
// A calibrated per-string fine-frequency fit complements the instantaneous
// harmonic mixture. The history is sampled near 100 Hz and bounded to 512
// complex phasors (about five seconds), so it can resolve ordinary slow beat
// patterns without adding per-sample work or allocating on the audio thread.
constexpr double kFineFrequencyTargetRateHz = 100.0;
constexpr std::uint32_t kFineFrequencyAnalysisStride = 5U;
// Give close calibrated physical-string offsets three seconds of beat-time
// evidence before admitting a multi-source interpretation. Ordinary pitch
// and chord admission stay on their short causal windows; only the optional
// same-pitch physical-string expansion waits for this evidence. Live testing
// can justify the stricter 3.25-second boundary if this remains unstable.
constexpr double kFineFrequencyMinimumEvidenceSeconds = 3.0;
constexpr double kFineFrequencyMaximumGapSeconds = 0.50;
constexpr double kFineFrequencyInitialConsensusSeconds = 0.20;
constexpr double kFineFrequencyReplacementConsensusSeconds = 2.25;
constexpr double kFineFrequencyRidge = 1.0e-5;
constexpr double kFineFrequencyMinimumRelativeAmplitude = 0.12;
constexpr double kFineFrequencyProfileMatchedRelativeAmplitude = 0.25;
constexpr double kFineFrequencyMinimumResidualImprovement = 0.08;
constexpr double kFineFrequencyMinimumPhaseDeviationHz = 0.03;
constexpr std::size_t kFineFrequencyMaximumPhaseSamples = 64U;
// A five-second causal observation cannot resolve templates that are only a
// few millihertz apart.  Keep the floor below the closest ordinary measured
// pair, but above the 0.0046 Hz near-duplicate calibration that caused one
// physical string to be represented by multiple lanes.
constexpr double kFineFrequencyDistinctSourceSeparationHz = 0.05;
// Phase modulation can corroborate a rejected single-string profile only
// when the calibrated fundamentals are themselves separated enough to be
// physically distinguishable over the bounded history. This keeps the
// recorded 0.12 Hz C4 near-duplicate from becoming a second string while
// retaining the closest confirmed two-cent unison pair (about 0.24 Hz).
constexpr double kFineFrequencyPhaseSupportedSeparationHz = 0.18;
// Calibration gives us a second, independent observation: a lone string's
// normalized harmonic profile.  Modulated phase alone is not enough because
// pick transients and dispersive decay can move the instantaneous frequency
// of one string. Only admit a multi-source interpretation when every single
// calibrated profile leaves a material normalized squared error.
constexpr double kFineFrequencySingleProfileRejectionError = 0.010;
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
// The fine-pitch phasor starts after causal pitch selection. Its cascaded
// smoothing needs this additional evidence before its first value is honest
// enough to expose as a tuner measurement.
constexpr double kPhaseCentsEvidenceSeconds = 0.160;
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
// Candidate scores are normalized to input energy; a clean sinusoid therefore
// contributes about 0.50 at its fundamental. Keep the position prior below
// that physical baseline even at fret 24, otherwise the DP prefers its empty
// state and the upper end of the declared M3 range can never enter attack.
constexpr double kM3FrettedNotePenalty = 0.20;
constexpr double kM3FretPenalty = 0.005;
// A full eight-string assignment has the same summed linear fret count under
// many cyclic permutations. A small convex position prior rejects those
// implausible high-fret rotations while leaving a learned string fingerprint
// enough authority to identify a genuinely high fretted string.
constexpr double kM3AssignmentFretShapePenalty = 0.50;
constexpr double kM3CalibrationProfileBonus = 512.0;
constexpr double kM3PartialCalibrationProfileBonus = 30.0;
constexpr double kM3CalibrationCentsPenalty = 16.0;
// When two physical lanes have materially different learned spectra, their
// per-fret cents corridors can disambiguate an articulation whose current
// harmonic balance drifted toward the wrong template. Near-collinear
// templates retain the ordinary cents weight because tuning drift alone is
// not a safe string-identity oracle.
constexpr double kM3DistinctiveCalibrationCentsPenalty = 21.0;
constexpr double kM3DistinctiveCalibrationProfileDistance = 0.010;
constexpr double kM3CalibratedCentsMinimumAdvantage = 0.75;
constexpr double kM3OpenStringAssignmentBonus = 64.0;
constexpr double kM3CalibratedCandidateThresholdRatio = 0.25;
constexpr double kM3CalibratedHighestOpenThresholdRatio = 0.08;
constexpr double kM3CalibratedCandidateMinimumSimilarity = 0.97;
constexpr double kM3CalibratedCandidateMinimumAdvantage = 0.015;
// A highly repeatable calibrated point already has a trustworthy absolute
// harmonic balance. Only less-repeatable points need the slower spectral-shape
// tie-breaker that tolerates pick-position changes.
constexpr double kM3SettledShapeMaximumConfidence = 0.95;
constexpr double kM3CalibratedHighestOpenMinimumSimilarity = 0.99;
constexpr double kM3TuningOffsetMinimumSimilarity = 0.82;
constexpr double kM3TuningOffsetMaximumCents = 8.0;
constexpr double kM3TuningOffsetPendingAgreementCents = 1.5;
constexpr double kM3TuningOffsetTrackingAgreementCents = 4.0;
constexpr double kM3TuningOffsetAcquisitionSeconds = 0.75;
constexpr double kM3TuningOffsetTrackingSeconds = 0.75;
constexpr std::size_t kM3TuningOffsetMinimumStrings = 3U;
constexpr double kM3ProvisionalStringRetentionBonus = 4.0;
// A sounding note owns its exposed tuner lane until note-off regardless of
// whether MIDI is routed through one channel or one channel per voice. This
// is larger than the maximum supported 36-fret position prior, while
// feasibility can still override it when that string is unavailable.
constexpr double kM3ActiveStringRetentionBonus = 1024.0;
// The posterior is deliberately smaller than the settled-lane retention and
// fine-frequency constraints. It stabilizes ambiguous alternatives without
// overruling direct physical evidence or making a provisional lane permanent.
constexpr double kM3StringPosteriorCost = 0.25;
constexpr double kM3StringPosteriorDecisiveCost = 2.0;
constexpr double kM3StringPosteriorDecisiveProbability = 0.80;
constexpr double kM3StringPosteriorProfileWeight = 6.0;
constexpr double kM3StringPosteriorDescriptorWeight = 1.5;
constexpr double kM3StringPosteriorDetuningWeight = 2.0;
constexpr double kM3StringPosteriorCentsScale = 4.0;
constexpr double kM3UnisonMinimumComponent = 0.15;
constexpr double kM3UnisonMinimumTemplateDistance = 0.0025;
constexpr double kM3UnisonMinimumErrorImprovement = 0.010;
constexpr double kM3UnisonMaximumErrorRatio = 0.55;
// A single ringing string can move between two almost coincident calibrated
// templates as its pick transient decays. A static harmonic snapshot may add
// a second lane only when the calibrated fundamentals are far enough apart to
// be independently resolved in that snapshot. Closer real unisons remain the
// responsibility of the causal fine-frequency or beat evidence paths.
constexpr double kM3ProfileOnlyUnisonMinimumSeparationHz = 0.35;
// Even when a transient rejects every stored single-string profile, a static
// mixture may not turn two sub-cent calibration neighbours into two physical
// sources. The physical C4 capture measured a 0.77-cent near-duplicate; the
// closest confirmed synthetic unison pair is two cents apart.
constexpr double kM3ProfileOnlyNearDuplicateSeparationCents = 1.25;
// Several physical strings can contribute complementary fingerprints that
// are weak in isolation but decisive together. The bounded complement search
// additionally requires independently measured beat evidence and must remove
// most of the remaining profile error.
constexpr double kM3UnisonComplementMaximumRemainingErrorRatio = 0.35;
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

}  // namespace

bool PolyphonicPitchDetector::configure(double sample_rate,
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
  long_harmonic_memory_decay = std::exp(
      -static_cast<double>(kDecisionQuantum) /
      (kLongHarmonicMemorySeconds * sample_rate_));
  unison_dropout_decisions_ = static_cast<std::uint16_t>(std::clamp(
      std::ceil(kM3UnisonDropoutSeconds * sample_rate_ /
                static_cast<double>(kDecisionQuantum)),
      1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  fine_frequency_decimation_decisions_ =
      static_cast<std::uint16_t>(std::clamp(
          std::round(sample_rate_ /
                     (static_cast<double>(kDecisionQuantum) *
                      kFineFrequencyTargetRateHz)),
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

void PolyphonicPitchDetector::set_runtime_config(
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

void PolyphonicPitchDetector::reset() noexcept {
  previous_input_ = 0.0;
  previous_dc_output_ = 0.0;
  fast_energy_ = 0.0;
  slow_energy_ = 0.0;
  previous_decision_energy_ = 0.0;
  calibration_tuning_offset_cents_ = 0.0;
  calibration_tuning_lane_cents_ = {};
  pending_calibration_tuning_lane_cents_ = {};
  pending_calibration_tuning_lane_observations_ = {};
  calibration_tuning_evidence_ = 0U;
  calibration_tuning_lane_mask_ = 0U;
  decision_phase_ = 0U;
  decision_counter_ = 0U;
  transition_sequence_ = 0U;
  snapshot_generation_ = 0U;
  signal_samples_ = 0U;
  narrow_signal_samples_ = 0U;
  signal_present_ = false;
  candidate_states_ = {};
  narrow_fundamental_real_ = {};
  narrow_fundamental_imaginary_ = {};
  harmonic_energy_memory_ = {};
  long_harmonic_energy_memory_ = {};
  harmonic_memory_updates_ = {};
  phase_cents_states_ = {};
  partial_detuning_trackers_ = {};
  partial_detuning_last_update_ticks_ = {};
  partial_detuning_cursor_ = 0U;
  beat_evidence_states_ = {};
  fine_frequency_evidence_states_ = {};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  selection_dispositions_ = {};
#endif
  string_fret_posteriors_.reset();
  string_fret_energy_memory_ = {};
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

bool PolyphonicPitchDetector::begin_string_calibration(
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

void PolyphonicPitchDetector::cancel_string_calibration() noexcept {
  calibrator_.cancel();
}

void PolyphonicPitchDetector::clear_string_calibration() noexcept {
  calibrator_.clear();
}

CalibrationSweepStatus PolyphonicPitchDetector::calibration_status()
    const noexcept {
  return calibrator_.status();
}

const StringCalibrationBank& PolyphonicPitchDetector::calibration_bank()
    const noexcept {
  return calibrator_.bank();
}

std::uint8_t PolyphonicPitchDetector::partial_detuning_candidate_count()
    const noexcept {
  std::uint8_t count = 0U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if ((partial_detuning_trackers_[candidate].evidence().valid_mask & 0x3EU) !=
        0U) {
      ++count;
    }
  }
  return count;
}

PartialDetuningEvidence PolyphonicPitchDetector::partial_detuning_evidence(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return {};
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? partial_detuning_trackers_[candidate].evidence()
             : PartialDetuningEvidence{};
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
SelectionDisposition PolyphonicPitchDetector::selection_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return SelectionDisposition::below_threshold;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? selection_dispositions_[candidate]
             : SelectionDisposition::below_threshold;
}

std::uint8_t PolyphonicPitchDetector::fine_frequency_member_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const FineFrequencyEvidenceState& state =
      fine_frequency_evidence_states_[candidate];
  return state.valid ? state.member_mask : 0U;
}

std::uint8_t PolyphonicPitchDetector::fine_frequency_pending_member_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate].pending_member_mask
             : 0U;
}

FineFrequencyDisposition PolyphonicPitchDetector::fine_frequency_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return FineFrequencyDisposition::unresolved;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate].disposition
             : FineFrequencyDisposition::unresolved;
}

std::uint8_t PolyphonicPitchDetector::fine_frequency_fit_member_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate].fit_member_mask
             : 0U;
}
#endif

void PolyphonicPitchDetector::set_calibration_bank(
    const StringCalibrationBank& bank) noexcept {
  calibrator_.set_bank(bank);
  fine_frequency_evidence_states_ = {};
  partial_detuning_trackers_ = {};
  partial_detuning_last_update_ticks_ = {};
  partial_detuning_cursor_ = 0U;
  string_fret_posteriors_.reset();
  string_fret_energy_memory_ = {};
  calibration_tuning_offset_cents_ = 0.0;
  calibration_tuning_lane_cents_ = {};
  pending_calibration_tuning_lane_cents_ = {};
  pending_calibration_tuning_lane_observations_ = {};
  calibration_tuning_evidence_ = 0U;
  calibration_tuning_lane_mask_ = 0U;
}

void PolyphonicPitchDetector::update_cell(Cell& cell, double sample) noexcept {
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

std::uint8_t PolyphonicPitchDetector::attack_decisions() const noexcept {
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

std::uint16_t PolyphonicPitchDetector::release_decisions() const noexcept {
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

std::uint16_t PolyphonicPitchDetector::candidate_release_decisions(
    std::size_t candidate, bool quiet) const noexcept {
  const std::uint16_t ordinary = release_decisions();
  if (quiet || profile_mode_ != ProfileMode::m3 ||
      candidate >= static_cast<std::size_t>(candidate_count_)) {
    return ordinary;
  }
  const std::uint8_t members =
      candidate_states_[candidate].assigned_string_mask;
  const bool resolved_unison =
      members != 0U &&
      (members & static_cast<std::uint8_t>(members - 1U)) != 0U;
  return resolved_unison
             ? std::max(ordinary, unison_dropout_decisions(candidate))
             : ordinary;
}

std::uint8_t PolyphonicPitchDetector::candidate_evidence_decisions(
    bool multi_voice) const noexcept {
  const double seconds = multi_voice ? kMultiVoiceEvidenceSeconds
                                     : kSingleVoiceEvidenceSeconds;
  const double decisions = std::ceil(seconds * sample_rate_ /
                                     static_cast<double>(kDecisionQuantum));
  return static_cast<std::uint8_t>(std::clamp(
      decisions, 1.0, static_cast<double>(std::numeric_limits<std::uint8_t>::max())));
}

double PolyphonicPitchDetector::signal_floor() const noexcept {
  return signal_floor_;
}

std::uint8_t PolyphonicPitchDetector::dynamic_velocity() const noexcept {
  if (velocity_mode_ == VelocityMode::fixed) {
    return fixed_velocity_;
  }
  const double amplitude = std::sqrt(std::max(0.0, fast_energy_));
  const double db = 20.0 * std::log10(std::max(amplitude, 1.0e-12));
  const double normalized = std::clamp((db + 60.0) / 54.0, 0.0, 1.0);
  const double velocity = 1.0 + normalized * 126.0;
  return static_cast<std::uint8_t>(std::lround(velocity));
}

void PolyphonicPitchDetector::append_transition(
    DetectorDecision& decision, TransitionKind kind, std::uint8_t note,
    std::uint8_t velocity, std::uint8_t voice_id) noexcept {
  const VoiceTransition transition{
      0U, kind, note, velocity, transition_sequence_++, voice_id};
  static_cast<void>(decision.transitions.push_back(transition));
}

bool PolyphonicPitchDetector::append_candidate_note_on(
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
    long_harmonic_energy_memory_[candidate] = {};
    harmonic_memory_updates_[candidate] = 0U;
    return true;
  }
  append_transition(decision, TransitionKind::note_on, note, velocity);
  harmonic_energy_memory_[candidate] = {};
  long_harmonic_energy_memory_[candidate] = {};
  harmonic_memory_updates_[candidate] = 0U;
  return true;
}

void PolyphonicPitchDetector::append_candidate_note_off(
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

bool PolyphonicPitchDetector::is_harmonic_shadow(
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

void PolyphonicPitchDetector::refresh_m3_playable_string_masks() noexcept {
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

std::uint8_t PolyphonicPitchDetector::playable_string_mask(
    std::size_t candidate) const noexcept {
  if (profile_mode_ != ProfileMode::m3 ||
      candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  return playable_string_masks_[candidate];
}

bool PolyphonicPitchDetector::has_calibrated_direct_support(
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    std::size_t candidate, std::size_t count, double threshold) const noexcept {
  if (candidate >= count ||
      calibrator_.bank().calibrated_string_mask == 0U) {
    return false;
  }
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  const double threshold_ratio =
      note == kM3OpenNotes.back()
          ? kM3CalibratedHighestOpenThresholdRatio
          : kM3CalibratedCandidateThresholdRatio;
  if (scores[candidate] <= threshold * threshold_ratio ||
      fundamentals[candidate] < 0.85 * scores[candidate] ||
      !has_direct_fundamental_peak(scores, fundamentals, candidate, count)) {
    return false;
  }
  const std::uint8_t playable = playable_string_mask(candidate);
  if (note < kM3OpenNotes.back()) {
    return false;
  }
  double best = -1.0;
  double second = -1.0;
  double highest_open_similarity = -1.0;
  std::size_t measured = 0U;
  std::size_t playable_count = 0U;
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
    if ((playable & bit) == 0U) {
      continue;
    }
    ++playable_count;
    const StringCalibrationPoint* point =
        calibrator_.bank().point(string, note - kM3OpenNotes[string]);
    if (point == nullptr ||
        point->quality == CalibrationPointQuality::missing) {
      continue;
    }
    ++measured;
    const double similarity = calibration_similarity(candidate, string);
    if (string + 1U == kM3OpenNotes.size()) {
      highest_open_similarity = similarity;
    }
    if (similarity > best) {
      second = best;
      best = similarity;
    } else if (similarity > second) {
      second = similarity;
    }
  }
  // The relaxed threshold is safe only when the calibration covers every
  // physically playable lane and distinguishes the best lane from another
  // measured alternative. Partial coverage would turn missing data into an
  // artificial identity advantage.
  const bool bounded_complete_shape =
      playable_count == 2U ||
      (note == kM3OpenNotes.back() &&
       playable_count == kM3OpenNotes.size() - 1U);
  if (!bounded_complete_shape || measured != playable_count) {
    return false;
  }
  if (note == kM3OpenNotes.back()) {
    // At C4 the bounded resonator bank retains little more than the
    // fundamental for most playable frets, so several correctly measured
    // templates can be nearly collinear. Do not require the open-string row
    // to beat them by an arbitrary cosine margin: require complete physical
    // calibration and an independently strong match to the exact open row.
    // Harmonic-only lower-string controls remain below this floor.
    return highest_open_similarity >=
           kM3CalibratedHighestOpenMinimumSimilarity;
  }
  return best >= kM3CalibratedCandidateMinimumSimilarity &&
         best - second >= kM3CalibratedCandidateMinimumAdvantage;
}

void PolyphonicPitchDetector::select_m3_feasible_candidates(
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    const std::array<double, kMaxCandidates>& narrow_fundamentals,
    double threshold,
    std::array<bool, kMaxCandidates>& selected, std::size_t count) noexcept {
  selected = {};
  m3_pool_ = {};
  m3_dp_states_ = {};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  selection_dispositions_.fill(SelectionDisposition::below_threshold);
#endif
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
      const bool calibrated_direct = has_calibrated_direct_support(
          scores, fundamentals, candidate, count, threshold);
      if (scores[candidate] <= threshold && !calibrated_direct) {
        continue;
      }
      raw_eligible[candidate] = candidate_states_[candidate].active ||
                                is_local_peak(scores, candidate, count) ||
                                has_m3_candidate_evidence(
                                    scores, fundamentals, candidate, count);
      const double normalized_score =
          scores[candidate] / std::max(fast_energy_, kScoreEpsilon);
      // A fully covered, clearly distinguished calibration can rescue a
      // direct high-fret fundamental from broadband attack energy. Give that
      // narrowly admitted candidate just enough rank to survive the largest
      // declared fret prior; this is not a general sensitivity reduction.
      const double calibrated_floor =
          kM3FrettedNotePenalty +
          kM3FretPenalty * static_cast<double>(max_fret_) + 0.01;
      selection_scores[candidate] =
          calibrated_direct ? std::max(normalized_score, calibrated_floor)
                            : normalized_score;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (raw_eligible[candidate]) {
      selection_dispositions_[candidate] =
          SelectionDisposition::spectral_rejected;
    }
#endif
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
      // Preserve a started higher string while it still has a direct local
      // fundamental. A new higher octave needs stricter evidence: its own
      // fundamental must dominate its score and remain comparable to the
      // lower fundamental. This keeps a bright lower string's upper partial
      // from becoming a second physical voice.
      const bool retained_higher_voice =
          candidate_states_[candidate].active &&
          has_direct_fundamental_peak(scores, fundamentals, candidate, count);
      const bool distinct_higher_peak =
          candidate > stronger &&
          (retained_higher_voice ||
           (is_local_peak(scores, candidate, count) &&
            fundamentals[candidate] >= 0.85 * scores[candidate] &&
            (fundamentals[candidate] >= 0.85 * fundamentals[stronger] ||
             has_calibrated_direct_support(scores, fundamentals, candidate,
                                           count, threshold))));
      if ((is_harmonic_shadow(candidate, stronger, fundamentals) ||
           is_m3_lower_cross_harmonic_shadow(candidate, stronger,
                                              fundamentals)) &&
          !distinct_lower_peak && !distinct_higher_peak) {
        shadowed = true;
        break;
      }
    }
    spectral_eligible[candidate] = !shadowed;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (spectral_eligible[candidate]) {
      selection_dispositions_[candidate] = SelectionDisposition::dp_evicted;
    }
#endif
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
      const std::size_t candidate = m3_pool_[option_index].detector_index;
      selected[candidate] = true;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      selection_dispositions_[candidate] = SelectionDisposition::selected;
#endif
    }
  }
  // A fret-position prior may rank a weak but direct high-fret candidate
  // below the empty DP state even though the candidate is a clear local
  // fundamental above the coherence floor.  The prior may choose among
  // feasible chord assignments; it must not turn the only physical pitch
  // into silence.  Admit exactly the strongest direct candidate in that
  // otherwise-empty case, leaving all multi-voice and shadow decisions to
  // the normal bounded assignment above.
  if (best.voice_count == 0U) {
    std::size_t strongest = pool_count;
    for (std::size_t option_index = 0U; option_index < pool_count;
         ++option_index) {
      const std::size_t candidate =
          m3_pool_[option_index].detector_index;
      if (!has_direct_fundamental_peak(scores, fundamentals, candidate,
                                       count) ||
          (strongest != pool_count &&
           selection_scores[candidate] <=
               selection_scores[m3_pool_[strongest].detector_index])) {
        continue;
      }
      strongest = option_index;
    }
    if (strongest != pool_count) {
      const std::size_t candidate = m3_pool_[strongest].detector_index;
      selected[candidate] = true;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      selection_dispositions_[candidate] = SelectionDisposition::selected;
#endif
    }
  }
}

void PolyphonicPitchDetector::update_calibration_tuning_offset(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }
  std::array<double, kMaxVoices> observations{};
  std::array<bool, kMaxVoices> observed{};
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_);
       ++candidate) {
    const PhaseCentsState& phase = phase_cents_states_[candidate];
    const CandidateState& state = candidate_states_[candidate];
    const std::uint8_t members =
        state.assigned_string_mask != 0U
            ? state.assigned_string_mask
            : (state.assigned_string < kM3OpenNotes.size()
                   ? static_cast<std::uint8_t>(1U << state.assigned_string)
                   : 0U);
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    if (!selected[candidate] || !phase.valid || !state.active ||
        state.polyphonic_context || members == 0U ||
        (members & static_cast<std::uint8_t>(members - 1U)) != 0U ||
        (fine.valid && fine.multi_source_observed)) {
      continue;
    }
    const std::uint8_t playable = playable_string_mask(candidate);
    const std::uint8_t note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      if ((playable & bit) == 0U || note != kM3OpenNotes[string] ||
          members != bit) {
        continue;
      }
      // A global reference shift must be inferred from an open string. A
      // fretted point carries local intonation and setup error; treating that
      // residual as common tuning moves every other string in the wrong
      // direction.
      const StringCalibrationPoint* point =
          calibrator_.bank().point(string, 0U);
      if (point == nullptr ||
          point->quality != CalibrationPointQuality::measured) {
        continue;
      }
      const double similarity = calibration_similarity(candidate, string);
      if (similarity < kM3TuningOffsetMinimumSimilarity) {
        continue;
      }
      const double learned_cents =
          static_cast<double>(point->cents_offset_q8) / 256.0;
      const double residual = phase.cents - learned_cents;
      if (std::isfinite(residual) &&
          std::abs(residual) <= kM3TuningOffsetMaximumCents) {
        observations[string] = residual;
        observed[string] = true;
      }
    }
  }
  const double ready_observations = std::ceil(
      kM3TuningOffsetAcquisitionSeconds * sample_rate_ /
      static_cast<double>(kDecisionQuantum));
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    if (!observed[string]) {
      continue;
    }
    std::uint16_t& count =
        pending_calibration_tuning_lane_observations_[string];
    double& pending = pending_calibration_tuning_lane_cents_[string];
    if (count == 0U ||
        std::abs(observations[string] - pending) <=
            kM3TuningOffsetPendingAgreementCents) {
      const double next_count = static_cast<double>(count) + 1.0;
      pending += (observations[string] - pending) / next_count;
      if (count < std::numeric_limits<std::uint16_t>::max()) {
        ++count;
      }
    } else {
      pending = observations[string];
      count = 1U;
    }
    if (static_cast<double>(count) >= ready_observations) {
      calibration_tuning_lane_cents_[string] = pending;
      calibration_tuning_lane_mask_ = static_cast<std::uint8_t>(
          calibration_tuning_lane_mask_ | (1U << string));
      pending = 0.0;
      count = 0U;
    }
  }

  std::array<double, kMaxVoices> lane_offsets{};
  std::size_t lane_count = 0U;
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    if ((calibration_tuning_lane_mask_ & (1U << string)) != 0U) {
      lane_offsets[lane_count++] = calibration_tuning_lane_cents_[string];
    }
  }
  if (lane_count < kM3TuningOffsetMinimumStrings) {
    return;
  }
  for (std::size_t index = 1U; index < lane_count; ++index) {
    const double value = lane_offsets[index];
    std::size_t insertion = index;
    while (insertion > 0U && lane_offsets[insertion - 1U] > value) {
      lane_offsets[insertion] = lane_offsets[insertion - 1U];
      --insertion;
    }
    lane_offsets[insertion] = value;
  }
  const double shared_offset = lane_offsets[lane_count / 2U];
  if (calibration_tuning_evidence_ == 0U) {
    calibration_tuning_offset_cents_ = shared_offset;
    calibration_tuning_evidence_ = 1U;
    return;
  }
  const double delta = shared_offset - calibration_tuning_offset_cents_;
  if (std::abs(delta) > kM3TuningOffsetTrackingAgreementCents) {
    return;
  }
  const double mix = 1.0 - std::exp(
      -static_cast<double>(kDecisionQuantum) /
      (kM3TuningOffsetTrackingSeconds * sample_rate_));
  calibration_tuning_offset_cents_ += mix * delta;
  if (calibration_tuning_evidence_ <
      std::numeric_limits<std::uint16_t>::max()) {
    ++calibration_tuning_evidence_;
  }
}

void PolyphonicPitchDetector::assign_m3_strings(
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
    } else if (!candidate_states_[candidate].active) {
      string_fret_posteriors_.reset(candidate);
      string_fret_energy_memory_[candidate] = 0.0;
    }
  }
  if (selected_count == 0U) {
    return;
  }
  if (selected_count > 1U) {
    for (std::size_t voice = 0U; voice < selected_count; ++voice) {
      bool only_upper_harmonics =
          candidate_states_[candidates[voice]].active;
      for (std::size_t other = 0U;
           only_upper_harmonics && other < selected_count; ++other) {
        if (other == voice) {
          continue;
        }
        if (candidates[other] <= candidates[voice]) {
          only_upper_harmonics = false;
          continue;
        }
        const std::size_t distance =
            candidates[other] - candidates[voice];
        only_upper_harmonics =
            std::find(kHarmonicIntervals.begin(), kHarmonicIntervals.end(),
                      static_cast<int>(distance)) != kHarmonicIntervals.end();
      }
      // A lower active candidate accompanied only by exact upper harmonics
      // has not established independent physical voices. Preserve the
      // established behavior for every other multi-candidate selection,
      // including ordinary chords, startup groups, and mixed spectra.
      if (!only_upper_harmonics) {
        candidate_states_[candidates[voice]].polyphonic_context = true;
      }
    }
  }
  bool isolated_selected_voice = selected_count == 1U;
  if (isolated_selected_voice) {
    const CandidateState& selected_state = candidate_states_[candidates[0U]];
    if (selected_state.polyphonic_context) {
      isolated_selected_voice = false;
    }
    const std::uint8_t selected_members = selected_state.assigned_string_mask;
    if (selected_members != 0U &&
        (selected_members & static_cast<std::uint8_t>(selected_members - 1U)) !=
            0U) {
      isolated_selected_voice = false;
    }
    for (std::size_t candidate = 0U;
         isolated_selected_voice &&
         candidate < static_cast<std::size_t>(candidate_count_);
         ++candidate) {
      if (candidate != candidates[0U] && candidate_states_[candidate].active) {
        isolated_selected_voice = false;
      }
    }
  }
  const std::uint16_t stable_tuner_ticks =
      static_cast<std::uint16_t>(std::clamp(
          std::ceil(kLongHarmonicProfileReadySeconds * sample_rate_ /
                    static_cast<double>(kDecisionQuantum)),
          1.0,
          static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  const bool calibrated_reassignment_ready =
      isolated_selected_voice && candidate_states_[candidates[0U]].active &&
      !candidate_states_[candidates[0U]].calibrated_lane_committed &&
      candidate_states_[candidates[0U]].age_ticks >= stable_tuner_ticks &&
      phase_cents_states_[candidates[0U]].valid;

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
    if (selected[candidate]) {
      if (state.active && state.assigned_string < kM3OpenNotes.size()) {
        const std::uint8_t primary = static_cast<std::uint8_t>(
            1U << state.assigned_string);
        reserved_strings = static_cast<std::uint8_t>(
            reserved_strings | (state.assigned_string_mask & ~primary));
      }
      continue;
    }
    if (!state.active || state.assigned_string >= kM3OpenNotes.size()) {
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
    std::array<double, kMaxVoices> learned_cents{};
    std::array<double, kMaxVoices> learned_cents_errors{};
    std::array<double, kMaxVoices> descriptor_log_likelihoods{};
    std::array<double, kMaxVoices> detuning_log_likelihoods{};
    std::array<bool, kMaxVoices> has_detuning_likelihood{};
    std::array<const StringCalibrationPoint*, kMaxVoices> learned_points{};
    std::array<bool, kMaxVoices> has_learned_profile{};
    double learned_sum = 0.0;
    double descriptor_sum = 0.0;
    double detuning_sum = 0.0;
    std::size_t detuning_count = 0U;
    std::size_t best_detuning_string = kMaxVoices;
    double best_detuning_log_likelihood =
        -std::numeric_limits<double>::infinity();
    double best_learned_similarity = -1.0;
    std::size_t learned_count = 0U;
    bool all_playable_profiles_learned = true;
    bool settled_shape_eligible = calibrated_reassignment_ready;
    if (settled_shape_eligible) {
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
        if ((playable & bit) == 0U) {
          continue;
        }
        const StringCalibrationPoint* point = calibrator_.bank().point(
            string, note - kM3OpenNotes[string]);
        if (point == nullptr ||
            point->quality == CalibrationPointQuality::missing ||
            static_cast<double>(point->confidence_q15) / 32767.0 >=
                kM3SettledShapeMaximumConfidence) {
          settled_shape_eligible = false;
          break;
        }
      }
    }
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
        all_playable_profiles_learned = false;
        continue;
      }
      has_learned_profile[string] = true;
      learned_points[string] = point;
      learned_similarities[string] =
          settled_shape_eligible
              ? settled_calibration_similarity(candidate, string)
              : calibration_similarity(candidate, string);
      best_learned_similarity =
          std::max(best_learned_similarity, learned_similarities[string]);
      learned_cents[string] =
          static_cast<double>(point->cents_offset_q8) / 256.0;
      learned_sum += learned_similarities[string];
      ++learned_count;
    }
    std::array<double, kHarmonicEvidenceCount> fast_energy{};
    std::array<double, kHarmonicEvidenceCount> settled_energy{};
    double fast_energy_total = 0.0;
    double transient_strength = 0.0;
    const bool posterior_available =
        all_playable_profiles_learned && learned_count > 0U;
    if (posterior_available) {
      double settled_energy_total = 0.0;
      for (std::size_t harmonic = 0U; harmonic < fast_energy.size();
           ++harmonic) {
        fast_energy[harmonic] =
            corrected_harmonic_energy(candidate, harmonic);
        settled_energy[harmonic] =
            0.25 * harmonic_energy_memory_[candidate][harmonic] +
            0.75 * long_harmonic_energy_memory_[candidate][harmonic];
        fast_energy_total += fast_energy[harmonic];
        settled_energy_total += settled_energy[harmonic];
      }
      if (settled_energy_total <= kScoreEpsilon) {
        settled_energy = fast_energy;
      }
      const HarmonicEvidence fast_descriptor =
          make_harmonic_evidence(fast_energy);
      const HarmonicEvidence settled_descriptor =
          make_harmonic_evidence(settled_energy);
      transient_strength =
          harmonic_transient_strength(fast_descriptor, settled_descriptor);
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if (!has_learned_profile[string]) {
          continue;
        }
        std::array<double, kHarmonicEvidenceCount> learned_energy{};
        for (std::size_t harmonic = 0U; harmonic < learned_energy.size();
             ++harmonic) {
          learned_energy[harmonic] = static_cast<double>(
              learned_points[string]->harmonic_profile_q15[harmonic]);
        }
        const HarmonicEvidence learned_descriptor =
            make_harmonic_evidence(learned_energy);
        const HarmonicEvidenceComparison fast_comparison =
            compare_harmonic_evidence(fast_descriptor, learned_descriptor);
        const HarmonicEvidenceComparison settled_comparison =
            compare_harmonic_evidence(settled_descriptor,
                                      learned_descriptor);
        // During a changing attack/decay envelope, retain part of the settled
        // observation instead of letting one upper-partial frame erase every
        // alternative. Once the envelope settles, the current lower/upper
        // evidence carries the full emission weight.
        descriptor_log_likelihoods[string] =
            (1.0 - transient_strength) *
                fast_comparison.combined_log_likelihood() +
            transient_strength *
                settled_comparison.combined_log_likelihood();
        descriptor_sum += descriptor_log_likelihoods[string];
      }
      const PartialDetuningEvidence observed_detuning =
          partial_detuning_trackers_[candidate].evidence();
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if (!has_learned_profile[string]) {
          continue;
        }
        std::array<double, kPartialDetuningCount> reference{};
        for (std::size_t partial = 0U; partial < reference.size(); ++partial) {
          reference[partial] = static_cast<double>(
                                   learned_points[string]
                                       ->partial_detuning_q8[partial]) /
                               256.0;
        }
        const PartialDetuningComparison comparison =
            compare_partial_detuning(
                observed_detuning, reference,
                learned_points[string]->partial_detuning_valid_mask);
        if (comparison.valid) {
          detuning_log_likelihoods[string] = comparison.log_likelihood;
          has_detuning_likelihood[string] = true;
          detuning_sum += comparison.log_likelihood;
          ++detuning_count;
          if (comparison.log_likelihood > best_detuning_log_likelihood) {
            best_detuning_log_likelihood = comparison.log_likelihood;
            best_detuning_string = string;
          }
        }
      }
    }
    const double learned_center =
        learned_count > 0U
            ? learned_sum / static_cast<double>(learned_count)
            : 0.0;
    const double descriptor_center =
        learned_count > 0U
            ? descriptor_sum / static_cast<double>(learned_count)
            : 0.0;
    const double detuning_center =
        detuning_count > 0U
            ? detuning_sum / static_cast<double>(detuning_count)
            : 0.0;
    if (calibrated_reassignment_ready && all_playable_profiles_learned) {
      candidate_states_[candidate].calibrated_lane_committed = true;
    }
    const PhaseCentsState& phase = phase_cents_states_[candidate];
    const double assignment_cents =
        calibration_tuning_evidence_ != 0U
            ? phase.cents - calibration_tuning_offset_cents_
            : phase.cents;
    double best_learned_cents_error =
        std::numeric_limits<double>::infinity();
    double second_learned_cents_error =
        std::numeric_limits<double>::infinity();
    std::size_t best_learned_cents_string = kMaxVoices;
    if (all_playable_profiles_learned && phase.valid) {
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if (!has_learned_profile[string]) {
          continue;
        }
        learned_cents_errors[string] =
            std::abs(assignment_cents - learned_cents[string]);
        if (learned_cents_errors[string] < best_learned_cents_error) {
          second_learned_cents_error = best_learned_cents_error;
          best_learned_cents_error = learned_cents_errors[string];
          best_learned_cents_string = string;
        } else if (learned_cents_errors[string] <
                   second_learned_cents_error) {
          second_learned_cents_error = learned_cents_errors[string];
        }
      }
    }
    const bool calibrated_cents_are_decisive =
        calibrated_reassignment_ready &&
        std::isfinite(second_learned_cents_error) &&
        second_learned_cents_error - best_learned_cents_error >=
            kM3CalibratedCentsMinimumAdvantage;
    bool distinctive_cents_override = false;
    const std::size_t retained_string =
        candidate_states_[candidate].assigned_string;
    if (calibrated_reassignment_ready &&
        best_learned_cents_string < kMaxVoices &&
        retained_string < kMaxVoices &&
        best_learned_cents_string != retained_string &&
        learned_points[best_learned_cents_string] != nullptr &&
        learned_points[retained_string] != nullptr) {
      double profile_distance = 0.0;
      for (std::size_t harmonic = 0U;
           harmonic < kCalibrationHarmonicCount; ++harmonic) {
        const double best_value = static_cast<double>(
            learned_points[best_learned_cents_string]
                ->harmonic_profile_q15[harmonic]) /
            32767.0;
        const double retained_value = static_cast<double>(
            learned_points[retained_string]->harmonic_profile_q15[harmonic]) /
            32767.0;
        const double difference = best_value - retained_value;
        profile_distance += difference * difference;
      }
      distinctive_cents_override =
          profile_distance >= kM3DistinctiveCalibrationProfileDistance;
    }
    if (posterior_available) {
      StringFretLikelihoodFrame posterior_frame;
      posterior_frame.playable_mask = playable;
      const double previous_energy = string_fret_energy_memory_[candidate];
      const double energy_rise =
          previous_energy > kScoreEpsilon
              ? std::clamp((fast_energy_total - previous_energy) /
                               previous_energy,
                           0.0, 1.0)
              : 1.0;
      posterior_frame.onset_strength =
          candidate_states_[candidate].active
              ? energy_rise * (0.5 + 0.5 * transient_strength)
              : 1.0;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
        if ((playable & bit) == 0U || !has_learned_profile[string]) {
          continue;
        }
        posterior_frame.log_likelihood[string] =
            kM3StringPosteriorProfileWeight *
                (learned_similarities[string] - learned_center) +
            kM3StringPosteriorDescriptorWeight *
                (descriptor_log_likelihoods[string] - descriptor_center);
        if (has_detuning_likelihood[string]) {
          posterior_frame.log_likelihood[string] +=
              kM3StringPosteriorDetuningWeight *
              (detuning_log_likelihoods[string] - detuning_center);
        }
        if (phase.valid) {
          const double normalized_error =
              learned_cents_errors[string] / kM3StringPosteriorCentsScale;
          posterior_frame.log_likelihood[string] -=
              0.5 * std::min(32.0, normalized_error * normalized_error);
        }
      }
      static_cast<void>(
          string_fret_posteriors_.update(candidate, posterior_frame));
      string_fret_energy_memory_[candidate] = fast_energy_total;
    } else {
      string_fret_posteriors_.reset(candidate);
      string_fret_energy_memory_[candidate] = 0.0;
    }
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
        const FineFrequencyEvidenceState& fine =
            fine_frequency_evidence_states_[candidate];
        const bool fine_has_multiple_members =
            fine.member_mask != 0U &&
            (fine.member_mask &
             static_cast<std::uint8_t>(fine.member_mask - 1U)) != 0U;
        const bool physical_unison_resolved =
            fine.valid && fine.multi_source_observed &&
            fine_has_multiple_members;
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
        // The convex fret-shape term is an uncalibrated ambiguity fallback.
        // Once every playable lane has a measured point for this pitch, its
        // physical cents/timbre fingerprint is the stronger identity signal;
        // retaining the quadratic prior would force high frets onto a thinner
        // string even when the complete calibration says otherwise.
        const double fret_shape_penalty =
            all_playable_profiles_learned ? 0.0
                                          : kM3AssignmentFretShapePenalty;
        const double fret_position_prior =
            all_playable_profiles_learned && calibrated_reassignment_ready
                ? kM3FretPenalty * fret_position
                : fret_position;
        proposal.cost += fret_position_prior +
                         fret_shape_penalty * stiffness_prior *
                             fret_position * fret_position;
        const bool posterior_assignment_ready =
            calibrated_reassignment_ready &&
            !beat_evidence_states_[candidate].valid;
        if (posterior_available && posterior_assignment_ready &&
            !calibrated_cents_are_decisive && !physical_unison_resolved) {
          const std::size_t posterior_best =
              string_fret_posteriors_.best_string(candidate);
          const double posterior_best_probability =
              posterior_best < kMaxVoices
                  ? string_fret_posteriors_.probability(candidate,
                                                        posterior_best)
                  : 0.0;
          const double posterior_cost =
              posterior_best_probability >=
                      kM3StringPosteriorDecisiveProbability &&
                      posterior_best == best_detuning_string
                  ? kM3StringPosteriorDecisiveCost
                  : kM3StringPosteriorCost;
          proposal.cost +=
              posterior_cost *
              string_fret_posteriors_.negative_log_probability(candidate,
                                                                string);
        }
        if (has_learned_profile[string] &&
            (all_playable_profiles_learned ||
             calibrated_reassignment_ready)) {
          // Calibration is comparative evidence, not an absolute prior. It
          // may identify a fresh lane only when every playable alternative
          // at this pitch has a measured point. Partial calibration remains
          // available solely behind the stable isolated-note reassignment
          // gate; it must not destabilize fresh notes or chords.
          proposal.cost -=
              (all_playable_profiles_learned
                   ? kM3CalibrationProfileBonus
                   : kM3PartialCalibrationProfileBonus) *
              (learned_similarities[string] - learned_center);
        }
        const bool contradicted_by_calibrated_cents =
            calibrated_reassignment_ready && all_playable_profiles_learned &&
            phase.valid &&
            learned_cents_errors[string] - best_learned_cents_error >=
                kM3CalibratedCentsMinimumAdvantage;
        // With a complete bank, an open lane must earn its prior from a
        // competitive calibrated fingerprint before capturing a note; an
        // unconditional bonus routed fretted plucks (string 8 fret 4 onto the
        // open C2 lane) for entire holds. An open lane already retained by
        // the active note keeps the prior so a flickering fast-correlator
        // similarity cannot toggle it within the hold.
        const bool retained_open_lane =
            candidate_states_[candidate].active &&
            candidate_states_[candidate].assigned_string == string;
        if (all_playable_profiles_learned && fret == 0U &&
            ((!calibrated_reassignment_ready && retained_open_lane) ||
             (best_learned_similarity - learned_similarities[string] <
                  kM3CalibratedCandidateMinimumAdvantage &&
              !contradicted_by_calibrated_cents))) {
          proposal.cost -= kM3OpenStringAssignmentBonus;
        }
        if (has_learned_profile[string] && all_playable_profiles_learned) {
          // A fully covered physical bank also provides comparable intonation
          // offsets. Partial coverage must not use this term because an
          // unmeasured lane has no honest cents value to compare.
          if (phase.valid) {
            const double cents_penalty =
                distinctive_cents_override
                    ? kM3DistinctiveCalibrationCentsPenalty
                    : kM3CalibrationCentsPenalty;
            proposal.cost +=
                cents_penalty *
                std::abs(assignment_cents - learned_cents[string]);
          }
        }
        if (fine.valid && fine.multi_source_observed &&
            fine_has_multiple_members &&
            (fine.member_mask & bit) != 0U) {
          // Once the calibrated beat-time fit has resolved multiple physical
          // lanes, keep the instantaneous spectral assignment inside that
          // measured member set. A single-source fit is deliberately not an
          // identity oracle: neighbouring string templates can be closer in
          // cents than the string that actually started the note.
          proposal.cost -= 512.0;
        }
        if (candidate_states_[candidate].active &&
            candidate_states_[candidate].assigned_string == string) {
          const bool contradicted_by_fine_evidence =
              fine.valid && fine.multi_source_observed &&
              fine_has_multiple_members &&
              (fine.member_mask & bit) == 0U;
          const bool contradicted_by_calibrated_profile =
              calibrated_reassignment_ready &&
              all_playable_profiles_learned &&
              has_learned_profile[string] &&
              best_learned_similarity - learned_similarities[string] >=
                  kM3CalibratedCandidateMinimumAdvantage;
          const bool settled_tuner_lane =
              candidate_states_[candidate].active &&
              candidate_states_[candidate].age_ticks >= stable_tuner_ticks &&
              !contradicted_by_fine_evidence &&
              !contradicted_by_calibrated_profile &&
              !contradicted_by_calibrated_cents;
          // Let every newly active note correct a provisional assignment
          // while its calibrated fingerprint and beat evidence settle. The
          // old per-voice shortcut made the first generic lowest-fret guess
          // permanent before physical-string evidence was available.
          proposal.cost -= settled_tuner_lane
                               ? kM3ActiveStringRetentionBonus
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

void PolyphonicPitchDetector::update_harmonic_profile_memory(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double mix = 1.0 - harmonic_memory_decay;
  const double long_mix = 1.0 - long_harmonic_memory_decay;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (!selected[candidate]) {
      if (!candidate_states_[candidate].active) {
        for (double& energy : harmonic_energy_memory_[candidate]) {
          energy *= harmonic_memory_decay;
        }
        for (double& energy : long_harmonic_energy_memory_[candidate]) {
          energy *= long_harmonic_memory_decay;
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
      long_harmonic_energy_memory_[candidate][harmonic] =
          long_harmonic_memory_decay *
              long_harmonic_energy_memory_[candidate][harmonic] +
          long_mix * instantaneous;
    }
    if (harmonic_memory_updates_[candidate] <
        std::numeric_limits<std::uint16_t>::max()) {
      ++harmonic_memory_updates_[candidate];
    }
  }
}

void PolyphonicPitchDetector::update_beat_evidence(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double decisions_per_second =
      sample_rate_ / static_cast<double>(kDecisionQuantum);
  const double mean_mix =
      1.0 - std::exp(-1.0 / (kBeatEnvelopeMeanSeconds *
                            decisions_per_second));
  const double deviation_mix =
      1.0 - std::exp(-1.0 / (kBeatDeviationSeconds *
                            decisions_per_second));
  const std::uint32_t minimum_period = static_cast<std::uint32_t>(
      std::max(1.0, std::floor(decisions_per_second / kMaximumBeatHz)));
  const std::uint32_t maximum_period = static_cast<std::uint32_t>(
      std::ceil(decisions_per_second / kMinimumBeatHz));

  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    BeatEvidenceState& state = beat_evidence_states_[candidate];
    if (!selected[candidate]) {
      // Bridge selector flicker only for an established pitch cell. An
      // adjacent semitone whose phase estimate falls outside its own cell may
      // coast for MIDI release, but must not accumulate a competing calibrated
      // fine-frequency identity during that coast.
      if (!candidate_states_[candidate].active ||
          !phase_cents_states_[candidate].valid) {
        state = {};
        continue;
      }
    }
    const Cell& fundamental = cells_[cell_index(candidate, 0U)];
    if (!fundamental.enabled) {
      state = {};
      continue;
    }
    const double energy = fundamental.fast_real * fundamental.fast_real +
                          fundamental.fast_imaginary *
                              fundamental.fast_imaginary;
    if (!std::isfinite(energy)) {
      state = {};
      continue;
    }
    if (!state.initialized) {
      state.envelope_mean = energy;
      state.initialized = true;
      continue;
    }

    if (state.decisions_since_crossing <
        std::numeric_limits<std::uint32_t>::max()) {
      ++state.decisions_since_crossing;
    }
    state.envelope_mean += mean_mix * (energy - state.envelope_mean);
    const double centered = energy - state.envelope_mean;
    state.absolute_deviation +=
        deviation_mix *
        (std::abs(centered) - state.absolute_deviation);
    const double gate = std::max(
        kScoreEpsilon,
        std::max(0.015 * std::max(state.envelope_mean, 0.0),
                 0.20 * state.absolute_deviation));
    if (centered < -gate) {
      state.below_gate = true;
    } else if (state.below_gate && centered > gate) {
      const std::uint32_t period = state.decisions_since_crossing;
      state.decisions_since_crossing = 0U;
      state.below_gate = false;
      if (period >= minimum_period && period <= maximum_period) {
        const double measured = decisions_per_second /
                                static_cast<double>(period);
        if (state.accepted_cycles == 0U) {
          state.beat_hz = measured;
        } else {
          state.beat_hz += 0.25 * (measured - state.beat_hz);
        }
        if (state.accepted_cycles <
            std::numeric_limits<std::uint16_t>::max()) {
          ++state.accepted_cycles;
        }
      } else {
        state.accepted_cycles = 0U;
        state.valid = false;
      }
    }
    if (state.decisions_since_crossing > maximum_period) {
      state.accepted_cycles = 0U;
      state.valid = false;
      state.decisions_since_crossing = maximum_period;
    }
    const double modulation_ratio =
        state.absolute_deviation /
        std::max(state.envelope_mean, kScoreEpsilon);
    state.valid = state.accepted_cycles >= 2U &&
                  modulation_ratio >= kMinimumBeatModulationRatio &&
                  state.beat_hz >= kMinimumBeatHz &&
                  state.beat_hz <= kMaximumBeatHz;
  }
}

void PolyphonicPitchDetector::update_fine_frequency_evidence(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3 ||
      fine_frequency_decimation_decisions_ == 0U ||
      decision_counter_ % fine_frequency_decimation_decisions_ != 0U) {
    return;
  }

  using Complex = std::complex<double>;
  const double seconds_per_decision =
      static_cast<double>(kDecisionQuantum) / sample_rate_;
  const std::uint32_t maximum_gap = static_cast<std::uint32_t>(
      std::max(1.0, std::ceil(kFineFrequencyMaximumGapSeconds /
                             seconds_per_decision)));
  const std::uint16_t minimum_samples = static_cast<std::uint16_t>(
      std::clamp(
          std::ceil(kFineFrequencyMinimumEvidenceSeconds * sample_rate_ /
                    (static_cast<double>(kDecisionQuantum) *
                     fine_frequency_decimation_decisions_)),
          2.0,
          static_cast<double>(kFineFrequencyHistoryCapacity)));

  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    FineFrequencyEvidenceState& state =
        fine_frequency_evidence_states_[candidate];
    if (!selected[candidate]) {
      if (decision_counter_ - state.last_decision_tick > maximum_gap) {
        state = {};
      }
      continue;
    }
    const Cell& fundamental = cells_[cell_index(candidate, 0U)];
    if (!fundamental.enabled || !std::isfinite(fundamental.fast_real) ||
        !std::isfinite(fundamental.fast_imaginary)) {
      state = {};
      continue;
    }
    if (state.count != 0U &&
        decision_counter_ - state.last_decision_tick > maximum_gap) {
      // Short selector gaps are represented by the retained decision ticks in
      // the irregular least-squares fit below. A longer gap starts a new
      // causal observation rather than joining unrelated articulations.
      state = {};
    }
    state.real[state.write_index] = fundamental.fast_real;
    state.imaginary[state.write_index] = fundamental.fast_imaginary;
    state.decision_ticks[state.write_index] = decision_counter_;
    state.write_index = static_cast<std::uint16_t>(
        (state.write_index + 1U) % kFineFrequencyHistoryCapacity);
    state.count = static_cast<std::uint16_t>(std::min<std::size_t>(
        static_cast<std::size_t>(state.count) + 1U,
        kFineFrequencyHistoryCapacity));
    state.last_decision_tick = decision_counter_;
    if (state.count < minimum_samples) {
      continue;
    }
    const std::uint32_t observation_index =
        decision_counter_ / fine_frequency_decimation_decisions_;
    if ((observation_index + static_cast<std::uint32_t>(candidate)) %
            kFineFrequencyAnalysisStride !=
        0U) {
      // Collection stays near 100 Hz, while calibrated least-squares analyses
      // are staggered across pitch candidates. This bounds the cost paid by
      // any one small host block without weakening the five-second evidence
      // window or moving work to an unsafe background thread.
      continue;
    }

    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    const double center_frequency =
        midi_to_frequency(static_cast<double>(note), 440.0);
    std::array<std::uint8_t, kMaxVoices> strings{};
    std::array<double, kMaxVoices> offsets{};
    std::array<double, kMaxVoices> cents_offsets{};
    std::size_t component_count = 0U;
    const std::uint8_t playable = playable_string_mask(candidate);
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      if ((playable & bit) == 0U || note < kM3OpenNotes[string]) {
        continue;
      }
      const StringCalibrationPoint* point =
          calibrator_.bank().point(string, note - kM3OpenNotes[string]);
      if (point == nullptr ||
          point->quality == CalibrationPointQuality::missing) {
        continue;
      }
      strings[component_count] = static_cast<std::uint8_t>(string);
      const double cents =
          static_cast<double>(point->cents_offset_q8) / 256.0;
      cents_offsets[component_count] = cents;
      offsets[component_count] =
          center_frequency * std::expm1(std::log(2.0) * cents / 1200.0);
      ++component_count;
    }
    if (component_count == 0U) {
      continue;
    }

    std::array<std::array<Complex, kMaxVoices>, kMaxVoices> gram{};
    std::array<Complex, kMaxVoices> correlations{};
    std::array<Complex, kMaxVoices> basis{};
    double signal_energy = 0.0;
    const std::size_t oldest =
        state.count < kFineFrequencyHistoryCapacity ? 0U : state.write_index;
    const std::uint32_t oldest_tick = state.decision_ticks[oldest];
    const std::size_t second_index =
        (oldest + 1U) % kFineFrequencyHistoryCapacity;
    const std::uint32_t uniform_tick_step =
        state.decision_ticks[second_index] - oldest_tick;
    bool uniformly_sampled = uniform_tick_step != 0U;
    for (std::size_t sample = 2U; sample < state.count && uniformly_sampled;
         ++sample) {
      const std::size_t previous =
          (oldest + sample - 1U) % kFineFrequencyHistoryCapacity;
      const std::size_t index =
          (oldest + sample) % kFineFrequencyHistoryCapacity;
      uniformly_sampled =
          state.decision_ticks[index] - state.decision_ticks[previous] ==
          uniform_tick_step;
    }
    if (uniformly_sampled) {
      std::array<Complex, kMaxVoices> step_basis{};
      for (std::size_t component = 0U; component < component_count;
           ++component) {
        basis[component] = Complex{1.0, 0.0};
        step_basis[component] = std::polar(
            1.0, kTwoPi * offsets[component] *
                     static_cast<double>(uniform_tick_step) *
                     seconds_per_decision);
      }
      for (std::size_t sample = 0U; sample < state.count; ++sample) {
        const std::size_t index =
            (oldest + sample) % kFineFrequencyHistoryCapacity;
        const Complex observation{state.real[index], state.imaginary[index]};
        signal_energy += std::norm(observation);
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          correlations[component] +=
              std::conj(basis[component]) * observation;
          basis[component] *= step_basis[component];
        }
      }
      // The uniform normal matrix is a finite complex geometric series. It
      // depends only on the calibrated frequency differences, sample count,
      // and fixed observation stride, so evaluating it directly avoids the
      // former history-length-times-components-squared callback spike.
      const double count_as_double = static_cast<double>(state.count);
      const double step_seconds =
          static_cast<double>(uniform_tick_step) * seconds_per_decision;
      for (std::size_t row = 0U; row < component_count; ++row) {
        for (std::size_t column = 0U; column < component_count; ++column) {
          const double half_angle =
              0.5 * kTwoPi * (offsets[column] - offsets[row]) * step_seconds;
          const double denominator = std::sin(half_angle);
          if (std::abs(denominator) <= 1.0e-12) {
            gram[row][column] = Complex{count_as_double, 0.0};
            continue;
          }
          const double magnitude =
              std::sin(count_as_double * half_angle) / denominator;
          const double phase = (count_as_double - 1.0) * half_angle;
          gram[row][column] =
              magnitude * Complex{std::cos(phase), std::sin(phase)};
        }
      }
    } else {
      // Selector gaps retain their real decision ticks and use the exact
      // irregular normal matrix. This bounded fallback preserves the existing
      // causal fit without penalizing the steady-state callback path.
      for (std::size_t sample = 0U; sample < state.count; ++sample) {
        const std::size_t index =
            (oldest + sample) % kFineFrequencyHistoryCapacity;
        const Complex observation{state.real[index], state.imaginary[index]};
        signal_energy += std::norm(observation);
        const double elapsed_seconds =
            static_cast<double>(state.decision_ticks[index] - oldest_tick) *
            seconds_per_decision;
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          basis[component] = std::polar(
              1.0, kTwoPi * offsets[component] * elapsed_seconds);
          correlations[component] +=
              std::conj(basis[component]) * observation;
        }
        for (std::size_t row = 0U; row < component_count; ++row) {
          for (std::size_t column = 0U; column < component_count; ++column) {
            gram[row][column] +=
                std::conj(basis[row]) * basis[column];
          }
        }
      }
    }
    const double inverse_count = 1.0 / static_cast<double>(state.count);
    signal_energy *= inverse_count;
    for (std::size_t row = 0U; row < component_count; ++row) {
      for (std::size_t column = 0U; column < component_count; ++column) {
        gram[row][column] *= inverse_count;
      }
    }
    double frequency_mean = 0.0;
    double frequency_square_sum = 0.0;
    std::size_t frequency_samples = 0U;
    const std::size_t phase_start = state.count / 5U;
    const std::size_t phase_candidates =
        state.count > phase_start + 1U ? state.count - phase_start - 1U : 0U;
    const std::size_t phase_stride = std::max<std::size_t>(
        1U, (phase_candidates + kFineFrequencyMaximumPhaseSamples - 1U) /
                kFineFrequencyMaximumPhaseSamples);
    for (std::size_t sample = phase_start + 1U; sample < state.count;
         sample += phase_stride) {
      const std::size_t previous_index =
          (oldest + sample - 1U) % kFineFrequencyHistoryCapacity;
      const std::size_t index =
          (oldest + sample) % kFineFrequencyHistoryCapacity;
      const std::uint32_t tick_delta =
          state.decision_ticks[index] -
          state.decision_ticks[previous_index];
      if (tick_delta == 0U) {
        continue;
      }
      const Complex previous{state.real[previous_index],
                             state.imaginary[previous_index]};
      const Complex current{state.real[index], state.imaginary[index]};
      if (std::norm(previous) <= kScoreEpsilon ||
          std::norm(current) <= kScoreEpsilon) {
        continue;
      }
      const Complex phase_cross = std::conj(previous) * current;
      const double phase_scale =
          std::sqrt(std::norm(previous) * std::norm(current));
      if (phase_scale <= kScoreEpsilon) {
        continue;
      }
      // The cell is accepted only inside +/-50 cents. At the 64-sample
      // decision cadence its largest supported phase step is under 0.13
      // radians even at C6, so sin(theta) is a bounded (<0.3%) approximation
      // of theta. Avoiding hundreds of atan2 calls keeps this evidence pass
      // inside the smallest callback budget without changing its variance
      // classification in the supported pitch range.
      const double phase_sine = std::clamp(
          std::imag(phase_cross) / phase_scale, -1.0, 1.0);
      const double frequency =
          phase_sine /
          (kTwoPi * static_cast<double>(tick_delta) *
           seconds_per_decision);
      if (!std::isfinite(frequency)) {
        continue;
      }
      frequency_mean += frequency;
      frequency_square_sum += frequency * frequency;
      ++frequency_samples;
    }
    if (frequency_samples > 1U) {
      frequency_mean /= static_cast<double>(frequency_samples);
      const double variance = std::max(
          0.0, frequency_square_sum /
                       static_cast<double>(frequency_samples) -
                   frequency_mean * frequency_mean);
      state.frequency_deviation_hz = std::sqrt(variance);
    }
    for (std::size_t row = 0U; row < component_count; ++row) {
      correlations[row] *= inverse_count;
      gram[row][row] += kFineFrequencyRidge;
    }

    std::array<Complex, kMaxVoices> solution = correlations;
    bool solvable = true;
    for (std::size_t column = 0U; column < component_count; ++column) {
      std::size_t pivot = column;
      for (std::size_t row = column + 1U; row < component_count; ++row) {
        if (std::abs(gram[row][column]) >
            std::abs(gram[pivot][column])) {
          pivot = row;
        }
      }
      if (std::abs(gram[pivot][column]) <= 1.0e-10) {
        solvable = false;
        break;
      }
      if (pivot != column) {
        std::swap(gram[pivot], gram[column]);
        std::swap(solution[pivot], solution[column]);
      }
      const Complex divisor = gram[column][column];
      for (std::size_t entry = column; entry < component_count; ++entry) {
        gram[column][entry] /= divisor;
      }
      solution[column] /= divisor;
      for (std::size_t row = 0U; row < component_count; ++row) {
        if (row == column) {
          continue;
        }
        const Complex factor = gram[row][column];
        for (std::size_t entry = column; entry < component_count; ++entry) {
          gram[row][entry] -= factor * gram[column][entry];
        }
        solution[row] -= factor * solution[column];
      }
    }
    if (!solvable || signal_energy <= kScoreEpsilon) {
      continue;
    }

    Complex fitted_cross{};
    double solution_norm = 0.0;
    for (std::size_t row = 0U; row < component_count; ++row) {
      fitted_cross += std::conj(solution[row]) * correlations[row];
      solution_norm += std::norm(solution[row]);
    }
    // The solution satisfies (X^H X + ridge I)a = X^H y.  Recover the
    // unregularized residual from that normal equation; gram has already been
    // reduced in place by the bounded solver above.
    const double fitted_error = std::max(
        0.0, signal_energy - std::real(fitted_cross) -
                 kFineFrequencyRidge * solution_norm);
    double best_single_error = signal_energy;
    double maximum_amplitude = 0.0;
    for (std::size_t component = 0U; component < component_count;
         ++component) {
      best_single_error = std::min(
          best_single_error,
          std::max(0.0, signal_energy - std::norm(correlations[component])));
      maximum_amplitude =
          std::max(maximum_amplitude, std::abs(solution[component]));
    }
    if (maximum_amplitude <= kScoreEpsilon) {
      continue;
    }

    std::array<double, kHarmonicCount> observed_profile{};
    double observed_profile_total = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
      observed_profile[harmonic] =
          0.25 * harmonic_energy_memory_[candidate][harmonic] +
          0.75 * long_harmonic_energy_memory_[candidate][harmonic];
      observed_profile_total += observed_profile[harmonic];
    }
    double best_single_profile_error =
        std::numeric_limits<double>::infinity();
    if (observed_profile_total > kScoreEpsilon) {
      for (double& value : observed_profile) {
        value /= observed_profile_total;
      }
      for (std::size_t component = 0U; component < component_count;
           ++component) {
        const StringCalibrationPoint* point = calibrator_.bank().point(
            strings[component], note - kM3OpenNotes[strings[component]]);
        if (point == nullptr) {
          continue;
        }
        double template_total = 0.0;
        for (const std::uint16_t value : point->harmonic_profile_q15) {
          template_total += static_cast<double>(value);
        }
        if (template_total <= kScoreEpsilon) {
          continue;
        }
        double error = 0.0;
        for (std::size_t harmonic = 0U; harmonic < kHarmonicCount;
             ++harmonic) {
          const double expected =
              static_cast<double>(point->harmonic_profile_q15[harmonic]) /
              template_total;
          const double difference = observed_profile[harmonic] - expected;
          error += difference * difference;
        }
        best_single_profile_error =
            std::min(best_single_profile_error, error);
      }
    }
    const bool single_profile_rejected =
        std::isfinite(best_single_profile_error) &&
        best_single_profile_error >=
            kFineFrequencySingleProfileRejectionError;
    const double minimum_relative_amplitude =
        single_profile_rejected
            ? kFineFrequencyMinimumRelativeAmplitude
            : kFineFrequencyProfileMatchedRelativeAmplitude;
    const bool beat_modulation_observed =
        beat_evidence_states_[candidate].valid;
    const bool phase_modulation_observed =
        state.frequency_deviation_hz >=
        kFineFrequencyMinimumPhaseDeviationHz;
    constexpr std::size_t kMaximumSimultaneousUnisonMembers = 4U;
    std::array<std::size_t, kMaxVoices> order{};
    for (std::size_t component = 0U; component < component_count;
         ++component) {
      order[component] = component;
    }
    for (std::size_t rank = 0U; rank < component_count; ++rank) {
      std::size_t strongest = rank;
      for (std::size_t probe = rank + 1U; probe < component_count; ++probe) {
        if (std::abs(solution[order[probe]]) >
            std::abs(solution[order[strongest]])) {
          strongest = probe;
        }
      }
      std::swap(order[rank], order[strongest]);
    }
    std::uint8_t members = 0U;
    std::size_t member_count = 0U;
    double minimum_member_relative_amplitude = 1.0;
    state.component_energy = {};
    for (std::size_t rank = 0U; rank < component_count &&
                               member_count <
                                   kMaximumSimultaneousUnisonMembers;
         ++rank) {
      const std::size_t component = order[rank];
      const double amplitude = std::abs(solution[component]);
      state.component_energy[strings[component]] = amplitude * amplitude;
      if (amplitude < maximum_amplitude * minimum_relative_amplitude) {
        continue;
      }
      members = static_cast<std::uint8_t>(
          members | (1U << strings[component]));
      minimum_member_relative_amplitude = std::min(
          minimum_member_relative_amplitude,
          amplitude / maximum_amplitude);
      ++member_count;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.fit_member_mask = members;
    state.disposition = member_count > 1U
                            ? FineFrequencyDisposition::multi_source_candidate
                            : FineFrequencyDisposition::amplitude_single;
#endif
    double minimum_member_separation_hz =
        std::numeric_limits<double>::infinity();
    for (std::size_t first = 0U; first < component_count; ++first) {
      if ((members & (1U << strings[first])) == 0U) {
        continue;
      }
      for (std::size_t second = first + 1U; second < component_count;
           ++second) {
        if ((members & (1U << strings[second])) == 0U) {
          continue;
        }
        minimum_member_separation_hz = std::min(
            minimum_member_separation_hz,
            std::abs(offsets[first] - offsets[second]));
      }
    }
    const bool distinctly_separated_sources =
        member_count > 1U &&
        minimum_member_separation_hz >=
            kFineFrequencyDistinctSourceSeparationHz;
    const bool independently_separated_sources =
        member_count > 1U &&
        minimum_member_separation_hz >=
            kM3ProfileOnlyUnisonMinimumSeparationHz &&
        minimum_member_relative_amplitude >=
            kFineFrequencyProfileMatchedRelativeAmplitude;
    // A changing harmonic envelope or instantaneous phase can reject every
    // stored single-string profile even when only one physical string is
    // ringing.  It may lower the component-amplitude floor above, but it is
    // not independent evidence for extra strings.  A new multi-string group
    // must also contain separately calibrated frequencies at the measured
    // safe spacing; otherwise one drifting source can be represented by
    // several nearly coincident templates.
    state.multi_source_observed = distinctly_separated_sources &&
                                  (independently_separated_sources ||
                                   beat_modulation_observed ||
                                   (single_profile_rejected &&
                                    phase_modulation_observed &&
                                    minimum_member_separation_hz >=
                                        kFineFrequencyPhaseSupportedSeparationHz));
    if (!state.multi_source_observed) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (member_count > 1U) {
        state.disposition =
            FineFrequencyDisposition::source_evidence_rejected;
      }
#endif
      std::size_t single_component = order[0U];
      const PhaseCentsState& cents = phase_cents_states_[candidate];
      if (cents.valid) {
        double closest = std::numeric_limits<double>::infinity();
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          const double distance =
              std::abs(cents.cents - cents_offsets[component]);
          if (distance < closest) {
            closest = distance;
            single_component = component;
          }
        }
      }
      members = static_cast<std::uint8_t>(1U << strings[single_component]);
    } else if (member_count > 1U) {
      const double improvement =
          (best_single_error - fitted_error) /
          std::max(best_single_error, kScoreEpsilon);
      if (!std::isfinite(improvement) ||
          improvement < kFineFrequencyMinimumResidualImprovement) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        state.disposition = FineFrequencyDisposition::residual_rejected;
#endif
        members = static_cast<std::uint8_t>(1U << strings[order[0U]]);
      }
    }
    if (members == state.pending_member_mask) {
      if (state.pending_count < std::numeric_limits<std::uint16_t>::max()) {
        ++state.pending_count;
      }
    } else {
      state.pending_member_mask = members;
      state.pending_count = 1U;
    }
    std::size_t current_member_count = 0U;
    std::size_t proposed_member_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      current_member_count +=
          (state.member_mask & (1U << string)) != 0U ? 1U : 0U;
      proposed_member_count +=
          (members & (1U << string)) != 0U ? 1U : 0U;
    }
    const bool first_resolved_multi =
        current_member_count <= 1U && proposed_member_count > 1U;
    const double consensus_seconds =
        state.member_mask == 0U || first_resolved_multi
            ? kFineFrequencyInitialConsensusSeconds
            : kFineFrequencyReplacementConsensusSeconds;
    const std::uint16_t consensus_samples = static_cast<std::uint16_t>(
        std::clamp(
            std::ceil(consensus_seconds * sample_rate_ /
                      (static_cast<double>(kDecisionQuantum) *
                       fine_frequency_decimation_decisions_ *
                       kFineFrequencyAnalysisStride)),
            1.0,
            static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
    if (members != 0U && state.pending_count >= consensus_samples) {
      state.member_mask = members;
    }
    state.valid = state.member_mask != 0U;
  }
}

std::uint16_t PolyphonicPitchDetector::unison_dropout_decisions(
    std::size_t candidate) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return unison_dropout_decisions_;
  }
  const BeatEvidenceState& beat = beat_evidence_states_[candidate];
  if (!beat.valid || beat.beat_hz < kMinimumBeatHz ||
      beat.beat_hz > kMaximumBeatHz) {
    return unison_dropout_decisions_;
  }
  const double hold_seconds = std::clamp(
      kBeatCyclesToHold / beat.beat_hz, kMinimumBeatAwareHoldSeconds,
      kMaximumBeatAwareHoldSeconds);
  const double decisions = std::ceil(
      hold_seconds * sample_rate_ / static_cast<double>(kDecisionQuantum));
  const std::uint16_t beat_hold = static_cast<std::uint16_t>(std::clamp(
      decisions, 1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  return std::max(unison_dropout_decisions_, beat_hold);
}

double PolyphonicPitchDetector::corrected_harmonic_energy(
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

void PolyphonicPitchDetector::update_phase_cents_estimates(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double decisions_per_second =
      sample_rate_ / static_cast<double>(kDecisionQuantum);
  const double phasor_mix =
      1.0 - std::exp(-1.0 / (0.015 * decisions_per_second));
  const double cents_mix =
      1.0 - std::exp(-1.0 / (0.010 * decisions_per_second));
  const std::uint16_t required_updates = static_cast<std::uint16_t>(
      std::clamp(std::ceil(kPhaseCentsEvidenceSeconds * decisions_per_second),
                 1.0,
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

void PolyphonicPitchDetector::update_partial_detuning_evidence(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  const double decisions_per_second =
      sample_rate_ / static_cast<double>(kDecisionQuantum);
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  if (count == 0U) {
    return;
  }
  std::size_t calibration_candidate = count;
  if (calibrator_.active()) {
    const CalibrationSweepStatus status = calibrator_.status();
    const std::uint16_t note = static_cast<std::uint16_t>(
        kM3OpenNotes[status.string_index] + status.requested_fret);
    if (note >= lowest_note_) {
      const std::size_t candidate = note - lowest_note_;
      if (candidate < count) {
        calibration_candidate = candidate;
      }
    }
  }
  const auto eligible = [this, &selected,
                         calibration_candidate](std::size_t candidate) {
    return selected[candidate] || candidate_states_[candidate].active ||
           candidate == calibration_candidate;
  };
  for (std::size_t candidate = 0U;
       candidate < count; ++candidate) {
    if (!eligible(candidate)) {
      partial_detuning_trackers_[candidate].reset();
      partial_detuning_last_update_ticks_[candidate] = 0U;
    }
  }
  // Expensive phase/log work is round-robined across active candidates. This
  // preserves a bounded callback spike while each candidate retains the exact
  // elapsed decision interval needed to recover its phase-advance rate.
  for (std::size_t probe = 0U; probe < count; ++probe) {
    const std::size_t candidate = (partial_detuning_cursor_ + probe) % count;
    if (!eligible(candidate)) {
      continue;
    }
    PartialDetuningTracker& tracker = partial_detuning_trackers_[candidate];
    PartialDetuningFrame frame{};
    for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
      const Cell& cell = cells_[cell_index(candidate, harmonic)];
      frame.real[harmonic] = cell.fast_real;
      frame.imaginary[harmonic] = cell.fast_imaginary;
      frame.center_hz[harmonic] =
          std::atan2(cell.sine_step, cell.cosine_step) * sample_rate_ / kTwoPi;
      frame.energy[harmonic] =
          cell.enabled ? cell.fast_real * cell.fast_real +
                             cell.fast_imaginary * cell.fast_imaginary
                       : 0.0;
    }
    const std::uint32_t previous_tick =
        partial_detuning_last_update_ticks_[candidate];
    const std::uint32_t elapsed_ticks =
        previous_tick == 0U ? 1U : decision_counter_ - previous_tick;
    tracker.update(frame,
                   decisions_per_second / static_cast<double>(elapsed_ticks));
    partial_detuning_last_update_ticks_[candidate] = decision_counter_;
    partial_detuning_cursor_ = (candidate + 1U) % count;
    break;
  }
}

void PolyphonicPitchDetector::infer_m3_unison_strings(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }

  std::size_t selected_count = 0U;
  std::uint8_t committed_selected_strings = 0U;
  std::array<std::uint8_t, kMaxVoices> committed_owner_counts{};
  // A coasting voice (active, unselected during its release hold) still owns
  // its string lanes, tuner slots, and per-voice MIDI identities until
  // note-off. An inferred unison lane must neither reuse one of those lanes
  // nor displace that voice from the bounded polyphony budget.
  std::uint8_t coasting_strings = 0U;
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    const CandidateState& candidate_state = candidate_states_[candidate];
    if (!selected[candidate]) {
      if (candidate_state.active) {
        std::uint8_t owned = static_cast<std::uint8_t>(
            candidate_state.assigned_string_mask |
            candidate_state.midi_voice_mask);
        if (owned == 0U &&
            candidate_state.assigned_string < kM3OpenNotes.size()) {
          owned = static_cast<std::uint8_t>(
              1U << candidate_state.assigned_string);
        }
        coasting_strings =
            static_cast<std::uint8_t>(coasting_strings | owned);
      }
      continue;
    }
    ++selected_count;
    const std::uint8_t primary = candidate_state.assigned_string;
    if (primary < kM3OpenNotes.size()) {
      const std::uint8_t primary_bit =
          static_cast<std::uint8_t>(1U << primary);
      const std::uint8_t committed =
          candidate_state.assigned_string_mask != 0U
              ? candidate_state.assigned_string_mask
              : primary_bit;
      committed_selected_strings = static_cast<std::uint8_t>(
          committed_selected_strings | committed);
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if ((committed & (1U << string)) != 0U &&
            committed_owner_counts[string] <
                std::numeric_limits<std::uint8_t>::max()) {
          ++committed_owner_counts[string];
        }
      }
    }
  }
  std::size_t occupied_lanes = 0U;
  const std::uint8_t committed_strings = static_cast<std::uint8_t>(
      committed_selected_strings | coasting_strings);
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    occupied_lanes +=
        (committed_strings & (1U << string)) != 0U ? 1U : 0U;
  }
  occupied_lanes = std::max(occupied_lanes, selected_count);
  std::size_t remaining_extra =
      max_polyphony_ > occupied_lanes ? max_polyphony_ - occupied_lanes : 0U;
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
    const std::uint8_t note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
    const std::uint8_t primary_bit =
        static_cast<std::uint8_t>(1U << primary);
    if (state.assigned_string_mask == 0U ||
        (state.assigned_string_mask & primary_bit) == 0U) {
      state.assigned_string_mask = primary_bit;
      state.unison_evidence_ticks = 0U;
      state.unison_gap_ticks = 0U;
      state.pending_unison_mask = 0U;
    }
    const std::uint8_t committed_for_candidate =
        state.assigned_string_mask != 0U ? state.assigned_string_mask
                                         : primary_bit;
    const std::uint8_t committed_extra_for_candidate =
        static_cast<std::uint8_t>(committed_for_candidate & ~primary_bit);
    std::size_t committed_extra_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      committed_extra_count +=
          (committed_extra_for_candidate & (1U << string)) != 0U ? 1U : 0U;
    }
    const std::size_t candidate_extra_capacity =
        std::min<std::size_t>(3U,
                              remaining_extra + committed_extra_count);
    std::uint8_t other_owned_strings = coasting_strings;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
      const std::uint8_t own_count =
          (committed_for_candidate & bit) != 0U ? 1U : 0U;
      if (committed_owner_counts[string] > own_count) {
        other_owned_strings =
            static_cast<std::uint8_t>(other_owned_strings | bit);
      }
    }

    std::uint8_t proposed_group = primary_bit;
    bool temporal_group_selected = false;
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    if (fine.valid) {
      const std::uint8_t temporal_group = static_cast<std::uint8_t>(
          fine.member_mask & playable_string_mask(candidate) &
          ~other_owned_strings & ~allocated_extra_strings);
      std::size_t temporal_count = 0U;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        temporal_count +=
            (temporal_group & (1U << string)) != 0U ? 1U : 0U;
      }
      if ((temporal_group & primary_bit) != 0U && temporal_count >= 2U &&
          temporal_count <= 4U &&
          temporal_count - 1U <= candidate_extra_capacity) {
        proposed_group = temporal_group;
        temporal_group_selected = true;
      }
    }
    if (!temporal_group_selected && state.age_ticks >= profile_ready_ticks &&
        candidate_extra_capacity > 0U) {
      const std::uint16_t long_profile_ready_ticks =
          static_cast<std::uint16_t>(std::clamp(
              std::ceil(kLongHarmonicProfileReadySeconds * sample_rate_ /
                        static_cast<double>(kDecisionQuantum)),
              1.0,
              static_cast<double>(
                  std::numeric_limits<std::uint16_t>::max())));
      const bool use_long_profile =
          harmonic_memory_updates_[candidate] >= long_profile_ready_ticks;
      std::array<double, kHarmonicCount> profile_energy{};
      double observed_total = 0.0;
      for (std::size_t harmonic = 0U; harmonic < profile_energy.size();
           ++harmonic) {
        profile_energy[harmonic] =
            use_long_profile
                ? 0.25 * harmonic_energy_memory_[candidate][harmonic] +
                      0.75 *
                          long_harmonic_energy_memory_[candidate][harmonic]
                : harmonic_energy_memory_[candidate][harmonic];
        const double energy = profile_energy[harmonic];
        observed_total += energy;
      }
      std::array<double, kHarmonicCount> observed{};
      if (observed_total > kScoreEpsilon) {
        for (std::size_t harmonic = 0U; harmonic < observed.size(); ++harmonic) {
          observed[harmonic] = profile_energy[harmonic] / observed_total;
        }

        std::array<std::array<double, kHarmonicCount>, kM3OpenNotes.size()>
            templates{};
        std::array<bool, kM3OpenNotes.size()> template_valid{};
        const std::uint8_t playable = playable_string_mask(candidate);
        for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          template_valid[string] =
              (playable & bit) != 0U &&
              load_template(candidate, string, templates[string]);
        }
        if (template_valid[primary]) {
          double best_single_error =
              std::numeric_limits<double>::infinity();
          for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
            if (!template_valid[string]) {
              continue;
            }
            double error = 0.0;
            for (std::size_t harmonic = 0U; harmonic < observed.size();
                 ++harmonic) {
              const double difference =
                  observed[harmonic] - templates[string][harmonic];
              error += difference * difference;
            }
            best_single_error = std::min(best_single_error, error);
          }

          std::array<double, kHarmonicCount> fitted = templates[primary];
          std::array<double, kM3OpenNotes.size()> component_weights{};
          component_weights[primary] = 1.0;
          double current_error = 0.0;
          for (std::size_t harmonic = 0U; harmonic < observed.size();
               ++harmonic) {
            const double difference = observed[harmonic] - fitted[harmonic];
            current_error += difference * difference;
          }

          // Refit a proposed physical-string set as one convex mixture. This
          // bounded KKT solve is used only for the beat-gated complement
          // escape below; ordinary one-at-a-time inference keeps its existing
          // cheap path. Eight strings cap the augmented system at 9 x 10 and
          // keep the audio callback allocation-free.
          const auto fit_group = [&templates, &observed](
                                     std::uint8_t member_mask,
                                     std::array<double, kHarmonicCount>&
                                         candidate_fitted,
                                     std::array<double, kM3OpenNotes.size()>&
                                         candidate_weights,
                                     double& candidate_error) noexcept {
            std::array<std::size_t, kM3OpenNotes.size()> members{};
            std::size_t member_count = 0U;
            for (std::size_t string = 0U; string < kM3OpenNotes.size();
                 ++string) {
              if ((member_mask & (1U << string)) != 0U) {
                members[member_count++] = string;
              }
            }
            if (member_count == 0U) {
              return false;
            }

            constexpr std::size_t kMaximumVariables =
                kM3OpenNotes.size() + 1U;
            std::array<std::array<double, kMaximumVariables + 1U>,
                       kMaximumVariables>
                system{};
            for (std::size_t row = 0U; row < member_count; ++row) {
              for (std::size_t column = 0U; column < member_count; ++column) {
                for (std::size_t harmonic = 0U; harmonic < observed.size();
                     ++harmonic) {
                  system[row][column] +=
                      templates[members[row]][harmonic] *
                      templates[members[column]][harmonic];
                }
              }
              // A tiny deterministic ridge makes nearly dependent measured
              // profiles refuse by component weight instead of destabilizing
              // the fixed-size elimination.
              system[row][row] += 1.0e-9;
              system[row][member_count] = 1.0;
              for (std::size_t harmonic = 0U; harmonic < observed.size();
                   ++harmonic) {
                system[row][member_count + 1U] +=
                    templates[members[row]][harmonic] * observed[harmonic];
              }
              system[member_count][row] = 1.0;
            }
            system[member_count][member_count + 1U] = 1.0;

            const std::size_t dimension = member_count + 1U;
            const std::size_t right_hand_side = dimension;
            for (std::size_t column = 0U; column < dimension; ++column) {
              std::size_t pivot = column;
              for (std::size_t row = column + 1U; row < dimension; ++row) {
                if (std::abs(system[row][column]) >
                    std::abs(system[pivot][column])) {
                  pivot = row;
                }
              }
              if (std::abs(system[pivot][column]) <= 1.0e-14) {
                return false;
              }
              if (pivot != column) {
                std::swap(system[pivot], system[column]);
              }
              const double divisor = system[column][column];
              for (std::size_t entry = column; entry <= right_hand_side;
                   ++entry) {
                system[column][entry] /= divisor;
              }
              for (std::size_t row = 0U; row < dimension; ++row) {
                if (row == column) {
                  continue;
                }
                const double factor = system[row][column];
                for (std::size_t entry = column; entry <= right_hand_side;
                     ++entry) {
                  system[row][entry] -= factor * system[column][entry];
                }
              }
            }

            candidate_fitted = {};
            candidate_weights = {};
            for (std::size_t member = 0U; member < member_count; ++member) {
              const double weight = system[member][right_hand_side];
              if (!std::isfinite(weight) ||
                  weight < kM3UnisonMinimumComponent) {
                return false;
              }
              candidate_weights[members[member]] = weight;
              for (std::size_t harmonic = 0U; harmonic < observed.size();
                   ++harmonic) {
                candidate_fitted[harmonic] +=
                    weight * templates[members[member]][harmonic];
              }
            }
            candidate_error = 0.0;
            for (std::size_t harmonic = 0U; harmonic < observed.size();
                 ++harmonic) {
              const double difference =
                  observed[harmonic] - candidate_fitted[harmonic];
              candidate_error += difference * difference;
            }
            return std::isfinite(candidate_error);
          };

          // Greedily grow one bounded convex mixture. Adding a component
          // rescales all retained weights, so every accepted member remains
          // physically present and no pairwise-only assumption survives.
          for (std::size_t extra_count = 0U;
               extra_count < candidate_extra_capacity; ++extra_count) {
            std::uint8_t best_string = kUnassignedTunerString;
            double best_alpha = 0.0;
            double best_error = current_error;
            std::array<double, kHarmonicCount> best_fitted{};
            for (std::size_t string = 0U; string < kM3OpenNotes.size();
                 ++string) {
              const std::uint8_t bit =
                  static_cast<std::uint8_t>(1U << string);
              if ((proposed_group & bit) != 0U || !template_valid[string] ||
                  (other_owned_strings & bit) != 0U ||
                  (allocated_extra_strings & bit) != 0U) {
                continue;
              }
              if (!beat_evidence_states_[candidate].valid &&
                  best_single_error <
                      kFineFrequencySingleProfileRejectionError) {
                const StringCalibrationPoint* added_point =
                    calibrator_.bank().point(
                        string, note - kM3OpenNotes[string]);
                bool independently_resolved = added_point != nullptr;
                if (added_point != nullptr) {
                  const double added_frequency = midi_to_frequency(
                      static_cast<double>(note) +
                          static_cast<double>(
                              added_point->cents_offset_q8) /
                              (256.0 * 100.0),
                      440.0);
                  for (std::size_t retained = 0U;
                       retained < kM3OpenNotes.size(); ++retained) {
                    if ((proposed_group & (1U << retained)) == 0U) {
                      continue;
                    }
                    const StringCalibrationPoint* retained_point =
                        calibrator_.bank().point(
                            retained, note - kM3OpenNotes[retained]);
                    if (retained_point == nullptr) {
                      independently_resolved = false;
                      break;
                    }
                    const double retained_frequency = midi_to_frequency(
                        static_cast<double>(note) +
                            static_cast<double>(
                                retained_point->cents_offset_q8) /
                                (256.0 * 100.0),
                        440.0);
                    if (std::abs(added_frequency - retained_frequency) <
                        kM3ProfileOnlyUnisonMinimumSeparationHz) {
                      independently_resolved = false;
                      break;
                    }
                  }
                }
                if (!independently_resolved) {
                  continue;
                }
              }
              double delta_norm = 0.0;
              double projection = 0.0;
              for (std::size_t harmonic = 0U; harmonic < observed.size();
                   ++harmonic) {
                const double delta =
                    templates[string][harmonic] - fitted[harmonic];
                delta_norm += delta * delta;
                projection +=
                    (observed[harmonic] - fitted[harmonic]) * delta;
              }
              if (delta_norm < kM3UnisonMinimumTemplateDistance) {
                continue;
              }
              const double alpha =
                  std::clamp(projection / delta_norm, 0.0, 1.0);
              if (alpha < kM3UnisonMinimumComponent) {
                continue;
              }
              bool retained_components_are_real = true;
              for (std::size_t retained = 0U;
                   retained < component_weights.size(); ++retained) {
                if (component_weights[retained] > 0.0 &&
                    component_weights[retained] * (1.0 - alpha) <
                        kM3UnisonMinimumComponent) {
                  retained_components_are_real = false;
                }
              }
              if (!retained_components_are_real) {
                continue;
              }
              std::array<double, kHarmonicCount> candidate_fitted{};
              double candidate_error = 0.0;
              for (std::size_t harmonic = 0U; harmonic < observed.size();
                   ++harmonic) {
                candidate_fitted[harmonic] =
                    fitted[harmonic] +
                    alpha * (templates[string][harmonic] - fitted[harmonic]);
                const double difference =
                    observed[harmonic] - candidate_fitted[harmonic];
                candidate_error += difference * difference;
              }
              const double comparison_error =
                  proposed_group == primary_bit ? best_single_error
                                                : current_error;
              if (comparison_error - candidate_error <
                      kM3UnisonMinimumErrorImprovement ||
                  candidate_error >
                      best_single_error * kM3UnisonMaximumErrorRatio ||
                  candidate_error >= best_error) {
                continue;
              }
              best_string = static_cast<std::uint8_t>(string);
              best_alpha = alpha;
              best_error = candidate_error;
              best_fitted = candidate_fitted;
            }
            if (best_string >= kM3OpenNotes.size()) {
              // Forward selection can stall when multiple missing strings
              // have complementary spectra: no one residual clears the
              // component floor although their joint calibrated mixture is
              // decisive. Search the at-most-eight-string complement without
              // allocation. From a lone primary it requires at least three
              // complementary additions; after a mixture exists it requires
              // at least two. Every path still needs a large relative error
              // collapse and a real minimum weight for every member.
              bool accepted_complement = false;
              const std::size_t available_slots =
                  candidate_extra_capacity > extra_count
                      ? candidate_extra_capacity - extra_count
                      : 0U;
              if (beat_evidence_states_[candidate].valid &&
                  available_slots >= (extra_count == 0U ? 3U : 2U)) {
                std::uint8_t available_mask = 0U;
                for (std::size_t string = 0U;
                     string < kM3OpenNotes.size(); ++string) {
                  const std::uint8_t bit =
                      static_cast<std::uint8_t>(1U << string);
                  if ((proposed_group & bit) == 0U && template_valid[string] &&
                      (other_owned_strings & bit) == 0U &&
                      (allocated_extra_strings & bit) == 0U) {
                    available_mask =
                        static_cast<std::uint8_t>(available_mask | bit);
                  }
                }
                std::uint8_t best_complement_mask = 0U;
                std::size_t best_added_count = 0U;
                double best_complement_error = current_error;
                std::array<double, kHarmonicCount> best_complement_fitted{};
                std::array<double, kM3OpenNotes.size()>
                    best_complement_weights{};
                constexpr std::uint16_t kSubsetLimit =
                    static_cast<std::uint16_t>(1U << kM3OpenNotes.size());
                for (std::uint16_t raw_subset = 1U;
                     raw_subset < kSubsetLimit; ++raw_subset) {
                  const std::uint8_t subset =
                      static_cast<std::uint8_t>(raw_subset);
                  if ((subset & static_cast<std::uint8_t>(~available_mask)) !=
                      0U) {
                    continue;
                  }
                  std::size_t added_count = 0U;
                  for (std::size_t string = 0U;
                       string < kM3OpenNotes.size(); ++string) {
                    added_count += (subset & (1U << string)) != 0U ? 1U : 0U;
                  }
                  const std::size_t minimum_added =
                      extra_count == 0U ? 3U : 2U;
                  if (added_count < minimum_added ||
                      added_count > available_slots) {
                    continue;
                  }
                  const std::uint8_t candidate_mask =
                      static_cast<std::uint8_t>(proposed_group | subset);
                  std::array<double, kHarmonicCount> candidate_fitted{};
                  std::array<double, kM3OpenNotes.size()> candidate_weights{};
                  double candidate_error = 0.0;
                  if (!fit_group(candidate_mask, candidate_fitted,
                                 candidate_weights, candidate_error) ||
                      candidate_error >
                          current_error *
                              kM3UnisonComplementMaximumRemainingErrorRatio ||
                      candidate_error >
                          best_single_error * kM3UnisonMaximumErrorRatio ||
                      candidate_error >= best_complement_error) {
                    continue;
                  }
                  best_complement_mask = candidate_mask;
                  best_added_count = added_count;
                  best_complement_error = candidate_error;
                  best_complement_fitted = candidate_fitted;
                  best_complement_weights = candidate_weights;
                }
                if (best_complement_mask != 0U) {
                  proposed_group = best_complement_mask;
                  current_error = best_complement_error;
                  fitted = best_complement_fitted;
                  component_weights = best_complement_weights;
                  extra_count += best_added_count - 1U;
                  accepted_complement = true;
                }
              }
              if (!accepted_complement) {
                break;
              }
              continue;
            }
            for (double& weight : component_weights) {
              weight *= 1.0 - best_alpha;
            }
            component_weights[best_string] = best_alpha;
            proposed_group = static_cast<std::uint8_t>(
                proposed_group | (1U << best_string));
            fitted = best_fitted;
            current_error = best_error;
          }
        }
      }
    }

    if (!temporal_group_selected &&
        !beat_evidence_states_[candidate].valid &&
        proposed_group != primary_bit) {
      bool near_duplicate = false;
      for (std::size_t first = 0U; first < kM3OpenNotes.size(); ++first) {
        if ((proposed_group & (1U << first)) == 0U) {
          continue;
        }
        const StringCalibrationPoint* first_point = calibrator_.bank().point(
            first, note - kM3OpenNotes[first]);
        for (std::size_t second = first + 1U;
             second < kM3OpenNotes.size(); ++second) {
          if ((proposed_group & (1U << second)) == 0U) {
            continue;
          }
          const StringCalibrationPoint* second_point =
              calibrator_.bank().point(second, note - kM3OpenNotes[second]);
          if (first_point == nullptr || second_point == nullptr ||
              std::abs(static_cast<double>(first_point->cents_offset_q8) -
                       static_cast<double>(second_point->cents_offset_q8)) <
                  kM3ProfileOnlyNearDuplicateSeparationCents * 256.0) {
            near_duplicate = true;
            break;
          }
        }
        if (near_duplicate) {
          break;
        }
      }
      if (near_duplicate) {
        proposed_group = primary_bit;
      }
    }

    if (!temporal_group_selected) {
      std::size_t snapshot_member_count = 0U;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        snapshot_member_count +=
            (proposed_group & (1U << string)) != 0U ? 1U : 0U;
      }
      if (snapshot_member_count > 3U ||
          (snapshot_member_count > 2U &&
           !beat_evidence_states_[candidate].valid)) {
        // A harmonic snapshot can support a calibrated three-component
        // mixture when independent beat modulation confirms more than one
        // source. Four-string groups remain reserved for the longer
        // calibrated fine-frequency fit: the static six-bin profile is
        // underdetermined beyond the practical three-string case.
        proposed_group = primary_bit;
      }
    }

    if (proposed_group != primary_bit) {
      if (state.pending_unison_mask == proposed_group) {
        if (state.unison_evidence_ticks <
            std::numeric_limits<std::uint8_t>::max()) {
          ++state.unison_evidence_ticks;
        }
      } else {
        state.pending_unison_mask = proposed_group;
        state.unison_evidence_ticks = 1U;
      }
      state.unison_gap_ticks = 0U;
      if (state.unison_evidence_ticks >= unison_evidence_ticks) {
        state.assigned_string_mask = proposed_group;
      }
    } else {
      state.pending_unison_mask = 0U;
      state.unison_evidence_ticks = 0U;
      if (state.assigned_string_mask != primary_bit &&
          state.unison_gap_ticks <
              std::numeric_limits<std::uint16_t>::max()) {
        ++state.unison_gap_ticks;
      }
      if (state.unison_gap_ticks >= unison_dropout_decisions(candidate)) {
        state.assigned_string_mask = primary_bit;
        state.unison_gap_ticks = 0U;
      }
    }

    const std::uint8_t extra = static_cast<std::uint8_t>(
        state.assigned_string_mask & ~primary_bit);
    const std::uint8_t additional_extra =
        static_cast<std::uint8_t>(extra & ~committed_extra_for_candidate);
    std::size_t additional_extra_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      additional_extra_count +=
          (additional_extra & (1U << string)) != 0U ? 1U : 0U;
    }
    if (extra != 0U && additional_extra_count <= remaining_extra &&
        (extra & other_owned_strings) == 0U &&
        (additional_extra & allocated_extra_strings) == 0U) {
      allocated_extra_strings = static_cast<std::uint8_t>(
          allocated_extra_strings | additional_extra);
      remaining_extra -= additional_extra_count;
    } else if (extra != 0U) {
      state.assigned_string_mask = primary_bit;
    }
  }
}

double PolyphonicPitchDetector::calibration_similarity(
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
  // Repeatability confidence should temper a measured fingerprint, not erase
  // it. Physical plucks with stable pitch but changing harmonic balance still
  // carry useful string identity; scaling the cosine all the way to zero let a
  // slightly more repeatable neighbouring fret steal an open-string lane.
  const double confidence_weight = 0.75 + 0.25 * learned_confidence;
  return std::clamp(dot / denominator, 0.0, 1.0) * quality *
         confidence_weight;
}

double PolyphonicPitchDetector::settled_calibration_similarity(
    std::size_t candidate, std::size_t string) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      string >= kM3OpenNotes.size()) {
    return 0.0;
  }
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  if (note < kM3OpenNotes[string]) {
    return 0.0;
  }
  const StringCalibrationPoint* point =
      calibrator_.bank().point(string, note - kM3OpenNotes[string]);
  if (point == nullptr ||
      point->quality == CalibrationPointQuality::missing) {
    return 0.0;
  }
  const double learned_confidence =
      static_cast<double>(point->confidence_q15) / 32767.0;

  std::array<double, kCalibrationHarmonicCount> observed{};
  std::array<double, kCalibrationHarmonicCount> learned{};
  double observed_total = 0.0;
  double learned_total = 0.0;
  for (std::size_t harmonic = 0U; harmonic < observed.size(); ++harmonic) {
    observed[harmonic] =
        0.25 * harmonic_energy_memory_[candidate][harmonic] +
        0.75 * long_harmonic_energy_memory_[candidate][harmonic];
    learned[harmonic] =
        static_cast<double>(point->harmonic_profile_q15[harmonic]);
    observed_total += observed[harmonic];
    learned_total += learned[harmonic];
  }
  if (observed_total <= kScoreEpsilon || learned_total <= kScoreEpsilon) {
    return 0.0;
  }
  for (std::size_t harmonic = 0U; harmonic < observed.size(); ++harmonic) {
    observed[harmonic] /= observed_total;
    learned[harmonic] /= learned_total;
  }

  constexpr double kProfileFloor = 1.0 / 32767.0;
  double ratio_error = 0.0;
  for (std::size_t harmonic = 1U; harmonic < observed.size(); ++harmonic) {
    const double observed_ratio =
        std::log(std::max(observed[harmonic], kProfileFloor)) -
        std::log(std::max(observed[harmonic - 1U], kProfileFloor));
    const double learned_ratio =
        std::log(std::max(learned[harmonic], kProfileFloor)) -
        std::log(std::max(learned[harmonic - 1U], kProfileFloor));
    const double difference = observed_ratio - learned_ratio;
    ratio_error += difference * difference;
  }
  ratio_error /= static_cast<double>(observed.size() - 1U);
  const double shape = std::exp(-ratio_error / 4.0);
  const double quality = point->quality == CalibrationPointQuality::measured
                             ? 1.0
                             : 0.55;
  const double stable_shape =
      shape * quality * (0.75 + 0.25 * learned_confidence);
  return 0.80 * calibration_similarity(candidate, string) +
         0.20 * stable_shape;
}

void PolyphonicPitchDetector::observe_calibration(
    const std::array<double, kMaxCandidates>& scores,
    double lower_guard_score, double upper_guard_score, bool quiet) noexcept {
  if (!calibrator_.active() || quiet) {
    return;
  }
  const CalibrationSweepStatus sweep = calibrator_.status();
  const std::size_t first =
      static_cast<std::size_t>(kM3OpenNotes[sweep.string_index] - lowest_note_);
  const std::size_t last = first + kCalibrationFretCount - 1U;
  if (last >= static_cast<std::size_t>(candidate_count_) ||
      sweep.requested_fret >= kCalibrationFretCount) {
    return;
  }
  // Calibration is explicitly prompted one fret at a time. Measure that
  // requested fret rather than the loudest candidate across the full string
  // range: a lingering lower fret, sympathetic resonance, or strong harmonic
  // must not be learned as the requested physical fret.
  const std::size_t target = first + sweep.requested_fret;
  const double threshold = std::max(fast_energy_ * kCandidateCoherenceRatio,
                                    kScoreEpsilon);
  if (scores[target] <= threshold) {
    return;
  }

  const double left_score =
      target > 0U ? scores[target - 1U] : lower_guard_score;
  const double right_score =
      target + 1U < static_cast<std::size_t>(candidate_count_)
          ? scores[target + 1U]
          : upper_guard_score;
  const double left = std::log(std::max(left_score, kScoreEpsilon));
  const double center = std::log(std::max(scores[target], kScoreEpsilon));
  const double right = std::log(std::max(right_score, kScoreEpsilon));
  const double denominator = left - 2.0 * center + right;
  double semitone_offset = 0.0;
  const PhaseCentsState& phase_cents = phase_cents_states_[target];
  const bool local_peak =
      scores[target] >= left_score && scores[target] >= right_score;
  if (phase_cents.valid) {
    // Calibration must learn the same settled pitch estimate that drives the
    // tuner display.  The neighbouring-bin parabola remains a startup
    // fallback while phase evidence is still accumulating.
    semitone_offset = phase_cents.cents / 100.0;
  } else if (local_peak && std::isfinite(denominator) &&
             denominator < -kScoreEpsilon) {
    // Low strings need the within-bin correction before phase evidence
    // settles, but only a local peak supplies a meaningful parabola.
    semitone_offset = std::clamp(
        0.5 * (left - right) / denominator, -0.5, 0.5);
  } else if (!local_peak) {
    // The explicitly prompted fret may legitimately be quieter than a stale
    // neighbour. Wait for its independent phase estimate before learning it;
    // admitting an uncentred placeholder here corrupts the per-fret profile.
    return;
  }

  CalibrationObservation observation;
  observation.midi_pitch = static_cast<double>(lowest_note_ + target) +
                           semitone_offset;
  observation.confidence = std::clamp(
      (scores[target] - threshold) / (scores[target] + threshold), 0.0, 1.0);
  for (std::size_t harmonic = 0U;
       harmonic < observation.harmonic_energy.size(); ++harmonic) {
    observation.harmonic_energy[harmonic] =
        corrected_harmonic_energy(target, harmonic);
  }
  const PartialDetuningEvidence detuning =
      partial_detuning_trackers_[target].evidence();
  if (detuning.valid_mask != 0U) {
    observation.partial_detuning_cents = detuning.residual_cents;
    observation.partial_detuning_valid_mask = detuning.valid_mask;
  }
  static_cast<void>(calibrator_.observe(observation));
}

void PolyphonicPitchDetector::write_snapshot(
    DetectorDecision& decision,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<bool, kMaxCandidates>& selected,
    bool quiet) noexcept {
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
    const BeatEvidenceState& beat = beat_evidence_states_[candidate];
    if (beat.valid && std::isfinite(beat.beat_hz)) {
      base_voice.beat_hz_q8 = static_cast<std::uint16_t>(std::clamp(
          std::lround(beat.beat_hz * 256.0), 0L,
          static_cast<long>(std::numeric_limits<std::uint16_t>::max())));
    }
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
    // Every physical lane derived from this candidate references one stable
    // pitch-evidence group. The member mask supports the calibrated two- to
    // four-string unison ceiling and distinguishes simultaneous shared groups.
    base_voice.pitch_evidence_group_id =
        static_cast<std::uint8_t>(candidate + 1U);
    base_voice.pitch_evidence_member_mask = strings;
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

DetectorDecision PolyphonicPitchDetector::make_decision() noexcept {
  DetectorDecision decision;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  selection_dispositions_.fill(SelectionDisposition::quiet);
#endif
  ++decision_counter_;
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  if (quiet) {
    selection_dispositions_.fill(SelectionDisposition::quiet);
  } else {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      if (selected[candidate]) {
        selection_dispositions_[candidate] = SelectionDisposition::selected;
      } else if (candidate_states_[candidate].active) {
        selection_dispositions_[candidate] = SelectionDisposition::coasting;
      }
    }
  }
#endif
  update_phase_cents_estimates(selected);
  update_partial_detuning_evidence(selected);
  update_fine_frequency_evidence(selected);
  assign_m3_strings(selected);
  update_harmonic_profile_memory(selected);
  update_beat_evidence(selected);
  infer_m3_unison_strings(selected);
  update_calibration_tuning_offset(selected);

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
    if (state.release_ticks >= candidate_release_decisions(candidate, quiet)) {
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
  write_snapshot(decision, scores, selected, quiet);
  return decision;
}

DetectorDecision PolyphonicPitchDetector::process_sample(double sample) noexcept {
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
      long_harmonic_energy_memory_ = {};
      harmonic_memory_updates_ = {};
      phase_cents_states_ = {};
      beat_evidence_states_ = {};
      fine_frequency_evidence_states_ = {};
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
