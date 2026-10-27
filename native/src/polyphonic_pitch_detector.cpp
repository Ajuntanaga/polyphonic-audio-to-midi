#include "m3/polyphonic_pitch_detector.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>

#include "m3/factory_calibration.hpp"
#include "m3/harmonic_evidence.hpp"
#include "m3/pitch_math.hpp"
#include "m3/unison_spectral_templates.hpp"

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
constexpr std::uint8_t kSpectralLaneDecimation = 4U;
constexpr std::uint8_t kGroupContinuityDecimation = 5U;
constexpr double kSpectralLaneMaximumError = 0.05;
constexpr double kSpectralLaneMinimumMargin = 0.02;
constexpr double kSpectralLaneOnsetMaximumError = 0.15;
constexpr double kSpectralLaneOnsetMinimumMargin = 0.005;
constexpr double kSpectralLaneIsolatedSettledMaximumError = 0.10;
constexpr double kSpectralLaneIsolatedSettledMinimumMargin = 0.02;
constexpr std::uint8_t kSpectralLaneIsolatedSettledStringMask = 0x08U;
constexpr double kAdjacentSpectralDuplicateMinimumErrorGap = 0.45;
constexpr double kAdjacentSpectralDuplicateMaximumErrorAgeSeconds = 0.75;
constexpr double kGroupContinuityCacheSeconds = 0.50;
constexpr double kGroupContinuityMinimumMargin = 0.00015;
constexpr double kGroupContinuityStartScoreRatio = 0.50;
constexpr double kGroupContinuityStartFundamentalRatio = 0.50;
constexpr double kGroupContinuityRetainScoreRatio = 0.25;
constexpr double kGroupContinuityRetainFundamentalRatio = 0.30;
constexpr double kGroupContinuityStartBandScoreRatio = 0.70;
constexpr double kGroupContinuityStartBandFundamentalRatio = 0.60;
constexpr double kGroupContinuityRetainBandScoreRatio = 0.40;
constexpr double kGroupContinuityRetainBandFundamentalRatio = 0.40;
constexpr double kGroupContinuityStartLocalGlobalFloor = 0.10;
constexpr double kGroupContinuityRetainLocalGlobalFloor = 0.05;
#if defined(M3_UNISON_SPECTRAL_SHADOW)
constexpr double kUnisonReacquisitionHoldSeconds = 0.50;
constexpr double kUnisonReacquisitionMinimumRevalidationSeconds = 0.20;
constexpr double kUnisonReacquisitionMaximumFingerprintDistance = 0.005;
#endif
constexpr std::uint32_t kFineFrequencyAnalysisStride = 5U;
// Give close calibrated physical-string offsets three seconds of beat-time
// evidence before admitting a multi-source interpretation. Ordinary pitch
// and chord admission stay on their short causal windows; only the optional
// same-pitch physical-string expansion waits for this evidence. Live testing
// can justify the stricter 3.25-second boundary if this remains unstable.
constexpr double kFineFrequencyMinimumEvidenceSeconds = 3.0;
constexpr double kFineFrequencyMaximumGapSeconds = 0.60;
constexpr double kFineFrequencyInitialConsensusSeconds = 0.20;
constexpr double kFineFrequencyReplacementConsensusSeconds = 2.25;
constexpr double kFineFrequencyRidge = 1.0e-5;
constexpr double kFineFrequencyMinimumRelativeAmplitude = 0.12;
constexpr double kFineFrequencyProfileMatchedRelativeAmplitude = 0.25;
constexpr double kFineFrequencyMinimumResidualImprovement = 0.08;
constexpr double kFineFrequencyMinimumPhaseDeviationHz = 0.03;
constexpr std::size_t kFineFrequencyMaximumPhaseSamples = 64U;
constexpr double kFineBeatPruningMemberPenalty = 0.02;
constexpr double kFineBeatPruningMinimumCoherence = 0.20;
constexpr double kFineBeatPruningTieEpsilon = 1.0e-12;
// A three-second causal observation cannot resolve templates that are only a
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
constexpr double kMaximumHarmonicEnergyCorrection = 8.0;
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
// A quiet upper-string chord tone may be strong inside its own octave while a
// low string keeps the broadband coherence floor above it.  Admit at most one
// such direct candidate after the normal joint selector, and only when its
// calibrated physical-string identity is decisive.  The accepted replay gate
// improves ordinary chords without changing isolated or 3--4-string unisons.
constexpr double kM3CalibratedBandRescueScoreRatio = 0.20;
constexpr double kM3CalibratedBandRescueFundamentalRatio = 0.80;
constexpr double kM3CalibratedBandRescueScorePeakRatio = 0.90;
constexpr double kM3CalibratedBandRescueFundamentalPeakRatio = 0.80;
constexpr double kM3CalibratedBandRescueMinimumSimilarity = 0.97;
constexpr double kM3CalibratedBandRescueMinimumMargin = 0.02;
constexpr double kM3DpReplacementMinimumSimilarity = 0.96;
constexpr double kM3DpReplacementMinimumScoreMargin = 0.50;
// The protected replay counterfactual found one safe additional policy: an
// already-active lowest-string voice may render the stronger DP-evicted note
// without replacing either candidate in the selector.  This intentionally
// uses the measured replay bounds rather than the stricter stateful-replacement
// similarity gate above; two-decision consensus and lane-zero-only ownership
// keep the output correction bounded.
constexpr double kM3DpOutputMinimumSimilarity = 0.50;
constexpr double kM3DpOutputMinimumCalibrationMargin = 0.0;
constexpr double kM3DpOutputMinimumScoreMargin = 0.50;
constexpr std::uint8_t kM3DpOutputConsensusDecisions = 2U;
constexpr std::uint8_t kM3DpOutputAllowedStringMask = 0x01U;
constexpr std::uint8_t kM3CalibratedBandRescueMinimumString = 6U;
constexpr double kM3IsolatedLowerOctaveMinimumSimilarity = 0.96;
constexpr double kM3IsolatedThirdPartialMinimumSimilarity = 0.90;
constexpr double kM3IsolatedLowerOctaveMinimumMargin = 0.50;
constexpr double kM3IsolatedThirdPartialMinimumMargin = 0.20;
constexpr double kM3TuningOffsetMinimumSimilarity = 0.82;
constexpr double kM3TuningOffsetMaximumCents = 8.0;
constexpr double kM3TuningOffsetPendingAgreementCents = 1.5;
constexpr double kM3TuningOffsetTrackingAgreementCents = 4.0;
constexpr double kM3TuningOffsetAcquisitionSeconds = 0.75;
constexpr double kM3TuningOffsetTrackingSeconds = 0.75;
constexpr std::size_t kM3TuningOffsetMinimumStrings = 3U;
// Adjacent-note correction is deliberately an output-layer decision. It is
// available only after one physical string has settled inside a chord, must
// beat the current fret center by at least half a semitone, and must agree on
// two consecutive detector decisions. It cannot create a candidate or alter
// a resolved physical unison group.
constexpr double kM3CalibratedOutputMinimumAgeSeconds = 0.050;
constexpr double kM3CalibratedOutputMinimumImprovementCents = 50.0;
// Crossing a semitone boundary is useful for the recorded low string only
// when the corrected pitch also lands close to that string's measured fret
// center.  Improvement alone is insufficient: a distant adjacent center can
// still beat an even more distant current center and turn uncertain evidence
// into a confident wrong note.
constexpr double kM3CalibratedOutputMaximumProjectedErrorCents = 15.0;
// Recorded M3 strings can sit just across the equal-tempered midpoint while
// remaining well inside the calibrated physical fret. Permit only that narrow
// ten-cent shoulder beyond the ordinary tuner range, then project the emitted
// note back into the normal +/-50-cent display interval.
constexpr double kM3OutputProjectionMaximumAbsoluteCents = 60.0;
constexpr std::uint8_t kM3CalibratedOutputConsensusDecisions = 2U;
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
// Once the causal fine-frequency fitter has committed a physical 2--4 string
// group, a normal selector miss must not let unrelated harmonics consume those
// lanes.  The reservation is still bounded by current signal energy: below
// half the ordinary coherence floor it releases through the normal path.
constexpr double kM3RetainedUnisonDecayFloorRatio = 0.50;
// Once a newly attacked adjacent pitch has direct fundamental support, an
// older single-string voice that has already fallen out of the selector must
// not occupy the lane for the rest of the general release hold.  The short
// onset window distinguishes a real note handoff from an intermittent miss
// inside a sustained semitone interval.  Resolved 2--4 string groups are
// excluded below and retain their beat-aware release policy.
constexpr double kM3AdjacentHandoffOnsetSeconds = 0.100;
// Retaining a resolved physical group is useful only when every calibrated
// member pair still leaves its expected slow beat in the fundamental
// envelope. This prevents a harmonic-rich single source from reserving extra
// tuner lanes merely because the fine-frequency fit can represent it with
// several nearby templates.
constexpr double kM3RetainedUnisonMinimumBeatCoherence = 0.20;
// A connected three- or four-string beat graph may survive one weak edge,
// but not an effectively absent edge. This bounded floor applies only to an
// already-committed group and prevents two strong edges from hiding a wholly
// unsupported third relationship.
constexpr double kM3RetainedUnisonRobustWeakPairFloor = 0.10;
constexpr double kM3RetainedUnisonRobustConfirmationSeconds = 0.75;
// Shadow replay measures whether the existing low/low-mid/high-mid/high
// heads can safely recover one missing lane only in this narrow causal beat
// corridor. Stronger coherence is deliberately not treated as stronger
// evidence here: in the measured corpus it represents the unresolved
// single-source/harmonic regime rather than an independently beating string.
constexpr double kM3SpectralTierCompletionMinimumBeatCoherence = 0.20;
constexpr double kM3SpectralTierCompletionMaximumBeatCoherence = 0.35;
// A tied tier head may complete exactly one already-active, fine-resolved
// group member only when that member also carries substantial independent
// component energy and lies inside the narrow measured beat corridor.  The
// stronger energy floor replaces the weaker head-margin proxy; all existing
// active/playable/one-member/beat gates remain mandatory.
constexpr double kM3SpectralTierCompletionMinimumMargin = 0.0;
constexpr double
    kM3SpectralTierCompletionThickestStringMinimumAddedMemberRatio = 0.06;
constexpr double kM3SpectralTierCompletionMinimumAddedMemberRatio = 0.10;
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

