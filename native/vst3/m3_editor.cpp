#include "m3_editor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>

#include "m3_editor_layout.hpp"
#include "vst3_parameter_bridge.hpp"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/cfont.h"
#include "vstgui/lib/cgradient.h"
#include "vstgui/lib/cgraphicspath.h"
#include "vstgui/lib/controls/ccontrol.h"
#include "vstgui/lib/cviewcontainer.h"
#include "vstgui/lib/events.h"
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
constexpr ParameterId kDetectorInputId = 0x4D330001U;
constexpr ParameterId kProfileModeId = 0x4D330002U;
constexpr ParameterId kLowestMidiNoteId = 0x4D330007U;
constexpr ParameterId kHighestMidiNoteId = 0x4D330008U;
constexpr ParameterId kVelocityModeId = 0x4D33000BU;
constexpr ParameterId kFixedVelocityId = 0x4D33000CU;

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

const VSTGUI::CColor kGraphite{17U, 20U, 25U, 255U};
const VSTGUI::CColor kPanelTop{34U, 39U, 47U, 255U};
const VSTGUI::CColor kPanelBottom{23U, 27U, 33U, 255U};
const VSTGUI::CColor kPanelEdge{61U, 69U, 80U, 255U};
const VSTGUI::CColor kText{231U, 238U, 244U, 255U};
const VSTGUI::CColor kMuted{137U, 150U, 163U, 255U};
const VSTGUI::CColor kCyan{23U, 218U, 232U, 255U};
const VSTGUI::CColor kAmber{238U, 174U, 61U, 255U};
const VSTGUI::CColor kRed{233U, 71U, 78U, 255U};

bool result_ok(Steinberg::tresult result) noexcept {
  return result == Steinberg::kResultOk || result == Steinberg::kResultTrue;
}

bool canonical_editor_value(ParameterId id, double requested,
                            VelocityMode velocity_mode,
                            double& normalized) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  double plain = 0.0;
  if (spec == nullptr || spec->read_only ||
      (id == kFixedVelocityId && velocity_mode != VelocityMode::fixed) ||
      !canonical_normalized_value(*spec, requested, plain)) {
    return false;
  }
  normalized = plain_to_normalized(*spec, plain);
  return std::isfinite(normalized);
}

EditorGesture perform_editor_gesture(
    Steinberg::Vst::EditController& controller, ParameterId id,
    double requested, VelocityMode velocity_mode) noexcept {
  EditorGesture output{id, requested, false};
  double normalized = 0.0;
  if (!canonical_editor_value(id, requested, velocity_mode, normalized)) {
    return output;
  }
  output.normalized_value = normalized;
  if (!result_ok(controller.beginEdit(id))) {
    return output;
  }
  const bool set = result_ok(controller.setParamNormalized(id, normalized));
  const bool performed = set && result_ok(controller.performEdit(id, normalized));
  const bool ended = result_ok(controller.endEdit(id));
  output.accepted = set && performed && ended;
  return output;
}

VSTGUI::CColor status_deck_color(Status status) noexcept {
  switch (status) {
    case Status::ready:
      return kCyan;
    case Status::panic_hold:
      return kAmber;
    case Status::reconfiguring:
      return VSTGUI::CColor(18U, 151U, 164U, 255U);
    case Status::midi_output_blocked:
      return VSTGUI::CColor(196U, 124U, 34U, 255U);
    case Status::invalid_input_or_state:
      return kRed;
    case Status::unsupported_layout:
      return VSTGUI::CColor(190U, 55U, 62U, 255U);
  }
  return kRed;
}

void draw_rounded_gradient(VSTGUI::CDrawContext* context,
                           const VSTGUI::CRect& rect,
                           const VSTGUI::CColor& top,
                           const VSTGUI::CColor& bottom,
                           const VSTGUI::CColor& edge,
                           VSTGUI::CCoord radius = 10.0) {
  if (context == nullptr) {
    return;
  }
  auto path = VSTGUI::owned(context->createGraphicsPath());
  if (!path) {
    return;
  }
  path->addRoundRect(rect, radius);
  auto gradient = VSTGUI::owned(path->createGradient(0.0, 1.0, top, bottom));
  if (gradient) {
    context->fillLinearGradient(path, *gradient, rect.getTopLeft(),
                                rect.getBottomLeft(), false);
  } else {
    context->setFillColor(bottom);
    context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathFilled);
  }
  context->setFrameColor(edge);
  context->setLineWidth(1.0);
  context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathStroked);
}

