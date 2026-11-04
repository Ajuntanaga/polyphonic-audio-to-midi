#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace m3::offline {

// Native reference for the frozen offline cue, not an audio-thread policy.
// Raw input and the fixed A4=440 geometry are its only evidence. A completed
// frame is usable on the NEXT sample and expires after one analysis hop.
class FrozenPartialCue final {
 public:
  static constexpr std::size_t kWindow = 16384U;
  static constexpr std::size_t kFft = 65536U;
  static constexpr std::size_t kHop = 1024U;
  static constexpr unsigned kFirstNote = 32U;
  static constexpr unsigned kLastNote = 84U;
  static constexpr std::size_t kNotes = kLastNote - kFirstNote + 1U;
  static constexpr double kProminence = 8.593275855114637;
  static constexpr double kAgreement = 25.0;

  enum class Reason { missing_peak, missing_reference, below_prominence,
                      missing_agreement, pitch_disagreement, cue };
  struct Peak final {
    bool found{}, reference_available{};
    std::uint32_t bin{};
    double frequency_hz{}, cents{}, power{}, reference_power{}, prominence_db{};
  };
  struct Note final {
    Peak third{}, fifth{};
    Reason reason{Reason::missing_peak};
  };
  struct Frame final {
    std::uint64_t end_sample{};  // Exclusive; first sample that may use this cue.
    bool history_available{}, valid{};
    std::array<Note, kNotes> notes{};
    std::array<std::uint64_t, 2U> mask{};
  };

  FrozenPartialCue() noexcept;
  ~FrozenPartialCue();
  FrozenPartialCue(const FrozenPartialCue&) = delete;
  FrozenPartialCue& operator=(const FrozenPartialCue&) = delete;
  // Allocation and coefficient preparation occur here, outside processing.
  // Only the already-frozen 96 kHz sidecar clock is supported in this probe.
  bool prepare(std::uint32_t sample_rate) noexcept;
  void reset() noexcept;
  // True once per hop, including warmup/invalid frames that clear the cue.
  bool push(float raw_sample) noexcept;
  const Frame& frame() const noexcept { return frame_; }
  static Reason screen(const Peak& third, const Peak& fifth) noexcept;
  static const char* reason_name(Reason reason) noexcept;
  static std::size_t storage_bytes() noexcept;

 private:
  struct Workspace;
  std::unique_ptr<Workspace> workspace_;
  Frame frame_{};
  std::uint64_t samples_{};
  std::size_t next_{}, invalid_samples_{};
  bool prepared_{};
  void measure() noexcept;
};

}  // namespace m3::offline
