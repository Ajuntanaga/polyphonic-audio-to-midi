#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "fake_vst3_host.hpp"
#include "m3/calibration_state_image.hpp"
#include "m3/parameter_contract.hpp"
#include "m3/state_image.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_component.hpp"
#include "vst3_ids.hpp"
#include "vst3_state_stream.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

m3::PersistentConfig nondefault_config() noexcept {
  m3::PersistentConfig config;
  config.midi_routing = m3::MidiRouting::per_voice;
  config.profile_mode = m3::ProfileMode::general;
  config.a4_hz = 432.5;
  config.input_trim_db = -12.5;
  config.sensitivity = 77;
  config.response = 88;
  config.lowest_note = 24;
  config.highest_note = 108;
  config.max_polyphony = 3;
  config.max_fret = 36;
  config.velocity_mode = m3::VelocityMode::fixed;
  config.fixed_velocity = 1;
  config.midi_channel = 16;
  config.dry_passthrough = false;
  return config;
}

bool same_config(const m3::PersistentConfig& left,
                 const m3::PersistentConfig& right) noexcept {
  return left.midi_routing == right.midi_routing &&
         left.profile_mode == right.profile_mode && left.a4_hz == right.a4_hz &&
         left.input_trim_db == right.input_trim_db &&
         left.sensitivity == right.sensitivity && left.response == right.response &&
         left.lowest_note == right.lowest_note &&
         left.highest_note == right.highest_note &&
         left.max_polyphony == right.max_polyphony &&
         left.max_fret == right.max_fret &&
         left.velocity_mode == right.velocity_mode &&
         left.fixed_velocity == right.fixed_velocity &&
         left.midi_channel == right.midi_channel &&
         left.dry_passthrough == right.dry_passthrough;
}

bool bytes_equal(const std::uint8_t* left, const std::uint8_t* right,
                 std::size_t size) noexcept {
  return left != nullptr && right != nullptr &&
         std::memcmp(left, right, size) == 0;
}

m3::StringCalibrationBank calibration_bank() noexcept {
  m3::StringCalibrationBank bank;
  bank.calibrated_string_mask = static_cast<std::uint8_t>(1U << 2U);
  for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
    auto& point = bank.points[2U][fret];
    point.cents_offset_q8 = static_cast<std::int16_t>(fret * 4U);
    point.harmonic_profile_q15 = {15000U, 7000U, 4000U,
                                  2500U, 1500U, 800U};
    point.confidence_q15 = 28000U;
    point.observation_count = 5U;
    point.quality = m3::CalibrationPointQuality::measured;
  }
  return bank;
}

bool same_calibration(const m3::StringCalibrationBank& left,
                      const m3::StringCalibrationBank& right) noexcept {
  if (left.calibrated_string_mask != right.calibrated_string_mask) {
    return false;
  }
  for (std::size_t string = 0U; string < m3::kMaxVoices; ++string) {
    for (std::size_t fret = 0U; fret < m3::kCalibrationFretCount; ++fret) {
      const auto& a = left.points[string][fret];
      const auto& b = right.points[string][fret];
      if (a.cents_offset_q8 != b.cents_offset_q8 ||
          a.harmonic_profile_q15 != b.harmonic_profile_q15 ||
          a.confidence_q15 != b.confidence_q15 ||
          a.observation_count != b.observation_count ||
          a.quality != b.quality) {
        return false;
      }
    }
  }
  return true;
}

struct ComponentInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  Steinberg::Vst::IEditController* controller{};
  m3::test::FakeVst3Host host{};
};

bool open_component(ComponentInstance& instance) noexcept {
  instance.factory = GetPluginFactory();
  if (instance.factory == nullptr) {
    return false;
  }
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  return instance.factory->createInstance(
             class_id, Steinberg::Vst::IComponent::iid,
             reinterpret_cast<void**>(&instance.component)) ==
             Steinberg::kResultOk &&
         instance.component != nullptr &&
         instance.component->initialize(&instance.host) ==
             Steinberg::kResultOk &&
         instance.component->queryInterface(
             Steinberg::Vst::IEditController::iid,
             reinterpret_cast<void**>(&instance.controller)) ==
             Steinberg::kResultOk &&
         instance.controller != nullptr &&
         instance.component->queryInterface(
             Steinberg::Vst::IAudioProcessor::iid,
             reinterpret_cast<void**>(&instance.processor)) ==
             Steinberg::kResultOk &&
         instance.processor != nullptr;
}

