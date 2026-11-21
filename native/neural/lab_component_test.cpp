#include "lab_component.hpp"
#include "lab_test_host.hpp"
#include "allocation_guard.hpp"
#include "pluginterfaces/vst/vstspeaker.h"
#include "public.sdk/source/common/memorystream.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include <cstring>
#include <iostream>
#include <limits>
using namespace m3::neural;
using namespace Steinberg;
using namespace Steinberg::Vst;
namespace {
void require(bool v,const char* why){if(!v)throw std::runtime_error(why);}
void call(LabComponent& c,ProcessData& d) {
  begin_callback_allocations();const auto result=c.process(d);const auto a=end_callback_allocations();
  require(result==kResultOk,"component process failed");
  require(!a.allocations && !a.deallocations,"component callback allocated or freed");
}
struct Fixture {
  test::Host host;test::Events events{4096};LabComponent component;Exchange exchange;ProcessData data{};
  Fixture(int format=kSample32,int channels=1) {
    require(component.initialize(&host)==kResultOk,"initialize");
    SpeakerArrangement arrangement=channels==1?SpeakerArr::kMono:SpeakerArr::kStereo;
    require(component.setBusArrangements(&arrangement,1,&arrangement,1)==kResultOk,"arrangements");
    ProcessSetup setup{};setup.processMode=kRealtime;setup.sampleRate=96000;
    setup.maxSamplesPerBlock=1024;setup.symbolicSampleSize=format;
    require(component.setupProcessing(setup)==kResultOk,"setup");
    component.attach_test_exchange(exchange);
    data.symbolicSampleSize=format;data.processMode=kRealtime;data.outputEvents=&events;
    call(component,data);
  }
  ~Fixture(){component.setActive(false);component.terminate();}
  void batch(std::initializer_list<m3::neural::Event> events,std::uint64_t epoch=0) {
    EpochBatch b;b.epoch=epoch?epoch:component.diagnostic_bridge().epoch();
    for(const auto& e:events)b.batch.add(e);
    require(exchange.output.push(b),"test queue push");
  }
};
void ownership_and_epoch() {
  Fixture f;f.batch({{0,60,true},{0,64,true}});call(f.component,f.data);
  require(f.events.count==2 && f.component.diagnostic_bridge().active_count()==2,"accepted owners");
  f.events.reject_off=true;f.batch({{1,60,false},{1,67,true}});call(f.component,f.data);
  require(f.events.count==2 && f.component.diagnostic_bridge().blocked(),"refused off blocks later on");
  require(f.component.diagnostic_bridge().active_count()==2,"refusal retains both owners");
  const auto old=f.component.diagnostic_bridge().epoch();
  require(f.component.setParamNormalized(0,1)==kResultOk,"Panic parameter");call(f.component,f.data);
  const auto fresh=f.component.diagnostic_bridge().epoch();require(fresh>old,"Panic advances epoch");
  f.exchange.acknowledged.store(fresh);f.batch({{2,69,true}},old);f.batch({{0,71,true}},fresh);
  call(f.component,f.data);require(f.events.count==2,"no new owner before accepted cleanup");
  f.events.reject_off=false;call(f.component,f.data);
  require(f.events.count==4 && f.component.diagnostic_bridge().active_count()==0,"cleanup exactly once per owner");
  f.batch({{3,73,true}},old);f.batch({{1,72,true}},fresh);call(f.component,f.data);
  require(f.events.count==5 && f.events.rows[4].event.noteOn.pitch==72,"stale generation discarded");
  f.events.reject_off=true;f.component.setProcessing(false);call(f.component,f.data);
  require(f.component.diagnostic_bridge().active_count()==1,"stop preserves refused owner");
  f.component.setActive(false);Exchange replacement;f.component.attach_test_exchange(replacement);
  call(f.component,f.data);require(f.component.diagnostic_bridge().active_count()==1,"reactivation retains owner");
  f.events.reject_off=false;call(f.component,f.data);
  require(f.component.diagnostic_bridge().active_count()==0 && f.events.count==6,"reactivated cleanup releases once");
  call(f.component,f.data);require(f.events.count==6,"quiet cleanup does not repeat");
  f.component.setActive(false); // before replacement is destroyed
}
void full_pitch_and_faults() {
  Fixture f;EpochBatch b;b.epoch=f.component.diagnostic_bridge().epoch();
  for(std::uint16_t n=21;n<=108;++n)b.batch.add({0,n,true});
  require(f.exchange.output.push(b),"88 pitch batch");call(f.component,f.data);
  require(f.events.count==88 && f.component.diagnostic_bridge().active_count()==88,"88 pitch owners");
  for(std::size_t i=0;i<88;++i) {
    const auto& e=f.events.rows[i].event;
    require(e.type==Steinberg::Vst::Event::kNoteOnEvent && e.noteOn.pitch==21+static_cast<int>(i) &&
      e.noteOn.noteId==-1000-e.noteOn.pitch && e.sampleOffset==0 && e.noteOn.channel==0,"stable pitch ID and offset");
  }
  f.exchange.fatal.store(true);call(f.component,f.data);
  require(f.events.count==176 && f.component.diagnostic_bridge().active_count()==0,"worker fault cleans every owner");
  f.component.setParamNormalized(0,1);call(f.component,f.data);
  require(f.component.diagnostic_bridge().blocked(),"Panic cannot hide terminal worker fault");
}
template<class Sample> void audio_test(int format,int channels) {
  Fixture f(format,channels);std::array<Sample,1024> left{},right{},outl{},outr{};
  for(std::size_t i=0;i<left.size();++i){left[i]=static_cast<Sample>(i*.0001);right[i]=-left[i]*Sample(.5);}
  Sample* inputs[]{left.data(),right.data()};Sample* outputs[]{outl.data(),outr.data()};
  AudioBusBuffers in{},out{};in.numChannels=out.numChannels=channels;
  if constexpr(std::is_same_v<Sample,float>){in.channelBuffers32=inputs;out.channelBuffers32=outputs;}
  else {in.channelBuffers64=inputs;out.channelBuffers64=outputs;}
  f.data.numInputs=f.data.numOutputs=1;f.data.inputs=&in;f.data.outputs=&out;
  for(int count:{32,512,1024}) {
    f.data.numSamples=count;call(f.component,f.data);
    require(std::memcmp(left.data(),outl.data(),count*sizeof(Sample))==0,"dry first channel identity");
    if(channels==2)require(std::memcmp(right.data(),outr.data(),count*sizeof(Sample))==0,"dry second channel identity");
  }
  require(f.component.diagnostic_bridge().source_samples()==1568,"variable block source continuity");
  const auto* packet=f.exchange.input.front();require(packet && packet->input.end==640,"packetized source clock");
  const float expected=channels==2?static_cast<float>((double(left[0])+double(right[0]))*.5):static_cast<float>(left[0]);
  require(packet->input.data[0]==expected,"mono mix");
  // No consumer: a finite full queue must stop, preserve dry audio, and clean owners.
  f.batch({{0,60,true}});f.data.numSamples=1024;
  for(int i=0;i<12;++i)call(f.component,f.data);
  require(f.component.diagnostic_bridge().blocked() && f.component.diagnostic_bridge().input_drops()==1,"input overflow blocks");
  require(f.component.diagnostic_bridge().active_count()==0,"overflow cleanup");
}
void unsupported_and_nonfinite() {
  Fixture f;f.component.setActive(false);ProcessSetup setup{};setup.sampleRate=48000;setup.maxSamplesPerBlock=512;
  require(f.component.setupProcessing(setup)==kResultFalse,"unsupported clock rejected");
  f.component.attach_test_exchange(f.exchange);call(f.component,f.data);
  std::array<float,1> input{std::numeric_limits<float>::quiet_NaN()},out{};float* ip=input.data();float* op=out.data();
  AudioBusBuffers in{},output{};in.numChannels=output.numChannels=1;in.channelBuffers32=&ip;output.channelBuffers32=&op;
  f.data.numSamples=1;f.data.numInputs=f.data.numOutputs=1;f.data.inputs=&in;f.data.outputs=&output;
  call(f.component,f.data);require(f.component.diagnostic_bridge().blocked(),"nonfinite input blocks detector");
  require(std::memcmp(input.data(),out.data(),sizeof(float))==0,"dry path preserves input bits");
}
std::array<unsigned char,12> saved_state(LabComponent& component) {
  MemoryStream stream;require(component.getState(&stream)==kResultOk && stream.getSize()==12,"state write");
  std::array<unsigned char,12> bytes{};std::memcpy(bytes.data(),stream.getData(),bytes.size());return bytes;
}
void gate_state_test() {
  Fixture f;
  require(f.component.getParameterCount()==3 && f.component.getParamNormalized(1)==0 &&
      f.component.getParamNormalized(2)==.5,"gate defaults");
  for(double normalized:{0.,.5,.75,1.}) {
    const double dbfs=-90.+60.*normalized;
    require(f.component.normalizedParamToPlain(2,normalized)==dbfs &&
        f.component.plainParamToNormalized(2,dbfs)==normalized,"gate dBFS mapping");
  }
  String128 display{};ParamValue parsed{};
  require(f.component.getParamStringByValue(2,301./600.,display)==kResultOk &&
      f.component.getParamValueByString(2,display,parsed)==kResultOk &&
      std::abs(parsed-301./600.)<1e-12,"gate tenth-decibel display roundtrip");
  require(f.component.setParamNormalized(1,1)==kResultOk && f.component.setParamNormalized(2,.75)==kResultOk,"gate UI controls");
  const auto original=saved_state(f.component);
  require(original[8]==194 && original[9]==1 && original[10]==0 && original[11]==128,"little endian gate state");
  f.component.setParamNormalized(1,0);f.component.setParamNormalized(2,0);
  MemoryStream roundtrip(const_cast<unsigned char*>(original.data()),original.size());
  require(f.component.setState(&roundtrip)==kResultOk && saved_state(f.component)==original &&
      f.component.getParamNormalized(1)==1 && f.component.getParamNormalized(2)==.75,"gate state roundtrip");
  auto invalid=original;invalid[10]=1;
  MemoryStream bad(invalid.data(),invalid.size());
  require(f.component.setState(&bad)==kResultFalse && saved_state(f.component)==original,"invalid bits leave state unchanged");
  MemoryStream short_state(invalid.data(),10);
  require(f.component.setState(&short_state)==kResultFalse && saved_state(f.component)==original,"truncated state leaves settings unchanged");
  for(double value:{-1.,2.,std::numeric_limits<double>::quiet_NaN()})
    require(f.component.setParamNormalized(2,value)==kInvalidArgument && saved_state(f.component)==original,"invalid parameter ignored");
  char legacy[]{'M','3','N','L','0','0','0','1'};MemoryStream old(legacy,sizeof legacy);
  require(f.component.setState(&old)==kResultOk && f.component.getParamNormalized(1)==0 &&
      f.component.getParamNormalized(2)==.5,"legacy preset remains gate off");
}
template<class Sample> void gate_automation_test(int format) {
  Fixture f(format);std::array<Sample,640> input{},output{};input.fill(Sample(.01));
  Sample* ip=input.data();Sample* op=output.data();AudioBusBuffers in{},out{};
  in.numChannels=out.numChannels=1;
  if constexpr(std::is_same_v<Sample,float>) {in.channelBuffers32=&ip;out.channelBuffers32=&op;}
  else {in.channelBuffers64=&ip;out.channelBuffers64=&op;}
  f.data.numInputs=f.data.numOutputs=1;f.data.inputs=&in;f.data.outputs=&out;f.data.numSamples=32;
  call(f.component,f.data); // This partial packet belongs to the old settings.
  ParameterChanges changes(2);int32 index=0;
  auto* enabled=changes.addParameterData(1,index);require(enabled!=nullptr,"enable queue");
  enabled->addPoint(0,1,index);
  auto* threshold=changes.addParameterData(2,index);require(threshold!=nullptr,"threshold queue");
  threshold->addPoint(0,0,index);threshold->addPoint(0,.75,index);
  f.data.inputParameterChanges=&changes;f.data.numSamples=608;call(f.component,f.data);
  auto* packet=f.exchange.input.front();
  require(packet && packet->gate_settings==kGateDefault && packet->input.end==640,"partial packet retains old settings");
  f.exchange.input.pop();f.data.inputParameterChanges=nullptr;f.data.numSamples=640;call(f.component,f.data);
  packet=f.exchange.input.front();
  require(packet && packet->gate_settings==(kGateEnabled|450U) && packet->input.end==1280,"automation reaches next packet");
  require(std::memcmp(input.data(),output.data(),sizeof input)==0,"gate automation preserves dry audio");
  const auto state=saved_state(f.component);
  require(state[8]==194 && state[9]==1 && state[11]==128,"automated values saved");
}
}
int main(){try{
  ownership_and_epoch();full_pitch_and_faults();
  audio_test<float>(kSample32,1);audio_test<float>(kSample32,2);
  audio_test<double>(kSample64,1);audio_test<double>(kSample64,2);unsupported_and_nonfinite();
  gate_state_test();gate_automation_test<float>(kSample32);gate_automation_test<double>(kSample64);
  std::cout<<"neural component ownership, epoch, overflow, dry and callback allocation tests passed\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
