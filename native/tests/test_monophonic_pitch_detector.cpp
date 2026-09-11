#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "m3/monophonic_pitch_detector.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"
#include "test_support.hpp"

namespace {

void feed_tone(m3::MonophonicPitchDetector& detector, std::uint8_t note,
               std::uint32_t samples, m3::TickTransitions& transitions,
               std::uint32_t* first_note_on_sample = nullptr) noexcept {
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
      if (first_note_on_sample != nullptr &&
          decision.transitions[event].kind == m3::TransitionKind::note_on &&
          decision.transitions[event].note == note &&
          *first_note_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        *first_note_on_sample = index;
      }
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

struct DyadLifecycle final {
  std::uint8_t low_note{};
  std::uint8_t high_note{};
  bool low_on{};
  bool high_on{};
  bool low_off{};
  bool high_off{};
  bool unexpected_on{};
  std::uint32_t low_on_sample{std::numeric_limits<std::uint32_t>::max()};
  std::uint32_t high_on_sample{std::numeric_limits<std::uint32_t>::max()};
};

void observe_dyad(const m3::DetectorDecision& decision,
                  DyadLifecycle& lifecycle, std::uint32_t sample) noexcept {
  for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
    const m3::VoiceTransition& transition = decision.transitions[event];
    if (transition.note == lifecycle.low_note) {
      lifecycle.low_on = lifecycle.low_on ||
                         transition.kind == m3::TransitionKind::note_on;
      if (transition.kind == m3::TransitionKind::note_on &&
          lifecycle.low_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        lifecycle.low_on_sample = sample;
      }
      lifecycle.low_off = lifecycle.low_off ||
                          transition.kind == m3::TransitionKind::note_off;
    }
    if (transition.note == lifecycle.high_note) {
      lifecycle.high_on = lifecycle.high_on ||
                          transition.kind == m3::TransitionKind::note_on;
      if (transition.kind == m3::TransitionKind::note_on &&
          lifecycle.high_on_sample == std::numeric_limits<std::uint32_t>::max()) {
        lifecycle.high_on_sample = sample;
      }
      lifecycle.high_off = lifecycle.high_off ||
                           transition.kind == m3::TransitionKind::note_off;
    }
    if (transition.kind == m3::TransitionKind::note_on &&
        transition.note != lifecycle.low_note &&
        transition.note != lifecycle.high_note) {
      lifecycle.unexpected_on = true;
    }
  }
}

void feed_dyad(m3::MonophonicPitchDetector& detector, std::uint8_t low_note,
               std::uint8_t high_note, double low_amplitude,
               double high_amplitude, std::uint32_t samples,
               DyadLifecycle& lifecycle,
               std::uint64_t starting_sample = 0U) noexcept {
  constexpr double kSampleRate = 48000.0;
  const double low_frequency =
      m3::midi_to_frequency(static_cast<double>(low_note), 440.0);
  const double high_frequency =
      m3::midi_to_frequency(static_cast<double>(high_note), 440.0);
  for (std::uint32_t index = 0; index < samples; ++index) {
    const double time =
        static_cast<double>(starting_sample + index) / kSampleRate;
    const double sample =
        low_amplitude * std::sin(6.28318530717958647692 * low_frequency * time) +
        high_amplitude * std::sin(6.28318530717958647692 * high_frequency * time);
    observe_dyad(detector.process_sample(sample), lifecycle, index);
  }
}

void release_dyad(m3::MonophonicPitchDetector& detector,
                  std::uint32_t samples, DyadLifecycle& lifecycle) noexcept {
  for (std::uint32_t index = 0; index < samples; ++index) {
    observe_dyad(detector.process_sample(0.0), lifecycle, index);
  }
}

struct ChordLifecycle final {
  std::array<std::uint8_t, m3::kMaxVoices> notes{};
  std::array<bool, m3::kMaxVoices> note_on{};
  std::array<bool, m3::kMaxVoices> note_off{};
  std::array<std::uint32_t, m3::kMaxVoices> first_on_sample{};
  std::size_t voice_count{};
  bool unexpected_on{};
};

void observe_chord(const m3::DetectorDecision& decision,
                   ChordLifecycle& lifecycle,
                   std::uint32_t sample) noexcept {
  for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
    const m3::VoiceTransition& transition = decision.transitions[event];
    bool known_note = false;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      if (transition.note != lifecycle.notes[voice]) {
        continue;
      }
      known_note = true;
      if (transition.kind == m3::TransitionKind::note_on) {
        lifecycle.note_on[voice] = true;
        if (lifecycle.first_on_sample[voice] ==
            std::numeric_limits<std::uint32_t>::max()) {
          lifecycle.first_on_sample[voice] = sample;
        }
      } else {
        lifecycle.note_off[voice] = true;
      }
      break;
    }
    if (!known_note && transition.kind == m3::TransitionKind::note_on) {
      lifecycle.unexpected_on = true;
    }
  }
}

