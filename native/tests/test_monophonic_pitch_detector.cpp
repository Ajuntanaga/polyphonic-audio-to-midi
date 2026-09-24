#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "m3/monophonic_pitch_detector.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"
#include "test_support.hpp"

namespace m3 {

struct MonophonicPitchDetectorTestAccess final {
  static DetectorDecision attempt_reserved_string_activation(
      MonophonicPitchDetector& detector) noexcept {
    detector.candidate_count_ = 2U;
    detector.lowest_note_ = 32U;
    detector.profile_mode_ = ProfileMode::m3;
    detector.midi_routing_ = MidiRouting::per_voice;
    detector.max_fret_ = 1U;
    detector.refresh_m3_playable_string_masks();

    detector.candidate_states_ = {};
    detector.candidate_states_[0U].active = true;
    detector.candidate_states_[0U].assigned_string = 0U;
    detector.candidate_states_[0U].assigned_string_mask = 1U;
    detector.candidate_states_[0U].midi_voice_mask = 1U;

    std::array<bool, kMaxCandidates> selected{};
    selected[1U] = true;
    detector.assign_m3_strings(selected);

    DetectorDecision decision;
    const bool activated = detector.append_candidate_note_on(
        decision, 1U, 100U);
    if (activated) {
      detector.candidate_states_[1U].active = true;
    }
    detector.append_candidate_note_off(decision, 1U);
    return decision;
  }
};

}  // namespace m3

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

void feed_calibration_pitch(m3::MonophonicPitchDetector& detector,
                            double midi_pitch,
                            std::uint32_t samples,
                            double* oscillator_phase = nullptr) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  const double frequency = m3::midi_to_frequency(midi_pitch, 440.0);
  double phase = oscillator_phase != nullptr ? *oscillator_phase : 0.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const m3::DetectorDecision decision =
        detector.process_sample(kAmplitude * std::sin(phase));
    phase = std::fmod(phase + 6.28318530717958647692 * frequency / kSampleRate,
                      6.28318530717958647692);
    static_cast<void>(decision);
  }
  if (oscillator_phase != nullptr) {
    *oscillator_phase = phase;
  }
}

void feed_calibration_glide(m3::MonophonicPitchDetector& detector,
                            double start_midi_pitch, double end_midi_pitch,
                            std::uint32_t samples,
                            double& oscillator_phase) noexcept {
  constexpr double kSampleRate = 48000.0;
  constexpr double kAmplitude = 0.20;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double amount = samples > 1U
                              ? static_cast<double>(index) /
                                    static_cast<double>(samples - 1U)
                              : 1.0;
    const double midi_pitch =
        start_midi_pitch + (end_midi_pitch - start_midi_pitch) * amount;
    const double frequency = m3::midi_to_frequency(midi_pitch, 440.0);
    static_cast<void>(
        detector.process_sample(kAmplitude * std::sin(oscillator_phase)));
    oscillator_phase = std::fmod(
        oscillator_phase + 6.28318530717958647692 * frequency / kSampleRate,
        6.28318530717958647692);
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
                   std::uint32_t sample) noexcept;

struct RealisticStringModel final {
  double detune_cents{};
  double amplitude{};
  double initial_phase{};
  double fundamental{};
  double second_harmonic{};
  double third_harmonic{};
  double fourth_harmonic{};
};

// A deterministic eight-string source model. Real strings never begin at the
// same phase, land at exactly zero cents, or share one harmonic envelope. Keep
// those differences in simultaneous-note tests so string assignment is not
// accidentally validated only against phase-aligned laboratory sines.
constexpr std::array<RealisticStringModel, m3::kMaxVoices>
    kRealisticM3Strings{{
        {-3.8, 0.021, 0.07, 1.0, 0.23, 0.10, 0.040},
        {2.6, 0.019, 0.41, 1.0, 0.29, 0.07, 0.055},
        {-1.4, 0.023, 0.89, 1.0, 0.18, 0.13, 0.035},
        {4.1, 0.020, 1.37, 1.0, 0.32, 0.05, 0.060},
        {-2.7, 0.022, 1.93, 1.0, 0.21, 0.11, 0.045},
        {1.8, 0.018, 2.51, 1.0, 0.27, 0.08, 0.030},
        {3.2, 0.021, 3.14, 1.0, 0.16, 0.14, 0.050},
        {-2.2, 0.020, 3.73, 1.0, 0.25, 0.06, 0.040},
    }};