std::uint8_t string_count(std::uint8_t mask) noexcept {
  std::uint8_t count = 0U;
  while (mask != 0U) {
    count = static_cast<std::uint8_t>(count + (mask & 1U));
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return count;
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

PolyphonicPitchDetector::SpectralLaneState*
PolyphonicPitchDetector::find_spectral_lane_state(
    std::size_t candidate) noexcept {
  for (SpectralLaneState& state : spectral_lane_states_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

const PolyphonicPitchDetector::SpectralLaneState*
PolyphonicPitchDetector::find_spectral_lane_state(
    std::size_t candidate) const noexcept {
  for (const SpectralLaneState& state : spectral_lane_states_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

PolyphonicPitchDetector::SpectralLaneState*
PolyphonicPitchDetector::acquire_spectral_lane_state(
    std::size_t candidate) noexcept {
  if (SpectralLaneState* existing = find_spectral_lane_state(candidate)) {
    return existing;
  }
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      candidate > std::numeric_limits<std::uint8_t>::max()) {
    return nullptr;
  }
  for (SpectralLaneState& state : spectral_lane_states_) {
    if (state.candidate_index != 0xffU) {
      continue;
    }
    state = {};
    state.candidate_index = static_cast<std::uint8_t>(candidate);
    const double effective_rate =
        sample_rate_ / static_cast<double>(spectral_lane_decimation_);
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    state.tracking = state.tracker.configure(effective_rate, note);
    if (!state.tracking) {
      state = {};
      return nullptr;
    }
    return &state;
  }
  return nullptr;
}

std::uint8_t PolyphonicPitchDetector::bounded_spectral_lane_assignment(
    bool active, std::uint8_t current_assignment_mask,
    std::uint8_t playable_mask, std::uint8_t other_owned_mask,
    bool polyphonic_context,
    bool fine_frequency_valid, bool fine_frequency_multi_source,
    std::uint8_t fine_frequency_member_mask,
    UnisonSpectralPhase phase,
    bool relaxed_onset_allowed,
    const UnisonSpectralClassification& classification) noexcept {
  const bool fine_frequency_confirms_lane =
      fine_frequency_valid && !fine_frequency_multi_source &&
      string_count(fine_frequency_member_mask) == 1U;
  const bool isolated_settled_confirms_lane =
      !polyphonic_context && !fine_frequency_valid &&
      phase == UnisonSpectralPhase::settled && classification.valid &&
      classification.member_count == 1U &&
      classification.member_mask == kSpectralLaneIsolatedSettledStringMask &&
      std::isfinite(classification.error) &&
      classification.error <= kSpectralLaneIsolatedSettledMaximumError &&
      std::isfinite(classification.posterior_margin) &&
      classification.posterior_margin >=
          kSpectralLaneIsolatedSettledMinimumMargin;
  const double maximum_error =
      isolated_settled_confirms_lane
          ? kSpectralLaneIsolatedSettledMaximumError
          : phase == UnisonSpectralPhase::onset && relaxed_onset_allowed
          ? kSpectralLaneOnsetMaximumError
          : kSpectralLaneMaximumError;
  const double minimum_margin =
      isolated_settled_confirms_lane
          ? kSpectralLaneIsolatedSettledMinimumMargin
          : phase == UnisonSpectralPhase::onset && relaxed_onset_allowed
          ? kSpectralLaneOnsetMinimumMargin
          : kSpectralLaneMinimumMargin;
  if (phase == UnisonSpectralPhase::unready || !active ||
      string_count(current_assignment_mask) != 1U ||
      (!polyphonic_context && !fine_frequency_confirms_lane &&
       !isolated_settled_confirms_lane) ||
      !classification.valid || classification.member_count != 1U ||
      !std::isfinite(classification.error) ||
      classification.error > maximum_error ||
      !std::isfinite(classification.posterior_margin) ||
      classification.posterior_margin < minimum_margin) {
    return 0U;
  }
  const std::uint8_t projected = classification.member_mask;
  if (string_count(projected) != 1U ||
      (fine_frequency_confirms_lane &&
       fine_frequency_member_mask != projected) ||
      (projected & playable_mask) != projected ||
      (projected & other_owned_mask) != 0U) {
    return 0U;
  }
  return projected;
}

std::uint8_t PolyphonicPitchDetector::projected_output_string_mask(
    std::uint8_t assigned_string_mask, std::uint8_t assigned_string,
    std::uint8_t spectral_lane_mask,
    std::uint8_t continuity_lane_mask) noexcept {
  std::uint8_t projected = assigned_string_mask;
  if (projected == 0U && assigned_string < kMaxVoices) {
    projected = static_cast<std::uint8_t>(1U << assigned_string);
  }
  if (string_count(projected) == 1U && spectral_lane_mask != 0U) {
    projected = spectral_lane_mask;
  }
  if (projected != 0U && continuity_lane_mask != 0U &&
      (projected & static_cast<std::uint8_t>(~continuity_lane_mask)) == 0U) {
    projected = continuity_lane_mask;
  }
  return projected;
}

std::uint8_t PolyphonicPitchDetector::bounded_group_continuity_projection(
    std::uint8_t current_assignment_mask,
    std::uint8_t cached_group_mask,
    const UnisonSpectralClassification& classification,
    UnisonSpectralPhase phase, std::uint8_t fine_frequency_mask,
    double minimum_beat_coherence, std::uint8_t profile_mask,
    std::uint8_t temporal_mask, std::uint8_t tier_projection_mask,
    std::uint8_t other_owned_mask, std::uint8_t playable_mask,
    std::uint8_t maximum_polyphony, bool active_candidate,
    bool selected_or_coasting, bool direct_fundamental, bool quiet,
    double cache_age_seconds) noexcept {
  const auto union_projection = [current_assignment_mask](
                                    std::uint8_t first,
                                    std::uint8_t second) noexcept {
    if (first == second) {
      return first;
    }
    if (first == current_assignment_mask) {
      return second;
    }
    if (second == current_assignment_mask) {
      return first;
    }
    return current_assignment_mask;
  };
  const auto physically_bounded = [other_owned_mask, playable_mask,
                                   maximum_polyphony](
                                      std::uint8_t mask) noexcept {
    return mask != 0U && maximum_polyphony > 0U &&
           maximum_polyphony <= kMaxVoices &&
           (mask & static_cast<std::uint8_t>(~playable_mask)) == 0U &&
           (mask & other_owned_mask) == 0U &&
           string_count(static_cast<std::uint8_t>(mask |
                                                  other_owned_mask)) <=
               maximum_polyphony;
  };

  if (quiet || !active_candidate || !selected_or_coasting ||
      !direct_fundamental || phase == UnisonSpectralPhase::unready ||
      string_count(current_assignment_mask) == 0U) {
    return current_assignment_mask;
  }

  std::uint8_t tier_projection = current_assignment_mask;
  if (string_count(current_assignment_mask) >= 2U &&
      tier_projection_mask != current_assignment_mask &&
      (current_assignment_mask &
       static_cast<std::uint8_t>(~tier_projection_mask)) == 0U &&
      string_count(tier_projection_mask) >= 2U &&
      string_count(tier_projection_mask) <= 4U &&
      physically_bounded(tier_projection_mask)) {
    tier_projection = tier_projection_mask;
  }

  const bool cache_valid =
      string_count(cached_group_mask) >= 3U &&
      string_count(cached_group_mask) <= 4U &&
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) == 0U &&
      physically_bounded(cached_group_mask) &&
      std::isfinite(cache_age_seconds) && cache_age_seconds >= 0.0 &&
      cache_age_seconds <= kGroupContinuityCacheSeconds;
  if (!cache_valid) {
    return current_assignment_mask;
  }

  const double phase_multiplier =
      phase == UnisonSpectralPhase::onset ? 2.0 : 1.0;
  const std::uint8_t classified_members =
      string_count(classification.member_mask);
  const std::uint8_t current_members =
      string_count(current_assignment_mask);
  const std::uint8_t fine_members = string_count(fine_frequency_mask);
  std::uint8_t candidate_projection = current_assignment_mask;
  if (current_members >= 2U && current_members <= 4U &&
      fine_members >= 2U && fine_members <= 4U && classification.valid &&
      classified_members >= 2U && classified_members <= 4U &&
      classification.member_count == classified_members &&
      (classification.member_mask & current_assignment_mask) ==
          current_assignment_mask &&
      std::isfinite(classification.posterior_margin) &&
      classification.posterior_margin >=
          kGroupContinuityMinimumMargin * phase_multiplier) {
    const bool exact_fine =
        classification.member_mask == fine_frequency_mask;
    const bool corroborated =
        std::isfinite(minimum_beat_coherence) &&
        minimum_beat_coherence >= 0.20 &&
        (classification.member_mask & fine_frequency_mask) ==
            fine_frequency_mask &&
        (classification.member_mask == profile_mask ||
         classification.member_mask == temporal_mask);
    if ((exact_fine || corroborated) &&
        physically_bounded(classification.member_mask)) {
      candidate_projection = classification.member_mask;
    }
  }
  if (candidate_projection != cached_group_mask) {
    candidate_projection = current_assignment_mask;
  }

  const std::uint8_t cached_completion = union_projection(
      candidate_projection, tier_projection);

  std::uint8_t classifier_projection = current_assignment_mask;
  if (current_members < string_count(cached_group_mask) &&
      classification.valid &&
      classification.member_mask == cached_group_mask &&
      classification.member_count == string_count(cached_group_mask) &&
      std::isfinite(classification.posterior_margin) &&
      classification.posterior_margin >= kGroupContinuityMinimumMargin) {
    classifier_projection = cached_group_mask;
  }
  return union_projection(cached_completion, classifier_projection);
}

std::uint8_t PolyphonicPitchDetector::
    bounded_three_member_articulated_group_continuity_projection(
        std::uint8_t current_assignment_mask,
        std::uint8_t cached_group_mask,
        std::uint8_t pending_fine_mask,
        double pending_evidence_seconds,
        double pending_beat_coherence,
        std::uint8_t spectral_tier_mask,
        std::uint8_t other_owned_mask,
        std::uint8_t playable_mask,
        std::uint8_t maximum_polyphony,
        double score_threshold_ratio,
        bool active_candidate,
        bool direct_fundamental,
        bool quiet,
        double cache_age_seconds) noexcept {
  constexpr double kMaximumGapSeconds = 0.25;
  constexpr double kMinimumRevalidationSeconds = 0.20;
  if (quiet || !active_candidate || !direct_fundamental ||
      !std::isfinite(score_threshold_ratio) ||
      score_threshold_ratio < kM3RetainedUnisonDecayFloorRatio ||
      string_count(cached_group_mask) != 3U ||
      !std::isfinite(cache_age_seconds) || cache_age_seconds < 0.0 ||
      cache_age_seconds > kMaximumGapSeconds ||
      current_assignment_mask == 0U ||
      string_count(current_assignment_mask) > 4U ||
      (current_assignment_mask &
       static_cast<std::uint8_t>(~cached_group_mask)) != 0U ||
      string_count(pending_fine_mask) < 2U ||
      string_count(pending_fine_mask) > 4U ||
      (pending_fine_mask & static_cast<std::uint8_t>(~cached_group_mask)) !=
          0U ||
      !std::isfinite(pending_evidence_seconds) ||
      pending_evidence_seconds < kMinimumRevalidationSeconds ||
      !std::isfinite(pending_beat_coherence) ||
      pending_beat_coherence < 0.20 ||
      spectral_tier_mask != cached_group_mask ||
      (cached_group_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (cached_group_mask & other_owned_mask) != 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      string_count(static_cast<std::uint8_t>(cached_group_mask |
                                             other_owned_mask)) >
          maximum_polyphony) {
    return current_assignment_mask;
  }
  return cached_group_mask;
}

std::uint8_t PolyphonicPitchDetector::
    bounded_solo_three_member_articulated_group_continuity_projection(
        std::uint8_t current_assignment_mask,
        std::uint8_t cached_group_mask,
        std::uint8_t pending_fine_mask,
        double pending_evidence_seconds,
        double pending_beat_coherence,
        std::uint8_t spectral_tier_mask,
        std::uint8_t other_owned_mask,
        std::uint8_t playable_mask,
        std::uint8_t maximum_polyphony,
        double score_threshold_ratio,
        bool active_candidate,
        bool direct_fundamental,
        bool quiet,
        double cache_age_seconds) noexcept {
  if (other_owned_mask != 0U || cached_group_mask != playable_mask) {
    return current_assignment_mask;
  }
  return bounded_three_member_articulated_group_continuity_projection(
      current_assignment_mask, cached_group_mask, pending_fine_mask,
      pending_evidence_seconds, pending_beat_coherence, spectral_tier_mask,
      other_owned_mask, playable_mask, maximum_polyphony,
      score_threshold_ratio, active_candidate, direct_fundamental, quiet,
      cache_age_seconds);
}

PolyphonicPitchDetector::GroupContinuityTrackerState*
PolyphonicPitchDetector::find_group_continuity_tracker(
    std::size_t candidate) noexcept {
  for (GroupContinuityTrackerState& state : group_continuity_trackers_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

const PolyphonicPitchDetector::GroupContinuityTrackerState*
PolyphonicPitchDetector::find_group_continuity_tracker(
    std::size_t candidate) const noexcept {
  for (const GroupContinuityTrackerState& state :
       group_continuity_trackers_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

void PolyphonicPitchDetector::update_group_continuity_trackers(
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet) noexcept {
  for (CandidateState& state : candidate_states_) {
    state.continuity_lane_mask = 0U;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.group_continuity_diagnostic_flags = 0U;
#endif
  }
  if (profile_mode_ != ProfileMode::m3 || sample_rate_ <= 0.0) {
    return;
  }

  constexpr std::size_t kPitchBandCount = 4U;
  constexpr std::uint8_t kPitchBandSemitones = 12U;
  std::array<double, kPitchBandCount> band_score_peak{};
  std::array<double, kPitchBandCount> band_fundamental_peak{};
  const auto pitch_band = [this](std::size_t candidate) noexcept {
    const std::uint8_t note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
    const std::uint8_t offset =
        note > kM3OpenNotes.front()
            ? static_cast<std::uint8_t>(note - kM3OpenNotes.front())
            : 0U;
    return std::min<std::size_t>(kPitchBandCount - 1U,
                                 offset / kPitchBandSemitones);
  };
  const auto playable_for_note = [this](std::uint8_t note) noexcept {
    std::uint8_t mask = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t open = kM3OpenNotes[string];
      if (note >= open &&
          static_cast<std::uint16_t>(note) <=
              static_cast<std::uint16_t>(open) + max_fret_) {
        mask = static_cast<std::uint8_t>(mask | (1U << string));
      }
    }
    return mask;
  };
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  const auto output_mask_for_note = [this, count](
                                        std::uint8_t note) noexcept {
    std::uint8_t mask = 0U;
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      const CandidateState& state = candidate_states_[candidate];
      if (!state.active || candidate_output_note(candidate) != note) {
        continue;
      }
      mask = static_cast<std::uint8_t>(
          mask | projected_output_string_mask(
                     state.assigned_string_mask, state.assigned_string,
                     state.spectral_lane_mask, 0U));
    }
    return mask;
  };
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (playable_string_mask(candidate) == 0U) {
      continue;
    }
    const std::size_t band = pitch_band(candidate);
    band_score_peak[band] = std::max(band_score_peak[band],
                                     scores[candidate]);
    band_fundamental_peak[band] = std::max(
        band_fundamental_peak[band], fundamentals[candidate]);
  }

  struct Rank final {
    double priority{};
    std::uint8_t candidate{};
  };
  std::array<Rank, kMaxCandidates> ranking{};
  std::size_t ranking_count = 0U;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const std::uint8_t playable = playable_string_mask(candidate);
    if (playable == 0U) {
      continue;
    }
    GroupContinuityTrackerState* existing =
        find_group_continuity_tracker(candidate);
    const bool tracking = existing != nullptr && existing->tracking;
    const CandidateState& candidate_state = candidate_states_[candidate];
    const bool admitted_active = candidate_state.active;
    const bool direct = has_direct_fundamental_peak(
                            scores, fundamentals, candidate, count) &&
                        (is_local_peak(scores, candidate, count) ||
                         has_m3_candidate_evidence(scores, fundamentals,
                                                   candidate, count));
    const double score_ratio =
        scores[candidate] / std::max(threshold, kScoreEpsilon);
    const double fundamental_ratio = fundamentals[candidate] /
                                     std::max(scores[candidate],
                                              kScoreEpsilon);
    const std::size_t band = pitch_band(candidate);
    const double band_score_ratio =
        scores[candidate] /
        std::max(band_score_peak[band], kScoreEpsilon);
    const double band_fundamental_ratio =
        fundamentals[candidate] /
        std::max(band_fundamental_peak[band], kScoreEpsilon);
    const auto note = candidate_output_note(candidate);
    const bool retain = tracking && !quiet &&
        (admitted_active ||
         (direct &&
          ((score_ratio >= kGroupContinuityRetainScoreRatio &&
            fundamental_ratio >=
                kGroupContinuityRetainFundamentalRatio) ||
           (score_ratio >= kGroupContinuityRetainLocalGlobalFloor &&
            band_score_ratio >= kGroupContinuityRetainBandScoreRatio &&
            band_fundamental_ratio >=
                kGroupContinuityRetainBandFundamentalRatio))));
    const bool start_evidence = !tracking && !quiet &&
        (admitted_active ||
         (!candidate_state.active && direct &&
          ((score_ratio >= kGroupContinuityStartScoreRatio &&
            fundamental_ratio >= kGroupContinuityStartFundamentalRatio) ||
           (score_ratio >= kGroupContinuityStartLocalGlobalFloor &&
            band_score_ratio >= kGroupContinuityStartBandScoreRatio &&
            fundamental_ratio >= kGroupContinuityStartFundamentalRatio &&
            band_fundamental_ratio >=
                kGroupContinuityStartBandFundamentalRatio))));
    const bool start = start_evidence &&
        factory_unison_spectral_templates_available(
            UnisonSpectralPhase::unready, note);
    if (!retain && !start) {
      continue;
    }
    ranking[ranking_count++] = {
        std::max(score_ratio, band_score_ratio) + (tracking ? 4.0 : 0.0),
        static_cast<std::uint8_t>(candidate)};
  }
  std::sort(ranking.begin(), ranking.begin() + ranking_count,
            [](const Rank& left, const Rank& right) noexcept {
              return left.priority > right.priority ||
                     (left.priority == right.priority &&
                      left.candidate < right.candidate);
            });
  std::array<bool, kMaxCandidates> desired{};
  const std::size_t desired_count = std::min(
      ranking_count, kMaximumGroupContinuityTrackers);
  for (std::size_t index = 0U; index < desired_count; ++index) {
    desired[ranking[index].candidate] = true;
  }

  for (GroupContinuityTrackerState& state : group_continuity_trackers_) {
    if (state.candidate_index < count &&
        !desired[state.candidate_index] && state.tracking) {
      state.tracker.reset();
      state.last_classification = {};
      state.tracking = false;
    }
  }
  const std::uint32_t maximum_age_ticks = static_cast<std::uint32_t>(
      std::max(1.0, std::ceil(kGroupContinuityCacheSeconds * sample_rate_ /
                             static_cast<double>(kDecisionQuantum))));
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (!desired[candidate]) {
      continue;
    }
    GroupContinuityTrackerState* state =
        find_group_continuity_tracker(candidate);
    if (state == nullptr) {
      for (GroupContinuityTrackerState& slot :
           group_continuity_trackers_) {
        if (slot.candidate_index == 0xffU) {
          state = &slot;
          break;
        }
      }
    }
    if (state == nullptr) {
      for (GroupContinuityTrackerState& slot :
           group_continuity_trackers_) {
        const CandidateState* cached =
            slot.candidate_index < count
                ? &candidate_states_[slot.candidate_index]
                : nullptr;
        if (!slot.tracking &&
            (cached == nullptr ||
             cached->continuity_cached_group_mask == 0U ||
             decision_counter_ -
                     cached->continuity_cached_group_tick >
                 maximum_age_ticks)) {
          state = &slot;
          break;
        }
      }
    }
    if (state == nullptr) {
      continue;
    }
    if (state->candidate_index != candidate) {
      *state = {};
      state->candidate_index = static_cast<std::uint8_t>(candidate);
    }
    const std::uint8_t output_note = candidate_output_note(candidate);
    if (state->midi_note != output_note) {
      state->tracker.reset();
      state->last_classification = {};
      state->templates_valid = false;
      state->tracking = false;
      state->midi_note = output_note;
      CandidateState& candidate_state = candidate_states_[candidate];
      candidate_state.continuity_cached_group_mask = 0U;
      candidate_state.continuity_cached_group_tick = 0U;
      candidate_state.continuity_cached_note = kTunerNoSignalNote;
    }
    if (!state->tracking) {
      const double effective_rate =
          sample_rate_ / static_cast<double>(group_continuity_decimation_);
      state->tracking = state->tracker.configure(effective_rate,
                                                 output_note);
    }
  }

  // The established physical group is causal detector state, not classifier
  // state.  Cache it even if the independent corridor has not settled yet;
  // a later projection still requires a live, exact classifier result.
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    const std::uint8_t output_note = candidate_output_note(candidate);
    if (state.continuity_cached_group_mask != 0U &&
        state.continuity_cached_note != output_note) {
      state.continuity_cached_group_mask = 0U;
      state.continuity_cached_group_tick = 0U;
      state.continuity_cached_note = kTunerNoSignalNote;
    }
    const std::uint8_t current = output_mask_for_note(output_note);
    const std::uint8_t current_members = string_count(current);
    if (!quiet && state.active &&
        current_members >= 3U && current_members <= 4U &&
        (state.continuity_cached_group_mask == 0U ||
         current_members >=
             string_count(state.continuity_cached_group_mask))) {
      state.continuity_cached_group_mask = current;
      state.continuity_cached_group_tick = decision_counter_;
      state.continuity_cached_note = output_note;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (state.continuity_cached_group_mask != 0U) {
      const double age =
          static_cast<double>(decision_counter_ -
                              state.continuity_cached_group_tick) *
          static_cast<double>(kDecisionQuantum) / sample_rate_;
      if (age <= kGroupContinuityCacheSeconds) {
        state.group_continuity_diagnostic_flags |= 0x01U;
      }
    }
#endif
  }

  const std::uint64_t readiness_lead_samples =
      static_cast<std::uint64_t>(std::ceil(
          static_cast<double>(kDecisionQuantum) /
          static_cast<double>(group_continuity_decimation_)));
  std::size_t classification_slot = group_continuity_trackers_.size();
  for (std::size_t offset = 0U;
       offset < group_continuity_trackers_.size(); ++offset) {
    const std::size_t slot =
        (group_continuity_classification_cursor_ + offset) %
        group_continuity_trackers_.size();
    const GroupContinuityTrackerState& continuity =
        group_continuity_trackers_[slot];
    if (continuity.tracking && continuity.candidate_index < count &&
        desired[continuity.candidate_index]) {
      classification_slot = slot;
      group_continuity_classification_cursor_ =
          static_cast<std::uint8_t>(
              (slot + 1U) % group_continuity_trackers_.size());
      break;
    }
  }
  for (std::size_t continuity_slot = 0U;
       continuity_slot < group_continuity_trackers_.size();
       ++continuity_slot) {
    GroupContinuityTrackerState& continuity =
        group_continuity_trackers_[continuity_slot];
    const std::size_t candidate = continuity.candidate_index;
    if (!continuity.tracking || candidate >= count ||
        !desired[candidate]) {
      continue;
    }
    CandidateState& candidate_state = candidate_states_[candidate];
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    candidate_state.group_continuity_diagnostic_flags |= 0x02U;
#endif
    if (!continuity.tracker.ready_with_lead(readiness_lead_samples)) {
      continue;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    candidate_state.group_continuity_diagnostic_flags |= 0x04U;
#endif
    const std::uint8_t current =
        output_mask_for_note(continuity.midi_note);
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t output_playable =
        playable_for_note(continuity.midi_note);
    const std::uint8_t fine_mask = static_cast<std::uint8_t>(
        fine.member_mask & output_playable);
    const UnisonSpectralPhase continuity_phase =
        continuity.tracker.phase_with_lead(readiness_lead_samples);
    if (continuity_slot == classification_slot) {
      UnisonSpectralPhase template_phase = continuity_phase;
      if (!factory_unison_spectral_templates_available(
              template_phase, continuity.midi_note)) {
        template_phase = UnisonSpectralPhase::unready;
      }
      if (!continuity.templates_valid ||
          continuity.template_phase != template_phase) {
        continuity.templates_valid = factory_unison_spectral_templates(
            template_phase, continuity.midi_note, continuity.templates);
        continuity.template_phase = template_phase;
      }
      if (!continuity.templates_valid) {
        continue;
      }
      continuity.last_classification = classify_feasible_unison(
            continuity.tracker.fingerprint_with_lead(
                readiness_lead_samples),
            continuity.templates, output_playable, 2U, 4U);
    }
    const UnisonSpectralClassification classification =
        continuity.last_classification;
    std::uint8_t other_owned = 0U;
    for (std::size_t other = 0U; other < count; ++other) {
      if (!candidate_states_[other].active ||
          candidate_output_note(other) == continuity.midi_note) {
        continue;
      }
      std::uint8_t owned = static_cast<std::uint8_t>(
          candidate_states_[other].assigned_string_mask |
          candidate_states_[other].midi_voice_mask);
      if (owned == 0U &&
          candidate_states_[other].assigned_string < kMaxVoices) {
        owned = static_cast<std::uint8_t>(
            1U << candidate_states_[other].assigned_string);
      }
      other_owned = static_cast<std::uint8_t>(other_owned | owned);
    }

    std::uint8_t tier_projection = current;
    const SpectralHeadEvidence spectral =
        string_fret_spectral_head_evidence(candidate);
    std::uint8_t tier_candidate = fine_mask;
    if (string_count(fine_mask) >= 2U && string_count(fine_mask) < 4U) {
      std::uint8_t qualified = fine_mask;
      const double phase_multiplier =
          continuity_phase == UnisonSpectralPhase::onset ? 2.0 : 1.0;
      for (std::size_t head = 0U; head < spectral.best_string.size(); ++head) {
        const std::uint8_t string = spectral.best_string[head];
        if (string < kMaxVoices &&
            std::isfinite(spectral.margin[head]) &&
            spectral.margin[head] >=
                kGroupContinuityMinimumMargin * phase_multiplier) {
          qualified = static_cast<std::uint8_t>(qualified |
                                                (1U << string));
        }
      }
      if (string_count(qualified) ==
          static_cast<std::uint8_t>(string_count(fine_mask) + 1U)) {
        tier_candidate = qualified;
      }
    }
    if (tier_candidate != fine_mask && current != 0U &&
        (current & static_cast<std::uint8_t>(~fine_mask)) == 0U) {
      const std::uint8_t added = static_cast<std::uint8_t>(
          tier_candidate & static_cast<std::uint8_t>(~fine_mask));
      std::size_t added_string = 0U;
      while (added_string < kMaxVoices &&
             (added & (1U << added_string)) == 0U) {
        ++added_string;
      }
      const double maximum_component = *std::max_element(
          fine.component_energy.begin(), fine.component_energy.end());
      const double added_ratio =
          added_string < kMaxVoices && maximum_component > kScoreEpsilon
              ? std::sqrt(std::max(
                    0.0, fine.component_energy[added_string] /
                             maximum_component))
              : 0.0;
      const double coherence =
          added_string < kMaxVoices
              ? fine.added_member_beat_coherence[added_string]
              : 0.0;
      if (std::isfinite(coherence) && coherence >= 0.20 &&
          coherence < 0.30 && added_ratio >= 0.08) {
        tier_projection = tier_candidate;
      }
    }

    const double age_seconds =
        candidate_state.continuity_cached_group_mask != 0U
            ? static_cast<double>(decision_counter_ -
                                  candidate_state.continuity_cached_group_tick) *
                  static_cast<double>(kDecisionQuantum) / sample_rate_
            : std::numeric_limits<double>::infinity();
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (candidate_state.continuity_cached_group_mask != 0U &&
        age_seconds <= kGroupContinuityCacheSeconds) {
      candidate_state.group_continuity_diagnostic_flags |= 0x01U;
    }
    if (classification.valid &&
        classification.member_mask ==
            candidate_state.continuity_cached_group_mask &&
        classification.member_count ==
            string_count(candidate_state.continuity_cached_group_mask) &&
        std::isfinite(classification.posterior_margin) &&
        classification.posterior_margin >=
            kGroupContinuityMinimumMargin) {
      candidate_state.group_continuity_diagnostic_flags |= 0x08U;
    }
    if (tier_projection != current) {
      candidate_state.group_continuity_diagnostic_flags |= 0x10U;
    }
#endif
    const std::uint8_t profile_mask =
        candidate_state.latest_unison_proposal_temporal
            ? 0U
            : candidate_state.latest_unison_proposal_mask;
    const std::uint8_t temporal_mask =
        candidate_state.latest_unison_proposal_temporal
            ? candidate_state.latest_unison_proposal_mask
            : 0U;
    const bool direct_fundamental = has_direct_fundamental_peak(
        scores, fundamentals, candidate, count);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (current != 0U &&
        string_count(current) <
            string_count(candidate_state.continuity_cached_group_mask) &&
        (current & static_cast<std::uint8_t>(
                       ~candidate_state.continuity_cached_group_mask)) == 0U) {
      candidate_state.group_continuity_diagnostic_flags |= 0x40U;
    }
    if (direct_fundamental) {
      candidate_state.group_continuity_diagnostic_flags |= 0x80U;
    }
#endif
    const std::uint8_t classified_projection =
        bounded_group_continuity_projection(
            current, candidate_state.continuity_cached_group_mask,
            classification, continuity_phase, fine_mask,
            fine.minimum_pairwise_beat_coherence, profile_mask,
            temporal_mask, tier_projection, other_owned,
            output_playable, max_polyphony_, candidate_state.active,
            selected[candidate] || candidate_state.active,
            direct_fundamental, quiet, age_seconds);
    const std::uint8_t articulated_tier_mask =
        bounded_spectral_tier_completion(
            candidate_state.active, candidate_state.assigned_string_mask,
            fine_mask, output_playable, spectral,
            fine.added_member_beat_coherence, fine.component_energy);
    const double pending_evidence_seconds =
        static_cast<double>(fine.pending_count) *
        static_cast<double>(kDecisionQuantum) *
        static_cast<double>(fine_frequency_decimation_decisions_) *
        static_cast<double>(kFineFrequencyAnalysisStride) / sample_rate_;
    const std::uint8_t articulated_projection =
        bounded_three_member_articulated_group_continuity_projection(
            current, candidate_state.continuity_cached_group_mask,
            fine.pending_member_mask, pending_evidence_seconds,
            fine.pending_minimum_pairwise_beat_coherence,
            articulated_tier_mask, other_owned, output_playable,
            max_polyphony_,
            scores[candidate] / std::max(threshold, kScoreEpsilon),
            candidate_state.active, direct_fundamental, quiet, age_seconds);
    candidate_state.continuity_lane_mask =
        classified_projection == current
            ? articulated_projection
            : (articulated_projection == current ||
                       articulated_projection == classified_projection
                   ? classified_projection
                   : current);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (candidate_state.continuity_lane_mask != current) {
      candidate_state.group_continuity_diagnostic_flags |= 0x20U;
    }
#endif
  }
}

std::uint8_t PolyphonicPitchDetector::spectral_lane_assignment(
    std::size_t candidate, bool isolated_selected_voice) noexcept {
  if (profile_mode_ != ProfileMode::m3 ||
      candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& candidate_state = candidate_states_[candidate];
  std::uint8_t current = candidate_state.assigned_string_mask;
  if (current == 0U && candidate_state.assigned_string < kMaxVoices) {
    current = static_cast<std::uint8_t>(
        1U << candidate_state.assigned_string);
  }
  SpectralLaneState* spectral = find_spectral_lane_state(candidate);
  if (spectral == nullptr || !spectral->tracking ||
      !spectral->tracker.ready()) {
    return 0U;
  }
  const UnisonSpectralPhase phase = spectral->tracker.phase();
  std::uint8_t other_owned = 0U;
  for (std::size_t other = 0U;
       other < static_cast<std::size_t>(candidate_count_); ++other) {
    if (other == candidate || !candidate_states_[other].active) {
      continue;
    }
    std::uint8_t owned = static_cast<std::uint8_t>(
        candidate_states_[other].assigned_string_mask |
        candidate_states_[other].midi_voice_mask);
    if (owned == 0U &&
        candidate_states_[other].assigned_string < kMaxVoices) {
      owned = static_cast<std::uint8_t>(
          1U << candidate_states_[other].assigned_string);
    }
    other_owned = static_cast<std::uint8_t>(other_owned | owned);
  }
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  UnisonSpectralPhase template_phase = phase;
  if (!factory_unison_spectral_templates_available(template_phase, note)) {
    template_phase = UnisonSpectralPhase::unready;
  }
  if (!spectral->templates_valid ||
      spectral->template_phase != template_phase ||
      spectral->midi_note != note) {
    spectral->templates_valid = factory_unison_spectral_templates(
        template_phase, note, spectral->templates);
    spectral->template_phase = template_phase;
    spectral->midi_note = note;
  }
  if (!spectral->templates_valid) {
    return 0U;
  }
  const UnisonSpectralClassification classification =
      classify_single_spectral_source(spectral->tracker.fingerprint(),
                                      spectral->templates,
                                      playable_string_mask(candidate));
  spectral->single_source_error_valid =
      classification.valid && classification.member_count == 1U &&
      std::isfinite(classification.error);
  spectral->single_source_best_error = classification.error;
  spectral->single_source_error_mask = classification.member_mask;
  spectral->single_source_error_tick = decision_counter_;
  const FineFrequencyEvidenceState& fine =
      fine_frequency_evidence_states_[candidate];
  const bool isolated_settled_confirms_lane =
      isolated_selected_voice && !candidate_state.polyphonic_context &&
      !fine.valid &&
      phase == UnisonSpectralPhase::settled && classification.valid &&
      classification.member_count == 1U &&
      classification.member_mask == kSpectralLaneIsolatedSettledStringMask &&
      std::isfinite(classification.error) &&
      classification.error <= kSpectralLaneIsolatedSettledMaximumError &&
      std::isfinite(classification.posterior_margin) &&
      classification.posterior_margin >=
          kSpectralLaneIsolatedSettledMinimumMargin;
  if (beat_evidence_states_[candidate].valid &&
      !isolated_settled_confirms_lane) {
    return 0U;
  }
  return bounded_spectral_lane_assignment(
      candidate_state.active, current, playable_string_mask(candidate),
      other_owned,
      candidate_state.polyphonic_context || !isolated_selected_voice,
      fine.valid,
      fine.multi_source_observed, fine.member_mask, phase,
      note < kM3OpenNotes.back(), classification);
}

std::uint8_t
PolyphonicPitchDetector::bounded_adjacent_spectral_duplicate_suppression(
    bool left_active, bool right_active, std::uint8_t left_note,
    std::uint8_t right_note, std::uint8_t left_output_mask,
    std::uint8_t right_output_mask, bool left_spectral_ready,
    bool right_spectral_ready, double left_error,
    double right_error) noexcept {
  const auto is_single_lane = [](std::uint8_t mask) noexcept {
    return mask != 0U && (mask & static_cast<std::uint8_t>(mask - 1U)) == 0U;
  };
  if (!left_active || !right_active || left_note >= 127U ||
      right_note != static_cast<std::uint8_t>(left_note + 1U) ||
      !is_single_lane(left_output_mask) ||
      !is_single_lane(right_output_mask) ||
      left_output_mask == right_output_mask || !left_spectral_ready ||
      !right_spectral_ready || !std::isfinite(left_error) ||
      !std::isfinite(right_error) ||
      std::abs(left_error - right_error) <
          kAdjacentSpectralDuplicateMinimumErrorGap) {
    return 0U;
  }
  return left_error > right_error ? 0x01U : 0x02U;
}

void PolyphonicPitchDetector::
update_adjacent_spectral_duplicate_suppression() noexcept {
  spectral_duplicate_suppressed_.fill(false);
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }
  std::array<std::uint8_t, kMaxCandidates> output_masks{};
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    if (!state.active) {
      continue;
    }
    output_masks[candidate] = projected_output_string_mask(
        state.assigned_string_mask, state.assigned_string,
        state.spectral_lane_mask, state.continuity_lane_mask);
    if (state.fine_beat_pruning_mask != 0U) {
      output_masks[candidate] = state.midi_voice_mask;
    }
  }
  std::array<double, kMaxCandidates> errors{};
  std::array<bool, kMaxCandidates> ready{};
  errors.fill(std::numeric_limits<double>::infinity());
  const std::uint32_t maximum_age = static_cast<std::uint32_t>(std::max(
      1.0, std::ceil(kAdjacentSpectralDuplicateMaximumErrorAgeSeconds *
                     sample_rate_ / static_cast<double>(kDecisionQuantum))));
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const SpectralLaneState* spectral = find_spectral_lane_state(candidate);
    if (!state.active || spectral == nullptr ||
        !spectral->single_source_error_valid ||
        spectral->single_source_error_mask != output_masks[candidate] ||
        decision_counter_ - spectral->single_source_error_tick > maximum_age) {
      continue;
    }
    ready[candidate] = true;
    errors[candidate] = spectral->single_source_best_error;
  }
  for (std::size_t left = 0U;
       left < static_cast<std::size_t>(candidate_count_); ++left) {
    if (!candidate_states_[left].active) {
      continue;
    }
    const std::uint8_t left_note = candidate_output_note(left);
    for (std::size_t right = left + 1U;
         right < static_cast<std::size_t>(candidate_count_); ++right) {
      if (!candidate_states_[right].active) {
        continue;
      }
      const std::uint8_t right_note = candidate_output_note(right);
      const std::uint8_t suppression =
          bounded_adjacent_spectral_duplicate_suppression(
              true, true, left_note, right_note, output_masks[left],
              output_masks[right], ready[left], ready[right], errors[left],
              errors[right]);
      if ((suppression & 0x01U) != 0U) {
        spectral_duplicate_suppressed_[left] = true;
      }
      if ((suppression & 0x02U) != 0U) {
        spectral_duplicate_suppressed_[right] = true;
      }
    }
  }
}

void PolyphonicPitchDetector::update_spectral_lane_states(
    const std::array<bool, kMaxCandidates>& selected, bool quiet) noexcept {
  for (SpectralLaneState& state : spectral_lane_states_) {
    const std::size_t candidate = state.candidate_index;
    if (candidate >= static_cast<std::size_t>(candidate_count_) || quiet ||
        profile_mode_ != ProfileMode::m3 ||
        !candidate_states_[candidate].active) {
      if (state.candidate_index != 0xffU) {
        state = {};
      }
    }
  }
  if (quiet || profile_mode_ != ProfileMode::m3) {
    return;
  }
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    if (selected[candidate] && candidate_states_[candidate].active) {
      static_cast<void>(acquire_spectral_lane_state(candidate));
    }
  }
}

bool PolyphonicPitchDetector::configure(double sample_rate,
                                        const PersistentConfig& config) noexcept {
  configured_ = false;
  cells_ = {};
  enabled_cell_indices_ = {};
  enabled_cell_count_ = 0U;
  lower_cents_guard_cells_ = {};
  upper_cents_guard_cells_ = {};
  if (!valid_config(sample_rate, config)) {
    reset();
    return false;
  }

  sample_rate_ = sample_rate;
  dc_pole = std::exp(-kTwoPi * kDcCutoffHz / sample_rate_);
  correlation_decay = std::exp(-1.0 / (kFastEnergySeconds * sample_rate_));
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  diagnostic_input_energy_decay_ = correlation_decay;
  diagnostic_selection_decay_ = correlation_decay;
  diagnostic_selection_window_only_ = false;
  diagnostic_correlation_shadow_only_ = false;
#endif
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
  const std::size_t fine_frequency_window_samples =
      static_cast<std::size_t>(std::clamp(
          std::ceil(kFineFrequencyMinimumEvidenceSeconds * sample_rate_ /
                    (static_cast<double>(kDecisionQuantum) *
                     fine_frequency_decimation_decisions_)),
          2.0,
          static_cast<double>(kFineFrequencyHistoryCapacity)));
  fine_frequency_hann_window_.fill(0.0);
  for (std::size_t sample = 0U; sample < fine_frequency_window_samples;
       ++sample) {
    fine_frequency_hann_window_[sample] =
        0.5 - 0.5 *
                  std::cos(kTwoPi * static_cast<double>(sample) /
                           static_cast<double>(fine_frequency_window_samples -
                                               1U));
  }
  spectral_lane_decimation_ = sample_rate_ >= 32000.0
                                  ? kSpectralLaneDecimation
                                  : 1U;
  group_continuity_decimation_ =
      sample_rate_ >= 40000.0 ? kGroupContinuityDecimation
                              : spectral_lane_decimation_;
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
      if (cell.enabled && enabled_cell_count_ < enabled_cell_indices_.size()) {
        enabled_cell_indices_[enabled_cell_count_++] =
            static_cast<std::uint16_t>(cell_index(candidate, harmonic));
      }
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
  invalidate_fine_frequency_uniform_gram_cache();
  return true;
}

void PolyphonicPitchDetector::set_runtime_config(
    const PersistentConfig& config) noexcept {
  const std::uint8_t previous_max_fret = max_fret_;
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
  if (configured_ && max_fret_ != previous_max_fret) {
    invalidate_fine_frequency_uniform_gram_cache();
  }
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
  if (hann_beat_shadow_buffer_ != nullptr) {
    *hann_beat_shadow_buffer_ = {};
  }
#endif
  selector_group_masks_ = {};
  spectral_lane_states_ = {};
  spectral_lane_decimation_sum_ = 0.0;
  spectral_lane_decimation_count_ = 0U;
  group_continuity_trackers_ = {};
  group_continuity_decimation_sum_ = 0.0;
  group_continuity_decimation_count_ = 0U;
  group_continuity_classification_cursor_ = 0U;
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  unison_reacquisition_states_ = {};
#endif
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  quiet_disposition_ = QuietDisposition::not_quiet;
  last_signal_loss_ = SignalLossDisposition::none;
  selection_dispositions_ = {};
  retained_unison_dispositions_ = {};
  fine_group_dispositions_ = {};
  candidate_admission_diagnostics_ = {};
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    cell.diagnostic_selection_real = 0.0;
    cell.diagnostic_selection_imaginary = 0.0;
#endif
  }
  const auto reset_guard = [](auto& cells) noexcept {
    for (Cell& cell : cells) {
      cell.cosine = 1.0;
      cell.sine = 0.0;
      cell.fast_real = 0.0;
      cell.fast_imaginary = 0.0;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      cell.diagnostic_selection_real = 0.0;
      cell.diagnostic_selection_imaginary = 0.0;
#endif
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
  invalidate_fine_frequency_uniform_gram_cache();
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
PartialAbsoluteCentsEvidence
PolyphonicPitchDetector::partial_absolute_cents_evidence(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return {};
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? partial_detuning_trackers_[candidate]
                   .absolute_cents_evidence()
             : PartialAbsoluteCentsEvidence{};
}
#endif

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

QuietDisposition PolyphonicPitchDetector::quiet_disposition() const noexcept {
  return quiet_disposition_;
}

std::uint8_t PolyphonicPitchDetector::selector_group_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? selector_group_masks_[candidate]
             : 0U;
}

TierCompletionDisposition
PolyphonicPitchDetector::tier_completion_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return TierCompletionDisposition::unavailable;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? tier_completion_dispositions_[candidate]
             : TierCompletionDisposition::unavailable;
}

std::uint8_t PolyphonicPitchDetector::fine_resume_evidence_flags(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& state = candidate_states_[candidate];
  const FineFrequencyEvidenceState& fine =
      fine_frequency_evidence_states_[candidate];
  const std::uint8_t owned = static_cast<std::uint8_t>(
      state.assigned_string_mask | state.midi_voice_mask);
  const std::uint8_t members = string_count(fine.member_mask);
  std::uint8_t flags = state.active ? 0x01U : 0U;
  flags = static_cast<std::uint8_t>(flags | (fine.valid ? 0x02U : 0U));
  flags = static_cast<std::uint8_t>(
      flags | (fine.multi_source_observed ? 0x04U : 0U));
  flags = static_cast<std::uint8_t>(
      flags | (members >= 2U && members <= 4U ? 0x08U : 0U));
  flags = static_cast<std::uint8_t>(
      flags | (owned == fine.member_mask ? 0x10U : 0U));
  flags = static_cast<std::uint8_t>(
      flags | (fine.robust_pairwise_beat_connected ? 0x20U : 0U));
  flags = static_cast<std::uint8_t>(
      flags | (std::isfinite(fine.minimum_pairwise_beat_coherence) &&
                       fine.minimum_pairwise_beat_coherence >=
                           kM3RetainedUnisonMinimumBeatCoherence
                   ? 0x40U
                   : 0U));
  return flags;
}

QuietDisposition PolyphonicPitchDetector::classify_quiet_disposition(
    bool minimum_evidence, bool below_signal_floor, bool had_active_voice,
    bool rapid_mute, bool below_slow_energy_ratio,
    bool multi_voice_evidence,
    SignalLossDisposition last_signal_loss) noexcept {
  if (!minimum_evidence) {
    if (last_signal_loss == SignalLossDisposition::signal_floor) {
      return QuietDisposition::minimum_evidence_after_signal_floor;
    }
    if (last_signal_loss == SignalLossDisposition::inactive_energy_ratio) {
      return QuietDisposition::minimum_evidence_after_inactive_energy_ratio;
    }
    return QuietDisposition::minimum_evidence_startup;
  }
  if (below_signal_floor) {
    return QuietDisposition::below_signal_floor;
  }
  if (below_slow_energy_ratio && rapid_mute) {
    return QuietDisposition::rapid_mute_ratio;
  }
  if (below_slow_energy_ratio && !had_active_voice) {
    return QuietDisposition::inactive_energy_ratio;
  }
  if (!multi_voice_evidence) {
    return QuietDisposition::multi_voice_evidence;
  }
  return QuietDisposition::not_quiet;
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

std::uint8_t PolyphonicPitchDetector::fine_mask_pruning_output_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& state = candidate_states_[candidate];
  if (state.fine_beat_pruning_mask != 0U) {
    return state.fine_beat_pruning_mask;
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  return state.diagnostic_fine_mask_pruning_mask;
#else
  return 0U;
#endif
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

double PolyphonicPitchDetector::fine_frequency_pending_evidence_seconds(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_ || sample_rate_ <= 0.0) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  return static_cast<double>(
             fine_frequency_evidence_states_[candidate].pending_count) *
         static_cast<double>(kDecisionQuantum) *
         static_cast<double>(fine_frequency_decimation_decisions_) *
         static_cast<double>(kFineFrequencyAnalysisStride) / sample_rate_;
}

double PolyphonicPitchDetector::
    fine_frequency_pending_minimum_pairwise_beat_coherence(
        std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate]
                   .pending_minimum_pairwise_beat_coherence
             : 0.0;
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

FineFrequencyUnresolvedReason
PolyphonicPitchDetector::fine_frequency_unresolved_reason(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return FineFrequencyUnresolvedReason::no_history;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return FineFrequencyUnresolvedReason::no_history;
  }
  const FineFrequencyEvidenceState& state =
      fine_frequency_evidence_states_[candidate];
  return state.valid ? FineFrequencyUnresolvedReason::none
                     : state.unresolved_reason;
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

double PolyphonicPitchDetector::fine_frequency_residual_improvement(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate]
                   .residual_improvement
             : 0.0;
}

double PolyphonicPitchDetector::fine_frequency_minimum_member_ratio(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  const FineFrequencyEvidenceState& state =
      fine_frequency_evidence_states_[candidate];
  double minimum = std::numeric_limits<double>::infinity();
  double maximum = 0.0;
  for (std::size_t string = 0U; string < state.component_energy.size();
       ++string) {
    if ((state.member_mask & (1U << string)) == 0U) {
      continue;
    }
    minimum = std::min(minimum, state.component_energy[string]);
    maximum = std::max(maximum, state.component_energy[string]);
  }
  return maximum > kScoreEpsilon && std::isfinite(minimum)
             ? std::sqrt(std::max(0.0, minimum / maximum))
             : 0.0;
}

std::array<double, kMaxVoices>
PolyphonicPitchDetector::fine_frequency_unique_member_improvement(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return {};
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate]
                   .unique_member_improvement
             : std::array<double, kMaxVoices>{};
}

const FineFrequencyMaskResidualTable&
PolyphonicPitchDetector::fine_frequency_mask_residuals(
    std::uint8_t midi_note) const noexcept {
  static const FineFrequencyMaskResidualTable empty{};
  if (midi_note < lowest_note_) {
    return empty;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_frequency_evidence_states_[candidate].mask_residuals
             : empty;
}

const HannBeatShadowTable& PolyphonicPitchDetector::hann_beat_shadow(
    std::uint8_t midi_note) const noexcept {
  static const HannBeatShadowTable empty{};
  if (hann_beat_shadow_buffer_ == nullptr || midi_note < lowest_note_) {
    return empty;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_) &&
                 fine_frequency_evidence_states_[candidate].count != 0U
             ? (*hann_beat_shadow_buffer_)[candidate]
             : empty;
}

double PolyphonicPitchDetector::fine_frequency_minimum_pairwise_beat_coherence(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  const FineFrequencyEvidenceState& state =
      fine_frequency_evidence_states_[candidate];
  return state.valid ? state.minimum_pairwise_beat_coherence : 0.0;
}

double PolyphonicPitchDetector::fine_frequency_pairwise_beat_coherence(
    std::uint8_t midi_note, std::uint8_t member_mask) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  return fine_frequency_evidence_states_[candidate]
      .pairwise_beat_coherence_by_mask[member_mask];
}

double PolyphonicPitchDetector::fine_frequency_added_member_beat_coherence(
    std::uint8_t midi_note, std::uint8_t completion_mask) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  return fine_frequency_evidence_states_[candidate]
      .added_member_beat_coherence_by_completion_mask[completion_mask];
}

