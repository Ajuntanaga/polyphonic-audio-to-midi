#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <memory>

#include "joint_pitch_residual.hpp"
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
                      std::uint8_t second_note = 49U) {
  auto detector = std::make_unique<m3::PolyphonicPitchDetector>();
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::general;
  config.lowest_note = 48U;
  config.highest_note = std::max<std::uint8_t>(60U, second_note);
  M3_EXPECT_TRUE(detector->configure(48000.0, config));
  constexpr double kTwoPi = 6.28318530717958647692;
  for (std::size_t sample = 0U; sample < 48000U; ++sample) {
    const double t = static_cast<double>(sample) / 48000.0;
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