double realistic_string_sample(std::uint8_t note, std::size_t string_index,
                               double time) noexcept {
  constexpr double kTwoPi = 6.28318530717958647692;
  const RealisticStringModel& model = kRealisticM3Strings[string_index];
  const double pitch =
      static_cast<double>(note) + model.detune_cents / 100.0;
  const double frequency = m3::midi_to_frequency(pitch, 440.0);
  const double phase = model.initial_phase + kTwoPi * frequency * time;
  const double string_phase = 0.13 * static_cast<double>(string_index + 1U);
  return model.amplitude *
         (model.fundamental * std::sin(phase) +
          model.second_harmonic * std::sin(2.0 * phase + string_phase) +
          model.third_harmonic * std::sin(3.0 * phase - 0.7 * string_phase) +
          model.fourth_harmonic * std::sin(4.0 * phase + 1.3 * string_phase));
}

void feed_realistic_string_chord(
    m3::MonophonicPitchDetector& detector,
    const std::array<std::uint8_t, m3::kMaxVoices>& notes,
    std::uint32_t samples, ChordLifecycle* lifecycle = nullptr,
    m3::TunerSnapshot* final_snapshot = nullptr) noexcept {
  constexpr double kSampleRate = 48000.0;
  for (std::uint32_t index = 0U; index < samples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    double sample = 0.0;
    for (std::size_t string = 0U; string < notes.size(); ++string) {
      sample += realistic_string_sample(notes[string], string, time);
    }
    const m3::DetectorDecision decision = detector.process_sample(sample);
    if (lifecycle != nullptr) {
      observe_chord(decision, *lifecycle, index);
    }
    if (final_snapshot != nullptr && decision.tuner_snapshot_ready) {
      *final_snapshot = decision.tuner_snapshot;
    }
  }
}

void set_measured_string_profile(
    m3::StringCalibrationBank& bank, std::size_t string, std::size_t fret,
    double cents,
    const std::array<double, m3::kCalibrationHarmonicCount>& amplitudes) noexcept {
  m3::StringCalibrationPoint& point = bank.points[string][fret];
  double total_energy = 0.0;
  for (const double amplitude : amplitudes) {
    total_energy += amplitude * amplitude;
  }
  for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
    point.harmonic_profile_q15[harmonic] =
        static_cast<std::uint16_t>(std::lround(
            32767.0 * amplitudes[harmonic] * amplitudes[harmonic] /
            total_energy));
  }
  point.cents_offset_q8 =
      static_cast<std::int16_t>(std::lround(cents * 256.0));
  point.confidence_q15 = 32767U;
  point.observation_count = 128U;
  point.quality = m3::CalibrationPointQuality::measured;
  bank.calibrated_string_mask = static_cast<std::uint8_t>(
      bank.calibrated_string_mask | (1U << string));
}

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
  feed_silence(detector, 16000U, transitions);

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

M3_TEST(native_detector_reports_cents_for_the_low_g_sharp_range_boundary) {
  constexpr double kSampleRate = 96000.0;
  constexpr double kDetuneCents = 12.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 1U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  const double frequency = m3::midi_to_frequency(
      32.0 + kDetuneCents / 100.0, config.a4_hz);
  bool found_valid_cents = false;
  double observed_cents = 0.0;
  for (std::uint32_t index = 0U; index < 24000U; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    const m3::DetectorDecision decision = detector.process_sample(
        0.08 * std::sin(6.28318530717958647692 * frequency * time));
    if (!decision.tuner_snapshot_ready) {
      continue;
    }
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& estimate = decision.tuner_snapshot.voices[voice];
      if (estimate.midi_note == 32U && estimate.cents_valid) {
        found_valid_cents = true;
        observed_cents = static_cast<double>(estimate.cents_q8) / 256.0;
      }
    }
  }
  M3_EXPECT_TRUE(found_valid_cents);
  M3_EXPECT_NEAR(observed_cents, kDetuneCents, 6.0);
}

