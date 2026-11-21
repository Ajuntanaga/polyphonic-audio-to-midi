// Actual ORT inference on a separate worker; paced, bounded accepting callback.
// Experimental standalone executable. No host SDK, labels or installed DSP path.
#include "stream_core.hpp"
#include "allocation_guard.hpp"
#include "ort_model.hpp"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <thread>
#include <vector>

using namespace m3::neural;
using Clock=std::chrono::steady_clock;
namespace {
template<class T> std::vector<T> read_binary(const std::string& path) {
  std::ifstream file(path,std::ios::binary|std::ios::ate);
  if(!file) throw std::runtime_error("cannot open input: "+path);
  const auto size=file.tellg();
  if(size<=0 || static_cast<std::uint64_t>(size)%sizeof(T)) throw std::runtime_error("invalid binary size");
  std::vector<T> data(static_cast<std::size_t>(size)/sizeof(T));
  file.seekg(0);file.read(reinterpret_cast<char*>(data.data()),size);
  if(!file) throw std::runtime_error("incomplete binary input");
  return data;
}
template<class T> void write_binary(const std::filesystem::path& path,const std::vector<T>& data) {
  std::ofstream file(path,std::ios::binary);
  file.write(reinterpret_cast<const char*>(data.data()),static_cast<std::streamsize>(data.size()*sizeof(T)));
  if(!file) throw std::runtime_error("binary evidence write failed");
}
std::string quote(const std::string& s) {
  std::string r="\"";for(unsigned char c:s) {
    if(c=='"' || c=='\\') {r+='\\';r+=static_cast<char>(c);}
    else if(c=='\n') r+="\\n";
    else if(c>=32) r+=static_cast<char>(c);
  }return r+'"';
}
std::uint64_t elapsed(Clock::time_point start) noexcept {
  return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
}

struct WorkerTime {
  std::uint64_t source_end{},arrival_ns{},started_ns{},service_ns{},finish_ns{},queued_ns{},model_ns{},called{};
};
struct Frame {std::array<std::uint64_t,4> clock{};std::array<float,88> note{},onset{};};
struct Delivery {Event event;std::uint64_t source_end{},ready_ns{},emitted_ns{};bool cleanup{};};
struct CallbackTime {std::uint64_t source_end{},started_ns{},duration_ns{},late_ns{},allocations{},frees{},quiet{};};
struct WorkerEvidence {
  std::vector<WorkerTime> timing;
  std::vector<Frame> frames;
  std::vector<float> resampled;
  std::vector<Delivery> generated;
  std::array<bool,88> open{};
  std::uint64_t samples{},calls{},output_drops{},next_end{};
  std::string error;
};
int run(const char* audio_path,const char* coefficients_path,const char* model_path,const char* output_path) {
  if(!std::getenv("GITHUB_ACTIONS") || std::string(std::getenv("GITHUB_ACTIONS"))!="true")
    throw std::runtime_error("recorded/native measurement requires GitHub Actions");
  static_assert(sizeof(float)==4 && sizeof(double)==8);
  const auto source=read_binary<float>(audio_path);
  const auto coeff=read_binary<double>(coefficients_path);
  if(coeff.size()!=kTaps || !std::all_of(source.begin(),source.end(),[](float x){return std::isfinite(x);}) ||
      !std::all_of(coeff.begin(),coeff.end(),[](double x){return std::isfinite(x);}))
    throw std::runtime_error("invalid finite input/filter");
  std::array<double,kTaps> h{};std::copy(coeff.begin(),coeff.end(),h.begin());
  Model model(model_path);
  std::vector<float> dry(source.size());
  const auto blocks=ceil_div(source.size(),640),frames=ceil_div(source.size()*147,640*512)*2+8;
  WorkerEvidence evidence;
  evidence.timing.reserve(blocks);evidence.frames.reserve(frames);
  evidence.resampled.reserve(ceil_div(source.size()*147,640));evidence.generated.reserve(frames*88);
  // Log storage is allocated before the paced callback and never grows there.
  std::vector<Delivery> deliveries(frames*88+88);
  std::vector<CallbackTime> callback_log(blocks+400);
  std::size_t delivered=0,callbacks=0;
  InputQueue input;OutputQueue output;PitchState state;
  std::atomic<bool> go{false},producer_done{false},worker_done{false},fatal{false};
  Clock::time_point start;
  std::thread worker([&]{
    while(!go.load(std::memory_order_acquire)) std::this_thread::sleep_for(std::chrono::microseconds(25));
    try {
      Resampler resampler(h);Window window;Decoder decoder;std::array<float,147> converted{};
      while(!fatal.load(std::memory_order_acquire)) {
        const auto* queued=input.front();
        if(!queued) {
          if(producer_done.load(std::memory_order_acquire)) break;
          std::this_thread::sleep_for(std::chrono::microseconds(25));continue;
        }
        const Input current=*queued;input.pop();
        if(current.end!=evidence.samples+current.count) throw std::runtime_error("source discontinuity");
        const auto began=elapsed(start);
        const auto count=resampler.consume(current.data.data(),current.count,converted);
        window.append(converted.data(),count);
        Batch batch;batch.source_end=current.end;
        std::array<Frame,2> emitted_frames{};
        std::uint64_t model_ns=0,called=0;
        if(window.ready()) {
          window.copy(model.window.data());const auto before_model=elapsed(start);
          auto prediction=model.predict();model_ns=elapsed(start)-before_model;
          for(std::size_t j=0;j<2;++j) {
            auto& frame=emitted_frames[j];frame.clock={decoder.frame(),decoder.frame()*256,window.end(),current.end};
            std::copy_n(prediction[0].GetTensorData<float>()+(164+j)*88,88,frame.note.begin());
            std::copy_n(prediction[1].GetTensorData<float>()+(164+j)*88,88,frame.onset.begin());
            decoder.consume(frame.note.data(),frame.onset.data(),batch);
          }
          window.advance();++evidence.calls;called=1;
        }
        const auto finished=elapsed(start);batch.ready_ns=finished;
        if(batch.count && !output.push(batch)) {++evidence.output_drops;throw std::runtime_error("output queue overflow");}
        // Evidence retention is outside service; its wall time still contributes to actual subsequent queue wait.
        evidence.samples=current.end;evidence.timing.push_back({current.end,current.arrival_ns,began,
            finished-began,finished,began-current.arrival_ns,model_ns,called});
        evidence.resampled.insert(evidence.resampled.end(),converted.begin(),converted.begin()+count);
        if(called) evidence.frames.insert(evidence.frames.end(),emitted_frames.begin(),emitted_frames.end());
        for(std::size_t i=0;i<batch.count;++i) evidence.generated.push_back({batch.events[i],batch.source_end,batch.ready_ns,0,false});
      }
      evidence.open=decoder.active();evidence.next_end=window.end();
    }catch(const std::exception& e){evidence.error=e.what();fatal.store(true,std::memory_order_release);}
    worker_done.store(true,std::memory_order_release);
  });
  std::uint64_t input_drops=0,delivery_faults=0,cleanup_events=0;
  bool terminal=false;
  start=Clock::now();go.store(true,std::memory_order_release);
  const auto callback=[&](std::size_t begin,std::size_t count,std::uint64_t scheduled,bool cleanup) noexcept {
    const auto began=elapsed(start);
    begin_callback_allocations();
    if(count) std::copy_n(source.data()+begin,count,dry.data()+begin);
    const auto sink=[&](const Event& event,std::uint64_t source_end,std::uint64_t ready,bool is_cleanup) noexcept {
      if(delivered==deliveries.size()) return false;
      deliveries[delivered++]={event,source_end,ready,elapsed(start),is_cleanup};
      if(is_cleanup) ++cleanup_events;
      return true;
    };
    if(fatal.load(std::memory_order_acquire)) terminal=true;
    if(terminal || cleanup) {
      if(!state.release_all([&](const Event& e) noexcept{return sink(e,begin+count,began,true);})) ++delivery_faults;
    }
    for(std::size_t drain=0;drain<16;++drain) {
      const auto* batch=output.front();if(!batch) break;
      if(!terminal && !cleanup) for(std::size_t i=0;i<batch->count;++i) {
        if(!state.apply(batch->events[i],[&](const Event& e) noexcept{return sink(e,batch->source_end,batch->ready_ns,false);})) {
          ++delivery_faults;terminal=true;fatal.store(true,std::memory_order_release);break;
        }
      }
      output.pop();
    }
    if(count && !terminal && !cleanup) {
      Input block;block.end=begin+count;block.count=count;block.arrival_ns=elapsed(start);
      std::copy_n(source.data()+begin,count,block.data.begin());
      if(!input.push(block)) {++input_drops;terminal=true;fatal.store(true,std::memory_order_release);}
    }
    if(terminal) state.release_all([&](const Event& e) noexcept{return sink(e,begin+count,began,true);});
    const auto allocation=end_callback_allocations();const auto duration=elapsed(start)-began;
    if(callbacks<callback_log.size()) callback_log[callbacks++]={begin+count,began,duration,
        began>scheduled?began-scheduled:0,allocation.allocations,allocation.deallocations,count?0U:1U};
    else {++delivery_faults;fatal.store(true,std::memory_order_release);}
  };
  for(std::size_t begin=0;begin<source.size();begin+=640) {
    const auto count=std::min<std::size_t>(640,source.size()-begin);
    const auto scheduled=ceil_div((begin+count)*kNs,kRate);
    std::this_thread::sleep_until(start+std::chrono::nanoseconds(scheduled));
    callback(begin,count,scheduled,false);
  }
  producer_done.store(true,std::memory_order_release);
  auto scheduled=ceil_div(source.size()*kNs,kRate);
  for(std::size_t extra=0;extra<300 && !worker_done.load(std::memory_order_acquire);++extra) {
    scheduled+=ceil_div(640*kNs,kRate);
    std::this_thread::sleep_until(start+std::chrono::nanoseconds(scheduled));
    callback(source.size(),0,scheduled,false);
  }
  if(!worker_done.load(std::memory_order_acquire)) fatal.store(true,std::memory_order_release);
  worker.join();
  // One final drain then explicit cleanup: never score an EOF release as a detector decision.
  callback(source.size(),0,elapsed(start),false);
  callback(source.size(),0,elapsed(start),true);
  const bool dry_identical=source.size()==dry.size() && std::memcmp(source.data(),dry.data(),source.size()*sizeof(float))==0;
  const std::filesystem::path folder(output_path);
  std::filesystem::create_directories(folder);
  write_binary(folder/"resampled.f32",evidence.resampled);
  std::vector<float> notes,onsets;notes.reserve(evidence.frames.size()*88);onsets.reserve(evidence.frames.size()*88);
  std::ofstream frame_file(folder/"frames.tsv");frame_file<<"frame\tnominal_model_sample\twindow_end\tsource_end\n";
  for(const auto& frame:evidence.frames) {
    frame_file<<frame.clock[0]<<'\t'<<frame.clock[1]<<'\t'<<frame.clock[2]<<'\t'<<frame.clock[3]<<'\n';
    notes.insert(notes.end(),frame.note.begin(),frame.note.end());onsets.insert(onsets.end(),frame.onset.begin(),frame.onset.end());
  }
  write_binary(folder/"notes.f32",notes);write_binary(folder/"onsets.f32",onsets);
  const auto events=[&](const char* name,const std::vector<Delivery>& rows,std::size_t count) {
    std::ofstream file(folder/name);file<<"frame\tnote\ton\tsource_end\tready_ns\temitted_ns\tcleanup\n";
    for(std::size_t i=0;i<count;++i) {const auto& row=rows[i];
      file<<row.event.frame<<'\t'<<row.event.note<<'\t'<<row.event.on<<'\t'<<row.source_end<<'\t'
          <<row.ready_ns<<'\t'<<row.emitted_ns<<'\t'<<row.cleanup<<'\n';}
    if(!file) throw std::runtime_error("event evidence write failed");
  };
  events("generated.tsv",evidence.generated,evidence.generated.size());events("delivered.tsv",deliveries,delivered);
  std::ofstream times(folder/"worker.tsv");times<<"source_end\tarrival_ns\tstarted_ns\tservice_ns\tfinish_ns\tqueued_ns\tmodel_ns\tcalled\n";
  for(const auto& row:evidence.timing) times<<row.source_end<<'\t'<<row.arrival_ns<<'\t'<<row.started_ns<<'\t'
      <<row.service_ns<<'\t'<<row.finish_ns<<'\t'<<row.queued_ns<<'\t'<<row.model_ns<<'\t'<<row.called<<'\n';
  std::ofstream callback_file(folder/"callbacks.tsv");callback_file<<"source_end\tstarted_ns\tduration_ns\tlate_ns\tallocations\tfrees\tquiet\n";
  for(std::size_t i=0;i<callbacks;++i) {const auto& row=callback_log[i];callback_file<<row.source_end<<'\t'
      <<row.started_ns<<'\t'<<row.duration_ns<<'\t'<<row.late_ns<<'\t'<<row.allocations<<'\t'<<row.frees<<'\t'<<row.quiet<<'\n';}
  if(!frame_file || !times || !callback_file) throw std::runtime_error("table evidence write failed");
  std::ofstream summary(folder/"summary.json");
  summary<<"{\"source_samples\":"<<source.size()<<",\"consumed_samples\":"<<evidence.samples
    <<",\"model_calls\":"<<evidence.calls<<",\"resampled_samples\":"<<evidence.resampled.size()
    <<",\"observed_frames\":"<<evidence.frames.size()<<",\"next_window_end\":"<<evidence.next_end
    <<",\"input_drops\":"<<input_drops<<",\"output_drops\":"<<evidence.output_drops
    <<",\"delivery_faults\":"<<delivery_faults<<",\"cleanup_events\":"<<cleanup_events
    <<",\"sink_active_after_cleanup\":"<<state.active_count()<<",\"dry_identical\":"<<(dry_identical?"true":"false")
    <<",\"fatal\":"<<(fatal.load()?"true":"false")<<",\"worker_error\":"<<quote(evidence.error)
    <<",\"warmup_ns\":"<<model.warmup_ns<<",\"ort_version\":\"1.20.1\",\"open_decoder_pitches\":[";
  bool comma=false;for(std::size_t i=0;i<88;++i) if(evidence.open[i]) {if(comma)summary<<',';summary<<i+21;comma=true;}
  summary<<"]}\n";summary.close();
  if(!summary) throw std::runtime_error("summary write failed");
  std::cout<<"native stream: "<<evidence.samples<<'/'<<source.size()<<" samples, "<<evidence.calls
      <<" calls, "<<delivered<<" delivered transitions including "<<cleanup_events<<" EOF releases\n";
  return fatal.load() || input_drops || evidence.output_drops || delivery_faults || !dry_identical || state.active_count() ? 2:0;
}
}
int main(int argc,char** argv) {
  if(argc!=5) {std::cerr<<"usage: neural_ort_harness mono.f32 coefficients.f64 model.onnx output-directory\n";return 1;}
  try{return run(argv[1],argv[2],argv[3],argv[4]);}
  catch(const std::exception& e){std::cerr<<"native failure: "<<e.what()<<'\n';return 1;}
}
