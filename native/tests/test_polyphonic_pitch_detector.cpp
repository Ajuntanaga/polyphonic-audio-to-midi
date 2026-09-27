#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdint>
#include <limits>

#include "m3/polyphonic_pitch_detector.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"
#include "test_support.hpp"

namespace m3 {

struct PolyphonicPitchDetectorTestAccess final {
  struct BeatProbe final {
    double beat_hz{};
    double hold_seconds{};
    bool valid{};
  };

  static BeatProbe beat_probe_for_interference(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t source_count) noexcept {
    detector.candidate_states_[candidate].active = true;
    detector.candidate_states_[candidate].assigned_string = 0U;
    detector.cells_[detector.cell_index(candidate, 0U)].enabled = true;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    const double decisions_per_second =
        detector.sample_rate_ / static_cast<double>(kDecisionQuantum);
    const std::uint32_t decisions =
        static_cast<std::uint32_t>(std::ceil(4.0 * decisions_per_second));
    for (std::uint32_t tick = 0U; tick < decisions; ++tick) {
      const double time = static_cast<double>(tick) / decisions_per_second;
      double real = std::cos(2.0 * 3.14159265358979323846 * -0.8 * time);
      double imaginary =
          std::sin(2.0 * 3.14159265358979323846 * -0.8 * time);
      if (source_count >= 2U) {
        real += 0.82 *
                std::cos(2.0 * 3.14159265358979323846 * 1.2 * time + 0.37);
        imaginary +=
            0.82 *
            std::sin(2.0 * 3.14159265358979323846 * 1.2 * time + 0.37);
      }
      if (source_count >= 3U) {
        real += 0.63 *
                std::cos(2.0 * 3.14159265358979323846 * 2.7 * time - 0.61);
        imaginary +=
            0.63 *
            std::sin(2.0 * 3.14159265358979323846 * 2.7 * time - 0.61);
      }
      auto& fundamental = detector.cells_[detector.cell_index(candidate, 0U)];
      fundamental.fast_real = real;
      fundamental.fast_imaginary = imaginary;
      detector.update_beat_evidence(selected);
    }
    const auto& beat = detector.beat_evidence_states_[candidate];
    return BeatProbe{
        beat.beat_hz,
        static_cast<double>(detector.unison_dropout_decisions(candidate)) /
            decisions_per_second,
        beat.valid};
  }

  static double harmonic_memory_after_note_on(
      PolyphonicPitchDetector& detector, std::size_t candidate) noexcept {
    for (double& energy : detector.harmonic_energy_memory_[candidate]) {
      energy = 1.0;
    }
    DetectorDecision decision;
    static_cast<void>(
        detector.append_candidate_note_on(decision, candidate, 100U));
    double total = 0.0;
    for (const double energy : detector.harmonic_energy_memory_[candidate]) {
      total += energy;
    }
    return total;
  }

  static std::uint8_t fresh_candidate_unison_mask(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t second) noexcept {
    detector.max_polyphony_ = 2U;
    detector.signal_samples_ = static_cast<std::uint32_t>(detector.sample_rate_);
    auto& state = detector.candidate_states_[candidate];
    state = {};
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    const auto& bank = detector.calibrator_.bank();
    const std::size_t note = detector.lowest_note_ + candidate;
    const auto* primary_point = bank.point(primary, note - kM3OpenNotes[primary]);
    const auto* second_point = bank.point(second, note - kM3OpenNotes[second]);
    if (primary_point == nullptr || second_point == nullptr) {
      return 0U;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      detector.harmonic_energy_memory_[candidate][harmonic] =
          0.5 * static_cast<double>(primary_point->harmonic_profile_q15[harmonic]) +
          0.5 * static_cast<double>(second_point->harmonic_profile_q15[harmonic]);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 8U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    return state.assigned_string_mask;
  }

  // Runs unison inference for an established calibrated unison candidate
  // while another voice is (optionally) coasting through its release hold on
  // `coasting_string`. Returns the unison candidate's string mask and the
  // resulting tuner snapshot.
  static std::uint8_t unison_mask_beside_coasting_voice(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t second, std::size_t coasting,
      std::uint8_t coasting_string, bool coasting_active,
      std::uint8_t max_polyphony, TunerSnapshot* snapshot = nullptr) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = static_cast<std::uint8_t>(1U << primary);
    auto& coast = detector.candidate_states_[coasting];
    coast.active = coasting_active;
    coast.release_ticks =
        static_cast<std::uint16_t>(coasting_active ? 1U : 0U);
    coast.assigned_string = coasting_string;
    coast.assigned_string_mask =
        static_cast<std::uint8_t>(1U << coasting_string);
    coast.midi_voice_mask = static_cast<std::uint8_t>(1U << coasting_string);
    const auto& bank = detector.calibrator_.bank();
    const std::size_t note = detector.lowest_note_ + candidate;
    const auto* primary_point = bank.point(primary, note - kM3OpenNotes[primary]);
    const auto* second_point = bank.point(second, note - kM3OpenNotes[second]);
    if (primary_point == nullptr || second_point == nullptr) {
      return 0U;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      detector.harmonic_energy_memory_[candidate][harmonic] =
          0.5 * static_cast<double>(primary_point->harmonic_profile_q15[harmonic]) +
          0.5 * static_cast<double>(second_point->harmonic_profile_q15[harmonic]);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    if (snapshot != nullptr) {
      std::array<double, kMaxCandidates> scores{};
      scores[candidate] = 1.0;
      DetectorDecision decision;
      detector.write_snapshot(decision, scores, selected, false);
      *snapshot = decision.tuner_snapshot;
    }
    return state.assigned_string_mask;
  }

  static TunerSnapshot snapshot_for_assigned_string_group(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t member_mask,
      std::uint8_t max_polyphony) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = 32U;
    state.assigned_string = primary;
    state.assigned_string_mask = member_mask;
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    std::array<double, kMaxCandidates> scores{};
    scores[candidate] = 1.0;
    DetectorDecision decision;
    detector.write_snapshot(decision, scores, selected, false);
    return decision.tuner_snapshot;
  }

