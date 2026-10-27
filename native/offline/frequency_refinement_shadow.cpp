#include "frequency_refinement_shadow.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>

namespace m3::offline {
namespace {
using Complex = std::complex<double>;
constexpr std::size_t kSamples = 512U;
constexpr std::size_t kSources = 4U;
constexpr double kTwoPi = 6.28318530717958647692;
using Series = std::array<Complex, kSamples>;
using Frequencies = std::array<double, kSources>;

struct LinearFit final {
  bool valid{};
  std::array<Series, kSources> q{};
  std::array<Complex, kSources> amplitudes{};
  Series residual{};
  double loss{};
  double minimum_ratio{};
  double conditioning{1.0};
};

LinearFit fit(const std::array<double, kSamples>& times, const Series& values,
              std::size_t begin, std::size_t end, const Frequencies& frequencies,
              std::size_t sources) noexcept {
  LinearFit out;
  std::array<std::array<Complex, kSources>, kSources> r{};
  std::array<Complex, kSources> projected{};
  double energy = 0.0;
  for (std::size_t n = begin; n < end; ++n) {
    energy += std::norm(values[n]);
  }
  if (!std::isfinite(energy) || energy <= 1.0e-25) {
    return out;
  }
  for (std::size_t j = 0U; j < sources; ++j) {
    for (std::size_t n = begin; n < end; ++n) {
      out.q[j][n] = std::polar(1.0, kTwoPi * frequencies[j] * times[n]);
    }
    // Reorthogonalized QR avoids squaring the close-frequency condition.
    for (std::size_t pass = 0U; pass < 2U; ++pass) {
      for (std::size_t k = 0U; k < j; ++k) {
        Complex dot{};
        for (std::size_t n = begin; n < end; ++n) {
          dot += std::conj(out.q[k][n]) * out.q[j][n];
        }
        r[k][j] += dot;
        for (std::size_t n = begin; n < end; ++n) {
          out.q[j][n] -= dot * out.q[k][n];
        }
      }
    }
    double norm = 0.0;
    for (std::size_t n = begin; n < end; ++n) {
      norm += std::norm(out.q[j][n]);
    }
    const double relative = norm / static_cast<double>(end - begin);
    out.conditioning = std::min(out.conditioning, relative);
    if (!std::isfinite(relative) || relative < 1.0e-6) {
      return out;
    }
    r[j][j] = std::sqrt(norm);
    for (std::size_t n = begin; n < end; ++n) {
      out.q[j][n] /= r[j][j];
      projected[j] += std::conj(out.q[j][n]) * values[n];
    }
  }
  for (std::size_t row = sources; row-- > 0U;) {
    Complex value = projected[row];
    for (std::size_t j = row + 1U; j < sources; ++j) {
      value -= r[row][j] * out.amplitudes[j];
    }
    out.amplitudes[row] = value / r[row][row];
  }
  double maximum = 0.0;
  double minimum = std::numeric_limits<double>::infinity();
  for (std::size_t j = 0U; j < sources; ++j) {
    const double amplitude = std::abs(out.amplitudes[j]);
    maximum = std::max(maximum, amplitude);
    minimum = std::min(minimum, amplitude);
  }
  double squared_error = 0.0;
  for (std::size_t n = begin; n < end; ++n) {
    Complex residual = values[n];
    for (std::size_t j = 0U; j < sources; ++j) {
      residual -= projected[j] * out.q[j][n];
    }
    out.residual[n] = residual;
    squared_error += std::norm(residual);
  }
  out.loss = squared_error / energy;
  out.minimum_ratio = maximum > 0.0 ? minimum / maximum : 0.0;
  out.valid = std::isfinite(out.loss) && std::isfinite(out.minimum_ratio);
  return out;
}

bool frequency_step(const std::array<double, kSamples>& times,
                    const LinearFit& base, const Frequencies& frequencies,
                    std::size_t count, std::size_t sources, bool common,
                    Frequencies& step, double& conditioning) noexcept {
  std::array<Series, kSources> derivative{};
  const double midpoint = 0.5 * (times[0U] + times[count - 1U]);
  for (std::size_t j = 0U; j < sources; ++j) {
    const std::size_t column = common ? 0U : j;
    for (std::size_t n = 0U; n < count; ++n) {
      derivative[column][n] += Complex{0.0, kTwoPi * (times[n] - midpoint)} *
          base.amplitudes[j] * std::polar(1.0, kTwoPi * frequencies[j] * times[n]);
    }
  }
  const std::size_t dimensions = common ? 1U : sources;
  std::array<double, kSources> scales{};
  std::array<std::array<double, kSources>, kSources> gram{};
  std::array<double, kSources> rhs{};
  for (std::size_t j = 0U; j < dimensions; ++j) {
    // Variable projection: frequency motion must explain signal outside the
    // freely fitted complex-amplitude subspace.
    for (std::size_t pass = 0U; pass < 2U; ++pass) {
      for (std::size_t k = 0U; k < sources; ++k) {
        Complex dot{};
        for (std::size_t n = 0U; n < count; ++n) {
          dot += std::conj(base.q[k][n]) * derivative[j][n];
        }
        for (std::size_t n = 0U; n < count; ++n) {
          derivative[j][n] -= dot * base.q[k][n];
        }
      }
    }
    double power = 0.0;
    for (std::size_t n = 0U; n < count; ++n) {
      power += std::norm(derivative[j][n]);
    }
    if (!std::isfinite(power) || power <= 1.0e-25) {
      return false;
    }
    scales[j] = std::sqrt(power);
    for (std::size_t n = 0U; n < count; ++n) {
      derivative[j][n] /= scales[j];
      rhs[j] += std::real(std::conj(derivative[j][n]) * base.residual[n]);
    }
  }
  for (std::size_t row = 0U; row < dimensions; ++row) {
    for (std::size_t column = 0U; column < dimensions; ++column) {
      for (std::size_t n = 0U; n < count; ++n) {
        gram[row][column] += std::real(
            std::conj(derivative[row][n]) * derivative[column][n]);
      }
    }
  }
  conditioning = 1.0;
  for (std::size_t column = 0U; column < dimensions; ++column) {
    const double pivot = gram[column][column];
    conditioning = std::min(conditioning, pivot);
    if (!std::isfinite(pivot) || pivot < 1.0e-6) {
      return false;
    }
    for (std::size_t row = column + 1U; row < dimensions; ++row) {
      const double factor = gram[row][column] / pivot;
      for (std::size_t j = column + 1U; j < dimensions; ++j) {
        gram[row][j] -= factor * gram[column][j];
      }
      rhs[row] -= factor * rhs[column];
    }
  }
  Frequencies solution{};
  for (std::size_t row = dimensions; row-- > 0U;) {
    double value = rhs[row];
    for (std::size_t j = row + 1U; j < dimensions; ++j) {
      value -= gram[row][j] * solution[j];
    }
    solution[row] = value / gram[row][row];
  }
  for (std::size_t j = 0U; j < sources; ++j) {
    const std::size_t column = common ? 0U : j;
    step[j] = solution[column] / scales[column];
    if (!std::isfinite(step[j])) {
      return false;
    }
  }
  return true;
}

double beat(const diagnostics::FrequencyRefinementView& view,
            const std::array<double, kSamples>& times,
            const Frequencies& frequencies, std::size_t sources) noexcept {
  if (view.beat_absolute_sum <= 1.0e-15) {
    return 0.0;
  }
  double minimum = 1.0;
  for (std::size_t j = 0U; j < sources; ++j) {
    for (std::size_t k = j + 1U; k < sources; ++k) {
      const double hz = std::abs(frequencies[j] - frequencies[k]);
      Complex correlation{};
      if (hz >= 0.25 && hz <= 12.0) {
        for (std::size_t n = 0U; n < view.count; ++n) {
          correlation += view.beat_samples[n] * std::polar(1.0, -kTwoPi * hz * times[n]);
        }
      }
      minimum = std::min(minimum, std::clamp(
          std::abs(correlation) / view.beat_absolute_sum, 0.0, 1.0));
    }
  }
  return minimum;
}
}  // namespace

FrequencyRefinementTable evaluate_frequency_refinement(
    const diagnostics::FrequencyRefinementView& view) noexcept {
  FrequencyRefinementTable table;
  if (view.count < 12U || view.count > kSamples || view.count > view.capacity ||
      view.oldest >= view.capacity || view.components < 2U || view.components > 8U ||
      view.real == nullptr || view.imaginary == nullptr || view.ticks == nullptr ||
      view.strings == nullptr || view.offsets_hz == nullptr ||
      view.feasible_masks == nullptr || view.beat_samples == nullptr ||
      !std::isfinite(view.center_hz) || view.center_hz <= 0.0 ||
      !std::isfinite(view.seconds_per_tick) || view.seconds_per_tick <= 0.0 ||
      !std::isfinite(view.beat_absolute_sum) || view.beat_absolute_sum < 0.0) {
    return table;
  }
  std::array<double, kSamples> times{};
  Series values{};
  const std::uint32_t first_tick = view.ticks[view.oldest];
  for (std::size_t n = 0U; n < view.count; ++n) {
    const std::size_t index = (view.oldest + n) % view.capacity;
    times[n] = static_cast<double>(view.ticks[index] - first_tick) * view.seconds_per_tick;
    values[n] = {view.real[index], view.imaginary[index]};
    if (!std::isfinite(times[n]) || !std::isfinite(values[n].real()) ||
        !std::isfinite(values[n].imag()) || !std::isfinite(view.beat_samples[n]) ||
        (n != 0U && times[n] <= times[n - 1U])) {
      return table;
    }
  }
  std::uint8_t available = 0U;
  for (std::size_t j = 0U; j < view.components; ++j) {
    if (view.strings[j] >= 8U || (available & (1U << view.strings[j])) != 0U ||
        !std::isfinite(view.offsets_hz[j]) || view.center_hz + view.offsets_hz[j] <= 0.0) {
      return table;
    }
    available = static_cast<std::uint8_t>(available | (1U << view.strings[j]));
  }
  const std::size_t training = view.count * 2U / 3U;
  const double train_span = times[training - 1U] - times[0U];
  table.prepared = true;
  table.training_samples = training;
  table.test_samples = view.count - training;
  for (std::size_t mask = 1U; mask < 256U; ++mask) {
    if (!view.feasible_masks[mask] || (mask & ~available) != 0U) {
      continue;
    }
    Frequencies original{};
    std::array<std::uint8_t, kSources> strings{};
    std::size_t sources = 0U;
    for (std::size_t j = 0U; j < view.components; ++j) {
      if ((mask & (1U << view.strings[j])) != 0U) {
        if (sources < kSources) {
          original[sources] = view.offsets_hz[j];
          strings[sources] = view.strings[j];
        }
        ++sources;
      }
    }
    if (sources < 2U || sources > kSources) {
      continue;
    }
    FrequencyRefinementMask result;
    result.mask = static_cast<std::uint8_t>(mask);
    const LinearFit base = fit(times, values, 0U, training, original, sources);
    if (!base.valid) {
      table.masks.push_back(result);
      continue;
    }
    for (std::size_t arm = 0U; arm < result.arms.size(); ++arm) {
      auto& out = result.arms[arm];
      Frequencies correction{}, frequencies = original;
      double step_conditioning = 1.0;
      if (arm != 0U && !frequency_step(times, base, original, training, sources,
                                      arm == 1U, correction, step_conditioning)) {
        continue;
      }
      // A quarter cycle over the training span, at most five cents. For
      // independent motion, also stay within a quarter of the nearest source
      // separation. No crossing or iterative search of the held-out data.
      double common_bound = 0.25 / train_span;
      for (std::size_t j = 0U; j < sources; ++j) {
        common_bound = std::min(common_bound,
            (view.center_hz + original[j]) *
                -std::expm1(-std::log(2.0) * 5.0 / 1200.0));
      }
      for (std::size_t j = 0U; j < sources; ++j) {
        double bound = common_bound;
        if (arm == 2U) {
          for (std::size_t k = 0U; k < sources; ++k) {
            if (k != j) {
              bound = std::min(bound, 0.25 * std::abs(original[j] - original[k]));
            }
          }
        }
        out.bounded = out.bounded || std::abs(correction[j]) >= bound;
        correction[j] = std::clamp(correction[j], -bound, bound);
        frequencies[j] += correction[j];
        const double cents = 1200.0 * std::log2(
            (view.center_hz + frequencies[j]) / (view.center_hz + original[j]));
        out.correction_cents[strings[j]] = cents;
        out.maximum_correction_cents = std::max(out.maximum_correction_cents, std::abs(cents));
      }
      const LinearFit train_fit = arm == 0U ? base :
          fit(times, values, 0U, training, frequencies, sources);
      const LinearFit test_fit = fit(times, values, training, view.count, frequencies, sources);
      if (!train_fit.valid || !test_fit.valid) {
        continue;
      }
      double energy = 0.0;
      double loss = 0.0;
      for (std::size_t n = training; n < view.count; ++n) {
        Complex prediction{};
        for (std::size_t j = 0U; j < sources; ++j) {
          prediction += train_fit.amplitudes[j] * std::polar(1.0, kTwoPi * frequencies[j] * times[n]);
        }
        loss += std::norm(values[n] - prediction);
        energy += std::norm(values[n]);
      }
      out.train_residual = train_fit.loss;
      out.test_refit_residual = test_fit.loss;
      out.test_prediction_residual = loss / energy;
      out.minimum_amplitude_ratio = std::min(train_fit.minimum_ratio, test_fit.minimum_ratio);
      out.minimum_full_window_beat = beat(view, times, frequencies, sources);
      out.conditioning_proxy = std::min({train_fit.conditioning, test_fit.conditioning, step_conditioning});
      out.valid = std::isfinite(out.test_prediction_residual);
    }
    table.masks.push_back(result);
  }
  return table;
}

void FrequencyRefinementShadow::observe(
    void* context, const diagnostics::FrequencyRefinementView& view) noexcept {
  auto& self = *static_cast<FrequencyRefinementShadow*>(context);
  if (view.count == 0U) {
    for (auto& table : self.tables_) {
      table = {};
    }
  } else if (view.midi_note < self.tables_.size()) {
    self.tables_[view.midi_note] = evaluate_frequency_refinement(view);
  }
}

}  // namespace m3::offline
