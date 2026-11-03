#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

#include "m3/generated_note_ledger.hpp"
#include "m3/pitch_math.hpp"
#include "m3/polyphonic_pitch_detector.hpp"
#include "replay.hpp"
#include "residual_recovery.hpp"
#include "test_support.hpp"
#include "unison_spectral_shadow.hpp"

namespace {

M3_TEST(offline_residual_recovery_requires_consecutive_fixed_audio_evidence) {
  using namespace m3::offline;
  ResidualRecoveryScreen screen;
  ResidualRecoveryEvidence evidence;
  evidence.note = 60U;
  evidence.available_mask = 3U;
  evidence.base_count = 2U;
  evidence.valid = evidence.fixed_context = true;
  evidence.gain = 0.2;
  evidence.independent_energy = 0.0001;
  evidence.fundamental_overlap = 0.98;
  evidence.lane_costs[1U] = 32.0;
  const auto observe = [&](std::uint32_t tick) {
    screen.begin_tick(); evidence.tick = tick; screen.observe(evidence);
    return screen.proposal();
  };
  const auto allocations = m3::test::allocation_count();
  M3_EXPECT_FALSE(observe(16U).valid);
  M3_EXPECT_FALSE(observe(32U).valid);
  M3_EXPECT_TRUE(observe(48U).valid);
  M3_EXPECT_EQ(screen.proposal().string, 0U);
  M3_EXPECT_FALSE(observe(48U).valid); // replaying a row cannot build persistence
  M3_EXPECT_FALSE(observe(80U).valid); // skipped observation starts over
  M3_EXPECT_FALSE(observe(96U).valid);
  M3_EXPECT_TRUE(observe(112U).valid);
  evidence.lane_costs[0U] = 64.0;
  M3_EXPECT_FALSE(observe(128U).valid); // changed winner starts over
  M3_EXPECT_FALSE(observe(144U).valid);
  M3_EXPECT_TRUE(observe(160U).valid);
  M3_EXPECT_EQ(screen.proposal().string, 1U);
  evidence.available_mask = 1U;
  M3_EXPECT_FALSE(observe(176U).valid); // no invented margin for a sole lane
  evidence.available_mask = 3U;
  M3_EXPECT_FALSE(observe(192U).valid);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations);
}

M3_TEST(offline_residual_recovery_rejects_ambiguous_invalid_or_shared_evidence) {
  using namespace m3::offline;
  for (unsigned scenario = 0U; scenario < 12U; ++scenario) {
    ResidualRecoveryScreen screen;
    ResidualRecoveryEvidence evidence;
    evidence.note = 60U;
    evidence.available_mask = 3U;
    evidence.base_count = 2U;
    evidence.valid = evidence.fixed_context = true;
    evidence.gain = 0.3;
    evidence.independent_energy = 0.01;
    evidence.fundamental_overlap = 0.5;
    evidence.lane_costs[1U] = 64.0;
    switch (scenario) {
      case 0U: evidence.valid = false; break;
      case 1U: evidence.fixed_context = false; break;
      case 2U: evidence.base_count = 1U; break;
      case 3U: evidence.shared_fundamental = true; break;
      case 4U: evidence.gain = 0.199; break;
      case 5U: evidence.independent_energy = 0.00009; break;
      case 6U: evidence.fundamental_overlap = 0.99; break;
      case 7U: evidence.lane_costs[1U] = 31.99; break;
      case 8U: evidence.gain = std::numeric_limits<double>::quiet_NaN(); break;
      case 9U: evidence.lane_costs[1U] = std::numeric_limits<double>::infinity(); break;
      case 10U: evidence.available_mask = 0U; break;
      case 11U: evidence.note = 128U; break;
    }
    for (const auto tick : {16U, 32U, 48U, 64U}) {
      screen.begin_tick(); evidence.tick = tick; screen.observe(evidence);
      M3_EXPECT_FALSE(screen.proposal().valid);
    }
  }
}

M3_TEST(offline_residual_recovery_renewal_requires_fresh_independent_audio) {
  using namespace m3::offline;
  ResidualRecoveryEvidence good;
  good.tick = 16U;
  good.note = 60U;
  good.available_mask = 8U;
  good.base_count = 2U;
  good.valid = good.fixed_context = true;
  good.gain = 0.2;
  good.independent_energy = 0.0001;
  good.fundamental_overlap = 0.98;
  // Renewal may retain an established owner without inventing a lane-cost
  // margin. Its independent audio evidence is still mandatory each time.
  good.lane_costs.fill(std::numeric_limits<double>::quiet_NaN());
  ResidualRecoveryScreen screen;
  const auto allocations = m3::test::allocation_count();
  screen.observe(good, 3U);
  M3_EXPECT_TRUE(screen.proposal().valid);
  M3_EXPECT_EQ(screen.proposal().string, 3U);
  screen.begin_tick();
  screen.observe(good, 3U);
  M3_EXPECT_FALSE(screen.proposal().valid);
  good.tick = 32U;
  screen.observe(good, 3U);
  M3_EXPECT_TRUE(screen.proposal().valid);
  for (unsigned scenario = 0U; scenario < 12U; ++scenario) {
    auto bad = good;
    bad.tick = 48U;
    switch (scenario) {
      case 0U: bad.valid = false; break;
      case 1U: bad.fixed_context = false; break;
      case 2U: bad.base_count = 1U; break;
      case 3U: bad.shared_fundamental = true; break;
      case 4U: bad.gain = 0.199; break;
      case 5U: bad.independent_energy = 0.00009; break;
      case 6U: bad.fundamental_overlap = 0.99; break;
      case 7U: bad.available_mask = 4U; break;
      case 8U: bad.gain = std::numeric_limits<double>::quiet_NaN(); break;
      case 9U: bad.independent_energy = std::numeric_limits<double>::infinity(); break;
      case 10U: bad.fundamental_overlap = std::numeric_limits<double>::quiet_NaN(); break;
      case 11U: bad.tick = 49U; break;
    }
    screen.begin_tick();
    screen.observe(bad, 3U);
    M3_EXPECT_FALSE(screen.proposal().valid);
  }
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations);
}

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

M3_TEST(offline_adjacent_envelope_coherence_separates_shared_and_opposed_motion) {
  m3::offline::AdjacentEnvelopeCoherenceState shared;
  m3::offline::AdjacentEnvelopeCoherenceState opposed;
  for (std::size_t frame = 0U; frame < 120U; ++frame) {
    const double value = std::sin(static_cast<double>(frame) * 0.17);
    m3::offline::observe_adjacent_envelope_coherence(shared, value, value);
    m3::offline::observe_adjacent_envelope_coherence(opposed, value, -value);
  }
  M3_EXPECT_TRUE(m3::offline::adjacent_envelope_coherence(shared) > 0.99);
  M3_EXPECT_TRUE(m3::offline::adjacent_envelope_coherence(opposed) < -0.99);
  M3_EXPECT_EQ(m3::offline::adjacent_envelope_coherence_bin(shared), 21U);
  M3_EXPECT_EQ(m3::offline::adjacent_envelope_coherence_bin(opposed), 1U);
  M3_EXPECT_EQ(m3::offline::adjacent_spectral_error_gap_bin(-1.0), 1U);
  M3_EXPECT_EQ(m3::offline::adjacent_spectral_error_gap_bin(0.0), 21U);
  M3_EXPECT_EQ(m3::offline::adjacent_spectral_error_gap_bin(1.0), 41U);
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

M3_TEST(offline_candidate_trace_preserves_output_and_partitioning) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(24000U);
  for (std::size_t sample = 0U; sample < 14400U; ++sample) {
    const double phase = 6.28318530717958647692 *
        m3::midi_to_frequency(40U, 440.0) *
        static_cast<double>(sample) / wave.sample_rate;
    wave.mono_samples[sample] =
        0.2 * std::sin(phase) + 0.04 * std::sin(2.0 * phase + 0.3);
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 39U;
  config.highest_note = 41U;
  config.max_polyphony = 1U;
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, {}, config, nullptr, 512U, *baseline, error));
  std::string reference;
  for (const std::size_t partition : {32U, 512U, 1024U}) {
    const auto close_stream = [](std::FILE* file) { std::fclose(file); };
    std::unique_ptr<std::FILE, decltype(close_stream)> stream(
        std::tmpfile(), close_stream);
    M3_EXPECT_TRUE(stream != nullptr);
    if (!stream) return;
    m3::offline::CandidateDecisionTrace trace;
    trace.stream = stream.get();
    trace.start_seconds = 0.12;
    trace.end_seconds = 0.50;
    const auto run = [&] {
      return m3::offline::run_detector_replay(
          wave, {}, config, nullptr, partition, *observed, error,
          nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
          false, false, false, -1.0, false, false, false, nullptr,
          false, false, false, &trace);
    };
    M3_EXPECT_TRUE(run());
    M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    M3_EXPECT_TRUE(trace.frames > 0U);
    M3_EXPECT_TRUE(trace.frames < trace.kMaximumFrames);
    M3_EXPECT_FALSE(trace.truncated);
    M3_EXPECT_FALSE(trace.failed);
    std::rewind(stream.get());
    std::string captured;
    std::array<char, 4096U> line{};
    std::size_t rows = 0U;
    std::size_t observed_column = 0U;
    std::size_t evaluated_column = 0U;
    bool saw_ownership = false;
    bool saw_quiet = false;
    bool saw_released_quiet = false;
    while (std::fgets(line.data(), line.size(), stream.get()) != nullptr) {
      captured += line.data();
      std::vector<std::string> fields;
      std::istringstream record(line.data());
      std::string field;
      while (std::getline(record, field, '\t')) fields.push_back(field);
      if (rows++ == 0U) {
        for (std::size_t column = 0U; column < fields.size(); ++column) {
          if (fields[column] == "ownership_observed") observed_column = column;
          if (fields[column] == "fine_group_evaluated") evaluated_column = column;
        }
        M3_EXPECT_TRUE(observed_column > 0U);
        M3_EXPECT_TRUE(evaluated_column > 0U);
        continue;
      }
      M3_EXPECT_TRUE(fields.size() > evaluated_column);
      if (fields.size() <= evaluated_column) return;
      saw_ownership = saw_ownership || fields[observed_column] == "1";
      if (fields[3U] != "0") {
        saw_quiet = true;
        // Active owners can coast during quiet until ordinary release, but
        // the empty selected set must not evaluate a new fine group.
        M3_EXPECT_EQ(fields[evaluated_column], std::string("0"));
        saw_released_quiet = saw_released_quiet ||
            fields[observed_column] == "0";
      }
      unsigned long long sample = 0U;
      unsigned tick = 0U;
      unsigned note = 0U;
      M3_EXPECT_EQ(std::sscanf(line.data(), "%llu\t%u\t%u",
                              &sample, &tick, &note), 3);
      M3_EXPECT_TRUE(sample >= 5760U && sample < 24000U);
      M3_EXPECT_TRUE(tick > 0U);
      M3_EXPECT_EQ(note, 40U);
    }
    M3_EXPECT_EQ(rows, trace.frames + 1U);
    M3_EXPECT_TRUE(saw_ownership);
    M3_EXPECT_TRUE(saw_quiet);
    M3_EXPECT_TRUE(saw_released_quiet);
    M3_EXPECT_TRUE(captured.find("fine_update_scheduled\treset_serial\treset_tick\t"
        "reset_prior_count\treset_prior_last_tick\treset_reason\tfine_disposition\t"
        "fit_residual_improvement\tfit_min_member_ratio\tpending_beat_min\t"
        "pending_seconds\tfit_unique_improvement\t"
        "fine_group_disposition\townership_observed\tfine_group_evaluated\t"
        "fine_group_mask\tfine_group_other_owned\tfine_group_overlap\t"
        "fine_group_allocated\tfine_group_extra_capacity\tfine_group_owners\t"
        "fine_group_owner_counts\n") !=
        std::string::npos);
    if (reference.empty()) reference = captured;
    M3_EXPECT_EQ(captured, reference);
    trace.end_seconds = trace.start_seconds;
    M3_EXPECT_FALSE(run());
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
#endif
}