  static std::uint8_t inferred_group_mask(
      PolyphonicPitchDetector& detector, std::size_t candidate,
      std::uint8_t primary, std::uint8_t source_members,
      std::uint8_t max_polyphony, TunerSnapshot* snapshot = nullptr) noexcept {
    detector.max_polyphony_ = max_polyphony;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    auto& state = detector.candidate_states_[candidate];
    state.active = true;
    state.age_ticks = std::numeric_limits<std::uint16_t>::max();
    state.assigned_string = primary;
    state.assigned_string_mask = static_cast<std::uint8_t>(1U << primary);
    state.midi_voice_mask = static_cast<std::uint8_t>(1U << primary);
    const auto& bank = detector.calibrator_.bank();
    const std::uint8_t note =
        static_cast<std::uint8_t>(detector.lowest_note_ + candidate);
    std::size_t source_count = 0U;
    for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
      if ((source_members & (1U << string)) != 0U) {
        ++source_count;
      }
    }
    if (source_count == 0U) {
      return 0U;
    }
    detector.beat_evidence_states_[candidate] = {};
    if (source_count >= 2U) {
      detector.beat_evidence_states_[candidate].beat_hz = 2.0;
      detector.beat_evidence_states_[candidate].accepted_cycles = 3U;
      detector.beat_evidence_states_[candidate].valid = true;
    }
    for (std::size_t harmonic = 0U;
         harmonic < detector.harmonic_energy_memory_[candidate].size();
         ++harmonic) {
      double energy = 0.0;
      for (std::size_t string = 0U; string < kM3OpenNotes.size(); ++string) {
        if ((source_members & (1U << string)) == 0U ||
            note < kM3OpenNotes[string]) {
          continue;
        }
        const auto* point = bank.point(string, note - kM3OpenNotes[string]);
        if (point == nullptr) {
          return 0U;
        }
        energy += static_cast<double>(point->harmonic_profile_q15[harmonic]);
      }
      detector.harmonic_energy_memory_[candidate][harmonic] =
          energy / static_cast<double>(source_count);
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    for (std::uint8_t decision = 0U; decision < 16U; ++decision) {
      detector.infer_m3_unison_strings(selected);
    }
    if (snapshot != nullptr) {
      std::array<double, kMaxCandidates> scores{};
      scores[candidate] = 1.0;
      DetectorDecision decision;
      detector.write_snapshot(decision, scores, selected, false);
      *snapshot = decision.tuner_snapshot;
    }
    return state.assigned_string_mask;
  }

  static std::array<std::uint8_t, 2U> legato_assignment_sequence(
      PolyphonicPitchDetector& detector) noexcept {
    constexpr std::size_t kReleasingCandidate = 12U;  // E3, string 3 open.
    constexpr std::size_t kReplacementCandidate = 13U;  // F3, fret 1.
    detector.candidate_states_ = {};
    detector.candidate_states_[kReleasingCandidate].active = true;
    detector.candidate_states_[kReleasingCandidate].assigned_string = 3U;
    detector.candidate_states_[kReleasingCandidate].assigned_string_mask =
        static_cast<std::uint8_t>(1U << 3U);

    std::array<bool, kMaxCandidates> selected{};
    selected[kReplacementCandidate] = true;
    detector.assign_m3_strings(selected);
    const std::uint8_t initial =
        detector.candidate_states_[kReplacementCandidate].assigned_string;

    detector.candidate_states_[kReleasingCandidate] = {};
    detector.candidate_states_[kReplacementCandidate].active = true;
    detector.candidate_states_[kReplacementCandidate].assigned_string_mask =
        static_cast<std::uint8_t>(1U << initial);
    detector.candidate_states_[kReplacementCandidate].midi_voice_mask =
        static_cast<std::uint8_t>(1U << initial);
    detector.assign_m3_strings(selected);
    return {initial,
            detector.candidate_states_[kReplacementCandidate].assigned_string};
  }

  static std::uint8_t assigned_string_for_profile(
      PolyphonicPitchDetector& detector, std::uint8_t note,
      const std::array<double, kCalibrationHarmonicCount>& amplitudes) noexcept {
    if (note < detector.lowest_note_) {
      return kUnassignedTunerString;
    }
    const std::size_t candidate = note - detector.lowest_note_;
    if (candidate >= static_cast<std::size_t>(detector.candidate_count_)) {
      return kUnassignedTunerString;
    }
    for (std::size_t harmonic = 0U; harmonic < amplitudes.size(); ++harmonic) {
      auto& cell = detector.cells_[detector.cell_index(candidate, harmonic)];
      cell.enabled = true;
      cell.fast_real = amplitudes[harmonic];
      cell.fast_imaginary = 0.0;
    }
    std::array<bool, kMaxCandidates> selected{};
    selected[candidate] = true;
    detector.assign_m3_strings(selected);
    return detector.candidate_states_[candidate].assigned_string;
  }

  static std::array<TunerVoice, 3U> snapshot_retention_sequence(
      PolyphonicPitchDetector& detector) noexcept {
    detector.candidate_count_ = 3U;
    detector.lowest_note_ = 39U;
    detector.max_polyphony_ = 1U;
    detector.profile_mode_ = ProfileMode::general;
    detector.fast_energy_ = 1.0;
    detector.candidate_states_ = {};
    detector.candidate_states_[1U].active = true;
    detector.phase_cents_states_[1U].cents = 7.5;
    detector.phase_cents_states_[1U].valid = true;

    std::array<double, kMaxCandidates> scores{};
    std::array<bool, kMaxCandidates> selected{};
    selected[1U] = true;
    scores[0U] = 0.60;
    scores[1U] = 1.00;
    scores[2U] = 0.40;
    DetectorDecision valid;
    detector.write_snapshot(valid, scores, selected, false);

    detector.phase_cents_states_[1U].valid = false;
    scores[0U] = 1.00;
    scores[1U] = 0.60;
    scores[2U] = 0.60;
    DetectorDecision invalid;
    detector.write_snapshot(invalid, scores, selected, false);

    selected[1U] = false;
    detector.candidate_states_[1U].release_ticks = 1U;
    DetectorDecision coast;
    detector.write_snapshot(coast, scores, selected, false);
    return {valid.tuner_snapshot.voices[0U],
            invalid.tuner_snapshot.voices[0U],
            coast.tuner_snapshot.voices[0U]};
  }

  static DetectorDecision attempt_reserved_string_activation(
      PolyphonicPitchDetector& detector) noexcept {
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

M3_TEST(native_detector_estimates_two_string_beat_period_from_long_envelope) {
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                                96000.0};
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 60U;
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));

    const auto beat =
        m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
            detector, 16U, 2U);
    M3_EXPECT_TRUE(beat.valid);
    M3_EXPECT_NEAR(beat.beat_hz, 2.0, 0.15);
    M3_EXPECT_TRUE(beat.hold_seconds >= 0.70);
  }
}

M3_TEST(native_detector_retains_beat_evidence_for_three_string_interference) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto beat =
      m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
          detector, 16U, 3U);
  M3_EXPECT_TRUE(beat.valid);
  M3_EXPECT_TRUE(beat.beat_hz >= 0.25);
  M3_EXPECT_TRUE(beat.beat_hz <= 12.0);
  M3_EXPECT_TRUE(beat.hold_seconds > 0.45);
}

M3_TEST(native_detector_does_not_invent_beat_evidence_for_one_steady_string) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const auto beat =
      m3::PolyphonicPitchDetectorTestAccess::beat_probe_for_interference(
          detector, 16U, 1U);
  M3_EXPECT_FALSE(beat.valid);
  M3_EXPECT_NEAR(beat.beat_hz, 0.0, 0.0);
  M3_EXPECT_NEAR(beat.hold_seconds, 0.45, 0.002);
}

