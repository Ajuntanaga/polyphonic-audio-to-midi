#include "replay.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstring>
#include <limits>
#include <memory>
#include <numeric>
#include <string_view>
#include <type_traits>

#include "m3/constants.hpp"
#include "m3/factory_calibration.hpp"
#include "m3/pitch_math.hpp"
#include "m3/polyphonic_pitch_detector.hpp"
#include "joint_pitch_residual.hpp"
#include "frequency_refinement_shadow.hpp"
#include "unison_spectral_shadow.hpp"

namespace m3::offline {
namespace {

constexpr std::size_t kMaximumLabelRows = 65536U;
constexpr std::size_t kMaximumLabeledCalibrationPasses = 8U;
constexpr std::size_t kMaximumInputPartition = 1U << 20U;
constexpr double kMaximumLabeledCalibrationCents = 49.0;
constexpr double kMaximumLabeledPassDifferenceCents = 24.0;
constexpr double kMinimumLabeledCorrelation = 0.55;
constexpr double kMaximumPartialDetuningStandardDeviationCents = 3.0;
constexpr std::size_t kLabeledAnalysisMilliseconds = 750U;
constexpr std::uint64_t kFnvOffset = 1469598103934665603ULL;
constexpr std::uint64_t kFnvPrime = 1099511628211ULL;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
static_assert(static_cast<std::size_t>(SelectionDisposition::count) == 6U);
static_assert(static_cast<std::size_t>(QuietDisposition::count) ==
              kQuietDispositionCount);
static_assert(
    static_cast<std::size_t>(FineFrequencyUnresolvedReason::count) ==
    kFineFrequencyUnresolvedReasonCount);
static_assert(static_cast<std::size_t>(RetainedUnisonDisposition::count) ==
              8U);
static_assert(static_cast<std::size_t>(FineGroupDisposition::count) == 7U);
static_assert(
    static_cast<std::size_t>(
        ObservedUnisonReacquisitionDisposition::count) ==
    kSpectralReacquisitionDispositionCount);
static_assert(
    static_cast<std::size_t>(
        ArticulatedUnisonReacquisitionDisposition::count) ==
    kArticulatedUnisonReacquisitionDispositionCount);
static_assert(kSpectralShadowMarginThresholdCount ==
              kSpectralShadowMarginThresholds.size());
constexpr std::array<double, kCandidateSpectralShadowPolicyCount>
    kCandidateSpectralShadowScoreFloors{0.70, 0.80, 0.90,
                                        0.70, 0.80, 0.90};
constexpr std::array<bool, kCandidateSpectralShadowPolicyCount>
    kCandidateSpectralShadowUsesPitchBand{false, false, false,
                                           true, true, true};
constexpr double kCandidateSpectralShadowFundamentalFloor = 0.60;
constexpr double kCandidateSpectralShadowLocalGlobalFloor = 0.10;
constexpr std::array<double,
                     kCandidateSpectralShadowErrorThresholdCount>
    kCandidateSpectralShadowErrorThresholds{0.05, 0.075, 0.10,
                                            0.125, 0.15, 0.20};
constexpr std::array<double,
                     kCandidateSpectralShadowMarginThresholdCount>
    kCandidateSpectralShadowMarginThresholds{0.05, 0.075, 0.10,
                                             0.125, 0.15, 0.20};
constexpr std::size_t kMaximumCandidateSpectralShadowTrackers = 12U;
constexpr double kCandidateSpectralTrackingStartScoreRatio = 0.50;
constexpr double kCandidateSpectralTrackingStartFundamentalRatio = 0.50;
constexpr double kCandidateSpectralTrackingRetainScoreRatio = 0.25;
constexpr double kCandidateSpectralTrackingRetainFundamentalRatio = 0.30;
constexpr double kCandidateSpectralTrackingStartBandScoreRatio = 0.70;
constexpr double kCandidateSpectralTrackingStartBandFundamentalRatio = 0.60;
constexpr double kCandidateSpectralTrackingRetainBandScoreRatio = 0.40;
constexpr double kCandidateSpectralTrackingRetainBandFundamentalRatio = 0.40;
constexpr double kCandidateSpectralTrackingStartLocalGlobalFloor = 0.10;
constexpr double kCandidateSpectralTrackingRetainLocalGlobalFloor = 0.05;
static_assert(kCandidateSpectralShadowGateCount ==
              kCandidateSpectralShadowErrorThresholdCount *
                  kCandidateSpectralShadowMarginThresholdCount);
static_assert(kCandidateSpectralShadowIntervalBucketCount ==
              kCandidateSpectralIntervalBucketCount);
#endif

std::uint8_t mask_member_count(std::uint8_t mask) noexcept {
  std::uint8_t count = 0U;
  while (mask != 0U) {
    count = static_cast<std::uint8_t>(count + (mask & 1U));
    mask = static_cast<std::uint8_t>(mask >> 1U);
  }
  return count;
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
std::size_t candidate_score_ratio_bin(double ratio) noexcept {
  return static_cast<std::size_t>(
      std::min(40.0, std::floor(std::clamp(ratio, 0.0, 2.0) * 20.0)));
}

std::size_t unit_ratio_bin(double ratio) noexcept {
  return static_cast<std::size_t>(
      std::min(20.0, std::floor(std::clamp(ratio, 0.0, 1.0) * 20.0)));
}

std::size_t calibration_margin_bin(double margin) noexcept {
  return static_cast<std::size_t>(
      std::min(20.0, std::floor(std::clamp(margin, 0.0, 0.20) * 100.0)));
}

std::size_t spectral_single_metric_bin(double value) noexcept {
  return static_cast<std::size_t>(
      std::min(40.0, std::floor(std::clamp(value, 0.0, 1.0) * 40.0)));
}

std::size_t candidate_admission_evidence_flags(
    const CandidateAdmissionDiagnostics& diagnostic) noexcept {
  return (diagnostic.active ? 1U : 0U) |
         (diagnostic.direct_fundamental_peak ? 2U : 0U) |
         (diagnostic.local_peak ? 4U : 0U) |
         (diagnostic.candidate_evidence ? 8U : 0U) |
         (diagnostic.calibrated_direct_support ? 16U : 0U);
}
#endif

std::uint16_t read_u16(const std::uint8_t* bytes) noexcept {
  return static_cast<std::uint16_t>(bytes[0]) |
         static_cast<std::uint16_t>(
             static_cast<std::uint16_t>(bytes[1]) << 8U);
}

std::uint32_t read_u32(const std::uint8_t* bytes) noexcept {
  std::uint32_t value = 0U;
  for (std::size_t index = 0U; index < 4U; ++index) {
    value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8U);
  }
  return value;
}

bool fourcc(const std::uint8_t* bytes, const char* expected) noexcept {
  return bytes[0] == static_cast<std::uint8_t>(expected[0]) &&
         bytes[1] == static_cast<std::uint8_t>(expected[1]) &&
         bytes[2] == static_cast<std::uint8_t>(expected[2]) &&
         bytes[3] == static_cast<std::uint8_t>(expected[3]);
}

void hash_byte(std::uint64_t& hash, std::uint8_t value) noexcept {
  hash = (hash ^ value) * kFnvPrime;
}

template <typename Integer>
void hash_integer(std::uint64_t& hash, Integer value) noexcept {
  using Unsigned = std::make_unsigned_t<Integer>;
  const Unsigned bits = static_cast<Unsigned>(value);
  for (std::size_t index = 0U; index < sizeof(Integer); ++index) {
    hash_byte(hash, static_cast<std::uint8_t>(
                        bits >> static_cast<unsigned>(index * 8U)));
  }
}

bool parse_u64(std::string_view field, std::uint64_t& value) noexcept {
  if (field.empty()) {
    return false;
  }
  const char* first = field.data();
  const char* last = first + field.size();
  const auto [parsed_end, error] = std::from_chars(first, last, value, 10);
  return error == std::errc{} && parsed_end == last;
}

bool parse_expected_cents(std::string_view field,
                          std::int16_t& value_q8) noexcept {
  if (field.empty()) {
    return false;
  }
  double value = 0.0;
  const char* first = field.data();
  const char* last = first + field.size();
  const auto [parsed_end, error] = std::from_chars(first, last, value);
  if (error != std::errc{} || parsed_end != last || !std::isfinite(value) ||
      value < -50.0 || value > 50.0) {
    return false;
  }
  value_q8 = static_cast<std::int16_t>(std::lround(value * 256.0));
  return true;
}

bool sample_is_inside_label(std::uint64_t sample_index,
                            const std::vector<ReplayLabel>& labels) noexcept {
  for (const ReplayLabel& label : labels) {
    if (sample_index >= label.start_sample &&
        sample_index < label.end_sample) {
      return true;
    }
  }
  return false;
}

bool lane_mask_matches_label(std::uint8_t observed_mask,
                             const ReplayLabel& label) noexcept {
  return label.string_mask == 0U ? observed_mask != 0U
                                 : observed_mask == label.string_mask;
}

bool snapshot_matches_label(const TunerSnapshot& snapshot,
                            const ReplayLabel& label) noexcept {
  std::uint8_t observed_mask = 0U;
  bool note_seen = false;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const TunerVoice& observed = snapshot.voices[voice];
    if (observed.midi_note != label.midi_note) {
      continue;
    }
    note_seen = true;
    if (observed.string_index < kMaxVoices) {
      observed_mask = static_cast<std::uint8_t>(
          observed_mask | (1U << observed.string_index));
    }
  }
  return label.string_mask == 0U ? note_seen
                                 : lane_mask_matches_label(observed_mask,
                                                           label);
}

std::uint8_t matching_note_lane_mask(const TunerSnapshot& snapshot,
                                     std::uint8_t midi_note) noexcept {
  std::uint8_t mask = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const TunerVoice& observed = snapshot.voices[voice];
    if (observed.midi_note == midi_note &&
        observed.string_index < kMaxVoices) {
      mask = static_cast<std::uint8_t>(
          mask | static_cast<std::uint8_t>(1U << observed.string_index));
    }
  }
  return mask;
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
std::uint8_t other_note_lane_mask(const TunerSnapshot& snapshot,
                                  std::uint8_t midi_note) noexcept {
  std::uint8_t mask = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const TunerVoice& observed = snapshot.voices[voice];
    if (observed.midi_note != midi_note &&
        observed.string_index < kMaxVoices) {
      mask = static_cast<std::uint8_t>(
          mask | static_cast<std::uint8_t>(1U << observed.string_index));
    }
  }
  return mask;
}

std::uint8_t playable_string_mask(std::uint8_t midi_note,
                                  std::uint8_t maximum_fret) noexcept {
  std::uint8_t mask = 0U;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if (midi_note >= kM3OpenNotes[string] &&
        static_cast<std::size_t>(midi_note - kM3OpenNotes[string]) <=
            maximum_fret) {
      mask = static_cast<std::uint8_t>(mask | (1U << string));
    }
  }
  return mask;
}
#endif

bool voice_matches_label(const TunerVoice& voice,
                         const ReplayLabel& label) noexcept {
  if (voice.midi_note != label.midi_note) {
    return false;
  }
  if (label.string_mask == 0U) {
    return true;
  }
  return voice.string_index < kMaxVoices &&
         (label.string_mask & (1U << voice.string_index)) != 0U;
}

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
TunerSnapshot calibrated_dp_replacement_projection(
    const TunerSnapshot& snapshot, const PolyphonicPitchDetector& detector,
    const CalibratedDpReplacementPolicy& policy,
    std::uint32_t& changed_voices) noexcept {
  TunerSnapshot projected = snapshot;
  for (std::size_t voice_index = 0U;
       voice_index < snapshot.voice_count; ++voice_index) {
    const TunerVoice& voice = snapshot.voices[voice_index];
    if (voice.shares_pitch_evidence() ||
        mask_member_count(
            detector.committed_unison_mask(voice.midi_note)) >= 2U) {
      return projected;
    }
  }
  for (std::size_t note = 0U; note < 128U; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (mask_member_count(detector.committed_unison_mask(midi_note)) >= 2U ||
        mask_member_count(detector.fine_frequency_member_mask(midi_note)) >=
            2U ||
        mask_member_count(
            detector.fine_frequency_pending_member_mask(midi_note)) >= 2U) {
      return projected;
    }
  }
  std::array<double, kMaxVoices> best_advantage{};
  std::array<std::uint8_t, kMaxVoices> best_note{};
  std::array<bool, kMaxVoices> has_proposal{};
  for (std::size_t note = 0U; note < 128U; ++note) {
    const auto midi_note = static_cast<std::uint8_t>(note);
    if (detector.selection_disposition(midi_note) !=
        SelectionDisposition::dp_evicted) {
      continue;
    }
    const CandidateAdmissionDiagnostics candidate =
        detector.candidate_admission_diagnostics(midi_note);
    const double calibration_margin =
        candidate.best_calibration_similarity -
        candidate.second_calibration_similarity;
    const std::uint8_t string = candidate.best_calibrated_string;
    if (candidate.active || !candidate.direct_fundamental_peak ||
        (!candidate.local_peak && !candidate.candidate_evidence) ||
        string >= kMaxVoices ||
        (policy.allowed_string_mask & (1U << string)) == 0U ||
        candidate.best_calibration_similarity < policy.minimum_similarity ||
        calibration_margin < policy.minimum_calibration_margin ||
        (candidate.playable_string_mask & (1U << string)) == 0U ||
        (candidate.calibrated_string_mask & (1U << string)) == 0U ||
        mask_member_count(detector.committed_unison_mask(midi_note)) >= 2U) {
      continue;
    }
    for (std::size_t voice_index = 0U;
         voice_index < snapshot.voice_count; ++voice_index) {
      const TunerVoice& incumbent = snapshot.voices[voice_index];
      if (incumbent.string_index != string ||
          incumbent.midi_note == midi_note ||
          incumbent.state == TunerVoiceState::coasting ||
          incumbent.shares_pitch_evidence() ||
          mask_member_count(
              detector.committed_unison_mask(incumbent.midi_note)) >= 2U) {
        continue;
      }
      const CandidateAdmissionDiagnostics incumbent_diagnostic =
          detector.candidate_admission_diagnostics(incumbent.midi_note);
      const double advantage = candidate.score_threshold_ratio -
                               incumbent_diagnostic.score_threshold_ratio;
      if (advantage < policy.minimum_score_margin ||
          (has_proposal[string] && advantage <= best_advantage[string])) {
        continue;
      }
      has_proposal[string] = true;
      best_advantage[string] = advantage;
      best_note[string] = midi_note;
    }
  }
  for (std::size_t voice_index = 0U;
       voice_index < projected.voice_count; ++voice_index) {
    TunerVoice& voice = projected.voices[voice_index];
    if (voice.string_index >= kMaxVoices ||
        !has_proposal[voice.string_index] ||
        voice.midi_note == best_note[voice.string_index]) {
      continue;
    }
    voice.midi_note = best_note[voice.string_index];
    voice.detected_midi_note = best_note[voice.string_index];
    voice.cents_valid = false;
    voice.detected_cents_valid = false;
    voice.pitch_evidence_group_id = kUnassignedPitchEvidenceGroup;
    voice.pitch_evidence_member_mask = 0U;
    ++changed_voices;
  }
  return projected;
}

TunerSnapshot adjacent_spectral_duplicate_projection(
    const TunerSnapshot& snapshot,
    const std::array<double, 128U>& single_source_error,
    const AdjacentSpectralDuplicatePolicy& policy,
    std::uint32_t& changed_voices) noexcept {
  TunerSnapshot projected = snapshot;
  std::array<bool, kMaxVoices> remove{};
  for (std::size_t left_index = 0U; left_index < snapshot.voice_count;
       ++left_index) {
    const TunerVoice& left = snapshot.voices[left_index];
    if (left.midi_note >= 127U || left.shares_pitch_evidence() ||
        mask_member_count(left.pitch_evidence_member_mask) >= 2U) {
      continue;
    }
    for (std::size_t right_index = left_index + 1U;
         right_index < snapshot.voice_count; ++right_index) {
      const TunerVoice& right = snapshot.voices[right_index];
      if (right.midi_note != left.midi_note + 1U ||
          right.shares_pitch_evidence() ||
          mask_member_count(right.pitch_evidence_member_mask) >= 2U ||
          left.string_index >= kMaxVoices ||
          right.string_index >= kMaxVoices ||
          left.string_index == right.string_index) {
        continue;
      }
      const double left_error = single_source_error[left.midi_note];
      const double right_error = single_source_error[right.midi_note];
      if (!std::isfinite(left_error) || !std::isfinite(right_error) ||
          std::abs(left_error - right_error) < policy.minimum_error_gap) {
        continue;
      }
      remove[left_error > right_error ? left_index : right_index] = true;
    }
  }
  std::size_t write_index = 0U;
  for (std::size_t read_index = 0U; read_index < projected.voice_count;
       ++read_index) {
    if (remove[read_index]) {
      ++changed_voices;
      continue;
    }
    projected.voices[write_index++] = projected.voices[read_index];
  }
  for (std::size_t index = write_index; index < projected.voice_count;
       ++index) {
    projected.voices[index] = {};
  }
  projected.voice_count = static_cast<std::uint8_t>(write_index);
  return projected;
}

TunerSnapshot fine_mask_complexity_projection(
    const TunerSnapshot& snapshot, const PolyphonicPitchDetector& detector,
    double member_penalty, std::uint8_t maximum_polyphony,
    std::uint32_t& changed_voices) noexcept {
  std::array<std::uint8_t, 128U> current_masks{};
  for (std::size_t voice_index = 0U; voice_index < snapshot.voice_count;
       ++voice_index) {
    const TunerVoice& voice = snapshot.voices[voice_index];
    if (voice.midi_note < current_masks.size() &&
        voice.string_index < kMaxVoices) {
      current_masks[voice.midi_note] = static_cast<std::uint8_t>(
          current_masks[voice.midi_note] | (1U << voice.string_index));
    }
  }
  std::array<std::uint8_t, 128U> projected_masks = current_masks;
  for (std::size_t note = 0U; note < current_masks.size(); ++note) {
    if (current_masks[note] == 0U ||
        note < kFineMaskComplexityMinimumMidiNote) {
      continue;
    }
    const auto midi_note = static_cast<std::uint8_t>(note);
    const CandidateAdmissionDiagnostics admission =
        detector.candidate_admission_diagnostics(midi_note);
    const SelectionDisposition disposition =
        detector.selection_disposition(midi_note);
    const FineFrequencyMaskResidualTable& residuals =
        detector.fine_frequency_mask_residuals(midi_note);
    const FineMaskComplexityEvidence evidence{
        admission.active,
        disposition == SelectionDisposition::selected,
        admission.direct_fundamental_peak,
        disposition == SelectionDisposition::quiet,
        admission.score_threshold_ratio,
        current_masks[note],
        admission.playable_string_mask,
        other_note_lane_mask(snapshot, midi_note)};
    projected_masks[note] = bounded_fine_mask_complexity_projection(
        evidence, residuals.normalized_residual, residuals.valid,
        member_penalty, maximum_polyphony);
  }

  TunerSnapshot projected = snapshot;
  std::size_t write_index = 0U;
  for (std::size_t read_index = 0U; read_index < snapshot.voice_count;
       ++read_index) {
    const TunerVoice& voice = snapshot.voices[read_index];
    const bool keep =
        voice.midi_note >= projected_masks.size() ||
        voice.string_index >= kMaxVoices ||
        (projected_masks[voice.midi_note] & (1U << voice.string_index)) != 0U;
    if (!keep) {
      ++changed_voices;
      continue;
    }
    projected.voices[write_index++] = voice;
  }
  for (std::size_t index = write_index; index < projected.voice_count;
       ++index) {
    projected.voices[index] = {};
  }
  projected.voice_count = static_cast<std::uint8_t>(write_index);
  return projected;
}

void accumulate_counterfactual_metrics(
    const TunerSnapshot& snapshot, std::uint64_t sample_index,
    const std::vector<ReplayLabel>& labels,
    ReplayCounterfactualMetrics& metrics) noexcept {
  bool any_active_label = false;
  for (const ReplayLabel& label : labels) {
    if (sample_index < label.start_sample || sample_index >= label.end_sample) {
      continue;
    }
    any_active_label = true;
    metrics.matched_label_frames += snapshot_matches_label(snapshot, label)
                                         ? 1U
                                         : 0U;
  }
  for (std::size_t voice_index = 0U;
       voice_index < snapshot.voice_count; ++voice_index) {
    const TunerVoice& voice = snapshot.voices[voice_index];
    bool expected = false;
    bool active_matching_note = false;
    for (const ReplayLabel& label : labels) {
      if (sample_index < label.start_sample ||
          sample_index >= label.end_sample) {
        continue;
      }
      expected = expected || voice_matches_label(voice, label);
      active_matching_note =
          active_matching_note || voice.midi_note == label.midi_note;
    }
    if (expected) {
      continue;
    }
    ++metrics.false_positive_voices;
    if (!any_active_label) {
      ++metrics.false_gap_voices;
    } else if (active_matching_note) {
      ++metrics.false_wrong_string_voices;
    } else {
      ++metrics.false_wrong_note_voices;
    }
  }
}
#endif

struct LabeledCalibrationEstimate final {
  double cents{};
  double correlation{};
  std::array<double, kCalibrationHarmonicCount> profile{};
  std::array<double, kCalibrationHarmonicCount> partial_detuning_cents{};
  std::uint8_t partial_detuning_valid_mask{};
};

bool estimate_labeled_calibration(const WaveData& wave,
                                  const ReplayLabel& label,
                                  double nominal_frequency,
                                  LabeledCalibrationEstimate& output) {
  output = {};
  if (!std::isfinite(nominal_frequency) || nominal_frequency <= 0.0 ||
      label.start_sample >= label.end_sample ||
      label.end_sample > wave.mono_samples.size()) {
    return false;
  }
  const std::size_t available = static_cast<std::size_t>(
      label.end_sample - label.start_sample);
  const std::size_t requested = static_cast<std::size_t>(
      (static_cast<std::uint64_t>(wave.sample_rate) *
       kLabeledAnalysisMilliseconds) /
      1000U);
  const std::size_t used = std::min(available, requested);
  if (used < 256U) {
    return false;
  }
  const std::size_t decimation = std::max<std::size_t>(
      1U, (static_cast<std::size_t>(wave.sample_rate) + 23999U) / 24000U);
  const std::size_t down_count = used / decimation;
  if (down_count < 128U) {
    return false;
  }
  std::vector<double> samples(down_count);
  const std::size_t source_start = static_cast<std::size_t>(label.start_sample);
  for (std::size_t index = 0U; index < down_count; ++index) {
    double sum = 0.0;
    for (std::size_t part = 0U; part < decimation; ++part) {
      const double value = wave.mono_samples[
          source_start + index * decimation + part];
      if (!std::isfinite(value)) {
        return false;
      }
      sum += value;
    }
    samples[index] = sum / static_cast<double>(decimation);
  }
  double mean = 0.0;
  for (const double sample : samples) {
    mean += sample;
  }
  mean /= static_cast<double>(samples.size());
  constexpr double kPi = 3.14159265358979323846;
  for (std::size_t index = 0U; index < samples.size(); ++index) {
    const double window = 0.5 -
                          0.5 * std::cos(2.0 * kPi *
                                         static_cast<double>(index) /
                                         static_cast<double>(samples.size() - 1U));
    samples[index] = (samples[index] - mean) * window;
  }
  const double down_rate =
      static_cast<double>(wave.sample_rate) / static_cast<double>(decimation);
  const double ratio = std::exp2(kMaximumLabeledCalibrationCents / 1200.0);
  const double nominal_lag = down_rate / nominal_frequency;
  // Keep one correlation sample outside each admitted cents boundary so a
  // peak next to that boundary can still be parabolically interpolated.
  const std::size_t minimum_lag = static_cast<std::size_t>(
      std::max(2.0, std::floor(nominal_lag / ratio) - 1.0));
  const std::size_t maximum_lag = static_cast<std::size_t>(
      std::min(static_cast<double>(samples.size() / 3U),
               std::ceil(nominal_lag * ratio) + 1.0));
  if (minimum_lag + 2U > maximum_lag) {
    return false;
  }
  std::vector<double> correlations(maximum_lag - minimum_lag + 1U);
  std::size_t best_lag = minimum_lag;
  double best = -1.0;
  for (std::size_t lag = minimum_lag; lag <= maximum_lag; ++lag) {
    double dot = 0.0;
    double left_energy = 0.0;
    double right_energy = 0.0;
    for (std::size_t index = 0U; index + lag < samples.size(); ++index) {
      const double left = samples[index];
      const double right = samples[index + lag];
      dot += left * right;
      left_energy += left * left;
      right_energy += right * right;
    }
    const double denominator = std::sqrt(left_energy * right_energy);
    const double correlation = denominator > 0.0 ? dot / denominator : 0.0;
    correlations[lag - minimum_lag] = correlation;
    if (correlation > best) {
      best = correlation;
      best_lag = lag;
    }
  }
  if (!std::isfinite(best) || best < kMinimumLabeledCorrelation) {
    return false;
  }
  double refined_lag = static_cast<double>(best_lag);
  if (best_lag > minimum_lag && best_lag < maximum_lag) {
    const double left = correlations[best_lag - minimum_lag - 1U];
    const double center = correlations[best_lag - minimum_lag];
    const double right = correlations[best_lag - minimum_lag + 1U];
    const double denominator = left - 2.0 * center + right;
    if (std::isfinite(denominator) && std::abs(denominator) > 1.0e-12) {
      refined_lag += 0.5 * (left - right) / denominator;
    }
  }
  const double autocorrelation_frequency = down_rate / refined_lag;
  constexpr double kRefinementStepCents = 0.1;
  constexpr int kRefinementRadiusSteps = 80;
  std::array<double, 2U * kRefinementRadiusSteps + 1U> spectral_scores{};
  const auto spectral_energy = [&samples, down_rate](double frequency) {
    const double angular = 2.0 * kPi * frequency / down_rate;
    const double cosine_step = std::cos(angular);
    const double sine_step = std::sin(angular);
    double cosine = 1.0;
    double sine = 0.0;
    double real = 0.0;
    double imaginary = 0.0;
    for (const double sample : samples) {
      real += sample * cosine;
      imaginary -= sample * sine;
      const double next_cosine = cosine * cosine_step - sine * sine_step;
      sine = sine * cosine_step + cosine * sine_step;
      cosine = next_cosine;
    }
    return real * real + imaginary * imaginary;
  };
  std::size_t best_refinement = 0U;
  for (int step = -kRefinementRadiusSteps;
       step <= kRefinementRadiusSteps; ++step) {
    const double frequency = autocorrelation_frequency *
                             std::exp2(kRefinementStepCents *
                                       static_cast<double>(step) / 1200.0);
    const std::size_t index =
        static_cast<std::size_t>(step + kRefinementRadiusSteps);
    spectral_scores[index] = spectral_energy(frequency);
    if (spectral_scores[index] > spectral_scores[best_refinement]) {
      best_refinement = index;
    }
  }
  double refined_step =
      static_cast<double>(best_refinement) - kRefinementRadiusSteps;
  if (best_refinement > 0U &&
      best_refinement + 1U < spectral_scores.size()) {
    const double left = spectral_scores[best_refinement - 1U];
    const double center = spectral_scores[best_refinement];
    const double right = spectral_scores[best_refinement + 1U];
    const double denominator = left - 2.0 * center + right;
    if (std::isfinite(denominator) && std::abs(denominator) > 1.0e-12) {
      refined_step += 0.5 * (left - right) / denominator;
    }
  }
  const double frequency = autocorrelation_frequency *
                           std::exp2(kRefinementStepCents * refined_step /
                                     1200.0);
  const double cents = 1200.0 * std::log2(frequency / nominal_frequency);
  if (!std::isfinite(cents) ||
      std::abs(cents) > kMaximumLabeledCalibrationCents) {
    return false;
  }
  constexpr double kPartialStepCents = 0.5;
  constexpr int kPartialMinimumStep = -20;
  constexpr int kPartialMaximumStep = 60;
  std::array<double, kCalibrationHarmonicCount> peak_steps{};
  std::array<double, kCalibrationHarmonicCount> partial_peak_energy{};
  double partial_peak_total = 0.0;
  for (std::size_t harmonic = 0U; harmonic < output.profile.size();
       ++harmonic) {
    const double exact_frequency =
        frequency * static_cast<double>(harmonic + 1U);
    output.profile[harmonic] = spectral_energy(exact_frequency);
    if (harmonic == 0U) {
      partial_peak_energy[harmonic] = output.profile[harmonic];
      peak_steps[harmonic] = 0.0;
    } else {
      constexpr std::size_t kPartialStepCount =
          static_cast<std::size_t>(kPartialMaximumStep -
                                   kPartialMinimumStep + 1);
      std::array<double, kPartialStepCount> scores{};
      std::size_t best_index = 0U;
      for (int step = kPartialMinimumStep; step <= kPartialMaximumStep;
           ++step) {
        const double partial_frequency =
            frequency * static_cast<double>(harmonic + 1U) *
            std::exp2(kPartialStepCents * static_cast<double>(step) / 1200.0);
        const std::size_t index =
            static_cast<std::size_t>(step - kPartialMinimumStep);
        scores[index] = spectral_energy(partial_frequency);
        if (scores[index] > scores[best_index]) {
          best_index = index;
        }
      }
      double refined = static_cast<double>(best_index + kPartialMinimumStep);
      if (best_index > 0U && best_index + 1U < scores.size()) {
        const double left = scores[best_index - 1U];
        const double center = scores[best_index];
        const double right = scores[best_index + 1U];
        const double denominator = left - 2.0 * center + right;
        if (std::isfinite(denominator) && std::abs(denominator) > 1.0e-12) {
          refined += 0.5 * (left - right) / denominator;
        }
      }
      partial_peak_energy[harmonic] = scores[best_index];
      peak_steps[harmonic] = refined;
    }
    partial_peak_total += partial_peak_energy[harmonic];
  }
  if (!std::isfinite(partial_peak_total) || partial_peak_total <= 0.0) {
    return false;
  }
  for (std::size_t harmonic = 0U; harmonic < output.profile.size();
       ++harmonic) {
    // Physical strings are mildly inharmonic. Preserve the energy at the
    // measured partial peak instead of attenuating the fingerprint by
    // sampling only the ideal integer multiple of the fundamental.
    output.profile[harmonic] =
        partial_peak_energy[harmonic] / partial_peak_total;
    const bool resolved = harmonic == 0U ||
                          (peak_steps[harmonic] > kPartialMinimumStep &&
                           peak_steps[harmonic] < kPartialMaximumStep &&
                           partial_peak_total > 0.0 &&
                           partial_peak_energy[harmonic] /
                                   partial_peak_total >=
                               0.001);
    if (resolved) {
      output.partial_detuning_cents[harmonic] =
          kPartialStepCents * peak_steps[harmonic];
      output.partial_detuning_valid_mask = static_cast<std::uint8_t>(
          output.partial_detuning_valid_mask | (1U << harmonic));
    }
  }
  output.cents = cents;
  output.correlation = best;
  return true;
}

}  // namespace

TunerSnapshot correlation_shadow_projection(
    const TunerSnapshot& snapshot, const std::array<double, 128U>& ratios,
    double sample_rate, const CorrelationShadowPolicy& policy,
    std::uint32_t& changed_voices,
    const std::array<bool, 128U>* pending_unison) noexcept {
  TunerSnapshot projected = snapshot;
  if (snapshot.state != TunerFrameState::tracking ||
      !std::isfinite(sample_rate) || sample_rate <= 0.0 ||
      !std::isfinite(policy.maximum_energy_ratio) ||
      policy.maximum_energy_ratio <= 0.0 ||
      !std::isfinite(policy.minimum_age_seconds) ||
      policy.minimum_age_seconds < 0.0) {
    return projected;
  }
  std::array<std::uint8_t, 128U> pitch_members{};
  for (std::size_t index = 0U; index < snapshot.voice_count; ++index) {
    const auto note = snapshot.voices[index].detected_midi_note;
    if (note < pitch_members.size()) {
      ++pitch_members[note];
    }
  }
  std::size_t write = 0U;
  for (std::size_t index = 0U; index < snapshot.voice_count; ++index) {
    const auto& voice = snapshot.voices[index];
    const std::size_t note = voice.detected_midi_note;
    const double age = static_cast<double>(voice.age_ticks) *
                       static_cast<double>(kDecisionQuantum) / sample_rate;
    const bool remove =
        voice.state == TunerVoiceState::tracking &&
        voice.string_index < kMaxVoices &&
        !voice.shares_pitch_evidence() &&
        voice.detected_midi_note == voice.midi_note &&
        note < ratios.size() && pitch_members[note] == 1U &&
        !(policy.protect_pending_unison && pending_unison != nullptr &&
          (*pending_unison)[note]) &&
        age >= policy.minimum_age_seconds &&
        std::isfinite(ratios[note]) && ratios[note] >= 0.0 &&
        ratios[note] < policy.maximum_energy_ratio;
    if (remove) {
      ++changed_voices;
    } else {
      projected.voices[write++] = voice;
    }
  }
  for (std::size_t index = write; index < projected.voice_count; ++index) {
    projected.voices[index] = {};
  }
  projected.voice_count = static_cast<std::uint8_t>(write);
  return projected;
}

void observe_adjacent_envelope_coherence(
    AdjacentEnvelopeCoherenceState& state, double left, double right,
    double smoothing) noexcept {
  if (!std::isfinite(left) || !std::isfinite(right) ||
      !std::isfinite(smoothing) || smoothing <= 0.0 || smoothing > 1.0) {
    return;
  }
  if (state.observations == 0U) {
    state.mean_left = left;
    state.mean_right = right;
    state.observations = 1U;
    return;
  }
  const double left_delta = left - state.mean_left;
  const double right_delta = right - state.mean_right;
  state.mean_left += smoothing * left_delta;
  state.mean_right += smoothing * right_delta;
  state.variance_left =
      (1.0 - smoothing) *
      (state.variance_left + smoothing * left_delta * left_delta);
  state.variance_right =
      (1.0 - smoothing) *
      (state.variance_right + smoothing * right_delta * right_delta);
  state.covariance =
      (1.0 - smoothing) *
      (state.covariance + smoothing * left_delta * right_delta);
  if (state.observations < std::numeric_limits<std::uint32_t>::max()) {
    ++state.observations;
  }
}

double adjacent_envelope_coherence(
    const AdjacentEnvelopeCoherenceState& state) noexcept {
  if (state.observations < 20U || state.variance_left <= 1.0e-12 ||
      state.variance_right <= 1.0e-12) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double denominator =
      std::sqrt(state.variance_left * state.variance_right);
  if (!std::isfinite(denominator) || denominator <= 1.0e-12) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return std::clamp(state.covariance / denominator, -1.0, 1.0);
}

std::size_t adjacent_envelope_coherence_bin(
    const AdjacentEnvelopeCoherenceState& state) noexcept {
  const double coherence = adjacent_envelope_coherence(state);
  if (!std::isfinite(coherence)) {
    return 0U;
  }
  return 1U + static_cast<std::size_t>(
                  std::min(20.0, std::floor((coherence + 1.0) * 10.0)));
}

std::size_t adjacent_spectral_error_gap_bin(double error_gap) noexcept {
  if (!std::isfinite(error_gap)) {
    return 0U;
  }
  return 1U + static_cast<std::size_t>(
                  std::min(40.0, std::floor(
                                     (std::clamp(error_gap, -1.0, 1.0) +
                                      1.0) *
                                     20.0)));
}

CandidateSpectralPartitionCell candidate_spectral_partition_cell(
    std::size_t policy, std::size_t gate, std::uint8_t member_mask,
    bool target_active, std::uint8_t expected_mask,
    bool note_only) noexcept {
  CandidateSpectralPartitionCell cell;
  if (policy >= kCandidateSpectralShadowPolicyCount ||
      gate >= kCandidateSpectralShadowGateCount || member_mask == 0U ||
      (member_mask & static_cast<std::uint8_t>(member_mask - 1U)) != 0U) {
    return cell;
  }

  std::size_t string = 0U;
  while ((member_mask & (1U << string)) == 0U) {
    ++string;
  }
  if (string >= kMaxVoices) {
    return cell;
  }

  cell.row = policy * kCandidateSpectralShadowGateCount + gate;
  cell.string = string;
  if (!target_active) {
    cell.classification = CandidateSpectralPartitionClass::other_false;
  } else if (note_only || (expected_mask & member_mask) != 0U) {
    cell.classification = CandidateSpectralPartitionClass::target_correct;
  } else {
    cell.classification =
        CandidateSpectralPartitionClass::target_wrong_string;
  }
  cell.valid = true;
  return cell;
}

std::size_t false_wrong_note_age_bucket(
    std::uint64_t sample_index, std::uint64_t latest_active_start_sample,
    std::uint32_t sample_rate) noexcept {
  if (sample_rate == 0U || sample_index < latest_active_start_sample) {
    return kFalseWrongNoteAgeBucketCount;
  }
  const std::uint64_t age = sample_index - latest_active_start_sample;
  std::size_t bucket = 0U;
  for (const std::uint32_t milliseconds :
       kFalseWrongNoteAgeThresholdMilliseconds) {
    const std::uint64_t threshold =
        (static_cast<std::uint64_t>(sample_rate) * milliseconds + 999U) /
        1000U;
    if (age < threshold) {
      break;
    }
    ++bucket;
  }
  return bucket;
}

std::size_t false_wrong_note_cents_bucket(std::int16_t cents_q8,
                                          bool cents_valid) noexcept {
  if (!cents_valid) {
    return kFalseWrongNoteCentsBucketCount - 1U;
  }
  constexpr std::int32_t kMinimumQ8 = -50 * 256;
  constexpr std::int32_t kMaximumQ8 = 50 * 256;
  constexpr std::int32_t kStepQ8 = 5 * 256;
  const std::int32_t bounded =
      std::clamp(static_cast<std::int32_t>(cents_q8), kMinimumQ8,
                 kMaximumQ8);
  return static_cast<std::size_t>(
      std::min<std::int32_t>(20, (bounded - kMinimumQ8) / kStepQ8));
}

CalibratedPitchRebinResult calibrated_pitch_rebin(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret,
    double minimum_error_improvement_cents) noexcept {
  const CalibratedNoteProjection projection = project_calibrated_note(
      note, cents_q8, cents_valid, string_index, bank, maximum_fret,
      minimum_error_improvement_cents);
  double projected_error_cents = 0.0;
  if (projection.changed && string_index < kM3OpenNotes.size() &&
      projection.note >= kM3OpenNotes[string_index]) {
    const std::size_t projected_fret =
        projection.note - kM3OpenNotes[string_index];
    const StringCalibrationPoint* point =
        bank.point(string_index, projected_fret);
    if (point != nullptr &&
        point->quality != CalibrationPointQuality::missing) {
      const double observed =
          100.0 * static_cast<double>(note) +
          static_cast<double>(cents_q8) / 256.0;
      const double center =
          100.0 * static_cast<double>(projection.note) +
          static_cast<double>(point->cents_offset_q8) / 256.0;
      projected_error_cents = std::abs(observed - center);
    }
  }
  return {projection.note, projection.fret_delta,
          projection.error_improvement_cents, projected_error_cents,
          projection.changed};
}

