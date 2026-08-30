#include <dirent.h>

#include <cstddef>
#include <cstdint>

#include "fake_vst3_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

struct RealtimeInstance final {
  Steinberg::IPluginFactory* factory{};
  Steinberg::Vst::IComponent* component{};
  Steinberg::Vst::IAudioProcessor* processor{};
  m3::test::FakeVst3Host host{};
};

std::size_t current_task_count() noexcept {
  DIR* directory = opendir("/proc/self/task");
  if (directory == nullptr) {
    return 0U;
  }
  std::size_t count = 0U;
  while (const dirent* entry = readdir(directory)) {
    if (entry->d_name[0] != '.') {
      ++count;
    }
  }
  static_cast<void>(closedir(directory));
  return count;
}

bool open_instance(RealtimeInstance& instance) noexcept {
  instance.factory = GetPluginFactory();
  if (instance.factory == nullptr) {
    return false;
  }
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  if (instance.factory->createInstance(
          class_id, Steinberg::Vst::IComponent::iid,
          reinterpret_cast<void**>(&instance.component)) !=
          Steinberg::kResultOk ||
      instance.component == nullptr ||
      instance.component->initialize(&instance.host) != Steinberg::kResultOk ||
      instance.component->queryInterface(
          Steinberg::Vst::IAudioProcessor::iid,
          reinterpret_cast<void**>(&instance.processor)) !=
          Steinberg::kResultOk ||
      instance.processor == nullptr) {
    return false;
  }
  Steinberg::Vst::ProcessSetup setup{};
  setup.processMode = Steinberg::Vst::kRealtime;
  setup.symbolicSampleSize = Steinberg::Vst::kSample32;
  setup.maxSamplesPerBlock = 1;
  setup.sampleRate = 48000.0;
  return instance.processor->setupProcessing(setup) == Steinberg::kResultOk &&
         instance.component->setActive(Steinberg::TBool{1}) ==
             Steinberg::kResultOk &&
         instance.processor->setProcessing(Steinberg::TBool{1}) ==
             Steinberg::kResultOk;
}

void close_instance(RealtimeInstance& instance) noexcept {
  if (instance.processor != nullptr) {
    static_cast<void>(instance.processor->setProcessing(Steinberg::TBool{0}));
  }
  if (instance.component != nullptr) {
    static_cast<void>(instance.component->setActive(Steinberg::TBool{0}));
    static_cast<void>(instance.component->terminate());
  }
  if (instance.processor != nullptr) {
    instance.processor->release();
  }
  if (instance.component != nullptr) {
    instance.component->release();
  }
  if (instance.factory != nullptr) {
    instance.factory->release();
  }
}

}  // namespace

M3_TEST(vst3_realtime_calls_allocate_zero_and_create_no_threads_100000) {
  RealtimeInstance instance;
  M3_EXPECT_TRUE(open_instance(instance));
  if (instance.processor == nullptr) {
    close_instance(instance);
    return;
  }

  m3::test::FakeVst3ProcessBlock<float> block;
  block.configure(1U, true);
  block.fill_silence();
  const std::size_t tasks_before = current_task_count();
  const std::size_t allocations_before = m3::test::allocation_count();
  const std::size_t deallocations_before = m3::test::deallocation_count();
  bool valid = tasks_before > 0U;
  for (std::size_t iteration = 0; iteration < 100000U; ++iteration) {
    valid = instance.processor->process(block.data()) ==
                Steinberg::kResultOk &&
            instance.processor->setProcessing(Steinberg::TBool{0}) ==
                Steinberg::kResultOk &&
            instance.processor->setProcessing(Steinberg::TBool{1}) ==
                Steinberg::kResultOk &&
            valid;
  }
  const std::size_t tasks_after = current_task_count();
  M3_EXPECT_TRUE(valid);
  M3_EXPECT_EQ(tasks_after, tasks_before);
  M3_EXPECT_EQ(m3::test::allocation_count(), allocations_before);
  M3_EXPECT_EQ(m3::test::deallocation_count(), deallocations_before);
  close_instance(instance);
}
