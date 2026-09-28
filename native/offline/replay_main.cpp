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
      "[--a4 HZ] [--block FRAMES] [--label-details] "
      "[--derive-calibration-string INDEX --calibration-output FILE]\n",
      program);
}

}  // namespace

int main(int argc, char** argv) {
  const char* wave_path = nullptr;
  const char* label_path = nullptr;
  const char* calibration_path = nullptr;
  const char* calibration_output_path = nullptr;
  int calibration_string = -1;
  std::size_t block_size = 512U;
  double a4_hz = 440.0;
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
  config.input_trim_db = -11.6;
  config.sensitivity = 70U;
  config.response = 81U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  if (calibration_path != nullptr) {
    std::vector<std::uint8_t> calibration_bytes;
    bool decoded = read_file(calibration_path, calibration_bytes);
    if (decoded && calibration_bytes.size() == m3::kCalibrationStateSize) {
      decoded = m3::decode_calibration_state(
          calibration_bytes.data(), calibration_bytes.size(), calibration);
    } else if (decoded &&
               calibration_bytes.size() ==
                   m3::kStateSize + m3::kCalibrationStateSize) {
      m3::PersistentConfig saved_config;
      decoded = m3::decode_state(calibration_bytes.data(), m3::kStateSize,
                                 saved_config) &&
                m3::decode_calibration_state(
                    calibration_bytes.data() + m3::kStateSize,
                    m3::kCalibrationStateSize, calibration);
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
  if (calibration_string >= 0) {
    if (calibration_output_path == nullptr || labels.empty()) {
      usage(argv[0]);
      return 2;
    }
    if (!m3::offline::derive_labeled_string_calibration(
            wave, labels, config,
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
  } else if (calibration_output_path != nullptr) {
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
  std::printf(
      "sample_rate\tblock\tsamples\tsnapshots\tlabeled\tmatched\t"
      "transitions\tfalse_positive_voices\tfingerprint\n"
      "%u\t%zu\t%llu\t%u\t%u\t%u\t%u\t%u\t%016llx\n",
      wave.sample_rate, block_size,
      static_cast<unsigned long long>(result.sample_count),
      result.snapshot_frames, result.labeled_frames,
      result.matched_label_frames, result.transition_count,
      result.false_positive_voices,
      static_cast<unsigned long long>(result.fingerprint));
  if (label_details) {
    std::printf(
        "label_index\tstart_sample\tend_sample\tmidi_note\tstring_mask\t"
        "labeled\tmatched\tmatch_percent\t"
        "max_beat_hz\t"
        "lane_0\tlane_1\tlane_2\tlane_3\tlane_4\tlane_5\tlane_6\t"
        "lane_7\tobserved_note_lane_masks\n");
    for (std::size_t index = 0U; index < labels.size(); ++index) {
      const m3::offline::ReplayLabel& label = labels[index];
      const m3::offline::ReplayLabelResult& detail =
          result.label_results[index];
      const double percent =
          detail.labeled_frames == 0U
              ? 0.0
              : 100.0 * static_cast<double>(detail.matched_frames) /
                    static_cast<double>(detail.labeled_frames);
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
      std::printf("\n");
    }
  }
  return 0;
}
