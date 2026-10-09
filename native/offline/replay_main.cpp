#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>

#include "m3/calibration_state_image.hpp"
#include "m3/state_image.hpp"
#include "replay.hpp"

namespace {

struct CentsSummary final {
  std::size_t count{};
  double mean{};
  double standard_deviation{};
  double p95_absolute{};
};

CentsSummary summarize_cents(
    const std::vector<std::int16_t>& errors_q8) {
  CentsSummary summary;
  summary.count = errors_q8.size();
  if (errors_q8.empty()) {
    return summary;
  }
  double sum = 0.0;
  double square_sum = 0.0;
  std::vector<std::uint16_t> absolute_errors;
  absolute_errors.reserve(errors_q8.size());
  for (const std::int16_t error_q8 : errors_q8) {
    const double cents = static_cast<double>(error_q8) / 256.0;
    sum += cents;
    square_sum += cents * cents;
    absolute_errors.push_back(static_cast<std::uint16_t>(
        std::abs(static_cast<std::int32_t>(error_q8))));
  }
  summary.mean = sum / static_cast<double>(errors_q8.size());
  summary.standard_deviation = std::sqrt(std::max(
      0.0, square_sum / static_cast<double>(errors_q8.size()) -
               summary.mean * summary.mean));
  const std::size_t percentile_index =
      (95U * absolute_errors.size() + 99U) / 100U - 1U;
  std::nth_element(absolute_errors.begin(),
                   absolute_errors.begin() + percentile_index,
                   absolute_errors.end());
  summary.p95_absolute =
      static_cast<double>(absolute_errors[percentile_index]) / 256.0;
  return summary;
}

bool read_file(const char* path, std::vector<std::uint8_t>& output) {
  output.clear();
  std::FILE* file = std::fopen(path, "rb");
  if (file == nullptr) {
    return false;
  }
  bool ok = std::fseek(file, 0L, SEEK_END) == 0;
  const long length = ok ? std::ftell(file) : -1L;
  ok = ok && length >= 0L && std::fseek(file, 0L, SEEK_SET) == 0;
  if (ok) {
    output.resize(static_cast<std::size_t>(length));
    ok = output.empty() ||
         std::fread(output.data(), 1U, output.size(), file) == output.size();
  }
  ok = std::fclose(file) == 0 && ok;
  if (!ok) {
    output.clear();
  }
  return ok;
}

bool write_file(const char* path, const std::uint8_t* bytes,
                std::size_t size) {
  if (path == nullptr || bytes == nullptr) {
    return false;
  }
  std::FILE* file = std::fopen(path, "wb");
  if (file == nullptr) {
    return false;
  }
  const bool ok = (size == 0U || std::fwrite(bytes, 1U, size, file) == size) &&
                  std::fclose(file) == 0;
  return ok;
}

void usage(const char* program) {
  std::fprintf(
      stderr,
      "usage: %s --wav FILE [--labels FILE] [--calibration FILE] "
      "[--a4 HZ] [--block FRAMES] [--input-trim DB] "
      "[--sensitivity 0..100] [--response 0..100] "
      "[--max-polyphony 1..8] [--max-fret 0..36] [--label-details] "
      "[--derive-calibration-string INDEX --calibration-output FILE "
      "[--exclude-calibration-pass PASS]]\n",
      program);
}

}  // namespace

