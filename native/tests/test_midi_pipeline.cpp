#include <clap/clap.h>
#include <clap/factory/plugin-factory.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

#include "clap_adapter.hpp"
#include "fake_clap_host.hpp"
#include "midi_pipeline.hpp"
#include "test_support.hpp"

namespace {

class MidiInputs final {
 public:
  MidiInputs() noexcept {
    list_.ctx = this;
    list_.size = &size;
    list_.get = &get;
  }

  bool push(std::uint32_t time, std::uint8_t status, std::uint8_t data1,
            std::uint8_t data2) noexcept {
    if (count_ >= events_.size()) {
      return false;
    }
    clap_event_midi_t& event = events_[count_++];
    event = {};
    event.header.size = sizeof(event);
    event.header.time = time;
    event.header.space_id = CLAP_CORE_EVENT_SPACE_ID;
    event.header.type = CLAP_EVENT_MIDI;
    event.port_index = 0;
    event.data[0] = status;
    event.data[1] = data1;
    event.data[2] = data2;
    return true;
  }

  const clap_input_events_t* list() const noexcept { return &list_; }

 private:
  static std::uint32_t CLAP_ABI size(const clap_input_events_t* list) noexcept {
    return static_cast<const MidiInputs*>(list->ctx)->count_;
  }
  static const clap_event_header_t* CLAP_ABI get(const clap_input_events_t* list,
                                                 std::uint32_t index) noexcept {
    const auto* self = static_cast<const MidiInputs*>(list->ctx);
    return index < self->count_ ? &self->events_[index].header : nullptr;
  }

  clap_input_events_t list_{};
  std::array<clap_event_midi_t, 256> events_{};
  std::uint32_t count_{};
};

class MidiOutputs final {
 public:
  MidiOutputs() noexcept {
    list_.ctx = this;
    list_.try_push = &try_push;
  }

  void reset(std::size_t reject_attempt = std::numeric_limits<std::size_t>::max()) noexcept {
    accepted_ = 0;
    attempts_ = 0;
    reject_attempt_ = reject_attempt;
    rejection_used_ = false;
  }
  const clap_output_events_t* list() const noexcept { return &list_; }
  std::size_t size() const noexcept { return accepted_; }
  std::size_t attempts() const noexcept { return attempts_; }
  const clap_event_midi_t& operator[](std::size_t index) const noexcept {
    return events_[index];
  }

 private:
  static bool CLAP_ABI try_push(const clap_output_events_t* list,
                                const clap_event_header_t* header) noexcept {
    auto* self = static_cast<MidiOutputs*>(list->ctx);
    const std::size_t attempt = self->attempts_++;
    if (!self->rejection_used_ && attempt == self->reject_attempt_) {
      self->rejection_used_ = true;
      return false;
    }
    if (header == nullptr || header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
        header->type != CLAP_EVENT_MIDI ||
        header->size < sizeof(clap_event_midi_t) ||
        self->accepted_ >= self->events_.size()) {
      return false;
    }
    self->events_[self->accepted_++] =
        *reinterpret_cast<const clap_event_midi_t*>(header);
    return true;
  }

  clap_output_events_t list_{};
  std::array<clap_event_midi_t, 512> events_{};
  std::size_t accepted_{};
  std::size_t attempts_{};
  std::size_t reject_attempt_{std::numeric_limits<std::size_t>::max()};
  bool rejection_used_{};
};

m3::VoiceTransition transition(std::uint32_t offset, m3::TransitionKind kind,
                               std::uint8_t note, std::uint8_t velocity,
                               std::uint32_t sequence) noexcept {
  return m3::VoiceTransition{offset, kind, note, velocity, sequence};
}

m3::MidiProcessResult process(m3::MidiPipeline& pipeline, std::uint32_t frames,
                              const clap_input_events_t* input,
                              MidiOutputs& output, double peak = 0.0,
                              bool finite = true,
                              bool supported = true) noexcept {
  return pipeline.process(frames, 1, input, output.list(), peak, finite, supported);
}

void establish_active_note(m3::MidiPipeline& pipeline, MidiOutputs& output,
                           std::uint8_t note) noexcept {
  pipeline.begin_block();
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(0, m3::TransitionKind::note_on, note, 100, 1), 32));
  output.reset();
  const m3::MidiProcessResult result = process(
      pipeline, 32, m3::test::FakeClapHost::empty_input_events(), output, 0.5);
  M3_EXPECT_FALSE(result.output_blocked);
  M3_EXPECT_TRUE(pipeline.is_active(note));
}

