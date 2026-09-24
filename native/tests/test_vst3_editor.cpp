#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <vector>

#include "fake_vst3_host.hpp"
#include "m3_editor.hpp"
#include "vst3_component.hpp"
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

bool write_editor_ppm(Steinberg::IPlugView& view, const char* path) {
  if (path == nullptr || path[0] == '\0') {
    return true;
  }
  constexpr std::size_t width =
      static_cast<std::size_t>(m3::vst3::kEditorWidth);
  constexpr std::size_t height =
      static_cast<std::size_t>(m3::vst3::kEditorHeight);
  std::vector<std::uint8_t> rgba(width * height * 4U);
  if (!m3::vst3::editor_render_rgba_for_test(view, rgba.data(),
                                              rgba.size())) {
    return false;
  }
  std::vector<std::uint8_t> rgb(width * height * 3U);
  for (std::size_t pixel = 0U; pixel < width * height; ++pixel) {
    rgb[pixel * 3U] = rgba[pixel * 4U];
    rgb[pixel * 3U + 1U] = rgba[pixel * 4U + 1U];
    rgb[pixel * 3U + 2U] = rgba[pixel * 4U + 2U];
  }
  std::FILE* file = std::fopen(path, "wb");
  if (file == nullptr) {
    return false;
  }
  const bool header_ok =
      std::fprintf(file, "P6\n%zu %zu\n255\n", width, height) > 0;
  const bool body_ok =
      header_ok && std::fwrite(rgb.data(), 1U, rgb.size(), file) == rgb.size();
  return std::fclose(file) == 0 && body_ok;
}

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
        M3_EXPECT_EQ(unchanged.right - unchanged.left,
                     m3::vst3::kEditorWidth);
        M3_EXPECT_EQ(unchanged.bottom - unchanged.top,
                     m3::vst3::kEditorHeight);
        M3_EXPECT_NEAR(
            m3::vst3::editor_content_scale_factor_for_test(*view), 1.0,
            1.0e-12);
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
      M3_EXPECT_EQ(constrained.right - constrained.left,
                   m3::vst3::kEditorWidth);
      M3_EXPECT_EQ(constrained.bottom - constrained.top,
                   m3::vst3::kEditorHeight);
      Steinberg::ViewRect resized{0, 0, 1200, 900};
      M3_EXPECT_EQ(view->onSize(&resized), Steinberg::kResultTrue);
      Steinberg::ViewRect actual{};
      M3_EXPECT_EQ(view->getSize(&actual), Steinberg::kResultTrue);
      M3_EXPECT_EQ(actual.right - actual.left, 1200);
      M3_EXPECT_EQ(actual.bottom - actual.top, 900);

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
        M3_EXPECT_EQ(scaled.right - scaled.left, m3::vst3::kEditorWidth);
        M3_EXPECT_EQ(scaled.bottom - scaled.top, m3::vst3::kEditorHeight);
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
  expect_scale_rejected(1.0e-6F);
  expect_scale_rejected(std::numeric_limits<float>::infinity());
  expect_scale_rejected(-std::numeric_limits<float>::infinity());
  expect_scale_rejected(std::numeric_limits<float>::quiet_NaN());
}

