#include <limits>
#include <new>

#include "fake_vst3_host.hpp"
#include "m3_editor.hpp"
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

void expect_edit_at(const m3::test::FakeVst3ComponentHandler& handler,
                    std::size_t offset,
                    Steinberg::Vst::ParamID parameter_id,
                    double normalized) noexcept {
  if (handler.edit_call_count() < offset + 3U) {
    M3_EXPECT_TRUE(false);
    return;
  }
  M3_EXPECT_EQ(handler.edit_call(offset).kind,
               m3::test::FakeVst3EditKind::begin);
  M3_EXPECT_EQ(handler.edit_call(offset).id, parameter_id);
  M3_EXPECT_EQ(handler.edit_call(offset + 1U).kind,
               m3::test::FakeVst3EditKind::perform);
  M3_EXPECT_EQ(handler.edit_call(offset + 1U).id, parameter_id);
  M3_EXPECT_NEAR(handler.edit_call(offset + 1U).value, normalized, 1.0e-6);
  M3_EXPECT_EQ(handler.edit_call(offset + 2U).kind,
               m3::test::FakeVst3EditKind::end);
  M3_EXPECT_EQ(handler.edit_call(offset + 2U).id, parameter_id);
}

void expect_single_edit(const m3::test::FakeVst3ComponentHandler& handler,
                        Steinberg::Vst::ParamID parameter_id,
                        double normalized) noexcept {
  M3_EXPECT_EQ(handler.edit_call_count(), 3U);
  expect_edit_at(handler, 0U, parameter_id, normalized);
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

M3_TEST(vst3_editor_writable_controls_emit_one_exact_host_gesture) {
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
    struct Case final {
      m3::ParameterId parameter_id;
      double normalized_value;
    };
    constexpr Case kCases[] = {
        {0x4D330001U, 0.5}, {0x4D330002U, 1.0},
        {0x4D330003U, 0.5}, {0x4D330004U, 0.75},
        {0x4D330005U, 0.75}, {0x4D330006U, 0.6},
        {0x4D330007U, 0.25}, {0x4D330008U, 0.75},
        {0x4D330009U, 4.0 / 7.0}, {0x4D33000AU, 0.5},
        {0x4D33000BU, 0.0}, {0x4D33000CU, 99.0 / 126.0},
        {0x4D33000DU, 4.0 / 15.0}, {0x4D33000FU, 0.0},
    };
    for (const Case& test_case : kCases) {
      handler.reset();
      const m3::vst3::EditorGesture gesture =
          m3::vst3::editor_gesture_for_test(
              *static_cast<Steinberg::Vst::EditController*>(controller),
              test_case.parameter_id,
              test_case.normalized_value, m3::VelocityMode::fixed);
      M3_EXPECT_TRUE(gesture.accepted);
      M3_EXPECT_EQ(gesture.parameter_id, test_case.parameter_id);
      M3_EXPECT_NEAR(gesture.normalized_value,
                     test_case.normalized_value, 1.0e-12);
      M3_EXPECT_EQ(handler.edit_call_count(), 3U);
      if (handler.edit_call_count() == 3U) {
        M3_EXPECT_EQ(handler.edit_call(0).kind,
                     m3::test::FakeVst3EditKind::begin);
        M3_EXPECT_EQ(handler.edit_call(0).id, test_case.parameter_id);
        M3_EXPECT_EQ(handler.edit_call(1).kind,
                     m3::test::FakeVst3EditKind::perform);
        M3_EXPECT_EQ(handler.edit_call(1).id, test_case.parameter_id);
        M3_EXPECT_NEAR(handler.edit_call(1).value,
                       test_case.normalized_value, 1.0e-12);
        M3_EXPECT_EQ(handler.edit_call(2).kind,
                     m3::test::FakeVst3EditKind::end);
        M3_EXPECT_EQ(handler.edit_call(2).id, test_case.parameter_id);
      }
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

M3_TEST(vst3_editor_status_and_dynamic_fixed_velocity_are_read_only) {
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
    const m3::vst3::EditorGesture status =
        m3::vst3::editor_gesture_for_test(
            *static_cast<Steinberg::Vst::EditController*>(controller),
            m3::kStatusParameterId, 1.0,
            m3::VelocityMode::fixed);
    M3_EXPECT_FALSE(status.accepted);
    M3_EXPECT_EQ(handler.edit_call_count(), 0U);

    const m3::vst3::EditorGesture fixed_velocity =
        m3::vst3::editor_gesture_for_test(
            *static_cast<Steinberg::Vst::EditController*>(controller),
            m3::ParameterId{0x4D33000CU}, 0.75,
            m3::VelocityMode::dynamic);
    M3_EXPECT_FALSE(fixed_velocity.accepted);
    M3_EXPECT_EQ(handler.edit_call_count(), 0U);
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

M3_TEST(vst3_editor_panic_press_resets_and_linked_range_writes_both_ends) {
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
    M3_EXPECT_TRUE(m3::vst3::editor_panic_for_test(
        *static_cast<Steinberg::Vst::EditController*>(controller)));
    M3_EXPECT_EQ(handler.edit_call_count(), 6U);
    if (handler.edit_call_count() == 6U) {
      M3_EXPECT_EQ(handler.edit_call(0).kind,
                   m3::test::FakeVst3EditKind::begin);
      M3_EXPECT_EQ(handler.edit_call(1).kind,
                   m3::test::FakeVst3EditKind::perform);
      M3_EXPECT_NEAR(handler.edit_call(1).value, 1.0, 1.0e-12);
      M3_EXPECT_EQ(handler.edit_call(2).kind,
                   m3::test::FakeVst3EditKind::end);
      M3_EXPECT_EQ(handler.edit_call(3).kind,
                   m3::test::FakeVst3EditKind::begin);
      M3_EXPECT_EQ(handler.edit_call(4).kind,
                   m3::test::FakeVst3EditKind::perform);
      M3_EXPECT_NEAR(handler.edit_call(4).value, 0.0, 1.0e-12);
      M3_EXPECT_EQ(handler.edit_call(5).kind,
                   m3::test::FakeVst3EditKind::end);
    }
    M3_EXPECT_NEAR(controller->getParamNormalized(m3::kPanicParameterId),
                   0.0, 1.0e-12);

    handler.reset();
    const m3::vst3::EditorRangeGesture range =
        m3::vst3::editor_range_gesture_for_test(
            *static_cast<Steinberg::Vst::EditController*>(controller), 0.25,
            0.75);
    M3_EXPECT_TRUE(range.accepted);
    M3_EXPECT_NEAR(range.low_normalized, 0.25, 1.0e-12);
    M3_EXPECT_NEAR(range.high_normalized, 0.75, 1.0e-12);
    M3_EXPECT_EQ(handler.edit_call_count(), 6U);
    if (handler.edit_call_count() == 6U) {
      M3_EXPECT_EQ(handler.edit_call(0).id, 0x4D330007U);
      M3_EXPECT_EQ(handler.edit_call(1).id, 0x4D330007U);
      M3_EXPECT_EQ(handler.edit_call(2).id, 0x4D330007U);
      M3_EXPECT_EQ(handler.edit_call(3).id, 0x4D330008U);
      M3_EXPECT_EQ(handler.edit_call(4).id, 0x4D330008U);
      M3_EXPECT_EQ(handler.edit_call(5).id, 0x4D330008U);
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

M3_TEST(vst3_editor_real_range_drag_clamps_low_to_the_shared_high_value) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      handler.reset();
      const double high = controller->getParamNormalized(0x4D330008U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330007U, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, 0x4D330007U, -1000.0));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
          *view, 0x4D330007U));
      expect_single_edit(handler, 0x4D330007U, high);
      M3_EXPECT_TRUE(controller->getParamNormalized(0x4D330007U) <=
                     controller->getParamNormalized(0x4D330008U));

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_wheel_for_test(
          *view, 0x4D330007U, -1.0));
      const double stepped_low = controller->getParamNormalized(0x4D330007U);
      expect_single_edit(handler, 0x4D330007U, stepped_low);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330007U, 0.5, 0.5, true));
      const double default_low = controller->getParamNormalized(0x4D330007U);
      expect_single_edit(handler, 0x4D330007U, default_low);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330008U, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, 0x4D330008U, 1000.0));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
          *view, 0x4D330008U));
      expect_single_edit(handler, 0x4D330008U, default_low);
      M3_EXPECT_TRUE(controller->getParamNormalized(0x4D330007U) <=
                     controller->getParamNormalized(0x4D330008U));
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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