double PolyphonicPitchDetector::fine_frequency_added_member_ratio(
    std::uint8_t midi_note, std::uint8_t completion_mask) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  const FineFrequencyEvidenceState& state =
      fine_frequency_evidence_states_[candidate];
  const std::uint8_t added = static_cast<std::uint8_t>(
      completion_mask & static_cast<std::uint8_t>(~state.member_mask));
  if (added == 0U || (added & static_cast<std::uint8_t>(added - 1U)) != 0U) {
    return 0.0;
  }
  std::size_t added_string = 0U;
  while ((added & (1U << added_string)) == 0U) {
    ++added_string;
  }
  const double maximum = *std::max_element(state.component_energy.begin(),
                                           state.component_energy.end());
  return maximum > kScoreEpsilon
             ? std::sqrt(std::max(
                   0.0, state.component_energy[added_string] / maximum))
             : 0.0;
}

std::uint8_t PolyphonicPitchDetector::string_fret_posterior_best(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return static_cast<std::uint8_t>(kMaxVoices);
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return static_cast<std::uint8_t>(kMaxVoices);
  }
  const std::size_t best = string_fret_posteriors_.best_string(candidate);
  return static_cast<std::uint8_t>(
      std::min(best, static_cast<std::size_t>(kMaxVoices)));
}

double PolyphonicPitchDetector::string_fret_posterior_best_probability(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  const std::size_t best = string_fret_posteriors_.best_string(candidate);
  return best < kMaxVoices
             ? string_fret_posteriors_.probability(candidate, best)
             : 0.0;
}

double PolyphonicPitchDetector::string_fret_posterior_margin(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0.0;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0.0;
  }
  const std::uint8_t playable = playable_string_mask(candidate);
  double best = 0.0;
  double second = 0.0;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((playable & (1U << string)) == 0U) {
      continue;
    }
    const double probability =
        string_fret_posteriors_.probability(candidate, string);
    if (probability > best) {
      second = best;
      best = probability;
    } else if (probability > second) {
      second = probability;
    }
  }
  return std::clamp(best - second, 0.0, 1.0);
}

std::array<double, kMaxVoices>
PolyphonicPitchDetector::string_fret_posterior_probabilities(
    std::uint8_t midi_note) const noexcept {
  std::array<double, kMaxVoices> probabilities{};
  if (midi_note < lowest_note_) {
    return probabilities;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return probabilities;
  }
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    probabilities[string] =
        string_fret_posteriors_.probability(candidate, string);
  }
  return probabilities;
}

std::uint8_t PolyphonicPitchDetector::string_fret_posterior_playable_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? playable_string_mask(candidate)
             : 0U;
}

std::uint8_t PolyphonicPitchDetector::profile_unison_proposal_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& state = candidate_states_[candidate];
  return state.diagnostic_unison_temporal
             ? 0U
             : state.diagnostic_unison_proposal_mask;
}

std::uint8_t PolyphonicPitchDetector::temporal_unison_proposal_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& state = candidate_states_[candidate];
  return state.diagnostic_unison_temporal
             ? state.diagnostic_unison_proposal_mask
             : 0U;
}


std::uint8_t PolyphonicPitchDetector::committed_unison_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& state = candidate_states_[candidate];
  return state.active ? state.assigned_string_mask : 0U;
}

std::uint16_t PolyphonicPitchDetector::committed_unison_gap_ticks(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? candidate_states_[candidate].unison_gap_ticks
             : 0U;
}

RetainedUnisonDisposition
PolyphonicPitchDetector::retained_unison_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return RetainedUnisonDisposition::not_applicable;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? retained_unison_dispositions_[candidate]
             : RetainedUnisonDisposition::not_applicable;
}

FineGroupDisposition PolyphonicPitchDetector::fine_group_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return FineGroupDisposition::unresolved;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? fine_group_dispositions_[candidate]
             : FineGroupDisposition::unresolved;
}

#if defined(M3_UNISON_SPECTRAL_SHADOW)
std::uint8_t PolyphonicPitchDetector::group_continuity_cached_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? candidate_states_[candidate].continuity_cached_group_mask
             : 0U;
}

double PolyphonicPitchDetector::group_continuity_cache_age_seconds(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_ || sample_rate_ <= 0.0) {
    return std::numeric_limits<double>::infinity();
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      candidate_states_[candidate].continuity_cached_group_mask == 0U) {
    return std::numeric_limits<double>::infinity();
  }
  return static_cast<double>(
             decision_counter_ -
             candidate_states_[candidate].continuity_cached_group_tick) *
         static_cast<double>(kDecisionQuantum) / sample_rate_;
}

bool PolyphonicPitchDetector::observed_spectral_lane_fingerprint(
    std::uint8_t midi_note,
    UnisonSpectralFingerprint& fingerprint) const noexcept {
  fingerprint = {};
  if (midi_note < lowest_note_) {
    return false;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  const SpectralLaneState* state = find_spectral_lane_state(candidate);
  if (state == nullptr || !state->tracking || !state->tracker.ready()) {
    return false;
  }
  fingerprint = state->tracker.fingerprint();
  return true;
}

bool PolyphonicPitchDetector::spectral_single_source_best_error(
    std::uint8_t midi_note, double& error) const noexcept {
  error = std::numeric_limits<double>::infinity();
  if (midi_note < lowest_note_) {
    return false;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  const SpectralLaneState* state = find_spectral_lane_state(candidate);
  if (state == nullptr || !state->tracking || !state->tracker.ready()) {
    return false;
  }
  UnisonSpectralPhase template_phase = state->tracker.phase();
  if (!factory_unison_spectral_templates_available(template_phase,
                                                    midi_note)) {
    template_phase = UnisonSpectralPhase::unready;
  }
  UnisonSpectralTemplateSet templates;
  if (!factory_unison_spectral_templates(template_phase, midi_note,
                                         templates)) {
    return false;
  }
  const auto scores = score_single_spectral_sources(
      state->tracker.fingerprint(), templates, playable_string_mask(candidate));
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if ((scores.valid_mask & (1U << string)) != 0U) {
      error = std::min(error, scores.error[string]);
    }
  }
  return std::isfinite(error);
}

std::uint8_t PolyphonicPitchDetector::spectral_tier_completion_proposal_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return 0U;
  }
  const CandidateState& candidate_state = candidate_states_[candidate];
  const FineFrequencyEvidenceState& fine =
      fine_frequency_evidence_states_[candidate];
  const std::uint8_t fine_mask = static_cast<std::uint8_t>(
      fine.member_mask & playable_string_mask(candidate));
  return bounded_spectral_tier_completion(
      candidate_state.active, candidate_state.assigned_string_mask, fine_mask,
      playable_string_mask(candidate),
      string_fret_spectral_head_evidence(candidate),
      fine.added_member_beat_coherence, fine.component_energy);
}

ObservedUnisonReacquisitionDisposition
PolyphonicPitchDetector::spectral_reacquisition_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return ObservedUnisonReacquisitionDisposition::no_cache;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? spectral_reacquisition_dispositions_[candidate]
             : ObservedUnisonReacquisitionDisposition::no_cache;
}

UnisonCacheRefreshDisposition
PolyphonicPitchDetector::unison_cache_refresh_disposition(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return UnisonCacheRefreshDisposition::inactive;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? unison_cache_refresh_dispositions_[candidate]
             : UnisonCacheRefreshDisposition::inactive;
}

double PolyphonicPitchDetector::unison_reacquisition_cache_age_seconds(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_ || sample_rate_ <= 0.0) {
    return std::numeric_limits<double>::infinity();
  }
  const std::size_t candidate = midi_note - lowest_note_;
  const UnisonReacquisitionState* state =
      find_unison_reacquisition_state(candidate);
  return state != nullptr
             ? static_cast<double>(decision_counter_ -
                                   state->last_confirmed_tick) *
                   static_cast<double>(kDecisionQuantum) / sample_rate_
             : std::numeric_limits<double>::infinity();
}

std::uint8_t PolyphonicPitchDetector::unison_reacquisition_cache_mask(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const UnisonReacquisitionState* state =
      find_unison_reacquisition_state(midi_note - lowest_note_);
  return state != nullptr ? state->resolved_mask : 0U;
}
#endif

CandidateAdmissionDiagnostics
PolyphonicPitchDetector::candidate_admission_diagnostics(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return {};
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? candidate_admission_diagnostics_[candidate]
             : CandidateAdmissionDiagnostics{};
}

std::uint8_t PolyphonicPitchDetector::group_continuity_diagnostic_flags(
    std::uint8_t midi_note) const noexcept {
  if (midi_note < lowest_note_) {
    return 0U;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  return candidate < static_cast<std::size_t>(candidate_count_)
             ? candidate_states_[candidate]
                   .group_continuity_diagnostic_flags
             : 0U;
}

bool PolyphonicPitchDetector::set_correlation_window_for_diagnostics(
    double seconds, bool selection_only, bool shadow_only) noexcept {
  if (!configured_ || !std::isfinite(seconds) || seconds < 0.020 ||
      seconds > 0.200 || decision_counter_ != 0U || decision_phase_ != 0U ||
      (selection_only && shadow_only)) {
    return false;
  }
  diagnostic_selection_window_only_ = selection_only || shadow_only;
  diagnostic_correlation_shadow_only_ = shadow_only;
  diagnostic_selection_decay_ = std::exp(-1.0 / (seconds * sample_rate_));
  correlation_decay = diagnostic_selection_window_only_
                          ? diagnostic_input_energy_decay_
                          : diagnostic_selection_decay_;
  return true;
}

bool PolyphonicPitchDetector::correlation_window_energy_ratio_for_diagnostics(
    std::uint8_t midi_note, bool fundamental_only,
    double& ratio) const noexcept {
  if (!diagnostic_selection_window_only_ || midi_note < lowest_note_) {
    return false;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  double reference_energy = 0.0;
  double window_energy = 0.0;
  const std::size_t harmonics = fundamental_only ? 1U : kHarmonicCount;
  for (std::size_t harmonic = 0U; harmonic < harmonics; ++harmonic) {
    const Cell& cell = cells_[cell_index(candidate, harmonic)];
    if (!cell.enabled) {
      continue;
    }
    const double weight = kHarmonicWeights[harmonic];
    reference_energy += weight * (cell.fast_real * cell.fast_real +
                                 cell.fast_imaginary * cell.fast_imaginary);
    window_energy += weight *
        (cell.diagnostic_selection_real * cell.diagnostic_selection_real +
         cell.diagnostic_selection_imaginary *
             cell.diagnostic_selection_imaginary);
  }
  if (!std::isfinite(reference_energy) || !std::isfinite(window_energy) ||
      reference_energy <= 1.0e-24 || window_energy < 0.0) {
    return false;
  }
  ratio = window_energy / reference_energy;
  return std::isfinite(ratio);
}

bool PolyphonicPitchDetector::harmonic_correlations_for_diagnostics(
    std::uint8_t midi_note, std::array<double, 6U>& frequencies,
    std::array<std::complex<double>, 6U>& correlations,
    double& signal_energy, double& decay) const noexcept {
  frequencies = {};
  correlations = {};
  if (!configured_ || midi_note < lowest_note_ ||
      midi_note - lowest_note_ >= candidate_count_) {
    return false;
  }
  const std::size_t candidate = midi_note - lowest_note_;
  signal_energy = fast_energy_;
  decay = correlation_decay;
  bool available = false;
  for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
    const Cell& cell = cells_[cell_index(candidate, harmonic)];
    if (!cell.enabled) {
      continue;
    }
    frequencies[harmonic] = sample_rate_ / kTwoPi *
        std::atan2(cell.sine_step, cell.cosine_step);
    correlations[harmonic] =
        std::complex<double>{cell.fast_real, cell.fast_imaginary} *
        std::complex<double>{cell.cosine, cell.sine};
    available = true;
  }
  return available;
}

bool PolyphonicPitchDetector::set_candidate_admission_rescue_for_diagnostics(
    double score_threshold_ratio,
    double fundamental_score_ratio) noexcept {
  if (!std::isfinite(score_threshold_ratio) ||
      !std::isfinite(fundamental_score_ratio) || score_threshold_ratio < 0.0 ||
      score_threshold_ratio > 1.0 || fundamental_score_ratio < 0.0 ||
      fundamental_score_ratio > 1.0) {
    return false;
  }
  diagnostic_candidate_rescue_score_ratio_ = score_threshold_ratio;
  diagnostic_candidate_rescue_fundamental_ratio_ = fundamental_score_ratio;
  diagnostic_candidate_rescue_enabled_ = true;
  return true;
}

bool PolyphonicPitchDetector::set_fretted_position_prior_for_diagnostics(
    double fixed_penalty, double per_fret_penalty) noexcept {
  if (!std::isfinite(fixed_penalty) ||
      !std::isfinite(per_fret_penalty) || fixed_penalty < 0.0 ||
      fixed_penalty > kM3FrettedNotePenalty || per_fret_penalty < 0.0 ||
      per_fret_penalty > kM3FretPenalty) {
    return false;
  }
  diagnostic_fretted_fixed_penalty_ = fixed_penalty;
  diagnostic_fretted_per_fret_penalty_ = per_fret_penalty;
  diagnostic_fretted_prior_enabled_ = true;
  return true;
}

bool PolyphonicPitchDetector::set_decisive_calibrated_selector_for_diagnostics(
    double minimum_margin, std::uint8_t allowed_string_mask) noexcept {
  if (!std::isfinite(minimum_margin) || minimum_margin < 0.0 ||
      minimum_margin > 1.0 || allowed_string_mask == 0U) {
    return false;
  }
  diagnostic_selector_calibration_margin_ = minimum_margin;
  diagnostic_selector_allowed_string_mask_ = allowed_string_mask;
  diagnostic_selector_calibration_enabled_ = true;
  return true;
}

bool PolyphonicPitchDetector::
set_calibrated_dp_replacement_lane_mask_for_diagnostics(
    std::uint8_t allowed_string_mask) noexcept {
  dp_replacement_allowed_string_mask_ = allowed_string_mask;
  return true;
}

#endif

PolyphonicPitchDetector::SpectralHeadEvidence
PolyphonicPitchDetector::string_fret_spectral_head_evidence(
    std::size_t candidate) const noexcept {
  SpectralHeadEvidence result;
  result.best_string.fill(kUnassignedTunerString);
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return result;
  }
  const std::uint8_t midi_note =
      static_cast<std::uint8_t>(lowest_note_ + candidate);
  std::array<double, kHarmonicEvidenceCount> fast_energy{};
  std::array<double, kHarmonicEvidenceCount> settled_energy{};
  double settled_total = 0.0;
  for (std::size_t harmonic = 0U; harmonic < fast_energy.size(); ++harmonic) {
    fast_energy[harmonic] = profile_harmonic_energy(candidate, harmonic);
    settled_energy[harmonic] =
        0.25 * harmonic_energy_memory_[candidate][harmonic] +
        0.75 * long_harmonic_energy_memory_[candidate][harmonic];
    settled_total += settled_energy[harmonic];
  }
  if (settled_total <= kScoreEpsilon) {
    settled_energy = fast_energy;
  }
  const HarmonicEvidence fast = make_harmonic_evidence(fast_energy);
  const HarmonicEvidence settled = make_harmonic_evidence(settled_energy);
  const double transient = harmonic_transient_strength(fast, settled);
  std::array<double, kSpectralTierCount + 1U> best_scores{};
  std::array<double, kSpectralTierCount + 1U> second_scores{};
  best_scores.fill(-std::numeric_limits<double>::infinity());
  second_scores.fill(-std::numeric_limits<double>::infinity());
  const std::uint8_t playable = playable_string_mask(candidate);
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    if ((playable & (1U << string)) == 0U) {
      continue;
    }
    const StringCalibrationPoint* point = calibrator_.bank().point(
        string, midi_note - kM3OpenNotes[string]);
    if (point == nullptr || point->quality == CalibrationPointQuality::missing) {
      continue;
    }
    std::array<double, kHarmonicEvidenceCount> reference_energy{};
    for (std::size_t harmonic = 0U; harmonic < reference_energy.size();
         ++harmonic) {
      reference_energy[harmonic] = point->harmonic_profile_q15[harmonic];
    }
    const HarmonicEvidence reference = make_harmonic_evidence(reference_energy);
    const SpectralTierComparison fast_comparison =
        compare_spectral_tiers(fast, reference);
    const SpectralTierComparison settled_comparison =
        compare_spectral_tiers(settled, reference);
    std::array<double, kSpectralTierCount + 1U> scores{};
    for (std::size_t tier = 0U; tier < kSpectralTierCount; ++tier) {
      scores[tier] = (1.0 - transient) *
                         fast_comparison.tier_log_likelihood[tier] +
                     transient *
                         settled_comparison.tier_log_likelihood[tier];
    }
    scores[kSpectralTierCount] =
        (1.0 - transient) *
            fast_comparison.overtone_separation_log_likelihood +
        transient * settled_comparison.overtone_separation_log_likelihood;
    for (std::size_t head = 0U; head < scores.size(); ++head) {
      if (scores[head] > best_scores[head]) {
        second_scores[head] = best_scores[head];
        best_scores[head] = scores[head];
        result.best_string[head] = static_cast<std::uint8_t>(string);
      } else if (scores[head] > second_scores[head]) {
        second_scores[head] = scores[head];
      }
    }
  }
  for (std::size_t head = 0U; head < best_scores.size(); ++head) {
    if (std::isfinite(best_scores[head]) &&
        std::isfinite(second_scores[head])) {
      result.margin[head] = best_scores[head] - second_scores[head];
    }
  }
  return result;
}

std::uint8_t PolyphonicPitchDetector::spectral_tier_completion_candidate(
    std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
    const SpectralHeadEvidence& spectral) noexcept {
  const std::uint8_t fine_count = string_count(fine_frequency_mask);
  if (fine_count < 2U || fine_count >= 4U) {
    return fine_frequency_mask;
  }
  std::uint8_t qualified = fine_frequency_mask;
  for (std::size_t head = 0U; head < spectral.best_string.size(); ++head) {
    const std::uint8_t string = spectral.best_string[head];
    if (string >= kMaxVoices ||
        (playable_mask & (1U << string)) == 0U ||
        !std::isfinite(spectral.margin[head]) ||
        spectral.margin[head] < kM3SpectralTierCompletionMinimumMargin) {
      continue;
    }
    qualified = static_cast<std::uint8_t>(qualified | (1U << string));
  }
  if (string_count(qualified) != static_cast<std::uint8_t>(fine_count + 1U)) {
    return fine_frequency_mask;
  }
  return qualified;
}

std::uint8_t PolyphonicPitchDetector::bounded_spectral_tier_completion(
    bool active, std::uint8_t current_assignment_mask,
    std::uint8_t fine_frequency_mask, std::uint8_t playable_mask,
    const SpectralHeadEvidence& spectral,
    const std::array<double, kMaxVoices>&
        added_member_beat_coherence,
    const std::array<double, kMaxVoices>& component_energy) noexcept {
  if (!active || current_assignment_mask == 0U) {
    return fine_frequency_mask;
  }
  const std::uint8_t qualified = spectral_tier_completion_candidate(
      fine_frequency_mask, playable_mask, spectral);
  if (qualified == fine_frequency_mask) {
    return fine_frequency_mask;
  }
  const bool current_is_fine_subset =
      (current_assignment_mask &
       static_cast<std::uint8_t>(~fine_frequency_mask)) == 0U;
  const bool current_is_committed_completion =
      current_assignment_mask == qualified;
  if (!current_is_fine_subset && !current_is_committed_completion) {
    return fine_frequency_mask;
  }

  const std::uint8_t added = static_cast<std::uint8_t>(
      qualified & static_cast<std::uint8_t>(~fine_frequency_mask));
  if (added == 0U || (added & static_cast<std::uint8_t>(added - 1U)) != 0U) {
    return fine_frequency_mask;
  }
  std::size_t added_string = 0U;
  while ((added & (1U << added_string)) == 0U) {
    ++added_string;
  }
  const double coherence = added_member_beat_coherence[added_string];
  const double maximum_component = *std::max_element(
      component_energy.begin(), component_energy.end());
  const double added_ratio =
      maximum_component > kScoreEpsilon
          ? std::sqrt(std::max(
                0.0, component_energy[added_string] / maximum_component))
          : 0.0;
  const double minimum_added_member_ratio =
      added_string == 0U
          ? kM3SpectralTierCompletionThickestStringMinimumAddedMemberRatio
          : kM3SpectralTierCompletionMinimumAddedMemberRatio;
  return std::isfinite(coherence) &&
                 coherence >=
                     kM3SpectralTierCompletionMinimumBeatCoherence &&
                 coherence < kM3SpectralTierCompletionMaximumBeatCoherence &&
                 added_ratio >= minimum_added_member_ratio
             ? qualified
             : fine_frequency_mask;
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS) && \
    defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
PolyphonicPitchDetector::SpectralHeadDiagnostics
PolyphonicPitchDetector::string_fret_spectral_heads(
    std::uint8_t midi_note) const noexcept {
  SpectralHeadDiagnostics result;
  result.best_string.fill(kUnassignedTunerString);
  if (midi_note < lowest_note_) {
    return result;
  }
  const SpectralHeadEvidence evidence =
      string_fret_spectral_head_evidence(midi_note - lowest_note_);
  result.best_string = evidence.best_string;
  result.margin = evidence.margin;
  return result;
}
#endif

void PolyphonicPitchDetector::set_calibration_bank(
    const StringCalibrationBank& bank) noexcept {
  calibrator_.set_bank(bank);
  invalidate_fine_frequency_uniform_gram_cache();
  fine_frequency_evidence_states_ = {};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  if (hann_beat_shadow_buffer_ != nullptr) {
    *hann_beat_shadow_buffer_ = {};
  }
#endif
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

void PolyphonicPitchDetector::invalidate_fine_frequency_uniform_gram_cache()
    noexcept {
  fine_frequency_uniform_gram_cache_ = {};
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  if (diagnostic_selection_window_only_) {
    const double selection_mix = 1.0 - diagnostic_selection_decay_;
    cell.diagnostic_selection_real =
        diagnostic_selection_decay_ * cell.diagnostic_selection_real +
        selection_mix * sample * next_cosine;
    cell.diagnostic_selection_imaginary =
        diagnostic_selection_decay_ * cell.diagnostic_selection_imaginary -
        selection_mix * sample * next_sine;
  }
#endif
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

bool PolyphonicPitchDetector::should_handoff_adjacent_coasting_candidate(
    std::size_t candidate,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    const std::array<bool, kMaxCandidates>& selected,
    std::size_t selected_count,
    bool quiet) const noexcept {
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  if (quiet || profile_mode_ != ProfileMode::m3 || candidate >= count ||
      !candidate_states_[candidate].active || selected[candidate]) {
    return false;
  }
  std::uint8_t owned = static_cast<std::uint8_t>(
      candidate_states_[candidate].assigned_string_mask |
      candidate_states_[candidate].midi_voice_mask);
  if (owned == 0U &&
      candidate_states_[candidate].assigned_string < kM3OpenNotes.size()) {
    owned = static_cast<std::uint8_t>(
        1U << candidate_states_[candidate].assigned_string);
  }
  const std::size_t owned_count = string_count(owned);
  const bool multi_string_group = owned_count > 1U;
  const auto onset_ticks = static_cast<std::uint16_t>(std::clamp(
      std::ceil(kM3AdjacentHandoffOnsetSeconds * sample_rate_ /
                static_cast<double>(kDecisionQuantum)),
      1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  for (std::size_t other = 0U; other < count; ++other) {
    const CandidateState& replacement = candidate_states_[other];
    if (other == candidate || !selected[other] ||
        replacement.age_ticks > onset_ticks) {
      continue;
    }
    if (!replacement.active) {
      if (selected_count < 2U ||
          !has_decisive_calibrated_shape(other, count)) {
        continue;
      }
      const std::uint8_t playable = playable_string_mask(other);
      double best_similarity = -1.0;
      std::uint8_t best_string = kUnassignedTunerString;
      const auto note = static_cast<std::uint8_t>(lowest_note_ + other);
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
        if ((playable & bit) == 0U) {
          continue;
        }
        const StringCalibrationPoint* point = calibrator_.bank().point(
            string, note - kM3OpenNotes[string]);
        if (point == nullptr ||
            point->quality == CalibrationPointQuality::missing) {
          continue;
        }
        const double similarity = calibration_similarity(other, string);
        if (similarity > best_similarity) {
          best_similarity = similarity;
          best_string = static_cast<std::uint8_t>(string);
        }
      }
      if (best_string >= kM3OpenNotes.size() ||
          (owned & static_cast<std::uint8_t>(1U << best_string)) == 0U) {
        continue;
      }
    }
    const std::size_t distance =
        other > candidate ? other - candidate : candidate - other;
    if (distance == 1U &&
        has_direct_fundamental_peak(scores, fundamentals, other, count)) {
      // Three- and four-string groups stay on the ordinary signal-aware
      // release path: their physical evidence window is the primary target
      // and an adjacent harmonic must not tear it down. A stale resolved pair
      // may yield once its own direct fundamental is gone; otherwise a short
      // articulation boundary can become several seconds of wrong notes.
      return !multi_string_group ||
             (owned_count == 2U &&
              !has_direct_fundamental_peak(
                  scores, fundamentals, candidate, count) &&
              scores[other] >= scores[candidate]);
    }
  }
  return false;
}

bool PolyphonicPitchDetector::
    should_handoff_coasting_candidate_to_resolved_group(
        std::size_t candidate,
        const std::array<bool, kMaxCandidates>& selected) const noexcept {
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  if (candidate >= count || selected[candidate] ||
      !candidate_states_[candidate].active) {
    return false;
  }
  std::uint8_t owned = static_cast<std::uint8_t>(
      candidate_states_[candidate].assigned_string_mask |
      candidate_states_[candidate].midi_voice_mask);
  if (owned == 0U &&
      candidate_states_[candidate].assigned_string < kM3OpenNotes.size()) {
    owned = static_cast<std::uint8_t>(
        1U << candidate_states_[candidate].assigned_string);
  }
  if (string_count(owned) != 1U) {
    return false;
  }
  for (std::size_t other = 0U; other < count; ++other) {
    if (other == candidate || !selected[other] ||
        !candidate_states_[other].active) {
      continue;
    }
    const std::uint8_t group = selector_group_masks_[other];
    const std::uint8_t members = string_count(group);
    if (members >= 2U && members <= 4U && (group & owned) != 0U) {
      return true;
    }
  }
  return false;
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

bool PolyphonicPitchDetector::has_minimum_signal_evidence(
    std::uint32_t signal_samples, double sample_rate,
    bool had_active_multi_string_group) noexcept {
  if (!std::isfinite(sample_rate) || sample_rate <= 0.0 ||
      signal_samples == 0U) {
    return false;
  }
  return had_active_multi_string_group ||
         static_cast<double>(signal_samples) >=
             sample_rate * kSingleVoiceEvidenceSeconds;
}

bool PolyphonicPitchDetector::is_resolved_unison_resume_candidate(
    bool active, std::uint8_t owned_string_mask, bool fine_valid,
    bool fine_multi_source, bool fine_robust_pairwise_beat_connected,
    double fine_minimum_pairwise_beat_coherence,
    std::uint8_t fine_member_mask) noexcept {
  const std::uint8_t members = string_count(fine_member_mask);
  const bool active_committed_group =
      active && members >= 2U && owned_string_mask == fine_member_mask;
  // A robust three- or four-string fit is rare enough to serve as bounded
  // recent-history evidence after the MIDI assignment has released. Its
  // history still expires at the ordinary fine-evidence gap, and current
  // selector evidence is required before any lane can be emitted again.
  const bool recent_robust_large_group =
      !active && members >= 3U && members <= 4U;
  return fine_valid && fine_multi_source &&
         fine_robust_pairwise_beat_connected &&
         (active_committed_group || recent_robust_large_group) &&
         std::isfinite(fine_minimum_pairwise_beat_coherence) &&
         fine_minimum_pairwise_beat_coherence >=
             kM3RetainedUnisonMinimumBeatCoherence;
}

void PolyphonicPitchDetector::filter_resume_selection(
    bool active_resume,
    const std::array<bool, kMaxCandidates>& active_candidates,
    std::array<bool, kMaxCandidates>& selected,
    std::size_t count) noexcept {
  if (!active_resume) {
    return;
  }
  for (std::size_t candidate = 0U;
       candidate < std::min(count, selected.size()); ++candidate) {
    selected[candidate] = selected[candidate] && active_candidates[candidate];
  }
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

bool PolyphonicPitchDetector::append_transition(
    DetectorDecision& decision, TransitionKind kind, std::uint8_t note,
    std::uint8_t velocity, std::uint8_t voice_id) noexcept {
  const VoiceTransition transition{
      0U, kind, note, velocity, transition_sequence_, voice_id};
  if (!decision.transitions.push_back(transition)) {
    return false;
  }
  ++transition_sequence_;
  return true;
}

std::uint8_t PolyphonicPitchDetector::candidate_output_note(
    std::size_t candidate) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return kTunerNoSignalNote;
  }
  const std::uint8_t detected =
      static_cast<std::uint8_t>(lowest_note_ + candidate);
  const std::uint8_t emitted = candidate_states_[candidate].emitted_note;
  return emitted < 128U ? emitted : detected;
}

std::uint8_t PolyphonicPitchDetector::candidate_midi_output_note(
    std::size_t candidate) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return kTunerNoSignalNote;
  }
  const std::uint8_t projected =
      candidate_states_[candidate].dp_output_projection_note;
  return projected < 128U ? projected : candidate_output_note(candidate);
}

std::int16_t PolyphonicPitchDetector::candidate_output_cents_q8(
    std::size_t candidate, std::int16_t detected_cents_q8) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return detected_cents_q8;
  }
  const std::int32_t detected_note =
      static_cast<std::int32_t>(lowest_note_ + candidate);
  const std::int32_t emitted_note = candidate_output_note(candidate);
  const std::int32_t adjusted =
      static_cast<std::int32_t>(detected_cents_q8) +
      (detected_note - emitted_note) * 100 * 256;
  return static_cast<std::int16_t>(std::clamp<std::int32_t>(
      adjusted, std::numeric_limits<std::int16_t>::min(),
      std::numeric_limits<std::int16_t>::max()));
}