bool calibrated_pitch_rebin_projected_error_eligible(
    const CalibratedPitchRebinResult& projection,
    double maximum_projected_error_cents) noexcept {
  return projection.changed &&
         std::isfinite(maximum_projected_error_cents) &&
         maximum_projected_error_cents >= 0.0 &&
         std::isfinite(projection.projected_error_cents) &&
         projection.projected_error_cents <= maximum_projected_error_cents;
}

bool calibrated_pitch_rebin_context_eligible(
    std::size_t pitch_group_members, std::size_t label_age_bucket,
    std::size_t snapshot_distinct_note_count) noexcept {
  return pitch_group_members <= 1U && label_age_bucket >= 1U &&
         label_age_bucket < kFalseWrongNoteAgeBucketCount &&
         snapshot_distinct_note_count >= 2U;
}

MultiPartialPhaseCentsResult robust_multi_partial_phase_cents(
    const PartialAbsoluteCentsEvidence& evidence,
    const StringCalibrationPoint& calibration,
    std::uint8_t minimum_partials,
    double maximum_deviation_cents) noexcept {
  MultiPartialPhaseCentsResult result{};
  if (minimum_partials < 2U ||
      minimum_partials >= kPartialDetuningCount ||
      !std::isfinite(maximum_deviation_cents) ||
      maximum_deviation_cents < 0.0 ||
      (evidence.valid_mask & 0xC0U) != 0U ||
      (calibration.partial_detuning_valid_mask & 0xC0U) != 0U) {
    return result;
  }
  std::array<double, kPartialDetuningCount - 1U> corrected{};
  std::size_t count = 0U;
  for (std::size_t partial = 1U; partial < kPartialDetuningCount; ++partial) {
    const std::uint8_t bit = static_cast<std::uint8_t>(1U << partial);
    if ((evidence.valid_mask & calibration.partial_detuning_valid_mask &
         bit) == 0U ||
        !std::isfinite(evidence.cents[partial])) {
      continue;
    }
    const double residual =
        static_cast<double>(calibration.partial_detuning_q8[partial]) /
        256.0;
    const double value = evidence.cents[partial] - residual;
    if (std::isfinite(value)) {
      corrected[count++] = value;
    }
  }
  if (count < minimum_partials) {
    return result;
  }
  // The collection is bounded to five upper partials.  A tiny insertion sort
  // is clearer here and avoids the generic introsort implementation's
  // deliberately wider sentinel accesses confusing aggressive bounds checks.
  for (std::size_t index = 1U; index < count; ++index) {
    const double value = corrected[index];
    std::size_t insertion = index;
    while (insertion > 0U && corrected[insertion - 1U] > value) {
      corrected[insertion] = corrected[insertion - 1U];
      --insertion;
    }
    corrected[insertion] = value;
  }
  const double median = count % 2U != 0U
                            ? corrected[count / 2U]
                            : 0.5 * (corrected[count / 2U - 1U] +
                                     corrected[count / 2U]);
  double maximum_deviation = 0.0;
  for (std::size_t index = 0U; index < count; ++index) {
    maximum_deviation =
        std::max(maximum_deviation, std::abs(corrected[index] - median));
  }
  result.cents = median;
  result.maximum_deviation_cents = maximum_deviation;
  result.partial_count = static_cast<std::uint8_t>(count);
  result.valid = maximum_deviation <= maximum_deviation_cents;
  return result;
}

CalibratedAdjacentProjectionDisposition
classify_calibrated_adjacent_projection(
    std::uint8_t note, std::int16_t cents_q8, bool cents_valid,
    std::uint8_t string_index, const StringCalibrationBank& bank,
    std::uint8_t maximum_fret, int expected_direction,
    double minimum_error_improvement_cents) noexcept {
  if (!cents_valid || string_index >= kM3OpenNotes.size() ||
      !bank.string_calibrated(string_index) ||
      (expected_direction != -1 && expected_direction != 1) ||
      !std::isfinite(minimum_error_improvement_cents) ||
      minimum_error_improvement_cents < 0.0 ||
      note < kM3OpenNotes[string_index]) {
    return CalibratedAdjacentProjectionDisposition::invalid_input;
  }
  const int fret = static_cast<int>(note - kM3OpenNotes[string_index]);
  if (fret < 0 || fret >= static_cast<int>(kCalibrationFretCount) ||
      fret > static_cast<int>(maximum_fret)) {
    return CalibratedAdjacentProjectionDisposition::invalid_input;
  }
  const StringCalibrationPoint* current =
      bank.point(string_index, static_cast<std::size_t>(fret));
  if (current == nullptr ||
      current->quality == CalibrationPointQuality::missing) {
    return CalibratedAdjacentProjectionDisposition::current_point_unavailable;
  }
  const int adjacent_note = static_cast<int>(note) + expected_direction;
  const int adjacent_fret = fret + expected_direction;
  if (adjacent_note < 0 || adjacent_note > 127 || adjacent_fret < 0 ||
      adjacent_fret >= static_cast<int>(kCalibrationFretCount) ||
      adjacent_fret > static_cast<int>(maximum_fret)) {
    return CalibratedAdjacentProjectionDisposition::
        expected_adjacent_point_unavailable;
  }
  const StringCalibrationPoint* adjacent =
      bank.point(string_index, static_cast<std::size_t>(adjacent_fret));
  if (adjacent == nullptr ||
      adjacent->quality == CalibrationPointQuality::missing) {
    return CalibratedAdjacentProjectionDisposition::
        expected_adjacent_point_unavailable;
  }
  const double observed =
      100.0 * static_cast<double>(note) +
      static_cast<double>(cents_q8) / 256.0;
  const double current_center =
      100.0 * static_cast<double>(note) +
      static_cast<double>(current->cents_offset_q8) / 256.0;
  const double adjacent_center =
      100.0 * static_cast<double>(adjacent_note) +
      static_cast<double>(adjacent->cents_offset_q8) / 256.0;
  const double current_error = std::abs(observed - current_center);
  const double adjacent_error = std::abs(observed - adjacent_center);
  if (adjacent_error + 1.0e-9 >= current_error) {
    return CalibratedAdjacentProjectionDisposition::
        expected_adjacent_not_better;
  }
  if (current_error - adjacent_error + 1.0e-9 <
      minimum_error_improvement_cents) {
    return CalibratedAdjacentProjectionDisposition::
        improvement_below_threshold;
  }
  return CalibratedAdjacentProjectionDisposition::available;
}

AdjacentWrongNoteProjectionDisposition
classify_adjacent_wrong_note_projection(
    const AdjacentWrongNoteProjectionContext& context) noexcept {
  if (!context.tracking) {
    return AdjacentWrongNoteProjectionDisposition::non_tracking;
  }
  if (!context.polyphonic_context) {
    return AdjacentWrongNoteProjectionDisposition::
        insufficient_polyphonic_context;
  }
  if (!context.old_enough) {
    return AdjacentWrongNoteProjectionDisposition::too_young;
  }
  if (!context.single_member) {
    return AdjacentWrongNoteProjectionDisposition::multi_member;
  }
  if (!context.cents_available) {
    return AdjacentWrongNoteProjectionDisposition::cents_unavailable;
  }
  if (!context.projection_available) {
    return AdjacentWrongNoteProjectionDisposition::projection_unavailable;
  }
  if (!context.projected_center_inside_guard) {
    return AdjacentWrongNoteProjectionDisposition::
        outside_projected_center_guard;
  }
  if (context.collision) {
    return AdjacentWrongNoteProjectionDisposition::collision;
  }
  return AdjacentWrongNoteProjectionDisposition::eligible_unapplied;
}

AdjacentWrongNoteExpectedPresence
classify_adjacent_wrong_note_expected_presence(
    const TunerSnapshot& snapshot, std::uint8_t expected_note,
    std::uint8_t observed_string) noexcept {
  bool same_string = false;
  bool other_string = false;
  const std::size_t count = std::min<std::size_t>(
      snapshot.voice_count, snapshot.voices.size());
  for (std::size_t voice = 0U; voice < count; ++voice) {
    if (snapshot.voices[voice].midi_note != expected_note) {
      continue;
    }
    if (snapshot.voices[voice].string_index == observed_string) {
      same_string = true;
    } else {
      other_string = true;
    }
  }
  if (same_string && other_string) {
    return AdjacentWrongNoteExpectedPresence::same_and_other_string;
  }
  if (same_string) {
    return AdjacentWrongNoteExpectedPresence::same_string;
  }
  if (other_string) {
    return AdjacentWrongNoteExpectedPresence::other_string;
  }
  return AdjacentWrongNoteExpectedPresence::absent;
}

bool CalibratedPitchRebinLatch::observe(
    bool eligible, std::uint8_t target_note,
    std::uint16_t required_frames) noexcept {
  if (!eligible || target_note >= 128U || required_frames == 0U) {
    reset();
    return false;
  }
  if (target_note_ != target_note) {
    target_note_ = target_note;
    consecutive_frames_ = 1U;
  } else if (consecutive_frames_ <
             std::numeric_limits<std::uint16_t>::max()) {
    ++consecutive_frames_;
  }
  return consecutive_frames_ >= required_frames;
}

void CalibratedPitchRebinLatch::reset() noexcept {
  target_note_ = 128U;
  consecutive_frames_ = 0U;
}

ReplayTargetLaneOutcome classify_target_lane_outcome(
    std::uint8_t observed_mask, std::uint8_t expected_mask) noexcept {
  if (observed_mask == 0U) {
    return ReplayTargetLaneOutcome::absent;
  }
  if (expected_mask == 0U || observed_mask == expected_mask) {
    return ReplayTargetLaneOutcome::exact;
  }
  const std::uint8_t unexpected = static_cast<std::uint8_t>(
      observed_mask & static_cast<std::uint8_t>(~expected_mask));
  const std::uint8_t missing = static_cast<std::uint8_t>(
      expected_mask & static_cast<std::uint8_t>(~observed_mask));
  if (unexpected == 0U) {
    return ReplayTargetLaneOutcome::subset_missing;
  }
  if (missing == 0U) {
    return ReplayTargetLaneOutcome::superset_extra;
  }
  if ((observed_mask & expected_mask) != 0U) {
    return ReplayTargetLaneOutcome::overlap_mixed;
  }
  return ReplayTargetLaneOutcome::disjoint_wrong;
}

std::uint8_t bounded_fine_residual_expansion(
    const FineResidualExpansionEvidence& evidence,
    double minimum_score_threshold_ratio, double minimum_improvement,
    std::uint8_t maximum_polyphony) noexcept {
  if (!evidence.active || !evidence.selected ||
      !evidence.direct_fundamental ||
      !std::isfinite(evidence.score_threshold_ratio) ||
      !std::isfinite(minimum_score_threshold_ratio) ||
      minimum_score_threshold_ratio < 0.0 ||
      evidence.score_threshold_ratio < minimum_score_threshold_ratio ||
      !std::isfinite(evidence.residual_improvement) ||
      !std::isfinite(minimum_improvement) || minimum_improvement < 0.0 ||
      evidence.residual_improvement < minimum_improvement ||
      !evidence.residual_rejected ||
      maximum_polyphony == 0U || maximum_polyphony > kMaxVoices) {
    return 0U;
  }
  const std::uint8_t committed_members =
      mask_member_count(evidence.committed_mask);
  const std::uint8_t fit_members = mask_member_count(evidence.fit_mask);
  if (committed_members == 0U || fit_members <= committed_members ||
      fit_members < 2U || fit_members > 4U ||
      fit_members > maximum_polyphony ||
      (evidence.fit_mask & evidence.committed_mask) !=
          evidence.committed_mask ||
      // This counterfactual is intentionally narrower than the ordinary
      // fine-frequency fit.  Completing an arbitrary playable subset made a
      // short upper unison gain members on the wrong strings.  Only test the
      // special case where the fitted physical mixture accounts for every
      // fret-feasible string at the pitch; the long low triple is such a
      // closed three-string system, while the ambiguous upper cases are not.
      evidence.fit_mask != evidence.playable_mask ||
      (evidence.fit_mask & evidence.other_owned_mask) != 0U ||
      mask_member_count(static_cast<std::uint8_t>(
          evidence.fit_mask | evidence.other_owned_mask)) >
          maximum_polyphony) {
    return 0U;
  }
  return evidence.fit_mask;
}

ReplayGroupMaskRelation classify_group_mask_relation(
    std::uint8_t observed_mask, std::uint8_t expected_mask,
    bool note_only) noexcept {
  if (observed_mask == 0U) {
    return ReplayGroupMaskRelation::absent;
  }
  if (note_only) {
    return ReplayGroupMaskRelation::exact;
  }
  if (observed_mask == expected_mask) {
    return ReplayGroupMaskRelation::exact;
  }
  if (expected_mask != 0U &&
      (observed_mask & static_cast<std::uint8_t>(~expected_mask)) == 0U) {
    return ReplayGroupMaskRelation::subset;
  }
  return ReplayGroupMaskRelation::other;
}

ReplayClassifierMaskRelation classify_classifier_mask_relation(
    const UnisonSpectralClassification& classification,
    std::uint8_t expected_mask, bool note_only) noexcept {
  const std::uint8_t members = mask_member_count(classification.member_mask);
  if (!classification.valid || classification.member_count != members ||
      members < 2U || members > 4U) {
    return ReplayClassifierMaskRelation::invalid;
  }
  if (note_only || classification.member_mask == expected_mask) {
    return ReplayClassifierMaskRelation::exact;
  }
  if (expected_mask != 0U &&
      (classification.member_mask &
       static_cast<std::uint8_t>(~expected_mask)) == 0U) {
    return ReplayClassifierMaskRelation::subset;
  }
  return ReplayClassifierMaskRelation::other;
}

ReplayObservedFingerprintChangedFrameDiagnostic
diagnose_observed_fingerprint_changed_frame(
    std::uint8_t committed_mask, std::uint8_t expected_mask,
    std::uint8_t snapshot_voice_count,
    std::uint8_t other_owned_mask) noexcept {
  ReplayObservedFingerprintChangedFrameDiagnostic diagnostic;
  diagnostic.committed_relation =
      classify_group_mask_relation(committed_mask, expected_mask);
  diagnostic.committed_member_count = static_cast<std::uint8_t>(
      std::min<std::size_t>(mask_member_count(committed_mask), kMaxVoices));
  diagnostic.snapshot_voice_count = static_cast<std::uint8_t>(
      std::min<std::size_t>(snapshot_voice_count, kMaxVoices));
  diagnostic.other_owned_lane_count = static_cast<std::uint8_t>(
      std::min<std::size_t>(mask_member_count(other_owned_mask), kMaxVoices));
  return diagnostic;
}

std::size_t physical_group_causal_cell_index(
    std::size_t selection_disposition, ReplayGroupMaskRelation fine_relation,
    ReplayGroupMaskRelation committed_relation,
    ReplayTargetLaneOutcome lane_outcome) noexcept {
  constexpr std::size_t kRelationCount =
      static_cast<std::size_t>(ReplayGroupMaskRelation::count);
  constexpr std::size_t kLaneOutcomeCount =
      static_cast<std::size_t>(ReplayTargetLaneOutcome::count);
  return (((selection_disposition * kRelationCount) +
           static_cast<std::size_t>(fine_relation)) *
              kRelationCount +
          static_cast<std::size_t>(committed_relation)) *
             kLaneOutcomeCount +
         static_cast<std::size_t>(lane_outcome);
}

std::size_t physical_group_fine_unresolved_cell_index(
    std::size_t selection_disposition, std::size_t unresolved_reason,
    ReplayTargetLaneOutcome lane_outcome) noexcept {
  constexpr std::size_t kLaneOutcomeCount =
      static_cast<std::size_t>(ReplayTargetLaneOutcome::count);
  return ((selection_disposition * kFineFrequencyUnresolvedReasonCount) +
          unresolved_reason) *
             kLaneOutcomeCount +
         static_cast<std::size_t>(lane_outcome);
}

std::size_t physical_group_fine_classifier_cell_index(
    ReplayGroupMaskRelation fine_relation,
    ReplayClassifierMaskRelation classifier_relation,
    ReplayTargetLaneOutcome lane_outcome) noexcept {
  constexpr std::size_t kClassifierRelationCount =
      static_cast<std::size_t>(ReplayClassifierMaskRelation::count);
  constexpr std::size_t kLaneOutcomeCount =
      static_cast<std::size_t>(ReplayTargetLaneOutcome::count);
  return ((static_cast<std::size_t>(fine_relation) *
           kClassifierRelationCount) +
          static_cast<std::size_t>(classifier_relation)) *
             kLaneOutcomeCount +
         static_cast<std::size_t>(lane_outcome);
}

ReplayPairwiseBeatSupport summarize_pairwise_beat_support(
    std::uint8_t member_mask,
    const std::array<double, 1U << kMaxVoices>& coherence_by_pair,
    double gate) noexcept {
  ReplayPairwiseBeatSupport result;
  if (!std::isfinite(gate) || gate < 0.0) {
    return result;
  }

  std::array<std::uint8_t, kMaxVoices> adjacency{};
  for (std::size_t left = 0U; left < kMaxVoices; ++left) {
    const std::uint8_t left_bit = static_cast<std::uint8_t>(1U << left);
    if ((member_mask & left_bit) == 0U) {
      continue;
    }
    for (std::size_t right = left + 1U; right < kMaxVoices; ++right) {
      const std::uint8_t right_bit = static_cast<std::uint8_t>(1U << right);
      if ((member_mask & right_bit) == 0U) {
        continue;
      }
      ++result.pair_count;
      const std::uint8_t pair_mask =
          static_cast<std::uint8_t>(left_bit | right_bit);
      const double coherence = coherence_by_pair[pair_mask];
      if (!std::isfinite(coherence) || coherence < gate) {
        continue;
      }
      ++result.above_gate_count;
      adjacency[left] = static_cast<std::uint8_t>(adjacency[left] | right_bit);
      adjacency[right] = static_cast<std::uint8_t>(adjacency[right] | left_bit);
    }
  }
  if (result.pair_count == 0U) {
    return result;
  }

  const std::uint8_t first = static_cast<std::uint8_t>(
      member_mask & static_cast<std::uint8_t>(0U - member_mask));
  std::uint8_t reached = first;
  for (std::size_t pass = 0U; pass < kMaxVoices; ++pass) {
    std::uint8_t expanded = reached;
    for (std::size_t string = 0U; string < kMaxVoices; ++string) {
      if ((reached & (1U << string)) != 0U) {
        expanded = static_cast<std::uint8_t>(expanded | adjacency[string]);
      }
    }
    if (expanded == reached) {
      break;
    }
    reached = expanded;
  }
  result.connected =
      static_cast<std::uint8_t>(reached & member_mask) == member_mask;
  return result;
}

std::uint8_t spectral_head_vote_mask(
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& heads) noexcept {
  std::uint8_t result = 0U;
  for (const std::uint8_t string : heads) {
    if (string < kMaxVoices) {
      result = static_cast<std::uint8_t>(result | (1U << string));
    }
  }
  return result;
}

SpectralHeadPlurality spectral_head_plurality(
    const std::array<std::uint8_t, kSpectralTierCount + 1U>& heads,
    const std::array<double, kSpectralTierCount + 1U>& margins,
    double minimum_margin) noexcept {
  SpectralHeadPlurality result;
  if (!std::isfinite(minimum_margin) || minimum_margin < 0.0) {
    return result;
  }
  std::array<std::uint8_t, kMaxVoices> votes{};
  std::array<double, kMaxVoices> margin_sums{};
  for (std::size_t head = 0U; head < heads.size(); ++head) {
    const std::uint8_t string = heads[head];
    if (string >= kMaxVoices || !std::isfinite(margins[head]) ||
        margins[head] < minimum_margin) {
      continue;
    }
    ++votes[string];
    margin_sums[string] += margins[head];
  }
  bool tied = false;
  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
    if (votes[string] == 0U) {
      continue;
    }
    if (votes[string] > result.votes ||
        (votes[string] == result.votes &&
         margin_sums[string] > result.margin_sum)) {
      result.string = static_cast<std::uint8_t>(string);
      result.votes = votes[string];
      result.margin_sum = margin_sums[string];
      tied = false;
    } else if (votes[string] == result.votes &&
               margin_sums[string] == result.margin_sum) {
      tied = true;
    }
  }
  if (tied) {
    result.string = kUnassignedTunerString;
  }
  return result;
}

bool decode_wave_bytes(const std::uint8_t* bytes, std::size_t size,
                       WaveData& output, ReplayError& error) {
  output = {};
  error = ReplayError::invalid_wave;
  if (bytes == nullptr || size < 12U || !fourcc(bytes, "RIFF") ||
      !fourcc(bytes + 8U, "WAVE")) {
    return false;
  }
  const std::uint64_t riff_size = read_u32(bytes + 4U);
  if (riff_size + 8U != size) {
    return false;
  }

  bool have_format = false;
  bool have_data = false;
  std::uint16_t format = 0U;
  std::uint16_t channels = 0U;
  std::uint32_t sample_rate = 0U;
  std::uint16_t block_align = 0U;
  std::uint16_t bits_per_sample = 0U;
  const std::uint8_t* data = nullptr;
  std::size_t data_size = 0U;
  std::size_t offset = 12U;
  while (offset < size) {
    if (size - offset < 8U) {
      return false;
    }
    const std::uint8_t* chunk = bytes + offset;
    const std::size_t chunk_size = read_u32(chunk + 4U);
    offset += 8U;
    if (chunk_size > size - offset) {
      return false;
    }
    if (fourcc(chunk, "fmt ")) {
      if (have_format || chunk_size < 16U) {
        return false;
      }
      have_format = true;
      format = read_u16(bytes + offset);
      channels = read_u16(bytes + offset + 2U);
      sample_rate = read_u32(bytes + offset + 4U);
      block_align = read_u16(bytes + offset + 12U);
      bits_per_sample = read_u16(bytes + offset + 14U);
    } else if (fourcc(chunk, "data")) {
      if (have_data) {
        return false;
      }
      have_data = true;
      data = bytes + offset;
      data_size = chunk_size;
    }
    offset += chunk_size;
    if ((chunk_size & 1U) != 0U) {
      if (offset >= size) {
        return false;
      }
      ++offset;
    }
  }
  if (!have_format || !have_data || data == nullptr || offset != size ||
      (channels != 1U && channels != 2U) || sample_rate < 8000U ||
      sample_rate > 384000U) {
    return false;
  }

  const bool integer_format = format == 1U &&
                              (bits_per_sample == 16U ||
                               bits_per_sample == 24U ||
                               bits_per_sample == 32U);
  const bool float_format = format == 3U && bits_per_sample == 32U;
  if (!integer_format && !float_format) {
    error = ReplayError::unsupported_wave;
    return false;
  }
  const std::size_t bytes_per_sample = bits_per_sample / 8U;
  const std::size_t expected_align =
      static_cast<std::size_t>(channels) * bytes_per_sample;
  if (block_align != expected_align || block_align == 0U ||
      data_size % block_align != 0U) {
    return false;
  }
  const std::size_t frame_count = data_size / block_align;
  output.sample_rate = sample_rate;
  output.source_channels = channels;
  output.mono_samples.resize(frame_count);
  for (std::size_t frame = 0U; frame < frame_count; ++frame) {
    double sum = 0.0;
    for (std::size_t channel = 0U; channel < channels; ++channel) {
      const std::uint8_t* sample =
          data + frame * block_align + channel * bytes_per_sample;
      double value = 0.0;
      if (format == 3U) {
        const std::uint32_t bits = read_u32(sample);
        float decoded = 0.0F;
        std::memcpy(&decoded, &bits, sizeof(decoded));
        if (!std::isfinite(decoded)) {
          output = {};
          error = ReplayError::nonfinite_audio;
          return false;
        }
        value = static_cast<double>(decoded);
      } else if (bits_per_sample == 16U) {
        value = static_cast<double>(
                    static_cast<std::int16_t>(read_u16(sample))) /
                32768.0;
      } else if (bits_per_sample == 24U) {
        std::int32_t decoded =
            static_cast<std::int32_t>(sample[0]) |
            (static_cast<std::int32_t>(sample[1]) << 8U) |
            (static_cast<std::int32_t>(sample[2]) << 16U);
        if ((decoded & 0x00800000) != 0) {
          decoded |= static_cast<std::int32_t>(0xFF000000U);
        }
        value = static_cast<double>(decoded) / 8388608.0;
      } else {
        const std::uint32_t raw = read_u32(sample);
        std::int32_t decoded = 0;
        std::memcpy(&decoded, &raw, sizeof(decoded));
        value = static_cast<double>(decoded) / 2147483648.0;
      }
      sum += value;
    }
    output.mono_samples[frame] =
        std::clamp(sum / static_cast<double>(channels), -1.0, 1.0);
  }
  error = ReplayError::none;
  return true;
}

bool parse_replay_labels(const char* text, std::size_t size,
                         std::uint64_t sample_count,
                         std::vector<ReplayLabel>& output,
                         ReplayError& error) {
  output.clear();
  error = ReplayError::invalid_labels;
  if (text == nullptr && size != 0U) {
    return false;
  }
  const std::string_view input{text == nullptr ? "" : text, size};
  std::size_t position = 0U;
  bool header_seen = false;
  bool calibration_pass_column = false;
  bool expected_cents_column = false;
  std::uint64_t prior_start = 0U;
  while (position < input.size()) {
    const std::size_t newline = input.find('\n', position);
    const std::size_t end =
        newline == std::string_view::npos ? input.size() : newline;
    std::string_view line = input.substr(position, end - position);
    if (!line.empty() && line.back() == '\r') {
      line.remove_suffix(1U);
    }
    position = newline == std::string_view::npos ? input.size() : newline + 1U;
    if (line.empty() || line.front() == '#') {
      continue;
    }
    constexpr std::string_view kHeader =
        "start_sample\tend_sample\tmidi_note\tstring_mask";
    constexpr std::string_view kPassHeader =
        "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass";
    constexpr std::string_view kExpectedCentsHeader =
        "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\t"
        "expected_cents";
    if (!header_seen &&
        (line == kHeader || line == kPassHeader ||
         line == kExpectedCentsHeader)) {
      calibration_pass_column = line != kHeader;
      expected_cents_column = line == kExpectedCentsHeader;
      header_seen = true;
      continue;
    }
    header_seen = true;
    std::array<std::string_view, 6U> fields{};
    const std::size_t field_count = expected_cents_column
                                        ? 6U
                                        : (calibration_pass_column ? 5U : 4U);
    std::size_t field_start = 0U;
    for (std::size_t field = 0U; field < field_count; ++field) {
      const std::size_t tab = line.find('\t', field_start);
      const bool last = field + 1U == field_count;
      if ((!last && tab == std::string_view::npos) ||
          (last && tab != std::string_view::npos)) {
        return false;
      }
      const std::size_t field_end = last ? line.size() : tab;
      fields[field] = line.substr(field_start, field_end - field_start);
      field_start = last ? line.size() : tab + 1U;
    }
    std::array<std::uint64_t, 5U> values{};
    const std::size_t integer_field_count =
        expected_cents_column ? 5U : field_count;
    for (std::size_t field = 0U; field < integer_field_count; ++field) {
      if (!parse_u64(fields[field], values[field])) {
        return false;
      }
    }
    std::int16_t expected_cents_q8 = 0;
    if (expected_cents_column &&
        !parse_expected_cents(fields[5], expected_cents_q8)) {
      return false;
    }
    if (output.size() >= kMaximumLabelRows || values[0] >= values[1] ||
        values[1] > sample_count || values[2] > 127U || values[3] > 255U ||
        (calibration_pass_column &&
         (values[4] == 0U || values[4] > 255U)) ||
        (!output.empty() && values[0] < prior_start)) {
      return false;
    }
    output.push_back(ReplayLabel{
        values[0], values[1], static_cast<std::uint8_t>(values[2]),
        static_cast<std::uint8_t>(values[3]),
        static_cast<std::uint8_t>(calibration_pass_column ? values[4] : 0U),
        expected_cents_q8, expected_cents_column});
    prior_start = values[0];
  }
  error = ReplayError::none;
  return true;
}

bool derive_labeled_string_calibration(
    const WaveData& wave, const std::vector<ReplayLabel>& labels,
    const PersistentConfig& config, std::uint8_t string_index,
    StringCalibrationBank& output, ReplayError& error) {
  error = ReplayError::invalid_calibration;
  if (wave.sample_rate == 0U || wave.source_channels == 0U ||
      string_index >= kMaxVoices || config.profile_mode != ProfileMode::m3 ||
      !std::isfinite(config.a4_hz) || labels.empty()) {
    return false;
  }
  PolyphonicPitchDetector validator;
  if (!validator.configure(static_cast<double>(wave.sample_rate), config)) {
    error = ReplayError::invalid_config;
    return false;
  }
  const bool explicit_passes = labels.front().calibration_pass != 0U;
  for (const ReplayLabel& label : labels) {
    if ((label.calibration_pass != 0U) != explicit_passes) {
      return false;
    }
  }
  struct Accumulator final {
    std::array<double, kCalibrationHarmonicCount> profile_sum{};
    std::array<double, kCalibrationHarmonicCount> first_profile{};
    std::array<double, kCalibrationHarmonicCount> partial_detuning_sum{};
    std::array<double, kCalibrationHarmonicCount>
        partial_detuning_square_sum{};
    std::array<std::uint16_t, kCalibrationHarmonicCount>
        partial_detuning_count{};
    double cents_sum{};
    double confidence_sum{};
    double profile_similarity_sum{};
    double minimum_cents{std::numeric_limits<double>::infinity()};
    double maximum_cents{-std::numeric_limits<double>::infinity()};
    std::uint16_t count{};
  };
  struct PassAccumulator final {
    double cents_sum{};
    std::uint16_t count{};
    std::uint8_t pass_id{};
  };
  struct FretPasses final {
    std::array<PassAccumulator, kMaximumLabeledCalibrationPasses> passes{};
    std::size_t count{};
  };
  std::array<Accumulator, kCalibrationFretCount> accumulated{};
  std::array<FretPasses, kCalibrationFretCount> pass_accumulated{};
  const std::uint8_t required_mask =
      static_cast<std::uint8_t>(1U << string_index);
  const std::uint8_t open_note = kM3OpenNotes[string_index];
  for (const ReplayLabel& label : labels) {
    if (label.string_mask != required_mask || label.midi_note < open_note ||
        label.midi_note >= open_note + kCalibrationFretCount ||
        label.start_sample >= label.end_sample ||
        label.end_sample > wave.mono_samples.size()) {
      return false;
    }
    const std::size_t fret = label.midi_note - open_note;
    const double nominal_frequency =
        midi_to_frequency(static_cast<double>(label.midi_note), config.a4_hz);
    LabeledCalibrationEstimate estimate;
    if (!estimate_labeled_calibration(
            wave, label, nominal_frequency, estimate)) {
      // An explicit multi-pass corpus may contain one weak isolated hold.
      // Ignore that observation and let the independent pass quorum below
      // decide whether the fret still has enough repeatable evidence.
      if (explicit_passes) {
        continue;
      }
      return false;
    }
    if (explicit_passes) {
      FretPasses& fret_passes = pass_accumulated[fret];
      PassAccumulator* pass = nullptr;
      for (std::size_t index = 0U; index < fret_passes.count; ++index) {
        if (fret_passes.passes[index].pass_id == label.calibration_pass) {
          pass = &fret_passes.passes[index];
          break;
        }
      }
      if (pass == nullptr) {
        if (fret_passes.count >= fret_passes.passes.size()) {
          return false;
        }
        pass = &fret_passes.passes[fret_passes.count++];
        pass->pass_id = label.calibration_pass;
      }
      if (pass->count == std::numeric_limits<std::uint16_t>::max()) {
        return false;
      }
      pass->cents_sum += estimate.cents;
      ++pass->count;
      // Passes 1 and 2 are the continuous ascending and descending walks.
      // They define the stable string-timbre template. Later isolated-note
      // passes refine pitch without shifting that template toward one pluck.
      if (label.calibration_pass > 2U) {
        continue;
      }
    }
    Accumulator& accumulator = accumulated[fret];
    if (accumulator.count != 0U) {
      double dot = 0.0;
      double left_norm = 0.0;
      double right_norm = 0.0;
      for (std::size_t harmonic = 0U;
           harmonic < kCalibrationHarmonicCount; ++harmonic) {
        const double left = accumulator.first_profile[harmonic];
        const double right = estimate.profile[harmonic];
        dot += left * right;
        left_norm += left * left;
        right_norm += right * right;
      }
      const double denominator = std::sqrt(left_norm * right_norm);
      if (denominator <= 0.0) {
        return false;
      }
      accumulator.profile_similarity_sum +=
          std::clamp(dot / denominator, 0.0, 1.0);
    } else {
      accumulator.first_profile = estimate.profile;
      accumulator.profile_similarity_sum = 1.0;
    }
    accumulator.cents_sum += estimate.cents;
    accumulator.confidence_sum += estimate.correlation;
    accumulator.minimum_cents =
        std::min(accumulator.minimum_cents, estimate.cents);
    accumulator.maximum_cents =
        std::max(accumulator.maximum_cents, estimate.cents);
    for (std::size_t harmonic = 0U;
         harmonic < kCalibrationHarmonicCount; ++harmonic) {
      accumulator.profile_sum[harmonic] += estimate.profile[harmonic];
      if ((estimate.partial_detuning_valid_mask & (1U << harmonic)) != 0U) {
        accumulator.partial_detuning_sum[harmonic] +=
            estimate.partial_detuning_cents[harmonic];
        accumulator.partial_detuning_square_sum[harmonic] +=
            estimate.partial_detuning_cents[harmonic] *
            estimate.partial_detuning_cents[harmonic];
        ++accumulator.partial_detuning_count[harmonic];
      }
    }
    if (accumulator.count == std::numeric_limits<std::uint16_t>::max()) {
      return false;
    }
    ++accumulator.count;
  }

  StringCalibrationBank candidate = output;
  candidate.clear_string(string_index);
  for (std::size_t fret = 0U; fret < kCalibrationFretCount; ++fret) {
    if (explicit_passes) {
      const FretPasses& fret_passes = pass_accumulated[fret];
      if (fret_passes.count < 2U) {
        return false;
      }
      bool have_ascending = false;
      bool have_descending = false;
      for (std::size_t pass = 0U; pass < fret_passes.count; ++pass) {
        have_ascending = have_ascending ||
                         fret_passes.passes[pass].pass_id == 1U;
        have_descending = have_descending ||
                          fret_passes.passes[pass].pass_id == 2U;
      }
      if (!have_ascending || !have_descending) {
        return false;
      }
      std::array<double, kMaximumLabeledCalibrationPasses> pass_cents{};
      for (std::size_t pass = 0U; pass < fret_passes.count; ++pass) {
        const PassAccumulator& accumulator = fret_passes.passes[pass];
        if (accumulator.count == 0U) {
          return false;
        }
        const double count = static_cast<double>(accumulator.count);
        pass_cents[pass] = accumulator.cents_sum / count;
      }

      // Select the largest repeatable collection of independent passes.
      // With three passes this averages all three when they agree, or the
      // closest pair when one pass is a transition/tuning outlier.
      std::uint16_t best_mask = 0U;
      std::size_t best_count = 0U;
      double best_pairwise_difference =
          std::numeric_limits<double>::infinity();
      const std::uint16_t subset_count =
          static_cast<std::uint16_t>(1U << fret_passes.count);
      for (std::uint16_t mask = 1U; mask < subset_count; ++mask) {
        std::size_t selected = 0U;
        bool eligible = true;
        double minimum = std::numeric_limits<double>::infinity();
        double maximum = -std::numeric_limits<double>::infinity();
        double pairwise_difference = 0.0;
        for (std::size_t left = 0U; left < fret_passes.count; ++left) {
          if ((mask & static_cast<std::uint16_t>(1U << left)) == 0U) {
            continue;
          }
          if (fret == 0U && fret_passes.passes[left].pass_id > 2U) {
            eligible = false;
            break;
          }
          ++selected;
          minimum = std::min(minimum, pass_cents[left]);
          maximum = std::max(maximum, pass_cents[left]);
          for (std::size_t right = left + 1U;
               right < fret_passes.count; ++right) {
            if ((mask & static_cast<std::uint16_t>(1U << right)) != 0U) {
              pairwise_difference +=
                  std::abs(pass_cents[left] - pass_cents[right]);
            }
          }
        }
        if (!eligible || selected < 2U ||
            maximum - minimum > kMaximumLabeledPassDifferenceCents) {
          continue;
        }
        if (selected > best_count ||
            (selected == best_count &&
             pairwise_difference < best_pairwise_difference)) {
          best_mask = mask;
          best_count = selected;
          best_pairwise_difference = pairwise_difference;
        }
      }
      if (best_count < 2U) {
        return false;
      }

      double cents_sum = 0.0;
      std::uint32_t observation_count = 0U;
      for (std::size_t pass = 0U; pass < fret_passes.count; ++pass) {
        if ((best_mask & static_cast<std::uint16_t>(1U << pass)) == 0U) {
          continue;
        }
        cents_sum += pass_cents[pass];
        observation_count += fret_passes.passes[pass].count;
      }
      if (observation_count > std::numeric_limits<std::uint16_t>::max()) {
        return false;
      }
      const double count = static_cast<double>(best_count);
      const Accumulator& identity = accumulated[fret];
      if (identity.count < 2U ||
          identity.maximum_cents - identity.minimum_cents >
              kMaximumLabeledPassDifferenceCents) {
        return false;
      }
      const double identity_count = static_cast<double>(identity.count);
      const double repeatability =
          1.0 - std::clamp(
                    (identity.maximum_cents - identity.minimum_cents) /
                        kMaximumLabeledPassDifferenceCents,
                    0.0, 1.0);
      StringCalibrationPoint& point = candidate.points[string_index][fret];
      point.cents_offset_q8 = static_cast<std::int16_t>(std::lround(
          std::clamp(cents_sum / count, -50.0, 50.0) * 256.0));
      for (std::size_t harmonic = 0U;
           harmonic < kCalibrationHarmonicCount; ++harmonic) {
        point.harmonic_profile_q15[harmonic] =
            static_cast<std::uint16_t>(std::lround(
                std::clamp(identity.profile_sum[harmonic] / identity_count,
                           0.0, 1.0) *
                32767.0));
        if (identity.partial_detuning_count[harmonic] >= 2U) {
          const double partial_count = static_cast<double>(
              identity.partial_detuning_count[harmonic]);
          const double partial_mean =
              identity.partial_detuning_sum[harmonic] / partial_count;
          const double partial_variance = std::max(
              0.0, identity.partial_detuning_square_sum[harmonic] /
                           partial_count -
                       partial_mean * partial_mean);
          if (std::sqrt(partial_variance) >
              kMaximumPartialDetuningStandardDeviationCents) {
            continue;
          }
          point.partial_detuning_q8[harmonic] =
              static_cast<std::int16_t>(std::lround(std::clamp(
                  partial_mean,
                  -50.0, 50.0) *
                                                      256.0));
          point.partial_detuning_valid_mask = static_cast<std::uint8_t>(
              point.partial_detuning_valid_mask | (1U << harmonic));
        }
      }
      point.confidence_q15 = static_cast<std::uint16_t>(std::lround(
          std::clamp(identity.confidence_sum / identity_count * repeatability,
                     0.0, 1.0) *
          std::clamp(identity.profile_similarity_sum / identity_count,
                     0.0, 1.0) *
          32767.0));
      point.observation_count =
          static_cast<std::uint16_t>(observation_count);
      point.quality = CalibrationPointQuality::measured;
      continue;
    }
    const Accumulator& accumulator = accumulated[fret];
    if (accumulator.count < 2U ||
        accumulator.maximum_cents - accumulator.minimum_cents >
            kMaximumLabeledPassDifferenceCents) {
      return false;
    }
    StringCalibrationPoint& point = candidate.points[string_index][fret];
    const double count = static_cast<double>(accumulator.count);
    point.cents_offset_q8 = static_cast<std::int16_t>(std::lround(
        std::clamp(accumulator.cents_sum / count, -50.0, 50.0) * 256.0));
    for (std::size_t harmonic = 0U;
         harmonic < kCalibrationHarmonicCount; ++harmonic) {
      point.harmonic_profile_q15[harmonic] =
          static_cast<std::uint16_t>(std::lround(std::clamp(
              accumulator.profile_sum[harmonic] / count, 0.0, 1.0) *
                                                 32767.0));
      if (accumulator.partial_detuning_count[harmonic] >= 2U) {
        const double partial_count = static_cast<double>(
            accumulator.partial_detuning_count[harmonic]);
        const double partial_mean =
            accumulator.partial_detuning_sum[harmonic] / partial_count;
        const double partial_variance = std::max(
            0.0, accumulator.partial_detuning_square_sum[harmonic] /
                         partial_count -
                     partial_mean * partial_mean);
        if (std::sqrt(partial_variance) >
            kMaximumPartialDetuningStandardDeviationCents) {
          continue;
        }
        point.partial_detuning_q8[harmonic] =
            static_cast<std::int16_t>(std::lround(std::clamp(
                partial_mean,
                -50.0, 50.0) *
                                                    256.0));
        point.partial_detuning_valid_mask = static_cast<std::uint8_t>(
            point.partial_detuning_valid_mask | (1U << harmonic));
      }
    }
    const double cents_span =
        accumulator.maximum_cents - accumulator.minimum_cents;
    const double repeatability =
        1.0 - std::clamp(cents_span / kMaximumLabeledPassDifferenceCents,
                         0.0, 1.0);
    // A physical string can present radically different harmonic balances
    // across otherwise valid plucks. Preserve that useful pitch evidence and
    // express timbre inconsistency as lower confidence instead of rejecting
    // the entire 25-fret calibration image.
    const double timbre_repeatability =
        std::clamp(accumulator.profile_similarity_sum / count, 0.0, 1.0);
    point.confidence_q15 = static_cast<std::uint16_t>(std::lround(
        std::clamp(accumulator.confidence_sum / count * repeatability,
                   0.0, 1.0) *
        timbre_repeatability *
        32767.0));
    point.observation_count = accumulator.count;
    point.quality = CalibrationPointQuality::measured;
  }
  candidate.calibrated_string_mask = static_cast<std::uint8_t>(
      candidate.calibrated_string_mask | required_mask);
  output = candidate;
  error = ReplayError::none;
  return true;
}

