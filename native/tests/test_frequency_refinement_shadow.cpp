#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <cstdio>
#include <cstring>
#include <memory>

#include "frequency_refinement_shadow.hpp"
#include "test_support.hpp"

namespace {
constexpr double kTwoPi = 6.28318530717958647692;
struct Fixture final {
  std::array<double, 512U> real{}, imaginary{}, beat{};
  std::array<std::uint32_t, 512U> ticks{};
  std::array<std::uint8_t, 3U> strings{0U, 1U, 2U};
  std::array<double, 3U> offsets{-1.0, -0.1, 1.2};
  std::array<bool, 256U> feasible{};
  m3::diagnostics::FrequencyRefinementView view;

  void fill(const std::array<double, 3U>& drift, bool pair = false,
            bool decay = false, double gain = 1.0) {
    feasible.fill(false);
    feasible[3U] = feasible[5U] = feasible[6U] = feasible[7U] = true;
    view = {40U, real.data(), imaginary.data(), ticks.data(), 401U,
            300U, 512U, 0.0001, 82.4069, strings.data(), offsets.data(),
            3U, feasible.data(), beat.data(), 1.0};
    constexpr std::array<double, 3U> amplitudes{0.8, 0.6, 0.45};
    for (std::size_t n = 0U; n < view.count; ++n) {
      const std::size_t index = (view.oldest + n) % view.capacity;
      ticks[index] = static_cast<std::uint32_t>(100U * n + 3U * (n / 37U));
      const double t = static_cast<double>(ticks[index]) * view.seconds_per_tick;
      std::complex<double> value{};
      for (std::size_t j = 0U; j < (pair ? 2U : 3U); ++j) {
        value += gain * amplitudes[j] *
            (decay ? std::exp(-(0.1 + 0.05 * static_cast<double>(j)) * t) : 1.0) *
            std::polar(1.0, kTwoPi * (offsets[j] + drift[j]) * t +
                           0.7 * static_cast<double>(j));
      }
      real[index] = value.real();
      imaginary[index] = value.imag();
      // Synthetic statistic is intentionally independent of the fit signal;
      // fitting must never use the beat gate or scoring labels as targets.
      beat[n] = 0.0;
    }
  }
};

const m3::offline::FrequencyRefinementMask& model(
    const m3::offline::FrequencyRefinementTable& table, std::uint8_t mask) {
  for (const auto& candidate : table.masks) {
    if (candidate.mask == mask) {
      return candidate;
    }
  }
  M3_EXPECT_TRUE(false);
  return table.masks.front();
}
}  // namespace

M3_TEST(frequency_refinement_shadow_separates_common_and_independent_drift) {
  Fixture fixture;
  fixture.fill({0.04, 0.04, 0.04});
  const auto common = m3::offline::evaluate_frequency_refinement(fixture.view);
  M3_EXPECT_TRUE(common.prepared);
  M3_EXPECT_EQ(common.training_samples, 200U);
  M3_EXPECT_EQ(common.test_samples, 100U);
  const auto& a = model(common, 7U).arms;
  M3_EXPECT_TRUE(a[0U].valid && a[1U].valid && a[2U].valid);
  M3_EXPECT_FALSE(a[1U].bounded);
  M3_EXPECT_TRUE(a[1U].test_refit_residual < a[0U].test_refit_residual * 0.05);
  M3_EXPECT_TRUE(a[1U].test_prediction_residual < a[0U].test_prediction_residual * 0.05);
  for (std::size_t j = 0U; j < 3U; ++j) {
    const double hz = (fixture.view.center_hz + fixture.offsets[j]) *
        std::expm1(std::log(2.0) * a[1U].correction_cents[j] / 1200.0);
    M3_EXPECT_NEAR(hz, 0.04, 0.01);
  }
  fixture.fill({-0.04, 0.03, 0.06});
  const auto independent = m3::offline::evaluate_frequency_refinement(fixture.view);
  const auto& b = model(independent, 7U).arms;
  M3_EXPECT_TRUE(b[2U].valid);
  M3_EXPECT_FALSE(b[2U].bounded);
  M3_EXPECT_TRUE(b[2U].test_refit_residual < b[1U].test_refit_residual * 0.15);
  M3_EXPECT_TRUE(b[2U].test_prediction_residual < b[1U].test_prediction_residual * 0.15);
}

