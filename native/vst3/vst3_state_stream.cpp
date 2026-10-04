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

bool read_bounded_to_eof(Steinberg::IBStream* stream, std::uint8_t* bytes,
                         std::size_t capacity, std::size_t& size) noexcept {
  size = 0U;
  while (size < capacity) {
    const auto request = static_cast<Steinberg::int32>(capacity - size);
    Steinberg::int32 read = 0;
    const Steinberg::tresult result =
        stream->read(bytes + size, request, &read);
    if (!result_ok(result) || read < 0 || read > request) {
      return false;
    }
    if (read == 0) {
      return true;
    }
    size += static_cast<std::size_t>(read);
  }
  return read_eof(stream);
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

  PersistentConfig config_candidate;
  StringCalibrationBank calibration_candidate;
  if (!decode_state(state_image.data(), state_image.size(), config_candidate)) {
    return false;
  }
  CalibrationStateImage calibration_image{};
  std::size_t calibration_size = 0U;
  if (!read_bounded_to_eof(stream, calibration_image.data(),
                           calibration_image.size(), calibration_size)) {
    return false;
  }
  if (calibration_size == 0U) {
    config = config_candidate;
    calibration = calibration_candidate;
    return true;
  }
  if (!decode_calibration_state(calibration_image.data(), calibration_size,
                                calibration_candidate)) {
    return false;
  }
  config = config_candidate;
  calibration = calibration_candidate;
  return true;
}

}  // namespace m3::vst3
