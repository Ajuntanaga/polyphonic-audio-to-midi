#pragma once
// Experimental worker-only model adapter. Never called from the audio callback.
#include "stream_core.hpp"
#include <onnxruntime_cxx_api.h>
#include <chrono>
#include <string>
#include <vector>
namespace m3::neural {
struct ModelOptions {
  int intra_threads=2;
  const char* profile_prefix=nullptr;
  bool cropped_readout=false;
};
class Model {
 public:
  explicit Model(const char* path,const ModelOptions& config={}):env_(ORT_LOGGING_LEVEL_WARNING,"m3-neural"),session_(nullptr),
      memory_(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator,OrtMemTypeDefault)),tensor_(nullptr),
      cropped_readout_(config.cropped_readout) {
    if(std::string(OrtGetApiBase()->GetVersionString())!="1.20.1") throw std::runtime_error("ORT version mismatch");
    Ort::SessionOptions options;
    if(config.intra_threads<1 || config.intra_threads>4) throw std::runtime_error("invalid worker thread count");
    options.SetIntraOpNumThreads(config.intra_threads);options.SetInterOpNumThreads(1);
    options.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
    options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    if(config.profile_prefix) options.EnableProfiling(config.profile_prefix);
    session_=Ort::Session(env_,path,options);
    Ort::AllocatorWithDefaultOptions allocator;
    if(cropped_readout_) {
      auto metadata=session_.GetModelMetadata();
      auto schema=metadata.LookupCustomMetadataMapAllocated("m3.crop.schema",allocator);
      auto parent=metadata.LookupCustomMetadataMapAllocated("m3.crop.parent_sha256",allocator);
      if(!schema || !parent || std::string(schema.get())!="m3_basic_pitch_readout164_165_tail144_v1" ||
          std::string(parent.get())!="2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec")
        throw std::runtime_error("cropped model provenance mismatch");
    }
    if(session_.GetInputCount()!=1 || std::string(session_.GetInputNameAllocated(0,allocator).get())!=input_names_[0])
      throw std::runtime_error("model input name mismatch");
    std::array<bool,2> found{};
    for(std::size_t i=0;i<session_.GetOutputCount();++i) {
      const std::string name=session_.GetOutputNameAllocated(i,allocator).get();
      for(std::size_t j=0;j<2;++j) if(name==output_names_[j]) found[j]=true;
    }
    if(!found[0] || !found[1]) throw std::runtime_error("model outputs unavailable");
    const std::array<std::int64_t,3> shape{1,43844,1};
    tensor_=Ort::Value::CreateTensor<float>(memory_,window.data(),window.size(),shape.data(),shape.size());
    const auto start=std::chrono::steady_clock::now();auto warmed=predict();(void)warmed;
    warmup_ns=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count());
  }
  std::vector<Ort::Value> predict() {
    auto output=session_.Run(Ort::RunOptions{nullptr},input_names_.data(),&tensor_,1,output_names_.data(),2);
    for(const auto& value:output) {
      const auto info=value.GetTensorTypeAndShapeInfo();
      if(info.GetElementType()!=ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT ||
          info.GetShape()!=std::vector<std::int64_t>{1,cropped_readout_?2:172,88})
        throw std::runtime_error("model output shape/type mismatch");
    }
    return output;
  }
  const float* readout(const std::vector<Ort::Value>& output,std::size_t head,std::size_t frame) const {
    if(head>=2 || frame>=2) throw std::runtime_error("invalid model readout");
    return output[head].GetTensorData<float>()+((cropped_readout_?0:164)+frame)*88;
  }
  std::string finish_profile() {
    Ort::AllocatorWithDefaultOptions allocator;
    auto path=session_.EndProfilingAllocated(allocator);return path.get();
  }
  std::array<float,kWindow> window{};
  std::uint64_t warmup_ns{};
 private:
  Ort::Env env_;Ort::Session session_;Ort::MemoryInfo memory_;Ort::Value tensor_;
  bool cropped_readout_;
  const std::array<const char*,1> input_names_{"serving_default_input_2:0"};
  const std::array<const char*,2> output_names_{"StatefulPartitionedCall:1","StatefulPartitionedCall:2"};
};
} // namespace m3::neural
