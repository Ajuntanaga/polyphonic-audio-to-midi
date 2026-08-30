#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "m3/generated_note_ledger.hpp"
#include "test_support.hpp"

namespace {

class NoteCapture final {
 public:
  explicit NoteCapture(
      std::size_t reject_attempt = std::numeric_limits<std::size_t>::max(),
      std::uint8_t external_channel = 1) noexcept
      : reject_attempt_(reject_attempt), external_channel_(external_channel) {}

  m3::NoteEventSink sink() noexcept {
    return m3::NoteEventSink{this, &push};
  }

  [[nodiscard]] std::size_t size() const noexcept { return size_; }
  [[nodiscard]] std::size_t attempts() const noexcept { return attempts_; }
  [[nodiscard]] std::uint8_t external_channel() const noexcept {
    return external_channel_;
  }
  const m3::VoiceTransition& operator[](std::size_t index) const noexcept {
    return events_[index];
  }

 private:
  static bool push(void* context,
                   const m3::VoiceTransition& transition) noexcept {
    auto* self = static_cast<NoteCapture*>(context);
    const std::size_t attempt = self->attempts_++;
    if (!self->rejection_used_ && attempt == self->reject_attempt_) {
      self->rejection_used_ = true;
      return false;
    }
    if (self->size_ >= self->events_.size()) {
      return false;
    }
    self->events_[self->size_++] = transition;
    return true;
  }

  std::array<m3::VoiceTransition, 4112> events_{};
  std::size_t size_{};
  std::size_t attempts_{};
  std::size_t reject_attempt_{};
  std::uint8_t external_channel_{};
  bool rejection_used_{};
};

m3::VoiceTransition transition(std::uint32_t offset,
                               m3::TransitionKind kind,
                               std::uint8_t note,
                               std::uint8_t velocity,
                               std::uint32_t sequence) noexcept {
  return m3::VoiceTransition{offset, kind, note, velocity, sequence};
}

m3::NoteDeliveryResult deliver(m3::GeneratedNoteLedger& ledger,
                               std::uint32_t frames, NoteCapture& capture,
                               double peak = 0.0, bool finite = true,
                               bool supported = true) noexcept {
  return ledger.deliver(frames, capture.sink(), peak, finite, supported);
}

void establish_note(m3::GeneratedNoteLedger& ledger, std::uint8_t note,
                    std::uint32_t sequence = 1) noexcept {
  ledger.begin_block();
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_on, note, 100, sequence), 32));
  NoteCapture capture;
  const m3::NoteDeliveryResult result = deliver(ledger, 32, capture, 0.5);
  M3_EXPECT_FALSE(result.output_blocked);
  M3_EXPECT_TRUE(ledger.is_active(note));
}

}  // namespace

M3_TEST(generated_note_ledger_validates_activation_capacity_and_boundaries) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_FALSE(ledger.activate(0));
  M3_EXPECT_FALSE(ledger.activate(16385));
  M3_EXPECT_TRUE(ledger.activate(1));
  M3_EXPECT_EQ(ledger.capacity(), 24U);
  ledger.begin_block();
  NoteCapture oversized;
  M3_EXPECT_FALSE(deliver(ledger, 2, oversized).detection_allowed);
  M3_EXPECT_TRUE(ledger.activate(16384));
  M3_EXPECT_EQ(ledger.capacity(), 4104U);

  ledger.begin_block();
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_on, 0, 1, 1), 16384));
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(16383, m3::TransitionKind::note_on, 127, 127, 2), 16384));
  NoteCapture capture(std::numeric_limits<std::size_t>::max(), 16);
  const m3::NoteDeliveryResult result = deliver(ledger, 16384, capture, 0.5);
  M3_EXPECT_TRUE(result.detection_allowed);
  M3_EXPECT_EQ(capture.size(), 2U);
  M3_EXPECT_EQ(capture[0].sample_offset, 0U);
  M3_EXPECT_EQ(capture[0].note, 0U);
  M3_EXPECT_EQ(capture[1].sample_offset, 16383U);
  M3_EXPECT_EQ(capture[1].note, 127U);
  M3_EXPECT_EQ(capture.external_channel(), 16U);

  ledger.begin_block();
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(32, m3::TransitionKind::note_on, 60, 100, 3), 32));
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_on, 255, 100, 4), 32));
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_on, 60, 0, 5), 32));
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_off, 60, 1, 6), 32));
  NoteCapture invalid_capture;
  M3_EXPECT_FALSE(deliver(ledger, 32, invalid_capture).detection_allowed);
}

