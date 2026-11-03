#pragma once

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <limits>
#include <string_view>
#include <system_error>
#include <vector>

namespace m3::offline {

// Offline-only, zero-based input sample clock. A cue covers [begin, end).
// The fixed window is complete before begin; labels and string IDs are absent.
class FrozenNoteCues final {
 public:
  bool parse(std::string_view text, std::uint32_t sample_rate,
             std::uint64_t sample_count) {
    spans_.clear();
    reset();
    valid_ = false;
    constexpr std::string_view header = "m3_frozen_note_cues_v1\t96000\t1024\n";
    if (sample_rate != 96000U || sample_count == 0U ||
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
    sample_count_ = sample_count;
    valid_ = true;
    return true;
  }

  bool matches(std::uint32_t rate, std::uint64_t count) const noexcept {
    return valid_ && rate == 96000U && count == sample_count_;
  }
  void reset() noexcept {
    cursor_ = 0U;
    next_transition_ = 0U;
    expiry_.fill(0U);
    mask_.fill(0U);
  }
  // Called in increasing sample order, before consuming the current sample.
  bool advance(std::uint64_t sample) noexcept {
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
};

}  // namespace m3::offline
