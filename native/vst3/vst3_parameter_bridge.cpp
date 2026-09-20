#include "vst3_parameter_bridge.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdint>
#include <limits>
#include <new>

#include "pluginterfaces/base/ustring.h"

namespace m3::vst3 {
namespace {

constexpr double kCanonicalTolerance = 1.0e-12;
// Hosts commonly persist or route VST3 normalized values through float.
// Accept that representation of a declared discrete step, then canonicalize
// it to the exact plain value before it reaches the processor.
constexpr double kHostNormalizedTolerance = 1.0e-6;
constexpr std::array<ParameterSpec, 2> kTunerParameters{{
    {kTunerNoteParameterId, "Tuner note", 0.0, 128.0, 1.0,
     static_cast<double>(kTunerNoSignalNote), 128,
     ParameterUpdateClass::telemetry, false, true, true},
    {kTunerCentsParameterId, "Tuner cents", -50.0, 50.0, 0.1, 0.0, 1000,
     ParameterUpdateClass::telemetry, false, false, true},
}};

bool result_ok(Steinberg::tresult result) noexcept {
  return result == Steinberg::kResultOk || result == Steinberg::kResultTrue;
}

bool same_value(double left, double right) noexcept {
  return std::abs(left - right) <= kCanonicalTolerance;
}

bool parameter_index(ParameterId id, std::size_t& output) noexcept {
  for (std::size_t index = 0; index < kParameterCount; ++index) {
    const ParameterSpec* spec = parameter_spec(index);
    if (spec != nullptr && spec->id == id) {
      output = index;
      return true;
    }
  }
  return false;
}

bool build_parameter_info(const ParameterSpec& spec,
                          Steinberg::Vst::ParameterInfo& info) noexcept {
  double normalized = 0.0;
  if (spec.name == nullptr ||
      !canonical_plain_value(spec, spec.default_value, normalized)) {
    return false;
  }
  info = {};
  Steinberg::UString(info.title, 128).fromAscii(spec.name);
  if (info.title[0] == 0) {
    return false;
  }
  info.id = static_cast<Steinberg::Vst::ParamID>(spec.id);
  info.stepCount = spec.step_count;
  info.defaultNormalizedValue = normalized;
  info.unitId = Steinberg::Vst::kRootUnitId;
  info.flags = Steinberg::Vst::ParameterInfo::kNoFlags;
  if (spec.list) {
    info.flags |= Steinberg::Vst::ParameterInfo::kIsList;
  }
  if (spec.read_only) {
    info.flags |= Steinberg::Vst::ParameterInfo::kIsReadOnly;
  }
  return true;
}

class ContractParameter final : public Steinberg::Vst::Parameter {
 public:
  ContractParameter(const ParameterSpec& spec,
                    const Steinberg::Vst::ParameterInfo& parameter_info) noexcept
      : Steinberg::Vst::Parameter(parameter_info), spec_(spec) {}

  void toString(Steinberg::Vst::ParamValue normalized,
                Steinberg::Vst::String128 output) const override {
    if (output == nullptr) {
      return;
    }
    output[0] = 0;
    double plain = 0.0;
    char text[128]{};
    if (!canonical_normalized_value(spec_, normalized, plain) ||
        !vst3_parameter_value_to_text(
            spec_.id, plain, text,
            static_cast<std::uint32_t>(sizeof(text)))) {
      return;
    }
    Steinberg::UString(output, 128).fromAscii(text);
  }

  bool fromString(const Steinberg::Vst::TChar* input,
                  Steinberg::Vst::ParamValue& normalized) const override {
    if (input == nullptr) {
      return false;
    }
    if (spec_.read_only) {
      return false;
    }
    char text[128]{};
    Steinberg::UString(
        const_cast<Steinberg::Vst::TChar*>(input), 128)
        .toAscii(text, static_cast<Steinberg::int32>(sizeof(text)));
    double plain = 0.0;
    return parameter_text_to_value(spec_.id, text, plain) &&
           canonical_plain_value(spec_, plain, normalized);
  }

  Steinberg::Vst::ParamValue toPlain(
      Steinberg::Vst::ParamValue normalized) const override {
    double plain = std::numeric_limits<double>::quiet_NaN();
    static_cast<void>(canonical_normalized_value(spec_, normalized, plain));
    return plain;
  }

