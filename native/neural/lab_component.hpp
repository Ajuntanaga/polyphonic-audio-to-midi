#pragma once
#include "public.sdk/source/vst/vstsinglecomponenteffect.h"
#include "lab_worker.hpp"
#include <atomic>
#include <memory>
#include <string>

namespace m3::neural {
class LabComponent final:public Steinberg::Vst::SingleComponentEffect {
 public:
  ~LabComponent() override;
  static Steinberg::FUnknown* createInstance(void*);
  Steinberg::tresult PLUGIN_API initialize(Steinberg::FUnknown*) override;
  Steinberg::tresult PLUGIN_API terminate() override;
  Steinberg::tresult PLUGIN_API setBusArrangements(Steinberg::Vst::SpeakerArrangement*,Steinberg::int32,
      Steinberg::Vst::SpeakerArrangement*,Steinberg::int32) override;
  Steinberg::tresult PLUGIN_API canProcessSampleSize(Steinberg::int32) override;
  Steinberg::tresult PLUGIN_API setupProcessing(Steinberg::Vst::ProcessSetup&) override;
  Steinberg::tresult PLUGIN_API setActive(Steinberg::TBool) override;
  Steinberg::tresult PLUGIN_API setProcessing(Steinberg::TBool) override;
  Steinberg::tresult PLUGIN_API process(Steinberg::Vst::ProcessData&) override;
  Steinberg::tresult PLUGIN_API setParamNormalized(Steinberg::Vst::ParamID,Steinberg::Vst::ParamValue) override;
  Steinberg::tresult PLUGIN_API setState(Steinberg::IBStream*) override;
  Steinberg::tresult PLUGIN_API getState(Steinberg::IBStream*) override;
  Steinberg::uint32 PLUGIN_API getLatencySamples() override {return 0;}
  Steinberg::uint32 PLUGIN_API getTailSamples() override {return Steinberg::Vst::kNoTail;}
#if defined(M3_NEURAL_LAB_DIAGNOSTICS)
  void configure_test_resources(const std::string& model,const std::string& filter,LabEvidence* evidence) {
    model_path_=model;filter_path_=filter;evidence_=evidence;
  }
  void attach_test_exchange(Exchange& e) noexcept {bridge_.attach(&e);active_=true;processing_=true;}
  const Bridge& diagnostic_bridge() const noexcept {return bridge_;}
  bool finish_test_input() noexcept {return bridge_.finish_input();}
  bool test_worker_finished() const noexcept {return bridge_.finished();}
#endif
 private:
  template<class Sample> Steinberg::tresult process_audio(Steinberg::Vst::ProcessData&);
  void stop_worker() noexcept;
  bool apply_gate_parameter(Steinberg::Vst::ParamID,Steinberg::Vst::ParamValue) noexcept;
  std::uint32_t gate_settings() const noexcept {
    return gate_threshold_.load(std::memory_order_relaxed) |
      (gate_enabled_.load(std::memory_order_relaxed)?kGateEnabled:0U);
  }
  Bridge bridge_;std::unique_ptr<Worker> worker_;
  std::string model_path_,filter_path_;LabEvidence* evidence_{};
  std::array<float,1024> mono_{};
  std::atomic<bool> panic_{false};
  // Host parameters are independent. One packed snapshot is latched per source packet.
  std::atomic<std::uint32_t> gate_enabled_{0},gate_threshold_{kGateDefault};
  Steinberg::int32 channels_{2},format_{Steinberg::Vst::kSample32},max_block_{1024};
  bool configured_{},active_{},processing_{};
};
} // namespace m3::neural
