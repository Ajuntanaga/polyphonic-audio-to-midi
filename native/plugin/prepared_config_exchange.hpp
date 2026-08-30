#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

#include "m3/types.hpp"

namespace m3 {

static_assert(std::atomic<std::uint64_t>::is_always_lock_free,
              "64-bit configuration atomics must be lock-free");
static_assert(std::atomic<std::uint32_t>::is_always_lock_free,
              "32-bit slot-state atomics must be lock-free");

bool generation_newer(std::uint64_t candidate,
                      std::uint64_t reference) noexcept;

struct ConfigRequestSnapshot final {
  PersistentConfig config{};
  std::uint64_t generation{};
};

class AtomicConfigRequest final {
 public:
  explicit AtomicConfigRequest(const PersistentConfig& initial = {},
                               std::uint64_t generation = 0) noexcept;
  AtomicConfigRequest(const AtomicConfigRequest&) = delete;
  AtomicConfigRequest& operator=(const AtomicConfigRequest&) = delete;

  bool publish(const PersistentConfig& config,
               std::uint64_t generation) noexcept;
  void reset(const PersistentConfig& config,
             std::uint64_t generation) noexcept;
  bool snapshot(ConfigRequestSnapshot& destination,
                std::uint32_t maximum_attempts = 3) const noexcept;

#if defined(M3_TESTING)
  bool hold_writer_for_test() noexcept;
  void release_writer_for_test() noexcept;
#endif

 private:
  static constexpr std::size_t kFieldCount = 14;
  void store_fields(const PersistentConfig& config) noexcept;
  PersistentConfig load_fields() const noexcept;

  mutable std::atomic<std::uint64_t> sequence_{0};
  std::array<std::atomic<std::uint64_t>, kFieldCount> fields_{};
  std::atomic<std::uint64_t> generation_{0};
};

struct PreparedConfig final {
  PersistentConfig requested{};
  double sample_rate{};
  double sample_period{};
  double decision_period{};
#if defined(M3_TESTING)
  // A wide payload makes torn-slot observations deterministic under stress.
  // Production builds contain only real prepared fields.
  std::array<std::uint64_t, 64> coherence_words{};
#endif
};

bool stage_prepared_config(const PersistentConfig& requested,
                           double sample_rate,
                           PreparedConfig& destination) noexcept;
bool structural_config_equal(const PersistentConfig& left,
                             const PersistentConfig& right) noexcept;
void copy_structural_config(PersistentConfig& destination,
                            const PersistentConfig& source) noexcept;
void copy_runtime_config(PersistentConfig& destination,
                         const PersistentConfig& source) noexcept;

#if defined(M3_TESTING)
[[nodiscard]] std::size_t prepared_config_stage_count_for_test() noexcept;
#endif

enum class PreparedSlotState : std::uint32_t {
  free,
  writing,
  ready,
  audio_claimed,
  active,
};

class PreparedConfigExchange final {
 public:
  struct Claim final {
    const PreparedConfig* config{};
    std::uint64_t generation{};

   private:
    friend class PreparedConfigExchange;
    std::uint32_t index{kSlotCount};
  };

  PreparedConfigExchange() noexcept = default;
  PreparedConfigExchange(const PreparedConfigExchange&) = delete;
  PreparedConfigExchange& operator=(const PreparedConfigExchange&) = delete;

  bool initialize(const PreparedConfig& initial,
                  std::uint64_t generation) noexcept;
  void reset() noexcept;

  // Main-thread producer operations.
  bool publish(const PreparedConfig& prepared,
               std::uint64_t generation) noexcept;

  // Audio-thread consumer operations. These never wait.
  bool claim_latest(Claim& claim) noexcept;
  bool commit(Claim& claim) noexcept;
  bool cancel(Claim& claim) noexcept;

  const PreparedConfig& active() const noexcept;
  std::uint64_t active_generation() const noexcept {
    return active_generation_;
  }

 private:
  static constexpr std::uint32_t kSlotCount = 3;
  struct Slot final {
    PreparedConfig prepared{};
    std::atomic<std::uint64_t> generation{0};
    std::atomic<std::uint32_t> state{
        static_cast<std::uint32_t>(PreparedSlotState::free)};
  };

  static std::uint32_t state_value(PreparedSlotState state) noexcept {
    return static_cast<std::uint32_t>(state);
  }
  bool claim_state(std::uint32_t index, PreparedSlotState expected,
                   PreparedSlotState desired) noexcept;
  void invalidate(Claim& claim) const noexcept;
  void reclaim_stale_ready() noexcept;

  std::array<Slot, kSlotCount> slots_{};
  std::uint32_t active_index_{};
  std::uint64_t active_generation_{};
  std::uint64_t publisher_generation_{};
  bool initialized_{};
};

}  // namespace m3
