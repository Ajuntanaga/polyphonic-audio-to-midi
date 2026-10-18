#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <numeric>
#include <string>
#include <vector>

#include "m3/pitch_math.hpp"
#include "replay.hpp"
#include "test_support.hpp"
#include "unison_spectral_shadow.hpp"

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

M3_TEST(offline_replay_pairwise_beat_support_requires_a_connected_graph) {
  std::array<double, 1U << m3::kMaxVoices> coherence{};
  coherence[0b00000011U] = 0.31;
  coherence[0b00000101U] = 0.22;
  coherence[0b00000110U] = 0.10;

  const auto triple = m3::offline::summarize_pairwise_beat_support(
      0b00000111U, coherence, 0.20);
  M3_EXPECT_EQ(triple.pair_count, 3U);
  M3_EXPECT_EQ(triple.above_gate_count, 2U);
  M3_EXPECT_TRUE(triple.connected);

  coherence.fill(0.0);
  coherence[0b00000011U] = 0.30;
  coherence[0b00001100U] = 0.30;
  const auto split = m3::offline::summarize_pairwise_beat_support(
      0b00001111U, coherence, 0.20);
  M3_EXPECT_EQ(split.pair_count, 6U);
  M3_EXPECT_EQ(split.above_gate_count, 2U);
  M3_EXPECT_FALSE(split.connected);

  coherence[0b00000101U] = 0.20;
  const auto spanning = m3::offline::summarize_pairwise_beat_support(
      0b00001111U, coherence, 0.20);
  M3_EXPECT_EQ(spanning.above_gate_count, 3U);
  M3_EXPECT_TRUE(spanning.connected);
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

M3_TEST(offline_replay_parses_expected_cents_for_accuracy_scoring) {
  const std::string text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\t"
      "expected_cents\n"
      "0\t12000\t40\t1\t1\t-12.375\n"
      "12000\t24000\t41\t1\t3\t7.5\n";
  std::vector<m3::offline::ReplayLabel> labels;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      text.data(), text.size(), 24000U, labels, error));
  M3_EXPECT_EQ(labels.size(), 2U);
  M3_EXPECT_TRUE(labels[0].expected_cents_valid);
  M3_EXPECT_EQ(labels[0].expected_cents_q8, -3168);
  M3_EXPECT_TRUE(labels[1].expected_cents_valid);
  M3_EXPECT_EQ(labels[1].expected_cents_q8, 1920);

  const std::string out_of_range =
      "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\t"
      "expected_cents\n"
      "0\t12000\t40\t1\t1\t50.001\n";
  M3_EXPECT_FALSE(m3::offline::parse_replay_labels(
      out_of_range.data(), out_of_range.size(), 12000U, labels, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_labels);
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
      "start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\t"
      "expected_cents\n"
      "0\t48000\t40\t0\t1\t0.0\n";
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
      M3_EXPECT_TRUE(result.label_results[0].cents_observations > 0U);
      M3_EXPECT_TRUE(
          result.label_results[0].first_valid_cents_sample < kToneSamples);
      M3_EXPECT_TRUE(
          result.label_results[0].first_correct_string_sample < kToneSamples);
      M3_EXPECT_TRUE(result.label_results[0].longest_correct_run_frames > 0U);
      M3_EXPECT_EQ(result.label_results[0].string_flip_count, 0U);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      std::uint32_t disposition_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].selection_disposition_frames) {
        disposition_frames += frames;
      }
      M3_EXPECT_EQ(disposition_frames,
                   result.label_results[0].labeled_frames);
      std::uint32_t quiet_disposition_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].quiet_disposition_frames) {
        quiet_disposition_frames += frames;
      }
      M3_EXPECT_EQ(
          result.label_results[0].quiet_disposition_frames[0U],
          0U);
      M3_EXPECT_EQ(
          quiet_disposition_frames,
          result.label_results[0].selection_disposition_frames[0U]);
      for (std::size_t cause = 0U;
           cause < result.label_results[0].quiet_disposition_frames.size();
           ++cause) {
        const std::uint32_t frames =
            result.label_results[0].quiet_disposition_frames[cause];
        const std::uint32_t runs =
            result.label_results[0].quiet_disposition_runs[cause];
        const std::uint32_t longest =
            result.label_results[0].longest_quiet_disposition_run_frames[cause];
        M3_EXPECT_TRUE(runs <= frames);
        M3_EXPECT_TRUE(longest <= frames);
        M3_EXPECT_EQ(frames == 0U, runs == 0U);
        M3_EXPECT_EQ(frames == 0U, longest == 0U);
      }
      std::uint32_t candidate_score_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].candidate_score_threshold_ratio_frames) {
        candidate_score_frames += frames;
      }
      M3_EXPECT_EQ(candidate_score_frames,
                   result.label_results[0].labeled_frames);
      const std::uint32_t dp_evicted_frames =
          result.label_results[0].selection_disposition_frames[3U];
      std::uint32_t dp_true_pitch_count_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].candidate_dp_evicted_true_pitch_count_frames) {
        dp_true_pitch_count_frames += frames;
      }
      M3_EXPECT_EQ(dp_true_pitch_count_frames, dp_evicted_frames);
      std::uint32_t dp_selected_pitch_count_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_selected_pitch_count_frames) {
        dp_selected_pitch_count_frames += frames;
      }
      M3_EXPECT_EQ(dp_selected_pitch_count_frames, dp_evicted_frames);
      std::uint32_t dp_score_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_score_ratio_frames) {
        dp_score_frames += frames;
      }
      M3_EXPECT_EQ(dp_score_frames, dp_evicted_frames);
      std::uint32_t dp_evidence_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_evidence_flag_frames) {
        dp_evidence_frames += frames;
      }
      M3_EXPECT_EQ(dp_evidence_frames, dp_evicted_frames);
      std::uint32_t dp_playable_lane_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_playable_lane_count_frames) {
        dp_playable_lane_frames += frames;
      }
      M3_EXPECT_EQ(dp_playable_lane_frames, dp_evicted_frames);
      std::uint32_t dp_calibration_relation_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_calibration_relation_frames) {
        dp_calibration_relation_frames += frames;
      }
      M3_EXPECT_EQ(dp_calibration_relation_frames, dp_evicted_frames);
      std::uint32_t dp_posterior_relation_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_dp_evicted_posterior_relation_frames) {
        dp_posterior_relation_frames += frames;
      }
      M3_EXPECT_EQ(dp_posterior_relation_frames, dp_evicted_frames);
      std::uint32_t below_threshold_score_frames = 0U;
      for (const std::uint32_t frames : result.label_results[0]
                                                .candidate_below_threshold_score_ratio_frames) {
        below_threshold_score_frames += frames;
      }
      M3_EXPECT_EQ(
          below_threshold_score_frames,
          result.label_results[0].selection_disposition_frames[1U]);
      std::uint32_t direct_evidence_frames = 0U;
      for (const auto& score_bins : result.label_results[0]
                                        .candidate_below_threshold_direct_evidence_frames) {
        for (const std::uint32_t frames : score_bins) {
          direct_evidence_frames += frames;
        }
      }
      M3_EXPECT_TRUE(direct_evidence_frames <= below_threshold_score_frames);
      std::uint32_t pitch_band_frames = 0U;
      for (const auto& score_bins : result.label_results[0]
                                         .candidate_below_threshold_pitch_band_peak_frames) {
        for (const std::uint32_t frames : score_bins) {
          pitch_band_frames += frames;
        }
      }
      M3_EXPECT_EQ(pitch_band_frames, direct_evidence_frames);
      std::uint32_t spectral_rejected_fundamental_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_fundamental_ratio_frames) {
        spectral_rejected_fundamental_frames += frames;
      }
      M3_EXPECT_EQ(
          spectral_rejected_fundamental_frames,
          result.label_results[0].selection_disposition_frames[2U]);
      std::uint32_t spectral_shadow_interval_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_shadow_interval_frames) {
        spectral_shadow_interval_frames += frames;
      }
      M3_EXPECT_EQ(spectral_shadow_interval_frames,
                   spectral_rejected_fundamental_frames);
      std::uint32_t spectral_shadow_kind_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_shadow_kind_frames) {
        spectral_shadow_kind_frames += frames;
      }
      M3_EXPECT_EQ(spectral_shadow_kind_frames,
                   spectral_rejected_fundamental_frames);
      std::uint32_t spectral_shadow_context_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_shadow_other_eligible_frames) {
        spectral_shadow_context_frames += frames;
      }
      M3_EXPECT_EQ(spectral_shadow_context_frames,
                   spectral_rejected_fundamental_frames);
      std::uint32_t spectral_shadow_other_interval_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_shadow_strongest_other_interval_frames) {
        spectral_shadow_other_interval_frames += frames;
      }
      M3_EXPECT_EQ(spectral_shadow_other_interval_frames,
                   spectral_rejected_fundamental_frames);
      std::uint32_t spectral_shadow_other_evidence_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .candidate_spectral_rejected_shadow_strongest_other_evidence_frames) {
        spectral_shadow_other_evidence_frames += frames;
      }
      M3_EXPECT_EQ(spectral_shadow_other_evidence_frames,
                   spectral_rejected_fundamental_frames);
      std::uint32_t fine_mask_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].fine_frequency_member_mask_frames) {
        fine_mask_frames += frames;
      }
      M3_EXPECT_EQ(fine_mask_frames,
                   result.label_results[0].labeled_frames);
      std::uint32_t pending_mask_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .fine_frequency_pending_member_mask_frames) {
        pending_mask_frames += frames;
      }
      M3_EXPECT_EQ(pending_mask_frames,
                   result.label_results[0].labeled_frames);
      for (const auto& dispositions :
           result.label_results[0]
               .articulated_unison_reacquisition_disposition_frames) {
        std::uint32_t articulated_disposition_frames = 0U;
        for (const std::uint32_t frames : dispositions) {
          articulated_disposition_frames += frames;
        }
        M3_EXPECT_EQ(articulated_disposition_frames,
                     result.label_results[0].labeled_frames);
      }
      const auto& observed = result.label_results[0];
      const std::uint32_t expected_changed =
          observed.observed_fingerprint_reacquisition_changed_frames
              [m3::offline::kObservedFingerprintProductionCandidatePolicy];
      std::uint32_t committed_relation_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_committed_relation_frames) {
        committed_relation_frames += frames;
      }
      std::uint32_t snapshot_voice_count_frames = 0U;
      std::uint32_t committed_member_count_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_committed_member_count_frames) {
        committed_member_count_frames += frames;
      }
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_snapshot_voice_count_frames) {
        snapshot_voice_count_frames += frames;
      }
      std::uint32_t other_owned_lane_count_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_other_owned_lane_count_frames) {
        other_owned_lane_count_frames += frames;
      }
      std::uint32_t production_disposition_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_production_disposition_frames) {
        production_disposition_frames += frames;
      }
      std::uint32_t production_cache_age_frames = 0U;
      for (const std::uint32_t frames :
           observed
               .observed_fingerprint_changed_production_cache_age_50ms_frames) {
        production_cache_age_frames += frames;
      }
      std::uint32_t production_cache_mask_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_production_cache_mask_frames) {
        production_cache_mask_frames += frames;
      }
      std::uint32_t changed_score_ratio_frames = 0U;
      for (const std::uint32_t frames :
           observed
               .observed_fingerprint_changed_score_threshold_ratio_05_frames) {
        changed_score_ratio_frames += frames;
      }
      std::uint32_t changed_direct_fundamental_frames = 0U;
      for (const std::uint32_t frames :
           observed.observed_fingerprint_changed_direct_fundamental_frames) {
        changed_direct_fundamental_frames += frames;
      }
      M3_EXPECT_EQ(committed_relation_frames, expected_changed);
      M3_EXPECT_EQ(committed_member_count_frames, expected_changed);
      M3_EXPECT_EQ(snapshot_voice_count_frames, expected_changed);
      M3_EXPECT_EQ(other_owned_lane_count_frames, expected_changed);
      M3_EXPECT_EQ(production_disposition_frames, expected_changed);
      M3_EXPECT_EQ(production_cache_age_frames, expected_changed);
      M3_EXPECT_EQ(production_cache_mask_frames, expected_changed);
      M3_EXPECT_EQ(changed_score_ratio_frames, expected_changed);
      M3_EXPECT_EQ(changed_direct_fundamental_frames, expected_changed);
      std::uint32_t fit_mask_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].fine_frequency_fit_member_mask_frames) {
        fit_mask_frames += frames;
      }
      M3_EXPECT_EQ(fit_mask_frames, result.label_results[0].labeled_frames);
      std::uint32_t fine_disposition_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0].fine_frequency_disposition_frames) {
        fine_disposition_frames += frames;
      }
      M3_EXPECT_EQ(fine_disposition_frames,
                   result.label_results[0].labeled_frames);
      M3_EXPECT_TRUE(result.label_results[0].spectral_corridor_frames > 0U);
      M3_EXPECT_EQ(result.label_results[0].spectral_corridor_frames,
                   result.label_results[0].spectral_onset_frames +
                       result.label_results[0].spectral_settled_frames);
      double spectral_total = 0.0;
      for (const double feature :
           result.label_results[0].spectral_corridor_fingerprint_sum) {
        spectral_total += feature;
      }
      M3_EXPECT_TRUE(spectral_total > 0.0);
