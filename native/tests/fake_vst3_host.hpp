#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <type_traits>

#include "m3/constants.hpp"
#include "pluginterfaces/base/ibstream.h"
#include "public.sdk/source/vst/vstsinglecomponenteffect.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivsthostapplication.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"

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

enum class FakeVst3EditKind : std::uint8_t {
  begin,
  perform,
  end,
};

struct FakeVst3EditCall final {
  FakeVst3EditKind kind{};
  Steinberg::Vst::ParamID id{};
  Steinberg::Vst::ParamValue value{};
};

class FakeVst3ComponentHandler final
    : public Steinberg::Vst::IComponentHandler {
 public:
  static constexpr std::size_t kCapacity = 64;

  FakeVst3ComponentHandler() noexcept = default;
  FakeVst3ComponentHandler(const FakeVst3ComponentHandler&) = delete;
  FakeVst3ComponentHandler& operator=(const FakeVst3ComponentHandler&) = delete;

  void reset() noexcept;
  [[nodiscard]] std::size_t edit_call_count() const noexcept {
    return edit_call_count_;
  }
  [[nodiscard]] const FakeVst3EditCall& edit_call(
      std::size_t index) const noexcept {
    return edit_calls_[index];
  }
  [[nodiscard]] std::uint32_t restart_count() const noexcept {
    return restart_count_;
  }

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::tresult PLUGIN_API beginEdit(
      Steinberg::Vst::ParamID id) override;
  Steinberg::tresult PLUGIN_API performEdit(
      Steinberg::Vst::ParamID id,
      Steinberg::Vst::ParamValue value_normalized) override;
  Steinberg::tresult PLUGIN_API endEdit(
      Steinberg::Vst::ParamID id) override;
  Steinberg::tresult PLUGIN_API restartComponent(
      Steinberg::int32 flags) override;

 private:
  Steinberg::tresult append_edit(FakeVst3EditKind kind,
                                 Steinberg::Vst::ParamID id,
                                 Steinberg::Vst::ParamValue value) noexcept;

  std::array<FakeVst3EditCall, kCapacity> edit_calls_{};
  std::size_t edit_call_count_{};
  Steinberg::uint32 reference_count_{1};
  std::uint32_t restart_count_{};
};

struct FakeVst3ParameterPoint final {
  Steinberg::int32 offset{};
  Steinberg::Vst::ParamValue value{};
};

class FakeVst3ParamValueQueue final
    : public Steinberg::Vst::IParamValueQueue {
 public:
  static constexpr std::size_t kCapacity = 64;

  FakeVst3ParamValueQueue() noexcept = default;
  FakeVst3ParamValueQueue(const FakeVst3ParamValueQueue&) = delete;
  FakeVst3ParamValueQueue& operator=(const FakeVst3ParamValueQueue&) = delete;

  void reset(Steinberg::Vst::ParamID id) noexcept;
  bool append_input(Steinberg::int32 offset,
                    Steinberg::Vst::ParamValue value) noexcept;
  void override_point_count(Steinberg::int32 count) noexcept;
  void clear_point_count_override() noexcept;
  void reject_get_point(Steinberg::int32 index) noexcept;
  void reject_add_point(bool reject) noexcept;

  [[nodiscard]] std::size_t stored_point_count() const noexcept {
    return point_count_;
  }
  [[nodiscard]] const FakeVst3ParameterPoint& stored_point(
      std::size_t index) const noexcept {
    return points_[index];
  }

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::Vst::ParamID PLUGIN_API getParameterId() override;
  Steinberg::int32 PLUGIN_API getPointCount() override;
  Steinberg::tresult PLUGIN_API getPoint(
      Steinberg::int32 index, Steinberg::int32& sample_offset,
      Steinberg::Vst::ParamValue& value) override;
  Steinberg::tresult PLUGIN_API addPoint(
      Steinberg::int32 sample_offset, Steinberg::Vst::ParamValue value,
      Steinberg::int32& index) override;

 private:
  Steinberg::Vst::ParamID id_{};
  std::array<FakeVst3ParameterPoint, kCapacity> points_{};
  std::size_t point_count_{};
  Steinberg::uint32 reference_count_{1};
  bool point_count_overridden_{};
  Steinberg::int32 point_count_override_{};
  Steinberg::int32 rejected_get_point_{-1};
  bool reject_add_point_{};
};

class FakeVst3ParameterChanges final
    : public Steinberg::Vst::IParameterChanges {
 public:
  static constexpr std::size_t kCapacity = 32;

  FakeVst3ParameterChanges() noexcept = default;
  FakeVst3ParameterChanges(const FakeVst3ParameterChanges&) = delete;
  FakeVst3ParameterChanges& operator=(const FakeVst3ParameterChanges&) =
      delete;

  void reset() noexcept;
  FakeVst3ParamValueQueue* append_queue(
      Steinberg::Vst::ParamID id) noexcept;
  bool append_input(Steinberg::Vst::ParamID id, Steinberg::int32 offset,
                    Steinberg::Vst::ParamValue value) noexcept;
  void override_parameter_count(Steinberg::int32 count) noexcept;
  void clear_parameter_count_override() noexcept;
  void return_null_queue(Steinberg::int32 index) noexcept;
  void reject_add_parameter(bool reject) noexcept;
  void reject_output_points(bool reject) noexcept;

  [[nodiscard]] std::size_t stored_queue_count() const noexcept {
    return queue_count_;
  }
  [[nodiscard]] FakeVst3ParamValueQueue* stored_queue(
      std::size_t index) noexcept {
    return index < queue_count_ ? &queues_[index] : nullptr;
  }

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::int32 PLUGIN_API getParameterCount() override;
  Steinberg::Vst::IParamValueQueue* PLUGIN_API getParameterData(
      Steinberg::int32 index) override;
  Steinberg::Vst::IParamValueQueue* PLUGIN_API addParameterData(
      const Steinberg::Vst::ParamID& id, Steinberg::int32& index) override;

 private:
  std::array<FakeVst3ParamValueQueue, kCapacity> queues_{};
  std::size_t queue_count_{};
  Steinberg::uint32 reference_count_{1};
  bool parameter_count_overridden_{};
  Steinberg::int32 parameter_count_override_{};
  Steinberg::int32 null_queue_index_{-1};
  bool reject_add_parameter_{};
  bool reject_output_points_{};
};

