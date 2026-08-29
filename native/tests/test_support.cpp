#include "test_support.hpp"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <new>

namespace {

std::atomic<std::size_t> allocations{0};
std::atomic<std::size_t> deallocations{0};
std::size_t failures = 0;
m3::test::TestCase* tests = nullptr;

void* allocate(std::size_t size) noexcept {
  allocations.fetch_add(1, std::memory_order_relaxed);
  if (void* memory = std::malloc(size == 0 ? 1 : size)) {
    return memory;
  }
  std::abort();
}

void* allocate_aligned(std::size_t size, std::size_t alignment) noexcept {
  allocations.fetch_add(1, std::memory_order_relaxed);
  void* memory = nullptr;
  if (posix_memalign(&memory, alignment, size == 0 ? alignment : size) == 0) {
    return memory;
  }
  std::abort();
}

void release(void* memory) noexcept {
  if (memory != nullptr) {
    deallocations.fetch_add(1, std::memory_order_relaxed);
    std::free(memory);
  }
}

}  // namespace

void* operator new(std::size_t size) { return allocate(size); }
void* operator new[](std::size_t size) { return allocate(size); }
void operator delete(void* memory) noexcept { release(memory); }
void operator delete[](void* memory) noexcept { release(memory); }
void operator delete(void* memory, std::size_t) noexcept { release(memory); }
void operator delete[](void* memory, std::size_t) noexcept { release(memory); }
void* operator new(std::size_t size, std::align_val_t alignment) {
  return allocate_aligned(size, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t size, std::align_val_t alignment) {
  return allocate_aligned(size, static_cast<std::size_t>(alignment));
}
void operator delete(void* memory, std::align_val_t) noexcept { release(memory); }
void operator delete[](void* memory, std::align_val_t) noexcept { release(memory); }
void operator delete(void* memory, std::size_t, std::align_val_t) noexcept {
  release(memory);
}
void operator delete[](void* memory, std::size_t, std::align_val_t) noexcept {
  release(memory);
}

namespace m3::test {

Registration::Registration(const char* name, void (*function)() noexcept) noexcept {
  static TestCase storage[256]{};
  static std::size_t count = 0;
  if (count >= 256) {
    std::abort();
  }
  TestCase& test = storage[count++];
  test = TestCase{name, function, tests};
  tests = &test;
}

std::size_t allocation_count() noexcept {
  return allocations.load(std::memory_order_relaxed);
}

std::size_t deallocation_count() noexcept {
  return deallocations.load(std::memory_order_relaxed);
}

void expect_true(bool condition, const char* expression, const char* file,
                 int line) noexcept {
  if (!condition) {
    ++failures;
    std::fprintf(stderr, "%s:%d: expectation failed: %s\n", file, line,
                 expression);
  }
}

void expect_near(double actual, double expected, double tolerance,
                 const char* expression, const char* file, int line) noexcept {
  const double difference = actual >= expected ? actual - expected : expected - actual;
  expect_true(difference <= tolerance, expression, file, line);
}

int run_all_tests() noexcept {
  std::size_t count = 0;
  for (TestCase* test = tests; test != nullptr; test = test->next) {
    ++count;
    std::fprintf(stdout, "[ RUN      ] %s\n", test->name);
    const std::size_t before = failures;
    test->function();
    std::fprintf(stdout, before == failures ? "[       OK ] %s\n"
                                            : "[  FAILED  ] %s\n",
                 test->name);
  }
  std::fprintf(stdout, "Ran %zu tests: %zu failure(s)\n", count, failures);
  return failures == 0 ? 0 : 1;
}

}  // namespace m3::test
