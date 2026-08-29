#include "parameter_contract.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

constexpr clap_param_info_flags kContinuous = CLAP_PARAM_REQUIRES_PROCESS;
constexpr clap_param_info_flags kStepped =
    CLAP_PARAM_IS_STEPPED | CLAP_PARAM_REQUIRES_PROCESS;
constexpr clap_param_info_flags kEnum =
    CLAP_PARAM_IS_STEPPED | CLAP_PARAM_IS_ENUM | CLAP_PARAM_REQUIRES_PROCESS;
constexpr clap_param_info_flags kReadOnlyEnum =
    CLAP_PARAM_IS_STEPPED | CLAP_PARAM_IS_ENUM | CLAP_PARAM_IS_READONLY;

constexpr std::array<m3::ParameterRecord, 16> kParameters{{
    {0x4D330001U, "Detector input", 0.0, 2.0, 0.0, kEnum,
     m3::ParameterUpdateClass::structural, true},
    {0x4D330002U, "Mode", 0.0, 1.0, 0.0, kEnum,
     m3::ParameterUpdateClass::structural, true},
    {0x4D330003U, "A4 reference", 400.0, 480.0, 440.0, kContinuous,
     m3::ParameterUpdateClass::structural, true},
    {0x4D330004U, "Input trim", -24.0, 24.0, 0.0, kContinuous,
     m3::ParameterUpdateClass::runtime, true},
    {0x4D330005U, "Sensitivity", 0.0, 100.0, 50.0, kStepped,
     m3::ParameterUpdateClass::runtime, true},
    {0x4D330006U, "Response", 0.0, 100.0, 25.0, kStepped,
     m3::ParameterUpdateClass::runtime, true},
    {0x4D330007U, "Lowest MIDI note", 24.0, 108.0, 32.0, kStepped,
     m3::ParameterUpdateClass::structural, true},
    {0x4D330008U, "Highest MIDI note", 24.0, 108.0, 84.0, kStepped,
     m3::ParameterUpdateClass::structural, true},
    {0x4D330009U, "Maximum polyphony", 1.0, 8.0, 8.0, kStepped,
     m3::ParameterUpdateClass::structural, true},
    {0x4D33000AU, "M3 maximum fret", 0.0, 36.0, 24.0, kStepped,
     m3::ParameterUpdateClass::structural, true},
    {0x4D33000BU, "Velocity mode", 0.0, 1.0, 1.0, kEnum,
     m3::ParameterUpdateClass::runtime, true},
    {0x4D33000CU, "Fixed velocity", 1.0, 127.0, 100.0, kStepped,
     m3::ParameterUpdateClass::runtime, true},
    {0x4D33000DU, "MIDI channel", 1.0, 16.0, 1.0, kStepped,
     m3::ParameterUpdateClass::structural, true},
    {m3::kPanicParameterId, "Panic", 0.0, 1.0, 0.0, kEnum,
     m3::ParameterUpdateClass::action, false},
    {0x4D33000FU, "Dry audio", 0.0, 1.0, 1.0, kEnum,
     m3::ParameterUpdateClass::runtime, true},
    {m3::kStatusParameterId, "Status", 0.0, 5.0, 0.0, kReadOnlyEnum,
     m3::ParameterUpdateClass::telemetry, false},
}};

constexpr std::array<clap_id, m3::kPersistentParameterCount> kPersistentIds{{
    0x4D330001U, 0x4D330002U, 0x4D330003U, 0x4D330004U, 0x4D330005U,
    0x4D330006U, 0x4D330007U, 0x4D330008U, 0x4D330009U, 0x4D33000AU,
    0x4D33000BU, 0x4D33000CU, 0x4D33000DU, 0x4D33000FU,
}};

constexpr const char* kDetectorInputLabels[] = {"Left", "Right", "Downmix"};
constexpr const char* kModeLabels[] = {"M3 Eight-String", "General Tonal"};
constexpr const char* kVelocityLabels[] = {"Fixed", "Dynamic"};
constexpr const char* kPanicLabels[] = {"Ready", "Panic"};
constexpr const char* kDryLabels[] = {"Muted", "Pass through"};
constexpr const char* kStatusLabels[] = {
    "Ready", "Panic Hold", "Reconfiguring", "MIDI Output Blocked",
    "Invalid Input or State", "Unsupported Layout"};

double canonical_value(const m3::ParameterRecord& record, double value) noexcept {
  value = std::max(record.minimum, std::min(value, record.maximum));
  if ((record.flags & CLAP_PARAM_IS_STEPPED) != 0U) {
    value = std::trunc(value);
  } else if (record.id == 0x4D330003U || record.id == 0x4D330004U) {
    value = std::round(value * 10.0) / 10.0;
  }
  return value;
}

bool copy_text(const char* source, char* output, std::uint32_t capacity) noexcept {
  if (source == nullptr || output == nullptr || capacity == 0) {
    return false;
  }
  const std::size_t length = std::strlen(source);
  if (length + 1U > capacity) {
    return false;
  }
  std::memcpy(output, source, length + 1U);
  return true;
}

const char* enum_label(clap_id id, std::size_t index) noexcept {
  switch (id) {
    case 0x4D330001U:
      return index < std::size(kDetectorInputLabels) ? kDetectorInputLabels[index] : nullptr;
    case 0x4D330002U:
      return index < std::size(kModeLabels) ? kModeLabels[index] : nullptr;
    case 0x4D33000BU:
      return index < std::size(kVelocityLabels) ? kVelocityLabels[index] : nullptr;
    case m3::kPanicParameterId:
      return index < std::size(kPanicLabels) ? kPanicLabels[index] : nullptr;
    case 0x4D33000FU:
      return index < std::size(kDryLabels) ? kDryLabels[index] : nullptr;
    case m3::kStatusParameterId:
      return index < std::size(kStatusLabels) ? kStatusLabels[index] : nullptr;
    default:
      return nullptr;
  }
}

}  // namespace