M3_TEST(native_detector_calibration_does_not_redefine_tuner_zero_cents) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kDetuneCents = 12.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 32U;
  config.max_polyphony = 1U;
  config.max_fret = 0U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(
      bank, 0U, 0U, kDetuneCents,
      {1.0, 0.02, 0.01, 0.0, 0.0, 0.0});
  detector.set_calibration_bank(bank);

  const double frequency = m3::midi_to_frequency(
      32.0 + kDetuneCents / 100.0, config.a4_hz);
  bool found_valid_cents = false;
  double observed_cents = 0.0;
  for (std::uint32_t sample = 0U; sample < 24000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const m3::DetectorDecision decision = detector.process_sample(
        0.08 * std::sin(6.28318530717958647692 * frequency * time));
    for (std::size_t voice = 0U;
         decision.tuner_snapshot_ready &&
         voice < decision.tuner_snapshot.voice_count;
         ++voice) {
      const m3::TunerVoice& estimate = decision.tuner_snapshot.voices[voice];
      if (estimate.midi_note == 32U && estimate.string_index == 0U &&
          estimate.cents_valid) {
        found_valid_cents = true;
        observed_cents = static_cast<double>(estimate.cents_q8) / 256.0;
      }
    }
  }

  M3_EXPECT_TRUE(found_valid_cents);
  M3_EXPECT_NEAR(observed_cents, kDetuneCents, 6.0);
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
  feed_silence(detector, 16000U, transitions);

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

M3_TEST(native_detector_holds_a_96khz_fingerstyle_m3_triad_at_the_live_calibration) {
  constexpr double kSampleRate = 96000.0;
  constexpr std::array<std::uint8_t, 3> kNotes{32U, 40U, 48U};
  // These post-trim amplitudes model the user's current -11.6 dB input trim
  // and an uneven three-string fingerstyle attack.
  constexpr std::array<double, 3> kAmplitudes{0.070, 0.054, 0.043};
  constexpr std::uint32_t kSustainSamples = 67200U;  // 700 ms

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 3U;
  config.max_fret = 24U;
  config.sensitivity = 69U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {kNotes[0], kNotes[1], kNotes[2], 0U, 0U, 0U, 0U, 0U};
  lifecycle.voice_count = kNotes.size();
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());

  std::size_t stable_snapshot_count = 0U;
  std::size_t minimum_known_voices = kNotes.size();
  for (std::uint32_t index = 0U; index < kSustainSamples; ++index) {
    const double time = static_cast<double>(index) / kSampleRate;
    const double attack = std::min(1.0, time / 0.004);
    const double decay = std::exp(-1.1 * time);
    const double dropout = time >= 0.350 && time < 0.365 ? 0.08 : 1.0;
    double sample = 0.0;
    for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
      const double frequency = m3::midi_to_frequency(
          static_cast<double>(kNotes[voice]), 440.0);
      const double phase = 6.28318530717958647692 * frequency * time;
      const double string = std::sin(phase) + 0.28 * std::sin(2.0 * phase) +
                            0.12 * std::sin(3.0 * phase);
      sample += kAmplitudes[voice] * attack * decay * dropout * string;
    }
    const m3::DetectorDecision decision = detector.process_sample(sample);
    observe_chord(decision, lifecycle, index);
    if (!decision.tuner_snapshot_ready || time < 0.150) {
      continue;
    }
    std::size_t known_voices = 0U;
    for (std::size_t candidate = 0U;
         candidate < decision.tuner_snapshot.voice_count; ++candidate) {
      const m3::TunerVoice& voice =
          decision.tuner_snapshot.voices[candidate];
      const std::uint8_t note =
          voice.midi_note;
      bool known = false;
      for (const std::uint8_t expected : kNotes) {
        known = known || note == expected;
      }
      // Settling candidates are deliberately exposed for continuity but are
      // not allowed to create a new display lane. Only confirmed tracking
      // voices must belong to the played chord.
      if (voice.state == m3::TunerVoiceState::tracking) {
        M3_EXPECT_TRUE(known);
      }
      known_voices += known ? 1U : 0U;
    }
    minimum_known_voices = std::min(minimum_known_voices, known_voices);
    ++stable_snapshot_count;
  }

  M3_EXPECT_TRUE(stable_snapshot_count > 0U);
  M3_EXPECT_EQ(minimum_known_voices, kNotes.size());
  for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_FALSE(lifecycle.note_off[voice]);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);

  release_chord(detector, 36000U, lifecycle);
  for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
  }
}

