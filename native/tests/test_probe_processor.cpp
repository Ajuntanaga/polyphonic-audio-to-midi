#include <clap/events.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include <unistd.h>

#include "clap_adapter.hpp"
#include "fake_clap_host.hpp"
#include "midi_pipeline.hpp"
#include "probe_processor.hpp"
#include "test_support.hpp"

namespace {

class ProbeMidiInputs final {
 public:
  ProbeMidiInputs() noexcept {
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
    return static_cast<const ProbeMidiInputs*>(list->ctx)->count_;
  }

  static const clap_event_header_t* CLAP_ABI get(
      const clap_input_events_t* list, std::uint32_t index) noexcept {
    const auto* self = static_cast<const ProbeMidiInputs*>(list->ctx);
    return index < self->count_ ? &self->events_[index].header : nullptr;
  }

  clap_input_events_t list_{};
  std::array<clap_event_midi_t, 32> events_{};
  std::uint32_t count_{};
};

class ProbeMidiOutputs final {
 public:
  ProbeMidiOutputs() noexcept {
    list_.ctx = this;
    list_.try_push = &try_push;
  }

  const clap_output_events_t* list() const noexcept { return &list_; }
  std::size_t size() const noexcept { return size_; }
  const clap_event_midi_t& operator[](std::size_t index) const noexcept {
    return events_[index];
  }

 private:
  static bool CLAP_ABI try_push(const clap_output_events_t* list,
                                const clap_event_header_t* header) noexcept {
    auto* self = static_cast<ProbeMidiOutputs*>(list->ctx);
    if (header == nullptr || header->space_id != CLAP_CORE_EVENT_SPACE_ID ||
        header->type != CLAP_EVENT_MIDI ||
        header->size < sizeof(clap_event_midi_t) ||
        self->size_ >= self->events_.size()) {
      return false;
    }
    self->events_[self->size_++] =
        *reinterpret_cast<const clap_event_midi_t*>(header);
    return true;
  }

  clap_output_events_t list_{};
  std::array<clap_event_midi_t, 64> events_{};
  std::size_t size_{};
};

void expect_midi(const ProbeMidiOutputs& output, std::size_t index,
                 std::uint32_t time, std::uint8_t status, std::uint8_t data1,
                 std::uint8_t data2) noexcept {
  M3_EXPECT_TRUE(index < output.size());
  if (index >= output.size()) {
    return;
  }
  const clap_event_midi_t& event = output[index];
  M3_EXPECT_EQ(event.header.time, time);
  M3_EXPECT_EQ(event.port_index, 0U);
  M3_EXPECT_EQ(event.data[0], status);
  M3_EXPECT_EQ(event.data[1], data1);
  M3_EXPECT_EQ(event.data[2], data2);
}

}  // namespace

M3_TEST(probe_trigger_one_preserves_input_and_inserts_exact_ordered_note_pair) {
  m3::ProbeProcessor probe;
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(32));
  pipeline.begin_block();

  ProbeMidiInputs input;
  M3_EXPECT_TRUE(input.push(4, 0x90, 67, 101));
  M3_EXPECT_TRUE(input.push(8, 0xB0, 119, 1));
  M3_EXPECT_TRUE(input.push(9, 0x90, 65, 99));
  M3_EXPECT_TRUE(input.push(11, 0xB0, 1, 64));
  M3_EXPECT_TRUE(input.push(20, 0x80, 67, 0));
  M3_EXPECT_TRUE(input.push(21, 0x80, 65, 0));
  M3_EXPECT_TRUE(probe.queue_trigger_transitions(pipeline, input.list(), 32));

  ProbeMidiOutputs output;
  const m3::MidiProcessResult result = pipeline.process(
      32, 1, input.list(), output.list(), 0.0, true, true);
  M3_EXPECT_FALSE(result.invalid_event);
  M3_EXPECT_EQ(output.size(), 8U);
  expect_midi(output, 0, 4, 0x90, 67, 101);
  expect_midi(output, 1, 8, 0xB0, 119, 1);
  expect_midi(output, 2, 9, 0x90, 65, 99);
  expect_midi(output, 3, 9, 0x90, 60, 100);
  expect_midi(output, 4, 11, 0x80, 60, 0);
  expect_midi(output, 5, 11, 0xB0, 1, 64);
  expect_midi(output, 6, 20, 0x80, 67, 0);
  expect_midi(output, 7, 21, 0x80, 65, 0);
}

M3_TEST(probe_trigger_two_holds_note_until_panic_releases_it) {
  m3::ProbeProcessor probe;
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(32));
  pipeline.begin_block();
  ProbeMidiInputs input;
  M3_EXPECT_TRUE(input.push(8, 0xB0, 119, 2));
  M3_EXPECT_TRUE(probe.queue_trigger_transitions(pipeline, input.list(), 32));
  ProbeMidiOutputs first_output;
  M3_EXPECT_FALSE(pipeline.process(32, 1, input.list(), first_output.list(),
                                   0.0, true, true)
                      .invalid_event);
  M3_EXPECT_EQ(first_output.size(), 2U);
  expect_midi(first_output, 0, 8, 0xB0, 119, 2);
  expect_midi(first_output, 1, 9, 0x90, 61, 100);
  M3_EXPECT_TRUE(pipeline.is_active(61));

  pipeline.begin_block();
  M3_EXPECT_TRUE(pipeline.request_panic(5, 32));
  ProbeMidiOutputs panic_output;
  static_cast<void>(pipeline.process(
      32, 1, m3::test::FakeClapHost::empty_input_events(), panic_output.list(),
      0.0, true, true));
  M3_EXPECT_EQ(panic_output.size(), 1U);
  expect_midi(panic_output, 0, 5, 0x80, 61, 0);
  M3_EXPECT_FALSE(pipeline.is_active(61));
}

