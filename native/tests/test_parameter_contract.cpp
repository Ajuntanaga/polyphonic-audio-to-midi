#include <clap/clap.h>
#include <clap/ext/params.h>
#include <clap/ext/state.h>
#include <clap/factory/plugin-factory.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>

#include "fake_clap_host.hpp"
#include "parameter_contract.hpp"
#include "state_codec.hpp"
#include "test_support.hpp"

namespace {

struct ExpectedParameter final {
  clap_id id;
  const char* name;
  double minimum;
  double maximum;
  double default_value;
  bool stepped;
  bool persistent;
};

constexpr ExpectedParameter kExpected[] = {
    {0x4D330001U, "Detector input", 0.0, 2.0, 0.0, true, true},
    {0x4D330002U, "Mode", 0.0, 1.0, 0.0, true, true},
    {0x4D330003U, "A4 reference", 400.0, 480.0, 440.0, false, true},
    {0x4D330004U, "Input trim", -24.0, 24.0, 0.0, false, true},
    {0x4D330005U, "Sensitivity", 0.0, 100.0, 50.0, true, true},
    {0x4D330006U, "Response", 0.0, 100.0, 25.0, true, true},
    {0x4D330007U, "Lowest MIDI note", 24.0, 108.0, 32.0, true, true},
    {0x4D330008U, "Highest MIDI note", 24.0, 108.0, 84.0, true, true},
    {0x4D330009U, "Maximum polyphony", 1.0, 8.0, 8.0, true, true},
    {0x4D33000AU, "M3 maximum fret", 0.0, 36.0, 24.0, true, true},
    {0x4D33000BU, "Velocity mode", 0.0, 1.0, 1.0, true, true},
    {0x4D33000CU, "Fixed velocity", 1.0, 127.0, 100.0, true, true},
    {0x4D33000DU, "MIDI channel", 1.0, 16.0, 1.0, true, true},
    {0x4D33000EU, "Panic", 0.0, 1.0, 0.0, true, false},
    {0x4D33000FU, "Dry audio", 0.0, 1.0, 1.0, true, true},
    {0x4D33FF01U, "Status", 0.0, 5.0, 0.0, true, false},
};

class ParamEvents final {
 public:
  ParamEvents() noexcept {
    list_.ctx = this;
    list_.size = &size;
    list_.get = &get;
  }

  bool push(clap_id id, double value, std::uint32_t time = 0) noexcept {
    if (count_ >= events_.size()) {
      return false;
    }
    clap_event_param_value_t& event = events_[count_++];
    event = {};
    event.header.size = sizeof(event);
    event.header.time = time;
    event.header.space_id = CLAP_CORE_EVENT_SPACE_ID;
    event.header.type = CLAP_EVENT_PARAM_VALUE;
    event.param_id = id;
    event.note_id = -1;
    event.port_index = -1;
    event.channel = -1;
    event.key = -1;
    event.value = value;
    return true;
  }

  const clap_input_events_t* list() const noexcept { return &list_; }

 private:
  static std::uint32_t CLAP_ABI size(const clap_input_events_t* list) noexcept {
    return static_cast<const ParamEvents*>(list->ctx)->count_;
  }
  static const clap_event_header_t* CLAP_ABI get(const clap_input_events_t* list,
                                                 std::uint32_t index) noexcept {
    const auto* self = static_cast<const ParamEvents*>(list->ctx);
    return index < self->count_ ? &self->events_[index].header : nullptr;
  }

