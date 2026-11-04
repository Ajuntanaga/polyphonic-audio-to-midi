#include "offline_c_allocation_guard.hpp"
#include <atomic>

namespace {
std::atomic<std::size_t> allocations{}, deallocations{};
}

extern "C" {
void* __real_malloc(std::size_t);
void* __real_calloc(std::size_t, std::size_t);
void* __real_realloc(void*, std::size_t);
void* __real_aligned_alloc(std::size_t, std::size_t);
int __real_posix_memalign(void**, std::size_t, std::size_t);
void __real_free(void*);

void* __wrap_malloc(std::size_t bytes) {
  allocations.fetch_add(1U, std::memory_order_relaxed);
  return __real_malloc(bytes);
}
void* __wrap_calloc(std::size_t count, std::size_t bytes) {
  allocations.fetch_add(1U, std::memory_order_relaxed);
  return __real_calloc(count, bytes);
}
void* __wrap_realloc(void* pointer, std::size_t bytes) {
  allocations.fetch_add(1U, std::memory_order_relaxed);
  if (pointer) deallocations.fetch_add(1U, std::memory_order_relaxed);
  return __real_realloc(pointer, bytes);
}
void* __wrap_aligned_alloc(std::size_t alignment, std::size_t bytes) {
  allocations.fetch_add(1U, std::memory_order_relaxed);
  return __real_aligned_alloc(alignment, bytes);
}
int __wrap_posix_memalign(void** pointer, std::size_t alignment, std::size_t bytes) {
  allocations.fetch_add(1U, std::memory_order_relaxed);
  return __real_posix_memalign(pointer, alignment, bytes);
}
void __wrap_free(void* pointer) {
  if (pointer) deallocations.fetch_add(1U, std::memory_order_relaxed);
  __real_free(pointer);
}
}

namespace m3::test {
std::size_t c_allocation_count() noexcept { return allocations.load(std::memory_order_relaxed); }
std::size_t c_deallocation_count() noexcept { return deallocations.load(std::memory_order_relaxed); }
}