bool run_detector_replay(const WaveData& wave,
                         const std::vector<ReplayLabel>& labels,
                         const PersistentConfig& config,
                         const StringCalibrationBank* calibration,
                         std::size_t input_partition,
                         ReplayResult& output, ReplayError& error,
                         const UnisonSpectralShadowTemplateBank*
                             spectral_shadow_templates,
                         const CandidateAdmissionRescuePolicy*
                             candidate_admission_rescue,
                         const FrettedPositionPriorPolicy*
                             fretted_position_prior,
                         const DecisiveCalibratedSelectorPolicy*
                             decisive_calibrated_selector,
                         const CalibratedDpReplacementPolicy*
                             calibrated_dp_replacement,
                         const ProductionDpReplacementLanePolicy*
                             production_dp_replacement_lanes,
                         bool diagnostic_fine_mask_pruning,
                         bool diagnostic_fine_beat_pruning,
                         bool diagnostic_collecting_fine_history_carry,
                         double diagnostic_correlation_seconds,
                         bool diagnostic_selection_window_only,
                         bool diagnostic_correlation_shadow_only,
                         bool diagnostic_joint_pitch_residual,
                         FrequencyWindowCapture* frequency_window_capture,
                         bool diagnostic_bounded_joint_pitch_residual) {
  output = {};
  error = ReplayError::invalid_config;
  if (wave.sample_rate == 0U || wave.source_channels == 0U ||
      input_partition == 0U || input_partition > kMaximumInputPartition) {
    return false;
  }
  if (diagnostic_joint_pitch_residual && diagnostic_correlation_seconds != -1.0) {
    return false;
  }
  if (diagnostic_bounded_joint_pitch_residual && !diagnostic_joint_pitch_residual) {
    return false;
  }
  for (const ReplayLabel& label : labels) {
    if (label.start_sample >= label.end_sample ||
        label.end_sample > wave.mono_samples.size()) {
      return false;
    }
  }
  // Diagnostic builds intentionally carry large fixed counter tables. Keep
  // the detector and result off callers' bounded thread stacks; replay is an
  // offline tool and may allocate before processing begins.
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::unique_ptr<HannBeatShadowBuffer> hann_shadow_storage;
  std::unique_ptr<FrequencyRefinementShadow> frequency_shadow_storage;
  if (spectral_shadow_templates != nullptr) {
    hann_shadow_storage = std::make_unique<HannBeatShadowBuffer>();
    frequency_shadow_storage = std::make_unique<FrequencyRefinementShadow>();
    frequency_shadow_storage->set_capture(frequency_window_capture);
  }
#endif
  auto detector_storage = std::make_unique<PolyphonicPitchDetector>();
  PolyphonicPitchDetector& detector = *detector_storage;
  if (!detector.configure(static_cast<double>(wave.sample_rate), config)) {
    return false;
  }
  if ((diagnostic_correlation_seconds == -1.0 &&
       (diagnostic_selection_window_only ||
        diagnostic_correlation_shadow_only)) ||
      (diagnostic_correlation_seconds != -1.0 &&
      !detector.set_correlation_window_for_diagnostics(
          diagnostic_correlation_seconds, diagnostic_selection_window_only,
          diagnostic_correlation_shadow_only))) {
    return false;
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  detector.set_hann_beat_shadow_buffer(hann_shadow_storage.get());
  if (frequency_shadow_storage != nullptr) {
    detector.set_frequency_refinement_observer(
        &FrequencyRefinementShadow::observe, frequency_shadow_storage.get());
  }
  detector.set_fine_mask_complexity_diagnostics_enabled(
      spectral_shadow_templates != nullptr || diagnostic_fine_mask_pruning ||
      diagnostic_fine_beat_pruning);
  detector.set_fine_mask_pruning_for_diagnostics(
      diagnostic_fine_mask_pruning);
  detector.set_fine_beat_pruning_for_diagnostics(
      diagnostic_fine_beat_pruning);
  detector.set_collecting_fine_history_carry_for_diagnostics(
      diagnostic_collecting_fine_history_carry);
#endif
  if (calibration != nullptr) {
    detector.set_calibration_bank(*calibration);
  }
  if (candidate_admission_rescue != nullptr &&
      !detector.set_candidate_admission_rescue_for_diagnostics(
          candidate_admission_rescue->score_threshold_ratio,
          candidate_admission_rescue->fundamental_score_ratio)) {
    return false;
  }
  if (fretted_position_prior != nullptr &&
      !detector.set_fretted_position_prior_for_diagnostics(
          fretted_position_prior->fixed_penalty,
          fretted_position_prior->per_fret_penalty)) {
    return false;
  }
  if (decisive_calibrated_selector != nullptr &&
      !detector.set_decisive_calibrated_selector_for_diagnostics(
          decisive_calibrated_selector->minimum_margin,
          decisive_calibrated_selector->allowed_string_mask)) {
    return false;
  }
  if (production_dp_replacement_lanes != nullptr &&
      !detector.set_calibrated_dp_replacement_lane_mask_for_diagnostics(
          production_dp_replacement_lanes->allowed_string_mask)) {
    return false;
  }
  auto result_storage = std::make_unique<ReplayResult>();
  ReplayResult& result = *result_storage;
  std::unique_ptr<m3::JointPitchResidual> joint_pitch_fit;
  if (diagnostic_joint_pitch_residual) {
    joint_pitch_fit = std::make_unique<m3::JointPitchResidual>();
  }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::array<AdjacentEnvelopeCoherenceState, 127U>
      adjacent_envelope_coherence_states{};
  result.physical_group_expected_observed_mask_frames.assign(1U << 16U, 0U);
  result.physical_group_expected_fine_mask_frames.assign(1U << 16U, 0U);
  result.physical_group_expected_committed_mask_frames.assign(1U << 16U,
                                                               0U);
#endif
  result.fingerprint = kFnvOffset;
  result.sample_count = wave.mono_samples.size();
  result.label_results.resize(labels.size());
  struct LabelTrackingState final {
    std::uint8_t previous_nonzero_lane_mask{};
    std::uint32_t current_correct_run_frames{};
    std::uint32_t current_committed_exact_fine_gap_frames{};
    std::size_t current_quiet_disposition{kQuietDispositionCount};
    std::uint32_t current_quiet_disposition_run_frames{};
    std::array<std::uint32_t, 8U>
        current_committed_exact_retained_disposition_run_frames{};
  };
  std::vector<LabelTrackingState> label_tracking(labels.size());
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::vector<std::size_t> label_starts(labels.size());
  std::vector<std::size_t> label_ends(labels.size());
  std::iota(label_starts.begin(), label_starts.end(), 0U);
  std::iota(label_ends.begin(), label_ends.end(), 0U);
  std::sort(label_starts.begin(), label_starts.end(),
            [&labels](std::size_t left, std::size_t right) {
              return labels[left].start_sample < labels[right].start_sample ||
                     (labels[left].start_sample == labels[right].start_sample &&
                      left < right);
            });
  std::sort(label_ends.begin(), label_ends.end(),
            [&labels](std::size_t left, std::size_t right) {
              return labels[left].end_sample < labels[right].end_sample ||
                     (labels[left].end_sample == labels[right].end_sample &&
                      left < right);
            });
  std::vector<UnisonSpectralCorridorTracker> spectral_trackers(128U);
  std::array<std::uint32_t, 128U> spectral_active_references{};
  std::array<std::uint64_t, 2U> spectral_active_notes{};
  struct PhysicalGroupRunState final {
    std::size_t cell{kPhysicalGroupCausalCellCount};
    std::uint32_t frames{};
    std::uint8_t expected_members{};
    ReplayTargetLaneOutcome last_outcome{ReplayTargetLaneOutcome::count};
    bool initialized{};
  };
  std::array<PhysicalGroupRunState, 128U> physical_group_runs{};
  struct PhysicalGroupFineUnresolvedRunState final {
    std::size_t cell{kPhysicalGroupFineUnresolvedCellCount};
    std::uint32_t frames{};
    std::uint8_t expected_members{};
  };
  std::array<PhysicalGroupFineUnresolvedRunState, 128U>
      physical_group_fine_unresolved_runs{};
  std::vector<UnisonSpectralCorridorTracker> candidate_spectral_trackers(
      128U);
  std::array<std::uint64_t, 2U> candidate_spectral_active_notes{};
  std::array<CandidateAdmissionDiagnostics, 128U>
      candidate_spectral_admission{};
  const std::size_t candidate_spectral_decimation =
      wave.sample_rate >= 32000U ? 4U : 1U;
  const double candidate_spectral_sample_rate =
      static_cast<double>(wave.sample_rate) /
      static_cast<double>(candidate_spectral_decimation);
  double candidate_spectral_decimation_sum = 0.0;
  std::size_t candidate_spectral_decimation_count = 0U;
  std::vector<bool> spectral_active_labels(labels.size(), false);
  std::array<std::uint8_t, 128U> spectral_expected_group_masks{};
  std::array<bool, 128U> spectral_expected_group_note_only{};
  std::array<std::size_t, 128U> spectral_group_leader_indices{};
  struct UnisonReacquisitionState final {
    std::uint8_t resolved_mask{};
    std::uint64_t last_confirmed_sample{
        std::numeric_limits<std::uint64_t>::max()};
    UnisonSpectralFingerprint confirmed_fingerprint{};
    bool confirmed_fingerprint_valid{};
  };
  std::array<UnisonReacquisitionState, 128U> unison_reacquisition_states{};
  std::array<UnisonReacquisitionState, 128U>
      committed_three_plus_cache_states{};
  std::vector<std::array<SpectralOnsetMaskLatch,
                         kSpectralShadowMarginThresholdCount>>
      spectral_onset_latches(128U);
  std::array<std::array<CalibratedPitchRebinLatch, 128U>,
             kCalibratedPitchRebinThresholds.size()>
      calibrated_pitch_rebin_latches{};
  std::array<std::array<CalibratedPitchRebinLatch, 128U>,
             kCalibratedPitchRebinProjectedErrorThresholds.size()>
      calibrated_pitch_rebin_projected_error_latches{};
  std::array<std::array<CalibratedPitchRebinLatch, 128U>,
             kMultiPartialPhasePolicyCount>
      multi_partial_phase_rebin_latches{};
  spectral_group_leader_indices.fill(labels.size());
  std::size_t next_label_start = 0U;
  std::size_t next_label_end = 0U;
  const auto rebuild_spectral_expected_group =
      [&labels, &spectral_active_labels, &spectral_expected_group_masks,
       &spectral_expected_group_note_only,
       &spectral_group_leader_indices](std::uint8_t note) {
        std::uint8_t expected_mask = 0U;
        bool note_only = false;
        std::size_t leader = labels.size();
        for (std::size_t label_index = 0U; label_index < labels.size();
             ++label_index) {
          const ReplayLabel& label = labels[label_index];
          if (!spectral_active_labels[label_index] ||
              label.midi_note != note) {
            continue;
          }
          leader = std::min(leader, label_index);
          note_only = note_only || label.string_mask == 0U;
          expected_mask = static_cast<std::uint8_t>(expected_mask |
                                                    label.string_mask);
        }
        spectral_expected_group_masks[note] =
            note_only ? std::numeric_limits<std::uint8_t>::max()
                      : expected_mask;
        spectral_expected_group_note_only[note] = note_only;
        spectral_group_leader_indices[note] = leader;
      };
#endif
  const double input_gain = std::pow(10.0, config.input_trim_db / 20.0);
  if (!std::isfinite(input_gain)) {
    return false;
  }
  for (std::size_t block_start = 0U; block_start < wave.mono_samples.size();
       block_start += input_partition) {
    const std::size_t block_end = std::min(
        wave.mono_samples.size(), block_start + input_partition);
    for (std::size_t sample_index = block_start; sample_index < block_end;
         ++sample_index) {
      const double sample = wave.mono_samples[sample_index] * input_gain;
      if (!std::isfinite(sample)) {
        error = ReplayError::nonfinite_audio;
        return false;
      }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      while (next_label_end < label_ends.size() &&
             labels[label_ends[next_label_end]].end_sample == sample_index) {
        const std::size_t label_index = label_ends[next_label_end];
        const std::uint8_t note = labels[label_index].midi_note;
        spectral_active_labels[label_index] = false;
        if (spectral_active_references[note] > 0U &&
            --spectral_active_references[note] == 0U) {
          spectral_active_notes[note / 64U] &=
              ~(std::uint64_t{1U} << (note % 64U));
          spectral_trackers[note].reset();
          for (SpectralOnsetMaskLatch& latch :
               spectral_onset_latches[note]) {
            latch.reset();
          }
          physical_group_runs[note] = {};
        }
        rebuild_spectral_expected_group(note);
        ++next_label_end;
      }
      while (next_label_start < label_starts.size() &&
             labels[label_starts[next_label_start]].start_sample ==
                 sample_index) {
        const std::size_t label_index = label_starts[next_label_start];
        const std::uint8_t note = labels[label_index].midi_note;
        spectral_active_labels[label_index] = true;
        if (spectral_active_references[note]++ == 0U) {
          for (SpectralOnsetMaskLatch& latch :
               spectral_onset_latches[note]) {
            latch.reset();
          }
          if (spectral_trackers[note].configure(
                  static_cast<double>(wave.sample_rate), note)) {
            spectral_active_notes[note / 64U] |=
                std::uint64_t{1U} << (note % 64U);
          }
        }
        rebuild_spectral_expected_group(note);
        ++next_label_start;
      }
      for (std::size_t half = 0U; half < spectral_active_notes.size(); ++half) {
        std::uint64_t active = spectral_active_notes[half];
        while (active != 0U) {
#if defined(__GNUC__) || defined(__clang__)
          const std::size_t bit =
              static_cast<std::size_t>(__builtin_ctzll(active));
#else
          std::size_t bit = 0U;
          while (((active >> bit) & 1U) == 0U) {
            ++bit;
          }
#endif
          spectral_trackers[half * 64U + bit].observe(sample);
          active &= active - 1U;
        }
      }
      if (spectral_shadow_templates != nullptr) {
        candidate_spectral_decimation_sum += sample;
        ++candidate_spectral_decimation_count;
        if (candidate_spectral_decimation_count ==
            candidate_spectral_decimation) {
          const double decimated =
              candidate_spectral_decimation_sum /
              static_cast<double>(candidate_spectral_decimation_count);
          for (std::size_t half = 0U;
               half < candidate_spectral_active_notes.size(); ++half) {
            std::uint64_t active = candidate_spectral_active_notes[half];
            while (active != 0U) {
#if defined(__GNUC__) || defined(__clang__)
              const std::size_t bit =
                  static_cast<std::size_t>(__builtin_ctzll(active));
#else
              std::size_t bit = 0U;
              while (((active >> bit) & 1U) == 0U) {
                ++bit;
              }
#endif
              candidate_spectral_trackers[half * 64U + bit].observe(
                  decimated);
              active &= active - 1U;
            }
          }
          candidate_spectral_decimation_sum = 0.0;
          candidate_spectral_decimation_count = 0U;
        }
      }
#endif
      const DetectorDecision decision = detector.process_sample(sample);
      for (const VoiceTransition& transition : decision.transitions) {
        ++result.transition_count;
        if (sample_is_inside_label(sample_index, labels)) {
          ++result.transition_inside_hold_count;
        } else {
          ++result.transition_gap_count;
        }
        hash_integer(result.fingerprint, sample_index);
        hash_byte(result.fingerprint,
                  static_cast<std::uint8_t>(transition.kind));
        hash_byte(result.fingerprint, transition.note);
        hash_byte(result.fingerprint, transition.velocity);
        hash_byte(result.fingerprint, transition.voice_id);
        hash_integer(result.fingerprint, transition.sequence);
      }
      if (!decision.tuner_snapshot_ready) {
        continue;
      }
      ++result.snapshot_frames;
      if (detector.partial_detuning_candidate_count() != 0U) {
        ++result.partial_detuning_frames;
      }
      const TunerSnapshot& snapshot = decision.tuner_snapshot;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      if (joint_pitch_fit != nullptr) {
        std::array<double, 128U> independent_energy;
        independent_energy.fill(std::numeric_limits<double>::quiet_NaN());
        std::array<bool, 128U> protected_notes{};
        std::array<double, 128U> fundamental_overlap{};
        std::array<bool, 128U> emitted{};
        for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
          const auto note = snapshot.voices[voice].detected_midi_note;
          if (note < emitted.size()) {
            emitted[note] = true;
          }
        }
        std::array<JointPitchObservation, kMaxVoices> observations{};
        std::size_t count = 0U;
        double energy = 0.0;
        double decay = 0.0;
        for (std::size_t note = 0U; note < emitted.size(); ++note) {
          if (!emitted[note] || count >= observations.size()) {
            continue;
          }
          auto& observed = observations[count];
          observed.note = static_cast<std::uint8_t>(note);
          if (detector.harmonic_correlations_for_diagnostics(
                  observed.note, observed.frequency_hz, observed.correlation,
                  energy, decay)) {
            ++count;
          }
          protected_notes[note] =
              mask_member_count(detector.fine_frequency_member_mask(
                  static_cast<std::uint8_t>(note))) >= 2U ||
              mask_member_count(detector.fine_frequency_pending_member_mask(
                  static_cast<std::uint8_t>(note))) >= 2U ||
              mask_member_count(detector.committed_unison_mask(
                  static_cast<std::uint8_t>(note))) >= 2U;
        }
        // At 20 time constants the missing pre-recording history has weight
        // below 3e-9, so the stationary Gram matrix is a bounded approximation.
        if (snapshot.state == TunerFrameState::tracking && count >= 2U &&
            static_cast<double>(sample_index + 1U) >=
                0.8 * static_cast<double>(wave.sample_rate)) {
          const auto fit = diagnostic_bounded_joint_pitch_residual
              ? joint_pitch_fit->evaluate_bounded(
                  observations, count, static_cast<double>(wave.sample_rate),
                  decay, energy)
              : joint_pitch_fit->evaluate(
                  observations, count, static_cast<double>(wave.sample_rate),
                  decay, energy);
          result.joint_pitch_max_rebuild_work = std::max(
              result.joint_pitch_max_rebuild_work,
              static_cast<std::uint32_t>(joint_pitch_fit->last_rebuild_work_units()));
          if (fit.valid) {
            ++result.joint_pitch_valid_frames;
            result.joint_pitch_residual_sum += fit.residual_fraction;
            for (std::size_t pitch = 0U; pitch < count; ++pitch) {
              const auto note = observations[pitch].note;
              independent_energy[note] = fit.independent_energy_fraction[pitch];
              fundamental_overlap[note] = fit.fundamental_overlap[pitch];
              // A shared fundamental alone cannot distinguish a real octave
              // tone from another pitch's harmonic. Keep that ambiguity.
              protected_notes[note] = protected_notes[note] ||
                                      fit.shared_fundamental[pitch];
            }
          } else {
            ++result.joint_pitch_invalid_frames;
            if (joint_pitch_fit->rebuild_pending()) {
              ++result.joint_pitch_build_pending_frames;
            }
          }
        } else if (diagnostic_bounded_joint_pitch_residual) {
          joint_pitch_fit->reset();
        }
        for (std::size_t policy = 0U; policy < kJointPitchPolicies.size();
             ++policy) {
          const auto& settings = kJointPitchPolicies[policy];
          std::array<bool, 128U> ambiguous = protected_notes;
          for (std::size_t note = 0U; note < ambiguous.size(); ++note) {
            ambiguous[note] = ambiguous[note] ||
                fundamental_overlap[note] >= settings.maximum_fundamental_overlap;
          }
          const CorrelationShadowPolicy veto{
              settings.minimum_energy_fraction, 0.30, false, true};
          const auto projected = correlation_shadow_projection(
              snapshot, independent_energy, static_cast<double>(wave.sample_rate),
              veto, result.joint_pitch_shadow[policy].changed_voices,
              &ambiguous);
          accumulate_counterfactual_metrics(
              projected, sample_index, labels, result.joint_pitch_shadow[policy]);
        }
      }
      if (diagnostic_correlation_shadow_only) {
        std::array<std::array<double, 128U>, 2U> ratios{};
        std::array<bool, 128U> pending_unison{};
        for (auto& row : ratios) {
          row.fill(std::numeric_limits<double>::quiet_NaN());
        }
        for (std::size_t index = 0U; index < snapshot.voice_count; ++index) {
          const auto note = snapshot.voices[index].detected_midi_note;
          if (note >= ratios[0U].size()) {
            continue;
          }
          pending_unison[note] =
              mask_member_count(detector.fine_frequency_member_mask(note)) >= 2U ||
              mask_member_count(
                  detector.fine_frequency_pending_member_mask(note)) >= 2U ||
              mask_member_count(detector.committed_unison_mask(note)) >= 2U;
          for (std::size_t kind = 0U; kind < ratios.size(); ++kind) {
            static_cast<void>(
                detector.correlation_window_energy_ratio_for_diagnostics(
                    note, kind != 0U, ratios[kind][note]));
          }
        }
        for (std::size_t policy = 0U;
             policy < kCorrelationShadowPolicies.size(); ++policy) {
          const auto& settings = kCorrelationShadowPolicies[policy];
          const auto projected = correlation_shadow_projection(
              snapshot, ratios[settings.fundamental_only ? 1U : 0U],
              static_cast<double>(wave.sample_rate), settings,
              result.correlation_shadow[policy].changed_voices,
              &pending_unison);
          accumulate_counterfactual_metrics(
              projected, sample_index, labels,
              result.correlation_shadow[policy]);
        }
      }
      std::array<TunerSnapshot, kAdjacentSpectralDuplicatePolicies.size()>
          adjacent_spectral_duplicate_projected{};
      adjacent_spectral_duplicate_projected.fill(snapshot);
      std::array<double, 128U> production_spectral_single_best_errors{};
      production_spectral_single_best_errors.fill(
          std::numeric_limits<double>::infinity());
      for (std::size_t note = 0U; note < 128U; ++note) {
        static_cast<void>(detector.spectral_single_source_best_error(
            static_cast<std::uint8_t>(note),
            production_spectral_single_best_errors[note]));
      }
      for (std::size_t policy = 0U;
           policy < kAdjacentSpectralDuplicatePolicies.size(); ++policy) {
        const TunerSnapshot projected = adjacent_spectral_duplicate_projection(
            snapshot, production_spectral_single_best_errors,
            kAdjacentSpectralDuplicatePolicies[policy],
            result.production_adjacent_spectral_duplicate_suppression[policy]
                .changed_voices);
        accumulate_counterfactual_metrics(
            projected, sample_index, labels,
            result.production_adjacent_spectral_duplicate_suppression[policy]);
      }
      std::array<bool, 128U> emitted_notes{};
      std::array<bool, 128U> expected_notes{};
      for (std::size_t note = 0U; note < 127U; ++note) {
        const auto left = detector.candidate_admission_diagnostics(
            static_cast<std::uint8_t>(note));
        const auto right = detector.candidate_admission_diagnostics(
            static_cast<std::uint8_t>(note + 1U));
        observe_adjacent_envelope_coherence(
            adjacent_envelope_coherence_states[note],
            std::log1p(std::max(0.0, left.fundamental_score_ratio)),
            std::log1p(std::max(0.0, right.fundamental_score_ratio)));
      }
      for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
        if (snapshot.voices[voice].midi_note < emitted_notes.size()) {
          emitted_notes[snapshot.voices[voice].midi_note] = true;
        }
      }
      for (const ReplayLabel& label : labels) {
        if (sample_index >= label.start_sample &&
            sample_index < label.end_sample &&
            label.midi_note < expected_notes.size()) {
          expected_notes[label.midi_note] = true;
        }
      }
      for (std::size_t note = 0U; note < 127U; ++note) {
        if (!emitted_notes[note] || !emitted_notes[note + 1U]) {
          continue;
        }
        const std::size_t expected_count =
            static_cast<std::size_t>(expected_notes[note]) +
            static_cast<std::size_t>(expected_notes[note + 1U]);
        const auto pair_class =
            expected_count == 2U
                ? AdjacentEnvelopePairClass::both_expected
                : expected_count == 1U
                      ? AdjacentEnvelopePairClass::one_expected
                      : AdjacentEnvelopePairClass::neither_expected;
        ++result.adjacent_envelope_coherence_frames
              [static_cast<std::size_t>(pair_class)]
              [adjacent_envelope_coherence_bin(
                  adjacent_envelope_coherence_states[note])];
      }
      if (calibrated_dp_replacement != nullptr) {
        TunerSnapshot projected = calibrated_dp_replacement_projection(
            snapshot, detector, *calibrated_dp_replacement,
            result.calibrated_dp_replacement.changed_voices);
        accumulate_counterfactual_metrics(
            projected, sample_index, labels,
            result.calibrated_dp_replacement);
      }
      if (spectral_shadow_templates != nullptr) {
        for (std::size_t policy = 0U;
             policy < kFineMaskComplexityPenalties.size(); ++policy) {
          TunerSnapshot projected = fine_mask_complexity_projection(
              snapshot, detector, kFineMaskComplexityPenalties[policy],
              config.max_polyphony,
              result.fine_mask_complexity[policy].changed_voices);
          accumulate_counterfactual_metrics(
              projected, sample_index, labels,
              result.fine_mask_complexity[policy]);
        }
      }
#endif
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      for (std::size_t note = 0U; note < 128U; ++note) {
        if (spectral_active_references[note] == 0U) {
          continue;
        }
        const std::uint8_t expected = spectral_expected_group_masks[note];
        const std::uint8_t observed = matching_note_lane_mask(
            snapshot, static_cast<std::uint8_t>(note));
        const std::uint8_t fine =
            detector.fine_frequency_member_mask(static_cast<std::uint8_t>(note));
        const std::uint8_t committed =
            detector.committed_unison_mask(static_cast<std::uint8_t>(note));
        const std::uint8_t pending =
            detector.fine_frequency_pending_member_mask(
                static_cast<std::uint8_t>(note));
        const bool note_only = spectral_expected_group_note_only[note];
        const auto stage_outcome =
            [note_only, expected](std::uint8_t mask) noexcept {
              return note_only
                         ? (mask == 0U ? ReplayTargetLaneOutcome::absent
                                      : ReplayTargetLaneOutcome::exact)
                         : classify_target_lane_outcome(mask, expected);
            };
        const ReplayTargetLaneOutcome outcome = stage_outcome(observed);
        const ReplayTargetLaneOutcome fine_outcome = stage_outcome(fine);
        const ReplayTargetLaneOutcome committed_outcome =
            stage_outcome(committed);
        const std::size_t outcome_index = static_cast<std::size_t>(outcome);
        const std::size_t fine_outcome_index =
            static_cast<std::size_t>(fine_outcome);
        const std::size_t committed_outcome_index =
            static_cast<std::size_t>(committed_outcome);
        const std::size_t members =
            note_only ? 0U : static_cast<std::size_t>(mask_member_count(expected));
        ++result.physical_group_labeled_frames;
        result.physical_group_matched_frames +=
            outcome == ReplayTargetLaneOutcome::exact ? 1U : 0U;
        ++result.physical_group_lane_outcome_frames[outcome_index];
        ++result.physical_group_expected_member_frames[members];
        ++result.physical_group_member_lane_outcome_frames[members]
                                                         [outcome_index];
        ++result.physical_group_fine_lane_outcome_frames[fine_outcome_index];
        ++result.physical_group_committed_lane_outcome_frames
              [committed_outcome_index];
        const std::size_t selection_disposition = static_cast<std::size_t>(
            detector.selection_disposition(static_cast<std::uint8_t>(note)));
        if (selection_disposition <
            result.physical_group_selection_lane_outcome_frames.size()) {
          ++result.physical_group_selection_lane_outcome_frames
                [selection_disposition][outcome_index];
          const ReplayGroupMaskRelation fine_relation =
              classify_group_mask_relation(fine, expected, note_only);
          const ReplayGroupMaskRelation committed_relation =
              classify_group_mask_relation(committed, expected, note_only);
          const ReplayGroupMaskRelation pending_relation =
              classify_group_mask_relation(pending, expected, note_only);
          const std::size_t causal_cell = physical_group_causal_cell_index(
              selection_disposition, fine_relation, committed_relation,
              outcome);
          ++result.physical_group_causal_frames[causal_cell];
          const std::size_t pending_causal_cell =
              physical_group_causal_cell_index(
                  selection_disposition, fine_relation, pending_relation,
                  outcome);
          ++result.physical_group_pending_causal_frames[pending_causal_cell];
          ++result.physical_group_member_pending_causal_frames[members]
                                                             [pending_causal_cell];
          ++result.physical_group_member_causal_frames[members][causal_cell];
          PhysicalGroupRunState& run = physical_group_runs[note];
          if (run.initialized && run.expected_members == members &&
              run.last_outcome == ReplayTargetLaneOutcome::exact &&
              outcome != ReplayTargetLaneOutcome::exact) {
            ++result.physical_group_member_exact_exit_frames[members]
                                                            [causal_cell];
          }
          run.last_outcome = outcome;
          run.initialized = true;
          if (run.cell != causal_cell || run.expected_members != members) {
            run.cell = causal_cell;
            run.frames = 0U;
            run.expected_members = static_cast<std::uint8_t>(members);
            ++result.physical_group_causal_runs[causal_cell];
            ++result.physical_group_member_causal_runs[members][causal_cell];
          }
          if (run.frames < std::numeric_limits<std::uint32_t>::max()) {
            ++run.frames;
          }
          result.physical_group_causal_longest_run_frames[causal_cell] =
              std::max(
                  result.physical_group_causal_longest_run_frames[causal_cell],
                  run.frames);
          result.physical_group_member_causal_longest_run_frames
              [members][causal_cell] =
              std::max(
                  result.physical_group_member_causal_longest_run_frames
                      [members][causal_cell],
                  run.frames);

          const std::size_t unresolved_reason = static_cast<std::size_t>(
              detector.fine_frequency_unresolved_reason(
                  static_cast<std::uint8_t>(note)));
          if (unresolved_reason < kFineFrequencyUnresolvedReasonCount) {
            const std::size_t unresolved_cell =
                physical_group_fine_unresolved_cell_index(
                    selection_disposition, unresolved_reason, outcome);
            ++result.physical_group_fine_unresolved_frames[unresolved_cell];
            ++result.physical_group_member_fine_unresolved_frames[members]
                                                                     [unresolved_cell];
            PhysicalGroupFineUnresolvedRunState& unresolved_run =
                physical_group_fine_unresolved_runs[note];
            if (unresolved_run.cell != unresolved_cell ||
                unresolved_run.expected_members != members) {
              unresolved_run.cell = unresolved_cell;
              unresolved_run.frames = 0U;
              unresolved_run.expected_members =
                  static_cast<std::uint8_t>(members);
              ++result.physical_group_fine_unresolved_runs[unresolved_cell];
              ++result.physical_group_member_fine_unresolved_runs[members]
                                                                   [unresolved_cell];
            }
            if (unresolved_run.frames <
                std::numeric_limits<std::uint32_t>::max()) {
              ++unresolved_run.frames;
            }
            result.physical_group_fine_unresolved_longest_run_frames
                [unresolved_cell] =
                std::max(
                    result.physical_group_fine_unresolved_longest_run_frames
                        [unresolved_cell],
                    unresolved_run.frames);
            result.physical_group_member_fine_unresolved_longest_run_frames
                [members][unresolved_cell] =
                std::max(
                    result
                        .physical_group_member_fine_unresolved_longest_run_frames
                            [members][unresolved_cell],
                    unresolved_run.frames);
          }
        }
        if (!note_only) {
          const CandidateAdmissionDiagnostics admission =
              detector.candidate_admission_diagnostics(
                  static_cast<std::uint8_t>(note));
          if (members == 3U &&
              selection_disposition == static_cast<std::size_t>(
                                           SelectionDisposition::selected) &&
              classify_group_mask_relation(fine, expected, false) ==
                  ReplayGroupMaskRelation::subset &&
              pending == expected &&
              outcome == ReplayTargetLaneOutcome::subset_missing) {
            const auto midi_note = static_cast<std::uint8_t>(note);
            const std::uint8_t cached =
                detector.group_continuity_cached_mask(midi_note);
            const auto projection =
                bounded_three_member_articulated_unison_reacquisition_projection(
                    observed, cached, pending,
                    detector.fine_frequency_pending_evidence_seconds(midi_note),
                    detector.fine_frequency_pending_minimum_pairwise_beat_coherence(
                        midi_note),
                    detector.spectral_tier_completion_proposal_mask(midi_note),
                    other_note_lane_mask(snapshot, midi_note),
                    admission.playable_string_mask, config.max_polyphony,
                    admission.direct_fundamental_peak, false,
                    detector.group_continuity_cache_age_seconds(midi_note),
                    0.25, 0.20);
            const std::size_t recovery_disposition =
                !admission.active ||
                        !std::isfinite(admission.score_threshold_ratio) ||
                        admission.score_threshold_ratio < 0.50
                    ? kArticulatedUnisonReacquisitionDispositionCount
                    : static_cast<std::size_t>(projection.disposition);
            const std::size_t cached_relation = static_cast<std::size_t>(
                classify_group_mask_relation(cached, expected, false));
            const std::size_t context =
                (static_cast<std::size_t>(mask_member_count(fine)) * 4U +
                 cached_relation) *
                    2U +
                ((detector.group_continuity_diagnostic_flags(midi_note) &
                  0x20U) != 0U ? 1U : 0U);
            ++result.physical_group_pending_triple_recovery_frames
                  [recovery_disposition];
            ++result.physical_group_pending_triple_recovery_context_frames
                  [recovery_disposition][context];
            // Deliberately bypass every gate only for error attribution.
            // Labels score this hypothetical cached mask; they never admit it.
            result.physical_group_pending_triple_cached_matched_delta
                [recovery_disposition] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(cached & expected))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(observed & expected)));
            result.physical_group_pending_triple_cached_exact_delta
                [recovery_disposition] += cached == expected ? 1 : 0;
            result.physical_group_pending_triple_cached_wrong_string_delta
                [recovery_disposition] += mask_member_count(
                static_cast<std::uint8_t>(cached & ~expected));
          }
          const FineResidualExpansionEvidence residual_evidence{
              admission.active,
              selection_disposition == static_cast<std::size_t>(
                                           SelectionDisposition::selected),
              admission.direct_fundamental_peak,
              admission.score_threshold_ratio,
              detector.fine_frequency_residual_improvement(
                  static_cast<std::uint8_t>(note)),
              detector.fine_frequency_disposition(
                  static_cast<std::uint8_t>(note)) ==
                  FineFrequencyDisposition::residual_rejected,
              committed,
              detector.fine_frequency_fit_member_mask(
                  static_cast<std::uint8_t>(note)),
              admission.playable_string_mask,
              other_note_lane_mask(snapshot, static_cast<std::uint8_t>(note))};
          std::size_t policy = 0U;
          for (const double score_floor :
               kFineResidualExpansionScoreFloors) {
            for (const double residual_floor :
                 kFineResidualExpansionThresholds) {
              const std::uint8_t projected = bounded_fine_residual_expansion(
                  residual_evidence, score_floor, residual_floor,
                  config.max_polyphony);
              if (projected != 0U) {
                result.fine_residual_expansion_changed_frames[policy] +=
                    projected != observed ? 1U : 0U;
                result.fine_residual_expansion_exact_frames[policy] +=
                    projected == expected ? 1U : 0U;
                result.fine_residual_expansion_matched_delta[policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(projected & expected))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(observed & expected)));
                result.fine_residual_expansion_wrong_string_delta[policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(projected & ~expected))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(observed & ~expected)));
              }
              ++policy;
            }
          }
        }
        ++result.physical_group_expected_observed_mask_frames[
            (static_cast<std::size_t>(expected) << 8U) | observed];
        ++result.physical_group_expected_fine_mask_frames[
            (static_cast<std::size_t>(expected) << 8U) | fine];
        ++result.physical_group_expected_committed_mask_frames[
            (static_cast<std::size_t>(expected) << 8U) | committed];
        if (!note_only) {
          result.physical_group_missing_string_voices +=
              mask_member_count(static_cast<std::uint8_t>(expected & ~observed));
          result.physical_group_extra_string_voices +=
              mask_member_count(static_cast<std::uint8_t>(observed & ~expected));
        }
      }
      std::array<UnisonSpectralFingerprint, 128U> spectral_fingerprints{};
      std::array<SpectralShadowPhase, 128U> spectral_phases{};
      std::array<bool, 128U> spectral_ready{};
      std::array<UnisonSpectralClassification, 128U>
          spectral_shadow_classifications{};
      std::array<UnisonSpectralClassification, 128U>
          spectral_single_classifications{};
      std::array<UnisonSpectralClassification, 128U>
          candidate_unison_classifications{};
      std::array<UnisonSpectralClassification, 128U>
          candidate_single_classifications{};
      std::array<double, 128U> candidate_spectral_single_best_errors{};
      candidate_spectral_single_best_errors.fill(
          std::numeric_limits<double>::infinity());
      std::array<bool, 128U> candidate_unison_ready{};
      std::array<UnisonSpectralFingerprint, 128U>
          observed_spectral_lane_fingerprints{};
      std::array<bool, 128U> observed_spectral_lane_ready{};
      std::array<SpectralShadowPhase, 128U> candidate_unison_phases{};
      std::array<UnisonSpectralSingleScores, 128U> spectral_single_scores{};
      std::array<double, 128U> spectral_single_best_errors{};
      spectral_single_best_errors.fill(
          std::numeric_limits<double>::infinity());
      std::array<std::uint8_t, 128U> spectral_playable_masks{};
      for (std::size_t note = 0U; note < 128U; ++note) {
        observed_spectral_lane_ready[note] =
            detector.observed_spectral_lane_fingerprint(
                static_cast<std::uint8_t>(note),
                observed_spectral_lane_fingerprints[note]);
      }
      for (std::size_t half = 0U; half < spectral_active_notes.size(); ++half) {
        std::uint64_t active = spectral_active_notes[half];
        while (active != 0U) {
#if defined(__GNUC__) || defined(__clang__)
          const std::size_t bit =
              static_cast<std::size_t>(__builtin_ctzll(active));
#else
          std::size_t bit = 0U;
          while (((active >> bit) & 1U) == 0U) {
            ++bit;
          }
#endif
          const std::size_t note = half * 64U + bit;
          spectral_ready[note] = spectral_trackers[note].ready();
          if (spectral_ready[note]) {
            spectral_fingerprints[note] =
                spectral_trackers[note].fingerprint();
            spectral_phases[note] = spectral_trackers[note].phase();
          }
          active &= active - 1U;
        }
      }
      if (spectral_shadow_templates != nullptr) {
        for (std::size_t note = 0U; note < 128U; ++note) {
          if (!spectral_ready[note] || spectral_active_references[note] == 0U) {
            continue;
          }
          const std::size_t phase =
              spectral_phases[note] == SpectralShadowPhase::onset ? 1U : 2U;
          const UnisonSpectralTemplateSet* template_set =
              &spectral_shadow_templates->by_phase[phase][note];
          if (template_set->valid_mask == 0U) {
            template_set = &spectral_shadow_templates->by_phase[0U][note];
          }
          spectral_playable_masks[note] = playable_string_mask(
              static_cast<std::uint8_t>(note), config.max_fret);
          spectral_shadow_classifications[note] = classify_feasible_unison(
              spectral_fingerprints[note], *template_set,
              spectral_playable_masks[note], 2U, 4U);
          spectral_single_classifications[note] =
              classify_single_spectral_source(
                  spectral_fingerprints[note], *template_set,
                  spectral_playable_masks[note]);
          spectral_single_scores[note] = score_single_spectral_sources(
              spectral_fingerprints[note], *template_set,
              spectral_playable_masks[note]);
          for (std::size_t string = 0U; string < kMaxVoices; ++string) {
            if ((spectral_single_scores[note].valid_mask &
                 (1U << string)) == 0U) {
              continue;
            }
            spectral_single_best_errors[note] = std::min(
                spectral_single_best_errors[note],
                spectral_single_scores[note].error[string]);
          }
          for (std::size_t threshold = 0U;
               threshold < kSpectralShadowMarginThresholds.size();
               ++threshold) {
            spectral_onset_latches[note][threshold].observe(
                spectral_phases[note],
                spectral_shadow_classifications[note],
                kSpectralShadowMarginThresholds[threshold]);
          }
        }
      }
      if (spectral_active_notes[0U] != 0U ||
          spectral_active_notes[1U] != 0U) {
        ++result.candidate_population_labeled_snapshots;
        for (std::size_t note = 0U; note < 128U; ++note) {
          const CandidateAdmissionDiagnostics admission =
              detector.candidate_admission_diagnostics(
                  static_cast<std::uint8_t>(note));
          candidate_spectral_admission[note] = admission;
          if (admission.playable_string_mask == 0U) {
            continue;
          }
          const std::size_t target_class =
              spectral_active_references[note] != 0U ? 0U : 1U;
          const std::size_t disposition = static_cast<std::size_t>(
              detector.selection_disposition(
                  static_cast<std::uint8_t>(note)));
          if (disposition >= kSelectionDispositionCount) {
            continue;
          }
          ++result.candidate_population_disposition_frames[target_class]
                                                        [disposition];
          if (disposition ==
              static_cast<std::size_t>(SelectionDisposition::quiet)) {
            continue;
          }
          const std::size_t score_bin =
              candidate_score_ratio_bin(admission.score_threshold_ratio);
          ++result
                .candidate_population_score_threshold_ratio_frames
                    [target_class][score_bin];
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
          const auto spectral_heads = detector.string_fret_spectral_heads(
              static_cast<std::uint8_t>(note));
          ++result.candidate_population_spectral_head_vote_mask_frames
                [target_class][spectral_head_vote_mask(
                    spectral_heads.best_string)];
#endif
          if (disposition == static_cast<std::size_t>(
                                 SelectionDisposition::spectral_rejected) &&
              admission.spectral_shadow_interval == 12 &&
              admission.spectral_shadow_kind == 1U && admission.local_peak &&
              admission.candidate_evidence &&
              !admission.direct_fundamental_peak &&
              admission.best_calibrated_string < kMaxVoices &&
              std::isfinite(admission.best_calibration_similarity) &&
              std::isfinite(admission.second_calibration_similarity)) {
            std::size_t calibration_class = 2U;
            if (target_class == 0U) {
              const std::uint8_t expected_mask =
                  spectral_expected_group_masks[note];
              const std::uint8_t best_string_bit =
                  static_cast<std::uint8_t>(
                      1U << admission.best_calibrated_string);
              calibration_class =
                  spectral_expected_group_note_only[note] ||
                          (expected_mask & best_string_bit) != 0U
                      ? 0U
                      : 1U;
            }
            const double calibration_margin =
                admission.best_calibration_similarity -
                admission.second_calibration_similarity;
            std::size_t policy = 0U;
            for (const double similarity_floor :
                 kSpectralShadowCalibrationSimilarityFloors) {
              for (const double margin_floor :
                   kSpectralShadowCalibrationMarginFloors) {
                if (admission.best_calibration_similarity >=
                        similarity_floor &&
                    calibration_margin >= margin_floor) {
                  ++result
                        .candidate_population_octave_shadow_calibration_frames
                            [policy][calibration_class];
                  if (admission.spectral_shadow_other_eligible_count == 0U &&
                      admission.spectral_shadow_other_active_count == 0U) {
                    ++result
                          .candidate_population_octave_shadow_isolated_context_frames
                              [policy][calibration_class];
                  }
                }
                ++policy;
              }
            }
          }
          if (disposition != static_cast<std::size_t>(
                                 SelectionDisposition::below_threshold)) {
            continue;
          }
          const std::size_t fundamental_bin =
              unit_ratio_bin(admission.fundamental_score_ratio);
          ++result
                .candidate_population_below_threshold_score_ratio_frames
                    [target_class][score_bin];
          ++result
                .candidate_population_below_threshold_fundamental_ratio_frames
                    [target_class][fundamental_bin];
          ++result
                .candidate_population_below_threshold_evidence_flag_frames
                    [target_class]
                    [candidate_admission_evidence_flags(admission)];
          if (admission.direct_fundamental_peak &&
              (admission.local_peak || admission.candidate_evidence)) {
            ++result
                  .candidate_population_below_threshold_direct_evidence_frames
                      [target_class][score_bin][fundamental_bin];
            ++result
                  .candidate_population_below_threshold_pitch_band_peak_frames
                      [target_class]
                      [unit_ratio_bin(
                          admission.pitch_band_score_peak_ratio)]
                      [unit_ratio_bin(
                          admission.pitch_band_fundamental_peak_ratio)];
            if (admission.best_calibrated_string < kMaxVoices &&
                std::isfinite(admission.best_calibration_similarity) &&
                std::isfinite(admission.second_calibration_similarity)) {
              std::size_t calibration_class = 2U;
              if (target_class == 0U) {
                const std::uint8_t expected_mask =
                    spectral_expected_group_masks[note];
                const std::uint8_t best_string_bit =
                    static_cast<std::uint8_t>(
                        1U << admission.best_calibrated_string);
                calibration_class =
                    spectral_expected_group_note_only[note] ||
                            (expected_mask & best_string_bit) != 0U
                        ? 0U
                        : 1U;
              }
              const std::size_t similarity_bin = unit_ratio_bin(
                  admission.best_calibration_similarity);
              const std::size_t margin_bin = calibration_margin_bin(
                  admission.best_calibration_similarity -
                  admission.second_calibration_similarity);
              const std::size_t row =
                  (calibration_class * kCandidateAdmissionRatioBinCount +
                   score_bin) *
                      kCandidateCalibrationSimilarityBinCount +
                  similarity_bin;
              ++result
                    .candidate_population_below_threshold_calibration_joint_frames
                        [row][margin_bin];
              if (mask_member_count(admission.playable_string_mask) == 1U) {
                ++result.candidate_population_unique_playable_direct_frames
                      [calibration_class];
              }
              const double calibration_margin =
                  admission.best_calibration_similarity -
                  admission.second_calibration_similarity;
              std::size_t policy = 0U;
              for (const double global_score_floor :
                   kCandidateBandCalibrationGlobalScoreFloors) {
                for (const double band_score_floor :
                     kCandidateBandCalibrationBandScoreFloors) {
                  for (const double band_fundamental_floor :
                       kCandidateBandCalibrationBandFundamentalFloors) {
                    for (const double similarity_floor :
                         kCandidateBandCalibrationSimilarityFloors) {
                      for (const double margin_floor :
                           kCandidateBandCalibrationMarginFloors) {
                        for (const std::uint8_t minimum_string :
                             kCandidateBandCalibrationMinimumStrings) {
                          for (const bool require_unique_playable :
                               kCandidateBandCalibrationRequireUniquePlayable) {
                            const bool passes =
                                admission.score_threshold_ratio >=
                                    global_score_floor &&
                                admission.fundamental_score_ratio >= 0.60 &&
                                admission.pitch_band_score_peak_ratio >=
                                    band_score_floor &&
                                admission.pitch_band_fundamental_peak_ratio >=
                                    band_fundamental_floor &&
                                admission.best_calibration_similarity >=
                                    similarity_floor &&
                                calibration_margin >= margin_floor &&
                                admission.best_calibrated_string >=
                                    minimum_string &&
                                (!require_unique_playable ||
                                 mask_member_count(
                                     admission.playable_string_mask) == 1U);
                            if (passes) {
                              ++result
                                    .candidate_population_band_calibration_shadow_frames
                                        [policy][calibration_class];
                            }
                            ++policy;
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        if (spectral_shadow_templates != nullptr) {
          std::uint8_t occupied_mask = 0U;
          for (std::size_t voice_index = 0U;
               voice_index < snapshot.voice_count; ++voice_index) {
            const std::uint8_t string =
                snapshot.voices[voice_index].string_index;
            if (string < kMaxVoices) {
              occupied_mask = static_cast<std::uint8_t>(
                  occupied_mask | (1U << string));
            }
          }

          std::array<UnisonSpectralClassification, 128U>
              candidate_classifications{};
          for (std::size_t half = 0U;
               half < candidate_spectral_active_notes.size(); ++half) {
            std::uint64_t active = candidate_spectral_active_notes[half];
            while (active != 0U) {
#if defined(__GNUC__) || defined(__clang__)
              const std::size_t bit =
                  static_cast<std::size_t>(__builtin_ctzll(active));
#else
              std::size_t bit = 0U;
              while (((active >> bit) & 1U) == 0U) {
                ++bit;
              }
#endif
              const std::size_t note = half * 64U + bit;
              const auto& tracker = candidate_spectral_trackers[note];
              if (tracker.ready()) {
                candidate_unison_ready[note] = true;
                candidate_unison_phases[note] = tracker.phase();
                const std::size_t phase =
                    static_cast<std::size_t>(tracker.phase());
                const UnisonSpectralTemplateSet* templates =
                    &spectral_shadow_templates->by_phase[phase][note];
                if (templates->valid_mask == 0U) {
                  templates = &spectral_shadow_templates->by_phase[0U][note];
                }
                candidate_classifications[note] =
                    classify_single_spectral_source(
                        tracker.fingerprint(), *templates,
                        candidate_spectral_admission[note]
                            .playable_string_mask);
                candidate_single_classifications[note] =
                    candidate_classifications[note];
                const auto single_scores = score_single_spectral_sources(
                    tracker.fingerprint(), *templates,
                    candidate_spectral_admission[note]
                        .playable_string_mask);
                for (std::size_t string = 0U; string < kMaxVoices;
                     ++string) {
                  if ((single_scores.valid_mask & (1U << string)) != 0U) {
                    candidate_spectral_single_best_errors[note] = std::min(
                        candidate_spectral_single_best_errors[note],
                        single_scores.error[string]);
                  }
                }
                candidate_unison_classifications[note] =
                    classify_feasible_unison(
                        tracker.fingerprint(), *templates,
                        candidate_spectral_admission[note]
                            .playable_string_mask,
                        2U, 4U);
              }
              active &= active - 1U;
            }
          }

          for (std::size_t note = 0U; note < 127U; ++note) {
            if (!emitted_notes[note] || !emitted_notes[note + 1U]) {
              continue;
            }
            const double left_error =
                candidate_spectral_single_best_errors[note];
            const double right_error =
                candidate_spectral_single_best_errors[note + 1U];
            const std::size_t expected_count =
                static_cast<std::size_t>(expected_notes[note]) +
                static_cast<std::size_t>(expected_notes[note + 1U]);
            const auto pair_class =
                expected_count == 2U
                    ? AdjacentEnvelopePairClass::both_expected
                    : expected_count == 1U
                          ? AdjacentEnvelopePairClass::one_expected
                          : AdjacentEnvelopePairClass::neither_expected;
            double error_gap = std::numeric_limits<double>::quiet_NaN();
            if (std::isfinite(left_error) && std::isfinite(right_error)) {
              if (expected_count == 1U) {
                error_gap = expected_notes[note]
                                ? right_error - left_error
                                : left_error - right_error;
              } else {
                error_gap = std::abs(left_error - right_error);
              }
            }
            ++result.adjacent_spectral_error_gap_frames
                  [static_cast<std::size_t>(pair_class)]
                  [adjacent_spectral_error_gap_bin(error_gap)];
          }
          for (std::size_t policy = 0U;
               policy < kAdjacentSpectralDuplicatePolicies.size(); ++policy) {
            adjacent_spectral_duplicate_projected[policy] =
                adjacent_spectral_duplicate_projection(
                snapshot, candidate_spectral_single_best_errors,
                kAdjacentSpectralDuplicatePolicies[policy],
                result.adjacent_spectral_duplicate_suppression[policy]
                    .changed_voices);
          }

          std::array<std::array<double,
                                kCandidateSpectralShadowGateCount>,
                     kCandidateSpectralShadowPolicyCount>
              best_score{};
          std::array<std::array<std::uint8_t,
                                kCandidateSpectralShadowGateCount>,
                     kCandidateSpectralShadowPolicyCount>
              best_note{};
          std::array<std::array<std::uint8_t,
                                kCandidateSpectralShadowGateCount>,
                     kCandidateSpectralShadowPolicyCount>
              best_member{};
          std::array<double, kCombinedCandidatePolicyCount>
              combined_best_score{};
          std::array<std::uint8_t, kCombinedCandidatePolicyCount>
              combined_best_note{};
          std::array<std::uint8_t, kCombinedCandidatePolicyCount>
              combined_best_member{};
          combined_best_score.fill(
              -std::numeric_limits<double>::infinity());
          combined_best_note.fill(128U);
          for (std::size_t policy = 0U;
               policy < kCandidateSpectralShadowPolicyCount; ++policy) {
            best_score[policy].fill(
                -std::numeric_limits<double>::infinity());
            best_note[policy].fill(128U);
          }

          for (std::size_t note = 0U; note < 128U; ++note) {
            const CandidateAdmissionDiagnostics& admission =
                candidate_spectral_admission[note];
            const std::size_t disposition = static_cast<std::size_t>(
                detector.selection_disposition(
                    static_cast<std::uint8_t>(note)));
            if (disposition != static_cast<std::size_t>(
                                   SelectionDisposition::below_threshold) ||
                admission.playable_string_mask == 0U) {
              continue;
            }
            const std::size_t target_class =
                spectral_active_references[note] != 0U ? 0U : 1U;
            const UnisonSpectralClassification& classification =
                candidate_classifications[note];
            CombinedCandidateAdmissionEvidence combined_evidence;
            combined_evidence.score_threshold_ratio =
                admission.score_threshold_ratio;
            combined_evidence.fundamental_score_ratio =
                admission.fundamental_score_ratio;
            combined_evidence.pitch_band_score_peak_ratio =
                admission.pitch_band_score_peak_ratio;
            combined_evidence.pitch_band_fundamental_peak_ratio =
                admission.pitch_band_fundamental_peak_ratio;
            combined_evidence.best_calibration_similarity =
                admission.best_calibration_similarity;
            combined_evidence.calibration_margin =
                admission.best_calibration_similarity -
                admission.second_calibration_similarity;
            combined_evidence.best_calibrated_string =
                admission.best_calibrated_string;
            combined_evidence.direct_fundamental_peak =
                admission.direct_fundamental_peak;
            combined_evidence.local_or_candidate_peak =
                admission.local_peak || admission.candidate_evidence;
            std::size_t combined_policy = 0U;
            for (const double global_score_floor :
                 kCombinedCandidateGlobalScoreFloors) {
              for (const std::uint8_t minimum_string :
                   kCombinedCandidateMinimumStrings) {
                for (const double maximum_error :
                     kCombinedCandidateSpectralMaximumErrors) {
                  for (const double minimum_margin :
                       kCombinedCandidateSpectralMarginFloors) {
                    const CombinedCandidateAdmissionLimits limits{
                        global_score_floor, minimum_string, maximum_error,
                        minimum_margin};
                    const std::uint8_t member =
                        bounded_combined_candidate_admission(
                            combined_evidence, classification,
                            admission.playable_string_mask, occupied_mask,
                            snapshot.voice_count, config.max_polyphony,
                            limits);
                    const double priority =
                        admission.pitch_band_score_peak_ratio +
                        classification.posterior_margin -
                        classification.error +
                        0.001 * admission.score_threshold_ratio;
                    if (member != 0U &&
                        priority > combined_best_score[combined_policy]) {
                      combined_best_score[combined_policy] = priority;
                      combined_best_note[combined_policy] =
                          static_cast<std::uint8_t>(note);
                      combined_best_member[combined_policy] = member;
                    }
                    ++combined_policy;
                  }
                }
              }
            }
            CandidateSpectralAdmissionEvidence evidence;
            evidence.score_threshold_ratio =
                admission.score_threshold_ratio;
            evidence.fundamental_score_ratio =
                admission.fundamental_score_ratio;
            evidence.direct_fundamental_peak =
                admission.direct_fundamental_peak;
            evidence.local_peak = admission.local_peak;
            evidence.candidate_evidence = admission.candidate_evidence;
            for (std::size_t policy = 0U;
                 policy < kCandidateSpectralShadowPolicyCount; ++policy) {
              CandidateSpectralAdmissionEvidence policy_evidence = evidence;
              if (kCandidateSpectralShadowUsesPitchBand[policy]) {
                if (admission.score_threshold_ratio <
                    kCandidateSpectralShadowLocalGlobalFloor) {
                  continue;
                }
                policy_evidence.score_threshold_ratio =
                    admission.pitch_band_score_peak_ratio;
                policy_evidence.fundamental_score_ratio = std::min(
                    admission.fundamental_score_ratio,
                    admission.pitch_band_fundamental_peak_ratio);
              }
              if (policy_evidence.score_threshold_ratio <
                      kCandidateSpectralShadowScoreFloors[policy] ||
                  policy_evidence.fundamental_score_ratio <
                      kCandidateSpectralShadowFundamentalFloor ||
                  !evidence.direct_fundamental_peak ||
                  (!evidence.local_peak && !evidence.candidate_evidence)) {
                continue;
              }
              ++result.candidate_spectral_shadow_candidate_frames
                    [policy][target_class];
              if (!classification.valid) {
                continue;
              }
              ++result.candidate_spectral_shadow_ready_frames
                    [policy][target_class];
              for (std::size_t error_index = 0U;
                   error_index <
                       kCandidateSpectralShadowErrorThresholdCount;
                   ++error_index) {
                for (std::size_t margin_index = 0U;
                     margin_index <
                         kCandidateSpectralShadowMarginThresholdCount;
                     ++margin_index) {
                  const std::size_t gate =
                      error_index *
                          kCandidateSpectralShadowMarginThresholdCount +
                      margin_index;
                  const CandidateSpectralAdmissionLimits limits{
                      kCandidateSpectralShadowScoreFloors[policy],
                      kCandidateSpectralShadowFundamentalFloor,
                      kCandidateSpectralShadowErrorThresholds[error_index],
                      kCandidateSpectralShadowMarginThresholds[margin_index]};
                  const std::uint8_t member =
                      bounded_candidate_spectral_admission(
                          policy_evidence, classification,
                          admission.playable_string_mask, occupied_mask,
                          snapshot.voice_count, config.max_polyphony, limits);
                  const double priority =
                      kCandidateSpectralShadowUsesPitchBand[policy]
                          ? policy_evidence.score_threshold_ratio +
                                classification.posterior_margin -
                                classification.error +
                                0.001 * admission.score_threshold_ratio
                          : policy_evidence.score_threshold_ratio;
                  if (member == 0U ||
                      priority <= best_score[policy][gate]) {
                    continue;
                  }
                  best_score[policy][gate] = priority;
                  best_note[policy][gate] =
                      static_cast<std::uint8_t>(note);
                  best_member[policy][gate] = member;
                }
              }
            }
          }

          for (std::size_t policy = 0U;
               policy < kCombinedCandidatePolicyCount; ++policy) {
            const std::uint8_t note = combined_best_note[policy];
            if (note >= 128U) {
              continue;
            }
            const std::uint8_t member = combined_best_member[policy];
            std::size_t population_class = 2U;
            if (spectral_active_references[note] != 0U) {
              population_class =
                  spectral_expected_group_note_only[note] ||
                          (spectral_expected_group_masks[note] &
                           member) != 0U
                      ? 0U
                      : 1U;
            }
            ++result.combined_candidate_admission_selected_frames
                  [policy][population_class];
          }

          for (std::size_t policy = 0U;
               policy < kCandidateSpectralShadowPolicyCount; ++policy) {
            for (std::size_t gate = 0U;
                 gate < kCandidateSpectralShadowGateCount; ++gate) {
              const std::uint8_t note = best_note[policy][gate];
              if (note >= 128U) {
                continue;
              }
              ++result.candidate_spectral_shadow_selected_frames
                    [policy][gate];
              const CandidateSpectralPartitionCell partition =
                  candidate_spectral_partition_cell(
                      policy, gate, best_member[policy][gate],
                      spectral_active_references[note] != 0U,
                      spectral_expected_group_masks[note],
                      spectral_expected_group_note_only[note]);
              if (!partition.valid) {
                continue;
              }
              if (partition.classification ==
                  CandidateSpectralPartitionClass::other_false) {
                ++result.candidate_spectral_shadow_other_false_frames
                      [policy][gate];
                ++result
                      .candidate_spectral_shadow_other_false_by_string_frames
                          [partition.row][partition.string];
                const std::size_t interval =
                    candidate_spectral_interval_bucket(
                        note, spectral_active_references);
                if (interval < kCandidateSpectralShadowIntervalBucketCount) {
                  ++result
                        .candidate_spectral_shadow_other_false_interval_frames
                            [partition.row]
                            [interval];
                }
                continue;
              }
              if (partition.classification ==
                  CandidateSpectralPartitionClass::target_correct) {
                ++result.candidate_spectral_shadow_target_correct_frames
                      [policy][gate];
                ++result
                      .candidate_spectral_shadow_target_correct_by_string_frames
                          [partition.row][partition.string];
              } else {
                ++result
                      .candidate_spectral_shadow_target_wrong_string_frames
                          [policy][gate];
                ++result
                      .candidate_spectral_shadow_target_wrong_string_by_string_frames
                          [partition.row][partition.string];
              }
            }
          }

          struct CandidateTrackerRank final {
            double priority{};
            std::uint8_t note{};
          };
          std::array<CandidateTrackerRank, 128U> ranking{};
          std::size_t ranking_count = 0U;
          for (std::size_t note = 0U; note < 128U; ++note) {
            const CandidateAdmissionDiagnostics& admission =
                candidate_spectral_admission[note];
            const bool active =
                (candidate_spectral_active_notes[note / 64U] &
                 (std::uint64_t{1U} << (note % 64U))) != 0U;
            const SelectionDisposition disposition =
                detector.selection_disposition(
                    static_cast<std::uint8_t>(note));
            const bool admitted_active_candidate =
                disposition == SelectionDisposition::selected ||
                (admission.active &&
                 disposition == SelectionDisposition::coasting);
            const bool track_admitted_candidate =
                admitted_active_candidate &&
                spectral_shadow_templates->by_phase[0U][note].valid_mask !=
                    0U;
            const bool direct = admission.direct_fundamental_peak &&
                                (admission.local_peak ||
                                 admission.candidate_evidence);
            const bool retain =
                active && disposition != SelectionDisposition::quiet &&
                (track_admitted_candidate ||
                 (direct &&
                  ((admission.score_threshold_ratio >=
                        kCandidateSpectralTrackingRetainScoreRatio &&
                    admission.fundamental_score_ratio >=
                        kCandidateSpectralTrackingRetainFundamentalRatio) ||
                   (admission.score_threshold_ratio >=
                        kCandidateSpectralTrackingRetainLocalGlobalFloor &&
                    admission.pitch_band_score_peak_ratio >=
                        kCandidateSpectralTrackingRetainBandScoreRatio &&
                    admission.pitch_band_fundamental_peak_ratio >=
                        kCandidateSpectralTrackingRetainBandFundamentalRatio))));
            const bool start =
                !active &&
                (track_admitted_candidate ||
                 (disposition == SelectionDisposition::below_threshold &&
                  direct &&
                  ((admission.score_threshold_ratio >=
                        kCandidateSpectralTrackingStartScoreRatio &&
                    admission.fundamental_score_ratio >=
                        kCandidateSpectralTrackingStartFundamentalRatio) ||
                   (admission.score_threshold_ratio >=
                        kCandidateSpectralTrackingStartLocalGlobalFloor &&
                    admission.pitch_band_score_peak_ratio >=
                        kCandidateSpectralTrackingStartBandScoreRatio &&
                    admission.fundamental_score_ratio >=
                        kCandidateSpectralTrackingStartFundamentalRatio &&
                    admission.pitch_band_fundamental_peak_ratio >=
                        kCandidateSpectralTrackingStartBandFundamentalRatio)) &&
                  spectral_shadow_templates->by_phase[0U][note].valid_mask !=
                      0U));
            if (!retain && !start) {
              continue;
            }
            ranking[ranking_count++] = CandidateTrackerRank{
                std::max(admission.score_threshold_ratio,
                         admission.pitch_band_score_peak_ratio) +
                    (active ? 4.0 : 0.0),
                static_cast<std::uint8_t>(note)};
          }
          std::sort(ranking.begin(), ranking.begin() + ranking_count,
                    [](const CandidateTrackerRank& left,
                       const CandidateTrackerRank& right) {
                      return left.priority > right.priority ||
                             (left.priority == right.priority &&
                              left.note < right.note);
                    });
          std::array<std::uint64_t, 2U> desired{};
          const std::size_t desired_count = std::min(
              ranking_count, kMaximumCandidateSpectralShadowTrackers);
          for (std::size_t index = 0U; index < desired_count; ++index) {
            const std::uint8_t note = ranking[index].note;
            desired[note / 64U] |=
                std::uint64_t{1U} << (note % 64U);
          }
          std::size_t active_count = 0U;
          for (std::size_t note = 0U; note < 128U; ++note) {
            const std::uint64_t bit =
                std::uint64_t{1U} << (note % 64U);
            const bool was_active =
                (candidate_spectral_active_notes[note / 64U] & bit) != 0U;
            bool should_be_active = (desired[note / 64U] & bit) != 0U;
            if (should_be_active && !was_active &&
                !candidate_spectral_trackers[note].configure(
                    candidate_spectral_sample_rate,
                    static_cast<std::uint8_t>(note))) {
              should_be_active = false;
              desired[note / 64U] &= ~bit;
            } else if (!should_be_active && was_active) {
              candidate_spectral_trackers[note].reset();
            }
            active_count += should_be_active ? 1U : 0U;
          }
          candidate_spectral_active_notes = desired;
          result.candidate_spectral_shadow_active_peak = std::max(
              result.candidate_spectral_shadow_active_peak,
              static_cast<std::uint64_t>(active_count));

        }
      } else if (spectral_shadow_templates != nullptr) {
        for (std::size_t note = 0U; note < 128U; ++note) {
          const std::uint64_t bit =
              std::uint64_t{1U} << (note % 64U);
          if ((candidate_spectral_active_notes[note / 64U] & bit) != 0U) {
            candidate_spectral_trackers[note].reset();
          }
        }
        candidate_spectral_active_notes = {};
        candidate_spectral_admission = {};
        candidate_spectral_decimation_sum = 0.0;
        candidate_spectral_decimation_count = 0U;
      }
      for (std::size_t policy = 0U;
           policy < kAdjacentSpectralDuplicatePolicies.size(); ++policy) {
        accumulate_counterfactual_metrics(
            adjacent_spectral_duplicate_projected[policy], sample_index,
            labels, result.adjacent_spectral_duplicate_suppression[policy]);
      }
#endif
      if (calibration != nullptr) {
        for (std::size_t voice_index = 0U;
             voice_index < snapshot.voice_count; ++voice_index) {
          const TunerVoice& voice = snapshot.voices[voice_index];
          bool expected_voice = false;
          for (const ReplayLabel& label : labels) {
            if (sample_index >= label.start_sample &&
                sample_index < label.end_sample &&
                voice_matches_label(voice, label)) {
              expected_voice = true;
              break;
            }
          }
          if (!expected_voice) {
            continue;
          }
          if (voice.string_index >= kMaxVoices ||
              voice.midi_note < kM3OpenNotes[voice.string_index]) {
            continue;
          }
          const std::size_t fret =
              voice.midi_note - kM3OpenNotes[voice.string_index];
          const StringCalibrationPoint* point =
              calibration->point(voice.string_index, fret);
          if (point == nullptr) {
            continue;
          }
          const PartialDetuningEvidence evidence =
              detector.partial_detuning_evidence(voice.midi_note);
          for (std::size_t partial = 1U;
               partial < kPartialDetuningCount; ++partial) {
            const std::uint8_t bit =
                static_cast<std::uint8_t>(1U << partial);
            if ((evidence.valid_mask &
                 point->partial_detuning_valid_mask & bit) == 0U) {
              continue;
            }
            result.partial_detuning_absolute_error_sum += std::abs(
                evidence.residual_cents[partial] -
                static_cast<double>(point->partial_detuning_q8[partial]) /
                    256.0);
            ++result.partial_detuning_comparisons;
          }
          std::array<double, kPartialDetuningCount> expected_reference{};
          for (std::size_t partial = 0U;
               partial < expected_reference.size(); ++partial) {
            expected_reference[partial] =
                static_cast<double>(point->partial_detuning_q8[partial]) /
                256.0;
          }
          const PartialDetuningComparison expected_comparison =
              compare_partial_detuning(
                  evidence, expected_reference,
                  point->partial_detuning_valid_mask);
          double best_other = -std::numeric_limits<double>::infinity();
          if (expected_comparison.valid) {
            for (std::size_t string = 0U; string < kMaxVoices; ++string) {
              if (string == voice.string_index ||
                  voice.midi_note < kM3OpenNotes[string]) {
                continue;
              }
              const std::size_t other_fret =
                  voice.midi_note - kM3OpenNotes[string];
              const StringCalibrationPoint* other =
                  calibration->point(string, other_fret);
              if (other == nullptr) {
                continue;
              }
              std::array<double, kPartialDetuningCount> other_reference{};
              for (std::size_t partial = 0U;
                   partial < other_reference.size(); ++partial) {
                other_reference[partial] =
                    static_cast<double>(other->partial_detuning_q8[partial]) /
                    256.0;
              }
              const PartialDetuningComparison other_comparison =
                  compare_partial_detuning(
                      evidence, other_reference,
                      other->partial_detuning_valid_mask);
              if (other_comparison.valid) {
                best_other =
                    std::max(best_other, other_comparison.log_likelihood);
              }
            }
          }
          if (std::isfinite(best_other)) {
            const double margin =
                expected_comparison.log_likelihood - best_other;
            result.partial_detuning_margin_sum += margin;
            ++result.partial_detuning_margin_frames;
            if (margin >= 0.0) {
              ++result.partial_detuning_expected_best_frames;
            }
          }
        }
      }
      hash_integer(result.fingerprint, sample_index);
      hash_byte(result.fingerprint, static_cast<std::uint8_t>(snapshot.state));
      hash_byte(result.fingerprint, snapshot.voice_count);
      std::size_t snapshot_distinct_note_count = 0U;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      std::size_t snapshot_selected_distinct_note_count = 0U;
#endif
      for (std::size_t voice_index = 0U;
           voice_index < snapshot.voice_count; ++voice_index) {
        bool first = true;
        for (std::size_t previous = 0U; previous < voice_index; ++previous) {
          if (snapshot.voices[previous].midi_note ==
              snapshot.voices[voice_index].midi_note) {
            first = false;
            break;
          }
        }
        snapshot_distinct_note_count += first ? 1U : 0U;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        if (snapshot.voices[voice_index].state !=
            TunerVoiceState::coasting) {
          bool first_selected = true;
          for (std::size_t previous = 0U; previous < voice_index; ++previous) {
            if (snapshot.voices[previous].state !=
                    TunerVoiceState::coasting &&
                snapshot.voices[previous].detected_midi_note ==
                    snapshot.voices[voice_index].detected_midi_note) {
              first_selected = false;
              break;
            }
          }
          snapshot_selected_distinct_note_count += first_selected ? 1U : 0U;
        }
#endif
      }
      for (std::size_t voice_index = 0U;
           voice_index < snapshot.voice_count; ++voice_index) {
        const TunerVoice& voice = snapshot.voices[voice_index];
        hash_byte(result.fingerprint, voice.midi_note);
        hash_integer(result.fingerprint, voice.cents_q8);
        hash_integer(result.fingerprint, voice.confidence_q15);
        hash_integer(result.fingerprint, voice.age_ticks);
        hash_byte(result.fingerprint, static_cast<std::uint8_t>(voice.state));
        hash_byte(result.fingerprint, voice.cents_valid ? 1U : 0U);
        hash_byte(result.fingerprint, voice.string_index);
        hash_byte(result.fingerprint, voice.pitch_evidence_group_id);
        hash_byte(result.fingerprint, voice.pitch_evidence_member_mask);
        hash_integer(result.fingerprint, voice.beat_hz_q8);
      }

#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      for (std::size_t note = 0U; note < 128U; ++note) {
        const bool quiet =
            detector.selection_disposition(static_cast<std::uint8_t>(note)) ==
            SelectionDisposition::quiet;
        const std::uint8_t committed = detector.committed_unison_mask(
            static_cast<std::uint8_t>(note));
        const std::uint8_t fine = detector.fine_frequency_member_mask(
            static_cast<std::uint8_t>(note));
        const std::uint8_t current_assignment = matching_note_lane_mask(
            snapshot, static_cast<std::uint8_t>(note));
        const std::uint8_t members = mask_member_count(committed);
        UnisonReacquisitionState& state =
            unison_reacquisition_states[note];
        const std::uint8_t cached =
            bounded_unison_reacquisition_cache_mask(
                state.resolved_mask, current_assignment, fine, committed,
                quiet);
        if (!quiet && members >= 2U && members <= 4U &&
            current_assignment == committed && cached == committed) {
          const bool group_changed = state.resolved_mask != cached;
          state.resolved_mask = cached;
          state.last_confirmed_sample = sample_index;
          if (observed_spectral_lane_ready[note]) {
            state.confirmed_fingerprint =
                observed_spectral_lane_fingerprints[note];
            state.confirmed_fingerprint_valid = true;
          } else if (group_changed) {
            state.confirmed_fingerprint = {};
            state.confirmed_fingerprint_valid = false;
          }
        }
        if (!quiet && members >= 3U && members <= 4U &&
            current_assignment == committed) {
          UnisonReacquisitionState& committed_cache =
              committed_three_plus_cache_states[note];
          committed_cache.resolved_mask = committed;
          committed_cache.last_confirmed_sample = sample_index;
        }
      }
      std::array<std::array<bool, 128U>,
                 kCalibratedPitchRebinThresholds.size()>
          calibrated_pitch_rebin_latch_seen{};
      std::array<std::array<bool, 128U>,
                 kCalibratedPitchRebinProjectedErrorThresholds.size()>
          calibrated_pitch_rebin_projected_error_latch_seen{};
      std::array<std::array<bool, 128U>, kMultiPartialPhasePolicyCount>
          multi_partial_phase_rebin_latch_seen{};
      std::array<bool, 128U> active_label_notes{};
      std::size_t active_label_distinct_note_count = 0U;
      for (const ReplayLabel& active_label : labels) {
        if (sample_index < active_label.start_sample ||
            sample_index >= active_label.end_sample ||
            active_label_notes[active_label.midi_note]) {
          continue;
        }
        active_label_notes[active_label.midi_note] = true;
        ++active_label_distinct_note_count;
      }
#endif
      for (std::size_t label_index = 0U; label_index < labels.size();
           ++label_index) {
        const ReplayLabel& label = labels[label_index];
        if (sample_index < label.start_sample ||
            sample_index >= label.end_sample) {
          continue;
        }
        ++result.labeled_frames;
        ReplayLabelResult& label_result = result.label_results[label_index];
        LabelTrackingState& tracking = label_tracking[label_index];
        ++label_result.labeled_frames;
        const std::uint8_t observed_lane_mask =
            matching_note_lane_mask(snapshot, label.midi_note);
        const ReplayTargetLaneOutcome lane_outcome =
            classify_target_lane_outcome(observed_lane_mask,
                                         label.string_mask);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        const std::size_t disposition = static_cast<std::size_t>(
            detector.selection_disposition(label.midi_note));
        const CandidateAdmissionDiagnostics admission =
            detector.candidate_admission_diagnostics(label.midi_note);
        std::uint8_t continuity_union_projection = observed_lane_mask;
        label_result.string_fret_onset_strength_max = std::max(
            label_result.string_fret_onset_strength_max,
            admission.string_fret_onset_strength);
        if (sample_index - label.start_sample <= wave.sample_rate / 4U) {
          label_result.string_fret_onset_strength_first_250ms_max = std::max(
              label_result.string_fret_onset_strength_first_250ms_max,
              admission.string_fret_onset_strength);
        }
        if (admission.active) {
          label_result.active_string_fret_onset_strength_max = std::max(
              label_result.active_string_fret_onset_strength_max,
              admission.string_fret_onset_strength);
          if (sample_index - label.start_sample <= wave.sample_rate / 4U) {
            label_result.active_string_fret_onset_strength_first_250ms_max =
                std::max(
                    label_result
                        .active_string_fret_onset_strength_first_250ms_max,
                    admission.string_fret_onset_strength);
          }
        }
        ++label_result.candidate_score_threshold_ratio_frames
              [candidate_score_ratio_bin(admission.score_threshold_ratio)];
        if (disposition ==
            static_cast<std::size_t>(SelectionDisposition::dp_evicted)) {
          const std::size_t true_pitch_count = std::min(
              active_label_distinct_note_count,
              static_cast<std::size_t>(kMaxVoices));
          const std::size_t selected_pitch_count = std::min(
              snapshot_selected_distinct_note_count,
              static_cast<std::size_t>(kMaxVoices));
          const std::size_t playable_lane_count = std::min(
              static_cast<std::size_t>(mask_member_count(
                  admission.playable_string_mask)),
              static_cast<std::size_t>(kMaxVoices));
          ++label_result.candidate_dp_evicted_true_pitch_count_frames
                [true_pitch_count];
          ++label_result.candidate_dp_evicted_selected_pitch_count_frames
                [selected_pitch_count];
          ++label_result.candidate_dp_evicted_score_ratio_frames
                [candidate_score_ratio_bin(admission.score_threshold_ratio)];
          ++label_result.candidate_dp_evicted_evidence_flag_frames
                [candidate_admission_evidence_flags(admission)];
          ++label_result.candidate_dp_evicted_playable_lane_count_frames
                [playable_lane_count];
          const auto lane_relation = [&label](std::uint8_t string) noexcept {
            if (string >= kMaxVoices) {
              return std::size_t{2U};
            }
            return (label.string_mask &
                    static_cast<std::uint8_t>(1U << string)) != 0U
                       ? std::size_t{0U}
                       : std::size_t{1U};
          };
          const std::size_t calibration_relation =
              lane_relation(admission.best_calibrated_string);
          ++label_result.candidate_dp_evicted_calibration_relation_frames
                [calibration_relation];
          ++label_result.candidate_dp_evicted_calibration_similarity_frames
                [calibration_relation][unit_ratio_bin(
                    admission.best_calibration_similarity)];
          ++label_result.candidate_dp_evicted_calibration_margin_frames
                [calibration_relation][unit_ratio_bin(
                    admission.best_calibration_similarity -
                    admission.second_calibration_similarity)];
          const std::uint8_t posterior_string =
              detector.string_fret_posterior_best(label.midi_note);
          const std::size_t posterior_relation =
              lane_relation(posterior_string);
          ++label_result.candidate_dp_evicted_posterior_relation_frames
                [posterior_relation];
          ++label_result.candidate_dp_evicted_posterior_probability_frames
                [posterior_relation][unit_ratio_bin(
                    detector.string_fret_posterior_best_probability(
                        label.midi_note))];
          ++label_result.candidate_dp_evicted_posterior_margin_frames
                [posterior_relation][unit_ratio_bin(
                    detector.string_fret_posterior_margin(
                        label.midi_note))];
        }
        if (disposition < label_result.selection_disposition_frames.size()) {
          ++label_result.selection_disposition_frames[disposition];
          ++label_result.selection_lane_outcome_frames[disposition]
                                                       [static_cast<std::size_t>(
                                                           lane_outcome)];
        }
        const std::size_t continuity_flags =
            detector.group_continuity_diagnostic_flags(label.midi_note);
        if (continuity_flags <
            label_result.group_continuity_diagnostic_frames.size()) {
          ++label_result
                .group_continuity_diagnostic_frames[continuity_flags];
        }
        if (disposition ==
            static_cast<std::size_t>(SelectionDisposition::quiet)) {
          const std::size_t quiet_disposition = static_cast<std::size_t>(
              detector.quiet_disposition());
          if (quiet_disposition <
              label_result.quiet_disposition_frames.size()) {
            ++label_result.quiet_disposition_frames[quiet_disposition];
            if (quiet_disposition == static_cast<std::size_t>(
                                         QuietDisposition::
                                             minimum_evidence_after_signal_floor)) {
              const std::size_t resume_flags =
                  detector.fine_resume_evidence_flags(label.midi_note);
              if (resume_flags <
                  label_result.minimum_evidence_resume_flag_frames.size()) {
                ++label_result.minimum_evidence_resume_flag_frames
                      [resume_flags];
              }
            }
            if (tracking.current_quiet_disposition != quiet_disposition) {
              tracking.current_quiet_disposition = quiet_disposition;
              tracking.current_quiet_disposition_run_frames = 0U;
              ++label_result.quiet_disposition_runs[quiet_disposition];
            }
            ++tracking.current_quiet_disposition_run_frames;
            label_result.longest_quiet_disposition_run_frames
                [quiet_disposition] = std::max(
                label_result.longest_quiet_disposition_run_frames
                    [quiet_disposition],
                tracking.current_quiet_disposition_run_frames);
          }
        } else {
          tracking.current_quiet_disposition = kQuietDispositionCount;
          tracking.current_quiet_disposition_run_frames = 0U;
        }
        const std::uint8_t diagnostic_fine =
            detector.fine_frequency_member_mask(label.midi_note);
        const std::uint8_t diagnostic_committed =
            detector.committed_unison_mask(label.midi_note);
        ReplayFineHistoryCarryDisposition fine_carry =
            ReplayFineHistoryCarryDisposition::selected;
        if (disposition ==
            static_cast<std::size_t>(SelectionDisposition::quiet)) {
          fine_carry = ReplayFineHistoryCarryDisposition::quiet;
        } else if (disposition !=
                   static_cast<std::size_t>(SelectionDisposition::selected)) {
          const std::uint8_t member_count =
              mask_member_count(diagnostic_fine);
          if (!admission.active) {
            fine_carry = ReplayFineHistoryCarryDisposition::inactive;
          } else if (diagnostic_fine == 0U) {
            fine_carry =
                ReplayFineHistoryCarryDisposition::fine_unavailable;
          } else if (member_count < 2U || member_count > 4U) {
            fine_carry = ReplayFineHistoryCarryDisposition::invalid_size;
          } else if (diagnostic_committed != diagnostic_fine) {
            fine_carry = ReplayFineHistoryCarryDisposition::mask_mismatch;
          } else if (admission.score_threshold_ratio < 0.50) {
            fine_carry = ReplayFineHistoryCarryDisposition::below_decay_floor;
          } else if (!admission.direct_fundamental_peak) {
            fine_carry =
                ReplayFineHistoryCarryDisposition::no_direct_fundamental;
          } else {
            fine_carry = ReplayFineHistoryCarryDisposition::eligible;
          }
        }
        const std::size_t fine_carry_disposition =
            static_cast<std::size_t>(fine_carry);
        if (fine_carry_disposition <
            label_result.fine_history_carry_disposition_frames.size()) {
          ++label_result.fine_history_carry_disposition_frames
                [fine_carry_disposition];
        }
        if (spectral_group_leader_indices[label.midi_note] == label_index) {
          const std::uint8_t expected_group =
              spectral_expected_group_masks[label.midi_note];
          const bool group_note_only =
              spectral_expected_group_note_only[label.midi_note];
          const std::uint8_t observed_group =
              matching_note_lane_mask(snapshot, label.midi_note);
          const std::uint8_t fine_group =
              detector.fine_frequency_member_mask(label.midi_note);
          const ReplayTargetLaneOutcome group_outcome =
              group_note_only
                  ? (observed_group == 0U
                         ? ReplayTargetLaneOutcome::absent
                         : ReplayTargetLaneOutcome::exact)
                  : classify_target_lane_outcome(observed_group,
                                                 expected_group);
          const ReplayGroupMaskRelation fine_relation =
              classify_group_mask_relation(fine_group, expected_group,
                                           group_note_only);
          const ReplayClassifierMaskRelation classifier_relation =
              classify_classifier_mask_relation(
                  candidate_unison_classifications[label.midi_note],
                  expected_group, group_note_only);
          const std::size_t joint_cell =
              physical_group_fine_classifier_cell_index(
                  fine_relation, classifier_relation, group_outcome);
          const std::size_t expected_members =
              group_note_only
                  ? 0U
                  : static_cast<std::size_t>(
                        mask_member_count(expected_group));
          ++result.physical_group_fine_classifier_frames[joint_cell];
          ++result.physical_group_member_fine_classifier_frames
                [expected_members][joint_cell];
        }
        if (candidate_unison_ready[label.midi_note]) {
          ++label_result.candidate_unison_spectral_frames;
          const UnisonSpectralClassification& candidate_classification =
              candidate_unison_classifications[label.midi_note];
          if (!candidate_classification.valid) {
            ++label_result.candidate_unison_spectral_invalid_frames;
          } else {
            ++label_result.candidate_unison_spectral_fitted_mask_frames
                  [candidate_classification.member_mask];
          }
        }
        {
          const std::size_t reacquisition_disposition =
              static_cast<std::size_t>(
                  detector.spectral_reacquisition_disposition(
                      label.midi_note));
          if (reacquisition_disposition <
              label_result.spectral_reacquisition_disposition_frames.size()) {
            ++label_result.spectral_reacquisition_disposition_frames
                  [reacquisition_disposition];
            ++label_result.spectral_reacquisition_lane_outcome_frames
                  [reacquisition_disposition]
                  [static_cast<std::size_t>(lane_outcome)];
          }
        }
        {
          const std::size_t refresh_disposition = static_cast<std::size_t>(
              detector.unison_cache_refresh_disposition(label.midi_note));
          if (refresh_disposition <
              label_result.unison_cache_refresh_disposition_frames.size()) {
            ++label_result.unison_cache_refresh_disposition_frames
                  [refresh_disposition];
            ++label_result.unison_cache_refresh_lane_outcome_frames
                  [refresh_disposition]
                  [static_cast<std::size_t>(lane_outcome)];
          }
        }
        {
          const std::uint8_t fine_mask =
              detector.fine_frequency_member_mask(label.midi_note);
          const std::uint8_t profile_mask =
              detector.profile_unison_proposal_mask(label.midi_note);
          const std::uint8_t temporal_mask =
              detector.temporal_unison_proposal_mask(label.midi_note);
          const double beat_coherence =
              detector.fine_frequency_minimum_pairwise_beat_coherence(
                  label.midi_note);
          const std::uint8_t expected_group =
              spectral_expected_group_masks[label.midi_note];
          const UnisonSpectralClassification& candidate_classification =
              candidate_unison_classifications[label.midi_note];
          for (std::size_t threshold = 0U;
               threshold < kSpectralShadowMarginThresholds.size();
               ++threshold) {
            const std::uint8_t projected = bounded_spectral_shadow_proposal(
                observed_lane_mask, fine_mask, beat_coherence, profile_mask,
                temporal_mask, candidate_unison_phases[label.midi_note],
                candidate_classification,
                kSpectralShadowMarginThresholds[threshold]);
            if (projected != observed_lane_mask) {
              ++label_result
                    .candidate_unison_projected_changed_frames[threshold];
            }
            if (lane_mask_matches_label(projected, label)) {
              ++label_result
                    .candidate_unison_projected_matched_frames[threshold];
            }
            if (spectral_group_leader_indices[label.midi_note] ==
                label_index) {
              if (projected == expected_group) {
                ++label_result
                      .candidate_unison_projected_exact_frames[threshold];
              }
              label_result
                  .candidate_unison_projected_wrong_string_voices[threshold] +=
                  mask_member_count(static_cast<std::uint8_t>(
                      projected & static_cast<std::uint8_t>(~expected_group)));
            }
          }
        }
        const UnisonReacquisitionState& reacquisition =
            unison_reacquisition_states[label.midi_note];
        if (reacquisition.resolved_mask != 0U &&
            reacquisition.last_confirmed_sample !=
                std::numeric_limits<std::uint64_t>::max() &&
            sample_index >= reacquisition.last_confirmed_sample) {
          const std::uint64_t age_samples =
              sample_index - reacquisition.last_confirmed_sample;
          const std::uint8_t fine =
              detector.fine_frequency_member_mask(label.midi_note);
          const std::uint8_t committed =
              detector.committed_unison_mask(label.midi_note);
          const double beat_coherence =
              detector.fine_frequency_pairwise_beat_coherence(
                  label.midi_note, fine);
          const bool spectral_group_agreement =
              detector.spectral_tier_completion_proposal_mask(
                  label.midi_note) == reacquisition.resolved_mask;
          const std::uint8_t other_owned =
              other_note_lane_mask(snapshot, label.midi_note);
          const std::uint8_t expected_group =
              spectral_expected_group_masks[label.midi_note];
          for (std::size_t hold = 0U;
               hold < kUnisonReacquisitionHoldSeconds.size(); ++hold) {
            const std::uint64_t maximum_age = static_cast<std::uint64_t>(
                std::ceil(kUnisonReacquisitionHoldSeconds[hold] *
                          static_cast<double>(wave.sample_rate)));
            if (age_samples > maximum_age) {
              continue;
            }
            ++label_result.unison_reacquisition_projected_frames[hold];
            const std::uint8_t projected =
                bounded_unison_reacquisition_projection(
                    observed_lane_mask, reacquisition.resolved_mask, fine,
                    committed, other_owned, admission.playable_string_mask,
                    config.max_polyphony, admission.direct_fundamental_peak,
                    beat_coherence, spectral_group_agreement,
                    disposition == static_cast<std::size_t>(
                                       SelectionDisposition::quiet));
            if (projected != observed_lane_mask) {
              ++label_result.unison_reacquisition_changed_frames[hold];
            }
            const bool observed_matches =
                lane_mask_matches_label(observed_lane_mask, label);
            const bool projected_matches =
                lane_mask_matches_label(projected, label);
            if (projected_matches) {
              ++label_result.unison_reacquisition_matched_frames[hold];
            }
            label_result.unison_reacquisition_matched_delta[hold] +=
                static_cast<std::int64_t>(projected_matches) -
                static_cast<std::int64_t>(observed_matches);
            if (spectral_group_leader_indices[label.midi_note] ==
                label_index) {
              const bool observed_exact = observed_lane_mask == expected_group;
              const bool projected_exact = projected == expected_group;
              if (projected_exact) {
                ++label_result.unison_reacquisition_exact_frames[hold];
              }
              label_result.unison_reacquisition_exact_delta[hold] +=
                  static_cast<std::int64_t>(projected_exact) -
                  static_cast<std::int64_t>(observed_exact);
              const std::int64_t projected_wrong = mask_member_count(
                  static_cast<std::uint8_t>(
                      projected & static_cast<std::uint8_t>(~expected_group)));
              const std::int64_t observed_wrong = mask_member_count(
                  static_cast<std::uint8_t>(observed_lane_mask &
                                            static_cast<std::uint8_t>(
                                                ~expected_group)));
              label_result.unison_reacquisition_wrong_string_voices[hold] +=
                  static_cast<std::uint32_t>(projected_wrong);
              label_result.unison_reacquisition_wrong_string_delta[hold] +=
                  projected_wrong - observed_wrong;
            }
          }
        }
        {
          const bool has_cache =
              reacquisition.resolved_mask != 0U &&
              reacquisition.last_confirmed_sample !=
                  std::numeric_limits<std::uint64_t>::max() &&
              sample_index >= reacquisition.last_confirmed_sample;
          const double cache_age_seconds =
              has_cache
                  ? static_cast<double>(sample_index -
                                        reacquisition.last_confirmed_sample) /
                        static_cast<double>(wave.sample_rate)
                  : std::numeric_limits<double>::infinity();
          const std::uint8_t pending_mask =
              detector.fine_frequency_pending_member_mask(label.midi_note);
          const double pending_seconds =
              detector.fine_frequency_pending_evidence_seconds(
                  label.midi_note);
          const double pending_beat = detector
                                          .fine_frequency_pending_minimum_pairwise_beat_coherence(
                                              label.midi_note);
          const std::uint8_t tier_mask =
              detector.spectral_tier_completion_proposal_mask(
                  label.midi_note);
          const std::uint8_t production_cached_mask =
              detector.group_continuity_cached_mask(label.midi_note);
          const double production_cache_age_seconds =
              detector.group_continuity_cache_age_seconds(label.midi_note);
          const std::uint8_t other_owned =
              other_note_lane_mask(snapshot, label.midi_note);
          const bool current_fingerprint_valid =
              observed_spectral_lane_ready[label.midi_note];
          const UnisonSpectralFingerprint current_fingerprint =
              current_fingerprint_valid
                  ? observed_spectral_lane_fingerprints[label.midi_note]
                  : UnisonSpectralFingerprint{};
          const std::uint8_t continuity_fine_mask =
              detector.fine_frequency_member_mask(label.midi_note);
          const std::uint8_t continuity_committed_mask =
              detector.committed_unison_mask(label.midi_note);
          const double continuity_beat =
              detector.fine_frequency_pairwise_beat_coherence(
                  label.midi_note, continuity_fine_mask);
          const bool continuity_quiet =
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::quiet);
          const bool continuity_tier_agrees =
              tier_mask == reacquisition.resolved_mask;
          const std::uint8_t settled_projection =
              has_cache && cache_age_seconds <= 0.05
                  ? bounded_unison_reacquisition_projection(
                        observed_lane_mask, reacquisition.resolved_mask,
                        continuity_fine_mask, continuity_committed_mask,
                        other_owned, admission.playable_string_mask,
                        config.max_polyphony,
                        admission.direct_fundamental_peak, continuity_beat,
                        continuity_tier_agrees, continuity_quiet)
                  : observed_lane_mask;
          const ArticulatedUnisonReacquisitionResult
              articulated_projection =
                  bounded_articulated_unison_reacquisition_projection(
                      observed_lane_mask, reacquisition.resolved_mask,
                      pending_mask, pending_seconds, pending_beat, tier_mask,
                      other_owned, admission.playable_string_mask,
                      config.max_polyphony,
                      admission.direct_fundamental_peak, continuity_quiet,
                      cache_age_seconds, 0.25, 0.20);
          continuity_union_projection =
              bounded_three_four_member_projection_union(
                  observed_lane_mask, reacquisition.resolved_mask,
                  settled_projection, articulated_projection.projected_mask);
          if (continuity_union_projection != observed_lane_mask) {
            ++label_result.continuity_union_changed_frames;
          }
          const bool continuity_observed_matches =
              lane_mask_matches_label(observed_lane_mask, label);
          const bool continuity_union_matches =
              lane_mask_matches_label(continuity_union_projection, label);
          if (continuity_union_matches) {
            ++label_result.continuity_union_matched_frames;
          }
          label_result.continuity_union_matched_delta +=
              static_cast<std::int64_t>(continuity_union_matches) -
              static_cast<std::int64_t>(continuity_observed_matches);
          if (spectral_group_leader_indices[label.midi_note] == label_index) {
            const std::uint8_t continuity_expected_group =
                spectral_expected_group_masks[label.midi_note];
            const bool continuity_observed_exact =
                observed_lane_mask == continuity_expected_group;
            const bool continuity_union_exact =
                continuity_union_projection == continuity_expected_group;
            if (continuity_union_exact) {
              ++label_result.continuity_union_exact_frames;
            }
            label_result.continuity_union_exact_delta +=
                static_cast<std::int64_t>(continuity_union_exact) -
                static_cast<std::int64_t>(continuity_observed_exact);
            label_result.continuity_union_wrong_string_delta +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        continuity_union_projection & static_cast<std::uint8_t>(
                                               ~continuity_expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask & static_cast<std::uint8_t>(
                                                 ~continuity_expected_group))));
          }
          std::size_t policy = 0U;
          for (const double maximum_gap :
               kArticulatedUnisonReacquisitionGapSeconds) {
            for (const double minimum_revalidation :
                 kArticulatedUnisonReacquisitionRevalidationSeconds) {
              if (has_cache && cache_age_seconds <= maximum_gap) {
                ++label_result
                      .articulated_unison_reacquisition_eligible_frames
                          [policy];
              }
              const ArticulatedUnisonReacquisitionResult projection =
                  bounded_articulated_unison_reacquisition_projection(
                      observed_lane_mask, reacquisition.resolved_mask,
                      pending_mask, pending_seconds, pending_beat, tier_mask,
                      other_owned, admission.playable_string_mask,
                      config.max_polyphony,
                      admission.direct_fundamental_peak,
                      disposition == static_cast<std::size_t>(
                                         SelectionDisposition::quiet),
                      cache_age_seconds, maximum_gap,
                      minimum_revalidation);
              const ArticulatedUnisonReacquisitionResult
                  three_member_projection =
                      bounded_three_member_articulated_unison_reacquisition_projection(
                          observed_lane_mask, reacquisition.resolved_mask,
                          pending_mask, pending_seconds, pending_beat,
                          tier_mask, other_owned,
                          admission.playable_string_mask,
                          config.max_polyphony,
                          admission.direct_fundamental_peak,
                          disposition == static_cast<std::size_t>(
                                             SelectionDisposition::quiet),
                          cache_age_seconds, maximum_gap,
                          minimum_revalidation);
              const ArticulatedUnisonReacquisitionResult
                  production_three_member_projection =
                      bounded_three_member_articulated_unison_reacquisition_projection(
                          observed_lane_mask, production_cached_mask,
                          pending_mask, pending_seconds, pending_beat,
                          tier_mask, other_owned,
                          admission.playable_string_mask,
                          config.max_polyphony,
                          admission.direct_fundamental_peak,
                          disposition == static_cast<std::size_t>(
                                             SelectionDisposition::quiet),
                          production_cache_age_seconds, maximum_gap,
                          minimum_revalidation);
              const ArticulatedUnisonReacquisitionResult
                  solo_three_member_projection =
                      other_owned == 0U &&
                              production_cached_mask ==
                                  admission.playable_string_mask
                          ? production_three_member_projection
                          : ArticulatedUnisonReacquisitionResult{
                                observed_lane_mask,
                                ArticulatedUnisonReacquisitionDisposition::
                                    ownership_conflict};
              const std::size_t projection_disposition =
                  static_cast<std::size_t>(projection.disposition);
              if (projection_disposition <
                  kArticulatedUnisonReacquisitionDispositionCount) {
                ++label_result
                      .articulated_unison_reacquisition_disposition_frames
                          [policy][projection_disposition];
                const bool group_leader =
                    spectral_group_leader_indices[label.midi_note] ==
                    label_index;
                const ArticulatedUnisonReacquisitionCounterfactual
                    counterfactual = articulated_reacquisition_counterfactual(
                        observed_lane_mask, reacquisition.resolved_mask,
                        label.string_mask,
                        spectral_expected_group_masks[label.midi_note],
                        group_leader);
                label_result
                    .articulated_unison_reacquisition_counterfactual_matched_delta
                        [policy][projection_disposition] +=
                    counterfactual.matched_delta;
                label_result
                    .articulated_unison_reacquisition_counterfactual_exact_delta
                        [policy][projection_disposition] +=
                    counterfactual.exact_delta;
                label_result
                    .articulated_unison_reacquisition_counterfactual_wrong_string_delta
                        [policy][projection_disposition] +=
                    counterfactual.wrong_string_delta;
              }
              if (projection.disposition ==
                  ArticulatedUnisonReacquisitionDisposition::accepted) {
                ++label_result
                      .articulated_unison_reacquisition_projected_frames
                          [policy];
                if (policy == 0U) {
                  ++label_result
                        .articulated_unison_reacquisition_accepted_cache_mask_frames
                            [reacquisition.resolved_mask];
                }
              }
              const bool observed_matches =
                  lane_mask_matches_label(observed_lane_mask, label);
              if (three_member_projection.projected_mask !=
                  observed_lane_mask) {
                ++label_result
                      .three_member_articulated_reacquisition_changed_frames
                          [policy];
              }
              label_result
                  .three_member_articulated_reacquisition_matched_delta
                      [policy] +=
                  static_cast<std::int64_t>(lane_mask_matches_label(
                      three_member_projection.projected_mask, label)) -
                  static_cast<std::int64_t>(observed_matches);
              if (spectral_group_leader_indices[label.midi_note] ==
                  label_index) {
                const std::uint8_t expected_group =
                    spectral_expected_group_masks[label.midi_note];
                label_result
                    .three_member_articulated_reacquisition_exact_delta
                        [policy] +=
                    static_cast<std::int64_t>(
                        three_member_projection.projected_mask ==
                        expected_group) -
                    static_cast<std::int64_t>(
                        observed_lane_mask == expected_group);
                label_result
                    .three_member_articulated_reacquisition_wrong_string_delta
                        [policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            three_member_projection.projected_mask &
                            static_cast<std::uint8_t>(~expected_group)))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            observed_lane_mask &
                            static_cast<std::uint8_t>(~expected_group))));
              }
              if (production_three_member_projection.projected_mask !=
                  observed_lane_mask) {
                ++label_result
                      .production_three_member_articulated_reacquisition_changed_frames
                          [policy];
              }
              label_result
                  .production_three_member_articulated_reacquisition_matched_delta
                      [policy] +=
                  static_cast<std::int64_t>(lane_mask_matches_label(
                      production_three_member_projection.projected_mask,
                      label)) -
                  static_cast<std::int64_t>(observed_matches);
              if (spectral_group_leader_indices[label.midi_note] ==
                  label_index) {
                const std::uint8_t expected_group =
                    spectral_expected_group_masks[label.midi_note];
                label_result
                    .production_three_member_articulated_reacquisition_exact_delta
                        [policy] +=
                    static_cast<std::int64_t>(
                        production_three_member_projection.projected_mask ==
                        expected_group) -
                    static_cast<std::int64_t>(
                        observed_lane_mask == expected_group);
                label_result
                    .production_three_member_articulated_reacquisition_wrong_string_delta
                        [policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            production_three_member_projection.projected_mask &
                            static_cast<std::uint8_t>(~expected_group)))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            observed_lane_mask &
                            static_cast<std::uint8_t>(~expected_group))));
              }
              if (solo_three_member_projection.projected_mask !=
                  observed_lane_mask) {
                ++label_result
                      .solo_three_member_articulated_reacquisition_changed_frames
                          [policy];
              }
              label_result
                  .solo_three_member_articulated_reacquisition_matched_delta
                      [policy] +=
                  static_cast<std::int64_t>(lane_mask_matches_label(
                      solo_three_member_projection.projected_mask, label)) -
                  static_cast<std::int64_t>(observed_matches);
              if (spectral_group_leader_indices[label.midi_note] ==
                  label_index) {
                const std::uint8_t expected_group =
                    spectral_expected_group_masks[label.midi_note];
                label_result
                    .solo_three_member_articulated_reacquisition_exact_delta
                        [policy] +=
                    static_cast<std::int64_t>(
                        solo_three_member_projection.projected_mask ==
                        expected_group) -
                    static_cast<std::int64_t>(
                        observed_lane_mask == expected_group);
                label_result
                    .solo_three_member_articulated_reacquisition_wrong_string_delta
                        [policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            solo_three_member_projection.projected_mask &
                            static_cast<std::uint8_t>(~expected_group)))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            observed_lane_mask &
                            static_cast<std::uint8_t>(~expected_group))));
              }
              std::size_t fingerprint_policy =
                  policy * kObservedFingerprintMaximumSquaredDistances.size();
              for (const double maximum_distance :
                   kObservedFingerprintMaximumSquaredDistances) {
                const ArticulatedUnisonReacquisitionResult
                    fingerprint_projection =
                        bounded_observed_fingerprint_reacquisition_projection(
                            projection, observed_lane_mask,
                            reacquisition.confirmed_fingerprint,
                            reacquisition.confirmed_fingerprint_valid,
                            current_fingerprint, current_fingerprint_valid,
                            maximum_distance);
                const std::size_t fingerprint_disposition =
                    static_cast<std::size_t>(
                        fingerprint_projection.disposition);
                if (fingerprint_disposition <
                    kArticulatedUnisonReacquisitionDispositionCount) {
                  ++label_result
                        .observed_fingerprint_reacquisition_disposition_frames
                            [fingerprint_policy][fingerprint_disposition];
                }
                if (fingerprint_projection.disposition ==
                    ArticulatedUnisonReacquisitionDisposition::accepted) {
                  ++label_result
                        .observed_fingerprint_reacquisition_projected_frames
                            [fingerprint_policy];
                  if (fingerprint_policy ==
                          kObservedFingerprintProductionCandidatePolicy &&
                      disposition <
                          label_result
                              .observed_fingerprint_reacquisition_selection_frames
                              .size()) {
                    ++label_result
                          .observed_fingerprint_reacquisition_selection_frames
                              [disposition];
                  }
                }
                if (fingerprint_projection.projected_mask !=
                    observed_lane_mask) {
                  ++label_result
                        .observed_fingerprint_reacquisition_changed_frames
                            [fingerprint_policy];
                  if (fingerprint_policy ==
                      kObservedFingerprintProductionCandidatePolicy) {
                    const std::uint8_t expected_group =
                        spectral_expected_group_masks[label.midi_note];
                    const auto diagnostic =
                        diagnose_observed_fingerprint_changed_frame(
                            diagnostic_committed, expected_group,
                            snapshot.voice_count, other_owned);
                    ++label_result
                          .observed_fingerprint_changed_committed_relation_frames
                              [static_cast<std::size_t>(
                                  diagnostic.committed_relation)];
                    ++label_result
                          .observed_fingerprint_changed_committed_member_count_frames
                              [diagnostic.committed_member_count];
                    ++label_result
                          .observed_fingerprint_changed_snapshot_voice_count_frames
                              [diagnostic.snapshot_voice_count];
                    ++label_result
                          .observed_fingerprint_changed_other_owned_lane_count_frames
                              [diagnostic.other_owned_lane_count];
                    const std::size_t production_disposition =
                        static_cast<std::size_t>(
                            detector.spectral_reacquisition_disposition(
                                label.midi_note));
                    if (production_disposition <
                        label_result
                            .observed_fingerprint_changed_production_disposition_frames
                            .size()) {
                      ++label_result
                            .observed_fingerprint_changed_production_disposition_frames
                                [production_disposition];
                    }
                    const double production_cache_age =
                        detector.unison_reacquisition_cache_age_seconds(
                            label.midi_note);
                    const std::size_t production_cache_age_bin =
                        std::isfinite(production_cache_age) &&
                                production_cache_age >= 0.0
                            ? std::min<std::size_t>(
                                  static_cast<std::size_t>(
                                      production_cache_age / 0.05),
                                  120U)
                            : 120U;
                    ++label_result
                          .observed_fingerprint_changed_production_cache_age_50ms_frames
                              [production_cache_age_bin];
                    ++label_result
                          .observed_fingerprint_changed_production_cache_mask_frames
                              [detector.unison_reacquisition_cache_mask(
                                  label.midi_note)];
                    const std::size_t score_ratio_bin =
                        std::isfinite(admission.score_threshold_ratio) &&
                                admission.score_threshold_ratio >= 0.0
                            ? std::min<std::size_t>(
                                  static_cast<std::size_t>(
                                      admission.score_threshold_ratio / 0.05),
                                  20U)
                            : 20U;
                    ++label_result
                          .observed_fingerprint_changed_score_threshold_ratio_05_frames
                              [score_ratio_bin];
                    ++label_result
                          .observed_fingerprint_changed_direct_fundamental_frames
                              [admission.direct_fundamental_peak ? 1U : 0U];
                  }
                }
                const bool fingerprint_matches = lane_mask_matches_label(
                    fingerprint_projection.projected_mask, label);
                if (fingerprint_matches) {
                  ++label_result
                        .observed_fingerprint_reacquisition_matched_frames
                            [fingerprint_policy];
                }
                label_result
                    .observed_fingerprint_reacquisition_matched_delta
                        [fingerprint_policy] +=
                    static_cast<std::int64_t>(fingerprint_matches) -
                    static_cast<std::int64_t>(observed_matches);
                if (spectral_group_leader_indices[label.midi_note] ==
                    label_index) {
                  const std::uint8_t expected_group =
                      spectral_expected_group_masks[label.midi_note];
                  const bool observed_exact =
                      observed_lane_mask == expected_group;
                  const bool fingerprint_exact =
                      fingerprint_projection.projected_mask == expected_group;
                  if (fingerprint_exact) {
                    ++label_result
                          .observed_fingerprint_reacquisition_exact_frames
                              [fingerprint_policy];
                  }
                  label_result
                      .observed_fingerprint_reacquisition_exact_delta
                          [fingerprint_policy] +=
                      static_cast<std::int64_t>(fingerprint_exact) -
                      static_cast<std::int64_t>(observed_exact);
                  const std::int64_t fingerprint_wrong = mask_member_count(
                      static_cast<std::uint8_t>(
                          fingerprint_projection.projected_mask &
                          static_cast<std::uint8_t>(~expected_group)));
                  const std::int64_t observed_wrong = mask_member_count(
                      static_cast<std::uint8_t>(
                          observed_lane_mask &
                          static_cast<std::uint8_t>(~expected_group)));
                  label_result
                      .observed_fingerprint_reacquisition_wrong_string_voices
                          [fingerprint_policy] +=
                      static_cast<std::uint32_t>(fingerprint_wrong);
                  label_result
                      .observed_fingerprint_reacquisition_wrong_string_delta
                          [fingerprint_policy] +=
                      fingerprint_wrong - observed_wrong;
                }
                ++fingerprint_policy;
              }
              if (projection.projected_mask != observed_lane_mask) {
                ++label_result
                      .articulated_unison_reacquisition_changed_frames
                          [policy];
              }
              const bool projected_matches = lane_mask_matches_label(
                  projection.projected_mask, label);
              if (projected_matches) {
                ++label_result
                      .articulated_unison_reacquisition_matched_frames
                          [policy];
              }
              label_result
                  .articulated_unison_reacquisition_matched_delta[policy] +=
                  static_cast<std::int64_t>(projected_matches) -
                  static_cast<std::int64_t>(observed_matches);
              if (spectral_group_leader_indices[label.midi_note] ==
                  label_index) {
                const std::uint8_t expected_group =
                    spectral_expected_group_masks[label.midi_note];
                const bool observed_exact =
                    observed_lane_mask == expected_group;
                const bool projected_exact =
                    projection.projected_mask == expected_group;
                if (projected_exact) {
                  ++label_result
                        .articulated_unison_reacquisition_exact_frames
                            [policy];
                }
                label_result
                    .articulated_unison_reacquisition_exact_delta[policy] +=
                    static_cast<std::int64_t>(projected_exact) -
                    static_cast<std::int64_t>(observed_exact);
                const std::int64_t projected_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        projection.projected_mask &
                        static_cast<std::uint8_t>(~expected_group)));
                const std::int64_t observed_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group)));
                label_result
                    .articulated_unison_reacquisition_wrong_string_voices
                        [policy] +=
                    static_cast<std::uint32_t>(projected_wrong);
                label_result
                    .articulated_unison_reacquisition_wrong_string_delta
                        [policy] += projected_wrong - observed_wrong;
              }
              ++policy;
            }
          }
        }
        if (disposition ==
            static_cast<std::size_t>(SelectionDisposition::below_threshold)) {
          const std::size_t score_bin =
              candidate_score_ratio_bin(admission.score_threshold_ratio);
          const std::size_t fundamental_bin =
              unit_ratio_bin(admission.fundamental_score_ratio);
          ++label_result.candidate_below_threshold_score_ratio_frames
                [score_bin];
          ++label_result.candidate_below_threshold_fundamental_ratio_frames
                [fundamental_bin];
          ++label_result.candidate_below_threshold_evidence_flag_frames
                [candidate_admission_evidence_flags(admission)];
          if (admission.direct_fundamental_peak &&
              (admission.local_peak || admission.candidate_evidence)) {
            ++label_result
                  .candidate_below_threshold_direct_evidence_frames[score_bin]
                                                                    [fundamental_bin];
            ++label_result
                  .candidate_below_threshold_pitch_band_peak_frames
                      [unit_ratio_bin(
                          admission.pitch_band_score_peak_ratio)]
                      [unit_ratio_bin(
                          admission.pitch_band_fundamental_peak_ratio)];
          }
          const std::size_t best_string =
              admission.best_calibrated_string < kMaxVoices
                  ? admission.best_calibrated_string
                  : kMaxVoices;
          ++label_result
                .candidate_below_threshold_calibration_best_string_frames
                    [best_string];
          const bool calibration_matches_expected =
              label.string_mask != 0U && best_string < kMaxVoices &&
              (label.string_mask & (1U << best_string)) != 0U;
          auto& similarity_bins =
              calibration_matches_expected
                  ? label_result
                        .candidate_below_threshold_calibration_correct_similarity_frames
                  : label_result
                        .candidate_below_threshold_calibration_other_similarity_frames;
          auto& margin_bins =
              calibration_matches_expected
                  ? label_result
                        .candidate_below_threshold_calibration_correct_margin_frames
                  : label_result
                        .candidate_below_threshold_calibration_other_margin_frames;
          ++similarity_bins[unit_ratio_bin(
              admission.best_calibration_similarity)];
          ++margin_bins[calibration_margin_bin(
              admission.best_calibration_similarity -
              admission.second_calibration_similarity)];
          ++label_result
                .candidate_below_threshold_calibration_relation_margin_frames
                    [calibration_matches_expected ? 0U : 1U]
                    [unit_ratio_bin(
                        admission.best_calibration_similarity -
                        admission.second_calibration_similarity)];
        }
        if (disposition == static_cast<std::size_t>(
                               SelectionDisposition::spectral_rejected)) {
          const std::size_t fundamental_bin =
              unit_ratio_bin(admission.fundamental_score_ratio);
          ++label_result
                .candidate_spectral_rejected_fundamental_ratio_frames
                    [fundamental_bin];
          ++label_result
                .candidate_spectral_rejected_evidence_flag_frames
                    [candidate_admission_evidence_flags(admission)];
          const std::size_t best_string =
              admission.best_calibrated_string < kMaxVoices
                  ? admission.best_calibrated_string
                  : kMaxVoices;
          ++label_result
                .candidate_spectral_rejected_calibration_best_string_frames
                    [best_string];
          const int interval =
              static_cast<int>(admission.spectral_shadow_interval);
          if (interval >= -static_cast<int>(kMaxCandidates) &&
              interval <= static_cast<int>(kMaxCandidates)) {
            ++label_result
                  .candidate_spectral_rejected_shadow_interval_frames
                      [static_cast<std::size_t>(
                          interval + static_cast<int>(kMaxCandidates))];
          }
          ++label_result
                .candidate_spectral_rejected_shadow_fundamental_ratio_frames
                    [unit_ratio_bin(
                        admission.spectral_shadow_fundamental_ratio)];
          const std::size_t shadow_kind =
              std::min<std::size_t>(
                  admission.spectral_shadow_kind,
                  label_result
                          .candidate_spectral_rejected_shadow_kind_frames
                          .size() -
                      1U);
          ++label_result
                .candidate_spectral_rejected_shadow_kind_frames[shadow_kind];
          ++label_result
                .candidate_spectral_rejected_shadow_other_eligible_frames
                    [std::min<std::size_t>(
                        admission.spectral_shadow_other_eligible_count,
                        kMaxCandidates)];
          ++label_result
                .candidate_spectral_rejected_shadow_other_active_frames
                    [std::min<std::size_t>(
                        admission.spectral_shadow_other_active_count,
                        kMaxCandidates)];
          const int strongest_other_interval = static_cast<int>(
              admission.spectral_shadow_strongest_other_interval);
          const std::size_t strongest_other_bin =
              strongest_other_interval >= -static_cast<int>(kMaxCandidates) &&
                      strongest_other_interval <=
                          static_cast<int>(kMaxCandidates)
                  ? static_cast<std::size_t>(
                        strongest_other_interval +
                        static_cast<int>(kMaxCandidates))
                  : kSpectralShadowIntervalBinCount;
          ++label_result
                .candidate_spectral_rejected_shadow_strongest_other_interval_frames
                    [strongest_other_bin];
          ++label_result
                .candidate_spectral_rejected_shadow_strongest_other_evidence_frames
                    [std::min<std::size_t>(
                        admission.spectral_shadow_strongest_other_evidence,
                        31U)];
          const bool calibration_matches_expected =
              label.string_mask != 0U && best_string < kMaxVoices &&
              (label.string_mask & (1U << best_string)) != 0U;
          ++label_result
                .candidate_spectral_rejected_calibration_relation_fundamental_frames
                    [calibration_matches_expected ? 0U : 1U]
                    [fundamental_bin];
          auto& similarity_bins =
              calibration_matches_expected
                  ? label_result
                        .candidate_spectral_rejected_calibration_correct_similarity_frames
                  : label_result
                        .candidate_spectral_rejected_calibration_other_similarity_frames;
          auto& margin_bins =
              calibration_matches_expected
                  ? label_result
                        .candidate_spectral_rejected_calibration_correct_margin_frames
                  : label_result
                        .candidate_spectral_rejected_calibration_other_margin_frames;
          ++similarity_bins[unit_ratio_bin(
              admission.best_calibration_similarity)];
          ++margin_bins[calibration_margin_bin(
              admission.best_calibration_similarity -
              admission.second_calibration_similarity)];
        }
        const std::size_t retained_disposition = static_cast<std::size_t>(
            detector.retained_unison_disposition(label.midi_note));
        if (retained_disposition <
            label_result.retained_unison_disposition_frames.size()) {
          ++label_result
                .retained_unison_disposition_frames[retained_disposition];
        }
        const std::size_t fine_group_disposition = static_cast<std::size_t>(
            detector.fine_group_disposition(label.midi_note));
        if (fine_group_disposition <
            label_result.fine_group_disposition_frames.size()) {
          ++label_result
                .fine_group_disposition_frames[fine_group_disposition];
          const double fine_group_beat_coherence = std::clamp(
              detector.fine_frequency_minimum_pairwise_beat_coherence(
                  label.midi_note),
              0.0, 1.0);
          const std::size_t fine_group_beat_bin =
              static_cast<std::size_t>(std::min(
                  20.0, std::floor(fine_group_beat_coherence * 20.0)));
          ++label_result.fine_group_disposition_beat_coherence_bins
                [fine_group_disposition][fine_group_beat_bin];
        }
        const std::uint8_t committed_mask =
            detector.committed_unison_mask(label.midi_note);
        ++label_result.committed_unison_mask_frames[committed_mask];
        const ReplayTargetLaneOutcome committed_outcome =
            classify_target_lane_outcome(committed_mask, label.string_mask);
        ++label_result.committed_unison_lane_outcome_frames
              [static_cast<std::size_t>(committed_outcome)]
              [static_cast<std::size_t>(lane_outcome)];
        label_result.maximum_committed_unison_gap_ticks = std::max(
            label_result.maximum_committed_unison_gap_ticks,
            detector.committed_unison_gap_ticks(label.midi_note));
        if (label.string_mask != 0U &&
            committed_mask == label.string_mask &&
            retained_disposition <
                label_result
                    .committed_exact_retained_unison_disposition_frames
                    .size()) {
          ++label_result
                .committed_exact_retained_unison_disposition_frames
                    [retained_disposition];
          const std::uint8_t committed_members =
              mask_member_count(committed_mask);
          if (committed_members >= 2U && committed_members <= 4U) {
            std::array<double, 1U << kMaxVoices> pair_coherence{};
            for (std::size_t left = 0U; left < kMaxVoices; ++left) {
              const std::uint8_t left_bit =
                  static_cast<std::uint8_t>(1U << left);
              if ((committed_mask & left_bit) == 0U) {
                continue;
              }
              for (std::size_t right = left + 1U; right < kMaxVoices;
                   ++right) {
                const std::uint8_t right_bit =
                    static_cast<std::uint8_t>(1U << right);
                if ((committed_mask & right_bit) == 0U) {
                  continue;
                }
                const std::uint8_t pair =
                    static_cast<std::uint8_t>(left_bit | right_bit);
                pair_coherence[pair] =
                    detector.fine_frequency_pairwise_beat_coherence(
                        label.midi_note, pair);
              }
            }
            const ReplayPairwiseBeatSupport support =
                summarize_pairwise_beat_support(committed_mask,
                                                pair_coherence, 0.20);
            const std::size_t above = std::min<std::size_t>(
                support.above_gate_count,
                label_result
                        .committed_exact_pairwise_beat_above_gate_frames
                            [retained_disposition]
                        .size() -
                    1U);
            ++label_result
                  .committed_exact_pairwise_beat_above_gate_frames
                      [retained_disposition][above];
            if (support.connected) {
              ++label_result
                    .committed_exact_pairwise_beat_connected_frames
                        [retained_disposition];
            }
          }
          for (std::size_t reason = 0U;
               reason < tracking
                            .current_committed_exact_retained_disposition_run_frames
                            .size();
               ++reason) {
            auto& current = tracking
                                .current_committed_exact_retained_disposition_run_frames
                                    [reason];
            if (reason == retained_disposition) {
              ++current;
              label_result
                  .longest_committed_exact_retained_disposition_run_frames
                      [reason] =
                  std::max(label_result
                               .longest_committed_exact_retained_disposition_run_frames
                                   [reason],
                           current);
            } else {
              current = 0U;
            }
          }
        } else {
          tracking
              .current_committed_exact_retained_disposition_run_frames.fill(
                  0U);
        }
        const std::size_t fine_member_mask =
            detector.fine_frequency_member_mask(label.midi_note);
        if (fine_member_mask <
            label_result.fine_frequency_member_mask_frames.size()) {
          ++label_result
                .fine_frequency_member_mask_frames[fine_member_mask];
          label_result.fine_frequency_member_mask_residual_sum
              [fine_member_mask] +=
              std::clamp(
                  detector.fine_frequency_residual_improvement(
                      label.midi_note),
                  0.0, 1.0);
          label_result.fine_frequency_member_mask_minimum_ratio_sum
              [fine_member_mask] +=
              detector.fine_frequency_minimum_member_ratio(label.midi_note);
          label_result.fine_frequency_member_mask_minimum_beat_coherence_sum
              [fine_member_mask] +=
              detector.fine_frequency_minimum_pairwise_beat_coherence(
                  label.midi_note);
          const double beat_coherence = std::clamp(
              detector.fine_frequency_minimum_pairwise_beat_coherence(
                  label.midi_note),
              0.0, 1.0);
          const std::size_t beat_bin = static_cast<std::size_t>(
              std::min(20.0, std::floor(beat_coherence * 20.0)));
          ++label_result
                .fine_frequency_member_mask_minimum_beat_coherence_bins
                    [fine_member_mask][beat_bin];
        }
        if (spectral_group_leader_indices[label.midi_note] == label_index) {
          const std::uint8_t expected_group =
              spectral_expected_group_masks[label.midi_note];
          const std::uint8_t fine_mask =
              static_cast<std::uint8_t>(fine_member_mask);
          const std::uint8_t projected =
              bounded_spectral_onset_latch_projection(
                  observed_lane_mask, fine_mask,
                  other_note_lane_mask(snapshot, label.midi_note),
                  admission.playable_string_mask, config.max_polyphony);
          if (projected != observed_lane_mask) {
            ++label_result.fine_exact_completion_changed_frames;
          }
          if (projected == expected_group) {
            ++label_result.fine_exact_completion_exact_frames;
          }
          label_result.fine_exact_completion_matched_delta +=
              static_cast<std::int64_t>(projected == expected_group) -
              static_cast<std::int64_t>(observed_lane_mask ==
                                        expected_group);
          label_result.fine_exact_completion_wrong_string_delta +=
              static_cast<std::int64_t>(mask_member_count(
                  static_cast<std::uint8_t>(
                      projected & static_cast<std::uint8_t>(
                                      ~expected_group)))) -
              static_cast<std::int64_t>(mask_member_count(
                  static_cast<std::uint8_t>(
                      observed_lane_mask & static_cast<std::uint8_t>(
                                               ~expected_group))));
        }
        const auto unique_member_improvement =
            detector.fine_frequency_unique_member_improvement(
                label.midi_note);
        for (std::size_t policy = 0U;
             policy < kFineUniqueMemberImprovementFloors.size(); ++policy) {
          const std::uint8_t projected =
              bounded_fine_unique_member_pruning_projection(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  unique_member_improvement,
                  kFineUniqueMemberImprovementFloors[policy]);
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          if (group_leader && projected != observed_lane_mask) {
            ++label_result
                  .fine_unique_member_pruning_changed_frames[policy];
          }
          if (group_leader &&
              projected == spectral_expected_group_masks[label.midi_note]) {
            ++label_result.fine_unique_member_pruning_exact_frames[policy];
          }
          label_result.fine_unique_member_pruning_matched_delta[policy] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(projected, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .fine_unique_member_pruning_wrong_string_delta[policy] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        projected & static_cast<std::uint8_t>(~expected)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(observed_lane_mask &
                                              static_cast<std::uint8_t>(
                                                  ~expected))));
          }
        }
        const FineFrequencyMaskResidualTable& mask_residuals =
            detector.fine_frequency_mask_residuals(label.midi_note);
        if (spectral_group_leader_indices[label.midi_note] == label_index) {
          const std::uint8_t expected_mask =
              spectral_expected_group_masks[label.midi_note];
          const std::uint8_t maximum_members = static_cast<std::uint8_t>(
              std::min<std::size_t>(4U, config.max_polyphony));
          const FineMaskModelRanking unpenalized =
              rank_fine_masks_by_complexity(
                  mask_residuals.normalized_residual,
                  mask_residuals.valid, admission.playable_string_mask,
                  maximum_members, expected_mask, 0.0);
          const auto& hann_shadow = detector.hann_beat_shadow(label.midi_note);
          const bool hann_eligible = admission.active && expected_mask != 0U &&
              disposition == static_cast<std::size_t>(SelectionDisposition::selected);
          if (hann_eligible && frequency_shadow_storage != nullptr) {
            auto& coverage = result.physical_group_frequency_refinement_coverage;
            ++coverage[0U];
            const auto& table = frequency_shadow_storage->at(label.midi_note);
            bool has_model = false;
            for (const auto& model : table.masks) {
              has_model = has_model || (mask_residuals.valid[model.mask] &&
                  mask_member_count(model.mask) <= maximum_members &&
                  (model.mask & ~admission.playable_string_mask) == 0U);
            }
            if (has_model) {
              ++coverage[1U];
              coverage[2U] += table.prepared ? 1U : 0U;
            }
            if (has_model && table.prepared) {
              for (const auto& model : table.masks) {
                if (!mask_residuals.valid[model.mask] ||
                    mask_member_count(model.mask) > maximum_members ||
                    (model.mask & ~admission.playable_string_mask) != 0U) {
                  continue;
                }
                ++coverage[3U];
                for (std::size_t arm = 0U; arm < model.arms.size(); ++arm) {
                  const auto& value = model.arms[arm];
                  const auto& fixed = model.arms[0U];
                  const std::uint64_t key = label.midi_note |
                      (static_cast<std::uint64_t>(expected_mask) << 7U) |
                      (static_cast<std::uint64_t>(model.mask) << 15U) |
                      (static_cast<std::uint64_t>(classify_target_lane_outcome(
                           observed_lane_mask, expected_mask)) << 23U) |
                      (static_cast<std::uint64_t>(arm) << 26U);
                  auto& summary = result.physical_group_frequency_refinement[key];
                  ++summary.frames;
                  summary.bounded_frames += value.bounded ? 1U : 0U;
                  if (!value.valid) {
                    continue;
                  }
                  ++summary.valid_frames;
                  const bool beat_supported = value.minimum_full_window_beat >= 0.20;
                  const bool gain = fixed.valid &&
                      fixed.test_refit_residual - value.test_refit_residual >= 0.02;
                  // Diagnose a nontrivial held-out improvement and preserve
                  // both full-window beat and relative-amplitude support.
                  // This qualification never edits actual or shadow MIDI.
                  const bool qualified = !value.bounded && beat_supported &&
                      value.minimum_amplitude_ratio >= 0.12;
                  const bool useful_gain = qualified && gain &&
                      value.train_residual <= fixed.train_residual &&
                      value.test_prediction_residual < fixed.test_prediction_residual;
                  summary.beat_supported_frames += beat_supported ? 1U : 0U;
                  summary.heldout_gain_frames += gain ? 1U : 0U;
                  summary.qualified_frames += qualified ? 1U : 0U;
                  summary.useful_gain_frames += useful_gain ? 1U : 0U;
                  summary.train_sum += value.train_residual;
                  summary.test_refit_sum += value.test_refit_residual;
                  summary.test_prediction_sum += value.test_prediction_residual;
                  summary.maximum_cents = std::max(summary.maximum_cents,
                      value.maximum_correction_cents);
                  summary.minimum_conditioning = std::min(
                      summary.minimum_conditioning, value.conditioning_proxy);
                  for (std::size_t string = 0U; string < kMaxVoices; ++string) {
                    summary.correction_cents_sum[string] += value.correction_cents[string];
                  }
                }
              }
            }
          }
          if (hann_eligible) {
            ++result.physical_group_hann_beat_coverage[0U];
            bool has_model = false;
            for (std::size_t mask = 1U; mask < 256U; ++mask) {
              const auto members = mask_member_count(static_cast<std::uint8_t>(mask));
              has_model = has_model || (mask_residuals.valid[mask] &&
                  members >= 2U && members <= maximum_members &&
                  (mask & ~admission.playable_string_mask) == 0U);
            }
            if (has_model) {
              ++result.physical_group_hann_beat_coverage[1U];
              ++result.physical_group_hann_beat_coverage[
                  hann_shadow.hann_detrending_valid ? 2U : 3U];
            }
          }
          if (hann_eligible && hann_shadow.hann_detrending_valid) {
            for (std::size_t mask_value = 1U; mask_value < 256U; ++mask_value) {
              const auto mask = static_cast<std::uint8_t>(mask_value);
              const std::uint8_t members = mask_member_count(mask);
              if (!mask_residuals.valid[mask_value] || members < 2U ||
                  members > maximum_members ||
                  (mask & ~admission.playable_string_mask) != 0U) {
                continue;
              }
              ++result.physical_group_hann_beat_coverage[4U];
              double minimum = 1.0;
              double minimum_cycles = std::numeric_limits<double>::infinity();
              for (std::size_t first = 0U; first < kMaxVoices; ++first) {
                if ((mask & (1U << first)) == 0U) {
                  continue;
                }
                for (std::size_t second = first + 1U; second < kMaxVoices;
                     ++second) {
                  if ((mask & (1U << second)) == 0U) {
                    continue;
                  }
                  const std::size_t edge =
                      diagnostics::beat_pair_index(first, second);
                  const double weighted =
                      hann_shadow.hann_detrended_pair_coherence[edge];
                  minimum = std::min(minimum, weighted);
                  minimum_cycles = std::min(minimum_cycles,
                      hann_shadow.pair_difference_hz[edge] *
                          hann_shadow.beat_window_seconds);
                  if (members == 2U) {
                    const std::uint64_t edge_key = label.midi_note |
                        (static_cast<std::uint64_t>(edge) << 7U) |
                        (static_cast<std::uint64_t>(
                             mask_member_count(expected_mask)) << 12U) |
                        (static_cast<std::uint64_t>(
                             (mask & expected_mask) == mask) << 16U);
                    auto& summary = result.physical_group_hann_beat_edges[edge_key];
                    const double original =
                        mask_residuals.minimum_beat_coherence[mask_value];
                    ++summary.frames;
                    summary.difference_hz = hann_shadow.pair_difference_hz[edge];
                    summary.minimum_window_seconds = std::min(
                        summary.minimum_window_seconds,
                        hann_shadow.beat_window_seconds);
                    summary.maximum_window_seconds = std::max(
                        summary.maximum_window_seconds,
                        hann_shadow.beat_window_seconds);
                    summary.original_sum += original;
                    summary.weighted_sum += weighted;
                    summary.original_minimum = std::min(summary.original_minimum, original);
                    summary.original_maximum = std::max(summary.original_maximum, original);
                    summary.weighted_minimum = std::min(summary.weighted_minimum, weighted);
                    summary.weighted_maximum = std::max(summary.weighted_maximum, weighted);
                  }
                }
              }
              const std::uint64_t cycles_bin = minimum_cycles < 1.0 ? 0U :
                  minimum_cycles < 2.0 ? 1U : minimum_cycles < 4.0 ? 2U : 3U;
              const std::uint64_t passes =
                  (mask_residuals.minimum_beat_coherence[mask_value] >= 0.20 ? 2U : 0U) |
                  (minimum >= 0.20 ? 1U : 0U);
              const std::uint64_t key = mask_member_count(expected_mask) |
                  (static_cast<std::uint64_t>(members) << 4U) |
                  (static_cast<std::uint64_t>(classify_target_lane_outcome(
                       mask, expected_mask)) << 8U) |
                  (passes << 11U) | (cycles_bin << 13U) |
                  (static_cast<std::uint64_t>(classify_target_lane_outcome(
                       observed_lane_mask, expected_mask)) << 16U);
              ++result.physical_group_hann_beat_mask_frames[key];
            }
          }
          const auto unresolved =
              detector.fine_frequency_unresolved_reason(label.midi_note);
          if (mask_member_count(expected_mask) == 3U &&
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::selected) &&
              classify_target_lane_outcome(observed_lane_mask, expected_mask) ==
                  ReplayTargetLaneOutcome::subset_missing &&
              (unresolved == FineFrequencyUnresolvedReason::none ||
               unresolved == FineFrequencyUnresolvedReason::analysis_wait)) {
            const std::uint64_t rank =
                unpenalized.expected_available
                    ? static_cast<std::uint64_t>(unpenalized.expected_rank) + 1U
                    : 0U;
            const bool valid_beat = mask_residuals.valid[expected_mask] &&
                std::isfinite(mask_residuals.minimum_beat_coherence[expected_mask]);
            const std::uint64_t key =
                static_cast<std::uint64_t>(unresolved) |
                (static_cast<std::uint64_t>(mask_member_count(
                     detector.fine_frequency_fit_member_mask(label.midi_note))) << 3U) |
                (static_cast<std::uint64_t>(mask_member_count(
                     detector.fine_frequency_member_mask(label.midi_note))) << 7U) |
                (static_cast<std::uint64_t>(
                     detector.fine_frequency_disposition(label.midi_note)) << 11U) |
                (rank << 15U) |
                (static_cast<std::uint64_t>(valid_beat &&
                     mask_residuals.minimum_beat_coherence[expected_mask] >= 0.20) << 23U) |
                (static_cast<std::uint64_t>(mask_residuals.valid[expected_mask] &&
                     mask_residuals.beat_graph_connected[expected_mask]) << 24U) |
                (static_cast<std::uint64_t>(classify_group_mask_relation(
                     detector.fine_frequency_pending_member_mask(label.midi_note),
                     expected_mask, false)) << 25U) |
                (static_cast<std::uint64_t>(classify_group_mask_relation(
                     detector.committed_unison_mask(label.midi_note),
                     expected_mask, false)) << 27U);
            ++result.physical_group_completed_triple_fit_frames[key];
          }
          if (unpenalized.expected_available) {
            ++label_result.fine_mask_model_expected_available_frames;
          }
          if (unpenalized.expected_rank <
              label_result.fine_mask_model_expected_rank_frames.size()) {
            ++label_result.fine_mask_model_expected_rank_frames
                  [unpenalized.expected_rank];
          }
          for (std::size_t policy = 0U;
               policy < kFineMaskComplexityPenalties.size(); ++policy) {
            const FineMaskModelRanking ranking =
                rank_fine_masks_by_complexity(
                    mask_residuals.normalized_residual,
                    mask_residuals.valid, admission.playable_string_mask,
                    maximum_members, expected_mask,
                    kFineMaskComplexityPenalties[policy]);
            if (ranking.best_mask == expected_mask) {
              ++label_result.fine_mask_model_exact_frames[policy];
            }
            if (ranking.tied) {
              ++label_result.fine_mask_model_tied_frames[policy];
            }
            const std::size_t winner_members =
                mask_member_count(ranking.best_mask);
            if (winner_members <
                label_result
                    .fine_mask_model_winner_member_frames[policy]
                    .size()) {
              ++label_result
                    .fine_mask_model_winner_member_frames[policy]
                    [winner_members];
            }
          }

          const std::array<double, kMaxVoices> string_probability =
              detector.string_fret_posterior_probabilities(label.midi_note);
          double posterior_total = 0.0;
          for (std::size_t string = 0U; string < kMaxVoices; ++string) {
            if ((admission.playable_string_mask & (1U << string)) != 0U) {
              posterior_total += string_probability[string];
            }
          }
          if (std::isfinite(posterior_total) && posterior_total > 0.0) {
            ++label_result.fine_mask_posterior_available_frames;
          }
          for (std::size_t size_policy = 0U;
               size_policy < kFineMaskComplexityPenalties.size();
               ++size_policy) {
            for (std::size_t posterior_policy = 0U;
                 posterior_policy < kFineMaskPosteriorWeights.size();
                 ++posterior_policy) {
              const FineMaskModelRanking ranking =
                  rank_fine_masks_with_string_posterior(
                      mask_residuals.normalized_residual,
                      mask_residuals.valid, string_probability,
                      admission.playable_string_mask, maximum_members,
                      expected_mask,
                      kFineMaskComplexityPenalties[size_policy],
                      kFineMaskPosteriorWeights[posterior_policy]);
              if (ranking.best_mask == expected_mask) {
                ++label_result.fine_mask_posterior_exact_frames[size_policy]
                                                             [posterior_policy];
              }
              if (ranking.tied) {
                ++label_result.fine_mask_posterior_tied_frames[size_policy]
                                                            [posterior_policy];
              }
            }
          }
          for (std::size_t beat_policy = 0U;
               beat_policy < kFineMaskBeatCoherenceFloors.size();
               ++beat_policy) {
            const FineMaskModelRanking availability =
                rank_fine_masks_with_beat_graph(
                    mask_residuals.normalized_residual,
                    mask_residuals.valid,
                    mask_residuals.minimum_beat_coherence,
                    mask_residuals.beat_graph_connected,
                    admission.playable_string_mask, maximum_members,
                    expected_mask, 0.0,
                    kFineMaskBeatCoherenceFloors[beat_policy]);
            if (availability.expected_available) {
              ++label_result
                    .fine_mask_beat_expected_available_frames[beat_policy];
            }
            for (std::size_t size_policy = 0U;
                 size_policy < kFineMaskComplexityPenalties.size();
                 ++size_policy) {
              const FineMaskModelRanking ranking =
                  rank_fine_masks_with_beat_graph(
                      mask_residuals.normalized_residual,
                      mask_residuals.valid,
                      mask_residuals.minimum_beat_coherence,
                      mask_residuals.beat_graph_connected,
                      admission.playable_string_mask, maximum_members,
                      expected_mask,
                      kFineMaskComplexityPenalties[size_policy],
                      kFineMaskBeatCoherenceFloors[beat_policy]);
              if (ranking.best_mask == expected_mask) {
                ++label_result.fine_mask_beat_exact_frames[size_policy]
                                                         [beat_policy];
              }
              if (ranking.tied) {
                ++label_result.fine_mask_beat_tied_frames[size_policy]
                                                        [beat_policy];
              }
            }
          }
        }
        if (spectral_group_leader_indices[label.midi_note] == label_index) {
          ++label_result.fine_mask_pruning_output_mask_frames
                [detector.fine_mask_pruning_output_mask(label.midi_note)];
        }
        const FineMaskComplexityEvidence complexity_evidence{
            admission.active,
            disposition ==
                static_cast<std::size_t>(SelectionDisposition::selected),
            admission.direct_fundamental_peak,
            disposition ==
                static_cast<std::size_t>(SelectionDisposition::quiet),
            admission.score_threshold_ratio,
            observed_lane_mask,
            admission.playable_string_mask,
            other_note_lane_mask(snapshot, label.midi_note)};
        const bool fine_mask_group_leader =
            spectral_group_leader_indices[label.midi_note] == label_index;
        const std::uint8_t beat_pruned =
            label.midi_note >= kFineMaskBeatPruningMinimumMidiNote
                ? bounded_fine_beat_graph_pruning_projection(
                      complexity_evidence,
                      mask_residuals.normalized_residual,
                      mask_residuals.valid,
                      mask_residuals.minimum_beat_coherence,
                      mask_residuals.beat_graph_connected, 0.02, 0.20,
                      config.max_polyphony)
                : observed_lane_mask;
        if (fine_mask_group_leader && beat_pruned != observed_lane_mask) {
          ++label_result.fine_mask_beat_pruning_changed_frames;
        }
        if (fine_mask_group_leader &&
            beat_pruned ==
                spectral_expected_group_masks[label.midi_note]) {
          ++label_result.fine_mask_beat_pruning_exact_frames;
        }
        label_result.fine_mask_beat_pruning_matched_delta +=
            static_cast<std::int64_t>(
                lane_mask_matches_label(beat_pruned, label)) -
            static_cast<std::int64_t>(
                lane_mask_matches_label(observed_lane_mask, label));
        if (fine_mask_group_leader) {
          const std::uint8_t expected =
              spectral_expected_group_masks[label.midi_note];
          label_result.fine_mask_beat_pruning_wrong_string_delta +=
              static_cast<std::int64_t>(mask_member_count(
                  static_cast<std::uint8_t>(
                      beat_pruned & static_cast<std::uint8_t>(~expected)))) -
              static_cast<std::int64_t>(mask_member_count(
                  static_cast<std::uint8_t>(
                      observed_lane_mask &
                      static_cast<std::uint8_t>(~expected))));
        }
        for (std::size_t policy = 0U;
             policy < kFineMaskComplexityPenalties.size(); ++policy) {
          const std::uint8_t projected =
              label.midi_note >= kFineMaskComplexityMinimumMidiNote
                  ? bounded_fine_mask_complexity_projection(
                        complexity_evidence,
                        mask_residuals.normalized_residual,
                        mask_residuals.valid,
                        kFineMaskComplexityPenalties[policy],
                        config.max_polyphony)
                  : observed_lane_mask;
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          if (group_leader && projected != observed_lane_mask) {
            ++label_result.fine_mask_complexity_changed_frames[policy];
          }
          if (group_leader &&
              projected == spectral_expected_group_masks[label.midi_note]) {
            ++label_result.fine_mask_complexity_exact_frames[policy];
          }
          label_result.fine_mask_complexity_matched_delta[policy] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(projected, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected =
                spectral_expected_group_masks[label.midi_note];
            label_result.fine_mask_complexity_wrong_string_delta[policy] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        projected & static_cast<std::uint8_t>(~expected)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected))));
          }
        }
        if (label.string_mask != 0U &&
            committed_mask == label.string_mask) {
          std::size_t fine_relation = 3U;
          if (fine_member_mask == 0U) {
            fine_relation = 0U;
          } else if (fine_member_mask == label.string_mask) {
            fine_relation = 1U;
          } else if ((fine_member_mask & static_cast<std::uint8_t>(
                                             ~label.string_mask)) == 0U &&
                     (fine_member_mask & label.string_mask) != 0U) {
            fine_relation = 2U;
          }
          ++label_result.committed_exact_fine_relation_lane_outcome_frames
                [fine_relation][static_cast<std::size_t>(lane_outcome)];
          if (fine_relation != 1U) {
            ++tracking.current_committed_exact_fine_gap_frames;
            label_result.longest_committed_exact_fine_gap_frames = std::max(
                label_result.longest_committed_exact_fine_gap_frames,
                tracking.current_committed_exact_fine_gap_frames);
          } else {
            tracking.current_committed_exact_fine_gap_frames = 0U;
          }
        } else {
          tracking.current_committed_exact_fine_gap_frames = 0U;
        }
        const std::size_t pending_member_mask =
            detector.fine_frequency_pending_member_mask(label.midi_note);
        if (pending_member_mask <
            label_result.fine_frequency_pending_member_mask_frames.size()) {
          ++label_result
                .fine_frequency_pending_member_mask_frames[pending_member_mask];
        }
        const std::size_t fine_disposition = static_cast<std::size_t>(
            detector.fine_frequency_disposition(label.midi_note));
        if (fine_disposition <
            label_result.fine_frequency_disposition_frames.size()) {
          ++label_result.fine_frequency_disposition_frames[fine_disposition];
        }
        const std::size_t unresolved_reason = static_cast<std::size_t>(
            detector.fine_frequency_unresolved_reason(label.midi_note));
        if (unresolved_reason < label_result
                                    .fine_frequency_unresolved_reason_frames
                                    .size()) {
          ++label_result.fine_frequency_unresolved_reason_frames
                [unresolved_reason];
        }
        const std::size_t fit_member_mask =
            detector.fine_frequency_fit_member_mask(label.midi_note);
        if (fit_member_mask <
            label_result.fine_frequency_fit_member_mask_frames.size()) {
          ++label_result
                .fine_frequency_fit_member_mask_frames[fit_member_mask];
        }
        const double residual_improvement = std::clamp(
            detector.fine_frequency_residual_improvement(label.midi_note),
            0.0, 1.0);
        const std::size_t residual_bin = static_cast<std::size_t>(
            std::min(20.0, std::floor(residual_improvement * 20.0)));
        auto& residual_bins =
            fit_member_mask == label.string_mask
                ? label_result.exact_fit_residual_improvement_frames
                : label_result.other_fit_residual_improvement_frames;
        ++residual_bins[residual_bin];
        const std::size_t posterior_best =
            detector.string_fret_posterior_best(label.midi_note);
        if (posterior_best <
            label_result.string_fret_posterior_best_frames.size()) {
          ++label_result.string_fret_posterior_best_frames[posterior_best];
        }
        const std::size_t posterior_class =
            posterior_best >= kMaxVoices
                ? 2U
                : ((label.string_mask == 0U ||
                    (label.string_mask & (1U << posterior_best)) != 0U)
                       ? 0U
                       : 1U);
        ++label_result.posterior_lane_outcome_frames[posterior_class]
                                                        [static_cast<std::size_t>(
                                                            lane_outcome)];
        const std::uint8_t posterior_playable =
            detector.string_fret_posterior_playable_mask(label.midi_note);
        const bool posterior_ambiguous =
            posterior_playable != 0U &&
            (posterior_playable & static_cast<std::uint8_t>(
                                      posterior_playable - 1U)) != 0U;
        if (posterior_ambiguous) {
          ++label_result.string_fret_posterior_probability_frames
                [posterior_class][unit_ratio_bin(
                    detector.string_fret_posterior_best_probability(
                        label.midi_note))];
          ++label_result.string_fret_posterior_margin_frames
                [posterior_class][unit_ratio_bin(
                    detector.string_fret_posterior_margin(label.midi_note))];
        }
        const double calibration_margin =
            admission.best_calibration_similarity -
            admission.second_calibration_similarity;
        const double posterior_probability =
            detector.string_fret_posterior_best_probability(label.midi_note);
        const double posterior_margin =
            detector.string_fret_posterior_margin(label.midi_note);
        const bool relaxed_band_base_candidate =
            disposition == static_cast<std::size_t>(
                               SelectionDisposition::below_threshold) &&
            label.string_mask != 0U &&
            admission.score_threshold_ratio > 0.10 &&
            admission.score_threshold_ratio < 0.20 &&
            admission.fundamental_score_ratio >= 0.80 &&
            admission.direct_fundamental_peak &&
            (admission.local_peak || admission.candidate_evidence) &&
            admission.pitch_band_score_peak_ratio >= 0.90 &&
            admission.pitch_band_fundamental_peak_ratio >= 0.80 &&
            admission.best_calibrated_string >= 6U &&
            admission.best_calibrated_string < kMaxVoices &&
            admission.best_calibration_similarity >= 0.97 &&
            calibration_margin >= 0.02;
        if (relaxed_band_base_candidate &&
            posterior_best == admission.best_calibrated_string) {
          const bool expected =
              (label.string_mask & (1U << posterior_best)) != 0U;
          std::size_t policy = 0U;
          for (const double probability_floor :
               kRelaxedBandPosteriorProbabilityFloors) {
            for (const double margin_floor :
                 kRelaxedBandPosteriorMarginFloors) {
              if (posterior_probability >= probability_floor &&
                  posterior_margin >= margin_floor) {
                ++label_result.relaxed_band_posterior_agreement_frames
                      [policy][expected ? 0U : 1U];
              }
              ++policy;
            }
          }
        }
        const UnisonSpectralClassification& relaxed_single =
            spectral_single_classifications[label.midi_note];
        const std::uint8_t best_calibrated_bit =
            admission.best_calibrated_string < kMaxVoices
                ? static_cast<std::uint8_t>(
                      1U << admission.best_calibrated_string)
                : 0U;
        if (relaxed_band_base_candidate && relaxed_single.valid &&
            relaxed_single.member_count == 1U &&
            relaxed_single.member_mask == best_calibrated_bit) {
          const bool expected =
              (label.string_mask & best_calibrated_bit) != 0U;
          std::size_t policy = 0U;
          for (const double maximum_error :
               kRelaxedBandSpectralMaximumErrors) {
            for (const double margin_floor : kSpectralSingleGapThresholds) {
              if (relaxed_single.error <= maximum_error &&
                  relaxed_single.posterior_margin >= margin_floor) {
                ++label_result.relaxed_band_spectral_agreement_frames
                      [policy][expected ? 0U : 1U];
              }
              ++policy;
            }
          }
        }
        ++label_result.profile_unison_proposal_mask_frames[
            detector.profile_unison_proposal_mask(label.midi_note)];
        ++label_result.temporal_unison_proposal_mask_frames[
            detector.temporal_unison_proposal_mask(label.midi_note)];
        const UnisonSpectralClassification shadow_classification =
            spectral_shadow_classifications[label.midi_note];
        if (spectral_ready[label.midi_note]) {
          const UnisonSpectralFingerprint& fingerprint =
              spectral_fingerprints[label.midi_note];
          ++label_result.spectral_corridor_frames;
          for (std::size_t feature = 0U; feature < fingerprint.size();
               ++feature) {
            label_result.spectral_corridor_fingerprint_sum[feature] +=
                fingerprint[feature];
          }
          if (spectral_phases[label.midi_note] ==
              SpectralShadowPhase::onset) {
            ++label_result.spectral_onset_frames;
            for (std::size_t feature = 0U; feature < fingerprint.size();
                 ++feature) {
              label_result.spectral_onset_fingerprint_sum[feature] +=
                  fingerprint[feature];
            }
          } else if (spectral_phases[label.midi_note] ==
                     SpectralShadowPhase::settled) {
            ++label_result.spectral_settled_frames;
            for (std::size_t feature = 0U; feature < fingerprint.size();
                 ++feature) {
              label_result.spectral_settled_fingerprint_sum[feature] +=
                  fingerprint[feature];
            }
          }
          if (spectral_shadow_templates != nullptr) {
            const std::size_t phase =
                spectral_phases[label.midi_note] ==
                        SpectralShadowPhase::onset
                    ? 1U
                    : 2U;
            const UnisonSpectralClassification single_classification =
                spectral_single_classifications[label.midi_note];
            ++label_result.spectral_single_frames;
            const std::size_t score_phase = phase - 1U;
            const UnisonSpectralSingleScores& single_scores =
                spectral_single_scores[label.midi_note];
            const double best_single_error =
                spectral_single_best_errors[label.midi_note];
            for (std::size_t string = 0U; string < kMaxVoices; ++string) {
              const std::uint8_t bit =
                  static_cast<std::uint8_t>(1U << string);
              if ((single_scores.valid_mask & bit) == 0U) {
                continue;
              }
              const double score_error = single_scores.error[string];
              label_result.spectral_single_phase_score_error_sum
                  [score_phase][string] += score_error;
              ++label_result.spectral_single_phase_score_frames
                    [score_phase][string];
              const double gap = std::max(0.0, score_error - best_single_error);
              for (std::size_t threshold = 0U;
                   threshold < kSpectralSingleGapThresholds.size();
                   ++threshold) {
                if (gap <= kSpectralSingleGapThresholds[threshold]) {
                  ++label_result.spectral_single_phase_gap_support_frames
                        [score_phase][threshold][string];
                }
              }
            }
            if (!single_classification.valid) {
              ++label_result.spectral_single_invalid_frames;
              if (disposition <
                  label_result.spectral_single_selection_disposition_frames
                      .size()) {
                ++label_result
                      .spectral_single_selection_disposition_frames
                          [disposition][0U];
                ++label_result
                      .spectral_single_group_selection_disposition_frames
                          [disposition][0U];
              }
            } else {
              const std::size_t single_mask =
                  single_classification.member_mask;
              if (single_classification.member_count == 1U) {
                for (std::size_t string = 0U; string < kMaxVoices; ++string) {
                  if (single_mask != (1U << string)) {
                    continue;
                  }
                  auto& phase_frames =
                      spectral_phases[label.midi_note] ==
                              SpectralShadowPhase::onset
                          ? label_result
                                .spectral_single_onset_string_frames
                          : label_result
                                .spectral_single_settled_string_frames;
                  ++phase_frames[string];
                  break;
                }
              }
              const bool matches_label =
                  label.string_mask == 0U ||
                  single_classification.member_mask == label.string_mask;
              const std::size_t outcome = matches_label ? 0U : 1U;
              const std::uint8_t expected_group =
                  spectral_expected_group_masks[label.midi_note];
              const bool matches_group =
                  expected_group == std::numeric_limits<std::uint8_t>::max() ||
                  (single_classification.member_mask & expected_group) != 0U;
              const std::size_t group_outcome = matches_group ? 0U : 1U;
              ++label_result
                    .spectral_single_fitted_mask_frames[single_mask];
              label_result.spectral_single_fitted_mask_error_sum[single_mask] +=
                  single_classification.error;
              ++label_result.spectral_single_error_outcome_frames[outcome]
                    [spectral_single_metric_bin(single_classification.error)];
              ++label_result
                    .spectral_single_group_error_outcome_frames[group_outcome]
                        [spectral_single_metric_bin(
                            single_classification.error)];
              if (disposition == static_cast<std::size_t>(
                                     SelectionDisposition::below_threshold)) {
                ++label_result
                      .spectral_single_below_threshold_error_outcome_frames
                          [outcome][spectral_single_metric_bin(
                              single_classification.error)];
              }
              if (std::isfinite(single_classification.posterior_margin)) {
                label_result
                    .spectral_single_fitted_mask_margin_sum[single_mask] +=
                    single_classification.posterior_margin;
                ++label_result
                      .spectral_single_fitted_mask_margin_frames[single_mask];
                ++label_result.spectral_single_margin_outcome_frames[outcome]
                      [spectral_single_metric_bin(
                          single_classification.posterior_margin)];
                ++label_result
                      .spectral_single_group_margin_outcome_frames
                          [group_outcome][spectral_single_metric_bin(
                              single_classification.posterior_margin)];
                if (disposition == static_cast<std::size_t>(
                                       SelectionDisposition::below_threshold)) {
                  ++label_result
                        .spectral_single_below_threshold_margin_outcome_frames
                            [outcome][spectral_single_metric_bin(
                                single_classification.posterior_margin)];
                }
              }
              if (disposition <
                  label_result.spectral_single_selection_disposition_frames
                      .size()) {
                ++label_result
                      .spectral_single_selection_disposition_frames
                          [disposition][matches_label ? 1U : 2U];
                ++label_result
                      .spectral_single_group_selection_disposition_frames
                          [disposition][matches_group ? 1U : 2U];
              }
              const std::uint8_t projected_lane =
                  single_classification.member_mask;
              const std::uint8_t other_owned_lanes =
                  other_note_lane_mask(snapshot, label.midi_note);
              const bool lane_projection_eligible =
                  admission.active &&
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::selected) &&
                  mask_member_count(label.string_mask) == 1U &&
                  mask_member_count(observed_lane_mask) == 1U &&
                  single_classification.member_count == 1U &&
                  (projected_lane & admission.playable_string_mask) ==
                      projected_lane &&
                  (projected_lane & other_owned_lanes) == 0U;
              if (lane_projection_eligible) {
                const bool observed_matches =
                    lane_mask_matches_label(observed_lane_mask, label);
                const bool projected_matches =
                    lane_mask_matches_label(projected_lane, label);
                const std::int64_t observed_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~label.string_mask)));
                const std::int64_t projected_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        projected_lane &
                        static_cast<std::uint8_t>(~label.string_mask)));
                std::size_t policy = 0U;
                for (const double maximum_error :
                     kRelaxedBandSpectralMaximumErrors) {
                  for (const double margin_floor :
                       kSpectralSingleGapThresholds) {
                    if (single_classification.error <= maximum_error &&
                        single_classification.posterior_margin >=
                            margin_floor) {
                      ++label_result
                            .spectral_lane_projection_frames[policy];
                      ++label_result
                            .spectral_lane_projection_phase_frames
                                [score_phase][policy];
                      if (projected_lane != observed_lane_mask) {
                        ++label_result
                              .spectral_lane_projection_changed_frames
                                  [policy];
                        ++label_result
                              .spectral_lane_projection_phase_changed_frames
                                  [score_phase][policy];
                      }
                      const std::int64_t matched_delta =
                          static_cast<std::int64_t>(projected_matches) -
                          static_cast<std::int64_t>(observed_matches);
                      const std::int64_t wrong_string_delta =
                          projected_wrong - observed_wrong;
                      label_result
                          .spectral_lane_projection_matched_delta[policy] +=
                          matched_delta;
                      label_result
                          .spectral_lane_projection_wrong_string_delta
                              [policy] += wrong_string_delta;
                      label_result
                          .spectral_lane_projection_phase_matched_delta
                              [score_phase][policy] += matched_delta;
                      label_result
                          .spectral_lane_projection_phase_wrong_string_delta
                              [score_phase][policy] += wrong_string_delta;
                    }
                    ++policy;
                  }
                }
              }
              const UnisonSpectralClassification& candidate_single =
                  candidate_single_classifications[label.midi_note];
              const std::uint8_t candidate_projected_lane =
                  candidate_single.member_mask;
              const bool candidate_lane_projection_eligible =
                  admission.active &&
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::selected) &&
                  candidate_unison_ready[label.midi_note] &&
                  mask_member_count(label.string_mask) == 1U &&
                  mask_member_count(observed_lane_mask) == 1U &&
                  candidate_single.valid &&
                  candidate_single.member_count == 1U &&
                  (candidate_projected_lane & admission.playable_string_mask) ==
                      candidate_projected_lane &&
                  (candidate_projected_lane & other_owned_lanes) == 0U;
              if (candidate_lane_projection_eligible) {
                const bool observed_matches =
                    lane_mask_matches_label(observed_lane_mask, label);
                const bool projected_matches =
                    lane_mask_matches_label(candidate_projected_lane, label);
                const std::int64_t observed_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~label.string_mask)));
                const std::int64_t projected_wrong = mask_member_count(
                    static_cast<std::uint8_t>(
                        candidate_projected_lane &
                        static_cast<std::uint8_t>(~label.string_mask)));
                const std::size_t candidate_phase =
                    candidate_unison_phases[label.midi_note] ==
                            SpectralShadowPhase::onset
                        ? 0U
                        : 1U;
                std::size_t policy = 0U;
                for (const double maximum_error :
                     kRelaxedBandSpectralMaximumErrors) {
                  for (const double margin_floor :
                       kSpectralSingleGapThresholds) {
                    if (candidate_single.error <= maximum_error &&
                        candidate_single.posterior_margin >= margin_floor) {
                      ++label_result
                            .candidate_spectral_lane_projection_frames[policy];
                      if (candidate_projected_lane != observed_lane_mask) {
                        ++label_result
                              .candidate_spectral_lane_projection_changed_frames
                                  [policy];
                      }
                      const std::int64_t matched_delta =
                          static_cast<std::int64_t>(projected_matches) -
                          static_cast<std::int64_t>(observed_matches);
                      const std::int64_t wrong_string_delta =
                          projected_wrong - observed_wrong;
                      label_result
                          .candidate_spectral_lane_projection_matched_delta
                              [policy] += matched_delta;
                      label_result
                          .candidate_spectral_lane_projection_wrong_string_delta
                              [policy] += wrong_string_delta;
                      ++label_result
                            .candidate_spectral_lane_projection_phase_frames
                                [candidate_phase][policy];
                      label_result
                          .candidate_spectral_lane_projection_phase_matched_delta
                              [candidate_phase][policy] += matched_delta;
                      label_result
                          .candidate_spectral_lane_projection_phase_wrong_string_delta
                              [candidate_phase][policy] += wrong_string_delta;
                    }
                    ++policy;
                  }
                }
              }
              ++label_result.spectral_single_disposition_frames
                    [static_cast<std::size_t>(classify_target_lane_outcome(
                        single_classification.member_mask,
                        spectral_expected_group_masks[label.midi_note]))];
            }
            const UnisonSpectralClassification& classification =
                shadow_classification;
            ++label_result.spectral_shadow_frames;
            if (!classification.valid) {
              ++label_result.spectral_shadow_invalid_frames;
            } else {
              const std::size_t mask = classification.member_mask;
              ++label_result.spectral_shadow_fitted_mask_frames[mask];
              label_result.spectral_shadow_fitted_mask_residual_sum[mask] +=
                  classification.error;
              if (std::isfinite(classification.posterior_margin)) {
                label_result.spectral_shadow_fitted_mask_margin_sum[mask] +=
                    classification.posterior_margin;
                ++label_result
                      .spectral_shadow_fitted_mask_margin_frames[mask];
              }
              ++label_result.spectral_shadow_phase_mask_frames[phase - 1U]
                                                              [mask];
              ++label_result.spectral_shadow_disposition_frames
                    [static_cast<std::size_t>(classify_target_lane_outcome(
                        classification.member_mask,
                        spectral_expected_group_masks[label.midi_note]))];
              const std::uint8_t fine_mask =
                  detector.fine_frequency_member_mask(label.midi_note);
              const std::uint8_t profile_mask =
                  detector.profile_unison_proposal_mask(label.midi_note);
              const std::uint8_t temporal_mask =
                  detector.temporal_unison_proposal_mask(label.midi_note);
              if (classification.member_mask != fine_mask) {
                ++label_result.spectral_shadow_fine_disagreement_frames;
              }
              if (detector.fine_frequency_minimum_pairwise_beat_coherence(
                      label.midi_note) >= 0.20) {
                ++label_result.spectral_shadow_beat_compared_frames;
                if (classification.member_mask != fine_mask) {
                  ++label_result.spectral_shadow_beat_disagreement_frames;
                }
              }
              if (classification.member_mask != profile_mask) {
                ++label_result.spectral_shadow_profile_disagreement_frames;
              }
              if (classification.member_mask != temporal_mask) {
                ++label_result.spectral_shadow_temporal_disagreement_frames;
              }
              if (classification.member_mask != observed_lane_mask) {
                ++label_result
                      .spectral_shadow_assignment_disagreement_frames;
              }
            }
          }
        }
        if (spectral_shadow_templates != nullptr) {
          ++label_result.spectral_shadow_projected_frames;
          const std::uint8_t fine_mask =
              detector.fine_frequency_member_mask(label.midi_note);
          const std::uint8_t profile_mask =
              detector.profile_unison_proposal_mask(label.midi_note);
          const std::uint8_t temporal_mask =
              detector.temporal_unison_proposal_mask(label.midi_note);
          const double beat_coherence =
              detector.fine_frequency_minimum_pairwise_beat_coherence(
                  label.midi_note);
          const SpectralShadowPhase phase_value =
              spectral_ready[label.midi_note]
                  ? spectral_phases[label.midi_note]
                  : SpectralShadowPhase::unready;
          const std::uint8_t expected_group =
              spectral_expected_group_masks[label.midi_note];
          for (std::size_t threshold = 0U;
               threshold < kSpectralShadowMarginThresholds.size();
               ++threshold) {
            const std::uint8_t projected = bounded_spectral_shadow_proposal(
                observed_lane_mask, fine_mask, beat_coherence, profile_mask,
                temporal_mask, phase_value, shadow_classification,
                kSpectralShadowMarginThresholds[threshold]);
            if (projected != observed_lane_mask) {
              ++label_result
                    .spectral_shadow_projected_changed_frames[threshold];
            }
            if (lane_mask_matches_label(projected, label)) {
              ++label_result
                    .spectral_shadow_projected_matched_frames[threshold];
            }
            if (spectral_group_leader_indices[label.midi_note] == label_index) {
              if (projected == expected_group) {
                ++label_result
                      .spectral_shadow_projected_exact_frames[threshold];
              }
              label_result
                  .spectral_shadow_projected_wrong_string_voices[threshold] +=
                  mask_member_count(static_cast<std::uint8_t>(
                      projected &
                      static_cast<std::uint8_t>(~expected_group)));
            }
          }
          const std::uint8_t other_owned_mask =
              other_note_lane_mask(snapshot, label.midi_note);
          for (std::size_t threshold = 0U;
               threshold < kSpectralShadowMarginThresholds.size();
               ++threshold) {
            const SpectralOnsetMaskLatch& latch =
                spectral_onset_latches[label.midi_note][threshold];
            label_result.spectral_onset_latch_committed_mask[threshold] =
                latch.committed_mask();
            label_result.spectral_onset_latch_qualified_votes[threshold] =
                latch.qualified_votes();
            label_result.spectral_onset_latch_winner_votes[threshold] =
                latch.winner_votes();
            ++label_result.spectral_onset_latch_projected_frames[threshold];
            const std::uint8_t projected =
                bounded_spectral_onset_latch_projection(
                    observed_lane_mask, latch.committed_mask(),
                    other_owned_mask,
                    spectral_playable_masks[label.midi_note],
                    config.max_polyphony);
            if (projected != observed_lane_mask) {
              ++label_result.spectral_onset_latch_changed_frames[threshold];
            }
            if (lane_mask_matches_label(projected, label)) {
              ++label_result.spectral_onset_latch_matched_frames[threshold];
            }
            if (spectral_group_leader_indices[label.midi_note] == label_index) {
              if (projected == expected_group) {
                ++label_result.spectral_onset_latch_exact_frames[threshold];
              }
              label_result.spectral_onset_latch_wrong_string_voices[threshold] +=
                  mask_member_count(static_cast<std::uint8_t>(
                      projected &
                      static_cast<std::uint8_t>(~expected_group)));
            }
            const std::uint8_t contracted =
                bounded_spectral_onset_latch_contraction_projection(
                    observed_lane_mask, latch.committed_mask(),
                    static_cast<std::uint8_t>(fine_member_mask),
                    other_owned_mask,
                    spectral_playable_masks[label.midi_note],
                    config.max_polyphony,
                    admission.direct_fundamental_peak,
                    disposition == static_cast<std::size_t>(
                                       SelectionDisposition::quiet));
            if (contracted != observed_lane_mask) {
              ++label_result
                    .spectral_onset_contraction_changed_frames[threshold];
              label_result
                  .spectral_onset_contraction_changed_onset_strength_max
                      [threshold] =
                  std::max(
                      label_result
                          .spectral_onset_contraction_changed_onset_strength_max
                              [threshold],
                      admission.string_fret_onset_strength);
            }
            const bool observed_matches =
                lane_mask_matches_label(observed_lane_mask, label);
            const bool contracted_matches =
                lane_mask_matches_label(contracted, label);
            if (contracted_matches) {
              ++label_result
                    .spectral_onset_contraction_matched_frames[threshold];
            }
            label_result.spectral_onset_contraction_matched_delta[threshold] +=
                static_cast<std::int64_t>(contracted_matches) -
                static_cast<std::int64_t>(observed_matches);
            if (spectral_group_leader_indices[label.midi_note] == label_index) {
              if (contracted == expected_group) {
                ++label_result
                      .spectral_onset_contraction_exact_frames[threshold];
              }
              label_result
                  .spectral_onset_contraction_wrong_string_delta[threshold] +=
                  static_cast<std::int64_t>(mask_member_count(
                      static_cast<std::uint8_t>(
                          contracted &
                          static_cast<std::uint8_t>(~expected_group)))) -
                  static_cast<std::int64_t>(mask_member_count(
                      static_cast<std::uint8_t>(
                          observed_lane_mask &
                          static_cast<std::uint8_t>(~expected_group))));
            }
          }
        }
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
        const auto spectral =
            detector.string_fret_spectral_heads(label.midi_note);
        const std::uint8_t spectral_vote_mask =
            spectral_head_vote_mask(spectral.best_string);
        ++label_result.spectral_head_vote_mask_frames[spectral_vote_mask];
        for (std::size_t threshold = 0U;
             threshold < kSpectralShadowMarginThresholds.size();
             ++threshold) {
          const SpectralHeadPlurality plurality = spectral_head_plurality(
              spectral.best_string, spectral.margin,
              kSpectralShadowMarginThresholds[threshold]);
          const std::size_t plurality_string =
              plurality.string < kMaxVoices ? plurality.string : kMaxVoices;
          ++label_result
                .spectral_head_plurality_best_frames[threshold]
                                                    [plurality_string];
        }
        const std::uint8_t production_tier_proposal =
            detector.spectral_tier_completion_proposal_mask(
                label.midi_note);
        ++label_result.spectral_tier_production_proposal_mask_frames[
            production_tier_proposal];
        ++label_result
              .spectral_tier_production_relation_lane_outcome_frames
                  [static_cast<std::size_t>(classify_group_mask_relation(
                      production_tier_proposal,
                      spectral_expected_group_masks[label.midi_note],
                      spectral_expected_group_note_only[label.midi_note]))]
                  [static_cast<std::size_t>(lane_outcome)];
        ++label_result.selector_group_relation_lane_outcome_frames
              [static_cast<std::size_t>(classify_group_mask_relation(
                  detector.selector_group_mask(label.midi_note),
                  spectral_expected_group_masks[label.midi_note],
                  spectral_expected_group_note_only[label.midi_note]))]
              [static_cast<std::size_t>(lane_outcome)];
        ++label_result.tier_completion_disposition_lane_outcome_frames
              [static_cast<std::size_t>(
                  detector.tier_completion_disposition(label.midi_note))]
              [static_cast<std::size_t>(lane_outcome)];
        if (lane_outcome == ReplayTargetLaneOutcome::subset_missing &&
            disposition ==
                static_cast<std::size_t>(SelectionDisposition::selected)) {
          const std::uint8_t tier_mask =
              detector.spectral_tier_completion_proposal_mask(
                  label.midi_note);
          const UnisonSpectralClassification& candidate_classification =
              candidate_unison_classifications[label.midi_note];
          const std::array<std::uint8_t, 6U> evidence_masks{
              static_cast<std::uint8_t>(fine_member_mask), committed_mask,
              detector.profile_unison_proposal_mask(label.midi_note),
              detector.temporal_unison_proposal_mask(label.midi_note),
              tier_mask,
              candidate_classification.valid
                  ? candidate_classification.member_mask
                  : static_cast<std::uint8_t>(0U)};
          for (std::size_t source = 0U; source < evidence_masks.size();
               ++source) {
            const ReplayTargetLaneOutcome evidence_outcome =
                classify_target_lane_outcome(
                    evidence_masks[source],
                    spectral_expected_group_masks[label.midi_note]);
            ++label_result.selected_subset_evidence_outcome_frames
                  [source][static_cast<std::size_t>(evidence_outcome)];
          }
          const std::uint8_t other_owned =
              other_note_lane_mask(snapshot, label.midi_note);
          for (std::size_t policy = 0U;
               policy < kSelectedSubsetCompletionSupportFloors.size();
               ++policy) {
            ++label_result
                  .selected_subset_consensus_projected_frames[policy];
            const std::uint8_t preliminary =
                bounded_selected_subset_completion_projection(
                    observed_lane_mask, evidence_masks, other_owned,
                    admission.playable_string_mask, config.max_polyphony,
                    kSelectedSubsetCompletionSupportFloors[policy],
                    admission.direct_fundamental_peak, 1.0, false, false);
            const double beat_coherence =
                detector.fine_frequency_pairwise_beat_coherence(
                    label.midi_note, preliminary);
            std::array<double, 1U << kMaxVoices> pair_coherence{};
            for (std::size_t left = 0U; left < kMaxVoices; ++left) {
              const std::uint8_t left_bit =
                  static_cast<std::uint8_t>(1U << left);
              if ((preliminary & left_bit) == 0U) {
                continue;
              }
              for (std::size_t right = left + 1U; right < kMaxVoices;
                   ++right) {
                const std::uint8_t right_bit =
                    static_cast<std::uint8_t>(1U << right);
                if ((preliminary & right_bit) == 0U) {
                  continue;
                }
                const std::uint8_t pair =
                    static_cast<std::uint8_t>(left_bit | right_bit);
                pair_coherence[pair] =
                    detector.fine_frequency_pairwise_beat_coherence(
                        label.midi_note, pair);
              }
            }
            const bool robust_connected =
                summarize_pairwise_beat_support(preliminary, pair_coherence,
                                                0.20)
                    .connected;
            const std::uint8_t projected =
                bounded_selected_subset_completion_projection(
                    observed_lane_mask, evidence_masks, other_owned,
                    admission.playable_string_mask, config.max_polyphony,
                    kSelectedSubsetCompletionSupportFloors[policy],
                    admission.direct_fundamental_peak, beat_coherence,
                    robust_connected, false);
            if (projected != observed_lane_mask) {
              ++label_result
                    .selected_subset_consensus_changed_frames[policy];
            }
            const bool observed_matches =
                lane_mask_matches_label(observed_lane_mask, label);
            const bool projected_matches =
                lane_mask_matches_label(projected, label);
            label_result.selected_subset_consensus_matched_delta[policy] +=
                static_cast<std::int64_t>(projected_matches) -
                static_cast<std::int64_t>(observed_matches);
            if (spectral_group_leader_indices[label.midi_note] == label_index) {
              const std::uint8_t expected_group =
                  spectral_expected_group_masks[label.midi_note];
              if (projected == expected_group) {
                ++label_result
                      .selected_subset_consensus_exact_frames[policy];
              }
              const std::int64_t projected_wrong = mask_member_count(
                  static_cast<std::uint8_t>(
                      projected & static_cast<std::uint8_t>(~expected_group)));
              const std::int64_t observed_wrong = mask_member_count(
                  static_cast<std::uint8_t>(observed_lane_mask &
                                            static_cast<std::uint8_t>(
                                                ~expected_group)));
              label_result
                  .selected_subset_consensus_wrong_string_delta[policy] +=
                  projected_wrong - observed_wrong;
            }
          }
          if (candidate_classification.valid) {
            const std::uint8_t proposed =
                candidate_classification.member_mask;
            const double proposed_beat_coherence =
                detector.fine_frequency_pairwise_beat_coherence(
                    label.midi_note, proposed);
            std::array<double, 1U << kMaxVoices> pair_coherence{};
            for (std::size_t left = 0U; left < kMaxVoices; ++left) {
              const std::uint8_t left_bit =
                  static_cast<std::uint8_t>(1U << left);
              if ((proposed & left_bit) == 0U) {
                continue;
              }
              for (std::size_t right = left + 1U; right < kMaxVoices;
                   ++right) {
                const std::uint8_t right_bit =
                    static_cast<std::uint8_t>(1U << right);
                if ((proposed & right_bit) == 0U) {
                  continue;
                }
                const std::uint8_t pair =
                    static_cast<std::uint8_t>(left_bit | right_bit);
                pair_coherence[pair] =
                    detector.fine_frequency_pairwise_beat_coherence(
                        label.midi_note, pair);
              }
            }
            const bool proposed_connected =
                summarize_pairwise_beat_support(proposed, pair_coherence, 0.20)
                    .connected;
            std::size_t classifier_policy = 0U;
            for (const double maximum_error :
                 kRelaxedBandSpectralMaximumErrors) {
              for (const double minimum_margin :
                   kSpectralSingleGapThresholds) {
                ++label_result
                      .classifier_subset_projection_frames[classifier_policy];
                const ClassifierSubsetProjectionResult projection =
                    diagnose_classifier_subset_completion_projection(
                        observed_lane_mask, candidate_classification,
                        other_owned, admission.playable_string_mask,
                        config.max_polyphony,
                        admission.direct_fundamental_peak,
                        proposed_beat_coherence, proposed_connected,
                        maximum_error, minimum_margin, false);
                const std::uint8_t projected = projection.projected_mask;
                ++label_result.classifier_subset_disposition_frames
                      [classifier_policy]
                      [static_cast<std::size_t>(projection.disposition)];
                if (projected != observed_lane_mask) {
                  ++label_result
                        .classifier_subset_changed_frames[classifier_policy];
                }
                const bool observed_matches =
                    lane_mask_matches_label(observed_lane_mask, label);
                const bool projected_matches =
                    lane_mask_matches_label(projected, label);
                label_result.classifier_subset_matched_delta
                    [classifier_policy] +=
                    static_cast<std::int64_t>(projected_matches) -
                    static_cast<std::int64_t>(observed_matches);
                if (spectral_group_leader_indices[label.midi_note] ==
                    label_index) {
                  const std::uint8_t expected_group =
                      spectral_expected_group_masks[label.midi_note];
                  if (projected == expected_group) {
                    ++label_result
                          .classifier_subset_exact_frames[classifier_policy];
                  }
                  const std::int64_t projected_wrong = mask_member_count(
                      static_cast<std::uint8_t>(
                          projected &
                          static_cast<std::uint8_t>(~expected_group)));
                  const std::int64_t observed_wrong = mask_member_count(
                      static_cast<std::uint8_t>(
                          observed_lane_mask &
                          static_cast<std::uint8_t>(~expected_group)));
                  label_result.classifier_subset_wrong_string_delta
                      [classifier_policy] += projected_wrong - observed_wrong;
                }
                ++classifier_policy;
              }
            }
          }
        }
        ++label_result.spectral_tier_completion_projected_frames;
        const SpectralShadowPhase tier_phase =
            spectral_ready[label.midi_note]
                ? spectral_phases[label.midi_note]
                : SpectralShadowPhase::unready;
        const std::uint8_t diagnostic_completion =
            spectral_tier_completion_candidate(
                static_cast<std::uint8_t>(fine_member_mask), tier_phase,
                spectral.best_string, spectral.margin, 0.0);
        if (diagnostic_completion != fine_member_mask) {
          ++label_result.spectral_tier_completion_candidate_mask_frames
                [diagnostic_completion];
          const double diagnostic_completion_coherence = std::clamp(
              detector.fine_frequency_added_member_beat_coherence(
                  label.midi_note, diagnostic_completion),
              0.0, 1.0);
          const std::size_t completion_beat_bin =
              static_cast<std::size_t>(std::min(
                  20.0,
                  std::floor(diagnostic_completion_coherence * 20.0)));
          ++label_result
                .spectral_tier_completion_added_member_beat_coherence_bins
                    [completion_beat_bin];
          const double diagnostic_added_ratio = std::clamp(
              detector.fine_frequency_added_member_ratio(
                  label.midi_note, diagnostic_completion),
              0.0, 1.0);
          const std::size_t completion_ratio_bin =
              static_cast<std::size_t>(std::min(
                  20.0, std::floor(diagnostic_added_ratio * 20.0)));
          ++label_result.spectral_tier_completion_added_member_ratio_bins
                [completion_ratio_bin];
        }
        for (std::size_t threshold = 0U;
             threshold < kSpectralShadowMarginThresholds.size(); ++threshold) {
          const std::uint8_t completion =
              spectral_tier_completion_candidate(
                  static_cast<std::uint8_t>(fine_member_mask), tier_phase,
                  spectral.best_string, spectral.margin,
                  kSpectralShadowMarginThresholds[threshold]);
          const double completion_beat_coherence =
              detector.fine_frequency_added_member_beat_coherence(
                  label.midi_note, completion);
          const double completion_added_member_ratio =
              detector.fine_frequency_added_member_ratio(label.midi_note,
                                                          completion);
          const std::uint8_t projected =
              bounded_spectral_tier_completion_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  completion_beat_coherence, completion_added_member_ratio,
                  tier_phase,
                  spectral.best_string, spectral.margin,
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t candidate_projected =
              bounded_spectral_shadow_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  detector.fine_frequency_minimum_pairwise_beat_coherence(
                      label.midi_note),
                  detector.profile_unison_proposal_mask(label.midi_note),
                  detector.temporal_unison_proposal_mask(label.midi_note),
                  candidate_unison_phases[label.midi_note],
                  candidate_unison_classifications[label.midi_note],
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t temporal_candidate_projected =
              bounded_temporal_spectral_shadow_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  detector.fine_frequency_minimum_pairwise_beat_coherence(
                      label.midi_note),
                  detector.temporal_unison_proposal_mask(label.midi_note),
                  candidate_unison_phases[label.midi_note],
                  candidate_unison_classifications[label.midi_note],
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t combined = bounded_projection_union(
              observed_lane_mask, candidate_projected, projected);
          const std::uint8_t temporal_combined = bounded_projection_union(
              observed_lane_mask, temporal_candidate_projected, projected);
          const std::uint8_t tier_priority_combined =
              projected != observed_lane_mask ? projected
                                               : temporal_candidate_projected;
          const UnisonReacquisitionState& cached_group =
              unison_reacquisition_states[label.midi_note];
          const std::uint64_t cached_group_maximum_age =
              static_cast<std::uint64_t>(std::ceil(
                  0.50 * static_cast<double>(wave.sample_rate)));
          const bool cached_group_is_recent =
              cached_group.last_confirmed_sample !=
                  std::numeric_limits<std::uint64_t>::max() &&
              sample_index >= cached_group.last_confirmed_sample &&
              sample_index - cached_group.last_confirmed_sample <=
                  cached_group_maximum_age;
          const std::uint8_t cached_candidate_projected =
              cached_group_is_recent &&
                      candidate_projected == cached_group.resolved_mask
                  ? candidate_projected
                  : observed_lane_mask;
          const std::uint8_t cached_group_combined = bounded_projection_union(
              observed_lane_mask, cached_candidate_projected, projected);
          const double cached_group_age_seconds =
              cached_group_is_recent
                  ? static_cast<double>(
                        sample_index - cached_group.last_confirmed_sample) /
                        static_cast<double>(wave.sample_rate)
                  : std::numeric_limits<double>::infinity();
          const bool selected_or_coasting =
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::selected) ||
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::coasting);
          const std::uint8_t cached_other_owned =
              other_note_lane_mask(snapshot, label.midi_note);
          const std::uint8_t cached_classifier_continuity =
              bounded_cached_classifier_continuity_projection(
                  observed_lane_mask, cached_group.resolved_mask,
                  candidate_unison_classifications[label.midi_note],
                  candidate_unison_phases[label.midi_note],
                  cached_other_owned,
                  admission.playable_string_mask, config.max_polyphony,
                  admission.active, selected_or_coasting,
                  admission.direct_fundamental_peak,
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::quiet),
                  cached_group_age_seconds, 0.50,
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t continuity_classifier_union =
              bounded_projection_union(observed_lane_mask,
                                       cached_group_combined,
                                       cached_classifier_continuity);
          const std::uint8_t production_cache_mask =
              detector.unison_reacquisition_cache_mask(label.midi_note);
          const double production_cache_age =
              detector.unison_reacquisition_cache_age_seconds(
                  label.midi_note);
          const bool production_cache_recent =
              production_cache_mask != 0U &&
              std::isfinite(production_cache_age) &&
              production_cache_age >= 0.0 && production_cache_age <= 0.50;
          const std::uint8_t production_cached_candidate =
              production_cache_recent &&
                      candidate_projected == production_cache_mask
                  ? candidate_projected
                  : observed_lane_mask;
          const std::uint8_t production_cached_group =
              bounded_projection_union(observed_lane_mask,
                                       production_cached_candidate,
                                       projected);
          const std::uint8_t production_cached_classifier =
              bounded_cached_classifier_continuity_projection(
                  observed_lane_mask, production_cache_mask,
                  candidate_unison_classifications[label.midi_note],
                  candidate_unison_phases[label.midi_note],
                  cached_other_owned, admission.playable_string_mask,
                  config.max_polyphony, admission.active,
                  selected_or_coasting, admission.direct_fundamental_peak,
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::quiet),
                  production_cache_age, 0.50,
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t production_cache_continuity =
              bounded_projection_union(observed_lane_mask,
                                       production_cached_group,
                                       production_cached_classifier);
          const UnisonReacquisitionState& committed_cache =
              committed_three_plus_cache_states[label.midi_note];
          const bool committed_cache_recent =
              committed_cache.resolved_mask != 0U &&
              committed_cache.last_confirmed_sample !=
                  std::numeric_limits<std::uint64_t>::max() &&
              sample_index >= committed_cache.last_confirmed_sample &&
              sample_index - committed_cache.last_confirmed_sample <=
                  cached_group_maximum_age;
          const double committed_cache_age =
              committed_cache_recent
                  ? static_cast<double>(
                        sample_index - committed_cache.last_confirmed_sample) /
                        static_cast<double>(wave.sample_rate)
                  : std::numeric_limits<double>::infinity();
          const std::uint8_t committed_cached_candidate =
              committed_cache_recent &&
                      candidate_projected == committed_cache.resolved_mask
                  ? candidate_projected
                  : observed_lane_mask;
          const std::uint8_t committed_cached_group =
              bounded_projection_union(observed_lane_mask,
                                       committed_cached_candidate,
                                       projected);
          const std::uint8_t committed_cached_classifier =
              bounded_cached_classifier_continuity_projection(
                  observed_lane_mask, committed_cache.resolved_mask,
                  candidate_unison_classifications[label.midi_note],
                  candidate_unison_phases[label.midi_note],
                  cached_other_owned, admission.playable_string_mask,
                  config.max_polyphony, admission.active,
                  selected_or_coasting, admission.direct_fundamental_peak,
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::quiet),
                  committed_cache_age, 0.50,
                  kSpectralShadowMarginThresholds[threshold]);
          const std::uint8_t committed_cache_continuity =
              bounded_projection_union(observed_lane_mask,
                                       committed_cached_group,
                                       committed_cached_classifier);
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          if (group_leader && projected != observed_lane_mask) {
            ++label_result
                  .spectral_tier_completion_changed_frames[threshold];
          }
          if (group_leader &&
              projected == spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .spectral_tier_completion_exact_frames[threshold];
          }
          if (lane_mask_matches_label(projected, label)) {
            ++label_result
                  .spectral_tier_completion_matched_frames[threshold];
          }
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .spectral_tier_completion_wrong_string_voices[threshold] +=
                mask_member_count(static_cast<std::uint8_t>(
                    projected &
                    static_cast<std::uint8_t>(~expected_group)));
          }
          if (group_leader &&
              committed_cache_continuity != observed_lane_mask) {
            ++label_result
                  .committed_cache_continuity_changed_frames[threshold];
          }
          if (group_leader &&
              committed_cache_continuity ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .committed_cache_continuity_exact_frames[threshold];
          }
          label_result.committed_cache_continuity_matched_delta[threshold] +=
              static_cast<std::int64_t>(lane_mask_matches_label(
                  committed_cache_continuity, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .committed_cache_continuity_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        committed_cache_continuity &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && combined != observed_lane_mask) {
            ++label_result
                  .combined_spectral_completion_changed_frames[threshold];
          }
          if (group_leader &&
              combined == spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .combined_spectral_completion_exact_frames[threshold];
          }
          if (lane_mask_matches_label(combined, label)) {
            ++label_result
                  .combined_spectral_completion_matched_frames[threshold];
          }
          label_result.combined_spectral_completion_matched_delta[threshold] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(combined, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .combined_spectral_completion_wrong_string_voices[threshold] +=
                mask_member_count(static_cast<std::uint8_t>(
                    combined & static_cast<std::uint8_t>(~expected_group)));
            label_result
                .combined_spectral_completion_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        combined & static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader &&
              cached_classifier_continuity != observed_lane_mask) {
            ++label_result
                  .cached_classifier_continuity_changed_frames[threshold];
          }
          if (group_leader &&
              cached_classifier_continuity ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .cached_classifier_continuity_exact_frames[threshold];
          }
          label_result.cached_classifier_continuity_matched_delta[threshold] +=
              static_cast<std::int64_t>(lane_mask_matches_label(
                  cached_classifier_continuity, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .cached_classifier_continuity_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        cached_classifier_continuity &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader &&
              continuity_classifier_union != observed_lane_mask) {
            ++label_result
                  .continuity_classifier_union_changed_frames[threshold];
          }
          if (group_leader &&
              continuity_classifier_union ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .continuity_classifier_union_exact_frames[threshold];
          }
          label_result.continuity_classifier_union_matched_delta[threshold] +=
              static_cast<std::int64_t>(lane_mask_matches_label(
                  continuity_classifier_union, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .continuity_classifier_union_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        continuity_classifier_union &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader &&
              production_cache_continuity != observed_lane_mask) {
            ++label_result
                  .production_cache_continuity_changed_frames[threshold];
          }
          if (group_leader &&
              production_cache_continuity ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .production_cache_continuity_exact_frames[threshold];
          }
          label_result.production_cache_continuity_matched_delta[threshold] +=
              static_cast<std::int64_t>(lane_mask_matches_label(
                  production_cache_continuity, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .production_cache_continuity_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        production_cache_continuity &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && temporal_combined != observed_lane_mask) {
            ++label_result
                  .temporal_combined_completion_changed_frames[threshold];
          }
          if (group_leader &&
              temporal_combined ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .temporal_combined_completion_exact_frames[threshold];
          }
          label_result.temporal_combined_completion_matched_delta[threshold] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(temporal_combined, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .temporal_combined_completion_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        temporal_combined &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && tier_priority_combined != observed_lane_mask) {
            ++label_result
                  .tier_priority_completion_changed_frames[threshold];
          }
          if (group_leader &&
              tier_priority_combined ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result
                  .tier_priority_completion_exact_frames[threshold];
          }
          label_result.tier_priority_completion_matched_delta[threshold] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(tier_priority_combined, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .tier_priority_completion_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        tier_priority_combined &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && cached_group_combined != observed_lane_mask) {
            ++label_result
                  .cached_group_completion_changed_frames[threshold];
          }
          if (group_leader &&
              cached_group_combined ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result.cached_group_completion_exact_frames[threshold];
          }
          label_result.cached_group_completion_matched_delta[threshold] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(cached_group_combined, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .cached_group_completion_wrong_string_delta[threshold] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        cached_group_combined &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
        }
        for (std::size_t ratio_policy = 0U;
             ratio_policy < kSpectralTierAddedMemberRatioFloors.size();
             ++ratio_policy) {
          const std::uint8_t completion =
              spectral_tier_completion_candidate(
                  static_cast<std::uint8_t>(fine_member_mask), tier_phase,
                  spectral.best_string, spectral.margin, 0.0);
          const std::uint8_t ratio_projected =
              bounded_spectral_tier_completion_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  detector.fine_frequency_added_member_beat_coherence(
                      label.midi_note, completion),
                  detector.fine_frequency_added_member_ratio(
                      label.midi_note, completion),
                  tier_phase, spectral.best_string, spectral.margin, 0.0,
                  kSpectralTierAddedMemberRatioFloors[ratio_policy]);
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          if (group_leader && ratio_projected != observed_lane_mask) {
            ++label_result
                  .tier_ratio_completion_changed_frames[ratio_policy];
          }
          if (group_leader &&
              ratio_projected ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result.tier_ratio_completion_exact_frames[ratio_policy];
          }
          label_result.tier_ratio_completion_matched_delta[ratio_policy] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(ratio_projected, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .tier_ratio_completion_wrong_string_delta[ratio_policy] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        ratio_projected &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (ratio_policy == 3U) {
            const std::size_t phase_index =
                std::min<std::size_t>(2U, static_cast<std::size_t>(tier_phase));
            if (group_leader && ratio_projected != observed_lane_mask) {
              ++label_result.tier_ratio08_changed_by_phase[phase_index];
            }
            label_result.tier_ratio08_matched_delta_by_phase[phase_index] +=
                static_cast<std::int64_t>(
                    lane_mask_matches_label(ratio_projected, label)) -
                static_cast<std::int64_t>(
                    lane_mask_matches_label(observed_lane_mask, label));
            if (group_leader) {
              const std::uint8_t expected_group =
                  spectral_expected_group_masks[label.midi_note];
              label_result.tier_ratio08_wrong_delta_by_phase[phase_index] +=
                  static_cast<std::int64_t>(mask_member_count(
                      static_cast<std::uint8_t>(
                          ratio_projected &
                          static_cast<std::uint8_t>(~expected_group)))) -
                  static_cast<std::int64_t>(mask_member_count(
                      static_cast<std::uint8_t>(
                          observed_lane_mask &
                          static_cast<std::uint8_t>(~expected_group))));
            }
          }
        }
        for (std::size_t beat_policy = 0U;
             beat_policy < kSpectralTierBeatMaximums.size(); ++beat_policy) {
          const std::uint8_t completion =
              spectral_tier_completion_candidate(
                  static_cast<std::uint8_t>(fine_member_mask), tier_phase,
                  spectral.best_string, spectral.margin, 0.0);
          const std::uint8_t beat_projected =
              bounded_spectral_tier_completion_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  detector.fine_frequency_added_member_beat_coherence(
                      label.midi_note, completion),
                  detector.fine_frequency_added_member_ratio(
                      label.midi_note, completion),
                  tier_phase, spectral.best_string, spectral.margin, 0.0,
                  0.08, 0.20, kSpectralTierBeatMaximums[beat_policy]);
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          if (group_leader && beat_projected != observed_lane_mask) {
            ++label_result
                  .tier_beat_completion_changed_frames[beat_policy];
          }
          if (group_leader &&
              beat_projected ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result.tier_beat_completion_exact_frames[beat_policy];
          }
          label_result.tier_beat_completion_matched_delta[beat_policy] +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(beat_projected, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result
                .tier_beat_completion_wrong_string_delta[beat_policy] +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        beat_projected &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
        }
        {
          const std::uint8_t completion =
              spectral_tier_completion_candidate(
                  static_cast<std::uint8_t>(fine_member_mask), tier_phase,
                  spectral.best_string, spectral.margin, 0.0);
          const std::uint8_t ratio08_projected =
              bounded_spectral_tier_completion_proposal(
                  observed_lane_mask,
                  static_cast<std::uint8_t>(fine_member_mask),
                  detector.fine_frequency_added_member_beat_coherence(
                      label.midi_note, completion),
                  detector.fine_frequency_added_member_ratio(
                      label.midi_note, completion),
                  tier_phase, spectral.best_string, spectral.margin, 0.0,
                  0.08);
          const UnisonSpectralClassification& candidate =
              candidate_unison_classifications[label.midi_note];
          std::size_t policy = 0U;
          for (const double maximum_error :
               kRelaxedBandSpectralMaximumErrors) {
            for (const double minimum_margin :
                 kSpectralSingleGapThresholds) {
              const bool classifier_agrees =
                  candidate.valid &&
                  candidate.member_mask == ratio08_projected &&
                  std::isfinite(candidate.error) &&
                  candidate.error <= maximum_error &&
                  std::isfinite(candidate.posterior_margin) &&
                  candidate.posterior_margin >= minimum_margin;
              const std::uint8_t classifier_projected =
                  ratio08_projected != observed_lane_mask &&
                          classifier_agrees
                      ? ratio08_projected
                      : observed_lane_mask;
              const bool group_leader =
                  spectral_group_leader_indices[label.midi_note] ==
                  label_index;
              if (group_leader &&
                  classifier_projected != observed_lane_mask) {
                ++label_result
                      .tier_classifier_completion_changed_frames[policy];
              }
              if (group_leader &&
                  classifier_projected ==
                      spectral_expected_group_masks[label.midi_note]) {
                ++label_result
                      .tier_classifier_completion_exact_frames[policy];
              }
              label_result
                  .tier_classifier_completion_matched_delta[policy] +=
                  static_cast<std::int64_t>(lane_mask_matches_label(
                      classifier_projected, label)) -
                  static_cast<std::int64_t>(
                      lane_mask_matches_label(observed_lane_mask, label));
              if (group_leader) {
                const std::uint8_t expected_group =
                    spectral_expected_group_masks[label.midi_note];
                label_result
                    .tier_classifier_completion_wrong_string_delta[policy] +=
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            classifier_projected & static_cast<std::uint8_t>(
                                                       ~expected_group)))) -
                    static_cast<std::int64_t>(mask_member_count(
                        static_cast<std::uint8_t>(
                            observed_lane_mask & static_cast<std::uint8_t>(
                                                     ~expected_group))));
              }
              ++policy;
            }
          }
        }
        {
          const std::uint8_t fine =
              static_cast<std::uint8_t>(fine_member_mask);
          const std::uint8_t completion =
              spectral_tier_completion_candidate(
                  fine, tier_phase, spectral.best_string, spectral.margin,
                  0.0);
          std::uint8_t safe_tier = bounded_spectral_tier_completion_proposal(
              observed_lane_mask, fine,
              detector.fine_frequency_added_member_beat_coherence(
                  label.midi_note, completion),
              detector.fine_frequency_added_member_ratio(label.midi_note,
                                                          completion),
              tier_phase, spectral.best_string, spectral.margin, 0.0, 0.10);
          const UnisonReacquisitionState& state =
              unison_reacquisition_states[label.midi_note];
          const bool resolved_group_is_recent =
              state.resolved_mask != 0U &&
              state.last_confirmed_sample !=
                  std::numeric_limits<std::uint64_t>::max() &&
              sample_index >= state.last_confirmed_sample &&
              sample_index - state.last_confirmed_sample <=
                  static_cast<std::uint64_t>(std::ceil(
                      3.00 * static_cast<double>(wave.sample_rate)));
          const std::uint8_t temporal_candidate =
              bounded_temporal_spectral_shadow_proposal(
                  observed_lane_mask, fine,
                  detector.fine_frequency_minimum_pairwise_beat_coherence(
                      label.midi_note),
                  detector.temporal_unison_proposal_mask(label.midi_note),
                  candidate_unison_phases[label.midi_note],
                  candidate_unison_classifications[label.midi_note], 0.0);

          std::uint8_t consensus = observed_lane_mask;
          if (lane_outcome == ReplayTargetLaneOutcome::subset_missing &&
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::selected)) {
            const std::uint8_t tier_mask =
                detector.spectral_tier_completion_proposal_mask(
                    label.midi_note);
            const UnisonSpectralClassification& candidate_classification =
                candidate_unison_classifications[label.midi_note];
            const std::array<std::uint8_t, 6U> evidence_masks{
                fine, committed_mask,
                detector.profile_unison_proposal_mask(label.midi_note),
                detector.temporal_unison_proposal_mask(label.midi_note),
                tier_mask,
                candidate_classification.valid
                    ? candidate_classification.member_mask
                    : static_cast<std::uint8_t>(0U)};
            const std::uint8_t other_owned =
                other_note_lane_mask(snapshot, label.midi_note);
            const std::uint8_t preliminary =
                bounded_selected_subset_completion_projection(
                    observed_lane_mask, evidence_masks, other_owned,
                    admission.playable_string_mask, config.max_polyphony, 2U,
                    admission.direct_fundamental_peak, 1.0, false, false);
            std::array<double, 1U << kMaxVoices> pair_coherence{};
            for (std::size_t left = 0U; left < kMaxVoices; ++left) {
              const std::uint8_t left_bit =
                  static_cast<std::uint8_t>(1U << left);
              if ((preliminary & left_bit) == 0U) {
                continue;
              }
              for (std::size_t right = left + 1U; right < kMaxVoices;
                   ++right) {
                const std::uint8_t right_bit =
                    static_cast<std::uint8_t>(1U << right);
                if ((preliminary & right_bit) == 0U) {
                  continue;
                }
                const std::uint8_t pair =
                    static_cast<std::uint8_t>(left_bit | right_bit);
                pair_coherence[pair] =
                    detector.fine_frequency_pairwise_beat_coherence(
                        label.midi_note, pair);
              }
            }
            consensus = bounded_selected_subset_completion_projection(
                observed_lane_mask, evidence_masks, other_owned,
                admission.playable_string_mask, config.max_polyphony, 2U,
                admission.direct_fundamental_peak,
                detector.fine_frequency_pairwise_beat_coherence(
                    label.midi_note, preliminary),
                summarize_pairwise_beat_support(preliminary, pair_coherence,
                                                0.20)
                    .connected,
                false);
          }

          std::uint8_t reacquired = observed_lane_mask;
          if (resolved_group_is_recent) {
            reacquired = bounded_unison_reacquisition_projection(
                observed_lane_mask, state.resolved_mask, fine, committed_mask,
                other_note_lane_mask(snapshot, label.midi_note),
                admission.playable_string_mask, config.max_polyphony,
                admission.direct_fundamental_peak,
                detector.fine_frequency_pairwise_beat_coherence(
                    label.midi_note, fine),
                detector.spectral_tier_completion_proposal_mask(
                    label.midi_note) == state.resolved_mask,
                disposition == static_cast<std::size_t>(
                                   SelectionDisposition::quiet));
          }

          const std::uint8_t fallback_joint = bounded_projection_union(
              observed_lane_mask, consensus, reacquired);
          const std::uint8_t safe_joint =
              safe_tier != observed_lane_mask
                  ? safe_tier
                  : (temporal_candidate != observed_lane_mask
                         ? temporal_candidate
                         : fallback_joint);
          const bool group_leader =
              spectral_group_leader_indices[label.midi_note] == label_index;
          const std::uint8_t bounded_tier =
              bounded_physical_tier_completion_projection(
                  observed_lane_mask, fine,
                  detector.fine_frequency_added_member_beat_coherence(
                      label.midi_note, completion),
                  detector.fine_frequency_added_member_ratio(
                      label.midi_note, completion),
                  tier_phase, spectral.best_string, spectral.margin,
                  other_note_lane_mask(snapshot, label.midi_note),
                  admission.playable_string_mask, config.max_polyphony,
                  disposition == static_cast<std::size_t>(
                                     SelectionDisposition::quiet));
          const FineResidualExpansionEvidence residual_evidence{
              admission.active,
              disposition == static_cast<std::size_t>(
                                 SelectionDisposition::selected),
              admission.direct_fundamental_peak,
              admission.score_threshold_ratio,
              detector.fine_frequency_residual_improvement(label.midi_note),
              detector.fine_frequency_disposition(label.midi_note) ==
                  FineFrequencyDisposition::residual_rejected,
              committed_mask,
              detector.fine_frequency_fit_member_mask(label.midi_note),
              admission.playable_string_mask,
              other_note_lane_mask(snapshot, label.midi_note)};
          const std::uint8_t residual_projection =
              bounded_fine_residual_expansion(
                  residual_evidence, 0.20, 0.0, config.max_polyphony);
          const std::uint8_t bounded_joint = bounded_projection_union(
              observed_lane_mask, bounded_tier,
              residual_projection != 0U ? residual_projection
                                         : observed_lane_mask);
          if (group_leader && bounded_tier != observed_lane_mask) {
            ++label_result.bounded_tier_completion_changed_frames;
          }
          if (group_leader &&
              bounded_tier ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result.bounded_tier_completion_exact_frames;
          }
          label_result.bounded_tier_completion_matched_delta +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(bounded_tier, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result.bounded_tier_completion_wrong_string_delta +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        bounded_tier &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && bounded_joint != observed_lane_mask) {
            ++label_result.bounded_joint_completion_changed_frames;
          }
          if (group_leader &&
              bounded_joint ==
                  spectral_expected_group_masks[label.midi_note]) {
            ++label_result.bounded_joint_completion_exact_frames;
          }
          label_result.bounded_joint_completion_matched_delta +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(bounded_joint, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result.bounded_joint_completion_wrong_string_delta +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        bounded_joint &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
          if (group_leader && safe_joint != observed_lane_mask) {
            ++label_result.safe_joint_completion_changed_frames;
          }
          if (group_leader &&
              safe_joint == spectral_expected_group_masks[label.midi_note]) {
            ++label_result.safe_joint_completion_exact_frames;
          }
          label_result.safe_joint_completion_matched_delta +=
              static_cast<std::int64_t>(
                  lane_mask_matches_label(safe_joint, label)) -
              static_cast<std::int64_t>(
                  lane_mask_matches_label(observed_lane_mask, label));
          if (group_leader) {
            const std::uint8_t expected_group =
                spectral_expected_group_masks[label.midi_note];
            label_result.safe_joint_completion_wrong_string_delta +=
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        safe_joint &
                        static_cast<std::uint8_t>(~expected_group)))) -
                static_cast<std::int64_t>(mask_member_count(
                    static_cast<std::uint8_t>(
                        observed_lane_mask &
                        static_cast<std::uint8_t>(~expected_group))));
          }
        }
        for (std::size_t head = 0U; head < spectral.best_string.size();
             ++head) {
          const std::size_t best =
              spectral.best_string[head] < kMaxVoices
                  ? spectral.best_string[head]
                  : kMaxVoices;
          if (best < label_result
                         .string_fret_spectral_head_best_frames[head]
                         .size()) {
            ++label_result.string_fret_spectral_head_best_frames[head][best];
          }
          const double margin = std::max(0.0, spectral.margin[head]);
          const std::size_t margin_bin = static_cast<std::size_t>(
              std::min(20.0, std::floor(margin * 10000.0)));
          const bool exact = spectral.best_string[head] < kMaxVoices &&
                             (label.string_mask &
                              (1U << spectral.best_string[head])) != 0U;
          auto& bins = exact
                           ? label_result
                                 .spectral_head_correct_margin_frames[head]
                           : label_result
                                 .spectral_head_other_margin_frames[head];
          ++bins[margin_bin];
        }
