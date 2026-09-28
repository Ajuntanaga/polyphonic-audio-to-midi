#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "m3/pitch_math.hpp"
#include "replay.hpp"
#include "test_support.hpp"

namespace {

void append_u16(std::vector<std::uint8_t>& bytes,
                std::uint16_t value) {
  bytes.push_back(static_cast<std::uint8_t>(value));
  bytes.push_back(static_cast<std::uint8_t>(value >> 8U));
}

void append_u32(std::vector<std::uint8_t>& bytes,
                std::uint32_t value) {
  for (std::size_t index = 0U; index < 4U; ++index) {
    bytes.push_back(static_cast<std::uint8_t>(value >> (index * 8U)));
  }
}

void patch_u32(std::vector<std::uint8_t>& bytes, std::size_t offset,
               std::uint32_t value) {
  for (std::size_t index = 0U; index < 4U; ++index) {
    bytes[offset + index] =
        static_cast<std::uint8_t>(value >> (index * 8U));
  }
}

std::vector<std::uint8_t> pcm16_wave(
    std::uint32_t sample_rate, std::uint16_t channels,
    const std::vector<std::int16_t>& interleaved) {
  std::vector<std::uint8_t> bytes;
  bytes.insert(bytes.end(), {'R', 'I', 'F', 'F'});
  append_u32(bytes, 0U);
  bytes.insert(bytes.end(), {'W', 'A', 'V', 'E'});
  bytes.insert(bytes.end(), {'f', 'm', 't', ' '});
  append_u32(bytes, 16U);
  append_u16(bytes, 1U);
  append_u16(bytes, channels);
  append_u32(bytes, sample_rate);
  append_u32(bytes, sample_rate * channels * 2U);
  append_u16(bytes, static_cast<std::uint16_t>(channels * 2U));
  append_u16(bytes, 16U);
  bytes.insert(bytes.end(), {'d', 'a', 't', 'a'});
  append_u32(bytes,
             static_cast<std::uint32_t>(interleaved.size() * 2U));
  for (const std::int16_t sample : interleaved) {
    append_u16(bytes, static_cast<std::uint16_t>(sample));
  }
  patch_u32(bytes, 4U, static_cast<std::uint32_t>(bytes.size() - 8U));
  return bytes;
}

std::vector<std::uint8_t> float32_wave(
    std::uint32_t sample_rate, const std::vector<float>& samples) {
  std::vector<std::uint8_t> bytes;
  bytes.insert(bytes.end(), {'R', 'I', 'F', 'F'});
  append_u32(bytes, 0U);
  bytes.insert(bytes.end(), {'W', 'A', 'V', 'E'});
  bytes.insert(bytes.end(), {'f', 'm', 't', ' '});
  append_u32(bytes, 16U);
  append_u16(bytes, 3U);
  append_u16(bytes, 1U);
  append_u32(bytes, sample_rate);
  append_u32(bytes, sample_rate * 4U);
  append_u16(bytes, 4U);
  append_u16(bytes, 32U);
  bytes.insert(bytes.end(), {'d', 'a', 't', 'a'});
  append_u32(bytes, static_cast<std::uint32_t>(samples.size() * 4U));
  for (const float sample : samples) {
    std::uint32_t bits = 0U;
    std::memcpy(&bits, &sample, sizeof(bits));
    append_u32(bytes, bits);
  }
  patch_u32(bytes, 4U, static_cast<std::uint32_t>(bytes.size() - 8U));
  return bytes;
}

M3_TEST(offline_replay_decodes_pcm16_stereo_and_float32_mono) {
  const std::vector<std::uint8_t> pcm =
      pcm16_wave(48000U, 2U, {32767, -32768, 16384, 16384});
  m3::offline::WaveData wave;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::decode_wave_bytes(
      pcm.data(), pcm.size(), wave, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  M3_EXPECT_EQ(wave.sample_rate, 48000U);
  M3_EXPECT_EQ(wave.source_channels, 2U);
  M3_EXPECT_EQ(wave.mono_samples.size(), 2U);
  M3_EXPECT_NEAR(wave.mono_samples[0], -1.0 / 65536.0, 1.0e-9);
  M3_EXPECT_NEAR(wave.mono_samples[1], 0.5, 1.0e-9);

  const std::vector<std::uint8_t> floating =
      float32_wave(96000U, {-0.25F, 0.5F});
  M3_EXPECT_TRUE(m3::offline::decode_wave_bytes(
      floating.data(), floating.size(), wave, error));
  M3_EXPECT_EQ(wave.sample_rate, 96000U);
  M3_EXPECT_EQ(wave.source_channels, 1U);
  M3_EXPECT_NEAR(wave.mono_samples[0], -0.25, 1.0e-12);
  M3_EXPECT_NEAR(wave.mono_samples[1], 0.5, 1.0e-12);
}

M3_TEST(offline_replay_rejects_malformed_wave_and_label_rows) {
  m3::offline::WaveData wave;
  m3::offline::ReplayError error{};
  constexpr std::array<std::uint8_t, 12U> bad_wave{
      'R', 'I', 'F', 'F', 4, 0, 0, 0, 'N', 'O', 'P', 'E'};
  M3_EXPECT_FALSE(m3::offline::decode_wave_bytes(
      bad_wave.data(), bad_wave.size(), wave, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_wave);

  std::vector<m3::offline::ReplayLabel> labels;
  const std::string bad_labels =
      "start_sample\tend_sample\tmidi_note\tstring_mask\n"
      "100\t90\t40\t1\n";
  M3_EXPECT_FALSE(m3::offline::parse_replay_labels(
      bad_labels.data(), bad_labels.size(), 1000U, labels, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_labels);
}

M3_TEST(offline_replay_parses_overlapping_exact_sample_labels) {
  const std::string text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\n"
      "0\t48000\t40\t1\n"
      "12000\t36000\t52\t16\n";
  std::vector<m3::offline::ReplayLabel> labels;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      text.data(), text.size(), 48000U, labels, error));
  M3_EXPECT_EQ(labels.size(), 2U);
  M3_EXPECT_EQ(labels[0].start_sample, 0U);
  M3_EXPECT_EQ(labels[0].end_sample, 48000U);
  M3_EXPECT_EQ(labels[0].midi_note, 40U);
  M3_EXPECT_EQ(labels[0].string_mask, 1U);
  M3_EXPECT_EQ(labels[1].string_mask, 16U);
}

M3_TEST(offline_replay_parses_explicit_calibration_passes) {
  const std::string text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\n"
      "0\t12000\t40\t1\t1\n"
      "12000\t24000\t40\t1\t3\n";
  std::vector<m3::offline::ReplayLabel> labels;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      text.data(), text.size(), 24000U, labels, error));
  M3_EXPECT_EQ(labels.size(), 2U);
  M3_EXPECT_EQ(labels[0].calibration_pass, 1U);
  M3_EXPECT_EQ(labels[1].calibration_pass, 3U);
}

