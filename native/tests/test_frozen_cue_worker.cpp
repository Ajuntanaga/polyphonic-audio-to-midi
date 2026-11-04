#include "frozen_cue_worker.hpp"
#include "offline_c_allocation_guard.hpp"
#include "test_support.hpp"

#include <limits>
#include <thread>

namespace {
using namespace m3::offline;
}

M3_TEST(frozen_cue_queue_wrap_and_full_preserve_order) {
  FrozenCueQueue<std::uint64_t, 3U> queue;
  for (std::uint64_t round = 0U; round < 20U; ++round) {
    M3_EXPECT_TRUE(queue.front() == nullptr);
    for (std::uint64_t i = 0U; i < 3U; ++i) M3_EXPECT_TRUE(queue.push(round * 3U + i));
    M3_EXPECT_FALSE(queue.push(999U));
    for (std::uint64_t i = 0U; i < 3U; ++i) {
      M3_EXPECT_TRUE(queue.front() != nullptr);
      M3_EXPECT_EQ(*queue.front(), round * 3U + i);
      queue.pop();
    }
  }
}

M3_TEST(frozen_cue_queue_concurrent_payloads_keep_sequence) {
  struct Item { std::uint64_t sequence, inverse; };
  FrozenCueQueue<Item, 16U> queue;
  constexpr std::uint64_t kCount = 20000U;
  std::thread producer([&queue]() {
    for (std::uint64_t i = 0U; i < kCount; ++i) {
      while (!queue.push({i, ~i})) std::this_thread::yield();
    }
  });
  for (std::uint64_t i = 0U; i < kCount; ++i) {
    const Item* item = nullptr;
    while (!(item = queue.front())) std::this_thread::yield();
    M3_EXPECT_EQ(item->sequence, i);
    M3_EXPECT_EQ(item->inverse, ~i);
    queue.pop();
  }
  producer.join();
  M3_EXPECT_TRUE(queue.front() == nullptr);
}

M3_TEST(frozen_cue_delivery_causality_renewal_expiry_and_late_abstention) {
  FrozenCueInputQueue input;
  FrozenCueOutputQueue output;
  FrozenCueClient client(input, output);
  M3_EXPECT_TRUE(output.push({1U, 16512U, 17536U, {1U, 2U}}));
  M3_EXPECT_EQ(client.advance(16511U).mask[0U], 0U);
  M3_EXPECT_EQ(client.advance(16512U).mask[0U], 1U);
  M3_EXPECT_EQ(client.advance(17535U).mask[1U], 2U);
  M3_EXPECT_TRUE(output.push({1U, 17536U, 18560U, {4U, 8U}}));
  M3_EXPECT_EQ(client.advance(17536U).mask[0U], 4U);
  M3_EXPECT_EQ(client.advance(18560U).mask[0U], 0U);
  M3_EXPECT_TRUE(output.push({1U, 18560U, 19584U, {16U, 32U}}));
  M3_EXPECT_EQ(client.advance(18561U).mask[0U], 0U);
  M3_EXPECT_EQ(client.stats().late, 1U);
  M3_EXPECT_EQ(client.stats().accepted, 2U);
}

M3_TEST(frozen_cue_reset_and_input_overflow_reject_queued_old_generation) {
  FrozenCueInputQueue input;
  FrozenCueOutputQueue output;
  FrozenCueClient client(input, output);
  const float value = 0.0F;
  M3_EXPECT_TRUE(output.push({1U, 100U, 1124U, {1U, 0U}}));
  M3_EXPECT_EQ(client.advance(100U).mask[0U], 1U);
  for (std::size_t i = 0U; i < kCueQueueCapacity; ++i) {
    M3_EXPECT_TRUE(client.submit(&value, 1U, i));
  }
  M3_EXPECT_FALSE(client.submit(&value, 1U, 16U));
  M3_EXPECT_EQ(client.generation(), 2U);
  M3_EXPECT_EQ(client.advance(101U).mask[0U], 0U);
  M3_EXPECT_TRUE(output.push({1U, 0U, 1024U, {2U, 0U}}));
  client.reset();
  M3_EXPECT_TRUE(output.push({3U, 0U, 1024U, {4U, 0U}}));
  M3_EXPECT_EQ(client.advance(0U).mask[0U], 4U);
  M3_EXPECT_EQ(client.stats().stale, 1U);
  M3_EXPECT_EQ(client.stats().input_drops, 1U);
}

M3_TEST(frozen_cue_worker_overflow_then_reset_clears_measurement_history) {
  FrozenCueInputQueue input;
  FrozenCueOutputQueue output;
  FrozenCueClient client(input, output);
  FrozenCueWorker worker(input, output);
  M3_EXPECT_TRUE(worker.prepare());
  std::array<float, kCueMaximumBlock> zero{};
  for (std::size_t block = 0U; block < kCueQueueCapacity + 2U; ++block) {
    M3_EXPECT_TRUE(client.submit(zero.data(), zero.size(), block * zero.size()));
    M3_EXPECT_TRUE(worker.step());
  }
  M3_EXPECT_EQ(worker.stats().output_drops, 2U);
  client.reset();
  M3_EXPECT_EQ(client.advance(0U).mask[0U], 0U);
  M3_EXPECT_EQ(client.stats().stale, kCueQueueCapacity);
  M3_EXPECT_TRUE(client.submit(zero.data(), zero.size(), 0U));
  M3_EXPECT_TRUE(worker.step());
  const auto& current = client.advance(1024U + kCueWorkerDelay);
  M3_EXPECT_EQ(current.generation, client.generation());
  M3_EXPECT_EQ(current.begin, 1024U + kCueWorkerDelay);
  M3_EXPECT_EQ(current.mask[0U], 0U);
  M3_EXPECT_EQ(worker.stats().discontinuities, 1U);
}

M3_TEST(frozen_cue_worker_and_callback_do_not_allocate_and_bound_bad_input) {
  FrozenCueInputQueue input;
  FrozenCueOutputQueue output;
  FrozenCueClient client(input, output);
  FrozenCueWorker worker(input, output);
  M3_EXPECT_TRUE(worker.prepare());
  std::array<float, kCueMaximumBlock> zero{};
  const auto cpp = m3::test::allocation_count(), cpp_free = m3::test::deallocation_count();
  const auto c = m3::test::c_allocation_count(), c_free = m3::test::c_deallocation_count();
  for (std::size_t block = 0U; block < 20U; ++block) {
    const auto begin = block * zero.size();
    M3_EXPECT_TRUE(client.submit(zero.data(), zero.size(), begin));
    M3_EXPECT_TRUE(worker.step());
    for (std::size_t i = 0U; i < zero.size(); ++i) client.advance(begin + i);
  }
  M3_EXPECT_FALSE(client.submit(nullptr, 1U, 0U));
  M3_EXPECT_FALSE(client.submit(zero.data(), zero.size() + 1U, 0U));
  M3_EXPECT_FALSE(client.submit(zero.data(), 1U, std::numeric_limits<std::uint64_t>::max()));
  client.reset();
  client.advance(0U);
  M3_EXPECT_EQ(m3::test::allocation_count(), cpp);
  M3_EXPECT_EQ(m3::test::deallocation_count(), cpp_free);
  M3_EXPECT_EQ(m3::test::c_allocation_count(), c);
  M3_EXPECT_EQ(m3::test::c_deallocation_count(), c_free);
}