M3_TEST(native_detector_tracks_all_eight_m3_open_strings_at_capacity) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  ChordLifecycle lifecycle;
  lifecycle.notes = {32U, 36U, 40U, 44U, 48U, 52U, 56U, 60U};
  lifecycle.voice_count = lifecycle.notes.size();
  lifecycle.first_on_sample.fill(std::numeric_limits<std::uint32_t>::max());
  feed_realistic_string_chord(detector, lifecycle.notes, 36000U, &lifecycle);
  // Response 81 deliberately holds vanished voices through brief fingerstyle
  // dropouts. Give the release path its full time-domain budget here.
  release_chord(detector, 16000U, lifecycle);

  for (std::size_t voice = 0U; voice < lifecycle.voice_count; ++voice) {
    M3_EXPECT_TRUE(lifecycle.note_on[voice]);
    M3_EXPECT_TRUE(lifecycle.note_off[voice]);
  }
  M3_EXPECT_FALSE(lifecycle.unexpected_on);
}

M3_TEST(native_detector_release_hold_is_time_based_at_supported_sample_rates) {
  constexpr std::array<double, 4> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::uint8_t kNote = 40U;
  constexpr double kTwoPi = 6.28318530717958647692;
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::MonophonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, 440.0);
    bool note_on = false;
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.60));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const auto decision = detector.process_sample(
          0.12 * std::sin(kTwoPi * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        note_on = note_on ||
                  (decision.transitions[event].kind ==
                       m3::TransitionKind::note_on &&
                   decision.transitions[event].note == kNote);
      }
    }
    M3_EXPECT_TRUE(note_on);

    std::uint32_t note_off_sample = std::numeric_limits<std::uint32_t>::max();
    const std::uint32_t silence =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.50));
    for (std::uint32_t sample = 0U; sample < silence; ++sample) {
      const auto decision = detector.process_sample(0.0);
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        if (decision.transitions[event].kind == m3::TransitionKind::note_off &&
            decision.transitions[event].note == kNote &&
            note_off_sample == std::numeric_limits<std::uint32_t>::max()) {
          note_off_sample = sample;
        }
      }
    }
    M3_EXPECT_TRUE(note_off_sample != std::numeric_limits<std::uint32_t>::max());
    if (note_off_sample != std::numeric_limits<std::uint32_t>::max()) {
      const double hold_seconds =
          static_cast<double>(note_off_sample) / sample_rate;
      M3_EXPECT_TRUE(hold_seconds >= 0.12);
      M3_EXPECT_TRUE(hold_seconds <= 0.45);
    }
  }
}

M3_TEST(native_detector_attack_hold_is_time_based_at_supported_sample_rates) {
  constexpr std::array<double, 4> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::uint8_t kNote = 40U;
  constexpr double kTwoPi = 6.28318530717958647692;
  double minimum_onset_seconds = std::numeric_limits<double>::max();
  double maximum_onset_seconds = 0.0;

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::MonophonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, 440.0);
    std::uint32_t note_on_sample = std::numeric_limits<std::uint32_t>::max();
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.12));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const auto decision = detector.process_sample(
          0.20 * std::sin(kTwoPi * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        if (decision.transitions[event].kind == m3::TransitionKind::note_on &&
            decision.transitions[event].note == kNote &&
            note_on_sample == std::numeric_limits<std::uint32_t>::max()) {
          note_on_sample = sample;
        }
      }
    }
    M3_EXPECT_TRUE(note_on_sample != std::numeric_limits<std::uint32_t>::max());
    if (note_on_sample != std::numeric_limits<std::uint32_t>::max()) {
      const double onset_seconds =
          static_cast<double>(note_on_sample) / sample_rate;
      minimum_onset_seconds = std::min(minimum_onset_seconds, onset_seconds);
      maximum_onset_seconds = std::max(maximum_onset_seconds, onset_seconds);
    }
  }

  M3_EXPECT_TRUE(maximum_onset_seconds - minimum_onset_seconds <= 0.002);
}