namespace {

void feed_tone(m3::PolyphonicPitchDetector& detector, std::uint8_t note,
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

void feed_silence(m3::PolyphonicPitchDetector& detector,
                  std::uint32_t samples,
                  m3::TickTransitions& transitions) noexcept {
  for (std::uint32_t index = 0; index < samples; ++index) {
    const m3::DetectorDecision decision = detector.process_sample(0.0);
    for (std::size_t event = 0; event < decision.transitions.size(); ++event) {
      M3_EXPECT_TRUE(transitions.push_back(decision.transitions[event]));
    }
  }
}

void feed_calibration_pitch(m3::PolyphonicPitchDetector& detector,
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

void feed_calibration_glide(m3::PolyphonicPitchDetector& detector,
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

void feed_dyad(m3::PolyphonicPitchDetector& detector, std::uint8_t low_note,
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

void release_dyad(m3::PolyphonicPitchDetector& detector,
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
    m3::PolyphonicPitchDetector& detector,
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

void feed_chord(m3::PolyphonicPitchDetector& detector,
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
    m3::PolyphonicPitchDetector& detector,
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

void release_chord(m3::PolyphonicPitchDetector& detector,
                   std::uint32_t samples, ChordLifecycle& lifecycle) noexcept {
  for (std::uint32_t index = 0U; index < samples; ++index) {
    observe_chord(detector.process_sample(0.0), lifecycle, index);
  }
}

}  // namespace

M3_TEST(native_polyphonic_detector_tracks_low_eight_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 48U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_reports_settled_cents_within_one_cent_at_48_and_96khz) {
  constexpr std::array<double, 2U> kSampleRates{48000.0, 96000.0};
  constexpr std::array<std::uint8_t, 4U> kNotes{32U, 40U, 48U, 60U};
  constexpr std::array<double, 5U> kOffsets{-40.0, -20.0, 0.0, 20.0, 40.0};
  double worst_error = 0.0;
  double worst_rate = 0.0;
  double worst_offset = 0.0;
  std::uint8_t worst_note = 0U;
  bool observed_every_case = true;

  for (const double sample_rate : kSampleRates) {
    for (const std::uint8_t note : kNotes) {
      for (const double offset : kOffsets) {
        m3::PersistentConfig config;
        config.profile_mode = m3::ProfileMode::m3;
        config.lowest_note = 32U;
        config.highest_note = 60U;
        config.max_polyphony = 1U;
        config.max_fret = 24U;
        config.sensitivity = 69U;
        config.response = 81U;

        m3::PolyphonicPitchDetector detector;
        M3_EXPECT_TRUE(detector.configure(sample_rate, config));
        const double frequency = m3::midi_to_frequency(
            static_cast<double>(note) + offset / 100.0, config.a4_hz);
        const std::uint32_t samples = static_cast<std::uint32_t>(
            std::lround(0.25 * sample_rate));
        bool observed = false;
        double measured = 0.0;
        for (std::uint32_t sample = 0U; sample < samples; ++sample) {
          const double time = static_cast<double>(sample) / sample_rate;
          const m3::DetectorDecision decision = detector.process_sample(
              0.12 * std::sin(6.28318530717958647692 * frequency * time));
          for (std::size_t voice = 0U;
               decision.tuner_snapshot_ready &&
               voice < decision.tuner_snapshot.voice_count;
               ++voice) {
            const m3::TunerVoice& estimate =
                decision.tuner_snapshot.voices[voice];
            if (estimate.midi_note == note && estimate.cents_valid &&
                estimate.state == m3::TunerVoiceState::tracking) {
              observed = true;
              measured = static_cast<double>(estimate.cents_q8) / 256.0;
            }
          }
        }
        observed_every_case = observed_every_case && observed;
        if (observed) {
          const double error = std::abs(measured - offset);
          if (error > worst_error) {
            worst_error = error;
            worst_rate = sample_rate;
            worst_note = note;
            worst_offset = offset;
          }
        }
      }
    }
  }

  if (worst_error > 1.0) {
    std::fprintf(stderr,
                 "worst settled cents error %.3f at %.0f Hz note %u offset %.1f\n",
                 worst_error, worst_rate, static_cast<unsigned>(worst_note),
                 worst_offset);
  }
  M3_EXPECT_TRUE(observed_every_case);
  M3_EXPECT_NEAR(worst_error, 0.0, 1.0);
}

M3_TEST(native_detector_never_labels_an_inaccurate_attack_cents_value_valid) {
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<std::uint8_t, 3U> kNotes{32U, 48U, 60U};
  constexpr std::array<double, 3U> kOffsets{-20.0, 0.0, 20.0};
  double worst_valid_error = 0.0;
  double worst_rate = 0.0;
  double worst_offset = 0.0;
  double worst_measured = 0.0;
  std::uint8_t worst_note = 0U;
  std::uint32_t worst_sample = 0U;
  bool observed_every_case = true;

  for (const double sample_rate : kSampleRates) {
    for (const std::uint8_t note : kNotes) {
      for (const double offset : kOffsets) {
        m3::PersistentConfig config;
        config.profile_mode = m3::ProfileMode::m3;
        config.lowest_note = 32U;
        config.highest_note = 60U;
        config.max_polyphony = 1U;
        config.max_fret = 24U;
        config.sensitivity = 69U;
        config.response = 81U;

        m3::PolyphonicPitchDetector detector;
        M3_EXPECT_TRUE(detector.configure(sample_rate, config));
        const double frequency = m3::midi_to_frequency(
            static_cast<double>(note) + offset / 100.0, config.a4_hz);
        const std::uint32_t samples = static_cast<std::uint32_t>(
            std::lround(0.22 * sample_rate));
        bool observed_valid = false;
        for (std::uint32_t sample = 0U; sample < samples; ++sample) {
          const double time = static_cast<double>(sample) / sample_rate;
          const m3::DetectorDecision decision = detector.process_sample(
              0.12 * std::sin(6.28318530717958647692 * frequency * time));
          for (std::size_t voice = 0U;
               decision.tuner_snapshot_ready &&
               voice < decision.tuner_snapshot.voice_count;
               ++voice) {
            const m3::TunerVoice& estimate =
                decision.tuner_snapshot.voices[voice];
            if (estimate.midi_note != note || !estimate.cents_valid ||
                estimate.state != m3::TunerVoiceState::tracking) {
              continue;
            }
            observed_valid = true;
            const double measured =
                static_cast<double>(estimate.cents_q8) / 256.0;
            const double error = std::abs(measured - offset);
            if (error > worst_valid_error) {
              worst_valid_error = error;
              worst_rate = sample_rate;
              worst_note = note;
              worst_offset = offset;
              worst_measured = measured;
              worst_sample = sample;
            }
          }
        }
        observed_every_case = observed_every_case && observed_valid;
      }
    }
  }

  if (worst_valid_error > 2.0) {
    std::fprintf(stderr,
                 "worst attack cents error %.3f at %.0f Hz note %u "
                 "offset %.1f measured %.3f sample %u\n",
                 worst_valid_error, worst_rate,
                 static_cast<unsigned>(worst_note), worst_offset,
                 worst_measured, static_cast<unsigned>(worst_sample));
  }
  M3_EXPECT_TRUE(observed_every_case);
  M3_EXPECT_NEAR(worst_valid_error, 0.0, 2.0);
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

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_polyphonic_detector_tracks_highest_open_string_tone_and_releases) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_tracks_the_twenty_fourth_fret_c6_range_boundary) {
  constexpr std::uint8_t kNote = 84U;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = kNote;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    const double frequency = m3::midi_to_frequency(kNote, config.a4_hz);
    bool note_on = false;
    bool tracked = false;
    const std::uint32_t samples = static_cast<std::uint32_t>(
        std::lround(0.30 * sample_rate));
    for (std::uint32_t sample = 0U; sample < samples; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const m3::DetectorDecision decision = detector.process_sample(
          0.12 * std::sin(6.28318530717958647692 * frequency * time));
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        note_on = note_on ||
                  (decision.transitions[event].kind ==
                       m3::TransitionKind::note_on &&
                   decision.transitions[event].note == kNote);
      }
      for (std::size_t voice = 0U;
           decision.tuner_snapshot_ready &&
           voice < decision.tuner_snapshot.voice_count;
           ++voice) {
        const m3::TunerVoice& estimate =
            decision.tuner_snapshot.voices[voice];
        tracked = tracked ||
                  (estimate.state == m3::TunerVoiceState::tracking &&
                   estimate.midi_note == kNote && estimate.string_index == 7U);
      }
    }
    M3_EXPECT_TRUE(note_on);
    M3_EXPECT_TRUE(tracked);
  }
}

M3_TEST(native_detector_does_not_expand_one_tone_into_the_polyphony_limit) {
  m3::PersistentConfig config;
  config.lowest_note = 36U;
  config.highest_note = 60U;
  config.max_polyphony = 8U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_distinguishes_a_bright_low_string_from_a_real_octave) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kLowNote = 40U;
  constexpr std::uint8_t kOctaveNote = 52U;
  const double low_frequency = m3::midi_to_frequency(kLowNote, 440.0);
  const double octave_frequency =
      m3::midi_to_frequency(static_cast<double>(kOctaveNote) + 0.04, 440.0);
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  const auto exercise = [&](bool add_independent_octave) noexcept {
    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    bool low_on = false;
    bool octave_on = false;
    bool unexpected = false;
    for (std::uint32_t sample = 0U; sample < 36000U; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      const double phase = 6.28318530717958647692 * low_frequency * time;
      double value = 0.10 * std::sin(phase + 0.13) +
                     0.075 * std::sin(2.0 * phase - 0.31) +
                     0.045 * std::sin(3.0 * phase + 0.47) +
                     0.025 * std::sin(4.0 * phase - 0.19);
      if (add_independent_octave) {
        const double octave_phase =
            6.28318530717958647692 * octave_frequency * time;
        value += 0.070 * std::sin(octave_phase + 1.17) +
                 0.030 * std::sin(2.0 * octave_phase - 0.83) +
                 0.015 * std::sin(3.0 * octave_phase + 0.62);
      }
      const m3::DetectorDecision decision = detector.process_sample(value);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        if (decision.transitions[event].kind !=
            m3::TransitionKind::note_on) {
          continue;
        }
        low_on = low_on || decision.transitions[event].note == kLowNote;
        octave_on = octave_on ||
                    decision.transitions[event].note == kOctaveNote;
        unexpected = unexpected ||
                     (decision.transitions[event].note != kLowNote &&
                      decision.transitions[event].note != kOctaveNote);
      }
    }
    return std::array<bool, 3U>{low_on, octave_on, unexpected};
  };

  const auto bright_low = exercise(false);
  M3_EXPECT_TRUE(bright_low[0U]);
  M3_EXPECT_FALSE(bright_low[1U]);
  M3_EXPECT_FALSE(bright_low[2U]);

  const auto real_octave = exercise(true);
  M3_EXPECT_TRUE(real_octave[0U]);
  M3_EXPECT_TRUE(real_octave[1U]);
  M3_EXPECT_FALSE(real_octave[2U]);
}

M3_TEST(native_detector_keeps_an_uneven_major_seventh_as_two_voices) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 2U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector m3_detector;
  M3_EXPECT_TRUE(m3_detector.configure(48000.0, m3_config));
  m3::TickTransitions m3_transitions;
  feed_tone(m3_detector, 33U, 30000U, m3_transitions);
  feed_silence(m3_detector, 8000U, m3_transitions);
  M3_EXPECT_EQ(m3_transitions.size(), 0U);