M3_TEST(generated_note_ledger_orders_ticks_and_equal_time_off_before_on) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(192));
  establish_note(ledger, 60);

  ledger.begin_block();
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(191, m3::TransitionKind::note_on, 64, 70, 4), 192));
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(64, m3::TransitionKind::note_on, 62, 80, 3), 192));
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(64, m3::TransitionKind::note_off, 60, 0, 2), 192));
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(128, m3::TransitionKind::note_on, 63, 90, 1), 192));
  NoteCapture capture;
  const m3::NoteDeliveryResult result = deliver(ledger, 192, capture, 0.5);
  M3_EXPECT_TRUE(result.detection_allowed);
  M3_EXPECT_EQ(capture.size(), 4U);
  M3_EXPECT_EQ(capture[0].kind, m3::TransitionKind::note_off);
  M3_EXPECT_EQ(capture[0].sample_offset, 64U);
  M3_EXPECT_EQ(capture[1].kind, m3::TransitionKind::note_on);
  M3_EXPECT_EQ(capture[1].sample_offset, 64U);
  M3_EXPECT_EQ(capture[2].sample_offset, 128U);
  M3_EXPECT_EQ(capture[3].sample_offset, 191U);
}

M3_TEST(generated_note_ledger_accepts_exact_capacity_then_flags_overflow) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(16384));
  ledger.begin_block();
  for (std::size_t index = 0; index < ledger.capacity(); ++index) {
    const std::uint32_t tick = static_cast<std::uint32_t>(index / 16U);
    const std::uint32_t offset = tick < 256U ? tick * 64U : 16383U;
    M3_EXPECT_TRUE(ledger.queue_transition(
        transition(offset, m3::TransitionKind::note_on,
                   static_cast<std::uint8_t>(index % 128U), 100,
                   static_cast<std::uint32_t>(index)),
        16384));
  }
  M3_EXPECT_FALSE(ledger.queue_transition(
      transition(16383, m3::TransitionKind::note_on, 1, 100, 4105), 16384));
  NoteCapture capture;
  M3_EXPECT_FALSE(deliver(ledger, 16384, capture, 0.5).detection_allowed);
}

M3_TEST(generated_note_ledger_fails_closed_on_duplicate_on_and_stray_off) {
  {
    m3::GeneratedNoteLedger ledger;
    M3_EXPECT_TRUE(ledger.activate(32));
    establish_note(ledger, 60);
    ledger.begin_block();
    M3_EXPECT_TRUE(ledger.queue_transition(
        transition(0, m3::TransitionKind::note_on, 60, 100, 2), 32));
    NoteCapture capture;
    const m3::NoteDeliveryResult result = deliver(ledger, 32, capture, 0.5);
    M3_EXPECT_TRUE(result.output_blocked);
    M3_EXPECT_EQ(capture.size(), 0U);
    M3_EXPECT_TRUE(ledger.is_active(60));
    M3_EXPECT_TRUE(ledger.is_pending_release(60));
  }
  {
    m3::GeneratedNoteLedger ledger;
    M3_EXPECT_TRUE(ledger.activate(32));
    ledger.begin_block();
    M3_EXPECT_TRUE(ledger.queue_transition(
        transition(31, m3::TransitionKind::note_off, 61, 0, 1), 32));
    NoteCapture capture;
    const m3::NoteDeliveryResult result = deliver(ledger, 32, capture, 0.5);
    M3_EXPECT_TRUE(result.output_blocked);
    M3_EXPECT_EQ(capture.size(), 0U);
    M3_EXPECT_FALSE(ledger.is_active(61));
    M3_EXPECT_FALSE(ledger.is_pending_release(61));
  }
}

M3_TEST(generated_note_ledger_release_all_is_individual_and_pitch_ascending) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(32));
  ledger.begin_block();
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(0, m3::TransitionKind::note_on, 127, 100, 1), 32));
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(1, m3::TransitionKind::note_on, 0, 100, 2), 32));
  NoteCapture ons;
  M3_EXPECT_TRUE(deliver(ledger, 32, ons, 0.5).detection_allowed);

  ledger.begin_block();
  ledger.request_release_all();
  NoteCapture offs;
  const m3::NoteDeliveryResult result = deliver(ledger, 32, offs, 0.0);
  M3_EXPECT_FALSE(result.output_blocked);
  M3_EXPECT_EQ(offs.size(), 2U);
  M3_EXPECT_EQ(offs[0].sample_offset, 0U);
  M3_EXPECT_EQ(offs[0].kind, m3::TransitionKind::note_off);
  M3_EXPECT_EQ(offs[0].note, 0U);
  M3_EXPECT_EQ(offs[1].note, 127U);
  M3_EXPECT_FALSE(ledger.is_active(0));
  M3_EXPECT_FALSE(ledger.is_active(127));
}

