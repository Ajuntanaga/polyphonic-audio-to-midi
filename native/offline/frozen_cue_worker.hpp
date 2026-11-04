#pragma once

#include "frozen_partial_cue.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <type_traits>

namespace m3::offline {

// Standalone scheduling experiment only. The audio-side methods neither wait
// nor allocate. Each queue has exactly one producer and one consumer; it must
// not be cleared or destroyed while either side is running.
template <class Item, std::size_t Capacity>
class FrozenCueQueue final {
 public:
  static_assert(Capacity > 0U);
  static_assert(std::is_trivially_copyable_v<Item>);
  static_assert(std::atomic<std::size_t>::is_always_lock_free);

  bool push(const Item& value) noexcept {
    const auto write = write_.load(std::memory_order_relaxed);
    const auto next = (write + 1U) % (Capacity + 1U);
    if (next == read_.load(std::memory_order_acquire)) return false;
    items_[write] = value;
    write_.store(next, std::memory_order_release);
    return true;
  }
  // Consumer only: the returned slot remains owned until pop().
  const Item* front() const noexcept {
    const auto read = read_.load(std::memory_order_relaxed);
    return read == write_.load(std::memory_order_acquire) ? nullptr : &items_[read];
  }
  void pop() noexcept {
    const auto read = read_.load(std::memory_order_relaxed);
    read_.store((read + 1U) % (Capacity + 1U), std::memory_order_release);
  }

 private:
  std::array<Item, Capacity + 1U> items_{};
  alignas(64) std::atomic<std::size_t> read_{0U};
  alignas(64) std::atomic<std::size_t> write_{0U};
};

constexpr std::size_t kCueQueueCapacity = 16U;
constexpr std::size_t kCueMaximumBlock = 1024U;
constexpr std::uint64_t kCueWorkerDelay = 128U;
struct FrozenCueInput final {
  std::uint64_t generation{}, begin{};
  std::size_t count{};
  std::array<float, kCueMaximumBlock> samples{};
};
struct FrozenCueOutput final {
  std::uint64_t generation{}, begin{}, end{};
  std::array<std::uint64_t, 2U> mask{};
};
using FrozenCueInputQueue = FrozenCueQueue<FrozenCueInput, kCueQueueCapacity>;
using FrozenCueOutputQueue = FrozenCueQueue<FrozenCueOutput, kCueQueueCapacity>;

class FrozenCueClient final {
 public:
  struct Stats final { std::uint64_t input_drops{}, accepted{}, late{}, stale{}; };
  FrozenCueClient(FrozenCueInputQueue& input, FrozenCueOutputQueue& output) noexcept
      : input_(input), output_(output) {}
  // Audio owner only. Old work is invalidated without touching queue cursors
  // owned by the worker. A new generation may use a new sample clock.
  void reset() noexcept {
    active_ = {};
    if (generation_ == std::numeric_limits<std::uint64_t>::max()) disabled_ = true;
    else ++generation_;
  }
  bool submit(const float* samples, std::size_t count, std::uint64_t begin) noexcept {
    if (disabled_ || !samples || count == 0U || count > kCueMaximumBlock ||
        begin > std::numeric_limits<std::uint64_t>::max() - count) {
      reset();
      ++stats_.input_drops;
      return false;
    }
    staging_.generation = generation_;
    staging_.begin = begin;
    staging_.count = count;
    std::copy_n(samples, count, staging_.samples.begin());
    if (input_.push(staging_)) return true;
    ++stats_.input_drops;
    reset();
    return false;
  }
  const FrozenCueOutput& advance(std::uint64_t sample) noexcept {
    if (disabled_ || sample >= active_.end) active_ = {};
    // A finite drain, even if the producer keeps filling released slots.
    for (std::size_t count = 0U; count < kCueQueueCapacity; ++count) {
      const auto* frame = output_.front();
      if (!frame) break;
      if (disabled_ || frame->generation != generation_) {
        ++stats_.stale;
      } else if (frame->begin > sample) {
        break;
      } else if (frame->begin < sample || frame->end <= sample) {
        // Never activate partway through a cue or extend an expired cue.
        ++stats_.late;
      } else {
        active_ = *frame;
        ++stats_.accepted;
      }
      output_.pop();
    }
    return active_;
  }
  const Stats& stats() const noexcept { return stats_; }
  std::uint64_t generation() const noexcept { return generation_; }

 private:
  FrozenCueInputQueue& input_;
  FrozenCueOutputQueue& output_;
  FrozenCueInput staging_{};
  FrozenCueOutput active_{};
  Stats stats_{};
  std::uint64_t generation_{1U};
  bool disabled_{};
};

class FrozenCueWorker final {
 public:
  struct Stats final {
    std::uint64_t blocks{}, samples{}, frames{}, output_drops{}, discontinuities{};
  };
  FrozenCueWorker(FrozenCueInputQueue& input, FrozenCueOutputQueue& output) noexcept
      : input_(input), output_(output) {}
  bool prepare() noexcept { return measurement_.prepare(96000U); }
  // Worker owner only. True if one input block was consumed.
  bool step() noexcept;
  // Read only after joining the worker (or on its owning thread).
  const Stats& stats() const noexcept { return stats_; }

 private:
  FrozenCueInputQueue& input_;
  FrozenCueOutputQueue& output_;
  FrozenPartialCue measurement_;
  Stats stats_{};
  std::uint64_t generation_{}, expected_{}, origin_{};
};

}  // namespace m3::offline