  m3::PersistentConfig general_config = m3_config;
  general_config.profile_mode = m3::ProfileMode::general;
  m3::PolyphonicPitchDetector general_detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_keeps_a_live_legato_replacement_on_its_started_string) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const auto assignments =
      m3::PolyphonicPitchDetectorTestAccess::legato_assignment_sequence(
          detector);
  M3_EXPECT_EQ(assignments[0U], 2U);
  M3_EXPECT_EQ(assignments[1U], assignments[0U]);
}

M3_TEST(native_detector_restarts_the_four_voice_evidence_gate_after_silence) {
  m3::PersistentConfig config;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 4U;
  config.sensitivity = 75U;
  config.response = 25U;

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

    m3::PolyphonicPitchDetector detector;
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
    bool saw_coasting = false;
    const std::uint32_t silence =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.50));
    for (std::uint32_t sample = 0U; sample < silence; ++sample) {
      const auto decision = detector.process_sample(0.0);
      if (decision.tuner_snapshot_ready &&
          decision.tuner_snapshot.voice_count == 1U &&
          decision.tuner_snapshot.voices[0U].state ==
              m3::TunerVoiceState::coasting) {
        saw_coasting = true;
        M3_EXPECT_TRUE(decision.tuner_snapshot.voices[0U].cents_valid);
      }
      for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
        if (decision.transitions[event].kind == m3::TransitionKind::note_off &&
            decision.transitions[event].note == kNote &&
            note_off_sample == std::numeric_limits<std::uint32_t>::max()) {
          note_off_sample = sample;
        }
      }
    }
    M3_EXPECT_TRUE(saw_coasting);
    M3_EXPECT_TRUE(note_off_sample != std::numeric_limits<std::uint32_t>::max());
    if (note_off_sample != std::numeric_limits<std::uint32_t>::max()) {
      const double hold_seconds =
          static_cast<double>(note_off_sample) / sample_rate;
      M3_EXPECT_TRUE(hold_seconds >= 0.12);
      M3_EXPECT_TRUE(hold_seconds <= 0.45);
    }
  }
}

