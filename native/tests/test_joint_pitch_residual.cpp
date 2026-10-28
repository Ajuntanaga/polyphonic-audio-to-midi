#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <memory>

#include "joint_pitch_residual.hpp"
#include "m3/joint_pitch_residual.hpp"
#include "m3/pitch_math.hpp"
#include "m3/polyphonic_pitch_detector.hpp"
#include "replay.hpp"
#include "test_support.hpp"

namespace {
struct MeasuredFrame final {
  std::array<m3::offline::JointPitchObservation, m3::kMaxVoices> pitches{};
  double energy{};
  double decay{};
};

MeasuredFrame measure(double second_amplitude, double phase,
                      std::uint8_t second_note = 49U, double sample_rate = 48000.0) {
  auto detector = std::make_unique<m3::PolyphonicPitchDetector>();
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 48U;
  config.highest_note = std::max<std::uint8_t>(60U, second_note);
  M3_EXPECT_TRUE(detector->configure(sample_rate, config));
  constexpr double kTwoPi = 6.28318530717958647692;
  for (std::size_t sample = 0U; sample < static_cast<std::size_t>(sample_rate); ++sample) {
    const double t = static_cast<double>(sample) / sample_rate;
    const double p = kTwoPi * m3::midi_to_frequency(48U, 440.0) * t;
    const double q = kTwoPi * m3::midi_to_frequency(second_note, 440.0) * t;
    static_cast<void>(detector->process_sample(
        0.2 * std::sin(p + phase) + 0.05 * std::sin(2.0 * p - 0.4) +
        second_amplitude * (std::sin(q - 0.7) +
                            0.3 * std::sin(3.0 * q + 0.8))));
  }
  MeasuredFrame frame;
  frame.pitches[0U].note = 48U;
  frame.pitches[1U].note = second_note;
  for (std::size_t index = 0U; index < 2U; ++index) {
    auto& pitch = frame.pitches[index];
    M3_EXPECT_TRUE(detector->harmonic_correlations_for_diagnostics(
        pitch.note, pitch.frequency_hz, pitch.correlation,
        frame.energy, frame.decay));
  }
  return frame;
}
}  // namespace

M3_TEST(offline_joint_pitch_residual_separates_leakage_from_adjacent_tones) {
  auto fit = std::make_unique<m3::offline::JointPitchResidual>();
  for (const double phase : {-0.8, 0.0, 1.2}) {
    const auto single = measure(0.0, phase);
    const auto absent = fit->evaluate(single.pitches, 2U, 48000.0,
                                     single.decay, single.energy);
    M3_EXPECT_TRUE(absent.valid);
    M3_EXPECT_TRUE(absent.residual_fraction < 1.0e-5);
    M3_EXPECT_TRUE(absent.independent_energy_fraction[0U] > 0.01);
    M3_EXPECT_TRUE(absent.independent_energy_fraction[1U] < 1.0e-6);
    const auto mixture = measure(0.12, phase);
    const auto present = fit->evaluate(mixture.pitches, 2U, 48000.0,
                                      mixture.decay, mixture.energy);
    M3_EXPECT_TRUE(present.valid);
    M3_EXPECT_TRUE(present.residual_fraction < 1.0e-5);
    M3_EXPECT_TRUE(present.independent_energy_fraction[0U] > 0.01);
    M3_EXPECT_TRUE(present.independent_energy_fraction[1U] > 0.01);
    M3_EXPECT_TRUE(present.fundamental_overlap[0U] < 0.90);
    M3_EXPECT_TRUE(present.fundamental_overlap[1U] < 0.90);
  }
}

