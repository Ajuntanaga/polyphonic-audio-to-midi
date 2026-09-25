#include <atomic>
#include <thread>

#include "m3/tuner_telemetry.hpp"
#include "test_support.hpp"

namespace {

M3_TEST(tuner_telemetry_transports_a_coherent_bounded_voice_snapshot) {
  m3::TunerTelemetry telemetry;
  m3::TunerSnapshot observed;
  M3_EXPECT_FALSE(telemetry.read_latest(observed));

  m3::TunerSnapshot expected;
  expected.generation = 17U;
  expected.state = m3::TunerFrameState::tracking;
  expected.voice_count = 2U;
  expected.max_polyphony = 2U;
  expected.voices[0] = m3::TunerVoice{
      40U, static_cast<std::int16_t>(-7 * 256), 28000U, 12U,
      m3::TunerVoiceState::tracking, true, 2U};
  expected.voices[1] = m3::TunerVoice{
      47U, static_cast<std::int16_t>(11 * 256), 20000U, 4U,
      m3::TunerVoiceState::settling, true};
  telemetry.publish(expected);

  M3_EXPECT_TRUE(telemetry.read_latest(observed));
  M3_EXPECT_EQ(observed.generation, 1U);
  M3_EXPECT_EQ(observed.state, m3::TunerFrameState::tracking);
  M3_EXPECT_EQ(observed.voice_count, 2U);
  M3_EXPECT_EQ(observed.max_polyphony, 2U);
  M3_EXPECT_EQ(observed.voices[0].midi_note, 40U);
  M3_EXPECT_EQ(observed.voices[0].cents_q8, -7 * 256);
  M3_EXPECT_EQ(observed.voices[0].confidence_q15, 28000U);
  M3_EXPECT_EQ(observed.voices[0].age_ticks, 12U);
  M3_EXPECT_EQ(observed.voices[0].state, m3::TunerVoiceState::tracking);
  M3_EXPECT_TRUE(observed.voices[0].cents_valid);
  M3_EXPECT_EQ(observed.voices[0].string_index, 2U);
  M3_EXPECT_EQ(observed.voices[1].midi_note, 47U);
  M3_EXPECT_EQ(observed.voices[1].cents_q8, 11 * 256);
  M3_EXPECT_EQ(observed.voices[1].state, m3::TunerVoiceState::settling);
  M3_EXPECT_EQ(observed.voices[1].string_index,
               m3::kUnassignedTunerString);
}

M3_TEST(tuner_telemetry_clears_and_sanitizes_display_only_values) {
  m3::TunerTelemetry telemetry;
  m3::TunerSnapshot expected;
  expected.generation = 9U;
  expected.state = m3::TunerFrameState::tracking;
  expected.voice_count = static_cast<std::uint8_t>(m3::kMaxVoices + 3U);
  expected.max_polyphony = static_cast<std::uint8_t>(m3::kMaxVoices + 3U);
  expected.voices[0] = m3::TunerVoice{
      255U, static_cast<std::int16_t>(70 * 256), 40000U, 3U,
      m3::TunerVoiceState::tracking, true};
  telemetry.publish(expected);

  m3::TunerSnapshot observed;
  M3_EXPECT_TRUE(telemetry.read_latest(observed));
  const std::uint32_t published_generation = observed.generation;
  M3_EXPECT_EQ(observed.voice_count, m3::kMaxVoices);
  M3_EXPECT_EQ(observed.max_polyphony, m3::kMaxVoices);
  M3_EXPECT_EQ(observed.voices[0].midi_note, 127U);
  M3_EXPECT_EQ(observed.voices[0].cents_q8, 50 * 256);
  M3_EXPECT_EQ(observed.voices[0].confidence_q15, 32767U);

  telemetry.clear(m3::TunerFrameState::no_signal);
  M3_EXPECT_TRUE(telemetry.read_latest(observed));
  M3_EXPECT_EQ(observed.state, m3::TunerFrameState::no_signal);
  M3_EXPECT_EQ(observed.voice_count, 0U);
  M3_EXPECT_TRUE(observed.generation > published_generation);
}

M3_TEST(tuner_telemetry_preserves_the_explicit_coasting_state) {
  m3::TunerTelemetry telemetry;
  m3::TunerSnapshot expected;
  expected.state = m3::TunerFrameState::tracking;
  expected.voice_count = 1U;
  expected.max_polyphony = 8U;
  expected.voices[0] = m3::TunerVoice{
      48U, static_cast<std::int16_t>(3 * 256), 21000U, 31U,
      m3::TunerVoiceState::coasting, true, 4U};
  telemetry.publish(expected);

  m3::TunerSnapshot observed;
  M3_EXPECT_TRUE(telemetry.read_latest(observed));
  M3_EXPECT_EQ(observed.voice_count, 1U);
  M3_EXPECT_EQ(observed.voices[0].state, m3::TunerVoiceState::coasting);
  M3_EXPECT_EQ(observed.voices[0].midi_note, 48U);
  M3_EXPECT_EQ(observed.voices[0].cents_q8, 3 * 256);
  M3_EXPECT_EQ(observed.voices[0].confidence_q15, 21000U);
  M3_EXPECT_EQ(observed.voices[0].string_index, 4U);
}

M3_TEST(tuner_telemetry_owns_monotonic_generations_across_source_resets) {
  m3::TunerTelemetry telemetry;
  m3::TunerSnapshot source;
  source.generation = 7U;
  source.state = m3::TunerFrameState::tracking;
  source.voice_count = 1U;
  source.voices[0].midi_note = 40U;
  telemetry.publish(source);

  m3::TunerSnapshot first;
  M3_EXPECT_TRUE(telemetry.read_latest(first));
  source.generation = 7U;  // A reset detector can repeat its local counter.
  source.state = m3::TunerFrameState::no_signal;
  source.voice_count = 0U;
  telemetry.publish(source);

  m3::TunerSnapshot second;
  M3_EXPECT_TRUE(telemetry.read_latest(second));
  M3_EXPECT_TRUE(second.generation > first.generation);
  M3_EXPECT_EQ(second.state, m3::TunerFrameState::no_signal);
  M3_EXPECT_EQ(second.voice_count, 0U);
}

M3_TEST(tuner_telemetry_never_mixes_concurrent_audio_and_ui_frames) {
  m3::TunerTelemetry telemetry;
  std::atomic<bool> start{};
  std::atomic<bool> writer_done{};
  std::atomic<bool> malformed{};
  std::atomic<std::uint32_t> accepted{};

  std::thread writer([&] {
    while (!start.load(std::memory_order_acquire)) {
    }
    for (std::uint32_t generation = 1U; generation <= 40000U; ++generation) {
      const bool low_pair = (generation & 1U) != 0U;
      m3::TunerSnapshot snapshot;
      snapshot.generation = generation;
      snapshot.state = m3::TunerFrameState::tracking;
      snapshot.voice_count = 2U;
      snapshot.max_polyphony = 2U;
      snapshot.voices[0] = m3::TunerVoice{
          static_cast<std::uint8_t>(low_pair ? 40U : 52U),
          static_cast<std::int16_t>(low_pair ? -7 * 256 : 9 * 256),
          static_cast<std::uint16_t>(low_pair ? 28000U : 18000U),
          static_cast<std::uint16_t>(generation),
          m3::TunerVoiceState::tracking, true};
      snapshot.voices[1] = m3::TunerVoice{
          static_cast<std::uint8_t>(low_pair ? 47U : 59U),
          static_cast<std::int16_t>(low_pair ? 11 * 256 : -13 * 256),
          static_cast<std::uint16_t>(low_pair ? 20000U : 24000U),
          static_cast<std::uint16_t>(generation + 1U),
          m3::TunerVoiceState::settling, true};
      telemetry.publish(snapshot);
      if ((generation & 255U) == 0U) {
        std::this_thread::yield();
      }
    }
    writer_done.store(true, std::memory_order_release);
  });

  std::thread reader([&] {
    while (!start.load(std::memory_order_acquire)) {
    }
    while (!writer_done.load(std::memory_order_acquire) ||
           accepted.load(std::memory_order_relaxed) < 1000U) {
      m3::TunerSnapshot snapshot;
      if (!telemetry.read_latest(snapshot)) {
        continue;
      }
      const bool low_pair = (snapshot.generation & 1U) != 0U;
      const bool valid =
          snapshot.state == m3::TunerFrameState::tracking &&
          snapshot.voice_count == 2U && snapshot.max_polyphony == 2U &&
          snapshot.voices[0].midi_note == (low_pair ? 40U : 52U) &&
          snapshot.voices[0].cents_q8 == (low_pair ? -7 * 256 : 9 * 256) &&
          snapshot.voices[0].confidence_q15 == (low_pair ? 28000U : 18000U) &&
          snapshot.voices[0].age_ticks == snapshot.generation &&
          snapshot.voices[1].midi_note == (low_pair ? 47U : 59U) &&
          snapshot.voices[1].cents_q8 == (low_pair ? 11 * 256 : -13 * 256) &&
          snapshot.voices[1].confidence_q15 == (low_pair ? 20000U : 24000U) &&
          snapshot.voices[1].age_ticks ==
              static_cast<std::uint16_t>(snapshot.generation + 1U);
      if (!valid) {
        malformed.store(true, std::memory_order_release);
      }
      accepted.fetch_add(1U, std::memory_order_relaxed);
    }
  });

  start.store(true, std::memory_order_release);
  writer.join();
  reader.join();

  M3_EXPECT_FALSE(malformed.load(std::memory_order_acquire));
  M3_EXPECT_TRUE(accepted.load(std::memory_order_acquire) >= 1000U);
}

}  // namespace