M3_TEST(vst3_editor_attached_tiny_scale_is_rejected_without_host_or_state_change) {
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
      Steinberg::IPlugViewContentScaleSupport* scale_support = nullptr;
      M3_EXPECT_EQ(view->queryInterface(
                       Steinberg::IPlugViewContentScaleSupport::iid,
                       reinterpret_cast<void**>(&scale_support)),
                   Steinberg::kResultTrue);
      M3_EXPECT_TRUE(scale_support != nullptr);
      if (scale_support != nullptr) {
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.0e-6F),
                     Steinberg::kInvalidArgument);
        M3_EXPECT_EQ(plug_frame.resize_count(), 0U);
        M3_EXPECT_NEAR(
            m3::vst3::editor_content_scale_factor_for_test(*view), 1.0,
            1.0e-12);
        Steinberg::ViewRect unchanged{};
        M3_EXPECT_EQ(view->getSize(&unchanged), Steinberg::kResultTrue);
        M3_EXPECT_EQ(unchanged.right - unchanged.left,
                     m3::vst3::kEditorWidth);
        M3_EXPECT_EQ(unchanged.bottom - unchanged.top,
                     m3::vst3::kEditorHeight);

        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.5F),
                     Steinberg::kResultOk);
        M3_EXPECT_EQ(plug_frame.resize_count(), 1U);
        M3_EXPECT_EQ(plug_frame.last_size().right -
                         plug_frame.last_size().left,
                     m3::vst3::kEditorWidth * 3 / 2);
        M3_EXPECT_EQ(plug_frame.last_size().bottom -
                         plug_frame.last_size().top,
                     m3::vst3::kEditorHeight * 3 / 2);
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
        M3_EXPECT_EQ(unchanged.right - unchanged.left,
                     m3::vst3::kEditorWidth);
        M3_EXPECT_EQ(unchanged.bottom - unchanged.top,
                     m3::vst3::kEditorHeight);

        plug_frame.reject_resize(false);
        M3_EXPECT_EQ(scale_support->setContentScaleFactor(1.5F),
                     Steinberg::kResultOk);
        M3_EXPECT_EQ(plug_frame.resize_count(), 2U);
        M3_EXPECT_EQ(plug_frame.last_size().right -
                         plug_frame.last_size().left,
                     m3::vst3::kEditorWidth * 3 / 2);
        M3_EXPECT_EQ(plug_frame.last_size().bottom -
                         plug_frame.last_size().top,
                     m3::vst3::kEditorHeight * 3 / 2);
        Steinberg::ViewRect scaled{};
        M3_EXPECT_EQ(view->getSize(&scaled), Steinberg::kResultTrue);
        M3_EXPECT_EQ(scaled.right - scaled.left,
                     m3::vst3::kEditorWidth * 3 / 2);
        M3_EXPECT_EQ(scaled.bottom - scaled.top,
                     m3::vst3::kEditorHeight * 3 / 2);
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