M3_TEST(vst3_editor_tiny_drag_and_fine_wheel_emit_exact_legal_steps) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      struct Case final {
        m3::ParameterId parameter_id;
        double drag_delta;
        double after_drag;
        double wheel_delta;
        double after_wheel;
      };
      constexpr Case kCases[] = {
          {0x4D330007U, -1.0, 9.0 / 84.0, 0.25, 10.0 / 84.0},
          {0x4D330008U, 1.0, 59.0 / 84.0, -0.25, 58.0 / 84.0},
          {0x4D330004U, -1.0, 242.0 / 480.0, 0.25, 243.0 / 480.0},
          {0x4D330009U, 1.0, 6.0 / 7.0, -0.25, 5.0 / 7.0},
          {0x4D33000DU, -1.0, 1.0 / 15.0, 0.25, 2.0 / 15.0},
      };
      for (const Case& test_case : kCases) {
        handler.reset();
        M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
            *view, test_case.parameter_id, 0.5, 0.5, false));
        M3_EXPECT_EQ(handler.edit_call_count(), 0U);
        M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
            *view, test_case.parameter_id, test_case.drag_delta));
        M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
            *view, test_case.parameter_id));
        expect_single_edit(handler, test_case.parameter_id,
                           test_case.after_drag);
        M3_EXPECT_NEAR(controller->getParamNormalized(test_case.parameter_id),
                       test_case.after_drag, 1.0e-6);

        handler.reset();
        M3_EXPECT_TRUE(m3::vst3::editor_wheel_for_test(
            *view, test_case.parameter_id, test_case.wheel_delta));
        expect_single_edit(handler, test_case.parameter_id,
                           test_case.after_wheel);
        M3_EXPECT_NEAR(controller->getParamNormalized(test_case.parameter_id),
                       test_case.after_wheel, 1.0e-6);
      }
      M3_EXPECT_TRUE(controller->getParamNormalized(0x4D330007U) <=
                     controller->getParamNormalized(0x4D330008U));
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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

