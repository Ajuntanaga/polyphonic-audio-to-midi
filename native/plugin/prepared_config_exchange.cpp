#include "prepared_config_exchange.hpp"

#include <cmath>
#include <cstring>
#include <limits>

namespace {

constexpr std::size_t kDetectorInput = 0;
constexpr std::size_t kProfileMode = 1;
constexpr std::size_t kA4Hz = 2;
constexpr std::size_t kInputTrimDb = 3;
constexpr std::size_t kSensitivity = 4;
constexpr std::size_t kResponse = 5;
constexpr std::size_t kLowestNote = 6;
constexpr std::size_t kHighestNote = 7;
constexpr std::size_t kMaxPolyphony = 8;
constexpr std::size_t kMaxFret = 9;
constexpr std::size_t kVelocityMode = 10;
constexpr std::size_t kFixedVelocity = 11;
constexpr std::size_t kMidiChannel = 12;
constexpr std::size_t kDryPassthrough = 13;

std::uint64_t double_bits(double value) noexcept {
  static_assert(sizeof(double) == sizeof(std::uint64_t));
  std::uint64_t bits = 0;
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

double bits_double(std::uint64_t bits) noexcept {
  double value = 0.0;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

}  // namespace

namespace m3 {

bool generation_newer(std::uint64_t candidate,
                      std::uint64_t reference) noexcept {
  constexpr std::uint64_t kHalfRange = std::uint64_t{1} << 63U;
  const std::uint64_t distance = candidate - reference;
  return distance != 0U && distance < kHalfRange;
}

AtomicConfigRequest::AtomicConfigRequest(const PersistentConfig& initial,
                                         std::uint64_t generation) noexcept {
  store_fields(initial);
  generation_.store(generation, std::memory_order_relaxed);
}

void AtomicConfigRequest::store_fields(
    const PersistentConfig& config) noexcept {
  fields_[kDetectorInput].store(static_cast<std::uint64_t>(config.detector_input),
                                std::memory_order_relaxed);
  fields_[kProfileMode].store(static_cast<std::uint64_t>(config.profile_mode),
                              std::memory_order_relaxed);
  fields_[kA4Hz].store(double_bits(config.a4_hz), std::memory_order_relaxed);
  fields_[kInputTrimDb].store(double_bits(config.input_trim_db),
                              std::memory_order_relaxed);
  fields_[kSensitivity].store(config.sensitivity, std::memory_order_relaxed);
  fields_[kResponse].store(config.response, std::memory_order_relaxed);
  fields_[kLowestNote].store(config.lowest_note, std::memory_order_relaxed);
  fields_[kHighestNote].store(config.highest_note, std::memory_order_relaxed);
  fields_[kMaxPolyphony].store(config.max_polyphony, std::memory_order_relaxed);
  fields_[kMaxFret].store(config.max_fret, std::memory_order_relaxed);
  fields_[kVelocityMode].store(static_cast<std::uint64_t>(config.velocity_mode),
                               std::memory_order_relaxed);
  fields_[kFixedVelocity].store(config.fixed_velocity,
                                std::memory_order_relaxed);
  fields_[kMidiChannel].store(config.midi_channel, std::memory_order_relaxed);
  fields_[kDryPassthrough].store(config.dry_passthrough ? 1U : 0U,
                                 std::memory_order_relaxed);
}

PersistentConfig AtomicConfigRequest::load_fields() const noexcept {
  PersistentConfig config;
  config.detector_input = static_cast<DetectorInput>(
      fields_[kDetectorInput].load(std::memory_order_relaxed));
  config.profile_mode = static_cast<ProfileMode>(
      fields_[kProfileMode].load(std::memory_order_relaxed));
  config.a4_hz = bits_double(fields_[kA4Hz].load(std::memory_order_relaxed));
  config.input_trim_db =
      bits_double(fields_[kInputTrimDb].load(std::memory_order_relaxed));
  config.sensitivity = static_cast<std::uint8_t>(
      fields_[kSensitivity].load(std::memory_order_relaxed));
  config.response = static_cast<std::uint8_t>(
      fields_[kResponse].load(std::memory_order_relaxed));
  config.lowest_note = static_cast<std::uint8_t>(
      fields_[kLowestNote].load(std::memory_order_relaxed));
  config.highest_note = static_cast<std::uint8_t>(
      fields_[kHighestNote].load(std::memory_order_relaxed));
  config.max_polyphony = static_cast<std::uint8_t>(
      fields_[kMaxPolyphony].load(std::memory_order_relaxed));
  config.max_fret = static_cast<std::uint8_t>(
      fields_[kMaxFret].load(std::memory_order_relaxed));
  config.velocity_mode = static_cast<VelocityMode>(
      fields_[kVelocityMode].load(std::memory_order_relaxed));
  config.fixed_velocity = static_cast<std::uint8_t>(
      fields_[kFixedVelocity].load(std::memory_order_relaxed));
  config.midi_channel = static_cast<std::uint8_t>(
      fields_[kMidiChannel].load(std::memory_order_relaxed));
  config.dry_passthrough =
      fields_[kDryPassthrough].load(std::memory_order_relaxed) != 0U;
  return config;
}

bool AtomicConfigRequest::publish(const PersistentConfig& config,
                                  std::uint64_t generation) noexcept {
  std::uint64_t sequence = sequence_.load(std::memory_order_acquire);
  if ((sequence & 1U) != 0U ||
      !sequence_.compare_exchange_strong(sequence, sequence + 1U,
                                         std::memory_order_acq_rel,
                                         std::memory_order_acquire)) {
    return false;
  }

  const std::uint64_t current_generation =
      generation_.load(std::memory_order_relaxed);
  if (!generation_newer(generation, current_generation)) {
    sequence_.store(sequence + 2U, std::memory_order_release);
    return false;
  }
  store_fields(config);
  generation_.store(generation, std::memory_order_relaxed);
  sequence_.store(sequence + 2U, std::memory_order_release);
  return true;
}

bool AtomicConfigRequest::snapshot(ConfigRequestSnapshot& destination,
                                   std::uint32_t maximum_attempts) const noexcept {
  for (std::uint32_t attempt = 0; attempt < maximum_attempts; ++attempt) {
    const std::uint64_t before = sequence_.load(std::memory_order_acquire);
    if ((before & 1U) != 0U) {
      continue;
    }
    ConfigRequestSnapshot candidate;
    candidate.generation = generation_.load(std::memory_order_relaxed);
    candidate.config = load_fields();
    const std::uint64_t after = sequence_.load(std::memory_order_acquire);
    if (before == after && (after & 1U) == 0U) {
      destination = candidate;
      return true;
    }
  }
  return false;
}

#if defined(M3_TESTING)
bool AtomicConfigRequest::hold_writer_for_test() noexcept {
  std::uint64_t sequence = sequence_.load(std::memory_order_acquire);
  return (sequence & 1U) == 0U &&
         sequence_.compare_exchange_strong(sequence, sequence + 1U,
                                           std::memory_order_acq_rel,
                                           std::memory_order_acquire);
}

void AtomicConfigRequest::release_writer_for_test() noexcept {
  const std::uint64_t sequence = sequence_.load(std::memory_order_relaxed);
  if ((sequence & 1U) != 0U) {
    sequence_.store(sequence + 1U, std::memory_order_release);
  }
}
#endif

bool stage_prepared_config(const PersistentConfig& requested,
                           double sample_rate,
                           PreparedConfig& destination) noexcept {
  if (!std::isfinite(sample_rate) || sample_rate <= 0.0 ||
      static_cast<std::uint8_t>(requested.detector_input) > 2U ||
      static_cast<std::uint8_t>(requested.profile_mode) > 1U ||
      static_cast<std::uint8_t>(requested.velocity_mode) > 1U) {
    return false;
  }
  destination = {};
  destination.requested = requested;
  destination.sample_rate = sample_rate;
  return true;
}

bool structural_config_equal(const PersistentConfig& left,
                             const PersistentConfig& right) noexcept {
  return left.detector_input == right.detector_input &&
         left.profile_mode == right.profile_mode && left.a4_hz == right.a4_hz &&
         left.lowest_note == right.lowest_note &&
         left.highest_note == right.highest_note &&
         left.max_polyphony == right.max_polyphony &&
         left.max_fret == right.max_fret &&
         left.midi_channel == right.midi_channel;
}

void copy_structural_config(PersistentConfig& destination,
                            const PersistentConfig& source) noexcept {
  destination.detector_input = source.detector_input;
  destination.profile_mode = source.profile_mode;
  destination.a4_hz = source.a4_hz;
  destination.lowest_note = source.lowest_note;
  destination.highest_note = source.highest_note;
  destination.max_polyphony = source.max_polyphony;
  destination.max_fret = source.max_fret;
  destination.midi_channel = source.midi_channel;
}

void copy_runtime_config(PersistentConfig& destination,
                         const PersistentConfig& source) noexcept {
  destination.input_trim_db = source.input_trim_db;
  destination.sensitivity = source.sensitivity;
  destination.response = source.response;
  destination.velocity_mode = source.velocity_mode;
  destination.fixed_velocity = source.fixed_velocity;
  destination.dry_passthrough = source.dry_passthrough;
}

bool PreparedConfigExchange::initialize(const PreparedConfig& initial,
                                        std::uint64_t generation) noexcept {
  reset();
  slots_[0].prepared = initial;
  slots_[0].generation.store(generation, std::memory_order_relaxed);
  slots_[0].state.store(state_value(PreparedSlotState::active),
                        std::memory_order_release);
  active_index_ = 0;
  active_generation_ = generation;
  publisher_generation_ = generation;
  initialized_ = true;
  return true;
}

void PreparedConfigExchange::reset() noexcept {
  for (Slot& slot : slots_) {
    slot.state.store(state_value(PreparedSlotState::free),
                     std::memory_order_relaxed);
    slot.generation.store(0, std::memory_order_relaxed);
  }
  active_index_ = 0;
  active_generation_ = 0;
  publisher_generation_ = 0;
  initialized_ = false;
}

bool PreparedConfigExchange::claim_state(std::uint32_t index,
                                         PreparedSlotState expected,
                                         PreparedSlotState desired) noexcept {
  std::uint32_t expected_value = state_value(expected);
  return slots_[index].state.compare_exchange_strong(
      expected_value, state_value(desired), std::memory_order_acq_rel,
      std::memory_order_acquire);
}

bool PreparedConfigExchange::publish(const PreparedConfig& prepared,
                                     std::uint64_t generation) noexcept {
  if (!initialized_ || !generation_newer(generation, publisher_generation_)) {
    return false;
  }

  for (std::uint32_t attempt = 0; attempt < kSlotCount; ++attempt) {
    std::uint32_t selected = kSlotCount;
    for (std::uint32_t index = 0; index < kSlotCount; ++index) {
      if (slots_[index].state.load(std::memory_order_acquire) ==
          state_value(PreparedSlotState::free)) {
        selected = index;
        break;
      }
    }

    PreparedSlotState expected = PreparedSlotState::free;
    if (selected == kSlotCount) {
      std::uint64_t oldest_generation = 0;
      bool found = false;
      for (std::uint32_t index = 0; index < kSlotCount; ++index) {
        if (slots_[index].state.load(std::memory_order_acquire) !=
            state_value(PreparedSlotState::ready)) {
          continue;
        }
        const std::uint64_t slot_generation =
            slots_[index].generation.load(std::memory_order_relaxed);
        if (!found || generation_newer(oldest_generation, slot_generation)) {
          selected = index;
          oldest_generation = slot_generation;
          found = true;
        }
      }
      if (!found) {
        return false;
      }
      expected = PreparedSlotState::ready;
    }

    if (!claim_state(selected, expected, PreparedSlotState::writing)) {
      continue;
    }
    slots_[selected].prepared = prepared;
    slots_[selected].generation.store(generation, std::memory_order_relaxed);
    slots_[selected].state.store(state_value(PreparedSlotState::ready),
                                 std::memory_order_release);
    publisher_generation_ = generation;
    return true;
  }
  return false;
}

void PreparedConfigExchange::invalidate(Claim& claim) const noexcept {
  claim.config = nullptr;
  claim.generation = 0;
  claim.index = kSlotCount;
}

bool PreparedConfigExchange::claim_latest(Claim& claim) noexcept {
  invalidate(claim);
  if (!initialized_) {
    return false;
  }

  for (std::uint32_t attempt = 0; attempt < kSlotCount; ++attempt) {
    std::uint32_t selected = kSlotCount;
    std::uint64_t newest_generation = active_generation_;
    for (std::uint32_t index = 0; index < kSlotCount; ++index) {
      if (slots_[index].state.load(std::memory_order_acquire) !=
          state_value(PreparedSlotState::ready)) {
        continue;
      }
      const std::uint64_t slot_generation =
          slots_[index].generation.load(std::memory_order_relaxed);
      if (generation_newer(slot_generation, newest_generation)) {
        selected = index;
        newest_generation = slot_generation;
      }
    }
    if (selected == kSlotCount) {
      reclaim_stale_ready();
      return false;
    }
    if (!claim_state(selected, PreparedSlotState::ready,
                     PreparedSlotState::audio_claimed)) {
      continue;
    }

    // A ready slot can be replaced and become ready again between the scan and
    // this CAS. Re-read its generation only after ownership is acquired so the
    // claim cannot pair an old tag with a newly written payload.
    const std::uint64_t claimed_generation =
        slots_[selected].generation.load(std::memory_order_relaxed);
    if (!generation_newer(claimed_generation, active_generation_)) {
      slots_[selected].state.store(state_value(PreparedSlotState::free),
                                   std::memory_order_release);
      continue;
    }

    bool newer_ready = false;
    for (std::uint32_t index = 0; index < kSlotCount; ++index) {
      if (slots_[index].state.load(std::memory_order_acquire) ==
              state_value(PreparedSlotState::ready) &&
          generation_newer(
              slots_[index].generation.load(std::memory_order_relaxed),
              claimed_generation)) {
        newer_ready = true;
        break;
      }
    }
    if (newer_ready) {
      slots_[selected].state.store(state_value(PreparedSlotState::ready),
                                   std::memory_order_release);
      continue;
    }

    claim.config = &slots_[selected].prepared;
    claim.generation = claimed_generation;
    claim.index = selected;
    return true;
  }
  return false;
}

void PreparedConfigExchange::reclaim_stale_ready() noexcept {
  for (std::uint32_t index = 0; index < kSlotCount; ++index) {
    if (slots_[index].state.load(std::memory_order_acquire) !=
        state_value(PreparedSlotState::ready)) {
      continue;
    }
    if (!claim_state(index, PreparedSlotState::ready,
                     PreparedSlotState::audio_claimed)) {
      continue;
    }
    // As in claim_latest(), ownership must precede the generation decision;
    // otherwise a ready -> writing -> ready replacement is an ABA window.
    const std::uint64_t slot_generation =
        slots_[index].generation.load(std::memory_order_relaxed);
    slots_[index].state.store(
        state_value(generation_newer(slot_generation, active_generation_)
                        ? PreparedSlotState::ready
                        : PreparedSlotState::free),
        std::memory_order_release);
  }
}

bool PreparedConfigExchange::commit(Claim& claim) noexcept {
  if (!initialized_ || claim.index >= kSlotCount || claim.config == nullptr ||
      slots_[claim.index].state.load(std::memory_order_acquire) !=
          state_value(PreparedSlotState::audio_claimed) ||
      slots_[claim.index].generation.load(std::memory_order_relaxed) !=
          claim.generation ||
      !generation_newer(claim.generation, active_generation_)) {
    return false;
  }
  slots_[active_index_].state.store(state_value(PreparedSlotState::free),
                                    std::memory_order_release);
  slots_[claim.index].state.store(state_value(PreparedSlotState::active),
                                  std::memory_order_release);
  active_index_ = claim.index;
  active_generation_ = claim.generation;
  invalidate(claim);
  reclaim_stale_ready();
  return true;
}

bool PreparedConfigExchange::cancel(Claim& claim) noexcept {
  if (!initialized_ || claim.index >= kSlotCount || claim.config == nullptr ||
      slots_[claim.index].state.load(std::memory_order_acquire) !=
          state_value(PreparedSlotState::audio_claimed) ||
      slots_[claim.index].generation.load(std::memory_order_relaxed) !=
          claim.generation) {
    return false;
  }
  slots_[claim.index].state.store(state_value(PreparedSlotState::ready),
                                  std::memory_order_release);
  invalidate(claim);
  return true;
}

const PreparedConfig& PreparedConfigExchange::active() const noexcept {
  return slots_[active_index_].prepared;
}

}  // namespace m3
