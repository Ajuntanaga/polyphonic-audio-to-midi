#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

#include "fake_vst3_host.hpp"
#include "m3/parameter_contract.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/base/ustring.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"
#include "vst3_parameter_bridge.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct ControllerInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  Steinberg::Vst::IEditController* controller{};
  m3::test::FakeVst3Host host{};
};

bool open_controller(ControllerInstance& instance,
                     bool activate = false) noexcept {
  instance.factory = GetPluginFactory();
  if (instance.factory == nullptr) {
    return false;
  }
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  if (instance.factory->createInstance(
          class_id, Steinberg::Vst::IComponent::iid,
          reinterpret_cast<void**>(&instance.component)) !=
          Steinberg::kResultOk ||
      instance.component == nullptr ||
      instance.component->initialize(&instance.host) != Steinberg::kResultOk ||
      instance.component->queryInterface(
          Steinberg::Vst::IEditController::iid,
          reinterpret_cast<void**>(&instance.controller)) !=
          Steinberg::kResultOk ||
      instance.controller == nullptr ||
      instance.component->queryInterface(
          Steinberg::Vst::IAudioProcessor::iid,
          reinterpret_cast<void**>(&instance.processor)) !=
          Steinberg::kResultOk ||
      instance.processor == nullptr) {
    return false;
  }
  if (!activate) {
    return true;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 128;
  setup.sampleRate = 48000.0;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_controller(ControllerInstance& instance) noexcept {
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

bool string_matches(const Steinberg::Vst::TChar* text,
                    const char* expected) noexcept {
  if (text == nullptr || expected == nullptr) {
    return false;
  }
  std::size_t index = 0;
  while (expected[index] != '\0') {
    if (text[index] !=
        static_cast<Steinberg::Vst::TChar>(expected[index])) {
      return false;
    }
    ++index;
  }
  return text[index] == 0;
}

void ascii_to_vst3(const char* source,
                   Steinberg::Vst::String128 destination) noexcept {
  Steinberg::UString(destination, 128).fromAscii(source);
}

bool same_config(const m3::PersistentConfig& left,
                 const m3::PersistentConfig& right) noexcept {
  return left.detector_input == right.detector_input &&
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

}  // namespace

M3_TEST(vst3_parameter_info_is_exact_and_generic) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance));
  if (instance.controller == nullptr) {
    close_controller(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->getParameterCount(),
               static_cast<Steinberg::int32>(m3::vst3::kVst3ParameterCount));
  for (std::size_t index = 0; index < m3::vst3::kVst3ParameterCount; ++index) {
    const m3::ParameterSpec* spec = m3::vst3::vst3_parameter_spec(index);
    M3_EXPECT_TRUE(spec != nullptr);
    if (spec == nullptr) {
      continue;
    }
    Steinberg::Vst::ParameterInfo info{};
    M3_EXPECT_EQ(instance.controller->getParameterInfo(
                     static_cast<Steinberg::int32>(index), info),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(info.id, spec->id);
    M3_EXPECT_TRUE(string_matches(info.title, spec->name));
    M3_EXPECT_EQ(info.stepCount, spec->step_count);
    M3_EXPECT_NEAR(info.defaultNormalizedValue,
                   m3::plain_to_normalized(*spec, spec->default_value), 0.0);
    const Steinberg::int32 expected_flags =
        (spec->list ? Steinberg::Vst::ParameterInfo::kIsList : 0) |
        (spec->read_only ? Steinberg::Vst::ParameterInfo::kIsReadOnly : 0);
    M3_EXPECT_EQ(info.flags, expected_flags);
    M3_EXPECT_EQ(info.flags & Steinberg::Vst::ParameterInfo::kCanAutomate, 0);
    M3_EXPECT_EQ(info.flags & Steinberg::Vst::ParameterInfo::kIsBypass, 0);
    M3_EXPECT_EQ(info.flags & Steinberg::Vst::ParameterInfo::kIsProgramChange,
                 0);
    M3_EXPECT_EQ(info.flags & Steinberg::Vst::ParameterInfo::kIsHidden, 0);
  }
  Steinberg::Vst::ParameterInfo extra{};
  M3_EXPECT_TRUE(instance.controller->getParameterInfo(18, extra) !=
                 Steinberg::kResultTrue);
  close_controller(instance);
}

M3_TEST(vst3_parameter_conversions_cover_every_exact_step) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance));
  if (instance.controller == nullptr) {
    close_controller(instance);
    return;
  }
  for (std::size_t spec_index = 0;
       spec_index < m3::vst3::kVst3ParameterCount;
       ++spec_index) {
    const m3::ParameterSpec* spec =
        m3::vst3::vst3_parameter_spec(spec_index);
    M3_EXPECT_TRUE(spec != nullptr);
    if (spec == nullptr) {
      continue;
    }
    for (Steinberg::int32 step = 0; step <= spec->step_count; ++step) {
      const double normalized =
          static_cast<double>(step) / static_cast<double>(spec->step_count);
      const double expected_plain = m3::canonical_plain(
          *spec, spec->minimum + spec->increment * static_cast<double>(step));
      M3_EXPECT_NEAR(instance.controller->normalizedParamToPlain(spec->id,
                                                                 normalized),
                     expected_plain, 1.0e-12);
      M3_EXPECT_NEAR(instance.controller->plainParamToNormalized(
                         spec->id, expected_plain),
                     normalized, 1.0e-12);

      Steinberg::Vst::String128 text{};
      M3_EXPECT_EQ(instance.controller->getParamStringByValue(
                       spec->id, normalized, text),
                   Steinberg::kResultTrue);
      Steinberg::Vst::ParamValue parsed = -1.0;
      if (spec->read_only) {
        M3_EXPECT_TRUE(instance.controller->getParamValueByString(
                           spec->id, text, parsed) != Steinberg::kResultTrue);
        M3_EXPECT_TRUE(instance.controller->setParamNormalized(
                           spec->id, normalized) != Steinberg::kResultTrue);
      } else {
        M3_EXPECT_EQ(instance.controller->getParamValueByString(
                         spec->id, text, parsed),
                     Steinberg::kResultTrue);
        M3_EXPECT_NEAR(parsed, normalized, 1.0e-12);
        M3_EXPECT_EQ(instance.controller->setParamNormalized(spec->id,
                                                              normalized),
                     Steinberg::kResultTrue);
      }
    }
  }
  close_controller(instance);
}

