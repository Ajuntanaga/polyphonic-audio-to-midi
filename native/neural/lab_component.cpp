#include "lab_component.hpp"
#include "../vst3/vst3_event_sink.hpp"
#include "pluginterfaces/base/fstrdefs.h"
#include "pluginterfaces/base/ibstream.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "pluginterfaces/vst/vstspeaker.h"
#include <dlfcn.h>
#include <filesystem>
#include <new>
#include <type_traits>

namespace m3::neural {
using namespace Steinberg;
using namespace Steinberg::Vst;
namespace {
void module_anchor(){}
std::filesystem::path resource_directory() {
  Dl_info info{};
  if(!dladdr(reinterpret_cast<const void*>(&module_anchor),&info) || !info.dli_fname)
    throw std::runtime_error("module resource directory unavailable");
  return std::filesystem::path(info.dli_fname).parent_path().parent_path()/"Resources";
}
constexpr std::array<char,8> old_state_tag{'M','3','N','L','0','0','0','1'};
constexpr std::array<char,8> state_tag{'M','3','N','L','0','0','0','2'};
static_assert(std::atomic<std::uint32_t>::is_always_lock_free);
}
LabComponent::~LabComponent(){stop_worker();}
FUnknown* LabComponent::createInstance(void*) {
  return static_cast<IAudioProcessor*>(new(std::nothrow) LabComponent);
}
tresult PLUGIN_API LabComponent::initialize(FUnknown* context) {
  const auto result=SingleComponentEffect::initialize(context);if(result!=kResultOk) return result;
  addAudioInput(STR16("Dry input"),SpeakerArr::kStereo);
  addAudioOutput(STR16("Dry output"),SpeakerArr::kStereo);
  addEventOutput(STR16("Experimental pitch MIDI"),1);
  parameters.addParameter(STR16("Panic"),nullptr,1,0,ParameterInfo::kCanAutomate,0);
  parameters.addParameter(STR16("Quiet input gate"),nullptr,1,0,ParameterInfo::kCanAutomate,1);
  parameters.addParameter(new RangeParameter(STR16("Gate threshold"),2,STR16("dBFS"),
      -90.0,-30.0,-60.0,600,ParameterInfo::kCanAutomate));
  return kResultOk;
}
void LabComponent::stop_worker() noexcept {
  if(worker_) worker_->stop();
  bridge_.detach();worker_.reset();active_=false;processing_=false;
}
tresult PLUGIN_API LabComponent::terminate() {stop_worker();return SingleComponentEffect::terminate();}
tresult PLUGIN_API LabComponent::setBusArrangements(SpeakerArrangement* inputs,int32 ni,SpeakerArrangement* outputs,int32 no) {
  if(active_ || ni!=1 || no!=1 || !inputs || !outputs || inputs[0]!=outputs[0] ||
      (inputs[0]!=SpeakerArr::kMono && inputs[0]!=SpeakerArr::kStereo)) return kResultFalse;
  const auto result=SingleComponentEffect::setBusArrangements(inputs,ni,outputs,no);
  if(result==kResultOk) channels_=inputs[0]==SpeakerArr::kMono?1:2;
  return result;
}
tresult PLUGIN_API LabComponent::canProcessSampleSize(int32 size) {
  return size==kSample32 || size==kSample64?kResultTrue:kResultFalse;
}
tresult PLUGIN_API LabComponent::setupProcessing(ProcessSetup& setup) {
  if(active_ || setup.sampleRate!=96000.0 || setup.maxSamplesPerBlock<1 || setup.maxSamplesPerBlock>1024 ||
      canProcessSampleSize(setup.symbolicSampleSize)!=kResultTrue || setup.processMode!=kRealtime)
    return kResultFalse;
  const auto result=SingleComponentEffect::setupProcessing(setup);
  if(result==kResultOk) {format_=setup.symbolicSampleSize;max_block_=setup.maxSamplesPerBlock;configured_=true;}
  return result;
}
tresult PLUGIN_API LabComponent::setActive(TBool state) {
  if(state!=0 && state!=1) return kInvalidArgument;
  if(!state) {stop_worker();return SingleComponentEffect::setActive(state);}
  if(active_) return kResultOk;
  if(!configured_) return kResultFalse;
  try {
    if(model_path_.empty()) {const auto dir=resource_directory();model_path_=(dir/"nmp.onnx").string();filter_path_=(dir/"coefficients.f64").string();}
    worker_=std::make_unique<Worker>(model_path_,filter_path_,evidence_);
    bridge_.attach(&worker_->exchange());active_=true;
  } catch(...) {stop_worker();return kResultFalse;}
  return SingleComponentEffect::setActive(state);
}
tresult PLUGIN_API LabComponent::setProcessing(TBool state) {
  if((state!=0 && state!=1) || (state && !active_)) return kResultFalse;
  if(!state) bridge_.reset(false);
  processing_=state!=0;return kResultOk;
}
bool LabComponent::apply_gate_parameter(ParamID id,ParamValue value) noexcept {
  if(!std::isfinite(value) || value<0 || value>1) return false;
  if(id==1) gate_enabled_.store(value>=0.5,std::memory_order_relaxed);
  else if(id==2) gate_threshold_.store(static_cast<std::uint32_t>(std::lround(value*600)),std::memory_order_relaxed);
  else return false;
  return true;
}
tresult PLUGIN_API LabComponent::setParamNormalized(ParamID id,ParamValue value) {
  if(!std::isfinite(value) || value<0 || value>1) return kInvalidArgument;
  if(id==0) {
    if(value>=0.5) panic_.store(true,std::memory_order_release);
    return SingleComponentEffect::setParamNormalized(id,0.0);
  }
  if(!apply_gate_parameter(id,value)) return kInvalidArgument;
  return SingleComponentEffect::setParamNormalized(id,id==1?(value>=0.5?1.0:0.0):std::round(value*600)/600);
}
tresult PLUGIN_API LabComponent::getState(IBStream* stream) {
  std::array<unsigned char,12> bytes{};std::copy(state_tag.begin(),state_tag.end(),bytes.begin());
  const auto settings=gate_settings();
  for(unsigned i=0;i<4;++i) bytes[8+i]=static_cast<unsigned char>(settings>>(i*8));
  int32 n=0;return stream && stream->write(bytes.data(),bytes.size(),&n)==kResultOk &&
      n==static_cast<int32>(bytes.size())?kResultOk:kResultFalse;
}
tresult PLUGIN_API LabComponent::setState(IBStream* stream) {
  std::array<char,8> tag{};int32 n=0;
  if(!stream || stream->read(tag.data(),tag.size(),&n)!=kResultOk || n!=static_cast<int32>(tag.size()))
    return kResultFalse;
  std::uint32_t settings=kGateDefault;
  if(tag==state_tag) {
    std::array<unsigned char,4> bytes{};
    if(stream->read(bytes.data(),bytes.size(),&n)!=kResultOk || n!=4) return kResultFalse;
    settings=0;for(unsigned i=0;i<4;++i) settings|=static_cast<std::uint32_t>(bytes[i])<<(i*8);
    if(!valid_gate_settings(settings)) return kResultFalse;
  } else if(tag!=old_state_tag) return kResultFalse;
  gate_enabled_.store((settings&kGateEnabled)!=0,std::memory_order_relaxed);
  gate_threshold_.store(settings&~kGateEnabled,std::memory_order_relaxed);
  SingleComponentEffect::setParamNormalized(1,(settings&kGateEnabled)?1.0:0.0);
  SingleComponentEffect::setParamNormalized(2,static_cast<double>(settings&~kGateEnabled)/600);
  panic_.store(true,std::memory_order_release);return kResultOk;
}
tresult PLUGIN_API LabComponent::process(ProcessData& data) {
  if(data.numSamples<0 || data.numSamples>max_block_ || data.symbolicSampleSize!=format_ || data.processMode!=kRealtime)
    {bridge_.fault();return kInvalidArgument;}
  bool panic=panic_.exchange(false,std::memory_order_acq_rel);
  if(data.inputParameterChanges) for(int32 i=0;i<data.inputParameterChanges->getParameterCount();++i) {
    auto* q=data.inputParameterChanges->getParameterData(i);
    if(q && q->getPointCount()>0) {
      int32 offset=0;ParamValue value=0;
      if(q->getPoint(q->getPointCount()-1,offset,value)==kResultOk && std::isfinite(value) && value>=0 && value<=1) {
        if(q->getParameterId()==0 && value>=0.5) panic=true;
        else apply_gate_parameter(q->getParameterId(),value);
      }
    }
  }
  bridge_.set_gate_settings(gate_settings());
  if(panic) bridge_.reset(true);
  if(data.numSamples && (data.numInputs!=1 || data.numOutputs!=1 || !data.inputs || !data.outputs ||
      data.inputs[0].numChannels!=channels_ || data.outputs[0].numChannels!=channels_))
    {bridge_.fault();return kInvalidArgument;}
  return format_==kSample32?process_audio<float>(data):process_audio<double>(data);
}
template<class Sample> tresult LabComponent::process_audio(ProcessData& data) {
  Sample** input=nullptr;Sample** output=nullptr;
  if(data.numSamples) {
    if constexpr(std::is_same_v<Sample,float>) {input=data.inputs[0].channelBuffers32;output=data.outputs[0].channelBuffers32;}
    else {input=data.inputs[0].channelBuffers64;output=data.outputs[0].channelBuffers64;}
    if(!input || !output) {bridge_.fault();return kInvalidArgument;}
    for(int32 c=0;c<channels_;++c) if(!input[c] || !output[c]) {bridge_.fault();return kInvalidArgument;}
    for(int32 i=0;i<data.numSamples;++i) {
      const Sample left=input[0][i],right=channels_==2?input[1][i]:left;
      mono_[static_cast<std::size_t>(i)]=static_cast<float>(channels_==2?(static_cast<double>(left)+static_cast<double>(right))*0.5:left);
      output[0][i]=left;if(channels_==2) output[1][i]=right;
    }
    data.outputs[0].silenceFlags=data.inputs[0].silenceFlags;
  }
  m3::vst3::Vst3EventSinkContext context{data.outputEvents};
  const auto sink=[&](const Event& e,std::uint64_t,std::uint64_t,bool) noexcept {
    VoiceTransition transition{};transition.note=static_cast<std::uint8_t>(e.note);
    transition.kind=e.on?TransitionKind::note_on:TransitionKind::note_off;
    transition.velocity=e.on?100:0;
    return m3::vst3::push_vst3_note(&context,transition,1);
  };
  bridge_.render(sink);
  if(active_ && processing_ && data.numSamples && bridge_.ready() &&
      !bridge_.feed(mono_.data(),static_cast<std::size_t>(data.numSamples)))
    bridge_.render(sink); // A new input fault releases accepted owners in this callback.
  return kResultOk;
}
} // namespace m3::neural