#endif
    }
    M3_EXPECT_EQ(result.transition_count, 2U);
    M3_EXPECT_EQ(result.transition_inside_hold_count +
                     result.transition_gap_count,
                 result.transition_count);
    M3_EXPECT_EQ(result.false_gap_voices + result.false_wrong_note_voices +
                     result.false_wrong_string_voices,
                 result.false_positive_voices);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
    M3_EXPECT_EQ(
        std::accumulate(
            result.false_wrong_note_interval_frames.begin(),
            result.false_wrong_note_interval_frames.end(), std::uint64_t{0}),
        result.false_wrong_note_voices);
    std::uint64_t age_interval_frames = 0U;
    for (const auto& age : result.false_wrong_note_age_interval_frames) {
      age_interval_frames = std::accumulate(age.begin(), age.end(),
                                            age_interval_frames);
    }
    M3_EXPECT_EQ(age_interval_frames, result.false_wrong_note_voices);
    std::uint64_t interval_cents_frames = 0U;
    for (const auto& interval :
         result.false_wrong_note_interval_cents_frames) {
      interval_cents_frames = std::accumulate(
          interval.begin(), interval.end(), interval_cents_frames);
    }
    M3_EXPECT_EQ(interval_cents_frames, result.false_wrong_note_voices);
    std::uint64_t state_interval_frames = 0U;
    for (const auto& state :
         result.false_wrong_note_state_interval_frames) {
      state_interval_frames = std::accumulate(
          state.begin(), state.end(), state_interval_frames);
    }
    M3_EXPECT_EQ(state_interval_frames, result.false_wrong_note_voices);
    std::uint64_t expected_observed_frames = 0U;
    for (const auto& expected_note :
         result.false_wrong_note_expected_observed_frames) {
      expected_observed_frames = std::accumulate(
          expected_note.begin(), expected_note.end(),
          expected_observed_frames);
    }
    M3_EXPECT_EQ(expected_observed_frames,
                 result.false_wrong_note_voices);
    M3_EXPECT_TRUE(result.false_wrong_note_detected_expected_frames <=
                   result.false_wrong_note_voices);
    M3_EXPECT_TRUE(result.false_wrong_note_output_changed_frames <=
                   result.false_wrong_note_voices);
    M3_EXPECT_TRUE(result.false_wrong_note_detected_expected_frames <=
                   result.false_wrong_note_output_changed_frames);
    for (std::size_t threshold = 0U;
         threshold < m3::offline::kCalibratedPitchRebinThresholds.size();
         ++threshold) {
      const std::uint64_t direct = std::accumulate(
          result.calibrated_pitch_rebin_outcome_frames[threshold].begin(),
          result.calibrated_pitch_rebin_outcome_frames[threshold].end(),
          std::uint64_t{0});
      std::uint64_t joint = 0U;
      for (std::size_t member = 0U;
           member < m3::offline::kCalibratedPitchRebinMemberBucketCount;
           ++member) {
        const auto& bins =
            result.calibrated_pitch_rebin_member_age_outcome_frames
                [threshold *
                     m3::offline::kCalibratedPitchRebinMemberBucketCount +
                 member];
        joint = std::accumulate(bins.begin(), bins.end(), joint);
      }
      M3_EXPECT_EQ(joint, direct);
    }
    const std::uint64_t production_improvement_total = std::accumulate(
        result.calibrated_pitch_rebin_stable_outcome_frames[7U].begin(),
        result.calibrated_pitch_rebin_stable_outcome_frames[7U].end(),
        std::uint64_t{0});
    for (std::size_t threshold = 0U;
         threshold <
         m3::offline::kCalibratedPitchRebinProjectedErrorThresholds.size();
         ++threshold) {
      const std::uint64_t swept_total = std::accumulate(
          result
              .calibrated_pitch_rebin_projected_error_outcome_frames[threshold]
              .begin(),
          result
              .calibrated_pitch_rebin_projected_error_outcome_frames[threshold]
              .end(),
          std::uint64_t{0});
      M3_EXPECT_EQ(swept_total, production_improvement_total);
      M3_EXPECT_TRUE(
          result.calibrated_pitch_rebin_projected_error_changed_frames
                    [threshold] <= swept_total);
    }
    for (std::size_t direction = 0U;
         direction < m3::offline::kAdjacentWrongNoteDirectionCount;
         ++direction) {
      const std::size_t interval =
          direction == 0U
              ? m3::offline::kCandidateSpectralIntervalRadius - 1U
              : m3::offline::kCandidateSpectralIntervalRadius + 1U;
      const std::uint64_t dispositions = std::accumulate(
          result.adjacent_wrong_note_projection_disposition_frames[direction]
              .begin(),
          result.adjacent_wrong_note_projection_disposition_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t lanes = std::accumulate(
          result.adjacent_wrong_note_lane_disposition_frames[direction].begin(),
          result.adjacent_wrong_note_lane_disposition_frames[direction].end(),
          std::uint64_t{0});
      const std::uint64_t reasons = std::accumulate(
          result.adjacent_wrong_note_projection_reason_frames[direction]
              .begin(),
          result.adjacent_wrong_note_projection_reason_frames[direction].end(),
          std::uint64_t{0});
      const std::uint64_t presence = std::accumulate(
          result.adjacent_wrong_note_expected_presence_frames[direction]
              .begin(),
          result.adjacent_wrong_note_expected_presence_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t joint = std::accumulate(
          result.adjacent_wrong_note_joint_context_frames[direction].begin(),
          result.adjacent_wrong_note_joint_context_frames[direction].end(),
          std::uint64_t{0});
      M3_EXPECT_EQ(dispositions,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(reasons,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(presence,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(lanes, result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(joint, result.false_wrong_note_interval_frames[interval]);
    }
#endif
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
      M3_EXPECT_EQ(result.transition_inside_hold_count,
                   baseline.transition_inside_hold_count);
      M3_EXPECT_EQ(result.transition_gap_count,
                   baseline.transition_gap_count);
      M3_EXPECT_EQ(result.false_gap_voices, baseline.false_gap_voices);
      M3_EXPECT_EQ(result.false_wrong_note_voices,
                   baseline.false_wrong_note_voices);
      M3_EXPECT_EQ(result.false_wrong_string_voices,
                   baseline.false_wrong_string_voices);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
      M3_EXPECT_EQ(
          result.false_wrong_note_state_interval_frames,
          baseline.false_wrong_note_state_interval_frames);
      M3_EXPECT_EQ(
          result.calibrated_pitch_rebin_projected_error_outcome_frames,
          baseline.calibrated_pitch_rebin_projected_error_outcome_frames);
      M3_EXPECT_EQ(
          result.calibrated_pitch_rebin_projected_error_changed_frames,
          baseline.calibrated_pitch_rebin_projected_error_changed_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_projection_disposition_frames,
          baseline.adjacent_wrong_note_projection_disposition_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_projection_reason_frames,
          baseline.adjacent_wrong_note_projection_reason_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_presence_frames,
          baseline.adjacent_wrong_note_expected_presence_frames);
      M3_EXPECT_EQ(result.adjacent_wrong_note_lane_disposition_frames,
                   baseline.adjacent_wrong_note_lane_disposition_frames);
      M3_EXPECT_EQ(result.adjacent_wrong_note_joint_context_frames,
                   baseline.adjacent_wrong_note_joint_context_frames);
      M3_EXPECT_EQ(result.multi_partial_phase_rebin_available_frames,
                   baseline.multi_partial_phase_rebin_available_frames);
      M3_EXPECT_EQ(result.multi_partial_phase_rebin_outcome_frames,
                   baseline.multi_partial_phase_rebin_outcome_frames);
      M3_EXPECT_EQ(result.multi_partial_phase_rebin_changed_frames,
                   baseline.multi_partial_phase_rebin_changed_frames);
      M3_EXPECT_EQ(
          result.combined_candidate_admission_selected_frames,
          baseline.combined_candidate_admission_selected_frames);
      M3_EXPECT_EQ(result.physical_group_causal_frames,
                   baseline.physical_group_causal_frames);
      M3_EXPECT_EQ(result.physical_group_pending_causal_frames,
                   baseline.physical_group_pending_causal_frames);
      M3_EXPECT_EQ(result.physical_group_member_pending_causal_frames,
                   baseline.physical_group_member_pending_causal_frames);
      M3_EXPECT_EQ(result.physical_group_member_exact_exit_frames,
                   baseline.physical_group_member_exact_exit_frames);
      M3_EXPECT_EQ(result.physical_group_causal_runs,
                   baseline.physical_group_causal_runs);
      M3_EXPECT_EQ(result.physical_group_causal_longest_run_frames,
                   baseline.physical_group_causal_longest_run_frames);
      M3_EXPECT_EQ(result.physical_group_member_causal_frames,
                   baseline.physical_group_member_causal_frames);
      M3_EXPECT_EQ(result.physical_group_member_causal_runs,
                   baseline.physical_group_member_causal_runs);
      M3_EXPECT_EQ(result.physical_group_member_causal_longest_run_frames,
                   baseline.physical_group_member_causal_longest_run_frames);
      M3_EXPECT_EQ(result.physical_group_fine_classifier_frames,
                   baseline.physical_group_fine_classifier_frames);
      M3_EXPECT_EQ(result.physical_group_member_fine_classifier_frames,
                   baseline.physical_group_member_fine_classifier_frames);
      M3_EXPECT_EQ(result.fine_residual_expansion_changed_frames,
                   baseline.fine_residual_expansion_changed_frames);
      M3_EXPECT_EQ(result.fine_residual_expansion_exact_frames,
                   baseline.fine_residual_expansion_exact_frames);
      M3_EXPECT_EQ(result.fine_residual_expansion_matched_delta,
                   baseline.fine_residual_expansion_matched_delta);
      M3_EXPECT_EQ(result.fine_residual_expansion_wrong_string_delta,
                   baseline.fine_residual_expansion_wrong_string_delta);
#endif
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
              baseline.label_results[label]
                  .maximum_matching_note_beat_hz_q8);
          M3_EXPECT_EQ(
              result.label_results[label].matching_note_lane_mask_frames,
              baseline.label_results[label].matching_note_lane_mask_frames);
          M3_EXPECT_EQ(result.label_results[label].cents_observations,
                       baseline.label_results[label].cents_observations);
          M3_EXPECT_EQ(result.label_results[label].cents_error_sum_q8,
                       baseline.label_results[label].cents_error_sum_q8);
          M3_EXPECT_EQ(result.label_results[label].cents_error_square_sum_q16,
                       baseline.label_results[label]
                           .cents_error_square_sum_q16);
          M3_EXPECT_EQ(result.label_results[label].cents_errors_q8,
                       baseline.label_results[label].cents_errors_q8);
          M3_EXPECT_EQ(result.label_results[label].first_valid_cents_sample,
                       baseline.label_results[label]
                           .first_valid_cents_sample);
          M3_EXPECT_EQ(result.label_results[label].first_correct_string_sample,
                       baseline.label_results[label]
                           .first_correct_string_sample);
          M3_EXPECT_EQ(result.label_results[label].string_flip_count,
                       baseline.label_results[label].string_flip_count);
          M3_EXPECT_EQ(result.label_results[label].longest_correct_run_frames,
                       baseline.label_results[label]
                           .longest_correct_run_frames);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
          M3_EXPECT_EQ(
              result.label_results[label].selection_disposition_frames,
              baseline.label_results[label].selection_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label].quiet_disposition_frames,
              baseline.label_results[label].quiet_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label].minimum_evidence_resume_flag_frames,
              baseline.label_results[label]
                  .minimum_evidence_resume_flag_frames);
          M3_EXPECT_EQ(
              result.label_results[label].quiet_disposition_runs,
              baseline.label_results[label].quiet_disposition_runs);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .longest_quiet_disposition_run_frames,
              baseline.label_results[label]
                  .longest_quiet_disposition_run_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_history_carry_disposition_frames,
              baseline.label_results[label]
                  .fine_history_carry_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label].candidate_unison_spectral_frames,
              baseline.label_results[label]
                  .candidate_unison_spectral_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_spectral_invalid_frames,
              baseline.label_results[label]
                  .candidate_unison_spectral_invalid_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_spectral_fitted_mask_frames,
              baseline.label_results[label]
                  .candidate_unison_spectral_fitted_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_reacquisition_disposition_frames,
              baseline.label_results[label]
                  .spectral_reacquisition_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_reacquisition_lane_outcome_frames,
              baseline.label_results[label]
                  .spectral_reacquisition_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_projected_changed_frames,
              baseline.label_results[label]
                  .candidate_unison_projected_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_projected_exact_frames,
              baseline.label_results[label]
                  .candidate_unison_projected_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_projected_matched_frames,
              baseline.label_results[label]
                  .candidate_unison_projected_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_unison_projected_wrong_string_voices,
              baseline.label_results[label]
                  .candidate_unison_projected_wrong_string_voices);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_projected_frames,
              baseline.label_results[label]
                  .unison_reacquisition_projected_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_changed_frames,
              baseline.label_results[label]
                  .unison_reacquisition_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_exact_frames,
              baseline.label_results[label]
                  .unison_reacquisition_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_matched_frames,
              baseline.label_results[label]
                  .unison_reacquisition_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_wrong_string_voices,
              baseline.label_results[label]
                  .unison_reacquisition_wrong_string_voices);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_exact_delta,
              baseline.label_results[label]
                  .unison_reacquisition_exact_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_matched_delta,
              baseline.label_results[label]
                  .unison_reacquisition_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_reacquisition_wrong_string_delta,
              baseline.label_results[label]
                  .unison_reacquisition_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_eligible_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_eligible_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_projected_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_projected_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_changed_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_exact_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_matched_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_wrong_string_voices,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_wrong_string_voices);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_exact_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_exact_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_matched_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_wrong_string_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_disposition_frames,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_matched_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_exact_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_exact_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_wrong_string_delta,
              baseline.label_results[label]
                  .articulated_unison_reacquisition_counterfactual_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label].continuity_union_changed_frames,
              baseline.label_results[label].continuity_union_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label].continuity_union_exact_frames,
              baseline.label_results[label].continuity_union_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label].continuity_union_matched_frames,
              baseline.label_results[label].continuity_union_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label].continuity_union_exact_delta,
              baseline.label_results[label].continuity_union_exact_delta);
          M3_EXPECT_EQ(
              result.label_results[label].continuity_union_matched_delta,
              baseline.label_results[label].continuity_union_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .continuity_union_wrong_string_delta,
              baseline.label_results[label]
                  .continuity_union_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_projected_frames,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_projected_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_changed_frames,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_exact_frames,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_matched_frames,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_wrong_string_voices,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_wrong_string_voices);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_exact_delta,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_exact_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_matched_delta,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_wrong_string_delta,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_reacquisition_disposition_frames,
              baseline.label_results[label]
                  .observed_fingerprint_reacquisition_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_committed_relation_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_committed_relation_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_committed_member_count_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_committed_member_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_snapshot_voice_count_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_snapshot_voice_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_other_owned_lane_count_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_other_owned_lane_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_production_disposition_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_production_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_production_cache_age_50ms_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_production_cache_age_50ms_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_production_cache_mask_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_production_cache_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_score_threshold_ratio_05_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_score_threshold_ratio_05_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .observed_fingerprint_changed_direct_fundamental_frames,
              baseline.label_results[label]
                  .observed_fingerprint_changed_direct_fundamental_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_score_threshold_ratio_frames,
              baseline.label_results[label]
                  .candidate_score_threshold_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_true_pitch_count_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_true_pitch_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_selected_pitch_count_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_selected_pitch_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_score_ratio_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_score_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_evidence_flag_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_evidence_flag_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_playable_lane_count_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_playable_lane_count_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_calibration_relation_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_calibration_relation_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_calibration_similarity_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_calibration_similarity_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_calibration_margin_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_calibration_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_posterior_relation_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_posterior_relation_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_posterior_probability_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_posterior_probability_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_dp_evicted_posterior_margin_frames,
              baseline.label_results[label]
                  .candidate_dp_evicted_posterior_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_score_ratio_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_score_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_fundamental_ratio_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_fundamental_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_evidence_flag_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_evidence_flag_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_direct_evidence_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_direct_evidence_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_pitch_band_peak_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_pitch_band_peak_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_calibration_best_string_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_calibration_best_string_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_below_threshold_calibration_relation_margin_frames,
              baseline.label_results[label]
                  .candidate_below_threshold_calibration_relation_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_fundamental_ratio_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_fundamental_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_evidence_flag_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_evidence_flag_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_calibration_relation_fundamental_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_calibration_relation_fundamental_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_calibration_best_string_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_calibration_best_string_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_interval_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_interval_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_fundamental_ratio_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_fundamental_ratio_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_kind_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_kind_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_other_eligible_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_other_eligible_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_strongest_other_interval_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_strongest_other_interval_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_rejected_shadow_strongest_other_evidence_frames,
              baseline.label_results[label]
                  .candidate_spectral_rejected_shadow_strongest_other_evidence_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_frequency_member_mask_frames,
              baseline.label_results[label]
                  .fine_frequency_member_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_unique_member_pruning_changed_frames,
              baseline.label_results[label]
                  .fine_unique_member_pruning_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_unique_member_pruning_exact_frames,
              baseline.label_results[label]
                  .fine_unique_member_pruning_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_unique_member_pruning_matched_delta,
              baseline.label_results[label]
                  .fine_unique_member_pruning_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_unique_member_pruning_wrong_string_delta,
              baseline.label_results[label]
                  .fine_unique_member_pruning_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_frequency_pending_member_mask_frames,
              baseline.label_results[label]
                  .fine_frequency_pending_member_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_frequency_disposition_frames,
              baseline.label_results[label]
                  .fine_frequency_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_frequency_fit_member_mask_frames,
              baseline.label_results[label]
                  .fine_frequency_fit_member_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_exact_pairwise_beat_above_gate_frames,
              baseline.label_results[label]
                  .committed_exact_pairwise_beat_above_gate_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_exact_pairwise_beat_connected_frames,
              baseline.label_results[label]
                  .committed_exact_pairwise_beat_connected_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .exact_fit_residual_improvement_frames,
              baseline.label_results[label]
                  .exact_fit_residual_improvement_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .other_fit_residual_improvement_frames,
              baseline.label_results[label]
                  .other_fit_residual_improvement_frames);
          M3_EXPECT_EQ(
              result.label_results[label].string_fret_posterior_best_frames,
              baseline.label_results[label]
                  .string_fret_posterior_best_frames);
          M3_EXPECT_EQ(
              result.label_results[label].selection_lane_outcome_frames,
              baseline.label_results[label]
                  .selection_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label].posterior_lane_outcome_frames,
              baseline.label_results[label]
                  .posterior_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .string_fret_posterior_probability_frames,
              baseline.label_results[label]
                  .string_fret_posterior_probability_frames);
          M3_EXPECT_EQ(
              result.label_results[label].string_fret_posterior_margin_frames,
              baseline.label_results[label]
                  .string_fret_posterior_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .relaxed_band_posterior_agreement_frames,
              baseline.label_results[label]
                  .relaxed_band_posterior_agreement_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .relaxed_band_spectral_agreement_frames,
              baseline.label_results[label]
                  .relaxed_band_spectral_agreement_frames);
          M3_EXPECT_EQ(
              result.label_results[label].spectral_lane_projection_frames,
              baseline.label_results[label]
                  .spectral_lane_projection_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_changed_frames,
              baseline.label_results[label]
                  .spectral_lane_projection_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_matched_delta,
              baseline.label_results[label]
                  .spectral_lane_projection_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_wrong_string_delta,
              baseline.label_results[label]
                  .spectral_lane_projection_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_phase_frames,
              baseline.label_results[label]
                  .spectral_lane_projection_phase_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_phase_changed_frames,
              baseline.label_results[label]
                  .spectral_lane_projection_phase_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_phase_matched_delta,
              baseline.label_results[label]
                  .spectral_lane_projection_phase_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_lane_projection_phase_wrong_string_delta,
              baseline.label_results[label]
                  .spectral_lane_projection_phase_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_frames,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_changed_frames,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_matched_delta,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_wrong_string_delta,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_phase_frames,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_phase_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_phase_matched_delta,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_phase_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .candidate_spectral_lane_projection_phase_wrong_string_delta,
              baseline.label_results[label]
                  .candidate_spectral_lane_projection_phase_wrong_string_delta);
