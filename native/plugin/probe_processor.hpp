#pragma once

#include <clap/clap.h>

#include <atomic>
#include <cstdint>

#include "midi_pipeline.hpp"

namespace m3 {

struct ProbeDiagnosticsSnapshot final {
  std::uint32_t create{};
  std::uint32_t init{};
  std::uint32_t activate{};
  std::uint32_t start{};
  std::uint32_t reset{};
  std::uint32_t stop{};
  std::uint32_t deactivate{};
  std::uint32_t destroy{};
  std::uint32_t trigger_one{};
  std::uint32_t trigger_two{};
  std::uint32_t trigger_overflow{};
  bool float32_seen{};
  bool float64_seen{};
  bool alias_seen{};
  bool separate_seen{};
  bool self_test_alias_passed{};
  bool self_test_separate_passed{};
};

class ProbeProcessor final {
 public:
  void record_create() noexcept;
  void record_init() noexcept;
  bool record_activate() noexcept;
  void record_start() noexcept;
  void record_reset() noexcept;
  void record_stop() noexcept;
  void record_deactivate() noexcept;
  void record_destroy() noexcept;
  void record_process(const clap_process_t& process) noexcept;

  bool queue_trigger_transitions(MidiPipeline& pipeline,
                                 const clap_input_events_t* input,
                                 std::uint32_t frames_count) noexcept;
  [[nodiscard]] ProbeDiagnosticsSnapshot snapshot() const noexcept;
  bool write_report() const noexcept;

 private:
  static bool dry_path_self_test(bool alias) noexcept;
  static bool buffers_alias(const clap_audio_buffer_t& input,
                            const clap_audio_buffer_t& output,
                            bool float32) noexcept;

  std::atomic<std::uint32_t> create_{};
  std::atomic<std::uint32_t> init_{};
  std::atomic<std::uint32_t> activate_{};
  std::atomic<std::uint32_t> start_{};
  std::atomic<std::uint32_t> reset_{};
  std::atomic<std::uint32_t> stop_{};
  std::atomic<std::uint32_t> deactivate_{};
  std::atomic<std::uint32_t> destroy_{};
  std::atomic<std::uint32_t> trigger_one_{};
  std::atomic<std::uint32_t> trigger_two_{};
  std::atomic<std::uint32_t> trigger_overflow_{};
  std::atomic<bool> float32_seen_{};
  std::atomic<bool> float64_seen_{};
  std::atomic<bool> alias_seen_{};
  std::atomic<bool> separate_seen_{};
  std::atomic<bool> self_test_alias_passed_{};
  std::atomic<bool> self_test_separate_passed_{};
  std::uint32_t next_sequence_{};
};

}  // namespace m3
