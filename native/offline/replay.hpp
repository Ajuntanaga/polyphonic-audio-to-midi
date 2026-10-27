#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <vector>

#include "m3/harmonic_evidence.hpp"
#include "m3/partial_detuning_evidence.hpp"
#include "m3/string_calibration.hpp"
#include "m3/tuner_telemetry.hpp"
#include "m3/types.hpp"
#include "m3/unison_spectral_classifier.hpp"
#include "unison_spectral_shadow.hpp"

namespace m3::offline {

class FrequencyWindowCapture;

struct HannBeatEdgeSummary final {
  std::uint64_t frames{};
  double difference_hz{};
  double minimum_window_seconds{std::numeric_limits<double>::infinity()};
  double maximum_window_seconds{};
  double original_sum{};
  double weighted_sum{};
  double original_minimum{1.0};
  double original_maximum{};
  double weighted_minimum{1.0};
  double weighted_maximum{};
};

struct FrequencyRefinementSummary final {
  std::uint64_t frames{};
  std::uint64_t valid_frames{};
  std::uint64_t bounded_frames{};
  std::uint64_t beat_supported_frames{};
  std::uint64_t heldout_gain_frames{};
  std::uint64_t qualified_frames{};
  std::uint64_t useful_gain_frames{};
  double train_sum{};
  double test_refit_sum{};
  double test_prediction_sum{};
  double maximum_cents{};
  double minimum_conditioning{1.0};
  std::array<double, 8U> correction_cents_sum{};
};

enum class ReplayFineHistoryCarryDisposition : std::uint8_t {
  selected,
  quiet,
  inactive,
  fine_unavailable,
  invalid_size,
  mask_mismatch,
  below_decay_floor,
  no_direct_fundamental,
  eligible,
  count,
};

struct UnisonSpectralShadowTemplateBank;
inline constexpr std::size_t kSpectralShadowMarginThresholdCount = 11U;
inline constexpr std::array<double, 5U>
    kSpectralTierAddedMemberRatioFloors{0.02, 0.04, 0.06, 0.08, 0.10};
inline constexpr std::array<double, 8U> kFineUniqueMemberImprovementFloors{
    0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.04, 0.08};
inline constexpr std::array<double, 13U> kFineMaskComplexityPenalties{
    0.0,    0.00001, 0.00002, 0.00005, 0.0001, 0.0002, 0.0005,
    0.001,  0.002,   0.005,   0.01,    0.02,   0.04};
inline constexpr std::array<double, 10U> kFineMaskPosteriorWeights{
    0.0, 0.00025, 0.0005, 0.001, 0.002,
    0.005, 0.01,    0.02,   0.04,  0.08};
inline constexpr std::array<double, 7U> kFineMaskBeatCoherenceFloors{
    0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30};
inline constexpr std::uint8_t kFineMaskBeatPruningMinimumMidiNote = 56U;
inline constexpr std::size_t kFineMaskModelRankBucketCount = 155U;
inline constexpr std::uint8_t kFineMaskComplexityMinimumMidiNote = 52U;
inline constexpr std::array<double, 9U> kSpectralTierBeatMaximums{
    0.21, 0.22, 0.23, 0.24, 0.25, 0.275, 0.30, 0.325, 0.35};
inline constexpr std::size_t kCandidateAdmissionRatioBinCount = 41U;
inline constexpr std::size_t kCandidateAdmissionEvidenceFlagCount = 32U;
inline constexpr std::size_t kSpectralShadowIntervalBinCount =
    2U * kMaxCandidates + 1U;
inline constexpr std::size_t kCandidateCalibrationPopulationClassCount = 3U;
inline constexpr std::size_t kCandidateCalibrationSimilarityBinCount = 21U;
inline constexpr std::size_t kCandidateCalibrationJointRowCount =
    kCandidateCalibrationPopulationClassCount *
    kCandidateAdmissionRatioBinCount *
    kCandidateCalibrationSimilarityBinCount;
inline constexpr std::array<double, 4U>
    kSpectralShadowCalibrationSimilarityFloors{0.85, 0.90, 0.95, 0.97};
inline constexpr std::array<double, 4U>
    kSpectralShadowCalibrationMarginFloors{0.02, 0.10, 0.25, 0.50};
inline constexpr std::size_t kSpectralShadowCalibrationPolicyCount =
    kSpectralShadowCalibrationSimilarityFloors.size() *
    kSpectralShadowCalibrationMarginFloors.size();
// Offline-only gate grid for measuring whether pitch-band-relative evidence
// and calibrated physical-string identity can safely recover candidates below
// the broadband threshold.  The grid never changes detector state or MIDI.
inline constexpr std::array<double, 2U>
    kCandidateBandCalibrationGlobalScoreFloors{0.05, 0.20};
inline constexpr std::array<double, 3U>
    kCandidateBandCalibrationBandScoreFloors{0.70, 0.80, 0.90};
inline constexpr std::array<double, 3U>
    kCandidateBandCalibrationBandFundamentalFloors{0.70, 0.80, 0.90};
inline constexpr std::array<double, 2U>
    kCandidateBandCalibrationSimilarityFloors{0.97, 0.99};
inline constexpr std::array<double, 2U>
    kCandidateBandCalibrationMarginFloors{0.01, 0.02};
inline constexpr std::array<std::uint8_t, 4U>
    kCandidateBandCalibrationMinimumStrings{0U, 4U, 6U, 7U};
inline constexpr std::array<bool, 2U>
    kCandidateBandCalibrationRequireUniquePlayable{false, true};
inline constexpr std::size_t kCandidateBandCalibrationPolicyCount =
    kCandidateBandCalibrationGlobalScoreFloors.size() *
    kCandidateBandCalibrationBandScoreFloors.size() *
    kCandidateBandCalibrationBandFundamentalFloors.size() *
    kCandidateBandCalibrationSimilarityFloors.size() *
    kCandidateBandCalibrationMarginFloors.size() *
    kCandidateBandCalibrationMinimumStrings.size() *
    kCandidateBandCalibrationRequireUniquePlayable.size();
inline constexpr std::array<double, 3U>
    kCombinedCandidateGlobalScoreFloors{0.05, 0.10, 0.20};
inline constexpr std::array<std::uint8_t, 4U>
    kCombinedCandidateMinimumStrings{0U, 4U, 6U, 7U};
inline constexpr std::array<double, 4U>
    kCombinedCandidateSpectralMaximumErrors{0.05, 0.10, 0.15, 0.20};
inline constexpr std::array<double, 4U>
    kCombinedCandidateSpectralMarginFloors{0.0, 0.02, 0.04, 0.08};
inline constexpr std::size_t kCombinedCandidatePolicyCount =
    kCombinedCandidateGlobalScoreFloors.size() *
    kCombinedCandidateMinimumStrings.size() *
    kCombinedCandidateSpectralMaximumErrors.size() *
    kCombinedCandidateSpectralMarginFloors.size();
// Replay-only audit for the incremental 0.10--0.20 global-score corridor.
// A relaxed candidate still has to clear every accepted local-band and
// calibration gate, then agree with the causal string/fret posterior.  The
// grid measures whether that extra agreement can separate useful quiet chord
// tones from wrong-string admissions before production behavior is touched.
inline constexpr std::array<double, 4U>
    kRelaxedBandPosteriorProbabilityFloors{0.50, 0.60, 0.70, 0.80};
inline constexpr std::array<double, 4U>
    kRelaxedBandPosteriorMarginFloors{0.05, 0.10, 0.20, 0.30};
inline constexpr std::size_t kRelaxedBandPosteriorPolicyCount =
    kRelaxedBandPosteriorProbabilityFloors.size() *
    kRelaxedBandPosteriorMarginFloors.size();
inline constexpr std::array<double, 4U>
    kRelaxedBandSpectralMaximumErrors{0.05, 0.10, 0.15, 0.20};
inline constexpr std::size_t kSpectralSingleMetricBinCount = 41U;
inline constexpr std::size_t kSpectralSingleGapThresholdCount = 8U;
inline constexpr std::array<double, kSpectralSingleGapThresholdCount>
    kSpectralSingleGapThresholds{0.0, 0.005, 0.01, 0.02,
                                 0.04, 0.08, 0.12, 0.20};
inline constexpr std::size_t kRelaxedBandSpectralPolicyCount =
    kRelaxedBandSpectralMaximumErrors.size() *
    kSpectralSingleGapThresholds.size();
inline constexpr std::size_t kClassifierSubsetDispositionCount =
    static_cast<std::size_t>(ClassifierSubsetDisposition::count);
inline constexpr std::size_t kCandidatePopulationClassCount = 2U;
inline constexpr std::size_t kSelectionDispositionCount = 6U;
inline constexpr std::size_t kQuietDispositionCount = 8U;
inline constexpr std::size_t kTierCompletionDispositionCount = 6U;
inline constexpr std::array<double, 10U>
    kUnisonReacquisitionHoldSeconds{0.05, 0.10, 0.20, 0.30, 0.50,
                                    1.00, 2.00, 4.00, 6.00, 8.00};
inline constexpr std::size_t kUnisonReacquisitionHoldCount =
    kUnisonReacquisitionHoldSeconds.size();
inline constexpr std::array<double, 4U>
    kArticulatedUnisonReacquisitionGapSeconds{0.25, 0.50, 0.75, 1.00};
inline constexpr std::array<double, 3U>
    kArticulatedUnisonReacquisitionRevalidationSeconds{0.20, 0.35, 0.50};
inline constexpr std::size_t kArticulatedUnisonReacquisitionPolicyCount =
    kArticulatedUnisonReacquisitionGapSeconds.size() *
    kArticulatedUnisonReacquisitionRevalidationSeconds.size();
inline constexpr std::array<double, 7U>
    kObservedFingerprintMaximumSquaredDistances{0.005, 0.01, 0.02, 0.04,
                                                 0.08, 0.16, 0.32};
inline constexpr std::size_t
    kObservedFingerprintReacquisitionPolicyCount =
        kArticulatedUnisonReacquisitionPolicyCount *
        kObservedFingerprintMaximumSquaredDistances.size();
inline constexpr std::size_t
    kObservedFingerprintProductionCandidatePolicy =
        (1U * kArticulatedUnisonReacquisitionRevalidationSeconds.size()) *
        kObservedFingerprintMaximumSquaredDistances.size();
inline constexpr std::size_t
    kArticulatedUnisonReacquisitionDispositionCount = 15U;
inline constexpr std::size_t kSpectralReacquisitionDispositionCount =
    static_cast<std::size_t>(ObservedUnisonReacquisitionDisposition::count);
inline constexpr std::size_t kFineFrequencyUnresolvedReasonCount = 7U;
inline constexpr std::array<double, 4U>
    kFineResidualExpansionScoreFloors{0.20, 0.30, 0.40, 0.50};
inline constexpr std::array<double, 8U>
    kFineResidualExpansionThresholds{0.00, 0.01, 0.02, 0.04,
                                     0.05, 0.06, 0.07, 0.08};
inline constexpr std::size_t kFineResidualExpansionPolicyCount =
    kFineResidualExpansionScoreFloors.size() *
    kFineResidualExpansionThresholds.size();
inline constexpr std::array<std::uint8_t, 3U>
    kSelectedSubsetCompletionSupportFloors{2U, 3U, 4U};
// Three existing broadband policies followed by three pitch-band-normalized
// policies. The latter remain offline-only until the cross-corpus gate proves
// that local normalization plus the string/fret classifier is selective.
inline constexpr std::size_t kCandidateSpectralShadowPolicyCount = 6U;
inline constexpr std::size_t kCandidateSpectralShadowErrorThresholdCount = 6U;
inline constexpr std::size_t kCandidateSpectralShadowMarginThresholdCount = 6U;
inline constexpr std::size_t kCandidateSpectralShadowGateCount =
    kCandidateSpectralShadowErrorThresholdCount *
    kCandidateSpectralShadowMarginThresholdCount;
inline constexpr std::size_t kCandidateSpectralShadowIntervalBucketCount = 97U;

enum class CandidateSpectralPartitionClass : std::uint8_t {
  target_correct,
  target_wrong_string,
  other_false,
};

struct CandidateSpectralPartitionCell final {
  std::size_t row{};
  std::size_t string{kMaxVoices};
  CandidateSpectralPartitionClass classification{
      CandidateSpectralPartitionClass::other_false};
  bool valid{};
};

// Classifies one replay-only spectral admission into the exact aggregate and
// physical-string partition cells used by ReplayResult. Keeping this pure
// makes every safety class directly testable without synthesizing detector
// conditions that happen to select a candidate first.
[[nodiscard]] CandidateSpectralPartitionCell candidate_spectral_partition_cell(
    std::size_t policy, std::size_t gate, std::uint8_t member_mask,
    bool target_active, std::uint8_t expected_mask,
    bool note_only) noexcept;

inline constexpr std::array<std::uint32_t, 6U>
    kFalseWrongNoteAgeThresholdMilliseconds{50U, 100U, 200U,
                                             350U, 500U, 750U};
inline constexpr std::size_t kFalseWrongNoteAgeBucketCount =
    kFalseWrongNoteAgeThresholdMilliseconds.size() + 1U;
inline constexpr std::size_t kFalseWrongNoteCentsBucketCount = 22U;
inline constexpr std::size_t kTunerVoiceStateCount = 3U;
inline constexpr std::array<double, 12U> kCalibratedPitchRebinThresholds{
    0.0, 5.0, 10.0, 15.0, 20.0, 30.0,
    40.0, 50.0, 60.0, 70.0, 80.0, 90.0};
// Offline-only sweep of the production projected-center guard while retaining
// the production 50-cent improvement and two-decision consensus. This makes a
// wider guard earn its way across every corpus before production changes.
inline constexpr std::array<double, 10U>
    kCalibratedPitchRebinProjectedErrorThresholds{
        5.0, 10.0, 15.0, 20.0, 25.0,
        30.0, 35.0, 40.0, 45.0, 50.0};
inline constexpr std::size_t kCalibratedPitchRebinOutcomeCount = 4U;
inline constexpr std::size_t kCalibratedPitchRebinMemberBucketCount = 6U;
inline constexpr std::size_t kCalibratedPitchRebinAgeOutcomeBucketCount =
    kFalseWrongNoteAgeBucketCount * kCalibratedPitchRebinOutcomeCount;
inline constexpr std::size_t kCalibratedPitchRebinDirectionCount = 2U;
inline constexpr std::size_t kCalibratedPitchRebinDetailRowCount =
    kCalibratedPitchRebinThresholds.size() * kMaxVoices *
    kCalibrationFretCount * kCalibratedPitchRebinDirectionCount;

struct CalibratedPitchRebinResult final {
  std::uint8_t note{};
  std::int8_t fret_delta{};
  double error_improvement_cents{};
  double projected_error_cents{};
  bool changed{};
};

class CalibratedPitchRebinLatch final {
 public:
  [[nodiscard]] bool observe(bool eligible, std::uint8_t target_note,
                             std::uint16_t required_frames) noexcept;
  void reset() noexcept;

