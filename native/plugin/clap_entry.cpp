#include <clap/clap.h>
#include <clap/factory/plugin-factory.h>

#include <cstdint>
#include <cstring>

#include "clap_adapter.hpp"

namespace {

std::uint32_t entry_initializations = 0;

bool CLAP_ABI entry_init(const char* plugin_path) noexcept {
  if (plugin_path == nullptr) {
    return false;
  }
  ++entry_initializations;
  return true;
}

void CLAP_ABI entry_deinit() noexcept {
  if (entry_initializations > 0) {
    --entry_initializations;
  }
}

std::uint32_t CLAP_ABI factory_count(const clap_plugin_factory_t*) noexcept {
  return entry_initializations == 0 ? 0U : 1U;
}

const clap_plugin_descriptor_t* CLAP_ABI factory_descriptor(
    const clap_plugin_factory_t*, std::uint32_t index) noexcept {
  if (entry_initializations == 0 || index != 0) {
    return nullptr;
  }
  return m3::selected_descriptor();
}

const clap_plugin_t* CLAP_ABI factory_create(const clap_plugin_factory_t*,
                                             const clap_host_t* host,
                                             const char* plugin_id) noexcept {
  if (entry_initializations == 0 || plugin_id == nullptr ||
      std::strcmp(plugin_id, m3::selected_descriptor()->id) != 0) {
    return nullptr;
  }
  return m3::create_adapter(host);
}

const clap_plugin_factory_t kFactory{
    &factory_count,
    &factory_descriptor,
    &factory_create,
};

const void* CLAP_ABI entry_get_factory(const char* factory_id) noexcept {
  if (entry_initializations == 0 || factory_id == nullptr ||
      std::strcmp(factory_id, CLAP_PLUGIN_FACTORY_ID) != 0) {
    return nullptr;
  }
  return &kFactory;
}

}  // namespace

extern "C" CLAP_EXPORT const clap_plugin_entry_t clap_entry{
    CLAP_VERSION,
    &entry_init,
    &entry_deinit,
    &entry_get_factory,
};