class FakeVst3EventList final : public Steinberg::Vst::IEventList {
 public:
  static constexpr std::size_t kCapacity = 4112;

  FakeVst3EventList() noexcept = default;
  FakeVst3EventList(const FakeVst3EventList&) = delete;
  FakeVst3EventList& operator=(const FakeVst3EventList&) = delete;

  void reset() noexcept;
  void reject_attempt(std::size_t attempt) noexcept;

  [[nodiscard]] std::size_t stored_event_count() const noexcept {
    return event_count_;
  }
  [[nodiscard]] std::size_t add_attempt_count() const noexcept {
    return add_attempt_count_;
  }
  [[nodiscard]] std::size_t get_count_call_count() const noexcept {
    return get_count_call_count_;
  }
  [[nodiscard]] std::size_t get_event_call_count() const noexcept {
    return get_event_call_count_;
  }
  [[nodiscard]] const Steinberg::Vst::Event& stored_event(
      std::size_t index) const noexcept {
    return events_[index];
  }

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::int32 PLUGIN_API getEventCount() override;
  Steinberg::tresult PLUGIN_API getEvent(
      Steinberg::int32 index, Steinberg::Vst::Event& event) override;
  Steinberg::tresult PLUGIN_API addEvent(
      Steinberg::Vst::Event& event) override;

 private:
  std::array<Steinberg::Vst::Event, kCapacity> events_{};
  std::size_t event_count_{};
  std::size_t add_attempt_count_{};
  std::size_t rejected_attempt_{std::numeric_limits<std::size_t>::max()};
  std::size_t get_count_call_count_{};
  std::size_t get_event_call_count_{};
  Steinberg::uint32 reference_count_{1};
  bool rejection_used_{};
};

class FakeVst3Stream final : public Steinberg::IBStream {
 public:
  static constexpr std::size_t kCapacity = 512;

  FakeVst3Stream() noexcept = default;
  FakeVst3Stream(const FakeVst3Stream&) = delete;
  FakeVst3Stream& operator=(const FakeVst3Stream&) = delete;

  bool set_input(const std::uint8_t* bytes, std::size_t size,
                 Steinberg::int32 chunk) noexcept;
  void reset_output(Steinberg::int32 chunk) noexcept;
  void force_read_result(Steinberg::tresult result,
                         Steinberg::int32 reported_bytes) noexcept;
  void force_write_result(Steinberg::tresult result,
                          Steinberg::int32 reported_bytes) noexcept;
  void clear_forced_results() noexcept;

  [[nodiscard]] const std::uint8_t* bytes() const noexcept {
    return bytes_.data();
  }
  [[nodiscard]] std::size_t size() const noexcept { return size_; }
  [[nodiscard]] std::size_t position() const noexcept { return position_; }

  Steinberg::tresult PLUGIN_API queryInterface(
      const Steinberg::TUID requested_iid, void** object) override;
  Steinberg::uint32 PLUGIN_API addRef() override;
  Steinberg::uint32 PLUGIN_API release() override;
  Steinberg::tresult PLUGIN_API read(
      void* buffer, Steinberg::int32 num_bytes,
      Steinberg::int32* num_bytes_read) override;
  Steinberg::tresult PLUGIN_API write(
      void* buffer, Steinberg::int32 num_bytes,
      Steinberg::int32* num_bytes_written) override;
  Steinberg::tresult PLUGIN_API seek(
      Steinberg::int64 position, Steinberg::int32 mode,
      Steinberg::int64* result) override;
  Steinberg::tresult PLUGIN_API tell(Steinberg::int64* position) override;

 private:
  std::array<std::uint8_t, kCapacity> bytes_{};
  std::size_t size_{};
  std::size_t position_{};
  Steinberg::int32 chunk_{1};
  Steinberg::uint32 reference_count_{1};
  bool read_forced_{};
  bool write_forced_{};
  Steinberg::tresult forced_read_result_{Steinberg::kResultOk};
  Steinberg::tresult forced_write_result_{Steinberg::kResultOk};
  Steinberg::int32 forced_read_bytes_{};
  Steinberg::int32 forced_write_bytes_{};
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

  void fill_silence() noexcept {
    const std::uint32_t frames =
        data_.numSamples > 0 ? static_cast<std::uint32_t>(data_.numSamples) : 0U;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
      input_left_[frame] = static_cast<Sample>(0);
      input_right_[frame] = static_cast<Sample>(0);
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
