#pragma once

#include <cstddef>
#if defined(M3_OFFLINE_ALLOCATION_TRACE)
#include <array>
#include <cstdint>
#endif

namespace m3::test {

struct TestCase final {
  const char* name;
  void (*function)() noexcept;
  TestCase* next;
};

class Registration final {
 public:
  Registration(const char* name, void (*function)() noexcept) noexcept;
};

std::size_t allocation_count() noexcept;
std::size_t deallocation_count() noexcept;
#if defined(M3_OFFLINE_ALLOCATION_TRACE)
struct AllocationCallsite final {
  std::uintptr_t return_address{};
  std::size_t count{};
  std::size_t bytes{};
};
struct AllocationTrace final {
  std::array<AllocationCallsite, 64> sites{};
  std::size_t used{};
  std::size_t events{};
  std::size_t dropped{};
};
// Fixed storage on the replay thread; no stack unwinding or I/O while enabled.
void reset_allocation_trace() noexcept;
void set_allocation_trace_active(bool active) noexcept;
const AllocationTrace& allocation_trace() noexcept;
#endif
void expect_true(bool condition, const char* expression, const char* file,
                 int line) noexcept;
void expect_near(double actual, double expected, double tolerance,
                 const char* expression, const char* file, int line) noexcept;
int run_all_tests() noexcept;

}  // namespace m3::test

#define M3_TEST(name)                                                        \
  static void name() noexcept;                                               \
  static ::m3::test::Registration registration_##name{#name, &name};         \
  static void name() noexcept

#define M3_EXPECT_TRUE(expression)                                           \
  ::m3::test::expect_true(static_cast<bool>(expression), #expression,        \
                          __FILE__, __LINE__)

#define M3_EXPECT_FALSE(expression) M3_EXPECT_TRUE(!(expression))

#define M3_EXPECT_EQ(actual, expected)                                       \
  do {                                                                       \
    const auto m3_actual = (actual);                                         \
    const auto m3_expected = (expected);                                     \
    ::m3::test::expect_true(m3_actual == m3_expected,                        \
                            #actual " == " #expected, __FILE__, __LINE__);   \
  } while (false)

#define M3_EXPECT_NEAR(actual, expected, tolerance)                          \
  ::m3::test::expect_near(static_cast<double>(actual),                       \
                          static_cast<double>(expected),                     \
                          static_cast<double>(tolerance),                    \
                          #actual " ~= " #expected, __FILE__, __LINE__)