M3_TEST(vst3_editor_real_control_events_cover_rotary_discrete_and_read_only_paths) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330005U, 0.5, 0.5, false));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, 0x4D330005U, -20.0));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
          *view, 0x4D330005U));
      expect_single_edit(handler, 0x4D330005U, 0.6);
      M3_EXPECT_NEAR(controller->getParamNormalized(0x4D330005U), 0.6,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_wheel_for_test(
          *view, 0x4D330005U, 1.0));
      expect_single_edit(handler, 0x4D330005U, 0.61);
      M3_EXPECT_NEAR(controller->getParamNormalized(0x4D330005U), 0.61,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330005U, 0.5, 0.5, true));
      expect_single_edit(handler, 0x4D330005U, 0.5);
      M3_EXPECT_NEAR(controller->getParamNormalized(0x4D330005U), 0.5,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, m3::kStatusParameterId, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D33000CU, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);

      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330001U, 0.9, 0.5, false));
      expect_single_edit(handler, 0x4D330001U, 1.0);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D330002U, 0.75, 0.5, false));
      expect_single_edit(handler, 0x4D330002U, 1.0);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D33000BU, 0.25, 0.5, false));
      expect_single_edit(handler, 0x4D33000BU, 0.0);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, 0x4D33000FU, 0.5, 0.5, false));
      expect_single_edit(handler, 0x4D33000FU, 0.0);
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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

M3_TEST(vst3_editor_real_panic_cancel_and_removal_each_reset_exactly_once) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, m3::kPanicParameterId, 0.5, 0.5, false));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *view, m3::kPanicParameterId));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *view, m3::kPanicParameterId));
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      if (handler.edit_call_count() == 6U) {
        expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
        expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
      }

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, m3::kPanicParameterId, 0.5, 0.5, false));
      M3_EXPECT_TRUE(m3::vst3::editor_remove_control_for_test(
          *view, m3::kPanicParameterId));
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      if (handler.edit_call_count() == 6U) {
        expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
        expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
      }
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();

      Steinberg::IPlugView* destruction_view =
          controller->createView(Steinberg::Vst::ViewType::kEditor);
      M3_EXPECT_TRUE(destruction_view != nullptr);
      if (destruction_view != nullptr) {
        M3_EXPECT_EQ(destruction_view->setFrame(&plug_frame),
                     Steinberg::kResultTrue);
        M3_EXPECT_EQ(destruction_view->attached(
                         nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                     Steinberg::kResultOk);
        handler.reset();
        M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
            *destruction_view, m3::kPanicParameterId, 0.5, 0.5, false));
        M3_EXPECT_EQ(destruction_view->removed(), Steinberg::kResultOk);
        M3_EXPECT_EQ(handler.edit_call_count(), 6U);
        if (handler.edit_call_count() == 6U) {
          expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
          expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
        }
        M3_EXPECT_EQ(destruction_view->setFrame(nullptr),
                     Steinberg::kResultTrue);
        destruction_view->release();
      }
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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