#if defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
          M3_EXPECT_EQ(
              result.label_results[label]
                  .string_fret_spectral_head_best_frames,
              baseline.label_results[label]
                  .string_fret_spectral_head_best_frames);
          M3_EXPECT_EQ(
              result.label_results[label].spectral_head_vote_mask_frames,
              baseline.label_results[label].spectral_head_vote_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_head_plurality_best_frames,
              baseline.label_results[label]
                  .spectral_head_plurality_best_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_tier_production_relation_lane_outcome_frames,
              baseline.label_results[label]
                  .spectral_tier_production_relation_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selector_group_relation_lane_outcome_frames,
              baseline.label_results[label]
                  .selector_group_relation_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_completion_disposition_lane_outcome_frames,
              baseline.label_results[label]
                  .tier_completion_disposition_lane_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label].profile_unison_proposal_mask_frames,
              baseline.label_results[label]
                  .profile_unison_proposal_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label].temporal_unison_proposal_mask_frames,
              baseline.label_results[label]
                  .temporal_unison_proposal_mask_frames);
          M3_EXPECT_EQ(
              result.label_results[label].spectral_corridor_fingerprint_sum,
              baseline.label_results[label]
                  .spectral_corridor_fingerprint_sum);
          M3_EXPECT_EQ(
              result.label_results[label].spectral_onset_fingerprint_sum,
              baseline.label_results[label].spectral_onset_fingerprint_sum);
          M3_EXPECT_EQ(
              result.label_results[label].spectral_settled_fingerprint_sum,
              baseline.label_results[label]
                  .spectral_settled_fingerprint_sum);
          M3_EXPECT_EQ(result.label_results[label].spectral_corridor_frames,
                       baseline.label_results[label]
                           .spectral_corridor_frames);
          M3_EXPECT_EQ(result.label_results[label].spectral_onset_frames,
                       baseline.label_results[label].spectral_onset_frames);
          M3_EXPECT_EQ(result.label_results[label].spectral_settled_frames,
                       baseline.label_results[label].spectral_settled_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_head_correct_margin_frames,
              baseline.label_results[label]
                  .spectral_head_correct_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .spectral_head_other_margin_frames,
              baseline.label_results[label]
                  .spectral_head_other_margin_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_consensus_projected_frames,
              baseline.label_results[label]
                  .selected_subset_consensus_projected_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_consensus_changed_frames,
              baseline.label_results[label]
                  .selected_subset_consensus_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_consensus_exact_frames,
              baseline.label_results[label]
                  .selected_subset_consensus_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_consensus_matched_delta,
              baseline.label_results[label]
                  .selected_subset_consensus_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_consensus_wrong_string_delta,
              baseline.label_results[label]
                  .selected_subset_consensus_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .selected_subset_evidence_outcome_frames,
              baseline.label_results[label]
                  .selected_subset_evidence_outcome_frames);
          M3_EXPECT_EQ(
              result.label_results[label].classifier_subset_projection_frames,
              baseline.label_results[label]
                  .classifier_subset_projection_frames);
          M3_EXPECT_EQ(
              result.label_results[label].classifier_subset_changed_frames,
              baseline.label_results[label].classifier_subset_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label].classifier_subset_exact_frames,
              baseline.label_results[label].classifier_subset_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label].classifier_subset_matched_delta,
              baseline.label_results[label].classifier_subset_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .classifier_subset_wrong_string_delta,
              baseline.label_results[label]
                  .classifier_subset_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .classifier_subset_disposition_frames,
              baseline.label_results[label]
                  .classifier_subset_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_changed_frames,
              baseline.label_results[label]
                  .combined_spectral_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_exact_frames,
              baseline.label_results[label]
                  .combined_spectral_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_matched_frames,
              baseline.label_results[label]
                  .combined_spectral_completion_matched_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_wrong_string_voices,
              baseline.label_results[label]
                  .combined_spectral_completion_wrong_string_voices);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_matched_delta,
              baseline.label_results[label]
                  .combined_spectral_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .combined_spectral_completion_wrong_string_delta,
              baseline.label_results[label]
                  .combined_spectral_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .temporal_combined_completion_changed_frames,
              baseline.label_results[label]
                  .temporal_combined_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .temporal_combined_completion_exact_frames,
              baseline.label_results[label]
                  .temporal_combined_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .temporal_combined_completion_matched_delta,
              baseline.label_results[label]
                  .temporal_combined_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .temporal_combined_completion_wrong_string_delta,
              baseline.label_results[label]
                  .temporal_combined_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_priority_completion_changed_frames,
              baseline.label_results[label]
                  .tier_priority_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_priority_completion_exact_frames,
              baseline.label_results[label]
                  .tier_priority_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_priority_completion_matched_delta,
              baseline.label_results[label]
                  .tier_priority_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_priority_completion_wrong_string_delta,
              baseline.label_results[label]
                  .tier_priority_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_group_completion_changed_frames,
              baseline.label_results[label]
                  .cached_group_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_group_completion_exact_frames,
              baseline.label_results[label]
                  .cached_group_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_group_completion_matched_delta,
              baseline.label_results[label]
                  .cached_group_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_group_completion_wrong_string_delta,
              baseline.label_results[label]
                  .cached_group_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_classifier_continuity_changed_frames,
              baseline.label_results[label]
                  .cached_classifier_continuity_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_classifier_continuity_exact_frames,
              baseline.label_results[label]
                  .cached_classifier_continuity_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_classifier_continuity_matched_delta,
              baseline.label_results[label]
                  .cached_classifier_continuity_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .cached_classifier_continuity_wrong_string_delta,
              baseline.label_results[label]
                  .cached_classifier_continuity_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .continuity_classifier_union_changed_frames,
              baseline.label_results[label]
                  .continuity_classifier_union_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .continuity_classifier_union_exact_frames,
              baseline.label_results[label]
                  .continuity_classifier_union_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .continuity_classifier_union_matched_delta,
              baseline.label_results[label]
                  .continuity_classifier_union_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .continuity_classifier_union_wrong_string_delta,
              baseline.label_results[label]
                  .continuity_classifier_union_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_ratio_completion_changed_frames,
              baseline.label_results[label]
                  .tier_ratio_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_ratio_completion_exact_frames,
              baseline.label_results[label]
                  .tier_ratio_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_ratio_completion_matched_delta,
              baseline.label_results[label]
                  .tier_ratio_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_ratio_completion_wrong_string_delta,
              baseline.label_results[label]
                  .tier_ratio_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .safe_joint_completion_changed_frames,
              baseline.label_results[label]
                  .safe_joint_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .safe_joint_completion_exact_frames,
              baseline.label_results[label]
                  .safe_joint_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .safe_joint_completion_matched_delta,
              baseline.label_results[label]
                  .safe_joint_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .safe_joint_completion_wrong_string_delta,
              baseline.label_results[label]
                  .safe_joint_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_tier_completion_changed_frames,
              baseline.label_results[label]
                  .bounded_tier_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_tier_completion_exact_frames,
              baseline.label_results[label]
                  .bounded_tier_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_tier_completion_matched_delta,
              baseline.label_results[label]
                  .bounded_tier_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_tier_completion_wrong_string_delta,
              baseline.label_results[label]
                  .bounded_tier_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_joint_completion_changed_frames,
              baseline.label_results[label]
                  .bounded_joint_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_joint_completion_exact_frames,
              baseline.label_results[label]
                  .bounded_joint_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_joint_completion_matched_delta,
              baseline.label_results[label]
                  .bounded_joint_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .bounded_joint_completion_wrong_string_delta,
              baseline.label_results[label]
                  .bounded_joint_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label].tier_ratio08_changed_by_phase,
              baseline.label_results[label].tier_ratio08_changed_by_phase);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_ratio08_matched_delta_by_phase,
              baseline.label_results[label]
                  .tier_ratio08_matched_delta_by_phase);
          M3_EXPECT_EQ(
              result.label_results[label].tier_ratio08_wrong_delta_by_phase,
              baseline.label_results[label]
                  .tier_ratio08_wrong_delta_by_phase);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_beat_completion_changed_frames,
              baseline.label_results[label]
                  .tier_beat_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_beat_completion_exact_frames,
              baseline.label_results[label]
                  .tier_beat_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_beat_completion_matched_delta,
              baseline.label_results[label]
                  .tier_beat_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_beat_completion_wrong_string_delta,
              baseline.label_results[label]
                  .tier_beat_completion_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_classifier_completion_changed_frames,
              baseline.label_results[label]
                  .tier_classifier_completion_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_classifier_completion_exact_frames,
              baseline.label_results[label]
                  .tier_classifier_completion_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_classifier_completion_matched_delta,
              baseline.label_results[label]
                  .tier_classifier_completion_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .tier_classifier_completion_wrong_string_delta,
              baseline.label_results[label]
                  .tier_classifier_completion_wrong_string_delta);
