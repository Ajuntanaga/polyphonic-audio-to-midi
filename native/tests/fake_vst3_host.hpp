#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <type_traits>

#include "m3/constants.hpp"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsthostapplication.h"

namespace m3::test {

class FakeVst3Host final : public Steinberg::Vst::IHostApplication {
 public:
  FakeVst3Host() noexcept = default;
  FakeVst3Host(const FakeVst3Host&) = delete;
  FakeVst3Host& operator=(const FakeVst3Host&) = delete;

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::tresult PLUGIN_API getName(
      Steinberg::Vst::String128 name) override;
  Steinberg::tresult PLUGIN_API createInstance(
      Steinberg::TUID class_id, Steinberg::TUID requested_iid,
      void** object) override;

  [[nodiscard]] Steinberg::uint32 reference_count() const noexcept {
    return reference_count_;
  }
  [[nodiscard]] std::uint32_t query_count() const noexcept {
    return query_count_;
  }

 private:
  Steinberg::uint32 reference_count_{1};
  std::uint32_t query_count_{};
};

template <typename Sample>
class FakeVst3ProcessBlock final {
 public:
  FakeVst3ProcessBlock() noexcept { configure(1, false); }

  void configure(std::uint32_t frames, bool in_place) noexcept {
    data_ = {};
    input_bus_ = {};
    output_bus_ = {};
    input_channels_[0] = input_left_.data();
    input_channels_[1] = input_right_.data();
    output_channels_[0] =
        in_place ? input_left_.data() : output_left_.data();
    output_channels_[1] =
        in_place ? input_right_.data() : output_right_.data();
    input_bus_.numChannels = 2;
    output_bus_.numChannels = 2;
    if constexpr (std::is_same_v<Sample, Steinberg::Vst::Sample32>) {
      input_bus_.channelBuffers32 = input_channels_.data();
      output_bus_.channelBuffers32 = output_channels_.data();
      data_.symbolicSampleSize = Steinberg::Vst::kSample32;
    } else {
      input_bus_.channelBuffers64 = input_channels_.data();
      output_bus_.channelBuffers64 = output_channels_.data();
      data_.symbolicSampleSize = Steinberg::Vst::kSample64;
    }
    data_.processMode = Steinberg::Vst::kRealtime;
    data_.numSamples = static_cast<Steinberg::int32>(frames);
    data_.numInputs = 1;
    data_.numOutputs = 1;
    data_.inputs = &input_bus_;
    data_.outputs = &output_bus_;
  }

  void fill_finite() noexcept {
    const std::uint32_t frames =
        data_.numSamples > 0 ? static_cast<std::uint32_t>(data_.numSamples) : 0U;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      input_left_[frame] = expected_input_left(frame);
      input_right_[frame] = expected_input_right(frame);
      output_left_[frame] = static_cast<Sample>(-0.75);
      output_right_[frame] = static_cast<Sample>(0.75);
    }
  }

  void share_input_channels() noexcept {
    input_channels_[1] = input_channels_[0];
  }

  void share_output_channels() noexcept {
    output_channels_[1] = output_channels_[0];
  }

  [[nodiscard]] static Sample expected_input_left(
      std::uint32_t frame) noexcept {
    return static_cast<Sample>(
        (static_cast<double>(frame % 29U) - 14.0) / 29.0);
  }
  [[nodiscard]] static Sample expected_input_right(
      std::uint32_t frame) noexcept {
    return static_cast<Sample>(
        (17.0 - static_cast<double>(frame % 31U)) / 31.0);
  }

  Steinberg::Vst::ProcessData& data() noexcept { return data_; }
  Steinberg::Vst::AudioBusBuffers& input_bus() noexcept { return input_bus_; }
  Steinberg::Vst::AudioBusBuffers& output_bus() noexcept { return output_bus_; }
  Sample*& input_channel(std::size_t index) noexcept {
    return input_channels_[index];
  }
  Sample*& output_channel(std::size_t index) noexcept {
    return output_channels_[index];
  }
  Sample* input_left() noexcept { return input_left_.data(); }
  Sample* input_right() noexcept { return input_right_.data(); }
  Sample* output_left() noexcept { return output_channels_[0]; }
  Sample* output_right() noexcept { return output_channels_[1]; }

 private:
  Steinberg::Vst::ProcessData data_{};
  Steinberg::Vst::AudioBusBuffers input_bus_{};
  Steinberg::Vst::AudioBusBuffers output_bus_{};
  std::array<Sample*, 2> input_channels_{};
  std::array<Sample*, 2> output_channels_{};
  std::array<Sample, m3::kMaxHostFrames> input_left_{};
  std::array<Sample, m3::kMaxHostFrames> input_right_{};
  std::array<Sample, m3::kMaxHostFrames> output_left_{};
  std::array<Sample, m3::kMaxHostFrames> output_right_{};
};

}  // namespace m3::test
