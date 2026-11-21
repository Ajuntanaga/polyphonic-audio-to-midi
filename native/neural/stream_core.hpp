#pragma once
// Experimental standalone port of tools/basic_pitch_streaming.py. No model,
// annotation, host SDK, file I/O or production dependency lives in this core.
#include "../offline/frozen_cue_worker.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace m3::neural {
constexpr std::size_t kBlock=640, kPitches=88, kWindow=43844, kTaps=12801;
constexpr std::uint64_t kRate=96000, kNs=1000000000;
inline std::uint64_t ceil_div(std::uint64_t n,std::uint64_t d) { return (n+d-1)/d; }
struct Event { std::uint64_t frame{}; std::uint16_t note{}; bool on{}; };
struct Batch {
  std::uint64_t source_end{}, ready_ns{};
  std::size_t count{};
  std::array<Event,2*kPitches> events{};
  void add(Event e) {
    if(count==events.size()) throw std::runtime_error("event batch overflow");
    events[count++]=e;
  }
};
// Optional worker-side level gate. Settings travel with the source packet, not
// with model completion time. Off preserves the original decoder exactly.
constexpr std::uint32_t kGateEnabled=0x80000000U, kGateDefault=300U;
constexpr std::size_t kGateFast=1920, kGateSlow=7680, kGateDwell=3840;
inline bool valid_gate_settings(std::uint32_t value) noexcept {
  return (value&~kGateEnabled)<=600U;
}
inline double gate_threshold_db(std::uint32_t value) noexcept {
  return -90.0+0.1*static_cast<double>(value&~kGateEnabled);
}
class QuietGate {
 public:
  void consume(const float* samples,std::size_t count,std::uint32_t settings) {
    if(!valid_gate_settings(settings)) throw std::runtime_error("invalid gate settings");
    if(settings!=settings_) {
      const bool was_enabled=enabled();settings_=settings;
      close_power_=std::pow(10.0,gate_threshold_db(settings)/10.0);
      open_power_=close_power_*std::pow(10.0,6.0/10.0);
      quiet_=0;
      if(enabled()!=was_enabled) {
        history_.fill(0);position_=seen_=0;fast_=slow_=level_=0;open_=false;
      }
    }
    if(!enabled()) return;
    for(std::size_t i=0;i<count;++i) {
      if(!std::isfinite(samples[i])) throw std::runtime_error("nonfinite gate source");
      const double power=static_cast<double>(samples[i])*samples[i];
      if(seen_>=kGateFast) fast_-=history_[(position_+kGateSlow-kGateFast)%kGateSlow];
      if(seen_>=kGateSlow) slow_-=history_[position_];
      history_[position_]=power;position_=(position_+1)%kGateSlow;
      seen_=std::min(kGateSlow,seen_+1);fast_+=power;slow_+=power;
      fast_=std::max(0.0,fast_);slow_=std::max(0.0,slow_);
      level_=std::max(fast_/std::min(seen_,kGateFast),slow_/seen_);
      if(!open_) {
        if(level_>=open_power_) {open_=true;quiet_=0;}
      } else if(level_<close_power_) {
        if(++quiet_>=kGateDwell) {open_=false;quiet_=0;}
      } else quiet_=0;
    }
  }
  bool enabled() const noexcept {return (settings_&kGateEnabled)!=0;}
  bool permits_notes() const noexcept {return !enabled() || open_;}
  double power() const noexcept {return level_;}
 private:
  std::array<double,kGateSlow> history_{};
  std::size_t position_{},seen_{},quiet_{};
  std::uint32_t settings_{kGateDefault};
  double fast_{},slow_{},level_{},close_power_{1e-6},open_power_{3.981071705534972e-6};
  bool open_{};
};
class Decoder {
 public:
  void consume(const float* notes,const float* onsets,Batch& events,bool permit_notes=true) {
    for(std::size_t i=0;i<kPitches;++i) {
      if(!std::isfinite(notes[i]) || !std::isfinite(onsets[i]) || notes[i]<0 ||
          notes[i]>1 || onsets[i]<0 || onsets[i]>1)
        throw std::runtime_error("invalid activation");
      if(!permit_notes) {
        if(active_[i]) events.add({frame_,static_cast<std::uint16_t>(i+21),false});
        active_[i]=false;attack_[i]=release_[i]=0;continue;
      }
      // Match Python's float64 comparison with its literal 0.3 threshold.
      const bool high=static_cast<double>(notes[i])>=0.3;
      attack_[i]=high ? std::min(3U,attack_[i]+1U) : 0U;
      release_[i]=high ? 0U : std::min(3U,release_[i]+1U);
      if(!active_[i] && high && (static_cast<double>(onsets[i])>=0.5 || attack_[i]>=3)) {
        active_[i]=true; events.add({frame_,static_cast<std::uint16_t>(i+21),true});
      } else if(active_[i] && release_[i]>=3) {
        active_[i]=false; events.add({frame_,static_cast<std::uint16_t>(i+21),false});
      }
    }
    ++frame_;
  }
  std::uint64_t frame() const noexcept {return frame_;}
  const std::array<bool,kPitches>& active() const noexcept {return active_;}
 private:
  std::array<bool,kPitches> active_{};
  std::array<unsigned,kPitches> attack_{},release_{};
  std::uint64_t frame_{};
};
class Resampler {
 public:
  explicit Resampler(const std::array<double,kTaps>& coefficients):h_(coefficients) {}
  std::size_t consume(const float* block,std::size_t count,std::array<float,147>& out) {
    if(ended_ || !count || count>kBlock) throw std::runtime_error("invalid input block");
    std::copy(history_.begin(),history_.end(),joined_.begin());
    for(std::size_t j=0;j<count;++j) {
      if(!std::isfinite(block[j])) throw std::runtime_error("nonfinite source");
      joined_[640+j]=block[j];
    }
    const auto n=static_cast<std::size_t>(ceil_div(count*147,640));
    for(std::size_t m=0;m<n;++m) {
      const std::size_t index=(147+m)*640;
      const auto first=static_cast<std::size_t>(ceil_div(index-(kTaps-1),147));
      const auto last=std::min(index/147,639+count);
      double sum=0;
      for(auto j=first;j<=last;++j) sum+=static_cast<double>(joined_[j])*h_[index-j*147];
      out[m]=static_cast<float>(sum);
    }
    std::copy_n(block,count,history_.begin());
    ended_=count<640;
    return n;
  }
 private:
  std::array<double,kTaps> h_;
  std::array<float,640> history_{};
  std::array<float,1280> joined_{};
  bool ended_{};
};
class Window {
 public:
  void append(const float* values,std::size_t count) noexcept {
    for(std::size_t i=0;i<count;++i) ring_[produced_++%ring_.size()]=values[i];
  }
  bool ready() const noexcept {return produced_>=next_end_;}
  void copy(float* destination) const {
    if(!ready() || produced_-next_end_>=147) throw std::runtime_error("window cadence mismatch");
    // The ring holds the requested window plus one source block of lookbehind.
    const auto start=static_cast<std::int64_t>(next_end_)-static_cast<std::int64_t>(kWindow);
    for(std::size_t i=0;i<kWindow;++i) {
      const auto pos=start+static_cast<std::int64_t>(i);
      destination[i]=pos<0 ? 0.0F : ring_[static_cast<std::size_t>(pos)%ring_.size()];
    }
  }
  void advance() noexcept {next_end_+=512;}
  std::uint64_t end() const noexcept {return next_end_;}
  std::uint64_t produced() const noexcept {return produced_;}
 private:
  std::array<float,kWindow+147> ring_{};
  std::uint64_t produced_{},next_end_{1860};
};
struct Input {std::uint64_t end{},arrival_ns{};std::size_t count{};std::array<float,kBlock> data{};};
using InputQueue=m3::offline::FrozenCueQueue<Input,16>;
using OutputQueue=m3::offline::FrozenCueQueue<Batch,16>;
// Callback-owned, accepting sink state; no lane cap and no re-assignment.
class PitchState {
 public:
  template<class Sink> bool apply(const Event& e,Sink&& sink) noexcept {
    if(e.note<21 || e.note>=21+kPitches) return false;
    const auto i=static_cast<std::size_t>(e.note-21);
    if(active_[i]==e.on || !sink(e)) return false;
    active_[i]=e.on; return true;
  }
  template<class Sink> bool release_all(Sink&& sink) noexcept {
    bool complete=true;
    for(std::size_t i=0;i<kPitches;++i) if(active_[i]) {
      const Event e{0,static_cast<std::uint16_t>(i+21),false};
      if(sink(e)) active_[i]=false; else complete=false;
    }
    return complete;
  }
  std::size_t active_count() const noexcept {return std::count(active_.begin(),active_.end(),true);}
 private:
  std::array<bool,kPitches> active_{};
};
} // namespace m3::neural
