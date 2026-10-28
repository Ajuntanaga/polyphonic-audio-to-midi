#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <type_traits>
#include <vector>

#include "m3/calibration_state_image.hpp"
#include "m3/state_image.hpp"
#include "replay.hpp"
#include "frequency_refinement_shadow.hpp"
#include "unison_spectral_shadow.hpp"

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

void print_fingerprint_mean(const m3::UnisonSpectralFingerprint& sum,
                            std::uint32_t count) {
  if (count == 0U) {
    return;
  }
  for (std::size_t feature = 0U; feature < sum.size(); ++feature) {
    std::printf("%s%.9g", feature == 0U ? "" : ",",
                sum[feature] / static_cast<double>(count));
  }
}

template <typename Value, std::size_t Size>
void print_sequence(const std::array<Value, Size>& values) {
  for (std::size_t index = 0U; index < values.size(); ++index) {
    if constexpr (std::is_floating_point_v<Value>) {
      std::printf("%s%.9g", index == 0U ? "" : ",",
                  static_cast<double>(values[index]));
    } else if constexpr (std::is_signed_v<Value>) {
      std::printf("%s%lld", index == 0U ? "" : ",",
                  static_cast<long long>(values[index]));
    } else {
      std::printf("%s%llu", index == 0U ? "" : ",",
                  static_cast<unsigned long long>(values[index]));
    }
  }
}

template <typename Values>
void print_sparse_u64_bins(const Values& values) {
  bool first = true;
  for (std::size_t index = 0U; index < values.size(); ++index) {
    if (values[index] == 0U) {
      continue;
    }
    std::printf("%s%zu:%llu", first ? "" : ",", index,
                static_cast<unsigned long long>(values[index]));
    first = false;
  }
}

