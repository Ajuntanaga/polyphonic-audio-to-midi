#include "m3/constants.hpp"
#include "m3/pitch_math.hpp"
#include "m3/types.hpp"

#include <limits>

#include "test_support.hpp"

M3_TEST(native_capacity_and_m3_tuning_contract) {
  M3_EXPECT_EQ(m3::kDecisionQuantum, 64U);
  M3_EXPECT_EQ(m3::kMaxHostFrames, 16384U);
  M3_EXPECT_EQ(m3::kMaxCandidates, 87U);
  M3_EXPECT_EQ(m3::kMaxHarmonics, 8U);
  M3_EXPECT_EQ(m3::kMaxVoices, 8U);
  M3_EXPECT_EQ(m3::kMaxInternalSelections, 16U);
  M3_EXPECT_EQ(m3::kMaxTickTransitions, 16U);
  constexpr std::uint8_t expected[] = {32, 36, 40, 44, 48, 52, 56, 60};
  for (std::size_t index = 0; index < m3::kM3OpenNotes.size(); ++index) {
    M3_EXPECT_EQ(m3::kM3OpenNotes[index], expected[index]);
  }
}

M3_TEST(pitch_math_handles_finite_and_clamped_boundaries) {
  M3_EXPECT_TRUE(m3::is_finite(0.0));
  M3_EXPECT_TRUE(m3::is_finite(-1.0));
  M3_EXPECT_FALSE(m3::is_finite(std::numeric_limits<double>::infinity()));
  M3_EXPECT_FALSE(m3::is_finite(std::numeric_limits<double>::quiet_NaN()));
  M3_EXPECT_EQ(m3::clamp_value(-2, -1, 3), -1);
  M3_EXPECT_EQ(m3::clamp_value(2, -1, 3), 2);
  M3_EXPECT_EQ(m3::clamp_value(9, -1, 3), 3);
}

M3_TEST(midi_frequency_uses_the_supplied_a4_reference) {
  M3_EXPECT_NEAR(m3::midi_to_frequency(69.0, 440.0), 440.0, 1.0e-12);
  M3_EXPECT_NEAR(m3::midi_to_frequency(57.0, 440.0), 220.0, 1.0e-12);
  M3_EXPECT_NEAR(m3::midi_to_frequency(69.0, 400.0), 400.0, 1.0e-12);
}

M3_TEST(persistent_config_defaults_match_the_public_surface) {
  const m3::PersistentConfig config;
  M3_EXPECT_EQ(config.midi_routing, m3::MidiRouting::single);
  M3_EXPECT_EQ(config.profile_mode, m3::ProfileMode::m3);
  M3_EXPECT_NEAR(config.a4_hz, 440.0, 0.0);
  M3_EXPECT_EQ(config.lowest_note, 32U);
  M3_EXPECT_EQ(config.highest_note, 84U);
  M3_EXPECT_EQ(config.max_polyphony, 8U);
  M3_EXPECT_EQ(config.max_fret, 24U);
  M3_EXPECT_EQ(config.midi_channel, 1U);
  M3_EXPECT_TRUE(config.dry_passthrough);
}