M3_TEST(offline_replay_result_is_invariant_across_input_partitions) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint32_t kToneSamples = kSampleRate;
  constexpr std::uint32_t kReleaseSamples = kSampleRate / 2U;
  constexpr std::uint8_t kNote = 40U;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);
  std::vector<std::int16_t> samples(kToneSamples + kReleaseSamples);
  for (std::uint32_t index = 0U; index < kToneSamples; ++index) {
    const double phase = 6.28318530717958647692 * frequency *
                         static_cast<double>(index) /
                         static_cast<double>(kSampleRate);
    samples[index] = static_cast<std::int16_t>(
        std::lround(0.30 * 32767.0 * std::sin(phase)));
  }
  const std::vector<std::uint8_t> bytes =
      pcm16_wave(kSampleRate, 1U, samples);
  m3::offline::WaveData wave;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::decode_wave_bytes(
      bytes.data(), bytes.size(), wave, error));
  const std::string label_text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\n"
      "0\t48000\t40\t0\n";
  std::vector<m3::offline::ReplayLabel> labels;
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      label_text.data(), label_text.size(), wave.mono_samples.size(), labels,
      error));

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 39U;
  config.highest_note = 41U;
  config.max_polyphony = 1U;
  config.sensitivity = 70U;
  config.response = 81U;
  constexpr std::array<std::size_t, 6U> kPartitions{
      1U, 17U, 64U, 128U, 511U, 4096U};
  m3::offline::ReplayResult baseline;
  bool have_baseline = false;
  for (const std::size_t partition : kPartitions) {
    m3::offline::ReplayResult result;
    M3_EXPECT_TRUE(m3::offline::run_detector_replay(
        wave, labels, config, nullptr, partition, result, error));
    M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
    M3_EXPECT_TRUE(result.snapshot_frames > 0U);
    M3_EXPECT_TRUE(result.matched_label_frames > 0U);
    M3_EXPECT_EQ(result.label_results.size(), 1U);
    if (result.label_results.size() == 1U) {
      M3_EXPECT_EQ(result.label_results[0].labeled_frames,
                   result.labeled_frames);
      M3_EXPECT_EQ(result.label_results[0].matched_frames,
                   result.matched_label_frames);
      std::uint32_t mask_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].matching_note_lane_mask_frames) {
        mask_frames += frames;
      }
      M3_EXPECT_EQ(mask_frames, result.label_results[0].labeled_frames);
    }
    M3_EXPECT_EQ(result.transition_count, 2U);
    if (!have_baseline) {
      baseline = result;
      have_baseline = true;
    } else {
      M3_EXPECT_EQ(result.fingerprint, baseline.fingerprint);
      M3_EXPECT_EQ(result.snapshot_frames, baseline.snapshot_frames);
      M3_EXPECT_EQ(result.labeled_frames, baseline.labeled_frames);
      M3_EXPECT_EQ(result.matched_label_frames,
                   baseline.matched_label_frames);
      M3_EXPECT_EQ(result.transition_count, baseline.transition_count);
      M3_EXPECT_EQ(result.false_positive_voices,
                   baseline.false_positive_voices);
      M3_EXPECT_EQ(result.label_results.size(),
                   baseline.label_results.size());
      if (result.label_results.size() == baseline.label_results.size()) {
        for (std::size_t label = 0U; label < result.label_results.size();
             ++label) {
          M3_EXPECT_EQ(result.label_results[label].labeled_frames,
                       baseline.label_results[label].labeled_frames);
          M3_EXPECT_EQ(result.label_results[label].matched_frames,
                       baseline.label_results[label].matched_frames);
      M3_EXPECT_EQ(
          result.label_results[label].matching_note_lane_frames,
          baseline.label_results[label].matching_note_lane_frames);
      M3_EXPECT_EQ(
          result.label_results[label].maximum_matching_note_beat_hz_q8,
          baseline.label_results[label].maximum_matching_note_beat_hz_q8);
      M3_EXPECT_EQ(
              result.label_results[label].matching_note_lane_mask_frames,
              baseline.label_results[label].matching_note_lane_mask_frames);
        }
      }
    }
  }
}

