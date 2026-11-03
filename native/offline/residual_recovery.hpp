#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace m3::offline {

// Frozen offline screen. Audio and native lane costs are the only inputs;
// annotated truth must never enter this policy.
struct ResidualRecoveryEvidence final {
  std::uint32_t tick{};
  std::uint8_t note{};
  std::uint8_t available_mask{};
  std::uint8_t base_count{};
  bool valid{};
  bool fixed_context{};
  bool shared_fundamental{};
  double gain{};
  double independent_energy{};
  double fundamental_overlap{};
  std::array<double, 8U> lane_costs{};
};

struct ResidualRecoveryProposal final {
  std::uint32_t tick{};
  std::uint8_t note{};
  std::uint8_t string{8U};
  double gain{};
  bool valid{};
};

class ResidualRecoveryScreen final {
 public:
  static constexpr std::uint32_t kDecimation = 16U;
  void begin_tick() noexcept { proposal_ = {}; }
  void observe(const ResidualRecoveryEvidence& e,
               std::uint8_t established_string = 8U) noexcept {
    if (e.note >= runs_.size() || e.tick % kDecimation != 0U ||
        !e.valid || !e.fixed_context || e.base_count < 2U ||
        e.shared_fundamental || !std::isfinite(e.gain) || e.gain < 0.20 ||
        !std::isfinite(e.independent_energy) || e.independent_energy < 0.0001 ||
        !std::isfinite(e.fundamental_overlap) || e.fundamental_overlap >= 0.99)
      return;
    auto& run = runs_[e.note];
    if (run.count != 0U && e.tick <= run.tick) return;
    // Renewal still needs a fresh independent audio fit. Its physical owner
    // comes from a previously emitted recovery, never from the current costs
    // (which include persistence bias), a label, or the candidate's own fit.
    if (established_string < 8U) {
      if ((e.available_mask & (1U << established_string)) == 0U) return;
      run = {e.tick, established_string, 3U};
      propose(e, established_string);
      return;
    }
    double first = std::numeric_limits<double>::infinity();
    double second = first;
    std::uint8_t best = 8U;
    for (std::uint8_t s = 0U; s < 8U; ++s) {
      if ((e.available_mask & (1U << s)) == 0U) continue;
      const double cost = e.lane_costs[s];
      if (!std::isfinite(cost)) return;
      if (cost < first) { second = first; first = cost; best = s; }
      else if (cost < second) second = cost;
    }
    // A sole available lane has no measured margin in the frozen screen.
    if (best == 8U || !std::isfinite(second) || second - first < 32.0) return;
    run.count = run.count != 0U && e.tick - run.tick == kDecimation &&
                    run.string == best
        ? static_cast<std::uint8_t>(run.count < 3U ? run.count + 1U : 3U) : 1U;
    run.tick = e.tick;
    run.string = best;
    if (run.count < 3U) return;
    propose(e, best);
  }
  [[nodiscard]] ResidualRecoveryProposal proposal() const noexcept {
    return proposal_;
  }
 private:
  void propose(const ResidualRecoveryEvidence& e, std::uint8_t string) noexcept {
    // One proposal per sampled decision. Stable note order breaks gain ties.
    if (!proposal_.valid || e.gain > proposal_.gain ||
        (e.gain == proposal_.gain && e.note < proposal_.note))
      proposal_ = {e.tick, e.note, string, e.gain, true};
  }
  struct Run final {
    std::uint32_t tick{};
    std::uint8_t string{8U};
    std::uint8_t count{};
  };
  std::array<Run, 128U> runs_{};
  ResidualRecoveryProposal proposal_{};
};

}  // namespace m3::offline