M3_TEST(offline_joint_pitch_residual_shares_harmonics_and_preserves_scale) {
  auto fit = std::make_unique<m3::offline::JointPitchResidual>();
  auto frame = measure(0.12, 0.4, 60U);
  const auto baseline = fit->evaluate(frame.pitches, 2U, 48000.0,
                                      frame.decay, frame.energy);
  M3_EXPECT_TRUE(baseline.valid);
  M3_EXPECT_TRUE(baseline.residual_fraction < 1.0e-5);
  M3_EXPECT_TRUE(baseline.independent_energy_fraction[0U] > 0.01);
  // The upper tone's third harmonic overlaps the lower tone's sixth, so
  // shared harmonics cannot independently prove either pitch's ownership.
  M3_EXPECT_TRUE(baseline.independent_energy_fraction[1U] < 1.0e-6);
  M3_EXPECT_TRUE(baseline.shared_fundamental[1U]);
  M3_EXPECT_FALSE(baseline.shared_fundamental[0U]);
  const auto near = measure(0.12, 0.4, 67U);
  const auto near_fit = fit->evaluate(near.pitches, 2U, 48000.0,
                                     near.decay, near.energy);
  M3_EXPECT_TRUE(near_fit.valid);
  M3_EXPECT_FALSE(near_fit.shared_fundamental[1U]);
  M3_EXPECT_TRUE(near_fit.fundamental_overlap[1U] > 0.95);
  for (auto& pitch : frame.pitches) {
    for (auto& value : pitch.correlation) {
      value *= 0.03;
    }
  }
  frame.energy *= 0.03 * 0.03;
  std::swap(frame.pitches[0U], frame.pitches[1U]);
  const auto scaled = fit->evaluate(frame.pitches, 2U, 48000.0,
                                    frame.decay, frame.energy);
  M3_EXPECT_TRUE(scaled.valid);
  M3_EXPECT_NEAR(scaled.residual_fraction, baseline.residual_fraction, 1.0e-9);
  M3_EXPECT_NEAR(scaled.independent_energy_fraction[1U],
                 baseline.independent_energy_fraction[0U], 1.0e-9);
  M3_EXPECT_FALSE(fit->evaluate(frame.pitches, 2U, 48000.0,
                                frame.decay, 0.0).valid);
  frame.pitches[0U].correlation[0U] = {
      std::numeric_limits<double>::quiet_NaN(), 0.0};
  M3_EXPECT_FALSE(fit->evaluate(frame.pitches, 2U, 48000.0,
                                frame.decay, frame.energy).valid);
}

M3_TEST(offline_joint_pitch_residual_replay_is_causal_and_partition_invariant) {
  m3::offline::WaveData wave;
  wave.sample_rate = 48000U;
  wave.source_channels = 1U;
  wave.mono_samples.resize(76800U);
  for (std::size_t sample = 0U; sample < 57600U; ++sample) {
    const double t = static_cast<double>(sample) / 48000.0;
    wave.mono_samples[sample] =
        0.2 * std::sin(6.28318530717958647692 *
                       m3::midi_to_frequency(48U, 440.0) * t) +
        0.12 * std::sin(6.28318530717958647692 *
                        m3::midi_to_frequency(53U, 440.0) * t + 0.7);
  }
  std::vector<m3::offline::ReplayLabel> labels(2U);
  labels[0U].midi_note = 48U;
  labels[1U].midi_note = 53U;
  for (auto& label : labels) {
    label.end_sample = 57600U;
  }
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.max_polyphony = 5U;
  config.sensitivity = 60U;
  config.response = 75U;
  m3::offline::ReplayError error{};
  auto baseline = std::make_unique<m3::offline::ReplayResult>();
  M3_EXPECT_TRUE(m3::offline::run_detector_replay(
      wave, labels, config, nullptr, 512U, *baseline, error));
  std::array<m3::offline::ReplayCounterfactualMetrics,
             m3::offline::kJointPitchPolicies.size()> previous{};
  for (const std::size_t partition : {512U, 32U, 1024U}) {
    auto current = std::make_unique<m3::offline::ReplayResult>();
    M3_EXPECT_TRUE(m3::offline::run_detector_replay(
        wave, labels, config, nullptr, partition, *current, error,
        nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
        false, false, false, -1.0, false, false, true));
    M3_EXPECT_EQ(current->fingerprint, baseline->fingerprint);
    M3_EXPECT_TRUE(current->joint_pitch_valid_frames > 0U);
    M3_EXPECT_EQ(current->joint_pitch_shadow[0U].matched_label_frames,
                 baseline->matched_label_frames);
    M3_EXPECT_EQ(current->joint_pitch_shadow[0U].false_positive_voices,
                 baseline->false_positive_voices);
    M3_EXPECT_EQ(current->joint_pitch_shadow[0U].changed_voices, 0U);
    if (partition != 512U) {
      for (std::size_t i = 0U; i < previous.size(); ++i) {
        M3_EXPECT_EQ(current->joint_pitch_shadow[i].matched_label_frames,
                     previous[i].matched_label_frames);
        M3_EXPECT_EQ(current->joint_pitch_shadow[i].false_positive_voices,
                     previous[i].false_positive_voices);
        M3_EXPECT_EQ(current->joint_pitch_shadow[i].changed_voices,
                     previous[i].changed_voices);
      }
    }
    previous = current->joint_pitch_shadow;
  }
}