M3_TEST(vst3_tuner_parameter_text_is_musical_and_read_only) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance));
  if (instance.controller == nullptr) {
    close_controller(instance);
    return;
  }

  struct Case final {
    m3::ParameterId id;
    double plain;
    const char* text;
  };
  constexpr Case cases[] = {
      {m3::vst3::kTunerNoteParameterId, 69.0, "A4"},
      {m3::vst3::kTunerNoteParameterId,
       static_cast<double>(m3::kTunerNoSignalNote), "No signal"},
      {m3::vst3::kTunerCentsParameterId, 12.3, "+12.3"},
      {m3::vst3::kTunerCentsParameterId, -7.4, "-7.4"},
  };
  for (const Case& test_case : cases) {
    const m3::ParameterSpec* spec =
        m3::vst3::find_vst3_parameter(test_case.id);
    M3_EXPECT_TRUE(spec != nullptr);
    if (spec == nullptr) {
      continue;
    }
    Steinberg::Vst::String128 text{};
    M3_EXPECT_EQ(instance.controller->getParamStringByValue(
                     test_case.id,
                     m3::plain_to_normalized(*spec, test_case.plain), text),
                 Steinberg::kResultTrue);
    M3_EXPECT_TRUE(string_matches(text, test_case.text));
    M3_EXPECT_TRUE(instance.controller->setParamNormalized(
                       test_case.id,
                       m3::plain_to_normalized(*spec, test_case.plain)) !=
                   Steinberg::kResultTrue);
  }
  close_controller(instance);
}

