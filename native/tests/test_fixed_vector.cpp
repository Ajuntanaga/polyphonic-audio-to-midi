#include "m3/fixed_vector.hpp"

#include "test_support.hpp"

M3_TEST(fixed_vector_zero_capacity_rejects_insertions) {
  m3::FixedVector<int, 0> values;
  M3_EXPECT_EQ(values.size(), 0U);
  M3_EXPECT_EQ(values.capacity(), 0U);
  M3_EXPECT_FALSE(values.push_back(7));
  M3_EXPECT_TRUE(values.begin() == values.end());
}

M3_TEST(fixed_vector_preserves_order_and_rejects_overflow) {
  m3::FixedVector<int, 3> values;
  M3_EXPECT_TRUE(values.push_back(7));
  M3_EXPECT_TRUE(values.push_back(11));
  M3_EXPECT_TRUE(values.push_back(13));
  M3_EXPECT_FALSE(values.push_back(17));
  M3_EXPECT_EQ(values.size(), 3U);
  M3_EXPECT_EQ(values[0], 7);
  M3_EXPECT_EQ(values[1], 11);
  M3_EXPECT_EQ(values[2], 13);
  M3_EXPECT_TRUE(values.begin() + 3 == values.end());
}

M3_TEST(fixed_vector_clear_reuses_storage_without_heap_work) {
  m3::FixedVector<int, 2> values;
  M3_EXPECT_TRUE(values.push_back(23));
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  values.clear();
  M3_EXPECT_EQ(values.size(), 0U);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  M3_EXPECT_TRUE(values.push_back(29));
  M3_EXPECT_EQ(values[0], 29);
}
