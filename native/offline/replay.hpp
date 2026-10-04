#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

#include "m3/string_calibration.hpp"
#include "m3/types.hpp"

namespace m3::offline {

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
                         ReplayResult& output, ReplayError& error);

// Derives one physical-string map from discrete, stable, labeled fret holds.
// Every fret must have at least two rows for the requested single-bit lane.
bool derive_labeled_string_calibration(
    const WaveData& wave, const std::vector<ReplayLabel>& labels,
    const PersistentConfig& config, std::uint8_t string_index,
    StringCalibrationBank& output, ReplayError& error);

const char* replay_error_name(ReplayError error) noexcept;

}  // namespace m3::offline