M3_TEST(offline_outcome_trace_reconciles_errors_and_preserves_partitioning) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(43200U);
  for (std::size_t sample = 0U; sample < 33600U; ++sample) {
    const double phase = 6.28318530717958647692 *
        m3::midi_to_frequency(40U, 440.0) *
        static_cast<double>(sample) / wave.sample_rate;
    wave.mono_samples[sample] =
        0.2 * std::sin(phase) + 0.04 * std::sin(2.0 * phase + 0.3);
  }
  const std::string label_text =
      "start_sample\tend_sample\tmidi_note\tstring_mask\n"
      "0\t9600\t41\t0\n"
      "9600\t19200\t40\t128\n"
      "19200\t28800\t40\t0\n";
  std::vector<m3::offline::ReplayLabel> labels;
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::parse_replay_labels(
      label_text.data(), label_text.size(), wave.mono_samples.size(), labels, error));
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 39U;
  config.highest_note = 41U;
  config.max_polyphony = 1U;
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, *baseline, error));
  std::string reference;
  const auto split = [](const std::string& text, char separator) {
    std::vector<std::string> parts;
    std::size_t start = 0U;
    while (true) {
      const auto end = text.find(separator, start);
      parts.push_back(text.substr(start, end - start));
      if (end == std::string::npos) break;
      start = end + 1U;
    }
    return parts;
  };
  for (const std::size_t partition : {32U, 512U, 1024U}) {
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
    M3_EXPECT_TRUE(stream != nullptr);
    if (!stream) return;
    m3::offline::CandidateOutcomeTrace trace;
    trace.stream = stream.get();
    const auto run = [&] {
      return m3::offline::run_detector_replay(
          wave, labels, config, nullptr, partition, *observed, error,
          nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
          false, false, false, -1.0, false, false, false, nullptr,
          false, false, false, nullptr, &trace);
    };
    M3_EXPECT_TRUE(run());
    M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    M3_EXPECT_EQ(trace.frames, observed->snapshot_frames);
    M3_EXPECT_FALSE(trace.failed);
    M3_EXPECT_FALSE(trace.truncated);
    std::rewind(stream.get());
    std::string captured;
    std::array<char, 8192U> chunk{};
    std::size_t count = 0U;
    while ((count = std::fread(chunk.data(), 1U, chunk.size(), stream.get())) != 0U)
      captured.append(chunk.data(), count);
    std::istringstream lines(captured);
    std::string line;
    std::getline(lines, line);
    M3_EXPECT_EQ(line, "# m3_candidate_outcome_v2");
    std::getline(lines, line);
    std::size_t rows = 0U, labeled = 0U, matched = 0U;
    std::array<std::size_t, 4U> outcomes{};
    bool observed_candidate = false;
    while (std::getline(lines, line)) {
      const auto fields = split(line, '\t');
      M3_EXPECT_EQ(fields.size(), 8U);
      if (fields.size() != 8U) continue;
      ++rows;
      if (!fields[4].empty()) labeled += split(fields[4], ',').size();
      if (!fields[5].empty()) matched += split(fields[5], ',').size();
      if (!fields[6].empty()) {
        for (const auto& voice : split(fields[6], ',')) {
          const auto values = split(voice, ':');
          M3_EXPECT_EQ(values.size(), 8U);
          if (values.size() != 8U) continue;
          const auto outcome = static_cast<std::size_t>(std::stoul(values[3]));
          M3_EXPECT_TRUE(outcome < outcomes.size());
          if (outcome < outcomes.size()) ++outcomes[outcome];
        }
      }
      if (!fields[7].empty()) {
        for (const auto& candidate : split(fields[7], ',')) {
          const auto values = split(candidate, ':');
          M3_EXPECT_EQ(values.size(), 42U);
          if (!values.empty() && values[0] == "40") observed_candidate = true;
        }
      }
    }
    M3_EXPECT_TRUE(observed_candidate);
    for (const auto outcome : outcomes) M3_EXPECT_TRUE(outcome > 0U);
    M3_EXPECT_EQ(rows, observed->snapshot_frames);
    M3_EXPECT_EQ(labeled, observed->labeled_frames);
    M3_EXPECT_EQ(matched, observed->matched_label_frames);
    M3_EXPECT_EQ(outcomes[1], observed->false_wrong_note_voices);
    M3_EXPECT_EQ(outcomes[2], observed->false_wrong_string_voices);
    M3_EXPECT_EQ(outcomes[3], observed->false_gap_voices);
    M3_EXPECT_EQ(outcomes[1] + outcomes[2] + outcomes[3], observed->false_positive_voices);
    if (reference.empty()) reference = captured;
    M3_EXPECT_EQ(captured, reference);
    trace.stream = nullptr;
    M3_EXPECT_FALSE(run());
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
#endif
}