#endif
#endif
        const bool matched = snapshot_matches_label(snapshot, label);
        result.matched_label_frames += matched ? 1U : 0U;
        label_result.matched_frames += matched ? 1U : 0U;
        if (matched) {
          if (label_result.first_correct_string_sample ==
              std::numeric_limits<std::uint64_t>::max()) {
            label_result.first_correct_string_sample = sample_index;
          }
          ++tracking.current_correct_run_frames;
          label_result.longest_correct_run_frames = std::max(
              label_result.longest_correct_run_frames,
              tracking.current_correct_run_frames);
        } else {
          tracking.current_correct_run_frames = 0U;
        }
        ++label_result.matching_note_lane_mask_frames[observed_lane_mask];
        if (observed_lane_mask != 0U) {
          if (tracking.previous_nonzero_lane_mask != 0U &&
              tracking.previous_nonzero_lane_mask != observed_lane_mask) {
            ++label_result.string_flip_count;
          }
          tracking.previous_nonzero_lane_mask = observed_lane_mask;
        }
        for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
          const TunerVoice& observed = snapshot.voices[voice];
          if (observed.midi_note == label.midi_note &&
              observed.string_index < kMaxVoices) {
            ++label_result.matching_note_lane_frames[observed.string_index];
            label_result.maximum_matching_note_beat_hz_q8 = std::max(
                label_result.maximum_matching_note_beat_hz_q8,
                observed.beat_hz_q8);
          }
          if (!voice_matches_label(observed, label) ||
              !observed.cents_valid) {
            continue;
          }
          if (label_result.first_valid_cents_sample ==
              std::numeric_limits<std::uint64_t>::max()) {
            label_result.first_valid_cents_sample = sample_index;
          }
          if (!label.expected_cents_valid) {
            continue;
          }
          const std::int32_t error_q8 =
              static_cast<std::int32_t>(observed.cents_q8) -
              static_cast<std::int32_t>(label.expected_cents_q8);
          ++label_result.cents_observations;
          label_result.cents_error_sum_q8 += error_q8;
          label_result.cents_error_square_sum_q16 +=
              static_cast<std::uint64_t>(
                  static_cast<std::int64_t>(error_q8) * error_q8);
          label_result.cents_errors_q8.push_back(
              static_cast<std::int16_t>(error_q8));
        }
      }
      for (std::size_t voice_index = 0U;
           voice_index < snapshot.voice_count; ++voice_index) {
        TunerVoice detected_voice = snapshot.voices[voice_index];
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        detected_voice.midi_note =
            snapshot.voices[voice_index].detected_midi_note;
        detected_voice.cents_q8 =
            snapshot.voices[voice_index].detected_cents_q8;
        detected_voice.cents_valid =
            snapshot.voices[voice_index].detected_cents_valid;
#endif
        bool expected = false;
        bool detected_expected = false;
        bool active_label = false;
        bool active_matching_note = false;
        std::uint64_t latest_active_start_sample = 0U;
        for (const ReplayLabel& label : labels) {
          if (sample_index < label.start_sample ||
              sample_index >= label.end_sample) {
            continue;
          }
          active_label = true;
          latest_active_start_sample =
              std::max(latest_active_start_sample, label.start_sample);
          expected = expected ||
                     voice_matches_label(snapshot.voices[voice_index], label);
          detected_expected = detected_expected ||
                              voice_matches_label(detected_voice, label);
          active_matching_note =
              active_matching_note ||
              snapshot.voices[voice_index].midi_note == label.midi_note;
        }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
        if (active_label && calibration != nullptr &&
            config.profile_mode == ProfileMode::m3) {
          const std::size_t members = std::min<std::size_t>(
              kCalibratedPitchRebinMemberBucketCount - 1U,
              mask_member_count(
                  snapshot.voices[voice_index].pitch_evidence_member_mask));
          const std::size_t age = false_wrong_note_age_bucket(
              sample_index, latest_active_start_sample, wave.sample_rate);
          const bool guarded_context =
              calibrated_pitch_rebin_context_eligible(
                  members, age, snapshot_distinct_note_count);
          for (std::size_t threshold_index = 0U;
               threshold_index < kCalibratedPitchRebinThresholds.size();
               ++threshold_index) {
            const CalibratedPitchRebinResult projection =
                calibrated_pitch_rebin(
                    detected_voice.midi_note, detected_voice.cents_q8,
                    detected_voice.cents_valid,
                    snapshot.voices[voice_index].string_index, *calibration,
                    config.max_fret,
                    kCalibratedPitchRebinThresholds[threshold_index]);
            TunerVoice projected = detected_voice;
            projected.midi_note = projection.note;
            bool projected_expected = false;
            for (const ReplayLabel& label : labels) {
              if (sample_index >= label.start_sample &&
                  sample_index < label.end_sample &&
                  voice_matches_label(projected, label)) {
                projected_expected = true;
                break;
              }
            }
            const std::size_t outcome = (detected_expected ? 2U : 0U) |
                                        (projected_expected ? 1U : 0U);
            ++result.calibrated_pitch_rebin_outcome_frames[threshold_index]
                                                           [outcome];
            result.calibrated_pitch_rebin_changed_frames[threshold_index] +=
                projection.changed ? 1U : 0U;
            const bool guarded_expected =
                guarded_context ? projected_expected : detected_expected;
            const std::size_t guarded_outcome =
                (detected_expected ? 2U : 0U) |
                (guarded_expected ? 1U : 0U);
            ++result
                  .calibrated_pitch_rebin_guarded_outcome_frames
                      [threshold_index][guarded_outcome];
            result.calibrated_pitch_rebin_guarded_changed_frames
                  [threshold_index] +=
                guarded_context && projection.changed ? 1U : 0U;
            bool stable_projection = false;
            const std::size_t candidate_note = detected_voice.midi_note;
            const std::uint16_t minimum_rebin_age_ticks =
                static_cast<std::uint16_t>(std::clamp(
                    std::ceil(0.050 * static_cast<double>(wave.sample_rate) /
                              static_cast<double>(kDecisionQuantum)),
                    1.0,
                    static_cast<double>(
                        std::numeric_limits<std::uint16_t>::max())));
            const bool production_context =
                members <= 1U && snapshot_distinct_note_count >= 2U &&
                snapshot.voices[voice_index].age_ticks >=
                    minimum_rebin_age_ticks;
            if (candidate_note < 128U) {
              calibrated_pitch_rebin_latch_seen[threshold_index]
                                                 [candidate_note] = true;
              stable_projection =
                  calibrated_pitch_rebin_latches[threshold_index]
                                                 [candidate_note]
                      .observe(production_context && projection.changed,
                               projection.note, 2U);
            }
            const bool stable_expected =
                stable_projection ? projected_expected : detected_expected;
            const std::size_t stable_outcome =
                (detected_expected ? 2U : 0U) |
                (stable_expected ? 1U : 0U);
            ++result.calibrated_pitch_rebin_stable_outcome_frames
                  [threshold_index][stable_outcome];
            result.calibrated_pitch_rebin_stable_changed_frames
                  [threshold_index] += stable_projection ? 1U : 0U;
            if (threshold_index == 7U) {
              for (std::size_t projected_error_index = 0U;
                   projected_error_index <
                   kCalibratedPitchRebinProjectedErrorThresholds.size();
                   ++projected_error_index) {
                bool error_guarded_projection = false;
                if (candidate_note < 128U) {
                  calibrated_pitch_rebin_projected_error_latch_seen
                      [projected_error_index][candidate_note] = true;
                  error_guarded_projection =
                      calibrated_pitch_rebin_projected_error_latches
                          [projected_error_index][candidate_note]
                              .observe(
                                  production_context &&
                                      calibrated_pitch_rebin_projected_error_eligible(
                                          projection,
                                          kCalibratedPitchRebinProjectedErrorThresholds
                                              [projected_error_index]),
                                  projection.note, 2U);
                }
                const bool error_guarded_expected =
                    error_guarded_projection ? projected_expected
                                             : detected_expected;
                const std::size_t error_guarded_outcome =
                    (detected_expected ? 2U : 0U) |
                    (error_guarded_expected ? 1U : 0U);
                ++result
                      .calibrated_pitch_rebin_projected_error_outcome_frames
                          [projected_error_index][error_guarded_outcome];
                result
                    .calibrated_pitch_rebin_projected_error_changed_frames
                        [projected_error_index] +=
                    error_guarded_projection ? 1U : 0U;
              }
            }
            if (threshold_index == 7U) {
              for (std::size_t label_index = 0U;
                   label_index < labels.size(); ++label_index) {
                const ReplayLabel& label = labels[label_index];
                if (sample_index < label.start_sample ||
                    sample_index >= label.end_sample) {
                  continue;
                }
                const bool label_detected_expected =
                    voice_matches_label(detected_voice, label);
                const bool label_projected_expected =
                    voice_matches_label(projected, label);
                if (!label_detected_expected && !label_projected_expected) {
                  continue;
                }
                ReplayLabelResult& detail = result.label_results[label_index];
                const std::size_t label_outcome =
                    (label_detected_expected ? 2U : 0U) |
                    (label_projected_expected ? 1U : 0U);
                ++detail.calibrated_pitch_rebin_50_outcome_frames
                      [label_outcome];
                detail.calibrated_pitch_rebin_50_changed_frames +=
                    projection.changed ? 1U : 0U;
                const bool label_stable_expected =
                    stable_projection ? label_projected_expected
                                      : label_detected_expected;
                const std::size_t label_stable_outcome =
                    (label_detected_expected ? 2U : 0U) |
                    (label_stable_expected ? 1U : 0U);
                ++detail.calibrated_pitch_rebin_50_stable_outcome_frames
                      [label_stable_outcome];
                detail.calibrated_pitch_rebin_50_stable_changed_frames +=
                    stable_projection ? 1U : 0U;
              }
            }
            if (age < kFalseWrongNoteAgeBucketCount) {
              ++result.calibrated_pitch_rebin_member_age_outcome_frames
                    [threshold_index *
                         kCalibratedPitchRebinMemberBucketCount +
                     members]
                    [age * kCalibratedPitchRebinOutcomeCount + outcome];
            }
            if (guarded_context && projection.changed) {
              const std::size_t string_index =
                  snapshot.voices[voice_index].string_index;
              const std::size_t current_fret =
                  detected_voice.midi_note - kM3OpenNotes[string_index];
              const std::size_t direction =
                  projection.fret_delta < 0 ? 0U : 1U;
              const std::size_t detail_row =
                  (((threshold_index * kMaxVoices + string_index) *
                        kCalibrationFretCount +
                    current_fret) *
                       kCalibratedPitchRebinDirectionCount +
                   direction);
              ++result
                    .calibrated_pitch_rebin_guarded_detail_outcome_frames
                        [detail_row][outcome];
            }
          }

          const std::uint8_t string_index =
              snapshot.voices[voice_index].string_index;
          const std::size_t candidate_note = detected_voice.midi_note;
          const std::uint16_t minimum_rebin_age_ticks =
              static_cast<std::uint16_t>(std::clamp(
                  std::ceil(0.050 * static_cast<double>(wave.sample_rate) /
                            static_cast<double>(kDecisionQuantum)),
                  1.0,
                  static_cast<double>(
                      std::numeric_limits<std::uint16_t>::max())));
          const bool multi_partial_context =
              !detected_voice.cents_valid && members <= 1U &&
              snapshot_distinct_note_count >= 2U &&
              snapshot.voices[voice_index].state ==
                  TunerVoiceState::tracking &&
              snapshot.voices[voice_index].age_ticks >=
                  minimum_rebin_age_ticks &&
              string_index < kM3OpenNotes.size() &&
              candidate_note >= kM3OpenNotes[string_index];
          const StringCalibrationPoint* current_point = nullptr;
          if (multi_partial_context) {
            const std::size_t current_fret =
                candidate_note - kM3OpenNotes[string_index];
            if (current_fret < kCalibrationFretCount &&
                current_fret <= config.max_fret) {
              current_point = calibration->point(string_index, current_fret);
            }
          }
          const PartialAbsoluteCentsEvidence partial_evidence =
              candidate_note < 128U
                  ? detector.partial_absolute_cents_evidence(
                        static_cast<std::uint8_t>(candidate_note))
                  : PartialAbsoluteCentsEvidence{};
          std::size_t policy = 0U;
          for (const std::uint8_t minimum_partials :
               kMultiPartialPhaseMinimumPartials) {
            for (const double maximum_deviation :
                 kMultiPartialPhaseMaximumDeviations) {
              MultiPartialPhaseCentsResult estimate{};
              if (current_point != nullptr &&
                  current_point->quality != CalibrationPointQuality::missing) {
                estimate = robust_multi_partial_phase_cents(
                    partial_evidence, *current_point, minimum_partials,
                    maximum_deviation);
              }
              result.multi_partial_phase_rebin_available_frames[policy] +=
                  estimate.valid ? 1U : 0U;
              CalibratedPitchRebinResult projection{};
              if (estimate.valid) {
                const auto cents_q8 = static_cast<std::int16_t>(
                    std::clamp<long>(
                        std::lround(estimate.cents * 256.0),
                        std::numeric_limits<std::int16_t>::min(),
                        std::numeric_limits<std::int16_t>::max()));
                projection = calibrated_pitch_rebin(
                    static_cast<std::uint8_t>(candidate_note), cents_q8, true,
                    string_index, *calibration, config.max_fret, 50.0);
              }
              bool collision = false;
              if (projection.changed) {
                for (std::size_t other = 0U; other < snapshot.voice_count;
                     ++other) {
                  if (other == voice_index) {
                    continue;
                  }
                  collision = collision ||
                              snapshot.voices[other].detected_midi_note ==
                                  projection.note ||
                              snapshot.voices[other].midi_note ==
                                  projection.note;
                }
              }
              bool stable_projection = false;
              if (candidate_note < 128U) {
                multi_partial_phase_rebin_latch_seen[policy][candidate_note] =
                    true;
                stable_projection =
                    multi_partial_phase_rebin_latches[policy][candidate_note]
                        .observe(
                            multi_partial_context && estimate.valid &&
                                !collision &&
                                calibrated_pitch_rebin_projected_error_eligible(
                                    projection, 15.0),
                            projection.note, 2U);
              }
              TunerVoice projected = detected_voice;
              if (stable_projection) {
                projected.midi_note = projection.note;
              }
              bool projected_expected = false;
              for (const ReplayLabel& label : labels) {
                if (sample_index >= label.start_sample &&
                    sample_index < label.end_sample &&
                    voice_matches_label(projected, label)) {
                  projected_expected = true;
                  break;
                }
              }
              const std::size_t outcome =
                  (detected_expected ? 2U : 0U) |
                  (projected_expected ? 1U : 0U);
              ++result.multi_partial_phase_rebin_outcome_frames[policy]
                                                                [outcome];
              result.multi_partial_phase_rebin_changed_frames[policy] +=
                  stable_projection ? 1U : 0U;
              ++policy;
            }
          }
        }
#endif
        if (expected) {
          continue;
        }
        ++result.false_positive_voices;
        if (!active_label) {
          ++result.false_gap_voices;
        } else if (active_matching_note) {
          ++result.false_wrong_string_voices;
        } else {
          ++result.false_wrong_note_voices;
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
          result.false_wrong_note_detected_expected_frames +=
              detected_expected ? 1U : 0U;
          result.false_wrong_note_output_changed_frames +=
              detected_voice.midi_note !=
                      snapshot.voices[voice_index].midi_note
                  ? 1U
                  : 0U;
          std::size_t nearest_expected_note = 128U;
          std::size_t nearest_distance = 128U;
          const std::size_t observed_note =
              snapshot.voices[voice_index].midi_note;
          for (std::size_t expected_note = 0U; expected_note < 128U;
               ++expected_note) {
            if (spectral_active_references[expected_note] == 0U) {
              continue;
            }
            const std::size_t distance =
                observed_note > expected_note
                    ? observed_note - expected_note
                    : expected_note - observed_note;
            if (distance < nearest_distance) {
              nearest_distance = distance;
              nearest_expected_note = expected_note;
            }
          }
          if (nearest_expected_note < 128U && observed_note < 128U) {
            ++result.false_wrong_note_expected_observed_frames
                  [nearest_expected_note][observed_note];
          }
          const std::size_t interval = candidate_spectral_interval_bucket(
              snapshot.voices[voice_index].midi_note,
              spectral_active_references);
          if (interval < result.false_wrong_note_interval_frames.size()) {
            ++result.false_wrong_note_interval_frames[interval];
            const std::size_t age = false_wrong_note_age_bucket(
                sample_index, latest_active_start_sample, wave.sample_rate);
            if (age < result.false_wrong_note_age_interval_frames.size()) {
              ++result.false_wrong_note_age_interval_frames[age][interval];
            }
            const std::size_t cents = false_wrong_note_cents_bucket(
                snapshot.voices[voice_index].cents_q8,
                snapshot.voices[voice_index].cents_valid);
            if (cents < kFalseWrongNoteCentsBucketCount) {
              ++result.false_wrong_note_interval_cents_frames[interval]
                                                             [cents];
            }
            const std::size_t voice_state = static_cast<std::size_t>(
                snapshot.voices[voice_index].state);
            if (voice_state < kTunerVoiceStateCount) {
              ++result.false_wrong_note_state_interval_frames[voice_state]
                                                            [interval];
            }
            const bool adjacent_below =
                interval == kCandidateSpectralIntervalRadius - 1U;
            const bool adjacent_above =
                interval == kCandidateSpectralIntervalRadius + 1U;
            if (adjacent_below || adjacent_above) {
              const std::size_t direction = adjacent_below ? 0U : 1U;
              const TunerVoice& voice = snapshot.voices[voice_index];
              const auto expected_admission =
                  detector.candidate_admission_diagnostics(
                      static_cast<std::uint8_t>(nearest_expected_note));
              const auto observed_admission =
                  detector.candidate_admission_diagnostics(
                      static_cast<std::uint8_t>(observed_note));
              const auto expected_selection = detector.selection_disposition(
                  static_cast<std::uint8_t>(nearest_expected_note));
              ++result.adjacent_wrong_note_expected_selection_frames
                    [direction][static_cast<std::size_t>(expected_selection)];
              ++result.adjacent_wrong_note_expected_score_ratio_frames
                    [direction][candidate_score_ratio_bin(
                        expected_admission.score_threshold_ratio)];
              const double relative_score =
                  expected_admission.score_threshold_ratio /
                  std::max(observed_admission.score_threshold_ratio,
                           1.0e-12);
              ++result
                    .adjacent_wrong_note_expected_to_observed_score_ratio_frames
                        [direction][candidate_score_ratio_bin(relative_score)];
              ++result.adjacent_wrong_note_expected_evidence_frames
                    [direction][candidate_admission_evidence_flags(
                        expected_admission)];
              std::size_t expected_lane_feasibility = 0U;
              if (expected_admission.playable_string_mask != 0U) {
                expected_lane_feasibility =
                    voice.string_index < kMaxVoices &&
                            (expected_admission.playable_string_mask &
                             (1U << voice.string_index)) != 0U
                        ? 2U
                        : 1U;
              }
              ++result.adjacent_wrong_note_expected_playable_lane_frames
                    [direction][expected_lane_feasibility];
              const std::size_t members =
                  mask_member_count(voice.pitch_evidence_member_mask);
              const std::uint16_t minimum_rebin_age_ticks =
                  static_cast<std::uint16_t>(std::clamp(
                      std::ceil(0.050 * static_cast<double>(wave.sample_rate) /
                                static_cast<double>(kDecisionQuantum)),
                      1.0,
                      static_cast<double>(
                          std::numeric_limits<std::uint16_t>::max())));
              CalibratedPitchRebinResult projection{};
              if (calibration != nullptr &&
                  voice.string_index < kM3OpenNotes.size()) {
                projection = calibrated_pitch_rebin(
                    detected_voice.midi_note, detected_voice.cents_q8,
                    detected_voice.cents_valid, voice.string_index,
                    *calibration, config.max_fret, 50.0);
              }
              bool collision = false;
              if (projection.changed) {
                for (std::size_t other = 0U;
                     other < snapshot.voice_count; ++other) {
                  if (other == voice_index) {
                    continue;
                  }
                  const TunerVoice& other_voice = snapshot.voices[other];
                  collision = collision ||
                              other_voice.detected_midi_note ==
                                  projection.note ||
                              other_voice.midi_note == projection.note;
                }
              }
              const AdjacentWrongNoteProjectionContext context{
                  voice.state == TunerVoiceState::tracking,
                  snapshot_selected_distinct_note_count >= 2U,
                  voice.age_ticks >= minimum_rebin_age_ticks,
                  members == 1U,
                  detected_voice.cents_valid,
                  projection.changed,
                  calibrated_pitch_rebin_projected_error_eligible(
                      projection, 15.0),
                  collision,
              };
              const auto disposition =
                  classify_adjacent_wrong_note_projection(context);
              ++result.adjacent_wrong_note_projection_disposition_frames
                    [direction][static_cast<std::size_t>(disposition)];
              const int expected_direction = adjacent_below ? 1 : -1;
              const auto projection_reason =
                  calibration == nullptr
                      ? CalibratedAdjacentProjectionDisposition::invalid_input
                      : classify_calibrated_adjacent_projection(
                            detected_voice.midi_note,
                            detected_voice.cents_q8,
                            detected_voice.cents_valid, voice.string_index,
                            *calibration, config.max_fret, expected_direction,
                            50.0);
              ++result.adjacent_wrong_note_projection_reason_frames
                    [direction]
                    [static_cast<std::size_t>(projection_reason)];
              const auto expected_presence =
                  classify_adjacent_wrong_note_expected_presence(
                      snapshot,
                      static_cast<std::uint8_t>(nearest_expected_note),
                      voice.string_index);
              ++result.adjacent_wrong_note_expected_presence_frames
                    [direction]
                    [static_cast<std::size_t>(expected_presence)];

              std::uint8_t expected_string_mask = 0U;
              bool note_only_label = false;
              for (const ReplayLabel& label : labels) {
                if (sample_index < label.start_sample ||
                    sample_index >= label.end_sample ||
                    label.midi_note != nearest_expected_note) {
                  continue;
                }
                expected_string_mask = static_cast<std::uint8_t>(
                    expected_string_mask | label.string_mask);
                note_only_label = note_only_label || label.string_mask == 0U;
              }
              AdjacentWrongNoteLaneDisposition lane_disposition =
                  AdjacentWrongNoteLaneDisposition::unavailable;
              if (!note_only_label && expected_string_mask != 0U) {
                const bool lane_matches =
                    voice.string_index < kM3OpenNotes.size() &&
                    (expected_string_mask & (1U << voice.string_index)) != 0U;
                lane_disposition =
                    lane_matches
                        ? AdjacentWrongNoteLaneDisposition::matches
                        : AdjacentWrongNoteLaneDisposition::mismatches;
              }
              ++result.adjacent_wrong_note_lane_disposition_frames
                    [direction][static_cast<std::size_t>(lane_disposition)];
              ++result.adjacent_wrong_note_joint_context_frames[direction]
                    [adjacent_wrong_note_joint_context_index(
                        disposition, expected_presence, lane_disposition)];
              ++result.adjacent_wrong_note_raw_output_lane_frames[direction]
                    [adjacent_wrong_note_raw_output_lane_index(
                        detected_voice.midi_note == nearest_expected_note,
                        detected_voice.midi_note != voice.midi_note,
                        lane_disposition)];
              ++result
                    .adjacent_wrong_note_expected_candidate_context_frames
                        [direction]
                        [adjacent_expected_candidate_context_index(
                            static_cast<std::size_t>(expected_selection),
                            expected_presence, lane_disposition)];
            }
          }
#endif
        }
      }
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      for (std::size_t threshold_index = 0U;
           threshold_index < kCalibratedPitchRebinThresholds.size();
           ++threshold_index) {
        for (std::size_t candidate_note = 0U; candidate_note < 128U;
             ++candidate_note) {
          if (!calibrated_pitch_rebin_latch_seen[threshold_index]
                                                  [candidate_note]) {
            calibrated_pitch_rebin_latches[threshold_index][candidate_note]
                .reset();
          }
        }
      }
      for (std::size_t threshold_index = 0U;
           threshold_index <
           kCalibratedPitchRebinProjectedErrorThresholds.size();
           ++threshold_index) {
        for (std::size_t candidate_note = 0U; candidate_note < 128U;
             ++candidate_note) {
          if (!calibrated_pitch_rebin_projected_error_latch_seen
                   [threshold_index][candidate_note]) {
            calibrated_pitch_rebin_projected_error_latches
                [threshold_index][candidate_note]
                    .reset();
          }
        }
      }
      for (std::size_t policy = 0U;
           policy < kMultiPartialPhasePolicyCount; ++policy) {
        for (std::size_t candidate_note = 0U; candidate_note < 128U;
             ++candidate_note) {
          if (!multi_partial_phase_rebin_latch_seen[policy][candidate_note]) {
            multi_partial_phase_rebin_latches[policy][candidate_note].reset();
          }
        }
      }