M3_TEST(native_detector_does_not_release_a_naturally_decaying_note_above_the_floor) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr double kInitialAmplitude = 0.20;
  constexpr std::uint8_t kSensitivity = 69U;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<double, 4U> kDecayRatesDbPerSecond{20.0, 30.0, 40.0,
                                                         60.0};
  const double floor_db =
      -70.0 + 0.20 * static_cast<double>(100U - kSensitivity);
  const double floor_amplitude = std::pow(10.0, floor_db / 20.0);

  for (const double sample_rate : kSampleRates) {
    for (const double decay_rate : kDecayRatesDbPerSecond) {
      m3::PersistentConfig config;
      config.profile_mode = m3::ProfileMode::m3;
      config.lowest_note = 32U;
      config.highest_note = 84U;
      config.max_polyphony = 1U;
      config.max_fret = 24U;
      config.sensitivity = kSensitivity;
      config.response = 81U;

      m3::PolyphonicPitchDetector detector;
      M3_EXPECT_TRUE(detector.configure(sample_rate, config));
      const double frequency = m3::midi_to_frequency(kNote, 440.0);
      double phase = 0.0;
      const double phase_step = kTwoPi * frequency / sample_rate;
      bool note_on = false;
      bool early_note_off = false;
      const std::uint32_t settle_samples =
          static_cast<std::uint32_t>(0.30 * sample_rate);
      for (std::uint32_t sample = 0U; sample < settle_samples; ++sample) {
        const auto decision =
            detector.process_sample(kInitialAmplitude * std::sin(phase));
        phase = std::fmod(phase + phase_step, kTwoPi);
        for (std::size_t event = 0U; event < decision.transitions.size();
             ++event) {
          note_on = note_on ||
                    (decision.transitions[event].kind ==
                         m3::TransitionKind::note_on &&
                     decision.transitions[event].note == kNote);
        }
      }
      M3_EXPECT_TRUE(note_on);

      for (std::uint32_t sample = 0U;; ++sample) {
        const double time = static_cast<double>(sample) / sample_rate;
        const double amplitude =
            kInitialAmplitude * std::pow(10.0, -decay_rate * time / 20.0);
        if (amplitude < 4.0 * floor_amplitude) {
          break;
        }
        const auto decision = detector.process_sample(amplitude * std::sin(phase));
        phase = std::fmod(phase + phase_step, kTwoPi);
        for (std::size_t event = 0U; event < decision.transitions.size();
             ++event) {
          early_note_off = early_note_off ||
                           (decision.transitions[event].kind ==
                                m3::TransitionKind::note_off &&
                            decision.transitions[event].note == kNote);
        }
      }
      M3_EXPECT_FALSE(early_note_off);
    }
  }
}

M3_TEST(native_detector_coasts_the_last_valid_tuner_pitch_through_a_short_dropout) {
  constexpr double kSampleRate = 48000.0;
  constexpr std::uint8_t kNote = 40U;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
  const double frequency = m3::midi_to_frequency(kNote + 0.07, 440.0);
  m3::TunerVoice last_tracking;
  bool tracked = false;
  for (std::uint32_t sample = 0U; sample < 24000U; ++sample) {
    const double value = 0.20 * std::sin(
        6.28318530717958647692 * frequency * sample / kSampleRate);
    const m3::DetectorDecision decision = detector.process_sample(value);
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::tracking &&
        decision.tuner_snapshot.voices[0U].cents_valid) {
      last_tracking = decision.tuner_snapshot.voices[0U];
      tracked = true;
    }
  }
  M3_EXPECT_TRUE(tracked);

  bool coasted = false;
  bool note_off = false;
  for (std::uint32_t sample = 0U; sample < 12000U && !coasted; ++sample) {
    const m3::DetectorDecision decision = detector.process_sample(0.0);
    for (std::size_t event = 0U; event < decision.transitions.size(); ++event) {
      note_off = note_off ||
                 decision.transitions[event].kind ==
                     m3::TransitionKind::note_off;
    }
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::tracking &&
        decision.tuner_snapshot.voices[0U].cents_valid) {
      last_tracking = decision.tuner_snapshot.voices[0U];
    }
    if (decision.tuner_snapshot_ready &&
        decision.tuner_snapshot.voice_count == 1U &&
        decision.tuner_snapshot.voices[0U].state ==
            m3::TunerVoiceState::coasting) {
      const m3::TunerVoice& coast = decision.tuner_snapshot.voices[0U];
      coasted = true;
      M3_EXPECT_EQ(coast.midi_note, last_tracking.midi_note);
      M3_EXPECT_TRUE(coast.cents_valid);
      M3_EXPECT_EQ(coast.cents_q8, last_tracking.cents_q8);
      M3_EXPECT_TRUE(coast.confidence_q15 <= last_tracking.confidence_q15);
    }
  }
  M3_EXPECT_TRUE(coasted);
  M3_EXPECT_FALSE(note_off);
}