M3_TEST(offline_residual_recovery_is_partition_and_label_independent_and_releases) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(96000U);
  for (std::size_t sample = 0U; sample < 76800U; ++sample) {
    for (const auto note : std::array<std::uint8_t, 3U>{40U, 44U, 51U}) {
      const double angle = 6.28318530717958647692 *
          m3::midi_to_frequency(note, 440.0) * static_cast<double>(sample) / wave.sample_rate;
      const double gain = note == 51U ? 0.06 : 0.2;
      wave.mono_samples[sample] += gain *
          (std::sin(angle) + 0.3 * std::sin(2.0 * angle + 0.4));
    }
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_polyphony = 5U;
  config.sensitivity = 60U;
  config.response = 75U;
  config.midi_routing = m3::MidiRouting::per_voice;
  std::vector<m3::offline::ReplayLabel> labels(1U);
  labels[0].midi_note = 51U;
  labels[0].end_sample = 76800U;
  labels[0].string_mask = 16U;
  auto reference = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  m3::offline::ReplayError error{};
  struct DeliveredMidi {
    std::array<int, m3::kMaxVoices> active{};
    std::size_t ons{}, offs{};
    bool invalid{};
    DeliveredMidi() { active.fill(-1); }
    static bool push(void* context, const m3::VoiceTransition& event,
                     std::uint8_t channel) noexcept {
      auto& self = *static_cast<DeliveredMidi*>(context);
      if (event.voice_id >= self.active.size() || channel != event.voice_id + 1U) {
        self.invalid = true;
        return false;
      }
      auto& current = self.active[event.voice_id];
      if (event.kind == m3::TransitionKind::note_on) {
        self.invalid |= current != -1 || event.velocity == 0U;
        current = event.note;
        ++self.ons;
      } else {
        self.invalid |= current != event.note;
        current = -1;
        ++self.offs;
      }
      return true;
    }
    m3::NoteEventSink sink() noexcept { return {this, &push}; }
  };
  // Pass the real event stream through the same bounded delivery ledger used
  // by the plugin, including its off-before-on sorting within each host block.
  const auto check_delivery = [&](const std::string& text, std::size_t partition,
                                  bool expect_blocked, bool panic) {
    struct TimedEvent { std::size_t sample{}; m3::VoiceTransition event{}; };
    std::vector<TimedEvent> parsed;
    std::istringstream rows(text);
    std::string header, kind;
    M3_EXPECT_TRUE(static_cast<bool>(std::getline(rows, header)));
    M3_EXPECT_TRUE(static_cast<bool>(std::getline(rows, header)));
    std::size_t sample = 0U, previous = 0U;
    unsigned note = 0U, velocity = 0U, voice = 0U, sequence = 0U;
    while (rows >> sample >> kind >> note >> velocity >> voice >> sequence) {
      M3_EXPECT_TRUE(sample >= previous && sample < 91200U);
      M3_EXPECT_TRUE(voice < m3::kMaxVoices && note < 128U);
      M3_EXPECT_TRUE(kind == "on" || kind == "off");
      previous = sample;
      parsed.push_back({sample, {0U,
          kind == "on" ? m3::TransitionKind::note_on : m3::TransitionKind::note_off,
          static_cast<std::uint8_t>(note), static_cast<std::uint8_t>(velocity),
          sequence, static_cast<std::uint8_t>(voice)}});
    }
    M3_EXPECT_FALSE(parsed.empty());
    m3::GeneratedNoteLedger delivery;
    M3_EXPECT_TRUE(delivery.activate(static_cast<std::uint32_t>(partition)));
    DeliveredMidi capture;
    const auto allocations = m3::test::allocation_count();
    std::size_t next = 0U;
    bool blocked = false;
    for (std::size_t start = 0U; start < wave.mono_samples.size(); start += partition) {
      delivery.begin_block();
      while (next < parsed.size() && parsed[next].sample < start + partition) {
        auto event = parsed[next].event;
        event.sample_offset = static_cast<std::uint32_t>(parsed[next].sample - start);
        M3_EXPECT_TRUE(delivery.queue_transition(event, static_cast<std::uint32_t>(partition)));
        ++next;
      }
      const auto result = delivery.deliver(static_cast<std::uint32_t>(partition),
          capture.sink(), start < 76800U ? 0.5 : 0.0, true, true,
          m3::MidiRouting::per_voice, 1U);
      blocked |= result.output_blocked;
      if (blocked || (panic && capture.ons > 0U)) break;
    }
    M3_EXPECT_EQ(m3::test::allocation_count(), allocations);
    M3_EXPECT_EQ(blocked, expect_blocked);
    if (!panic && !expect_blocked) {
      M3_EXPECT_EQ(next, parsed.size());
      M3_EXPECT_EQ(capture.ons + capture.offs, parsed.size());
      M3_EXPECT_EQ(capture.ons, capture.offs);
      for (const auto active_note : capture.active) M3_EXPECT_EQ(active_note, -1);
    }
    // Panic also releases notes from a real, delivered chord attack. Do not
    // manufacture detector activity or confuse this with positive recovery.
    delivery.request_release_all();
    M3_EXPECT_TRUE(delivery.retry_pending_releases(capture.sink()));
    M3_EXPECT_FALSE(delivery.release_pending());
    M3_EXPECT_TRUE(capture.ons > 0U);
    M3_EXPECT_EQ(capture.ons, capture.offs);
    M3_EXPECT_FALSE(capture.invalid);
    for (const auto active_note : capture.active) M3_EXPECT_EQ(active_note, -1);
  };
  for (const bool joint_ownership : {false, true}) {
    for (const bool continuity : {false, true}) {
      std::string reference_events;
      for (const std::size_t partition : {32U, 512U, 1024U}) {
        if (!joint_ownership && (continuity || partition != 32U)) continue;
        std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
        std::unique_ptr<std::FILE, int (*)(std::FILE*)> events(std::tmpfile(), &std::fclose);
        M3_EXPECT_TRUE(stream != nullptr && events != nullptr);
        if (!stream || !events) return;
        m3::offline::MidiEventTrace event_trace;
        event_trace.stream = events.get();
        m3::offline::CandidateOutcomeTrace trace;
        trace.stream = stream.get();
        const auto run = [&](m3::offline::CandidateOutcomeTrace* output_trace,
                             m3::offline::MidiEventTrace* output_events,
                             m3::offline::JointOwnershipAblation ablation =
                                 m3::offline::JointOwnershipAblation::none) {
          return m3::offline::run_detector_replay(
              wave, labels, config, nullptr, partition, *observed, error,
              nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
              false, false, false, -1.0, false, false, false, nullptr,
              false, false, false, nullptr, output_trace, false, nullptr, nullptr,
              false, false, false, false, false, false, false, false, false, true,
              output_events, continuity, joint_ownership, ablation);
        };
        if (!joint_ownership) {
          M3_EXPECT_FALSE(run(nullptr, nullptr,
              m3::offline::JointOwnershipAblation::solver_only));
          M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
          M3_EXPECT_FALSE(run(nullptr, nullptr,
              m3::offline::JointOwnershipAblation::midi_guard_only));
          M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
          M3_EXPECT_FALSE(run(nullptr, nullptr,
              static_cast<m3::offline::JointOwnershipAblation>(255U)));
          M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
        }
        M3_EXPECT_TRUE(run(&trace, &event_trace));
        M3_EXPECT_FALSE(event_trace.failed);
        M3_EXPECT_FALSE(event_trace.truncated);
        M3_EXPECT_EQ(event_trace.rows, observed->transition_count);
        std::rewind(events.get());
        std::string event_text;
        std::array<char, 256U> event_line{};
        while (std::fgets(event_line.data(), event_line.size(), events.get()) != nullptr)
          event_text += event_line.data();
        if (partition == 32U) reference_events = event_text;
        M3_EXPECT_EQ(event_text, reference_events);
        // This synthetic fixture exercises the public MIDI seam and silence. It
        // does not establish successful recovery from recorded audio.
        check_delivery(event_text, partition, !joint_ownership, false);
        if (!joint_ownership) continue;
        check_delivery(event_text, partition, false, true);
        M3_EXPECT_FALSE(trace.failed);
        M3_EXPECT_FALSE(trace.truncated);
        if (partition == 32U) *reference = *observed;
        M3_EXPECT_EQ(observed->fingerprint, reference->fingerprint);
        M3_EXPECT_EQ(observed->residual_recovery_proposals, reference->residual_recovery_proposals);
        M3_EXPECT_EQ(observed->residual_recovery_selected_ticks,
                     reference->residual_recovery_selected_ticks);
        M3_EXPECT_EQ(observed->residual_recovery_note_ons, reference->residual_recovery_note_ons);
        // Annotation changes affect scoring only, never policy or MIDI decisions.
        labels[0].midi_note = 72U;
        labels[0].string_mask = 128U;
        M3_EXPECT_TRUE(run(nullptr, nullptr));
        M3_EXPECT_EQ(observed->fingerprint, reference->fingerprint);
        M3_EXPECT_EQ(observed->residual_recovery_proposals, reference->residual_recovery_proposals);
        M3_EXPECT_EQ(observed->residual_recovery_selected_ticks,
                     reference->residual_recovery_selected_ticks);
        M3_EXPECT_EQ(observed->residual_recovery_note_ons, reference->residual_recovery_note_ons);
        labels[0].midi_note = 51U;
        labels[0].string_mask = 16U;
        std::rewind(stream.get());
        std::array<char, 32768U> line{};
        std::size_t silent_frames = 0U;
        M3_EXPECT_TRUE(std::fgets(line.data(), line.size(), stream.get()) != nullptr);
        M3_EXPECT_TRUE(std::fgets(line.data(), line.size(), stream.get()) != nullptr);
        while (std::fgets(line.data(), line.size(), stream.get()) != nullptr) {
          std::istringstream row(line.data());
          std::array<std::string, 7U> columns;
          for (auto& column : columns) M3_EXPECT_TRUE(static_cast<bool>(std::getline(row, column, '\t')));
          if (std::stoull(columns[0]) < 91200U) continue;
          ++silent_frames;
          M3_EXPECT_TRUE(columns[6].empty());
        }
        M3_EXPECT_TRUE(silent_frames > 0U);
      }
    }
  }
#endif
}