VSTGUI::CRect to_rect(const EditorRect& rect) noexcept {
  return VSTGUI::CRect(rect.left, rect.top, rect.right, rect.bottom);
}

const char* const* segment_labels(ParameterId id,
                                  std::size_t& count) noexcept {
  static const char* const kInputLabels[] = {"LEFT", "RIGHT", "DOWNMIX"};
  static const char* const kModeLabels[] = {"M3 8-STRING", "GENERAL"};
  static const char* const kVelocityLabels[] = {"FIXED", "DYNAMIC"};
  count = 0U;
  if (id == kDetectorInputId) {
    count = std::size(kInputLabels);
    return kInputLabels;
  }
  if (id == kProfileModeId) {
    count = std::size(kModeLabels);
    return kModeLabels;
  }
  if (id == kVelocityModeId) {
    count = std::size(kVelocityLabels);
    return kVelocityLabels;
  }
  return nullptr;
}

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

class M3DeckControl final : public VSTGUI::CControl {
 public:
  M3DeckControl(const EditorControlLayout& layout,
                VSTGUI::IControlListener* control_listener,
                Steinberg::Vst::EditController& controller)
      : VSTGUI::CControl(to_rect(layout.bounds), control_listener,
                         static_cast<Steinberg::int32>(layout.parameter_id)),
        layout_(layout),
        controller_(controller) {
    if (layout_.parameter_id == kFixedVelocityId) {
      // Keep the dependent control recessed but focusable so switching to
      // Fixed mode immediately makes it actionable without rebuilding views.
      layout_.visible = true;
      layout_.enabled = true;
    }
    setWantsFocus(layout_.enabled);
    const ParameterSpec* spec = find_parameter(layout.parameter_id);
    if (spec != nullptr) {
      setTooltipText(spec->name);
      setDefaultValue(static_cast<float>(plain_to_normalized(
          *spec, spec->default_value)));
      setWheelInc(1.0F / static_cast<float>(spec->step_count));
    }
    if (!layout_.enabled) {
      setMouseEnabled(false);
    }
  }

  void draw(VSTGUI::CDrawContext* context) override {
    if (context == nullptr) {
      return;
    }
    const double normalized = std::clamp(
        controller_.getParamNormalized(layout_.parameter_id), 0.0, 1.0);
    setValueNormalized(static_cast<float>(normalized));
    switch (layout_.presentation) {
      case EditorPresentation::knob:
        draw_knob(context, normalized);
        break;
      case EditorPresentation::segment:
        draw_segment(context, normalized);
        break;
      case EditorPresentation::toggle:
        draw_toggle(context, normalized);
        break;
      case EditorPresentation::note_range:
        draw_note_range(context, normalized);
        break;
      case EditorPresentation::momentary:
        draw_momentary(context);
        break;
      case EditorPresentation::status:
        draw_status(context, normalized);
        break;
    }
    setDirty(false);
  }

  VSTGUI::CMouseEventResult onMouseDown(
      VSTGUI::CPoint& where,
      const VSTGUI::CButtonState& buttons) override {
    if (!layout_.enabled || !buttons.isLeftButton() ||
        !interaction_allowed()) {
      return VSTGUI::kMouseEventNotHandled;
    }
    if (layout_.presentation == EditorPresentation::momentary) {
      panic_pressed_ = emit(1.0);
      return panic_pressed_ ? VSTGUI::kMouseEventHandled
                            : VSTGUI::kMouseEventNotHandled;
    }
    double requested = getValueNormalized();
    if (layout_.presentation == EditorPresentation::toggle) {
      requested = requested >= 0.5 ? 0.0 : 1.0;
    } else if (layout_.presentation == EditorPresentation::segment) {
      std::size_t count = 0U;
      static_cast<void>(segment_labels(layout_.parameter_id, count));
      const double width = std::max(1.0, getViewSize().getWidth());
      const double unit = std::clamp(
          (where.x - getViewSize().left) / width, 0.0, 0.999999);
      const std::size_t selected = std::min(
          count - 1U,
          static_cast<std::size_t>(unit * static_cast<double>(count)));
      requested = static_cast<double>(selected) /
                  static_cast<double>(count - 1U);
    } else {
      const double height = std::max(1.0, getViewSize().getHeight());
      requested = std::clamp(
          (getViewSize().bottom - where.y) / height, 0.0, 1.0);
    }
    return emit(requested) ? VSTGUI::kMouseEventHandled
                           : VSTGUI::kMouseEventNotHandled;
  }