M3_TEST(frequency_refinement_shadow_is_train_only_and_scale_invariant) {
  Fixture fixture;
  fixture.fill({-0.03, 0.02, 0.04});
  const auto baseline = m3::offline::evaluate_frequency_refinement(fixture.view);
  const auto& before = model(baseline, 7U).arms;
  fixture.fill({-0.03, 0.02, 0.04}, false, false, 0.01);
  const auto scaled = m3::offline::evaluate_frequency_refinement(fixture.view);
  for (std::size_t arm = 0U; arm < 3U; ++arm) {
    const auto& after = model(scaled, 7U).arms[arm];
    M3_EXPECT_TRUE(after.valid);
    M3_EXPECT_NEAR(after.test_refit_residual, before[arm].test_refit_residual, 1.0e-10);
    for (std::size_t j = 0U; j < 3U; ++j) {
      M3_EXPECT_NEAR(after.correction_cents[j], before[arm].correction_cents[j], 1.0e-10);
    }
  }
  for (std::size_t n = 200U; n < fixture.view.count; ++n) {
    const std::size_t index = (fixture.view.oldest + n) % fixture.view.capacity;
    fixture.real[index] += 0.03 * std::sin(static_cast<double>(n));
    fixture.imaginary[index] -= 0.02;
  }
  const auto changed_test = m3::offline::evaluate_frequency_refinement(fixture.view);
  for (std::size_t arm = 0U; arm < 3U; ++arm) {
    const auto& after = model(changed_test, 7U).arms[arm];
    for (std::size_t j = 0U; j < 3U; ++j) {
      M3_EXPECT_NEAR(after.correction_cents[j], before[arm].correction_cents[j], 1.0e-10);
    }
  }
}

M3_TEST(frequency_refinement_shadow_keeps_negative_controls_and_bounds) {
  Fixture fixture;
  fixture.fill({0.0, 0.0, 0.0}, true, true);
  const auto pair = m3::offline::evaluate_frequency_refinement(fixture.view);
  for (const auto& arm : model(pair, 7U).arms) {
    M3_EXPECT_TRUE(!arm.valid || arm.minimum_amplitude_ratio < 0.12);
    M3_EXPECT_EQ(arm.minimum_full_window_beat, 0.0);
  }
  fixture.fill({0.0, 0.0, 0.0}, false, true);
  const auto decaying = m3::offline::evaluate_frequency_refinement(fixture.view);
  const auto& decay = model(decaying, 7U).arms;
  M3_EXPECT_TRUE(decay[0U].valid && decay[1U].valid && decay[2U].valid);
  M3_EXPECT_TRUE(decay[0U].test_refit_residual - decay[1U].test_refit_residual < 0.02);
  M3_EXPECT_TRUE(decay[0U].test_refit_residual - decay[2U].test_refit_residual < 0.02);
  fixture.fill({0.25, 0.25, 0.25});
  const auto excessive = m3::offline::evaluate_frequency_refinement(fixture.view);
  M3_EXPECT_TRUE(model(excessive, 7U).arms[1U].bounded);
  fixture.feasible[7U] = false;
  const auto feasible = m3::offline::evaluate_frequency_refinement(fixture.view);
  M3_EXPECT_EQ(feasible.masks.size(), 3U);
  fixture.offsets[1U] = fixture.offsets[0U];
  const auto duplicate = m3::offline::evaluate_frequency_refinement(fixture.view);
  M3_EXPECT_FALSE(model(duplicate, 3U).arms[0U].valid);
  fixture.ticks[(fixture.view.oldest + 1U) % fixture.view.capacity] =
      fixture.ticks[fixture.view.oldest];
  M3_EXPECT_FALSE(m3::offline::evaluate_frequency_refinement(fixture.view).prepared);
  auto observer = std::make_unique<m3::offline::FrequencyRefinementShadow>();
  fixture.fill({0.0, 0.0, 0.0});
  observer->observe(observer.get(), fixture.view);
  M3_EXPECT_TRUE(observer->at(40U).prepared);
  observer->observe(observer.get(), {});
  M3_EXPECT_FALSE(observer->at(40U).prepared);
}

M3_TEST(frequency_refinement_shadow_handles_four_sources_without_crossing) {
  Fixture fixture;
  fixture.fill({-0.03, 0.02, 0.04});
  std::array<std::uint8_t, 4U> strings{0U, 1U, 2U, 3U};
  std::array<double, 4U> offsets{-1.0, -0.1, 1.2, 3.0};
  fixture.view.strings = strings.data();
  fixture.view.offsets_hz = offsets.data();
  fixture.view.components = 4U;
  fixture.feasible[15U] = true;
  for (std::size_t n = 0U; n < fixture.view.count; ++n) {
    const std::size_t index = (fixture.view.oldest + n) % fixture.view.capacity;
    const double t = static_cast<double>(fixture.ticks[index]) * fixture.view.seconds_per_tick;
    const auto fourth = std::polar(0.3, kTwoPi * 3.025 * t - 1.2);
    fixture.real[index] += fourth.real();
    fixture.imaginary[index] += fourth.imag();
  }
  const auto table = m3::offline::evaluate_frequency_refinement(fixture.view);
  const auto& arms = model(table, 15U).arms;
  M3_EXPECT_TRUE(arms[2U].valid);
  M3_EXPECT_FALSE(arms[2U].bounded);
  M3_EXPECT_TRUE(arms[2U].test_refit_residual < arms[0U].test_refit_residual * 0.1);
  M3_EXPECT_TRUE(arms[2U].maximum_correction_cents < 5.0);
  double previous = -100.0;
  for (std::size_t j = 0U; j < 4U; ++j) {
    const double corrected = (fixture.view.center_hz + offsets[j]) *
        std::exp(std::log(2.0) * arms[2U].correction_cents[j] / 1200.0);
    M3_EXPECT_TRUE(corrected > previous);
    previous = corrected;
  }
}