M3_TEST(offline_residual_admission_trace_preserves_audio_and_partitioning) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(96000U);
  for (std::size_t sample = 0U; sample < 76800U; ++sample) {
    // Two open notes make the weaker fretted note compete with the ordinary
    // fret penalty. Unlike an adjacent unresolved peak, it reaches the DP.
    for (const auto note : std::array<std::uint8_t, 3U>{40U, 44U, 51U}) {
      const double angle = 6.28318530717958647692 *
          m3::midi_to_frequency(note, 440.0) * static_cast<double>(sample) / wave.sample_rate;
      const double gain = note == 51U ? 0.06 : 0.2;
      wave.mono_samples[sample] += gain *
          (std::sin(angle) + 0.3 * std::sin(2.0 * angle + 0.4));
    }
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_polyphony = 5U;
  config.sensitivity = 60U;
  config.response = 75U;
  std::vector<m3::offline::ReplayLabel> labels(1U);
  labels[0].midi_note = 51U;
  labels[0].end_sample = 76800U;
  labels[0].string_mask = 16U;
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, *baseline, error));
  const auto fields = [](const std::string& line, char delimiter) {
    std::vector<std::string> result;
    std::istringstream input(line);
    std::string value;
    while (std::getline(input, value, delimiter)) result.push_back(value);
    if (!result.empty() && !result.back().empty() && result.back().back() == '\n')
      result.back().pop_back();
    return result;
  };
  std::string reference, assignment_reference;
  for (const std::size_t partition : {32U, 512U, 1024U}) {
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> assignment_stream(
        std::tmpfile(), &std::fclose);
    M3_EXPECT_TRUE(stream != nullptr && assignment_stream != nullptr);
    if (!stream || !assignment_stream) return;
    m3::offline::ResidualAdmissionTrace trace;
    trace.stream = stream.get();
    m3::offline::StringAssignmentTrace assignment_trace;
    assignment_trace.stream = assignment_stream.get();
    double correlation_seconds = -1.0;
    const auto run = [&] {
      return m3::offline::run_detector_replay(
          wave, labels, config, nullptr, partition, *observed, error,
          nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
          false, false, false, correlation_seconds, false, false, false, nullptr,
          false, false, false, nullptr, nullptr, false, &trace, &assignment_trace);
    };
    M3_EXPECT_TRUE(run());
    M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    M3_EXPECT_TRUE(trace.rows > 0U);
    M3_EXPECT_EQ(trace.rows, trace.candidates);
    M3_EXPECT_FALSE(trace.failed);
    M3_EXPECT_FALSE(trace.truncated);
    M3_EXPECT_FALSE(assignment_trace.failed);
    M3_EXPECT_FALSE(assignment_trace.truncated);
    std::rewind(assignment_stream.get());
    std::array<char, 8192U> assignment_line{};
    std::string assignment_captured;
    std::map<std::array<std::uint64_t, 3U>, std::array<double, 8U>> fixed_costs;
    std::size_t assignment_rows = 0U, settled_shadow_rows = 0U;
    while (std::fgets(assignment_line.data(), assignment_line.size(),
                     assignment_stream.get()) != nullptr) {
      assignment_captured += assignment_line.data();
      const auto columns = fields(assignment_line.data(), '\t');
      M3_EXPECT_EQ(columns.size(), 79U);
      if (columns.size() != 79U) return;
      if (assignment_rows++ == 0U) {
        M3_EXPECT_EQ(columns[69], "fixed_context");
        M3_EXPECT_EQ(columns[70], "phase_shadow");
        continue;
      }
      if (columns[69] != "1") {
        M3_EXPECT_EQ(columns[70], "0");
        continue;
      }
      M3_EXPECT_EQ(columns[70], "1");
      if (columns[37] == "1") {
        ++settled_shadow_rows;
        M3_EXPECT_EQ(columns[36], "1");
        M3_EXPECT_TRUE(std::stoul(columns[35]) >= 120U);
        M3_EXPECT_TRUE(std::abs(std::stod(columns[32])) <= 50.0);
      }
      M3_EXPECT_EQ(columns[3], "0"); // never claim an actual assignment
      M3_EXPECT_EQ(columns[4], "0");
      M3_EXPECT_EQ(columns[6], "255");
      M3_EXPECT_EQ(columns[16], "255");
      // Final ownership is the existing candidate state, which may retain an
      // earlier assignment after release. Only the new DP decision is absent.
      M3_EXPECT_TRUE(std::stoul(columns[5]) >= 2U);
      const auto totals = fields(columns[29], ',');
      const auto terms = fields(columns[30], ',');
      M3_EXPECT_EQ(totals.size(), 8U);
      M3_EXPECT_EQ(terms.size(), 8U);
      if (totals.size() != 8U || terms.size() != 8U) return;
      std::array<double, 8U> costs{};
      for (std::size_t string = 0U; string < 8U; ++string) {
        const auto components = fields(terms[string], ':');
        M3_EXPECT_EQ(components.size(), 7U);
        double sum = 0.0;
        for (const auto& component : components) {
          M3_EXPECT_TRUE(std::isfinite(std::stod(component)));
          sum += std::stod(component);
        }
        costs[string] = std::stod(totals[string]);
        M3_EXPECT_NEAR(sum, costs[string], 1.0e-10);
      }
      const std::array<std::uint64_t, 3U> key{
          std::stoull(columns[0]), std::stoull(columns[1]), std::stoull(columns[2])};
      M3_EXPECT_TRUE(fixed_costs.emplace(key, costs).second);
    }
    M3_EXPECT_EQ(assignment_rows, assignment_trace.rows + 1U);
    M3_EXPECT_TRUE(settled_shadow_rows > 0U);
    M3_EXPECT_FALSE(fixed_costs.empty());
    if (assignment_reference.empty()) assignment_reference = assignment_captured;
    M3_EXPECT_EQ(assignment_captured, assignment_reference);
    std::rewind(stream.get());
    std::array<char, 4096U> line{};
    std::string captured;
    std::size_t rows = 0U;
    std::size_t native_cost_rows = 0U;
    while (std::fgets(line.data(), line.size(), stream.get()) != nullptr) {
      captured += line.data();
      if (rows++ == 0U) continue;
      unsigned long long sample = 0U;
      unsigned tick = 0U, note = 0U, base_count = 0U, used_mask = 0U, free_mask = 0U;
      M3_EXPECT_EQ(std::sscanf(line.data(), "%llu\t%u\t%u\t%u\t%u\t%u",
          &sample, &tick, &note, &base_count, &used_mask, &free_mask), 6);
      M3_EXPECT_EQ(tick % trace.kTickDecimation, 0U);
      M3_EXPECT_TRUE(sample >= 38399U);
      M3_EXPECT_TRUE(sample < 86400U); // settled silence cannot propose notes
      M3_EXPECT_TRUE(base_count > 0U && base_count < config.max_polyphony);
      M3_EXPECT_TRUE(free_mask != 0U);
      M3_EXPECT_EQ(used_mask & free_mask, 0U);
      std::istringstream residual_fields(line.data());
      std::vector<std::string> values;
      std::string field;
      while (std::getline(residual_fields, field, '\t')) values.push_back(field);
      M3_EXPECT_EQ(values.size(), 36U);
      if (values.size() != 36U) continue;
      const auto lane_observed = std::stoul(values[25U]);
      const auto lane_count = std::stoul(values[26U]);
      const auto lane_mask = std::stoul(values[27U]);
      M3_EXPECT_EQ(lane_mask & ~free_mask, 0U);
      if (lane_observed != 0U) {
        ++native_cost_rows;
        M3_EXPECT_TRUE(lane_count >= 2U && lane_count <= 8U);
        const auto joined = fixed_costs.find({sample, tick, note});
        M3_EXPECT_TRUE(joined != fixed_costs.end());
        if (joined == fixed_costs.end()) return;
        for (std::size_t string = 0U; string < 8U; ++string)
          if ((lane_mask & (1U << string)) != 0U)
            M3_EXPECT_EQ(std::stod(values[28U + string]), joined->second[string]);
      } else {
        M3_EXPECT_EQ(lane_count, 0U);
        M3_EXPECT_EQ(lane_mask, 0U);
      }
      for (std::size_t string = 0U; string < 8U; ++string) {
        const double cost = std::stod(values[28U + string]);
        M3_EXPECT_TRUE(std::isfinite(cost));
        if ((lane_mask & (1U << string)) == 0U) M3_EXPECT_EQ(cost, 0.0);
      }
    }
    M3_EXPECT_EQ(rows, trace.rows + 1U);
    M3_EXPECT_TRUE(native_cost_rows > 0U);
    if (reference.empty()) reference = captured;
    M3_EXPECT_EQ(captured, reference);
    if (partition == 512U) {
      // Labels may change the score columns, never which models are fitted or
      // any measured evidence. A fresh stream also checks repeatable reset.
      std::unique_ptr<std::FILE, int (*)(std::FILE*)> unlabeled_stream(
          std::tmpfile(), &std::fclose);
      std::unique_ptr<std::FILE, int (*)(std::FILE*)> unlabeled_assignment(
          std::tmpfile(), &std::fclose);
      M3_EXPECT_TRUE(unlabeled_stream != nullptr && unlabeled_assignment != nullptr);
      if (!unlabeled_stream || !unlabeled_assignment) return;
      trace.stream = unlabeled_stream.get();
      assignment_trace.stream = unlabeled_assignment.get();
      labels.clear();
      M3_EXPECT_TRUE(run());
      M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
      std::rewind(unlabeled_stream.get());
      std::istringstream expected(captured);
      std::string expected_line;
      while (std::fgets(line.data(), line.size(), unlabeled_stream.get()) != nullptr) {
        M3_EXPECT_TRUE(static_cast<bool>(std::getline(expected, expected_line)));
        std::istringstream labeled_fields(expected_line);
        std::istringstream unlabeled_fields(line.data());
        std::string labeled_field, unlabeled_field;
        std::size_t field = 0U;
        while (std::getline(labeled_fields, labeled_field, '\t')) {
          M3_EXPECT_TRUE(static_cast<bool>(
              std::getline(unlabeled_fields, unlabeled_field, '\t')));
          if (field < 6U || field > 8U) {
            if (!unlabeled_field.empty() && unlabeled_field.back() == '\n')
              unlabeled_field.pop_back();
            M3_EXPECT_EQ(unlabeled_field, labeled_field);
          }
          ++field;
        }
      }
      M3_EXPECT_FALSE(static_cast<bool>(std::getline(expected, expected_line)));
      std::rewind(unlabeled_assignment.get());
      std::istringstream expected_assignment(assignment_captured);
      while (std::fgets(assignment_line.data(), assignment_line.size(),
                       unlabeled_assignment.get()) != nullptr) {
        M3_EXPECT_TRUE(static_cast<bool>(std::getline(expected_assignment, expected_line)));
        const auto before = fields(expected_line, '\t');
        const auto after = fields(assignment_line.data(), '\t');
        M3_EXPECT_EQ(before.size(), after.size());
        for (std::size_t column = 0U; column < before.size() && column < after.size(); ++column)
          if (column < 24U || column > 26U) M3_EXPECT_EQ(before[column], after[column]);
      }
      M3_EXPECT_FALSE(static_cast<bool>(std::getline(expected_assignment, expected_line)));
      labels.resize(1U);
      labels[0].midi_note = 51U;
      labels[0].end_sample = 76800U;
      labels[0].string_mask = 16U;
      trace.stream = stream.get();
      assignment_trace.stream = assignment_stream.get();
    }
    correlation_seconds = 0.06;
    M3_EXPECT_FALSE(run());
    correlation_seconds = -1.0;
    config.profile_mode = m3::ProfileMode::general;
    M3_EXPECT_FALSE(run());
    config.profile_mode = m3::ProfileMode::m3;
    trace.stream = nullptr;
    M3_EXPECT_FALSE(run());
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
#endif
}