  VSTGUI::CMouseEventResult onMouseUp(
      VSTGUI::CPoint&,
      const VSTGUI::CButtonState&) override {
    if (!panic_pressed_) {
      return VSTGUI::kMouseEventNotHandled;
    }
    panic_pressed_ = false;
    static_cast<void>(emit(0.0));
    return VSTGUI::kMouseEventHandled;
  }

  void onKeyboardEvent(VSTGUI::KeyboardEvent& event) override {
    if (event.type != VSTGUI::EventType::KeyDown || !layout_.enabled ||
        !interaction_allowed()) {
      return;
    }
    if (layout_.presentation == EditorPresentation::momentary &&
        (event.virt == VSTGUI::VirtualKey::Space ||
         event.virt == VSTGUI::VirtualKey::Return ||
         event.virt == VSTGUI::VirtualKey::Enter)) {
      static_cast<void>(editor_panic_for_test(controller_));
      event.consumed = true;
      invalid();
      return;
    }
    double delta = 0.0;
    if (event.virt == VSTGUI::VirtualKey::Up ||
        event.virt == VSTGUI::VirtualKey::Right) {
      delta = getWheelInc();
    } else if (event.virt == VSTGUI::VirtualKey::Down ||
               event.virt == VSTGUI::VirtualKey::Left) {
      delta = -getWheelInc();
    } else if ((event.virt == VSTGUI::VirtualKey::Space ||
                event.virt == VSTGUI::VirtualKey::Return ||
                event.virt == VSTGUI::VirtualKey::Enter) &&
               layout_.presentation == EditorPresentation::toggle) {
      delta = getValueNormalized() >= 0.5F ? -1.0 : 1.0;
    } else {
      return;
    }
    static_cast<void>(emit(
        std::clamp(static_cast<double>(getValueNormalized()) + delta,
                   0.0, 1.0)));
    event.consumed = true;
  }

 private:
  bool interaction_allowed() const noexcept {
    return layout_.parameter_id != kFixedVelocityId ||
           controller_.getParamNormalized(kVelocityModeId) < 0.5;
  }

  bool emit(double requested) {
    const VelocityMode velocity_mode =
        controller_.getParamNormalized(kVelocityModeId) >= 0.5
            ? VelocityMode::dynamic
            : VelocityMode::fixed;
    const EditorGesture gesture = perform_editor_gesture(
        controller_, layout_.parameter_id, requested, velocity_mode);
    if (!gesture.accepted) {
      return false;
    }
    setValueNormalized(static_cast<float>(gesture.normalized_value));
    invalid();
    if (VSTGUI::CView* parent = getParentView()) {
      parent->invalid();
    }
    return true;
  }

  void draw_label(VSTGUI::CDrawContext* context, const char* label,
                  const VSTGUI::CRect& rect,
                  const VSTGUI::CColor& color = kMuted,
                  VSTGUI::CHoriTxtAlign align = VSTGUI::kCenterText) const {
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(color);
    context->drawString(label, rect, align, true);
  }

  void parameter_text(double normalized, char (&text)[128]) const noexcept {
    text[0] = '\0';
    const ParameterSpec* spec = find_parameter(layout_.parameter_id);
    if (spec != nullptr) {
      static_cast<void>(parameter_value_to_text(
          layout_.parameter_id, normalized_to_plain(*spec, normalized), text,
          static_cast<std::uint32_t>(sizeof(text))));
    }
  }

