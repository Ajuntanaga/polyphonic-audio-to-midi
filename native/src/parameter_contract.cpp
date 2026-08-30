#include "m3/parameter_contract.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace {

constexpr std::array<m3::ParameterSpec, m3::kParameterCount> kParameters{{
    {0x4D330001U, "Detector input", 0.0, 2.0, 1.0, 0.0, 2,
     m3::ParameterUpdateClass::structural, true, true, false},
    {0x4D330002U, "Mode", 0.0, 1.0, 1.0, 0.0, 1,
     m3::ParameterUpdateClass::structural, true, true, false},
    {0x4D330003U, "A4 reference", 400.0, 480.0, 0.1, 440.0, 800,
     m3::ParameterUpdateClass::structural, true, false, false},
    {0x4D330004U, "Input trim", -24.0, 24.0, 0.1, 0.0, 480,
     m3::ParameterUpdateClass::runtime, true, false, false},
    {0x4D330005U, "Sensitivity", 0.0, 100.0, 1.0, 50.0, 100,
     m3::ParameterUpdateClass::runtime, true, false, false},
    {0x4D330006U, "Response", 0.0, 100.0, 1.0, 25.0, 100,
     m3::ParameterUpdateClass::runtime, true, false, false},
    {0x4D330007U, "Lowest MIDI note", 24.0, 108.0, 1.0, 32.0, 84,
     m3::ParameterUpdateClass::structural, true, false, false},
    {0x4D330008U, "Highest MIDI note", 24.0, 108.0, 1.0, 84.0, 84,
     m3::ParameterUpdateClass::structural, true, false, false},
    {0x4D330009U, "Maximum polyphony", 1.0, 8.0, 1.0, 8.0, 7,
     m3::ParameterUpdateClass::structural, true, false, false},
    {0x4D33000AU, "M3 maximum fret", 0.0, 36.0, 1.0, 24.0, 36,
     m3::ParameterUpdateClass::structural, true, false, false},
    {0x4D33000BU, "Velocity mode", 0.0, 1.0, 1.0, 1.0, 1,
     m3::ParameterUpdateClass::runtime, true, true, false},
    {0x4D33000CU, "Fixed velocity", 1.0, 127.0, 1.0, 100.0, 126,
     m3::ParameterUpdateClass::runtime, true, false, false},
    {0x4D33000DU, "MIDI channel", 1.0, 16.0, 1.0, 1.0, 15,
     m3::ParameterUpdateClass::structural, true, false, false},
    {m3::kPanicParameterId, "Panic", 0.0, 1.0, 1.0, 0.0, 1,
     m3::ParameterUpdateClass::action, false, true, false},
    {0x4D33000FU, "Dry audio", 0.0, 1.0, 1.0, 1.0, 1,
     m3::ParameterUpdateClass::runtime, true, true, false},
    {m3::kStatusParameterId, "Status", 0.0, 5.0, 1.0, 0.0, 5,
     m3::ParameterUpdateClass::telemetry, false, true, true},
}};

constexpr std::array<m3::ParameterId, m3::kPersistentParameterCount>
    kPersistentIds{{
        0x4D330001U, 0x4D330002U, 0x4D330003U, 0x4D330004U,
        0x4D330005U, 0x4D330006U, 0x4D330007U, 0x4D330008U,
        0x4D330009U, 0x4D33000AU, 0x4D33000BU, 0x4D33000CU,
        0x4D33000DU, 0x4D33000FU,
    }};

constexpr const char* kDetectorInputLabels[] = {"Left", "Right", "Downmix"};
constexpr const char* kModeLabels[] = {"M3 Eight-String", "General Tonal"};
constexpr const char* kVelocityLabels[] = {"Fixed", "Dynamic"};
constexpr const char* kPanicLabels[] = {"Ready", "Panic"};
constexpr const char* kDryLabels[] = {"Muted", "Pass through"};
constexpr const char* kStatusLabels[] = {
    "Ready", "Panic Hold", "Reconfiguring", "MIDI Output Blocked",
    "Invalid Input or State", "Unsupported Layout"};

bool valid_spec(const m3::ParameterSpec& spec) noexcept {
  return spec.name != nullptr && std::isfinite(spec.minimum) &&
         std::isfinite(spec.maximum) && std::isfinite(spec.increment) &&
         spec.maximum > spec.minimum && spec.increment > 0.0 &&
         spec.step_count > 0;
}