M3_TEST(native_detector_does_not_overwrite_retained_cents_with_an_invalid_frame) {
  m3::PolyphonicPitchDetector detector;
  const auto voices =
      m3::PolyphonicPitchDetectorTestAccess::snapshot_retention_sequence(
          detector);
  M3_EXPECT_TRUE(voices[0U].cents_valid);
  M3_EXPECT_EQ(voices[0U].state, m3::TunerVoiceState::tracking);
  M3_EXPECT_TRUE(voices[1U].cents_valid);
  M3_EXPECT_EQ(voices[1U].state, m3::TunerVoiceState::tracking);
  M3_EXPECT_EQ(voices[1U].cents_q8, voices[0U].cents_q8);
  M3_EXPECT_TRUE(voices[2U].cents_valid);
  M3_EXPECT_EQ(voices[2U].state, m3::TunerVoiceState::coasting);
  M3_EXPECT_EQ(voices[2U].cents_q8, voices[0U].cents_q8);
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

    m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_tracks_a_stiff_string_chord_through_sympathetic_leakage) {
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::array<double, 4U> kSampleRates{44100.0, 48000.0, 88200.0,
                                               96000.0};
  constexpr std::array<std::uint8_t, 4U> kNotes{32U, 40U, 48U, 60U};
  constexpr std::array<double, 4U> kCents{-3.8, 2.1, -1.7, 4.4};
  constexpr std::array<double, 4U> kInharmonicity{0.00004, 0.00007, 0.00011,
                                                 0.00016};
  constexpr std::array<double, 4U> kAmplitude{0.034, 0.031, 0.029, 0.026};
  constexpr std::array<double, 6U> kPartialAmplitude{1.0, 0.31, 0.17, 0.10,
                                                     0.06, 0.035};

  for (const double sample_rate : kSampleRates) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 84U;
    config.max_polyphony = 4U;
    config.max_fret = 24U;
    config.sensitivity = 69U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(sample_rate, config));
    std::array<bool, kNotes.size()> note_on{};
    bool unexpected_on = false;
    std::size_t stable_frames = 0U;
    std::size_t evaluated_frames = 0U;
    const std::uint32_t sustain =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.65));
    const std::uint32_t stable_start =
        static_cast<std::uint32_t>(std::lround(sample_rate * 0.35));
    for (std::uint32_t sample = 0U; sample < sustain; ++sample) {
      const double time = static_cast<double>(sample) / sample_rate;
      const double attack = std::min(1.0, time / 0.006);
      const double decay = std::exp(-0.45 * time);
      double mixed = 0.0;
      for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
        const double fundamental = m3::midi_to_frequency(
            static_cast<double>(kNotes[voice]) + kCents[voice] / 100.0,
            440.0);
        const double base_stretch = std::sqrt(1.0 + kInharmonicity[voice]);
        for (std::size_t partial = 0U; partial < kPartialAmplitude.size();
             ++partial) {
          const double order = static_cast<double>(partial + 1U);
          const double stretch =
              std::sqrt(1.0 + kInharmonicity[voice] * order * order) /
              base_stretch;
          const double phase =
              0.29 * static_cast<double>(voice + 1U) +
              0.11 * order + kTwoPi * fundamental * order * stretch * time;
          mixed += kAmplitude[voice] * kPartialAmplitude[partial] * attack *
                   decay * std::sin(phase);
        }
      }
      // Weak resonances from two unsounded strings model body/pickup leakage.
      // They are real energy, but not strong independent note evidence.
      mixed += 0.0025 * attack *
               std::sin(kTwoPi * m3::midi_to_frequency(36.0, 440.0) * time +
                        0.83);
      mixed += 0.0020 * attack *
               std::sin(kTwoPi * m3::midi_to_frequency(56.0, 440.0) * time +
                        1.37);

      const m3::DetectorDecision decision = detector.process_sample(mixed);
      for (std::size_t event = 0U; event < decision.transitions.size();
           ++event) {
        const m3::VoiceTransition& transition = decision.transitions[event];
        if (transition.kind != m3::TransitionKind::note_on) {
          continue;
        }
        bool expected = false;
        for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
          if (transition.note == kNotes[voice]) {
            note_on[voice] = true;
            expected = true;
          }
        }
        unexpected_on = unexpected_on || !expected;
      }
      if (!decision.tuner_snapshot_ready || sample < stable_start) {
        continue;
      }
      ++evaluated_frames;
      std::array<bool, kNotes.size()> found{};
      bool only_expected = true;
      for (std::size_t observed = 0U;
           observed < decision.tuner_snapshot.voice_count; ++observed) {
        const std::uint8_t note =
            decision.tuner_snapshot.voices[observed].midi_note;
        bool expected = false;
        for (std::size_t voice = 0U; voice < kNotes.size(); ++voice) {
          if (note == kNotes[voice]) {
            found[voice] = true;
            expected = true;
          }
        }
        only_expected = only_expected && expected;
      }
      if (only_expected &&
          std::all_of(found.begin(), found.end(), [](bool value) {
            return value;
          })) {
        ++stable_frames;
      }
    }
    for (const bool started : note_on) {
      M3_EXPECT_TRUE(started);
    }
    M3_EXPECT_FALSE(unexpected_on);
    M3_EXPECT_TRUE(evaluated_frames > 0U);
    M3_EXPECT_TRUE(stable_frames * 10U >= evaluated_frames * 9U);
  }
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

    m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_keeps_a_calibrated_harmonic_fingerprint_when_detuned) {
  constexpr double kSampleRate = 48000.0;
  constexpr double kTwoPi = 6.28318530717958647692;
  constexpr std::uint8_t kNote = 60U;
  constexpr std::array<double, 3U> kOffsetsCents{0.0, -10.0, 10.0};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kBrightProfile{
      1.00, 1.00, 1.00, 1.00, 0.00, 0.00};
  // This darker lane closely matches the uncorrected fixed-Hz resonator
  // response of the same bright source at ten cents off centre.
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kDarkProfile{
      1.00, 0.00, 0.00, 0.00, 0.00, 0.00};

  for (const double cents : kOffsetsCents) {
    m3::PersistentConfig config;
    config.profile_mode = m3::ProfileMode::m3;
    config.lowest_note = 32U;
    config.highest_note = 84U;
    config.max_polyphony = 1U;
    config.max_fret = 24U;
    config.sensitivity = 70U;
    config.response = 81U;

    m3::PolyphonicPitchDetector detector;
    M3_EXPECT_TRUE(detector.configure(kSampleRate, config));
    m3::StringCalibrationBank bank;
    set_measured_string_profile(bank, 6U, 4U, 0.0, kBrightProfile);
    set_measured_string_profile(bank, 7U, 0U, 0.0, kDarkProfile);
    detector.set_calibration_bank(bank);

    const double frequency =
        m3::midi_to_frequency(static_cast<double>(kNote) + cents / 100.0,
                              440.0);
    std::uint8_t observed_string = m3::kUnassignedTunerString;
    bool tracked = false;
    std::uint32_t settled_tracking_frames = 0U;
    std::uint32_t settled_correct_frames = 0U;
    for (std::uint32_t sample = 0U; sample < 48000U; ++sample) {
      const double time = static_cast<double>(sample) / kSampleRate;
      const double phase = kTwoPi * frequency * time;
      const double value =
          0.050 * (std::sin(phase) + std::sin(2.0 * phase + 0.23) +
                   std::sin(3.0 * phase - 0.41) +
                   std::sin(4.0 * phase + 0.67));
      const m3::DetectorDecision decision = detector.process_sample(value);
      if (!decision.tuner_snapshot_ready) {
        continue;
      }
      for (std::size_t voice = 0U;
           voice < decision.tuner_snapshot.voice_count; ++voice) {
        const m3::TunerVoice& observed =
            decision.tuner_snapshot.voices[voice];
        if (observed.state == m3::TunerVoiceState::tracking &&
            observed.midi_note == kNote) {
          tracked = true;
          observed_string = observed.string_index;
          if (sample >= 12000U) {
            ++settled_tracking_frames;
            if (observed.string_index == 6U) {
              ++settled_correct_frames;
            }
          }
        }
      }
    }
    M3_EXPECT_TRUE(tracked);
    M3_EXPECT_EQ(observed_string, 6U);
    M3_EXPECT_TRUE(settled_tracking_frames > 0U);
    M3_EXPECT_TRUE(settled_correct_frames * 10U >=
                   settled_tracking_frames * 9U);
  }
}

M3_TEST(native_detector_clears_prior_harmonic_memory_when_a_note_activates) {
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));

  const double remaining =
      m3::PolyphonicPitchDetectorTestAccess::harmonic_memory_after_note_on(
          detector, 8U);
  M3_EXPECT_NEAR(remaining, 0.0, 0.0);
}

M3_TEST(native_detector_does_not_prearm_a_fresh_unison_from_global_signal_age) {
  constexpr std::uint8_t kNote = 48U;
  constexpr std::uint8_t kPrimaryString = 4U;
  constexpr std::uint8_t kSecondString = 0U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 2U;
  config.max_fret = 24U;
  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, kPrimaryString, 0U, 4.2, kOpenProfile);
  set_measured_string_profile(bank, kSecondString, 16U, -3.5, kLowProfile);
  detector.set_calibration_bank(bank);

  const std::uint8_t mask =
      m3::PolyphonicPitchDetectorTestAccess::fresh_candidate_unison_mask(
          detector, kNote - config.lowest_note, kPrimaryString,
          kSecondString);
  M3_EXPECT_EQ(mask, static_cast<std::uint8_t>(1U << kPrimaryString));
}

namespace {

constexpr std::uint8_t kSharedUnisonNote = 48U;
constexpr std::uint8_t kSharedUnisonPrimary = 4U;  // C3 open.
constexpr std::uint8_t kSharedUnisonSecond = 0U;   // G#1 string, fret 16.

void configure_calibrated_unison(m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kLowProfile{
      1.00, 0.16, 0.07, 0.03, 0.01, 0.00};
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kOpenProfile{
      0.68, 0.62, 0.24, 0.08, 0.02, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 3U;
  config.max_fret = 24U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, kSharedUnisonPrimary, 0U, 4.2,
                              kOpenProfile);
  set_measured_string_profile(bank, kSharedUnisonSecond, 16U, -3.5,
                              kLowProfile);
  detector.set_calibration_bank(bank);
}

void add_third_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kMiddleProfile{
      0.42, 0.31, 0.68, 0.19, 0.07, 0.03};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kThirdString = 2U;  // E2 string, fret 8 => C3.
  set_measured_string_profile(bank, kThirdString, 8U, 1.1, kMiddleProfile);
  detector.set_calibration_bank(bank);
}