M3_TEST(vst3_parameter_edits_reject_unknown_nonfinite_and_noncanonical_values) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance));
  if (instance.controller == nullptr) {
    close_controller(instance);
    return;
  }
  constexpr Steinberg::Vst::ParamID kUnknown = 0xDEADBEEFU;
  Steinberg::Vst::String128 text{};
  ascii_to_vst3("432.5", text);
  Steinberg::Vst::ParamValue parsed = -1.0;
  M3_EXPECT_TRUE(instance.controller->getParamStringByValue(kUnknown, 0.0,
                                                             text) !=
                 Steinberg::kResultTrue);
  M3_EXPECT_TRUE(instance.controller->getParamValueByString(kUnknown, text,
                                                             parsed) !=
                 Steinberg::kResultTrue);
  M3_EXPECT_TRUE(std::isnan(
      instance.controller->normalizedParamToPlain(kUnknown, 0.0)));
  M3_EXPECT_TRUE(std::isnan(
      instance.controller->plainParamToNormalized(kUnknown, 0.0)));
  M3_EXPECT_TRUE(instance.controller->setParamNormalized(kUnknown, 0.0) !=
                 Steinberg::kResultTrue);

  constexpr Steinberg::Vst::ParamID kA4 = 0x4D330003U;
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double infinity = std::numeric_limits<double>::infinity();
  for (const double invalid : {nan, infinity, -infinity, -0.1, 1.1,
                               0.123456789}) {
    M3_EXPECT_TRUE(instance.controller->getParamStringByValue(kA4, invalid,
                                                               text) !=
                   Steinberg::kResultTrue);
    M3_EXPECT_TRUE(std::isnan(
        instance.controller->normalizedParamToPlain(kA4, invalid)));
    M3_EXPECT_TRUE(instance.controller->setParamNormalized(kA4, invalid) !=
                   Steinberg::kResultTrue);
  }
  for (const double invalid_plain : {nan, infinity, -infinity, 399.9, 480.1,
                                     432.56}) {
    M3_EXPECT_TRUE(std::isnan(instance.controller->plainParamToNormalized(
        kA4, invalid_plain)));
  }
  ascii_to_vst3("432.5 Hz", text);
  M3_EXPECT_TRUE(instance.controller->getParamValueByString(kA4, text,
                                                             parsed) !=
                 Steinberg::kResultTrue);
  ascii_to_vst3("nan", text);
  M3_EXPECT_TRUE(instance.controller->getParamValueByString(kA4, text,
                                                             parsed) !=
                 Steinberg::kResultTrue);
  M3_EXPECT_TRUE(instance.controller->setParamNormalized(
                     m3::kStatusParameterId, 0.0) != Steinberg::kResultTrue);
  close_controller(instance);
}

M3_TEST(vst3_parameter_edits_accept_float_encoded_host_steps) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance));
  if (instance.controller == nullptr) {
    close_controller(instance);
    return;
  }

  const double highest_48 = static_cast<double>(
      static_cast<float>((48.0 - 24.0) / (108.0 - 24.0)));
  const double max_fret_12 = static_cast<double>(static_cast<float>(12.0 / 36.0));
  const double sensitivity_80 = static_cast<double>(static_cast<float>(0.80));
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330008U,
                                                        highest_48),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D33000AU,
                                                        max_fret_12),
               Steinberg::kResultTrue);
  M3_EXPECT_EQ(instance.controller->setParamNormalized(0x4D330005U,
                                                        sensitivity_80),
               Steinberg::kResultTrue);
  close_controller(instance);
}

M3_TEST(vst3_parameter_queue_coalesces_last_boundary_values_atomically) {
  m3::PersistentConfig initial;
  m3::test::FakeVst3ParameterChanges changes;
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 0, 0.5));
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 31, 0.40625));
  M3_EXPECT_TRUE(changes.append_input(0x4D33000FU, 7, 0.0));
  M3_EXPECT_TRUE(changes.append_input(m3::kPanicParameterId, 12, 1.0));
  M3_EXPECT_TRUE(changes.append_input(0xDEADBEEFU, -99,
                                      std::numeric_limits<double>::quiet_NaN()));
  m3::vst3::ParameterBatch batch;
  M3_EXPECT_TRUE(m3::vst3::read_last_boundary_values(
      &changes, 32, initial, batch));
  M3_EXPECT_TRUE(batch.changed);
  M3_EXPECT_TRUE(batch.structural);
  M3_EXPECT_TRUE(batch.panic);
  M3_EXPECT_NEAR(batch.candidate.a4_hz, 432.5, 1.0e-12);
  M3_EXPECT_FALSE(batch.candidate.dry_passthrough);

  m3::vst3::ParameterBatch empty;
  M3_EXPECT_TRUE(m3::vst3::read_last_boundary_values(nullptr, 0, initial,
                                                      empty));
  M3_EXPECT_FALSE(empty.changed);
  M3_EXPECT_FALSE(empty.structural);
  M3_EXPECT_FALSE(empty.panic);
  M3_EXPECT_TRUE(same_config(empty.candidate, initial));
}