bool copy_text(const char* source, char* output,
               std::uint32_t capacity) noexcept {
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

bool append_unsigned(std::uint32_t value, char* output,
                     std::size_t capacity, std::size_t& position) noexcept {
  char reversed[10]{};
  std::size_t digit_count = 0U;
  do {
    reversed[digit_count++] =
        static_cast<char>('0' + static_cast<char>(value % 10U));
    value /= 10U;
  } while (value > 0U && digit_count < std::size(reversed));
  if (position + digit_count >= capacity) {
    return false;
  }
  while (digit_count > 0U) {
    output[position++] = reversed[--digit_count];
  }
  return true;
}

bool format_parameter_number(double value, bool one_decimal, char* output,
                             std::uint32_t capacity) noexcept {
  if (output == nullptr || capacity == 0U || !std::isfinite(value)) {
    return false;
  }
  char text[32]{};
  std::size_t position = 0U;
  const double scale = one_decimal ? 10.0 : 1.0;
  const long long signed_scaled = std::llround(value * scale);
  const bool negative = signed_scaled < 0;
  const auto magnitude = static_cast<std::uint32_t>(
      negative ? -signed_scaled : signed_scaled);
  if (negative) {
    text[position++] = '-';
  }
  const std::uint32_t whole = one_decimal ? magnitude / 10U : magnitude;
  if (!append_unsigned(whole, text, std::size(text), position)) {
    return false;
  }
  if (one_decimal) {
    if (position + 2U >= std::size(text)) {
      return false;
    }
    text[position++] = '.';
    text[position++] =
        static_cast<char>('0' + static_cast<char>(magnitude % 10U));
  }
  text[position] = '\0';
  return copy_text(text, output, capacity);
}

const char* enum_label(m3::ParameterId id, std::size_t index) noexcept {
  switch (id) {
    case 0x4D330001U:
      return index < std::size(kDetectorInputLabels)
                 ? kDetectorInputLabels[index]
                 : nullptr;
    case 0x4D330002U:
      return index < std::size(kModeLabels) ? kModeLabels[index] : nullptr;
    case 0x4D33000BU:
      return index < std::size(kVelocityLabels) ? kVelocityLabels[index]
                                                : nullptr;
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

const ParameterSpec* parameter_spec(std::size_t index) noexcept {
  return index < kParameters.size() ? &kParameters[index] : nullptr;
}

const ParameterSpec* find_parameter(ParameterId id) noexcept {
  for (const ParameterSpec& spec : kParameters) {
    if (spec.id == id) {
      return &spec;
    }
  }
  return nullptr;
}

double canonical_plain(const ParameterSpec& spec, double value) noexcept {
  if (!valid_spec(spec) || !std::isfinite(value)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double bounded = std::max(spec.minimum, std::min(value, spec.maximum));
  const double steps = std::round((bounded - spec.minimum) / spec.increment);
  const double rounded = spec.minimum + steps * spec.increment;
  return std::max(spec.minimum, std::min(rounded, spec.maximum));
}

double plain_to_normalized(const ParameterSpec& spec, double value) noexcept {
  const double plain = canonical_plain(spec, value);
  if (!std::isfinite(plain)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double normalized =
      (plain - spec.minimum) / (spec.maximum - spec.minimum);
  return std::max(0.0, std::min(normalized, 1.0));
}

double normalized_to_plain(const ParameterSpec& spec, double value) noexcept {
  if (!valid_spec(spec) || !std::isfinite(value)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double normalized = std::max(0.0, std::min(value, 1.0));
  return canonical_plain(
      spec, spec.minimum + normalized * (spec.maximum - spec.minimum));
}

bool parameter_value(const PersistentConfig& config, Status status,
                     ParameterId id, double& value) noexcept {
  switch (id) {
    case 0x4D330001U:
      value = static_cast<double>(config.detector_input);
      return true;
    case 0x4D330002U:
      value = static_cast<double>(config.profile_mode);
      return true;
    case 0x4D330003U:
      value = config.a4_hz;
      return true;
    case 0x4D330004U:
      value = config.input_trim_db;
      return true;
    case 0x4D330005U:
      value = config.sensitivity;
      return true;
    case 0x4D330006U:
      value = config.response;
      return true;
    case 0x4D330007U:
      value = config.lowest_note;
      return true;
    case 0x4D330008U:
      value = config.highest_note;
      return true;
    case 0x4D330009U:
      value = config.max_polyphony;
      return true;
    case 0x4D33000AU:
      value = config.max_fret;
      return true;
    case 0x4D33000BU:
      value = static_cast<double>(config.velocity_mode);
      return true;
    case 0x4D33000CU:
      value = config.fixed_velocity;
      return true;
    case 0x4D33000DU:
      value = config.midi_channel;
      return true;
    case kPanicParameterId:
      value = 0.0;
      return true;
    case 0x4D33000FU:
      value = config.dry_passthrough ? 1.0 : 0.0;
      return true;
    case kStatusParameterId:
      value = static_cast<double>(status);
      return true;
    default:
      return false;
  }
}

ParameterApplyResult apply_parameter(PersistentConfig& config, ParameterId id,
                                     double plain_value) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  if (spec == nullptr || spec->read_only || !std::isfinite(plain_value)) {
    return ParameterApplyResult::rejected;
  }
  const double value = canonical_plain(*spec, plain_value);
  if (!std::isfinite(value)) {
    return ParameterApplyResult::rejected;
  }
  if (id == kPanicParameterId) {
    return value >= 1.0 ? ParameterApplyResult::panic
                        : ParameterApplyResult::unchanged;
  }

  double previous = 0.0;
  static_cast<void>(parameter_value(config, Status::ready, id, previous));
  switch (id) {
    case 0x4D330001U:
      config.detector_input = static_cast<DetectorInput>(value);
      break;
    case 0x4D330002U:
      config.profile_mode = static_cast<ProfileMode>(value);
      break;
    case 0x4D330003U:
      config.a4_hz = value;
      break;
    case 0x4D330004U:
      config.input_trim_db = value;
      break;
    case 0x4D330005U:
      config.sensitivity = static_cast<std::uint8_t>(value);
      break;
    case 0x4D330006U:
      config.response = static_cast<std::uint8_t>(value);
      break;
    case 0x4D330007U:
      config.lowest_note = static_cast<std::uint8_t>(value);
      break;
    case 0x4D330008U:
      config.highest_note = static_cast<std::uint8_t>(value);
      break;
    case 0x4D330009U:
      config.max_polyphony = static_cast<std::uint8_t>(value);
      break;
    case 0x4D33000AU:
      config.max_fret = static_cast<std::uint8_t>(value);
      break;
    case 0x4D33000BU:
      config.velocity_mode = static_cast<VelocityMode>(value);
      break;
    case 0x4D33000CU:
      config.fixed_velocity = static_cast<std::uint8_t>(value);
      break;
    case 0x4D33000DU:
      config.midi_channel = static_cast<std::uint8_t>(value);
      break;
    case 0x4D33000FU:
      config.dry_passthrough = value >= 1.0;
      break;
    default:
      return ParameterApplyResult::rejected;
  }
  return previous == value ? ParameterApplyResult::unchanged
                           : ParameterApplyResult::changed;
}

bool parameter_value_to_text(ParameterId id, double value, char* output,
                             std::uint32_t capacity) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  if (spec == nullptr || !std::isfinite(value) || output == nullptr ||
      capacity == 0) {
    return false;
  }
  value = canonical_plain(*spec, value);
  if (!std::isfinite(value)) {
    return false;
  }
  if (const char* label = enum_label(id, static_cast<std::size_t>(value))) {
    return copy_text(label, output, capacity);
  }
  return format_parameter_number(
      value, id == 0x4D330003U || id == 0x4D330004U, output, capacity);
}

bool parameter_text_to_value(ParameterId id, const char* text,
                             double& value) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  if (spec == nullptr || text == nullptr || spec->read_only) {
    return false;
  }
  for (std::int32_t step = 0; step <= spec->step_count; ++step) {
    const char* label = enum_label(id, static_cast<std::size_t>(step));
    if (label != nullptr && std::strcmp(label, text) == 0) {
      value = spec->minimum + spec->increment * static_cast<double>(step);
      return true;
    }
  }
  char* end = nullptr;
  const double parsed = std::strtod(text, &end);
  if (end == text || *end != '\0' || !std::isfinite(parsed)) {
    return false;
  }
  value = canonical_plain(*spec, parsed);
  return std::isfinite(value);
}

const ParameterId* persistent_parameter_ids() noexcept {
  return kPersistentIds.data();
}

}  // namespace m3
