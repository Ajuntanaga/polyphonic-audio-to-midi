#pragma once

// Compile-only offline probes: absent from production and acceptance builds.
#if defined(M3_OFFLINE_STAGE_TIMING)
#if !defined(__linux__) || !defined(M3_OFFLINE_REPLAY_DIAGNOSTICS)
#error "Stage CPU probes require Linux offline replay diagnostics"
#endif
#include <array>
#include <cstddef>
#include <cstdint>
#include <time.h>

namespace m3::offline::stage_timing {
enum class Stage : std::size_t {
  cue, signal_observe, signal_reset, selection, partial_frequency,
  fine_frequency, string_assignment, voice_lifecycle, calibration_snapshot, count
};
constexpr std::size_t kCount = static_cast<std::size_t>(Stage::count);
constexpr std::array<const char*, kCount> kNames{
    "cue", "signal_observe", "signal_reset", "selection", "partial_frequency",
    "fine_frequency", "string_assignment", "voice_lifecycle", "calibration_snapshot"};
struct Block final {
  std::array<std::uint64_t, kCount> ns{}, calls{};
  bool valid{true};
};
inline thread_local Block* active_block = nullptr;

inline bool read_clock(std::uint64_t& result) noexcept {
  timespec value{};
  if (::clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0) return false;
  result = static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL +
           static_cast<std::uint64_t>(value.tv_nsec);
  return true;
}

// Scopes are sequential, never nested: stop the caller before entering a
// separately instrumented callee. Bookkeeping/clock overhead is diagnostic.
class Scope final {
 public:
  explicit Scope(Stage stage) noexcept { start(stage); }
  ~Scope() { stop(); }
  Scope(const Scope&) = delete;
  Scope& operator=(const Scope&) = delete;
  void switch_to(Stage stage) noexcept { stop(); start(stage); }
  void stop() noexcept {
    if (block_ == nullptr) return;
    std::uint64_t end{};
    if (read_clock(end) && end >= start_) {
      block_->ns[index_] += end - start_;
      ++block_->calls[index_];
    } else {
      block_->valid = false;
    }
    block_ = nullptr;
  }
 private:
  void start(Stage stage) noexcept {
    block_ = active_block;
    index_ = static_cast<std::size_t>(stage);
    if (block_ != nullptr && !read_clock(start_)) {
      block_->valid = false;
      block_ = nullptr;
    }
  }
  Block* block_{};
  std::size_t index_{};
  std::uint64_t start_{};
};
}  // namespace m3::offline::stage_timing
#endif