const clap_plugin_t* create_adapter(m3::test::FakeClapHost& host) noexcept {
  M3_EXPECT_TRUE(clap_entry.init("/build/test/M3.clap"));
  const auto* factory = static_cast<const clap_plugin_factory_t*>(
      clap_entry.get_factory(CLAP_PLUGIN_FACTORY_ID));
  M3_EXPECT_TRUE(factory != nullptr);
  const auto* descriptor = factory->get_plugin_descriptor(factory, 0);
  M3_EXPECT_TRUE(descriptor != nullptr);
  const clap_plugin_t* plugin =
      factory->create_plugin(factory, host.host(), descriptor->id);
  M3_EXPECT_TRUE(plugin != nullptr);
  M3_EXPECT_TRUE(plugin->init(plugin));
  return plugin;
}

}  // namespace

M3_TEST(midi_merge_orders_off_input_and_on_at_equal_offsets) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(128));
  MidiOutputs output;
  establish_active_note(pipeline, output, 60);

  pipeline.begin_block();
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(31, m3::TransitionKind::note_on, 72, 90, 3), 32));
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(5, m3::TransitionKind::note_on, 62, 80, 2), 32));
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(5, m3::TransitionKind::note_off, 60, 0, 1), 32));
  MidiInputs input;
  M3_EXPECT_TRUE(input.push(0, 0xB0, 1, 10));
  M3_EXPECT_TRUE(input.push(5, 0xB0, 2, 20));
  output.reset();
  const m3::MidiProcessResult result = process(pipeline, 32, input.list(), output, 0.5);
  M3_EXPECT_FALSE(result.output_blocked);
  M3_EXPECT_EQ(output.size(), 5U);
  M3_EXPECT_EQ(output[0].header.time, 0U);
  M3_EXPECT_EQ(output[0].data[0], 0xB0U);
  M3_EXPECT_EQ(output[1].header.time, 5U);
  M3_EXPECT_EQ(output[1].data[0], 0x80U);
  M3_EXPECT_EQ(output[1].data[1], 60U);
  M3_EXPECT_EQ(output[2].header.time, 5U);
  M3_EXPECT_EQ(output[2].data[0], 0xB0U);
  M3_EXPECT_EQ(output[2].data[1], 2U);
  M3_EXPECT_EQ(output[3].header.time, 5U);
  M3_EXPECT_EQ(output[3].data[0], 0x90U);
  M3_EXPECT_EQ(output[3].data[1], 62U);
  M3_EXPECT_EQ(output[4].header.time, 31U);
  M3_EXPECT_EQ(output[4].data[1], 72U);
}

M3_TEST(midi_queue_validates_capacity_offsets_and_midi_bounds) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(16384));
  M3_EXPECT_EQ(pipeline.capacity(), 4106U);
  pipeline.begin_block();
  M3_EXPECT_FALSE(pipeline.queue_transition(
      transition(32, m3::TransitionKind::note_on, 60, 100, 1), 32));
  M3_EXPECT_FALSE(pipeline.queue_transition(
      transition(0, m3::TransitionKind::note_on, 255, 100, 1), 32));
  M3_EXPECT_FALSE(pipeline.queue_transition(
      transition(0, m3::TransitionKind::note_on, 60, 255, 1), 32));
  M3_EXPECT_FALSE(pipeline.queue_transition(
      transition(0, static_cast<m3::TransitionKind>(9), 60, 100, 1), 32));
  MidiOutputs output;
  output.reset();
  const m3::MidiProcessResult result = pipeline.process(
      32, 0, m3::test::FakeClapHost::empty_input_events(), output.list(),
      0.0, true, true);
  M3_EXPECT_TRUE(result.invalid_event);
  M3_EXPECT_EQ(output.size(), 0U);
}