M3_TEST(frequency_refinement_capture_is_bounded_and_samples_actual_time) {
  Fixture fixture;
  fixture.fill({0.0, 0.0, 0.0});
  const auto table = m3::offline::evaluate_frequency_refinement(fixture.view);
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
  M3_EXPECT_TRUE(stream != nullptr);
  m3::offline::FrequencyWindowCapture capture(stream.get(), 40);
  capture.append(fixture.view, table);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 1U);
  fixture.view.midi_note = 41U;
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 1U);
  fixture.view.midi_note = 40U;
  for (std::size_t window = 1U; window < 514U; ++window) {
    for (auto& tick : fixture.ticks) {
      tick += 5000U;
    }
    capture.append(fixture.view, table);
    if (window == 511U) {
      M3_EXPECT_FALSE(capture.truncated());
    }
  }
  M3_EXPECT_EQ(capture.windows(), 512U);
  M3_EXPECT_TRUE(capture.truncated());
  M3_EXPECT_FALSE(capture.failed());
  M3_EXPECT_EQ(std::fflush(stream.get()), 0);
  std::rewind(stream.get());
  std::array<char, 180U> prefix{};
  M3_EXPECT_TRUE(std::fgets(prefix.data(), static_cast<int>(prefix.size()), stream.get()) != nullptr);
  M3_EXPECT_TRUE(std::strstr(prefix.data(), "\"note\":40") != nullptr);
  M3_EXPECT_TRUE(std::strstr(prefix.data(), "\"training_samples\":200") != nullptr);
}

M3_TEST(frequency_refinement_capture_range_preserves_complete_native_history) {
  Fixture fixture;
  fixture.fill({0.0, 0.0, 0.0});
  const auto table = m3::offline::evaluate_frequency_refinement(fixture.view);
  const auto last = (fixture.view.oldest + fixture.view.count - 1U) % fixture.view.capacity;
  const auto origin = fixture.ticks[last];
  const auto set_end = [&](std::uint32_t tick) {
    const auto delta = tick - fixture.ticks[last];
    for (auto& value : fixture.ticks) {
      value += delta;
    }
  };
  // Exact binary fractions avoid imposing floating-point boundary rounding on
  // the time-spacing contract. Out-of-range callbacks must not consume a slot
  // or delay the first in-range observation.
  constexpr double start = 3.125;
  constexpr double end = 3.375;
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> control_stream(std::tmpfile(), &std::fclose);
  M3_EXPECT_TRUE(stream != nullptr && control_stream != nullptr);
  m3::offline::FrequencyWindowCapture capture(stream.get(), 40, {start, end, 0.125});
  m3::offline::FrequencyWindowCapture control(control_stream.get(), 40);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 0U);
  set_end(31250U);
  capture.append(fixture.view, table);
  control.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 1U);
  M3_EXPECT_EQ(std::fflush(stream.get()), 0);
  M3_EXPECT_EQ(std::fflush(control_stream.get()), 0);
  std::rewind(stream.get());
  std::rewind(control_stream.get());
  int actual = 0;
  do {
    actual = std::fgetc(stream.get());
    M3_EXPECT_EQ(actual, std::fgetc(control_stream.get()));
  } while (actual != EOF);
  M3_EXPECT_TRUE(fixture.ticks[fixture.view.oldest] < origin);
  // Restore write position after the byte comparison.
  M3_EXPECT_EQ(std::fseek(stream.get(), 0, SEEK_END), 0);
  capture.append(fixture.view, table);
  set_end(32499U);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 1U);
  set_end(32500U);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 2U);
  set_end(33750U);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 2U);
  M3_EXPECT_FALSE(capture.truncated());
}

M3_TEST(frequency_refinement_capture_zero_spacing_deduplicates_each_note) {
  Fixture fixture;
  fixture.fill({0.0, 0.0, 0.0});
  const auto table = m3::offline::evaluate_frequency_refinement(fixture.view);
  std::unique_ptr<std::FILE, int (*)(std::FILE*)> stream(std::tmpfile(), &std::fclose);
  M3_EXPECT_TRUE(stream != nullptr);
  m3::offline::FrequencyWindowCapture capture(
      stream.get(), -1, {0.0, std::numeric_limits<double>::infinity(), 0.0});
  capture.append(fixture.view, table);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 1U);
  fixture.view.midi_note = 41U;
  capture.append(fixture.view, table);
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 2U);
  fixture.view.midi_note = 40U;
  for (auto& tick : fixture.ticks) {
    ++tick;
  }
  capture.append(fixture.view, table);
  M3_EXPECT_EQ(capture.windows(), 3U);
  M3_EXPECT_FALSE(capture.failed());
}