  void draw_knob(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    const bool suppressed = !interaction_allowed();
    if (suppressed) {
      draw_rounded_gradient(context, bounds,
                            VSTGUI::CColor(27U, 31U, 37U, 255U), kGraphite,
                            kPanelEdge, 8.0);
      draw_label(context, "FIXED VELOCITY",
                 VSTGUI::CRect(bounds.left, bounds.top + 28.0, bounds.right,
                                bounds.top + 52.0),
                 kMuted);
      draw_label(context, "AVAILABLE IN FIXED MODE",
                 VSTGUI::CRect(bounds.left, bounds.top + 54.0, bounds.right,
                                bounds.top + 80.0),
                 kAmber);
      return;
    }
    const VSTGUI::CCoord diameter =
        std::min(bounds.getWidth(), bounds.getHeight() - 28.0);
    const VSTGUI::CPoint center(bounds.getCenter().x, bounds.top + diameter / 2.0);
    VSTGUI::CRect dial(center.x - diameter / 2.0, center.y - diameter / 2.0,
                       center.x + diameter / 2.0, center.y + diameter / 2.0);
    dial.inset(9.0, 9.0);
    context->setFillColor(VSTGUI::CColor(42U, 48U, 56U, 255U));
    context->setFrameColor(kPanelEdge);
    context->setLineWidth(2.0);
    context->drawEllipse(dial, VSTGUI::kDrawFilledAndStroked);
    context->setFrameColor(kCyan);
    context->setLineWidth(4.0);
    context->drawArc(dial, 135.0,
                     static_cast<float>(135.0 + normalized * 270.0),
                     VSTGUI::kDrawStroked);
    const double angle = (135.0 + normalized * 270.0) *
                         VSTGUI::Constants::pi / 180.0;
    const double radius = dial.getWidth() * 0.32;
    context->setFrameColor(kText);
    context->setLineWidth(2.0);
    context->drawLine(center,
                      VSTGUI::CPoint(center.x + std::cos(angle) * radius,
                                    center.y + std::sin(angle) * radius));
    char value_text[128]{};
    parameter_text(normalized, value_text);
    draw_label(context, value_text,
               VSTGUI::CRect(bounds.left, bounds.bottom - 36.0,
                              bounds.right, bounds.bottom - 18.0),
               kText);
    const ParameterSpec* spec = find_parameter(layout_.parameter_id);
    draw_label(context, spec == nullptr ? "" : spec->name,
               VSTGUI::CRect(bounds.left, bounds.bottom - 18.0,
                              bounds.right, bounds.bottom),
               kAmber);
  }

  void draw_segment(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_gradient(context, bounds, kPanelTop, kPanelBottom, kPanelEdge,
                          8.0);
    std::size_t count = 0U;
    const char* const* labels = segment_labels(layout_.parameter_id, count);
    if (labels == nullptr || count < 2U) {
      return;
    }
    const std::size_t selected = static_cast<std::size_t>(
        std::llround(normalized * static_cast<double>(count - 1U)));
    const double width = bounds.getWidth() / static_cast<double>(count);
    for (std::size_t index = 0; index < count; ++index) {
      VSTGUI::CRect segment(
          bounds.left + width * static_cast<double>(index), bounds.top,
          bounds.left + width * static_cast<double>(index + 1U),
          bounds.bottom);
      if (index == selected) {
        segment.inset(3.0, 3.0);
        context->setFillColor(VSTGUI::CColor(18U, 95U, 105U, 255U));
        context->drawRect(segment, VSTGUI::kDrawFilled);
      }
      draw_label(context, labels[index], segment,
                 index == selected ? kCyan : kMuted);
    }
  }

  void draw_toggle(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_gradient(context, bounds, kPanelTop, kPanelBottom, kPanelEdge,
                          bounds.getHeight() / 2.0);
    VSTGUI::CRect lamp = bounds;
    lamp.inset(10.0, 10.0);
    lamp.setWidth(lamp.getHeight());
    if (normalized >= 0.5) {
      lamp.offset(bounds.getWidth() - lamp.getWidth() - 20.0, 0.0);
    }
    context->setFillColor(normalized >= 0.5 ? kCyan : kMuted);
    context->drawEllipse(lamp, VSTGUI::kDrawFilled);
    draw_label(context, normalized >= 0.5 ? "DRY AUDIO  ON" : "DRY AUDIO  OFF",
               bounds, normalized >= 0.5 ? kText : kMuted);
  }

  void draw_note_range(VSTGUI::CDrawContext* context,
                       double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_gradient(context, bounds, kPanelTop, kPanelBottom, kCyan,
                          8.0);
    char value_text[128]{};
    parameter_text(normalized, value_text);
    context->setFont(VSTGUI::kNormalFontBig);
    context->setFontColor(kText);
    context->drawString(value_text,
                        VSTGUI::CRect(bounds.left, bounds.top + 8.0,
                                     bounds.right, bounds.bottom - 18.0),
                        VSTGUI::kCenterText, true);
    draw_label(context,
               layout_.parameter_id == kLowestMidiNoteId ? "LOW · LINKED RANGE"
                                                         : "HIGH · LINKED RANGE",
               VSTGUI::CRect(bounds.left, bounds.bottom - 22.0,
                              bounds.right, bounds.bottom),
               kCyan);
  }