void PolyphonicPitchDetector::change_candidate_output_note(
    DetectorDecision& decision, std::size_t candidate,
    std::uint8_t output_note) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      output_note >= 128U) {
    return;
  }
  CandidateState& state = candidate_states_[candidate];
  const std::uint8_t previous_note = candidate_midi_output_note(candidate);
  const std::uint8_t previous_base = candidate_output_note(candidate);
  if (previous_base == output_note) {
    return;
  }
  const std::uint8_t next_note =
      state.dp_output_projection_note < 128U
          ? state.dp_output_projection_note
          : output_note;
  if (previous_note == next_note) {
    state.emitted_note = output_note;
    return;
  }
  if (state.spectral_duplicate_output_suppressed) {
    state.emitted_note = output_note;
    return;
  }
  const std::uint8_t velocity = dynamic_velocity();
  const std::size_t lane_count =
      midi_routing_ == MidiRouting::per_voice
          ? string_count(state.midi_voice_mask)
          : 1U;
  const std::size_t required = 2U * lane_count;
  if (required > decision.transitions.capacity() -
                     decision.transitions.size()) {
    return;
  }
  if (midi_routing_ == MidiRouting::per_voice) {
    for (std::uint8_t lane = 0U; lane < kMaxVoices; ++lane) {
      if ((state.midi_voice_mask & (1U << lane)) == 0U) {
        continue;
      }
      static_cast<void>(append_transition(
          decision, TransitionKind::note_off, previous_note, 0U, lane));
      static_cast<void>(append_transition(
          decision, TransitionKind::note_on, next_note, velocity, lane));
    }
  } else {
    static_cast<void>(append_transition(
        decision, TransitionKind::note_off, previous_note, 0U));
    static_cast<void>(append_transition(
        decision, TransitionKind::note_on, next_note, velocity));
  }
  state.emitted_note = output_note;
}

bool PolyphonicPitchDetector::change_candidate_dp_output_projection(
    DetectorDecision& decision, std::size_t candidate,
    std::uint8_t output_note) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      (output_note >= 128U && output_note != kTunerNoSignalNote)) {
    return false;
  }
  CandidateState& state = candidate_states_[candidate];
  const std::uint8_t previous_note = candidate_midi_output_note(candidate);
  const std::uint8_t next_note =
      output_note < 128U ? output_note : candidate_output_note(candidate);
  if (previous_note == next_note) {
    state.dp_output_projection_note = output_note;
    return true;
  }
  if (state.spectral_duplicate_output_suppressed) {
    state.dp_output_projection_note = output_note;
    return true;
  }
  const std::size_t lane_count =
      midi_routing_ == MidiRouting::per_voice
          ? string_count(state.midi_voice_mask)
          : 1U;
  if (lane_count == 0U) {
    return false;
  }
  const std::size_t required = 2U * lane_count;
  if (required > decision.transitions.capacity() -
                     decision.transitions.size()) {
    return false;
  }
  const std::uint8_t velocity = dynamic_velocity();
  if (midi_routing_ == MidiRouting::per_voice) {
    for (std::uint8_t lane = 0U; lane < kMaxVoices; ++lane) {
      if ((state.midi_voice_mask & (1U << lane)) == 0U) {
        continue;
      }
      static_cast<void>(append_transition(
          decision, TransitionKind::note_off, previous_note, 0U, lane));
      static_cast<void>(append_transition(
          decision, TransitionKind::note_on, next_note, velocity, lane));
    }
  } else {
    static_cast<void>(append_transition(
        decision, TransitionKind::note_off, previous_note, 0U));
    static_cast<void>(append_transition(
        decision, TransitionKind::note_on, next_note, velocity));
  }
  state.dp_output_projection_note = output_note;
  return true;
}

void PolyphonicPitchDetector::update_calibrated_output_notes(
    DetectorDecision& decision,
    const std::array<bool, kMaxCandidates>& selected,
    std::size_t selected_note_count) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }
  const std::uint16_t minimum_age = static_cast<std::uint16_t>(std::clamp(
      std::ceil(kM3CalibratedOutputMinimumAgeSeconds * sample_rate_ /
                static_cast<double>(kDecisionQuantum)),
      1.0,
      static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    std::uint8_t member_mask = state.assigned_string_mask;
    if (member_mask == 0U && state.assigned_string < kM3OpenNotes.size()) {
      member_mask = static_cast<std::uint8_t>(1U << state.assigned_string);
    }
    const bool single_member = string_count(member_mask) == 1U;
    if (!selected[candidate] || !state.active || selected_note_count < 2U ||
        state.age_ticks < minimum_age || !single_member ||
        !phase_cents_states_[candidate].output_projection_valid) {
      state.calibrated_output_target = kTunerNoSignalNote;
      state.calibrated_output_ticks = 0U;
      continue;
    }
    std::uint8_t string = 0U;
    while ((member_mask & (1U << string)) == 0U) {
      ++string;
    }
    const double cents = phase_cents_states_[candidate].cents;
    if (!std::isfinite(cents)) {
      state.calibrated_output_target = kTunerNoSignalNote;
      state.calibrated_output_ticks = 0U;
      continue;
    }
    const auto cents_q8 = static_cast<std::int16_t>(std::clamp<long>(
        std::lround(cents * 256.0),
        std::numeric_limits<std::int16_t>::min(),
        std::numeric_limits<std::int16_t>::max()));
    const std::uint8_t detected_note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
    const CalibratedNoteProjection projection = project_calibrated_note(
        detected_note, cents_q8, true, string, calibrator_.bank(), max_fret_,
        kM3CalibratedOutputMinimumImprovementCents);
    bool trusted_projection = projection.changed;
    if (trusted_projection) {
      const std::size_t projected_fret =
          projection.note - kM3OpenNotes[string];
      const StringCalibrationPoint* projected_point =
          calibrator_.bank().point(string, projected_fret);
      const double observed_pitch =
          100.0 * static_cast<double>(detected_note) + cents;
      const double projected_center =
          projected_point == nullptr
              ? std::numeric_limits<double>::infinity()
              : 100.0 * static_cast<double>(projection.note) +
                    static_cast<double>(projected_point->cents_offset_q8) /
                        256.0;
      trusted_projection =
          projected_point != nullptr &&
          projected_point->quality != CalibrationPointQuality::missing &&
          std::abs(observed_pitch - projected_center) <=
              kM3CalibratedOutputMaximumProjectedErrorCents;
    }
    if (!trusted_projection) {
      if (candidate_output_note(candidate) == detected_note) {
        state.calibrated_output_target = kTunerNoSignalNote;
        state.calibrated_output_ticks = 0U;
        continue;
      }
      if (state.calibrated_output_target != detected_note) {
        state.calibrated_output_target = detected_note;
        state.calibrated_output_ticks = 1U;
        continue;
      }
      if (state.calibrated_output_ticks <
          std::numeric_limits<std::uint8_t>::max()) {
        ++state.calibrated_output_ticks;
      }
      if (state.calibrated_output_ticks >=
          kM3CalibratedOutputConsensusDecisions) {
        change_candidate_output_note(decision, candidate, detected_note);
        state.calibrated_output_target = kTunerNoSignalNote;
        state.calibrated_output_ticks = 0U;
      }
      continue;
    }
    bool collision = false;
    for (std::size_t other = 0U;
         other < static_cast<std::size_t>(candidate_count_); ++other) {
      if (other == candidate) {
        continue;
      }
      const std::uint8_t other_detected =
          static_cast<std::uint8_t>(lowest_note_ + other);
      collision = collision ||
                  (selected[other] && other_detected == projection.note) ||
                  (candidate_states_[other].active &&
                   candidate_output_note(other) == projection.note);
    }
    if (collision) {
      change_candidate_output_note(decision, candidate, detected_note);
      state.calibrated_output_target = kTunerNoSignalNote;
      state.calibrated_output_ticks = 0U;
      continue;
    }
    if (state.calibrated_output_target != projection.note) {
      state.calibrated_output_target = projection.note;
      state.calibrated_output_ticks = 1U;
      continue;
    }
    if (state.calibrated_output_ticks <
        std::numeric_limits<std::uint8_t>::max()) {
      ++state.calibrated_output_ticks;
    }
    if (state.calibrated_output_ticks <
        kM3CalibratedOutputConsensusDecisions) {
      continue;
    }
    change_candidate_output_note(decision, candidate, projection.note);
  }
}

bool PolyphonicPitchDetector::append_candidate_note_on(
    DetectorDecision& decision, std::size_t candidate,
    std::uint8_t velocity) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  CandidateState& state = candidate_states_[candidate];
  state.spectral_duplicate_output_suppressed = false;
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
    const std::size_t required = string_count(desired);
    if (required > decision.transitions.capacity() -
                       decision.transitions.size()) {
      return false;
    }
    for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((desired & (1U << string)) != 0U) {
        if (!append_transition(decision, TransitionKind::note_on, note,
                               velocity, string)) {
          return false;
        }
      }
    }
    state.emitted_note = note;
    state.midi_voice_mask = desired;
    harmonic_energy_memory_[candidate] = {};
    long_harmonic_energy_memory_[candidate] = {};
    harmonic_memory_updates_[candidate] = 0U;
    return true;
  }
  if (!append_transition(decision, TransitionKind::note_on, note, velocity)) {
    return false;
  }
  state.emitted_note = note;
  harmonic_energy_memory_[candidate] = {};
  long_harmonic_energy_memory_[candidate] = {};
  harmonic_memory_updates_[candidate] = 0U;
  return true;
}

bool PolyphonicPitchDetector::append_candidate_note_off(
    DetectorDecision& decision, std::size_t candidate) noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_)) {
    return false;
  }
  CandidateState& state = candidate_states_[candidate];
  if (state.spectral_duplicate_output_suppressed) {
    return true;
  }
  const auto note = candidate_midi_output_note(candidate);
  if (profile_mode_ == ProfileMode::m3 &&
      midi_routing_ == MidiRouting::per_voice) {
    const std::size_t required = string_count(state.midi_voice_mask);
    if (required > decision.transitions.capacity() -
                       decision.transitions.size()) {
      return false;
    }
    for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((state.midi_voice_mask & (1U << string)) != 0U) {
        if (!append_transition(decision, TransitionKind::note_off, note, 0U,
                               string)) {
          return false;
        }
      }
    }
    return true;
  }
  if (decision.transitions.size() == decision.transitions.capacity()) {
    return false;
  }
  return append_transition(decision, TransitionKind::note_off, note, 0U);
}

bool PolyphonicPitchDetector::append_atomic_candidate_handoff(
    DetectorDecision& decision, std::size_t incumbent, std::size_t target,
    std::uint8_t velocity) noexcept {
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  if (incumbent >= count || target >= count || incumbent == target) {
    return false;
  }
  CandidateState& incumbent_state = candidate_states_[incumbent];
  CandidateState& target_state = candidate_states_[target];
  if (!incumbent_state.active || target_state.active) {
    return false;
  }

  std::size_t off_count = 1U;
  std::size_t on_count = 1U;
  if (profile_mode_ == ProfileMode::m3 &&
      midi_routing_ == MidiRouting::per_voice) {
    off_count = string_count(incumbent_state.midi_voice_mask);
    std::uint8_t desired = target_state.assigned_string_mask;
    if (desired == 0U && target_state.assigned_string < kM3OpenNotes.size()) {
      desired = static_cast<std::uint8_t>(1U << target_state.assigned_string);
    }
    on_count = string_count(desired);
    if (off_count == 0U || on_count == 0U) {
      return false;
    }
  }
  const std::size_t required = off_count + on_count;
  if (required > decision.transitions.capacity() -
                     decision.transitions.size()) {
    return false;
  }

  if (!append_candidate_note_off(decision, incumbent) ||
      !append_candidate_note_on(decision, target, velocity)) {
    return false;
  }
  incumbent_state = {};
  target_state.active = true;
  target_state.attack_ticks = 0U;
  target_state.evidence_ticks = 0U;
  target_state.evidence_gap_ticks = 0U;
  target_state.release_ticks = 0U;
  return true;
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

bool PolyphonicPitchDetector::has_decisive_calibrated_shape(
    std::size_t candidate, std::size_t count) const noexcept {
  return has_calibrated_shape_thresholds(
      candidate, count, kM3IsolatedLowerOctaveMinimumSimilarity,
      kM3IsolatedLowerOctaveMinimumMargin);
}

bool PolyphonicPitchDetector::has_calibrated_shape_thresholds(
    std::size_t candidate, std::size_t count,
    double minimum_similarity, double minimum_margin) const noexcept {
  if (candidate >= count || calibrator_.bank().calibrated_string_mask == 0U) {
    return false;
  }
  const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
  const std::uint8_t playable = playable_string_mask(candidate);
  double best = -1.0;
  double second = -1.0;
  std::size_t playable_count = 0U;
  std::size_t measured_count = 0U;
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
    ++measured_count;
    const double similarity = calibration_similarity(candidate, string);
    if (similarity > best) {
      second = best;
      best = similarity;
    } else if (similarity > second) {
      second = similarity;
    }
  }
  return has_decisive_calibrated_shape_thresholds(
      playable_count, measured_count, best, second, minimum_similarity,
      minimum_margin);
}

bool PolyphonicPitchDetector::has_decisive_calibrated_shape_thresholds(
    std::size_t playable_count, std::size_t measured_count,
    double best_similarity, double second_similarity,
    double minimum_similarity, double minimum_margin) noexcept {
  return playable_count != 0U && measured_count == playable_count &&
         best_similarity >= minimum_similarity &&
         best_similarity - second_similarity >= minimum_margin;
}

bool PolyphonicPitchDetector::has_isolated_shadow_context(
    std::uint8_t other_eligible, std::uint8_t other_active,
    bool sole_other_is_harmonic) noexcept {
  return other_active == 0U &&
         (other_eligible == 0U ||
          (other_eligible == 1U && sole_other_is_harmonic));
}

bool PolyphonicPitchDetector::has_isolated_third_partial_context(
    std::size_t candidate, std::size_t strongest_other,
    std::uint8_t other_eligible, std::uint8_t other_active,
    bool strongest_other_has_decisive_shape) noexcept {
  return other_eligible == 1U && other_active == 0U &&
         strongest_other > candidate && strongest_other - candidate == 19U &&
         !strongest_other_has_decisive_shape;
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
  selector_group_masks_ = {};
  if (dp_replacement_allowed_string_mask_ != 0U) {
    selector_dp_evicted_candidates_ = {};
    selector_atomic_handoff_targets_ = {};
    selector_atomic_handoff_target_for_incumbent_ = {};
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  selection_dispositions_.fill(SelectionDisposition::below_threshold);
  retained_unison_dispositions_.fill(
      RetainedUnisonDisposition::not_applicable);
  diagnostic_selector_string_masks_.fill(0U);
#endif
#if defined(M3_TESTING)
  selection_work_ = {};
#endif

  std::array<bool, kMaxCandidates> raw_eligible{};
  std::array<double, kMaxCandidates> selection_scores{};
  std::array<bool, kMaxCandidates> calibrated_band_rescue_candidates{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  // Shadow-only candidates admitted below the ordinary coherence threshold.
  // They are deliberately withheld from the primary DP so the experiment can
  // measure additive recovery without evicting a production-selected pitch.
  std::array<bool, kMaxCandidates> diagnostic_rescue_candidates{};
#endif
  const bool narrow_profile = max_fret_ <= 2U;
  double fretted_fixed_penalty = kM3FrettedNotePenalty;
  double fretted_per_fret_penalty = kM3FretPenalty;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  if (diagnostic_fretted_prior_enabled_) {
    fretted_fixed_penalty = diagnostic_fretted_fixed_penalty_;
    fretted_per_fret_penalty = diagnostic_fretted_per_fret_penalty_;
  }
#endif
  const bool narrow_ready =
      !narrow_profile ||
      static_cast<double>(narrow_signal_samples_) >=
          sample_rate_ * kNarrowFundamentalSeconds;
  if (!narrow_ready) {
    return;
  }
  const std::uint16_t robust_confirmation_ticks =
      static_cast<std::uint16_t>(std::clamp(
          std::ceil(kM3RetainedUnisonRobustConfirmationSeconds *
                    sample_rate_ / static_cast<double>(kDecisionQuantum)),
          1.0,
          static_cast<double>(std::numeric_limits<std::uint16_t>::max())));
  std::size_t retained_unison = count;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t committed = state.assigned_string_mask;
    const std::uint8_t members = string_count(committed);
    if (!state.active || members < 2U || members > 4U ||
        members > static_cast<std::uint8_t>(max_polyphony_)) {
      continue;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    auto& retained_disposition = retained_unison_dispositions_[candidate];
#endif
    if (!fine.valid || !fine.multi_source_observed) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      retained_disposition = RetainedUnisonDisposition::fine_unavailable;
#endif
      continue;
    }
    if (fine.member_mask != committed) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      retained_disposition = RetainedUnisonDisposition::fine_mask_mismatch;
#endif
      continue;
    }
    const bool minimum_pairwise_beat_supported =
        fine.minimum_pairwise_beat_coherence >=
        kM3RetainedUnisonMinimumBeatCoherence;
    const bool robust_multi_pair_beat_supported =
        members >= 3U && fine.robust_pairwise_beat_connected &&
        fine.minimum_pairwise_beat_coherence >=
            kM3RetainedUnisonRobustWeakPairFloor &&
        state.committed_unison_confirmed_ticks >=
            robust_confirmation_ticks;
    if (!minimum_pairwise_beat_supported &&
        !robust_multi_pair_beat_supported) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      retained_disposition = RetainedUnisonDisposition::beat_below_gate;
#endif
      continue;
    }
    if ((committed & playable_string_mask(candidate)) != committed) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      retained_disposition = RetainedUnisonDisposition::unplayable;
#endif
      continue;
    }
    if (scores[candidate] <=
        threshold * kM3RetainedUnisonDecayFloorRatio) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      retained_disposition = RetainedUnisonDisposition::below_decay_floor;
#endif
      continue;
    }
    // Every eligible committed group remains an atomic selector option. The
    // highest-scoring group still receives the priority seed below, while any
    // additional disjoint group must pay its true physical lane count in the
    // DP rather than masquerading as one voice.
    selector_group_masks_[candidate] = committed;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    retained_disposition = RetainedUnisonDisposition::retained;
#endif
    if (retained_unison != count &&
        scores[candidate] <= scores[retained_unison]) {
      continue;
    }
    retained_unison = candidate;
  }

  // Reserve a measured one-lane tier completion as one atomic selector
  // option before the physical-string DP runs.  The earlier inference-only
  // placement could describe the completed group after selection, but it
  // could not protect that group from being split during the selection that
  // produced the same frame.  This remains narrower than ordinary candidate
  // admission: an active pitch, a valid 2--3 member fine fit, direct local
  // fundamental evidence, and the normal retained-score floor are all
  // required before the existing beat/component tier gate may add one lane.
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t playable = playable_string_mask(candidate);
    const std::uint8_t fine_group =
        static_cast<std::uint8_t>(fine.member_mask & playable);
    const std::uint8_t fine_members = string_count(fine_group);
    if (!state.active || !fine.valid || !fine.multi_source_observed ||
        fine_members < 2U || fine_members >= 4U ||
        scores[candidate] <=
            threshold * kM3RetainedUnisonDecayFloorRatio ||
        !has_direct_fundamental_peak(scores, fundamentals, candidate, count)) {
      continue;
    }
    const std::uint8_t completion = bounded_spectral_tier_completion(
        true, state.assigned_string_mask, fine_group, playable,
        string_fret_spectral_head_evidence(candidate),
        fine.added_member_beat_coherence, fine.component_energy);
    const std::uint8_t completion_members = string_count(completion);
    if (completion != fine_group && completion_members >= 2U &&
        completion_members <= 4U &&
        completion_members <= static_cast<std::uint8_t>(max_polyphony_)) {
      selector_group_masks_[candidate] = completion;
    }
  }
  double maximum_narrow_fundamental = 0.0;
  if (narrow_profile) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      maximum_narrow_fundamental =
          std::max(maximum_narrow_fundamental, narrow_fundamentals[candidate]);
    }
  }
  constexpr std::size_t kPitchBandCount = 4U;
  constexpr std::uint8_t kPitchBandSemitones = 12U;
  std::array<double, kPitchBandCount> pitch_band_score_peak{};
  std::array<double, kPitchBandCount> pitch_band_fundamental_peak{};
  const auto pitch_band_for_note = [](std::uint8_t note) noexcept {
    const std::uint8_t offset =
        note > kM3OpenNotes.front()
            ? static_cast<std::uint8_t>(note - kM3OpenNotes.front())
            : 0U;
    return std::min<std::size_t>(
        kPitchBandCount - 1U, offset / kPitchBandSemitones);
  };
  if (!narrow_profile) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      if (playable_string_mask(candidate) == 0U) {
        continue;
      }
      const std::size_t band = pitch_band_for_note(
          static_cast<std::uint8_t>(lowest_note_ + candidate));
      pitch_band_score_peak[band] =
          std::max(pitch_band_score_peak[band], scores[candidate]);
      pitch_band_fundamental_peak[band] = std::max(
          pitch_band_fundamental_peak[band], fundamentals[candidate]);
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
      bool calibrated_band_rescue = false;
      if (!calibrated_direct && scores[candidate] <= threshold &&
          scores[candidate] >
              threshold * kM3CalibratedBandRescueScoreRatio &&
          fundamentals[candidate] >=
              kM3CalibratedBandRescueFundamentalRatio * scores[candidate] &&
          has_direct_fundamental_peak(scores, fundamentals, candidate, count) &&
          (is_local_peak(scores, candidate, count) ||
           has_m3_candidate_evidence(scores, fundamentals, candidate, count))) {
        const std::size_t band = pitch_band_for_note(
            static_cast<std::uint8_t>(lowest_note_ + candidate));
        const double score_peak_ratio =
            scores[candidate] /
            std::max(pitch_band_score_peak[band], kScoreEpsilon);
        const double fundamental_peak_ratio =
            fundamentals[candidate] /
            std::max(pitch_band_fundamental_peak[band], kScoreEpsilon);
        double best_similarity = 0.0;
        double second_similarity = 0.0;
        std::uint8_t best_string = kUnassignedTunerString;
        const auto note =
            static_cast<std::uint8_t>(lowest_note_ + candidate);
        const std::uint8_t playable = playable_string_mask(candidate);
        for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          if ((playable & bit) == 0U) {
            continue;
          }
          const StringCalibrationPoint* point = calibrator_.bank().point(
              string, note - kM3OpenNotes[string]);
          if (point == nullptr ||
              point->quality == CalibrationPointQuality::missing) {
            continue;
          }
          const double similarity = calibration_similarity(candidate, string);
          if (similarity > best_similarity) {
            second_similarity = best_similarity;
            best_similarity = similarity;
            best_string = static_cast<std::uint8_t>(string);
          } else if (similarity > second_similarity) {
            second_similarity = similarity;
          }
        }
        calibrated_band_rescue =
            score_peak_ratio >= kM3CalibratedBandRescueScorePeakRatio &&
            fundamental_peak_ratio >=
                kM3CalibratedBandRescueFundamentalPeakRatio &&
            best_string >= kM3CalibratedBandRescueMinimumString &&
            best_similarity >= kM3CalibratedBandRescueMinimumSimilarity &&
            best_similarity - second_similarity >=
                kM3CalibratedBandRescueMinimumMargin;
      }
      calibrated_band_rescue_candidates[candidate] = calibrated_band_rescue;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      const bool diagnostic_rescue =
          diagnostic_candidate_rescue_enabled_ &&
          scores[candidate] >
              threshold * diagnostic_candidate_rescue_score_ratio_ &&
          fundamentals[candidate] >=
              diagnostic_candidate_rescue_fundamental_ratio_ *
                  scores[candidate] &&
          has_direct_fundamental_peak(scores, fundamentals, candidate, count) &&
          (is_local_peak(scores, candidate, count) ||
           has_m3_candidate_evidence(scores, fundamentals, candidate, count));
      diagnostic_rescue_candidates[candidate] =
          diagnostic_rescue && scores[candidate] <= threshold &&
          !calibrated_direct;
#else
      constexpr bool diagnostic_rescue = false;
