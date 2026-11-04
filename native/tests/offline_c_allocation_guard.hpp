#pragma once
#include <cstddef>

namespace m3::test {
// GNU linker wrappers for the standalone test executable only.
std::size_t c_allocation_count() noexcept;
std::size_t c_deallocation_count() noexcept;
}