void close_component(ComponentInstance& instance) noexcept {
  if (instance.processor != nullptr) {
    static_cast<void>(instance.processor->setProcessing(Steinberg::TBool{0}));
  }
  if (instance.component != nullptr) {
    static_cast<void>(instance.component->setActive(Steinberg::TBool{0}));
    static_cast<void>(instance.component->terminate());
  }
  if (instance.controller != nullptr) {
    instance.controller->release();
  }
  if (instance.processor != nullptr) {
    instance.processor->release();
  }
  if (instance.component != nullptr) {
    instance.component->release();
  }
  if (instance.factory != nullptr) {
    instance.factory->release();
  }
}

class CountingComponentHandler final
    : public Steinberg::Vst::IComponentHandler {
 public:
  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override {
    if (object == nullptr) {
      return Steinberg::kInvalidArgument;
    }
    *object = nullptr;
    if (Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                              Steinberg::FUnknown::iid) ||
        Steinberg::FUnknownPrivate::iidEqual(
            requested_iid, Steinberg::Vst::IComponentHandler::iid)) {
      *object = static_cast<Steinberg::Vst::IComponentHandler*>(this);
      addRef();
      return Steinberg::kResultOk;
    }
    return Steinberg::kNoInterface;
  }
  Steinberg::uint32 PLUGIN_API addRef() override { return ++references_; }
  Steinberg::uint32 PLUGIN_API release() override {
    if (references_ > 0U) {
      --references_;
    }
    return references_;
  }
  Steinberg::tresult PLUGIN_API beginEdit(Steinberg::Vst::ParamID) override {
    ++callbacks_;
    return Steinberg::kResultOk;
  }
  Steinberg::tresult PLUGIN_API performEdit(
      Steinberg::Vst::ParamID, Steinberg::Vst::ParamValue) override {
    ++callbacks_;
    return Steinberg::kResultOk;
  }
  Steinberg::tresult PLUGIN_API endEdit(Steinberg::Vst::ParamID) override {
    ++callbacks_;
    return Steinberg::kResultOk;
  }
  Steinberg::tresult PLUGIN_API restartComponent(
      Steinberg::int32) override {
    ++callbacks_;
    return Steinberg::kResultOk;
  }
  [[nodiscard]] std::uint32_t callbacks() const noexcept { return callbacks_; }

 private:
  Steinberg::uint32 references_{1};
  std::uint32_t callbacks_{};
};

}  // namespace

M3_TEST(vst3_state_stream_matches_neutral_default_and_nondefault_images) {
  for (const m3::PersistentConfig config : {m3::PersistentConfig{},
                                            nondefault_config()}) {
    m3::StateImage expected{};
    M3_EXPECT_TRUE(m3::encode_state(config, expected));
    m3::test::FakeVst3Stream output;
    output.reset_output(7);
    M3_EXPECT_TRUE(m3::vst3::save_vst3_state(config, &output));
    M3_EXPECT_EQ(output.size(), m3::kStateSize);
    M3_EXPECT_TRUE(bytes_equal(output.bytes(), expected.data(),
                               expected.size()));

    m3::test::FakeVst3Stream input;
    M3_EXPECT_TRUE(input.set_input(output.bytes(), output.size(), 5));
    m3::PersistentConfig decoded;
    M3_EXPECT_TRUE(m3::vst3::load_vst3_state(&input, decoded));
    M3_EXPECT_TRUE(same_config(decoded, config));
  }
}

M3_TEST(vst3_extended_state_persists_calibration_and_accepts_legacy_state) {
  const m3::PersistentConfig config = nondefault_config();
  const m3::StringCalibrationBank calibration = calibration_bank();
  m3::test::FakeVst3Stream output;
  output.reset_output(31);
  M3_EXPECT_TRUE(m3::vst3::save_vst3_state_with_calibration(
      config, calibration, &output));
  M3_EXPECT_EQ(output.size(),
               m3::kStateSize + m3::kCalibrationStateSize);

  m3::test::FakeVst3Stream input;
  M3_EXPECT_TRUE(input.set_input(output.bytes(), output.size(), 23));
  m3::PersistentConfig decoded_config;
  m3::StringCalibrationBank decoded_calibration;
  M3_EXPECT_TRUE(m3::vst3::load_vst3_state_with_calibration(
      &input, decoded_config, decoded_calibration));
  M3_EXPECT_TRUE(same_config(decoded_config, config));
  M3_EXPECT_TRUE(same_calibration(decoded_calibration, calibration));

  m3::StateImage legacy{};
  M3_EXPECT_TRUE(m3::encode_state(config, legacy));
  M3_EXPECT_TRUE(input.set_input(legacy.data(), legacy.size(), 19));
  decoded_calibration = calibration;
  M3_EXPECT_TRUE(m3::vst3::load_vst3_state_with_calibration(
      &input, decoded_config, decoded_calibration));
  M3_EXPECT_TRUE(same_config(decoded_config, config));
  M3_EXPECT_EQ(decoded_calibration.calibrated_string_mask, 0U);
}