#endif
#endif
        }
      }
    }
  }
}

M3_TEST(offline_wrong_note_age_buckets_have_exact_causal_boundaries) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint64_t kStart = 1000U;
  const auto bucket = [](std::uint64_t age) {
    return m3::offline::false_wrong_note_age_bucket(
        kStart + age, kStart, kSampleRate);
  };

  M3_EXPECT_EQ(bucket(0U), 0U);
  M3_EXPECT_EQ(bucket(2399U), 0U);
  M3_EXPECT_EQ(bucket(2400U), 1U);
  M3_EXPECT_EQ(bucket(4799U), 1U);
  M3_EXPECT_EQ(bucket(4800U), 2U);
  M3_EXPECT_EQ(bucket(9599U), 2U);
  M3_EXPECT_EQ(bucket(9600U), 3U);
  M3_EXPECT_EQ(bucket(16799U), 3U);
  M3_EXPECT_EQ(bucket(16800U), 4U);
  M3_EXPECT_EQ(bucket(23999U), 4U);
  M3_EXPECT_EQ(bucket(24000U), 5U);
  M3_EXPECT_EQ(bucket(35999U), 5U);
  M3_EXPECT_EQ(bucket(36000U), 6U);
  M3_EXPECT_EQ(
      m3::offline::false_wrong_note_age_bucket(kStart - 1U, kStart,
                                                kSampleRate),
      m3::offline::kFalseWrongNoteAgeBucketCount);
  M3_EXPECT_EQ(
      m3::offline::false_wrong_note_age_bucket(kStart, kStart, 0U),
      m3::offline::kFalseWrongNoteAgeBucketCount);
}

M3_TEST(offline_wrong_note_cents_buckets_preserve_quantization_boundaries) {
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(-12800, true), 0U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(-11521, true), 0U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(-11520, true), 1U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(-1, true), 9U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(0, true), 10U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(11519, true), 18U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(11520, true), 19U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(12800, true), 20U);
  M3_EXPECT_EQ(m3::offline::false_wrong_note_cents_bucket(0, false), 21U);
}

M3_TEST(offline_calibrated_pitch_rebin_requires_a_decisively_closer_fret) {
  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  auto& current = bank.points[0][8];
  current.quality = m3::CalibrationPointQuality::measured;
  current.cents_offset_q8 = static_cast<std::int16_t>(-40 * 256);
  auto& upper = bank.points[0][9];
  upper.quality = m3::CalibrationPointQuality::measured;
  upper.cents_offset_q8 = static_cast<std::int16_t>(-40 * 256);

  const auto changed = m3::offline::calibrated_pitch_rebin(
      40U, static_cast<std::int16_t>(48 * 256), true, 0U, bank, 24U,
      75.0);
  M3_EXPECT_TRUE(changed.changed);
  M3_EXPECT_EQ(changed.note, 41U);
  M3_EXPECT_EQ(changed.fret_delta, 1);
  M3_EXPECT_NEAR(changed.error_improvement_cents, 76.0, 1.0e-9);
  M3_EXPECT_NEAR(changed.projected_error_cents, 12.0, 1.0e-9);
  M3_EXPECT_TRUE(
      m3::offline::calibrated_pitch_rebin_projected_error_eligible(
          changed, 12.0));
  M3_EXPECT_FALSE(
      m3::offline::calibrated_pitch_rebin_projected_error_eligible(
          changed, 11.9));

  const auto bounded = m3::offline::calibrated_pitch_rebin(
      40U, static_cast<std::int16_t>(48 * 256), true, 0U, bank, 24U,
      77.0);
  M3_EXPECT_FALSE(bounded.changed);
  M3_EXPECT_EQ(bounded.note, 40U);
  M3_EXPECT_EQ(bounded.fret_delta, 0);
  M3_EXPECT_FALSE(
      m3::offline::calibrated_pitch_rebin_projected_error_eligible(
          bounded, 100.0));

  const auto invalid = m3::offline::calibrated_pitch_rebin(
      40U, static_cast<std::int16_t>(48 * 256), false, 0U, bank, 24U,
      0.0);
  M3_EXPECT_FALSE(invalid.changed);
  M3_EXPECT_EQ(invalid.note, 40U);
}

M3_TEST(offline_calibrated_pitch_rebin_context_excludes_onsets_and_unisons) {
  M3_EXPECT_TRUE(m3::offline::calibrated_pitch_rebin_context_eligible(
      0U, 1U, 2U));
  M3_EXPECT_TRUE(m3::offline::calibrated_pitch_rebin_context_eligible(
      1U, 1U, 2U));
  M3_EXPECT_FALSE(m3::offline::calibrated_pitch_rebin_context_eligible(
      2U, 1U, 2U));
  M3_EXPECT_FALSE(m3::offline::calibrated_pitch_rebin_context_eligible(
      1U, 0U, 2U));
  M3_EXPECT_FALSE(m3::offline::calibrated_pitch_rebin_context_eligible(
      1U, 1U, 1U));
}