M3_TEST(midi_failure_never_activates_rejected_on_and_retains_accepted_notes) {
  for (std::size_t rejected_push = 0; rejected_push < 2; ++rejected_push) {
    m3::MidiPipeline pipeline;
    M3_EXPECT_TRUE(pipeline.activate(128));
    pipeline.begin_block();
    M3_EXPECT_TRUE(pipeline.queue_transition(
        transition(0, m3::TransitionKind::note_on, 60, 100, 1), 32));
    M3_EXPECT_TRUE(pipeline.queue_transition(
        transition(1, m3::TransitionKind::note_on, 61, 100, 2), 32));
    MidiOutputs output;
    output.reset(rejected_push);
    const m3::MidiProcessResult result = process(
        pipeline, 32, m3::test::FakeClapHost::empty_input_events(), output, 0.5);
    M3_EXPECT_TRUE(result.output_blocked);
    M3_EXPECT_EQ(pipeline.is_active(60), rejected_push == 1U);
    M3_EXPECT_EQ(pipeline.is_pending_release(60), rejected_push == 1U);
    M3_EXPECT_FALSE(pipeline.is_active(61));
    M3_EXPECT_FALSE(pipeline.is_pending_release(61));
  }
}

M3_TEST(midi_rejected_off_retries_at_zero_before_both_channel_panics_and_input) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(128));
  MidiOutputs output;
  establish_active_note(pipeline, output, 60);
  pipeline.begin_block();
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(7, m3::TransitionKind::note_off, 60, 0, 2), 32));
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(8, m3::TransitionKind::note_on, 62, 90, 3), 32));
  output.reset(0);
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .output_blocked);
  M3_EXPECT_TRUE(pipeline.is_pending_release(60));
  M3_EXPECT_FALSE(pipeline.is_active(62));

  pipeline.begin_block();
  MidiInputs input;
  M3_EXPECT_TRUE(input.push(0, 0xB0, 1, 64));
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(0, m3::TransitionKind::note_on, 70, 100, 4), 32));
  output.reset();
  M3_EXPECT_TRUE(process(pipeline, 32, input.list(), output).output_blocked);
  M3_EXPECT_EQ(output.size(), 4U);
  M3_EXPECT_EQ(output[0].data[0], 0x80U);
  M3_EXPECT_EQ(output[0].data[1], 60U);
  M3_EXPECT_EQ(output[1].data[1], 123U);
  M3_EXPECT_EQ(output[2].data[1], 120U);
  M3_EXPECT_EQ(output[3].data[1], 1U);
  M3_EXPECT_FALSE(pipeline.is_active(70));
}

M3_TEST(midi_channel_panics_must_both_succeed_in_one_cleanup_call) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(128));
  MidiOutputs output;
  establish_active_note(pipeline, output, 60);
  pipeline.begin_block();
  MidiInputs input;
  M3_EXPECT_TRUE(input.push(0, 0xB0, 7, 1));
  output.reset(0);
  M3_EXPECT_TRUE(process(pipeline, 32, input.list(), output).output_blocked);

  pipeline.begin_block();
  output.reset(2);
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .output_blocked);
  M3_EXPECT_EQ(output.size(), 2U);
  M3_EXPECT_EQ(output[0].data[1], 60U);
  M3_EXPECT_EQ(output[1].data[1], 123U);

  pipeline.begin_block();
  output.reset();
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .output_blocked);
  M3_EXPECT_EQ(output.size(), 2U);
  M3_EXPECT_EQ(output[0].data[1], 123U);
  M3_EXPECT_EQ(output[1].data[1], 120U);
}