M3_TEST(vst3_component_restores_and_resaves_string_calibration) {
  ComponentInstance instance;
  M3_EXPECT_TRUE(open_component(instance));
  if (instance.component == nullptr || instance.processor == nullptr) {
    close_component(instance);
    return;
  }

  const m3::PersistentConfig config = nondefault_config();
  const m3::StringCalibrationBank calibration = calibration_bank();
  m3::test::FakeVst3Stream encoded;
  encoded.reset_output(31);
  M3_EXPECT_TRUE(m3::vst3::save_vst3_state_with_calibration(
      config, calibration, &encoded));

  m3::test::FakeVst3Stream input;
  M3_EXPECT_TRUE(input.set_input(encoded.bytes(), encoded.size(), 23));
  M3_EXPECT_EQ(instance.component->setState(&input), Steinberg::kResultOk);

  m3::test::FakeVst3Stream resaved;
  resaved.reset_output(29);
  M3_EXPECT_EQ(instance.component->getState(&resaved), Steinberg::kResultOk);
  m3::test::FakeVst3Stream resaved_input;
  M3_EXPECT_TRUE(
      resaved_input.set_input(resaved.bytes(), resaved.size(), 19));
  m3::PersistentConfig restored_config;
  m3::StringCalibrationBank restored_calibration;
  M3_EXPECT_TRUE(m3::vst3::load_vst3_state_with_calibration(
      &resaved_input, restored_config, restored_calibration));
  M3_EXPECT_TRUE(same_config(restored_config, config));
  M3_EXPECT_TRUE(same_calibration(restored_calibration, calibration));

  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 512;
  setup.sampleRate = 48000.0;
  M3_EXPECT_EQ(instance.processor->setupProcessing(setup),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  Steinberg::Vst::ProcessData flush{};
  flush.processMode = Steinberg::Vst::kRealtime;
  flush.symbolicSampleSize = Steinberg::Vst::kSample32;
  flush.numSamples = 0;
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
  const auto ui_state =
      m3::vst3::string_calibration_ui_state_for_test(instance.processor);
  M3_EXPECT_EQ(ui_state.calibrated_string_mask,
               calibration.calibrated_string_mask);

  close_component(instance);
}

M3_TEST(vst3_component_terminate_clears_unrestored_detector_calibration) {
  ComponentInstance instance;
  M3_EXPECT_TRUE(open_component(instance));
  if (instance.component == nullptr || instance.processor == nullptr) {
    close_component(instance);
    return;
  }

  m3::test::FakeVst3Stream encoded;
  encoded.reset_output(31);
  M3_EXPECT_TRUE(m3::vst3::save_vst3_state_with_calibration(
      m3::PersistentConfig{}, calibration_bank(), &encoded));
  m3::test::FakeVst3Stream input;
  M3_EXPECT_TRUE(input.set_input(encoded.bytes(), encoded.size(), 23));
  M3_EXPECT_EQ(instance.component->setState(&input), Steinberg::kResultOk);

  const auto process_once = [&instance]() noexcept {
    Steinberg::Vst::ProcessSetup setup{};
    setup.processMode = Steinberg::Vst::kRealtime;
    setup.symbolicSampleSize = Steinberg::Vst::kSample32;
    setup.maxSamplesPerBlock = 512;
    setup.sampleRate = 48000.0;
    M3_EXPECT_EQ(instance.processor->setupProcessing(setup),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    Steinberg::Vst::ProcessData flush{};
    flush.processMode = Steinberg::Vst::kRealtime;
    flush.symbolicSampleSize = Steinberg::Vst::kSample32;
    flush.numSamples = 0;
    M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
  };

  process_once();
  M3_EXPECT_TRUE(
      m3::vst3::string_calibration_ui_state_for_test(instance.processor)
          .calibrated_string_mask != 0U);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{0}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.component->terminate(), Steinberg::kResultOk);

  M3_EXPECT_EQ(instance.component->initialize(&instance.host),
               Steinberg::kResultOk);
  process_once();
  M3_EXPECT_EQ(
      m3::vst3::string_calibration_ui_state_for_test(instance.processor)
          .calibrated_string_mask,
      0U);

  close_component(instance);
}

M3_TEST(vst3_state_stream_rejects_null_failure_and_invalid_progress) {
  m3::PersistentConfig destination = nondefault_config();
  const m3::PersistentConfig before = destination;
  M3_EXPECT_FALSE(m3::vst3::save_vst3_state(m3::PersistentConfig{}, nullptr));
  M3_EXPECT_FALSE(m3::vst3::load_vst3_state(nullptr, destination));
  M3_EXPECT_TRUE(same_config(destination, before));

  m3::StateImage image{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, image));
  for (const Steinberg::tresult failure : {Steinberg::kResultFalse,
                                           Steinberg::kInvalidArgument}) {
    m3::test::FakeVst3Stream input;
    M3_EXPECT_TRUE(input.set_input(image.data(), image.size(), 9));
    input.force_read_result(failure, 1);
    M3_EXPECT_FALSE(m3::vst3::load_vst3_state(&input, destination));
    M3_EXPECT_TRUE(same_config(destination, before));

    m3::test::FakeVst3Stream output;
    output.reset_output(11);
    output.force_write_result(failure, 1);
    M3_EXPECT_FALSE(m3::vst3::save_vst3_state(m3::PersistentConfig{},
                                               &output));
  }
  for (const Steinberg::int32 invalid_count : {0, -1, 185}) {
    m3::test::FakeVst3Stream input;
    M3_EXPECT_TRUE(input.set_input(image.data(), image.size(), 9));
    input.force_read_result(Steinberg::kResultOk, invalid_count);
    M3_EXPECT_FALSE(m3::vst3::load_vst3_state(&input, destination));
    M3_EXPECT_TRUE(same_config(destination, before));

    m3::test::FakeVst3Stream output;
    output.reset_output(11);
    output.force_write_result(Steinberg::kResultOk, invalid_count);
    M3_EXPECT_FALSE(m3::vst3::save_vst3_state(m3::PersistentConfig{},
                                               &output));
  }
}