M3_TEST(vst3_parameter_queue_rejects_malformed_host_data_without_mutation) {
  const m3::PersistentConfig initial;
  const auto rejected = [&](m3::test::FakeVst3ParameterChanges& changes,
                            Steinberg::int32 frames) noexcept {
    m3::vst3::ParameterBatch batch;
    batch.candidate.a4_hz = 432.5;
    M3_EXPECT_FALSE(m3::vst3::read_last_boundary_values(
        &changes, frames, initial, batch));
    M3_EXPECT_TRUE(same_config(batch.candidate, initial));
    M3_EXPECT_FALSE(batch.changed);
    M3_EXPECT_FALSE(batch.structural);
    M3_EXPECT_FALSE(batch.panic);
  };

  m3::test::FakeVst3ParameterChanges changes;
  changes.override_parameter_count(-1);
  rejected(changes, 32);
  changes.reset();
  changes.override_parameter_count(
      m3::vst3::kMaxParameterQueues + Steinberg::int32{1});
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 0, 0.5));
  changes.return_null_queue(0);
  rejected(changes, 32);
  changes.reset();
  auto* queue = changes.append_queue(0x4D330003U);
  M3_EXPECT_TRUE(queue != nullptr);
  if (queue != nullptr) {
    queue->override_point_count(-1);
  }
  rejected(changes, 32);
  changes.reset();
  queue = changes.append_queue(0x4D330003U);
  M3_EXPECT_TRUE(queue != nullptr);
  if (queue != nullptr) {
    queue->override_point_count(
        m3::vst3::kMaxParameterPointsPerQueue + Steinberg::int32{1});
  }
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 0, 0.5));
  queue = changes.stored_queue(0);
  if (queue != nullptr) {
    queue->reject_get_point(0);
  }
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, -1, 0.5));
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 32, 0.5));
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(
      0x4D330003U, 0, std::numeric_limits<double>::infinity()));
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(0x4D330003U, 0, 0.123456789));
  rejected(changes, 32);
  changes.reset();
  M3_EXPECT_TRUE(changes.append_input(m3::kStatusParameterId, 0, 0.0));
  rejected(changes, 32);
  changes.reset();
  rejected(changes, -1);
}

M3_TEST(vst3_output_parameter_helper_reports_every_rejection) {
  m3::test::FakeVst3ParameterChanges output;
  M3_EXPECT_TRUE(m3::vst3::push_output_value(
      &output, m3::kPanicParameterId, 0.0, 0));
  M3_EXPECT_EQ(output.stored_queue_count(), 1U);
  auto* queue = output.stored_queue(0);
  M3_EXPECT_TRUE(queue != nullptr);
  if (queue != nullptr) {
    M3_EXPECT_EQ(queue->getParameterId(), m3::kPanicParameterId);
    M3_EXPECT_EQ(queue->stored_point_count(), 1U);
    M3_EXPECT_EQ(queue->stored_point(0).offset, 0);
    M3_EXPECT_NEAR(queue->stored_point(0).value, 0.0, 0.0);
  }
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      nullptr, m3::kPanicParameterId, 0.0, 0));
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      &output, 0xDEADBEEFU, 0.0, 0));
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      &output, m3::kPanicParameterId,
      std::numeric_limits<double>::quiet_NaN(), 0));
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      &output, m3::kPanicParameterId, 0.0, -1));
  output.reset();
  output.reject_add_parameter(true);
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      &output, m3::kPanicParameterId, 0.0, 0));
  output.reset();
  output.reject_output_points(true);
  M3_EXPECT_FALSE(m3::vst3::push_output_value(
      &output, m3::kPanicParameterId, 0.0, 0));
}

M3_TEST(vst3_panic_is_momentary_and_retries_ready_output) {
  ControllerInstance instance;
  M3_EXPECT_TRUE(open_controller(instance, true));
  if (instance.controller == nullptr || instance.processor == nullptr) {
    close_controller(instance);
    return;
  }
  M3_EXPECT_EQ(instance.controller->setParamNormalized(
                   m3::kPanicParameterId, 1.0),
               Steinberg::kResultTrue);
  M3_EXPECT_NEAR(instance.controller->getParamNormalized(
                     m3::kPanicParameterId),
                 0.0, 0.0);

  Steinberg::Vst::ProcessData flush{};
  flush.processMode = Steinberg::Vst::kRealtime;
  flush.symbolicSampleSize = Steinberg::Vst::kSample32;
  flush.numSamples = 0;
  m3::test::FakeVst3ParameterChanges rejected;
  rejected.reject_output_points(true);
  flush.outputParameterChanges = &rejected;
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);

  m3::test::FakeVst3ParameterChanges accepted;
  flush.outputParameterChanges = &accepted;
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
  M3_EXPECT_EQ(accepted.stored_queue_count(), 1U);
  auto* queue = accepted.stored_queue(0);
  M3_EXPECT_TRUE(queue != nullptr);
  if (queue != nullptr) {
    M3_EXPECT_EQ(queue->getParameterId(), m3::kPanicParameterId);
    M3_EXPECT_EQ(queue->stored_point_count(), 1U);
    M3_EXPECT_NEAR(queue->stored_point(0).value, 0.0, 0.0);
  }
  accepted.reset();
  M3_EXPECT_EQ(instance.processor->process(flush), Steinberg::kResultOk);
  M3_EXPECT_EQ(accepted.stored_queue_count(), 0U);
  close_controller(instance);
}