M3_TEST(vst3_editor_custom_generic_custom_round_trip_restores_full_surface) {
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
      M3_EXPECT_EQ(
          m3::vst3::editor_attach_refresh_count_for_test(*view), 1U);

      // REAPER temporarily substitutes a shorter generic parameter view.
      Steinberg::ViewRect generic_size{0, 0, m3::vst3::kEditorWidth,
                                       m3::vst3::kEditorHeight - 100};
      M3_EXPECT_EQ(view->onSize(&generic_size), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);

      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      M3_EXPECT_EQ(
          m3::vst3::editor_attach_refresh_count_for_test(*view), 2U);
      Steinberg::ViewRect restored{};
      M3_EXPECT_EQ(view->getSize(&restored), Steinberg::kResultTrue);
      M3_EXPECT_EQ(restored.getWidth(), m3::vst3::kEditorWidth);
      M3_EXPECT_EQ(restored.getHeight(), m3::vst3::kEditorHeight);
      m3::vst3::EditorRect dry_audio{};
      M3_EXPECT_TRUE(m3::vst3::editor_control_bounds_for_test(
          *view, 0x4D33000FU, dry_audio));
      M3_EXPECT_TRUE(dry_audio.bottom <=
                     static_cast<double>(m3::vst3::kEditorHeight));

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
        {0x4D330001U, 1.0}, {0x4D330002U, 1.0},
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

M3_TEST(vst3_editor_tuner_snapshot_refreshes_without_parameter_edits) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  Steinberg::Vst::IAudioProcessor* processor = nullptr;
  if (component != nullptr) {
    static_cast<void>(component->queryInterface(
        Steinberg::Vst::IAudioProcessor::iid,
        reinterpret_cast<void**>(&processor)));
  }
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(processor != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr && processor != nullptr &&
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
      const std::size_t before =
          m3::vst3::editor_tuner_invalidation_count_for_test(*view);
      m3::TunerSnapshot published;
      published.generation = 41U;
      published.state = m3::TunerFrameState::tracking;
      published.voice_count = 2U;
      published.max_polyphony = 2U;
      published.voices[0] = m3::TunerVoice{
          40U, static_cast<std::int16_t>(-7 * 256), 28000U, 8U,
          m3::TunerVoiceState::tracking, true};
      published.voices[1] = m3::TunerVoice{
          47U, static_cast<std::int16_t>(11 * 256), 19000U, 3U,
          m3::TunerVoiceState::settling, true};
      m3::vst3::publish_tuner_snapshot_for_test(processor, published);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_FALSE(m3::vst3::editor_refresh_tuner_for_test(*view));
      m3::TunerSnapshot observed;
      M3_EXPECT_TRUE(
          m3::vst3::editor_tuner_snapshot_for_test(*view, observed));
      const std::uint32_t first_generation = observed.generation;
      M3_EXPECT_TRUE(first_generation > 0U);
      M3_EXPECT_EQ(observed.state, m3::TunerFrameState::tracking);
      M3_EXPECT_EQ(observed.voice_count, 2U);
      M3_EXPECT_EQ(observed.max_polyphony, 2U);
      M3_EXPECT_EQ(observed.voices[0].midi_note, 40U);
      M3_EXPECT_EQ(observed.voices[1].midi_note, 47U);
      M3_EXPECT_TRUE(
          m3::vst3::editor_tuner_invalidation_count_for_test(*view) > before);
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);

      m3::TunerVoice displayed{};
      bool lane_active = false;
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 0U, displayed, lane_active));
      M3_EXPECT_FALSE(lane_active);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 1U, displayed, lane_active));
      // A never-confirmed settling candidate must not create an extra meter.
      M3_EXPECT_FALSE(lane_active);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 2U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.midi_note, 40U);

      m3::TunerSnapshot reordered;
      reordered.generation = 42U;
      reordered.state = m3::TunerFrameState::tracking;
      reordered.voice_count = 2U;
      reordered.max_polyphony = 2U;
      reordered.voices[0] = m3::TunerVoice{
          47U, static_cast<std::int16_t>(9 * 256), 25000U, 9U,
          m3::TunerVoiceState::tracking, true};
      reordered.voices[1] = m3::TunerVoice{
          40U, 0, 10000U, 9U, m3::TunerVoiceState::settling, false};
      m3::vst3::publish_tuner_snapshot_for_test(processor, reordered);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 2U, displayed, lane_active));
      // Existing notes keep their physical meter while release evidence is
      // settling, even if the detector's candidate array changes order.
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.midi_note, 40U);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 3U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.midi_note, 47U);

      m3::TunerSnapshot open_strings;
      open_strings.generation = 43U;
      open_strings.state = m3::TunerFrameState::tracking;
      open_strings.voice_count = 8U;
      open_strings.max_polyphony = 8U;
      for (std::size_t input = 0U; input < m3::kM3OpenNotes.size(); ++input) {
        const std::size_t string = m3::kM3OpenNotes.size() - 1U - input;
        open_strings.voices[input] = m3::TunerVoice{
            m3::kM3OpenNotes[string], 0, 30000U, 12U,
            m3::TunerVoiceState::tracking, true};
      }
      m3::vst3::publish_tuner_snapshot_for_test(processor, open_strings);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      for (std::size_t string = 0U; string < m3::kM3OpenNotes.size();
           ++string) {
        M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
            *view, string, displayed, lane_active));
        M3_EXPECT_TRUE(lane_active);
        M3_EXPECT_EQ(displayed.midi_note, m3::kM3OpenNotes[string]);
      }

      m3::TunerSnapshot unison;
      unison.generation = 44U;
      unison.state = m3::TunerFrameState::tracking;
      unison.voice_count = 2U;
      unison.max_polyphony = 8U;
      unison.voices[0] = m3::TunerVoice{
          44U, 0, 30000U, 12U, m3::TunerVoiceState::tracking, true};
      unison.voices[1] = m3::TunerVoice{
          44U, 0, 28000U, 12U, m3::TunerVoiceState::tracking, true};
      m3::vst3::publish_tuner_snapshot_for_test(processor, unison);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 2U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.midi_note, 44U);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 3U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.midi_note, 44U);

      m3::TunerSnapshot explicit_strings;
      explicit_strings.generation = 45U;
      explicit_strings.state = m3::TunerFrameState::tracking;
      explicit_strings.voice_count = 2U;
      explicit_strings.max_polyphony = 8U;
      explicit_strings.voices[0] = m3::TunerVoice{
          44U, 0, 30000U, 12U, m3::TunerVoiceState::tracking, true, 0U};
      explicit_strings.voices[1] = m3::TunerVoice{
          44U, 0, 28000U, 12U, m3::TunerVoiceState::tracking, true, 3U};
      m3::vst3::publish_tuner_snapshot_for_test(processor, explicit_strings);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 0U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.string_index, 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 3U, displayed, lane_active));
      M3_EXPECT_TRUE(lane_active);
      M3_EXPECT_EQ(displayed.string_index, 3U);

      m3::TunerSnapshot empty;
      // A reset detector can restart its local generation at the same value.
      // The transport must still deliver the later no-signal frame to the UI.
      empty.generation = published.generation;
      empty.state = m3::TunerFrameState::no_signal;
      m3::vst3::publish_tuner_snapshot_for_test(processor, empty);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_TRUE(
          m3::vst3::editor_tuner_snapshot_for_test(*view, observed));
      M3_EXPECT_TRUE(observed.generation > first_generation);
      M3_EXPECT_EQ(observed.state, m3::TunerFrameState::no_signal);
      M3_EXPECT_EQ(observed.voice_count, 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 2U, displayed, lane_active));
      M3_EXPECT_FALSE(lane_active);
      M3_EXPECT_TRUE(m3::vst3::editor_tuner_display_lane_for_test(
          *view, 3U, displayed, lane_active));
      M3_EXPECT_FALSE(lane_active);
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
  }
  if (processor != nullptr) {
    processor->release();
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

M3_TEST(vst3_editor_in_tune_needle_is_blue_and_layers_over_scale) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  Steinberg::Vst::IAudioProcessor* processor = nullptr;
  if (component != nullptr) {
    static_cast<void>(component->queryInterface(
        Steinberg::Vst::IAudioProcessor::iid,
        reinterpret_cast<void**>(&processor)));
  }
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3ComponentHandler handler;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(processor != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr && processor != nullptr &&
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

      m3::TunerSnapshot snapshot;
      snapshot.generation = 73U;
      snapshot.state = m3::TunerFrameState::tracking;
      snapshot.voice_count = 1U;
      snapshot.max_polyphony = 8U;
      snapshot.voices[0] = m3::TunerVoice{
          32U, 0, 30000U, 8U, m3::TunerVoiceState::tracking, true};
      m3::vst3::publish_tuner_snapshot_for_test(processor, snapshot);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));

      constexpr std::size_t width =
          static_cast<std::size_t>(m3::vst3::kEditorWidth);
      constexpr std::size_t height =
          static_cast<std::size_t>(m3::vst3::kEditorHeight);
      std::vector<std::uint8_t> rgba(width * height * 4U);
      M3_EXPECT_TRUE(m3::vst3::editor_render_rgba_for_test(
          *view, rgba.data(), rgba.size()));
      M3_EXPECT_TRUE(write_editor_ppm(
          *view, std::getenv("M3_EDITOR_IN_TUNE_SCREENSHOT")));

      const m3::vst3::EditorRect panel =
          m3::vst3::editor_tuner_display_bounds();
      const double lane_left = panel.left + 18.0;
      const double lane_right = panel.right - 18.0;
      const double lane_width = (lane_right - lane_left) / 8.0;
      const double lane_top = panel.top + 42.0;
      const m3::vst3::EditorRect arc =
          m3::vst3::editor_tuner_meter_arc_bounds(
              {lane_left, lane_top, lane_left + lane_width,
               panel.bottom - 15.0});
      const int center_x =
          static_cast<int>(std::lround((arc.left + arc.right) * 0.5));
      const int arc_top = static_cast<int>(std::lround(arc.top));
      const auto is_blue = [&rgba](int x, int y, int margin) noexcept {
        constexpr std::size_t row_width =
            static_cast<std::size_t>(m3::vst3::kEditorWidth);
        const std::size_t offset =
            (static_cast<std::size_t>(y) * row_width +
             static_cast<std::size_t>(x)) *
            4U;
        return rgba[offset + 2U] > rgba[offset] + margin &&
               rgba[offset + 2U] > rgba[offset + 1U] + margin / 3;
      };

      bool blue_core = false;
      bool blue_over_scale = false;
      bool blue_scale_underglow = false;
      bool pale_needle_highlight = false;
      bool wide_soft_bloom = false;
      for (int y = arc_top + 7; y <= arc_top + 22; ++y) {
        for (int x = center_x - 2; x <= center_x + 2; ++x) {
          blue_core = blue_core || is_blue(x, y, 48);
          constexpr std::size_t row_width =
              static_cast<std::size_t>(m3::vst3::kEditorWidth);
          const std::size_t offset =
              (static_cast<std::size_t>(y) * row_width +
               static_cast<std::size_t>(x)) *
              4U;
          pale_needle_highlight =
              pale_needle_highlight ||
              (rgba[offset + 2U] >= 220U && rgba[offset + 1U] >= 145U &&
               rgba[offset + 2U] > rgba[offset] + 80U);
        }
      }
      for (int y = arc_top - 2; y <= arc_top + 3; ++y) {
        for (int x = center_x - 2; x <= center_x + 2; ++x) {
          blue_over_scale = blue_over_scale || is_blue(x, y, 36);
        }
      }
      for (int y = arc_top + 1; y <= arc_top + 10; ++y) {
        for (int x = center_x - 34; x <= center_x + 34; ++x) {
          if (x < center_x - 7 || x > center_x + 7) {
            blue_scale_underglow =
                blue_scale_underglow || is_blue(x, y, 8);
          }
        }
      }
      for (int y = arc_top + 12; y <= arc_top + 25; ++y) {
        for (int x = center_x - 44; x <= center_x + 44; ++x) {
          const int distance = x < center_x ? center_x - x : x - center_x;
          if (distance >= 38 && distance <= 44) {
            wide_soft_bloom = wide_soft_bloom || is_blue(x, y, 5);
          }
        }
      }
      M3_EXPECT_TRUE(blue_core);
      M3_EXPECT_TRUE(blue_over_scale);
      M3_EXPECT_TRUE(blue_scale_underglow);
      M3_EXPECT_TRUE(pale_needle_highlight);
      M3_EXPECT_TRUE(wide_soft_bloom);

      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(controller->setComponentHandler(nullptr),
                 Steinberg::kResultTrue);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
  }
  if (processor != nullptr) {
    processor->release();
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

M3_TEST(vst3_editor_opens_on_tuner_and_settings_toggle_is_parameter_silent) {
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
      M3_EXPECT_FALSE(
          m3::vst3::editor_focus_drawing_enabled_for_test(*view));
      M3_EXPECT_FALSE(m3::vst3::editor_settings_open_for_test(*view));
      M3_EXPECT_TRUE(write_editor_ppm(
          *view, std::getenv("M3_EDITOR_TUNER_SCREENSHOT")));
      M3_EXPECT_TRUE(m3::vst3::editor_control_visible_for_test(
          *view, m3::ParameterId{0x4D330001U}));
      M3_EXPECT_FALSE(m3::vst3::editor_control_visible_for_test(
          *view, m3::ParameterId{0x4D330004U}));
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      M3_EXPECT_TRUE(m3::vst3::editor_settings_open_for_test(*view));
      M3_EXPECT_TRUE(write_editor_ppm(
          *view, std::getenv("M3_EDITOR_SETTINGS_SCREENSHOT")));
      M3_EXPECT_TRUE(m3::vst3::editor_control_visible_for_test(
          *view, m3::ParameterId{0x4D330004U}));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      M3_EXPECT_FALSE(m3::vst3::editor_settings_open_for_test(*view));
      M3_EXPECT_FALSE(m3::vst3::editor_control_visible_for_test(
          *view, m3::ParameterId{0x4D330004U}));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
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
      M3_EXPECT_EQ(handler.edit_call_count(), 1U);
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
      M3_EXPECT_EQ(handler.edit_call_count(), 1U);
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

M3_TEST(vst3_editor_drag_and_wheel_share_one_open_host_gesture) {
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
      constexpr m3::ParameterId kSensitivityId = 0x4D330005U;
      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kSensitivityId, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 1U);
      if (handler.edit_call_count() >= 1U) {
        M3_EXPECT_EQ(handler.edit_call(0U).kind,
                     m3::test::FakeVst3EditKind::begin);
        M3_EXPECT_EQ(handler.edit_call(0U).id, kSensitivityId);
      }

      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, kSensitivityId, -1.0));
      M3_EXPECT_EQ(handler.edit_call_count(), 2U);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.51,
                     1.0e-6);
      if (handler.edit_call_count() >= 2U) {
        M3_EXPECT_EQ(handler.edit_call(1U).kind,
                     m3::test::FakeVst3EditKind::perform);
        M3_EXPECT_NEAR(handler.edit_call(1U).value, 0.51, 1.0e-6);
      }

      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, kSensitivityId, -4.0));
      M3_EXPECT_EQ(handler.edit_call_count(), 3U);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.52,
                     1.0e-6);
      if (handler.edit_call_count() >= 3U) {
        M3_EXPECT_EQ(handler.edit_call(2U).kind,
                     m3::test::FakeVst3EditKind::perform);
        M3_EXPECT_NEAR(handler.edit_call(2U).value, 0.52, 1.0e-6);
      }

      M3_EXPECT_TRUE(m3::vst3::editor_wheel_for_test(
          *view, kSensitivityId, 1.0));
      M3_EXPECT_EQ(handler.edit_call_count(), 4U);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.53,
                     1.0e-6);
      if (handler.edit_call_count() >= 4U) {
        M3_EXPECT_EQ(handler.edit_call(3U).kind,
                     m3::test::FakeVst3EditKind::perform);
        M3_EXPECT_EQ(handler.edit_call(3U).id, kSensitivityId);
        M3_EXPECT_NEAR(handler.edit_call(3U).value, 0.53, 1.0e-6);
      }

      M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
          *view, kSensitivityId));
      M3_EXPECT_EQ(handler.edit_call_count(), 5U);
      if (handler.edit_call_count() >= 5U) {
        M3_EXPECT_EQ(handler.edit_call(4U).kind,
                     m3::test::FakeVst3EditKind::end);
        M3_EXPECT_EQ(handler.edit_call(4U).id, kSensitivityId);
      }
      M3_EXPECT_TRUE(!m3::vst3::editor_pointer_up_for_test(
          *view, kSensitivityId));
      M3_EXPECT_EQ(handler.edit_call_count(), 5U);

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