M3_TEST(offline_partial_motion_getter_measures_baseband_without_mutation) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  constexpr double rate = 48000.0, two_pi = 6.28318530717958647692;
  constexpr std::uint8_t note = 52U;
  const double center = m3::midi_to_frequency(note, 440.0);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  auto detector = std::make_unique<m3::PolyphonicPitchDetector>();
  std::array<double, 6U> frequencies{};
  std::array<std::complex<double>, 6U> measured{}, previous{};
  double energy{}, decay{};
  M3_EXPECT_FALSE(detector->demodulated_harmonic_tracks_for_diagnostics(
      note, frequencies, measured, energy, decay));
  for (std::size_t h = 0U; h < 6U; ++h) {
    M3_EXPECT_TRUE(detector->configure(rate, config));
    double phase_sum = 0.0;
    std::size_t intervals = 0U;
    bool have_previous = false;
    const double harmonic = static_cast<double>(h + 1U);
    for (std::size_t sample = 0U; sample < 48000U; ++sample) {
      (void)detector->process_sample(0.2 * std::sin(
          two_pi * harmonic * (center + 1.25) * static_cast<double>(sample) / rate));
      if (sample < 24000U || sample % 64U != 0U) continue;
      const auto allocations = m3::test::allocation_count();
      M3_EXPECT_TRUE(detector->demodulated_harmonic_tracks_for_diagnostics(
          note, frequencies, measured, energy, decay));
      std::array<std::complex<double>, 6U> again{};
      M3_EXPECT_TRUE(detector->demodulated_harmonic_tracks_for_diagnostics(
          note, frequencies, again, energy, decay));
      M3_EXPECT_EQ(m3::test::allocation_count(), allocations);
      M3_EXPECT_EQ(measured, again);
      M3_EXPECT_NEAR(frequencies[h], center * harmonic, 1.0e-8);
      M3_EXPECT_TRUE(energy > 0.0 && decay > 0.0 && decay < 1.0);
      if (have_previous) {
        phase_sum += std::arg(measured[h] * std::conj(previous[h]));
        ++intervals;
      }
      previous = measured;
      have_previous = true;
    }
    M3_EXPECT_TRUE(intervals > 300U);
    const double seconds = static_cast<double>(intervals) * 64.0 / rate;
    M3_EXPECT_NEAR(phase_sum / (two_pi * seconds * harmonic), 1.25, 0.04);
  }
  M3_EXPECT_FALSE(detector->demodulated_harmonic_tracks_for_diagnostics(
      0U, frequencies, measured, energy, decay));
  M3_EXPECT_EQ(frequencies, (std::array<double, 6U>{}));
  M3_EXPECT_EQ(measured, (std::array<std::complex<double>, 6U>{}));
  // The production bank deliberately uses fewer bands for higher pitches.
  // Disabled bands must stay unavailable rather than becoming measurements.
  for (const std::uint8_t upper_note : std::array<std::uint8_t, 2U>{69U, 76U}) {
    M3_EXPECT_TRUE(detector->configure(rate, config));
    M3_EXPECT_TRUE(detector->demodulated_harmonic_tracks_for_diagnostics(
        upper_note, frequencies, measured, energy, decay));
    const std::size_t enabled_bands = upper_note == 69U ? 4U : 3U;
    for (std::size_t h = 0U; h < 6U; ++h) {
      const double expected = h < enabled_bands
          ? m3::midi_to_frequency(upper_note, 440.0) * static_cast<double>(h + 1U)
          : 0.0;
      M3_EXPECT_NEAR(frequencies[h], expected, 1.0e-8);
      M3_EXPECT_EQ(measured[h], std::complex<double>{});
    }
  }
#endif
}

M3_TEST(offline_partial_motion_trace_preserves_output_clock_and_labels) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(38400U);
  for (std::size_t sample = 4800U; sample < 28800U; ++sample) {
    const double angle = 6.28318530717958647692 *
        m3::midi_to_frequency(56U, 440.0) * static_cast<double>(sample) / wave.sample_rate;
    wave.mono_samples[sample] = 0.2 * (std::sin(angle) + 0.3 * std::sin(2.0 * angle));
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_polyphony = 5U;
  config.sensitivity = 60U;
  config.response = 75U;
  std::vector<m3::offline::ReplayLabel> labels(1U);
  labels[0].midi_note = 56U;
  labels[0].end_sample = 28800U;
  labels[0].string_mask = 64U;
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, *baseline, error));
  const auto read = [](std::FILE* stream) {
    std::rewind(stream);
    std::array<char, 4096U> buffer{};
    std::string output;
    while (std::fgets(buffer.data(), buffer.size(), stream) != nullptr)
      output += buffer.data();
    return output;
  };
  std::string reference;
  for (const std::size_t block : {32U, 512U, 1024U}) {
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
    M3_EXPECT_TRUE(stream != nullptr);
    if (!stream) return;
    m3::offline::PartialMotionTrace trace;
    trace.stream = stream.get();
    trace.midi_note = 56;
    trace.end_seconds = 0.8;
    const auto run = [&] {
      return m3::offline::run_detector_replay(
          wave, labels, config, nullptr, block, *observed, error,
          nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
          false, false, false, -1.0, false, false, false, nullptr,
          false, false, false, nullptr, nullptr, false, nullptr, nullptr,
          false, false, false, false, false, false, false, false, false,
          false, nullptr, false, false, m3::offline::JointOwnershipAblation::none, &trace);
    };
    M3_EXPECT_TRUE(run());
    M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    M3_EXPECT_FALSE(trace.failed);
    M3_EXPECT_FALSE(trace.truncated);
    M3_EXPECT_TRUE(trace.frames > 100U);
    const auto captured = read(stream.get());
    M3_EXPECT_TRUE(captured.find("\"tracks\":\"measured_demodulated_mixture\"") != std::string::npos);
    M3_EXPECT_TRUE(captured.find("\"harmonics\":6,\"strings\":8") != std::string::npos);
    M3_EXPECT_TRUE(captured.find("\"active\":0") != std::string::npos);
    M3_EXPECT_EQ(static_cast<std::size_t>(std::count(captured.begin(), captured.end(), '\n')),
                 trace.frames + 1U);
    if (reference.empty()) reference = captured;
    M3_EXPECT_EQ(captured, reference);
    if (block == 512U) {
      std::unique_ptr<std::FILE, int (*)(std::FILE*)> unlabeled(std::tmpfile(), &std::fclose);
      M3_EXPECT_TRUE(unlabeled != nullptr);
      if (!unlabeled) return;
      trace.stream = unlabeled.get();
      labels.clear();
      M3_EXPECT_TRUE(run());
      M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
      M3_EXPECT_EQ(read(unlabeled.get()), captured);
      trace.frame_limit = 2U;
      M3_EXPECT_TRUE(run());
      M3_EXPECT_EQ(trace.frames, 2U);
      M3_EXPECT_TRUE(trace.truncated);
      M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    }
    trace.stream = nullptr;
    M3_EXPECT_FALSE(run());
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
#endif
}