#endif
      if (scores[candidate] <= threshold && !calibrated_direct &&
          !calibrated_band_rescue && !diagnostic_rescue) {
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
          fretted_fixed_penalty +
          fretted_per_fret_penalty * static_cast<double>(max_fret_) + 0.01;
      selection_scores[candidate] =
          calibrated_direct ? std::max(normalized_score, calibrated_floor)
                            : normalized_score;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (diagnostic_selector_calibration_enabled_ &&
          raw_eligible[candidate]) {
        const CandidateAdmissionDiagnostics& diagnostic =
            candidate_admission_diagnostics_[candidate];
        const double margin = diagnostic.best_calibration_similarity -
                              diagnostic.second_calibration_similarity;
        if (diagnostic.best_calibrated_string < kMaxVoices &&
            (diagnostic_selector_allowed_string_mask_ &
             static_cast<std::uint8_t>(
                 1U << diagnostic.best_calibrated_string)) != 0U &&
            diagnostic.calibrated_string_mask ==
                diagnostic.playable_string_mask &&
            diagnostic.best_calibration_similarity >=
                kM3IsolatedLowerOctaveMinimumSimilarity &&
            margin >= diagnostic_selector_calibration_margin_ &&
            diagnostic.direct_fundamental_peak &&
            (diagnostic.local_peak || diagnostic.candidate_evidence)) {
          diagnostic_selector_string_masks_[candidate] =
              static_cast<std::uint8_t>(
                  1U << diagnostic.best_calibrated_string);
        }
      }
#endif
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
  std::array<std::size_t, kMaxCandidates> shadowed_by{};
  shadowed_by.fill(count);
  std::array<std::uint8_t, kMaxCandidates> shadow_kinds{};
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
      const bool harmonic_shadow =
          is_harmonic_shadow(candidate, stronger, fundamentals);
      const bool lower_cross_harmonic_shadow =
          is_m3_lower_cross_harmonic_shadow(candidate, stronger,
                                            fundamentals);
      if ((harmonic_shadow || lower_cross_harmonic_shadow) &&
          !distinct_lower_peak && !distinct_higher_peak) {
        shadowed = true;
        shadowed_by[candidate] = stronger;
        shadow_kinds[candidate] = static_cast<std::uint8_t>(
            (harmonic_shadow ? 1U : 0U) |
            (lower_cross_harmonic_shadow ? 2U : 0U));
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        CandidateAdmissionDiagnostics& diagnostic =
            candidate_admission_diagnostics_[candidate];
        diagnostic.spectral_shadow_interval = static_cast<std::int8_t>(
            static_cast<int>(stronger) - static_cast<int>(candidate));
        diagnostic.spectral_shadow_fundamental_ratio =
            fundamentals[candidate] /
            std::max(fundamentals[stronger], kScoreEpsilon);
        diagnostic.spectral_shadow_kind = static_cast<std::uint8_t>(
            (harmonic_shadow ? 1U : 0U) |
            (lower_cross_harmonic_shadow ? 2U : 0U));
#endif
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
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (shadowed_by[candidate] == count) {
      continue;
    }
    const std::size_t stronger = shadowed_by[candidate];
    std::uint8_t other_eligible = 0U;
    std::uint8_t other_active = 0U;
    std::size_t strongest_other = count;
    for (std::size_t other = 0U; other < count; ++other) {
      if (other == candidate || other == stronger) {
        continue;
      }
      if (spectral_eligible[other]) {
        ++other_eligible;
        if (strongest_other == count ||
            scores[other] > scores[strongest_other]) {
          strongest_other = other;
        }
      }
      if (candidate_states_[other].active) {
        ++other_active;
      }
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    CandidateAdmissionDiagnostics& diagnostic =
        candidate_admission_diagnostics_[candidate];
    diagnostic.spectral_shadow_other_eligible_count = other_eligible;
    diagnostic.spectral_shadow_other_active_count = other_active;
    if (strongest_other != count) {
      diagnostic.spectral_shadow_strongest_other_interval =
          static_cast<std::int8_t>(static_cast<int>(strongest_other) -
                                   static_cast<int>(candidate));
      diagnostic.spectral_shadow_strongest_other_evidence =
          static_cast<std::uint8_t>(
              (has_direct_fundamental_peak(scores, fundamentals,
                                           strongest_other, count)
                   ? 1U
                   : 0U) |
              (is_local_peak(scores, strongest_other, count) ? 2U : 0U) |
              (has_m3_candidate_evidence(scores, fundamentals,
                                         strongest_other, count)
                   ? 4U
                   : 0U) |
              (candidate_states_[strongest_other].active ? 8U : 0U) |
              (has_decisive_calibrated_shape(strongest_other, count)
                   ? 16U
                   : 0U));
    }
#endif
    // A strong third partial can itself pass the local/direct tests despite
    // lacking a decisive physical-string shape. Treat exactly that lone,
    // inactive +19-semitone candidate as part of the isolated source; a
    // calibrated or already-active chord voice never receives this exception.
    const bool sole_other_is_harmonic =
        strongest_other != count &&
        has_isolated_third_partial_context(
            candidate, strongest_other, other_eligible, other_active,
            has_decisive_calibrated_shape(strongest_other, count));
    const bool isolated_calibrated_lower_octave =
        stronger == candidate + 12U && shadow_kinds[candidate] == 1U &&
        has_isolated_shadow_context(other_eligible, other_active,
                                    sole_other_is_harmonic) &&
        is_local_peak(scores, candidate, count) &&
        has_m3_candidate_evidence(scores, fundamentals, candidate, count) &&
        !has_direct_fundamental_peak(scores, fundamentals, candidate, count) &&
        has_calibrated_shape_thresholds(
            candidate, count,
            sole_other_is_harmonic
                ? kM3IsolatedThirdPartialMinimumSimilarity
                : kM3IsolatedLowerOctaveMinimumSimilarity,
            sole_other_is_harmonic
                ? kM3IsolatedThirdPartialMinimumMargin
                : kM3IsolatedLowerOctaveMinimumMargin);
    if (isolated_calibrated_lower_octave) {
      spectral_eligible[candidate] = true;
      // This is a classification, not additive admission. In an otherwise
      // isolated frame the measured lower fundamental replaces the octave
      // partial that originally shadowed it.
      spectral_eligible[stronger] = false;
      if (sole_other_is_harmonic) {
        spectral_eligible[strongest_other] = false;
      }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      selection_dispositions_[stronger] =
          SelectionDisposition::spectral_rejected;
      selection_dispositions_[candidate] = SelectionDisposition::dp_evicted;
#endif
    }
  }

  // The measured classifier/tier gates have not qualified. Replay and
  // production therefore share the accepted fine-frequency/beat path; the
  // richer spectral results remain diagnostics and counterfactuals only.
  const std::size_t priority_unison = retained_unison;
  const std::uint8_t priority_unison_mask =
      priority_unison != count ? selector_group_masks_[priority_unison] : 0U;
  const std::uint8_t priority_unison_members =
      string_count(priority_unison_mask);

  const auto selector_string_mask = [this](std::size_t candidate) noexcept {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (candidate < diagnostic_selector_string_masks_.size() &&
        diagnostic_selector_string_masks_[candidate] != 0U) {
      return diagnostic_selector_string_masks_[candidate];
    }
#endif
    return playable_string_mask(candidate);
  };

  std::array<bool, kMaxCandidates> in_pool{};
  std::size_t pool_count = 0U;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const std::uint8_t group_mask = selector_group_masks_[candidate];
    const std::uint8_t group_members = string_count(group_mask);
    if (candidate == priority_unison || group_members < 2U ||
        group_members > 4U ||
        group_members > static_cast<std::uint8_t>(max_polyphony_) ||
        pool_count >= m3_pool_.size()) {
      continue;
    }
    in_pool[candidate] = true;
    const double group_score =
        selection_scores[candidate] > 0.0
            ? selection_scores[candidate]
            : scores[candidate] / std::max(fast_energy_, kScoreEpsilon);
    m3_pool_[pool_count++] = M3PoolCandidate{
        static_cast<std::uint8_t>(candidate), group_mask, group_score, true};
  }
  for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
    const std::uint8_t string_bit = static_cast<std::uint8_t>(1U << string);
    std::array<bool, kMaxCandidates> selected_for_string{};
    for (std::size_t rank = 0U;
         rank < static_cast<std::size_t>(max_polyphony_); ++rank) {
      std::size_t best = count;
      for (std::size_t candidate = 0U; candidate < count; ++candidate) {
        if (candidate == priority_unison || !spectral_eligible[candidate] ||
            selected_for_string[candidate] ||
            calibrated_band_rescue_candidates[candidate] ||
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
            diagnostic_rescue_candidates[candidate] ||
#endif
            (selector_string_mask(candidate) & string_bit) == 0U) {
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
          static_cast<std::uint8_t>(best), selector_string_mask(best),
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
  if (priority_unison != count) {
    M3DpState& seed = m3_dp_states_[priority_unison_mask];
    seed.valid = true;
    seed.score_sum =
        scores[priority_unison] / std::max(fast_energy_, kScoreEpsilon);
    seed.voice_count = priority_unison_members;
    seed.retained_active = 1U;
  } else {
    m3_dp_states_[0U].valid = true;
  }
  for (std::size_t option_index = 0U; option_index < pool_count; ++option_index) {
    const M3PoolCandidate& option = m3_pool_[option_index];
    std::uint8_t atomic_group =
        selector_group_masks_[option.detector_index];
    std::uint8_t atomic_members = string_count(atomic_group);
    if (atomic_members < 2U) {
      // A resolved fine fit must not make an established group look like one
      // lane to the DP merely because it missed the stronger retention gate.
      // Charge the lanes that assignment will actually expose, but only while
      // live multi-source evidence exactly matches the committed group.
      const CandidateState& state =
          candidate_states_[option.detector_index];
      const FineFrequencyEvidenceState& fine =
          fine_frequency_evidence_states_[option.detector_index];
      const std::uint8_t committed = state.assigned_string_mask;
      const std::uint8_t committed_members = string_count(committed);
      const std::uint8_t fine_members = string_count(fine.member_mask);
      if (state.active && committed_members >= 2U &&
          committed_members <= 4U &&
          fine.valid && fine.multi_source_observed && fine_members >= 2U &&
          fine_members <= 4U &&
          fine.member_mask == committed &&
          (committed & option.string_mask) == committed) {
        atomic_group = committed;
        atomic_members = committed_members;
      }
    }
    if (atomic_members >= 2U) {
      for (std::size_t used = kM3StringMaskCount; used-- > 0U;) {
        const M3DpState state = m3_dp_states_[used];
        if (!state.valid ||
            (static_cast<std::uint8_t>(used) & atomic_group) != 0U ||
            static_cast<std::uint16_t>(state.voice_count) + atomic_members >
                static_cast<std::uint16_t>(max_polyphony_)) {
          continue;
        }
#if defined(M3_TESTING)
        selection_work_.assignment_edges = static_cast<std::uint32_t>(
            selection_work_.assignment_edges + atomic_members);
#endif
        const std::size_t next = used | atomic_group;
        M3DpState proposal = state;
        proposal.valid = true;
        proposal.score_sum += option.score;
        proposal.chosen |= (std::uint64_t{1U} << option_index);
        proposal.voice_count = static_cast<std::uint8_t>(
            proposal.voice_count + atomic_members);
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
      continue;
    }
    std::array<double, kMaxVoices> assignment_scores{};
    const auto note = static_cast<std::uint8_t>(
        lowest_note_ + option.detector_index);
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      const std::uint8_t string_bit =
          static_cast<std::uint8_t>(1U << string);
      if ((option.string_mask & string_bit) == 0U) {
        continue;
      }
      const std::uint8_t fret =
          static_cast<std::uint8_t>(note - kM3OpenNotes[string]);
      double assignment_penalty =
          (open_candidate_count >= kM3OpenChordMinimum ||
           note > kM3OpenNotes.back()) &&
                  fret > 0U
              ? fretted_fixed_penalty +
                    fretted_per_fret_penalty * static_cast<double>(fret)
              : 0.0;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if ((diagnostic_selector_string_masks_[option.detector_index] &
           string_bit) != 0U) {
        assignment_penalty = 0.0;
      }
#endif
      assignment_scores[string] = option.score - assignment_penalty;
    }
    for (std::size_t used = kM3StringMaskCount; used-- > 0U;) {
      const M3DpState state = m3_dp_states_[used];
      if (!state.valid ||
          state.voice_count >= static_cast<std::uint8_t>(max_polyphony_)) {
        continue;
      }
      std::uint8_t available = static_cast<std::uint8_t>(
          option.string_mask & ~static_cast<std::uint8_t>(used));
      while (available != 0U) {
#if defined(__GNUC__) || defined(__clang__)
        const std::size_t string =
            static_cast<std::size_t>(__builtin_ctz(available));
#else
        std::size_t string = 0U;
        while ((available & (1U << string)) == 0U) {
          ++string;
        }
#endif
        const std::uint8_t string_bit =
            static_cast<std::uint8_t>(1U << string);
        available = static_cast<std::uint8_t>(available & (available - 1U));
#if defined(M3_TESTING)
        ++selection_work_.assignment_edges;
#endif
        const std::size_t next = used | string_bit;
        M3DpState proposal = state;
        proposal.valid = true;
        proposal.score_sum += assignment_scores[string];
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
  if (priority_unison != count) {
    selected[priority_unison] = true;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    selection_dispositions_[priority_unison] = SelectionDisposition::selected;
#endif
  }

  M3DpState best{};
  std::uint8_t best_used_mask = 0U;
  for (std::size_t used = 0U; used < m3_dp_states_.size(); ++used) {
    const M3DpState& state = m3_dp_states_[used];
    const bool better =
        state.valid &&
        (!best.valid || state.score_sum > best.score_sum ||
         (state.score_sum == best.score_sum &&
          (state.retained_active > best.retained_active ||
           (state.retained_active == best.retained_active &&
            state.voice_count > best.voice_count))));
    if (better) {
      best = state;
      best_used_mask = static_cast<std::uint8_t>(used);
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
  // The calibrated-band rescue is additive by construction: admit at
  // most one below-threshold direct pitch, only when the production DP already
  // established a non-empty chord and left both a voice slot and a feasible
  // physical string. This prevents the policy from replacing a stronger
  // selected pitch, bypassing Max Polyphony, or inventing a lane.
  if (best.voice_count > 0U &&
      best.voice_count < static_cast<std::uint8_t>(max_polyphony_)) {
    std::size_t rescued = count;
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      bool eligible = calibrated_band_rescue_candidates[candidate];
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      eligible = eligible ||
                 (diagnostic_candidate_rescue_enabled_ &&
                  diagnostic_rescue_candidates[candidate]);
#endif
      if (!eligible ||
          !spectral_eligible[candidate] || selected[candidate] ||
          (playable_string_mask(candidate) &
           ~static_cast<std::uint8_t>(best_used_mask)) == 0U ||
          (rescued != count &&
           selection_scores[candidate] <= selection_scores[rescued])) {
        continue;
      }
      rescued = candidate;
    }
    if (rescued != count) {
      selected[rescued] = true;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      selection_dispositions_[rescued] = SelectionDisposition::selected;
#endif
    }
  }
  if (dp_replacement_allowed_string_mask_ != 0U) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      selector_dp_evicted_candidates_[candidate] =
          in_pool[candidate] && !selected[candidate];
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
  std::array<std::uint8_t, kMaxVoices> spectral_lane_proposals{};
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
        const std::uint8_t joint_group =
            selector_group_masks_[candidate] != 0U
                ? selector_group_masks_[candidate]
                : state.assigned_string_mask;
        reserved_strings = static_cast<std::uint8_t>(
            reserved_strings | (joint_group & ~primary));
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
    std::uint8_t playable = playable_string_mask(candidate);
    const std::uint8_t spectral_lane =
        spectral_lane_assignment(candidate, isolated_selected_voice);
    spectral_lane_proposals[voice] = spectral_lane;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (diagnostic_selector_string_masks_[candidate] != 0U) {
      playable = diagnostic_selector_string_masks_[candidate];
    }
#endif
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
    std::array<double, kHarmonicEvidenceCount> fast_energy{};
    double fast_energy_total = 0.0;
    bool fast_energy_ready = false;
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
      // The observed candidate profile is identical for every physical-string
      // comparison in this decision. Reuse it without carrying audio evidence
      // across decisions or changing the order of its harmonic accumulation.
      if (!fast_energy_ready) {
        for (std::size_t harmonic = 0U; harmonic < fast_energy.size();
             ++harmonic) {
          fast_energy[harmonic] =
              corrected_harmonic_energy(candidate, harmonic);
          fast_energy_total += fast_energy[harmonic];
        }
        fast_energy_ready = true;
      }
      const double fast_similarity = calibration_similarity_from_energy_profile(
          candidate, string, fast_energy, fast_energy_total);
      learned_similarities[string] =
          settled_shape_eligible
              ? settled_calibration_similarity_from_fast_similarity(
                    candidate, string, fast_similarity)
              : fast_similarity;
      best_learned_similarity =
          std::max(best_learned_similarity, learned_similarities[string]);
      learned_cents[string] =
          static_cast<double>(point->cents_offset_q8) / 256.0;
      learned_sum += learned_similarities[string];
      ++learned_count;
    }
    std::array<double, kHarmonicEvidenceCount> settled_energy{};
    double transient_strength = 0.0;
    const bool posterior_available =
        all_playable_profiles_learned && learned_count > 0U;
    if (posterior_available) {
      double settled_energy_total = 0.0;
      for (std::size_t harmonic = 0U; harmonic < fast_energy.size();
           ++harmonic) {
        settled_energy[harmonic] =
            0.25 * harmonic_energy_memory_[candidate][harmonic] +
            0.75 * long_harmonic_energy_memory_[candidate][harmonic];
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      candidate_admission_diagnostics_[candidate]
          .string_fret_onset_strength = posterior_frame.onset_strength;
#endif
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
    CandidateState& state = candidate_states_[candidates[voice]];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidates[voice]];
    state.assigned_string =
        static_cast<std::uint8_t>((best.strings >> (voice * 3U)) & 0x07U);
    const bool physical_group_emerging =
        beat_evidence_states_[candidates[voice]].valid ||
        string_count(fine.member_mask) > 1U ||
        string_count(fine.pending_member_mask) > 1U;
    const bool isolated_spectral_reassignment =
        isolated_selected_voice && spectral_lane_proposals[voice] != 0U &&
        !fine.valid && string_count(fine.member_mask) <= 1U &&
        string_count(fine.pending_member_mask) <= 1U;
    if (physical_group_emerging && !isolated_spectral_reassignment) {
      state.spectral_lane_mask = 0U;
    } else if (spectral_lane_proposals[voice] != 0U) {
      state.spectral_lane_mask = spectral_lane_proposals[voice];
    } else {
      state.spectral_lane_mask = 0U;
    }
  }
}

void PolyphonicPitchDetector::apply_calibrated_dp_replacements(
    std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet, std::size_t count) noexcept {
  if (profile_mode_ != ProfileMode::m3 || quiet ||
      dp_replacement_allowed_string_mask_ == 0U) {
    return;
  }
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    if (string_count(state.assigned_string_mask) >= 2U ||
        string_count(state.midi_voice_mask) >= 2U ||
        string_count(state.spectral_lane_mask) >= 2U ||
        string_count(state.continuity_lane_mask) >= 2U ||
        string_count(fine.member_mask) >= 2U ||
        string_count(fine.pending_member_mask) >= 2U) {
      return;
    }
  }

  std::array<std::size_t, kMaxVoices> replacement_targets{};
  std::array<std::size_t, kMaxVoices> replacement_incumbents{};
  std::array<double, kMaxVoices> replacement_advantages{};
  std::array<std::size_t, kMaxVoices> active_incumbents{};
  replacement_targets.fill(count);
  replacement_incumbents.fill(count);
  active_incumbents.fill(count);
  std::uint8_t occupied_replaceable_lanes = 0U;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    std::uint8_t owned_mask = state.assigned_string_mask;
    if (owned_mask == 0U && state.assigned_string < kMaxVoices) {
      owned_mask = static_cast<std::uint8_t>(1U << state.assigned_string);
    }
    if (!selected[candidate] || !state.active ||
        state.assigned_string >= kMaxVoices ||
        string_count(owned_mask) != 1U) {
      continue;
    }
    const std::uint8_t bit =
        static_cast<std::uint8_t>(1U << state.assigned_string);
    if ((dp_replacement_allowed_string_mask_ & bit) == 0U ||
        active_incumbents[state.assigned_string] != count) {
      continue;
    }
    active_incumbents[state.assigned_string] = candidate;
    occupied_replaceable_lanes =
        static_cast<std::uint8_t>(occupied_replaceable_lanes | bit);
  }
  if (occupied_replaceable_lanes == 0U) {
    return;
  }
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    if (!selector_dp_evicted_candidates_[candidate] ||
        candidate_states_[candidate].active ||
        !has_direct_fundamental_peak(scores, fundamentals, candidate, count) ||
        (!is_local_peak(scores, candidate, count) &&
         !has_m3_candidate_evidence(scores, fundamentals, candidate, count))) {
      continue;
    }
    const std::uint8_t playable = playable_string_mask(candidate);
    const std::uint8_t eligible_lanes =
        static_cast<std::uint8_t>(playable & occupied_replaceable_lanes);
    bool score_can_replace = false;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((eligible_lanes & (1U << string)) == 0U) {
        continue;
      }
      const std::size_t incumbent = active_incumbents[string];
      const double advantage =
          (scores[candidate] - scores[incumbent]) /
          std::max(threshold, kScoreEpsilon);
      score_can_replace = score_can_replace ||
                          advantage >= kM3DpReplacementMinimumScoreMargin;
    }
    if (!score_can_replace) {
      continue;
    }
    std::array<double, kCalibrationHarmonicCount> current{};
    double current_total = 0.0;
    for (std::size_t harmonic = 0U; harmonic < current.size(); ++harmonic) {
      current[harmonic] = corrected_harmonic_energy(candidate, harmonic);
      current_total += current[harmonic];
    }
    if (current_total <= kScoreEpsilon) {
      continue;
    }
    std::size_t best_string = kMaxVoices;
    double best_similarity = -1.0;
    double second_similarity = -1.0;
    std::size_t playable_count = 0U;
    std::size_t measured_count = 0U;
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((playable & (1U << string)) == 0U) {
        continue;
      }
      ++playable_count;
      const StringCalibrationPoint* point =
          calibrator_.bank().point(string, note - kM3OpenNotes[string]);
      if (point == nullptr ||
          point->quality == CalibrationPointQuality::missing) {
        continue;
      }
      ++measured_count;
      const double similarity = calibration_similarity_from_energy_profile(
          candidate, string, current, current_total);
      if (similarity > best_similarity) {
        second_similarity = best_similarity;
        best_similarity = similarity;
        best_string = string;
      } else if (similarity > second_similarity) {
        second_similarity = similarity;
      }
    }
    if (best_string >= kMaxVoices ||
        (dp_replacement_allowed_string_mask_ & (1U << best_string)) == 0U ||
        !has_decisive_calibrated_shape_thresholds(
            playable_count, measured_count, best_similarity,
            second_similarity, kM3DpReplacementMinimumSimilarity,
            kM3CalibratedCandidateMinimumAdvantage)) {
      continue;
    }
    const std::size_t incumbent = active_incumbents[best_string];
    if (incumbent == count) {
      continue;
    }
    const double advantage =
        (scores[candidate] - scores[incumbent]) /
        std::max(threshold, kScoreEpsilon);
    if (advantage < kM3DpReplacementMinimumScoreMargin ||
        (replacement_targets[best_string] != count &&
         advantage <= replacement_advantages[best_string])) {
      continue;
    }
    replacement_targets[best_string] = candidate;
    replacement_incumbents[best_string] = incumbent;
    replacement_advantages[best_string] = advantage;
  }
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    const std::size_t candidate = replacement_targets[string];
    const std::size_t incumbent = replacement_incumbents[string];
    if (candidate == count || incumbent == count) {
      continue;
    }
    selected[incumbent] = false;
    selected[candidate] = true;
    CandidateState& target = candidate_states_[candidate];
    target.assigned_string = static_cast<std::uint8_t>(string);
    target.assigned_string_mask = static_cast<std::uint8_t>(1U << string);
    selector_atomic_handoff_targets_[candidate] = true;
    selector_atomic_handoff_target_for_incumbent_[incumbent] =
        static_cast<std::uint8_t>(candidate + 1U);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    selection_dispositions_[incumbent] = SelectionDisposition::dp_evicted;
    selection_dispositions_[candidate] = SelectionDisposition::selected;
#endif
  }
}

void PolyphonicPitchDetector::update_calibrated_dp_output_projections(
    DetectorDecision& decision,
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet, std::size_t count) noexcept {
  if (profile_mode_ != ProfileMode::m3 ||
      midi_routing_ != MidiRouting::per_voice) {
    return;
  }
  if (quiet) {
    // Silence and coasting must release the note that was actually rendered;
    // never re-articulate the detector's base pitch on the way to note-off.
    // A proposal that has not yet rendered is different: clear its consensus
    // so two separate articulations cannot combine across true silence.
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      CandidateState& state = candidate_states_[candidate];
      state.dp_output_projection_target =
          state.dp_output_projection_note;
      state.dp_output_projection_ticks =
          state.dp_output_projection_note < 128U
              ? kM3DpOutputConsensusDecisions
              : 0U;
    }
    return;
  }

  const auto stage_projection =
      [this, &decision](std::size_t candidate,
                        std::uint8_t desired_note) noexcept {
        CandidateState& state = candidate_states_[candidate];
        if (state.dp_output_projection_note == desired_note) {
          state.dp_output_projection_target = desired_note;
          state.dp_output_projection_ticks =
              kM3DpOutputConsensusDecisions;
          return;
        }
        if (state.dp_output_projection_target != desired_note) {
          state.dp_output_projection_target = desired_note;
          state.dp_output_projection_ticks = 1U;
          return;
        }
        if (state.dp_output_projection_ticks <
            std::numeric_limits<std::uint8_t>::max()) {
          ++state.dp_output_projection_ticks;
        }
        if (state.dp_output_projection_ticks <
            kM3DpOutputConsensusDecisions) {
          return;
        }
        if (change_candidate_dp_output_projection(
                decision, candidate, desired_note)) {
          state.dp_output_projection_ticks =
              kM3DpOutputConsensusDecisions;
        }
      };

  bool grouped_context = false;
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    if (string_count(state.assigned_string_mask) >= 2U ||
        string_count(state.midi_voice_mask) >= 2U ||
        string_count(state.spectral_lane_mask) >= 2U ||
        string_count(state.continuity_lane_mask) >= 2U ||
        string_count(fine.member_mask) >= 2U ||
        string_count(fine.pending_member_mask) >= 2U) {
      grouped_context = true;
      break;
    }
  }

  std::size_t incumbent = count;
  if (!grouped_context) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      const CandidateState& state = candidate_states_[candidate];
      std::uint8_t owned = state.assigned_string_mask;
      if (owned == 0U && state.assigned_string < kMaxVoices) {
        owned = static_cast<std::uint8_t>(1U << state.assigned_string);
      }
      if (!selected[candidate] || !state.active || owned != 0x01U ||
          state.midi_voice_mask != 0x01U ||
          state.spectral_duplicate_output_suppressed) {
        continue;
      }
      if (incumbent != count) {
        incumbent = count;
        break;
      }
      incumbent = candidate;
    }
  }

  std::size_t best_target = count;
  double best_advantage = -std::numeric_limits<double>::infinity();
  if (incumbent != count) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      if (!selector_dp_evicted_candidates_[candidate] ||
          candidate_states_[candidate].active ||
          !has_direct_fundamental_peak(scores, fundamentals, candidate,
                                       count) ||
          (!is_local_peak(scores, candidate, count) &&
           !has_m3_candidate_evidence(scores, fundamentals, candidate,
                                      count))) {
        continue;
      }
      const std::uint8_t playable = playable_string_mask(candidate);
      if ((playable & kM3DpOutputAllowedStringMask) == 0U) {
        continue;
      }
      std::array<double, kCalibrationHarmonicCount> current{};
      double current_total = 0.0;
      for (std::size_t harmonic = 0U; harmonic < current.size(); ++harmonic) {
        current[harmonic] = corrected_harmonic_energy(candidate, harmonic);
        current_total += current[harmonic];
      }
      if (current_total <= kScoreEpsilon) {
        continue;
      }
      std::size_t best_string = kMaxVoices;
      double best_similarity = -1.0;
      double second_similarity = -1.0;
      const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
      for (std::size_t string = 0U; string < kMaxVoices; ++string) {
        if ((playable & (1U << string)) == 0U) {
          continue;
        }
        const StringCalibrationPoint* point =
            calibrator_.bank().point(string, note - kM3OpenNotes[string]);
        if (point == nullptr ||
            point->quality == CalibrationPointQuality::missing) {
          continue;
        }
        const double similarity = calibration_similarity_from_energy_profile(
            candidate, string, current, current_total);
        if (similarity > best_similarity) {
          second_similarity = best_similarity;
          best_similarity = similarity;
          best_string = string;
        } else if (similarity > second_similarity) {
          second_similarity = similarity;
        }
      }
      if (best_string != 0U ||
          best_similarity < kM3DpOutputMinimumSimilarity ||
          best_similarity - second_similarity <
              kM3DpOutputMinimumCalibrationMargin) {
        continue;
      }
      const double advantage =
          (scores[candidate] - scores[incumbent]) /
          std::max(threshold, kScoreEpsilon);
      if (advantage < kM3DpOutputMinimumScoreMargin ||
          (best_target != count && advantage <= best_advantage)) {
        continue;
      }
      best_target = candidate;
      best_advantage = advantage;
    }
  }

  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    if (!state.active) {
      state.dp_output_projection_note = kTunerNoSignalNote;
      state.dp_output_projection_target = kTunerNoSignalNote;
      state.dp_output_projection_ticks = 0U;
      continue;
    }
    if (!selected[candidate]) {
      // Coasting keeps the actual rendered note until the ordinary release
      // duration emits its matching note-off.
      state.dp_output_projection_target = state.dp_output_projection_note;
      state.dp_output_projection_ticks =
          state.dp_output_projection_note < 128U
              ? kM3DpOutputConsensusDecisions
              : 0U;
      continue;
    }
    const std::uint8_t desired =
        candidate == incumbent && best_target != count
            ? static_cast<std::uint8_t>(lowest_note_ + best_target)
            : kTunerNoSignalNote;
    if (desired == kTunerNoSignalNote &&
        state.dp_output_projection_note == kTunerNoSignalNote) {
      state.dp_output_projection_target = kTunerNoSignalNote;
      state.dp_output_projection_ticks = 0U;
      continue;
    }
    stage_projection(candidate, desired);
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