void add_fourth_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      0.55, 0.18, 0.22, 0.58, 0.10, 0.04};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kFourthString = 1U;  // C2 string, fret 12 => C3.
  set_measured_string_profile(bank, kFourthString, 12U, -0.8, kProfile);
  detector.set_calibration_bank(bank);
}

void add_fifth_calibrated_unison_string(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      0.36, 0.55, 0.17, 0.24, 0.49, 0.08};
  m3::StringCalibrationBank bank = detector.calibration_bank();
  constexpr std::uint8_t kFifthString = 3U;  // G#2 string, fret 4 => C3.
  set_measured_string_profile(bank, kFifthString, 4U, 2.0, kProfile);
  detector.set_calibration_bank(bank);
}

void configure_calibrated_high_unison(
    m3::PolyphonicPitchDetector& detector) {
  constexpr std::uint8_t kNote = 56U;  // G#3, playable on strings 0..6.
  constexpr std::array<std::array<double, m3::kCalibrationHarmonicCount>, 7U>
      kProfiles{{
          {{1.00, 0.14, 0.06, 0.025, 0.010, 0.004}},
          {{0.78, 0.30, 0.12, 0.050, 0.020, 0.008}},
          {{0.55, 0.24, 0.61, 0.150, 0.060, 0.020}},
          {{0.40, 0.68, 0.21, 0.100, 0.040, 0.015}},
          {{0.65, 0.50, 0.28, 0.320, 0.080, 0.025}},
          {{0.32, 0.42, 0.18, 0.600, 0.200, 0.050}},
          {{0.50, 0.58, 0.38, 0.160, 0.450, 0.120}},
      }};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 7U;
  config.max_fret = 24U;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  for (std::size_t string = 0U; string < kProfiles.size(); ++string) {
    const std::size_t fret = kNote - m3::kM3OpenNotes[string];
    set_measured_string_profile(bank, string, fret,
                                static_cast<double>(string) - 3.0,
                                kProfiles[string]);
  }
  detector.set_calibration_bank(bank);
}

}  // namespace

M3_TEST(native_detector_never_infers_a_unison_lane_owned_by_a_coasting_voice) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 0U;  // G#1, open on the second string.
  constexpr std::uint8_t kBoth = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  // Control: without a live owner, the calibrated mixture is a unison.
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kSharedUnisonSecond,
                   false, 3U),
               kBoth);

  // A coasting voice still owns its string lane and per-voice MIDI channel
  // until note-off. The inferred unison must not claim that lane: a second
  // note-on on a live voice identity makes the ledger block all output.
  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kSharedUnisonSecond,
                   true, 3U, &snapshot),
               static_cast<std::uint8_t>(1U << kSharedUnisonPrimary));
  std::uint8_t published_lanes = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const std::uint8_t bit = static_cast<std::uint8_t>(
        1U << snapshot.voices[voice].string_index);
    M3_EXPECT_TRUE((published_lanes & bit) == 0);
    published_lanes = static_cast<std::uint8_t>(published_lanes | bit);
  }
  M3_EXPECT_EQ(snapshot.voice_count, 2U);
}

M3_TEST(native_detector_counts_coasting_lanes_against_the_unison_budget) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 8U;         // E2, open on string 2.
  constexpr std::uint8_t kCoastingString = 2U;  // Not the unison lane.
  constexpr std::uint8_t kBoth = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  // One selected voice plus one coasting voice already fill a two-voice
  // limit, so an inferred third lane would push a live voice out of the
  // bounded tuner snapshot.
  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kCoastingString, true, 2U,
                   &snapshot),
               static_cast<std::uint8_t>(1U << kSharedUnisonPrimary));
  M3_EXPECT_EQ(snapshot.voice_count, 2U);
  bool coasting_published = false;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    coasting_published = coasting_published ||
                         snapshot.voices[voice].string_index == kCoastingString;
  }
  M3_EXPECT_TRUE(coasting_published);

  // With room for a third lane the same evidence is still a unison.
  M3_EXPECT_EQ(Access::unison_mask_beside_coasting_voice(
                   detector, kUnison, kSharedUnisonPrimary,
                   kSharedUnisonSecond, kCoasting, kCoastingString, true, 3U),
               kBoth);
}

M3_TEST(native_detector_groups_inferred_unison_lanes_under_one_pitch_estimate) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  constexpr std::size_t kUnison = kSharedUnisonNote - 32U;
  constexpr std::size_t kCoasting = 8U;
  constexpr std::uint8_t kCoastingString = 2U;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);

  m3::TunerSnapshot snapshot;
  static_cast<void>(Access::unison_mask_beside_coasting_voice(
      detector, kUnison, kSharedUnisonPrimary, kSharedUnisonSecond, kCoasting,
      kCoastingString, true, 3U, &snapshot));
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  std::size_t shared = 0U;
  std::uint8_t shared_group = m3::kUnassignedPitchEvidenceGroup;
  constexpr std::uint8_t kUnisonMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond));
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = snapshot.voices[voice];
    // Both unison lanes carry one merged pitch estimate. The frame must say
    // so rather than implying two independent per-string measurements; the
    // independent coasting string is not shared.
    const bool unison_lane = observed.midi_note == kSharedUnisonNote;
    M3_EXPECT_EQ(observed.shares_pitch_evidence(), unison_lane);
    if (unison_lane) {
      M3_EXPECT_EQ(observed.pitch_evidence_member_mask, kUnisonMembers);
      if (shared_group == m3::kUnassignedPitchEvidenceGroup) {
        shared_group = observed.pitch_evidence_group_id;
      }
      M3_EXPECT_EQ(observed.pitch_evidence_group_id, shared_group);
    } else {
      M3_EXPECT_EQ(observed.pitch_evidence_member_mask,
                   static_cast<std::uint8_t>(1U << kCoastingString));
      M3_EXPECT_TRUE(observed.pitch_evidence_group_id != shared_group);
    }
    shared += observed.shares_pitch_evidence() ? 1U : 0U;
  }
  M3_EXPECT_EQ(shared, 2U);
  M3_EXPECT_TRUE(shared_group != m3::kUnassignedPitchEvidenceGroup);
}

M3_TEST(native_detector_pitch_evidence_group_represents_three_string_unison) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kMembers =
      static_cast<std::uint8_t>((1U << 0U) | (1U << 4U) | (1U << 7U));

  const m3::TunerSnapshot snapshot =
      Access::snapshot_for_assigned_string_group(
          detector, kCandidate, kSharedUnisonPrimary, kMembers, 3U);
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  const std::uint8_t group = snapshot.voices[0].pitch_evidence_group_id;
  M3_EXPECT_TRUE(group != m3::kUnassignedPitchEvidenceGroup);
  std::uint8_t published_members = 0U;
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    const m3::TunerVoice& observed = snapshot.voices[voice];
    M3_EXPECT_TRUE(observed.shares_pitch_evidence());
    M3_EXPECT_EQ(observed.pitch_evidence_group_id, group);
    M3_EXPECT_EQ(observed.pitch_evidence_member_mask, kMembers);
    published_members = static_cast<std::uint8_t>(
        published_members | (1U << observed.string_index));
  }
  M3_EXPECT_EQ(published_members, kMembers);
}

