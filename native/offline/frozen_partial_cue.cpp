#include "frozen_partial_cue.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>
#include <new>
#if defined(M3_FROZEN_CUE_COOPERATIVE) && !defined(M3_FROZEN_CUE_PFFFT)
#error Cooperative cue calculation requires PFFFT.
#endif
#if defined(M3_FROZEN_CUE_PFFFT)
#include "pffft_double.h"
#endif

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
#if defined(M3_FROZEN_CUE_PFFFT)
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  static constexpr std::size_t kPartFft = kFft / 4U;
  alignas(64) std::array<std::array<double, kPartFft>, 4U> input{};
  alignas(64) std::array<double, kPartFft> transform{}, scratch{};
  std::array<std::complex<double>, kPartFft / 2U> accumulator{};
  std::array<std::array<std::complex<double>, kPartFft / 2U>, 3U> twiddles{};
#else
  alignas(64) std::array<double, kFft> input{}, transform{}, scratch{};
#endif
  PFFFTD_Setup* setup{};
  std::size_t power_end{};
  ~Workspace() { pffftd_destroy_setup(setup); }
#else
  std::array<std::complex<double>, kFft> transform{};
  std::array<std::complex<double>, kFft / 2U> twiddles{};
  std::array<std::uint32_t, kFft> reversed{};
#endif
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
#if defined(M3_FROZEN_CUE_PFFFT)
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  if (!work.setup) work.setup = pffftd_new_setup(static_cast<int>(Workspace::kPartFft), PFFFT_REAL);
  for (std::size_t residue = 1U; residue < 4U; ++residue) {
    for (std::size_t bin = 0U; bin < work.accumulator.size(); ++bin) {
      const double angle = -2.0 * kPi * static_cast<double>(residue * bin) / static_cast<double>(kFft);
      work.twiddles[residue - 1U][bin] = {std::cos(angle), std::sin(angle)};
    }
  }
#else
  if (!work.setup) work.setup = pffftd_new_setup(static_cast<int>(kFft), PFFFT_REAL);
#endif
  if (!work.setup) return false;
  work.power_end = 0U;
#else
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
#endif
  for (std::size_t index = 0U; index < kNotes; ++index) {
    const double fundamental = 440.0 * std::pow(2.0,
        (static_cast<double>(index + kFirstNote) - 69.0) / 12.0);
    work.regions[index] = {region(fundamental * 3.0), region(fundamental * 5.0)};
#if defined(M3_FROZEN_CUE_PFFFT)
    // Include the peak search's neighbouring bins and both reference bands.
    // Higher spectrum bins are never read by the frozen note screen.
    for (const auto& range : work.regions[index]) {
      work.power_end = std::max({work.power_end, range.last + 1U,
                                range.left_last, range.right_last});
    }
#endif
  }
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  // Only these positive bins are read; no wrapped or Nyquist bins are needed.
  if (work.power_end > work.accumulator.size()) return false;
#endif
  prepared_ = true;
  return true;
}

void FrozenPartialCue::reset() noexcept {
  samples_ = 0U;
  next_ = 0U;
  invalid_samples_ = 0U;
  frame_ = {};
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  pending_ = {};
  pending_ready_ = false;
#endif
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
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  const auto phase = static_cast<std::size_t>(samples_ % kHop);
  // Each residue's old samples are copied before the frame ends. The final
  // 128 arriving samples are patched directly, retaining the exact window.
  if (phase == 0U || phase > kHop - kPreparationLead) {
    const auto index = phase == 0U ? kWindow - 1U : kWindow - kHop + phase - 1U;
    workspace_->input[index % 4U][index / 4U] = static_cast<double>(raw_sample) * workspace_->taper[index];
  }
  if (phase >= kHop - kPreparationLead && phase % 32U == 0U) {
    prepare_residue((phase - (kHop - kPreparationLead)) / 32U, kHop - phase);
  }
  if (phase == 0U) {
    pending_ = {};
    pending_.end_sample = samples_;
    pending_.history_available = samples_ >= kWindow;
    pending_.valid = pending_.history_available && invalid_samples_ == 0U;
    pending_ready_ = true;
  } else if (pending_ready_ && phase <= kAvailabilityDelay && phase % 32U == 0U) {
    // Transform at 32/96/160/224, between the detector's 64-sample decisions.
    // The finished frame remains private until its fixed publication at 256.
    if (pending_.valid && phase % 64U == 32U) {
      const auto residue = phase / 64U;
      transform_residue(residue);
      if (residue == 3U) select_peaks(pending_);
    }
    if (phase == kAvailabilityDelay) {
      frame_ = pending_;
      pending_ready_ = false;
      return true;
    }
  }
  return false;
#else
  if (samples_ % kHop != 0U) return false;
  frame_ = {};
  frame_.end_sample = samples_;
  frame_.history_available = samples_ >= kWindow;
  frame_.valid = frame_.history_available && invalid_samples_ == 0U;
  if (frame_.valid) measure();
  return true;
#endif
}