M3_TEST(compact_joint_pitch_residual_matches_all_deletions_and_topology_changes) {
  static_assert(sizeof(m3::JointPitchResidual) < 48U * 1024U);
  M3_EXPECT_TRUE(sizeof(m3::JointPitchResidual) < sizeof(m3::offline::JointPitchResidual) / 10U);
  auto reference = std::make_unique<m3::offline::JointPitchResidual>();
  auto compact = std::make_unique<m3::JointPitchResidual>();
  auto detector = std::make_unique<m3::PolyphonicPitchDetector>();
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  M3_EXPECT_TRUE(detector->configure(48000.0, config));
  const std::array<std::uint8_t, m3::kMaxVoices> notes{36U, 40U, 43U, 48U, 53U, 59U, 67U, 72U};
  std::array<double, m3::kMaxVoices> frequencies{};
  for (std::size_t i = 0U; i < notes.size(); ++i) {
    frequencies[i] = m3::midi_to_frequency(notes[i], 440.0);
  }
  for (std::size_t sample = 0U; sample < 48000U; ++sample) {
    double value = 0.0;
    for (std::size_t i = 0U; i < 6U; ++i) {
      const double angle = 6.28318530717958647692 * frequencies[i] *
                           static_cast<double>(sample) / 48000.0;
      value += (0.04 + 0.003 * static_cast<double>(i)) *
          (std::sin(angle + 0.4 * static_cast<double>(i)) +
           0.3 * std::sin(2.0 * angle - 0.3) + 0.16 * std::sin(3.0 * angle + 0.7));
    }
    static_cast<void>(detector->process_sample(value));
  }
  MeasuredFrame frame;
  for (std::size_t i = 0U; i < notes.size(); ++i) {
    frame.pitches[i].note = notes[i];
    M3_EXPECT_TRUE(detector->harmonic_correlations_for_diagnostics(
        notes[i], frame.pitches[i].frequency_hz, frame.pitches[i].correlation,
        frame.energy, frame.decay));
  }
  const auto compare = [&](std::size_t count) {
    const auto before_allocations = m3::test::allocation_count();
    const auto before_deallocations = m3::test::deallocation_count();
    const auto expected = reference->evaluate(frame.pitches, count, 48000.0, frame.decay, frame.energy);
    const auto actual = compact->evaluate(frame.pitches, count, 48000.0, frame.decay, frame.energy);
    M3_EXPECT_EQ(m3::test::allocation_count(), before_allocations);
    M3_EXPECT_EQ(m3::test::deallocation_count(), before_deallocations);
    M3_EXPECT_TRUE(expected.valid && actual.valid);
    M3_EXPECT_NEAR(actual.residual_fraction, expected.residual_fraction, 1.0e-9);
    for (std::size_t pitch = 0U; pitch < count; ++pitch) {
      M3_EXPECT_NEAR(actual.independent_energy_fraction[pitch], expected.independent_energy_fraction[pitch], 1.0e-9);
      M3_EXPECT_EQ(actual.shared_fundamental[pitch], expected.shared_fundamental[pitch]);
      M3_EXPECT_NEAR(actual.fundamental_overlap[pitch], expected.fundamental_overlap[pitch], 1.0e-12);
    }
  };
  for (std::size_t count = 1U; count <= notes.size(); ++count) {
    compare(count);  // Rebuild.
    compare(count);  // Cached factorization.
  }
  std::reverse(frame.pitches.begin(), frame.pitches.end());
  compare(notes.size());
  for (auto& pitch : frame.pitches) {
    for (auto& value : pitch.correlation) {
      value *= 0.01;
    }
  }
  frame.energy *= 0.0001;
  compare(notes.size());
  frame.pitches[0U].frequency_hz[5U] = 0.0;
  compare(notes.size());
}

M3_TEST(compact_joint_pitch_residual_keeps_negative_and_shared_pitch_controls) {
  m3::JointPitchResidual compact;
  auto reference = std::make_unique<m3::offline::JointPitchResidual>();
  for (const auto sample_rate : {44100.0, 48000.0, 88200.0, 96000.0}) {
   for (const auto note : {49U, 60U, 67U}) {
    const auto frame = measure(0.0, 0.7, static_cast<std::uint8_t>(note), sample_rate);
    const auto expected = reference->evaluate(frame.pitches, 2U, sample_rate, frame.decay, frame.energy);
    const auto actual = compact.evaluate(frame.pitches, 2U, sample_rate, frame.decay, frame.energy);
    M3_EXPECT_TRUE(expected.valid && actual.valid);
    M3_EXPECT_NEAR(actual.independent_energy_fraction[1U], expected.independent_energy_fraction[1U], 1.0e-9);
    M3_EXPECT_EQ(actual.shared_fundamental[1U], expected.shared_fundamental[1U]);
    M3_EXPECT_FALSE(compact.evaluate(frame.pitches, 2U, sample_rate, frame.decay, 0.0).valid);
    auto invalid = frame.pitches;
    invalid[0U].correlation[0U] = {std::numeric_limits<double>::infinity(), 0.0};
    M3_EXPECT_FALSE(compact.evaluate(invalid, 2U, sample_rate, frame.decay, frame.energy).valid);
   }
  }
}
