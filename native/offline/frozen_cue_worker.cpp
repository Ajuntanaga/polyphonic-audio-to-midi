#include "frozen_cue_worker.hpp"

namespace m3::offline {

bool FrozenCueWorker::step() noexcept {
  const auto* block = input_.front();
  if (!block) return false;
  if (block->generation != generation_ || block->begin != expected_) {
    if (generation_ != 0U) ++stats_.discontinuities;
    measurement_.reset();
    generation_ = block->generation;
    expected_ = origin_ = block->begin;
  }
  for (std::size_t index = 0U; index < block->count; ++index) {
    if (!measurement_.push(block->samples[index])) continue;
    const auto& frame = measurement_.frame();
    ++stats_.frames;
    constexpr auto kMaximum = std::numeric_limits<std::uint64_t>::max();
    if (frame.end_sample > kMaximum - origin_ ||
        origin_ + frame.end_sample > kMaximum - kCueWorkerDelay - FrozenPartialCue::kHop) {
      ++stats_.output_drops;
      continue;
    }
    const auto begin = origin_ + frame.end_sample + kCueWorkerDelay;
    const FrozenCueOutput result{generation_, begin, begin + FrozenPartialCue::kHop, frame.mask};
    if (!output_.push(result)) ++stats_.output_drops;
  }
  expected_ = block->begin + block->count;
  ++stats_.blocks;
  stats_.samples += block->count;
  input_.pop();
  return true;
}

}  // namespace m3::offline
