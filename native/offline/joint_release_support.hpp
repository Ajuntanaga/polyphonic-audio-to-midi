#pragma once

#include <array>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

namespace m3::offline {

// Measured model deliveries, not nominal model-frame times. Parsing may
// allocate; monotonically advancing the tape and resetting it never do.
class JointReleaseSupport final {
 public:
  bool parse(std::string_view text, std::uint32_t rate, std::uint64_t count) {
    valid_ = false;
    events_.clear();
    reset();
    constexpr std::string_view header = "m3_joint_release_support_v1\t96000\n";
    if (rate != 96000U || count == 0U || text.substr(0U, header.size()) != header)
      return false;
    text.remove_prefix(header.size());
    std::array<bool, 128U> active{};
    std::uint64_t previous = 0U;
    while (!text.empty()) {
      std::array<std::uint64_t, 3U> fields{};
      for (std::size_t i = 0U; i < fields.size(); ++i) {
        const auto size = text.find(i == 2U ? '\n' : '\t');
        if (size == std::string_view::npos || size == 0U) return false;
        const auto parsed = std::from_chars(text.data(), text.data() + size, fields[i]);
        if (parsed.ec != std::errc{} || parsed.ptr != text.data() + size) return false;
        text.remove_prefix(size + 1U);
      }
      const auto sample = fields[0U], on = fields[1U], note = fields[2U];
      if (sample < previous || sample >= count || on > 1U || note > 127U ||
          active[note] == (on != 0U) || events_.size() >= 1000000U) return false;
      active[note] = on != 0U;
      previous = sample;
      events_.push_back({sample, static_cast<std::uint8_t>(note), on != 0U});
    }
    sample_count_ = count;
    valid_ = true;
    return true;
  }
  bool matches(std::uint32_t rate, std::uint64_t count) const noexcept {
    return valid_ && rate == 96000U && count == sample_count_;
  }
  void reset() noexcept { cursor_ = 0U; mask_ = {}; primed_ = false; }
  bool advance(std::uint64_t sample) noexcept {
    bool changed = false;
    while (valid_ && cursor_ < events_.size() && events_[cursor_].sample <= sample) {
      const auto& event = events_[cursor_++];
      const auto bit = std::uint64_t{1U} << (event.note % 64U);
      if (event.on) { mask_[event.note / 64U] |= bit; primed_ = true; }
      else mask_[event.note / 64U] &= ~bit;
      changed = true;
    }
    return changed;
  }
  const std::array<std::uint64_t, 2U>& mask() const noexcept { return mask_; }
  bool primed() const noexcept { return primed_; }

 private:
  struct Event final { std::uint64_t sample; std::uint8_t note; bool on; };
  std::vector<Event> events_;
  std::array<std::uint64_t, 2U> mask_{};
  std::size_t cursor_{};
  std::uint64_t sample_count_{};
  bool valid_{}, primed_{};
};

}  // namespace m3::offline
