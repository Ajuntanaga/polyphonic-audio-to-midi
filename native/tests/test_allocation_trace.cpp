#include "test_support.hpp"

#include <new>

M3_TEST(allocation_trace_captures_all_new_overloads_only_inside_scope) {
  m3::test::reset_allocation_trace();
  void* outside = ::operator new(7);
  ::operator delete(outside);
  M3_EXPECT_EQ(m3::test::allocation_trace().events, 0U);
  const auto before = m3::test::allocation_count();
  m3::test::set_allocation_trace_active(true);
  void* pointers[] = {
      ::operator new(16), ::operator new[](16),
      ::operator new(16, std::nothrow), ::operator new[](16, std::nothrow),
      ::operator new(16, std::align_val_t{64}),
      ::operator new[](16, std::align_val_t{64}),
      ::operator new(16, std::align_val_t{64}, std::nothrow),
      ::operator new[](16, std::align_val_t{64}, std::nothrow)};
  m3::test::set_allocation_trace_active(false);
  const auto after = m3::test::allocation_count();
  const auto& trace = m3::test::allocation_trace();
  M3_EXPECT_EQ(after - before, 8U);
  M3_EXPECT_EQ(trace.events, 8U);
  M3_EXPECT_EQ(trace.dropped, 0U);
  std::size_t count = 0, bytes = 0;
  for (std::size_t index = 0; index < trace.used; ++index) {
    M3_EXPECT_TRUE(trace.sites[index].return_address != 0U);
    count += trace.sites[index].count;
    bytes += trace.sites[index].bytes;
  }
  M3_EXPECT_EQ(count, 8U);
  M3_EXPECT_EQ(bytes, 128U);
  ::operator delete(pointers[0]);
  ::operator delete[](pointers[1]);
  ::operator delete(pointers[2], std::nothrow);
  ::operator delete[](pointers[3], std::nothrow);
  ::operator delete(pointers[4], std::align_val_t{64});
  ::operator delete[](pointers[5], std::align_val_t{64});
  ::operator delete(pointers[6], std::align_val_t{64}, std::nothrow);
  ::operator delete[](pointers[7], std::align_val_t{64}, std::nothrow);
  m3::test::reset_allocation_trace();
  M3_EXPECT_EQ(m3::test::allocation_trace().events, 0U);
  M3_EXPECT_EQ(m3::test::allocation_trace().used, 0U);
}
