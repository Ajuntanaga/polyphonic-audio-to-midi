#include <cmath>
#include <cstddef>
#include <cstdint>

#include "m3/monophonic_pitch_detector.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"
#include "test_support.hpp"

namespace {

void feed_tone(m3::MonophonicPitchDetector& detector, std::uint8_t note,
               std::uint32_t samples, m3::TickTransitions& transitions) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  const double frequency =
      m3::midi_to_frequency(static_cast<double>(note), 440.0);
  for (std::uint32_t index = 0; index < samples; ++index) {
    const double phase =
        6.28318530717958647692 * frequency * static_cast<double>(index) /
        kSampleRate;
    const m3::DetectorDecision decision =
        detector.process_sample(kAmplitude * std::sin(phase));
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
    }
  }
}

void feed_silence(m3::MonophonicPitchDetector& detector,
                  std::uint32_t samples,
                  m3::TickTransitions& transitions) noexcept {
  for (std::uint32_t index = 0; index < samples; ++index) {
    const m3::DetectorDecision decision = detector.process_sample(0.0);
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
    }
  }
}

void feed_dyad(m3::MonophonicPitchDetector& detector, std::uint8_t first,
               std::uint8_t second, std::uint32_t samples,
               m3::TickTransitions& transitions) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.15;
  const double first_frequency =
      m3::midi_to_frequency(static_cast<double>(first), 440.0);
  const double second_frequency =
      m3::midi_to_frequency(static_cast<double>(second), 440.0);
  for (std::uint32_t index = 0; index < samples; ++index) {
    const double phase = 6.28318530717958647692 * static_cast<double>(index) /
                         kSampleRate;
    const m3::DetectorDecision decision = detector.process_sample(
        kAmplitude * (std::sin(phase * first_frequency) +
                      std::sin(phase * second_frequency)));
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
    }
  }
}

bool contains_transition(const m3::TickTransitions& transitions,
                         m3::TransitionKind kind, std::uint8_t note) noexcept {
  for (std::size_t index = 0; index < transitions.size(); ++index) {
    if (transitions[index].kind == kind && transitions[index].note == note) {
      return true;
    }
  }
  return false;
}

}  // namespace

M3_TEST(native_monophonic_detector_tracks_low_eight_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 48U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 32U, 24000U, transitions);
  feed_silence(detector, 6000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 32U);
    M3_EXPECT_TRUE(transitions[0].velocity > 0U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 32U);
    M3_EXPECT_EQ(transitions[1].velocity, 0U);
  }
}

M3_TEST(native_monophonic_detector_tracks_highest_open_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 60U, 24000U, transitions);
  feed_silence(detector, 6000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 60U);
    M3_EXPECT_TRUE(transitions[0].velocity > 0U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 60U);
    M3_EXPECT_EQ(transitions[1].velocity, 0U);
  }
}

M3_TEST(native_detector_tracks_and_releases_a_two_note_chord) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_dyad(detector, 32U, 40U, 48000U, transitions);
  feed_silence(detector, 12000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 4U);
  M3_EXPECT_TRUE(
      contains_transition(transitions, m3::TransitionKind::note_on, 32U));
  M3_EXPECT_TRUE(
      contains_transition(transitions, m3::TransitionKind::note_on, 40U));
  M3_EXPECT_TRUE(
      contains_transition(transitions, m3::TransitionKind::note_off, 32U));
  M3_EXPECT_TRUE(
      contains_transition(transitions, m3::TransitionKind::note_off, 40U));
}
