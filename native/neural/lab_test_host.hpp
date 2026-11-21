#pragma once
// Accepting/refusing test host storage, allocated before any process call.
#include "pluginterfaces/vst/ivsthostapplication.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "lab_bridge.hpp"
#include <vector>
namespace m3::neural::test {
class Host final:public Steinberg::Vst::IHostApplication {
 public:
  Steinberg::tresult PLUGIN_API queryInterface(const Steinberg::TUID iid,void** out) override {
    if(!out)return Steinberg::kInvalidArgument;*out=nullptr;
    if(Steinberg::FUnknownPrivate::iidEqual(iid,Steinberg::FUnknown::iid) ||
       Steinberg::FUnknownPrivate::iidEqual(iid,Steinberg::Vst::IHostApplication::iid)) {
      *out=this;addRef();return Steinberg::kResultOk;
    }return Steinberg::kNoInterface;
  }
  Steinberg::uint32 PLUGIN_API addRef() override{return ++refs_;}
  Steinberg::uint32 PLUGIN_API release() override{return --refs_;}
  Steinberg::tresult PLUGIN_API getName(Steinberg::Vst::String128 name) override {
    if(!name)return Steinberg::kInvalidArgument;
    std::fill_n(name,128,0);constexpr char text[]="M3 Neural Lab integration host";
    for(std::size_t i=0;i<sizeof(text);++i)name[i]=text[i];return Steinberg::kResultOk;
  }
  Steinberg::tresult PLUGIN_API createInstance(Steinberg::TUID,Steinberg::TUID,void** out) override {
    if(out)*out=nullptr;return Steinberg::kNoInterface;
  }
 private: Steinberg::uint32 refs_{1};
};
struct Received {
  std::uint64_t emitted_ns{},host_sample{};Steinberg::Vst::Event event{};bool cleanup{};
};
class Events final:public Steinberg::Vst::IEventList {
 public:
  explicit Events(std::size_t capacity):rows(capacity){}
  std::vector<Received> rows;std::size_t count{},attempts{},refused{};
  std::uint64_t origin{},host_sample{};bool cleanup{},reject_off{},reject_all{},overflow{};
  Steinberg::tresult PLUGIN_API queryInterface(const Steinberg::TUID iid,void** out) override {
    if(!out)return Steinberg::kInvalidArgument;*out=nullptr;
    if(Steinberg::FUnknownPrivate::iidEqual(iid,Steinberg::FUnknown::iid) ||
       Steinberg::FUnknownPrivate::iidEqual(iid,Steinberg::Vst::IEventList::iid)) {
      *out=this;addRef();return Steinberg::kResultOk;
    }return Steinberg::kNoInterface;
  }
  Steinberg::uint32 PLUGIN_API addRef() override{return ++refs_;}
  Steinberg::uint32 PLUGIN_API release() override{return --refs_;}
  Steinberg::int32 PLUGIN_API getEventCount() override{return static_cast<Steinberg::int32>(count);}
  Steinberg::tresult PLUGIN_API getEvent(Steinberg::int32 i,Steinberg::Vst::Event& e) override {
    if(i<0 || static_cast<std::size_t>(i)>=count)return Steinberg::kResultFalse;
    e=rows[static_cast<std::size_t>(i)].event;return Steinberg::kResultOk;
  }
  Steinberg::tresult PLUGIN_API addEvent(Steinberg::Vst::Event& e) override {
    ++attempts;
    if(reject_all || (reject_off && e.type==Steinberg::Vst::Event::kNoteOffEvent)) {
      ++refused;return Steinberg::kResultFalse;
    }
    if(count==rows.size()){overflow=true;return Steinberg::kResultFalse;}
    rows[count++]={monotonic_ns()-origin,host_sample,e,cleanup};return Steinberg::kResultOk;
  }
 private: Steinberg::uint32 refs_{1};
};
} // namespace m3::neural::test