M3_TEST(probe_adapter_hooks_the_trigger_processor_only_in_probe_or_test_builds) {
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = m3::create_adapter(host.host());
  M3_EXPECT_TRUE(plugin != nullptr);
  M3_EXPECT_TRUE(plugin->init(plugin));
  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 32));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));

  ProbeMidiInputs input;
  M3_EXPECT_TRUE(input.push(8, 0xB0, 119, 1));
  ProbeMidiOutputs output;
  m3::test::FakeProcessBlock<float> block;
  block.configure(32, false);
  block.fill_finite();
  block.set_input_events(input.list());
  block.set_output_events(output.list());
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(output.size(), 3U);
  expect_midi(output, 0, 8, 0xB0, 119, 1);
  expect_midi(output, 1, 9, 0x90, 60, 100);
  expect_midi(output, 2, 11, 0x80, 60, 0);

  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
}

M3_TEST(probe_rejects_a_trigger_whose_generated_pair_exceeds_the_block) {
  m3::ProbeProcessor probe;
  m3::MidiPipeline pipeline;
  M3_EXPECT_TRUE(pipeline.activate(32));
  pipeline.begin_block();
  ProbeMidiInputs input;
  M3_EXPECT_TRUE(input.push(30, 0xB0, 119, 1));
  M3_EXPECT_FALSE(probe.queue_trigger_transitions(pipeline, input.list(), 32));
  M3_EXPECT_EQ(probe.snapshot().trigger_overflow, 1U);
}

M3_TEST(probe_diagnostics_cover_lifecycle_formats_alias_modes_and_atomic_report) {
  m3::ProbeProcessor probe;
  probe.record_create();
  probe.record_init();
  M3_EXPECT_TRUE(probe.record_activate());
  probe.record_start();
  probe.record_reset();

  m3::test::FakeProcessBlock<float> float_alias;
  float_alias.configure(32, true);
  probe.record_process(*float_alias.process());
  m3::test::FakeProcessBlock<double> double_separate;
  double_separate.configure(32, false);
  probe.record_process(*double_separate.process());

  probe.record_stop();
  probe.record_deactivate();
  probe.record_destroy();
  const m3::ProbeDiagnosticsSnapshot snapshot = probe.snapshot();
  M3_EXPECT_EQ(snapshot.create, 1U);
  M3_EXPECT_EQ(snapshot.init, 1U);
  M3_EXPECT_EQ(snapshot.activate, 1U);
  M3_EXPECT_EQ(snapshot.start, 1U);
  M3_EXPECT_EQ(snapshot.reset, 1U);
  M3_EXPECT_EQ(snapshot.stop, 1U);
  M3_EXPECT_EQ(snapshot.deactivate, 1U);
  M3_EXPECT_EQ(snapshot.destroy, 1U);
  M3_EXPECT_EQ(snapshot.trigger_overflow, 0U);
  M3_EXPECT_TRUE(snapshot.float32_seen);
  M3_EXPECT_TRUE(snapshot.float64_seen);
  M3_EXPECT_TRUE(snapshot.alias_seen);
  M3_EXPECT_TRUE(snapshot.separate_seen);
  M3_EXPECT_TRUE(snapshot.self_test_alias_passed);
  M3_EXPECT_TRUE(snapshot.self_test_separate_passed);

  char report_path[] = "/tmp/m3-native-probe-report-XXXXXX";
  const int descriptor = mkstemp(report_path);
  M3_EXPECT_TRUE(descriptor >= 0);
  if (descriptor >= 0) {
    static_cast<void>(close(descriptor));
    static_cast<void>(std::remove(report_path));
    M3_EXPECT_EQ(setenv("M3_CLAP_PROBE_REPORT", report_path, 1), 0);
    M3_EXPECT_TRUE(probe.write_report());
    FILE* report = std::fopen(report_path, "rb");
    M3_EXPECT_TRUE(report != nullptr);
    if (report != nullptr) {
      std::array<char, 2048> contents{};
      const std::size_t count =
          std::fread(contents.data(), 1, contents.size() - 1U, report);
      contents[count] = '\0';
      static_cast<void>(std::fclose(report));
      M3_EXPECT_TRUE(std::strstr(contents.data(), "destroy\t1\n") != nullptr);
      M3_EXPECT_TRUE(std::strstr(contents.data(), "float64_seen\t1\n") != nullptr);
      M3_EXPECT_TRUE(
          std::strstr(contents.data(), "self_test_alias_passed\t1\n") != nullptr);
    }
    static_cast<void>(std::remove(report_path));
    static_cast<void>(unsetenv("M3_CLAP_PROBE_REPORT"));
  }
}
