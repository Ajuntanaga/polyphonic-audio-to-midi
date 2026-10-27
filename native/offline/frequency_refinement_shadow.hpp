#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
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

// Replay owns this on the heap. Production contains neither the observer nor
// these tables. A callback stores one result per MIDI note without labels.
class FrequencyRefinementShadow final {
 public:
  static void observe(void* context,
                      const diagnostics::FrequencyRefinementView& view) noexcept;
  [[nodiscard]] const FrequencyRefinementTable& at(std::uint8_t note) const {
    return tables_[note];
  }

 private:
  std::array<FrequencyRefinementTable, 128U> tables_{};
};

}  // namespace m3::offline