M3_TEST(offline_calibrated_adjacent_projection_explains_unavailable_evidence) {
  using Disposition =
      m3::offline::CalibratedAdjacentProjectionDisposition;
  constexpr std::uint8_t kNote = 40U;
  constexpr std::int16_t kObserved = 48 * 256;

  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = 1U;
  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kObserved, true, 0U, bank, 24U, 1, 50.0),
               Disposition::current_point_unavailable);

  bank.points[0U][8U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][8U].cents_offset_q8 = 0;
  bank.points[0U][9U] = {};
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kObserved, true, 0U, bank, 24U, 1, 50.0),
               Disposition::expected_adjacent_point_unavailable);

  bank.points[0U][9U].quality =
      m3::CalibrationPointQuality::measured;
  bank.points[0U][9U].cents_offset_q8 = 0;
  constexpr std::int16_t kNearCurrent = 5 * 256;
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kNearCurrent, true, 0U, bank, 24U, 1, 50.0),
               Disposition::expected_adjacent_not_better);

  bank.points[0U][8U].cents_offset_q8 =
      static_cast<std::int16_t>(-5 * 256);
  bank.points[0U][9U].cents_offset_q8 =
      static_cast<std::int16_t>(-40 * 256);
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kObserved, true, 0U, bank, 24U, 1, 50.0),
               Disposition::improvement_below_threshold);
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kObserved, true, 0U, bank, 24U, 1, 40.0),
               Disposition::available);
  M3_EXPECT_EQ(m3::offline::classify_calibrated_adjacent_projection(
                   kNote, kObserved, false, 0U, bank, 24U, 1, 40.0),
               Disposition::invalid_input);
}

M3_TEST(offline_multi_partial_phase_cents_is_robust_and_stretch_corrected) {
  m3::PartialAbsoluteCentsEvidence evidence;
  evidence.cents = {0.0, 23.0, 24.0, 25.0, 80.0, 0.0};
  evidence.valid_mask = 0x1EU;
  m3::StringCalibrationPoint point;
  point.partial_detuning_q8 = {0, 3 * 256, 4 * 256, 5 * 256, 60 * 256, 0};
  point.partial_detuning_valid_mask = 0x1EU;

  const auto accepted = m3::offline::robust_multi_partial_phase_cents(
      evidence, point, 3U, 0.01);
  M3_EXPECT_TRUE(accepted.valid);
  M3_EXPECT_EQ(accepted.partial_count, 4U);
  M3_EXPECT_NEAR(accepted.cents, 20.0, 1.0e-9);
  M3_EXPECT_NEAR(accepted.maximum_deviation_cents, 0.0, 1.0e-9);

  evidence.cents[4U] = 92.0;
  const auto rejected = m3::offline::robust_multi_partial_phase_cents(
      evidence, point, 3U, 5.0);
  M3_EXPECT_FALSE(rejected.valid);
  M3_EXPECT_NEAR(rejected.cents, 20.0, 1.0e-9);
  M3_EXPECT_NEAR(rejected.maximum_deviation_cents, 12.0, 1.0e-9);

  point.partial_detuning_valid_mask = 0x06U;
  const auto insufficient = m3::offline::robust_multi_partial_phase_cents(
      evidence, point, 3U, 20.0);
  M3_EXPECT_FALSE(insufficient.valid);
}

M3_TEST(offline_adjacent_wrong_note_disposition_follows_the_production_gate_order) {
  using Context = m3::offline::AdjacentWrongNoteProjectionContext;
  using Disposition = m3::offline::AdjacentWrongNoteProjectionDisposition;
  const Context eligible{true, true, true, true, true, true, true, false};
  M3_EXPECT_EQ(
      m3::offline::classify_adjacent_wrong_note_projection(eligible),
      Disposition::eligible_unapplied);

  Context context = eligible;
  context.tracking = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::non_tracking);
  context = eligible;
  context.polyphonic_context = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::insufficient_polyphonic_context);
  context = eligible;
  context.old_enough = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::too_young);
  context = eligible;
  context.single_member = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::multi_member);
  context = eligible;
  context.cents_available = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::cents_unavailable);
  context = eligible;
  context.projection_available = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::projection_unavailable);
  context = eligible;
  context.projected_center_inside_guard = false;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::outside_projected_center_guard);
  context = eligible;
  context.collision = true;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_projection(context),
               Disposition::collision);
}

M3_TEST(offline_adjacent_wrong_note_expected_presence_preserves_lane_identity) {
  using Presence = m3::offline::AdjacentWrongNoteExpectedPresence;
  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_expected_presence(
                   snapshot, 49U, 2U),
               Presence::absent);

  snapshot.voice_count = 1U;
  snapshot.voices[0U].midi_note = 49U;
  snapshot.voices[0U].string_index = 2U;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_expected_presence(
                   snapshot, 49U, 2U),
               Presence::same_string);

  snapshot.voices[0U].string_index = 3U;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_expected_presence(
                   snapshot, 49U, 2U),
               Presence::other_string);

  snapshot.voice_count = 2U;
  snapshot.voices[1U].midi_note = 49U;
  snapshot.voices[1U].string_index = 2U;
  M3_EXPECT_EQ(m3::offline::classify_adjacent_wrong_note_expected_presence(
                   snapshot, 49U, 2U),
               Presence::same_and_other_string);
}

M3_TEST(offline_calibrated_pitch_rebin_latch_requires_consecutive_agreement) {
  m3::offline::CalibratedPitchRebinLatch latch;
  M3_EXPECT_FALSE(latch.observe(true, 41U, 2U));
  M3_EXPECT_TRUE(latch.observe(true, 41U, 2U));
  M3_EXPECT_FALSE(latch.observe(true, 42U, 2U));
  M3_EXPECT_FALSE(latch.observe(false, 42U, 2U));
  M3_EXPECT_FALSE(latch.observe(true, 42U, 2U));
  M3_EXPECT_TRUE(latch.observe(true, 42U, 2U));
  latch.reset();
  M3_EXPECT_FALSE(latch.observe(true, 42U, 2U));
}

M3_TEST(offline_replay_classifies_target_lane_outcomes_without_losing_masks) {
  using m3::offline::ReplayTargetLaneOutcome;
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x00U, 0x07U),
               ReplayTargetLaneOutcome::absent);
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x07U, 0x07U),
               ReplayTargetLaneOutcome::exact);
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x03U, 0x07U),
               ReplayTargetLaneOutcome::subset_missing);
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x0fU, 0x07U),
               ReplayTargetLaneOutcome::superset_extra);
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x0dU, 0x07U),
               ReplayTargetLaneOutcome::overlap_mixed);
  M3_EXPECT_EQ(m3::offline::classify_target_lane_outcome(0x18U, 0x07U),
               ReplayTargetLaneOutcome::disjoint_wrong);

  using m3::offline::ReplayGroupMaskRelation;
  M3_EXPECT_EQ(m3::offline::classify_group_mask_relation(0x00U, 0x07U),
               ReplayGroupMaskRelation::absent);
  M3_EXPECT_EQ(m3::offline::classify_group_mask_relation(0x07U, 0x07U),
               ReplayGroupMaskRelation::exact);
  M3_EXPECT_EQ(m3::offline::classify_group_mask_relation(0x03U, 0x07U),
               ReplayGroupMaskRelation::subset);
  M3_EXPECT_EQ(m3::offline::classify_group_mask_relation(0x09U, 0x07U),
               ReplayGroupMaskRelation::other);
  M3_EXPECT_EQ(m3::offline::classify_group_mask_relation(0x09U, 0xffU, true),
               ReplayGroupMaskRelation::exact);
  const std::size_t last = m3::offline::physical_group_causal_cell_index(
      m3::offline::kSelectionDispositionCount - 1U,
      ReplayGroupMaskRelation::other, ReplayGroupMaskRelation::other,
      ReplayTargetLaneOutcome::disjoint_wrong);
  M3_EXPECT_EQ(last, m3::offline::kPhysicalGroupCausalCellCount - 1U);
  const std::size_t last_unresolved =
      m3::offline::physical_group_fine_unresolved_cell_index(
          m3::offline::kSelectionDispositionCount - 1U,
          m3::offline::kFineFrequencyUnresolvedReasonCount - 1U,
          ReplayTargetLaneOutcome::disjoint_wrong);
  M3_EXPECT_EQ(
      last_unresolved,
      m3::offline::kPhysicalGroupFineUnresolvedCellCount - 1U);

  using m3::offline::ReplayClassifierMaskRelation;
  m3::UnisonSpectralClassification classifier;
  M3_EXPECT_EQ(m3::offline::classify_classifier_mask_relation(
                   classifier, 0x07U),
               ReplayClassifierMaskRelation::invalid);
  classifier.valid = true;
  classifier.member_mask = 0x07U;
  classifier.member_count = 3U;
  M3_EXPECT_EQ(m3::offline::classify_classifier_mask_relation(
                   classifier, 0x07U),
               ReplayClassifierMaskRelation::exact);
  classifier.member_mask = 0x03U;
  classifier.member_count = 2U;
  M3_EXPECT_EQ(m3::offline::classify_classifier_mask_relation(
                   classifier, 0x07U),
               ReplayClassifierMaskRelation::subset);
  classifier.member_mask = 0x09U;
  M3_EXPECT_EQ(m3::offline::classify_classifier_mask_relation(
                   classifier, 0x07U),
               ReplayClassifierMaskRelation::other);
  const std::size_t last_classifier =
      m3::offline::physical_group_fine_classifier_cell_index(
          ReplayGroupMaskRelation::other,
          ReplayClassifierMaskRelation::other,
          ReplayTargetLaneOutcome::disjoint_wrong);
  M3_EXPECT_EQ(
      last_classifier,
      m3::offline::kPhysicalGroupFineClassifierCellCount - 1U);

  m3::offline::FineResidualExpansionEvidence expansion;
  expansion.active = true;
  expansion.selected = true;
  expansion.direct_fundamental = true;
  expansion.score_threshold_ratio = 0.75;
  expansion.residual_improvement = 0.06;
  expansion.residual_rejected = true;
  expansion.committed_mask = 0x03U;
  expansion.fit_mask = 0x07U;
  expansion.playable_mask = 0x07U;
  expansion.other_owned_mask = 0x00U;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0x07U);
  expansion.playable_mask = 0x0fU;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0U);
  expansion.playable_mask = 0x07U;
  expansion.fit_mask = 0x06U;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0U);
  expansion.fit_mask = 0x07U;
  expansion.other_owned_mask = 0x04U;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0U);
  expansion.other_owned_mask = 0x00U;
  expansion.residual_improvement = 0.04;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0U);
  expansion.residual_improvement = 0.06;
  expansion.residual_rejected = false;
  M3_EXPECT_EQ(m3::offline::bounded_fine_residual_expansion(
                   expansion, 0.50, 0.05, 5U),
               0U);
}

M3_TEST(offline_replay_classifies_observed_fingerprint_changed_frame_state) {
  const auto subset =
      m3::offline::diagnose_observed_fingerprint_changed_frame(
          0x03U, 0x07U, 5U, 0x30U);
  M3_EXPECT_EQ(subset.committed_relation,
               m3::offline::ReplayGroupMaskRelation::subset);
  M3_EXPECT_EQ(subset.committed_member_count, 2U);
  M3_EXPECT_EQ(subset.snapshot_voice_count, 5U);
  M3_EXPECT_EQ(subset.other_owned_lane_count, 2U);

  const auto saturated =
      m3::offline::diagnose_observed_fingerprint_changed_frame(
          0x07U, 0x07U, 0xffU, 0xffU);
  M3_EXPECT_EQ(saturated.committed_relation,
               m3::offline::ReplayGroupMaskRelation::exact);
  M3_EXPECT_EQ(saturated.committed_member_count, 3U);
  M3_EXPECT_EQ(saturated.snapshot_voice_count,
               static_cast<std::uint8_t>(m3::kMaxVoices));
  M3_EXPECT_EQ(saturated.other_owned_lane_count,
               static_cast<std::uint8_t>(m3::kMaxVoices));
}

