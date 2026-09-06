#include "m3_editor.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
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
};

}  // internal

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept {
  return new (std::nothrow) M3Editor(controller);
}

}  // namespace m3::vst3