M3_TEST(vst3_state_stream_rejects_every_truncation_trailing_and_bad_image) {
  m3::StateImage image{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, image));
  m3::PersistentConfig destination = nondefault_config();
  const m3::PersistentConfig before = destination;
  for (std::size_t size = 0; size < image.size(); ++size) {
    m3::test::FakeVst3Stream input;
    M3_EXPECT_TRUE(input.set_input(image.data(), size, 13));
    M3_EXPECT_FALSE(m3::vst3::load_vst3_state(&input, destination));
    M3_EXPECT_TRUE(same_config(destination, before));
  }

  std::array<std::uint8_t, m3::kStateSize + 1U> trailing{};
  std::copy(image.begin(), image.end(), trailing.begin());
  trailing.back() = 0x5AU;
  m3::test::FakeVst3Stream extra;
  M3_EXPECT_TRUE(extra.set_input(trailing.data(), trailing.size(), 17));
  M3_EXPECT_FALSE(m3::vst3::load_vst3_state(&extra, destination));
  M3_EXPECT_TRUE(same_config(destination, before));

  image[0] = 'X';
  m3::test::FakeVst3Stream bad;
  M3_EXPECT_TRUE(bad.set_input(image.data(), image.size(), 19));
  M3_EXPECT_FALSE(m3::vst3::load_vst3_state(&bad, destination));
  M3_EXPECT_TRUE(same_config(destination, before));
}