int main(int argc, char** argv) {
  const char* wave_path = nullptr;
  const char* label_path = nullptr;
  const char* calibration_path = nullptr;
  const char* calibration_output_path = nullptr;
  int calibration_string = -1;
  std::uint8_t excluded_calibration_pass = 0U;
  std::size_t block_size = 512U;
  double a4_hz = 440.0;
  double input_trim_db = -11.6;
  int sensitivity = 70;
  int response = 81;
  int max_polyphony = 8;
  int max_fret = 24;
  bool label_details = false;
  for (int index = 1; index < argc; ++index) {
    const bool has_value = index + 1 < argc;
    if (std::strcmp(argv[index], "--wav") == 0 && has_value) {
      wave_path = argv[++index];
    } else if (std::strcmp(argv[index], "--labels") == 0 && has_value) {
      label_path = argv[++index];
    } else if (std::strcmp(argv[index], "--calibration") == 0 && has_value) {
      calibration_path = argv[++index];
    } else if (std::strcmp(argv[index], "--calibration-output") == 0 &&
               has_value) {
      calibration_output_path = argv[++index];
    } else if (std::strcmp(argv[index], "--derive-calibration-string") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 0L ||
          parsed >= static_cast<long>(m3::kMaxVoices)) {
        usage(argv[0]);
        return 2;
      }
      calibration_string = static_cast<int>(parsed);
    } else if (std::strcmp(argv[index], "--exclude-calibration-pass") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const unsigned long parsed = std::strtoul(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed == 0UL ||
          parsed > 255UL) {
        usage(argv[0]);
        return 2;
      }
      excluded_calibration_pass = static_cast<std::uint8_t>(parsed);
    } else if (std::strcmp(argv[index], "--a4") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed)) {
        usage(argv[0]);
        return 2;
      }
      a4_hz = parsed;
    } else if (std::strcmp(argv[index], "--block") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const unsigned long long parsed = std::strtoull(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed == 0ULL ||
          parsed > static_cast<unsigned long long>(
                       std::numeric_limits<std::size_t>::max())) {
        usage(argv[0]);
        return 2;
      }
      block_size = static_cast<std::size_t>(parsed);
    } else if (std::strcmp(argv[index], "--input-trim") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < -24.0 || parsed > 24.0) {
        usage(argv[0]);
        return 2;
      }
      input_trim_db = parsed;
    } else if (std::strcmp(argv[index], "--sensitivity") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 0L ||
          parsed > 100L) {
        usage(argv[0]);
        return 2;
      }
      sensitivity = static_cast<int>(parsed);
    } else if (std::strcmp(argv[index], "--response") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 0L ||
          parsed > 100L) {
        usage(argv[0]);
        return 2;
      }
      response = static_cast<int>(parsed);
    } else if (std::strcmp(argv[index], "--max-polyphony") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 1L ||
          parsed > static_cast<long>(m3::kMaxVoices)) {
        usage(argv[0]);
        return 2;
      }
      max_polyphony = static_cast<int>(parsed);
    } else if (std::strcmp(argv[index], "--max-fret") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 0L ||
          parsed > 36L) {
        usage(argv[0]);
        return 2;
      }
      max_fret = static_cast<int>(parsed);
    } else if (std::strcmp(argv[index], "--label-details") == 0) {
      label_details = true;
    } else if (std::strcmp(argv[index], "--help") == 0) {
      usage(argv[0]);
      return 0;
    } else {
      usage(argv[0]);
      return 2;
    }
  }
  if (wave_path == nullptr) {
    usage(argv[0]);
    return 2;
  }

  std::vector<std::uint8_t> wave_bytes;
  if (!read_file(wave_path, wave_bytes)) {
    std::fprintf(stderr, "m3_replay: cannot read WAV: %s\n", wave_path);
    return 1;
  }
  m3::offline::ReplayError error{};
  m3::offline::WaveData wave;
  if (!m3::offline::decode_wave_bytes(
          wave_bytes.data(), wave_bytes.size(), wave, error)) {
    std::fprintf(stderr, "m3_replay: %s\n",
                 m3::offline::replay_error_name(error));
    return 1;
  }

  std::vector<m3::offline::ReplayLabel> labels;
  if (label_path != nullptr) {
    std::vector<std::uint8_t> label_bytes;
    if (!read_file(label_path, label_bytes) ||
        !m3::offline::parse_replay_labels(
            reinterpret_cast<const char*>(label_bytes.data()),
            label_bytes.size(), wave.mono_samples.size(), labels, error)) {
      std::fprintf(stderr, "m3_replay: %s\n",
                   m3::offline::replay_error_name(
                       label_bytes.empty() ?
                           m3::offline::ReplayError::invalid_labels : error));
      return 1;
    }
  }

  m3::StringCalibrationBank calibration;
  const m3::StringCalibrationBank* calibration_pointer = nullptr;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.a4_hz = a4_hz;
  config.input_trim_db = input_trim_db;
  config.sensitivity = static_cast<std::uint8_t>(sensitivity);
  config.response = static_cast<std::uint8_t>(response);
  config.max_polyphony = static_cast<std::uint8_t>(max_polyphony);
  config.max_fret = static_cast<std::uint8_t>(max_fret);
  if (calibration_path != nullptr) {
    std::vector<std::uint8_t> calibration_bytes;
    bool decoded = read_file(calibration_path, calibration_bytes);
    if (decoded &&
        (calibration_bytes.size() == m3::kCalibrationStateSize ||
         calibration_bytes.size() == m3::kCalibrationStateV1Size)) {
      decoded = m3::decode_calibration_state(
          calibration_bytes.data(), calibration_bytes.size(), calibration);
    } else if (decoded &&
               (calibration_bytes.size() ==
                    m3::kStateSize + m3::kCalibrationStateSize ||
                calibration_bytes.size() ==
                    m3::kStateSize + m3::kCalibrationStateV1Size)) {
      m3::PersistentConfig saved_config;
      decoded = m3::decode_state(calibration_bytes.data(), m3::kStateSize,
                                 saved_config) &&
                m3::decode_calibration_state(
                    calibration_bytes.data() + m3::kStateSize,
                    calibration_bytes.size() - m3::kStateSize, calibration);
      if (decoded) {
        config = saved_config;
      }
    } else {
      decoded = false;
    }
    if (!decoded) {
      std::fprintf(stderr, "m3_replay: invalid calibration image\n");
      return 1;
    }
    calibration_pointer = &calibration;
  }
  // Command-line controls are intentional replay overrides. Apply them after
  // a combined state+calibration image has restored its saved configuration.
  config.a4_hz = a4_hz;
  config.input_trim_db = input_trim_db;
  config.sensitivity = static_cast<std::uint8_t>(sensitivity);
  config.response = static_cast<std::uint8_t>(response);
  config.max_polyphony = static_cast<std::uint8_t>(max_polyphony);
  config.max_fret = static_cast<std::uint8_t>(max_fret);
  if (calibration_string >= 0) {
    if (calibration_output_path == nullptr || labels.empty()) {
      usage(argv[0]);
      return 2;
    }
    std::vector<m3::offline::ReplayLabel> calibration_labels;
    const std::vector<m3::offline::ReplayLabel>* derivation_labels = &labels;
    if (excluded_calibration_pass != 0U) {
      for (const m3::offline::ReplayLabel& label : labels) {
        if (label.calibration_pass != excluded_calibration_pass) {
          calibration_labels.push_back(label);
        }
      }
      if (calibration_labels.empty()) {
        std::fprintf(stderr, "m3_replay: excluded every calibration label\n");
        return 1;
      }
      derivation_labels = &calibration_labels;
    }
    if (!m3::offline::derive_labeled_string_calibration(
            wave, *derivation_labels, config,
            static_cast<std::uint8_t>(calibration_string), calibration,
            error)) {
      std::fprintf(stderr, "m3_replay: %s\n",
                   m3::offline::replay_error_name(error));
      return 1;
    }
    m3::CalibrationStateImage encoded{};
    if (!m3::encode_calibration_state(calibration, encoded) ||
        !write_file(calibration_output_path, encoded.data(), encoded.size())) {
      std::fprintf(stderr, "m3_replay: cannot write calibration: %s\n",
                   calibration_output_path);
      return 1;
    }
    calibration_pointer = &calibration;
    std::fprintf(stderr,
                 "m3_replay: calibrated string %d -> %s (%zu bytes)\n",
                 calibration_string, calibration_output_path,
                 encoded.size());
  } else if (calibration_output_path != nullptr ||
             excluded_calibration_pass != 0U) {
    usage(argv[0]);
    return 2;
  }

  m3::offline::ReplayResult result;
  if (!m3::offline::run_detector_replay(
          wave, labels, config, calibration_pointer, block_size, result,
          error)) {
    std::fprintf(stderr, "m3_replay: %s\n",
                 m3::offline::replay_error_name(error));
    return 1;
  }
  std::vector<std::int16_t> all_cents_errors;
  for (const m3::offline::ReplayLabelResult& detail : result.label_results) {
    all_cents_errors.insert(all_cents_errors.end(),
                            detail.cents_errors_q8.begin(),
                            detail.cents_errors_q8.end());
  }
  const CentsSummary cents = summarize_cents(all_cents_errors);
  std::printf(
      "sample_rate\tblock\tsamples\tsnapshots\tlabeled\tmatched\t"
      "transitions\ttransitions_inside_holds\ttransitions_in_gaps\t"
      "false_positive_voices\tfalse_gap_voices\tfalse_wrong_note_voices\t"
      "false_wrong_string_voices\tcents_observations\tcents_mean_error\t"
      "cents_sd\tcents_p95_abs\tpartial_detuning_frames\t"
      "partial_detuning_comparisons\tpartial_detuning_mean_abs_error\t"
      "partial_detuning_margin_frames\tpartial_detuning_expected_best_frames\t"
      "partial_detuning_expected_best_rate\tpartial_detuning_mean_margin\t"
      "fingerprint\n"
      "%u\t%zu\t%llu\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t"
      "%zu\t%.6f\t%.6f\t%.6f\t%u\t%u\t%.6f\t%u\t%u\t%.6f\t%.6f\t"
      "%016llx\n",
      wave.sample_rate, block_size,
      static_cast<unsigned long long>(result.sample_count),
      result.snapshot_frames, result.labeled_frames,
      result.matched_label_frames, result.transition_count,
      result.transition_inside_hold_count, result.transition_gap_count,
      result.false_positive_voices, result.false_gap_voices,
      result.false_wrong_note_voices, result.false_wrong_string_voices,
      cents.count, cents.mean, cents.standard_deviation, cents.p95_absolute,
      result.partial_detuning_frames,
      result.partial_detuning_comparisons,
      result.partial_detuning_comparisons != 0U
          ? result.partial_detuning_absolute_error_sum /
                static_cast<double>(result.partial_detuning_comparisons)
          : 0.0,
      result.partial_detuning_margin_frames,
      result.partial_detuning_expected_best_frames,
      result.partial_detuning_margin_frames != 0U
          ? static_cast<double>(result.partial_detuning_expected_best_frames) /
                static_cast<double>(result.partial_detuning_margin_frames)
          : 0.0,
      result.partial_detuning_margin_frames != 0U
          ? result.partial_detuning_margin_sum /
                static_cast<double>(result.partial_detuning_margin_frames)
          : 0.0,
      static_cast<unsigned long long>(result.fingerprint));
  if (label_details) {
    std::printf(
        "label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t"
        "labeled\tmatched\tmatch_percent\t"
        "max_beat_hz\t"
        "lane_0\tlane_1\tlane_2\tlane_3\tlane_4\tlane_5\tlane_6\t"
        "lane_7\tobserved_note_lane_masks\texpected_cents\t"
        "cents_observations\tcents_mean_error\tcents_sd\tcents_p95_abs\t"
        "first_valid_cents_ms\tfirst_correct_string_ms\tstring_flips\t"
        "longest_correct_run_ms");
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    std::printf(
        "\tselection_quiet\tselection_below_threshold\t"
        "selection_spectral_rejected\tselection_dp_evicted\t"
        "selection_selected\tselection_coasting");
#endif
    std::printf("\n");
    for (std::size_t index = 0U; index < labels.size(); ++index) {
      const m3::offline::ReplayLabel& label = labels[index];
      const m3::offline::ReplayLabelResult& detail =
          result.label_results[index];
      const double percent =
          detail.labeled_frames == 0U
              ? 0.0
              : 100.0 * static_cast<double>(detail.matched_frames) /
                    static_cast<double>(detail.labeled_frames);
      const CentsSummary label_cents = summarize_cents(detail.cents_errors_q8);
      std::printf("%zu\t%llu\t%llu\t%u\t%u\t%u\t%u\t%.3f\t%.3f", index,
                  static_cast<unsigned long long>(label.start_sample),
                  static_cast<unsigned long long>(label.end_sample),
                  label.midi_note, label.string_mask,
                  detail.labeled_frames, detail.matched_frames, percent,
                  static_cast<double>(
                      detail.maximum_matching_note_beat_hz_q8) /
                      256.0);
      for (const std::uint32_t lane_frames :
           detail.matching_note_lane_frames) {
        std::printf("\t%u", lane_frames);
      }
      std::printf("\t");
      bool first_mask = true;
      for (std::size_t mask = 0U;
           mask < detail.matching_note_lane_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.matching_note_lane_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_mask ? "" : ",", mask, frames);
        first_mask = false;
      }
      const double expected_cents =
          label.expected_cents_valid
              ? static_cast<double>(label.expected_cents_q8) / 256.0
              : std::numeric_limits<double>::quiet_NaN();
      const double first_valid_ms =
          detail.first_valid_cents_sample ==
                  std::numeric_limits<std::uint64_t>::max()
              ? -1.0
              : 1000.0 * static_cast<double>(
                             detail.first_valid_cents_sample -
                             label.start_sample) /
                    static_cast<double>(wave.sample_rate);
      const double first_correct_ms =
          detail.first_correct_string_sample ==
                  std::numeric_limits<std::uint64_t>::max()
              ? -1.0
              : 1000.0 * static_cast<double>(
                             detail.first_correct_string_sample -
                             label.start_sample) /
                    static_cast<double>(wave.sample_rate);
      const double longest_correct_ms =
          1000.0 * static_cast<double>(
                       detail.longest_correct_run_frames *
                       static_cast<std::uint64_t>(m3::kDecisionQuantum)) /
          static_cast<double>(wave.sample_rate);
      std::printf("\t%.6f\t%zu\t%.6f\t%.6f\t%.6f\t%.3f\t%.3f\t%u\t%.3f",
                  expected_cents, label_cents.count, label_cents.mean,
                  label_cents.standard_deviation,
                  label_cents.p95_absolute, first_valid_ms,
                  first_correct_ms, detail.string_flip_count,
                  longest_correct_ms);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      for (const std::uint32_t frames :
           detail.selection_disposition_frames) {
        std::printf("\t%u", frames);
      }
#endif
      std::printf("\n");
    }
  }
  return 0;
}