void feed_chord(m3::MonophonicPitchDetector& detector,
                double amplitude, std::uint32_t samples,
                ChordLifecycle& lifecycle) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(lifecycle.notes[voice]), 440.0);
      sample += amplitude * std::sin(6.28318530717958647692 * frequency * time);
    }
    observe_chord(detector.process_sample(sample), lifecycle, index);
  }
}

void feed_weighted_chord(
    m3::MonophonicPitchDetector& detector,
    const std::array<double, m3::kMaxVoices>& amplitudes,
    std::uint32_t samples, ChordLifecycle& lifecycle) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(lifecycle.notes[voice]), 440.0);
      sample += amplitudes[voice] *
                std::sin(6.28318530717958647692 * frequency * time);
    }
    observe_chord(detector.process_sample(sample), lifecycle, index);
  }
}

void release_chord(m3::MonophonicPitchDetector& detector,
                   std::uint32_t samples, ChordLifecycle& lifecycle) noexcept {
  for (std::uint32_t index = 0U; index < samples; ++index) {
    observe_chord(detector.process_sample(0.0), lifecycle, index);
  }
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

M3_TEST(native_detector_does_not_expand_one_tone_into_the_polyphony_limit) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 40U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 40U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 40U);
  }
}

M3_TEST(native_detector_rejects_octave_and_fifth_subharmonics_at_default_range) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  m3::TickTransitions transitions;
  feed_tone(detector, 52U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0].note, 52U);
    M3_EXPECT_EQ(transitions[1].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1].note, 52U);
  }
}

M3_TEST(native_detector_tracks_two_independent_chord_voices_and_releases_each) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.low_on_sample <= 3120U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_keeps_an_uneven_major_seventh_as_two_voices) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  DyadLifecycle lifecycle{32U, 43U};
  feed_dyad(detector, 32U, 43U, 0.15, 0.20, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_honors_m3_maximum_fret_without_limiting_general_mode) {
  m3::PersistentConfig m3_config;
  m3_config.profile_mode = m3::ProfileMode::m3;
  m3_config.lowest_note = 32U;
  m3_config.highest_note = 84U;
  m3_config.max_polyphony = 1U;
  m3_config.max_fret = 0U;
  m3_config.sensitivity = 75U;
  m3_config.response = 25U;

  m3::MonophonicPitchDetector m3_detector;
  M3_EXPECT_TRUE(m3_detector.configure(48000.0, m3_config));
  m3::TickTransitions m3_transitions;
  feed_tone(m3_detector, 33U, 30000U, m3_transitions);
  feed_silence(m3_detector, 8000U, m3_transitions);
  M3_EXPECT_EQ(m3_transitions.size(), 0U);

  m3::PersistentConfig general_config = m3_config;
  general_config.profile_mode = m3::ProfileMode::general;
  m3::MonophonicPitchDetector general_detector;
  M3_EXPECT_TRUE(general_detector.configure(48000.0, general_config));
  m3::TickTransitions general_transitions;
  feed_tone(general_detector, 33U, 30000U, general_transitions);
  feed_silence(general_detector, 8000U, general_transitions);
  M3_EXPECT_EQ(general_transitions.size(), 2U);
  if (general_transitions.size() == 2U) {
    M3_EXPECT_EQ(general_transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(general_transitions[0U].note, 33U);
    M3_EXPECT_EQ(general_transitions[1U].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(general_transitions[1U].note, 33U);
  }
}

M3_TEST(native_detector_keeps_a_clear_m3_fretted_fundamental_over_the_open_prior) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions transitions;
  feed_tone(detector, 41U, 30000U, transitions);
  feed_silence(detector, 8000U, transitions);

  M3_EXPECT_EQ(transitions.size(), 2U);
  if (transitions.size() == 2U) {
    M3_EXPECT_EQ(transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0U].note, 41U);
    M3_EXPECT_EQ(transitions[1U].kind, m3::TransitionKind::note_off);
    M3_EXPECT_EQ(transitions[1U].note, 41U);
  }
}