#if defined(M3_FROZEN_CUE_COOPERATIVE)
void FrozenPartialCue::prepare_residue(std::size_t residue, std::size_t until_end) noexcept {
  auto& work = *workspace_;
  const auto start = (next_ + until_end) % kWindow;
  for (auto index = residue; index < kWindow - kPreparationLead; index += 4U) {
    work.input[residue][index / 4U] = work.ring[(start + index) % kWindow] * work.taper[index];
  }
}

void FrozenPartialCue::transform_residue(std::size_t residue) noexcept {
  auto& work = *workspace_;
  // For a[n] = the zero-padded window, e_r[m] = a[4m+r].
  // X[k] = sum_r exp(-2*pi*i*k*r/65536) * DFT16384(e_r)[k].
  pffftd_transform_ordered(work.setup, work.input[residue].data(), work.transform.data(),
                          work.scratch.data(), PFFFT_FORWARD);
  for (std::size_t bin = 0U; bin < work.power_end; ++bin) {
    const std::complex<double> value = bin == 0U ? std::complex<double>{work.transform[0U], 0.0}
        : std::complex<double>{work.transform[2U * bin], work.transform[2U * bin + 1U]};
    if (residue == 0U) work.accumulator[bin] = value;
    else work.accumulator[bin] += work.twiddles[residue - 1U][bin] * value;
    if (residue == 3U) {
      // Finite float input leaves ample double range after the windowed FFT.
      // Compute squared magnitude directly instead of squaring hypot's result.
      const double real = work.accumulator[bin].real() * work.normalizer;
      const double imaginary = work.accumulator[bin].imag() * work.normalizer;
      work.power[bin] = real * real + imaginary * imaginary;
    }
  }
}
#else
void FrozenPartialCue::measure() noexcept {
  auto& work = *workspace_;
#if defined(M3_FROZEN_CUE_PFFFT)
  for (std::size_t index = 0U; index < kWindow; ++index) {
    work.input[index] = work.ring[(next_ + index) % kWindow] * work.taper[index];
  }
  // The zero-padded tail stays zero; the transform treats its input as const.
  pffftd_transform_ordered(work.setup, work.input.data(), work.transform.data(),
                          work.scratch.data(), PFFFT_FORWARD);
  const double dc = work.transform[0U] * work.normalizer;
  work.power[0U] = dc * dc;
  for (std::size_t index = 1U; index < work.power_end; ++index) {
    const std::complex<double> value{work.transform[2U * index], work.transform[2U * index + 1U]};
    const double amplitude = std::abs(value * work.normalizer);
    work.power[index] = amplitude * amplitude;
  }
#else
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
#endif
  select_peaks(frame_);
}
#endif

void FrozenPartialCue::select_peaks(Frame& frame) noexcept {
  auto& work = *workspace_;
  for (std::size_t index = 0U; index < kNotes; ++index) {
    auto& note = frame.notes[index];
    note.third = peak(work.power.data(), work.regions[index][0U]);
    note.fifth = peak(work.power.data(), work.regions[index][1U]);
    note.reason = screen(note.third, note.fifth);
    if (note.reason == Reason::cue) {
      const auto midi = index + kFirstNote;
      frame.mask[midi / 64U] |= std::uint64_t{1U} << (midi % 64U);
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
