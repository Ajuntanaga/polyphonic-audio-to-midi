#include "fake_vst3_host.hpp"

#include <algorithm>
#include <cstddef>
#include <cstring>

#include "pluginterfaces/base/funknown.h"

namespace m3::test {

Steinberg::tresult PLUGIN_API FakeVst3Host::queryInterface(
    const Steinberg::TUID requested_iid, void** object) {
  ++query_count_;
  if (object == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  *object = nullptr;
  if (Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                            Steinberg::FUnknown::iid) ||
      Steinberg::FUnknownPrivate::iidEqual(
          requested_iid, Steinberg::Vst::IHostApplication::iid)) {
    *object = static_cast<Steinberg::Vst::IHostApplication*>(this);
    addRef();
    return Steinberg::kResultOk;
  }
  return Steinberg::kNoInterface;
}

Steinberg::uint32 PLUGIN_API FakeVst3Host::addRef() {
  return ++reference_count_;
}

Steinberg::uint32 PLUGIN_API FakeVst3Host::release() {
  if (reference_count_ > 0U) {
    --reference_count_;
  }
  return reference_count_;
}

Steinberg::tresult PLUGIN_API FakeVst3Host::getName(
    Steinberg::Vst::String128 name) {
  if (name == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  constexpr char kName[] = "M3 Fake VST3 Host";
  for (std::size_t index = 0; index < 128U; ++index) {
    name[index] = 0;
  }
  for (std::size_t index = 0; index + 1U < sizeof(kName); ++index) {
    name[index] = static_cast<Steinberg::Vst::TChar>(kName[index]);
  }
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API FakeVst3Host::createInstance(
    Steinberg::TUID, Steinberg::TUID, void** object) {
  if (object != nullptr) {
    *object = nullptr;
  }
  return Steinberg::kNoInterface;
}

void FakeVst3ParamValueQueue::reset(Steinberg::Vst::ParamID id) noexcept {
  id_ = id;
  point_count_ = 0;
  point_count_overridden_ = false;
  point_count_override_ = 0;
  rejected_get_point_ = -1;
  reject_add_point_ = false;
}

bool FakeVst3ParamValueQueue::append_input(
    Steinberg::int32 offset, Steinberg::Vst::ParamValue value) noexcept {
  if (point_count_ >= points_.size()) {
    return false;
  }
  points_[point_count_++] = FakeVst3ParameterPoint{offset, value};
  return true;
}

void FakeVst3ParamValueQueue::override_point_count(
    Steinberg::int32 count) noexcept {
  point_count_overridden_ = true;
  point_count_override_ = count;
}

void FakeVst3ParamValueQueue::clear_point_count_override() noexcept {
  point_count_overridden_ = false;
}

void FakeVst3ParamValueQueue::reject_get_point(
    Steinberg::int32 index) noexcept {
  rejected_get_point_ = index;
}

void FakeVst3ParamValueQueue::reject_add_point(bool reject) noexcept {
  reject_add_point_ = reject;
}

Steinberg::tresult PLUGIN_API FakeVst3ParamValueQueue::queryInterface(
    const Steinberg::TUID requested_iid, void** object) {
  if (object == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  *object = nullptr;
  if (Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                            Steinberg::FUnknown::iid) ||
      Steinberg::FUnknownPrivate::iidEqual(
          requested_iid, Steinberg::Vst::IParamValueQueue::iid)) {
    *object = static_cast<Steinberg::Vst::IParamValueQueue*>(this);
    addRef();
    return Steinberg::kResultOk;
  }
  return Steinberg::kNoInterface;
}

Steinberg::uint32 PLUGIN_API FakeVst3ParamValueQueue::addRef() {
  return ++reference_count_;
}

Steinberg::uint32 PLUGIN_API FakeVst3ParamValueQueue::release() {
  if (reference_count_ > 0U) {
    --reference_count_;
  }
  return reference_count_;
}

Steinberg::Vst::ParamID PLUGIN_API
FakeVst3ParamValueQueue::getParameterId() {
  return id_;
}

Steinberg::int32 PLUGIN_API FakeVst3ParamValueQueue::getPointCount() {
  return point_count_overridden_
             ? point_count_override_
             : static_cast<Steinberg::int32>(point_count_);
}

Steinberg::tresult PLUGIN_API FakeVst3ParamValueQueue::getPoint(
    Steinberg::int32 index, Steinberg::int32& sample_offset,
    Steinberg::Vst::ParamValue& value) {
  if (index == rejected_get_point_ || index < 0 ||
      static_cast<std::size_t>(index) >= point_count_) {
    return Steinberg::kResultFalse;
  }
  sample_offset = points_[static_cast<std::size_t>(index)].offset;
  value = points_[static_cast<std::size_t>(index)].value;
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API FakeVst3ParamValueQueue::addPoint(
    Steinberg::int32 sample_offset, Steinberg::Vst::ParamValue value,
    Steinberg::int32& index) {
  if (reject_add_point_ || point_count_ >= points_.size()) {
    index = -1;
    return Steinberg::kResultFalse;
  }
  index = static_cast<Steinberg::int32>(point_count_);
  points_[point_count_++] = FakeVst3ParameterPoint{sample_offset, value};
  return Steinberg::kResultOk;
}

void FakeVst3ParameterChanges::reset() noexcept {
  queue_count_ = 0;
  parameter_count_overridden_ = false;
  parameter_count_override_ = 0;
  null_queue_index_ = -1;
  reject_add_parameter_ = false;
  reject_output_points_ = false;
}

FakeVst3ParamValueQueue* FakeVst3ParameterChanges::append_queue(
    Steinberg::Vst::ParamID id) noexcept {
  if (queue_count_ >= queues_.size()) {
    return nullptr;
  }
  FakeVst3ParamValueQueue& queue = queues_[queue_count_++];
  queue.reset(id);
  queue.reject_add_point(reject_output_points_);
  return &queue;
}

bool FakeVst3ParameterChanges::append_input(
    Steinberg::Vst::ParamID id, Steinberg::int32 offset,
    Steinberg::Vst::ParamValue value) noexcept {
  FakeVst3ParamValueQueue* queue = nullptr;
  for (std::size_t index = 0; index < queue_count_; ++index) {
    if (queues_[index].getParameterId() == id) {
      queue = &queues_[index];
      break;
    }
  }
  if (queue == nullptr) {
    queue = append_queue(id);
  }
  return queue != nullptr && queue->append_input(offset, value);
}

void FakeVst3ParameterChanges::override_parameter_count(
    Steinberg::int32 count) noexcept {
  parameter_count_overridden_ = true;
  parameter_count_override_ = count;
}

void FakeVst3ParameterChanges::clear_parameter_count_override() noexcept {
  parameter_count_overridden_ = false;
}

void FakeVst3ParameterChanges::return_null_queue(
    Steinberg::int32 index) noexcept {
  null_queue_index_ = index;
}

void FakeVst3ParameterChanges::reject_add_parameter(bool reject) noexcept {
  reject_add_parameter_ = reject;
}

void FakeVst3ParameterChanges::reject_output_points(bool reject) noexcept {
  reject_output_points_ = reject;
  for (std::size_t index = 0; index < queue_count_; ++index) {
    queues_[index].reject_add_point(reject);
  }
}

Steinberg::tresult PLUGIN_API FakeVst3ParameterChanges::queryInterface(
    const Steinberg::TUID requested_iid, void** object) {
  if (object == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  *object = nullptr;
  if (Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                            Steinberg::FUnknown::iid) ||
      Steinberg::FUnknownPrivate::iidEqual(
          requested_iid, Steinberg::Vst::IParameterChanges::iid)) {
    *object = static_cast<Steinberg::Vst::IParameterChanges*>(this);
    addRef();
    return Steinberg::kResultOk;
  }
  return Steinberg::kNoInterface;
}

Steinberg::uint32 PLUGIN_API FakeVst3ParameterChanges::addRef() {
  return ++reference_count_;
}

Steinberg::uint32 PLUGIN_API FakeVst3ParameterChanges::release() {
  if (reference_count_ > 0U) {
    --reference_count_;
  }
  return reference_count_;
}

Steinberg::int32 PLUGIN_API
FakeVst3ParameterChanges::getParameterCount() {
  return parameter_count_overridden_
             ? parameter_count_override_
             : static_cast<Steinberg::int32>(queue_count_);
}

Steinberg::Vst::IParamValueQueue* PLUGIN_API
FakeVst3ParameterChanges::getParameterData(Steinberg::int32 index) {
  if (index == null_queue_index_ || index < 0 ||
      static_cast<std::size_t>(index) >= queue_count_) {
    return nullptr;
  }
  return &queues_[static_cast<std::size_t>(index)];
}

Steinberg::Vst::IParamValueQueue* PLUGIN_API
FakeVst3ParameterChanges::addParameterData(
    const Steinberg::Vst::ParamID& id, Steinberg::int32& index) {
  if (reject_add_parameter_) {
    index = -1;
    return nullptr;
  }
  for (std::size_t queue_index = 0; queue_index < queue_count_;
       ++queue_index) {
    if (queues_[queue_index].getParameterId() == id) {
      index = static_cast<Steinberg::int32>(queue_index);
      queues_[queue_index].reject_add_point(reject_output_points_);
      return &queues_[queue_index];
    }
  }
  FakeVst3ParamValueQueue* queue = append_queue(id);
  if (queue == nullptr) {
    index = -1;
    return nullptr;
  }
  index = static_cast<Steinberg::int32>(queue_count_ - 1U);
  queue->reject_add_point(reject_output_points_);
  return queue;
}

bool FakeVst3Stream::set_input(const std::uint8_t* bytes, std::size_t size,
                               Steinberg::int32 chunk) noexcept {
  if ((bytes == nullptr && size != 0U) || size > bytes_.size() || chunk <= 0) {
    return false;
  }
  bytes_.fill(0U);
  if (size != 0U) {
    std::memcpy(bytes_.data(), bytes, size);
  }
  size_ = size;
  position_ = 0;
  chunk_ = chunk;
  clear_forced_results();
  return true;
}

void FakeVst3Stream::reset_output(Steinberg::int32 chunk) noexcept {
  bytes_.fill(0U);
  size_ = 0;
  position_ = 0;
  chunk_ = chunk > 0 ? chunk : 1;
  clear_forced_results();
}

void FakeVst3Stream::force_read_result(
    Steinberg::tresult result, Steinberg::int32 reported_bytes) noexcept {
  read_forced_ = true;
  forced_read_result_ = result;
  forced_read_bytes_ = reported_bytes;
}

void FakeVst3Stream::force_write_result(
    Steinberg::tresult result, Steinberg::int32 reported_bytes) noexcept {
  write_forced_ = true;
  forced_write_result_ = result;
  forced_write_bytes_ = reported_bytes;
}

void FakeVst3Stream::clear_forced_results() noexcept {
  read_forced_ = false;
  write_forced_ = false;
  forced_read_result_ = Steinberg::kResultOk;
  forced_write_result_ = Steinberg::kResultOk;
  forced_read_bytes_ = 0;
  forced_write_bytes_ = 0;
}

Steinberg::tresult PLUGIN_API FakeVst3Stream::queryInterface(
    const Steinberg::TUID requested_iid, void** object) {
  if (object == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  *object = nullptr;
  if (Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                            Steinberg::FUnknown::iid) ||
      Steinberg::FUnknownPrivate::iidEqual(requested_iid,
                                            Steinberg::IBStream::iid)) {
    *object = static_cast<Steinberg::IBStream*>(this);
    addRef();
    return Steinberg::kResultOk;
  }
  return Steinberg::kNoInterface;
}

Steinberg::uint32 PLUGIN_API FakeVst3Stream::addRef() {
  return ++reference_count_;
}

Steinberg::uint32 PLUGIN_API FakeVst3Stream::release() {
  if (reference_count_ > 0U) {
    --reference_count_;
  }
  return reference_count_;
}

Steinberg::tresult PLUGIN_API FakeVst3Stream::read(
    void* buffer, Steinberg::int32 num_bytes,
    Steinberg::int32* num_bytes_read) {
  if (num_bytes_read != nullptr) {
    *num_bytes_read = 0;
  }
  if (read_forced_) {
    if (num_bytes_read != nullptr) {
      *num_bytes_read = forced_read_bytes_;
    }
    return forced_read_result_;
  }
  if (buffer == nullptr || num_bytes < 0) {
    return Steinberg::kInvalidArgument;
  }
  const std::size_t remaining = size_ - std::min(position_, size_);
  const std::size_t amount = std::min(
      {static_cast<std::size_t>(num_bytes),
       static_cast<std::size_t>(chunk_), remaining});
  if (amount != 0U) {
    std::memcpy(buffer, bytes_.data() + position_, amount);
    position_ += amount;
  }
  if (num_bytes_read != nullptr) {
    *num_bytes_read = static_cast<Steinberg::int32>(amount);
  }
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API FakeVst3Stream::write(
    void* buffer, Steinberg::int32 num_bytes,
    Steinberg::int32* num_bytes_written) {
  if (num_bytes_written != nullptr) {
    *num_bytes_written = 0;
  }
  if (write_forced_) {
    if (num_bytes_written != nullptr) {
      *num_bytes_written = forced_write_bytes_;
    }
    return forced_write_result_;
  }
  if (buffer == nullptr || num_bytes < 0) {
    return Steinberg::kInvalidArgument;
  }
  const std::size_t remaining = bytes_.size() - position_;
  const std::size_t amount = std::min(
      {static_cast<std::size_t>(num_bytes),
       static_cast<std::size_t>(chunk_), remaining});
  if (amount != 0U) {
    std::memcpy(bytes_.data() + position_, buffer, amount);
    position_ += amount;
    size_ = std::max(size_, position_);
  }
  if (num_bytes_written != nullptr) {
    *num_bytes_written = static_cast<Steinberg::int32>(amount);
  }
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API FakeVst3Stream::seek(
    Steinberg::int64 position, Steinberg::int32 mode,
    Steinberg::int64* result) {
  Steinberg::int64 base = 0;
  if (mode == Steinberg::IBStream::kIBSeekCur) {
    base = static_cast<Steinberg::int64>(position_);
  } else if (mode == Steinberg::IBStream::kIBSeekEnd) {
    base = static_cast<Steinberg::int64>(size_);
  } else if (mode != Steinberg::IBStream::kIBSeekSet) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::int64 maximum =
      static_cast<Steinberg::int64>(bytes_.size());
  if (position < -base || position > maximum - base) {
    return Steinberg::kInvalidArgument;
  }
  const Steinberg::int64 target = base + position;
  if (target < 0 || static_cast<std::uint64_t>(target) > bytes_.size()) {
    return Steinberg::kInvalidArgument;
  }
  position_ = static_cast<std::size_t>(target);
  if (result != nullptr) {
    *result = target;
  }
  return Steinberg::kResultOk;
}

Steinberg::tresult PLUGIN_API FakeVst3Stream::tell(
    Steinberg::int64* position) {
  if (position == nullptr) {
    return Steinberg::kInvalidArgument;
  }
  *position = static_cast<Steinberg::int64>(position_);
  return Steinberg::kResultOk;
}

}  // namespace m3::test