M3_TEST(native_detector_publishes_one_stable_physical_lane_per_m3_string) {
  constexpr double kSampleRate = 48000.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.max_fret = 0U;
  config.sensitivity = 75U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::TunerSnapshot final_snapshot;
  feed_realistic_string_chord(detector, m3::kM3OpenNotes, 36000U, nullptr,
                              &final_snapshot);

  std::array<bool, m3::kMaxVoices> found{};
  for (std::size_t voice = 0U; voice < final_snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = final_snapshot.voices[voice];
    M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
    if (observed.string_index < m3::kMaxVoices) {
      M3_EXPECT_FALSE(found[observed.string_index]);
      found[observed.string_index] = true;
      M3_EXPECT_EQ(observed.midi_note,
                   m3::kM3OpenNotes[observed.string_index]);
    }
  }
  for (const bool present : found) {
    M3_EXPECT_TRUE(present);
  }
}

M3_TEST(native_detector_keeps_realistic_fretted_chord_inside_each_string_range) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::array<std::uint8_t, m3::kMaxVoices> kFrettedNotes{
      39U, 42U, 45U, 48U, 51U, 54U, 57U, 60U};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  std::array<bool, m3::kMaxVoices> observed_string{};
  std::size_t checked_snapshots = 0U;
  for (std::uint32_t sample = 0U; sample < 48000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    double mixed = 0.0;
    for (std::size_t string = 0U; string < kFrettedNotes.size(); ++string) {
      mixed += realistic_string_sample(kFrettedNotes[string], string, time);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (!decision.tuner_snapshot_ready || sample < 24000U) {
      continue;
    }
    std::array<bool, m3::kMaxVoices> used_in_snapshot{};
    for (std::size_t voice = 0U;
         voice < decision.tuner_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = decision.tuner_snapshot.voices[voice];
      if (observed.state != m3::TunerVoiceState::tracking) {
        continue;
      }
      M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
      if (observed.string_index >= m3::kMaxVoices) {
        continue;
      }
      M3_EXPECT_FALSE(used_in_snapshot[observed.string_index]);
      used_in_snapshot[observed.string_index] = true;
      observed_string[observed.string_index] = true;
      const std::uint8_t open = m3::kM3OpenNotes[observed.string_index];
      M3_EXPECT_TRUE(observed.midi_note >= open);
      M3_EXPECT_TRUE(static_cast<std::uint16_t>(observed.midi_note) <=
                     static_cast<std::uint16_t>(open) + config.max_fret);
      // This staircase chord gives each modeled physical string one distinct
      // fret. Its lane must not migrate as relative phase and beating evolve.
      M3_EXPECT_EQ(observed.midi_note,
                   kFrettedNotes[observed.string_index]);
    }
    ++checked_snapshots;
  }

  M3_EXPECT_TRUE(checked_snapshots > 0U);
  for (const bool present : observed_string) {
    M3_EXPECT_TRUE(present);
  }
}

