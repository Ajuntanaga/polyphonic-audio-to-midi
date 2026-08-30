#include "vst3_state_stream.hpp"

#include <cstddef>
#include <cstdint>

namespace m3::vst3 {
namespace {

bool result_ok(Steinberg::tresult result) noexcept {
  return result == Steinberg::kResultOk || result == Steinberg::kResultTrue;
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
  std::size_t position = 0;
  while (position < image.size()) {
    const std::size_t remaining = image.size() - position;
    const auto request = static_cast<Steinberg::int32>(remaining);
    Steinberg::int32 written = 0;
    const Steinberg::tresult result = stream->write(
        static_cast<void*>(image.data() + position), request, &written);
    if (!result_ok(result) || written <= 0 || written > request) {
      return false;
    }
    position += static_cast<std::size_t>(written);
  }
  return true;
}

bool load_vst3_state(Steinberg::IBStream* stream,
                     PersistentConfig& output) noexcept {
  if (stream == nullptr) {
    return false;
  }
  StateImage image{};
  std::size_t position = 0;
  while (position < image.size()) {
    const std::size_t remaining = image.size() - position;
    const auto request = static_cast<Steinberg::int32>(remaining);
    Steinberg::int32 read = 0;
    const Steinberg::tresult result =
        stream->read(image.data() + position, request, &read);
    if (!result_ok(result) || read <= 0 || read > request) {
      return false;
    }
    position += static_cast<std::size_t>(read);
  }

  std::uint8_t trailing = 0;
  Steinberg::int32 trailing_read = 0;
  const Steinberg::tresult trailing_result =
      stream->read(&trailing, 1, &trailing_read);
  if (!result_ok(trailing_result) || trailing_read != 0) {
    return false;
  }

  PersistentConfig candidate;
  if (!decode_state(image.data(), image.size(), candidate)) {
    return false;
  }
  output = candidate;
  return true;
}

}  // namespace m3::vst3