template <typename Matrix>
void print_sparse_u64_joint_bins(const Matrix& values) {
  bool first = true;
  for (std::size_t row = 0U; row < values.size(); ++row) {
    for (std::size_t column = 0U; column < values[row].size(); ++column) {
      if (values[row][column] == 0U) {
        continue;
      }
      std::printf("%s%zu.%zu:%llu", first ? "" : ",", row, column,
                  static_cast<unsigned long long>(values[row][column]));
      first = false;
    }
  }
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
      "[--spectral-shadow-templates FILE] "
      "[--fine-window-dump FILE --fine-window-note 0..127] "
      "[--fine-window-start SECONDS --fine-window-end SECONDS "
      "--fine-window-min-spacing SECONDS] "
      "[--candidate-rescue-score-ratio 0..1 "
      "--candidate-rescue-fundamental-ratio 0..1] "
      "[--diagnostic-fretted-fixed-penalty 0..0.20 "
      "--diagnostic-fretted-per-fret-penalty 0..0.005] "
      "[--diagnostic-calibrated-selector-margin 0..1] "
      "[--diagnostic-calibrated-selector-string-mask 1..255] "
      "[--diagnostic-dp-replacement-similarity 0..1 "
      "--diagnostic-dp-replacement-calibration-margin 0..1 "
      "--diagnostic-dp-replacement-score-margin 0..10] "
      "[--diagnostic-dp-replacement-string-mask 1..255] "
      "[--diagnostic-production-dp-replacement-string-mask 0..255] "
      "[--diagnostic-correlation-seconds 0.020..0.200] "
      "[--diagnostic-selection-window-only] "
      "[--diagnostic-fine-mask-pruning] "
      "[--diagnostic-fine-beat-pruning] "
      "[--diagnostic-collecting-fine-history-carry] "
      "[--diagnostic-joint-pitch-residual] "
      "[--diagnostic-bounded-joint-pitch-residual] "
      "[--diagnostic-correlation-seconds 0.020..0.200 "
      "[--diagnostic-selection-window-only | "
      "--diagnostic-correlation-shadow-only]] "
      "[--diagnostic-early-solo-three-member-continuity] "
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
  const char* spectral_shadow_template_path = nullptr;
  const char* fine_window_dump_path = nullptr;
  int fine_window_note = -1;
  m3::offline::FrequencyWindowCaptureOptions fine_window_options;
  bool fine_window_range_set = false;
  int calibration_string = -1;
  std::uint8_t excluded_calibration_pass = 0U;
  std::size_t block_size = 512U;
  double a4_hz = 440.0;
  double input_trim_db = -11.6;
  int sensitivity = 70;
  int response = 81;
  int max_polyphony = 8;
  int max_fret = 24;
  double candidate_rescue_score_ratio = -1.0;
  double candidate_rescue_fundamental_ratio = -1.0;
  double diagnostic_fretted_fixed_penalty = -1.0;
  double diagnostic_fretted_per_fret_penalty = -1.0;
  double diagnostic_calibrated_selector_margin = -1.0;
  std::uint8_t diagnostic_calibrated_selector_string_mask = 0xffU;
  double diagnostic_dp_replacement_similarity = -1.0;
  double diagnostic_dp_replacement_calibration_margin = -1.0;
  double diagnostic_dp_replacement_score_margin = -1.0;
  std::uint8_t diagnostic_dp_replacement_string_mask = 0xffU;
  std::uint8_t diagnostic_production_dp_replacement_string_mask = 0xffU;
  bool diagnostic_production_dp_replacement_string_mask_set = false;
  bool diagnostic_fine_mask_pruning = false;
  bool diagnostic_fine_beat_pruning = false;
  bool diagnostic_collecting_fine_history_carry = false;
  double diagnostic_correlation_seconds = -1.0;
  bool diagnostic_selection_window_only = false;
  bool diagnostic_correlation_shadow_only = false;
  bool diagnostic_joint_pitch_residual = false;
  bool diagnostic_bounded_joint_pitch_residual = false;
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
    } else if (std::strcmp(argv[index],
                           "--candidate-rescue-score-ratio") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0 || parsed > 1.0) {
        usage(argv[0]);
        return 2;
      }
      candidate_rescue_score_ratio = parsed;
    } else if (std::strcmp(argv[index],
                           "--candidate-rescue-fundamental-ratio") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0 || parsed > 1.0) {
        usage(argv[0]);
        return 2;
      }
      candidate_rescue_fundamental_ratio = parsed;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-fretted-fixed-penalty") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0 || parsed > 0.20) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_fretted_fixed_penalty = parsed;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-fretted-per-fret-penalty") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0 || parsed > 0.005) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_fretted_per_fret_penalty = parsed;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-calibrated-selector-margin") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0 || parsed > 1.0) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_calibrated_selector_margin = parsed;
    } else if (std::strcmp(
                   argv[index],
                   "--diagnostic-calibrated-selector-string-mask") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const unsigned long parsed = std::strtoul(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed == 0UL ||
          parsed > 255UL) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_calibrated_selector_string_mask =
          static_cast<std::uint8_t>(parsed);
    } else if (std::strcmp(argv[index],
                           "--diagnostic-dp-replacement-similarity") == 0 &&
               has_value) {
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (end == argv[index] || *end != '\0' || !std::isfinite(parsed) ||
          parsed < 0.0 || parsed > 1.0) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_dp_replacement_similarity = parsed;
    } else if (std::strcmp(
                   argv[index],
                   "--diagnostic-dp-replacement-calibration-margin") == 0 &&
               has_value) {
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (end == argv[index] || *end != '\0' || !std::isfinite(parsed) ||
          parsed < 0.0 || parsed > 1.0) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_dp_replacement_calibration_margin = parsed;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-dp-replacement-score-margin") == 0 &&
               has_value) {
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (end == argv[index] || *end != '\0' || !std::isfinite(parsed) ||
          parsed < 0.0 || parsed > 10.0) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_dp_replacement_score_margin = parsed;
    } else if (std::strcmp(
                   argv[index],
                   "--diagnostic-dp-replacement-string-mask") == 0 &&
               has_value) {
      char* end = nullptr;
      const unsigned long parsed = std::strtoul(argv[++index], &end, 10);
      if (end == argv[index] || *end != '\0' || parsed == 0UL ||
          parsed > 255UL) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_dp_replacement_string_mask =
          static_cast<std::uint8_t>(parsed);
    } else if (std::strcmp(
                   argv[index],
                   "--diagnostic-production-dp-replacement-string-mask") ==
                   0 &&
               has_value) {
      char* end = nullptr;
      const unsigned long parsed = std::strtoul(argv[++index], &end, 10);
      if (end == argv[index] || *end != '\0' || parsed > 255UL) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_production_dp_replacement_string_mask =
          static_cast<std::uint8_t>(parsed);
      diagnostic_production_dp_replacement_string_mask_set = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-correlation-seconds") == 0 &&
               has_value) {
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.020 || parsed > 0.200) {
        usage(argv[0]);
        return 2;
      }
      diagnostic_correlation_seconds = parsed;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-selection-window-only") == 0) {
      diagnostic_selection_window_only = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-correlation-shadow-only") == 0) {
      diagnostic_correlation_shadow_only = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-joint-pitch-residual") == 0) {
      diagnostic_joint_pitch_residual = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-bounded-joint-pitch-residual") == 0) {
      diagnostic_joint_pitch_residual = true;
      diagnostic_bounded_joint_pitch_residual = true;
    } else if (std::strcmp(argv[index], "--label-details") == 0) {
      label_details = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-fine-mask-pruning") == 0) {
      diagnostic_fine_mask_pruning = true;
    } else if (std::strcmp(argv[index],
                           "--diagnostic-fine-beat-pruning") == 0) {
      diagnostic_fine_beat_pruning = true;
    } else if (std::strcmp(
                   argv[index],
                   "--diagnostic-collecting-fine-history-carry") == 0) {
      diagnostic_collecting_fine_history_carry = true;
    } else if (std::strcmp(argv[index], "--spectral-shadow-templates") == 0 &&
               has_value) {
      spectral_shadow_template_path = argv[++index];
    } else if (std::strcmp(argv[index], "--fine-window-dump") == 0 && has_value) {
      fine_window_dump_path = argv[++index];
    } else if (std::strcmp(argv[index], "--fine-window-note") == 0 && has_value) {
      errno = 0;
      char* end = nullptr;
      const long parsed = std::strtol(argv[++index], &end, 10);
      if (errno != 0 || end == argv[index] || *end != '\0' || parsed < 0L || parsed > 127L) {
        usage(argv[0]);
        return 2;
      }
      fine_window_note = static_cast<int>(parsed);
    } else if ((std::strcmp(argv[index], "--fine-window-start") == 0 ||
                std::strcmp(argv[index], "--fine-window-end") == 0 ||
                std::strcmp(argv[index], "--fine-window-min-spacing") == 0) && has_value) {
      const char* option = argv[index];
      errno = 0;
      char* end = nullptr;
      const double parsed = std::strtod(argv[++index], &end);
      if (errno != 0 || end == argv[index] || *end != '\0' ||
          !std::isfinite(parsed) || parsed < 0.0) {
        usage(argv[0]);
        return 2;
      }
      if (std::strcmp(option, "--fine-window-start") == 0) {
        fine_window_options.start_seconds = parsed;
      } else if (std::strcmp(option, "--fine-window-end") == 0) {
        fine_window_options.end_seconds = parsed;
      } else {
        fine_window_options.min_spacing_seconds = parsed;
      }
      fine_window_range_set = true;
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
  if ((fine_window_dump_path == nullptr && (fine_window_note >= 0 || fine_window_range_set)) ||
      (fine_window_dump_path != nullptr && spectral_shadow_template_path == nullptr) ||
      fine_window_options.end_seconds <= fine_window_options.start_seconds) {
    usage(argv[0]);
    return 2;
  }
  const bool candidate_rescue_requested =
      candidate_rescue_score_ratio >= 0.0 ||
      candidate_rescue_fundamental_ratio >= 0.0;
  if (candidate_rescue_requested &&
      (candidate_rescue_score_ratio < 0.0 ||
       candidate_rescue_fundamental_ratio < 0.0)) {
    usage(argv[0]);
    return 2;
  }
  const bool diagnostic_fretted_prior_requested =
      diagnostic_fretted_fixed_penalty >= 0.0 ||
      diagnostic_fretted_per_fret_penalty >= 0.0;
  if (diagnostic_fretted_prior_requested &&
      (diagnostic_fretted_fixed_penalty < 0.0 ||
       diagnostic_fretted_per_fret_penalty < 0.0)) {
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

  m3::offline::UnisonSpectralShadowTemplateBank spectral_shadow_templates;
  const m3::offline::UnisonSpectralShadowTemplateBank*
      spectral_shadow_template_pointer = nullptr;
  if (spectral_shadow_template_path != nullptr) {
    if (!label_details || labels.empty()) {
      usage(argv[0]);
      return 2;
    }
    std::vector<std::uint8_t> template_bytes;
    if (!read_file(spectral_shadow_template_path, template_bytes) ||
        !m3::offline::parse_unison_spectral_shadow_templates(
            reinterpret_cast<const char*>(template_bytes.data()),
            template_bytes.size(), spectral_shadow_templates)) {
      std::fprintf(stderr, "m3_replay: invalid spectral shadow templates: %s\n",
                   spectral_shadow_template_path);
      return 1;
    }
    spectral_shadow_template_pointer = &spectral_shadow_templates;
  }

  m3::offline::ReplayResult result;
  m3::offline::CandidateAdmissionRescuePolicy candidate_rescue{
      candidate_rescue_score_ratio, candidate_rescue_fundamental_ratio};
  const m3::offline::CandidateAdmissionRescuePolicy* candidate_rescue_pointer =
      candidate_rescue_requested ? &candidate_rescue : nullptr;
  m3::offline::FrettedPositionPriorPolicy fretted_position_prior{
      diagnostic_fretted_fixed_penalty,
      diagnostic_fretted_per_fret_penalty};
  const m3::offline::FrettedPositionPriorPolicy* fretted_position_prior_pointer =
      diagnostic_fretted_prior_requested ? &fretted_position_prior : nullptr;
  m3::offline::DecisiveCalibratedSelectorPolicy calibrated_selector{
      diagnostic_calibrated_selector_margin,
      diagnostic_calibrated_selector_string_mask};
  const m3::offline::DecisiveCalibratedSelectorPolicy*
      calibrated_selector_pointer =
          diagnostic_calibrated_selector_margin >= 0.0
              ? &calibrated_selector
              : nullptr;
  const bool diagnostic_dp_replacement_requested =
      diagnostic_dp_replacement_similarity >= 0.0 ||
      diagnostic_dp_replacement_calibration_margin >= 0.0 ||
      diagnostic_dp_replacement_score_margin >= 0.0;
  if (diagnostic_dp_replacement_requested &&
      (diagnostic_dp_replacement_similarity < 0.0 ||
       diagnostic_dp_replacement_calibration_margin < 0.0 ||
       diagnostic_dp_replacement_score_margin < 0.0)) {
    usage(argv[0]);
    return 2;
  }
  m3::offline::CalibratedDpReplacementPolicy dp_replacement{
      diagnostic_dp_replacement_similarity,
      diagnostic_dp_replacement_calibration_margin,
      diagnostic_dp_replacement_score_margin,
      diagnostic_dp_replacement_string_mask};
  const m3::offline::CalibratedDpReplacementPolicy* dp_replacement_pointer =
      diagnostic_dp_replacement_requested ? &dp_replacement : nullptr;
  m3::offline::ProductionDpReplacementLanePolicy production_dp_lanes{
      diagnostic_dp_replacement_requested &&
              !diagnostic_production_dp_replacement_string_mask_set
          ? static_cast<std::uint8_t>(0U)
          : diagnostic_production_dp_replacement_string_mask};
  const m3::offline::ProductionDpReplacementLanePolicy*
      production_dp_lanes_pointer =
          diagnostic_dp_replacement_requested ||
                  diagnostic_production_dp_replacement_string_mask_set
              ? &production_dp_lanes
              : nullptr;
  if (((diagnostic_selection_window_only ||
        diagnostic_correlation_shadow_only) &&
       diagnostic_correlation_seconds < 0.0) ||
      (diagnostic_selection_window_only &&
       diagnostic_correlation_shadow_only)) {
    usage(argv[0]);
    return 2;
  }
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> fine_window_stream(nullptr, &std::fclose);
  if (fine_window_dump_path != nullptr) {
    fine_window_stream.reset(std::fopen(fine_window_dump_path, "wb"));
    if (fine_window_stream == nullptr) {
      std::fprintf(stderr, "m3_replay: could not open fine-window dump\n");
      return 1;
    }
  }
  m3::offline::FrequencyWindowCapture fine_window_capture(
      fine_window_stream.get(), fine_window_note, fine_window_options);
  if (!m3::offline::run_detector_replay(
          wave, labels, config, calibration_pointer, block_size, result,
          error, spectral_shadow_template_pointer, candidate_rescue_pointer,
          fretted_position_prior_pointer, calibrated_selector_pointer,
          dp_replacement_pointer, production_dp_lanes_pointer,
          diagnostic_fine_mask_pruning,
          diagnostic_fine_beat_pruning,
          diagnostic_collecting_fine_history_carry,
          diagnostic_correlation_seconds,
          diagnostic_selection_window_only,
          diagnostic_correlation_shadow_only,
          diagnostic_joint_pitch_residual,
          fine_window_stream != nullptr ? &fine_window_capture : nullptr,
          diagnostic_bounded_joint_pitch_residual)) {
    std::fprintf(stderr, "m3_replay: %s\n",
                 m3::offline::replay_error_name(error));
    return 1;
  }
  if (fine_window_stream != nullptr &&
      (fine_window_capture.failed() || std::fflush(fine_window_stream.get()) != 0)) {
    std::fprintf(stderr, "m3_replay: fine-window dump write failed\n");
    return 1;
  }
  if (fine_window_stream != nullptr) {
    std::fprintf(stderr, "m3_replay: fine_window_capture windows=%zu cap=512 truncated=%u\n",
        fine_window_capture.windows(), fine_window_capture.truncated() ? 1U : 0U);
    std::fprintf(stderr, "m3_replay: fine_window_range start=%.17g end=%.17g min_spacing=%.17g\n",
        fine_window_options.start_seconds, fine_window_options.end_seconds,
        fine_window_options.min_spacing_seconds);
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
      "partial_detuning_expected_best_rate\tpartial_detuning_mean_margin");
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::printf(
      "\tfalse_wrong_note_intervals\tfalse_wrong_note_age_intervals\t"
      "false_wrong_note_interval_cents\t"
      "false_wrong_note_state_intervals\t"
      "false_wrong_note_expected_observed\t"
      "false_wrong_note_detected_expected\t"
      "false_wrong_note_output_changed\t"
      "adjacent_wrong_note_projection_dispositions\t"
      "adjacent_wrong_note_projection_disposition_frames\t"
      "adjacent_wrong_note_projection_reasons\t"
      "adjacent_wrong_note_projection_reason_frames\t"
      "adjacent_wrong_note_expected_presence\t"
      "adjacent_wrong_note_expected_presence_frames\t"
      "adjacent_wrong_note_lane_dispositions\t"
      "adjacent_wrong_note_lane_disposition_frames\t"
      "adjacent_wrong_note_joint_context_encoding\t"
      "adjacent_wrong_note_joint_context_frames\t"
      "adjacent_wrong_note_raw_output_lane_encoding\t"
      "adjacent_wrong_note_raw_output_lane_frames\t"
      "adjacent_wrong_note_expected_selection_dispositions\t"
      "adjacent_wrong_note_expected_selection_frames\t"
      "adjacent_wrong_note_expected_score_ratio_bins\t"
      "adjacent_wrong_note_expected_score_ratio_frames\t"
      "adjacent_wrong_note_expected_to_observed_score_ratio_bins\t"
      "adjacent_wrong_note_expected_to_observed_score_ratio_frames\t"
      "adjacent_wrong_note_expected_evidence_flags\t"
      "adjacent_wrong_note_expected_evidence_frames\t"
      "adjacent_wrong_note_expected_playable_lane_dispositions\t"
      "adjacent_wrong_note_expected_playable_lane_frames\t"
      "adjacent_wrong_note_expected_candidate_context_encoding\t"
      "adjacent_wrong_note_expected_candidate_context_frames\t"
      "adjacent_envelope_coherence_classes\t"
      "adjacent_envelope_coherence_frames\t"
      "adjacent_spectral_error_gap_frames\t"
      "adjacent_spectral_duplicate_thresholds\t"
      "adjacent_spectral_duplicate_matched\t"
      "adjacent_spectral_duplicate_false_positive\t"
      "adjacent_spectral_duplicate_false_gap\t"
      "adjacent_spectral_duplicate_false_wrong_note\t"
      "adjacent_spectral_duplicate_false_wrong_string\t"
      "adjacent_spectral_duplicate_changed\t"
      "production_adjacent_spectral_duplicate_matched\t"
      "production_adjacent_spectral_duplicate_false_positive\t"
      "production_adjacent_spectral_duplicate_false_gap\t"
      "production_adjacent_spectral_duplicate_false_wrong_note\t"
      "production_adjacent_spectral_duplicate_false_wrong_string\t"
      "production_adjacent_spectral_duplicate_changed\t"
      "multi_partial_phase_minimum_partials\t"
      "multi_partial_phase_maximum_deviations\t"
      "multi_partial_phase_rebin_available\t"
      "multi_partial_phase_rebin_outcomes\t"
      "multi_partial_phase_rebin_changed\t"
      "calibrated_pitch_rebin_thresholds\t"
      "calibrated_pitch_rebin_outcomes\t"
      "calibrated_pitch_rebin_changed\t"
      "calibrated_pitch_rebin_guarded_outcomes\t"
      "calibrated_pitch_rebin_guarded_changed\t"
      "calibrated_pitch_rebin_member_age_outcomes\t"
      "calibrated_pitch_rebin_guarded_detail_outcomes\t"
      "calibrated_pitch_rebin_stable_outcomes\t"
      "calibrated_pitch_rebin_stable_changed\t"
      "calibrated_pitch_rebin_projected_error_thresholds\t"
      "calibrated_pitch_rebin_projected_error_outcomes\t"
      "calibrated_pitch_rebin_projected_error_changed\t"
      "physical_group_labeled\tphysical_group_matched\t"
      "physical_group_missing_string_voices\t"
      "physical_group_extra_string_voices\t"
      "physical_group_lane_outcomes\t"
      "physical_group_expected_member_frames\t"
      "physical_group_member_lane_outcomes\t"
      "physical_group_expected_observed_masks\t"
      "physical_group_fine_lane_outcomes\t"
      "physical_group_committed_lane_outcomes\t"
      "physical_group_selection_lane_outcomes\t"
      "physical_group_causal_encoding\t"
      "physical_group_causal_frames\t"
      "physical_group_pending_causal_encoding\t"
      "physical_group_pending_causal_frames\t"
      "physical_group_member_pending_causal_frames\t"
      "physical_group_pending_triple_recovery_encoding\t"
      "physical_group_pending_triple_recovery_frames\t"
      "physical_group_pending_triple_recovery_context_frames\t"
      "physical_group_pending_triple_cached_matched_delta\t"
      "physical_group_pending_triple_cached_exact_delta\t"
      "physical_group_pending_triple_cached_wrong_string_delta\t"
      "physical_group_completed_triple_fit_encoding\t"
      "physical_group_completed_triple_fit_frames\t"
      "physical_group_hann_beat_mask_encoding\t"
      "physical_group_hann_beat_mask_frames\t"
      "physical_group_hann_beat_coverage_encoding\t"
      "physical_group_hann_beat_coverage\t"
      "physical_group_hann_beat_edge_encoding\t"
      "physical_group_hann_beat_edges\t"
      "physical_group_frequency_refinement_coverage_encoding\t"
      "physical_group_frequency_refinement_coverage\t"
      "physical_group_frequency_refinement_encoding\t"
      "physical_group_frequency_refinement\t"
      "physical_group_member_exact_exit_frames\t"
      "physical_group_causal_runs\t"
      "physical_group_causal_longest_runs\t"
      "physical_group_member_causal_frames\t"
      "physical_group_member_causal_runs\t"
      "physical_group_member_causal_longest_runs\t"
      "physical_group_fine_unresolved_encoding\t"
      "physical_group_fine_unresolved_frames\t"
      "physical_group_fine_unresolved_runs\t"
      "physical_group_fine_unresolved_longest_runs\t"
      "physical_group_member_fine_unresolved_frames\t"
      "physical_group_member_fine_unresolved_runs\t"
      "physical_group_member_fine_unresolved_longest_runs\t"
      "physical_group_fine_classifier_encoding\t"
      "physical_group_fine_classifier_frames\t"
      "physical_group_member_fine_classifier_frames\t"
      "fine_residual_expansion_score_floors\t"
      "fine_residual_expansion_thresholds\t"
      "fine_residual_expansion_changed\t"
      "fine_residual_expansion_exact\t"
      "fine_residual_expansion_matched_delta\t"
      "fine_residual_expansion_wrong_string_delta\t"
      "physical_group_expected_fine_masks\t"
      "physical_group_expected_committed_masks\t"
      "candidate_population_labeled_snapshots\t"
      "candidate_population_target_dispositions\t"
      "candidate_population_other_dispositions\t"
      "candidate_population_target_score_ratio_bins\t"
      "candidate_population_other_score_ratio_bins\t"
      "candidate_population_target_below_score_ratio_bins\t"
      "candidate_population_other_below_score_ratio_bins\t"
      "candidate_population_target_below_fundamental_ratio_bins\t"
      "candidate_population_other_below_fundamental_ratio_bins\t"
      "candidate_population_target_below_evidence_flags\t"
      "candidate_population_other_below_evidence_flags\t"
      "candidate_population_target_below_direct_evidence_bins\t"
      "candidate_population_other_below_direct_evidence_bins\t"
      "candidate_population_target_below_pitch_band_peak_bins\t"
      "candidate_population_other_below_pitch_band_peak_bins\t"
      "candidate_population_below_threshold_calibration_joint\t"
      "candidate_population_unique_playable_direct_frames\t"
      "candidate_population_band_calibration_shadow\t"
      "candidate_population_octave_shadow_similarity_floors\t"
      "candidate_population_octave_shadow_margin_floors\t"
      "candidate_population_octave_shadow_calibration\t"
      "candidate_population_octave_shadow_isolated_context\t"
      "combined_candidate_admission_selected_frames");
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  std::printf(
      "\tcandidate_population_target_spectral_head_vote_masks\t"
      "candidate_population_other_spectral_head_vote_masks");
#endif
  std::printf(
      "\tcandidate_spectral_shadow_active_peak\t"
      "candidate_spectral_shadow_candidate_frames\t"
      "candidate_spectral_shadow_ready_frames\t"
      "candidate_spectral_shadow_selected_frames\t"
      "candidate_spectral_shadow_target_correct_frames\t"
      "candidate_spectral_shadow_target_wrong_string_frames\t"
      "candidate_spectral_shadow_other_false_frames\t"
      "candidate_spectral_shadow_target_correct_by_string_frames\t"
      "candidate_spectral_shadow_target_wrong_string_by_string_frames\t"
      "candidate_spectral_shadow_other_false_by_string_frames\t"
      "candidate_spectral_shadow_other_false_intervals");
#endif
  std::printf(
      "\tfine_mask_complexity_penalties\t"
      "fine_mask_complexity_matched\t"
      "fine_mask_complexity_false_positive\t"
      "fine_mask_complexity_false_gap\t"
      "fine_mask_complexity_false_wrong_note\t"
      "fine_mask_complexity_false_wrong_string\t"
      "fine_mask_complexity_changed\t"
      "correlation_shadow_ratio\tcorrelation_shadow_age_seconds\t"
      "correlation_shadow_fundamental_only\t"
      "correlation_shadow_protect_pending_unison\t"
      "correlation_shadow_matched\tcorrelation_shadow_false_positive\t"
      "correlation_shadow_false_gap\tcorrelation_shadow_false_wrong_note\t"
      "correlation_shadow_false_wrong_string\tcorrelation_shadow_changed\t"
      "joint_pitch_thresholds\tjoint_pitch_overlap_limits\tjoint_pitch_matched\t"
      "joint_pitch_false_positive\tjoint_pitch_false_gap\t"
      "joint_pitch_false_wrong_note\tjoint_pitch_false_wrong_string\t"
      "joint_pitch_changed\tjoint_pitch_valid_frames\t"
      "joint_pitch_invalid_frames\tjoint_pitch_mean_residual\t"
      "joint_pitch_build_pending_frames\tjoint_pitch_max_rebuild_work\t"
      "dp_replacement_matched\tdp_replacement_false_positive\t"
      "dp_replacement_false_gap\tdp_replacement_false_wrong_note\t"
      "dp_replacement_false_wrong_string\tdp_replacement_changed\t"
      "fingerprint\n");
  std::printf(
      "%u\t%zu\t%llu\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t"
      "%zu\t%.6f\t%.6f\t%.6f\t%u\t%u\t%.6f\t%u\t%u\t%.6f\t%.6f",
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
          : 0.0);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  std::printf("\t");
  print_sparse_u64_bins(result.false_wrong_note_interval_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.false_wrong_note_age_interval_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.false_wrong_note_interval_cents_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.false_wrong_note_state_interval_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.false_wrong_note_expected_observed_frames);
  std::printf("\t%llu\t%llu",
              static_cast<unsigned long long>(
                  result.false_wrong_note_detected_expected_frames),
              static_cast<unsigned long long>(
                  result.false_wrong_note_output_changed_frames));
  std::printf(
      "\tnon_tracking,insufficient_polyphonic_context,too_young,"
      "multi_member,cents_unavailable,projection_unavailable,"
      "outside_projected_center_guard,collision,eligible_unapplied\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_projection_disposition_frames);
  std::printf(
      "\tinvalid_input,current_point_unavailable,"
      "expected_adjacent_point_unavailable,expected_adjacent_not_better,"
      "improvement_below_threshold,available\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_projection_reason_frames);
  std::printf(
      "\tabsent,same_string,other_string,same_and_other_string\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_presence_frames);
  std::printf("\tunavailable,matches,mismatches\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_lane_disposition_frames);
  std::printf(
      "\tcontext=((projection*4)+presence)*3+lane\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_joint_context_frames);
  std::printf(
      "\tcontext=((raw_matches_nearest*2)+output_changed)*3+lane\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_raw_output_lane_frames);
  std::printf(
      "\tquiet,below_threshold,spectral_rejected,dp_evicted,selected,"
      "coasting\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_selection_frames);
  std::printf("\t0_to_2_by_0.05\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_score_ratio_frames);
  std::printf("\t0_to_2_by_0.05\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_to_observed_score_ratio_frames);
  std::printf(
      "\tactive=1,direct_fundamental=2,local_peak=4,candidate_evidence=8,"
      "calibrated_direct=16\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_evidence_frames);
  std::printf("\tunavailable,other_lanes,emitted_lane\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_playable_lane_frames);
  std::printf(
      "\tcontext=((expected_selection*4)+expected_presence)*3+lane\t");
  print_sparse_u64_joint_bins(
      result.adjacent_wrong_note_expected_candidate_context_frames);
  std::printf("\tboth_expected,one_expected,neither_expected\t");
  print_sparse_u64_joint_bins(result.adjacent_envelope_coherence_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(result.adjacent_spectral_error_gap_frames);
  std::printf("\t");
  for (std::size_t policy = 0U;
       policy < m3::offline::kAdjacentSpectralDuplicatePolicies.size();
       ++policy) {
    std::printf(
        "%s%.9g", policy == 0U ? "" : ",",
        m3::offline::kAdjacentSpectralDuplicatePolicies[policy]
            .minimum_error_gap);
  }
  const auto print_adjacent_spectral_duplicate_metric =
      [&](const auto& accessor) {
        for (std::size_t policy = 0U;
             policy < result.adjacent_spectral_duplicate_suppression.size();
             ++policy) {
          std::printf(
              "%s%u", policy == 0U ? "" : ",",
              accessor(
                  result.adjacent_spectral_duplicate_suppression[policy]));
        }
      };
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.matched_label_frames; });
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_positive_voices; });
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_gap_voices; });
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_wrong_note_voices; });
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_wrong_string_voices; });
  std::printf("\t");
  print_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.changed_voices; });
  const auto print_production_adjacent_spectral_duplicate_metric =
      [&](const auto& accessor) {
        for (std::size_t policy = 0U;
             policy <
             result.production_adjacent_spectral_duplicate_suppression.size();
             ++policy) {
          std::printf(
              "%s%u", policy == 0U ? "" : ",",
              accessor(result
                           .production_adjacent_spectral_duplicate_suppression
                               [policy]));
        }
      };
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.matched_label_frames; });
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_positive_voices; });
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_gap_voices; });
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_wrong_note_voices; });
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.false_wrong_string_voices; });
  std::printf("\t");
  print_production_adjacent_spectral_duplicate_metric(
      [](const auto& metrics) { return metrics.changed_voices; });
  std::printf("\t");
  print_sequence(m3::offline::kMultiPartialPhaseMinimumPartials);
  std::printf("\t");
  print_sequence(m3::offline::kMultiPartialPhaseMaximumDeviations);
  std::printf("\t");
  print_sequence(result.multi_partial_phase_rebin_available_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.multi_partial_phase_rebin_outcome_frames);
  std::printf("\t");
  print_sequence(result.multi_partial_phase_rebin_changed_frames);
  std::printf("\t");
  print_sequence(m3::offline::kCalibratedPitchRebinThresholds);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_outcome_frames);
  std::printf("\t");
  print_sequence(result.calibrated_pitch_rebin_changed_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_guarded_outcome_frames);
  std::printf("\t");
  print_sequence(result.calibrated_pitch_rebin_guarded_changed_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_member_age_outcome_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_guarded_detail_outcome_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_stable_outcome_frames);
  std::printf("\t");
  print_sequence(result.calibrated_pitch_rebin_stable_changed_frames);
  std::printf("\t");
  print_sequence(
      m3::offline::kCalibratedPitchRebinProjectedErrorThresholds);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.calibrated_pitch_rebin_projected_error_outcome_frames);
  std::printf("\t");
  print_sequence(
      result.calibrated_pitch_rebin_projected_error_changed_frames);
  std::printf("\t%llu\t%llu\t%llu\t%llu\t",
              static_cast<unsigned long long>(
                  result.physical_group_labeled_frames),
              static_cast<unsigned long long>(
                  result.physical_group_matched_frames),
              static_cast<unsigned long long>(
                  result.physical_group_missing_string_voices),
              static_cast<unsigned long long>(
                  result.physical_group_extra_string_voices));
  print_sparse_u64_bins(result.physical_group_lane_outcome_frames);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_expected_member_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_lane_outcome_frames);
  std::printf("\t");
  print_sparse_u64_bins(
      result.physical_group_expected_observed_mask_frames);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_fine_lane_outcome_frames);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_committed_lane_outcome_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_selection_lane_outcome_frames);
  std::printf(
      "\tcell=(((selection*4)+fine_relation)*4+committed_relation)*6+"
      "lane_outcome\t");
  print_sparse_u64_bins(result.physical_group_causal_frames);
  std::printf(
      "\tcell=(((selection*4)+fine_relation)*4+pending_relation)*6+"
      "lane_outcome\t");
  print_sparse_u64_bins(result.physical_group_pending_causal_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_pending_causal_frames);
  std::printf(
      "\tdisposition=articulated_reacquisition,15=inactive_or_low_score;"
      "context=(fine_members*4+cached_relation)*2+continuity_changed;"
      "frame_end_counterfactual\t");
  print_sparse_u64_bins(result.physical_group_pending_triple_recovery_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_pending_triple_recovery_context_frames);
  std::printf("\t");
  print_sequence(result.physical_group_pending_triple_cached_matched_delta);
  std::printf("\t");
  print_sequence(result.physical_group_pending_triple_cached_exact_delta);
  std::printf("\t");
  print_sequence(result.physical_group_pending_triple_cached_wrong_string_delta);
  std::printf(
      "\treason:0..2,fit_count:3..6,fine_count:7..10,disposition:11..14,"
      "rank_plus_one:15..22,beat_ge_0.20:23,connected:24,"
      "pending_relation:25..26,committed_relation:27..28\t");
  bool first_completed_fit = true;
  for (const auto& [key, frames] :
       result.physical_group_completed_triple_fit_frames) {
    std::printf("%s%llu:%llu", first_completed_fit ? "" : ",",
                static_cast<unsigned long long>(key),
                static_cast<unsigned long long>(frames));
    first_completed_fit = false;
  }
  std::printf(
      "\texpected_count:0..3,proposed_count:4..7,proposed_outcome:8..10,"
      "passes(old*2+new):11..12,cycles_bin(<1,<2,<4,>=4):13..15,"
      "output_outcome:16..18\t");
  bool first_hann_mask = true;
  for (const auto& [key, frames] : result.physical_group_hann_beat_mask_frames) {
    std::printf("%s%llu:%llu", first_hann_mask ? "" : ",",
                static_cast<unsigned long long>(key),
                static_cast<unsigned long long>(frames));
    first_hann_mask = false;
  }
  std::printf("\teligible_groups,groups_with_model,prepared_groups,"
              "invalid_prepare_groups,evaluated_masks\t");
  print_sequence(result.physical_group_hann_beat_coverage);
  std::printf(
      "\tkey=note:0..6,edge:7..11,expected_count:12..15,expected_pair:16;"
      "value=frames/hz/min_seconds/max_seconds/old_mean/new_mean/old_min/"
      "old_max/new_min/new_max\t");
  bool first_hann_edge = true;
  for (const auto& [key, edge] : result.physical_group_hann_beat_edges) {
    std::printf("%s%llu:%llu/%.9g/%.9g/%.9g/%.9g/%.9g/%.9g/%.9g/%.9g/%.9g",
                first_hann_edge ? "" : ",",
                static_cast<unsigned long long>(key),
                static_cast<unsigned long long>(edge.frames),
                edge.difference_hz, edge.minimum_window_seconds,
                edge.maximum_window_seconds,
                edge.original_sum / static_cast<double>(edge.frames),
                edge.weighted_sum / static_cast<double>(edge.frames),
                edge.original_minimum, edge.original_maximum,
                edge.weighted_minimum, edge.weighted_maximum);
    first_hann_edge = false;
  }
  std::printf("\teligible_groups,groups_with_model,prepared_groups,evaluated_masks\t");
  print_sequence(result.physical_group_frequency_refinement_coverage);
  std::printf(
      "\tkey=note:0..6,expected_mask:7..14,model_mask:15..22,"
      "output_outcome:23..25,arm(fixed/common/independent):26..27;"
      "value=frames/valid/bounded/beat_supported/heldout_gain/qualified/useful_gain/"
      "train_mean/test_refit_mean/test_prediction_mean/max_cents/min_condition/"
      "cents_mean_string0..7;gain=test_refit_drop>=0.02;qualified=not_bounded+"
      "full_window_beat>=0.20+train_and_test_amplitude_ratio>=0.12;"
      "useful=qualified+gain+train_nonregression+prediction_improves\t");
  bool first_frequency = true;
  for (const auto& [key, summary] : result.physical_group_frequency_refinement) {
    const double denominator = static_cast<double>(
        std::max<std::uint64_t>(1U, summary.valid_frames));
    std::printf("%s%llu:%llu/%llu/%llu/%llu/%llu/%llu/%llu/%.9g/%.9g/%.9g/%.9g/%.9g",
                first_frequency ? "" : ",", static_cast<unsigned long long>(key),
                static_cast<unsigned long long>(summary.frames),
                static_cast<unsigned long long>(summary.valid_frames),
                static_cast<unsigned long long>(summary.bounded_frames),
                static_cast<unsigned long long>(summary.beat_supported_frames),
                static_cast<unsigned long long>(summary.heldout_gain_frames),
                static_cast<unsigned long long>(summary.qualified_frames),
                static_cast<unsigned long long>(summary.useful_gain_frames),
                summary.train_sum / denominator, summary.test_refit_sum / denominator,
                summary.test_prediction_sum / denominator, summary.maximum_cents,
                summary.minimum_conditioning);
    for (double correction_sum : summary.correction_cents_sum) {
      std::printf("/%.9g", correction_sum / denominator);
    }
    first_frequency = false;
  }
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_exact_exit_frames);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_causal_runs);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_causal_longest_run_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(result.physical_group_member_causal_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(result.physical_group_member_causal_runs);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_causal_longest_run_frames);
  std::printf(
      "\tcell=((selection*7)+fine_unresolved_reason)*6+lane_outcome\t");
  print_sparse_u64_bins(result.physical_group_fine_unresolved_frames);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_fine_unresolved_runs);
  std::printf("\t");
  print_sparse_u64_bins(
      result.physical_group_fine_unresolved_longest_run_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_fine_unresolved_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_fine_unresolved_runs);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_fine_unresolved_longest_run_frames);
  std::printf(
      "\tcell=((fine_relation*4)+classifier_relation)*6+lane_outcome\t");
  print_sparse_u64_bins(result.physical_group_fine_classifier_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.physical_group_member_fine_classifier_frames);
  std::printf("\t");
  print_sequence(m3::offline::kFineResidualExpansionScoreFloors);
  std::printf("\t");
  print_sequence(m3::offline::kFineResidualExpansionThresholds);
  std::printf("\t");
  print_sequence(result.fine_residual_expansion_changed_frames);
  std::printf("\t");
  print_sequence(result.fine_residual_expansion_exact_frames);
  std::printf("\t");
  print_sequence(result.fine_residual_expansion_matched_delta);
  std::printf("\t");
  print_sequence(result.fine_residual_expansion_wrong_string_delta);
  std::printf("\t");
  print_sparse_u64_bins(result.physical_group_expected_fine_mask_frames);
  std::printf("\t");
  print_sparse_u64_bins(
      result.physical_group_expected_committed_mask_frames);
  std::printf("\t%llu\t",
              static_cast<unsigned long long>(
                  result.candidate_population_labeled_snapshots));
  print_sparse_u64_bins(
      result.candidate_population_disposition_frames[0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_disposition_frames[1U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_score_threshold_ratio_frames[0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_score_threshold_ratio_frames[1U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_score_ratio_frames[0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_score_ratio_frames[1U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_fundamental_ratio_frames
          [0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_fundamental_ratio_frames
          [1U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_evidence_flag_frames[0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_below_threshold_evidence_flag_frames[1U]);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_below_threshold_direct_evidence_frames[0U]);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_below_threshold_direct_evidence_frames[1U]);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_below_threshold_pitch_band_peak_frames[0U]);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_below_threshold_pitch_band_peak_frames[1U]);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_below_threshold_calibration_joint_frames);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_unique_playable_direct_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_band_calibration_shadow_frames);
  std::printf("\t");
  print_sequence(
      m3::offline::kSpectralShadowCalibrationSimilarityFloors);
  std::printf("\t");
  print_sequence(m3::offline::kSpectralShadowCalibrationMarginFloors);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_octave_shadow_calibration_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_population_octave_shadow_isolated_context_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.combined_candidate_admission_selected_frames);
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_spectral_head_vote_mask_frames[0U]);
  std::printf("\t");
  print_sparse_u64_bins(
      result.candidate_population_spectral_head_vote_mask_frames[1U]);
#endif
  std::printf("\t%llu\t",
              static_cast<unsigned long long>(
                  result.candidate_spectral_shadow_active_peak));
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_candidate_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(result.candidate_spectral_shadow_ready_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_selected_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_target_correct_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_target_wrong_string_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_other_false_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_target_correct_by_string_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_target_wrong_string_by_string_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_other_false_by_string_frames);
  std::printf("\t");
  print_sparse_u64_joint_bins(
      result.candidate_spectral_shadow_other_false_interval_frames);
#endif
  const auto print_complexity_metric = [&](const auto& accessor) {
    for (std::size_t policy = 0U;
         policy < result.fine_mask_complexity.size(); ++policy) {
      std::printf("%s%u", policy == 0U ? "" : ",",
                  accessor(result.fine_mask_complexity[policy]));
    }
  };
  std::printf("\t");
  print_sequence(m3::offline::kFineMaskComplexityPenalties);
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.matched_label_frames; });
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.false_positive_voices; });
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.false_gap_voices; });
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.false_wrong_note_voices; });
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.false_wrong_string_voices; });
  std::printf("\t");
  print_complexity_metric(
      [](const auto& metrics) { return metrics.changed_voices; });
  const auto print_correlation_policy = [&](const auto& accessor) {
    std::printf("\t");
    for (std::size_t policy = 0U;
         policy < m3::offline::kCorrelationShadowPolicies.size(); ++policy) {
      std::printf("%s%.6f", policy == 0U ? "" : ",",
                  static_cast<double>(
                      accessor(m3::offline::kCorrelationShadowPolicies[policy])));
    }
  };
  print_correlation_policy(
      [](const auto& policy) { return policy.maximum_energy_ratio; });
  print_correlation_policy(
      [](const auto& policy) { return policy.minimum_age_seconds; });
  print_correlation_policy(
      [](const auto& policy) { return policy.fundamental_only; });
  print_correlation_policy(
      [](const auto& policy) { return policy.protect_pending_unison; });
  const auto print_correlation_metric = [&](const auto& accessor) {
    std::printf("\t");
    for (std::size_t policy = 0U;
         policy < result.correlation_shadow.size(); ++policy) {
      std::printf("%s%u", policy == 0U ? "" : ",",
                  accessor(result.correlation_shadow[policy]));
    }
  };
  print_correlation_metric(
      [](const auto& metrics) { return metrics.matched_label_frames; });
  print_correlation_metric(
      [](const auto& metrics) { return metrics.false_positive_voices; });
  print_correlation_metric(
      [](const auto& metrics) { return metrics.false_gap_voices; });
  print_correlation_metric(
      [](const auto& metrics) { return metrics.false_wrong_note_voices; });
  print_correlation_metric(
      [](const auto& metrics) { return metrics.false_wrong_string_voices; });
  print_correlation_metric(
      [](const auto& metrics) { return metrics.changed_voices; });
  const auto print_joint_policy = [&](const auto& accessor) {
    std::printf("\t");
    for (std::size_t i = 0U; i < m3::offline::kJointPitchPolicies.size(); ++i) {
      std::printf("%s%.6f", i == 0U ? "" : ",",
                  accessor(m3::offline::kJointPitchPolicies[i]));
    }
  };
  print_joint_policy(
      [](const auto& policy) { return policy.minimum_energy_fraction; });
  print_joint_policy(
      [](const auto& policy) { return policy.maximum_fundamental_overlap; });
  const auto print_joint_metric = [&](const auto& accessor) {
    std::printf("\t");
    for (std::size_t policy = 0U; policy < result.joint_pitch_shadow.size();
         ++policy) {
      std::printf("%s%u", policy == 0U ? "" : ",",
                  accessor(result.joint_pitch_shadow[policy]));
    }
  };
  print_joint_metric(
      [](const auto& metrics) { return metrics.matched_label_frames; });
  print_joint_metric(
      [](const auto& metrics) { return metrics.false_positive_voices; });
  print_joint_metric(
      [](const auto& metrics) { return metrics.false_gap_voices; });
  print_joint_metric(
      [](const auto& metrics) { return metrics.false_wrong_note_voices; });
  print_joint_metric(
      [](const auto& metrics) { return metrics.false_wrong_string_voices; });
  print_joint_metric(
      [](const auto& metrics) { return metrics.changed_voices; });
  std::printf("\t%u\t%u\t%.9f", result.joint_pitch_valid_frames,
              result.joint_pitch_invalid_frames,
              result.joint_pitch_valid_frames == 0U ? 0.0 :
                  result.joint_pitch_residual_sum /
                      static_cast<double>(result.joint_pitch_valid_frames));
  std::printf("\t%u\t%u", result.joint_pitch_build_pending_frames,
              result.joint_pitch_max_rebuild_work);
  std::printf("\t%u\t%u\t%u\t%u\t%u\t%u",
              result.calibrated_dp_replacement.matched_label_frames,
              result.calibrated_dp_replacement.false_positive_voices,
              result.calibrated_dp_replacement.false_gap_voices,
              result.calibrated_dp_replacement.false_wrong_note_voices,
              result.calibrated_dp_replacement.false_wrong_string_voices,
              result.calibrated_dp_replacement.changed_voices);
  std::printf("\t%016llx\n",
              static_cast<unsigned long long>(result.fingerprint));
  if (label_details) {
    std::printf(
        "label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t"
        "calibration_pass\t"
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
        "selection_selected\tselection_coasting\t"
        "group_continuity_diagnostic_flags\tselection_quiet_causes\t"
        "selection_quiet_cause_runs\t"
        "selection_quiet_cause_longest_frames\t"
        "minimum_evidence_resume_flags\t"
        "fine_history_carry_dispositions\t"
        "candidate_unison_spectral_frames\t"
        "candidate_unison_spectral_invalid\t"
        "candidate_unison_spectral_fitted_masks\t"
        "spectral_reacquisition_dispositions\t"
        "spectral_reacquisition_lane_outcomes\t"
        "unison_cache_refresh_dispositions\t"
        "unison_cache_refresh_lane_outcomes\t"
        "candidate_unison_margin_thresholds\t"
        "candidate_unison_projected_changed\t"
        "candidate_unison_projected_exact\t"
        "candidate_unison_projected_matched\t"
        "candidate_unison_projected_wrong_strings\t"
        "unison_reacquisition_hold_seconds\t"
        "unison_reacquisition_projected\t"
        "unison_reacquisition_changed\t"
        "unison_reacquisition_exact\t"
        "unison_reacquisition_matched\t"
        "unison_reacquisition_wrong_strings\t"
        "unison_reacquisition_exact_delta\t"
        "unison_reacquisition_matched_delta\t"
        "unison_reacquisition_wrong_string_delta\t"
        "articulated_unison_reacquisition_gap_seconds\t"
        "articulated_unison_reacquisition_revalidation_seconds\t"
        "articulated_unison_reacquisition_eligible\t"
        "articulated_unison_reacquisition_projected\t"
        "articulated_unison_reacquisition_changed\t"
        "articulated_unison_reacquisition_exact\t"
        "articulated_unison_reacquisition_matched\t"
        "articulated_unison_reacquisition_wrong_strings\t"
        "articulated_unison_reacquisition_exact_delta\t"
        "articulated_unison_reacquisition_matched_delta\t"
        "articulated_unison_reacquisition_wrong_string_delta\t"
        "articulated_unison_reacquisition_accepted_cache_masks\t"
        "three_member_articulated_reacquisition_changed\t"
        "three_member_articulated_reacquisition_exact_delta\t"
        "three_member_articulated_reacquisition_matched_delta\t"
        "three_member_articulated_reacquisition_wrong_string_delta\t"
        "production_three_member_articulated_reacquisition_changed\t"
        "production_three_member_articulated_reacquisition_exact_delta\t"
        "production_three_member_articulated_reacquisition_matched_delta\t"
        "production_three_member_articulated_reacquisition_wrong_string_delta\t"
        "solo_three_member_articulated_reacquisition_changed\t"
        "solo_three_member_articulated_reacquisition_exact_delta\t"
        "solo_three_member_articulated_reacquisition_matched_delta\t"
        "solo_three_member_articulated_reacquisition_wrong_string_delta\t"
        "articulated_unison_reacquisition_dispositions\t"
        "articulated_unison_reacquisition_counterfactual_matched_delta\t"
        "articulated_unison_reacquisition_counterfactual_exact_delta\t"
        "articulated_unison_reacquisition_counterfactual_wrong_string_delta\t"
        "continuity_union_changed\tcontinuity_union_exact\t"
        "continuity_union_matched\tcontinuity_union_exact_delta\t"
        "continuity_union_matched_delta\t"
        "continuity_union_wrong_string_delta\t"
        "observed_fingerprint_maximum_squared_distances\t"
        "observed_fingerprint_reacquisition_projected\t"
        "observed_fingerprint_reacquisition_changed\t"
        "observed_fingerprint_reacquisition_exact\t"
        "observed_fingerprint_reacquisition_matched\t"
        "observed_fingerprint_reacquisition_wrong_strings\t"
        "observed_fingerprint_reacquisition_exact_delta\t"
        "observed_fingerprint_reacquisition_matched_delta\t"
        "observed_fingerprint_reacquisition_wrong_string_delta\t"
        "observed_fingerprint_reacquisition_dispositions\t"
        "observed_fingerprint_reacquisition_selection\t"
        "observed_fingerprint_changed_committed_relations\t"
        "observed_fingerprint_changed_committed_member_counts\t"
        "observed_fingerprint_changed_snapshot_voice_counts\t"
        "observed_fingerprint_changed_other_owned_lane_counts\t"
        "observed_fingerprint_changed_production_dispositions\t"
        "observed_fingerprint_changed_production_cache_age_50ms\t"
        "observed_fingerprint_changed_production_cache_masks\t"
        "observed_fingerprint_changed_score_threshold_ratio_05\t"
        "observed_fingerprint_changed_direct_fundamental\t"
        "selection_quiet_lane_outcomes\t"
        "selection_below_threshold_lane_outcomes\t"
        "selection_spectral_rejected_lane_outcomes\t"
        "selection_dp_evicted_lane_outcomes\t"
        "selection_selected_lane_outcomes\t"
        "selection_coasting_lane_outcomes\t"
        "calibrated_rebin_50_outcomes\t"
        "calibrated_rebin_50_stable_outcomes\t"
        "calibrated_rebin_50_changed\t"
        "calibrated_rebin_50_stable_changed\t"
        "candidate_score_threshold_ratio_bins\t"
        "string_fret_onset_strength_max\t"
        "string_fret_onset_strength_first_250ms_max\t"
        "active_string_fret_onset_strength_max\t"
        "active_string_fret_onset_strength_first_250ms_max\t"
        "candidate_dp_evicted_true_pitch_count\t"
        "candidate_dp_evicted_selected_pitch_count\t"
        "candidate_dp_evicted_score_ratio_bins\t"
        "candidate_dp_evicted_evidence_flags\t"
        "candidate_dp_evicted_playable_lane_count\t"
        "candidate_dp_evicted_calibration_relation\t"
        "candidate_dp_evicted_calibration_similarity\t"
        "candidate_dp_evicted_calibration_margin\t"
        "candidate_dp_evicted_posterior_relation\t"
        "candidate_dp_evicted_posterior_probability\t"
        "candidate_dp_evicted_posterior_margin\t"
        "candidate_below_threshold_score_ratio_bins\t"
        "candidate_below_threshold_fundamental_ratio_bins\t"
        "candidate_below_threshold_evidence_flags\t"
        "candidate_below_threshold_direct_evidence_bins\t"
        "candidate_below_threshold_pitch_band_peak_bins\t"
        "candidate_below_threshold_calibration_correct_similarity_bins\t"
        "candidate_below_threshold_calibration_other_similarity_bins\t"
        "candidate_below_threshold_calibration_correct_margin_bins\t"
        "candidate_below_threshold_calibration_other_margin_bins\t"
        "candidate_below_threshold_calibration_relation_margin\t"
        "candidate_below_threshold_calibration_best_string\t"
        "candidate_spectral_rejected_fundamental_ratio_bins\t"
        "candidate_spectral_rejected_evidence_flags\t"
        "candidate_spectral_rejected_calibration_relation_fundamental_bins\t"
        "candidate_spectral_rejected_calibration_correct_similarity_bins\t"
        "candidate_spectral_rejected_calibration_other_similarity_bins\t"
        "candidate_spectral_rejected_calibration_correct_margin_bins\t"
        "candidate_spectral_rejected_calibration_other_margin_bins\t"
        "candidate_spectral_rejected_calibration_best_string\t"
        "candidate_spectral_rejected_shadow_intervals\t"
        "candidate_spectral_rejected_shadow_fundamental_ratios\t"
        "candidate_spectral_rejected_shadow_kinds\t"
        "candidate_spectral_rejected_shadow_other_eligible\t"
        "candidate_spectral_rejected_shadow_other_active\t"
        "candidate_spectral_rejected_shadow_strongest_other_intervals\t"
        "candidate_spectral_rejected_shadow_strongest_other_evidence\t"
        "posterior_expected_lane_outcomes\t"
        "posterior_other_lane_outcomes\t"
        "posterior_unresolved_lane_outcomes\t"
        "posterior_probability_by_disposition\t"
        "posterior_margin_by_disposition\t"
        "relaxed_band_posterior_probability_floors\t"
        "relaxed_band_posterior_margin_floors\t"
        "relaxed_band_posterior_agreement_frames\t"
        "relaxed_band_spectral_maximum_errors\t"
        "relaxed_band_spectral_margin_floors\t"
        "relaxed_band_spectral_agreement_frames\t"
        "spectral_lane_projection_frames\t"
        "spectral_lane_projection_changed\t"
        "spectral_lane_projection_matched_delta\t"
        "spectral_lane_projection_wrong_string_delta\t"
        "spectral_lane_projection_phase_frames\t"
        "spectral_lane_projection_phase_changed\t"
        "spectral_lane_projection_phase_matched_delta\t"
        "spectral_lane_projection_phase_wrong_string_delta\t"
        "candidate_spectral_lane_projection_frames\t"
        "candidate_spectral_lane_projection_changed\t"
        "candidate_spectral_lane_projection_matched_delta\t"
        "candidate_spectral_lane_projection_wrong_string_delta\t"
        "candidate_spectral_lane_projection_phase_frames\t"
        "candidate_spectral_lane_projection_phase_matched_delta\t"
        "candidate_spectral_lane_projection_phase_wrong_string_delta\t"
        "profile_unison_proposal_masks\t"
        "temporal_unison_proposal_masks\t"
        "committed_unison_masks\t"
        "committed_unison_lane_outcomes\t"
        "retained_unison_dispositions\t"
        "fine_group_dispositions\t"
        "fine_group_disposition_beat_coherence_bins\t"
        "committed_exact_retained_unison_dispositions\t"
        "committed_exact_pairwise_beat_above_gate\t"
        "committed_exact_pairwise_beat_connected\t"
        "longest_committed_exact_retained_disposition_ms\t"
        "committed_exact_fine_unresolved_lane_outcomes\t"
        "committed_exact_fine_exact_lane_outcomes\t"
        "committed_exact_fine_subset_lane_outcomes\t"
        "committed_exact_fine_other_lane_outcomes\t"
        "longest_committed_exact_fine_gap_ms\t"
        "maximum_committed_unison_gap_ticks\t"
        "fine_frequency_member_masks\t"
        "fine_frequency_member_residual_means\t"
        "fine_frequency_member_minimum_ratio_means\t"
        "fine_frequency_member_minimum_beat_coherence_means\t"
        "fine_frequency_member_minimum_beat_coherence_bins\t"
        "fine_unique_member_pruning_floors\t"
        "fine_unique_member_pruning_changed\t"
        "fine_unique_member_pruning_exact\t"
        "fine_unique_member_pruning_matched_delta\t"
        "fine_unique_member_pruning_wrong_string_delta\t"
        "fine_mask_complexity_penalties\t"
        "fine_mask_complexity_changed\t"
        "fine_mask_complexity_exact\t"
        "fine_mask_complexity_matched_delta\t"
        "fine_mask_complexity_wrong_string_delta\t"
        "fine_mask_model_expected_available\t"
        "fine_mask_model_expected_ranks\t"
        "fine_mask_model_exact\t"
        "fine_mask_model_tied\t"
        "fine_mask_model_winner_members\t"
        "fine_mask_posterior_weights\t"
        "fine_mask_posterior_available\t"
        "fine_mask_posterior_exact\t"
        "fine_mask_posterior_tied\t"
        "fine_mask_beat_floors\t"
        "fine_mask_beat_expected_available\t"
        "fine_mask_beat_exact\t"
        "fine_mask_beat_tied\t"
        "fine_mask_beat_pruning_changed\t"
        "fine_mask_beat_pruning_exact\t"
        "fine_mask_beat_pruning_matched_delta\t"
        "fine_mask_beat_pruning_wrong_string_delta\t"
        "fine_mask_pruning_output_masks\t"
        "fine_frequency_pending_member_masks\t"
        "fine_frequency_fit_member_masks\t"
        "fine_exact_fit_residual_bins\t"
        "fine_other_fit_residual_bins\t"
        "string_fret_posterior_best\t"
        "spectral_corridor_frames\tspectral_onset_frames\t"
        "spectral_settled_frames\tspectral_corridor_mean\t"
        "spectral_onset_mean\tspectral_settled_mean\t"
        "spectral_shadow_frames\tspectral_shadow_invalid\t"
        "spectral_shadow_fitted_masks\t"
        "spectral_shadow_residual_means\t"
        "spectral_shadow_margin_means\t"
        "spectral_shadow_onset_masks\t"
        "spectral_shadow_settled_masks\t"
        "spectral_shadow_dispositions\t"
        "spectral_shadow_fine_disagreements\t"
        "spectral_shadow_beat_compared\t"
        "spectral_shadow_beat_disagreements\t"
        "spectral_shadow_profile_disagreements\t"
        "spectral_shadow_temporal_disagreements\t"
        "spectral_shadow_assignment_disagreements\t"
        "spectral_single_frames\tspectral_single_invalid\t"
        "spectral_single_fitted_masks\t"
        "spectral_single_error_means\t"
        "spectral_single_margin_means\t"
        "spectral_single_dispositions\t"
        "spectral_single_onset_strings\t"
        "spectral_single_settled_strings\t"
        "spectral_single_gap_thresholds\t"
        "spectral_single_onset_score_error_means\t"
        "spectral_single_settled_score_error_means\t"
        "spectral_single_onset_gap_support\t"
        "spectral_single_settled_gap_support\t"
        "spectral_single_exact_error_bins\t"
        "spectral_single_other_error_bins\t"
        "spectral_single_exact_margin_bins\t"
        "spectral_single_other_margin_bins\t"
        "spectral_single_group_correct_error_bins\t"
        "spectral_single_group_other_error_bins\t"
        "spectral_single_group_correct_margin_bins\t"
        "spectral_single_group_other_margin_bins\t"
        "spectral_single_below_threshold_exact_error_bins\t"
        "spectral_single_below_threshold_other_error_bins\t"
        "spectral_single_below_threshold_exact_margin_bins\t"
        "spectral_single_below_threshold_other_margin_bins\t"
        "spectral_single_selection_dispositions\t"
        "spectral_single_group_selection_dispositions\t"
        "spectral_shadow_projected_frames\t"
        "spectral_shadow_margin_thresholds\t"
        "spectral_shadow_projected_changed\t"
        "spectral_shadow_projected_exact\t"
        "spectral_shadow_projected_matched\t"
        "spectral_shadow_projected_wrong_strings\t"
        "spectral_onset_latch_committed_masks\t"
        "spectral_onset_latch_qualified_votes\t"
        "spectral_onset_latch_winner_votes\t"
        "spectral_onset_latch_projected_frames\t"
        "spectral_onset_latch_changed\t"
        "spectral_onset_latch_exact\t"
        "spectral_onset_latch_matched\t"
        "spectral_onset_latch_wrong_strings\t"
        "spectral_onset_contraction_changed\t"
        "spectral_onset_contraction_exact\t"
        "spectral_onset_contraction_matched\t"
        "spectral_onset_contraction_matched_delta\t"
        "spectral_onset_contraction_wrong_string_delta\t"
        "spectral_onset_contraction_changed_onset_strength_max\t"
        "spectral_low_best\tspectral_low_mid_best\t"
        "spectral_high_mid_best\tspectral_high_best\t"
        "spectral_overtone_separation_best\t"
        "spectral_head_vote_masks\t"
        "spectral_head_plurality_margin_thresholds\t"
        "spectral_head_plurality_best\t"
        "spectral_tier_production_proposal_masks\t"
        "spectral_tier_production_relation_lane_outcomes\t"
        "selector_group_relation_lane_outcomes\t"
        "tier_completion_disposition_lane_outcomes\t"
        "spectral_tier_completion_frames\t"
        "spectral_tier_completion_candidate_masks\t"
        "spectral_tier_completion_added_member_beat_bins\t"
        "spectral_tier_completion_added_member_ratio_bins\t"
        "selected_subset_consensus_support_floors\t"
        "selected_subset_consensus_projected\t"
        "selected_subset_consensus_changed\t"
        "selected_subset_consensus_exact\t"
        "selected_subset_consensus_matched_delta\t"
        "selected_subset_consensus_wrong_string_delta\t"
        "selected_subset_evidence_outcomes\t"
        "classifier_subset_projection_frames\t"
        "classifier_subset_changed\t"
        "classifier_subset_exact\t"
        "classifier_subset_matched_delta\t"
        "classifier_subset_wrong_string_delta\t"
        "classifier_subset_dispositions\t"
        "spectral_tier_completion_margin_thresholds\t"
        "spectral_tier_completion_changed\t"
        "spectral_tier_completion_exact\t"
        "spectral_tier_completion_matched\t"
        "spectral_tier_completion_wrong_strings\t"
        "combined_spectral_completion_changed\t"
        "combined_spectral_completion_exact\t"
        "combined_spectral_completion_matched\t"
        "combined_spectral_completion_wrong_strings\t"
        "combined_spectral_completion_matched_delta\t"
        "combined_spectral_completion_wrong_string_delta\t"
        "temporal_combined_completion_changed\t"
        "temporal_combined_completion_exact\t"
        "temporal_combined_completion_matched_delta\t"
        "temporal_combined_completion_wrong_string_delta\t"
        "tier_priority_completion_changed\t"
        "tier_priority_completion_exact\t"
        "tier_priority_completion_matched_delta\t"
        "tier_priority_completion_wrong_string_delta\t"
        "cached_group_completion_changed\t"
        "cached_group_completion_exact\t"
        "cached_group_completion_matched_delta\t"
        "cached_group_completion_wrong_string_delta\t"
        "cached_classifier_continuity_changed\t"
        "cached_classifier_continuity_exact\t"
        "cached_classifier_continuity_matched_delta\t"
        "cached_classifier_continuity_wrong_string_delta\t"
        "continuity_classifier_union_changed\t"
        "continuity_classifier_union_exact\t"
        "continuity_classifier_union_matched_delta\t"
        "continuity_classifier_union_wrong_string_delta\t"
        "production_cache_continuity_changed\t"
        "production_cache_continuity_exact\t"
        "production_cache_continuity_matched_delta\t"
        "production_cache_continuity_wrong_string_delta\t"
        "committed_cache_continuity_changed\t"
        "committed_cache_continuity_exact\t"
        "committed_cache_continuity_matched_delta\t"
        "committed_cache_continuity_wrong_string_delta\t"
        "tier_ratio_completion_floors\t"
        "tier_ratio_completion_changed\t"
        "tier_ratio_completion_exact\t"
        "tier_ratio_completion_matched_delta\t"
        "tier_ratio_completion_wrong_string_delta\t"
        "safe_joint_completion_changed\t"
        "safe_joint_completion_exact\t"
        "safe_joint_completion_matched_delta\t"
        "safe_joint_completion_wrong_string_delta\t"
        "bounded_tier_completion_changed\t"
        "bounded_tier_completion_exact\t"
        "bounded_tier_completion_matched_delta\t"
        "bounded_tier_completion_wrong_string_delta\t"
        "bounded_joint_completion_changed\t"
        "bounded_joint_completion_exact\t"
        "bounded_joint_completion_matched_delta\t"
        "bounded_joint_completion_wrong_string_delta\t"
        "fine_exact_completion_changed\t"
        "fine_exact_completion_exact\t"
        "fine_exact_completion_matched_delta\t"
        "fine_exact_completion_wrong_string_delta\t"
        "tier_ratio08_changed_by_phase\t"
        "tier_ratio08_matched_delta_by_phase\t"
        "tier_ratio08_wrong_delta_by_phase\t"
        "tier_beat_completion_maximums\t"
        "tier_beat_completion_changed\t"
        "tier_beat_completion_exact\t"
        "tier_beat_completion_matched_delta\t"
        "tier_beat_completion_wrong_string_delta\t"
        "tier_classifier_completion_changed\t"
        "tier_classifier_completion_exact\t"
        "tier_classifier_completion_matched_delta\t"
        "tier_classifier_completion_wrong_string_delta\t"
        "spectral_low_correct_margin_bins\t"
        "spectral_low_other_margin_bins\t"
        "spectral_low_mid_correct_margin_bins\t"
        "spectral_low_mid_other_margin_bins\t"
        "spectral_high_mid_correct_margin_bins\t"
        "spectral_high_mid_other_margin_bins\t"
        "spectral_high_correct_margin_bins\t"
        "spectral_high_other_margin_bins\t"
        "spectral_overtone_correct_margin_bins\t"
        "spectral_overtone_other_margin_bins\t"
        "fine_unresolved_reasons\t"
        "fine_unresolved\tfine_amplitude_single\t"
        "fine_source_rejected\tfine_residual_rejected\t"
        "fine_multi_candidate");
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
      std::printf("%zu\t%llu\t%llu\t%u\t%u\t%u\t%u\t%u\t%.3f\t%.3f", index,
                  static_cast<unsigned long long>(label.start_sample),
                  static_cast<unsigned long long>(label.end_sample),
                  label.midi_note, label.string_mask, label.calibration_pass,
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
      const auto print_bins = [](const auto& bins) {
        bool first = true;
        for (std::size_t bin = 0U; bin < bins.size(); ++bin) {
          if (bins[bin] == 0U) {
            continue;
          }
          std::printf("%s%zu:%u", first ? "" : ",", bin, bins[bin]);
          first = false;
        }
      };
      std::printf("\t");
      print_bins(detail.group_continuity_diagnostic_frames);
      const auto print_joint_bins = [](const auto& matrix) {
        bool first = true;
        for (std::size_t row = 0U; row < matrix.size(); ++row) {
          for (std::size_t column = 0U; column < matrix[row].size();
               ++column) {
            if (matrix[row][column] == 0U) {
              continue;
            }
            std::printf("%s%zu.%zu:%u", first ? "" : ",", row, column,
                        matrix[row][column]);
            first = false;
          }
        }
      };
      const auto print_joint_signed_bins = [](const auto& matrix) {
        bool first = true;
        for (std::size_t row = 0U; row < matrix.size(); ++row) {
          for (std::size_t column = 0U; column < matrix[row].size();
               ++column) {
            if (matrix[row][column] == 0) {
              continue;
            }
            std::printf("%s%zu.%zu:%lld", first ? "" : ",", row, column,
                        static_cast<long long>(matrix[row][column]));
            first = false;
          }
        }
      };
      std::printf("\t");
      print_bins(detail.quiet_disposition_frames);
      std::printf("\t");
      print_bins(detail.quiet_disposition_runs);
      std::printf("\t");
      print_bins(detail.longest_quiet_disposition_run_frames);
      std::printf("\t");
      print_bins(detail.minimum_evidence_resume_flag_frames);
      std::printf("\t");
      print_bins(detail.fine_history_carry_disposition_frames);
      std::printf("\t%u\t%u\t", detail.candidate_unison_spectral_frames,
                  detail.candidate_unison_spectral_invalid_frames);
      print_bins(detail.candidate_unison_spectral_fitted_mask_frames);
      std::printf("\t");
      print_bins(detail.spectral_reacquisition_disposition_frames);
      std::printf("\t");
      print_joint_bins(detail.spectral_reacquisition_lane_outcome_frames);
      std::printf("\t");
      print_bins(detail.unison_cache_refresh_disposition_frames);
      std::printf("\t");
      print_joint_bins(detail.unison_cache_refresh_lane_outcome_frames);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralShadowMarginThresholds);
      std::printf("\t");
      print_sequence(detail.candidate_unison_projected_changed_frames);
      std::printf("\t");
      print_sequence(detail.candidate_unison_projected_exact_frames);
      std::printf("\t");
      print_sequence(detail.candidate_unison_projected_matched_frames);
      std::printf("\t");
      print_sequence(detail.candidate_unison_projected_wrong_string_voices);
      std::printf("\t");
      print_sequence(m3::offline::kUnisonReacquisitionHoldSeconds);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_projected_frames);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_exact_frames);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_matched_frames);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(detail.unison_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_sequence(
          m3::offline::kArticulatedUnisonReacquisitionGapSeconds);
      std::printf("\t");
      print_sequence(
          m3::offline::kArticulatedUnisonReacquisitionRevalidationSeconds);
      std::printf("\t");
      print_sequence(
          detail.articulated_unison_reacquisition_eligible_frames);
      std::printf("\t");
      print_sequence(
          detail.articulated_unison_reacquisition_projected_frames);
      std::printf("\t");
      print_sequence(
          detail.articulated_unison_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(detail.articulated_unison_reacquisition_exact_frames);
      std::printf("\t");
      print_sequence(detail.articulated_unison_reacquisition_matched_frames);
      std::printf("\t");
      print_sequence(
          detail.articulated_unison_reacquisition_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.articulated_unison_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(detail.articulated_unison_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.articulated_unison_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_bins(
          detail.articulated_unison_reacquisition_accepted_cache_mask_frames);
      std::printf("\t");
      print_sequence(
          detail.three_member_articulated_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(
          detail.three_member_articulated_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(
          detail.three_member_articulated_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.three_member_articulated_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_sequence(
          detail.production_three_member_articulated_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(
          detail.production_three_member_articulated_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(
          detail.production_three_member_articulated_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.production_three_member_articulated_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_sequence(
          detail.solo_three_member_articulated_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(
          detail.solo_three_member_articulated_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(
          detail.solo_three_member_articulated_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.solo_three_member_articulated_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(
          detail.articulated_unison_reacquisition_disposition_frames);
      std::printf("\t");
      print_joint_signed_bins(
          detail.articulated_unison_reacquisition_counterfactual_matched_delta);
      std::printf("\t");
      print_joint_signed_bins(
          detail.articulated_unison_reacquisition_counterfactual_exact_delta);
      std::printf("\t");
      print_joint_signed_bins(
          detail.articulated_unison_reacquisition_counterfactual_wrong_string_delta);
      std::printf("\t%u\t%u\t%u\t%lld\t%lld\t%lld",
                  detail.continuity_union_changed_frames,
                  detail.continuity_union_exact_frames,
                  detail.continuity_union_matched_frames,
                  static_cast<long long>(detail.continuity_union_exact_delta),
                  static_cast<long long>(detail.continuity_union_matched_delta),
                  static_cast<long long>(
                      detail.continuity_union_wrong_string_delta));
      std::printf("\t");
      print_sequence(
          m3::offline::kObservedFingerprintMaximumSquaredDistances);
      std::printf("\t");
      print_sequence(
          detail.observed_fingerprint_reacquisition_projected_frames);
      std::printf("\t");
      print_sequence(
          detail.observed_fingerprint_reacquisition_changed_frames);
      std::printf("\t");
      print_sequence(detail.observed_fingerprint_reacquisition_exact_frames);
      std::printf("\t");
      print_sequence(
          detail.observed_fingerprint_reacquisition_matched_frames);
      std::printf("\t");
      print_sequence(
          detail.observed_fingerprint_reacquisition_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.observed_fingerprint_reacquisition_exact_delta);
      std::printf("\t");
      print_sequence(detail.observed_fingerprint_reacquisition_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.observed_fingerprint_reacquisition_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(
          detail.observed_fingerprint_reacquisition_disposition_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_reacquisition_selection_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_committed_relation_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_committed_member_count_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_snapshot_voice_count_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_other_owned_lane_count_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_production_disposition_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_production_cache_age_50ms_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_production_cache_mask_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_score_threshold_ratio_05_frames);
      std::printf("\t");
      print_bins(
          detail.observed_fingerprint_changed_direct_fundamental_frames);
      for (const auto& outcomes : detail.selection_lane_outcome_frames) {
        std::printf("\t");
        print_bins(outcomes);
      }
      std::printf("\t");
      print_bins(detail.calibrated_pitch_rebin_50_outcome_frames);
      std::printf("\t");
      print_bins(detail.calibrated_pitch_rebin_50_stable_outcome_frames);
      std::printf("\t%u\t%u",
                  detail.calibrated_pitch_rebin_50_changed_frames,
                  detail.calibrated_pitch_rebin_50_stable_changed_frames);
      std::printf("\t");
      print_bins(detail.candidate_score_threshold_ratio_frames);
      std::printf("\t%.9f\t%.9f\t%.9f\t%.9f",
                  detail.string_fret_onset_strength_max,
                  detail.string_fret_onset_strength_first_250ms_max,
                  detail.active_string_fret_onset_strength_max,
                  detail.active_string_fret_onset_strength_first_250ms_max);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_true_pitch_count_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_selected_pitch_count_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_score_ratio_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_evidence_flag_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_playable_lane_count_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_calibration_relation_frames);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_dp_evicted_calibration_similarity_frames);
      std::printf("\t");
      print_joint_bins(detail.candidate_dp_evicted_calibration_margin_frames);
      std::printf("\t");
      print_bins(detail.candidate_dp_evicted_posterior_relation_frames);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_dp_evicted_posterior_probability_frames);
      std::printf("\t");
      print_joint_bins(detail.candidate_dp_evicted_posterior_margin_frames);
      std::printf("\t");
      print_bins(detail.candidate_below_threshold_score_ratio_frames);
      std::printf("\t");
      print_bins(detail.candidate_below_threshold_fundamental_ratio_frames);
      std::printf("\t");
      print_bins(detail.candidate_below_threshold_evidence_flag_frames);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_below_threshold_direct_evidence_frames);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_below_threshold_pitch_band_peak_frames);
      std::printf("\t");
      print_bins(detail
                     .candidate_below_threshold_calibration_correct_similarity_frames);
      std::printf("\t");
      print_bins(detail
                     .candidate_below_threshold_calibration_other_similarity_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_below_threshold_calibration_correct_margin_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_below_threshold_calibration_other_margin_frames);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_below_threshold_calibration_relation_margin_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_below_threshold_calibration_best_string_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_fundamental_ratio_frames);
      std::printf("\t");
      print_bins(detail.candidate_spectral_rejected_evidence_flag_frames);
      std::printf("\t");
      print_joint_bins(
          detail
              .candidate_spectral_rejected_calibration_relation_fundamental_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_calibration_correct_similarity_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_calibration_other_similarity_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_calibration_correct_margin_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_calibration_other_margin_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_calibration_best_string_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_shadow_interval_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_shadow_fundamental_ratio_frames);
      std::printf("\t");
      print_bins(detail.candidate_spectral_rejected_shadow_kind_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_shadow_other_eligible_frames);
      std::printf("\t");
      print_bins(
          detail.candidate_spectral_rejected_shadow_other_active_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_shadow_strongest_other_interval_frames);
      std::printf("\t");
      print_bins(
          detail
              .candidate_spectral_rejected_shadow_strongest_other_evidence_frames);
      for (const auto& outcomes : detail.posterior_lane_outcome_frames) {
        std::printf("\t");
        print_bins(outcomes);
      }
      std::printf("\t");
      print_joint_bins(detail.string_fret_posterior_probability_frames);
      std::printf("\t");
      print_joint_bins(detail.string_fret_posterior_margin_frames);
      std::printf("\t");
      print_sequence(
          m3::offline::kRelaxedBandPosteriorProbabilityFloors);
      std::printf("\t");
      print_sequence(m3::offline::kRelaxedBandPosteriorMarginFloors);
      std::printf("\t");
      print_joint_bins(
          detail.relaxed_band_posterior_agreement_frames);
      std::printf("\t");
      print_sequence(m3::offline::kRelaxedBandSpectralMaximumErrors);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralSingleGapThresholds);
      std::printf("\t");
      print_joint_bins(
          detail.relaxed_band_spectral_agreement_frames);
      std::printf("\t");
      print_sequence(detail.spectral_lane_projection_frames);
      std::printf("\t");
      print_sequence(detail.spectral_lane_projection_changed_frames);
      std::printf("\t");
      print_sequence(detail.spectral_lane_projection_matched_delta);
      std::printf("\t");
      print_sequence(detail.spectral_lane_projection_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(detail.spectral_lane_projection_phase_frames);
      std::printf("\t");
      print_joint_bins(
          detail.spectral_lane_projection_phase_changed_frames);
      std::printf("\t");
      print_joint_signed_bins(
          detail.spectral_lane_projection_phase_matched_delta);
      std::printf("\t");
      print_joint_signed_bins(
          detail.spectral_lane_projection_phase_wrong_string_delta);
      std::printf("\t");
      print_sequence(
          detail.candidate_spectral_lane_projection_frames);
      std::printf("\t");
      print_sequence(
          detail.candidate_spectral_lane_projection_changed_frames);
      std::printf("\t");
      print_sequence(
          detail.candidate_spectral_lane_projection_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.candidate_spectral_lane_projection_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(
          detail.candidate_spectral_lane_projection_phase_frames);
      std::printf("\t");
      print_joint_signed_bins(
          detail.candidate_spectral_lane_projection_phase_matched_delta);
      std::printf("\t");
      print_joint_signed_bins(
          detail.candidate_spectral_lane_projection_phase_wrong_string_delta);
      std::printf("\t");
      print_bins(detail.profile_unison_proposal_mask_frames);
      std::printf("\t");
      print_bins(detail.temporal_unison_proposal_mask_frames);
      std::printf("\t");
      print_bins(detail.committed_unison_mask_frames);
      std::printf("\t");
      print_joint_bins(detail.committed_unison_lane_outcome_frames);
      std::printf("\t");
      print_bins(detail.retained_unison_disposition_frames);
      std::printf("\t");
      print_bins(detail.fine_group_disposition_frames);
      std::printf("\t");
      print_joint_bins(detail.fine_group_disposition_beat_coherence_bins);
      std::printf("\t");
      print_bins(detail.committed_exact_retained_unison_disposition_frames);
      std::printf("\t");
      print_joint_bins(
          detail.committed_exact_pairwise_beat_above_gate_frames);
      std::printf("\t");
      print_bins(detail.committed_exact_pairwise_beat_connected_frames);
      std::printf("\t");
      bool first_retained_run = true;
      for (std::size_t reason = 0U;
           reason < detail
                        .longest_committed_exact_retained_disposition_run_frames
                        .size();
           ++reason) {
        const std::uint32_t frames =
            detail.longest_committed_exact_retained_disposition_run_frames
                [reason];
        if (frames == 0U) {
          continue;
        }
        const double milliseconds =
            1000.0 * static_cast<double>(
                         frames * static_cast<std::uint64_t>(
                                      m3::kDecisionQuantum)) /
            static_cast<double>(wave.sample_rate);
        std::printf("%s%zu:%.3f", first_retained_run ? "" : ",", reason,
                    milliseconds);
        first_retained_run = false;
      }
      for (const auto& outcomes :
           detail.committed_exact_fine_relation_lane_outcome_frames) {
        std::printf("\t");
        print_bins(outcomes);
      }
      const double longest_committed_gap_ms =
          1000.0 * static_cast<double>(
                       detail.longest_committed_exact_fine_gap_frames *
                       static_cast<std::uint64_t>(m3::kDecisionQuantum)) /
          static_cast<double>(wave.sample_rate);
      std::printf("\t%.3f\t%u\t", longest_committed_gap_ms,
                  detail.maximum_committed_unison_gap_ticks);
      bool first_fine_mask = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_member_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_fine_mask ? "" : ",", mask,
                    frames);
        first_fine_mask = false;
      }
      std::printf("\t");
      bool first_fine_residual = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_member_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        const double mean =
            detail.fine_frequency_member_mask_residual_sum[mask] /
            static_cast<double>(frames);
        std::printf("%s%zu:%.6f", first_fine_residual ? "" : ",", mask,
                    mean);
        first_fine_residual = false;
      }
      std::printf("\t");
      bool first_fine_ratio = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_member_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        const double mean =
            detail.fine_frequency_member_mask_minimum_ratio_sum[mask] /
            static_cast<double>(frames);
        std::printf("%s%zu:%.6f", first_fine_ratio ? "" : ",", mask,
                    mean);
        first_fine_ratio = false;
      }
      std::printf("\t");
      bool first_fine_beat = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_member_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        const double mean = detail
                                .fine_frequency_member_mask_minimum_beat_coherence_sum
                                    [mask] /
                            static_cast<double>(frames);
        std::printf("%s%zu:%.6f", first_fine_beat ? "" : ",", mask,
                    mean);
        first_fine_beat = false;
      }
      std::printf("\t");
      bool first_fine_beat_bin = true;
      for (std::size_t mask = 0U;
           mask < detail
                      .fine_frequency_member_mask_minimum_beat_coherence_bins
                      .size();
           ++mask) {
        const auto& bins = detail
                               .fine_frequency_member_mask_minimum_beat_coherence_bins
                                   [mask];
        for (std::size_t bin = 0U; bin < bins.size(); ++bin) {
          if (bins[bin] == 0U) {
            continue;
          }
          std::printf("%s%zu.%zu:%u", first_fine_beat_bin ? "" : ",",
                      mask, bin, bins[bin]);
          first_fine_beat_bin = false;
        }
      }
      std::printf("\t");
      print_sequence(m3::offline::kFineUniqueMemberImprovementFloors);
      std::printf("\t");
      print_sequence(detail.fine_unique_member_pruning_changed_frames);
      std::printf("\t");
      print_sequence(detail.fine_unique_member_pruning_exact_frames);
      std::printf("\t");
      print_sequence(detail.fine_unique_member_pruning_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.fine_unique_member_pruning_wrong_string_delta);
      std::printf("\t");
      print_sequence(m3::offline::kFineMaskComplexityPenalties);
      std::printf("\t");
      print_sequence(detail.fine_mask_complexity_changed_frames);
      std::printf("\t");
      print_sequence(detail.fine_mask_complexity_exact_frames);
      std::printf("\t");
      print_sequence(detail.fine_mask_complexity_matched_delta);
      std::printf("\t");
      print_sequence(detail.fine_mask_complexity_wrong_string_delta);
      std::printf("\t");
      std::printf("%u", detail.fine_mask_model_expected_available_frames);
      std::printf("\t");
      print_bins(detail.fine_mask_model_expected_rank_frames);
      std::printf("\t");
      print_sequence(detail.fine_mask_model_exact_frames);
      std::printf("\t");
      print_sequence(detail.fine_mask_model_tied_frames);
      std::printf("\t");
      print_joint_bins(detail.fine_mask_model_winner_member_frames);
      std::printf("\t");
      print_sequence(m3::offline::kFineMaskPosteriorWeights);
      std::printf("\t%u\t", detail.fine_mask_posterior_available_frames);
      print_joint_bins(detail.fine_mask_posterior_exact_frames);
      std::printf("\t");
      print_joint_bins(detail.fine_mask_posterior_tied_frames);
      std::printf("\t");
      print_sequence(m3::offline::kFineMaskBeatCoherenceFloors);
      std::printf("\t");
      print_sequence(detail.fine_mask_beat_expected_available_frames);
      std::printf("\t");
      print_joint_bins(detail.fine_mask_beat_exact_frames);
      std::printf("\t");
      print_joint_bins(detail.fine_mask_beat_tied_frames);
      std::printf("\t%u\t%u\t%lld\t%lld\t",
                  detail.fine_mask_beat_pruning_changed_frames,
                  detail.fine_mask_beat_pruning_exact_frames,
                  static_cast<long long>(
                      detail.fine_mask_beat_pruning_matched_delta),
                  static_cast<long long>(
                      detail.fine_mask_beat_pruning_wrong_string_delta));
      bool first_pruning_mask = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_mask_pruning_output_mask_frames.size();
           ++mask) {
        const std::uint32_t frames =
            detail.fine_mask_pruning_output_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_pruning_mask ? "" : ",", mask,
                    frames);
        first_pruning_mask = false;
      }
      std::printf("\t");
      bool first_pending_mask = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_pending_member_mask_frames.size();
           ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_pending_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_pending_mask ? "" : ",", mask,
                    frames);
        first_pending_mask = false;
      }
      std::printf("\t");
      bool first_fit_mask = true;
      for (std::size_t mask = 0U;
           mask < detail.fine_frequency_fit_member_mask_frames.size();
           ++mask) {
        const std::uint32_t frames =
            detail.fine_frequency_fit_member_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_fit_mask ? "" : ",", mask, frames);
        first_fit_mask = false;
      }
      std::printf("\t");
      print_bins(detail.exact_fit_residual_improvement_frames);
      std::printf("\t");
      print_bins(detail.other_fit_residual_improvement_frames);
      std::printf("\t");
      bool first_posterior = true;
      for (std::size_t string = 0U;
           string < detail.string_fret_posterior_best_frames.size();
           ++string) {
        const std::uint32_t frames =
            detail.string_fret_posterior_best_frames[string];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_posterior ? "" : ",", string,
                    frames);
        first_posterior = false;
      }
      std::printf("\t%u\t%u\t%u\t", detail.spectral_corridor_frames,
                  detail.spectral_onset_frames,
                  detail.spectral_settled_frames);
      print_fingerprint_mean(detail.spectral_corridor_fingerprint_sum,
                             detail.spectral_corridor_frames);
      std::printf("\t");
      print_fingerprint_mean(detail.spectral_onset_fingerprint_sum,
                             detail.spectral_onset_frames);
      std::printf("\t");
      print_fingerprint_mean(detail.spectral_settled_fingerprint_sum,
                             detail.spectral_settled_frames);
      std::printf("\t%u\t%u\t", detail.spectral_shadow_frames,
                  detail.spectral_shadow_invalid_frames);
      print_bins(detail.spectral_shadow_fitted_mask_frames);
      std::printf("\t");
      bool first_shadow_residual = true;
      for (std::size_t mask = 0U;
           mask < detail.spectral_shadow_fitted_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.spectral_shadow_fitted_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%.9g", first_shadow_residual ? "" : ",", mask,
                    detail.spectral_shadow_fitted_mask_residual_sum[mask] /
                        static_cast<double>(frames));
        first_shadow_residual = false;
      }
      std::printf("\t");
      bool first_shadow_margin = true;
      for (std::size_t mask = 0U;
           mask < detail.spectral_shadow_fitted_mask_margin_frames.size();
           ++mask) {
        const std::uint32_t frames =
            detail.spectral_shadow_fitted_mask_margin_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%.9g", first_shadow_margin ? "" : ",", mask,
                    detail.spectral_shadow_fitted_mask_margin_sum[mask] /
                        static_cast<double>(frames));
        first_shadow_margin = false;
      }
      std::printf("\t");
      print_bins(detail.spectral_shadow_phase_mask_frames[0U]);
      std::printf("\t");
      print_bins(detail.spectral_shadow_phase_mask_frames[1U]);
      std::printf("\t");
      print_bins(detail.spectral_shadow_disposition_frames);
      std::printf("\t%u\t%u\t%u\t%u\t%u\t%u",
                  detail.spectral_shadow_fine_disagreement_frames,
                  detail.spectral_shadow_beat_compared_frames,
                  detail.spectral_shadow_beat_disagreement_frames,
                  detail.spectral_shadow_profile_disagreement_frames,
                  detail.spectral_shadow_temporal_disagreement_frames,
                  detail.spectral_shadow_assignment_disagreement_frames);
      std::printf("\t%u\t%u\t", detail.spectral_single_frames,
                  detail.spectral_single_invalid_frames);
      print_bins(detail.spectral_single_fitted_mask_frames);
      std::printf("\t");
      bool first_single_error = true;
      for (std::size_t mask = 0U;
           mask < detail.spectral_single_fitted_mask_frames.size(); ++mask) {
        const std::uint32_t frames =
            detail.spectral_single_fitted_mask_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%.9g", first_single_error ? "" : ",", mask,
                    detail.spectral_single_fitted_mask_error_sum[mask] /
                        static_cast<double>(frames));
        first_single_error = false;
      }
      std::printf("\t");
      bool first_single_margin = true;
      for (std::size_t mask = 0U;
           mask < detail.spectral_single_fitted_mask_margin_frames.size();
           ++mask) {
        const std::uint32_t frames =
            detail.spectral_single_fitted_mask_margin_frames[mask];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%.9g", first_single_margin ? "" : ",", mask,
                    detail.spectral_single_fitted_mask_margin_sum[mask] /
                        static_cast<double>(frames));
        first_single_margin = false;
      }
      std::printf("\t");
      print_bins(detail.spectral_single_disposition_frames);
      std::printf("\t");
      print_bins(detail.spectral_single_onset_string_frames);
      std::printf("\t");
      print_bins(detail.spectral_single_settled_string_frames);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralSingleGapThresholds);
      for (std::size_t phase = 0U; phase < 2U; ++phase) {
        std::printf("\t");
        bool first_score_error = true;
        for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
          const std::uint32_t frames =
              detail.spectral_single_phase_score_frames[phase][string];
          if (frames == 0U) {
            continue;
          }
          std::printf(
              "%s%zu:%.9g", first_score_error ? "" : ",", string,
              detail.spectral_single_phase_score_error_sum[phase][string] /
                  static_cast<double>(frames));
          first_score_error = false;
        }
      }
      std::printf("\t");
      print_joint_bins(
          detail.spectral_single_phase_gap_support_frames[0U]);
      std::printf("\t");
      print_joint_bins(
          detail.spectral_single_phase_gap_support_frames[1U]);
      std::printf("\t");
      print_bins(detail.spectral_single_error_outcome_frames[0U]);
      std::printf("\t");
      print_bins(detail.spectral_single_error_outcome_frames[1U]);
      std::printf("\t");
      print_bins(detail.spectral_single_margin_outcome_frames[0U]);
      std::printf("\t");
      print_bins(detail.spectral_single_margin_outcome_frames[1U]);
      std::printf("\t");
      print_bins(detail.spectral_single_group_error_outcome_frames[0U]);
      std::printf("\t");
      print_bins(detail.spectral_single_group_error_outcome_frames[1U]);
      std::printf("\t");
      print_bins(detail.spectral_single_group_margin_outcome_frames[0U]);
      std::printf("\t");
      print_bins(detail.spectral_single_group_margin_outcome_frames[1U]);
      std::printf("\t");
      print_bins(
          detail.spectral_single_below_threshold_error_outcome_frames[0U]);
      std::printf("\t");
      print_bins(
          detail.spectral_single_below_threshold_error_outcome_frames[1U]);
      std::printf("\t");
      print_bins(
          detail.spectral_single_below_threshold_margin_outcome_frames[0U]);
      std::printf("\t");
      print_bins(
          detail.spectral_single_below_threshold_margin_outcome_frames[1U]);
      std::printf("\t");
      print_joint_bins(
          detail.spectral_single_selection_disposition_frames);
      std::printf("\t");
      print_joint_bins(
          detail.spectral_single_group_selection_disposition_frames);
      std::printf("\t%u\t", detail.spectral_shadow_projected_frames);
      print_sequence(m3::offline::kSpectralShadowMarginThresholds);
      std::printf("\t");
      print_sequence(detail.spectral_shadow_projected_changed_frames);
      std::printf("\t");
      print_sequence(detail.spectral_shadow_projected_exact_frames);
      std::printf("\t");
      print_sequence(detail.spectral_shadow_projected_matched_frames);
      std::printf("\t");
      print_sequence(detail.spectral_shadow_projected_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_committed_mask);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_qualified_votes);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_winner_votes);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_projected_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_changed_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_exact_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_matched_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_latch_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.spectral_onset_contraction_changed_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_contraction_exact_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_contraction_matched_frames);
      std::printf("\t");
      print_sequence(detail.spectral_onset_contraction_matched_delta);
      std::printf("\t");
      print_sequence(detail.spectral_onset_contraction_wrong_string_delta);
      std::printf("\t");
      print_sequence(
          detail.spectral_onset_contraction_changed_onset_strength_max);
      for (const auto& head :
           detail.string_fret_spectral_head_best_frames) {
        std::printf("\t");
        bool first = true;
        for (std::size_t string = 0U; string < head.size(); ++string) {
          if (head[string] == 0U) {
            continue;
          }
          std::printf("%s%zu:%u", first ? "" : ",", string,
                      head[string]);
          first = false;
        }
      }
      std::printf("\t");
      print_bins(detail.spectral_head_vote_mask_frames);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralShadowMarginThresholds);
      std::printf("\t");
      print_joint_bins(detail.spectral_head_plurality_best_frames);
      std::printf("\t");
      print_bins(detail.spectral_tier_production_proposal_mask_frames);
      std::printf("\t");
      print_joint_bins(
          detail.spectral_tier_production_relation_lane_outcome_frames);
      std::printf("\t");
      print_joint_bins(detail.selector_group_relation_lane_outcome_frames);
      std::printf("\t");
      print_joint_bins(
          detail.tier_completion_disposition_lane_outcome_frames);
      std::printf("\t%u\t",
                  detail.spectral_tier_completion_projected_frames);
      print_bins(detail.spectral_tier_completion_candidate_mask_frames);
      std::printf("\t");
      print_bins(
          detail.spectral_tier_completion_added_member_beat_coherence_bins);
      std::printf("\t");
      print_bins(detail.spectral_tier_completion_added_member_ratio_bins);
      std::printf("\t");
      print_sequence(m3::offline::kSelectedSubsetCompletionSupportFloors);
      std::printf("\t");
      print_sequence(detail.selected_subset_consensus_projected_frames);
      std::printf("\t");
      print_sequence(detail.selected_subset_consensus_changed_frames);
      std::printf("\t");
      print_sequence(detail.selected_subset_consensus_exact_frames);
      std::printf("\t");
      print_sequence(detail.selected_subset_consensus_matched_delta);
      std::printf("\t");
      print_sequence(detail.selected_subset_consensus_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(detail.selected_subset_evidence_outcome_frames);
      std::printf("\t");
      print_sequence(detail.classifier_subset_projection_frames);
      std::printf("\t");
      print_sequence(detail.classifier_subset_changed_frames);
      std::printf("\t");
      print_sequence(detail.classifier_subset_exact_frames);
      std::printf("\t");
      print_sequence(detail.classifier_subset_matched_delta);
      std::printf("\t");
      print_sequence(detail.classifier_subset_wrong_string_delta);
      std::printf("\t");
      print_joint_bins(detail.classifier_subset_disposition_frames);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralShadowMarginThresholds);
      std::printf("\t");
      print_sequence(detail.spectral_tier_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.spectral_tier_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.spectral_tier_completion_matched_frames);
      std::printf("\t");
      print_sequence(
          detail.spectral_tier_completion_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.combined_spectral_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.combined_spectral_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.combined_spectral_completion_matched_frames);
      std::printf("\t");
      print_sequence(
          detail.combined_spectral_completion_wrong_string_voices);
      std::printf("\t");
      print_sequence(detail.combined_spectral_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.combined_spectral_completion_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.temporal_combined_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.temporal_combined_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.temporal_combined_completion_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.temporal_combined_completion_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.tier_priority_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.tier_priority_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.tier_priority_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.tier_priority_completion_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.cached_group_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.cached_group_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.cached_group_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.cached_group_completion_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.cached_classifier_continuity_changed_frames);
      std::printf("\t");
      print_sequence(detail.cached_classifier_continuity_exact_frames);
      std::printf("\t");
      print_sequence(detail.cached_classifier_continuity_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.cached_classifier_continuity_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.continuity_classifier_union_changed_frames);
      std::printf("\t");
      print_sequence(detail.continuity_classifier_union_exact_frames);
      std::printf("\t");
      print_sequence(detail.continuity_classifier_union_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.continuity_classifier_union_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.production_cache_continuity_changed_frames);
      std::printf("\t");
      print_sequence(detail.production_cache_continuity_exact_frames);
      std::printf("\t");
      print_sequence(detail.production_cache_continuity_matched_delta);
      std::printf("\t");
      print_sequence(
          detail.production_cache_continuity_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.committed_cache_continuity_changed_frames);
      std::printf("\t");
      print_sequence(detail.committed_cache_continuity_exact_frames);
      std::printf("\t");
      print_sequence(detail.committed_cache_continuity_matched_delta);
      std::printf("\t");
      print_sequence(detail.committed_cache_continuity_wrong_string_delta);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralTierAddedMemberRatioFloors);
      std::printf("\t");
      print_sequence(detail.tier_ratio_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.tier_ratio_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.tier_ratio_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.tier_ratio_completion_wrong_string_delta);
      std::printf("\t%u\t%u\t%lld\t%lld",
                  detail.safe_joint_completion_changed_frames,
                  detail.safe_joint_completion_exact_frames,
                  static_cast<long long>(
                      detail.safe_joint_completion_matched_delta),
                  static_cast<long long>(
                      detail.safe_joint_completion_wrong_string_delta));
      std::printf("\t%u\t%u\t%lld\t%lld",
                  detail.bounded_tier_completion_changed_frames,
                  detail.bounded_tier_completion_exact_frames,
                  static_cast<long long>(
                      detail.bounded_tier_completion_matched_delta),
                  static_cast<long long>(
                      detail.bounded_tier_completion_wrong_string_delta));
      std::printf("\t%u\t%u\t%lld\t%lld",
                  detail.bounded_joint_completion_changed_frames,
                  detail.bounded_joint_completion_exact_frames,
                  static_cast<long long>(
                      detail.bounded_joint_completion_matched_delta),
                  static_cast<long long>(
                      detail.bounded_joint_completion_wrong_string_delta));
      std::printf("\t%u\t%u\t%lld\t%lld",
                  detail.fine_exact_completion_changed_frames,
                  detail.fine_exact_completion_exact_frames,
                  static_cast<long long>(
                      detail.fine_exact_completion_matched_delta),
                  static_cast<long long>(
                      detail.fine_exact_completion_wrong_string_delta));
      std::printf("\t");
      print_sequence(detail.tier_ratio08_changed_by_phase);
      std::printf("\t");
      print_sequence(detail.tier_ratio08_matched_delta_by_phase);
      std::printf("\t");
      print_sequence(detail.tier_ratio08_wrong_delta_by_phase);
      std::printf("\t");
      print_sequence(m3::offline::kSpectralTierBeatMaximums);
      std::printf("\t");
      print_sequence(detail.tier_beat_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.tier_beat_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.tier_beat_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.tier_beat_completion_wrong_string_delta);
      std::printf("\t");
      print_sequence(detail.tier_classifier_completion_changed_frames);
      std::printf("\t");
      print_sequence(detail.tier_classifier_completion_exact_frames);
      std::printf("\t");
      print_sequence(detail.tier_classifier_completion_matched_delta);
      std::printf("\t");
      print_sequence(detail.tier_classifier_completion_wrong_string_delta);
      for (std::size_t head = 0U;
           head < detail.spectral_head_correct_margin_frames.size(); ++head) {
        std::printf("\t");
        print_bins(detail.spectral_head_correct_margin_frames[head]);
        std::printf("\t");
        print_bins(detail.spectral_head_other_margin_frames[head]);
      }
      std::printf("\t");
      bool first_unresolved_reason = true;
      for (std::size_t reason = 0U;
           reason < detail.fine_frequency_unresolved_reason_frames.size();
           ++reason) {
        const std::uint32_t frames =
            detail.fine_frequency_unresolved_reason_frames[reason];
        if (frames == 0U) {
          continue;
        }
        std::printf("%s%zu:%u", first_unresolved_reason ? "" : ",", reason,
                    frames);
        first_unresolved_reason = false;
      }
      for (const std::uint32_t frames :
           detail.fine_frequency_disposition_frames) {
        std::printf("\t%u", frames);
      }
#endif
      std::printf("\n");
    }
  }
  return 0;
}