M3_TEST(offline_labeled_calibration_learns_each_discrete_fret_and_intonation) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint32_t kSamplesPerNote = 12000U;
  constexpr double kTwoPi = 6.28318530717958647692;
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  std::vector<m3::offline::ReplayLabel> labels;
  double phase = 0.0;
  const auto append_fret = [&](std::size_t fret, double cents) {
    const std::uint64_t start = wave.mono_samples.size();
    const double pitch = static_cast<double>(m3::kM3OpenNotes[0U]) +
                         static_cast<double>(fret) + cents / 100.0;
    const double frequency = m3::midi_to_frequency(pitch, 440.0);
    for (std::uint32_t sample = 0U; sample < kSamplesPerNote; ++sample) {
      const double value = 0.24 * std::sin(phase) +
                           0.08 * std::sin(2.0 * phase + 0.17) +
                           0.035 * std::sin(3.0 * phase - 0.31);
      wave.mono_samples.push_back(value);
      phase = std::fmod(phase + kTwoPi * frequency / kSampleRate, kTwoPi);
    }
    labels.push_back(m3::offline::ReplayLabel{
        start, wave.mono_samples.size(),
        static_cast<std::uint8_t>(m3::kM3OpenNotes[0U] + fret), 1U});
  };
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    append_fret(fret, 45.0 * static_cast<double>(fret) / 24.0);
  }
  for (std::size_t fret = m3::kCalibrationFretCount; fret-- > 0U;) {
    append_fret(fret, 1.0 + 44.0 * static_cast<double>(fret) / 24.0);
  }

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.a4_hz = 440.0;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  m3::StringCalibrationBank bank;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::derive_labeled_string_calibration(
      wave, labels, config, 0U, bank, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  M3_EXPECT_TRUE(bank.string_calibrated(0U));
  const auto* open = bank.point(0U, 0U);
  const auto* highest = bank.point(0U, 24U);
  M3_EXPECT_TRUE(open != nullptr);
  M3_EXPECT_TRUE(highest != nullptr);
  if (open != nullptr && highest != nullptr) {
    M3_EXPECT_EQ(open->quality, m3::CalibrationPointQuality::measured);
    M3_EXPECT_EQ(highest->quality, m3::CalibrationPointQuality::measured);
    M3_EXPECT_NEAR(static_cast<double>(open->cents_offset_q8) / 256.0,
                   0.5, 1.0);
    M3_EXPECT_NEAR(static_cast<double>(highest->cents_offset_q8) / 256.0,
                   45.0, 1.0);
    M3_EXPECT_EQ(highest->observation_count, 2U);
    M3_EXPECT_TRUE(highest->harmonic_profile_q15[0] >
                   highest->harmonic_profile_q15[1]);
  }
}

