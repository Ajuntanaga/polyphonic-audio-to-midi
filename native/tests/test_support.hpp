#pragma once

#include <cstddef>

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
