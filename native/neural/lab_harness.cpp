// Paced recorded waveform through the actual experimental VST3 component.
// No labels enter this process. Evidence is read after the worker is joined.
#include "lab_component.hpp"
#include "lab_test_host.hpp"
#include "allocation_guard.hpp"
#include "pluginterfaces/vst/vstspeaker.h"
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <thread>
#include <type_traits>

using namespace m3::neural;
namespace {
using Clock=std::chrono::steady_clock;
struct CallbackTime {
  std::uint64_t source_end{},samples{},started_ns{},duration_ns{},late_ns{},allocations{},frees{};
};
std::vector<float> read_audio(const std::string& path) {
  std::ifstream file(path,std::ios::binary|std::ios::ate);
  if(!file || file.tellg()<=0 || static_cast<std::uint64_t>(file.tellg())%sizeof(float))
    throw std::runtime_error("invalid mono float input");
  std::vector<float> result(static_cast<std::size_t>(file.tellg())/sizeof(float));
  file.seekg(0);file.read(reinterpret_cast<char*>(result.data()),result.size()*sizeof(float));
  if(!file || !std::all_of(result.begin(),result.end(),[](float x){return std::isfinite(x);}))
    throw std::runtime_error("invalid finite input");
  return result;
}
std::string quote(const std::string& s) {
  std::string r="\"";
  for(unsigned char c:s) {
    if(c=='"' || c=='\\') {r+='\\';r+=static_cast<char>(c);}
    else if(c=='\n') r+="\\n";
    else if(c>=32) r+=static_cast<char>(c);
  }
  return r+'"';
}
void require(Steinberg::tresult r,const char* message) {
  if(r!=Steinberg::kResultOk) throw std::runtime_error(message);
}
template<class Sample> int run(const char* audio,const char* coefficients,const char* model,const char* output,
                              bool gate_enabled,double gate_db) {
  if(!std::getenv("GITHUB_ACTIONS") || std::string(std::getenv("GITHUB_ACTIONS"))!="true")
    throw std::runtime_error("recorded component measurement requires GitHub Actions");
  using namespace Steinberg;using namespace Steinberg::Vst;
  const auto f32=read_audio(audio);
  const std::vector<Sample> source(f32.begin(),f32.end());
  LabEvidence evidence;evidence.generated.reserve(32768);evidence.timing.reserve(ceil_div(source.size(),640));
  evidence.gate.reserve(ceil_div(source.size(),2000));
  test::Host host;test::Events events(100000);
  LabComponent component;
  require(component.initialize(&host),"initialize failed");
  require(component.setParamNormalized(2,(gate_db+90)/60),"gate threshold failed");
  require(component.setParamNormalized(1,gate_enabled?1:0),"gate enable failed");
  SpeakerArrangement arrangement=SpeakerArr::kMono;
  require(component.setBusArrangements(&arrangement,1,&arrangement,1),"mono arrangement failed");
  constexpr int32 format=std::is_same_v<Sample,float>?kSample32:kSample64;
  ProcessSetup setup{kRealtime,format,1024,96000.0};
  require(component.setupProcessing(setup),"setup failed");
  component.configure_test_resources(model,coefficients,&evidence);
  require(component.setActive(true),"worker activation failed");
  require(component.setProcessing(true),"processing activation failed");
  std::array<Sample,1024> dry{};Sample* input_ptr=nullptr;Sample* output_ptr=dry.data();
  AudioBusBuffers in{},out{};in.numChannels=1;out.numChannels=1;
  if constexpr(std::is_same_v<Sample,float>) {in.channelBuffers32=&input_ptr;out.channelBuffers32=&output_ptr;}
  else {in.channelBuffers64=&input_ptr;out.channelBuffers64=&output_ptr;}
  ProcessData data{};data.processMode=kRealtime;data.symbolicSampleSize=format;
  data.numInputs=1;data.numOutputs=1;data.inputs=&in;data.outputs=&out;data.outputEvents=&events;
  std::vector<CallbackTime> timing(ceil_div(source.size(),32)+400);
  std::size_t calls=0;bool dry_identical=true,process_ok=true,log_ok=true;
  const auto start=Clock::now();
  const auto origin=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(start.time_since_epoch()).count());
  events.origin=origin;
  const auto callback=[&](std::size_t begin,std::size_t count,std::uint64_t scheduled,bool cleanup) {
    data.numSamples=static_cast<int32>(count);input_ptr=const_cast<Sample*>(source.data()+begin);
    events.host_sample=begin;events.cleanup=cleanup;
    const auto began=monotonic_ns()-origin;
    begin_callback_allocations();
    const auto result=component.process(data);
    const auto allocations=end_callback_allocations();
    const auto duration=monotonic_ns()-origin-began;
    if(result!=kResultOk) process_ok=false;
    if(count && std::memcmp(source.data()+begin,dry.data(),count*sizeof(Sample))) dry_identical=false;
    if(calls<timing.size()) timing[calls++]={begin+count,count,began,duration,
      began>scheduled?began-scheduled:0,allocations.allocations,allocations.deallocations};
    else log_ok=false;
  };
  callback(0,0,0,false); // Complete initial cleanup/epoch handshake before the first input.
  constexpr std::array<std::size_t,3> pattern{32,512,1024};
  std::size_t step=0;
  for(std::size_t begin=0;begin<source.size();) {
    const auto count=std::min(pattern[step++%pattern.size()],source.size()-begin);
    const auto scheduled=ceil_div((begin+count)*kNs,kRate);
    std::this_thread::sleep_until(start+std::chrono::nanoseconds(scheduled));
    callback(begin,count,scheduled,false);begin+=count;
  }
  begin_callback_allocations();
  const bool finish_ok=component.finish_test_input();
  const auto finish_allocations=end_callback_allocations();
  auto scheduled=ceil_div(source.size()*kNs,kRate);
  for(std::size_t i=0;i<300 && !component.test_worker_finished();++i) {
    scheduled+=ceil_div(640*kNs,kRate);
    std::this_thread::sleep_until(start+std::chrono::nanoseconds(scheduled));
    callback(source.size(),0,scheduled,false);
  }
  const bool finished=component.test_worker_finished();
  callback(source.size(),0,monotonic_ns()-origin,false);
  const auto source_received=component.diagnostic_bridge().source_samples();
  const auto input_drops=component.diagnostic_bridge().input_drops();
  const auto delivery_faults=component.diagnostic_bridge().delivery_faults();
  const bool blocked=component.diagnostic_bridge().blocked();
  require(component.setParamNormalized(0,1),"Panic parameter failed");
  callback(source.size(),0,monotonic_ns()-origin,true);
  const auto active_after=component.diagnostic_bridge().active_count();
  require(component.setProcessing(false),"processing stop failed");
  require(component.setActive(false),"worker deactivation failed");
  require(component.terminate(),"terminate failed");
  // Worker evidence is now immutable; model loading, join and writes were never timed as process().
  const std::filesystem::path folder(output);std::filesystem::create_directories(folder);
  std::ofstream generated(folder/"generated.tsv");generated<<"frame\tnote\ton\tsource_end\tready_ns\n";
  for(const auto& r:evidence.generated) generated<<r.event.frame<<'\t'<<r.event.note<<'\t'<<r.event.on
      <<'\t'<<r.source_end<<'\t'<<r.ready_ns-origin<<'\n';
  std::ofstream delivered(folder/"delivered.tsv");delivered<<"note\ton\thost_sample\temitted_ns\tcleanup\n";
  std::size_t cleanup_count=0;bool event_contract=true;
  for(std::size_t i=0;i<events.count;++i) {
    const auto& r=events.rows[i];const auto& e=r.event;
    const bool on=e.type==Steinberg::Vst::Event::kNoteOnEvent;
    const bool off=e.type==Steinberg::Vst::Event::kNoteOffEvent;
    const auto note=on?e.noteOn.pitch:e.noteOff.pitch;
    event_contract&=(on || off) && e.busIndex==0 && e.sampleOffset==0 &&
      (on?e.noteOn.channel:e.noteOff.channel)==0 && (on?e.noteOn.noteId:e.noteOff.noteId)==-1000-note;
    delivered<<note<<'\t'<<on<<'\t'<<r.host_sample<<'\t'<<r.emitted_ns<<'\t'<<r.cleanup<<'\n';
    cleanup_count+=r.cleanup;
  }
  std::ofstream workers(folder/"worker.tsv");workers<<"source_end\tqueued_ns\tservice_ns\tmodel_ns\n";
  for(const auto& r:evidence.timing) workers<<r.source_end<<'\t'<<r.queued_ns<<'\t'<<r.service_ns<<'\t'<<r.model_ns<<'\n';
  std::ofstream gate(folder/"gate.tsv");gate<<"source_end\tframe\tpower\tenabled\topen\n"<<std::setprecision(17);
  for(const auto& r:evidence.gate) gate<<r.source_end<<'\t'<<r.frame<<'\t'<<r.power<<'\t'<<r.enabled<<'\t'<<r.open<<'\n';
  std::ofstream callbacks(folder/"callbacks.tsv");callbacks<<"source_end\tsamples\tstarted_ns\tduration_ns\tlate_ns\tallocations\tfrees\n";
  for(std::size_t i=0;i<calls;++i) {const auto& r=timing[i];callbacks<<r.source_end<<'\t'<<r.samples<<'\t'
    <<r.started_ns<<'\t'<<r.duration_ns<<'\t'<<r.late_ns<<'\t'<<r.allocations<<'\t'<<r.frees<<'\n';}
  if(!generated || !delivered || !workers || !callbacks || !gate) throw std::runtime_error("table write failed");
  const bool ok=process_ok && log_ok && dry_identical && event_contract && finish_ok && finished && !blocked &&
    source_received==source.size() && evidence.consumed==source.size() && !input_drops && !delivery_faults &&
    !evidence.output_drops && evidence.error.empty() && !events.overflow && !events.refused && !active_after;
  std::ofstream summary(folder/"summary.json");
  summary<<"{\"sample_format\":"<<(std::is_same_v<Sample,float>?32:64)<<",\"source_samples\":"<<source.size()
    <<",\"gate_enabled\":"<<(gate_enabled?"true":"false")<<",\"gate_threshold_db\":"<<gate_db
    <<",\"gate_closed_frames\":"<<evidence.gate_closed_frames<<",\"gate_forced_releases\":"<<evidence.gate_forced_releases
    <<",\"source_received\":"<<source_received<<",\"consumed_samples\":"<<evidence.consumed
    <<",\"model_calls\":"<<evidence.calls<<",\"input_drops\":"<<input_drops
    <<",\"output_drops\":"<<evidence.output_drops<<",\"delivery_faults\":"<<delivery_faults
    <<",\"cleanup_events\":"<<cleanup_count<<",\"sink_active_after_cleanup\":"<<active_after
    <<",\"finish_allocations\":"<<finish_allocations.allocations<<",\"finish_deallocations\":"<<finish_allocations.deallocations
    <<",\"warmup_ns\":"<<evidence.warmup_ns<<",\"worker_error\":"<<quote(evidence.error)
    <<",\"dry_identical\":"<<(dry_identical?"true":"false")<<",\"event_contract\":"<<(event_contract?"true":"false")
    <<",\"worker_finished\":"<<(finished?"true":"false")<<",\"execution_pass\":"<<(ok?"true":"false")<<"}\n";
  summary.close();if(!summary) throw std::runtime_error("summary write failed");
  std::cout<<"actual component: "<<evidence.consumed<<'/'<<source.size()<<" samples, "<<events.count
    <<" accepted events, "<<cleanup_count<<" explicit EOF releases, format "<<(std::is_same_v<Sample,float>?32:64)<<'\n';
  return ok?0:2;
}
}
int main(int argc,char** argv) {
  if(argc!=6 && argc!=7) {std::cerr<<"usage: neural_lab_harness mono.f32 coefficients.f64 model output-directory 32|64 [gate-dBFS]\n";return 1;}
  try {
    const double db=argc==7?std::stod(argv[6]):-60;
    if(!std::isfinite(db) || db < -90 || db > -30) throw std::runtime_error("invalid gate threshold");
    if(std::string(argv[5])=="32") return run<float>(argv[1],argv[2],argv[3],argv[4],argc==7,db);
    if(std::string(argv[5])=="64") return run<double>(argv[1],argv[2],argv[3],argv[4],argc==7,db);
    throw std::runtime_error("unsupported sample format");
  } catch(const std::exception& e) {std::cerr<<"component failure: "<<e.what()<<'\n';return 1;}
}
