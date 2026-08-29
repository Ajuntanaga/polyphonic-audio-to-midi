#include <new>

#include "test_support.hpp"

M3_TEST(test_allocator_counts_nothrow_new_and_matching_delete) {
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  int* value = new (std::nothrow) int{37};
  M3_EXPECT_TRUE(value != nullptr);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before + 1U);
  delete value;
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before + 1U);
}