M3_TEST(offline_assignment_trace_preserves_output_and_records_winner_costs) {
#if defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(115200U);
  for (std::size_t sample = 0U; sample < 96000U; ++sample) {
    for (const auto note : std::array<std::uint8_t, 2U>{56U, 60U}) {
      if (note == 60U && sample < 48000U) continue;
      const double angle = 6.28318530717958647692 *
          m3::midi_to_frequency(note, 440.0) * static_cast<double>(sample) / wave.sample_rate;
      wave.mono_samples[sample] += 0.15 *
          (std::sin(angle) + 0.3 * std::sin(2.0 * angle + 0.4));
    }
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_polyphony = 5U;
  config.sensitivity = 60U;
  config.response = 75U;
  m3::StringCalibrationBank calibration;
  calibration.calibrated_string_mask = 255U;
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    for (auto& point : calibration.points[string]) {
      point.harmonic_profile_q15 = {24000U, 7000U, 900U, 400U, 200U, 100U};
      point.harmonic_profile_q15[1U] =
          static_cast<std::uint16_t>(3000U + string * 1200U);
      point.partial_detuning_valid_mask = 0x02U;
      point.partial_detuning_q8[1U] = static_cast<std::int16_t>(string * 256U);
      point.confidence_q15 = 32767U;
      point.observation_count = 64U;
      point.quality = m3::CalibrationPointQuality::measured;
    }
  }
  std::vector<m3::offline::ReplayLabel> labels(1U);
  labels[0].midi_note = 56U;
  labels[0].end_sample = 96000U;
  labels[0].string_mask = 64U;
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  auto observed = std::make_unique<m3::offline::ReplayResult>();
  m3::offline::ReplayError error{};
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, &calibration, 512U, *baseline, error));
  const auto fields = [](const std::string& line, char delimiter) {
    std::vector<std::string> result;
    std::istringstream input(line);
    std::string value;
    while (std::getline(input, value, delimiter)) result.push_back(value);
    return result;
  };
  std::string reference;
  for (const std::size_t partition : {32U, 512U, 1024U}) {
    std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
    M3_EXPECT_TRUE(stream != nullptr);
    if (!stream) return;
    m3::offline::StringAssignmentTrace trace;
    trace.stream = stream.get();
    const auto run = [&] {
      return m3::offline::run_detector_replay(
          wave, labels, config, &calibration, partition, *observed, error,
          nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
          false, false, false, -1.0, false, false, false, nullptr,
          false, false, false, nullptr, nullptr, false, nullptr, &trace);
    };
    M3_EXPECT_TRUE(run());
    M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
    M3_EXPECT_TRUE(trace.rows > 0U);
    M3_EXPECT_FALSE(trace.failed);
    M3_EXPECT_FALSE(trace.truncated);
    std::rewind(stream.get());
    std::array<char, 8192U> line{};
    std::string captured;
    std::size_t rows = 0U, solitary = 0U, joint = 0U, posterior_rows = 0U;
    std::size_t detuning_rows = 0U, detuning_nonzero_rows = 0U;
    std::size_t weighted_detuning_rows = 0U;
    while (std::fgets(line.data(), line.size(), stream.get()) != nullptr) {
      captured += line.data();
      if (rows++ == 0U) continue;
      const auto columns = fields(line.data(), '\t');
      M3_EXPECT_EQ(columns.size(), 79U);
      if (columns.size() != 79U) return;
      M3_EXPECT_EQ(std::stoul(columns[69]), 0U);
      M3_EXPECT_EQ(std::stoul(columns[70]), 0U);
      for (std::size_t column = 74U; column < 77U; ++column)
        M3_EXPECT_EQ(fields(columns[column], ',').size(), 8U);
      const auto detuning_mask = std::stoul(columns[77]);
      const auto detuning = fields(columns[78], ',');
      M3_EXPECT_EQ(detuning.size(), 8U);
      M3_EXPECT_EQ(detuning_mask & ~std::stoul(columns[11]), 0U);
      bool nonzero_detuning = false;
      double detuning_sum = 0.0;
      for (std::size_t lane = 0U; lane < detuning.size(); ++lane) {
        const double contribution = std::stod(detuning[lane]);
        M3_EXPECT_TRUE(std::isfinite(contribution));
        if ((detuning_mask & (1U << lane)) == 0U)
          M3_EXPECT_EQ(contribution, 0.0);
        nonzero_detuning |= contribution != 0.0;
        detuning_sum += contribution;
      }
      M3_EXPECT_NEAR(detuning_sum, 0.0, 1.0e-10);
      // One-cent reference spacing makes the unsaturated quadratic's second
      // difference -2/9: weight 2 and comparison scale 3 cents. Centering and
      // the unknown observed offset cancel, so this checks sign and weight.
      bool correct_curvature = false;
      for (std::size_t lane = 0U; lane + 2U < detuning.size(); ++lane) {
        if ((detuning_mask & (7U << lane)) != (7U << lane)) continue;
        const double curvature = std::stod(detuning[lane + 2U]) -
            2.0 * std::stod(detuning[lane + 1U]) + std::stod(detuning[lane]);
        correct_curvature |= std::abs(curvature + 2.0 / 9.0) < 1.0e-10;
      }
      weighted_detuning_rows += correct_curvature ? 1U : 0U;
      detuning_rows += detuning_mask != 0U ? 1U : 0U;
      detuning_nonzero_rows += nonzero_detuning ? 1U : 0U;
      if (columns[71] == "1") {
        ++posterior_rows;
        M3_EXPECT_EQ(columns[72], "1");
        const double onset = std::stod(columns[73]);
        M3_EXPECT_TRUE(onset >= 0.0 && onset <= 1.0);
        const auto likelihood = fields(columns[74], ',');
        const auto prior = fields(columns[75], ',');
        const auto posterior = fields(columns[76], ',');
        const auto mask = std::stoul(columns[11]);
        double before = 0.0, after = 0.0;
        for (std::size_t lane = 0U; lane < 8U; ++lane) {
          M3_EXPECT_TRUE(std::isfinite(std::stod(likelihood[lane])));
          const double p = std::stod(posterior[lane]);
          M3_EXPECT_TRUE(p >= 0.0 && p <= 1.0);
          if ((mask & (1U << lane)) == 0U) M3_EXPECT_EQ(p, 0.0);
          before += std::stod(prior[lane]);
          after += p;
        }
        M3_EXPECT_TRUE(before == 0.0 || std::abs(before - 1.0) < 1.0e-10);
        M3_EXPECT_NEAR(after, 1.0, 1.0e-10);
      } else {
        M3_EXPECT_EQ(columns[72], "0");
        M3_EXPECT_EQ(detuning_mask, 0U);
      }
      M3_EXPECT_EQ(fields(columns[40], ',').size(), 8U);
      M3_EXPECT_EQ(fields(columns[59], ',').size(), 8U);
      M3_EXPECT_EQ(fields(columns[60], ',').size(), 6U);
      M3_EXPECT_EQ(fields(columns[61], ',').size(), 8U);
      for (std::size_t column = 66U; column < 69U; ++column)
        M3_EXPECT_EQ(fields(columns[column], ':').size(), 12U);
      if (columns[37] == "1") {
        M3_EXPECT_EQ(columns[36], "1");
        M3_EXPECT_TRUE(std::stoul(columns[35]) >= 120U);
        M3_EXPECT_TRUE(std::abs(std::stod(columns[32])) <= 50.0);
      }
      M3_EXPECT_EQ(std::stoul(columns[1]) % trace.kTickDecimation, 0U);
      if (columns[4] != "1") continue;
      const auto playable = std::stoul(columns[11]);
      const auto reserved = std::stoul(columns[12]) | std::stoul(columns[13]);
      const auto winner = std::stoul(columns[16]);
      M3_EXPECT_TRUE(winner < 8U);
      if (winner >= 8U) return;
      M3_EXPECT_TRUE((playable & (1U << winner)) != 0U);
      M3_EXPECT_EQ(reserved & (1U << winner), 0U);
      const auto totals = fields(columns[29], ',');
      const auto terms = fields(columns[30], ',');
      M3_EXPECT_EQ(totals.size(), 8U);
      M3_EXPECT_EQ(terms.size(), 8U);
      if (totals.size() != 8U || terms.size() != 8U) return;
      for (std::size_t lane = 0U; lane < 8U; ++lane) {
        double sum = 0.0;
        const auto lane_terms = fields(terms[lane], ':');
        M3_EXPECT_EQ(lane_terms.size(), 7U);
        for (const auto& term : lane_terms) sum += std::stod(term);
        M3_EXPECT_NEAR(sum, std::stod(totals[lane]), 1.0e-10);
        if (columns[5] == "1" && (playable & ~reserved & (1U << lane)) != 0U)
          M3_EXPECT_TRUE(std::stod(totals[winner]) <= std::stod(totals[lane]) + 1.0e-10);
      }
      if (columns[5] == "1") {
        ++solitary;
        M3_EXPECT_NEAR(std::stod(columns[28]), std::stod(totals[winner]), 1.0e-10);
      } else {
        ++joint;
      }
    }
    M3_EXPECT_EQ(rows, trace.rows + 1U);
    M3_EXPECT_TRUE(solitary > 0U);
    M3_EXPECT_TRUE(joint > 0U);
    M3_EXPECT_TRUE(posterior_rows > 0U);
    M3_EXPECT_TRUE(detuning_rows > 0U);
    M3_EXPECT_TRUE(detuning_nonzero_rows > 0U);
    M3_EXPECT_TRUE(weighted_detuning_rows > 0U);
    if (reference.empty()) reference = captured;
    M3_EXPECT_EQ(captured, reference);
    if (partition == 512U) {
      std::unique_ptr<std::FILE, int (*)(std::FILE*)> unlabeled(std::tmpfile(), &std::fclose);
      M3_EXPECT_TRUE(unlabeled != nullptr);
      if (!unlabeled) return;
      trace.stream = unlabeled.get();
      labels.clear();
      M3_EXPECT_TRUE(run());
      M3_EXPECT_EQ(observed->fingerprint, baseline->fingerprint);
      std::rewind(unlabeled.get());
      std::istringstream expected(captured);
      std::string expected_line;
      while (std::fgets(line.data(), line.size(), unlabeled.get()) != nullptr) {
        M3_EXPECT_TRUE(static_cast<bool>(std::getline(expected, expected_line)));
        const auto before = fields(expected_line, '\t');
        auto after = fields(line.data(), '\t');
        if (!after.empty() && !after.back().empty() && after.back().back() == '\n')
          after.back().pop_back();
        M3_EXPECT_EQ(before.size(), after.size());
        for (std::size_t column = 0U; column < before.size() && column < after.size(); ++column)
          if (column < 24U || column > 26U) M3_EXPECT_EQ(before[column], after[column]);
      }
      M3_EXPECT_FALSE(static_cast<bool>(std::getline(expected, expected_line)));
      labels.resize(1U);
      labels[0].midi_note = 56U;
      labels[0].end_sample = 96000U;
      labels[0].string_mask = 64U;
      trace.stream = stream.get();
    }
    trace.stream = nullptr;
    M3_EXPECT_FALSE(run());
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
#endif
}