  void draw_momentary(VSTGUI::CDrawContext* context) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_gradient(context, bounds,
                          panic_pressed_ ? kRed
                                         : VSTGUI::CColor(83U, 29U, 34U, 255U),
                          VSTGUI::CColor(41U, 19U, 23U, 255U), kRed, 8.0);
    draw_label(context, panic_pressed_ ? "PANIC HELD" : "PANIC", bounds,
               kText);
  }

  void draw_status(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    const int status_index = std::clamp(
        static_cast<int>(std::llround(normalized * 5.0)), 0, 5);
    const Status status = static_cast<Status>(status_index);
    draw_rounded_gradient(context, bounds, kPanelTop, kPanelBottom,
                          status_deck_color(status), 8.0);
    draw_label(context, "M3  /  POLYPHONIC AUDIO → MIDI  /  CAUSAL LIVE",
               VSTGUI::CRect(bounds.left + 14.0, bounds.top,
                              bounds.right - 190.0, bounds.bottom),
               kText, VSTGUI::kLeftText);
    draw_label(context, status_label(status),
               VSTGUI::CRect(bounds.right - 185.0, bounds.top,
                              bounds.right - 14.0, bounds.bottom),
               status_deck_color(status), VSTGUI::kRightText);
  }

  EditorControlLayout layout_;
  Steinberg::Vst::EditController& controller_;
  bool panic_pressed_{};

  CLASS_METHODS_NOCOPY(M3DeckControl, VSTGUI::CControl)
};

class M3RootSurface final : public VSTGUI::CViewContainer {
 public:
  M3RootSurface(VSTGUI::IControlListener* listener,
                Steinberg::Vst::EditController& controller)
      : VSTGUI::CViewContainer(
            VSTGUI::CRect(0.0, 0.0, kEditorWidth, kEditorHeight)) {
    setBackgroundColor(kGraphite);
    const PersistentConfig config{};
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      layouts_[index] = editor_control_layout(index, config, Status::ready);
      controls_[index] =
          new (std::nothrow) M3DeckControl(layouts_[index], listener, controller);
      if (controls_[index] != nullptr) {
        static_cast<void>(addView(controls_[index]));
      }
    }
  }

  VSTGUI::CControl* control_at(std::size_t index) const noexcept {
    return index < controls_.size() ? controls_[index] : nullptr;
  }

  void drawBackgroundRect(VSTGUI::CDrawContext* context,
                          const VSTGUI::CRect&) override {
    if (context == nullptr) {
      return;
    }
    const VSTGUI::CRect bounds = getViewSize();
    context->setFillColor(kGraphite);
    context->drawRect(bounds, VSTGUI::kDrawFilled);
    draw_rounded_gradient(context, VSTGUI::CRect(14.0, 84.0, 1010.0, 262.0),
                          VSTGUI::CColor(27U, 32U, 39U, 255U), kGraphite,
                          kPanelEdge, 12.0);
    draw_rounded_gradient(context, VSTGUI::CRect(14.0, 270.0, 1010.0, 412.0),
                          VSTGUI::CColor(25U, 33U, 40U, 255U), kGraphite,
                          VSTGUI::CColor(26U, 120U, 130U, 255U), 12.0);
    context->setFillColor(kCyan);
    context->drawRect(VSTGUI::CRect(216.0, 334.0, 244.0, 346.0),
                      VSTGUI::kDrawFilled);
    draw_rounded_gradient(context, VSTGUI::CRect(14.0, 424.0, 1010.0, 596.0),
                          VSTGUI::CColor(30U, 31U, 38U, 255U), kGraphite,
                          kPanelEdge, 12.0);
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(kAmber);
    context->drawString("SOURCE + TUNING", VSTGUI::CRect(24.0, 92.0, 500.0, 116.0),
                        VSTGUI::kLeftText, true);
    context->setFontColor(kCyan);
    context->drawString("TRACKING", VSTGUI::CRect(522.0, 92.0, 1000.0, 116.0),
                        VSTGUI::kLeftText, true);
    context->drawString("PERFORMANCE RANGE", VSTGUI::CRect(24.0, 278.0, 440.0, 298.0),
                        VSTGUI::kLeftText, true);
    context->setFontColor(kMuted);
    context->drawString("ADVANCED  ·  LIVE ROUTING", VSTGUI::CRect(24.0, 430.0, 700.0, 452.0),
                        VSTGUI::kLeftText, true);
  }

 private:
  std::array<EditorControlLayout, kEditorControlCount> layouts_{};
  std::array<M3DeckControl*, kEditorControlCount> controls_{};
};

