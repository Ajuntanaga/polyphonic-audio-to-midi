// Load the packaged module through official VST3 interfaces, without test hooks.
#include "lab_test_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <type_traits>

namespace {
using namespace Steinberg;
using namespace Steinberg::Vst;
void require(bool pass,const char* message) {if(!pass) throw std::runtime_error(message);}
struct Module {
  void* handle{};bool entered{},initialized{},active{},processing{};
  IPluginFactory* factory{};IComponent* component{};IAudioProcessor* processor{};IEditController* controller{};
  ~Module() {
    if(processing) processor->setProcessing(false);
    if(active) component->setActive(false);
    if(initialized) component->terminate();
    if(controller) controller->release();
    if(processor) processor->release();
    if(component) component->release();
    if(factory) factory->release();
    if(entered) {const auto exit=reinterpret_cast<bool(*)()>(dlsym(handle,"ModuleExit"));if(exit)exit();}
    if(handle) dlclose(handle);
  }
};
template<class Sample> void check_format(Module& m) {
  constexpr int32 format=std::is_same_v<Sample,float>?kSample32:kSample64;
  ProcessSetup setup{kRealtime,format,1024,96000.0};
  require(m.processor->setupProcessing(setup)==kResultOk,"96 kHz setup failed");
  require(m.component->setActive(true)==kResultOk,"bundled model/runtime activation failed");m.active=true;
  require(m.processor->setProcessing(true)==kResultOk,"processing start failed");m.processing=true;
  std::array<Sample,32> left{},right{},out_left{},out_right{};
  for(std::size_t i=0;i<left.size();++i) {left[i]=static_cast<Sample>(i*.001);right[i]=-left[i];}
  Sample* inputs[]{left.data(),right.data()};Sample* outputs[]{out_left.data(),out_right.data()};
  AudioBusBuffers input{},output{};input.numChannels=2;output.numChannels=2;
  if constexpr(std::is_same_v<Sample,float>) {input.channelBuffers32=inputs;output.channelBuffers32=outputs;}
  else {input.channelBuffers64=inputs;output.channelBuffers64=outputs;}
  m3::neural::test::Events events(176);events.origin=m3::neural::monotonic_ns();
  ProcessData data{};data.processMode=kRealtime;data.symbolicSampleSize=format;
  data.numInputs=1;data.numOutputs=1;data.inputs=&input;data.outputs=&output;data.outputEvents=&events;
  require(m.processor->process(data)==kResultOk,"initial zero-sample callback failed");
  data.numSamples=32;
  require(m.processor->process(data)==kResultOk,"packaged process failed");
  require(!std::memcmp(left.data(),out_left.data(),sizeof(left)) &&
          !std::memcmp(right.data(),out_right.data(),sizeof(right)),"packaged dry audio differs");
  require(m.controller->setParamNormalized(0,1)==kResultOk,"Panic parameter failed");
  data.numSamples=0;
  require(m.processor->process(data)==kResultOk,"Panic callback failed");
  require(m.processor->setProcessing(false)==kResultOk,"processing stop failed");m.processing=false;
  require(m.component->setActive(false)==kResultOk,"deactivation failed");m.active=false;
}
}
int main(int argc,char** argv) {
  if(argc!=2) {std::cerr<<"usage: neural_lab_bundle_test module-path\n";return 1;}
  try {
    m3::neural::test::Host host;Module m;
    m.handle=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    if(!m.handle) throw std::runtime_error(dlerror());
    const auto enter=reinterpret_cast<bool(*)(void*)>(dlsym(m.handle,"ModuleEntry"));
    require(enter && enter(m.handle),"ModuleEntry failed");m.entered=true;
    const auto factory_fn=reinterpret_cast<IPluginFactory*(*)()>(dlsym(m.handle,"GetPluginFactory"));
    require(factory_fn!=nullptr,"GetPluginFactory missing");m.factory=factory_fn();
    require(m.factory && m.factory->countClasses()==1,"unexpected factory class count");
    PClassInfo info{};require(m.factory->getClassInfo(0,&info)==kResultOk,"factory class metadata failed");
    const FUID expected(0x4DF13B28,0x9E8349D1,0xB17DA623,0x251F806C);
    require(FUnknownPrivate::iidEqual(info.cid,expected) && !std::strcmp(info.name,"M3 Neural Lab (96 kHz)"),
            "experimental class identity differs");
    require(m.factory->createInstance(info.cid,IComponent::iid,reinterpret_cast<void**>(&m.component))==kResultOk,
            "factory create failed");
    require(m.component->queryInterface(IAudioProcessor::iid,reinterpret_cast<void**>(&m.processor))==kResultOk,
            "audio processor interface missing");
    require(m.component->queryInterface(IEditController::iid,reinterpret_cast<void**>(&m.controller))==kResultOk,
            "single-component controller missing");
    require(m.component->initialize(&host)==kResultOk,"packaged initialize failed");m.initialized=true;
    require(m.controller->getParameterCount()==3,"unexpected parameter count");
    require(m.controller->getParamNormalized(1)==0 && m.controller->getParamNormalized(2)==0.5,
            "quiet gate defaults differ");
    require(m.controller->normalizedParamToPlain(2,.5)==-60. &&
            m.controller->plainParamToNormalized(2,-60.)==.5,"quiet gate units differ");
    require(m.component->getBusCount(kAudio,kInput)==1 && m.component->getBusCount(kAudio,kOutput)==1 &&
            m.component->getBusCount(kEvent,kOutput)==1,"unexpected bus layout");
    ProcessSetup unsupported{kRealtime,kSample32,512,48000.0};
    require(m.processor->setupProcessing(unsupported)!=kResultOk,"unsupported rate accepted");
    check_format<float>(m);check_format<double>(m);
    std::cout<<"Packaged factory, resources, CPU runtime, 96 kHz activation, float32/64 dry process and Panic passed\n";
    return 0;
  } catch(const std::exception& e) {std::cerr<<"bundle failure: "<<e.what()<<'\n';return 1;}
}