#endif
    }
  }
#if defined(M3_JOINT_RESIDUAL_SHADOW) && defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  const auto core_residual = detector.joint_residual_shadow_work();
  result.core_residual_enabled = 1U;
  result.core_residual_evaluated_frames = core_residual.evaluated_frames;
  result.core_residual_valid_frames = core_residual.valid_frames;
  result.core_residual_pending_frames = core_residual.pending_frames;
  result.core_residual_max_work = core_residual.max_rebuild_work;
  result.core_residual_max_pitches = core_residual.max_pitch_count;
  result.core_residual_sum = core_residual.residual_sum;
#endif
  output = result;
  error = ReplayError::none;
  return true;
}

const char* replay_error_name(ReplayError error) noexcept {
  switch (error) {
    case ReplayError::none:
      return "none";
    case ReplayError::invalid_wave:
      return "invalid_wave";
    case ReplayError::unsupported_wave:
      return "unsupported_wave";
    case ReplayError::invalid_labels:
      return "invalid_labels";
    case ReplayError::invalid_config:
      return "invalid_config";
    case ReplayError::invalid_calibration:
      return "invalid_calibration";
    case ReplayError::nonfinite_audio:
      return "nonfinite_audio";
  }
  return "unknown";
}

}  // namespace m3::offline