M3_TEST(offline_replay_correlation_window_preserves_default_and_partitioning) {
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(24000U);
  for (std::size_t sample = 0U; sample < 14400U; ++sample) {
    const double phase = 6.28318530717958647692 *
        m3::midi_to_frequency(40U, 440.0) *
        static_cast<double>(sample) / 48000.0;
    wave.mono_samples[sample] =
        0.2 * std::sin(phase) + 0.04 * std::sin(2.0 * phase + 0.3);
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 39U;
  config.highest_note = 41U;
  config.max_polyphony = 1U;
  m3::offline::ReplayError error{};
  const auto fingerprint = [&](double seconds, std::size_t partition,
                               bool selection_only = false,
                               bool shadow_only = false) {
    // Offline reports contain large counter tables. Keep each inlined call's
    // report off the bounded test stack, as the replay executable does.
    auto result = std::make_unique<m3::offline::ReplayResult>();
    M3_EXPECT_TRUE(m3::offline::run_detector_replay(
        wave, {}, config, nullptr, partition, *result, error,
        nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
        false, false, false, seconds, selection_only, shadow_only));
    return result->fingerprint;
  };
  M3_EXPECT_EQ(fingerprint(-1.0, 512U), fingerprint(0.040, 512U));
  const auto longer = fingerprint(0.080, 512U);
  M3_EXPECT_EQ(longer, fingerprint(0.080, 32U));
  M3_EXPECT_EQ(longer, fingerprint(0.080, 1024U));
  M3_EXPECT_TRUE(longer != fingerprint(0.040, 512U));
  M3_EXPECT_EQ(fingerprint(-1.0, 512U), fingerprint(0.040, 512U, true));
  const auto selection_longer = fingerprint(0.080, 512U, true);
  M3_EXPECT_EQ(selection_longer, fingerprint(0.080, 32U, true));
  M3_EXPECT_EQ(selection_longer, fingerprint(0.080, 1024U, true));
  for (const std::size_t partition : {32U, 512U, 1024U}) {
    M3_EXPECT_EQ(fingerprint(-1.0, 512U),
                 fingerprint(0.120, partition, false, true));
  }
  for (const double seconds : {0.0, 0.019, 0.201,
           std::numeric_limits<double>::quiet_NaN()}) {
    auto result = std::make_unique<m3::offline::ReplayResult>();
    M3_EXPECT_FALSE(m3::offline::run_detector_replay(
        wave, {}, config, nullptr, 512U, *result, error,
        nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
        false, false, false, seconds));
    M3_EXPECT_EQ(error, m3::offline::ReplayError::invalid_config);
  }
}

M3_TEST(offline_correlation_shadow_protects_attacks_groups_and_release) {
  using m3::offline::correlation_shadow_projection;
  m3::TunerSnapshot snapshot;
  snapshot.state = m3::TunerFrameState::tracking;
  snapshot.voice_count = 1U;
  auto& voice = snapshot.voices[0U];
  voice.midi_note = voice.detected_midi_note = 52U;
  voice.state = m3::TunerVoiceState::tracking;
  voice.age_ticks = 600U;
  voice.string_index = 2U;
  voice.pitch_evidence_member_mask = 4U;
  voice.pitch_evidence_group_id = 1U;
  std::array<double, 128U> ratios;
  ratios.fill(std::numeric_limits<double>::quiet_NaN());
  ratios[52U] = 0.20;
  const m3::offline::CorrelationShadowPolicy policy{0.35, 0.30, false};
  std::uint32_t changed = 0U;
  M3_EXPECT_EQ(correlation_shadow_projection(
                   snapshot, ratios, 48000.0, policy, changed).voice_count,
               0U);
  M3_EXPECT_EQ(changed, 1U);
  std::array<bool, 128U> pending{};
  pending[52U] = true;
  auto pending_policy = policy;
  pending_policy.protect_pending_unison = true;
  changed = 0U;
  M3_EXPECT_EQ(correlation_shadow_projection(
                   snapshot, ratios, 48000.0, pending_policy, changed,
                   &pending).voice_count,
               1U);
  M3_EXPECT_EQ(changed, 0U);
  M3_EXPECT_EQ(correlation_shadow_projection(
                   snapshot, ratios, 48000.0, policy, changed,
                   &pending).voice_count,
               0U);
  M3_EXPECT_EQ(changed, 1U);
  const auto expect_retained = [&](const m3::TunerSnapshot& protected_frame) {
    std::uint32_t removed = 0U;
    const auto projected = correlation_shadow_projection(
        protected_frame, ratios, 48000.0, policy, removed);
    M3_EXPECT_EQ(projected.voice_count, protected_frame.voice_count);
    M3_EXPECT_EQ(removed, 0U);
  };
  auto protected_frame = snapshot;
  protected_frame.voices[0U].age_ticks = 1U;
  expect_retained(protected_frame);
  protected_frame = snapshot;
  protected_frame.voices[0U].state = m3::TunerVoiceState::coasting;
  expect_retained(protected_frame);
  protected_frame = snapshot;
  protected_frame.voices[0U].midi_note = 53U;
  expect_retained(protected_frame);
  protected_frame = snapshot;
  protected_frame.voices[0U].pitch_evidence_member_mask = 12U;
  expect_retained(protected_frame);
  protected_frame = snapshot;
  protected_frame.voice_count = 2U;
  protected_frame.voices[1U] = voice;
  protected_frame.voices[1U].string_index = 3U;
  expect_retained(protected_frame);
  protected_frame = snapshot;
  protected_frame.state = m3::TunerFrameState::no_signal;
  expect_retained(protected_frame);
  for (const double ratio : {0.35, 0.99, -1.0,
           std::numeric_limits<double>::quiet_NaN()}) {
    ratios[52U] = ratio;
    expect_retained(snapshot);
  }
}

M3_TEST(offline_correlation_shadow_ratio_is_scale_invariant) {
  const auto measured = [](double amplitude) {
    auto detector = std::make_unique<m3::PolyphonicPitchDetector>();
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::general;
    config.lowest_note = 51U;
    config.highest_note = 54U;
    M3_EXPECT_TRUE(detector->configure(48000.0, config));
    M3_EXPECT_TRUE(detector->set_correlation_window_for_diagnostics(
        0.080, false, true));
    double ratio = 0.0;
    M3_EXPECT_FALSE(detector->correlation_window_energy_ratio_for_diagnostics(
        53U, true, ratio));
    for (std::size_t sample = 0U; sample < 48000U; ++sample) {
      static_cast<void>(detector->process_sample(
          amplitude * std::sin(6.28318530717958647692 *
              m3::midi_to_frequency(53U, 440.0) *
              static_cast<double>(sample) / 48000.0)));
    }
    std::array<double, 2U> result{};
    M3_EXPECT_TRUE(detector->correlation_window_energy_ratio_for_diagnostics(
        53U, true, result[0U]));
    M3_EXPECT_TRUE(detector->correlation_window_energy_ratio_for_diagnostics(
        52U, true, result[1U]));
    M3_EXPECT_TRUE(result[0U] > 0.90);
    M3_EXPECT_TRUE(result[1U] < 0.50);
    M3_EXPECT_FALSE(detector->set_correlation_window_for_diagnostics(
        0.120, false, true));
    return result;
  };
  const auto quiet = measured(0.01);
  const auto loud = measured(0.20);
  for (std::size_t index = 0U; index < quiet.size(); ++index) {
    M3_EXPECT_TRUE(std::abs(quiet[index] - loud[index]) < 1.0e-10);
  }
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
      std::uint32_t cache_refresh_frames = 0U;
      for (const std::uint32_t frames :
           result.label_results[0]
               .unison_cache_refresh_disposition_frames) {
        cache_refresh_frames += frames;
      }
      M3_EXPECT_EQ(cache_refresh_frames,
                   result.label_results[0].labeled_frames);
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
      const std::uint64_t raw_output_lane = std::accumulate(
          result.adjacent_wrong_note_raw_output_lane_frames[direction].begin(),
          result.adjacent_wrong_note_raw_output_lane_frames[direction].end(),
          std::uint64_t{0});
      const std::uint64_t expected_selection = std::accumulate(
          result.adjacent_wrong_note_expected_selection_frames[direction]
              .begin(),
          result.adjacent_wrong_note_expected_selection_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t expected_score = std::accumulate(
          result.adjacent_wrong_note_expected_score_ratio_frames[direction]
              .begin(),
          result.adjacent_wrong_note_expected_score_ratio_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t relative_score = std::accumulate(
          result
              .adjacent_wrong_note_expected_to_observed_score_ratio_frames
                  [direction]
              .begin(),
          result
              .adjacent_wrong_note_expected_to_observed_score_ratio_frames
                  [direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t expected_evidence = std::accumulate(
          result.adjacent_wrong_note_expected_evidence_frames[direction]
              .begin(),
          result.adjacent_wrong_note_expected_evidence_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t expected_lane = std::accumulate(
          result
              .adjacent_wrong_note_expected_playable_lane_frames[direction]
              .begin(),
          result
              .adjacent_wrong_note_expected_playable_lane_frames[direction]
              .end(),
          std::uint64_t{0});
      const std::uint64_t expected_context = std::accumulate(
          result
              .adjacent_wrong_note_expected_candidate_context_frames
                  [direction]
              .begin(),
          result
              .adjacent_wrong_note_expected_candidate_context_frames
                  [direction]
              .end(),
          std::uint64_t{0});
      M3_EXPECT_EQ(dispositions,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(raw_output_lane,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(reasons,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(presence,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(lanes, result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(joint, result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(expected_selection,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(expected_score,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(relative_score,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(expected_evidence,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(expected_lane,
                   result.false_wrong_note_interval_frames[interval]);
      M3_EXPECT_EQ(expected_context,
                   result.false_wrong_note_interval_frames[interval]);
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
      M3_EXPECT_EQ(result.adjacent_wrong_note_raw_output_lane_frames,
                   baseline.adjacent_wrong_note_raw_output_lane_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_selection_frames,
          baseline.adjacent_wrong_note_expected_selection_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_score_ratio_frames,
          baseline.adjacent_wrong_note_expected_score_ratio_frames);
      M3_EXPECT_EQ(
          result
              .adjacent_wrong_note_expected_to_observed_score_ratio_frames,
          baseline
              .adjacent_wrong_note_expected_to_observed_score_ratio_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_evidence_frames,
          baseline.adjacent_wrong_note_expected_evidence_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_playable_lane_frames,
          baseline.adjacent_wrong_note_expected_playable_lane_frames);
      M3_EXPECT_EQ(
          result.adjacent_wrong_note_expected_candidate_context_frames,
          baseline.adjacent_wrong_note_expected_candidate_context_frames);
      M3_EXPECT_EQ(result.adjacent_envelope_coherence_frames,
                   baseline.adjacent_envelope_coherence_frames);
      M3_EXPECT_EQ(result.adjacent_spectral_error_gap_frames,
                   baseline.adjacent_spectral_error_gap_frames);
      for (std::size_t policy = 0U;
           policy < result.adjacent_spectral_duplicate_suppression.size();
           ++policy) {
        const auto& actual =
            result.adjacent_spectral_duplicate_suppression[policy];
        const auto& expected =
            baseline.adjacent_spectral_duplicate_suppression[policy];
        M3_EXPECT_EQ(actual.matched_label_frames,
                     expected.matched_label_frames);
        M3_EXPECT_EQ(actual.false_positive_voices,
                     expected.false_positive_voices);
        M3_EXPECT_EQ(actual.false_gap_voices, expected.false_gap_voices);
        M3_EXPECT_EQ(actual.false_wrong_note_voices,
                     expected.false_wrong_note_voices);
        M3_EXPECT_EQ(actual.false_wrong_string_voices,
                     expected.false_wrong_string_voices);
        M3_EXPECT_EQ(actual.changed_voices, expected.changed_voices);
      }
      for (std::size_t policy = 0U;
           policy <
           result.production_adjacent_spectral_duplicate_suppression.size();
           ++policy) {
        const auto& actual =
            result.production_adjacent_spectral_duplicate_suppression[policy];
        const auto& expected =
            baseline.production_adjacent_spectral_duplicate_suppression
                [policy];
        M3_EXPECT_EQ(actual.matched_label_frames,
                     expected.matched_label_frames);
        M3_EXPECT_EQ(actual.false_positive_voices,
                     expected.false_positive_voices);
        M3_EXPECT_EQ(actual.false_gap_voices, expected.false_gap_voices);
        M3_EXPECT_EQ(actual.false_wrong_note_voices,
                     expected.false_wrong_note_voices);
        M3_EXPECT_EQ(actual.false_wrong_string_voices,
                     expected.false_wrong_string_voices);
        M3_EXPECT_EQ(actual.changed_voices, expected.changed_voices);
      }
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
      M3_EXPECT_EQ(result.physical_group_pending_triple_recovery_frames,
                   baseline.physical_group_pending_triple_recovery_frames);
      M3_EXPECT_EQ(result.physical_group_pending_triple_recovery_context_frames,
                   baseline.physical_group_pending_triple_recovery_context_frames);
      M3_EXPECT_EQ(result.physical_group_pending_triple_cached_matched_delta,
                   baseline.physical_group_pending_triple_cached_matched_delta);
      M3_EXPECT_EQ(result.physical_group_pending_triple_cached_exact_delta,
                   baseline.physical_group_pending_triple_cached_exact_delta);
      M3_EXPECT_EQ(result.physical_group_pending_triple_cached_wrong_string_delta,
                   baseline.physical_group_pending_triple_cached_wrong_string_delta);
      M3_EXPECT_EQ(result.physical_group_completed_triple_fit_frames,
                   baseline.physical_group_completed_triple_fit_frames);
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
          result.label_results[label].group_continuity_diagnostic_frames,
          baseline.label_results[label]
              .group_continuity_diagnostic_frames);
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
                  .unison_cache_refresh_disposition_frames,
              baseline.label_results[label]
                  .unison_cache_refresh_disposition_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .unison_cache_refresh_lane_outcome_frames,
              baseline.label_results[label]
                  .unison_cache_refresh_lane_outcome_frames);
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
                  .fine_mask_complexity_changed_frames,
              baseline.label_results[label]
                  .fine_mask_complexity_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_complexity_exact_frames,
              baseline.label_results[label]
                  .fine_mask_complexity_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_complexity_matched_delta,
              baseline.label_results[label]
                  .fine_mask_complexity_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_complexity_wrong_string_delta,
              baseline.label_results[label]
                  .fine_mask_complexity_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_model_expected_available_frames,
              baseline.label_results[label]
                  .fine_mask_model_expected_available_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_model_expected_rank_frames,
              baseline.label_results[label]
                  .fine_mask_model_expected_rank_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_model_exact_frames,
              baseline.label_results[label].fine_mask_model_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_model_tied_frames,
              baseline.label_results[label].fine_mask_model_tied_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_model_winner_member_frames,
              baseline.label_results[label]
                  .fine_mask_model_winner_member_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_posterior_available_frames,
              baseline.label_results[label]
                  .fine_mask_posterior_available_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_posterior_exact_frames,
              baseline.label_results[label].fine_mask_posterior_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_posterior_tied_frames,
              baseline.label_results[label].fine_mask_posterior_tied_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_beat_expected_available_frames,
              baseline.label_results[label]
                  .fine_mask_beat_expected_available_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_beat_exact_frames,
              baseline.label_results[label].fine_mask_beat_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_beat_tied_frames,
              baseline.label_results[label].fine_mask_beat_tied_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_beat_pruning_changed_frames,
              baseline.label_results[label]
                  .fine_mask_beat_pruning_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label].fine_mask_beat_pruning_exact_frames,
              baseline.label_results[label]
                  .fine_mask_beat_pruning_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_beat_pruning_matched_delta,
              baseline.label_results[label]
                  .fine_mask_beat_pruning_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_beat_pruning_wrong_string_delta,
              baseline.label_results[label]
                  .fine_mask_beat_pruning_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .fine_mask_pruning_output_mask_frames,
              baseline.label_results[label]
                  .fine_mask_pruning_output_mask_frames);
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
                  .production_cache_continuity_changed_frames,
              baseline.label_results[label]
                  .production_cache_continuity_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .production_cache_continuity_exact_frames,
              baseline.label_results[label]
                  .production_cache_continuity_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .production_cache_continuity_matched_delta,
              baseline.label_results[label]
                  .production_cache_continuity_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .production_cache_continuity_wrong_string_delta,
              baseline.label_results[label]
                  .production_cache_continuity_wrong_string_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_cache_continuity_changed_frames,
              baseline.label_results[label]
                  .committed_cache_continuity_changed_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_cache_continuity_exact_frames,
              baseline.label_results[label]
                  .committed_cache_continuity_exact_frames);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_cache_continuity_matched_delta,
              baseline.label_results[label]
                  .committed_cache_continuity_matched_delta);
          M3_EXPECT_EQ(
              result.label_results[label]
                  .committed_cache_continuity_wrong_string_delta,
              baseline.label_results[label]
                  .committed_cache_continuity_wrong_string_delta);
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
