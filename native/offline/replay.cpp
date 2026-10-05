#include "replay.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstring>
#include <limits>
#include <string_view>
#include <type_traits>

#include "m3/constants.hpp"
#include "m3/pitch_math.hpp"
#include "m3/polyphonic_pitch_detector.hpp"

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
                                 : observed_mask == label.string_mask;
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
  double profile_total = 0.0;
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
    profile_total += output.profile[harmonic];
    partial_peak_total += partial_peak_energy[harmonic];
  }
  if (!std::isfinite(profile_total) || profile_total <= 0.0) {
    return false;
  }
  for (std::size_t harmonic = 0U; harmonic < output.profile.size();
       ++harmonic) {
    output.profile[harmonic] /= profile_total;
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
                         ReplayResult& output, ReplayError& error) {
  output = {};
  error = ReplayError::invalid_config;
  if (wave.sample_rate == 0U || wave.source_channels == 0U ||
      input_partition == 0U || input_partition > kMaximumInputPartition) {
    return false;
  }
  for (const ReplayLabel& label : labels) {
    if (label.start_sample >= label.end_sample ||
        label.end_sample > wave.mono_samples.size()) {
      return false;
    }
  }
  PolyphonicPitchDetector detector;
  if (!detector.configure(static_cast<double>(wave.sample_rate), config)) {
    return false;
  }
  if (calibration != nullptr) {
    detector.set_calibration_bank(*calibration);
  }
  ReplayResult result;
  result.fingerprint = kFnvOffset;
  result.sample_count = wave.mono_samples.size();
  result.label_results.resize(labels.size());
  struct LabelTrackingState final {
    std::uint8_t previous_nonzero_lane_mask{};
    std::uint32_t current_correct_run_frames{};
  };
  std::vector<LabelTrackingState> label_tracking(labels.size());
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

      for (std::size_t label_index = 0U; label_index < labels.size();
           ++label_index) {
        const ReplayLabel& label = labels[label_index];
        if (sample_index < label.start_sample ||
            sample_index >= label.end_sample) {
          continue;
        }
        ++result.labeled_frames;
        ReplayLabelResult& label_result = result.label_results[label_index];
        ++label_result.labeled_frames;
        const bool matched = snapshot_matches_label(snapshot, label);
        result.matched_label_frames += matched ? 1U : 0U;
        label_result.matched_frames += matched ? 1U : 0U;
        LabelTrackingState& tracking = label_tracking[label_index];
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
        const std::uint8_t observed_lane_mask =
            matching_note_lane_mask(snapshot, label.midi_note);
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
        bool expected = false;
        for (const ReplayLabel& label : labels) {
          if (sample_index >= label.start_sample &&
              sample_index < label.end_sample &&
              voice_matches_label(snapshot.voices[voice_index], label)) {
            expected = true;
            break;
          }
        }
        if (expected) {
          continue;
        }
        ++result.false_positive_voices;
        bool active_label = false;
        bool active_matching_note = false;
        for (const ReplayLabel& label : labels) {
          if (sample_index < label.start_sample ||
              sample_index >= label.end_sample) {
            continue;
          }
          active_label = true;
          active_matching_note =
              active_matching_note ||
              snapshot.voices[voice_index].midi_note == label.midi_note;
        }
        if (!active_label) {
          ++result.false_gap_voices;
        } else if (active_matching_note) {
          ++result.false_wrong_string_voices;
        } else {
          ++result.false_wrong_note_voices;
        }
      }
    }
  }
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