bool PolyphonicPitchDetector::retain_fine_frequency_history_across_gap(
    const FineFrequencyEvidenceState& fine,
    std::uint16_t established_group_samples) noexcept {
  const std::uint8_t members = string_count(fine.member_mask);
  if (!fine.valid || members < 2U || members > 4U) {
    return false;
  }
  const bool committed_resolved_group =
      fine.pending_member_mask == fine.member_mask &&
      fine.pending_count >= established_group_samples;
  if (committed_resolved_group) {
    return true;
  }
  if (!fine.multi_source_observed) {
    return false;
  }
  const bool robust_multi_pair_beat_supported =
      members >= 3U && fine.robust_pairwise_beat_connected &&
      fine.minimum_pairwise_beat_coherence >=
          kM3RetainedUnisonRobustWeakPairFloor;
  return robust_multi_pair_beat_supported;
}

bool PolyphonicPitchDetector::committed_fine_group_matches_assignment(
    const FineFrequencyEvidenceState& fine,
    bool candidate_active, std::uint8_t assigned_member_mask) noexcept {
  const std::uint8_t members = string_count(fine.member_mask);
  return candidate_active && fine.valid && fine.multi_source_observed &&
         members >= 2U && members <= 4U &&
         assigned_member_mask == fine.member_mask;
}

double PolyphonicPitchDetector::fine_frequency_consensus_seconds(
    std::uint8_t current_member_mask, std::uint8_t proposed_member_mask,
    std::uint8_t playable_member_mask) noexcept {
  const std::uint8_t current_members = string_count(current_member_mask);
  const std::uint8_t proposed_members = string_count(proposed_member_mask);
  const std::uint8_t playable_members = string_count(playable_member_mask);
  // Preserve the established initial-acquisition timing. The additional fast
  // path introduced here applies only to a monotonic expansion that completes
  // the entire bounded playable group.
  const bool first_resolved_multi =
      current_members <= 1U && proposed_members > 1U;
  const bool complete_bounded_playable_expansion =
      current_members >= 2U && proposed_members > current_members &&
      proposed_member_mask == playable_member_mask &&
      playable_members >= 2U && playable_members <= 4U;
  if (current_member_mask == 0U || first_resolved_multi) {
    return kFineFrequencyInitialConsensusSeconds;
  }
  if (complete_bounded_playable_expansion) {
    return 0.0;
  }
  return kFineFrequencyReplacementConsensusSeconds;
}