M3_TEST(vst3_editor_partial_panic_press_still_resets_once_on_every_exit) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    M3_EXPECT_EQ(controller->setComponentHandler(&handler),
                 Steinberg::kResultTrue);
    auto attach_view = [&]() noexcept {
      Steinberg::IPlugView* view =
          controller->createView(Steinberg::Vst::ViewType::kEditor);
      M3_EXPECT_TRUE(view != nullptr);
      if (view != nullptr) {
        M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
        M3_EXPECT_EQ(view->attached(
                         nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                     Steinberg::kResultOk);
      }
      return view;
    };

    Steinberg::IPlugView* cancel_view = attach_view();
    if (cancel_view != nullptr) {
      handler.reset();
      handler.fail_next_perform_edit();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *cancel_view, m3::kPanicParameterId, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 3U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *cancel_view, m3::kPanicParameterId));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *cancel_view, m3::kPanicParameterId));
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      if (handler.edit_call_count() == 6U) {
        expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
        expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
      }
      M3_EXPECT_EQ(cancel_view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      M3_EXPECT_EQ(cancel_view->setFrame(nullptr), Steinberg::kResultTrue);
      cancel_view->release();
    }

    Steinberg::IPlugView* removal_view = attach_view();
    if (removal_view != nullptr) {
      handler.reset();
      handler.fail_next_end_edit();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *removal_view, m3::kPanicParameterId, 0.5, 0.5, false));
      M3_EXPECT_TRUE(m3::vst3::editor_remove_control_for_test(
          *removal_view, m3::kPanicParameterId));
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      if (handler.edit_call_count() == 6U) {
        expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
        expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
      }
      M3_EXPECT_EQ(removal_view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      M3_EXPECT_EQ(removal_view->setFrame(nullptr), Steinberg::kResultTrue);
      removal_view->release();
    }

    Steinberg::IPlugView* destruction_view = attach_view();
    if (destruction_view != nullptr) {
      handler.reset();
      handler.fail_next_end_edit();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *destruction_view, m3::kPanicParameterId, 0.5, 0.5, false));
      M3_EXPECT_EQ(destruction_view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(handler.edit_call_count(), 6U);
      if (handler.edit_call_count() == 6U) {
        expect_edit_at(handler, 0U, m3::kPanicParameterId, 1.0);
        expect_edit_at(handler, 3U, m3::kPanicParameterId, 0.0);
      }
      M3_EXPECT_EQ(destruction_view->setFrame(nullptr),
                   Steinberg::kResultTrue);
      destruction_view->release();
    }

    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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

M3_TEST(vst3_editor_accepted_resize_reflows_real_child_controls) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      m3::vst3::EditorRect before{};
      m3::vst3::EditorRect after{};
      M3_EXPECT_TRUE(m3::vst3::editor_control_bounds_for_test(
          *view, 0x4D330005U, before));
      Steinberg::ViewRect resized{0, 0, 1200, 720};
      M3_EXPECT_EQ(view->onSize(&resized), Steinberg::kResultTrue);
      M3_EXPECT_TRUE(m3::vst3::editor_control_bounds_for_test(
          *view, 0x4D330005U, after));
      M3_EXPECT_TRUE(after.left > before.left);
      M3_EXPECT_TRUE(after.top > before.top);
      M3_EXPECT_TRUE(after.right > before.right);
      M3_EXPECT_TRUE(after.bottom > before.bottom);
      M3_EXPECT_NEAR(after.left, before.left * 1200.0 / 1024.0, 1.0e-6);
      M3_EXPECT_NEAR(after.top, before.top * 720.0 / 620.0, 1.0e-6);
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
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
