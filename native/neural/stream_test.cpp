#include "stream_core.hpp"
#include "allocation_guard.hpp"
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>
#include <thread>

using namespace m3::neural;
namespace {
void require(bool value,const char* message) {if(!value) throw std::runtime_error(message);}
template<class F> void throws(F f) {
  bool caught=false;try{f();}catch(const std::exception&){caught=true;}
  require(caught,"missing invalid-input exception");
}
void decoder_test() {
  Decoder decoder;Batch out;std::array<float,88> notes{},onsets{};
  notes[39]=0.8F;
  decoder.consume(notes.data(),onsets.data(),out);
  decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==0,"attack persistence is causal");
  decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==1 && out.events[0].frame==2 && out.events[0].note==60 && out.events[0].on,"third-frame attack");
  onsets[39]=1;decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==1,"no held-note retrigger");
  notes[39]=0;
  decoder.consume(notes.data(),onsets.data(),out);decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==1,"release waits three frames");
  decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==2 && !out.events[1].on && out.events[1].frame==6,"release at current frame");
  notes[0]=0.3F;onsets[0]=0.5F;decoder.consume(notes.data(),onsets.data(),out);
  require(out.count==3 && out.events[2].note==21,"onset threshold and pitch range");
  notes[87]=std::numeric_limits<float>::quiet_NaN();
  throws([&]{decoder.consume(notes.data(),onsets.data(),out);});
  Decoder all;notes.fill(1);onsets.fill(1);Batch chord;
  all.consume(notes.data(),onsets.data(),chord);
  require(chord.count==88 && chord.events[87].note==108,"all 88 pitches survive");
}
void resampler_window_test() {
  std::array<double,kTaps> h{};h[0]=1;
  Resampler sampler(h);std::array<float,640> input{};std::array<float,147> result{};
  input[0]=0.75F;input[1]=0.5F;
  require(sampler.consume(input.data(),640,result)==147 && result[0]==0.75F,"polyphase phase zero");
  require(result[1]==0,"unobserved upsample phases are zero");
  require(sampler.consume(input.data(),1,result)==1 && result[0]==0.75F,"partial final block");
  throws([&]{sampler.consume(input.data(),1,result);});
  Window window;std::array<float,kWindow> copy{};
  std::array<float,147> chunk{};std::uint64_t produced=0,calls=0;
  for(int block=0;block<650;++block) {
    for(auto& value:chunk) value=static_cast<float>(produced++);
    window.append(chunk.data(),chunk.size());
    if(window.ready()) {
      window.copy(copy.data());
      const auto start=static_cast<std::int64_t>(window.end())-static_cast<std::int64_t>(kWindow);
      for(std::size_t i=0;i<copy.size();++i) require(copy[i]==static_cast<float>(std::max<std::int64_t>(0,start+static_cast<std::int64_t>(i))),"window alignment/padding/ring wrap");
      window.advance();++calls;
    }
  }
  require(calls>100,"exercise wrapped streaming window");
}
void queue_and_sink_test() {
  m3::offline::FrozenCueQueue<std::uint64_t,4> queue;
  for(std::uint64_t i=0;i<4;++i) require(queue.push(i),"bounded queue admission");
  require(!queue.push(5),"queue overflow is explicit");
  for(std::uint64_t i=0;i<4;++i){require(queue.front() && *queue.front()==i,"queue order");queue.pop();}
  require(queue.front()==nullptr,"queue fully drained");
  PitchState state;std::size_t accepted=0;
  const auto accept=[&](const Event&) noexcept{++accepted;return true;};
  const auto reject=[](const Event&) noexcept{return false;};
  require(state.apply(Event{1,60,true},accept),"accept initial note");
  require(!state.apply(Event{2,60,true},accept) && accepted==1,"no duplicate on delivery");
  require(!state.apply(Event{3,60,false},reject) && state.active_count()==1,"refused release retains owner");
  require(!state.release_all(reject) && state.active_count()==1,"cleanup retry remains pending");
  require(state.release_all(accept) && state.active_count()==0 && accepted==2,"cleanup releases once");
  require(state.release_all(accept) && accepted==2,"quiet repeated cleanup");
  require(!state.apply(Event{4,20,true},accept),"reject out-of-range output");
}
void allocation_test() {
  begin_callback_allocations();
  // Explicit function pointers keep the optimizer from eliding allocator probes.
  void* (*volatile alloc)(std::size_t)=std::malloc;
  void (*volatile free_fn)(void*)=std::free;
  auto* p=alloc(17);free_fn(p);
  void* (*volatile new_fn)(std::size_t)=::operator new;
  void (*volatile delete_fn)(void*)=::operator delete;
  p=new_fn(19);delete_fn(p);
  const auto counts=end_callback_allocations();
  require(counts.allocations==2 && counts.deallocations==2,"C and C++ allocation probes");
  std::atomic<bool> go{false},done{false};
  std::thread worker([&]{while(!go.load(std::memory_order_acquire))std::this_thread::yield();
    auto* q=alloc(23);free_fn(q);done.store(true,std::memory_order_release);});
  begin_callback_allocations();go.store(true,std::memory_order_release);
  while(!done.load(std::memory_order_acquire))std::this_thread::yield();
  const auto isolated=end_callback_allocations();worker.join();
  require(!isolated.allocations && !isolated.deallocations,"worker allocation is not callback allocation");
  PitchState state;InputQueue input;OutputQueue output;
  Input block;Batch events;events.add({0,108,true});
  begin_callback_allocations();
  const bool pushed=input.push(block) && output.push(events);
  const bool delivered=state.apply(output.front()->events[0],[](const Event&) noexcept{return true;});
  output.pop();input.pop();state.release_all([](const Event&) noexcept{return true;});
  const auto callback=end_callback_allocations();
  require(pushed && delivered && !callback.allocations && !callback.deallocations,"callback mechanics do not allocate");
}
}
int main() {
  try{decoder_test();resampler_window_test();queue_and_sink_test();allocation_test();
    std::cout<<"neural core tests passed\n";return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