std::uint8_t PolyphonicPitchDetector::bounded_fine_mask_complexity_output(
    bool active, bool selected, bool direct_fundamental, bool quiet,
    double score_threshold_ratio, std::uint8_t current_output_mask,
    std::uint8_t playable_mask, std::uint8_t other_output_mask,
    std::uint8_t maximum_polyphony,
    const std::array<std::uint8_t, 11U>& masks,
    const std::array<double, 11U>& normalized_residual,
    std::size_t count) noexcept {
  constexpr double kMemberPenalty = 0.02;
  constexpr double kTieEpsilon = 1.0e-12;
  const std::uint8_t current_members = string_count(current_output_mask);
  if (!active || !selected || !direct_fundamental || quiet ||
      !std::isfinite(score_threshold_ratio) ||
      score_threshold_ratio < kM3RetainedUnisonDecayFloorRatio ||
      current_members != 4U ||
      other_output_mask != 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      count == 0U || count > masks.size()) {
    return current_output_mask;
  }

  double best_score = std::numeric_limits<double>::infinity();
  std::uint8_t best_mask = 0U;
  bool tied = false;
  for (std::size_t index = 0U; index < count; ++index) {
    const std::uint8_t mask = masks[index];
    const std::uint8_t members = string_count(mask);
    const double residual = normalized_residual[index];
    if (members != 3U ||
        (mask & static_cast<std::uint8_t>(~current_output_mask)) != 0U ||
        (mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
        (mask & other_output_mask) != 0U ||
        string_count(static_cast<std::uint8_t>(mask | other_output_mask)) >
            maximum_polyphony ||
        !std::isfinite(residual) || residual < 0.0) {
      continue;
    }
    const double score =
        residual + kMemberPenalty * static_cast<double>(members - 2U);
    if (score + kTieEpsilon < best_score) {
      best_score = score;
      best_mask = mask;
      tied = false;
    } else if (std::abs(score - best_score) <= kTieEpsilon) {
      tied = true;
    }
  }
  return !tied && best_mask != 0U ? best_mask : current_output_mask;
}

std::uint8_t PolyphonicPitchDetector::bounded_fine_beat_pruning_output(
    std::uint8_t midi_note, bool active, bool selected,
    bool direct_fundamental, bool quiet, double score_threshold_ratio,
    std::uint8_t current_output_mask, std::uint8_t playable_mask,
    std::uint8_t other_output_mask, std::uint8_t maximum_polyphony,
    const std::array<std::uint8_t, 10U>& masks,
    const std::array<double, 10U>& normalized_residual,
    const std::array<double, 10U>& minimum_beat_coherence,
    const std::array<bool, 10U>& beat_graph_connected,
    std::size_t count) noexcept {
  constexpr std::uint8_t kLowestPrunedNote = 56U;
  const std::uint8_t current_members = string_count(current_output_mask);
  if (midi_note < kLowestPrunedNote || !active || !selected ||
      !direct_fundamental || quiet ||
      !std::isfinite(score_threshold_ratio) ||
      score_threshold_ratio < kM3RetainedUnisonDecayFloorRatio ||
      current_members < 3U || current_members > 4U ||
      (current_output_mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
      (current_output_mask & other_output_mask) != 0U ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices ||
      string_count(static_cast<std::uint8_t>(current_output_mask |
                                             other_output_mask)) >
          maximum_polyphony ||
      count == 0U || count > masks.size()) {
    return current_output_mask;
  }

  double best_score = std::numeric_limits<double>::infinity();
  std::uint8_t best_mask = 0U;
  bool tied = false;
  for (std::size_t index = 0U; index < count; ++index) {
    const std::uint8_t mask = masks[index];
    const std::uint8_t members = string_count(mask);
    const double residual = normalized_residual[index];
    const double coherence = minimum_beat_coherence[index];
    if (members < 2U || members >= current_members ||
        (mask & static_cast<std::uint8_t>(~current_output_mask)) != 0U ||
        (mask & static_cast<std::uint8_t>(~playable_mask)) != 0U ||
        (mask & other_output_mask) != 0U ||
        string_count(static_cast<std::uint8_t>(mask | other_output_mask)) >
            maximum_polyphony ||
        !beat_graph_connected[index] || !std::isfinite(residual) ||
        residual < 0.0 || !std::isfinite(coherence) ||
        coherence < kFineBeatPruningMinimumCoherence) {
      continue;
    }
    const double score = residual +
                         kFineBeatPruningMemberPenalty *
                             static_cast<double>(members - 2U);
    if (score + kFineBeatPruningTieEpsilon < best_score) {
      best_score = score;
      best_mask = mask;
      tied = false;
    } else if (std::abs(score - best_score) <=
               kFineBeatPruningTieEpsilon) {
      tied = true;
    }
  }
  return !tied && best_mask != 0U ? best_mask : current_output_mask;
}

void PolyphonicPitchDetector::update_fine_frequency_evidence(
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet) noexcept {
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
  const std::size_t candidate_count =
      static_cast<std::size_t>(candidate_count_);
  bool analysis_claimed = false;
  for (std::size_t candidate = 0U; candidate < candidate_count; ++candidate) {
    FineFrequencyEvidenceState& state =
        fine_frequency_evidence_states_[candidate];
    CandidateState& candidate_state = candidate_states_[candidate];
    if (!selected[candidate]) {
      const std::uint8_t members = string_count(state.member_mask);
      const bool carry_established_physical_group =
          !quiet && candidate_state.active && state.valid &&
          state.multi_source_observed && members >= 2U && members <= 4U &&
          candidate_state.assigned_string_mask == state.member_mask &&
          scores[candidate] >=
              threshold * kM3RetainedUnisonDecayFloorRatio &&
          has_direct_fundamental_peak(scores, fundamentals, candidate,
                                      candidate_count);
      bool carry_collecting_physical_group = false;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      carry_collecting_physical_group =
          diagnostic_collecting_fine_history_carry_enabled_ && !quiet &&
          candidate_state.active && !state.valid && state.count != 0U &&
          playable_string_mask(candidate) != 0U &&
          scores[candidate] >=
              threshold * kM3RetainedUnisonDecayFloorRatio &&
          has_direct_fundamental_peak(scores, fundamentals, candidate,
                                      candidate_count) &&
          has_m3_candidate_evidence(scores, fundamentals, candidate,
                                    candidate_count);
#endif
      if (!carry_established_physical_group &&
          !carry_collecting_physical_group) {
        if (decision_counter_ - state.last_decision_tick > maximum_gap) {
          state = {};
        }
        continue;
      }
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (!state.valid) {
        state.unresolved_reason = FineFrequencyUnresolvedReason::collecting;
      }
#endif
      continue;
    }
    const std::uint32_t observation_index =
        decision_counter_ / fine_frequency_decimation_decisions_;
    if ((observation_index + static_cast<std::uint32_t>(candidate)) %
                kFineFrequencyAnalysisStride !=
            0U ||
        analysis_claimed) {
      // Collection stays near 100 Hz and only one calibrated least-squares
      // fit runs per decision callback.
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (!state.valid) {
        state.unresolved_reason = FineFrequencyUnresolvedReason::analysis_wait;
      }
#endif
      continue;
    }
    analysis_claimed = true;
    const std::uint8_t previous_beat_pruning_source_mask =
        state.beat_pruning_source_mask;
    const std::uint8_t previous_beat_pruned_member_mask =
        state.beat_pruned_member_mask;
    state.beat_pruning_source_mask = 0U;
    state.beat_pruned_member_mask = 0U;

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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (!state.valid) {
        state.unresolved_reason =
            FineFrequencyUnresolvedReason::no_calibration_components;
      }
#endif
      continue;
    }

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (!state.valid) {
      state.unresolved_reason = FineFrequencyUnresolvedReason::fit_failure;
    }
#endif

    std::array<std::array<Complex, kMaxVoices>, kMaxVoices> gram{};
    std::array<Complex, kMaxVoices> correlations{};
    std::array<Complex, kMaxVoices> basis{};
    double signal_energy = 0.0;
    // A coherent phasor model is valid only over the causal evidence window.
    // Keeping older attacks in the normal equations makes natural pitch
    // decay cancel a still-present source. Retain the larger ring for gap
    // continuity, but fit exactly the most recent admitted window.
    const std::size_t fit_count = minimum_samples;
    const std::size_t oldest =
        (state.write_index + kFineFrequencyHistoryCapacity - fit_count) %
        kFineFrequencyHistoryCapacity;
    const std::uint32_t oldest_tick = state.decision_ticks[oldest];
    const std::size_t second_index =
        (oldest + 1U) % kFineFrequencyHistoryCapacity;
    const std::uint32_t uniform_tick_step =
        state.decision_ticks[second_index] - oldest_tick;
    bool uniformly_sampled = uniform_tick_step != 0U;
    for (std::size_t sample = 2U; sample < fit_count && uniformly_sampled;
         ++sample) {
      const std::size_t previous =
          (oldest + sample - 1U) % kFineFrequencyHistoryCapacity;
      const std::size_t index =
          (oldest + sample) % kFineFrequencyHistoryCapacity;
      uniformly_sampled =
          state.decision_ticks[index] - state.decision_ticks[previous] ==
          uniform_tick_step;
    }
    bool gram_is_normalized = false;
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
      for (std::size_t sample = 0U; sample < fit_count; ++sample) {
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
      FineFrequencyUniformGramCache& cache =
          fine_frequency_uniform_gram_cache_[candidate];
      bool cache_matches = cache.valid &&
                           cache.sample_count == fit_count &&
                           cache.tick_step == uniform_tick_step &&
                           cache.component_count == component_count;
      for (std::size_t component = 0U;
           component < component_count && cache_matches; ++component) {
        cache_matches = cache.offsets[component] == offsets[component];
      }
      if (cache_matches) {
        gram = cache.normalized_gram;
        gram_is_normalized = true;
      } else {
        // The uniform normal matrix is a finite complex geometric series.
        // Populate only the candidate that has accumulated a complete causal
        // window. Calibration and state changes merely invalidate caches, so
        // they never perform candidate-wide trigonometric work in a callback.
        const double count_as_double = static_cast<double>(fit_count);
        const double inverse_count = 1.0 / count_as_double;
        const double step_seconds =
            static_cast<double>(uniform_tick_step) * seconds_per_decision;
        cache = {};
        cache.component_count = static_cast<std::uint8_t>(component_count);
        cache.sample_count = static_cast<std::uint16_t>(fit_count);
        cache.tick_step = uniform_tick_step;
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          cache.offsets[component] = offsets[component];
        }
        for (std::size_t row = 0U; row < component_count; ++row) {
          for (std::size_t column = 0U; column < component_count; ++column) {
            const double half_angle =
                0.5 * kTwoPi * (offsets[column] - offsets[row]) *
                step_seconds;
            const double denominator = std::sin(half_angle);
            Complex value;
            if (std::abs(denominator) <= 1.0e-12) {
              value = Complex{count_as_double, 0.0};
            } else {
              const double magnitude =
                  std::sin(count_as_double * half_angle) / denominator;
              const double phase = (count_as_double - 1.0) * half_angle;
              value = magnitude *
                      Complex{std::cos(phase), std::sin(phase)};
            }
            cache.normalized_gram[row][column] = value * inverse_count;
          }
        }
        cache.valid = true;
        gram = cache.normalized_gram;
        gram_is_normalized = true;
      }
    } else {
      // Selector gaps retain their real decision ticks and use the exact
      // irregular normal matrix. This bounded fallback preserves the existing
      // causal fit without penalizing the steady-state callback path.
      for (std::size_t sample = 0U; sample < fit_count; ++sample) {
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
    const double inverse_count = 1.0 / static_cast<double>(fit_count);
    signal_energy *= inverse_count;
    if (!gram_is_normalized) {
      for (std::size_t row = 0U; row < component_count; ++row) {
        for (std::size_t column = 0U; column < component_count; ++column) {
          gram[row][column] *= inverse_count;
        }
      }
    }
    double frequency_mean = 0.0;
    double frequency_square_sum = 0.0;
    std::size_t frequency_samples = 0U;
    const std::size_t phase_start = fit_count / 5U;
    const std::size_t phase_candidates =
        fit_count > phase_start + 1U ? fit_count - phase_start - 1U : 0U;
    const std::size_t phase_stride = std::max<std::size_t>(
        1U, (phase_candidates + kFineFrequencyMaximumPhaseSamples - 1U) /
                kFineFrequencyMaximumPhaseSamples);
    for (std::size_t sample = phase_start + 1U; sample < fit_count;
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
    // The full solve below reduces gram in place. Preserve the normalized
    // matrix once so the bounded strict-subset fits can reuse the same causal
    // window without a second history scan.
    const auto subset_fit_gram = gram;

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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (!state.valid) {
        state.unresolved_reason = FineFrequencyUnresolvedReason::zero_solution;
      }
#endif
      continue;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.unresolved_reason = FineFrequencyUnresolvedReason::none;
#endif

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
    const std::size_t maximum_member_count = std::min<std::size_t>(
        kMaximumSimultaneousUnisonMembers, max_polyphony_);
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.unique_member_improvement = {};
#endif
    for (std::size_t rank = 0U; rank < component_count &&
                               member_count < maximum_member_count;
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
    const auto fitted_error_for_components =
        [&](const std::array<std::size_t, kMaxVoices>& retained,
            std::size_t retained_count) noexcept {
          if (retained_count == 0U) {
            return signal_energy;
          }
          std::array<std::array<Complex, kMaxVoices>, kMaxVoices> matrix{};
          std::array<Complex, kMaxVoices> reduced_solution{};
          for (std::size_t row = 0U; row < retained_count; ++row) {
            reduced_solution[row] = correlations[retained[row]];
            for (std::size_t column = 0U; column < retained_count;
                 ++column) {
              matrix[row][column] =
                  subset_fit_gram[retained[row]][retained[column]];
            }
          }
          for (std::size_t column = 0U; column < retained_count; ++column) {
            std::size_t pivot = column;
            for (std::size_t row = column + 1U; row < retained_count; ++row) {
              if (std::abs(matrix[row][column]) >
                  std::abs(matrix[pivot][column])) {
                pivot = row;
              }
            }
            if (std::abs(matrix[pivot][column]) <= 1.0e-10) {
              return signal_energy;
            }
            if (pivot != column) {
              std::swap(matrix[pivot], matrix[column]);
              std::swap(reduced_solution[pivot], reduced_solution[column]);
            }
            const Complex divisor = matrix[column][column];
            for (std::size_t entry = column; entry < retained_count; ++entry) {
              matrix[column][entry] /= divisor;
            }
            reduced_solution[column] /= divisor;
            for (std::size_t row = 0U; row < retained_count; ++row) {
              if (row == column) {
                continue;
              }
              const Complex factor = matrix[row][column];
              for (std::size_t entry = column; entry < retained_count;
                   ++entry) {
                matrix[row][entry] -= factor * matrix[column][entry];
              }
              reduced_solution[row] -= factor * reduced_solution[column];
            }
          }
          Complex reduced_cross{};
          double reduced_norm = 0.0;
          for (std::size_t row = 0U; row < retained_count; ++row) {
            reduced_cross += std::conj(reduced_solution[row]) *
                             correlations[retained[row]];
            reduced_norm += std::norm(reduced_solution[row]);
          }
          return std::max(0.0, signal_energy - std::real(reduced_cross) -
                                   kFineFrequencyRidge * reduced_norm);
        };
    std::array<std::uint8_t, 10U> beat_pruning_masks{};
    std::array<double, 10U> beat_pruning_residuals{};
    std::array<double, 10U> beat_pruning_coherence{};
    std::array<bool, 10U> beat_pruning_connected{};
    std::size_t beat_pruning_count = 0U;
    std::uint8_t beat_pruning_source_mask = 0U;
    std::uint8_t beat_pruning_other_output = 0U;
    const std::uint8_t current_output = projected_output_string_mask(
        candidate_state.assigned_string_mask, candidate_state.assigned_string,
        candidate_state.spectral_lane_mask,
        candidate_state.continuity_lane_mask);
    const std::uint8_t current_output_members = string_count(current_output);
    const bool beat_pruning_direct = has_direct_fundamental_peak(
        scores, fundamentals, candidate, candidate_count);
    const bool full_output_is_fine_confirmed =
        state.valid && state.multi_source_observed &&
        state.member_mask == current_output;
    if (full_output_is_fine_confirmed) {
      // A complete fine-frequency fit already authorizes every current lane,
      // so pruning cannot affect this decision. Keep the most recent bounded
      // pruning cache for a later loss of fine confirmation instead of
      // rescanning three seconds of history or erasing reacquisition state.
      state.beat_pruning_source_mask = previous_beat_pruning_source_mask;
      state.beat_pruned_member_mask = previous_beat_pruned_member_mask;
    } else if (note >= 56U && candidate_state.active && selected[candidate] &&
        !quiet && beat_pruning_direct &&
        scores[candidate] / std::max(threshold, kScoreEpsilon) >=
            kM3RetainedUnisonDecayFloorRatio &&
        current_output_members >= 3U && current_output_members <= 4U &&
        (current_output & static_cast<std::uint8_t>(~playable)) == 0U) {
      for (std::size_t other = 0U; other < candidate_count; ++other) {
        if (other != candidate && candidate_states_[other].active) {
          beat_pruning_other_output = static_cast<std::uint8_t>(
              beat_pruning_other_output |
              candidate_states_[other].midi_voice_mask);
        }
      }
      if ((current_output & beat_pruning_other_output) == 0U &&
          string_count(static_cast<std::uint8_t>(
              current_output | beat_pruning_other_output)) <= max_polyphony_) {
        beat_pruning_source_mask = current_output;
        for (std::uint8_t mask = static_cast<std::uint8_t>(
                 (current_output - 1U) & current_output);
             mask != 0U;
             mask = static_cast<std::uint8_t>((mask - 1U) & current_output)) {
          const std::uint8_t mask_members = string_count(mask);
          if (mask_members < 2U || mask_members >= current_output_members ||
              beat_pruning_count >= beat_pruning_masks.size()) {
            continue;
          }
          std::array<std::size_t, kMaxVoices> retained{};
          std::size_t retained_count = 0U;
          std::uint8_t represented_mask = 0U;
          for (std::size_t component = 0U; component < component_count;
               ++component) {
            const std::uint8_t bit =
                static_cast<std::uint8_t>(1U << strings[component]);
            if ((mask & bit) == 0U) {
              continue;
            }
            retained[retained_count++] = component;
            represented_mask =
                static_cast<std::uint8_t>(represented_mask | bit);
          }
          if (represented_mask != mask || retained_count != mask_members) {
            continue;
          }
          const double subset_error =
              fitted_error_for_components(retained, retained_count);
          if (!std::isfinite(subset_error)) {
            continue;
          }
          beat_pruning_masks[beat_pruning_count] = mask;
          beat_pruning_residuals[beat_pruning_count] =
              subset_error / std::max(signal_energy, kScoreEpsilon);
          ++beat_pruning_count;
        }
      }
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.mask_residuals = {};
    const auto fitted_error_without_component =
        [&](std::size_t omitted_component) noexcept {
          std::array<std::size_t, kMaxVoices> retained{};
          std::size_t retained_count = 0U;
          for (std::size_t component = 0U; component < component_count;
               ++component) {
            if (component != omitted_component) {
              retained[retained_count++] = component;
            }
          }
          return fitted_error_for_components(retained, retained_count);
        };
    for (std::size_t component = 0U; component < component_count;
         ++component) {
      const std::uint8_t bit =
          static_cast<std::uint8_t>(1U << strings[component]);
      if ((members & bit) == 0U) {
        continue;
      }
      const double without_error =
          fitted_error_without_component(component);
      state.unique_member_improvement[strings[component]] = std::clamp(
          (without_error - fitted_error) /
              std::max(without_error, kScoreEpsilon),
          0.0, 1.0);
    }
    if (fine_mask_complexity_diagnostics_enabled_) {
      for (std::size_t physical_mask = 1U;
           physical_mask < state.mask_residuals.valid.size();
           ++physical_mask) {
        const std::uint8_t mask = static_cast<std::uint8_t>(physical_mask);
        const std::uint8_t mask_members = string_count(mask);
        if (mask_members < 2U || mask_members > maximum_member_count) {
          continue;
        }
        std::array<std::size_t, kMaxVoices> retained{};
        std::size_t retained_count = 0U;
        std::uint8_t represented_mask = 0U;
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          const std::uint8_t bit =
              static_cast<std::uint8_t>(1U << strings[component]);
          if ((mask & bit) == 0U) {
            continue;
          }
          retained[retained_count++] = component;
          represented_mask =
              static_cast<std::uint8_t>(represented_mask | bit);
        }
        if (represented_mask != mask || retained_count != mask_members) {
          continue;
        }
        const double subset_error =
            fitted_error_for_components(retained, retained_count);
        if (!std::isfinite(subset_error)) {
          continue;
        }
        state.mask_residuals.normalized_residual[physical_mask] =
            subset_error / std::max(signal_energy, kScoreEpsilon);
        state.mask_residuals.valid[physical_mask] = true;
      }
    }
    state.fit_member_mask = members;
    state.residual_improvement = 0.0;
    state.residual_rejected = false;
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      state.residual_improvement =
          std::isfinite(improvement) ? improvement : 0.0;
#endif
      if (!std::isfinite(improvement) ||
          improvement < kFineFrequencyMinimumResidualImprovement) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        state.residual_rejected = true;
        state.disposition = FineFrequencyDisposition::residual_rejected;
#endif
        members = static_cast<std::uint8_t>(1U << strings[order[0U]]);
      }
    }
    struct PairwiseBeatResult final {
      double minimum{};
      bool connected{};
    };
    // Every mask query below is assembled from the same calibrated string
    // pairs and the same causal history window.  Compute the detrending terms
    // once, then memoize each pair's bounded correlation for this analysis.
    // Offline diagnostics query many overlapping masks; without this cache the
    // audio callback rescanned the three-second history (and repeated all
    // trigonometry) for the same pair dozens of times.
    const std::uint32_t pairwise_first_tick = state.decision_ticks[oldest];
    std::array<double, kFineFrequencyHistoryCapacity>
        pairwise_weighted_centered{};
    std::array<double, kFineFrequencyHistoryCapacity>
        pairwise_weighted_absolute{};
    double pairwise_weighted_absolute_sum = 0.0;
    bool pairwise_prepared = false;
    const auto prepare_pairwise = [&]() noexcept {
      if (pairwise_prepared) {
        return;
      }
      double pairwise_mean_time = 0.0;
      double pairwise_mean_energy = 0.0;
      for (std::size_t sample = 0U; sample < fit_count; ++sample) {
        const std::size_t index =
            (oldest + sample) % kFineFrequencyHistoryCapacity;
        pairwise_mean_time +=
            static_cast<double>(state.decision_ticks[index] -
                                pairwise_first_tick) *
            seconds_per_decision;
        pairwise_mean_energy += state.real[index] * state.real[index] +
                                state.imaginary[index] *
                                    state.imaginary[index];
      }
      pairwise_mean_time /= static_cast<double>(fit_count);
      pairwise_mean_energy /= static_cast<double>(fit_count);
      double pairwise_covariance = 0.0;
      double pairwise_time_variance = 0.0;
      for (std::size_t sample = 0U; sample < fit_count; ++sample) {
        const std::size_t index =
            (oldest + sample) % kFineFrequencyHistoryCapacity;
        const double seconds =
            static_cast<double>(state.decision_ticks[index] -
                                pairwise_first_tick) *
            seconds_per_decision;
        const double energy = state.real[index] * state.real[index] +
                              state.imaginary[index] * state.imaginary[index];
        pairwise_covariance +=
            (seconds - pairwise_mean_time) *
            (energy - pairwise_mean_energy);
        pairwise_time_variance +=
            (seconds - pairwise_mean_time) *
            (seconds - pairwise_mean_time);
      }
      const double pairwise_slope =
          pairwise_time_variance > kScoreEpsilon
              ? pairwise_covariance / pairwise_time_variance
              : 0.0;
      for (std::size_t sample = 0U; sample < fit_count; ++sample) {
        const std::size_t index =
            (oldest + sample) % kFineFrequencyHistoryCapacity;
        const double seconds =
            static_cast<double>(state.decision_ticks[index] -
                                pairwise_first_tick) *
            seconds_per_decision;
        const double energy = state.real[index] * state.real[index] +
                              state.imaginary[index] *
                                  state.imaginary[index];
        const double centered =
            energy -
            (pairwise_mean_energy +
             pairwise_slope * (seconds - pairwise_mean_time));
        const double window = fine_frequency_hann_window_[sample];
        pairwise_weighted_centered[sample] = window * centered;
        pairwise_weighted_absolute[sample] = window * std::abs(centered);
        pairwise_weighted_absolute_sum += pairwise_weighted_absolute[sample];
      }
      pairwise_prepared = true;
    };
    std::array<std::array<double, kMaxVoices>, kMaxVoices>
        pairwise_coherence_cache{};
    std::array<std::array<bool, kMaxVoices>, kMaxVoices>
        pairwise_coherence_measured{};
    const auto pair_coherence = [&](std::size_t first,
                                    std::size_t second) noexcept {
      if (pairwise_coherence_measured[first][second]) {
        return pairwise_coherence_cache[first][second];
      }
      const double beat_hz = std::abs(offsets[first] - offsets[second]);
      Complex correlation{};
      double absolute = 0.0;
      if (beat_hz >= kMinimumBeatHz && beat_hz <= kMaximumBeatHz) {
        prepare_pairwise();
        absolute = pairwise_weighted_absolute_sum;
        if (uniformly_sampled) {
          const double step_seconds =
              static_cast<double>(uniform_tick_step) * seconds_per_decision;
          const Complex phase_step =
              std::polar(1.0, -kTwoPi * beat_hz * step_seconds);
          Complex phase{1.0, 0.0};
          for (std::size_t sample = 0U; sample < fit_count; ++sample) {
            correlation += pairwise_weighted_centered[sample] * phase;
            phase *= phase_step;
          }
        } else {
          for (std::size_t sample = 0U; sample < fit_count; ++sample) {
            const std::size_t index =
                (oldest + sample) % kFineFrequencyHistoryCapacity;
            const double seconds =
                static_cast<double>(state.decision_ticks[index] -
                                    pairwise_first_tick) *
                seconds_per_decision;
            const double phase = -kTwoPi * beat_hz * seconds;
            correlation += pairwise_weighted_centered[sample] *
                           Complex{std::cos(phase), std::sin(phase)};
          }
        }
      }
      const double coherence =
          absolute > kScoreEpsilon
              ? std::clamp(std::abs(correlation) / absolute, 0.0, 1.0)
              : 0.0;
      pairwise_coherence_cache[first][second] = coherence;
      pairwise_coherence_cache[second][first] = coherence;
      pairwise_coherence_measured[first][second] = true;
      pairwise_coherence_measured[second][first] = true;
      return coherence;
    };
    const auto pairwise_beat_coherence = [&](std::uint8_t mask) noexcept {
      PairwiseBeatResult result;
      if (string_count(mask) < 2U || fit_count < 2U) {
        return result;
      }
      double minimum = std::numeric_limits<double>::infinity();
      std::array<std::uint8_t, kMaxVoices> adjacency{};
      for (std::size_t first = 0U; first < component_count; ++first) {
        if ((mask & (1U << strings[first])) == 0U) {
          continue;
        }
        for (std::size_t second = first + 1U; second < component_count;
             ++second) {
          if ((mask & (1U << strings[second])) == 0U) {
            continue;
          }
          const double coherence = pair_coherence(first, second);
          minimum = std::min(minimum, coherence);
          if (coherence >= kM3RetainedUnisonMinimumBeatCoherence) {
            const std::uint8_t first_bit =
                static_cast<std::uint8_t>(1U << strings[first]);
            const std::uint8_t second_bit =
                static_cast<std::uint8_t>(1U << strings[second]);
            adjacency[strings[first]] = static_cast<std::uint8_t>(
                adjacency[strings[first]] | second_bit);
            adjacency[strings[second]] = static_cast<std::uint8_t>(
                adjacency[strings[second]] | first_bit);
          }
        }
      }
      result.minimum = std::isfinite(minimum) ? minimum : 0.0;
      const std::uint8_t first_member = static_cast<std::uint8_t>(
          mask & static_cast<std::uint8_t>(0U - mask));
      std::uint8_t reached = first_member;
      for (std::size_t pass = 0U; pass < kMaxVoices; ++pass) {
        std::uint8_t expanded = reached;
        for (std::size_t string = 0U; string < kMaxVoices; ++string) {
          if ((reached & (1U << string)) != 0U) {
            expanded =
                static_cast<std::uint8_t>(expanded | adjacency[string]);
          }
        }
        if (expanded == reached) {
          break;
        }
        reached = expanded;
      }
      result.connected =
          static_cast<std::uint8_t>(reached & mask) == mask;
      return result;
    };
    if (beat_pruning_source_mask != 0U && beat_pruning_count != 0U) {
      for (std::size_t index = 0U; index < beat_pruning_count; ++index) {
        const PairwiseBeatResult support =
            pairwise_beat_coherence(beat_pruning_masks[index]);
        beat_pruning_coherence[index] = support.minimum;
        beat_pruning_connected[index] = support.connected;
      }
      const std::uint8_t projection = bounded_fine_beat_pruning_output(
          note, candidate_state.active, selected[candidate],
          beat_pruning_direct, quiet,
          scores[candidate] / std::max(threshold, kScoreEpsilon),
          beat_pruning_source_mask, playable, beat_pruning_other_output,
          max_polyphony_, beat_pruning_masks, beat_pruning_residuals,
          beat_pruning_coherence, beat_pruning_connected,
          beat_pruning_count);
      state.beat_pruning_source_mask = beat_pruning_source_mask;
      if (projection != beat_pruning_source_mask) {
        state.beat_pruned_member_mask = projection;
      }
    }
    const PairwiseBeatResult proposed_beat_support =
        pairwise_beat_coherence(members);
    const double proposed_beat_coherence = proposed_beat_support.minimum;
    if (members == state.pending_member_mask) {
      if (state.pending_count < std::numeric_limits<std::uint16_t>::max()) {
        ++state.pending_count;
      }
      state.pending_minimum_pairwise_beat_coherence =
          0.75 * state.pending_minimum_pairwise_beat_coherence +
          0.25 * proposed_beat_coherence;
      state.pending_robust_pairwise_beat_connected =
          proposed_beat_support.connected;
    } else {
      state.pending_member_mask = members;
      state.pending_count = 1U;
      state.pending_minimum_pairwise_beat_coherence = proposed_beat_coherence;
      state.pending_robust_pairwise_beat_connected =
          proposed_beat_support.connected;
    }
    const double consensus_seconds = fine_frequency_consensus_seconds(
        state.member_mask, members, playable);
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
      state.minimum_pairwise_beat_coherence =
          state.pending_minimum_pairwise_beat_coherence;
      state.robust_pairwise_beat_connected =
          state.pending_robust_pairwise_beat_connected;
    } else if (members == state.member_mask) {
      state.minimum_pairwise_beat_coherence =
          0.75 * state.minimum_pairwise_beat_coherence +
          0.25 * proposed_beat_coherence;
      state.robust_pairwise_beat_connected =
          proposed_beat_support.connected;
    }
    // Refresh the small production beat cache only at the already-decimated
    // fine-frequency analysis cadence. Spectral heads are evaluated at the
    // normal detector-decision cadence below, so retain one bounded value per
    // possible added physical string rather than a 256-mask matrix.
    state.added_member_beat_coherence.fill(0.0);
    const std::uint8_t completion_base_count =
        string_count(state.member_mask);
    if (completion_base_count >= 2U && completion_base_count < 4U) {
      for (std::size_t component = 0U; component < component_count;
           ++component) {
        const std::uint8_t added_bit =
            static_cast<std::uint8_t>(1U << strings[component]);
        if ((state.member_mask & added_bit) != 0U) {
          continue;
        }
        double strongest_added_pair = 0.0;
        for (std::size_t base_string = 0U; base_string < component_count;
             ++base_string) {
          const std::uint8_t base_bit =
              static_cast<std::uint8_t>(1U << strings[base_string]);
          if ((state.member_mask & base_bit) == 0U) {
            continue;
          }
          strongest_added_pair = std::max(
              strongest_added_pair,
              pairwise_beat_coherence(
                  static_cast<std::uint8_t>(base_bit | added_bit))
                  .minimum);
        }
        state.added_member_beat_coherence[strings[component]] =
            strongest_added_pair;
      }
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (offline_replay_diagnostics_enabled_) {
      state.pairwise_beat_coherence_by_mask.fill(0.0);
      state.added_member_beat_coherence_by_completion_mask.fill(0.0);
      if (fine_mask_complexity_diagnostics_enabled_ &&
          hann_beat_shadow_buffer_ != nullptr) {
        auto& shadow_table = (*hann_beat_shadow_buffer_)[candidate];
        shadow_table = {};
        std::array<double, kFineFrequencyHistoryCapacity> shadow_seconds{};
        std::array<double, kFineFrequencyHistoryCapacity> shadow_energy{};
        for (std::size_t sample = 0U; sample < fit_count; ++sample) {
          const std::size_t index =
              (oldest + sample) % kFineFrequencyHistoryCapacity;
          shadow_seconds[sample] =
              static_cast<double>(state.decision_ticks[index] -
                                  pairwise_first_tick) * seconds_per_decision;
          shadow_energy[sample] = state.real[index] * state.real[index] +
              state.imaginary[index] * state.imaginary[index];
        }
        diagnostics::HannDetrendedBeatShadow<kFineFrequencyHistoryCapacity>
            shadow;
        shadow_table.hann_detrending_valid = shadow.prepare(
            shadow_seconds, shadow_energy, fine_frequency_hann_window_,
            fit_count);
        shadow_table.beat_window_seconds = shadow.duration_seconds;
        if (shadow_table.hann_detrending_valid) {
          for (std::size_t first = 0U; first < component_count; ++first) {
            for (std::size_t second = first + 1U; second < component_count;
                 ++second) {
              const std::size_t edge = diagnostics::beat_pair_index(
                  strings[first], strings[second]);
              const double beat_hz =
                  std::abs(offsets[first] - offsets[second]);
              shadow_table.pair_difference_hz[edge] = beat_hz;
              if (beat_hz >= kMinimumBeatHz && beat_hz <= kMaximumBeatHz) {
                shadow_table.hann_detrended_pair_coherence[edge] =
                    shadow.coherence(beat_hz);
              }
            }
          }
        }
      }
      for (std::size_t physical_mask = 1U;
           physical_mask < state.mask_residuals.valid.size();
           ++physical_mask) {
        if (!state.mask_residuals.valid[physical_mask]) {
          continue;
        }
        const PairwiseBeatResult support = pairwise_beat_coherence(
            static_cast<std::uint8_t>(physical_mask));
        state.mask_residuals.minimum_beat_coherence[physical_mask] =
            support.minimum;
        state.mask_residuals.beat_graph_connected[physical_mask] =
            support.connected;
      }
      std::array<bool, 1U << kMaxVoices> measured_masks{};
      const auto measure_completion_mask = [&](std::uint8_t mask) noexcept {
        const std::uint8_t count = string_count(mask);
        if (count < 2U || count > 4U || measured_masks[mask]) {
          return;
        }
        measured_masks[mask] = true;
        state.pairwise_beat_coherence_by_mask[mask] =
            pairwise_beat_coherence(mask).minimum;
      };
      // The production decision only needs the current mask and one-member
      // completions. Offline replay also needs every feasible two-string edge
      // so it can distinguish one genuinely weak pair from a disconnected
      // three- or four-string group without changing MIDI output.
      for (std::size_t left = 0U; left < component_count; ++left) {
        const std::uint8_t left_bit =
            static_cast<std::uint8_t>(1U << strings[left]);
        for (std::size_t right = left + 1U; right < component_count; ++right) {
          const std::uint8_t right_bit =
              static_cast<std::uint8_t>(1U << strings[right]);
          measure_completion_mask(
              static_cast<std::uint8_t>(left_bit | right_bit));
        }
      }
      const std::array<std::uint8_t, 2U> completion_bases{
          state.fit_member_mask, state.member_mask};
      for (const std::uint8_t base : completion_bases) {
        measure_completion_mask(base);
        const std::uint8_t base_count = string_count(base);
        if (base_count < 2U || base_count >= 4U) {
          continue;
        }
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          const std::uint8_t bit =
              static_cast<std::uint8_t>(1U << strings[component]);
          if ((base & bit) != 0U) {
            continue;
          }
          measure_completion_mask(static_cast<std::uint8_t>(base | bit));
        }
      }
      const std::uint8_t completion_base = state.member_mask;
      const std::uint8_t diagnostic_completion_base_count =
          string_count(completion_base);
      if (diagnostic_completion_base_count >= 2U &&
          diagnostic_completion_base_count < 4U) {
        for (std::size_t component = 0U; component < component_count;
             ++component) {
          const std::uint8_t added_bit =
              static_cast<std::uint8_t>(1U << strings[component]);
          if ((completion_base & added_bit) != 0U) {
            continue;
          }
          const std::uint8_t completion =
              static_cast<std::uint8_t>(completion_base | added_bit);
          state.added_member_beat_coherence_by_completion_mask[completion] =
              state.added_member_beat_coherence[strings[component]];
        }
      }
    }
#endif
    state.valid = state.member_mask != 0U;
  }
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
void PolyphonicPitchDetector::update_fine_mask_pruning_output_projection(
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet) noexcept {
  const std::size_t candidate_count =
      static_cast<std::size_t>(candidate_count_);
  for (std::size_t candidate = 0U; candidate < candidate_count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    state.diagnostic_fine_mask_pruning_mask = 0U;
    if (!diagnostic_fine_mask_pruning_enabled_) {
      continue;
    }
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    if (note < 52U) {
      continue;
    }
    const std::uint8_t current_output = projected_output_string_mask(
        state.assigned_string_mask, state.assigned_string,
        state.spectral_lane_mask, state.continuity_lane_mask);
    if (string_count(current_output) < 3U ||
        string_count(current_output) > 4U) {
      continue;
    }
    std::array<std::uint8_t, 11U> masks{};
    std::array<double, 11U> normalized_residual{};
    std::size_t mask_count = 0U;
    const FineFrequencyMaskResidualTable& residuals =
        fine_frequency_evidence_states_[candidate].mask_residuals;
    for (std::uint8_t mask = current_output; mask != 0U;
         mask = static_cast<std::uint8_t>((mask - 1U) & current_output)) {
      const std::uint8_t members = string_count(mask);
      if (members < 2U || members > 4U || !residuals.valid[mask] ||
          mask_count >= masks.size()) {
        continue;
      }
      masks[mask_count] = mask;
      normalized_residual[mask_count] = residuals.normalized_residual[mask];
      ++mask_count;
    }
    std::uint8_t other_output = 0U;
    for (std::size_t other = 0U; other < candidate_count; ++other) {
      if (other != candidate && candidate_states_[other].active) {
        other_output = static_cast<std::uint8_t>(
            other_output | candidate_states_[other].midi_voice_mask);
      }
    }
    const std::uint8_t projection = bounded_fine_mask_complexity_output(
        state.active, selected[candidate],
        has_direct_fundamental_peak(scores, fundamentals, candidate,
                                    candidate_count),
        quiet, scores[candidate] / std::max(threshold, kScoreEpsilon),
        current_output, playable_string_mask(candidate), other_output,
        max_polyphony_, masks, normalized_residual, mask_count);
    if (projection != current_output) {
      state.diagnostic_fine_mask_pruning_mask = projection;
    }
  }
}
#endif

void PolyphonicPitchDetector::update_fine_beat_pruning_output_projection(
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet) noexcept {
  const std::size_t candidate_count =
      static_cast<std::size_t>(candidate_count_);
  for (std::size_t candidate = 0U; candidate < candidate_count; ++candidate) {
    CandidateState& state = candidate_states_[candidate];
    state.fine_beat_pruning_mask = 0U;
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    if (note < 56U || !state.active || !selected[candidate] || quiet ||
        !has_direct_fundamental_peak(scores, fundamentals, candidate,
                                     candidate_count) ||
        scores[candidate] /
                std::max(threshold, kScoreEpsilon) <
            kM3RetainedUnisonDecayFloorRatio) {
      continue;
    }
    const std::uint8_t current_output = projected_output_string_mask(
        state.assigned_string_mask, state.assigned_string,
        state.spectral_lane_mask, state.continuity_lane_mask);
    const std::uint8_t current_members = string_count(current_output);
    if (current_members < 3U || current_members > 4U ||
        (current_output &
         static_cast<std::uint8_t>(~playable_string_mask(candidate))) != 0U) {
      continue;
    }
    std::uint8_t other_output = 0U;
    for (std::size_t other = 0U; other < candidate_count; ++other) {
      if (other != candidate && candidate_states_[other].active) {
        other_output = static_cast<std::uint8_t>(
            other_output | candidate_states_[other].midi_voice_mask);
      }
    }
    if ((current_output & other_output) != 0U ||
        string_count(static_cast<std::uint8_t>(current_output |
                                               other_output)) >
            max_polyphony_) {
      continue;
    }
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t projection = fine.beat_pruned_member_mask;
    const bool full_output_is_fine_confirmed =
        fine.valid && fine.multi_source_observed &&
        fine.member_mask == current_output;
    if (!full_output_is_fine_confirmed &&
        fine.beat_pruning_source_mask == current_output &&
        string_count(projection) >= 2U &&
        string_count(projection) < current_members &&
        (projection & static_cast<std::uint8_t>(~current_output)) == 0U &&
        (projection & other_output) == 0U &&
        string_count(static_cast<std::uint8_t>(projection | other_output)) <=
            max_polyphony_) {
      state.fine_beat_pruning_mask = projection;
    }
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
  return harmonic_energy_at_cents(candidate, harmonic, phase.cents);
}

double PolyphonicPitchDetector::profile_harmonic_energy(
    std::size_t candidate, std::size_t harmonic) const noexcept {
  const double selector_energy =
      corrected_harmonic_energy(candidate, harmonic);
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      harmonic >= kHarmonicCount ||
      !phase_cents_states_[candidate].valid) {
    return selector_energy;
  }
  const PartialDetuningEvidence detuning =
      partial_detuning_trackers_[candidate].evidence();
  const std::uint8_t bit = static_cast<std::uint8_t>(1U << harmonic);
  if ((detuning.valid_mask & bit) == 0U) {
    return selector_energy;
  }
  return harmonic_energy_at_cents(
      candidate, harmonic,
      phase_cents_states_[candidate].cents + detuning.residual_cents[harmonic]);
}

double PolyphonicPitchDetector::harmonic_energy_at_cents(
    std::size_t candidate, std::size_t harmonic, double cents) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      harmonic >= kHarmonicCount || !std::isfinite(cents)) {
    return 0.0;
  }
  const Cell& cell = cells_[cell_index(candidate, harmonic)];
  if (!cell.enabled) {
    return 0.0;
  }
  const double raw = cell.fast_real * cell.fast_real +
                     cell.fast_imaginary * cell.fast_imaginary;
  if (raw <= kScoreEpsilon) {
    return raw;
  }
  constexpr double kNaturalLogTwo = 0.69314718055994530942;
  const double fractional_offset =
      std::expm1(kNaturalLogTwo * cents / 1200.0);
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
    state.output_projection_valid = false;
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
    const bool settled =
        accepted && state.accepted_updates >= required_updates;
    state.output_projection_valid =
        settled &&
        state.cents >= -kM3OutputProjectionMaximumAbsoluteCents &&
        state.cents <= kM3OutputProjectionMaximumAbsoluteCents;
    state.valid = state.output_projection_valid && state.cents >= -50.0 &&
                  state.cents <= 50.0;
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

#if defined(M3_UNISON_SPECTRAL_SHADOW)
PolyphonicPitchDetector::UnisonReacquisitionState*
PolyphonicPitchDetector::find_unison_reacquisition_state(
    std::size_t candidate) noexcept {
  for (UnisonReacquisitionState& state : unison_reacquisition_states_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

const PolyphonicPitchDetector::UnisonReacquisitionState*
PolyphonicPitchDetector::find_unison_reacquisition_state(
    std::size_t candidate) const noexcept {
  for (const UnisonReacquisitionState& state :
       unison_reacquisition_states_) {
    if (state.candidate_index == candidate) {
      return &state;
    }
  }
  return nullptr;
}

PolyphonicPitchDetector::UnisonReacquisitionState*
PolyphonicPitchDetector::acquire_unison_reacquisition_state(
    std::size_t candidate) noexcept {
  if (UnisonReacquisitionState* existing =
          find_unison_reacquisition_state(candidate)) {
    return existing;
  }
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      candidate > std::numeric_limits<std::uint8_t>::max()) {
    return nullptr;
  }
  for (UnisonReacquisitionState& state : unison_reacquisition_states_) {
    if (state.candidate_index != 0xffU) {
      continue;
    }
    state = {};
    state.candidate_index = static_cast<std::uint8_t>(candidate);
    return &state;
  }
  const std::uint32_t maximum_age = static_cast<std::uint32_t>(std::clamp(
      std::ceil(kUnisonReacquisitionHoldSeconds * sample_rate_ /
                static_cast<double>(kDecisionQuantum)),
      1.0, static_cast<double>(std::numeric_limits<std::uint32_t>::max())));
  UnisonReacquisitionState* oldest = nullptr;
  for (UnisonReacquisitionState& state : unison_reacquisition_states_) {
    if (state.candidate_index == 0xffU ||
        decision_counter_ - state.last_confirmed_tick <= maximum_age) {
      continue;
    }
    if (oldest == nullptr || state.last_confirmed_tick <
                                oldest->last_confirmed_tick) {
      oldest = &state;
    }
  }
  if (oldest != nullptr) {
    *oldest = {};
    oldest->candidate_index = static_cast<std::uint8_t>(candidate);
  }
  return oldest;
}

void PolyphonicPitchDetector::update_unison_reacquisition_state(
    const std::array<bool, kMaxCandidates>& selected,
    const std::array<double, kMaxCandidates>& scores,
    const std::array<double, kMaxCandidates>& fundamentals,
    double threshold, bool quiet) noexcept {
  if (profile_mode_ != ProfileMode::m3 || sample_rate_ <= 0.0) {
    return;
  }
  const std::size_t count = static_cast<std::size_t>(candidate_count_);

  // Snapshot a newly established exact group before applying any cached
  // restoration. A restored group therefore cannot refresh its own lifetime.
  for (std::size_t candidate = 0U;
       candidate < count; ++candidate) {
    CandidateState& candidate_state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t assignment = candidate_state.assigned_string_mask;
    const bool above_decay_floor =
        std::isfinite(scores[candidate]) && std::isfinite(threshold) &&
        scores[candidate] >= threshold * kM3RetainedUnisonDecayFloorRatio;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    UnisonCacheRefreshDisposition refresh_disposition =
        UnisonCacheRefreshDisposition::refreshed;
    const std::uint8_t assignment_members = string_count(assignment);
    if (quiet) {
      refresh_disposition = UnisonCacheRefreshDisposition::quiet;
    } else if (!candidate_state.active) {
      refresh_disposition = UnisonCacheRefreshDisposition::inactive;
    } else if (!selected[candidate] && !above_decay_floor) {
      refresh_disposition =
          UnisonCacheRefreshDisposition::below_decay_floor;
    } else if (!fine.valid) {
      refresh_disposition = UnisonCacheRefreshDisposition::fine_invalid;
    } else if (assignment_members < 3U || assignment_members > 4U) {
      refresh_disposition =
          UnisonCacheRefreshDisposition::invalid_member_count;
    } else if (assignment != fine.member_mask) {
      refresh_disposition =
          UnisonCacheRefreshDisposition::assignment_fine_mismatch;
    }
    unison_cache_refresh_dispositions_[candidate] = refresh_disposition;
#endif
    if (!bounded_observed_unison_cache_refresh(
            candidate_state.active, selected[candidate], above_decay_floor,
            quiet, assignment, fine.member_mask)) {
      continue;
    }
    const SpectralLaneState* spectral = find_spectral_lane_state(candidate);
    if (!fine.valid) {
      continue;
    }
    UnisonReacquisitionState* cache_ptr =
        acquire_unison_reacquisition_state(candidate);
    if (cache_ptr == nullptr) {
      continue;
    }
    UnisonReacquisitionState& cache = *cache_ptr;
    const bool group_changed = cache.resolved_mask != assignment;
    cache.resolved_mask = assignment;
    cache.last_confirmed_tick = decision_counter_;
    if (spectral != nullptr && spectral->tracking &&
        spectral->tracker.ready()) {
      cache.confirmed_fingerprint = spectral->tracker.fingerprint();
      cache.confirmed_fingerprint_valid = true;
    } else if (group_changed) {
      cache.confirmed_fingerprint = {};
      cache.confirmed_fingerprint_valid = false;
    }
  }

  if (quiet) {
    return;
  }
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    CandidateState& candidate_state = candidate_states_[candidate];
    if (!selected[candidate] || !candidate_state.active) {
      continue;
    }
    const UnisonReacquisitionState* cache =
        find_unison_reacquisition_state(candidate);
    const SpectralLaneState* spectral = find_spectral_lane_state(candidate);
    if (cache == nullptr || spectral == nullptr || !spectral->tracking ||
        !spectral->tracker.ready()) {
      continue;
    }
    std::uint8_t other_owned = 0U;
    for (std::size_t other = 0U; other < count; ++other) {
      if (other == candidate || !candidate_states_[other].active) {
        continue;
      }
      std::uint8_t owned = static_cast<std::uint8_t>(
          candidate_states_[other].assigned_string_mask |
          candidate_states_[other].midi_voice_mask);
      if (owned == 0U &&
          candidate_states_[other].assigned_string < kMaxVoices) {
        owned = static_cast<std::uint8_t>(
            1U << candidate_states_[other].assigned_string);
      }
      other_owned = static_cast<std::uint8_t>(other_owned | owned);
    }
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    const std::uint8_t playable = playable_string_mask(candidate);
    const std::uint8_t fine_mask =
        static_cast<std::uint8_t>(fine.member_mask & playable);
    const std::uint8_t tier_mask = bounded_spectral_tier_completion(
        candidate_state.active, candidate_state.assigned_string_mask,
        fine_mask, playable, string_fret_spectral_head_evidence(candidate),
        fine.added_member_beat_coherence, fine.component_energy);
    const UnisonSpectralFingerprint current_fingerprint =
        spectral->tracker.fingerprint();
    const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
    ObservedUnisonReacquisitionEvidence evidence;
    evidence.current_assignment_mask = candidate_state.assigned_string_mask;
    evidence.cached_group_mask = cache->resolved_mask;
    evidence.pending_fine_mask = fine.pending_member_mask;
    evidence.spectral_tier_mask = tier_mask;
    evidence.other_owned_mask = other_owned;
    evidence.playable_mask = playable;
    evidence.maximum_polyphony = max_polyphony_;
    evidence.direct_fundamental =
        has_direct_fundamental_peak(scores, fundamentals, candidate, count);
    evidence.cache_age_seconds =
        static_cast<double>(decision_counter_ - cache->last_confirmed_tick) *
        static_cast<double>(kDecisionQuantum) / sample_rate_;
    evidence.maximum_cache_age_seconds =
        kUnisonReacquisitionHoldSeconds;
    evidence.pending_evidence_seconds =
        fine_frequency_pending_evidence_seconds(note);
    evidence.minimum_revalidation_seconds =
        kUnisonReacquisitionMinimumRevalidationSeconds;
    evidence.pending_beat_coherence =
        fine.pending_minimum_pairwise_beat_coherence;
    evidence.cached_fingerprint_valid = cache->confirmed_fingerprint_valid;
    evidence.current_fingerprint_valid = true;
    evidence.fingerprint_squared_distance =
        normalized_spectral_fingerprint_squared_distance(
            cache->confirmed_fingerprint, current_fingerprint);
    evidence.maximum_fingerprint_squared_distance =
        kUnisonReacquisitionMaximumFingerprintDistance;
    const ObservedUnisonReacquisitionResult projection =
        diagnose_observed_unison_reacquisition(evidence);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS) && \
    defined(M3_UNISON_SPECTRAL_SHADOW)
    spectral_reacquisition_dispositions_[candidate] = projection.disposition;
#endif
    // This is an offline shadow policy. Record whether the bounded
    // counterfactual would accept, but never feed it back into the detector's
    // assignment or MIDI/tuner state. The replay's production metrics and
    // fingerprint must therefore remain identical with diagnostics enabled.
    (void)projection.projected_mask;
  }
}
#endif

void PolyphonicPitchDetector::infer_m3_unison_strings(
    const std::array<bool, kMaxCandidates>& selected) noexcept {
  if (profile_mode_ != ProfileMode::m3) {
    return;
  }

  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    candidate_states_[candidate].latest_unison_proposal_mask = 0U;
    candidate_states_[candidate].latest_unison_proposal_temporal = false;
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  for (std::size_t candidate = 0U;
       candidate < static_cast<std::size_t>(candidate_count_); ++candidate) {
    candidate_states_[candidate].diagnostic_unison_proposal_mask = 0U;
    candidate_states_[candidate].diagnostic_unison_temporal = false;
  }
  fine_group_dispositions_.fill(FineGroupDisposition::unresolved);
  tier_completion_dispositions_.fill(
      TierCompletionDisposition::unavailable);
#endif

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
      const std::uint8_t fine_temporal_group = static_cast<std::uint8_t>(
          fine.member_mask & playable_string_mask(candidate));
      std::uint8_t raw_temporal_group = fine_temporal_group;
      std::size_t raw_temporal_count = 0U;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        raw_temporal_count +=
            (raw_temporal_group & (1U << string)) != 0U ? 1U : 0U;
      }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      FineGroupDisposition fine_group_disposition =
          FineGroupDisposition::unresolved;
      if ((raw_temporal_group & primary_bit) == 0U) {
        fine_group_disposition = FineGroupDisposition::missing_primary;
      } else if (raw_temporal_count < 2U || raw_temporal_count > 4U) {
        fine_group_disposition = FineGroupDisposition::invalid_size;
      } else if ((raw_temporal_group & other_owned_strings) != 0U) {
        fine_group_disposition =
            FineGroupDisposition::conflicts_other_owned;
      } else if ((raw_temporal_group & allocated_extra_strings) != 0U) {
        fine_group_disposition = FineGroupDisposition::conflicts_allocated;
      } else if (raw_temporal_count - 1U > candidate_extra_capacity) {
        fine_group_disposition = FineGroupDisposition::over_capacity;
      } else {
        fine_group_disposition = FineGroupDisposition::accepted;
      }
      fine_group_dispositions_[candidate] = fine_group_disposition;