  clap_input_events_t list_{};
  std::array<clap_event_param_value_t, 8> events_{};
  std::uint32_t count_{};
};

const clap_plugin_t* create_plugin(m3::test::FakeClapHost& host) noexcept {
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

M3_TEST(parameter_table_has_exact_stable_public_contract) {
  M3_EXPECT_EQ(m3::parameter_count(), 16U);
  for (std::size_t index = 0; index < std::size(kExpected); ++index) {
    const m3::ParameterRecord* record = m3::parameter_record(index);
    M3_EXPECT_TRUE(record != nullptr);
    M3_EXPECT_EQ(record->id, kExpected[index].id);
    M3_EXPECT_TRUE(std::strcmp(record->name, kExpected[index].name) == 0);
    M3_EXPECT_NEAR(record->minimum, kExpected[index].minimum, 0.0);
    M3_EXPECT_NEAR(record->maximum, kExpected[index].maximum, 0.0);
    M3_EXPECT_NEAR(record->default_value, kExpected[index].default_value, 0.0);
    M3_EXPECT_EQ((record->flags & CLAP_PARAM_IS_STEPPED) != 0U,
                 kExpected[index].stepped);
    M3_EXPECT_EQ(record->persistent, kExpected[index].persistent);
    M3_EXPECT_EQ(record->flags & CLAP_PARAM_IS_AUTOMATABLE, 0U);
    M3_EXPECT_EQ((record->flags & CLAP_PARAM_IS_READONLY) != 0U,
                 record->id == m3::kStatusParameterId);
  }
  M3_EXPECT_TRUE(m3::parameter_record(16) == nullptr);
}

M3_TEST(parameter_validation_clamps_and_rejects_without_partial_changes) {
  m3::PersistentConfig config;
  M3_EXPECT_EQ(m3::apply_parameter(config, 0x4D330003U, 999.0),
               m3::ParameterApplyResult::changed);
  M3_EXPECT_NEAR(config.a4_hz, 480.0, 0.0);
  M3_EXPECT_EQ(m3::apply_parameter(config, 0x4D330003U, 432.56),
               m3::ParameterApplyResult::changed);
  M3_EXPECT_NEAR(config.a4_hz, 432.6, 1.0e-12);
  M3_EXPECT_EQ(m3::apply_parameter(config, 0x4D330004U, -99.0),
               m3::ParameterApplyResult::changed);
  M3_EXPECT_NEAR(config.input_trim_db, -24.0, 0.0);
  M3_EXPECT_EQ(m3::apply_parameter(config, 0x4D330001U, 2.9),
               m3::ParameterApplyResult::changed);
  M3_EXPECT_EQ(config.detector_input, m3::DetectorInput::downmix);
  M3_EXPECT_EQ(m3::apply_parameter(config, 0x4D33000DU, 99.0),
               m3::ParameterApplyResult::changed);
  M3_EXPECT_EQ(config.midi_channel, 16U);
  const m3::PersistentConfig before = config;
  M3_EXPECT_EQ(
      m3::apply_parameter(config, 0x4D330003U,
                          std::numeric_limits<double>::quiet_NaN()),
      m3::ParameterApplyResult::rejected);
  M3_EXPECT_NEAR(config.a4_hz, before.a4_hz, 0.0);
  M3_EXPECT_EQ(m3::apply_parameter(config, m3::kStatusParameterId, 2.0),
               m3::ParameterApplyResult::rejected);
  M3_EXPECT_EQ(m3::apply_parameter(config, m3::kPanicParameterId, 1.0),
               m3::ParameterApplyResult::panic);
  double panic_value = -1.0;
  M3_EXPECT_TRUE(m3::parameter_value(config, m3::Status::ready,
                                      m3::kPanicParameterId, panic_value));
  M3_EXPECT_NEAR(panic_value, 0.0, 0.0);
}

M3_TEST(parameter_text_conversions_cover_enum_and_numeric_views) {
  char text[64]{};
  M3_EXPECT_TRUE(m3::parameter_value_to_text(0x4D330001U, 2.0, text,
                                              sizeof(text)));
  M3_EXPECT_TRUE(std::strcmp(text, "Downmix") == 0);
  double value = -1.0;
  M3_EXPECT_TRUE(m3::parameter_text_to_value(0x4D330001U, "Right", value));
  M3_EXPECT_NEAR(value, 1.0, 0.0);
  M3_EXPECT_TRUE(m3::parameter_value_to_text(0x4D330003U, 440.0, text,
                                              sizeof(text)));
  M3_EXPECT_TRUE(std::strcmp(text, "440.0") == 0);
  M3_EXPECT_TRUE(m3::parameter_text_to_value(0x4D330003U, "432.5", value));
  M3_EXPECT_NEAR(value, 432.5, 0.0);
}

M3_TEST(clap_parameter_extension_mirrors_table_and_applies_boundary_events) {
  m3::test::FakeClapHost host;
  const clap_plugin_t* plugin = create_plugin(host);
  const auto* params = static_cast<const clap_plugin_params_t*>(
      plugin->get_extension(plugin, CLAP_EXT_PARAMS));
  M3_EXPECT_TRUE(params != nullptr);
  M3_EXPECT_EQ(params->count(plugin), 16U);
  for (std::uint32_t index = 0; index < 16; ++index) {
    clap_param_info_t info{};
    M3_EXPECT_TRUE(params->get_info(plugin, index, &info));
    M3_EXPECT_EQ(info.id, kExpected[index].id);
    M3_EXPECT_TRUE(std::strcmp(info.name, kExpected[index].name) == 0);
    M3_EXPECT_EQ(info.flags & CLAP_PARAM_IS_AUTOMATABLE, 0U);
  }

  ParamEvents inactive;
  M3_EXPECT_TRUE(inactive.push(0x4D33000FU, 0.0));
  params->flush(plugin, inactive.list(),
                m3::test::FakeClapHost::accepting_output_events());
  double dry_value = -1.0;
  M3_EXPECT_TRUE(params->get_value(plugin, 0x4D33000FU, &dry_value));
  M3_EXPECT_NEAR(dry_value, 0.0, 0.0);

  M3_EXPECT_TRUE(plugin->activate(plugin, 48000.0, 1, 128));
  M3_EXPECT_TRUE(plugin->start_processing(plugin));
  m3::test::FakeProcessBlock<float> block;
  block.configure(32, false);
  block.fill_finite();
  ParamEvents active;
  M3_EXPECT_TRUE(active.push(0x4D33000FU, 1.0, 7));
  M3_EXPECT_TRUE(active.push(m3::kPanicParameterId, 1.0, 9));
  block.process()->in_events = active.list();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  for (std::uint32_t frame = 0; frame < 32; ++frame) {
    M3_EXPECT_EQ(block.output_left()[frame], block.input_left()[frame]);
  }
  double panic_value = -1.0;
  M3_EXPECT_TRUE(params->get_value(plugin, m3::kPanicParameterId, &panic_value));
  M3_EXPECT_NEAR(panic_value, 0.0, 0.0);

  block.configure(32, false);
  block.fill_finite();
  block.input_left()[0] = std::numeric_limits<float>::infinity();
  M3_EXPECT_EQ(plugin->process(plugin, block.process()), CLAP_PROCESS_CONTINUE);
  M3_EXPECT_EQ(host.callback_requests(), 1U);
  plugin->on_main_thread(plugin);
  M3_EXPECT_EQ(host.param_rescans(), 1U);
  M3_EXPECT_EQ(host.param_rescan_flags(),
               static_cast<clap_param_rescan_flags>(CLAP_PARAM_RESCAN_VALUES));

  plugin->stop_processing(plugin);
  plugin->deactivate(plugin);
  plugin->destroy(plugin);
  clap_entry.deinit();
}