M3_TEST(offline_labeled_calibration_resolves_thinnest_string_high_frets_at_96k) {
  constexpr std::uint32_t kSampleRate = 96000U;
  constexpr std::uint32_t kSamplesPerNote = 24000U;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr double kCents = 29.0;
  constexpr std::size_t kString = 7U;
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  std::vector<m3::offline::ReplayLabel> labels;
  double phase = 0.0;
  const auto append_fret = [&](std::size_t fret) {
    const std::uint64_t start = wave.mono_samples.size();
    const double pitch = static_cast<double>(m3::kM3OpenNotes[kString]) +
                         static_cast<double>(fret) + kCents / 100.0;
    const double frequency = m3::midi_to_frequency(pitch, 440.0);
    for (std::uint32_t sample = 0U; sample < kSamplesPerNote; ++sample) {
      wave.mono_samples.push_back(
          0.22 * std::sin(phase) +
          0.06 * std::sin(2.0 * phase + 0.19) +
          0.02 * std::sin(3.0 * phase - 0.37));
      phase = std::fmod(phase + kTwoPi * frequency / kSampleRate, kTwoPi);
    }
    labels.push_back(m3::offline::ReplayLabel{
        start, wave.mono_samples.size(),
        static_cast<std::uint8_t>(m3::kM3OpenNotes[kString] + fret),
        static_cast<std::uint8_t>(1U << kString)});
  };
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    append_fret(fret);
  }
  for (std::size_t fret = m3::kCalibrationFretCount; fret-- > 0U;) {
    append_fret(fret);
  }

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.a4_hz = 440.0;
  config.lowest_note = 60U;
  config.highest_note = 84U;
  m3::StringCalibrationBank bank;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::derive_labeled_string_calibration(
      wave, labels, config, static_cast<std::uint8_t>(kString), bank,
      error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  M3_EXPECT_TRUE(bank.string_calibrated(kString));
  const auto* highest = bank.point(kString, 24U);
  M3_EXPECT_TRUE(highest != nullptr);
  if (highest != nullptr) {
    M3_EXPECT_NEAR(static_cast<double>(highest->cents_offset_q8) / 256.0,
                   kCents, 1.0);
  }
}

M3_TEST(offline_labeled_calibration_retains_repeatable_pitch_across_pluck_timbres) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint32_t kSamplesPerNote = 12000U;
  constexpr double kTwoPi = 6.28318530717958647692;
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  std::vector<m3::offline::ReplayLabel> labels;
  double phase = 0.0;
  const auto append_fret = [&](std::size_t fret, bool bright_pluck) {
    const std::uint64_t start = wave.mono_samples.size();
    const double pitch = static_cast<double>(m3::kM3OpenNotes[1U]) +
                         static_cast<double>(fret) - 22.0 / 100.0;
    const double frequency = m3::midi_to_frequency(pitch, 440.0);
    for (std::uint32_t sample = 0U; sample < kSamplesPerNote; ++sample) {
      const double fundamental = bright_pluck ? 0.03 : 0.24;
      const double second = bright_pluck ? 0.25 : 0.015;
      wave.mono_samples.push_back(
          fundamental * std::sin(phase) +
          second * std::sin(2.0 * phase + 0.31));
      phase = std::fmod(phase + kTwoPi * frequency / kSampleRate, kTwoPi);
    }
    labels.push_back(m3::offline::ReplayLabel{
        start, wave.mono_samples.size(),
        static_cast<std::uint8_t>(m3::kM3OpenNotes[1U] + fret), 2U});
  };
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    append_fret(fret, false);
  }
  for (std::size_t fret = m3::kCalibrationFretCount; fret-- > 0U;) {
    append_fret(fret, true);
  }

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.a4_hz = 440.0;
  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][0U].quality = m3::CalibrationPointQuality::measured;
  bank.points[0U][0U].cents_offset_q8 = 123;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::derive_labeled_string_calibration(
      wave, labels, config, 1U, bank, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  M3_EXPECT_TRUE(bank.string_calibrated(0U));
  M3_EXPECT_TRUE(bank.string_calibrated(1U));
  M3_EXPECT_EQ(bank.points[0U][0U].cents_offset_q8, 123);
  const auto* point = bank.point(1U, 12U);
  M3_EXPECT_TRUE(point != nullptr);
  if (point != nullptr) {
    M3_EXPECT_NEAR(static_cast<double>(point->cents_offset_q8) / 256.0,
                   -22.0, 1.0);
    M3_EXPECT_EQ(point->observation_count, 2U);
    M3_EXPECT_TRUE(point->confidence_q15 > 0U);
  }
}

