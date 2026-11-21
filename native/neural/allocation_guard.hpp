#pragma once
#include <cstddef>
namespace m3::neural {
struct Allocations {std::size_t allocations{},deallocations{};};
void begin_callback_allocations() noexcept;
Allocations end_callback_allocations() noexcept;
}
