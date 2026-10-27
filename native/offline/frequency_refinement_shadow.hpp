#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <vector>

#include "m3/frequency_refinement_observer.hpp"

namespace m3::offline {

struct FrequencyRefinementArm final {
  bool valid{};
  bool bounded{};
  double train_residual{};
  // Frequencies come exclusively from training samples. Test amplitudes are
  // refit nuisance variables; this residual is not out-of-sample prediction.
  double test_refit_residual{};
  // Amplitudes AND frequencies come exclusively from the training samples.
  double test_prediction_residual{};
  double minimum_amplitude_ratio{};
  double minimum_full_window_beat{};
  // Minimum normalized QR diagonal power and normalized GN pivot ratio;
  // conservative degeneracy diagnostics, not a condition-number estimate.
  double conditioning_proxy{};
  double maximum_correction_cents{};
  std::array<double, 8U> correction_cents{};
};

struct FrequencyRefinementMask final {
  std::uint8_t mask{};
  // Fixed calibrated frequencies, one common shift, one per-component step.
  // The last arm includes common motion; individual-drift benefit must be
  // measured beyond the common arm. All three use the same unregularized QR
  // amplitude fit with conditioning rejection. The fixed-frequency control
  // is not an exact replica of production's ridge-regularized full-window fit.
  std::array<FrequencyRefinementArm, 3U> arms{};
};

struct FrequencyRefinementTable final {
  bool prepared{};
  std::size_t training_samples{};
  std::size_t test_samples{};
  std::vector<FrequencyRefinementMask> masks{};
};

[[nodiscard]] FrequencyRefinementTable evaluate_frequency_refinement(
    const diagnostics::FrequencyRefinementView& view) noexcept;

// Optional, bounded diagnostic export. It samples by elapsed time and note,
// never labels or a desired fit result. The caller owns the output stream.
struct FrequencyWindowCaptureOptions final {
  // Select by the newest observation time, using a half-open interval. The
  // complete history is exported, including observations before the start.
  double start_seconds{};
  double end_seconds{std::numeric_limits<double>::infinity()};
  // Zero captures every distinct observation time; duplicate callbacks do not
  // consume the fixed 512-window budget.
  double min_spacing_seconds{0.5};
};

class FrequencyWindowCapture final {
 public:
  explicit FrequencyWindowCapture(
      std::FILE* stream, int note = -1,
      FrequencyWindowCaptureOptions options = {}) noexcept
      : stream_(stream), note_(note), options_(options) {}
  void append(const diagnostics::FrequencyRefinementView& view,
              const FrequencyRefinementTable& table) noexcept;
  [[nodiscard]] std::size_t windows() const noexcept { return windows_; }
  [[nodiscard]] bool failed() const noexcept { return failed_; }
  [[nodiscard]] bool truncated() const noexcept { return truncated_; }

 private:
  std::FILE* stream_{};
  int note_{-1};
  FrequencyWindowCaptureOptions options_{};
  std::size_t windows_{};
  bool failed_{};
  bool truncated_{};
  std::array<double, 128U> last_seconds_{};
  std::array<bool, 128U> seen_{};
};

// Replay owns this on the heap. Production contains neither the observer nor
// these tables. A callback stores one result per MIDI note without labels.
class FrequencyRefinementShadow final {
 public:
  void set_capture(FrequencyWindowCapture* capture) noexcept { capture_ = capture; }
  static void observe(void* context,
                      const diagnostics::FrequencyRefinementView& view) noexcept;
  [[nodiscard]] const FrequencyRefinementTable& at(std::uint8_t note) const {
    return tables_[note];
  }

 private:
  std::array<FrequencyRefinementTable, 128U> tables_{};
  FrequencyWindowCapture* capture_{};
};

}  // namespace m3::offline
