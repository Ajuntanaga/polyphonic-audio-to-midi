#include "frozen_partial_cue.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>
#include <new>

namespace m3::offline {
namespace {
constexpr double kPi = 3.141592653589793238462643383279502884;
constexpr double kRate = 96000.0;
constexpr double kBinHz = kRate / static_cast<double>(FrozenPartialCue::kFft);

struct Region final {
  double center{}, low{}, high{};
  std::size_t first{}, last{}, left_first{}, left_last{}, right_first{}, right_last{};
};

Region region(double center) noexcept {
  Region value{};
  value.center = center;
  value.low = center * std::pow(2.0, -50.0 / 1200.0);
  value.high = center * std::pow(2.0, 50.0 / 1200.0);
  // Retain the reference's exact inequalities on the FFT frequency grid.
  value.first = static_cast<std::size_t>(std::max(1.0, std::ceil((value.low - kBinHz) / kBinHz)));
  value.last = static_cast<std::size_t>(std::ceil((value.high + kBinHz) / kBinHz));
  const double inner = 3.0 * kRate / static_cast<double>(FrozenPartialCue::kWindow);
  const double outer = 5.0 * kRate / static_cast<double>(FrozenPartialCue::kWindow);
  if (center - outer > 0.0 && center + outer < kRate / 2.0) {
    value.left_first = static_cast<std::size_t>(std::ceil((center - outer) / kBinHz));
    value.left_last = static_cast<std::size_t>(std::ceil((center - inner) / kBinHz));
    value.right_first = static_cast<std::size_t>(std::floor((center + inner) / kBinHz)) + 1U;
    value.right_last = static_cast<std::size_t>(std::floor((center + outer) / kBinHz)) + 1U;
  }
  return value;
}

double median(const double* power, std::size_t first, std::size_t last) noexcept {
  // Fixed sideband width is eight FFT bins; allow either inclusive endpoint.
  std::array<double, 10U> values{};
  const auto count = last - first;
  if (count == 0U || count > values.size()) return 0.0;
  std::copy(power + first, power + last, values.begin());
  std::sort(values.begin(), values.begin() + static_cast<std::ptrdiff_t>(count));
  return count % 2U == 0U ? (values[count / 2U - 1U] + values[count / 2U]) / 2.0
                          : values[count / 2U];
}

FrozenPartialCue::Peak peak(const double* power, const Region& range) noexcept {
  FrozenPartialCue::Peak chosen{};
  for (auto index = range.first; index < range.last && index < FrozenPartialCue::kFft / 2U; ++index) {
    if (!(power[index] > power[index - 1U] && power[index] > power[index + 1U])) continue;
    const double left = std::log(std::max(power[index - 1U], std::numeric_limits<double>::min()));
    const double middle = std::log(std::max(power[index], std::numeric_limits<double>::min()));
    const double right = std::log(std::max(power[index + 1U], std::numeric_limits<double>::min()));
    const double denominator = left - 2.0 * middle + right;
    if (denominator == 0.0) continue;
    const double delta = 0.5 * (left - right) / denominator;
    const double hz = (static_cast<double>(index) + delta) * kBinHz;
    const double cents = 1200.0 * std::log2(hz / range.center);
    if (!(cents >= -50.0 && cents < 50.0)) continue;
    // Python's max tuple prefers the higher bin when powers are equal.
    if (!chosen.found || power[index] >= chosen.power) {
      chosen.found = true;
      chosen.bin = static_cast<std::uint32_t>(index);
      chosen.frequency_hz = hz;
      chosen.cents = cents;
      chosen.power = power[index];
    }
  }
  if (chosen.found) {
    chosen.reference_power = std::max(median(power, range.left_first, range.left_last),
                                     median(power, range.right_first, range.right_last));
    chosen.reference_available = chosen.reference_power > 0.0 && std::isfinite(chosen.reference_power);
    if (chosen.reference_available) {
      chosen.prominence_db = 10.0 * (std::log10(chosen.power) - std::log10(chosen.reference_power));
    }
  }
  return chosen;
}
}  // namespace

struct FrozenPartialCue::Workspace final {
  std::array<double, kWindow> ring{}, taper{};
  std::array<std::complex<double>, kFft> transform{};
  std::array<std::complex<double>, kFft / 2U> twiddles{};
  std::array<std::uint32_t, kFft> reversed{};
  std::array<double, kFft / 2U + 1U> power{};
  std::array<std::array<Region, 2U>, kNotes> regions{};
  double normalizer{};
};

FrozenPartialCue::FrozenPartialCue() noexcept = default;
FrozenPartialCue::~FrozenPartialCue() = default;

std::size_t FrozenPartialCue::storage_bytes() noexcept {
  return sizeof(Workspace) + sizeof(FrozenPartialCue);
}

bool FrozenPartialCue::prepare(std::uint32_t sample_rate) noexcept {
  prepared_ = false;
  reset();
  if (sample_rate != 96000U) return false;
  if (!workspace_) workspace_.reset(new (std::nothrow) Workspace{});
  if (!workspace_) return false;
  auto& work = *workspace_;
  double sum = 0.0;
  for (std::size_t index = 0U; index < kWindow; ++index) {
    work.taper[index] = 0.5 - 0.5 * std::cos(2.0 * kPi * static_cast<double>(index) /
                                                        static_cast<double>(kWindow - 1U));
    sum += work.taper[index];
  }
  work.normalizer = 2.0 / sum;
  for (std::size_t index = 0U; index < kFft / 2U; ++index) {
    const double angle = -2.0 * kPi * static_cast<double>(index) / static_cast<double>(kFft);
    work.twiddles[index] = {std::cos(angle), std::sin(angle)};
  }
  for (std::uint32_t index = 0U; index < kFft; ++index) {
    auto bits = index;
    std::uint32_t reversed = 0U;
    for (unsigned shift = 0U; shift < 16U; ++shift) {
      reversed = (reversed << 1U) | (bits & 1U);
      bits >>= 1U;
    }
    work.reversed[index] = reversed;
  }
  for (std::size_t index = 0U; index < kNotes; ++index) {
    const double fundamental = 440.0 * std::pow(2.0,
        (static_cast<double>(index + kFirstNote) - 69.0) / 12.0);
    work.regions[index] = {region(fundamental * 3.0), region(fundamental * 5.0)};
  }
  prepared_ = true;
  return true;
}

void FrozenPartialCue::reset() noexcept {
  samples_ = 0U;
  next_ = 0U;
  invalid_samples_ = 0U;
  frame_ = {};
  if (workspace_) workspace_->ring.fill(0.0);
}

bool FrozenPartialCue::push(float raw_sample) noexcept {
  if (!prepared_) return false;
  auto& ring = workspace_->ring;
  if (!std::isfinite(ring[next_])) --invalid_samples_;
  ring[next_] = static_cast<double>(raw_sample);
  if (!std::isfinite(ring[next_])) ++invalid_samples_;
  next_ = (next_ + 1U) % kWindow;
  ++samples_;
  if (samples_ % kHop != 0U) return false;
  frame_ = {};
  frame_.end_sample = samples_;
  frame_.history_available = samples_ >= kWindow;
  frame_.valid = frame_.history_available && invalid_samples_ == 0U;
  if (frame_.valid) measure();
  return true;
}

void FrozenPartialCue::measure() noexcept {
  auto& work = *workspace_;
  work.transform.fill({0.0, 0.0});
  for (std::size_t index = 0U; index < kWindow; ++index) {
    work.transform[work.reversed[index]] = {work.ring[(next_ + index) % kWindow] * work.taper[index], 0.0};
  }
  for (std::size_t width = 2U; width <= kFft; width *= 2U) {
    const auto half = width / 2U;
    const auto stride = kFft / width;
    for (std::size_t begin = 0U; begin < kFft; begin += width) {
      for (std::size_t offset = 0U; offset < half; ++offset) {
        const auto even = work.transform[begin + offset];
        const auto odd = work.transform[begin + offset + half] * work.twiddles[offset * stride];
        work.transform[begin + offset] = even + odd;
        work.transform[begin + offset + half] = even - odd;
      }
    }
  }
  for (std::size_t index = 0U; index < work.power.size(); ++index) {
    const double amplitude = std::abs(work.transform[index] * work.normalizer);
    work.power[index] = amplitude * amplitude;
  }
  for (std::size_t index = 0U; index < kNotes; ++index) {
    auto& note = frame_.notes[index];
    note.third = peak(work.power.data(), work.regions[index][0U]);
    note.fifth = peak(work.power.data(), work.regions[index][1U]);
    note.reason = screen(note.third, note.fifth);
    if (note.reason == Reason::cue) {
      const auto midi = index + kFirstNote;
      frame_.mask[midi / 64U] |= std::uint64_t{1U} << (midi % 64U);
    }
  }
}

FrozenPartialCue::Reason FrozenPartialCue::screen(const Peak& third, const Peak& fifth) noexcept {
  if (!third.found || !fifth.found) return Reason::missing_peak;
  if (!third.reference_available || !fifth.reference_available ||
      !std::isfinite(third.prominence_db) || !std::isfinite(fifth.prominence_db)) return Reason::missing_reference;
  if (std::min(third.prominence_db, fifth.prominence_db) <= kProminence) return Reason::below_prominence;
  const double agreement = std::abs(third.cents - fifth.cents);
  if (!std::isfinite(agreement)) return Reason::missing_agreement;
  if (!(agreement >= 0.0 && agreement <= kAgreement)) return Reason::pitch_disagreement;
  return Reason::cue;
}

const char* FrozenPartialCue::reason_name(Reason reason) noexcept {
  switch (reason) {
    case Reason::missing_peak: return "missing_peak";
    case Reason::missing_reference: return "missing_reference";
    case Reason::below_prominence: return "below_prominence";
    case Reason::missing_agreement: return "missing_agreement";
    case Reason::pitch_disagreement: return "pitch_disagreement";
    case Reason::cue: return "cue";
  }
  return "invalid_reason";
}

}  // namespace m3::offline