M3_TEST(offline_candidate_spectral_partition_covers_each_safety_class) {
  using m3::offline::CandidateSpectralPartitionClass;
  constexpr std::size_t kGateCount =
      m3::offline::kCandidateSpectralShadowGateCount;

  const auto correct = m3::offline::candidate_spectral_partition_cell(
      1U, 2U, 0x04U, true, 0x04U, false);
  M3_EXPECT_TRUE(correct.valid);
  M3_EXPECT_EQ(correct.row, kGateCount + 2U);
  M3_EXPECT_EQ(correct.string, 2U);
  M3_EXPECT_EQ(correct.classification,
               CandidateSpectralPartitionClass::target_correct);

  const auto wrong_string =
      m3::offline::candidate_spectral_partition_cell(
          2U, 3U, 0x20U, true, 0x04U, false);
  M3_EXPECT_TRUE(wrong_string.valid);
  M3_EXPECT_EQ(wrong_string.row, 2U * kGateCount + 3U);
  M3_EXPECT_EQ(wrong_string.string, 5U);
  M3_EXPECT_EQ(wrong_string.classification,
               CandidateSpectralPartitionClass::target_wrong_string);

  const auto other_false =
      m3::offline::candidate_spectral_partition_cell(
          4U, 5U, 0x80U, false, 0U, false);
  M3_EXPECT_TRUE(other_false.valid);
  M3_EXPECT_EQ(other_false.row, 4U * kGateCount + 5U);
  M3_EXPECT_EQ(other_false.string, 7U);
  M3_EXPECT_EQ(other_false.classification,
               CandidateSpectralPartitionClass::other_false);
}

M3_TEST(offline_replay_shadow_classifies_each_ready_frame_without_midi_changes) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kSamples = kSampleRate;
  constexpr double kTwoPi = 6.28318530717958647692;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  wave.mono_samples.resize(kSamples);
  m3::offline::UnisonSpectralCorridorTracker tracker;
  M3_EXPECT_TRUE(tracker.configure(kSampleRate, kNote));
  for (std::size_t sample = 0U; sample < kSamples; ++sample) {
    const bool sounding =
        (sample >= kSampleRate / 6U && sample < kSampleRate / 3U) ||
        sample >= kSampleRate / 2U;
    const double value =
        sounding ? 0.30 * std::sin(kTwoPi * frequency *
                                   static_cast<double>(sample) / kSampleRate)
                 : 0.0;
    wave.mono_samples[sample] = value;
    tracker.observe(value);
  }
  const m3::UnisonSpectralFingerprint observed = tracker.fingerprint();
  m3::offline::UnisonSpectralShadowTemplateBank templates;
  for (std::size_t phase = 0U;
       phase < m3::offline::kSpectralShadowTemplatePhaseCount; ++phase) {
    auto& set = templates.by_phase[phase][kNote];
    set.valid_mask = 0x07U;
    for (std::size_t feature = 0U; feature < observed.size(); ++feature) {
      set.fingerprint[0U][feature] =
          feature % 3U == 0U ? observed[feature] : 0.0;
      set.fingerprint[1U][feature] =
          feature % 3U == 1U ? observed[feature] : 0.0;
      set.fingerprint[2U][feature] =
          feature % 3U == 2U ? observed[feature] : 0.0;
    }
  }
  std::vector<m3::offline::ReplayLabel> labels{
      {0U, kSamples, kNote, 0x01U, 1U, 0, false},
      {0U, kSamples, kNote, 0x02U, 1U, 0, false},
      {0U, kSamples, kNote, 0x04U, 1U, 0, false},
  };
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  config.sensitivity = 60U;
  config.response = 75U;
  m3::offline::ReplayError error{};
  m3::offline::ReplayResult baseline;
  m3::offline::ReplayResult shadow;
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, baseline, error));
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, shadow, error, &templates));
  M3_EXPECT_EQ(shadow.fingerprint, baseline.fingerprint);
  M3_EXPECT_EQ(shadow.matched_label_frames, baseline.matched_label_frames);
  M3_EXPECT_EQ(shadow.transition_count, baseline.transition_count);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  M3_EXPECT_EQ(shadow.label_results.size(), 3U);
  for (const auto& result : shadow.label_results) {
    M3_EXPECT_EQ(result.spectral_shadow_frames,
                 result.spectral_corridor_frames);
    M3_EXPECT_EQ(result.spectral_shadow_projected_frames,
                 result.labeled_frames);
    std::uint32_t classified = result.spectral_shadow_invalid_frames;
    for (const std::uint32_t frames :
         result.spectral_shadow_fitted_mask_frames) {
      classified += frames;
    }
    M3_EXPECT_EQ(classified, result.spectral_shadow_frames);
    M3_EXPECT_TRUE(result.spectral_shadow_fitted_mask_frames[0x07U] > 0U);
    std::uint32_t single_classified = result.spectral_single_invalid_frames;
    for (const std::uint32_t frames :
         result.spectral_single_fitted_mask_frames) {
      single_classified += frames;
    }
    M3_EXPECT_EQ(result.spectral_single_frames,
                 result.spectral_corridor_frames);
    M3_EXPECT_EQ(single_classified, result.spectral_single_frames);
    const std::uint32_t onset_single_winners = std::accumulate(
        result.spectral_single_onset_string_frames.begin(),
        result.spectral_single_onset_string_frames.end(), 0U);
    const std::uint32_t settled_single_winners = std::accumulate(
        result.spectral_single_settled_string_frames.begin(),
        result.spectral_single_settled_string_frames.end(), 0U);
    M3_EXPECT_EQ(onset_single_winners + settled_single_winners,
                 result.spectral_single_frames);
    for (std::size_t phase = 0U; phase < 2U; ++phase) {
      const std::uint32_t expected_phase_frames =
          phase == 0U ? result.spectral_onset_frames
                      : result.spectral_settled_frames;
      for (std::size_t string = 0U; string < 3U; ++string) {
        M3_EXPECT_EQ(
            result.spectral_single_phase_score_frames[phase][string],
            expected_phase_frames);
        M3_EXPECT_TRUE(
            std::isfinite(
                result.spectral_single_phase_score_error_sum[phase][string]));
        M3_EXPECT_TRUE(
            result.spectral_single_phase_gap_support_frames[phase]
                [m3::offline::kSpectralSingleGapThresholdCount - 1U][string] <=
            expected_phase_frames);
      }
      for (std::size_t string = 3U; string < m3::kMaxVoices; ++string) {
        M3_EXPECT_EQ(
            result.spectral_single_phase_score_frames[phase][string], 0U);
      }
    }
    std::uint32_t single_error_binned = 0U;
    for (const auto& outcome_bins :
         result.spectral_single_error_outcome_frames) {
      for (const std::uint32_t frames : outcome_bins) {
        single_error_binned += frames;
      }
    }
    M3_EXPECT_EQ(single_error_binned, result.spectral_single_frames);
    std::uint32_t single_selection_crossed = 0U;
    for (const auto& disposition :
         result.spectral_single_selection_disposition_frames) {
      for (const std::uint32_t frames : disposition) {
        single_selection_crossed += frames;
      }
    }
    M3_EXPECT_EQ(single_selection_crossed, result.spectral_single_frames);
    std::uint32_t group_selection_crossed = 0U;
    std::uint32_t group_selection_correct = 0U;
    for (const auto& disposition :
         result.spectral_single_group_selection_disposition_frames) {
      for (const std::uint32_t frames : disposition) {
        group_selection_crossed += frames;
      }
      group_selection_correct += disposition[1U];
    }
    M3_EXPECT_EQ(group_selection_crossed, result.spectral_single_frames);
    M3_EXPECT_EQ(group_selection_correct, result.spectral_single_frames);
    const std::uint32_t below_threshold_classified =
        result.spectral_single_selection_disposition_frames[1U][1U] +
        result.spectral_single_selection_disposition_frames[1U][2U];
    std::uint32_t below_threshold_error_binned = 0U;
    for (const auto& outcome_bins :
         result.spectral_single_below_threshold_error_outcome_frames) {
      for (const std::uint32_t frames : outcome_bins) {
        below_threshold_error_binned += frames;
      }
    }
    M3_EXPECT_EQ(below_threshold_error_binned,
                 below_threshold_classified);
    std::uint32_t group_correct_error_binned = 0U;
    for (const std::uint32_t frames :
         result.spectral_single_group_error_outcome_frames[0U]) {
      group_correct_error_binned += frames;
    }
    std::uint32_t group_other_error_binned = 0U;
    for (const std::uint32_t frames :
         result.spectral_single_group_error_outcome_frames[1U]) {
      group_other_error_binned += frames;
    }
    M3_EXPECT_EQ(group_correct_error_binned,
                 result.spectral_single_frames);
    M3_EXPECT_EQ(group_other_error_binned, 0U);
    M3_EXPECT_TRUE(result.spectral_onset_latch_qualified_votes[0U] > 0U);
    if (result.spectral_settled_frames == 0U) {
      M3_EXPECT_EQ(result.spectral_onset_latch_committed_mask[0U], 0U);
      M3_EXPECT_EQ(result.spectral_onset_latch_winner_votes[0U], 0U);
    } else {
      M3_EXPECT_EQ(result.spectral_onset_latch_committed_mask[0U], 0x07U);
      M3_EXPECT_EQ(result.spectral_onset_latch_winner_votes[0U],
                   result.spectral_onset_latch_qualified_votes[0U]);
    }
    M3_EXPECT_EQ(result.spectral_onset_latch_projected_frames[0U],
                 result.labeled_frames);
    M3_EXPECT_TRUE(
        result.spectral_onset_contraction_matched_frames[0U] <=
        result.labeled_frames);
    M3_EXPECT_TRUE(result.string_fret_onset_strength_max >= 0.0);
    M3_EXPECT_TRUE(result.string_fret_onset_strength_max <= 1.0);
    M3_EXPECT_TRUE(result.string_fret_onset_strength_first_250ms_max <=
                   result.string_fret_onset_strength_max);
    M3_EXPECT_TRUE(result.active_string_fret_onset_strength_max <=
                   result.string_fret_onset_strength_max);
    M3_EXPECT_TRUE(
        result.active_string_fret_onset_strength_first_250ms_max <=
        result.string_fret_onset_strength_first_250ms_max);
  }
  for (std::size_t policy = 0U;
       policy < m3::offline::kCandidateSpectralShadowPolicyCount; ++policy) {
    for (std::size_t gate = 0U;
         gate < m3::offline::kCandidateSpectralShadowGateCount; ++gate) {
      const std::size_t row =
          policy * m3::offline::kCandidateSpectralShadowGateCount + gate;
      const auto sum_predicted_strings = [](const auto& counts) {
        return std::accumulate(counts.begin(), counts.end(), std::uint64_t{0});
      };
      M3_EXPECT_EQ(
          sum_predicted_strings(
              shadow.candidate_spectral_shadow_target_correct_by_string_frames
                  [row]),
          shadow.candidate_spectral_shadow_target_correct_frames[policy]
                                                                  [gate]);
      M3_EXPECT_EQ(
          sum_predicted_strings(
              shadow
                  .candidate_spectral_shadow_target_wrong_string_by_string_frames
                      [row]),
          shadow.candidate_spectral_shadow_target_wrong_string_frames[policy]
                                                                       [gate]);
      M3_EXPECT_EQ(
          sum_predicted_strings(
              shadow.candidate_spectral_shadow_other_false_by_string_frames
                  [row]),
          shadow.candidate_spectral_shadow_other_false_frames[policy][gate]);
    }
  }

#endif
}

M3_TEST(offline_replay_shadow_diagnostics_never_reject_out_of_band_labels) {
  constexpr std::uint32_t kSampleRate = 22050U;
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  wave.mono_samples.assign(kSampleRate / 2U, 0.0);
  const std::vector<m3::offline::ReplayLabel> labels{
      {0U, wave.mono_samples.size(), 127U, 0U, 0U, 0, false},
  };
  m3::PersistentConfig config;
  m3::offline::ReplayResult result;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 64U, result, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
}

