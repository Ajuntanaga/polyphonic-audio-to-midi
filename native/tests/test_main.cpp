#include "test_support.hpp"

extern "C" bool ModuleEntry(void* shared_library_handle);
extern "C" bool ModuleExit();

int main() {
  if (!ModuleEntry(nullptr)) {
    return 1;
  }
  const int result = m3::test::run_all_tests();
  return ModuleExit() ? result : 1;
}