M3_TEST(midi_cleanup_does_not_replay_failed_input_and_requires_explicit_recovery) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(128));
  MidiInputs input;
  M3_EXPECT_TRUE(input.push(0, 0xB0, 74, 55));
  MidiOutputs output;
  pipeline.begin_block();
  output.reset(0);
  M3_EXPECT_TRUE(process(pipeline, 32, input.list(), output).output_blocked);
  pipeline.begin_block();
  output.reset();
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .output_blocked);
  for (std::size_t index = 0; index < output.size(); ++index) {
    M3_EXPECT_FALSE(output[index].data[1] == 74U);
  }
  pipeline.begin_block();
  output.reset();
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .output_blocked);

  pipeline.begin_block();
  pipeline.request_reset();
  output.reset();
  M3_EXPECT_TRUE(process(pipeline, 32,
                          m3::test::FakeClapHost::empty_input_events(), output)
                     .panic_hold);
  pipeline.begin_block();
  output.reset();
  const m3::MidiProcessResult recovered = process(
      pipeline, 32, m3::test::FakeClapHost::empty_input_events(), output);
  M3_EXPECT_FALSE(recovered.output_blocked);
  M3_EXPECT_FALSE(recovered.panic_hold);
  M3_EXPECT_TRUE(recovered.detection_allowed);
}

M3_TEST(midi_panic_hold_needs_a_later_quiet_finite_supported_call) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(128));
  MidiOutputs output;
  establish_active_note(pipeline, output, 60);
  pipeline.begin_block();
  M3_EXPECT_TRUE(pipeline.request_panic(9, 32));
  M3_EXPECT_TRUE(pipeline.queue_transition(
      transition(10, m3::TransitionKind::note_on, 62, 100, 2), 32));
  output.reset();
  m3::MidiProcessResult result = process(
      pipeline, 32, m3::test::FakeClapHost::empty_input_events(), output, 0.0);
  M3_EXPECT_TRUE(result.panic_hold);
  M3_EXPECT_EQ(output.size(), 1U);
  M3_EXPECT_EQ(output[0].header.time, 9U);
  M3_EXPECT_EQ(output[0].data[0], 0x80U);

  pipeline.begin_block();
  output.reset();
  result = process(pipeline, 32, m3::test::FakeClapHost::empty_input_events(),
                   output, 0.1);
  M3_EXPECT_TRUE(result.panic_hold);
  pipeline.begin_block();
  output.reset();
  result = process(pipeline, 32, m3::test::FakeClapHost::empty_input_events(),
                   output, 0.0, false, true);
  M3_EXPECT_TRUE(result.panic_hold);
  pipeline.begin_block();
  output.reset();
  result = process(pipeline, 32, m3::test::FakeClapHost::empty_input_events(),
                   output, 0.0, true, false);
  M3_EXPECT_TRUE(result.panic_hold);
  pipeline.begin_block();
  output.reset();
  result = process(pipeline, 32, m3::test::FakeClapHost::empty_input_events(),
                   output, 0.0, true, true);
  M3_EXPECT_FALSE(result.panic_hold);
  M3_EXPECT_TRUE(result.detection_allowed);
}

M3_TEST(midi_processing_performs_no_heap_work_after_activation) {
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(16384));
  MidiInputs input;
  for (std::uint32_t index = 0; index < 256; ++index) {
    M3_EXPECT_TRUE(input.push(index, 0xB0, static_cast<std::uint8_t>(index % 120U),
                              static_cast<std::uint8_t>(index % 128U)));
  }
  pipeline.begin_block();
  for (std::uint32_t index = 0; index < 128; ++index) {
    M3_EXPECT_TRUE(pipeline.queue_transition(
        transition(index * 64U, m3::TransitionKind::note_on,
                   static_cast<std::uint8_t>(index), 100, index), 16384));
  }
  MidiOutputs output;
  output.reset();
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  static_cast<void>(process(pipeline, 16384, input.list(), output, 0.5));
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
}

M3_TEST(midi_output_failure_does_not_interrupt_adapter_dry_audio) {
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_adapter(host);
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 128));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));
  M3_EXPECT_TRUE(m3::queue_transition_for_test(
      plugin, transition(0, m3::TransitionKind::note_on, 60, 100, 1), 32));
  m3::test::FakeProcessBlock<float> block;
  block.configure(32, false);
  block.fill_finite();
  MidiOutputs output;
  output.reset(0);
  block.set_output_events(output.list());
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
    M3_EXPECT_EQ(block.output_right()[frame], block.input_right()[frame]);
  }
  M3_EXPECT_EQ(m3::adapter_status_for_test(plugin),
               m3::Status::midi_output_blocked);
  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}
