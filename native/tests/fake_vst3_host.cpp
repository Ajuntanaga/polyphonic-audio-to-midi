#include "fake_vst3_host.hpp"

#include <cstddef>

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

}  // namespace m3::test
