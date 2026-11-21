#pragma once
// Fixed storage shared by the experimental component and its inference worker.
// The callback owns Bridge/PitchState. Only the worker owns inference state.
#include "stream_core.hpp"
#include <atomic>
#include <chrono>

namespace m3::neural {
inline std::uint64_t monotonic_ns() noexcept {
  return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());
}
struct EpochInput {std::uint64_t epoch{};Input input{};};
struct EpochBatch {std::uint64_t epoch{};Batch batch{};};
struct Exchange {
  m3::offline::FrozenCueQueue<EpochInput,16> input;
  m3::offline::FrozenCueQueue<EpochBatch,16> output;
  std::atomic<std::uint64_t> requested{1},acknowledged{1},finish{0},finished{0};
  std::atomic<bool> fatal{false},stop{false};
};
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);

class Bridge {
 public:
  // Called with processing stopped. Accepted owners deliberately survive it.
  void attach(Exchange* exchange) noexcept {
    exchange_=exchange;epoch_=exchange?exchange->requested.load():0;
    partial_={};source_samples_=0;input_finished_=false;blocked_=false;holding_=true;
  }
  void detach() noexcept {exchange_=nullptr;partial_={};holding_=true;}
  void reset(bool recover) noexcept {
    partial_={};source_samples_=0;input_finished_=false;holding_=true;
    if(recover) blocked_=false;
    if(exchange_) epoch_=exchange_->requested.fetch_add(1,std::memory_order_acq_rel)+1;
  }
  template<class Sink> void render(Sink&& sink) noexcept {
    if(exchange_ && exchange_->fatal.load(std::memory_order_acquire)) blocked_=true;
    if(holding_ || blocked_ || !exchange_)
      state_.release_all([&](const Event& e) noexcept{return sink(e,0,0,true);});
    if(exchange_ && holding_ && !blocked_ && state_.active_count()==0 &&
        exchange_->acknowledged.load(std::memory_order_acquire)==epoch_) holding_=false;
    if(exchange_) for(std::size_t drain=0;drain<16;++drain) {
      const auto* queued=exchange_->output.front();if(!queued) break;
      if(queued->epoch==epoch_ && !holding_ && !blocked_) {
        const auto& b=queued->batch;
        for(std::size_t i=0;i<b.count;++i) {
          if(!state_.apply(b.events[i],[&](const Event& e) noexcept{
              return sink(e,b.source_end,b.ready_ns,false);})) {
            ++delivery_faults_;blocked_=true;reset(false);break;
          }
        }
      }
      exchange_->output.pop();
    }
    if(blocked_) state_.release_all([&](const Event& e) noexcept{return sink(e,0,0,true);});
  }
  bool feed(const float* samples,std::size_t count) noexcept {
    if(!ready() || input_finished_) return false;
    while(count) {
      const auto n=std::min(count,kBlock-partial_.count);
      for(std::size_t i=0;i<n;++i) if(!std::isfinite(samples[i])) {fault();return false;}
      std::copy_n(samples,n,partial_.data.begin()+partial_.count);
      samples+=n;count-=n;partial_.count+=n;source_samples_+=n;
      if(partial_.count==kBlock && !publish()) return false;
    }
    return true;
  }
  // Test/offline EOF boundary; live transport resets use reset().
  bool finish_input() noexcept {
    if(!ready()) return false;
    if(partial_.count && !publish()) return false;
    input_finished_=true;exchange_->finish.store(epoch_,std::memory_order_release);return true;
  }
  bool finished() const noexcept {
    return exchange_ && exchange_->finished.load(std::memory_order_acquire)==epoch_;
  }
  bool ready() const noexcept {
    return exchange_ && !blocked_ && !holding_ && !exchange_->fatal.load(std::memory_order_acquire);
  }
  bool blocked() const noexcept {return blocked_;}
  std::uint64_t epoch() const noexcept {return epoch_;}
  std::uint64_t source_samples() const noexcept {return source_samples_;}
  std::size_t active_count() const noexcept {return state_.active_count();}
  std::uint64_t input_drops() const noexcept {return input_drops_;}
  std::uint64_t delivery_faults() const noexcept {return delivery_faults_;}
  void fault() noexcept {blocked_=true;reset(false);}
 private:
  bool publish() noexcept {
    partial_.end=source_samples_;partial_.arrival_ns=monotonic_ns();
    if(!exchange_->input.push(EpochInput{epoch_,partial_})) {++input_drops_;fault();return false;}
    partial_.count=0;return true;
  }
  Exchange* exchange_{};PitchState state_;Input partial_;
  std::uint64_t epoch_{},source_samples_{},input_drops_{},delivery_faults_{};
  bool blocked_{},holding_{true},input_finished_{};
};
} // namespace m3::neural