M3_TEST(vst3_component_and_controller_state_synchronize_without_callbacks) {
  ComponentInstance instance;
  M3_EXPECT_TRUE(open_component(instance));
  if (instance.component == nullptr || instance.controller == nullptr) {
    close_component(instance);
    return;
  }
  const m3::PersistentConfig config = nondefault_config();
  m3::StateImage expected{};
  M3_EXPECT_TRUE(m3::encode_state(config, expected));

  CountingComponentHandler handler;
  M3_EXPECT_EQ(instance.controller->setComponentHandler(&handler),
               Steinberg::kResultTrue);
  m3::test::FakeVst3Stream processor_input;
  M3_EXPECT_TRUE(processor_input.set_input(expected.data(), expected.size(), 7));
  M3_EXPECT_EQ(instance.component->setState(&processor_input),
               Steinberg::kResultOk);
  const m3::ParameterSpec* a4 = m3::find_parameter(0x4D330003U);
  M3_EXPECT_TRUE(a4 != nullptr);
  if (a4 != nullptr) {
    M3_EXPECT_NEAR(instance.controller->getParamNormalized(0x4D330003U),
                   m3::plain_to_normalized(*a4, 440.0), 0.0);
  }

  m3::test::FakeVst3Stream processor_output;
  processor_output.reset_output(11);
  M3_EXPECT_EQ(instance.component->getState(&processor_output),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(processor_output.size(),
               m3::kStateSize + m3::kCalibrationStateSize);
  M3_EXPECT_TRUE(bytes_equal(processor_output.bytes(), expected.data(),
                             expected.size()));
  m3::StringCalibrationBank saved_calibration;
  M3_EXPECT_TRUE(m3::decode_calibration_state(
      processor_output.bytes() + m3::kStateSize,
      m3::kCalibrationStateSize, saved_calibration));
  M3_EXPECT_EQ(saved_calibration.calibrated_string_mask, 0U);

  m3::test::FakeVst3Stream controller_input;
  M3_EXPECT_TRUE(controller_input.set_input(expected.data(), expected.size(),
                                             5));
  M3_EXPECT_EQ(instance.controller->setComponentState(&controller_input),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(handler.callbacks(), 0U);
  for (std::size_t index = 0; index < m3::kPersistentParameterCount; ++index) {
    const m3::ParameterId id = m3::persistent_parameter_ids()[index];
    const m3::ParameterSpec* spec = m3::find_parameter(id);
    double plain = 0.0;
    M3_EXPECT_TRUE(spec != nullptr);
    M3_EXPECT_TRUE(m3::parameter_value(config, m3::Status::ready, id, plain));
    if (spec != nullptr) {
      M3_EXPECT_NEAR(instance.controller->getParamNormalized(id),
                     m3::plain_to_normalized(*spec, plain), 1.0e-12);
    }
  }
  M3_EXPECT_NEAR(instance.controller->getParamNormalized(
                     m3::kPanicParameterId),
                 0.0, 0.0);
  M3_EXPECT_NEAR(instance.controller->getParamNormalized(
                     m3::kStatusParameterId),
                 0.0, 0.0);

  m3::StateImage bad_image = expected;
  bad_image[0] = 'X';
  m3::test::FakeVst3Stream invalid;
  M3_EXPECT_TRUE(invalid.set_input(bad_image.data(), bad_image.size(), 23));
  M3_EXPECT_TRUE(instance.component->setState(&invalid) !=
                 Steinberg::kResultOk);
  processor_output.reset_output(29);
  M3_EXPECT_EQ(instance.component->getState(&processor_output),
               Steinberg::kResultOk);
  M3_EXPECT_TRUE(bytes_equal(processor_output.bytes(), expected.data(),
                             expected.size()));

  M3_EXPECT_EQ(instance.controller->setComponentHandler(nullptr),
               Steinberg::kResultTrue);
  close_component(instance);
}

M3_TEST(vst3_component_state_sync_does_not_restore_nonpersistent_status) {
  ComponentInstance instance;
  M3_EXPECT_TRUE(open_component(instance));
  if (instance.component == nullptr || instance.processor == nullptr ||
      instance.controller == nullptr) {
    close_component(instance);
    return;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 32;
  setup.sampleRate = 48000.0;
  M3_EXPECT_EQ(instance.processor->setupProcessing(setup),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.component->setActive(Steinberg::TBool{1}),
               Steinberg::kResultOk);
  M3_EXPECT_EQ(instance.processor->setProcessing(Steinberg::TBool{1}),
               Steinberg::kResultOk);

  m3::test::FakeVst3ParameterChanges invalid_changes;
  M3_EXPECT_TRUE(
      invalid_changes.append_input(m3::kStatusParameterId, 0, 0.0));
  Steinberg::Vst::ProcessData flush{};
  flush.processMode = Steinberg::Vst::kRealtime;
  flush.symbolicSampleSize = Steinberg::Vst::kSample32;
  flush.numSamples = 0;
  flush.inputParameterChanges = &invalid_changes;
  M3_EXPECT_TRUE(instance.processor->process(flush) != Steinberg::kResultOk);

  m3::StateImage state{};
  M3_EXPECT_TRUE(m3::encode_state(m3::PersistentConfig{}, state));
  m3::test::FakeVst3Stream input;
  M3_EXPECT_TRUE(input.set_input(state.data(), state.size(), 9));
  M3_EXPECT_EQ(instance.controller->setComponentState(&input),
               Steinberg::kResultOk);
  const m3::ParameterSpec* status =
      m3::find_parameter(m3::kStatusParameterId);
  M3_EXPECT_TRUE(status != nullptr);
  if (status != nullptr) {
    M3_EXPECT_NEAR(instance.controller->getParamNormalized(
                       m3::kStatusParameterId),
                   m3::plain_to_normalized(
                       *status,
                       static_cast<double>(m3::Status::invalid_input_or_state)),
                   0.0);
  }
  close_component(instance);
}