  Steinberg::Vst::ParamValue toNormalized(
      Steinberg::Vst::ParamValue plain) const override {
    double normalized = std::numeric_limits<double>::quiet_NaN();
    static_cast<void>(canonical_plain_value(spec_, plain, normalized));
    return normalized;
  }

  bool setNormalized(Steinberg::Vst::ParamValue normalized) override {
    double plain = 0.0;
    return canonical_normalized_value(spec_, normalized, plain) &&
           Steinberg::Vst::Parameter::setNormalized(normalized);
  }

 private:
  const ParameterSpec& spec_;
};

}  // namespace

const ParameterSpec* vst3_parameter_spec(std::size_t index) noexcept {
  if (index < kParameterCount) {
    return parameter_spec(index);
  }
  const std::size_t tuner_index = index - kParameterCount;
  return tuner_index < kTunerParameters.size()
             ? &kTunerParameters[tuner_index]
             : nullptr;
}

const ParameterSpec* find_vst3_parameter(ParameterId id) noexcept {
  if (const ParameterSpec* shared = find_parameter(id); shared != nullptr) {
    return shared;
  }
  for (const ParameterSpec& spec : kTunerParameters) {
    if (spec.id == id) {
      return &spec;
    }
  }
  return nullptr;
}

bool vst3_parameter_value_to_text(ParameterId id, double value, char* output,
                                  std::uint32_t capacity) noexcept {
  if (output == nullptr || capacity == 0U || !std::isfinite(value)) {
    return false;
  }
  output[0] = '\0';
  int written = -1;
  if (id == kTunerNoteParameterId) {
    const long note = std::lround(value);
    if (note == static_cast<long>(kTunerNoSignalNote)) {
      written = std::snprintf(output, capacity, "%s", "No signal");
    } else if (note >= 0L && note <= 127L) {
      constexpr std::array<const char*, 12> kNames{
          "C", "C#", "D", "D#", "E", "F",
          "F#", "G", "G#", "A", "A#", "B"};
      written = std::snprintf(output, capacity, "%s%ld",
                              kNames[static_cast<std::size_t>(note % 12L)],
                              note / 12L - 1L);
    }
  } else if (id == kTunerCentsParameterId) {
    const double canonical = std::abs(value) < 0.05 ? 0.0 : value;
    written = std::snprintf(output, capacity, "%+.1f", canonical);
  } else {
    return parameter_value_to_text(id, value, output, capacity);
  }
  return written >= 0 && static_cast<std::uint32_t>(written) < capacity;
}

bool canonical_normalized_value(const ParameterSpec& spec, double normalized,
                                double& plain) noexcept {
  if (!std::isfinite(normalized) || normalized < 0.0 || normalized > 1.0) {
    return false;
  }
  const double candidate = normalized_to_plain(spec, normalized);
  const double canonical = plain_to_normalized(spec, candidate);
  if (!std::isfinite(candidate) || !std::isfinite(canonical) ||
      std::abs(normalized - canonical) > kHostNormalizedTolerance) {
    return false;
  }
  plain = candidate;
  return true;
}

bool canonical_plain_value(const ParameterSpec& spec, double plain,
                           double& normalized) noexcept {
  if (!std::isfinite(plain) || plain < spec.minimum || plain > spec.maximum) {
    return false;
  }
  const double candidate = canonical_plain(spec, plain);
  if (!std::isfinite(candidate) || !same_value(plain, candidate)) {
    return false;
  }
  const double output = plain_to_normalized(spec, candidate);
  if (!std::isfinite(output)) {
    return false;
  }
  normalized = output;
  return true;
}

bool register_vst3_parameters(
    Steinberg::Vst::ParameterContainer& container) noexcept {
  container.init(static_cast<Steinberg::int32>(kVst3ParameterCount));
  for (std::size_t index = 0; index < kVst3ParameterCount; ++index) {
    const ParameterSpec* spec = vst3_parameter_spec(index);
    Steinberg::Vst::ParameterInfo info{};
    if (spec == nullptr || !build_parameter_info(*spec, info)) {
      return false;
    }
    auto* parameter = new (std::nothrow) ContractParameter(*spec, info);
    if (parameter == nullptr) {
      return false;
    }
    static_cast<void>(container.addParameter(parameter));
  }
  return true;
}

bool synchronize_vst3_parameters(
    Steinberg::Vst::ParameterContainer& container,
    const PersistentConfig& config, Status status) noexcept {
  for (std::size_t index = 0; index < kVst3ParameterCount; ++index) {
    const ParameterSpec* spec = vst3_parameter_spec(index);
    if (spec == nullptr) {
      return false;
    }
    double plain = 0.0;
    double normalized = 0.0;
    Steinberg::Vst::Parameter* parameter = container.getParameter(spec->id);
    const bool has_value = index < kParameterCount
                               ? parameter_value(config, status, spec->id, plain)
                               : (plain = spec->default_value, true);
    if (parameter == nullptr || !has_value ||
        !canonical_plain_value(*spec, plain, normalized)) {
      return false;
    }
    static_cast<void>(parameter->setNormalized(normalized));
  }
  return true;
}

bool read_last_boundary_values(
    Steinberg::Vst::IParameterChanges* changes, Steinberg::int32 num_samples,
    const PersistentConfig& current, ParameterBatch& output) noexcept {
  output = ParameterBatch{current, false, false, false};
  if (num_samples < 0) {
    return false;
  }
  if (changes == nullptr) {
    return true;
  }
  const Steinberg::int32 queue_count = changes->getParameterCount();
  if (queue_count < 0 || queue_count > kMaxParameterQueues) {
    return false;
  }

  std::array<double, kParameterCount> last_values{};
  std::array<bool, kParameterCount> seen{};
  for (Steinberg::int32 queue_index = 0; queue_index < queue_count;
       ++queue_index) {
    Steinberg::Vst::IParamValueQueue* queue =
        changes->getParameterData(queue_index);
    if (queue == nullptr) {
      return false;
    }
    std::size_t spec_index = 0;
    if (!parameter_index(queue->getParameterId(), spec_index)) {
      if (find_vst3_parameter(queue->getParameterId()) != nullptr) {
        return false;
      }
      continue;
    }
    const ParameterSpec* spec = parameter_spec(spec_index);
    if (spec == nullptr) {
      return false;
    }
    const Steinberg::int32 point_count = queue->getPointCount();
    if (point_count < 0 || point_count > kMaxParameterPointsPerQueue) {
      return false;
    }
    for (Steinberg::int32 point_index = 0; point_index < point_count;
         ++point_index) {
      Steinberg::int32 offset = -1;
      Steinberg::Vst::ParamValue normalized =
          std::numeric_limits<double>::quiet_NaN();
      if (!result_ok(queue->getPoint(point_index, offset, normalized)) ||
          offset < 0 ||
          (num_samples == 0 ? offset != 0 : offset >= num_samples)) {
        return false;
      }
      double plain = 0.0;
      if (spec->read_only ||
          !canonical_normalized_value(*spec, normalized, plain)) {
        return false;
      }
      last_values[spec_index] = normalized;
      seen[spec_index] = true;
    }
  }

  ParameterBatch candidate{current, false, false, false};
  for (std::size_t index = 0; index < kParameterCount; ++index) {
    if (!seen[index]) {
      continue;
    }
    const ParameterSpec* spec = parameter_spec(index);
    if (spec == nullptr) {
      return false;
    }
    double plain = 0.0;
    if (!canonical_normalized_value(*spec, last_values[index], plain)) {
      return false;
    }
    const ParameterApplyResult result =
        apply_parameter(candidate.candidate, spec->id, plain);
    if (result == ParameterApplyResult::rejected) {
      return false;
    }
    if (result == ParameterApplyResult::panic) {
      candidate.panic = true;
      continue;
    }
    if (result == ParameterApplyResult::changed) {
      candidate.changed = true;
      candidate.structural =
          candidate.structural ||
          spec->update_class == ParameterUpdateClass::structural;
    }
  }
  output = candidate;
  return true;
}

bool push_output_value(Steinberg::Vst::IParameterChanges* changes,
                       ParameterId id, double normalized,
                       Steinberg::int32 offset) noexcept {
  const ParameterSpec* spec = find_vst3_parameter(id);
  double plain = 0.0;
  if (changes == nullptr || spec == nullptr || offset < 0 ||
      !canonical_normalized_value(*spec, normalized, plain)) {
    return false;
  }
  Steinberg::int32 queue_index = -1;
  Steinberg::Vst::IParamValueQueue* queue =
      changes->addParameterData(id, queue_index);
  if (queue == nullptr || queue_index < 0) {
    return false;
  }
  Steinberg::int32 point_index = -1;
  return result_ok(queue->addPoint(offset, normalized, point_index)) &&
         point_index >= 0;
}

}  // namespace m3::vst3