M3_TEST(vst3_editor_drag_cancel_removal_and_destruction_end_once) {
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
    constexpr m3::ParameterId kSensitivityId = 0x4D330005U;
    auto attach_view = [&]() noexcept {
      Steinberg::IPlugView* view =
          controller->createView(Steinberg::Vst::ViewType::kEditor);
      M3_EXPECT_TRUE(view != nullptr);
      if (view != nullptr) {
        M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
        M3_EXPECT_EQ(view->attached(
                         nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                     Steinberg::kResultOk);
        M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      }
      return view;
    };
    auto begin_and_move = [&](Steinberg::IPlugView& view) noexcept {
      M3_EXPECT_EQ(controller->setParamNormalized(kSensitivityId, 0.5),
                   Steinberg::kResultTrue);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          view, kSensitivityId, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 1U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          view, kSensitivityId, -1.0));
      M3_EXPECT_EQ(handler.edit_call_count(), 2U);
    };
    auto expect_closed_once = [&]() noexcept {
      M3_EXPECT_EQ(handler.edit_call_count(), 3U);
      if (handler.edit_call_count() >= 3U) {
        M3_EXPECT_EQ(handler.edit_call(0U).kind,
                     m3::test::FakeVst3EditKind::begin);
        M3_EXPECT_EQ(handler.edit_call(1U).kind,
                     m3::test::FakeVst3EditKind::perform);
        M3_EXPECT_EQ(handler.edit_call(2U).kind,
                     m3::test::FakeVst3EditKind::end);
        M3_EXPECT_EQ(handler.edit_call(2U).id, kSensitivityId);
      }
    };

    Steinberg::IPlugView* cancel_view = attach_view();
    if (cancel_view != nullptr) {
      begin_and_move(*cancel_view);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *cancel_view, kSensitivityId));
      expect_closed_once();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_cancel_for_test(
          *cancel_view, kSensitivityId));
      expect_closed_once();
      M3_EXPECT_EQ(cancel_view->removed(), Steinberg::kResultOk);
      expect_closed_once();
      M3_EXPECT_EQ(cancel_view->setFrame(nullptr), Steinberg::kResultTrue);
      cancel_view->release();
      expect_closed_once();
    }

    Steinberg::IPlugView* removal_view = attach_view();
    if (removal_view != nullptr) {
      begin_and_move(*removal_view);
      M3_EXPECT_TRUE(m3::vst3::editor_remove_control_for_test(
          *removal_view, kSensitivityId));
      expect_closed_once();
      M3_EXPECT_EQ(removal_view->removed(), Steinberg::kResultOk);
      expect_closed_once();
      M3_EXPECT_EQ(removal_view->setFrame(nullptr), Steinberg::kResultTrue);
      removal_view->release();
      expect_closed_once();
    }

    Steinberg::IPlugView* destruction_view = attach_view();
    if (destruction_view != nullptr) {
      begin_and_move(*destruction_view);
      M3_EXPECT_EQ(destruction_view->removed(), Steinberg::kResultOk);
      expect_closed_once();
      M3_EXPECT_EQ(destruction_view->setFrame(nullptr),
                   Steinberg::kResultTrue);
      destruction_view->release();
      expect_closed_once();
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
        M3_EXPECT_EQ(handler.edit_call_count(), 1U);
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
      constexpr m3::ParameterId kSensitivityId = 0x4D330005U;
      constexpr m3::ParameterId kResponseId = 0x4D330006U;

      // The compact tuner-page ranges are read-only summaries. Precision
      // editing belongs exclusively to the settings page.
      M3_EXPECT_EQ(controller->setParamNormalized(kSensitivityId, 0.5),
                   Steinberg::kResultTrue);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kSensitivityId, 0.90, 0.72, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.5,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kResponseId, 0.10, 0.72, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);

      // The settings-page versions remain continuous knobs.
      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      M3_EXPECT_EQ(controller->setParamNormalized(kSensitivityId, 0.5),
                   Steinberg::kResultTrue);
      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kSensitivityId, 0.5, 0.5, false));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_drag_for_test(
          *view, kSensitivityId, -20.0));
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_up_for_test(
          *view, kSensitivityId));
      expect_single_edit(handler, kSensitivityId, 0.6);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.6,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_wheel_for_test(
          *view, kSensitivityId, 1.0));
      expect_single_edit(handler, kSensitivityId, 0.61);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.61,
                     1.0e-6);

      handler.reset();
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kSensitivityId, 0.5, 0.5, true));
      expect_single_edit(handler, kSensitivityId, 0.5);
      M3_EXPECT_NEAR(controller->getParamNormalized(kSensitivityId), 0.5,
                     1.0e-6);
      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));

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

