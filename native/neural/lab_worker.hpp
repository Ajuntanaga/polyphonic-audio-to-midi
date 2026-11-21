#pragma once
#include "lab_bridge.hpp"
#include <memory>
#include <string>
#include <vector>

namespace m3::neural {
struct Generated {Event event{};std::uint64_t source_end{},ready_ns{};};
struct WorkerTiming {
  std::uint64_t source_end{},queued_ns{},service_ns{},model_ns{};
};
struct GateObservation {
  std::uint64_t source_end{},frame{};double power{};bool enabled{},open{};
};
// Evidence is optional and only written by the worker, read after stop/join.
struct LabEvidence {
  std::vector<Generated> generated;
  std::vector<WorkerTiming> timing;
  std::vector<GateObservation> gate;
  std::uint64_t consumed{},calls{},output_drops{},warmup_ns{};
  std::uint64_t gate_closed_frames{},gate_forced_releases{};
  std::string error;
};
class Worker {
 public:
  Worker(const std::string& model,const std::string& coefficients,LabEvidence* evidence=nullptr);
  ~Worker();
  Worker(const Worker&)=delete;Worker& operator=(const Worker&)=delete;
  Exchange& exchange() noexcept;
  void stop() noexcept;
 private:
  struct Impl;std::unique_ptr<Impl> impl_;
};
} // namespace m3::neural
