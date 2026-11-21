#include "lab_worker.hpp"
#include "ort_model.hpp"
#include <fstream>
#include <thread>

namespace m3::neural {
namespace {
std::array<double,kTaps> load_filter(const std::string& path) {
  std::array<double,kTaps> result{};std::ifstream file(path,std::ios::binary|std::ios::ate);
  if(!file || file.tellg()!=static_cast<std::streamoff>(sizeof(result)))
    throw std::runtime_error("invalid filter file");
  file.seekg(0);file.read(reinterpret_cast<char*>(result.data()),sizeof(result));
  if(!file || !std::all_of(result.begin(),result.end(),[](double x){return std::isfinite(x);}))
    throw std::runtime_error("invalid filter coefficients");
  return result;
}
struct Processor {
  explicit Processor(const std::array<double,kTaps>& h):resampler(h){}
  Resampler resampler;Window window;Decoder decoder;std::uint64_t consumed{};
};
}
struct Worker::Impl {
  Model model;std::array<double,kTaps> coefficients;Exchange exchange;
  LabEvidence* evidence;std::unique_ptr<Processor> processor;std::thread thread;
  Impl(const std::string& model_path,const std::string& filter,LabEvidence* log)
      :model(model_path.c_str()),coefficients(load_filter(filter)),evidence(log),
       processor(std::make_unique<Processor>(coefficients)) {
    if(evidence) evidence->warmup_ns=model.warmup_ns;
    thread=std::thread([this]{run();});
  }
  void run() noexcept {
    std::uint64_t epoch=1;
    try {
      std::array<float,147> converted{};
      while(!exchange.stop.load(std::memory_order_acquire)) {
        const auto requested=exchange.requested.load(std::memory_order_acquire);
        if(requested!=epoch) {
          processor=std::make_unique<Processor>(coefficients);epoch=requested;
          exchange.acknowledged.store(epoch,std::memory_order_release);
        }
        const auto* queued=exchange.input.front();
        if(!queued) {
          if(exchange.finish.load(std::memory_order_acquire)==epoch && !exchange.input.front())
            exchange.finished.store(epoch,std::memory_order_release);
          std::this_thread::sleep_for(std::chrono::microseconds(25));continue;
        }
        const auto packet=*queued;exchange.input.pop();
        if(packet.epoch!=epoch) continue;
        const auto& input=packet.input;auto& p=*processor;
        if(input.end!=p.consumed+input.count) throw std::runtime_error("source discontinuity");
        const auto began=monotonic_ns();
        const auto count=p.resampler.consume(input.data.data(),input.count,converted);
        p.window.append(converted.data(),count);Batch batch;batch.source_end=input.end;
        std::uint64_t model_time=0;
        if(p.window.ready()) {
          p.window.copy(model.window.data());const auto started=monotonic_ns();
          auto prediction=model.predict();model_time=monotonic_ns()-started;
          for(std::size_t j=0;j<2;++j) p.decoder.consume(
              prediction[0].GetTensorData<float>()+(164+j)*88,
              prediction[1].GetTensorData<float>()+(164+j)*88,batch);
          p.window.advance();if(evidence) ++evidence->calls;
        }
        p.consumed=input.end;batch.ready_ns=monotonic_ns();
        // A reset during inference invalidates the whole old batch.
        if(exchange.requested.load(std::memory_order_acquire)!=epoch) continue;
        if(batch.count && !exchange.output.push(EpochBatch{epoch,batch})) {
          if(evidence) ++evidence->output_drops;
          throw std::runtime_error("output queue overflow");
        }
        if(evidence) {
          evidence->consumed=input.end;
          evidence->timing.push_back({input.end,began-input.arrival_ns,batch.ready_ns-began,model_time});
          for(std::size_t i=0;i<batch.count;++i)
            evidence->generated.push_back({batch.events[i],batch.source_end,batch.ready_ns});
        }
      }
    } catch(const std::exception& e) {
      if(evidence) evidence->error=e.what();
      exchange.fatal.store(true,std::memory_order_release);
    } catch(...) {exchange.fatal.store(true,std::memory_order_release);}
  }
};
Worker::Worker(const std::string& model,const std::string& coefficients,LabEvidence* evidence)
    :impl_(std::make_unique<Impl>(model,coefficients,evidence)){}
Worker::~Worker(){stop();}
Exchange& Worker::exchange() noexcept {return impl_->exchange;}
void Worker::stop() noexcept {
  impl_->exchange.stop.store(true,std::memory_order_release);
  if(impl_->thread.joinable()) impl_->thread.join();
}
} // namespace m3::neural