M3_TEST(native_detector_single_voice_onset_meets_the_causal_45ms_gate) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions transitions;
  std::uint32_t first_note_on_sample =
      std::numeric_limits<std::uint32_t>::max();
  feed_tone(detector, 40U, 6000U, transitions, &first_note_on_sample);
  M3_EXPECT_TRUE(first_note_on_sample <= 2160U);
  M3_EXPECT_EQ(transitions.size(), 1U);
  if (transitions.size() == 1U) {
    M3_EXPECT_EQ(transitions[0U].note, 40U);
  }
}

M3_TEST(native_detector_restarts_the_single_voice_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  m3::TickTransitions transitions;
  std::uint32_t first_note_on_sample =
      std::numeric_limits<std::uint32_t>::max();
  feed_tone(detector, 52U, 6000U, transitions, &first_note_on_sample);
  M3_EXPECT_TRUE(first_note_on_sample <= 2160U);
  M3_EXPECT_EQ(transitions.size(), 1U);
  if (transitions.size() == 1U) {
    M3_EXPECT_EQ(transitions[0U].kind, m3::TransitionKind::note_on);
    M3_EXPECT_EQ(transitions[0U].note, 52U);
  }
}

M3_TEST(native_detector_restarts_the_chord_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 6000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.low_on_sample <= 3120U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_requires_fresh_evidence_for_a_legato_added_voice) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.0, 6000U, lifecycle);
  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_FALSE(lifecycle.high_on);

  feed_dyad(detector, 40U, 47U, 0.16, 0.16, 6000U, lifecycle, 6000U);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.high_on_sample >= 2304U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 3120U);
}

M3_TEST(native_detector_requires_fresh_evidence_for_a_legato_replacement) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{40U, 47U};
  feed_dyad(detector, 40U, 47U, 0.16, 0.0, 6000U, lifecycle);
  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_FALSE(lifecycle.high_on);

  feed_dyad(detector, 40U, 47U, 0.0, 0.16, 6000U, lifecycle, 6000U);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.high_on);
  M3_EXPECT_TRUE(lifecycle.high_off);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
  M3_EXPECT_TRUE(lifecycle.high_on_sample >= 1792U);
  M3_EXPECT_TRUE(lifecycle.high_on_sample <= 2640U);
}

M3_TEST(native_detector_restarts_the_four_voice_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 4U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::TickTransitions discarded;
  feed_silence(detector, 24000U, discarded);

  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 40U, 48U, 56U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 4U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_chord(detector, 0.04, 6000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
    M3_EXPECT_TRUE(lifecycle.first_on_sample[voice] <= 3120U);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_completes_a_four_note_m3_chord_within_65ms) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 4U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 40U, 48U, 56U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 4U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_chord(detector, 0.04, 36000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
    M3_EXPECT_TRUE(lifecycle.first_on_sample[voice] <= 3120U);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_tracks_all_eight_m3_open_strings_at_capacity) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 36U, 40U, 44U, 48U, 52U, 56U, 60U};
  lifecycle.voice_count = lifecycle.notes.size();
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_chord(detector, 0.025, 36000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_backfills_a_valid_open_string_after_an_unplayable_peak) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 1U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  DyadLifecycle lifecycle{32U, 34U};
  feed_dyad(detector, 32U, 34U, 0.20, 0.24, 36000U, lifecycle);
  release_dyad(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.low_on);
  M3_EXPECT_TRUE(lifecycle.low_off);
  M3_EXPECT_FALSE(lifecycle.high_on);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_keeps_an_independent_open_string_when_fret_masks_conflict) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 40U;
  config.max_polyphony = 3U;
  config.max_fret = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 34U, 36U, 0U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = 3U;
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_weighted_chord(detector,
                      {0.20, 0.18, 0.08, 0.0, 0.0, 0.0, 0.0, 0.0},
                      36000U, lifecycle);
  release_chord(detector, 8000U, lifecycle);

  M3_EXPECT_TRUE(lifecycle.note_on[0U]);
  M3_EXPECT_TRUE(lifecycle.note_on[2U]);
  M3_EXPECT_TRUE(lifecycle.note_off[0U]);
  M3_EXPECT_TRUE(lifecycle.note_off[2U]);
  M3_EXPECT_FALSE(lifecycle.note_on[1U]);
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}