#endif
      if ((raw_temporal_group & primary_bit) != 0U &&
          raw_temporal_count >= 2U && raw_temporal_count <= 4U &&
          (raw_temporal_group & other_owned_strings) == 0U &&
          (raw_temporal_group & allocated_extra_strings) == 0U &&
          raw_temporal_count - 1U <= candidate_extra_capacity) {
        proposed_group = raw_temporal_group;
        temporal_group_selected = true;
      }
    }
    // A settled fine-frequency pair can be missing one physical lane even
    // while the independent low/low-mid/high-mid/high spectral heads and the
    // added member's beat envelope agree on it. Complete only that one lane
    // for a selected pitch with an established or freshly resolved fine group,
    // through the same physical ownership and polyphony bounds used by every
    // other group proposal.
    const std::uint8_t fine_group = static_cast<std::uint8_t>(
        fine.member_mask & playable_string_mask(candidate));
    std::uint8_t tier_completion = state.assigned_string_mask;
    const std::uint8_t fine_members = string_count(fine_group);
    if (fine.valid && fine_members >= 2U && fine_members < 4U) {
      const SpectralHeadEvidence tier_spectral =
          string_fret_spectral_head_evidence(candidate);
      // A selected candidate can accumulate a complete multi-source fine fit
      // before its ordinary attack gate activates the MIDI voice.  Treat that
      // resolved pair as the live base for a bounded one-lane completion so
      // the first emitted frame does not unnecessarily expose only the pair.
      const bool established_or_fresh_resolved_group =
          state.active || fine.multi_source_observed;
      const std::uint8_t completed_fine_group =
          bounded_spectral_tier_completion(
              established_or_fresh_resolved_group,
              state.assigned_string_mask, fine_group,
              playable_string_mask(candidate), tier_spectral,
              fine.added_member_beat_coherence, fine.component_energy);
      if (completed_fine_group != fine_group) {
        tier_completion = completed_fine_group;
      }
    }
    const std::uint8_t tier_members = string_count(tier_completion);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (tier_completion != state.assigned_string_mask) {
      TierCompletionDisposition disposition =
          TierCompletionDisposition::accepted;
      if ((tier_completion & primary_bit) == 0U || tier_members < 2U ||
          tier_members > 4U) {
        disposition = TierCompletionDisposition::missing_primary;
      } else if ((tier_completion & other_owned_strings) != 0U) {
        disposition = TierCompletionDisposition::conflicts_other_owned;
      } else if ((tier_completion & allocated_extra_strings) != 0U) {
        disposition = TierCompletionDisposition::conflicts_allocated;
      } else if (tier_members - 1U > candidate_extra_capacity) {
        disposition = TierCompletionDisposition::over_capacity;
      }
      tier_completion_dispositions_[candidate] = disposition;
    }
#endif
    if (tier_completion != state.assigned_string_mask &&
        (tier_completion & primary_bit) != 0U && tier_members >= 2U &&
        tier_members <= 4U &&
        (tier_completion & other_owned_strings) == 0U &&
        (tier_completion & allocated_extra_strings) == 0U &&
        tier_members - 1U <= candidate_extra_capacity) {
      proposed_group = tier_completion;
      temporal_group_selected = true;
      selector_group_masks_[candidate] = tier_completion;
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

    state.latest_unison_proposal_mask = proposed_group;
    state.latest_unison_proposal_temporal = temporal_group_selected;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    state.diagnostic_unison_proposal_mask = proposed_group;
    state.diagnostic_unison_temporal = temporal_group_selected;
#endif

    if (proposed_group != primary_bit) {
      const bool jointly_reserved =
          selector_group_masks_[candidate] == proposed_group;
      if (jointly_reserved) {
        // The joint selector has already excluded every competing pitch from
        // these physical lanes using the three-second fine fit, spectral tier
        // margin, and beat-window corroboration. Repeating the short generic
        // profile evidence gate here only discards the first frames of each
        // otherwise identical reserved segment.
        state.pending_unison_mask = proposed_group;
        state.unison_evidence_ticks = unison_evidence_ticks;
      } else if (state.pending_unison_mask == proposed_group) {
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
    const std::uint8_t confirmed_members =
        string_count(state.assigned_string_mask);
    const bool confirmed_current_group =
        confirmed_members >= 3U &&
        proposed_group == state.assigned_string_mask && fine.valid &&
        fine.member_mask == state.assigned_string_mask;
    if (confirmed_current_group) {
      if (state.committed_unison_confirmed_ticks <
          std::numeric_limits<std::uint16_t>::max()) {
        ++state.committed_unison_confirmed_ticks;
      }
    } else {
      state.committed_unison_confirmed_ticks = 0U;
    }
  }
}

double PolyphonicPitchDetector::calibration_similarity(
    std::size_t candidate, std::size_t string) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      string >= kM3OpenNotes.size()) {
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
  return calibration_similarity_from_energy_profile(candidate, string,
                                                    current, total);
}

double PolyphonicPitchDetector::calibration_similarity_from_energy_profile(
    std::size_t candidate, std::size_t string,
    const std::array<double, kCalibrationHarmonicCount>& current,
    double total) const noexcept {
  if (candidate >= static_cast<std::size_t>(candidate_count_) ||
      string >= kM3OpenNotes.size() || total <= kScoreEpsilon) {
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
  return settled_calibration_similarity_from_fast_similarity(
      candidate, string, calibration_similarity(candidate, string));
}

double PolyphonicPitchDetector::settled_calibration_similarity_from_fast_similarity(
    std::size_t candidate, std::size_t string,
    double fast_similarity) const noexcept {
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
  return 0.80 * fast_similarity +
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
        profile_harmonic_energy(target, harmonic);
  }
  const PartialDetuningEvidence detuning =
      partial_detuning_trackers_[target].evidence();
  if (detuning.valid_mask != 0U) {
    observation.partial_detuning_cents = detuning.residual_cents;
    observation.partial_detuning_valid_mask = detuning.valid_mask;
  }
  if (calibrator_.observe(observation) &&
      calibrator_.status().phase == CalibrationSweepPhase::complete) {
    invalidate_fine_frequency_uniform_gram_cache();
  }
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
    if (state.active && state.spectral_duplicate_output_suppressed) {
      continue;
    }
    TunerVoice base_voice;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    base_voice.detected_midi_note =
        static_cast<std::uint8_t>(lowest_note_ + candidate);
#endif
    const bool dp_output_projected =
        state.dp_output_projection_note < 128U;
    base_voice.midi_note = candidate_midi_output_note(candidate);
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
    if (dp_output_projected) {
      if (coasting) {
        const std::uint16_t release = release_decisions();
        const double remaining =
            release > state.release_ticks
                ? static_cast<double>(release - state.release_ticks) /
                      static_cast<double>(release)
                : 0.0;
        base_voice.confidence_q15 = static_cast<std::uint16_t>(std::lround(
            static_cast<double>(state.retained_confidence_q15) * remaining));
      } else {
        const double normalized = std::clamp(
            (scores[candidate] - threshold) /
                (scores[candidate] + threshold),
            0.0, 1.0);
        base_voice.confidence_q15 = static_cast<std::uint16_t>(
            std::lround(normalized * 32767.0));
        if (tracking) {
          state.retained_confidence_q15 = base_voice.confidence_q15;
        }
      }
      // The projected MIDI identity belongs to a different resonator bin;
      // reporting the incumbent bin's cents as if they described that note
      // would make the tuner display falsely precise.
      base_voice.cents_valid = false;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      base_voice.detected_cents_valid = false;
#endif
    } else if (coasting) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      base_voice.detected_cents_q8 = state.retained_cents_q8;
      base_voice.detected_cents_valid = state.retained_cents_valid;
#endif
      base_voice.cents_q8 = candidate_output_cents_q8(
          candidate, state.retained_cents_q8);
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
      const std::uint8_t detected_note =
          static_cast<std::uint8_t>(lowest_note_ + candidate);
      const bool corrected_boundary_projection =
          phase_cents.output_projection_valid &&
          candidate_output_note(candidate) != detected_note;
      if (phase_cents.valid || corrected_boundary_projection) {
        const auto detected_cents_q8 = static_cast<std::int16_t>(
            std::clamp<long>(
                std::lround(phase_cents.cents * 256.0),
                std::numeric_limits<std::int16_t>::min(),
                std::numeric_limits<std::int16_t>::max()));
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        base_voice.detected_cents_q8 = detected_cents_q8;
        base_voice.detected_cents_valid =
            phase_cents.output_projection_valid;
#endif
        base_voice.cents_q8 = candidate_output_cents_q8(
            candidate, detected_cents_q8);
        base_voice.cents_valid =
            phase_cents.valid ||
            (base_voice.cents_q8 >= -50 * 256 &&
             base_voice.cents_q8 <= 50 * 256);
      }
      if (tracking) {
        if (base_voice.cents_valid) {
          state.retained_cents_q8 = static_cast<std::int16_t>(
              std::clamp<long>(
                  std::lround(phase_cents.cents * 256.0),
                  std::numeric_limits<std::int16_t>::min(),
                  std::numeric_limits<std::int16_t>::max()));
          state.retained_cents_valid = true;
          state.retained_confidence_q15 = base_voice.confidence_q15;
        } else if (state.retained_cents_valid) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
          base_voice.detected_cents_q8 = state.retained_cents_q8;
          base_voice.detected_cents_valid = true;
#endif
          base_voice.cents_q8 = candidate_output_cents_q8(
              candidate, state.retained_cents_q8);
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
    std::uint8_t strings = projected_output_string_mask(
        state.assigned_string_mask, state.assigned_string,
        state.spectral_lane_mask, state.continuity_lane_mask);
    if (state.active && state.fine_beat_pruning_mask != 0U) {
      strings = state.midi_voice_mask;
    }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    // The fine-mask pruning experiment is output-only.  Score the exact lanes
    // that the diagnostic MIDI path has emitted rather than the wider internal
    // assignment that remains available for subsequent evidence updates.
    if (state.active &&
        ((diagnostic_fine_mask_pruning_enabled_ &&
          state.diagnostic_fine_mask_pruning_mask != 0U) ||
         (diagnostic_fine_beat_pruning_enabled_ &&
          state.diagnostic_fine_beat_pruning_mask != 0U))) {
      strings = state.midi_voice_mask;
    }
#endif
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
  retained_unison_dispositions_.fill(
      RetainedUnisonDisposition::not_applicable);
  fine_group_dispositions_.fill(FineGroupDisposition::unresolved);
  if (offline_replay_diagnostics_enabled_) {
  candidate_admission_diagnostics_ = {};
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  spectral_reacquisition_dispositions_.fill(
      ObservedUnisonReacquisitionDisposition::no_cache);
  unison_cache_refresh_dispositions_.fill(
      UnisonCacheRefreshDisposition::inactive);
#endif
  }
#endif
  ++decision_counter_;
  std::array<double, kMaxCandidates> scores{};
  std::array<double, kMaxCandidates> fundamentals{};
  std::array<double, kMaxCandidates> narrow_fundamentals{};
  std::array<bool, kMaxCandidates> selected{};
  const std::size_t count = static_cast<std::size_t>(candidate_count_);
  bool had_active_voice = false;
  bool had_active_multi_string_group = false;
  std::array<bool, kMaxCandidates> resumable_candidates{};
  for (std::size_t candidate = 0U; candidate < count; ++candidate) {
    const CandidateState& state = candidate_states_[candidate];
    const FineFrequencyEvidenceState& fine =
        fine_frequency_evidence_states_[candidate];
    had_active_voice = had_active_voice || state.active;
    const std::uint8_t owned = static_cast<std::uint8_t>(
        state.assigned_string_mask | state.midi_voice_mask);
    const bool resolved_fine_resume =
        is_resolved_unison_resume_candidate(
            state.active, owned, fine.valid, fine.multi_source_observed,
            fine.robust_pairwise_beat_connected,
            fine.minimum_pairwise_beat_coherence, fine.member_mask);
    resumable_candidates[candidate] = resolved_fine_resume;
    had_active_multi_string_group =
        had_active_multi_string_group || resolved_fine_resume;
  }
  const bool ordinary_minimum_evidence =
      static_cast<double>(signal_samples_) >=
      sample_rate_ * kSingleVoiceEvidenceSeconds;
  const bool minimum_evidence =
      had_active_multi_string_group || ordinary_minimum_evidence;
  const bool active_resume = minimum_evidence &&
                             !ordinary_minimum_evidence &&
                             had_active_multi_string_group;
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
  const bool below_signal_floor = fast_energy_ < signal_floor();
  const bool below_slow_energy_ratio =
      fast_energy_ < slow_energy_ * kSilenceEnergyRatio;
  bool quiet = !minimum_evidence || below_signal_floor ||
               ((!had_active_voice || rapid_mute) &&
                below_slow_energy_ratio);
  const double threshold = fast_energy_ * kCandidateCoherenceRatio;
  if (!quiet) {
    for (std::size_t candidate = 0U; candidate < count; ++candidate) {
      double score = 0.0;
      for (std::size_t harmonic = 0U; harmonic < kHarmonicCount; ++harmonic) {
        const Cell& cell = cells_[cell_index(candidate, harmonic)];
        if (!cell.enabled) {
          continue;
        }
        double energy = cell.fast_real * cell.fast_real +
                        cell.fast_imaginary * cell.fast_imaginary;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        if (diagnostic_selection_window_only_ &&
            !diagnostic_correlation_shadow_only_) {
          energy = cell.diagnostic_selection_real *
                       cell.diagnostic_selection_real +
                   cell.diagnostic_selection_imaginary *
                       cell.diagnostic_selection_imaginary;
        }
#endif
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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (offline_replay_diagnostics_enabled_) {
      constexpr std::size_t kPitchBandCount = 4U;
      constexpr std::uint8_t kPitchBandSemitones = 12U;
      std::array<double, kPitchBandCount> pitch_band_score_peak{};
      std::array<double, kPitchBandCount> pitch_band_fundamental_peak{};
      const auto pitch_band_for_note = [](std::uint8_t note) noexcept {
        const std::uint8_t offset =
            note > kM3OpenNotes.front()
                ? static_cast<std::uint8_t>(note - kM3OpenNotes.front())
                : 0U;
        return std::min<std::size_t>(
            kPitchBandCount - 1U, offset / kPitchBandSemitones);
      };
      for (std::size_t candidate = 0U; candidate < count; ++candidate) {
        if (playable_string_mask(candidate) == 0U) {
          continue;
        }
        const std::size_t band = pitch_band_for_note(
            static_cast<std::uint8_t>(lowest_note_ + candidate));
        pitch_band_score_peak[band] =
            std::max(pitch_band_score_peak[band], scores[candidate]);
        pitch_band_fundamental_peak[band] = std::max(
            pitch_band_fundamental_peak[band], fundamentals[candidate]);
      }
      for (std::size_t candidate = 0U; candidate < count; ++candidate) {
        CandidateAdmissionDiagnostics& diagnostic =
            candidate_admission_diagnostics_[candidate];
        const std::size_t pitch_band = pitch_band_for_note(
            static_cast<std::uint8_t>(lowest_note_ + candidate));
        diagnostic.score_threshold_ratio =
            scores[candidate] / std::max(threshold, kScoreEpsilon);
        diagnostic.fundamental_score_ratio = fundamentals[candidate] /
                                             std::max(scores[candidate],
                                                      kScoreEpsilon);
        diagnostic.pitch_band_score_peak_ratio =
            scores[candidate] /
            std::max(pitch_band_score_peak[pitch_band], kScoreEpsilon);
        diagnostic.pitch_band_fundamental_peak_ratio =
            fundamentals[candidate] /
            std::max(pitch_band_fundamental_peak[pitch_band], kScoreEpsilon);
        diagnostic.pitch_band = static_cast<std::uint8_t>(pitch_band);
        diagnostic.playable_string_mask = playable_string_mask(candidate);
        diagnostic.active = candidate_states_[candidate].active;
        diagnostic.direct_fundamental_peak =
            has_direct_fundamental_peak(scores, fundamentals, candidate, count);
        diagnostic.local_peak = is_local_peak(scores, candidate, count);
        diagnostic.candidate_evidence =
            has_m3_candidate_evidence(scores, fundamentals, candidate, count);
        diagnostic.calibrated_direct_support =
            profile_mode_ == ProfileMode::m3 &&
            has_calibrated_direct_support(scores, fundamentals, candidate,
                                          count, threshold);
        if (profile_mode_ == ProfileMode::m3) {
          const auto note = static_cast<std::uint8_t>(lowest_note_ + candidate);
          for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
            const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
            if ((diagnostic.playable_string_mask & bit) == 0U) {
              continue;
            }
            const StringCalibrationPoint* point = calibrator_.bank().point(
                string, note - kM3OpenNotes[string]);
            if (point == nullptr ||
                point->quality == CalibrationPointQuality::missing) {
              continue;
            }
            diagnostic.calibrated_string_mask = static_cast<std::uint8_t>(
                diagnostic.calibrated_string_mask | bit);
            const double similarity = calibration_similarity(candidate, string);
            if (similarity > diagnostic.best_calibration_similarity) {
              diagnostic.second_calibration_similarity =
                  diagnostic.best_calibration_similarity;
              diagnostic.best_calibration_similarity = similarity;
              diagnostic.best_calibrated_string =
                  static_cast<std::uint8_t>(string);
            } else if (similarity >
                       diagnostic.second_calibration_similarity) {
              diagnostic.second_calibration_similarity = similarity;
            }
          }
        }
      }
    }
#endif
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

  filter_resume_selection(active_resume, resumable_candidates, selected,
                          count);

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
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  quiet_disposition_ = classify_quiet_disposition(
      minimum_evidence, below_signal_floor, had_active_voice, rapid_mute,
      below_slow_energy_ratio, multi_voice_evidence, last_signal_loss_);
#endif
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
  update_fine_frequency_evidence(selected, scores, fundamentals, threshold,
                                 quiet);
  update_spectral_lane_states(selected, quiet);
  assign_m3_strings(selected);
  update_adjacent_spectral_duplicate_suppression();
  apply_calibrated_dp_replacements(selected, scores, fundamentals, threshold,
                                   quiet, count);
  update_harmonic_profile_memory(selected);
  update_beat_evidence(selected);
  infer_m3_unison_strings(selected);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  update_fine_mask_pruning_output_projection(
      selected, scores, fundamentals, threshold, quiet);
#endif
  update_fine_beat_pruning_output_projection(
      selected, scores, fundamentals, threshold, quiet);
  update_calibration_tuning_offset(selected);
  update_calibrated_output_notes(decision, selected, selected_voice_count);
  update_calibrated_dp_output_projections(
      decision, selected, scores, fundamentals, threshold, quiet, count);
#if defined(M3_UNISON_SPECTRAL_SHADOW)
  if (offline_replay_diagnostics_enabled_) {
    update_unison_reacquisition_state(selected, scores, fundamentals,
                                       threshold, quiet);
  }
#endif
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
    const bool suppress_spectral_duplicate =
        spectral_duplicate_suppressed_[candidate];
    if (suppress_spectral_duplicate &&
        !state.spectral_duplicate_output_suppressed) {
      if (append_candidate_note_off(decision, candidate)) {
        state.midi_voice_mask = 0U;
        state.spectral_duplicate_output_suppressed = true;
      }
    } else if (!suppress_spectral_duplicate &&
               state.spectral_duplicate_output_suppressed &&
               selected[candidate]) {
      if (midi_routing_ == MidiRouting::per_voice) {
        state.spectral_duplicate_output_suppressed = false;
      } else if (append_transition(
                     decision, TransitionKind::note_on,
                     candidate_midi_output_note(candidate),
                     dynamic_velocity())) {
        state.spectral_duplicate_output_suppressed = false;
      }
    }
    if (selected[candidate]) {
      state.release_ticks = 0U;
      if (profile_mode_ == ProfileMode::m3 &&
          midi_routing_ == MidiRouting::per_voice) {
        const std::uint8_t desired =
            state.spectral_duplicate_output_suppressed
                ? 0U
                : projected_output_string_mask(
                      state.assigned_string_mask, state.assigned_string,
                      state.spectral_lane_mask,
                      state.continuity_lane_mask);
        std::uint8_t pruned_desired = desired;
        if (state.fine_beat_pruning_mask != 0U) {
          pruned_desired = static_cast<std::uint8_t>(
              pruned_desired & state.fine_beat_pruning_mask);
        }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        if (diagnostic_fine_mask_pruning_enabled_ &&
            state.diagnostic_fine_mask_pruning_mask != 0U) {
          pruned_desired = static_cast<std::uint8_t>(
              pruned_desired & state.diagnostic_fine_mask_pruning_mask);
        }
        if (diagnostic_fine_beat_pruning_enabled_ &&
            state.diagnostic_fine_beat_pruning_mask != 0U) {
          pruned_desired = static_cast<std::uint8_t>(
              pruned_desired & state.diagnostic_fine_beat_pruning_mask);
        }
#endif
        const std::uint8_t removed = static_cast<std::uint8_t>(
            state.midi_voice_mask & ~pruned_desired);
        const std::uint8_t added = static_cast<std::uint8_t>(
            pruned_desired & ~state.midi_voice_mask);
        const std::uint8_t note = candidate_midi_output_note(candidate);
        const std::size_t required =
            string_count(removed) + string_count(added);
        if (required > decision.transitions.capacity() -
                           decision.transitions.size()) {
          ++active_count;
          continue;
        }
        for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          if ((removed & bit) != 0U) {
            static_cast<void>(append_transition(
                decision, TransitionKind::note_off, note, 0U, string));
          }
        }
        const std::uint8_t velocity = dynamic_velocity();
        for (std::uint8_t string = 0U; string < kM3OpenNotes.size(); ++string) {
          const std::uint8_t bit = static_cast<std::uint8_t>(1U << string);
          if ((added & bit) != 0U) {
            static_cast<void>(append_transition(
                decision, TransitionKind::note_on, note, velocity, string));
          }
        }
        state.midi_voice_mask = pruned_desired;
      }
      ++active_count;
      continue;
    }
    const std::uint8_t handoff_target_code =
        selector_atomic_handoff_target_for_incumbent_[candidate];
    if (handoff_target_code != 0U) {
      const std::size_t handoff_target = handoff_target_code - 1U;
      if (append_atomic_candidate_handoff(
              decision, candidate, handoff_target, dynamic_velocity())) {
        continue;
      }
      if (handoff_target < count) {
        selected[handoff_target] = false;
        selector_atomic_handoff_targets_[handoff_target] = false;
      }
      selected[candidate] = true;
      state.release_ticks = 0U;
      ++active_count;
      continue;
    }
    if (should_handoff_coasting_candidate_to_resolved_group(candidate,
                                                             selected) ||
        should_handoff_adjacent_coasting_candidate(
            candidate, scores, fundamentals, selected,
            selected_voice_count, quiet)) {
      if (append_candidate_note_off(decision, candidate)) {
        state = {};
        continue;
      }
    }
    if (state.release_ticks < std::numeric_limits<std::uint16_t>::max()) {
      ++state.release_ticks;
    }
    if (state.release_ticks >= candidate_release_decisions(candidate, quiet)) {
      if (append_candidate_note_off(decision, candidate)) {
        state = {};
      } else {
        ++active_count;
      }
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
    const bool atomic_handoff =
        selector_atomic_handoff_targets_[candidate];
    if (!atomic_handoff && fast_energy_ < slow_energy_ * kAttackEnergyRatio) {
      state.attack_ticks = 0U;
      state.evidence_ticks = 0U;
      state.evidence_gap_ticks = 0U;
      continue;
    }
    if (!atomic_handoff && state.evidence_ticks == 0U) {
      state.attack_ticks = 0U;
      continue;
    }
    if (!atomic_handoff && had_active_voice) {
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
    if (atomic_handoff) {
      state.attack_ticks = attack_decisions();
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
  update_group_continuity_trackers(selected, scores, fundamentals, threshold,
                                   quiet);
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
  if (profile_mode_ == ProfileMode::m3) {
    spectral_lane_decimation_sum_ += dc_blocked;
    group_continuity_decimation_sum_ += sample;
    ++spectral_lane_decimation_count_;
    ++group_continuity_decimation_count_;
    if (spectral_lane_decimation_count_ == spectral_lane_decimation_) {
      const double decimated =
          spectral_lane_decimation_sum_ /
          static_cast<double>(spectral_lane_decimation_count_);
      for (SpectralLaneState& state : spectral_lane_states_) {
        if (state.tracking) {
          state.tracker.observe(decimated);
        }
      }
      spectral_lane_decimation_sum_ = 0.0;
      spectral_lane_decimation_count_ = 0U;
    }
    if (group_continuity_decimation_count_ == group_continuity_decimation_) {
      const double decimated =
          group_continuity_decimation_sum_ /
          static_cast<double>(group_continuity_decimation_count_);
      for (GroupContinuityTrackerState& state :
           group_continuity_trackers_) {
        if (state.tracking) {
          state.tracker.observe(decimated);
        }
      }
      group_continuity_decimation_sum_ = 0.0;
      group_continuity_decimation_count_ = 0U;
    }
  }
  const double power = dc_blocked * dc_blocked;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  const double input_energy_decay = diagnostic_input_energy_decay_;
#else
  const double input_energy_decay = correlation_decay;
#endif
  const double energy_mix = 1.0 - input_energy_decay;
  fast_energy_ = input_energy_decay * fast_energy_ + energy_mix * power;
  const double slow_energy_mix = 1.0 - slow_energy_decay;
  slow_energy_ = slow_energy_decay * slow_energy_ + slow_energy_mix * power;
  for (std::size_t index = 0U; index < enabled_cell_count_; ++index) {
    update_cell(cells_[enabled_cell_indices_[index]], dc_blocked);
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
  const bool above_signal_floor = fast_energy_ >= signal_floor();
  const bool signal_present =
      above_signal_floor &&
      (has_active_voice ||
       fast_energy_ >= slow_energy_ * kSilenceEnergyRatio);
  if (!signal_present) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    if (signal_present_) {
      last_signal_loss_ = above_signal_floor
                              ? SignalLossDisposition::inactive_energy_ratio
                              : SignalLossDisposition::signal_floor;
    }
#endif
    if (signal_present_) {
      for (CandidateState& state : candidate_states_) {
        state.evidence_ticks = 0U;
      }
      harmonic_energy_memory_ = {};
      long_harmonic_energy_memory_ = {};
      harmonic_memory_updates_ = {};
      phase_cents_states_ = {};
      beat_evidence_states_ = {};
      const std::uint16_t established_group_samples =
          static_cast<std::uint16_t>(std::clamp(
              std::ceil(kM3RetainedUnisonRobustConfirmationSeconds *
                        sample_rate_ /
                        (static_cast<double>(kDecisionQuantum) *
                         fine_frequency_decimation_decisions_ *
                         kFineFrequencyAnalysisStride)),
              1.0,
              static_cast<double>(
                  std::numeric_limits<std::uint16_t>::max())));
      for (std::size_t candidate = 0U;
           candidate < static_cast<std::size_t>(candidate_count_);
           ++candidate) {
        FineFrequencyEvidenceState& fine =
            fine_frequency_evidence_states_[candidate];
        const std::uint8_t members = string_count(fine.member_mask);
        const bool committed_resolved_group =
            fine.valid && members >= 2U && members <= 4U &&
            fine.pending_member_mask == fine.member_mask &&
            fine.pending_count >= established_group_samples;
        const bool candidate_committed_group =
            committed_fine_group_matches_assignment(
                fine, candidate_states_[candidate].active,
                candidate_states_[candidate].assigned_string_mask);
        if (!retain_fine_frequency_history_across_gap(
                fine, established_group_samples) &&
            !candidate_committed_group) {
          fine = {};
        } else if (!committed_resolved_group &&
                   !candidate_committed_group) {
          // Keep only the phasor history. The previous articulation's group
          // cannot influence assignment after the gap until fresh samples
          // re-fit and re-confirm it.
          fine.member_mask = 0U;
          fine.pending_member_mask = 0U;
          fine.pending_count = 0U;
          fine.minimum_pairwise_beat_coherence = 0.0;
          fine.pending_minimum_pairwise_beat_coherence = 0.0;
          fine.robust_pairwise_beat_connected = false;
          fine.pending_robust_pairwise_beat_connected = false;
          fine.multi_source_observed = false;
          fine.valid = false;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
          fine.disposition = FineFrequencyDisposition::unresolved;
          fine.unresolved_reason = FineFrequencyUnresolvedReason::analysis_wait;
#endif
        }
      }
      // Candidate/MIDI state still releases normally. Fine-frequency history
      // receives no samples during silence and its decimated path clears every
      // retained observation after the same bounded maximum gap. Only an
      // already-valid, beat-supported physical group bridges a natural
      // sub-gap; collecting and single-source histories are discarded so
      // separate short articulations cannot be fused into a false group.
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