M3_TEST(native_detector_separates_a_calibrated_detuned_unison_into_string_lanes) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kUnisonNote = 48U;
  constexpr double kLowStringCents = -3.5;
  constexpr double kOpenStringCents = 4.2;
  constexpr std::array<double, 4> kSampleRates{
      44100.0, 48000.0, 88200.0, 96000.0};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.midi_routing = m3::MidiRouting::per_voice;
    config.lowest_note = 32U;
    config.highest_note = 59U;
    config.max_polyphony = 2U;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;

    m3::MonophonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    m3::StringCalibrationBank bank;
    set_measured_string_profile(bank, 0U, 16U, kLowStringCents, kLowProfile);
    set_measured_string_profile(bank, 4U, 0U, kOpenStringCents, kOpenProfile);
    detector.set_calibration_bank(bank);

    m3::TunerSnapshot final_snapshot;
    std::array<bool, m3::kMaxVoices> midi_note_on{};
    std::array<bool, m3::kMaxVoices> midi_note_off{};
    std::size_t evaluated_frames = 0U;
    std::size_t stable_frames = 0U;
    const double low_frequency =
        m3::midi_to_frequency(kUnisonNote + kLowStringCents / 100.0, 440.0);
    const double open_frequency =
        m3::midi_to_frequency(kUnisonNote + kOpenStringCents / 100.0, 440.0);
    const std::uint32_t sample_count =
        static_cast<std::uint32_t>(std::lround(1.5 * sample_rate));
    const std::uint32_t stable_start =
        static_cast<std::uint32_t>(std::lround(0.75 * sample_rate));
    for (std::uint32_t sample = 0U; sample < sample_count; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const double low_phase = 0.17 + kTwoPi * low_frequency * time;
      const double open_phase = 1.03 + kTwoPi * open_frequency * time;
      double mixed = 0.0;
      for (std::size_t harmonic = 0U; harmonic < kLowProfile.size();
           ++harmonic) {
        const double partial = static_cast<double>(harmonic + 1U);
        mixed += 0.055 * kLowProfile[harmonic] *
                 std::sin(partial * low_phase + 0.11 * partial);
        mixed += 0.050 * kOpenProfile[harmonic] *
                 std::sin(partial * open_phase - 0.07 * partial);
      }
      const m3::DetectorDecision decision = detector.process_sample(mixed);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.note != kUnisonNote ||
            transition.voice_id >= m3::kMaxVoices) {
          continue;
        }
        if (transition.kind == m3::TransitionKind::note_on) {
          midi_note_on[transition.voice_id] = true;
        }
      }
      if (!decision.tuner_snapshot_ready) {
        continue;
      }
      final_snapshot = decision.tuner_snapshot;
      if (sample < stable_start) {
        continue;
      }
      ++evaluated_frames;
      bool low_string = false;
      bool open_string = false;
      bool only_unison_note = true;
      for (std::size_t voice = 0U;
           voice < decision.tuner_snapshot.voice_count; ++voice) {
        const m3::TunerVoice& observed =
            decision.tuner_snapshot.voices[voice];
        only_unison_note =
            only_unison_note && observed.midi_note == kUnisonNote;
        low_string = low_string || observed.string_index == 0U;
        open_string = open_string || observed.string_index == 4U;
      }
      if (decision.tuner_snapshot.voice_count == 2U && only_unison_note &&
          low_string && open_string) {
        ++stable_frames;
      }
    }

    std::array<bool, m3::kMaxVoices> found{};
    for (std::size_t voice = 0U; voice < final_snapshot.voice_count; ++voice) {
      const m3::TunerVoice& observed = final_snapshot.voices[voice];
      M3_EXPECT_EQ(observed.midi_note, kUnisonNote);
      M3_EXPECT_TRUE(observed.string_index < m3::kMaxVoices);
      if (observed.string_index < m3::kMaxVoices) {
        found[observed.string_index] = true;
      }
    }
    M3_EXPECT_EQ(final_snapshot.voice_count, 2U);
    M3_EXPECT_TRUE(found[0U]);
    M3_EXPECT_TRUE(found[4U]);
    M3_EXPECT_TRUE(evaluated_frames > 0U);
    M3_EXPECT_TRUE(stable_frames * 10U >= evaluated_frames * 9U);
    M3_EXPECT_TRUE(midi_note_on[0U]);
    M3_EXPECT_TRUE(midi_note_on[4U]);

    const std::uint32_t release_samples =
        static_cast<std::uint32_t>(std::lround(0.60 * sample_rate));
    for (std::uint32_t sample = 0U; sample < release_samples; ++sample) {
      const m3::DetectorDecision decision = detector.process_sample(0.0);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.kind == m3::TransitionKind::note_off &&
            transition.note == kUnisonNote &&
            transition.voice_id < m3::kMaxVoices) {
          midi_note_off[transition.voice_id] = true;
        }
      }
    }
    M3_EXPECT_TRUE(midi_note_off[0U]);
    M3_EXPECT_TRUE(midi_note_off[4U]);
  }
}

M3_TEST(native_detector_does_not_split_one_calibrated_string_into_a_unison) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 48U;
  constexpr double kCents = 4.2;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 59U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 16U, -3.5, kLowProfile);
  set_measured_string_profile(bank, 4U, 0U, kCents, kOpenProfile);
  detector.set_calibration_bank(bank);

  m3::TunerSnapshot final_snapshot;
  const double frequency =
      m3::midi_to_frequency(kNote + kCents / 100.0, 440.0);
  for (std::uint32_t sample = 0U; sample < 72000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double phase = 1.03 + kTwoPi * frequency * time;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kOpenProfile.size();
         ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      mixed += 0.050 * kOpenProfile[harmonic] *
               std::sin(partial * phase - 0.07 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    if (decision.tuner_snapshot_ready) {
      final_snapshot = decision.tuner_snapshot;
    }
  }

  M3_EXPECT_EQ(final_snapshot.voice_count, 1U);
  if (final_snapshot.voice_count == 1U) {
    M3_EXPECT_EQ(final_snapshot.voices[0U].midi_note, kNote);
    M3_EXPECT_EQ(final_snapshot.voices[0U].string_index, 4U);
  }
}