class M3Editor final : public VSTGUI::VST3Editor {
 public:
  explicit M3Editor(Steinberg::Vst::EditController& edit_controller)
      : VSTGUI::VST3Editor(new StaticEditorDescription(), &edit_controller,
                           kEditorTemplateName),
        edit_controller_(edit_controller) {
    getUIDescription()->forget();
    setRect(Steinberg::ViewRect(0, 0, kEditorWidth, kEditorHeight));
    static_cast<void>(setEditorSizeConstrains(
        VSTGUI::CPoint(kEditorWidth, kEditorHeight),
        VSTGUI::CPoint(kEditorMaximumWidth, kEditorMaximumHeight)));
    enableTooltips(true);
  }

 protected:
  ~M3Editor() override = default;

  VSTGUI::CView* createView(
      const VSTGUI::UIAttributes& attributes,
      const VSTGUI::IUIDescription* ui_description) override {
    const std::string* custom_view = attributes.getAttributeValue(
        VSTGUI::IUIDescription::kCustomViewName);
    if (custom_view != nullptr && *custom_view == kRootViewName) {
      auto* surface =
          new (std::nothrow) M3RootSurface(this, edit_controller_);
      if (surface == nullptr) {
        return nullptr;
      }
      VSTGUI::UIAttributes control_attributes;
      for (std::size_t index = 0; index < kEditorControlCount; ++index) {
        if (VSTGUI::CControl* control = surface->control_at(index)) {
          static_cast<void>(verifyView(control, control_attributes,
                                       ui_description));
        }
      }
      return surface;
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

  Steinberg::Vst::EditController& edit_controller_;
  double logical_width_{static_cast<double>(kEditorWidth)};
  double logical_height_{static_cast<double>(kEditorHeight)};
};

}  // namespace

EditorGesture editor_gesture_for_test(
    Steinberg::Vst::EditController& controller, ParameterId parameter_id,
    double normalized_value, VelocityMode velocity_mode) noexcept {
  return perform_editor_gesture(controller, parameter_id, normalized_value,
                                velocity_mode);
}

bool editor_panic_for_test(
    Steinberg::Vst::EditController& controller) noexcept {
  const EditorGesture press = perform_editor_gesture(
      controller, kPanicParameterId, 1.0, VelocityMode::fixed);
  const EditorGesture reset = perform_editor_gesture(
      controller, kPanicParameterId, 0.0, VelocityMode::fixed);
  return press.accepted && reset.accepted;
}

EditorRangeGesture editor_range_gesture_for_test(
    Steinberg::Vst::EditController& controller, double low_normalized,
    double high_normalized) noexcept {
  EditorRangeGesture output{low_normalized, high_normalized, false};
  double canonical_low = 0.0;
  double canonical_high = 0.0;
  const ParameterSpec* low_spec = find_parameter(kLowestMidiNoteId);
  const ParameterSpec* high_spec = find_parameter(kHighestMidiNoteId);
  double low_plain = 0.0;
  double high_plain = 0.0;
  if (low_spec == nullptr || high_spec == nullptr ||
      !canonical_editor_value(kLowestMidiNoteId, low_normalized,
                              VelocityMode::fixed, canonical_low) ||
      !canonical_editor_value(kHighestMidiNoteId, high_normalized,
                              VelocityMode::fixed, canonical_high) ||
      !canonical_normalized_value(*low_spec, canonical_low, low_plain) ||
      !canonical_normalized_value(*high_spec, canonical_high, high_plain) ||
      low_plain > high_plain) {
    return output;
  }
  output.low_normalized = canonical_low;
  output.high_normalized = canonical_high;
  const EditorGesture low = perform_editor_gesture(
      controller, kLowestMidiNoteId, canonical_low, VelocityMode::fixed);
  const EditorGesture high = perform_editor_gesture(
      controller, kHighestMidiNoteId, canonical_high, VelocityMode::fixed);
  output.accepted = low.accepted && high.accepted;
  return output;
}

Steinberg::IPlugView* create_m3_editor(
    Steinberg::Vst::EditController& controller) noexcept {
  return new (std::nothrow) M3Editor(controller);
}

}  // namespace m3::vst3
