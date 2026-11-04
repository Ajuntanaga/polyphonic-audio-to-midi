#pragma once

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <limits>
#include <memory>
#include <string_view>
#include <system_error>
#include <vector>
#if defined(M3_FROZEN_CUE_COOPERATIVE)
#include "frozen_partial_cue.hpp"
#endif

namespace m3::offline {

// Offline-only, zero-based input sample clock. A cue covers [begin, end).
// The fixed window is complete before begin; labels and string IDs are absent.
class FrozenNoteCues final {
 public:
  bool parse(std::string_view text, std::uint32_t sample_rate,
             std::uint64_t sample_count, std::uint32_t availability_delay_samples = 0U) {
#if defined(M3_FROZEN_CUE_COOPERATIVE)
    native_.reset();
#endif
    spans_.clear();
    reset();
    valid_ = false;
    constexpr std::string_view header = "m3_frozen_note_cues_v1\t96000\t1024\n";
    if (sample_rate != 96000U || sample_count == 0U || availability_delay_samples > 1024U ||
        text.substr(0U, header.size()) != header) return false;
    text.remove_prefix(header.size());
    std::array<std::uint64_t, 128U> previous_end{};
    std::uint64_t previous_begin = 0U;
    unsigned previous_note = 0U;
    while (!text.empty()) {
      std::array<std::uint64_t, 3U> fields{};
      for (std::size_t index = 0U; index < fields.size(); ++index) {
        const char delimiter = index == 2U ? '\n' : '\t';
        const auto length = text.find(delimiter);
        if (length == std::string_view::npos || length == 0U) return false;
        const auto parsed = std::from_chars(text.data(), text.data() + length, fields[index]);
        if (parsed.ec != std::errc{} || parsed.ptr != text.data() + length) return false;
        text.remove_prefix(length + 1U);
      }
      const auto begin = fields[0U], end = fields[1U], note = fields[2U];
      if (note > 127U || begin < 16384U || begin >= end || end > sample_count ||
          begin % 1024U != 0U || end - begin != std::min<std::uint64_t>(1024U, sample_count - begin) ||
          begin < previous_begin || (begin == previous_begin && note <= previous_note) ||
          begin < previous_end[note] || spans_.size() >= 100000U) return false;
      spans_.push_back({begin, end, static_cast<unsigned>(note)});
      previous_begin = begin;
      previous_note = static_cast<unsigned>(note);
      previous_end[note] = end;
    }
    // Validate the original clock first. This offline scheduling experiment
    // shifts both availability and expiry without changing the source cues.
    if (availability_delay_samples != 0U) {
      std::size_t retained = 0U;
      for (auto& span : spans_) {
        if (availability_delay_samples >= sample_count - span.begin) break;
        span.begin += availability_delay_samples;
        span.end += std::min<std::uint64_t>(availability_delay_samples, sample_count - span.end);
        ++retained;
      }
      spans_.resize(retained);
    }
    sample_count_ = sample_count;
    valid_ = true;
    return true;
  }

#if defined(M3_FROZEN_CUE_COOPERATIVE)
  // Explicit offline opt-in. Preparation may allocate; observe/advance do not.
  bool prepare_native(std::uint32_t rate, std::uint64_t count) {
    valid_ = false;
    spans_.clear();
    native_ = std::make_unique<FrozenPartialCue>();
    reset();
    if (count == 0U || !native_->prepare(rate)) return false;
    sample_count_ = count;
    valid_ = true;
    return true;
  }
#endif
  void observe(float raw_sample) noexcept {
#if defined(M3_FROZEN_CUE_COOPERATIVE)
    if (valid_ && native_ != nullptr && native_->push(raw_sample)) {
      const auto& frame = native_->frame();
      pending_mask_ = frame.valid ? frame.mask : std::array<std::uint64_t, 2U>{};
      pending_at_ = frame.end_sample + FrozenPartialCue::kAvailabilityDelay;
      pending_ = true;
    }
#else
    (void)raw_sample;
#endif
  }

  bool matches(std::uint32_t rate, std::uint64_t count) const noexcept {
    return valid_ && rate == 96000U && count == sample_count_;
  }
  void reset() noexcept {
#if defined(M3_FROZEN_CUE_COOPERATIVE)
    if (native_ != nullptr) native_->reset();
    pending_mask_ = {};
    pending_at_ = native_expiry_ = 0U;
    pending_ = false;
#endif
    cursor_ = 0U;
    next_transition_ = 0U;
    expiry_.fill(0U);
    mask_.fill(0U);
  }
  // Called in increasing sample order, before consuming the current sample.
  bool advance(std::uint64_t sample) noexcept {
#if defined(M3_FROZEN_CUE_COOPERATIVE)
    if (valid_ && native_ != nullptr) {
      const auto previous = mask_;
      if (sample >= native_expiry_ || sample >= sample_count_) mask_ = {};
      if (pending_ && sample >= pending_at_) {
        if (pending_at_ < sample_count_) {
          native_expiry_ = pending_at_ + std::min<std::uint64_t>(
              FrozenPartialCue::kHop, sample_count_ - pending_at_);
          if (sample < native_expiry_) mask_ = pending_mask_;
        }
        pending_ = false;
      }
      return mask_ != previous;
    }
#endif
    if (!valid_ || sample < next_transition_) return false;
    const auto previous = mask_;
    for (std::size_t note = 0U; note < expiry_.size(); ++note) {
      if (expiry_[note] <= sample) {
        mask_[note / 64U] &= ~(std::uint64_t{1U} << (note % 64U));
      }
    }
    while (cursor_ < spans_.size() && spans_[cursor_].begin <= sample) {
      const auto& span = spans_[cursor_++];
      if (sample < span.end) {
        expiry_[span.note] = span.end;
        mask_[span.note / 64U] |= std::uint64_t{1U} << (span.note % 64U);
      }
    }
    next_transition_ = cursor_ < spans_.size() ? spans_[cursor_].begin :
        std::numeric_limits<std::uint64_t>::max();
    for (const auto expiry : expiry_) {
      if (expiry > sample) next_transition_ = std::min(next_transition_, expiry);
    }
    return previous != mask_;
  }
  const std::array<std::uint64_t, 2U>& mask() const noexcept { return mask_; }

 private:
  struct Span final { std::uint64_t begin, end; unsigned note; };
  std::vector<Span> spans_;
  std::array<std::uint64_t, 128U> expiry_{};
  std::array<std::uint64_t, 2U> mask_{};
  std::size_t cursor_{};
  std::uint64_t next_transition_{}, sample_count_{};
  bool valid_{};
#if defined(M3_FROZEN_CUE_COOPERATIVE)
  std::unique_ptr<FrozenPartialCue> native_;
  std::array<std::uint64_t, 2U> pending_mask_{};
  std::uint64_t pending_at_{}, native_expiry_{};
  bool pending_{};
#endif
};

}  // namespace m3::offline
