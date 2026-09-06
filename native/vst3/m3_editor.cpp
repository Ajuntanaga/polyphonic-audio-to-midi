#include "m3_editor.hpp"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <new>

#include "m3_editor_layout.hpp"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cviewcontainer.h"
#include "vstgui/plugin-bindings/vst3editor.h"
#include "vstgui/uidescription/iuidescription.h"
#include "vstgui/uidescription/uiattributes.h"
#include "vstgui/uidescription/uicontentprovider.h"
#include "vstgui/uidescription/uidescription.h"

namespace m3::vst3 {
namespace {

constexpr Steinberg::int32 kEditorWidth = 1024;
constexpr Steinberg::int32 kEditorHeight = 620;
constexpr Steinberg::int32 kEditorMaximumWidth = 2048;
constexpr Steinberg::int32 kEditorMaximumHeight = 1240;
constexpr char kEditorTemplateName[] = "M3Editor";
constexpr char kRootViewName[] = "M3RootSurface";
constexpr char kEditorDescription[] = R"(
{
  "vstgui-ui-description": {
    "version": "1",
    "templates": {
      "M3Editor": {
        "attributes": {
          "autosize": "left right top bottom",
          "class": "CViewContainer",
          "custom-view-name": "M3RootSurface",
          "maxSize": "2048, 1240",
          "minSize": "1024, 620",
          "mouse-enabled": "true",
          "opacity": "1",
          "origin": "0, 0",
          "size": "1024, 620",
          "transparent": "false"
        }
      }
    }
  }
}
)";

class StaticEditorDescription final : public VSTGUI::UIDescription {
 public:
  StaticEditorDescription()
      : StaticEditorDescription(new VSTGUI::MemoryContentProvider(
            kEditorDescription,
            static_cast<std::uint32_t>(sizeof(kEditorDescription) - 1U))) {}

 private:
  explicit StaticEditorDescription(VSTGUI::MemoryContentProvider* provider)
      : VSTGUI::UIDescription(provider), provider_(provider) {}

  std::unique_ptr<VSTGUI::MemoryContentProvider> provider_;
};

class M3RootSurface final : public VSTGUI::CViewContainer {
 public:
  M3RootSurface()
      : VSTGUI::CViewContainer(
            VSTGUI::CRect(0.0, 0.0, kEditorWidth, kEditorHeight)) {
    setBackgroundColor(VSTGUI::CColor(24U, 27U, 32U, 255U));
    const PersistentConfig config{};
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      layouts_[index] = editor_control_layout(index, config, Status::ready);
    }
  }

 private:
  std::array<EditorControlLayout, kEditorControlCount> layouts_{};
};

class M3Editor final : public VSTGUI::VST3Editor {
 public:
  explicit M3Editor(Steinberg::Vst::EditController& edit_controller)
      : VSTGUI::VST3Editor(new StaticEditorDescription(), &edit_controller,
                           kEditorTemplateName) {
    getUIDescription()->forget();
    setRect(Steinberg::ViewRect(0, 0, kEditorWidth, kEditorHeight));
    static_cast<void>(setEditorSizeConstrains(
        VSTGUI::CPoint(kEditorWidth, kEditorHeight),
        VSTGUI::CPoint(kEditorMaximumWidth, kEditorMaximumHeight)));
  }

 protected:
  ~M3Editor() override = default;

  VSTGUI::CView* createView(
      const VSTGUI::UIAttributes& attributes,
      const VSTGUI::IUIDescription* ui_description) override {
    const std::string* custom_view = attributes.getAttributeValue(
        VSTGUI::IUIDescription::kCustomViewName);
    if (custom_view != nullptr && *custom_view == kRootViewName) {
      return new (std::nothrow) M3RootSurface();
    }
    return VSTGUI::VST3Editor::createView(attributes, ui_description);
  }

  Steinberg::tresult PLUGIN_API setContentScaleFactor(
      ScaleFactor factor) override {
    const double requested_factor = static_cast<double>(factor);
    Steinberg::int32 scaled_width = 0;
    Steinberg::int32 scaled_height = 0;
    if (!std::isfinite(requested_factor) || requested_factor <= 0.0 ||
        !physical_extent(logical_width_, requested_factor, scaled_width) ||
        !physical_extent(logical_height_, requested_factor, scaled_height)) {
      return Steinberg::kInvalidArgument;
    }
    const double previous_factor = getContentScaleFactor();
    if (requested_factor == previous_factor) {
      return Steinberg::kResultOk;
    }
    const Steinberg::ViewRect previous_rect = getRect();
    const Steinberg::tresult result =
        VSTGUI::VST3Editor::setContentScaleFactor(factor);
    if (result == Steinberg::kResultOk) {
      Steinberg::ViewRect scaled = previous_rect;
      scaled.right = scaled.left + scaled_width;
      scaled.bottom = scaled.top + scaled_height;
      if (plugFrame) {
        if (requestResize(
                VSTGUI::CPoint(scaled.getWidth(), scaled.getHeight()))) {
          return Steinberg::kResultOk;
        }
        static_cast<void>(VSTGUI::VST3Editor::setContentScaleFactor(
            static_cast<ScaleFactor>(previous_factor)));
        return Steinberg::kResultFalse;
      }
      setRect(scaled);
    }
    return result;
  }

  Steinberg::tresult PLUGIN_API onSize(
      Steinberg::ViewRect* new_size) override {
    if (new_size == nullptr) {
      return Steinberg::kInvalidArgument;
    }
    const Steinberg::tresult result = VSTGUI::VST3Editor::onSize(new_size);
    if (result == Steinberg::kResultOk) {
      const double factor = getContentScaleFactor();
      Steinberg::int32 expected_width = 0;
      Steinberg::int32 expected_height = 0;
      const bool matches_logical_size =
          physical_extent(logical_width_, factor, expected_width) &&
          physical_extent(logical_height_, factor, expected_height) &&
          new_size->getWidth() == expected_width &&
          new_size->getHeight() == expected_height;
      if (!matches_logical_size) {
        logical_width_ = static_cast<double>(new_size->getWidth()) / factor;
        logical_height_ = static_cast<double>(new_size->getHeight()) / factor;
      }
    }
    return result;
  }

 private:
  static bool physical_extent(double logical_extent, double factor,
                              Steinberg::int32& physical) noexcept {
    const double scaled = std::floor(logical_extent * factor);
    if (!std::isfinite(scaled) || scaled < 0.0 ||
        scaled > static_cast<double>(
                     std::numeric_limits<Steinberg::int32>::max())) {
      return false;
    }
    physical = static_cast<Steinberg::int32>(scaled);
    return true;
  }

  double logical_width_{static_cast<double>(kEditorWidth)};
  double logical_height_{static_cast<double>(kEditorHeight)};
};

}  // internal

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept {
  return new (std::nothrow) M3Editor(controller);
}

}  // namespace m3::vst3