namespace m3 {

std::size_t parameter_count() noexcept { return kParameters.size(); }

const ParameterRecord* parameter_record(std::size_t index) noexcept {
  return index < kParameters.size() ? &kParameters[index] : nullptr;
}

const ParameterRecord* find_parameter(clap_id id) noexcept {
  for (const ParameterRecord& record : kParameters) {
    if (record.id == id) {
      return &record;
    }
  }
  return nullptr;
}

bool parameter_value(const PersistentConfig& config, Status status, clap_id id,
                     double& value) noexcept {
  switch (id) {
    case 0x4D330001U: value = static_cast<double>(config.detector_input); return true;
    case 0x4D330002U: value = static_cast<double>(config.profile_mode); return true;
    case 0x4D330003U: value = config.a4_hz; return true;
    case 0x4D330004U: value = config.input_trim_db; return true;
    case 0x4D330005U: value = config.sensitivity; return true;
    case 0x4D330006U: value = config.response; return true;
    case 0x4D330007U: value = config.lowest_note; return true;
    case 0x4D330008U: value = config.highest_note; return true;
    case 0x4D330009U: value = config.max_polyphony; return true;
    case 0x4D33000AU: value = config.max_fret; return true;
    case 0x4D33000BU: value = static_cast<double>(config.velocity_mode); return true;
    case 0x4D33000CU: value = config.fixed_velocity; return true;
    case 0x4D33000DU: value = config.midi_channel; return true;
    case kPanicParameterId: value = 0.0; return true;
    case 0x4D33000FU: value = config.dry_passthrough ? 1.0 : 0.0; return true;
    case kStatusParameterId: value = static_cast<double>(status); return true;
    default: return false;
  }
}

ParameterApplyResult apply_parameter(PersistentConfig& config, clap_id id,
                                     double value) noexcept {
  const ParameterRecord* record = find_parameter(id);
  if (record == nullptr || !std::isfinite(value) || id == kStatusParameterId) {
    return ParameterApplyResult::rejected;
  }
  value = canonical_value(*record, value);
  if (id == kPanicParameterId) {
    return value >= 1.0 ? ParameterApplyResult::panic
                        : ParameterApplyResult::unchanged;
  }

  double previous = 0.0;
  static_cast<void>(parameter_value(config, Status::ready, id, previous));
  switch (id) {
    case 0x4D330001U: config.detector_input = static_cast<DetectorInput>(value); break;
    case 0x4D330002U: config.profile_mode = static_cast<ProfileMode>(value); break;
    case 0x4D330003U: config.a4_hz = value; break;
    case 0x4D330004U: config.input_trim_db = value; break;
    case 0x4D330005U: config.sensitivity = static_cast<std::uint8_t>(value); break;
    case 0x4D330006U: config.response = static_cast<std::uint8_t>(value); break;
    case 0x4D330007U: config.lowest_note = static_cast<std::uint8_t>(value); break;
    case 0x4D330008U: config.highest_note = static_cast<std::uint8_t>(value); break;
    case 0x4D330009U: config.max_polyphony = static_cast<std::uint8_t>(value); break;
    case 0x4D33000AU: config.max_fret = static_cast<std::uint8_t>(value); break;
    case 0x4D33000BU: config.velocity_mode = static_cast<VelocityMode>(value); break;
    case 0x4D33000CU: config.fixed_velocity = static_cast<std::uint8_t>(value); break;
    case 0x4D33000DU: config.midi_channel = static_cast<std::uint8_t>(value); break;
    case 0x4D33000FU: config.dry_passthrough = value >= 1.0; break;
    default: return ParameterApplyResult::rejected;
  }
  return previous == value ? ParameterApplyResult::unchanged
                           : ParameterApplyResult::changed;
}

bool parameter_value_to_text(clap_id id, double value, char* output,
                             std::uint32_t capacity) noexcept {
  const ParameterRecord* record = find_parameter(id);
  if (record == nullptr || !std::isfinite(value) || output == nullptr || capacity == 0) {
    return false;
  }
  value = canonical_value(*record, value);
  if (const char* label = enum_label(id, static_cast<std::size_t>(value))) {
    return copy_text(label, output, capacity);
  }
  const int written = (id == 0x4D330003U || id == 0x4D330004U)
                          ? std::snprintf(output, capacity, "%.1f", value)
                          : std::snprintf(output, capacity, "%.0f", value);
  return written >= 0 && static_cast<std::uint32_t>(written) < capacity;
}

bool parameter_text_to_value(clap_id id, const char* text, double& value) noexcept {
  const ParameterRecord* record = find_parameter(id);
  if (record == nullptr || text == nullptr || id == kStatusParameterId) {
    return false;
  }
  for (std::size_t index = 0; index <= static_cast<std::size_t>(record->maximum); ++index) {
    const char* label = enum_label(id, index);
    if (label != nullptr && std::strcmp(label, text) == 0) {
      value = static_cast<double>(index);
      return true;
    }
  }
  char* end = nullptr;
  const double parsed = std::strtod(text, &end);
  if (end == text || *end != '\0' || !std::isfinite(parsed)) {
    return false;
  }
  value = canonical_value(*record, parsed);
  return true;
}

const clap_id* persistent_parameter_ids() noexcept { return kPersistentIds.data(); }

}  // namespace m3
