#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "m3/parameter_contract.hpp"
#include "test_support.hpp"

namespace {

constexpr std::array<m3::ParameterId, m3::kPersistentParameterCount>
    kExpectedPersistentIds{{
        0x4D330001U, 0x4D330002U, 0x4D330003U, 0x4D330004U,
        0x4D330005U, 0x4D330006U, 0x4D330007U, 0x4D330008U,
        0x4D330009U, 0x4D33000AU, 0x4D33000BU, 0x4D33000CU,
        0x4D33000DU, 0x4D33000FU,
    }};

double tolerance_for(const m3::ParameterSpec& spec) noexcept {
  return spec.increment * 1.0e-9 + 1.0e-12;
}

}  // namespace

M3_TEST(parameter_normalization_round_trips_every_declared_step) {
  for (std::size_t index = 0; index < m3::kParameterCount; ++index) {
    const m3::ParameterSpec* spec = m3::parameter_spec(index);
    M3_EXPECT_TRUE(spec != nullptr);
    M3_EXPECT_TRUE(spec->maximum > spec->minimum);
    M3_EXPECT_TRUE(spec->increment > 0.0);
    M3_EXPECT_TRUE(spec->step_count > 0);
    M3_EXPECT_NEAR(
        spec->minimum + spec->increment * static_cast<double>(spec->step_count),
        spec->maximum, tolerance_for(*spec));

    for (std::int32_t step = 0; step <= spec->step_count; ++step) {
      const double plain =
          spec->minimum + spec->increment * static_cast<double>(step);
      const double normalized = m3::plain_to_normalized(*spec, plain);
      const double expected_normalized =
          static_cast<double>(step) / static_cast<double>(spec->step_count);
      M3_EXPECT_NEAR(normalized, expected_normalized, 1.0e-12);
      M3_EXPECT_NEAR(m3::normalized_to_plain(*spec, normalized), plain,
                     tolerance_for(*spec));
      M3_EXPECT_NEAR(m3::canonical_plain(*spec, plain), plain,
                     tolerance_for(*spec));
    }

    M3_EXPECT_NEAR(
        m3::normalized_to_plain(
            *spec, m3::plain_to_normalized(*spec, spec->default_value)),
        spec->default_value, tolerance_for(*spec));
  }
}

M3_TEST(parameter_normalization_clamps_and_rounds_at_the_common_boundary) {
  for (std::size_t index = 0; index < m3::kParameterCount; ++index) {
    const m3::ParameterSpec* spec = m3::parameter_spec(index);
    M3_EXPECT_TRUE(spec != nullptr);
    M3_EXPECT_NEAR(m3::canonical_plain(*spec, spec->minimum - 1000.0),
                   spec->minimum, 0.0);
    M3_EXPECT_NEAR(m3::canonical_plain(*spec, spec->maximum + 1000.0),
                   spec->maximum, 0.0);
    M3_EXPECT_NEAR(m3::plain_to_normalized(*spec, spec->minimum - 1000.0),
                   0.0, 0.0);
    M3_EXPECT_NEAR(m3::plain_to_normalized(*spec, spec->maximum + 1000.0),
                   1.0, 0.0);
    M3_EXPECT_NEAR(m3::normalized_to_plain(*spec, -1.0), spec->minimum, 0.0);
    M3_EXPECT_NEAR(m3::normalized_to_plain(*spec, 2.0), spec->maximum, 0.0);
  }

  const m3::ParameterSpec* a4 = m3::find_parameter(0x4D330003U);
  const m3::ParameterSpec* routing = m3::find_parameter(0x4D330001U);
  M3_EXPECT_TRUE(a4 != nullptr);
  M3_EXPECT_TRUE(routing != nullptr);
  M3_EXPECT_NEAR(m3::canonical_plain(*a4, 432.56), 432.6, 1.0e-12);
  M3_EXPECT_NEAR(m3::canonical_plain(*routing, 1.6), 1.0, 0.0);
}

M3_TEST(parameter_normalization_rejects_nonfinite_values_without_mutation) {
  const m3::ParameterSpec* a4 = m3::find_parameter(0x4D330003U);
  M3_EXPECT_TRUE(a4 != nullptr);
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double infinity = std::numeric_limits<double>::infinity();
  M3_EXPECT_TRUE(std::isnan(m3::canonical_plain(*a4, nan)));
  M3_EXPECT_TRUE(std::isnan(m3::canonical_plain(*a4, infinity)));
  M3_EXPECT_TRUE(std::isnan(m3::plain_to_normalized(*a4, nan)));
  M3_EXPECT_TRUE(std::isnan(m3::normalized_to_plain(*a4, -infinity)));

  m3::PersistentConfig config;
  const m3::PersistentConfig before = config;
  M3_EXPECT_EQ(m3::apply_parameter(config, a4->id, nan),
               m3::ParameterApplyResult::rejected);
  M3_EXPECT_EQ(m3::apply_parameter(config, a4->id, infinity),
               m3::ParameterApplyResult::rejected);
  M3_EXPECT_NEAR(config.a4_hz, before.a4_hz, 0.0);
}

M3_TEST(parameter_persistence_excludes_action_and_telemetry_and_channel_is_one_based) {
  const m3::ParameterId* persistent = m3::persistent_parameter_ids();
  M3_EXPECT_TRUE(persistent != nullptr);
  for (std::size_t index = 0; index < kExpectedPersistentIds.size(); ++index) {
    M3_EXPECT_EQ(persistent[index], kExpectedPersistentIds[index]);
    const m3::ParameterSpec* spec = m3::find_parameter(persistent[index]);
    M3_EXPECT_TRUE(spec != nullptr);
    M3_EXPECT_TRUE(spec->persistent);
    M3_EXPECT_FALSE(spec->read_only);
  }

  const m3::ParameterSpec* panic = m3::find_parameter(m3::kPanicParameterId);
  const m3::ParameterSpec* status = m3::find_parameter(m3::kStatusParameterId);
  const m3::ParameterSpec* channel = m3::find_parameter(0x4D33000DU);
  M3_EXPECT_TRUE(panic != nullptr);
  M3_EXPECT_TRUE(status != nullptr);
  M3_EXPECT_TRUE(channel != nullptr);
  M3_EXPECT_FALSE(panic->persistent);
  M3_EXPECT_FALSE(status->persistent);
  M3_EXPECT_EQ(panic->update_class, m3::ParameterUpdateClass::action);
  M3_EXPECT_EQ(status->update_class, m3::ParameterUpdateClass::telemetry);
  M3_EXPECT_TRUE(status->read_only);
  M3_EXPECT_NEAR(channel->minimum, 1.0, 0.0);
  M3_EXPECT_NEAR(channel->maximum, 16.0, 0.0);
  M3_EXPECT_EQ(channel->step_count, 15);
}