M3_TEST(offline_replay_candidate_population_separates_targets_from_harmonics) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint8_t kNote = 40U;
  constexpr std::size_t kSamples = kSampleRate;
  constexpr double kTwoPi = 6.28318530717958647692;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);

  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  wave.mono_samples.resize(kSamples);
  for (std::size_t sample = 0U; sample < kSamples; ++sample) {
    const double phase =
        kTwoPi * frequency * static_cast<double>(sample) / kSampleRate;
    wave.mono_samples[sample] =
        0.24 * std::sin(phase) + 0.13 * std::sin(2.0 * phase) +
        0.08 * std::sin(3.0 * phase);
  }
  const std::vector<m3::offline::ReplayLabel> labels{
      {0U, kSamples, kNote, 0x04U, 1U, 0, false},
  };
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  config.sensitivity = 60U;
  config.response = 75U;
  m3::StringCalibrationBank calibration;
  constexpr std::array<std::array<std::uint16_t,
                                  m3::kCalibrationHarmonicCount>,
                       3U>
      kProfiles{{
          {5000U, 21000U, 4000U, 1800U, 800U, 400U},
          {9000U, 5000U, 18000U, 2200U, 900U, 400U},
          {23000U, 6800U, 2600U, 900U, 300U, 100U},
  }};
  for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
    for (auto& point : calibration.points[string]) {
      point.harmonic_profile_q15 = kProfiles[string];
      point.confidence_q15 = 32767U;
      point.observation_count = 64U;
      point.quality = m3::CalibrationPointQuality::measured;
    }
    calibration.calibrated_string_mask = static_cast<std::uint8_t>(
        calibration.calibrated_string_mask | (1U << string));
  }
  m3::offline::ReplayResult result;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, &calibration, 512U, result, error));
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  M3_EXPECT_TRUE(result.candidate_population_labeled_snapshots > 0U);
  std::uint64_t target_dispositions = 0U;
  std::uint64_t other_dispositions = 0U;
  for (const std::uint64_t frames :
       result.candidate_population_disposition_frames[0U]) {
    target_dispositions += frames;
  }
  for (const std::uint64_t frames :
       result.candidate_population_disposition_frames[1U]) {
    other_dispositions += frames;
  }
  M3_EXPECT_TRUE(target_dispositions > 0U);
  M3_EXPECT_TRUE(other_dispositions > target_dispositions);
  M3_EXPECT_TRUE(
      result.candidate_population_disposition_frames[0U][4U] > 0U);
  M3_EXPECT_TRUE(
      result.candidate_population_disposition_frames[1U][1U] > 0U);
  std::uint64_t other_below_score_frames = 0U;
  for (const std::uint64_t frames :
       result.candidate_population_below_threshold_score_ratio_frames[1U]) {
    other_below_score_frames += frames;
  }
  M3_EXPECT_EQ(
      other_below_score_frames,
      result.candidate_population_disposition_frames[1U][1U]);
  std::uint64_t target_direct_frames = 0U;
  std::uint64_t target_pitch_band_frames = 0U;
  for (const auto& score_bins :
       result.candidate_population_below_threshold_direct_evidence_frames[0U]) {
    for (const std::uint64_t frames : score_bins) {
      target_direct_frames += frames;
    }
  }
  for (const auto& score_bins :
       result.candidate_population_below_threshold_pitch_band_peak_frames[0U]) {
    for (const std::uint64_t frames : score_bins) {
      target_pitch_band_frames += frames;
    }
  }
  M3_EXPECT_EQ(target_pitch_band_frames, target_direct_frames);
  std::uint64_t other_direct_frames = 0U;
  for (const auto& score_bins :
       result.candidate_population_below_threshold_direct_evidence_frames[1U]) {
    for (const std::uint64_t frames : score_bins) {
      other_direct_frames += frames;
    }
  }
  std::uint64_t calibrated_joint_frames = 0U;
  for (const auto& row :
       result.candidate_population_below_threshold_calibration_joint_frames) {
    for (const std::uint64_t frames : row) {
      calibrated_joint_frames += frames;
    }
  }
  M3_EXPECT_TRUE(calibrated_joint_frames > 0U);
  M3_EXPECT_TRUE(calibrated_joint_frames <=
                 target_direct_frames + other_direct_frames);
  for (const auto& policy :
       result.candidate_population_band_calibration_shadow_frames) {
    std::uint64_t band_calibration_shadow_frames = 0U;
    for (const std::uint64_t frames : policy) {
      band_calibration_shadow_frames += frames;
    }
    M3_EXPECT_TRUE(band_calibration_shadow_frames <=
                   calibrated_joint_frames);
  }
  for (const auto& policy :
       result.candidate_population_octave_shadow_calibration_frames) {
    std::uint64_t octave_shadow_frames = 0U;
    for (const std::uint64_t frames : policy) {
      octave_shadow_frames += frames;
    }
    M3_EXPECT_TRUE(
        octave_shadow_frames <=
        result.candidate_population_disposition_frames[0U][2U] +
            result.candidate_population_disposition_frames[1U][2U]);
  }
  for (const auto& policy :
       result.candidate_population_octave_shadow_isolated_context_frames) {
    std::uint64_t isolated_context_frames = 0U;
    for (const std::uint64_t frames : policy) {
      isolated_context_frames += frames;
    }
    M3_EXPECT_TRUE(
        isolated_context_frames <=
        result.candidate_population_disposition_frames[0U][2U] +
            result.candidate_population_disposition_frames[1U][2U]);
  }
  std::uint64_t unique_playable_direct_frames = 0U;
  for (const std::uint64_t frames :
       result.candidate_population_unique_playable_direct_frames) {
    unique_playable_direct_frames += frames;
  }
  M3_EXPECT_TRUE(unique_playable_direct_frames <= calibrated_joint_frames);
  std::uint64_t target_nonquiet_score_frames = 0U;
  for (const std::uint64_t frames :
       result.candidate_population_score_threshold_ratio_frames[0U]) {
    target_nonquiet_score_frames += frames;
  }
  M3_EXPECT_EQ(
      target_nonquiet_score_frames,
      target_dispositions -
          result.candidate_population_disposition_frames[0U][0U]);
#endif
}

M3_TEST(offline_replay_projection_unions_overlapping_same_note_labels) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kSamples = kSampleRate;
  constexpr double kTwoPi = 6.28318530717958647692;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);

  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  wave.mono_samples.resize(kSamples);
  for (std::size_t sample = 0U; sample < kSamples; ++sample) {
    wave.mono_samples[sample] =
        0.30 * std::sin(kTwoPi * frequency * static_cast<double>(sample) /
                        static_cast<double>(kSampleRate));
  }

  std::vector<m3::offline::ReplayLabel> labels;
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    labels.push_back(m3::offline::ReplayLabel{
        string, kSamples - string, kNote,
        static_cast<std::uint8_t>(1U << string), 1U, 0, false});
  }
  labels.push_back(m3::offline::ReplayLabel{
      m3::kMaxVoices, kSamples - m3::kMaxVoices, kNote, 0U, 1U, 0, false});

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  config.sensitivity = 60U;
  config.response = 75U;

  m3::offline::ReplayResult result;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, result, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS) && \
    defined(M3_SPECTRAL_TIER_DIAGNOSTICS)
  std::uint64_t observed_note_frames = 0U;
  for (const std::uint32_t frames :
       result.label_results.front().matching_note_lane_mask_frames) {
    observed_note_frames += frames;
  }
  M3_EXPECT_TRUE(observed_note_frames > 0U);
  for (std::size_t threshold = 0U;
       threshold < m3::offline::kSpectralShadowMarginThresholdCount;
       ++threshold) {
    std::uint64_t changed_frames = 0U;
    std::uint64_t projected_matched = 0U;
    std::uint64_t projected_wrong_strings = 0U;
    for (const auto& label : result.label_results) {
      changed_frames +=
          label.spectral_tier_completion_changed_frames[threshold];
      projected_matched +=
          label.spectral_tier_completion_matched_frames[threshold];
      projected_wrong_strings +=
          label.spectral_tier_completion_wrong_string_voices[threshold];
    }
    M3_EXPECT_EQ(changed_frames, 0U);
    M3_EXPECT_EQ(projected_matched, result.matched_label_frames);
    M3_EXPECT_EQ(projected_wrong_strings,
                 result.false_wrong_string_voices);
  }
#endif
}

