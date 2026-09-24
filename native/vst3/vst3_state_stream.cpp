#include "vst3_state_stream.hpp"

#include <cstddef>
#include <cstdint>

#include "m3/calibration_state_image.hpp"

namespace m3::vst3 {
namespace {

bool result_ok(Steinberg::tresult result) noexcept {
  return result == Steinberg::kResultOk || result == Steinberg::kResultTrue;
}

bool write_exact(Steinberg::IBStream* stream, const std::uint8_t* bytes,
                 std::size_t size) noexcept {
  std::size_t position = 0U;
  while (position < size) {
    const std::size_t remaining = size - position;
    const auto request = static_cast<Steinberg::int32>(remaining);
    Steinberg::int32 written = 0;
    const Steinberg::tresult result = stream->write(
        const_cast<std::uint8_t*>(bytes + position), request, &written);
    if (!result_ok(result) || written <= 0 || written > request) {
      return false;
    }
    position += static_cast<std::size_t>(written);
  }
  return true;
}

bool read_exact(Steinberg::IBStream* stream, std::uint8_t* bytes,
                std::size_t size) noexcept {
  std::size_t position = 0U;
  while (position < size) {
    const std::size_t remaining = size - position;
    const auto request = static_cast<Steinberg::int32>(remaining);
    Steinberg::int32 read = 0;
    const Steinberg::tresult result =
        stream->read(bytes + position, request, &read);
    if (!result_ok(result) || read <= 0 || read > request) {
      return false;
    }
    position += static_cast<std::size_t>(read);
  }
  return true;
}

bool read_eof(Steinberg::IBStream* stream) noexcept {
  std::uint8_t trailing = 0U;
  Steinberg::int32 trailing_read = 0;
  const Steinberg::tresult result =
      stream->read(&trailing, 1, &trailing_read);
  return result_ok(result) && trailing_read == 0;
}

}  // namespace

bool save_vst3_state(const PersistentConfig& config,
                     Steinberg::IBStream* stream) noexcept {
  if (stream == nullptr) {
    return false;
  }
  StateImage image{};
  if (!encode_state(config, image)) {
    return false;
  }
  return write_exact(stream, image.data(), image.size());
}

bool load_vst3_state(Steinberg::IBStream* stream,
                     PersistentConfig& output) noexcept {
  if (stream == nullptr) {
    return false;
  }
  StateImage image{};
  if (!read_exact(stream, image.data(), image.size()) || !read_eof(stream)) {
    return false;
  }

  PersistentConfig candidate;
  if (!decode_state(image.data(), image.size(), candidate)) {
    return false;
  }
  output = candidate;
  return true;
}

bool save_vst3_state_with_calibration(
    const PersistentConfig& config, const StringCalibrationBank& calibration,
    Steinberg::IBStream* stream) noexcept {
  if (stream == nullptr) {
    return false;
  }
  StateImage state_image{};
  CalibrationStateImage calibration_image{};
  if (!encode_state(config, state_image) ||
      !encode_calibration_state(calibration, calibration_image)) {
    return false;
  }
  return write_exact(stream, state_image.data(), state_image.size()) &&
         write_exact(stream, calibration_image.data(),
                     calibration_image.size());
}

bool load_vst3_state_with_calibration(
    Steinberg::IBStream* stream, PersistentConfig& config,
    StringCalibrationBank& calibration) noexcept {
  if (stream == nullptr) {
    return false;
  }
  StateImage state_image{};
  if (!read_exact(stream, state_image.data(), state_image.size())) {
    return false;
  }

  std::uint8_t first = 0U;
  Steinberg::int32 first_read = 0;
  const Steinberg::tresult first_result =
      stream->read(&first, 1, &first_read);
  if (!result_ok(first_result) || first_read < 0 || first_read > 1) {
    return false;
  }

  PersistentConfig config_candidate;
  StringCalibrationBank calibration_candidate;
  if (!decode_state(state_image.data(), state_image.size(), config_candidate)) {
    return false;
  }
  if (first_read == 0) {
    config = config_candidate;
    calibration = calibration_candidate;
    return true;
  }

  CalibrationStateImage calibration_image{};
  calibration_image[0] = first;
  if (!read_exact(stream, calibration_image.data() + 1U,
                  calibration_image.size() - 1U) ||
      !read_eof(stream) ||
      !decode_calibration_state(calibration_image.data(),
                                calibration_image.size(),
                                calibration_candidate)) {
    return false;
  }
  config = config_candidate;
  calibration = calibration_candidate;
  return true;
}

}  // namespace m3::vst3