M3_TEST(offline_labeled_calibration_balances_passes_and_rejects_one_outlier) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint32_t kSamplesPerNote = 12000U;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::size_t kBalancedFret = 12U;
  constexpr std::size_t kOutlierFret = 13U;
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  std::vector<m3::offline::ReplayLabel> labels;
  double phase = 0.0;
  const auto append_fret = [&](std::size_t fret, double cents,
                               std::uint8_t pass) {
    const std::uint64_t start = wave.mono_samples.size();
    const double pitch = static_cast<double>(m3::kM3OpenNotes[0U]) +
                         static_cast<double>(fret) + cents / 100.0;
    const double frequency = m3::midi_to_frequency(pitch, 440.0);
    for (std::uint32_t sample = 0U; sample < kSamplesPerNote; ++sample) {
      wave.mono_samples.push_back(
          0.22 * std::sin(phase) +
          0.06 * std::sin(2.0 * phase + 0.19) +
          0.02 * std::sin(3.0 * phase - 0.37));
      phase = std::fmod(phase + kTwoPi * frequency / kSampleRate, kTwoPi);
    }
    labels.push_back(m3::offline::ReplayLabel{
        start, wave.mono_samples.size(),
        static_cast<std::uint8_t>(m3::kM3OpenNotes[0U] + fret), 1U, pass});
  };
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    append_fret(fret, -6.0, 1U);
  }
  for (std::size_t fret = m3::kCalibrationFretCount; fret-- > 0U;) {
    append_fret(fret, 6.0, 2U);
  }
  for (std::size_t repeat = 0U; repeat < 4U; ++repeat) {
    append_fret(kBalancedFret, 12.0, 3U);
  }
  for (std::size_t repeat = 0U; repeat < 3U; ++repeat) {
    append_fret(0U, 12.0, 3U);
  }
  append_fret(kOutlierFret, 40.0, 3U);
  const std::uint64_t silent_start = wave.mono_samples.size();
  wave.mono_samples.resize(wave.mono_samples.size() + kSamplesPerNote, 0.0);
  labels.push_back(m3::offline::ReplayLabel{
      silent_start, wave.mono_samples.size(),
      static_cast<std::uint8_t>(m3::kM3OpenNotes[0U] + kBalancedFret), 1U,
      4U});

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.a4_hz = 440.0;
  m3::StringCalibrationBank bank;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::derive_labeled_string_calibration(
      wave, labels, config, 0U, bank, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  const auto* balanced = bank.point(0U, kBalancedFret);
  const auto* outlier = bank.point(0U, kOutlierFret);
  const auto* open = bank.point(0U, 0U);
  M3_EXPECT_TRUE(balanced != nullptr);
  M3_EXPECT_TRUE(outlier != nullptr);
  M3_EXPECT_TRUE(open != nullptr);
  if (balanced != nullptr && outlier != nullptr && open != nullptr) {
    // Each recording pass has equal influence even if the isolated-note pass
    // contains several repeated holds of this fret.
    M3_EXPECT_NEAR(static_cast<double>(balanced->cents_offset_q8) / 256.0,
                   4.0, 1.0);
    M3_EXPECT_EQ(balanced->observation_count, 6U);
    // When one of three pass means lies outside the repeatable corridor, the
    // closest two passes define the physical pitch instead of invalidating
    // the complete 25-fret bank.
    M3_EXPECT_NEAR(static_cast<double>(outlier->cents_offset_q8) / 256.0,
                   0.0, 1.0);
    M3_EXPECT_EQ(outlier->observation_count, 2U);
    // Fret zero is the string's absolute anchor. Repeated later attacks may
    // validate it, but do not move the bidirectional walk's pitch center.
    M3_EXPECT_NEAR(static_cast<double>(open->cents_offset_q8) / 256.0,
                   0.0, 1.0);
    M3_EXPECT_EQ(open->observation_count, 2U);
  }

  std::vector<m3::offline::ReplayLabel> missing_ascending = labels;
  for (m3::offline::ReplayLabel& label : missing_ascending) {
    if (label.calibration_pass == 1U &&
        label.midi_note == m3::kM3OpenNotes[0U] + kBalancedFret) {
      label.calibration_pass = 2U;
    }
  }
  m3::StringCalibrationBank invalid_bank;
  M3_EXPECT_FALSE(m3::offline::derive_labeled_string_calibration(
      wave, missing_ascending, config, 0U, invalid_bank, error));
}

}  // namespace
