#pragma once

#include <array>
#include <cstddef>
#include <utility>

namespace m3 {

template <typename T, std::size_t Capacity>
class FixedVector final {
 public:
  using iterator = typename std::array<T, Capacity>::iterator;
  using const_iterator = typename std::array<T, Capacity>::const_iterator;

  constexpr bool push_back(const T& value) noexcept {
    if (size_ >= Capacity) {
      return false;
    }
    storage_[size_++] = value;
    return true;
  }

  constexpr bool push_back(T&& value) noexcept {
    if (size_ >= Capacity) {
      return false;
    }
    storage_[size_++] = std::move(value);
    return true;
  }

  constexpr void clear() noexcept { size_ = 0; }
  [[nodiscard]] constexpr std::size_t size() const noexcept { return size_; }
  [[nodiscard]] static constexpr std::size_t capacity() noexcept {
    return Capacity;
  }

  constexpr T& operator[](std::size_t index) noexcept {
    if (index >= size_) {
      __builtin_trap();
    }
    return storage_[index];
  }

  constexpr const T& operator[](std::size_t index) const noexcept {
    if (index >= size_) {
      __builtin_trap();
    }
    return storage_[index];
  }

  constexpr iterator begin() noexcept { return storage_.begin(); }
  constexpr const_iterator begin() const noexcept { return storage_.begin(); }
  constexpr iterator end() noexcept {
    if constexpr (Capacity == 0) {
      return storage_.end();
    }
    return storage_.begin() + static_cast<std::ptrdiff_t>(size_);
  }
  constexpr const_iterator end() const noexcept {
    if constexpr (Capacity == 0) {
      return storage_.end();
    }
    return storage_.begin() + static_cast<std::ptrdiff_t>(size_);
  }

 private:
  std::array<T, Capacity> storage_{};
  std::size_t size_{};
};

}  // namespace m3