M3_TEST(native_detector_infers_three_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kThirdString = 2U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << kThirdString));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kSharedUnisonPrimary, kMembers, 3U,
                   &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 3U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_infers_four_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  add_fourth_calibrated_unison_string(detector);
  // Keep a fifth, distinct template available so this also proves the fitter
  // does not increase the group merely because another calibrated lane exists.
  add_fifth_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << 2U) | (1U << 1U));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kSharedUnisonPrimary, kMembers, 4U,
                   &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 4U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_infers_five_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_unison(detector);
  add_third_calibrated_unison_string(detector);
  add_fourth_calibrated_unison_string(detector);
  add_fifth_calibrated_unison_string(detector);
  constexpr std::size_t kCandidate = kSharedUnisonNote - 32U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << kSharedUnisonPrimary) | (1U << kSharedUnisonSecond) |
      (1U << 2U) | (1U << 1U) | (1U << 3U));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kSharedUnisonPrimary, kMembers, 5U,
                   &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 5U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_infers_six_calibrated_strings_from_one_pitch_group) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_high_unison(detector);
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kCandidate = kNote - 32U;
  constexpr std::uint8_t kPrimary = 6U;
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << 1U) | (1U << 2U) | (1U << 3U) | (1U << 4U) |
      (1U << 5U) | (1U << 6U));

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kPrimary, kMembers, 7U, &snapshot),
               kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 6U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_infers_seven_calibrated_strings_at_the_physical_limit) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_high_unison(detector);
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kCandidate = kNote - 32U;
  constexpr std::uint8_t kPrimary = 6U;
  // G#3 is the only M3 note shared by seven strings inside the configured
  // 24-fret range. The eighth string opens above it, so seven is the physical
  // same-pitch ceiling rather than an arbitrary software limit.
  constexpr std::uint8_t kMembers = static_cast<std::uint8_t>(
      (1U << 0U) | (1U << 1U) | (1U << 2U) | (1U << 3U) |
      (1U << 4U) | (1U << 5U) | (1U << 6U));

  m3::TunerSnapshot snapshot;
  const std::uint8_t inferred = Access::inferred_group_mask(
      detector, kCandidate, kPrimary, kMembers, 7U, &snapshot);
  M3_EXPECT_EQ(inferred, kMembers);
  M3_EXPECT_EQ(snapshot.voice_count, 7U);
  for (std::size_t voice = 0U; voice < snapshot.voice_count; ++voice) {
    M3_EXPECT_EQ(snapshot.voices[voice].pitch_evidence_member_mask, kMembers);
    M3_EXPECT_TRUE(snapshot.voices[voice].shares_pitch_evidence());
  }
}

M3_TEST(native_detector_does_not_expand_one_high_calibrated_string_to_seven) {
  using Access = m3::PolyphonicPitchDetectorTestAccess;
  m3::PolyphonicPitchDetector detector;
  configure_calibrated_high_unison(detector);
  constexpr std::uint8_t kNote = 56U;
  constexpr std::size_t kCandidate = kNote - 32U;
  constexpr std::uint8_t kPrimary = 6U;
  constexpr std::uint8_t kMember = static_cast<std::uint8_t>(1U << kPrimary);

  m3::TunerSnapshot snapshot;
  M3_EXPECT_EQ(Access::inferred_group_mask(
                   detector, kCandidate, kPrimary, kMember, 7U, &snapshot),
               kMember);
  M3_EXPECT_EQ(snapshot.voice_count, 1U);
  M3_EXPECT_EQ(snapshot.voices[0].pitch_evidence_member_mask, kMember);
  M3_EXPECT_FALSE(snapshot.voices[0].shares_pitch_evidence());
}

M3_TEST(native_detector_does_not_bias_assignment_toward_a_lone_calibrated_lane) {
  constexpr std::uint8_t kNote = 40U;
  constexpr std::array<double, m3::kCalibrationHarmonicCount> kProfile{
      1.00, 0.20, 0.08, 0.03, 0.01, 0.00};
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 60U;
  config.max_polyphony = 1U;
  config.max_fret = 24U;

  m3::PolyphonicPitchDetector baseline;
  M3_EXPECT_TRUE(baseline.configure(48000.0, config));
  const std::uint8_t baseline_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          baseline, kNote, kProfile);
  M3_EXPECT_EQ(baseline_string, 2U);

  m3::PolyphonicPitchDetector partially_calibrated;
  M3_EXPECT_TRUE(partially_calibrated.configure(48000.0, config));
  m3::StringCalibrationBank bank;
  set_measured_string_profile(bank, 1U, 4U, 0.0, kProfile);
  partially_calibrated.set_calibration_bank(bank);
  const std::uint8_t calibrated_string =
      m3::PolyphonicPitchDetectorTestAccess::assigned_string_for_profile(
          partially_calibrated, kNote, kProfile);

  M3_EXPECT_EQ(calibrated_string, baseline_string);
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
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

M3_TEST(native_detector_calibration_retains_a_detuned_strings_cents_offset) {
  // Calibration intentionally requires the open string to be tuned first;
  // verify a realistic residual offset inside that admission window.
  constexpr double kDetuneCents = 6.0;
  m3::PersistentConfig config;
  config.profile_mode = m3::ProfileMode::m3;
  config.lowest_note = 32U;
  config.highest_note = 84U;
  config.max_polyphony = 8U;
  config.max_fret = 24U;
  config.sensitivity = 70U;
  config.response = 81U;

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  M3_EXPECT_TRUE(detector.begin_string_calibration(0U));
  double oscillator_phase = 0.0;
  const double open_pitch =
      static_cast<double>(m3::kM3OpenNotes[0U]) + kDetuneCents / 100.0;
  feed_calibration_pitch(detector, open_pitch, 16000U, &oscillator_phase);
  constexpr std::uint32_t kOneWaySweepSamples = 144000U;
  feed_calibration_glide(detector, open_pitch, open_pitch + 24.0,
                         kOneWaySweepSamples, oscillator_phase);
  feed_calibration_glide(detector, open_pitch + 24.0, open_pitch,
                         kOneWaySweepSamples, oscillator_phase);
  feed_calibration_pitch(detector, open_pitch, 8000U, &oscillator_phase);

  M3_EXPECT_EQ(detector.calibration_status().phase,
               m3::CalibrationSweepPhase::complete);
  const m3::StringCalibrationPoint* open =
      detector.calibration_bank().point(0U, 0U);
  M3_EXPECT_TRUE(open != nullptr);
  if (open != nullptr) {
    M3_EXPECT_NEAR(static_cast<double>(open->cents_offset_q8) / 256.0,
                   kDetuneCents, 2.0);
  }
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

  m3::PolyphonicPitchDetector detector;
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

  m3::PolyphonicPitchDetector detector;
  M3_EXPECT_TRUE(detector.configure(48000.0, config));
  const m3::DetectorDecision decision =
      m3::PolyphonicPitchDetectorTestAccess::
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

  m3::PolyphonicPitchDetector detector;
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
