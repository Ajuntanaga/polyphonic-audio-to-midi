#include "m3/tuner_telemetry.hpp"

#include <algorithm>

namespace m3 {
namespace {

constexpr std::uint32_t kVoiceCountMask = 0x0FU;
constexpr std::uint32_t kFrameStateShift = 8U;
constexpr std::uint32_t kMaxPolyphonyShift = 16U;
constexpr std::uint32_t kVoiceStateShift = 8U;
constexpr std::uint32_t kCentsValidBit = 1U << 10U;
constexpr std::uint32_t kCentsShift = 16U;
constexpr std::uint32_t kAgeShift = 16U;
constexpr std::int16_t kMinimumCentsQ8 = -50 * 256;
constexpr std::int16_t kMaximumCentsQ8 = 50 * 256;
constexpr std::uint16_t kMaximumConfidenceQ15 = 32767U;

static_assert(std::atomic<std::uint32_t>::is_always_lock_free,
              "M3 tuner telemetry requires lock-free 32-bit atomics");

std::uint32_t pack_header(TunerFrameState state, std::uint8_t voice_count,
                          std::uint8_t max_polyphony) noexcept {
  const std::uint32_t safe_state =
      std::min<std::uint32_t>(static_cast<std::uint32_t>(state),
                              static_cast<std::uint32_t>(TunerFrameState::tracking));
  const std::uint32_t safe_count =
      std::min<std::uint32_t>(voice_count, static_cast<std::uint32_t>(kMaxVoices));
  const std::uint32_t safe_max = std::clamp<std::uint32_t>(
      max_polyphony, 1U, static_cast<std::uint32_t>(kMaxVoices));
  return (safe_max << kMaxPolyphonyShift) | (safe_state << kFrameStateShift) |
         safe_count;
}

TunerFrameState unpack_frame_state(std::uint32_t header) noexcept {
  const std::uint32_t raw = (header >> kFrameStateShift) & 0xFFU;
  return raw <= static_cast<std::uint32_t>(TunerFrameState::tracking)
             ? static_cast<TunerFrameState>(raw)
             : TunerFrameState::unavailable;
}

std::uint8_t unpack_max_polyphony(std::uint32_t header) noexcept {
  return static_cast<std::uint8_t>(std::clamp<std::uint32_t>(
      header >> kMaxPolyphonyShift, 1U, static_cast<std::uint32_t>(kMaxVoices)));
}

std::uint32_t pack_voice_a(const TunerVoice& voice) noexcept {
  const std::uint32_t safe_state =
      std::min<std::uint32_t>(static_cast<std::uint32_t>(voice.state),
                              static_cast<std::uint32_t>(TunerVoiceState::tracking));
  const std::int16_t cents =
      std::clamp(voice.cents_q8, kMinimumCentsQ8, kMaximumCentsQ8);
  return static_cast<std::uint32_t>(std::min<std::uint8_t>(voice.midi_note, 127U)) |
         (safe_state << kVoiceStateShift) |
         (voice.cents_valid ? kCentsValidBit : 0U) |
         (static_cast<std::uint32_t>(static_cast<std::uint16_t>(cents))
          << kCentsShift);
}

std::uint32_t pack_voice_b(const TunerVoice& voice) noexcept {
  const std::uint16_t confidence =
      std::min<std::uint16_t>(voice.confidence_q15, kMaximumConfidenceQ15);
  return static_cast<std::uint32_t>(confidence) |
         (static_cast<std::uint32_t>(voice.age_ticks) << kAgeShift);
}

TunerVoice unpack_voice(std::uint32_t word_a, std::uint32_t word_b) noexcept {
  TunerVoice voice;
  voice.midi_note = static_cast<std::uint8_t>(word_a & 0xFFU);
  const std::uint32_t raw_state = (word_a >> kVoiceStateShift) & 0x03U;
  voice.state = raw_state <= static_cast<std::uint32_t>(TunerVoiceState::tracking)
                    ? static_cast<TunerVoiceState>(raw_state)
                    : TunerVoiceState::settling;
  voice.cents_valid = (word_a & kCentsValidBit) != 0U;
  voice.cents_q8 = static_cast<std::int16_t>(word_a >> kCentsShift);
  voice.confidence_q15 = static_cast<std::uint16_t>(word_b & 0xFFFFU);
  voice.age_ticks = static_cast<std::uint16_t>(word_b >> kAgeShift);
  return voice;
}

}  // namespace

void TunerTelemetry::publish(const TunerSnapshot& snapshot) noexcept {
  const std::uint32_t before = sequence_.load(std::memory_order_seq_cst);
  const std::uint32_t writing = before | 1U;
  sequence_.store(writing, std::memory_order_seq_cst);

  const std::uint8_t count = static_cast<std::uint8_t>(
      std::min<std::size_t>(snapshot.voice_count, kMaxVoices));
  header_.store(pack_header(snapshot.state, count, snapshot.max_polyphony),
                std::memory_order_seq_cst);
  for (std::size_t index = 0U; index < kMaxVoices; ++index) {
    const TunerVoice voice = index < count ? snapshot.voices[index] : TunerVoice{};
    voice_words_a_[index].store(pack_voice_a(voice), std::memory_order_seq_cst);
    voice_words_b_[index].store(pack_voice_b(voice), std::memory_order_seq_cst);
  }
  // The transport, rather than the detector, owns UI generations. Detector
  // resets are allowed to restart their local counters; doing so must never
  // make an attached editor mistake a fresh frame for a cached one.
  static_cast<void>(generation_.fetch_add(1U, std::memory_order_seq_cst));
  sequence_.store(writing + 1U, std::memory_order_seq_cst);
}

void TunerTelemetry::clear(TunerFrameState state) noexcept {
  TunerSnapshot snapshot;
  snapshot.state = state;
  publish(snapshot);
}

bool TunerTelemetry::read_latest(TunerSnapshot& snapshot) const noexcept {
  for (std::size_t attempt = 0U; attempt < kReadAttempts; ++attempt) {
    const std::uint32_t before = sequence_.load(std::memory_order_seq_cst);
    if ((before & 1U) != 0U || before == 0U) {
      continue;
    }
    const std::uint32_t header = header_.load(std::memory_order_seq_cst);
    const std::uint8_t count = static_cast<std::uint8_t>(
        std::min<std::uint32_t>(header & kVoiceCountMask,
                                static_cast<std::uint32_t>(kMaxVoices)));
    TunerSnapshot candidate;
    candidate.generation = generation_.load(std::memory_order_seq_cst);
    candidate.state = unpack_frame_state(header);
    candidate.voice_count = count;
    candidate.max_polyphony = unpack_max_polyphony(header);
    for (std::size_t index = 0U; index < count; ++index) {
      candidate.voices[index] = unpack_voice(
          voice_words_a_[index].load(std::memory_order_seq_cst),
          voice_words_b_[index].load(std::memory_order_seq_cst));
    }
    const std::uint32_t after = sequence_.load(std::memory_order_seq_cst);
    if (before == after && (after & 1U) == 0U) {
      snapshot = candidate;
      return true;
    }
  }
  return false;
}

}  // namespace m3
