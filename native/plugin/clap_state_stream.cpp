#include "clap_state_stream.hpp"

#include <cstddef>
#include <cstdint>

namespace m3 {

bool save_clap_state(const PersistentConfig& config,
                     const clap_ostream_t* stream) noexcept {
  if (stream == nullptr || stream->write == nullptr) {
    return false;
  }
  StateImage image{};
  if (!encode_state(config, image)) {
    return false;
  }
  std::size_t position = 0;
  while (position < image.size()) {
    const std::uint64_t remaining = image.size() - position;
    const std::int64_t written =
        stream->write(stream, image.data() + position, remaining);
    if (written <= 0 || static_cast<std::uint64_t>(written) > remaining) {
      return false;
    }
    position += static_cast<std::size_t>(written);
  }
  return true;
}

bool load_clap_state(const clap_istream_t* stream,
                     PersistentConfig& output) noexcept {
  if (stream == nullptr || stream->read == nullptr) {
    return false;
  }
  StateImage image{};
  std::size_t position = 0;
  while (position < image.size()) {
    const std::uint64_t remaining = image.size() - position;
    const std::int64_t read =
        stream->read(stream, image.data() + position, remaining);
    if (read <= 0 || static_cast<std::uint64_t>(read) > remaining) {
      return false;
    }
    position += static_cast<std::size_t>(read);
  }
  std::uint8_t trailing = 0;
  if (stream->read(stream, &trailing, 1) != 0) {
    return false;
  }
  PersistentConfig candidate;
  if (!decode_state(image.data(), image.size(), candidate)) {
    return false;
  }
  output = candidate;
  return true;
}

}  // namespace m3