 private:
  std::uint8_t target_note_{128U};
  std::uint16_t consecutive_frames_{};
};

// Returns the causal age bucket measured from the newest currently active
// label onset.  The sentinel kFalseWrongNoteAgeBucketCount denotes invalid
// chronology or sample-rate input and is never emitted into replay totals.
[[nodiscard]] std::size_t false_wrong_note_age_bucket(
    std::uint64_t sample_index, std::uint64_t latest_active_start_sample,
    std::uint32_t sample_rate) noexcept;
// Twenty-one five-cent bins cover [-50,+50], and the final bin records an
// unavailable continuous tuner estimate.
[[nodiscard]] std::size_t false_wrong_note_cents_bucket(
    std::int16_t cents_q8, bool cents_valid) noexcept;
// Offline counterfactual only: compare the current cell with its adjacent
// frets on the already-assigned physical string.  It never invents a string,
// uses an unmeasured calibration point, or changes production MIDI.
[[nodiscard]] CalibratedPitchRebinResult calibrated_pitch_rebin(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret, double minimum_error_improvement_cents) noexcept;
[[nodiscard]] bool calibrated_pitch_rebin_projected_error_eligible(
    const CalibratedPitchRebinResult& projection,
    double maximum_projected_error_cents) noexcept;
[[nodiscard]] bool calibrated_pitch_rebin_context_eligible(
    std::size_t pitch_group_members, std::size_t label_age_bucket,
    std::size_t snapshot_distinct_note_count) noexcept;

struct MultiPartialPhaseCentsResult final {
  double cents{};
  double maximum_deviation_cents{};
  std::uint8_t partial_count{};
  bool valid{};
};

// Offline shadow only.  Upper-partial absolute phase offsets are corrected by
// the measured per-string stretch profile, then combined with a fixed-size
// median.  This tests a replacement cents source without changing detector
// selection or MIDI.
[[nodiscard]] MultiPartialPhaseCentsResult
robust_multi_partial_phase_cents(
    const PartialAbsoluteCentsEvidence& evidence,
    const StringCalibrationPoint& calibration,
    std::uint8_t minimum_partials,
    double maximum_deviation_cents) noexcept;

inline constexpr std::array<std::uint8_t, 2U>
    kMultiPartialPhaseMinimumPartials{2U, 3U};
inline constexpr std::array<double, 7U>
    kMultiPartialPhaseMaximumDeviations{
        2.0, 5.0, 10.0, 20.0, 30.0, 40.0, 50.0};
inline constexpr std::size_t kMultiPartialPhasePolicyCount =
    kMultiPartialPhaseMinimumPartials.size() *
    kMultiPartialPhaseMaximumDeviations.size();

enum class CalibratedAdjacentProjectionDisposition : std::uint8_t {
  invalid_input,
  current_point_unavailable,
  expected_adjacent_point_unavailable,
  expected_adjacent_not_better,
  improvement_below_threshold,
  available,
  count,
};

// Offline diagnostic for the one adjacent fret that a label says should have
// won. This refines the production projection_unavailable bucket without
// changing detector state or MIDI output.
[[nodiscard]] CalibratedAdjacentProjectionDisposition
classify_calibrated_adjacent_projection(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret, int expected_direction,
    double minimum_error_improvement_cents) noexcept;

enum class AdjacentWrongNoteProjectionDisposition : std::uint8_t {
  non_tracking,
  insufficient_polyphonic_context,
  too_young,
  multi_member,
  cents_unavailable,
  projection_unavailable,
  outside_projected_center_guard,
  collision,
  eligible_unapplied,
  count,
};

inline constexpr std::size_t kAdjacentWrongNoteDirectionCount = 2U;

// Replay-only amplitude-envelope relationship between neighboring pitch
// candidates. A leaked or drifting copy of one source tends to rise and fall
// with its real pitch, while two independently articulated chord tones need
// not. Histogram index zero is unready; indices 1..21 cover -1 through +1.
inline constexpr std::size_t kAdjacentEnvelopeCoherenceBinCount = 22U;
inline constexpr std::size_t kAdjacentSpectralErrorGapBinCount = 42U;

enum class AdjacentEnvelopePairClass : std::uint8_t {
  both_expected,
  one_expected,
  neither_expected,
  count,
};

struct AdjacentEnvelopeCoherenceState final {
  double mean_left{};
  double mean_right{};
  double variance_left{};
  double variance_right{};
  double covariance{};
  std::uint32_t observations{};
};

void observe_adjacent_envelope_coherence(
    AdjacentEnvelopeCoherenceState& state, double left, double right,
    double smoothing = 0.05) noexcept;
[[nodiscard]] double adjacent_envelope_coherence(
    const AdjacentEnvelopeCoherenceState& state) noexcept;
[[nodiscard]] std::size_t adjacent_envelope_coherence_bin(
    const AdjacentEnvelopeCoherenceState& state) noexcept;
// Index zero is unavailable. Indices 1..41 cover a signed false-minus-true
// single-source template error gap from -1 through +1. For two real or two
// false neighbors the absolute gap is recorded instead.
[[nodiscard]] std::size_t adjacent_spectral_error_gap_bin(
    double error_gap) noexcept;

enum class AdjacentWrongNoteLaneDisposition : std::uint8_t {
  unavailable,
  matches,
  mismatches,
  count,
};

inline constexpr std::size_t kAdjacentWrongNoteRawOutputLaneCount =
    2U * 2U *
    static_cast<std::size_t>(AdjacentWrongNoteLaneDisposition::count);

[[nodiscard]] constexpr std::size_t adjacent_wrong_note_raw_output_lane_index(
    bool raw_matches_nearest, bool output_changed,
    AdjacentWrongNoteLaneDisposition lane) noexcept {
  return ((raw_matches_nearest ? 1U : 0U) * 2U +
          (output_changed ? 1U : 0U)) *
             static_cast<std::size_t>(
                 AdjacentWrongNoteLaneDisposition::count) +
         static_cast<std::size_t>(lane);
}

enum class AdjacentWrongNoteExpectedPresence : std::uint8_t {
  absent,
  same_string,
  other_string,
  same_and_other_string,
  count,
};

inline constexpr std::size_t kAdjacentWrongNoteJointContextCount =
    static_cast<std::size_t>(
        AdjacentWrongNoteProjectionDisposition::count) *
    static_cast<std::size_t>(AdjacentWrongNoteExpectedPresence::count) *
    static_cast<std::size_t>(AdjacentWrongNoteLaneDisposition::count);

[[nodiscard]] constexpr std::size_t adjacent_wrong_note_joint_context_index(
    AdjacentWrongNoteProjectionDisposition projection,
    AdjacentWrongNoteExpectedPresence presence,
    AdjacentWrongNoteLaneDisposition lane) noexcept {
  return (static_cast<std::size_t>(projection) *
              static_cast<std::size_t>(
                  AdjacentWrongNoteExpectedPresence::count) +
          static_cast<std::size_t>(presence)) *
             static_cast<std::size_t>(
                 AdjacentWrongNoteLaneDisposition::count) +
         static_cast<std::size_t>(lane);
}

inline constexpr std::size_t kAdjacentExpectedCandidateContextCount =
    kSelectionDispositionCount *
    static_cast<std::size_t>(AdjacentWrongNoteExpectedPresence::count) *
    static_cast<std::size_t>(AdjacentWrongNoteLaneDisposition::count);

[[nodiscard]] constexpr std::size_t
adjacent_expected_candidate_context_index(
    std::size_t selection, AdjacentWrongNoteExpectedPresence presence,
    AdjacentWrongNoteLaneDisposition lane) noexcept {
  return (selection *
              static_cast<std::size_t>(
                  AdjacentWrongNoteExpectedPresence::count) +
          static_cast<std::size_t>(presence)) *
             static_cast<std::size_t>(
                 AdjacentWrongNoteLaneDisposition::count) +
         static_cast<std::size_t>(lane);
}

struct AdjacentWrongNoteProjectionContext final {
  bool tracking{};
  bool polyphonic_context{};
  bool old_enough{};
  bool single_member{};
  bool cents_available{};
  bool projection_available{};
  bool projected_center_inside_guard{};
  bool collision{};
};

[[nodiscard]] AdjacentWrongNoteProjectionDisposition
classify_adjacent_wrong_note_projection(
    const AdjacentWrongNoteProjectionContext& context) noexcept;
[[nodiscard]] AdjacentWrongNoteExpectedPresence
classify_adjacent_wrong_note_expected_presence(
    const TunerSnapshot& snapshot, std::uint8_t expected_note,
    std::uint8_t observed_string) noexcept;

struct CandidateAdmissionRescuePolicy final {
  double score_threshold_ratio{};
  double fundamental_score_ratio{};
};

// Exact replay-only selector counterfactual. Values may only reduce the
// production fretted-position prior; no production VST3 build exposes this.
struct FrettedPositionPriorPolicy final {
  double fixed_penalty{};
  double per_fret_penalty{};
};

struct DecisiveCalibratedSelectorPolicy final {
  double minimum_margin{};
  std::uint8_t allowed_string_mask{0xffU};
};

// Replay-only one-for-one replacement. It cannot add a voice: a DP-evicted
// direct candidate may only replace the non-coasting single-lane voice that
// already occupies its strongest calibrated string.
struct CalibratedDpReplacementPolicy final {
  double minimum_similarity{};
  double minimum_calibration_margin{};
  double minimum_score_margin{};
  std::uint8_t allowed_string_mask{0xffU};
};

struct ProductionDpReplacementLanePolicy final {
  std::uint8_t allowed_string_mask{0xffU};
};

// Replay-only removal of the worse-fitting member of an adjacent single-voice
// pair. It is evaluated only when both emitted pitches have ready, bounded
// candidate spectral fingerprints; it cannot add or retune a voice.
struct AdjacentSpectralDuplicatePolicy final {
  double minimum_error_gap{};
};

inline constexpr std::array<AdjacentSpectralDuplicatePolicy, 5U>
    kAdjacentSpectralDuplicatePolicies{{
        {0.30}, {0.40}, {0.45}, {0.50}, {0.60},
    }};

struct ReplayCounterfactualMetrics final {
  std::uint32_t matched_label_frames{};
  std::uint32_t false_positive_voices{};
  std::uint32_t false_gap_voices{};
  std::uint32_t false_wrong_note_voices{};
  std::uint32_t false_wrong_string_voices{};
  std::uint32_t changed_voices{};
};

// Causal shadow-only veto: a second, longer correlation window may remove
// one established single-string proposal. Labels never enter this rule.
struct CorrelationShadowPolicy final {
  double maximum_energy_ratio{};
  double minimum_age_seconds{};
  bool fundamental_only{};
  bool protect_pending_unison{};
};

inline constexpr auto kCorrelationShadowPolicies = [] {
  std::array<CorrelationShadowPolicy, 72U> policies{};
  std::size_t index = 0U;
  for (const bool protect_pending : {false, true}) {
    for (const bool fundamental : {false, true}) {
      for (const double age : {0.15, 0.30, 0.60}) {
        for (const double ratio : {0.12, 0.18, 0.25, 0.35, 0.50, 0.70}) {
          policies[index++] = {ratio, age, fundamental, protect_pending};
        }
      }
    }
  }
  return policies;
}();

inline constexpr std::array<double, 7U> kJointPitchEnergyFloors{
    0.0, 0.0001, 0.001, 0.005, 0.01, 0.02, 0.05};

struct JointPitchShadowPolicy final {
  double minimum_energy_fraction{};
  double maximum_fundamental_overlap{};
};
inline constexpr auto kJointPitchPolicies = [] {
  std::array<JointPitchShadowPolicy, 35U> policies{};
  std::size_t index = 0U;
  for (const double overlap : {1.0, 0.999, 0.99, 0.95, 0.90}) {
    for (const double energy : kJointPitchEnergyFloors) {
      policies[index++] = {energy, overlap};
    }
  }
  return policies;
}();

[[nodiscard]] TunerSnapshot correlation_shadow_projection(
    const TunerSnapshot& snapshot, const std::array<double, 128U>& ratios,
    double sample_rate, const CorrelationShadowPolicy& policy,
    std::uint32_t& changed_voices,
    const std::array<bool, 128U>* pending_unison = nullptr) noexcept;


enum class ReplayError : std::uint8_t {
  none,
  invalid_wave,
  unsupported_wave,
  invalid_labels,
  invalid_config,
  invalid_calibration,
  nonfinite_audio,
};

struct WaveData final {
  std::uint32_t sample_rate{};
  std::uint16_t source_channels{};
  std::vector<double> mono_samples{};
};

struct ReplayLabel final {
  std::uint64_t start_sample{};
  std::uint64_t end_sample{};
  std::uint8_t midi_note{};
  // Zero requests note-only scoring. A nonzero mask requests exact physical
  // tuner lanes and is the preferred form for isolated-string/unison corpora.
  std::uint8_t string_mask{};
  // Zero preserves the legacy observation-weighted calibration behavior.
  // Nonzero values identify independent recording passes so repeated holds
  // within one pass cannot outweigh the ascending or descending fret walks.
  std::uint8_t calibration_pass{};
  // Optional expected acoustic offset from the equal-tempered MIDI center.
  // This is measurement truth for scoring and is deliberately independent
  // from the detector's calibration bank.
  std::int16_t expected_cents_q8{};
  bool expected_cents_valid{};
};

enum class ReplayTargetLaneOutcome : std::size_t {
  absent,
  exact,
  subset_missing,
  superset_extra,
  overlap_mixed,
  disjoint_wrong,
  count,
};

// Coarse relation used by the physical-group causal audit. Fine and committed
// masks need only distinguish missing evidence, an exact group, a useful
// nonzero subset, and evidence that points outside the expected group.
enum class ReplayGroupMaskRelation : std::size_t {
  absent,
  exact,
  subset,
  other,
  count,
};

// Relation between the independently fitted spectral classifier mask and the
// labeled physical group. Invalid is kept separate from an ordinary wrong
// mask so replay can distinguish missing classifier evidence from a genuine
// disagreement.
enum class ReplayClassifierMaskRelation : std::size_t {
  invalid,
  exact,
  subset,
  other,
  count,
};

inline constexpr std::size_t kPhysicalGroupCausalCellCount =
    kSelectionDispositionCount *
    static_cast<std::size_t>(ReplayGroupMaskRelation::count) *
    static_cast<std::size_t>(ReplayGroupMaskRelation::count) *
    static_cast<std::size_t>(ReplayTargetLaneOutcome::count);
inline constexpr std::size_t kPhysicalGroupFineUnresolvedCellCount =
    kSelectionDispositionCount * kFineFrequencyUnresolvedReasonCount *
    static_cast<std::size_t>(ReplayTargetLaneOutcome::count);
inline constexpr std::size_t kPhysicalGroupFineClassifierCellCount =
    static_cast<std::size_t>(ReplayGroupMaskRelation::count) *
    static_cast<std::size_t>(ReplayClassifierMaskRelation::count) *
    static_cast<std::size_t>(ReplayTargetLaneOutcome::count);

ReplayGroupMaskRelation classify_group_mask_relation(
    std::uint8_t observed_mask, std::uint8_t expected_mask,
    bool note_only = false) noexcept;

ReplayClassifierMaskRelation classify_classifier_mask_relation(
    const UnisonSpectralClassification& classification,
    std::uint8_t expected_mask, bool note_only = false) noexcept;

struct ReplayObservedFingerprintChangedFrameDiagnostic final {
  ReplayGroupMaskRelation committed_relation{ReplayGroupMaskRelation::absent};
  std::uint8_t committed_member_count{};
  std::uint8_t snapshot_voice_count{};
  std::uint8_t other_owned_lane_count{};
};

ReplayObservedFingerprintChangedFrameDiagnostic
diagnose_observed_fingerprint_changed_frame(
    std::uint8_t committed_mask, std::uint8_t expected_mask,
    std::uint8_t snapshot_voice_count,
    std::uint8_t other_owned_mask) noexcept;

std::size_t physical_group_causal_cell_index(
    std::size_t selection_disposition, ReplayGroupMaskRelation fine_relation,
    ReplayGroupMaskRelation committed_relation,
    ReplayTargetLaneOutcome lane_outcome) noexcept;

std::size_t physical_group_fine_unresolved_cell_index(
    std::size_t selection_disposition, std::size_t unresolved_reason,
    ReplayTargetLaneOutcome lane_outcome) noexcept;

std::size_t physical_group_fine_classifier_cell_index(
    ReplayGroupMaskRelation fine_relation,
    ReplayClassifierMaskRelation classifier_relation,
    ReplayTargetLaneOutcome lane_outcome) noexcept;

ReplayTargetLaneOutcome classify_target_lane_outcome(
    std::uint8_t observed_mask, std::uint8_t expected_mask) noexcept;

struct FineResidualExpansionEvidence final {
  bool active{};
  bool selected{};
  bool direct_fundamental{};
  double score_threshold_ratio{};
  double residual_improvement{};
  bool residual_rejected{};
  std::uint8_t committed_mask{};
  std::uint8_t fit_mask{};
  std::uint8_t playable_mask{};
  std::uint8_t other_owned_mask{};
};

// Returns a strict, already-fitted physical-group expansion, or zero. This is
// an offline counterfactual only and cannot create a pitch or alter MIDI.
std::uint8_t bounded_fine_residual_expansion(
    const FineResidualExpansionEvidence& evidence,
    double minimum_score_threshold_ratio, double minimum_improvement,
    std::uint8_t maximum_polyphony) noexcept;


struct ReplayPairwiseBeatSupport final {
  std::uint8_t pair_count{};
  std::uint8_t above_gate_count{};
  bool connected{};
};

ReplayPairwiseBeatSupport summarize_pairwise_beat_support(
    std::uint8_t member_mask,
    const std::array<double, 1U << kMaxVoices>& coherence_by_pair,
    double gate) noexcept;

std::uint8_t spectral_head_vote_mask(
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& heads) noexcept;

struct SpectralHeadPlurality final {
  std::uint8_t string{kUnassignedTunerString};
  std::uint8_t votes{};
  double margin_sum{};
};

// Offline-only ensemble over the already-computed low/low-mid/high-mid/high
// and overtone-separation heads. Heads below the supplied confidence margin
// abstain. Equal vote and margin totals remain unresolved rather than being
// broken by physical-string order.
SpectralHeadPlurality spectral_head_plurality(
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& heads,
    const std::array<double, kSpectralTierCount + 1U>& margins,
    double minimum_margin) noexcept;

struct ReplayLabelResult final {
  std::uint32_t labeled_frames{};
  std::uint32_t matched_frames{};
  std::uint16_t maximum_matching_note_beat_hz_q8{};
  std::array<std::uint32_t, kMaxVoices> matching_note_lane_frames{};
  // One entry per observed physical-lane mask for the label's MIDI note.
  // Index zero records labeled snapshots where that note was absent.
  std::array<std::uint32_t, 1U << kMaxVoices>
      matching_note_lane_mask_frames{};
  std::uint32_t cents_observations{};
  std::int64_t cents_error_sum_q8{};
  std::uint64_t cents_error_square_sum_q16{};
  std::vector<std::int16_t> cents_errors_q8{};
  std::uint64_t first_valid_cents_sample{
      std::numeric_limits<std::uint64_t>::max()};
  std::uint64_t first_correct_string_sample{
      std::numeric_limits<std::uint64_t>::max()};
  std::uint32_t string_flip_count{};
  std::uint32_t longest_correct_run_frames{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  // Mutually exclusive selector outcomes for this label's target pitch.
  // This diagnostic exists only in the offline replay/test targets.
  std::array<std::uint32_t, 6U> selection_disposition_frames{};
  // Bitset rows from the production-shaped independent continuity tracker:
  // cache, tracking, ready, exact classifier, tier proposal, projection,
  // live proper subset, direct fundamental.
  std::array<std::uint32_t, 256U> group_continuity_diagnostic_frames{};
  // First causal quiet gate for frames counted in selection_quiet. Indexes
  // follow QuietDisposition; not_quiet must remain zero here.
  std::array<std::uint32_t, kQuietDispositionCount>
      quiet_disposition_frames{};
  std::array<std::uint32_t, kQuietDispositionCount>
      quiet_disposition_runs{};
  std::array<std::uint32_t, kQuietDispositionCount>
      longest_quiet_disposition_run_frames{};
  std::array<std::uint32_t, 128U>
      minimum_evidence_resume_flag_frames{};
  std::array<std::uint32_t,
             static_cast<std::size_t>(
                 ReplayFineHistoryCarryDisposition::count)>
      fine_history_carry_disposition_frames{};
  std::uint32_t candidate_unison_spectral_frames{};
  std::uint32_t candidate_unison_spectral_invalid_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      candidate_unison_spectral_fitted_mask_frames{};
  std::array<std::uint32_t, kSpectralReacquisitionDispositionCount>
      spectral_reacquisition_disposition_frames{};
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
             kSpectralReacquisitionDispositionCount>
      spectral_reacquisition_lane_outcome_frames{};
  std::array<std::uint32_t, 7U>
      unison_cache_refresh_disposition_frames{};
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
             7U>
      unison_cache_refresh_lane_outcome_frames{};
  // Production-feasible active-candidate classifier, passed through the same
  // bounded fine/beat/profile/temporal corroboration policy as the original
  // label-scoped shadow. These counters remain replay-only and never alter
  // detector output.
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      candidate_unison_projected_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      candidate_unison_projected_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      candidate_unison_projected_matched_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      candidate_unison_projected_wrong_string_voices{};
  std::array<std::uint32_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_projected_frames{};
  std::array<std::uint32_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_changed_frames{};
  std::array<std::uint32_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_exact_frames{};
  std::array<std::uint32_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_matched_frames{};
  std::array<std::uint32_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_wrong_string_voices{};
  std::array<std::int64_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_exact_delta{};
  std::array<std::int64_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_matched_delta{};
  std::array<std::int64_t, kUnisonReacquisitionHoldCount>
      unison_reacquisition_wrong_string_delta{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_eligible_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_projected_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_changed_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_exact_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_matched_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_wrong_string_voices{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_exact_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_matched_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_wrong_string_delta{};
  // Policy zero only (0.25 s cache, 0.20 s fresh revalidation). This exposes
  // which causal physical group was restored without consulting label data.
  std::array<std::uint32_t, 1U << kMaxVoices>
      articulated_unison_reacquisition_accepted_cache_mask_frames{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      three_member_articulated_reacquisition_changed_frames{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      three_member_articulated_reacquisition_exact_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      three_member_articulated_reacquisition_matched_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      three_member_articulated_reacquisition_wrong_string_delta{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      production_three_member_articulated_reacquisition_changed_frames{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      production_three_member_articulated_reacquisition_exact_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      production_three_member_articulated_reacquisition_matched_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      production_three_member_articulated_reacquisition_wrong_string_delta{};
  std::array<std::uint32_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      solo_three_member_articulated_reacquisition_changed_frames{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      solo_three_member_articulated_reacquisition_exact_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      solo_three_member_articulated_reacquisition_matched_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionPolicyCount>
      solo_three_member_articulated_reacquisition_wrong_string_delta{};
  std::array<
      std::array<std::uint32_t,
                 kArticulatedUnisonReacquisitionDispositionCount>,
      kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_disposition_frames{};
  std::array<
      std::array<std::int64_t,
                 kArticulatedUnisonReacquisitionDispositionCount>,
      kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_counterfactual_matched_delta{};
  std::array<
      std::array<std::int64_t,
                 kArticulatedUnisonReacquisitionDispositionCount>,
      kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_counterfactual_exact_delta{};
  std::array<
      std::array<std::int64_t,
                 kArticulatedUnisonReacquisitionDispositionCount>,
      kArticulatedUnisonReacquisitionPolicyCount>
      articulated_unison_reacquisition_counterfactual_wrong_string_delta{};
  std::uint32_t continuity_union_changed_frames{};
  std::uint32_t continuity_union_exact_frames{};
  std::uint32_t continuity_union_matched_frames{};
  std::int64_t continuity_union_exact_delta{};
  std::int64_t continuity_union_matched_delta{};
  std::int64_t continuity_union_wrong_string_delta{};
  std::array<std::uint32_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_projected_frames{};
  std::array<std::uint32_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_changed_frames{};
  std::array<std::uint32_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_exact_frames{};
  std::array<std::uint32_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_matched_frames{};
  std::array<std::uint32_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_wrong_string_voices{};
  std::array<std::int64_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_exact_delta{};
  std::array<std::int64_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_matched_delta{};
  std::array<std::int64_t,
             kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_wrong_string_delta{};
  std::array<
      std::array<std::uint32_t,
                 kArticulatedUnisonReacquisitionDispositionCount>,
      kObservedFingerprintReacquisitionPolicyCount>
      observed_fingerprint_reacquisition_disposition_frames{};
  // Selection state for the production-candidate policy only: 0.50 s cache,
  // 0.20 s revalidation, and 0.005 normalized squared fingerprint distance.
  // This distinguishes a genuine selected MIDI-path recovery from a cosmetic
  // lane projection on an already-coasting voice.
  std::array<std::uint32_t, kSelectionDispositionCount>
      observed_fingerprint_reacquisition_selection_frames{};
  // Causal state for changed frames under the production-candidate shadow
  // policy. These bins distinguish an incomplete internal physical group
  // from output slot pressure without changing detector output.
  std::array<std::uint32_t,
             static_cast<std::size_t>(ReplayGroupMaskRelation::count)>
      observed_fingerprint_changed_committed_relation_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      observed_fingerprint_changed_committed_member_count_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      observed_fingerprint_changed_snapshot_voice_count_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      observed_fingerprint_changed_other_owned_lane_count_frames{};
  std::array<std::uint32_t, kSpectralReacquisitionDispositionCount>
      observed_fingerprint_changed_production_disposition_frames{};
  // Fifty-millisecond bins through 5.95 s, plus an overflow/non-finite bin.
  std::array<std::uint32_t, 121U>
      observed_fingerprint_changed_production_cache_age_50ms_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      observed_fingerprint_changed_production_cache_mask_frames{};
  std::array<std::uint32_t, 21U>
      observed_fingerprint_changed_score_threshold_ratio_05_frames{};
  std::array<std::uint32_t, 2U>
      observed_fingerprint_changed_direct_fundamental_frames{};
  // Joint selector/output accounting. Rows use SelectionDisposition order;
  // columns use ReplayTargetLaneOutcome order. This keeps the offline audit
  // causal: a missing pitch can be separated from a correct pitch assigned
  // to the wrong physical strings.
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(
                            ReplayTargetLaneOutcome::count)>,
             6U>
      selection_lane_outcome_frames{};
  // Label-local form of the 50-cent adjacent-fret counterfactual. Aggregate
  // outcomes can hide a regression when the projected pitch happens to match
  // a different simultaneous label, so this keeps each physical label's
  // before/after truth separate.
  std::array<std::uint32_t, kCalibratedPitchRebinOutcomeCount>
      calibrated_pitch_rebin_50_outcome_frames{};
  std::array<std::uint32_t, kCalibratedPitchRebinOutcomeCount>
      calibrated_pitch_rebin_50_stable_outcome_frames{};
  std::uint32_t calibrated_pitch_rebin_50_changed_frames{};
  std::uint32_t calibrated_pitch_rebin_50_stable_changed_frames{};
  // Candidate-admission evidence for the label's expected pitch. Ratio bins
  // are five percentage points wide; the final score bin means >=2.0x the
  // ordinary threshold and the final fundamental bin means >=100% of score.
  // Evidence flags are active=1, direct fundamental=2, local peak=4,
  // M3 candidate evidence=8, calibrated direct support=16.
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_score_threshold_ratio_frames{};
  double string_fret_onset_strength_max{};
  double string_fret_onset_strength_first_250ms_max{};
  double active_string_fret_onset_strength_max{};
  double active_string_fret_onset_strength_first_250ms_max{};
  // Frames where the labeled pitch cleared admission and harmonic rejection
  // but lost the bounded joint selector.  These bins distinguish genuine
  // five-voice pressure from avoidable selector occupancy without changing
  // production decisions.  Count bins saturate at kMaxVoices.
  std::array<std::uint32_t, kMaxVoices + 1U>
      candidate_dp_evicted_true_pitch_count_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      candidate_dp_evicted_selected_pitch_count_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_dp_evicted_score_ratio_frames{};
  std::array<std::uint32_t, kCandidateAdmissionEvidenceFlagCount>
      candidate_dp_evicted_evidence_flag_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      candidate_dp_evicted_playable_lane_count_frames{};
  // Rows are expected lane, other lane, unavailable. Posterior columns are
  // five-percentage-point probability/margin bins.
  std::array<std::uint32_t, 3U>
      candidate_dp_evicted_calibration_relation_frames{};
  std::array<std::array<std::uint32_t, 21U>, 3U>
      candidate_dp_evicted_calibration_similarity_frames{};
  std::array<std::array<std::uint32_t, 21U>, 3U>
      candidate_dp_evicted_calibration_margin_frames{};
  std::array<std::uint32_t, 3U>
      candidate_dp_evicted_posterior_relation_frames{};
  std::array<std::array<std::uint32_t, 21U>, 3U>
      candidate_dp_evicted_posterior_probability_frames{};
  std::array<std::array<std::uint32_t, 21U>, 3U>
      candidate_dp_evicted_posterior_margin_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_below_threshold_score_ratio_frames{};
  std::array<std::uint32_t, 21U>
      candidate_below_threshold_fundamental_ratio_frames{};
  std::array<std::uint32_t, kCandidateAdmissionEvidenceFlagCount>
      candidate_below_threshold_evidence_flag_frames{};
  // Joint score/fundamental bins for candidates that already have a direct
  // fundamental plus a local peak or the existing M3 candidate predicate.
  // These are the only below-threshold frames eligible for the bounded rescue
  // experiment; retaining the joint matrix avoids optimistic marginal math.
  std::array<std::array<std::uint32_t, 21U>,
             kCandidateAdmissionRatioBinCount>
      candidate_below_threshold_direct_evidence_frames{};
  // Joint one-octave-band score/fundamental peak ratios for the same direct
  // below-threshold candidates. These ratios are scale invariant and let the
  // shadow audit test local normalization without changing MIDI selection.
  std::array<std::array<std::uint32_t, 21U>, 21U>
      candidate_below_threshold_pitch_band_peak_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_below_threshold_calibration_correct_similarity_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_below_threshold_calibration_other_similarity_frames{};
  std::array<std::uint32_t, 21U>
      candidate_below_threshold_calibration_correct_margin_frames{};
  std::array<std::uint32_t, 21U>
      candidate_below_threshold_calibration_other_margin_frames{};
  std::array<std::array<std::uint32_t, 21U>, 2U>
      candidate_below_threshold_calibration_relation_margin_frames{};
  // Index eight means calibrated evidence was unavailable.
  std::array<std::uint32_t, kMaxVoices + 1U>
      candidate_below_threshold_calibration_best_string_frames{};
  // The same physical-evidence partition for candidates that cleared the
  // ordinary score gate but were rejected as a harmonic shadow. The joint
  // matrix is indexed by whether the best calibrated string matches this
  // label, then by the fundamental/score ratio. It distinguishes a weak real
  // fundamental from an attractive but wrong calibrated harmonic before any
  // production shadow rule is relaxed.
  std::array<std::uint32_t, 21U>
      candidate_spectral_rejected_fundamental_ratio_frames{};
  std::array<std::uint32_t, kCandidateAdmissionEvidenceFlagCount>
      candidate_spectral_rejected_evidence_flag_frames{};
  std::array<std::array<std::uint32_t, 21U>, 2U>
      candidate_spectral_rejected_calibration_relation_fundamental_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_spectral_rejected_calibration_correct_similarity_frames{};
  std::array<std::uint32_t, kCandidateAdmissionRatioBinCount>
      candidate_spectral_rejected_calibration_other_similarity_frames{};
  std::array<std::uint32_t, 21U>
      candidate_spectral_rejected_calibration_correct_margin_frames{};
  std::array<std::uint32_t, 21U>
      candidate_spectral_rejected_calibration_other_margin_frames{};
  std::array<std::uint32_t, kMaxVoices + 1U>
      candidate_spectral_rejected_calibration_best_string_frames{};
  // Exact cause of harmonic-shadow rejection for the labeled candidate.
  // Interval bins encode [-kMaxCandidates, +kMaxCandidates] with the zero
  // point at kMaxCandidates. Kind bits are harmonic=1, M3 cross-harmonic=2.
  std::array<std::uint32_t, kSpectralShadowIntervalBinCount>
      candidate_spectral_rejected_shadow_interval_frames{};
  std::array<std::uint32_t, 21U>
      candidate_spectral_rejected_shadow_fundamental_ratio_frames{};
  std::array<std::uint32_t, 4U>
      candidate_spectral_rejected_shadow_kind_frames{};
  std::array<std::uint32_t, kMaxCandidates + 1U>
      candidate_spectral_rejected_shadow_other_eligible_frames{};
  std::array<std::uint32_t, kMaxCandidates + 1U>
      candidate_spectral_rejected_shadow_other_active_frames{};
  // Bins zero through 2*kMaxCandidates encode the signed interval with zero
  // centered at kMaxCandidates. The final bin means no other eligible pitch.
  std::array<std::uint32_t, kSpectralShadowIntervalBinCount + 1U>
      candidate_spectral_rejected_shadow_strongest_other_interval_frames{};
  std::array<std::uint32_t, 32U>
      candidate_spectral_rejected_shadow_strongest_other_evidence_frames{};
  // Expected-lane, other-lane, unresolved posterior decisions crossed with
  // the same observed target-lane outcome.
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(
                            ReplayTargetLaneOutcome::count)>,
             3U>
      posterior_lane_outcome_frames{};
  // Correct, other, and unresolved posterior decisions crossed with their
  // confidence and top-two probability margin. These are counted only when
  // the pitch is playable on at least two physical strings, so a forced
  // one-string state cannot inflate apparent classifier precision.
  std::array<std::array<std::uint32_t, 21U>, 3U>
      string_fret_posterior_probability_frames{};
  std::array<std::array<std::uint32_t, 21U>, 3U>
      string_fret_posterior_margin_frames{};
  // Policy-major; column zero means the agreed string is expected by this
  // physical label and column one means it is a wrong physical string.
  std::array<std::array<std::uint32_t, 2U>,
             kRelaxedBandPosteriorPolicyCount>
      relaxed_band_posterior_agreement_frames{};
  // The same incremental corridor crossed with the independent 102-feature
  // one-string classifier. Column meanings match the posterior matrix above;
  // rows use kSpectralShadowMarginThresholds.
  std::array<std::array<std::uint32_t, 2U>,
             kRelaxedBandSpectralPolicyCount>
      relaxed_band_spectral_agreement_frames{};
  // Counterfactual lane-only projection for an already-active one-string
  // pitch. It cannot create a note, add polyphony, or steal another pitch's
  // lane. The policy grid shares the spectral error/margin thresholds above.
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      spectral_lane_projection_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      spectral_lane_projection_changed_frames{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      spectral_lane_projection_matched_delta{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      spectral_lane_projection_wrong_string_delta{};
  // The same lane-only projection split by classifier phase (row zero is
  // onset, row one is settled). This keeps temporal safety measurable before
  // any shadow policy is admitted to the real-time assignment path.
  std::array<std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>, 2U>
      spectral_lane_projection_phase_frames{};
  std::array<std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>, 2U>
      spectral_lane_projection_phase_changed_frames{};
  std::array<std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>, 2U>
      spectral_lane_projection_phase_matched_delta{};
  std::array<std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>, 2U>
      spectral_lane_projection_phase_wrong_string_delta{};
  // Candidate-lifecycle version of the same counterfactual. Unlike the
  // label-timed corridor above, this tracker is acquired and reset using only
  // detector-visible candidate evidence, so it is the production-feasibility
  // gate for lane reassignment.
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      candidate_spectral_lane_projection_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      candidate_spectral_lane_projection_changed_frames{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      candidate_spectral_lane_projection_matched_delta{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      candidate_spectral_lane_projection_wrong_string_delta{};
  std::array<std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>, 2U>
      candidate_spectral_lane_projection_phase_frames{};
  std::array<std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>, 2U>
      candidate_spectral_lane_projection_phase_matched_delta{};
  std::array<std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>, 2U>
      candidate_spectral_lane_projection_phase_wrong_string_delta{};
  // Fine-frequency physical-member masks for the same target pitch. Index
  // zero represents unresolved evidence, not a ninth physical-string state.
  std::array<std::uint32_t, 1U << kMaxVoices>
      fine_frequency_member_mask_frames{};
  std::array<double, 1U << kMaxVoices>
      fine_frequency_member_mask_residual_sum{};
  std::array<double, 1U << kMaxVoices>
      fine_frequency_member_mask_minimum_ratio_sum{};
  std::array<double, 1U << kMaxVoices>
      fine_frequency_member_mask_minimum_beat_coherence_sum{};
  std::array<std::array<std::uint32_t, 21U>, 1U << kMaxVoices>
      fine_frequency_member_mask_minimum_beat_coherence_bins{};
  std::array<std::uint32_t, kFineUniqueMemberImprovementFloors.size()>
      fine_unique_member_pruning_changed_frames{};
  std::array<std::uint32_t, kFineUniqueMemberImprovementFloors.size()>
      fine_unique_member_pruning_exact_frames{};
  std::array<std::int64_t, kFineUniqueMemberImprovementFloors.size()>
      fine_unique_member_pruning_matched_delta{};
  std::array<std::int64_t, kFineUniqueMemberImprovementFloors.size()>
      fine_unique_member_pruning_wrong_string_delta{};
  std::array<std::uint32_t, kFineMaskComplexityPenalties.size()>
      fine_mask_complexity_changed_frames{};
  std::array<std::uint32_t, kFineMaskComplexityPenalties.size()>
      fine_mask_complexity_exact_frames{};
  std::array<std::int64_t, kFineMaskComplexityPenalties.size()>
      fine_mask_complexity_matched_delta{};
  std::array<std::int64_t, kFineMaskComplexityPenalties.size()>
      fine_mask_complexity_wrong_string_delta{};
  std::uint32_t fine_mask_model_expected_available_frames{};
  std::array<std::uint32_t, kFineMaskModelRankBucketCount>
      fine_mask_model_expected_rank_frames{};
  std::array<std::uint32_t, kFineMaskComplexityPenalties.size()>
      fine_mask_model_exact_frames{};
  std::array<std::uint32_t, kFineMaskComplexityPenalties.size()>
      fine_mask_model_tied_frames{};
  std::array<std::array<std::uint32_t, 5U>,
             kFineMaskComplexityPenalties.size()>
      fine_mask_model_winner_member_frames{};
  std::uint32_t fine_mask_posterior_available_frames{};
  std::array<std::array<std::uint32_t, kFineMaskPosteriorWeights.size()>,
             kFineMaskComplexityPenalties.size()>
      fine_mask_posterior_exact_frames{};
  std::array<std::array<std::uint32_t, kFineMaskPosteriorWeights.size()>,
             kFineMaskComplexityPenalties.size()>
      fine_mask_posterior_tied_frames{};
  std::array<std::uint32_t, kFineMaskBeatCoherenceFloors.size()>
      fine_mask_beat_expected_available_frames{};
  std::array<std::array<std::uint32_t, kFineMaskBeatCoherenceFloors.size()>,
             kFineMaskComplexityPenalties.size()>
      fine_mask_beat_exact_frames{};
  std::array<std::array<std::uint32_t, kFineMaskBeatCoherenceFloors.size()>,
             kFineMaskComplexityPenalties.size()>
      fine_mask_beat_tied_frames{};
  std::uint32_t fine_mask_beat_pruning_changed_frames{};
  std::uint32_t fine_mask_beat_pruning_exact_frames{};
  std::int64_t fine_mask_beat_pruning_matched_delta{};
  std::int64_t fine_mask_beat_pruning_wrong_string_delta{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      fine_mask_pruning_output_mask_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      fine_frequency_pending_member_mask_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      fine_frequency_fit_member_mask_frames{};
  // unresolved, amplitude-single, source-rejected, residual-rejected,
  // multi-source-candidate; kept numeric here to avoid coupling the public
  // replay result header to the detector implementation header.
  std::array<std::uint32_t, 5U> fine_frequency_disposition_frames{};
  std::array<std::uint32_t, kFineFrequencyUnresolvedReasonCount>
      fine_frequency_unresolved_reason_frames{};
  // Five-percentage-point bins from <=0% through >=100%, split by whether
  // the pre-residual fit has the label's exact physical-string mask.
  std::array<std::uint32_t, 21U> exact_fit_residual_improvement_frames{};
  std::array<std::uint32_t, 21U> other_fit_residual_improvement_frames{};
  // Index eight means no posterior decision; 0..7 are physical strings.
  std::array<std::uint32_t, kMaxVoices + 1U>
      string_fret_posterior_best_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      profile_unison_proposal_mask_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      temporal_unison_proposal_mask_frames{};
  // The physical mask committed by the production detector after assignment,
  // independent of whether the selector exposed all of those lanes in this
  // snapshot. These counters locate selector loss after a group was already
  // causally resolved.
  std::array<std::uint32_t, 1U << kMaxVoices>
      committed_unison_mask_frames{};
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(
                            ReplayTargetLaneOutcome::count)>,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      committed_unison_lane_outcome_frames{};
  // not-applicable, fine-unavailable, fine-mask-mismatch, beat-below-gate,
  // unplayable, below-decay-floor, superseded, retained.
  std::array<std::uint32_t, 8U> retained_unison_disposition_frames{};
  std::array<std::uint32_t, 8U>
      committed_exact_retained_unison_disposition_frames{};
  // For each retained-unison disposition, classify an exact committed
  // 2--4-string group by how many of its pairwise beat edges clear the
  // unchanged 0.20 gate. Connected counts identify a spanning set of strong
  // edges even when the current minimum-of-all-pairs rule rejects the group.
  std::array<std::array<std::uint32_t, 7U>, 8U>
      committed_exact_pairwise_beat_above_gate_frames{};
  std::array<std::uint32_t, 8U>
      committed_exact_pairwise_beat_connected_frames{};
  std::array<std::uint32_t, 8U>
      longest_committed_exact_retained_disposition_run_frames{};
  // unresolved, missing-primary, invalid-size, conflicts-other-owned,
  // conflicts-allocated, over-capacity, accepted.
  std::array<std::uint32_t, 7U> fine_group_disposition_frames{};
  std::array<std::array<std::uint32_t, 21U>, 7U>
      fine_group_disposition_beat_coherence_bins{};
  // When the committed mask exactly matches the label, cross the current
  // fine evidence (unresolved, exact, nonzero subset, other) with the exposed
  // lane outcome. The longest run measures non-confirming frames while the
  // exact commitment survives.
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(
                            ReplayTargetLaneOutcome::count)>,
             4U>
      committed_exact_fine_relation_lane_outcome_frames{};
  std::uint32_t longest_committed_exact_fine_gap_frames{};
  std::uint16_t maximum_committed_unison_gap_ticks{};
  // Offline-only normalized corridor descriptors. Every ready labeled target
  // frame contributes once to the all-phase sum and exactly one onset/settled
  // sum. Callers divide by the corresponding count before classification.
  UnisonSpectralFingerprint spectral_corridor_fingerprint_sum{};
  UnisonSpectralFingerprint spectral_onset_fingerprint_sum{};
  UnisonSpectralFingerprint spectral_settled_fingerprint_sum{};
  std::uint32_t spectral_corridor_frames{};
  std::uint32_t spectral_onset_frames{};
  std::uint32_t spectral_settled_frames{};
  // Optional per-frame shadow-classifier diagnostics. These remain zero
  // unless run_detector_replay receives an offline template bank.
  std::uint32_t spectral_shadow_frames{};
  std::uint32_t spectral_shadow_invalid_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_shadow_fitted_mask_frames{};
  std::array<double, 1U << kMaxVoices>
      spectral_shadow_fitted_mask_residual_sum{};
  std::array<double, 1U << kMaxVoices>
      spectral_shadow_fitted_mask_margin_sum{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_shadow_fitted_mask_margin_frames{};
  std::array<std::array<std::uint32_t, 1U << kMaxVoices>, 2U>
      spectral_shadow_phase_mask_frames{};
  std::array<std::uint32_t,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      spectral_shadow_disposition_frames{};
  std::uint32_t spectral_shadow_fine_disagreement_frames{};
  std::uint32_t spectral_shadow_beat_compared_frames{};
  std::uint32_t spectral_shadow_beat_disagreement_frames{};
  std::uint32_t spectral_shadow_profile_disagreement_frames{};
  std::uint32_t spectral_shadow_temporal_disagreement_frames{};
  std::uint32_t spectral_shadow_assignment_disagreement_frames{};
  std::uint32_t spectral_shadow_projected_frames{};
  // Exact one-string classifier diagnostics for ordinary interval candidates.
  // These share the same 102-feature corridor but do not compete with or alter
  // the production selector.
  std::uint32_t spectral_single_frames{};
  std::uint32_t spectral_single_invalid_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_single_fitted_mask_frames{};
  std::array<double, 1U << kMaxVoices>
      spectral_single_fitted_mask_error_sum{};
  std::array<double, 1U << kMaxVoices>
      spectral_single_fitted_mask_margin_sum{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_single_fitted_mask_margin_frames{};
  std::array<std::uint32_t,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      spectral_single_disposition_frames{};
  // Phase-specific physical-string winner counts. Unlike the multi-mask NNLS
  // fit, these preserve the strong one-string classifier signal so an offline
  // temporal union can be evaluated without assuming spectral magnitudes add
  // linearly for close unisons.
  std::array<std::uint32_t, kMaxVoices>
      spectral_single_onset_string_frames{};
  std::array<std::uint32_t, kMaxVoices>
      spectral_single_settled_string_frames{};
  // Every feasible one-string fit, not only the argmax. Phase row zero is
  // onset and row one is settled. Gap-support rows use
  // kSpectralSingleGapThresholds and count frames whose fit error is within
  // that threshold of the best feasible string for the same snapshot.
  std::array<std::array<double, kMaxVoices>, 2U>
      spectral_single_phase_score_error_sum{};
  std::array<std::array<std::uint32_t, kMaxVoices>, 2U>
      spectral_single_phase_score_frames{};
  std::array<std::array<
                 std::array<std::uint32_t, kMaxVoices>,
                 kSpectralSingleGapThresholdCount>,
             2U>
      spectral_single_phase_gap_support_frames{};
  // Forty equal bins across [0, 1], with the final bin also containing larger
  // finite values. Row zero means the fitted one-string mask matches the
  // label; row one means it selected another physical string.
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_error_outcome_frames{};
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_margin_outcome_frames{};
  // The same diagnostics against the union of all simultaneously active
  // labels for this pitch. This treats any real member of a physical unison
  // as correct instead of penalizing a one-string fit for choosing a sibling
  // label in the same group.
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_group_error_outcome_frames{};
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_group_margin_outcome_frames{};
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_below_threshold_error_outcome_frames{};
  std::array<std::array<std::uint32_t, kSpectralSingleMetricBinCount>, 2U>
      spectral_single_below_threshold_margin_outcome_frames{};
  // Selection dispositions are quiet, below-threshold, spectral-rejected,
  // DP-evicted, selected, and coasting. Columns are invalid, exact-label,
  // and other-label classifier outcomes. This exposes whether high-confidence
  // spectral evidence is selective specifically at the admission failure.
  std::array<std::array<std::uint32_t, 3U>, 6U>
      spectral_single_selection_disposition_frames{};
  // The same selection cross-tab classified against the union of all active
  // same-note labels. Every sibling label receives the identical group-level
  // value so report aggregation is invariant to label ordering.
  std::array<std::array<std::uint32_t, 3U>, 6U>
      spectral_single_group_selection_disposition_frames{};
  // Counterfactual output of the bounded secondary-evidence policy at seven
  // fixed posterior-margin floors. These are diagnostics only: replay MIDI and
  // fingerprints remain those of the production detector.
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_shadow_projected_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_shadow_projected_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_shadow_projected_matched_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_shadow_projected_wrong_string_voices{};
  // Causal onset-memory counterfactual. Each threshold owns an independent
  // latch, votes only during onset, and freezes at the first settled frame.
  // The projection remains offline-only and is bounded by current activity,
  // fret feasibility, string ownership, and Max Polyphony.
  std::array<std::uint8_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_committed_mask{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_qualified_votes{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_winner_votes{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_projected_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_matched_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_latch_wrong_string_voices{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_matched_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_wrong_string_delta{};
  std::array<double, kSpectralShadowMarginThresholdCount>
      spectral_onset_contraction_changed_onset_strength_max{};
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  // Low, low-mid, high-mid, high, then the body/overtone crossover.
  std::array<std::array<std::uint32_t, kMaxVoices + 1U>,
             kSpectralTierCount + 1U>
      string_fret_spectral_head_best_frames{};
  // Union of the independent low/low-mid/high-mid/high/overtone winners.
  // This tests whether the separated heads jointly expose a physical group
  // that a single argmax necessarily cannot represent.
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_head_vote_mask_frames{};
  // Row is kSpectralShadowMarginThresholds; columns are strings zero through
  // seven followed by the unresolved sentinel.
  std::array<std::array<std::uint32_t, kMaxVoices + 1U>,
             kSpectralShadowMarginThresholdCount>
      spectral_head_plurality_best_frames{};
  // The exact bounded proposal currently available to production inference.
  // This isolates policy/cache rejection from the counterfactual projection.
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_tier_production_proposal_mask_frames{};
  std::array<
      std::array<std::uint32_t,
                 static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
      static_cast<std::size_t>(ReplayGroupMaskRelation::count)>
      spectral_tier_production_relation_lane_outcome_frames{};
  std::array<
      std::array<std::uint32_t,
                 static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
      static_cast<std::size_t>(ReplayGroupMaskRelation::count)>
      selector_group_relation_lane_outcome_frames{};
  std::array<
      std::array<std::uint32_t,
                 static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
      kTierCompletionDispositionCount>
      tier_completion_disposition_lane_outcome_frames{};
  // Counterfactual completion of exactly one missing fine-frequency member
  // from the independent tier heads. It remains offline-only until an entire
  // replay gate demonstrates that the completion is selective enough.
  std::uint32_t spectral_tier_completion_projected_frames{};
  std::array<std::uint32_t, 1U << kMaxVoices>
      spectral_tier_completion_candidate_mask_frames{};
  std::array<std::uint32_t, 21U>
      spectral_tier_completion_added_member_beat_coherence_bins{};
  std::array<std::uint32_t, 21U>
      spectral_tier_completion_added_member_ratio_bins{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_tier_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_tier_completion_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_tier_completion_matched_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      spectral_tier_completion_wrong_string_voices{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_exact_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_matched_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_wrong_string_voices{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      combined_spectral_completion_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      temporal_combined_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      temporal_combined_completion_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      temporal_combined_completion_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      temporal_combined_completion_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      tier_priority_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      tier_priority_completion_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      tier_priority_completion_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      tier_priority_completion_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      cached_group_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      cached_group_completion_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      cached_group_completion_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      cached_group_completion_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      cached_classifier_continuity_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      cached_classifier_continuity_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      cached_classifier_continuity_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      cached_classifier_continuity_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      continuity_classifier_union_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      continuity_classifier_union_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      continuity_classifier_union_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      continuity_classifier_union_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      production_cache_continuity_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      production_cache_continuity_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      production_cache_continuity_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      production_cache_continuity_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      committed_cache_continuity_changed_frames{};
  std::array<std::uint32_t, kSpectralShadowMarginThresholdCount>
      committed_cache_continuity_exact_frames{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      committed_cache_continuity_matched_delta{};
  std::array<std::int64_t, kSpectralShadowMarginThresholdCount>
      committed_cache_continuity_wrong_string_delta{};
  std::array<std::uint32_t, kSpectralTierAddedMemberRatioFloors.size()>
      tier_ratio_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralTierAddedMemberRatioFloors.size()>
      tier_ratio_completion_exact_frames{};
  std::array<std::int64_t, kSpectralTierAddedMemberRatioFloors.size()>
      tier_ratio_completion_matched_delta{};
  std::array<std::int64_t, kSpectralTierAddedMemberRatioFloors.size()>
      tier_ratio_completion_wrong_string_delta{};
  std::uint32_t safe_joint_completion_changed_frames{};
  std::uint32_t safe_joint_completion_exact_frames{};
  std::int64_t safe_joint_completion_matched_delta{};
  std::int64_t safe_joint_completion_wrong_string_delta{};
  std::uint32_t bounded_tier_completion_changed_frames{};
  std::uint32_t bounded_tier_completion_exact_frames{};
  std::int64_t bounded_tier_completion_matched_delta{};
  std::int64_t bounded_tier_completion_wrong_string_delta{};
  std::uint32_t bounded_joint_completion_changed_frames{};
  std::uint32_t bounded_joint_completion_exact_frames{};
  std::int64_t bounded_joint_completion_matched_delta{};
  std::int64_t bounded_joint_completion_wrong_string_delta{};
  std::uint32_t fine_exact_completion_changed_frames{};
  std::uint32_t fine_exact_completion_exact_frames{};
  std::int64_t fine_exact_completion_matched_delta{};
  std::int64_t fine_exact_completion_wrong_string_delta{};
  std::array<std::uint32_t, 3U> tier_ratio08_changed_by_phase{};
  std::array<std::int64_t, 3U> tier_ratio08_matched_delta_by_phase{};
  std::array<std::int64_t, 3U> tier_ratio08_wrong_delta_by_phase{};
  std::array<std::uint32_t, kSpectralTierBeatMaximums.size()>
      tier_beat_completion_changed_frames{};
  std::array<std::uint32_t, kSpectralTierBeatMaximums.size()>
      tier_beat_completion_exact_frames{};
  std::array<std::int64_t, kSpectralTierBeatMaximums.size()>
      tier_beat_completion_matched_delta{};
  std::array<std::int64_t, kSpectralTierBeatMaximums.size()>
      tier_beat_completion_wrong_string_delta{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      tier_classifier_completion_changed_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      tier_classifier_completion_exact_frames{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      tier_classifier_completion_matched_delta{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      tier_classifier_completion_wrong_string_delta{};
  std::array<std::array<std::uint32_t, 21U>, kSpectralTierCount + 1U>
      spectral_head_correct_margin_frames{};
  std::array<std::array<std::uint32_t, 21U>, kSpectralTierCount + 1U>
      spectral_head_other_margin_frames{};
  // Replay-only consensus sweep for selected pitches whose physical mask is
  // a strict subset of the labeled group. The six inputs are existing fine,
  // committed, profile, temporal, tier-completion, and classifier masks.
  std::array<std::uint32_t, kSelectedSubsetCompletionSupportFloors.size()>
      selected_subset_consensus_projected_frames{};
  std::array<std::uint32_t, kSelectedSubsetCompletionSupportFloors.size()>
      selected_subset_consensus_changed_frames{};
  std::array<std::uint32_t, kSelectedSubsetCompletionSupportFloors.size()>
      selected_subset_consensus_exact_frames{};
  std::array<std::int64_t, kSelectedSubsetCompletionSupportFloors.size()>
      selected_subset_consensus_matched_delta{};
  std::array<std::int64_t, kSelectedSubsetCompletionSupportFloors.size()>
      selected_subset_consensus_wrong_string_delta{};
  // For the same selected-subset frames, rows are fine, committed, profile,
  // temporal, tier completion, and independent classifier masks; columns use
  // ReplayTargetLaneOutcome against the complete labeled group.
  std::array<std::array<std::uint32_t,
                        static_cast<std::size_t>(
                            ReplayTargetLaneOutcome::count)>,
             6U>
      selected_subset_evidence_outcome_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      classifier_subset_projection_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      classifier_subset_changed_frames{};
  std::array<std::uint32_t, kRelaxedBandSpectralPolicyCount>
      classifier_subset_exact_frames{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      classifier_subset_matched_delta{};
  std::array<std::int64_t, kRelaxedBandSpectralPolicyCount>
      classifier_subset_wrong_string_delta{};
  std::array<std::array<std::uint32_t, kClassifierSubsetDispositionCount>,
             kRelaxedBandSpectralPolicyCount>
      classifier_subset_disposition_frames{};
#endif
#endif
};

struct ReplayResult final {
  std::uint64_t fingerprint{};
  std::uint64_t sample_count{};
  std::uint32_t snapshot_frames{};
  std::uint32_t labeled_frames{};
  std::uint32_t matched_label_frames{};
  std::uint32_t transition_count{};
  std::uint32_t transition_inside_hold_count{};
  std::uint32_t transition_gap_count{};
  std::uint32_t false_positive_voices{};
  std::uint32_t false_gap_voices{};
  std::uint32_t false_wrong_note_voices{};
  std::uint32_t false_wrong_string_voices{};
  std::uint32_t partial_detuning_frames{};
  std::uint32_t partial_detuning_comparisons{};
  double partial_detuning_absolute_error_sum{};
  std::uint32_t partial_detuning_margin_frames{};
  std::uint32_t partial_detuning_expected_best_frames{};
  double partial_detuning_margin_sum{};
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  ReplayCounterfactualMetrics calibrated_dp_replacement{};
  std::array<ReplayCounterfactualMetrics,
             kAdjacentSpectralDuplicatePolicies.size()>
      adjacent_spectral_duplicate_suppression{};
  std::array<ReplayCounterfactualMetrics,
             kAdjacentSpectralDuplicatePolicies.size()>
      production_adjacent_spectral_duplicate_suppression{};
  std::array<ReplayCounterfactualMetrics,
             kFineMaskComplexityPenalties.size()>
      fine_mask_complexity{};
  std::array<ReplayCounterfactualMetrics, kCorrelationShadowPolicies.size()>
      correlation_shadow{};
  std::array<ReplayCounterfactualMetrics, kJointPitchPolicies.size()>
      joint_pitch_shadow{};
  std::uint32_t joint_pitch_valid_frames{};
  std::uint32_t joint_pitch_invalid_frames{};
  double joint_pitch_residual_sum{};
#endif
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::array<std::uint64_t, kCandidateSpectralShadowIntervalBucketCount>
      false_wrong_note_interval_frames{};
  std::array<
      std::array<std::uint64_t,
                 kCandidateSpectralShadowIntervalBucketCount>,
      kFalseWrongNoteAgeBucketCount>
      false_wrong_note_age_interval_frames{};
  std::array<
      std::array<std::uint64_t, kFalseWrongNoteCentsBucketCount>,
      kCandidateSpectralShadowIntervalBucketCount>
      false_wrong_note_interval_cents_frames{};
  // Rows follow TunerVoiceState (settling, coasting, tracking); columns are
  // the existing absolute wrong-note interval buckets. This reveals whether
  // an error is newly selected or merely surviving the release path.
  std::array<
      std::array<std::uint64_t,
                 kCandidateSpectralShadowIntervalBucketCount>,
      kTunerVoiceStateCount>
      false_wrong_note_state_interval_frames{};
  // Rows are the nearest active labeled MIDI note; columns are the emitted
  // MIDI note. This offline-only matrix preserves the actual replacement
  // direction that the absolute interval histogram intentionally discards.
  std::array<std::array<std::uint64_t, 128U>, 128U>
      false_wrong_note_expected_observed_frames{};
  // These counters split final wrong-note frames into raw detector errors and
  // errors introduced by the calibrated output-note layer.
  std::uint64_t false_wrong_note_detected_expected_frames{};
  std::uint64_t false_wrong_note_output_changed_frames{};
  // Direction zero is one semitone below the nearest active label; direction
  // one is one semitone above it. Projection disposition follows the exact
  // production gate order. Lane disposition is independent so a pitch fix
  // cannot hide a physical-string regression.
  std::array<
      std::array<std::uint64_t,
                 static_cast<std::size_t>(
                     AdjacentWrongNoteProjectionDisposition::count)>,
      kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_projection_disposition_frames{};
  std::array<
      std::array<std::uint64_t,
                 static_cast<std::size_t>(
                     CalibratedAdjacentProjectionDisposition::count)>,
      kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_projection_reason_frames{};
  std::array<
      std::array<std::uint64_t,
                 static_cast<std::size_t>(
                     AdjacentWrongNoteExpectedPresence::count)>,
      kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_presence_frames{};
  std::array<
      std::array<std::uint64_t,
                 static_cast<std::size_t>(
                     AdjacentWrongNoteLaneDisposition::count)>,
      kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_lane_disposition_frames{};
  // Column encoding is
  // ((projection * expected_presence_count) + presence) * lane_count + lane.
  // Keeping the three predicates joint distinguishes a stale coasting extra
  // voice from a genuinely missing adjacent target without changing MIDI.
  std::array<std::array<std::uint64_t,
                        kAdjacentWrongNoteJointContextCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_joint_context_frames{};
  // Joint causal attribution for the same adjacent wrong-note frames:
  // raw detector identity, whether output calibration changed the note, and
  // whether the emitted lane belongs to the nearest expected pitch.
  std::array<std::array<std::uint64_t,
                        kAdjacentWrongNoteRawOutputLaneCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_raw_output_lane_frames{};
  // Candidate-level cause of an adjacent wrong note. Direction zero means
  // the output was one semitone below the nearest active label; direction one
  // means it was one semitone above. These replay-only counters answer whether
  // the intended pitch was quiet/weak/rejected/evicted, how competitive its
  // raw score was against the emitted pitch, whether it retained direct
  // evidence, and whether the emitted physical lane could legally host it.
  std::array<std::array<
                 std::uint64_t, kSelectionDispositionCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_selection_frames{};
  std::array<std::array<std::uint64_t, kCandidateAdmissionRatioBinCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_score_ratio_frames{};
  std::array<std::array<std::uint64_t, kCandidateAdmissionRatioBinCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_to_observed_score_ratio_frames{};
  std::array<std::array<std::uint64_t, 32U>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_evidence_frames{};
  // Columns are unavailable, playable only on other lanes, and playable on
  // the emitted lane. This is deliberately independent of label correctness.
  std::array<std::array<std::uint64_t, 3U>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_playable_lane_frames{};
  // Joint selector/presence/lane table. This distinguishes a missing intended
  // pitch from a duplicate neighboring candidate emitted beside an already
  // correct pitch without using either marginal as a proxy for the other.
  std::array<std::array<std::uint64_t,
                        kAdjacentExpectedCandidateContextCount>,
             kAdjacentWrongNoteDirectionCount>
      adjacent_wrong_note_expected_candidate_context_frames{};
  // Rows distinguish real adjacent chord tones, one expected tone plus one
  // false neighbor, and two unlabeled outputs. This tests separability before
  // any suppression policy is permitted to affect a replay snapshot.
  std::array<
      std::array<std::uint64_t, kAdjacentEnvelopeCoherenceBinCount>,
      static_cast<std::size_t>(AdjacentEnvelopePairClass::count)>
      adjacent_envelope_coherence_frames{};
  std::array<
      std::array<std::uint64_t, kAdjacentSpectralErrorGapBinCount>,
      static_cast<std::size_t>(AdjacentEnvelopePairClass::count)>
      adjacent_spectral_error_gap_frames{};
  // Offline replacement-cents shadow. Rows are minimum-partial count first,
  // then maximum-deviation threshold. Columns use the standard
  // current/projected expected outcome encoding.
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kMultiPartialPhasePolicyCount>
      multi_partial_phase_rebin_outcome_frames{};
  std::array<std::uint64_t, kMultiPartialPhasePolicyCount>
      multi_partial_phase_rebin_available_frames{};
  std::array<std::uint64_t, kMultiPartialPhasePolicyCount>
      multi_partial_phase_rebin_changed_frames{};
  // Outcome index is (current_expected ? 2 : 0) |
  //                  (projected_expected ? 1 : 0).
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_outcome_frames{};
  std::array<std::uint64_t, kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_changed_frames{};
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_guarded_outcome_frames{};
  std::array<std::uint64_t, kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_guarded_changed_frames{};
  // Row is threshold*member_bucket_count + member_count (five means >=5).
  // Column is label_age_bucket*outcome_count + outcome.
  std::array<
      std::array<std::uint64_t,
                 kCalibratedPitchRebinAgeOutcomeBucketCount>,
      kCalibratedPitchRebinThresholds.size() *
          kCalibratedPitchRebinMemberBucketCount>
      calibrated_pitch_rebin_member_age_outcome_frames{};
  // Row is (((threshold*string_count + string)*fret_count + current_fret)*2
  //           + direction), where direction zero is lower and one is upper.
  // Only context-eligible changed projections are recorded. Column is the
  // same current/projected expected outcome used by the other rebin tables.
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kCalibratedPitchRebinDetailRowCount>
      calibrated_pitch_rebin_guarded_detail_outcome_frames{};
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_stable_outcome_frames{};
  std::array<std::uint64_t, kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_stable_changed_frames{};
  std::array<std::array<std::uint64_t,
                        kCalibratedPitchRebinOutcomeCount>,
             kCalibratedPitchRebinProjectedErrorThresholds.size()>
      calibrated_pitch_rebin_projected_error_outcome_frames{};
  std::array<std::uint64_t,
             kCalibratedPitchRebinProjectedErrorThresholds.size()>
      calibrated_pitch_rebin_projected_error_changed_frames{};
  // Scores each simultaneously active MIDI pitch once, after unioning the
  // physical-string masks of every overlapping label for that pitch. The
  // legacy per-label counters remain useful for isolated material, but they
  // cannot represent a real multi-string unison because the detector exposes
  // one combined lane mask. Member-count bin zero is reserved for note-only
  // labels. The expected/observed matrix is indexed as expected*256+observed.
  std::uint64_t physical_group_labeled_frames{};
  std::uint64_t physical_group_matched_frames{};
  std::uint64_t physical_group_missing_string_voices{};
  std::uint64_t physical_group_extra_string_voices{};
  std::array<std::uint64_t,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      physical_group_lane_outcome_frames{};
  std::array<std::uint64_t, kMaxVoices + 1U>
      physical_group_expected_member_frames{};
  std::array<std::array<
                 std::uint64_t,
                 static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
             kMaxVoices + 1U>
      physical_group_member_lane_outcome_frames{};
  // Evidence-stage attribution for each physical group. These distinguish a
  // failed fine-frequency fit from a fit that was not committed, and both
  // from a committed group that was later lost by selection/assignment.
  std::array<std::uint64_t,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      physical_group_fine_lane_outcome_frames{};
  std::array<std::uint64_t,
             static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>
      physical_group_committed_lane_outcome_frames{};
  std::array<std::array<
                 std::uint64_t,
                 static_cast<std::size_t>(ReplayTargetLaneOutcome::count)>,
             kSelectionDispositionCount>
      physical_group_selection_lane_outcome_frames{};
  // Flattened as
  // (((selection * 4 + fine_relation) * 4 + committed_relation) * 6 +
  //   observed_lane_outcome). Each active physical-group frame contributes
  // exactly once. Run counters and maxima expose whether a loss is a brief
  // transition or a sustained evidence/assignment failure.
  std::array<std::uint64_t, kPhysicalGroupCausalCellCount>
      physical_group_causal_frames{};
  // Same encoding as physical_group_causal_frames, with the third relation
  // representing the fresh pending fine mask instead of the committed mask.
  // This identifies a full group that is already measured but still waiting
  // at the consensus/commit boundary.
  std::array<std::uint64_t, kPhysicalGroupCausalCellCount>
      physical_group_pending_causal_frames{};
  std::array<std::array<std::uint64_t, kPhysicalGroupCausalCellCount>,
             kMaxVoices + 1U>
      physical_group_member_pending_causal_frames{};
  // Join the selected triple / fine subset / exact pending / missing output
  // cell to the existing recovery policy, evaluated from exposed frame-end
  // state. These are counterfactual gates, not a trace of the production call.
  // Last disposition is the production active/score guard, which precedes
  // the shared recovery policy. Context = (fine members * 4 + cached relation)
  // * 2 + production continuity-changed flag.
  std::array<std::uint64_t,
             kArticulatedUnisonReacquisitionDispositionCount + 1U>
      physical_group_pending_triple_recovery_frames{};
  std::array<std::array<std::uint64_t, (kMaxVoices + 1U) * 4U * 2U>,
             kArticulatedUnisonReacquisitionDispositionCount + 1U>
      physical_group_pending_triple_recovery_context_frames{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionDispositionCount + 1U>
      physical_group_pending_triple_cached_matched_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionDispositionCount + 1U>
      physical_group_pending_triple_cached_exact_delta{};
  std::array<std::int64_t,
             kArticulatedUnisonReacquisitionDispositionCount + 1U>
      physical_group_pending_triple_cached_wrong_string_delta{};
  // Sparse attribution of selected, incomplete triples with a valid fit or
  // enough history but a deferred analysis. Bit fields: reason[0:2], fit
  // member count[3:6], final fine member count[7:10], disposition[11:14],
  // expected residual rank + 1[15:22] (zero unavailable), beat >= .20[23],
  // connected[24], pending relation[25:26], committed relation[27:28].
  // Available only with the offline spectral-template diagnostics enabled.
  std::map<std::uint64_t, std::uint64_t>
      physical_group_completed_triple_fit_frames{};
  // All feasible 2-4 masks on active selected labeled pitches. The hypothesis
  // changes only nuisance-trend weighting, never the .20 per-edge threshold.
  // Key: expected count[0:3], proposed count[4:7], proposed outcome[8:10],
  // old/new pass bits[11:12], minimum cycles bin[13:15], output outcome[16:18].
  std::map<std::uint64_t, std::uint64_t> physical_group_hann_beat_mask_frames{};
  // Active selected physical groups; groups with a feasible 2-4 mask;
  // successfully prepared groups; prepare-invalid groups with a model;
  // evaluated masks. No-fit groups = first minus second.
  std::array<std::uint64_t, 5U> physical_group_hann_beat_coverage{};
  // Key: note[0:6], edge index[7:11], expected count[12:15],
  // both edge strings expected[16]. Each edge counted once per physical group.
  std::map<std::uint64_t, HannBeatEdgeSummary> physical_group_hann_beat_edges{};
  // Eligible labeled groups, groups with models, prepared groups, masks.
  std::array<std::uint64_t, 4U> physical_group_frequency_refinement_coverage{};
  // Key: note[0:6], expected mask[7:14], proposed mask[15:22],
  // actual output outcome[23:25], arm (fixed/common/independent)[26:27].
  std::map<std::uint64_t, FrequencyRefinementSummary>
      physical_group_frequency_refinement{};
  // Counts the first non-exact causal cell after an exact physical-group
  // output. Member-indexing isolates practical triples and quads from pair
  // setup passages without retaining frame-level traces.
  std::array<std::array<std::uint64_t, kPhysicalGroupCausalCellCount>,
             kMaxVoices + 1U>
      physical_group_member_exact_exit_frames{};
  std::array<std::uint64_t, kPhysicalGroupCausalCellCount>
      physical_group_causal_runs{};
  std::array<std::uint32_t, kPhysicalGroupCausalCellCount>
      physical_group_causal_longest_run_frames{};
  std::array<std::array<std::uint64_t, kPhysicalGroupCausalCellCount>,
             kMaxVoices + 1U>
      physical_group_member_causal_frames{};
  std::array<std::array<std::uint64_t, kPhysicalGroupCausalCellCount>,
             kMaxVoices + 1U>
      physical_group_member_causal_runs{};
  std::array<std::array<std::uint32_t, kPhysicalGroupCausalCellCount>,
             kMaxVoices + 1U>
      physical_group_member_causal_longest_run_frames{};
  // Flattened as ((selection * 7 + fine_unresolved_reason) * 6 +
  // observed_lane_outcome). This separates history starvation from a fit that
  // reached the commit or assignment stages. Member-indexed rows distinguish
  // the practical three-string target from the preceding physical pairs.
  std::array<std::uint64_t, kPhysicalGroupFineUnresolvedCellCount>
      physical_group_fine_unresolved_frames{};
  std::array<std::uint64_t, kPhysicalGroupFineUnresolvedCellCount>
      physical_group_fine_unresolved_runs{};
  std::array<std::uint32_t, kPhysicalGroupFineUnresolvedCellCount>
      physical_group_fine_unresolved_longest_run_frames{};
  std::array<
      std::array<std::uint64_t, kPhysicalGroupFineUnresolvedCellCount>,
      kMaxVoices + 1U>
      physical_group_member_fine_unresolved_frames{};
  std::array<
      std::array<std::uint64_t, kPhysicalGroupFineUnresolvedCellCount>,
      kMaxVoices + 1U>
      physical_group_member_fine_unresolved_runs{};
  std::array<
      std::array<std::uint32_t, kPhysicalGroupFineUnresolvedCellCount>,
      kMaxVoices + 1U>
      physical_group_member_fine_unresolved_longest_run_frames{};
  // Flattened as ((fine_relation * 4 + classifier_relation) * 6 +
  // observed_lane_outcome). This offline-only joint table shows whether an
  // exact spectral fit exists specifically when fine evidence or the emitted
  // physical group is incomplete. Each physical group contributes once via
  // its deterministic leader label.
  std::array<std::uint64_t, kPhysicalGroupFineClassifierCellCount>
      physical_group_fine_classifier_frames{};
  std::array<
      std::array<std::uint64_t, kPhysicalGroupFineClassifierCellCount>,
      kMaxVoices + 1U>
      physical_group_member_fine_classifier_frames{};
  std::array<std::uint64_t, kFineResidualExpansionPolicyCount>
      fine_residual_expansion_changed_frames{};
  std::array<std::uint64_t, kFineResidualExpansionPolicyCount>
      fine_residual_expansion_exact_frames{};
  std::array<std::int64_t, kFineResidualExpansionPolicyCount>
      fine_residual_expansion_matched_delta{};
  std::array<std::int64_t, kFineResidualExpansionPolicyCount>
      fine_residual_expansion_wrong_string_delta{};
  std::vector<std::uint64_t>
      physical_group_expected_observed_mask_frames{};
  std::vector<std::uint64_t> physical_group_expected_fine_mask_frames{};
  std::vector<std::uint64_t>
      physical_group_expected_committed_mask_frames{};
  // Candidate-population evidence during labeled snapshots. Class zero is a
  // MIDI pitch named by at least one active label; class one is every other
  // playable pitch and therefore contains the competing harmonics and other
  // false admissions that target-only diagnostics cannot measure.
  std::uint64_t candidate_population_labeled_snapshots{};
  std::array<std::array<std::uint64_t, kSelectionDispositionCount>,
             kCandidatePopulationClassCount>
      candidate_population_disposition_frames{};
  std::array<std::array<std::uint64_t, kCandidateAdmissionRatioBinCount>,
             kCandidatePopulationClassCount>
      candidate_population_score_threshold_ratio_frames{};
  std::array<std::array<std::uint64_t, kCandidateAdmissionRatioBinCount>,
             kCandidatePopulationClassCount>
      candidate_population_below_threshold_score_ratio_frames{};
  std::array<std::array<std::uint64_t, 21U>,
             kCandidatePopulationClassCount>
      candidate_population_below_threshold_fundamental_ratio_frames{};
  std::array<std::array<std::uint64_t,
                        kCandidateAdmissionEvidenceFlagCount>,
             kCandidatePopulationClassCount>
      candidate_population_below_threshold_evidence_flag_frames{};
  std::array<std::array<std::array<std::uint64_t, 21U>,
                        kCandidateAdmissionRatioBinCount>,
             kCandidatePopulationClassCount>
      candidate_population_below_threshold_direct_evidence_frames{};
  std::array<std::array<std::array<std::uint64_t, 21U>, 21U>,
             kCandidatePopulationClassCount>
      candidate_population_below_threshold_pitch_band_peak_frames{};
  // Joint calibration selectivity for direct, below-threshold candidates.
  // Rows flatten class (target/correct string, target/wrong string,
  // non-target), score ratio, and best-profile similarity; columns are the
  // best-minus-second profile margin. This remains replay-only and cannot
  // change MIDI output.
  std::array<std::array<std::uint64_t,
                        kCandidateCalibrationSimilarityBinCount>,
             kCandidateCalibrationJointRowCount>
      candidate_population_below_threshold_calibration_joint_frames{};
  std::array<std::uint64_t, kCandidateCalibrationPopulationClassCount>
      candidate_population_unique_playable_direct_frames{};
  // Policy-major, then target/correct-string, target/wrong-string, and
  // non-target population classes. A frame may satisfy multiple policies.
  std::array<std::array<std::uint64_t,
                        kCandidateCalibrationPopulationClassCount>,
             kCandidateBandCalibrationPolicyCount>
      candidate_population_band_calibration_shadow_frames{};
  // Counterfactual for the exact string-5 failure signature: a lower
  // candidate rejected by its octave despite a decisive measured string
  // fingerprint. Columns are target/correct string, target/wrong string, and
  // non-target. This is diagnostic only and never admits a production voice.
  std::array<std::array<std::uint64_t,
                        kCandidateCalibrationPopulationClassCount>,
             kSpectralShadowCalibrationPolicyCount>
      candidate_population_octave_shadow_calibration_frames{};
  std::array<std::array<std::uint64_t,
                        kCandidateCalibrationPopulationClassCount>,
             kSpectralShadowCalibrationPolicyCount>
      candidate_population_octave_shadow_isolated_context_frames{};
  // One winner per snapshot for the conjunction of direct local evidence,
  // measured calibration identity, and the independent one-string spectral
  // classifier. Columns are target/correct string, target/wrong string, and
  // non-target. This remains replay-only.
  std::array<std::array<std::uint64_t,
                        kCandidateCalibrationPopulationClassCount>,
             kCombinedCandidatePolicyCount>
      combined_candidate_admission_selected_frames{};
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  std::array<std::array<std::uint64_t, 1U << kMaxVoices>,
             kCandidatePopulationClassCount>
      candidate_population_spectral_head_vote_mask_frames{};
#endif
  // All-candidate 102-value corridor admission shadow. Each policy applies a
  // different score floor; every gate combines one maximum fit error with one
  // minimum posterior margin. Class zero is a labeled pitch and class one is
  // a competing pitch. These counters never affect detector state or MIDI.
  std::uint64_t candidate_spectral_shadow_active_peak{};
  std::array<std::array<std::uint64_t, kCandidatePopulationClassCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_candidate_frames{};
  std::array<std::array<std::uint64_t, kCandidatePopulationClassCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_ready_frames{};
  std::array<std::array<std::uint64_t, kCandidateSpectralShadowGateCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_selected_frames{};
  std::array<std::array<std::uint64_t, kCandidateSpectralShadowGateCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_target_correct_frames{};
  std::array<std::array<std::uint64_t, kCandidateSpectralShadowGateCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_target_wrong_string_frames{};
  std::array<std::array<std::uint64_t, kCandidateSpectralShadowGateCount>,
             kCandidateSpectralShadowPolicyCount>
      candidate_spectral_shadow_other_false_frames{};
  // Predicted physical-string partition for each policy/gate outcome above.
  // Rows are flattened as policy * gate-count + gate; columns are strings
  // zero through seven. These remain offline-only and let replay determine
  // whether a narrow string-specific gate is materially safer than the
  // aggregate spectral admission policy.
  std::array<std::array<std::uint64_t, kMaxVoices>,
             kCandidateSpectralShadowPolicyCount *
                 kCandidateSpectralShadowGateCount>
      candidate_spectral_shadow_target_correct_by_string_frames{};
  std::array<std::array<std::uint64_t, kMaxVoices>,
             kCandidateSpectralShadowPolicyCount *
                 kCandidateSpectralShadowGateCount>
      candidate_spectral_shadow_target_wrong_string_by_string_frames{};
  std::array<std::array<std::uint64_t, kMaxVoices>,
             kCandidateSpectralShadowPolicyCount *
                 kCandidateSpectralShadowGateCount>
      candidate_spectral_shadow_other_false_by_string_frames{};
  std::array<
      std::array<std::uint64_t,
                 kCandidateSpectralShadowIntervalBucketCount>,
      kCandidateSpectralShadowPolicyCount * kCandidateSpectralShadowGateCount>
      candidate_spectral_shadow_other_false_interval_frames{};
#endif
  std::vector<ReplayLabelResult> label_results{};
};

bool decode_wave_bytes(const std::uint8_t* bytes, std::size_t size,
                       WaveData& output, ReplayError& error);

// TSV columns are exact sample indices:
// start_sample<TAB>end_sample<TAB>midi_note<TAB>string_mask
// An optional fifth calibration_pass column accepts values 1..255.
// A six-column form appends expected_cents in the closed range -50..50.
// Rows may overlap to describe chords. They must be ordered by start sample.
bool parse_replay_labels(const char* text, std::size_t size,
                         std::uint64_t sample_count,
                         std::vector<ReplayLabel>& output,
                         ReplayError& error);

bool run_detector_replay(const WaveData& wave,
                         const std::vector<ReplayLabel>& labels,
                         const PersistentConfig& config,
                         const StringCalibrationBank* calibration,
                         std::size_t input_partition,
                         ReplayResult& output, ReplayError& error,
                         const UnisonSpectralShadowTemplateBank*
                             spectral_shadow_templates = nullptr,
                         const CandidateAdmissionRescuePolicy*
                             candidate_admission_rescue = nullptr,
                         const FrettedPositionPriorPolicy*
                             fretted_position_prior = nullptr,
                         const DecisiveCalibratedSelectorPolicy*
                             decisive_calibrated_selector = nullptr,
                         const CalibratedDpReplacementPolicy*
                             calibrated_dp_replacement = nullptr,
                         const ProductionDpReplacementLanePolicy*
                             production_dp_replacement_lanes = nullptr,
                         bool diagnostic_fine_mask_pruning = false,
                         bool diagnostic_fine_beat_pruning = false,
                         bool diagnostic_collecting_fine_history_carry =
                             false,
                         double diagnostic_correlation_seconds = -1.0,
                         bool diagnostic_selection_window_only = false,
                         bool diagnostic_correlation_shadow_only = false,
                         bool diagnostic_joint_pitch_residual = false,
                         FrequencyWindowCapture* frequency_window_capture = nullptr);

// Derives one physical-string map from discrete, stable, labeled fret holds.
// Every fret must have at least two rows for the requested single-bit lane.
bool derive_labeled_string_calibration(
    const WaveData& wave, const std::vector<ReplayLabel>& labels,
    const PersistentConfig& config, std::uint8_t string_index,
    StringCalibrationBank& output, ReplayError& error);

const char* replay_error_name(ReplayError error) noexcept;

}  // namespace m3::offline