M3_TEST(vst3_editor_external_velocity_mode_invalidates_fixed_velocity) {
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
      constexpr m3::ParameterId kVelocityModeId = 0x4D33000BU;
      constexpr m3::ParameterId kFixedVelocityId = 0x4D33000CU;
      const std::size_t before_fixed =
          m3::vst3::editor_control_invalidation_count_for_test(
              *view, kFixedVelocityId);

      handler.reset();
      M3_EXPECT_EQ(controller->setParamNormalized(kVelocityModeId, 0.0),
                   Steinberg::kResultTrue);
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_EQ(
          m3::vst3::editor_control_invalidation_count_for_test(
              *view, kFixedVelocityId),
          before_fixed + 1U);

      M3_EXPECT_EQ(controller->setParamNormalized(kVelocityModeId, 1.0),
                   Steinberg::kResultTrue);
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);
      M3_EXPECT_EQ(
          m3::vst3::editor_control_invalidation_count_for_test(
              *view, kFixedVelocityId),
          before_fixed + 2U);
      M3_EXPECT_TRUE(m3::vst3::editor_pointer_down_for_test(
          *view, kFixedVelocityId, 0.5, 0.5, false));
      M3_EXPECT_EQ(handler.edit_call_count(), 0U);

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

M3_TEST(vst3_editor_double_click_tuner_lane_requests_physical_string_calibration) {
  Steinberg::IPluginFactory* factory = GetPluginFactory();
  Steinberg::Vst::IComponent* component = nullptr;
  Steinberg::Vst::IEditController* controller =
      create_controller(factory, component);
  Steinberg::Vst::IAudioProcessor* processor = nullptr;
  if (component != nullptr) {
    static_cast<void>(component->queryInterface(
        Steinberg::Vst::IAudioProcessor::iid,
        reinterpret_cast<void**>(&processor)));
  }
  m3::test::FakeVst3Host host;
  m3::test::FakeVst3PlugFrame plug_frame;
  const VSTGUI::LinuxFactory* platform_factory =
      VSTGUI::getPlatformFactory().asLinuxFactory();
  const auto run_loop = VSTGUI::makeOwned<FakeVstguiRunLoop>();
  M3_EXPECT_TRUE(component != nullptr);
  M3_EXPECT_TRUE(controller != nullptr);
  M3_EXPECT_TRUE(processor != nullptr);
  M3_EXPECT_TRUE(platform_factory != nullptr);
  if (component != nullptr && controller != nullptr && processor != nullptr &&
      platform_factory != nullptr) {
    platform_factory->setRunLoop(run_loop);
    M3_EXPECT_EQ(component->initialize(&host), Steinberg::kResultOk);
    Steinberg::Vst::ProcessSetup setup{};
    setup.processMode = Steinberg::Vst::kRealtime;
    setup.symbolicSampleSize = Steinberg::Vst::kSample32;
    setup.maxSamplesPerBlock = 512;
    setup.sampleRate = 48000.0;
    M3_EXPECT_EQ(processor->setupProcessing(setup), Steinberg::kResultOk);
    M3_EXPECT_EQ(component->setActive(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(processor->setProcessing(Steinberg::TBool{1}),
                 Steinberg::kResultOk);
    Steinberg::IPlugView* view =
        controller->createView(Steinberg::Vst::ViewType::kEditor);
    M3_EXPECT_TRUE(view != nullptr);
    if (view != nullptr) {
      M3_EXPECT_EQ(view->setFrame(&plug_frame), Steinberg::kResultTrue);
      M3_EXPECT_EQ(view->attached(
                       nullptr, Steinberg::kPlatformTypeWaylandSurfaceID),
                   Steinberg::kResultOk);
      M3_EXPECT_EQ(
          m3::vst3::editor_pending_calibration_command_for_test(*view), 0U);
      M3_EXPECT_TRUE(
          m3::vst3::editor_double_click_tuner_lane_for_test(*view, 5U));
      M3_EXPECT_EQ(
          m3::vst3::editor_pending_calibration_command_for_test(*view), 6U);
      Steinberg::Vst::ProcessData flush{};
      flush.processMode = Steinberg::Vst::kRealtime;
      flush.symbolicSampleSize = Steinberg::Vst::kSample32;
      flush.numSamples = 0;
      M3_EXPECT_EQ(processor->process(flush), Steinberg::kResultOk);
      M3_EXPECT_TRUE(m3::vst3::editor_refresh_tuner_for_test(*view));
      M3_EXPECT_TRUE(write_editor_ppm(
          *view, std::getenv("M3_EDITOR_CALIBRATION_SCREENSHOT")));
      M3_EXPECT_EQ(
          m3::vst3::editor_pending_calibration_command_for_test(*view), 0U);

      M3_EXPECT_TRUE(m3::vst3::editor_toggle_settings_for_test(*view));
      static_cast<void>(
          m3::vst3::editor_double_click_tuner_lane_for_test(*view, 2U));
      M3_EXPECT_EQ(
          m3::vst3::editor_pending_calibration_command_for_test(*view), 0U);
      M3_EXPECT_EQ(view->removed(), Steinberg::kResultOk);
      M3_EXPECT_EQ(view->setFrame(nullptr), Steinberg::kResultTrue);
      view->release();
    }
    M3_EXPECT_EQ(processor->setProcessing(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(component->setActive(Steinberg::TBool{0}),
                 Steinberg::kResultOk);
    M3_EXPECT_EQ(component->terminate(), Steinberg::kResultOk);
    platform_factory->setRunLoop({});
  }
  if (controller != nullptr) {
    controller->release();
  }
  if (processor != nullptr) {
    processor->release();
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
      Steinberg::ViewRect resized{0, 0, 1200, 900};
      M3_EXPECT_EQ(view->onSize(&resized), Steinberg::kResultTrue);
      M3_EXPECT_TRUE(m3::vst3::editor_control_bounds_for_test(
          *view, 0x4D330005U, after));
      M3_EXPECT_TRUE(after.left > before.left);
      M3_EXPECT_TRUE(after.top > before.top);
      M3_EXPECT_TRUE(after.right > before.right);
      M3_EXPECT_TRUE(after.bottom > before.bottom);
      M3_EXPECT_NEAR(after.left, before.left * 1200.0 /
                                      static_cast<double>(m3::vst3::kEditorWidth),
                     1.0e-6);
      M3_EXPECT_NEAR(after.top, before.top * 900.0 /
                                     static_cast<double>(m3::vst3::kEditorHeight),
                     1.0e-6);
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