M3_TEST(offline_replay_scores_overlapping_same_note_labels_as_one_physical_group) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint8_t kNote = 40U;
  constexpr std::size_t kSamples = kSampleRate;
  constexpr double kTwoPi = 6.28318530717958647692;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);

  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  wave.mono_samples.resize(kSamples);
  for (std::size_t sample = 0U; sample < kSamples; ++sample) {
    wave.mono_samples[sample] =
        0.25 * std::sin(kTwoPi * frequency * static_cast<double>(sample) /
                        static_cast<double>(kSampleRate));
  }
  const std::vector<m3::offline::ReplayLabel> labels{
      {0U, kSamples, kNote, 0x01U, 1U, 0, false},
      {0U, kSamples, kNote, 0x02U, 1U, 0, false},
  };
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 5U;
  config.max_fret = 24U;
  config.sensitivity = 60U;
  config.response = 75U;

  m3::offline::ReplayResult result;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, result, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  const std::vector<m3::offline::ReplayLabel> reversed_labels{
      labels.rbegin(), labels.rend()};
  m3::offline::ReplayResult reversed;
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, reversed_labels, config, nullptr, 512U, reversed, error));
  M3_EXPECT_EQ(error, m3::offline::ReplayError::none);
  M3_EXPECT_EQ(result.physical_group_labeled_frames, result.snapshot_frames);
  M3_EXPECT_EQ(result.physical_group_expected_member_frames[2U],
               result.snapshot_frames);
  std::uint64_t classified = 0U;
  for (const std::uint64_t frames : result.physical_group_lane_outcome_frames) {
    classified += frames;
  }
  M3_EXPECT_EQ(classified, result.physical_group_labeled_frames);
  M3_EXPECT_TRUE(result.labeled_frames > result.physical_group_labeled_frames);
  M3_EXPECT_EQ(result.physical_group_labeled_frames,
               reversed.physical_group_labeled_frames);
  M3_EXPECT_EQ(result.physical_group_lane_outcome_frames,
               reversed.physical_group_lane_outcome_frames);
  M3_EXPECT_EQ(result.physical_group_fine_lane_outcome_frames,
               reversed.physical_group_fine_lane_outcome_frames);
  M3_EXPECT_EQ(result.physical_group_committed_lane_outcome_frames,
               reversed.physical_group_committed_lane_outcome_frames);
  M3_EXPECT_EQ(result.physical_group_selection_lane_outcome_frames,
               reversed.physical_group_selection_lane_outcome_frames);
  std::uint64_t causal_frames = 0U;
  std::uint64_t causal_runs = 0U;
  for (std::size_t cell = 0U;
       cell < m3::offline::kPhysicalGroupCausalCellCount; ++cell) {
    causal_frames += result.physical_group_causal_frames[cell];
    causal_runs += result.physical_group_causal_runs[cell];
    M3_EXPECT_TRUE(
        result.physical_group_causal_longest_run_frames[cell] <=
        result.physical_group_causal_frames[cell]);
  }
  M3_EXPECT_EQ(causal_frames, result.physical_group_labeled_frames);
  M3_EXPECT_TRUE(causal_runs > 0U);
  std::uint64_t pending_causal_frames = 0U;
  for (const std::uint64_t frames :
       result.physical_group_pending_causal_frames) {
    pending_causal_frames += frames;
  }
  M3_EXPECT_EQ(pending_causal_frames,
               result.physical_group_labeled_frames);
  M3_EXPECT_EQ(result.physical_group_causal_frames,
               reversed.physical_group_causal_frames);
  M3_EXPECT_EQ(result.physical_group_pending_causal_frames,
               reversed.physical_group_pending_causal_frames);
  M3_EXPECT_EQ(result.physical_group_member_pending_causal_frames,
               reversed.physical_group_member_pending_causal_frames);
  M3_EXPECT_EQ(result.physical_group_member_exact_exit_frames,
               reversed.physical_group_member_exact_exit_frames);
  M3_EXPECT_EQ(result.physical_group_causal_runs,
               reversed.physical_group_causal_runs);
  M3_EXPECT_EQ(result.physical_group_causal_longest_run_frames,
               reversed.physical_group_causal_longest_run_frames);
  for (std::size_t members = 0U; members <= m3::kMaxVoices; ++members) {
    std::uint64_t member_causal_frames = 0U;
    for (std::size_t cell = 0U;
         cell < m3::offline::kPhysicalGroupCausalCellCount; ++cell) {
      member_causal_frames +=
          result.physical_group_member_causal_frames[members][cell];
      M3_EXPECT_TRUE(
          result.physical_group_member_causal_longest_run_frames
                    [members][cell] <=
          result.physical_group_member_causal_frames[members][cell]);
    }
    M3_EXPECT_EQ(member_causal_frames,
                 result.physical_group_expected_member_frames[members]);
    std::uint64_t member_pending_causal_frames = 0U;
    for (const std::uint64_t frames :
         result.physical_group_member_pending_causal_frames[members]) {
      member_pending_causal_frames += frames;
    }
    M3_EXPECT_EQ(member_pending_causal_frames,
                 result.physical_group_expected_member_frames[members]);
    std::uint64_t member_exact_exits = 0U;
    for (const std::uint64_t frames :
         result.physical_group_member_exact_exit_frames[members]) {
      member_exact_exits += frames;
    }
    M3_EXPECT_TRUE(
        member_exact_exits <=
        result.physical_group_member_lane_outcome_frames[members]
                                                        [static_cast<std::size_t>(
                                                            m3::offline::
                                                                ReplayTargetLaneOutcome::
                                                                    exact)]);
  }
  M3_EXPECT_EQ(result.physical_group_member_causal_frames,
               reversed.physical_group_member_causal_frames);
  std::uint64_t unresolved_causal_frames = 0U;
  for (std::size_t cell = 0U;
       cell < m3::offline::kPhysicalGroupFineUnresolvedCellCount; ++cell) {
    unresolved_causal_frames +=
        result.physical_group_fine_unresolved_frames[cell];
    M3_EXPECT_TRUE(
        result.physical_group_fine_unresolved_longest_run_frames[cell] <=
        result.physical_group_fine_unresolved_frames[cell]);
  }
  M3_EXPECT_EQ(unresolved_causal_frames,
               result.physical_group_labeled_frames);
  M3_EXPECT_EQ(result.physical_group_fine_unresolved_frames,
               reversed.physical_group_fine_unresolved_frames);
  M3_EXPECT_EQ(result.physical_group_fine_unresolved_runs,
               reversed.physical_group_fine_unresolved_runs);
  M3_EXPECT_EQ(result.physical_group_fine_unresolved_longest_run_frames,
               reversed.physical_group_fine_unresolved_longest_run_frames);
  for (std::size_t members = 0U; members <= m3::kMaxVoices; ++members) {
    std::uint64_t member_unresolved_frames = 0U;
    for (std::size_t cell = 0U;
         cell < m3::offline::kPhysicalGroupFineUnresolvedCellCount; ++cell) {
      member_unresolved_frames +=
          result.physical_group_member_fine_unresolved_frames[members][cell];
    }
    M3_EXPECT_EQ(member_unresolved_frames,
                 result.physical_group_expected_member_frames[members]);
  }
  M3_EXPECT_EQ(result.physical_group_member_fine_unresolved_frames,
               reversed.physical_group_member_fine_unresolved_frames);
  M3_EXPECT_EQ(result.physical_group_member_fine_unresolved_runs,
               reversed.physical_group_member_fine_unresolved_runs);
  M3_EXPECT_EQ(
      result.physical_group_member_fine_unresolved_longest_run_frames,
      reversed.physical_group_member_fine_unresolved_longest_run_frames);
  std::uint64_t fine_classifier_frames = 0U;
  for (const std::uint64_t frames :
       result.physical_group_fine_classifier_frames) {
    fine_classifier_frames += frames;
  }
  M3_EXPECT_EQ(fine_classifier_frames,
               result.physical_group_labeled_frames);
  M3_EXPECT_EQ(result.physical_group_fine_classifier_frames,
               reversed.physical_group_fine_classifier_frames);
  M3_EXPECT_EQ(result.physical_group_member_fine_classifier_frames,
               reversed.physical_group_member_fine_classifier_frames);
  for (std::size_t members = 0U; members <= m3::kMaxVoices; ++members) {
    std::uint64_t member_fine_classifier_frames = 0U;
    for (const std::uint64_t frames :
         result.physical_group_member_fine_classifier_frames[members]) {
      member_fine_classifier_frames += frames;
    }
    M3_EXPECT_EQ(member_fine_classifier_frames,
                 result.physical_group_expected_member_frames[members]);
  }
  M3_EXPECT_EQ(result.physical_group_member_causal_runs,
               reversed.physical_group_member_causal_runs);
  M3_EXPECT_EQ(result.physical_group_member_causal_longest_run_frames,
               reversed.physical_group_member_causal_longest_run_frames);
  M3_EXPECT_EQ(result.physical_group_expected_observed_mask_frames,
               reversed.physical_group_expected_observed_mask_frames);
  M3_EXPECT_EQ(result.physical_group_expected_fine_mask_frames,
               reversed.physical_group_expected_fine_mask_frames);
  M3_EXPECT_EQ(result.physical_group_expected_committed_mask_frames,
               reversed.physical_group_expected_committed_mask_frames);
#endif
}

M3_TEST(offline_replay_combines_independent_spectral_head_votes) {
  const std::array<std::uint8_t, m3::kSpectralTierCount + 1U> heads{
      0U, 2U, 1U, 2U, static_cast<std::uint8_t>(m3::kMaxVoices)};
  M3_EXPECT_EQ(m3::offline::spectral_head_vote_mask(heads), 0x07U);
}

M3_TEST(offline_replay_spectral_head_plurality_abstains_on_exact_ties) {
  const std::array<std::uint8_t, m3::kSpectralTierCount + 1U> heads{
      2U, 2U, 5U, 5U, 7U};
  const std::array<double, m3::kSpectralTierCount + 1U> margins{
      0.4, 0.3, 0.2, 0.1, 0.01};
  const auto winner =
      m3::offline::spectral_head_plurality(heads, margins, 0.05);
  M3_EXPECT_EQ(winner.string, 2U);
  M3_EXPECT_EQ(winner.votes, 2U);
  M3_EXPECT_NEAR(winner.margin_sum, 0.7, 1.0e-12);

  const std::array<double, m3::kSpectralTierCount + 1U> tied_margins{
      0.2, 0.1, 0.2, 0.1, 0.01};
  const auto tied =
      m3::offline::spectral_head_plurality(heads, tied_margins, 0.05);
  M3_EXPECT_EQ(tied.string, m3::kUnassignedTunerString);

  const auto filtered =
      m3::offline::spectral_head_plurality(heads, margins, 0.35);
  M3_EXPECT_EQ(filtered.string, 2U);
  M3_EXPECT_EQ(filtered.votes, 1U);
}

M3_TEST(offline_replay_applies_the_same_input_trim_as_the_live_processor) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint8_t kNote = 40U;
  const double frequency = m3::midi_to_frequency(kNote, 440.0);
  m3::offline::WaveData original;
  original.sample_rate = kSampleRate;
  original.source_channels = 1U;
  original.mono_samples.resize(kSampleRate);
  for (std::uint32_t index = 0U; index < kSampleRate; ++index) {
    original.mono_samples[index] =
        0.02 * std::sin(6.28318530717958647692 * frequency *
                        static_cast<double>(index) /
                        static_cast<double>(kSampleRate));
  }
  constexpr double kGain = 0.5;
  m3::offline::WaveData scaled = original;
  for (double& sample : scaled.mono_samples) {
    sample *= kGain;
  }
  const std::string label_text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\n"
      "0\t48000\t40\t0\n";
  std::vector<m3::offline::ReplayLabel> labels;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      label_text.data(), label_text.size(), original.mono_samples.size(),
      labels, error));

  m3::PersistentConfig trimmed_config;
  trimmed_config.profile_mode = m3::ProfileMode::general;
  trimmed_config.lowest_note = 39U;
  trimmed_config.highest_note = 41U;
  trimmed_config.max_polyphony = 1U;
  trimmed_config.sensitivity = 70U;
  trimmed_config.response = 81U;
  trimmed_config.input_trim_db = 20.0 * std::log10(kGain);
  m3::PersistentConfig unity_config = trimmed_config;
  unity_config.input_trim_db = 0.0;

  m3::offline::ReplayResult trimmed;
  m3::offline::ReplayResult pre_scaled;
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      original, labels, trimmed_config, nullptr, 512U, trimmed, error));
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      scaled, labels, unity_config, nullptr, 512U, pre_scaled, error));
  M3_EXPECT_EQ(trimmed.fingerprint, pre_scaled.fingerprint);
  M3_EXPECT_EQ(trimmed.matched_label_frames,
               pre_scaled.matched_label_frames);
  M3_EXPECT_EQ(trimmed.transition_count, pre_scaled.transition_count);
  M3_EXPECT_EQ(trimmed.false_positive_voices,
               pre_scaled.false_positive_voices);
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

M3_TEST(offline_labeled_calibration_profiles_detuned_partial_peaks) {
  constexpr std::uint32_t kSampleRate = 48000U;
  constexpr std::uint32_t kSamplesPerNote = 12000U;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::array<double, 3U> kAmplitudes{0.22, 0.12, 0.07};
  constexpr std::array<double, 3U> kPartialCents{0.0, 16.0, 27.0};
  m3::offline::WaveData wave;
  wave.sample_rate = kSampleRate;
  wave.source_channels = 1U;
  std::vector<m3::offline::ReplayLabel> labels;
  const auto append_fret = [&](std::size_t fret) {
    const std::uint64_t start = wave.mono_samples.size();
    const std::uint8_t note =
        static_cast<std::uint8_t>(m3::kM3OpenNotes[0U] + fret);
    const double fundamental = m3::midi_to_frequency(note, 440.0);
    for (std::uint32_t sample = 0U; sample < kSamplesPerNote; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      double value = 0.0;
      for (std::size_t partial = 0U; partial < kAmplitudes.size();
           ++partial) {
        const double frequency =
            fundamental * static_cast<double>(partial + 1U) *
            std::exp2(kPartialCents[partial] / 1200.0);
        value += kAmplitudes[partial] *
                 std::sin(kTwoPi * frequency * time +
                          0.19 * static_cast<double>(partial));
      }
      wave.mono_samples.push_back(value);
    }
    labels.push_back(m3::offline::ReplayLabel{
        start, wave.mono_samples.size(), note, 1U});
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
  m3::StringCalibrationBank bank;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::derive_labeled_string_calibration(
      wave, labels, config, 0U, bank, error));
  const auto* point = bank.point(0U, 12U);
  M3_EXPECT_TRUE(point != nullptr);
  if (point != nullptr) {
    M3_EXPECT_TRUE(point->harmonic_profile_q15[1U] > 5000U);
    M3_EXPECT_TRUE(point->harmonic_profile_q15[2U] > 1500U);
    M3_EXPECT_TRUE((point->partial_detuning_valid_mask & 0x06U) == 0x06U);
    const double fundamental_cents =
        static_cast<double>(point->cents_offset_q8) / 256.0;
    M3_EXPECT_NEAR(fundamental_cents +
                       static_cast<double>(point->partial_detuning_q8[1U]) /
                           256.0,
                   kPartialCents[1U], 1.0);
    M3_EXPECT_NEAR(fundamental_cents +
                       static_cast<double>(point->partial_detuning_q8[2U]) /
                           256.0,
                   kPartialCents[2U], 1.0);
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
