#include "fake_vst3_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/gui/iplugview.h"
#include "pluginterfaces/gui/iplugviewcontentscalesupport.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

Steinberg::Vst::IEditController* create_controller(
    Steinberg::IPluginFactory* factory,
    Steinberg::Vst::IComponent*& component) noexcept {
  const auto& words = m3::vst3::kProbeClassIdWords;
  const Steinberg::FUID id(words[0], words[1], words[2], words[3]);
  Steinberg::TUID class_id{};
  id.toTUID(class_id);
  component = nullptr;
  if (factory == nullptr ||
      factory->createInstance(class_id, Steinberg::Vst::IComponent::iid,
                              reinterpret_cast<void**>(&component)) !=
          Steinberg::kResultOk ||
      component == nullptr) {
    return nullptr;
  }
  Steinberg::Vst::IEditController* controller = nullptr;
  component->queryInterface(Steinberg::Vst::IEditController::iid,
                            reinterpret_cast<void**>(&controller));
  return controller;
}

}  // namespace

M3_TEST(vst3_editor_remove_before_attach_is_safe_and_silent) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);

  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  if (component != nullptr && controller != nullptr) {
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->canResize(), Steinberg::kResultTrue);
      Steinberg::ViewRect constrained{10, 20, 510, 420};
      M3_EXPECT_EQ(view->checkSizeConstraint(&constrained),
                   Steinberg::kResultTrue);
      M3_EXPECT_EQ(constrained.right - constrained.left, 1024);
      M3_EXPECT_EQ(constrained.bottom - constrained.top, 620);
      Steinberg::ViewRect resized{0, 0, 1200, 720};
      M3_EXPECT_EQ(view->onSize(&resized), Steinberg::kResultTrue);
      Steinberg::ViewRect actual{};
      M3_EXPECT_EQ(view->getSize(&actual), Steinberg::kResultTrue);
      M3_EXPECT_EQ(actual.right - actual.left, 1200);
      M3_EXPECT_EQ(actual.bottom - actual.top, 720);

      Steinberg::IPlugViewContentScaleSupport* scale_support = nullptr;
      M3_EXPECT_EQ(view->queryInterface(
                       Steinberg::IPlugViewContentScaleSupport::iid,
                       reinterpret_cast<void**>(&scale_support)),
                   Steinberg::kResultTrue);
      M3_EXPECT_TRUE(scale_support != nullptr);
      if (scale_support != nullptr) {
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.5),
                     Steinberg::kResultOk);
        scale_support->release();
      }
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
  }

  if (controller != nullptr) {
    controller->release();
  }
  if (component != nullptr) {
    component->release();
  }
  if (factory != nullptr) {
    factory->release();
  }
}
