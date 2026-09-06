#include <limits>
#include <new>

#include "fake_vst3_host.hpp"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/gui/iplugview.h"
#include "pluginterfaces/gui/iplugviewcontentscalesupport.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "test_support.hpp"
#include "vst3_ids.hpp"
#include "vst3_probe_processor.hpp"
#include "vstgui/lib/platform/linux/linuxfactory.h"
#include "vstgui/lib/platform/platform_linux.h"
#include "vstgui/lib/platform/platformfactory.h"

extern "C" Steinberg::IPluginFactory* PLUGIN_API GetPluginFactory();

namespace {

class FakeVstguiRunLoop final : public VSTGUI::IRunLoop,
                                public VSTGUI::NonAtomicReferenceCounted {
 public:
  bool registerEventHandler(int, VSTGUI::IEventHandler*) override {
    return true;
  }
  bool unregisterEventHandler(VSTGUI::IEventHandler*) override { return true; }
  bool registerTimer(std::uint64_t, VSTGUI::ITimerHandler*) override {
    return true;
  }
  bool unregisterTimer(VSTGUI::ITimerHandler*) override { return true; }
};

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

void expect_scale_rejected(float factor) noexcept {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  m3::test::FakeVst3Host host;
  if (component != nullptr && controller != nullptr) {
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      Steinberg::IPlugViewContentScaleSupport* scale_support = nullptr;
      M3_EXPECT_EQ(view->queryInterface(
                       Steinberg::IPlugViewContentScaleSupport::iid,
                       reinterpret_cast<void**>(&scale_support)),
                   Steinberg::kResultTrue);
      M3_EXPECT_TRUE(scale_support != nullptr);
      if (scale_support != nullptr) {
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(factor),
                     Steinberg::kInvalidArgument);
        Steinberg::ViewRect unchanged{};
        M3_EXPECT_EQ(view->getSize(&unchanged), Steinberg::kResultTrue);
        M3_EXPECT_EQ(unchanged.right - unchanged.left, 1024);
        M3_EXPECT_EQ(unchanged.bottom - unchanged.top, 620);
        scale_support->release();
      }
      view->release();
    }
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

M3_TEST(vst3_editor_scale_round_trip_restores_logical_geometry) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);

  m3::test::FakeVst3Host host;
  if (component != nullptr && controller != nullptr) {
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      Steinberg::IPlugViewContentScaleSupport* scale_support = nullptr;
      M3_EXPECT_EQ(view->queryInterface(
                       Steinberg::IPlugViewContentScaleSupport::iid,
                       reinterpret_cast<void**>(&scale_support)),
                   Steinberg::kResultTrue);
      M3_EXPECT_TRUE(scale_support != nullptr);
      if (scale_support != nullptr) {
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.3F),
                     Steinberg::kResultOk);
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.0F),
                     Steinberg::kResultOk);
        Steinberg::ViewRect scaled{};
        M3_EXPECT_EQ(view->getSize(&scaled), Steinberg::kResultTrue);
        M3_EXPECT_EQ(scaled.right - scaled.left, 1024);
        M3_EXPECT_EQ(scaled.bottom - scaled.top, 620);
        scale_support->release();
      }
      view->release();
    }
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

M3_TEST(vst3_editor_rejects_invalid_scale_without_geometry_mutation) {
  expect_scale_rejected(0.0F);
  expect_scale_rejected(-1.0F);
  expect_scale_rejected(std::numeric_limits<float>::infinity());
  expect_scale_rejected(-std::numeric_limits<float>::infinity());
  expect_scale_rejected(std::numeric_limits<float>::quiet_NaN());
}

M3_TEST(vst3_editor_scale_requests_host_resize_and_accepts_on_size) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);

  m3::test::FakeVst3Host host;
  m3::test::FakeVst3PlugFrame plug_frame;
  if (component != nullptr && controller != nullptr) {
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      plug_frame.reject_resize(true);
      Steinberg::IPlugViewContentScaleSupport* scale_support = nullptr;
      M3_EXPECT_EQ(view->queryInterface(
                       Steinberg::IPlugViewContentScaleSupport::iid,
                       reinterpret_cast<void**>(&scale_support)),
                   Steinberg::kResultTrue);
      M3_EXPECT_TRUE(scale_support != nullptr);
      if (scale_support != nullptr) {
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.5F),
                     Steinberg::kResultFalse);
        M3_EXPECT_EQ(plug_frame.resize_count(), 1U);
        Steinberg::ViewRect unchanged{};
        M3_EXPECT_EQ(view->getSize(&unchanged), Steinberg::kResultTrue);
        M3_EXPECT_EQ(unchanged.right - unchanged.left, 1024);
        M3_EXPECT_EQ(unchanged.bottom - unchanged.top, 620);

        plug_frame.reject_resize(false);
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.5F),
                     Steinberg::kResultOk);
        M3_EXPECT_EQ(plug_frame.resize_count(), 2U);
        M3_EXPECT_EQ(plug_frame.last_size().right -
                         plug_frame.last_size().left,
                     1536);
        M3_EXPECT_EQ(plug_frame.last_size().bottom -
                         plug_frame.last_size().top,
                     930);
        Steinberg::ViewRect scaled{};
        M3_EXPECT_EQ(view->getSize(&scaled), Steinberg::kResultTrue);
        M3_EXPECT_EQ(scaled.right - scaled.left, 1536);
        M3_EXPECT_EQ(scaled.bottom - scaled.top, 930);
        scale_support->release();
      }
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
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

M3_TEST(vst3_probe_editor_public_attach_remove_is_safe_and_silent) {
  auto* probe = new (std::nothrow) m3::vst3::M3ProbeProcessor;
  M3_EXPECT_TRUE(probe != nullptr);
  if (probe == nullptr) {
    return;
  }

  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
  }
  M3_EXPECT_EQ(probe->initialize(&host), Steinberg::kResultOk);
  M3_EXPECT_EQ(probe->setComponentHandler(&handler), Steinberg::kResultTrue);
  Steinberg::IPlugView* view =
      probe->createView(Steinberg::Vst::ViewType::kEditor);
  M3_EXPECT_TRUE(view != nullptr);
  if (view != nullptr) {
    M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
    M3_EXPECT_EQ(view->attached(
                     nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                 Steinberg::kResultOk);
    M3_EXPECT_TRUE(plug_frame.resize_count() > 0U);
    M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
    M3_EXPECT_EQ(handler.edit_call_count(), 0U);
    M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
    view->release();
  }
  M3_EXPECT_EQ(probe->setComponentHandler(nullptr), Steinberg::kResultTrue);
  M3_EXPECT_EQ(probe->terminate(), Steinberg::kResultOk);
  delete probe;
  if (platform_factory != nullptr) {
    platform_factory->setRunLoop({});
  }
}