M3_TEST(generated_note_ledger_rejection_never_activates_later_notes) {
  for (std::size_t rejected = 0; rejected < 3; ++rejected) {
    m3::GeneratedNoteLedger ledger;
    M3_EXPECT_TRUE(ledger.activate(64));
    ledger.begin_block();
    for (std::uint8_t index = 0; index < 3; ++index) {
      M3_EXPECT_TRUE(ledger.queue_transition(
          transition(index, m3::TransitionKind::note_on,
                     static_cast<std::uint8_t>(60U + index), 100, index),
          64));
    }
    NoteCapture rejected_sink(rejected);
    const m3::NoteDeliveryResult failed =
        deliver(ledger, 64, rejected_sink, 0.5);
    M3_EXPECT_TRUE(failed.output_blocked);
    for (std::size_t index = 0; index < 3; ++index) {
      const auto note = static_cast<std::uint8_t>(60U + index);
      M3_EXPECT_EQ(ledger.is_active(note), index < rejected);
      M3_EXPECT_EQ(ledger.is_pending_release(note), index < rejected);
    }

    ledger.begin_block();
    M3_EXPECT_TRUE(ledger.queue_transition(
        transition(1, m3::TransitionKind::note_on, 70, 100, 4), 64));
    NoteCapture cleanup;
    const m3::NoteDeliveryResult inhibited = deliver(ledger, 64, cleanup);
    M3_EXPECT_TRUE(inhibited.output_blocked);
    M3_EXPECT_EQ(cleanup.size(), rejected);
    for (std::size_t index = 0; index < cleanup.size(); ++index) {
      M3_EXPECT_EQ(cleanup[index].sample_offset, 0U);
      M3_EXPECT_EQ(cleanup[index].kind, m3::TransitionKind::note_off);
      if (index > 0) {
        M3_EXPECT_TRUE(cleanup[index - 1U].note < cleanup[index].note);
      }
    }
    M3_EXPECT_FALSE(ledger.is_active(70));
  }
}

M3_TEST(generated_note_ledger_blocks_a_ninth_active_voice_before_delivery) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(32));
  ledger.begin_block();
  for (std::uint8_t voice = 0; voice < 9U; ++voice) {
    M3_EXPECT_TRUE(ledger.queue_transition(
        transition(voice, m3::TransitionKind::note_on,
                   static_cast<std::uint8_t>(40U + voice), 100, voice),
        32));
  }
  NoteCapture capture;
  const m3::NoteDeliveryResult result = deliver(ledger, 32, capture, 0.5);
  M3_EXPECT_TRUE(result.output_blocked);
  M3_EXPECT_EQ(capture.size(), m3::kMaxVoices);
  for (std::uint8_t voice = 0; voice < 9U; ++voice) {
    const std::uint8_t note = static_cast<std::uint8_t>(40U + voice);
    M3_EXPECT_EQ(ledger.is_active(note), voice < m3::kMaxVoices);
    M3_EXPECT_EQ(ledger.is_pending_release(note), voice < m3::kMaxVoices);
  }
}

M3_TEST(generated_note_ledger_retries_each_cleanup_rejection_in_one_pass) {
  for (std::size_t rejected = 0; rejected < 3; ++rejected) {
    m3::GeneratedNoteLedger ledger;
    M3_EXPECT_TRUE(ledger.activate(32));
    ledger.begin_block();
    for (const std::uint8_t note : {std::uint8_t{127}, std::uint8_t{60},
                                    std::uint8_t{0}}) {
      M3_EXPECT_TRUE(ledger.queue_transition(
          transition(0, m3::TransitionKind::note_on, note, 100, note), 32));
    }
    NoteCapture ons;
    M3_EXPECT_TRUE(deliver(ledger, 32, ons, 0.5).detection_allowed);

    ledger.begin_block();
    ledger.request_release_all();
    NoteCapture rejected_sink(rejected);
    M3_EXPECT_TRUE(deliver(ledger, 32, rejected_sink).output_blocked);
    M3_EXPECT_EQ(rejected_sink.attempts(), rejected + 1U);

    ledger.begin_block();
    ledger.request_recovery();
    NoteCapture retry;
    const m3::NoteDeliveryResult holding = deliver(ledger, 32, retry);
    M3_EXPECT_TRUE(holding.output_blocked);
    M3_EXPECT_TRUE(holding.panic_hold);
    M3_EXPECT_EQ(retry.size(), 3U - rejected);
    for (std::size_t index = 0; index < retry.size(); ++index) {
      M3_EXPECT_EQ(retry[index].sample_offset, 0U);
      if (index > 0) {
        M3_EXPECT_TRUE(retry[index - 1U].note < retry[index].note);
      }
    }

    ledger.begin_block();
    NoteCapture quiet;
    const m3::NoteDeliveryResult recovered = deliver(ledger, 32, quiet);
    M3_EXPECT_FALSE(recovered.output_blocked);
    M3_EXPECT_FALSE(recovered.panic_hold);
    M3_EXPECT_TRUE(recovered.detection_allowed);
  }
}

M3_TEST(generated_note_ledger_null_sink_and_delivery_are_allocation_free) {
  m3::GeneratedNoteLedger ledger;
  M3_EXPECT_TRUE(ledger.activate(128));
  ledger.begin_block();
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  const m3::NoteDeliveryResult empty =
      ledger.deliver(32, m3::NoteEventSink{}, 0.0, true, true);
  M3_EXPECT_TRUE(empty.detection_allowed);
  M3_EXPECT_TRUE(ledger.queue_transition(
      transition(31, m3::TransitionKind::note_on, 60, 100, 1), 32));
  const m3::NoteDeliveryResult rejected =
      ledger.deliver(32, m3::NoteEventSink{}, 0.5, true, true);
  M3_EXPECT_TRUE(rejected.output_blocked);
  M3_EXPECT_FALSE(ledger.is_active(60));
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
}