M3_TEST(native_detector_single_routing_collapses_a_calibrated_unison_to_one_midi_note) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 48U;
  constexpr double kLowCents = -3.5;
  constexpr double kOpenCents = 4.2;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};

  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::single;
  config.lowest_note = 32U;
  config.highest_note = 59U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 0U, 16U, kLowCents, kLowProfile);
  set_measured_string_profile(bank, 4U, 0U, kOpenCents, kOpenProfile);
  detector.set_calibration_bank(bank);

  std::size_t note_ons = 0U;
  m3::TunerSnapshot final_snapshot;
  const double low_frequency =
      m3::midi_to_frequency(kNote + kLowCents / 100.0, 440.0);
  const double open_frequency =
      m3::midi_to_frequency(kNote + kOpenCents / 100.0, 440.0);
  for (std::uint32_t sample = 0U; sample < 72000U; ++sample) {
    const double time = static_cast<double>(sample) / kSampleRate;
    const double low_phase = 0.17 + kTwoPi * low_frequency * time;
    const double open_phase = 1.03 + kTwoPi * open_frequency * time;
    double mixed = 0.0;
    for (std::size_t harmonic = 0U; harmonic < kLowProfile.size();
         ++harmonic) {
      const double partial = static_cast<double>(harmonic + 1U);
      mixed += 0.055 * kLowProfile[harmonic] *
               std::sin(partial * low_phase + 0.11 * partial);
      mixed += 0.050 * kOpenProfile[harmonic] *
               std::sin(partial * open_phase - 0.07 * partial);
    }
    const m3::DetectorDecision decision = detector.process_sample(mixed);
    for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
      const m3::VoiceTransition& transition = decision.transitions[event];
      if (transition.kind == m3::TransitionKind::note_on &&
          transition.note == kNote) {
        ++note_ons;
        M3_EXPECT_EQ(transition.voice_id, m3::kUnassignedVoiceId);
      }
    }
    if (decision.tuner_snapshot_ready) {
      final_snapshot = decision.tuner_snapshot;
    }
  }
  M3_EXPECT_EQ(note_ons, 1U);
  M3_EXPECT_EQ(final_snapshot.voice_count, 2U);
}

M3_TEST(native_detector_learns_a_real_audio_open_to_24_and_back_sweep) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_TRUE(detector.begin_string_calibration(0U));
  double oscillator_phase = 0.0;
  feed_calibration_pitch(detector, m3::kM3OpenNotes[0U], 16000U,
                         &oscillator_phase);
  M3_EXPECT_EQ(detector.calibration_status().phase,
               m3::CalibrationSweepPhase::ascending);

  constexpr std::uint32_t kOneWaySweepSamples = 144000U;
  const double open_pitch = static_cast<double>(m3::kM3OpenNotes[0U]);
  feed_calibration_glide(detector, open_pitch, open_pitch + 24.0,
                         kOneWaySweepSamples, oscillator_phase);
  feed_calibration_glide(detector, open_pitch + 24.0, open_pitch,
                         kOneWaySweepSamples, oscillator_phase);
  // Hold the returned open string briefly so the bounded correlation window
  // can settle at the endpoint, matching the UI's completion cue.
  feed_calibration_pitch(detector, open_pitch, 8000U, &oscillator_phase);

  const m3::CalibrationSweepStatus status = detector.calibration_status();
  M3_EXPECT_EQ(status.phase, m3::CalibrationSweepPhase::complete);
  M3_EXPECT_EQ(status.highest_fret, 24U);
  M3_EXPECT_TRUE(status.measured_frets >= 18U);
  M3_EXPECT_TRUE(detector.calibration_bank().string_calibrated(0U));
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

M3_TEST(native_detector_does_not_activate_without_an_owned_m3_string_lane) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 33U;
  config.max_polyphony = 2U;
  config.max_fret = 1U;

  m3::MonophonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const m3::DetectorDecision decision =
      m3::MonophonicPitchDetectorTestAccess::
          attempt_reserved_string_activation(detector);

  M3_EXPECT_EQ(decision.transitions.size(), 0U);
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
