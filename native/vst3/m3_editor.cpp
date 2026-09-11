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
#include "vst3_component.hpp"
#include "vst3_parameter_bridge.hpp"
#include "vstgui/lib/ccolor.h"
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/cfont.h"
#include "vstgui/lib/cgraphicspath.h"
#include "vstgui/lib/cvstguitimer.h"
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
          "maxSize": "2048, 1616",
          "minSize": "1024, 808",
          "mouse-enabled": "true",
          "opacity": "1",
          "origin": "0, 0",
          "size": "1024, 808",
          "transparent": "false"
        }
      }
    }
  }
}
)";

const VSTGUI::CColor kGraphite{9U, 13U, 18U, 255U};
const VSTGUI::CColor kPanelTop{20U, 27U, 35U, 255U};
const VSTGUI::CColor kPanelBottom{15U, 21U, 28U, 255U};
const VSTGUI::CColor kPanelRaised{25U, 34U, 44U, 255U};
const VSTGUI::CColor kPanelEdge{47U, 61U, 74U, 255U};
const VSTGUI::CColor kPanelEdgeSoft{31U, 42U, 53U, 255U};
const VSTGUI::CColor kText{236U, 242U, 247U, 255U};
const VSTGUI::CColor kMuted{146U, 160U, 174U, 255U};
const VSTGUI::CColor kMutedLow{91U, 106U, 120U, 255U};
const VSTGUI::CColor kCyan{35U, 219U, 230U, 255U};
const VSTGUI::CColor kAmber{244U, 181U, 63U, 255U};
const VSTGUI::CColor kRed{240U, 76U, 86U, 255U};

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

bool editor_parameter_writable(ParameterId id,
                               VelocityMode velocity_mode) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  return spec != nullptr && !spec->read_only &&
         (id != kFixedVelocityId || velocity_mode == VelocityMode::fixed);
}

EditorGesture apply_editor_value(
    Steinberg::Vst::EditController& controller, ParameterId id,
    double normalized) noexcept {
  EditorGesture output{id, normalized, false, false};
  const bool set = result_ok(controller.setParamNormalized(id, normalized));
  output.value_applied = set;
  const bool performed =
      set && result_ok(controller.performEdit(id, normalized));
  output.accepted = set && performed;
  return output;
}

EditorGesture perform_open_editor_value(
    Steinberg::Vst::EditController& controller, ParameterId id,
    double requested, VelocityMode velocity_mode) noexcept {
  EditorGesture output{id, requested, false, false};
  double normalized = 0.0;
  if (!canonical_editor_value(id, requested, velocity_mode, normalized)) {
    return output;
  }
  return apply_editor_value(controller, id, normalized);
}

EditorGesture perform_editor_gesture(
    Steinberg::Vst::EditController& controller, ParameterId id,
    double requested, VelocityMode velocity_mode) noexcept {
  EditorGesture output{id, requested, false, false};
  double normalized = 0.0;
  if (!canonical_editor_value(id, requested, velocity_mode, normalized)) {
    return output;
  }
  output.normalized_value = normalized;
  if (!result_ok(controller.beginEdit(id))) {
    return output;
  }
  output = apply_editor_value(controller, id, normalized);
  const bool ended = result_ok(controller.endEdit(id));
  output.accepted = output.accepted && ended;
  return output;
}

double linked_range_request(Steinberg::Vst::EditController& controller,
                            ParameterId id, double requested) noexcept {
  if (id != kLowestMidiNoteId && id != kHighestMidiNoteId) {
    return requested;
  }
  const ParameterId other_id = id == kLowestMidiNoteId
                                   ? kHighestMidiNoteId
                                   : kLowestMidiNoteId;
  const ParameterSpec* spec = find_parameter(id);
  const ParameterSpec* other_spec = find_parameter(other_id);
  double requested_plain = 0.0;
  double other_plain = 0.0;
  const double other_normalized = controller.getParamNormalized(other_id);
  if (spec == nullptr || other_spec == nullptr ||
      !canonical_normalized_value(*spec, requested, requested_plain) ||
      !canonical_normalized_value(*other_spec, other_normalized,
                                  other_plain)) {
    return requested;
  }
  if (id == kLowestMidiNoteId && requested_plain > other_plain) {
    return plain_to_normalized(*spec, other_plain);
  }
  if (id == kHighestMidiNoteId && requested_plain < other_plain) {
    return plain_to_normalized(*spec, other_plain);
  }
  return requested;
}

double canonical_ui_request(ParameterId id, double requested) noexcept {
  const ParameterSpec* spec = find_parameter(id);
  if (spec == nullptr) {
    return requested;
  }
  const double plain = normalized_to_plain(*spec, requested);
  return std::isfinite(plain) ? plain_to_normalized(*spec, plain) : requested;
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

void draw_rounded_surface(VSTGUI::CDrawContext* context,
                          const VSTGUI::CRect& rect,
                          const VSTGUI::CColor& fill,
                          const VSTGUI::CColor& edge,
                          VSTGUI::CCoord radius = 10.0,
                          VSTGUI::CCoord line_width = 1.0) {
  if (context == nullptr) {
    return;
  }
  auto path = VSTGUI::owned(context->createGraphicsPath());
  if (!path) {
    return;
  }
  path->addRoundRect(rect, radius);
  context->setFillColor(fill);
  context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathFilled);
  context->setFrameColor(edge);
  context->setLineWidth(line_width);
  context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathStroked);
}

void draw_rule(VSTGUI::CDrawContext* context, const VSTGUI::CPoint& start,
               const VSTGUI::CPoint& end, const VSTGUI::CColor& color,
               VSTGUI::CCoord width = 1.0) {
  if (context == nullptr) {
    return;
  }
  context->setFrameColor(color);
  context->setLineWidth(width);
  context->drawLine(start, end);
}

void draw_glow_layer(VSTGUI::CDrawContext* context,
                     const VSTGUI::CRect& rect,
                     const VSTGUI::CColor& color,
                     VSTGUI::CCoord radius,
                     VSTGUI::CCoord spread,
                     VSTGUI::CCoord line_width,
                     std::uint8_t alpha) {
  if (context == nullptr) {
    return;
  }
  VSTGUI::CRect halo = rect;
  halo.extend(spread, spread);
  auto path = VSTGUI::owned(context->createGraphicsPath());
  if (!path) {
    return;
  }
  path->addRoundRect(halo, radius + spread);
  context->setFrameColor(
      VSTGUI::CColor(color.red, color.green, color.blue, alpha));
  context->setLineWidth(line_width);
  context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathStroked);
}

// Static, low-alpha layers add depth without suggesting live signal telemetry
// or introducing timer-driven motion into the editor.
void draw_static_glow_outline(VSTGUI::CDrawContext* context,
                              const VSTGUI::CRect& rect,
                              const VSTGUI::CColor& color,
                              VSTGUI::CCoord radius) {
  draw_glow_layer(context, rect, color, radius, 6.0, 2.0, 18U);
  draw_glow_layer(context, rect, color, radius, 2.0, 1.0, 54U);
}

// CControl drawing is clipped to its view bounds. Keep this variant fully
// inside that clipping region so a state glow remains visible on child views.
void draw_inset_glow_outline(VSTGUI::CDrawContext* context,
                             const VSTGUI::CRect& rect,
                             const VSTGUI::CColor& color,
                             VSTGUI::CCoord radius) {
  VSTGUI::CRect outer = rect;
  outer.inset(3.0, 3.0);
  draw_glow_layer(context, outer, color,
                  std::max<VSTGUI::CCoord>(0.0, radius - 3.0), 0.0, 4.0,
                  18U);
  VSTGUI::CRect inner = outer;
  inner.inset(2.0, 2.0);
  draw_glow_layer(context, inner, color,
                  std::max<VSTGUI::CCoord>(0.0, radius - 5.0), 0.0, 2.0,
                  54U);
}

VSTGUI::CRect to_rect(const EditorRect& rect) noexcept {
  return VSTGUI::CRect(rect.left, rect.top, rect.right, rect.bottom);
}

const char* const* segment_labels(ParameterId id,
                                  std::size_t& count) noexcept {
  static const char* const kInputLabels[] = {"LEFT", "RIGHT", "L + R"};
  static const char* const kModeLabels[] = {"M3", "GENERAL"};
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

const char* segment_title(ParameterId id) noexcept {
  if (id == kDetectorInputId) {
    return "DETECTOR INPUT";
  }
  if (id == kProfileModeId) {
    return "INSTRUMENT PROFILE";
  }
  if (id == kVelocityModeId) {
    return "VELOCITY MODE";
  }
  return "MODE";
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

  ~M3DeckControl() noexcept override { cancel_interaction(); }

  void set_dependent_control(M3DeckControl* dependent) noexcept {
    dependent_control_ = dependent;
  }

  void setValue(float new_value) override {
    const float previous = getValue();
    VSTGUI::CControl::setValue(new_value);
    if (dependent_control_ != nullptr && getValue() != previous) {
      dependent_control_->invalid();
    }
  }

#if defined(M3_TESTING)
  void invalid() override {
    ++invalidation_count_;
    VSTGUI::CControl::invalid();
  }

  std::size_t invalidation_count_for_test() const noexcept {
    return invalidation_count_;
  }
#endif

  void dispatchEvent(VSTGUI::Event& event) override {
    if (event.type == VSTGUI::EventType::MouseDown) {
      auto& mouse_event = static_cast<VSTGUI::MouseDownEvent&>(event);
      if (!layout_.enabled || !interaction_allowed()) {
        event.consumed = true;
        mouse_event.ignoreFollowUpMoveAndUpEvents(true);
        return;
      }
      if (mouse_event.buttonState.isLeft() &&
          mouse_event.modifiers.is(VSTGUI::ModifierKey::Control) &&
          layout_.presentation != EditorPresentation::momentary) {
        const ParameterSpec* spec = find_parameter(layout_.parameter_id);
        if (spec != nullptr) {
          static_cast<void>(emit(
              plain_to_normalized(*spec, spec->default_value)));
        }
        event.consumed = true;
        mouse_event.ignoreFollowUpMoveAndUpEvents(true);
        return;
      }
    }
    VSTGUI::CControl::dispatchEvent(event);
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
      const EditorGesture press = emit(1.0);
      panic_pressed_ = press.value_applied;
      return panic_pressed_ ? VSTGUI::kMouseEventHandled
                            : VSTGUI::kMouseEventNotHandled;
    }
    if (layout_.presentation == EditorPresentation::knob ||
        layout_.presentation == EditorPresentation::note_range) {
      finish_drag();
      const VelocityMode velocity_mode = current_velocity_mode();
      if (!editor_parameter_writable(layout_.parameter_id, velocity_mode) ||
          !result_ok(controller_.beginEdit(layout_.parameter_id))) {
        return VSTGUI::kMouseEventNotHandled;
      }
      dragging_ = true;
      drag_edit_open_ = true;
      drag_origin_y_ = where.y;
      drag_start_normalized_ = getValueNormalized();
      return VSTGUI::kMouseEventHandled;
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
    return emit(requested).accepted ? VSTGUI::kMouseEventHandled
                                    : VSTGUI::kMouseEventNotHandled;
  }

  VSTGUI::CMouseEventResult onMouseUp(
      VSTGUI::CPoint&,
      const VSTGUI::CButtonState&) override {
    if (panic_pressed_) {
      reset_panic();
      return VSTGUI::kMouseEventHandled;
    }
    if (finish_drag()) {
      return VSTGUI::kMouseEventHandled;
    }
    return VSTGUI::kMouseEventNotHandled;
  }

  VSTGUI::CMouseEventResult onMouseMoved(
      VSTGUI::CPoint& where,
      const VSTGUI::CButtonState& buttons) override {
    if (!dragging_ || !buttons.isLeftButton() || !interaction_allowed()) {
      return VSTGUI::kMouseEventNotHandled;
    }
    const double requested = std::clamp(
        drag_start_normalized_ + meaningful_delta(
                                     (drag_origin_y_ - where.y) / 200.0),
        0.0, 1.0);
    static_cast<void>(emit_open(requested));
    return VSTGUI::kMouseEventHandled;
  }

  VSTGUI::CMouseEventResult onMouseCancel() override {
    static_cast<void>(finish_drag());
    reset_panic();
    return VSTGUI::kMouseEventHandled;
  }

  void onMouseWheelEvent(VSTGUI::MouseWheelEvent& event) override {
    if (!layout_.enabled || !interaction_allowed() ||
        (layout_.presentation != EditorPresentation::knob &&
         layout_.presentation != EditorPresentation::note_range)) {
      return;
    }
    const double requested = std::clamp(
        static_cast<double>(getValueNormalized()) + meaningful_delta(
            static_cast<double>(event.deltaY) * getWheelInc()), 0.0, 1.0);
    static_cast<void>(emit(requested));
    event.consumed = true;
  }

  bool removed(VSTGUI::CView* parent) override {
    cancel_interaction();
    return VSTGUI::CControl::removed(parent);
  }

  void cancel_interaction() noexcept {
    static_cast<void>(finish_drag());
    reset_panic();
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
  double meaningful_delta(double delta) const noexcept {
    const ParameterSpec* spec = find_parameter(layout_.parameter_id);
    if (spec == nullptr || spec->step_count <= 0 || !std::isfinite(delta) ||
        delta == 0.0) {
      return delta;
    }
    const double step = 1.0 / static_cast<double>(spec->step_count);
    return std::abs(delta) < step ? std::copysign(step, delta) : delta;
  }

  bool interaction_allowed() const noexcept {
    return layout_.parameter_id != kFixedVelocityId ||
           controller_.getParamNormalized(kVelocityModeId) < 0.5;
  }

  VelocityMode current_velocity_mode() const noexcept {
    return controller_.getParamNormalized(kVelocityModeId) >= 0.5
               ? VelocityMode::dynamic
               : VelocityMode::fixed;
  }

  EditorGesture update_after_gesture(const EditorGesture& gesture) {
    if (gesture.value_applied) {
      setValueNormalized(static_cast<float>(gesture.normalized_value));
      invalid();
      if (VSTGUI::CView* parent = getParentView()) {
        parent->invalid();
      }
    }
    return gesture;
  }

  double prepared_ui_request(double requested) const noexcept {
    const double canonical =
        canonical_ui_request(layout_.parameter_id, requested);
    return linked_range_request(controller_, layout_.parameter_id, canonical);
  }

  EditorGesture emit(double requested) {
    const double linked = prepared_ui_request(requested);
    const EditorGesture gesture = perform_editor_gesture(
        controller_, layout_.parameter_id, linked, current_velocity_mode());
    return update_after_gesture(gesture);
  }

  EditorGesture emit_open(double requested) {
    const double linked = prepared_ui_request(requested);
    const EditorGesture gesture = perform_open_editor_value(
        controller_, layout_.parameter_id, linked, current_velocity_mode());
    return update_after_gesture(gesture);
  }

  bool finish_drag() noexcept {
    const bool was_dragging = dragging_;
    dragging_ = false;
    if (!drag_edit_open_) {
      return was_dragging;
    }
    drag_edit_open_ = false;
    static_cast<void>(controller_.endEdit(layout_.parameter_id));
    return true;
  }

  void reset_panic() noexcept {
    if (!panic_pressed_) {
      return;
    }
    panic_pressed_ = false;
    static_cast<void>(perform_editor_gesture(
        controller_, kPanicParameterId, 0.0, VelocityMode::fixed));
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
      draw_rounded_surface(context, bounds, kPanelBottom, kPanelEdgeSoft, 7.0);
      draw_label(context, "FIXED VELOCITY",
                 VSTGUI::CRect(bounds.left, bounds.top + 18.0, bounds.right,
                                bounds.top + 38.0),
                 kMuted);
      context->setFont(VSTGUI::kNormalFontBig);
      context->setFontColor(kMutedLow);
      context->drawString("LOCKED",
                          VSTGUI::CRect(bounds.left, bounds.top + 40.0,
                                       bounds.right, bounds.top + 72.0),
                          VSTGUI::kCenterText, true);
      draw_label(context, "SELECT FIXED MODE",
                 VSTGUI::CRect(bounds.left, bounds.top + 78.0, bounds.right,
                                bounds.top + 100.0),
                 kAmber);
      return;
    }
    const VSTGUI::CCoord diameter =
        std::min(bounds.getWidth(), bounds.getHeight() - 28.0);
    const VSTGUI::CPoint center(bounds.getCenter().x, bounds.top + diameter / 2.0);
    VSTGUI::CRect dial(center.x - diameter / 2.0, center.y - diameter / 2.0,
                       center.x + diameter / 2.0, center.y + diameter / 2.0);
    dial.inset(8.0, 8.0);
    context->setFillColor(kPanelBottom);
    context->setFrameColor(kPanelEdgeSoft);
    context->setLineWidth(1.0);
    context->drawEllipse(dial, VSTGUI::kDrawFilledAndStroked);
    context->setFrameColor(kPanelEdge);
    context->setLineWidth(3.0);
    context->drawArc(dial, 135.0, 405.0, VSTGUI::kDrawStroked);
    context->setFrameColor(kCyan);
    context->setLineWidth(3.0);
    context->drawArc(dial, 135.0,
                     static_cast<float>(135.0 + normalized * 270.0),
                     VSTGUI::kDrawStroked);
    const double tick_outer = dial.getWidth() * 0.55;
    const double tick_inner = dial.getWidth() * 0.48;
    for (unsigned tick = 0U; tick <= 10U; ++tick) {
      const double tick_angle =
          (135.0 + static_cast<double>(tick) * 27.0) *
          VSTGUI::Constants::pi / 180.0;
      draw_rule(context,
                VSTGUI::CPoint(center.x + std::cos(tick_angle) * tick_inner,
                               center.y + std::sin(tick_angle) * tick_inner),
                VSTGUI::CPoint(center.x + std::cos(tick_angle) * tick_outer,
                               center.y + std::sin(tick_angle) * tick_outer),
                tick <= static_cast<unsigned>(std::lround(normalized * 10.0))
                    ? kCyan
                    : kMutedLow,
                1.0);
    }
    VSTGUI::CRect hub = dial;
    hub.inset(dial.getWidth() * 0.18, dial.getHeight() * 0.18);
    context->setFillColor(kPanelRaised);
    context->setFrameColor(kPanelEdgeSoft);
    context->setLineWidth(1.0);
    context->drawEllipse(hub, VSTGUI::kDrawFilledAndStroked);
    const double angle = (135.0 + normalized * 270.0) *
                         VSTGUI::Constants::pi / 180.0;
    const double radius = dial.getWidth() * 0.25;
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
               kMuted);
  }

  void draw_segment(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_surface(context, bounds, kPanelBottom, kPanelEdgeSoft, 7.0);
    draw_label(context, segment_title(layout_.parameter_id),
               VSTGUI::CRect(bounds.left + 8.0, bounds.top + 3.0,
                              bounds.right - 8.0, bounds.top + 19.0),
               kMutedLow, VSTGUI::kLeftText);
    std::size_t count = 0U;
    const char* const* labels = segment_labels(layout_.parameter_id, count);
    if (labels == nullptr || count < 2U) {
      return;
    }
    const std::size_t selected = static_cast<std::size_t>(
        std::llround(normalized * static_cast<double>(count - 1U)));
    VSTGUI::CRect selector = bounds;
    selector.inset(5.0, 5.0);
    selector.top = bounds.top + 22.0;
    const double width = selector.getWidth() / static_cast<double>(count);
    for (std::size_t index = 0; index < count; ++index) {
      VSTGUI::CRect segment(
          selector.left + width * static_cast<double>(index), selector.top,
          selector.left + width * static_cast<double>(index + 1U),
          selector.bottom);
      if (index == selected) {
        VSTGUI::CRect active = segment;
        active.inset(2.0, 1.0);
        draw_rounded_surface(context, active,
                             VSTGUI::CColor(18U, 69U, 78U, 255U), kCyan,
                             4.0, 1.0);
        draw_rule(context,
                  VSTGUI::CPoint(active.left + 7.0, active.bottom - 3.0),
                  VSTGUI::CPoint(active.right - 7.0, active.bottom - 3.0),
                  kCyan, 2.0);
      } else if (index > 0U) {
        draw_rule(context, VSTGUI::CPoint(segment.left, segment.top + 6.0),
                  VSTGUI::CPoint(segment.left, segment.bottom - 6.0),
                  kPanelEdgeSoft);
      }
      draw_label(context, labels[index], segment,
                 index == selected ? kText : kMuted);
    }
  }

  void draw_toggle(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    const bool enabled = normalized >= 0.5;
    draw_rounded_surface(context, bounds, kPanelBottom, kPanelEdgeSoft,
                         bounds.getHeight() / 2.0);
    draw_label(context, "DRY AUDIO",
               VSTGUI::CRect(bounds.left + 16.0, bounds.top + 8.0,
                              bounds.right - 76.0, bounds.top + 28.0),
               kText, VSTGUI::kLeftText);
    draw_label(context, enabled ? "MONITOR ON" : "MONITOR OFF",
               VSTGUI::CRect(bounds.left + 16.0, bounds.top + 28.0,
                              bounds.right - 76.0, bounds.bottom - 6.0),
               enabled ? kCyan : kMuted, VSTGUI::kLeftText);
    VSTGUI::CRect track(bounds.right - 64.0, bounds.top + 16.0,
                        bounds.right - 12.0, bounds.bottom - 16.0);
    draw_rounded_surface(context, track,
                         enabled ? VSTGUI::CColor(14U, 67U, 75U, 255U)
                                 : VSTGUI::CColor(28U, 37U, 46U, 255U),
                         enabled ? kCyan : kPanelEdge, track.getHeight() / 2.0);
    VSTGUI::CRect lamp = track;
    lamp.inset(3.0, 3.0);
    lamp.setWidth(lamp.getHeight());
    if (enabled) {
      lamp.offset(track.getWidth() - lamp.getWidth() - 6.0, 0.0);
    }
    context->setFillColor(enabled ? kCyan : kMuted);
    context->drawEllipse(lamp, VSTGUI::kDrawFilled);
  }

  void draw_note_range(VSTGUI::CDrawContext* context,
                       double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_surface(context, bounds, kPanelBottom, kPanelEdgeSoft, 7.0);
    context->setFillColor(kCyan);
    context->drawRect(VSTGUI::CRect(bounds.left, bounds.top + 12.0,
                                    bounds.left + 3.0, bounds.bottom - 12.0),
                      VSTGUI::kDrawFilled);
    char value_text[128]{};
    parameter_text(normalized, value_text);
    draw_label(context,
               layout_.parameter_id == kLowestMidiNoteId ? "LOW LIMIT"
                                                         : "HIGH LIMIT",
               VSTGUI::CRect(bounds.left + 16.0, bounds.top + 7.0,
                              bounds.right - 12.0, bounds.top + 25.0),
               kMuted, VSTGUI::kLeftText);
    context->setFont(VSTGUI::kNormalFontVeryBig);
    context->setFontColor(kText);
    context->drawString(value_text,
                        VSTGUI::CRect(bounds.left + 16.0, bounds.top + 23.0,
                                     bounds.right - 12.0, bounds.bottom - 19.0),
                        VSTGUI::kLeftText, true);
    draw_label(context, "MIDI NOTE  ·  LINKED",
               VSTGUI::CRect(bounds.left + 16.0, bounds.bottom - 21.0,
                              bounds.right - 12.0, bounds.bottom - 5.0),
               kCyan, VSTGUI::kLeftText);
  }

  void draw_momentary(VSTGUI::CDrawContext* context) const {
    const VSTGUI::CRect bounds = getViewSize();
    draw_rounded_surface(context, bounds,
                         panic_pressed_
                             ? VSTGUI::CColor(108U, 25U, 34U, 255U)
                             : VSTGUI::CColor(44U, 20U, 26U, 255U),
                         kRed, 7.0, panic_pressed_ ? 2.0 : 1.0);
    context->setFillColor(kRed);
    context->drawRect(VSTGUI::CRect(bounds.left, bounds.top + 9.0,
                                    bounds.left + 3.0, bounds.bottom - 9.0),
                      VSTGUI::kDrawFilled);
    draw_label(context, panic_pressed_ ? "PANIC HELD" : "PANIC",
               VSTGUI::CRect(bounds.left + 16.0, bounds.top + 5.0,
                              bounds.right - 10.0, bounds.top + 26.0),
               kText, VSTGUI::kLeftText);
    draw_label(context, "ALL NOTES OFF",
               VSTGUI::CRect(bounds.left + 16.0, bounds.top + 25.0,
                              bounds.right - 10.0, bounds.bottom - 4.0),
               panic_pressed_ ? kText : kRed, VSTGUI::kLeftText);
  }

  void draw_status(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    const int status_index = std::clamp(
        static_cast<int>(std::llround(normalized * 5.0)), 0, 5);
    const Status status = static_cast<Status>(status_index);
    draw_rounded_surface(context, bounds, kPanelBottom, kPanelEdgeSoft, 7.0);
    if (status == Status::ready) {
      draw_inset_glow_outline(context, bounds, kCyan, 8.0);
    }
    context->setFont(VSTGUI::kNormalFontVeryBig);
    context->setFontColor(kCyan);
    context->drawString("M3",
                        VSTGUI::CRect(bounds.left + 14.0, bounds.top + 4.0,
                                     bounds.left + 66.0, bounds.bottom - 4.0),
                        VSTGUI::kLeftText, true);
    draw_rule(context, VSTGUI::CPoint(bounds.left + 72.0, bounds.top + 10.0),
              VSTGUI::CPoint(bounds.left + 72.0, bounds.bottom - 10.0),
              kPanelEdge);
    draw_label(context, "POLYPHONIC AUDIO → MIDI",
               VSTGUI::CRect(bounds.left + 86.0, bounds.top + 6.0,
                              bounds.right - 210.0, bounds.top + 27.0),
               kText, VSTGUI::kLeftText);
    draw_label(context, "CAUSAL NATIVE ENGINE  ·  ZERO LOOKAHEAD",
               VSTGUI::CRect(bounds.left + 86.0, bounds.top + 26.0,
                              bounds.right - 210.0, bounds.bottom - 5.0),
               kMuted, VSTGUI::kLeftText);
    const VSTGUI::CRect status_pill(bounds.right - 181.0, bounds.top + 10.0,
                                    bounds.right - 12.0, bounds.bottom - 10.0);
    draw_rounded_surface(context, status_pill,
                         VSTGUI::CColor(13U, 25U, 30U, 255U),
                         status_deck_color(status), status_pill.getHeight() / 2.0);
    context->setFillColor(status_deck_color(status));
    context->drawEllipse(VSTGUI::CRect(status_pill.left + 10.0,
                                       status_pill.top + 9.0,
                                       status_pill.left + 18.0,
                                       status_pill.top + 17.0),
                         VSTGUI::kDrawFilled);
    draw_label(context, status_label(status),
               VSTGUI::CRect(status_pill.left + 24.0, status_pill.top,
                              status_pill.right - 10.0, status_pill.bottom),
               status_deck_color(status), VSTGUI::kLeftText);
  }

  EditorControlLayout layout_;
  Steinberg::Vst::EditController& controller_;
  M3DeckControl* dependent_control_{};
  bool panic_pressed_{};
  bool dragging_{};
  bool drag_edit_open_{};
  double drag_origin_y_{};
  double drag_start_normalized_{};
#if defined(M3_TESTING)
  std::size_t invalidation_count_{};
#endif

  CLASS_METHODS_NOCOPY(M3DeckControl, VSTGUI::CControl)
};

class M3RootSurface final : public VSTGUI::CViewContainer {
 public:
  M3RootSurface(VSTGUI::IControlListener* listener,
                Steinberg::Vst::EditController& controller,
                const TunerTelemetry& tuner_telemetry)
      : VSTGUI::CViewContainer(
            VSTGUI::CRect(0.0, 0.0, kEditorWidth, kEditorHeight)),
        tuner_telemetry_(tuner_telemetry) {
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
    M3DeckControl* velocity_mode = control_for(kVelocityModeId);
    if (velocity_mode != nullptr) {
      velocity_mode->set_dependent_control(control_for(kFixedVelocityId));
    }
  }

  bool refresh_tuner() noexcept {
    TunerSnapshot snapshot;
    if (!tuner_telemetry_.read_latest(snapshot)) {
      return false;
    }
    if (has_tuner_snapshot_ &&
        snapshot.generation == tuner_snapshot_.generation) {
      return false;
    }
    tuner_snapshot_ = snapshot;
    has_tuner_snapshot_ = true;
#if defined(M3_TESTING)
    ++tuner_invalidation_count_;
#endif
    invalid();
    return true;
  }

  bool tuner_snapshot_for_test(TunerSnapshot& snapshot) const noexcept {
    if (!has_tuner_snapshot_) {
      return false;
    }
    snapshot = tuner_snapshot_;
    return true;
  }

#if defined(M3_TESTING)
  std::size_t tuner_invalidation_count_for_test() const noexcept {
    return tuner_invalidation_count_;
  }
#endif

  VSTGUI::CControl* control_at(std::size_t index) const noexcept {
    return index < controls_.size() ? controls_[index] : nullptr;
  }

  M3DeckControl* control_for(ParameterId parameter_id) const noexcept {
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      if (layouts_[index].parameter_id == parameter_id) {
        return controls_[index];
      }
    }
    return nullptr;
  }

  bool remove_control(ParameterId parameter_id) noexcept {
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      if (layouts_[index].parameter_id == parameter_id &&
          controls_[index] != nullptr) {
        M3DeckControl* control = controls_[index];
        if (parameter_id == kFixedVelocityId) {
          M3DeckControl* velocity_mode = control_for(kVelocityModeId);
          if (velocity_mode != nullptr) {
            velocity_mode->set_dependent_control(nullptr);
          }
        }
        control->cancel_interaction();
        controls_[index] = nullptr;
        return removeView(control, true);
      }
    }
    return false;
  }

  void setViewSize(const VSTGUI::CRect& rect, bool invalid = true) override {
    VSTGUI::CViewContainer::setViewSize(rect, invalid);
    relayout_controls();
  }

  void drawBackgroundRect(VSTGUI::CDrawContext* context,
                          const VSTGUI::CRect&) override {
    if (context == nullptr) {
      return;
    }
    const VSTGUI::CRect bounds = getViewSize();
    context->setFillColor(kGraphite);
    context->drawRect(bounds, VSTGUI::kDrawFilled);
    draw_rule(context, scaled_rect(24.0, 78.0, 1000.0, 78.0).getTopLeft(),
              scaled_rect(24.0, 78.0, 1000.0, 78.0).getTopRight(),
              kPanelEdgeSoft);
    draw_rounded_surface(context, scaled_rect(14.0, 84.0, 1010.0, 262.0),
                         kPanelBottom, kPanelEdgeSoft, 10.0);
    const VSTGUI::CRect tuner_panel =
        scaled_rect(14.0, 270.0, 1010.0, 446.0);
    draw_rounded_surface(context, tuner_panel,
                         VSTGUI::CColor(10U, 19U, 24U, 255U),
                         VSTGUI::CColor(22U, 111U, 120U, 255U), 10.0);
    // This static frame establishes deck hierarchy only. Actual voice state is
    // rendered from the snapshot inside it, with a textual state in every row.
    draw_static_glow_outline(context, tuner_panel,
                             VSTGUI::CColor(26U, 120U, 130U, 255U), 12.0);
    draw_rounded_surface(context, scaled_rect(14.0, 458.0, 1010.0, 608.0),
                         kPanelBottom, kPanelEdgeSoft, 10.0);
    draw_rounded_surface(context, scaled_rect(14.0, 620.0, 1010.0, 792.0),
                         kPanelBottom, kPanelEdgeSoft, 10.0);
    draw_tuner(context);
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(kMuted);
    context->drawString("01  /  INPUT & DETECTOR",
                        scaled_rect(24.0, 92.0, 500.0, 114.0),
                        VSTGUI::kLeftText, true);
    context->setFontColor(kMutedLow);
    context->drawString("SIGNAL PATH",
                        scaled_rect(760.0, 92.0, 1000.0, 114.0),
                        VSTGUI::kRightText, true);
    context->setFontColor(kCyan);
    context->drawString("03  /  RANGE & VOICING",
                        scaled_rect(24.0, 466.0, 440.0, 486.0),
                        VSTGUI::kLeftText, true);
    context->setFontColor(kMuted);
    context->drawString("04  /  OUTPUT & ROUTING",
                        scaled_rect(24.0, 626.0, 700.0, 648.0),
                        VSTGUI::kLeftText, true);
    context->setFontColor(kMutedLow);
    context->drawString("M3 NATIVE  ·  8 VOICE CORE",
                        scaled_rect(700.0, 626.0, 1000.0, 648.0),
                        VSTGUI::kRightText, true);
  }

 private:
  static void draw_label(
      VSTGUI::CDrawContext* context, const char* label,
      const VSTGUI::CRect& rect, const VSTGUI::CColor& color = kMuted,
      VSTGUI::CHoriTxtAlign align = VSTGUI::kCenterText) {
    if (context == nullptr) {
      return;
    }
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(color);
    context->drawString(label, rect, align, true);
  }

  static char* append_literal(char* cursor, char* end,
                              const char* source) noexcept {
    while (source != nullptr && *source != '\0' && cursor + 1 < end) {
      *cursor++ = *source++;
    }
    return cursor;
  }

  static char* append_unsigned(char* cursor, char* end, unsigned value,
                               unsigned minimum_digits = 0U) noexcept {
    std::array<char, 10> reversed{};
    std::size_t count = 0U;
    do {
      reversed[count++] = static_cast<char>('0' + value % 10U);
      value /= 10U;
    } while (value != 0U && count < reversed.size());
    while (count < minimum_digits && count < reversed.size()) {
      reversed[count++] = '0';
    }
    while (count > 0U && cursor + 1 < end) {
      *cursor++ = reversed[--count];
    }
    return cursor;
  }

  static char* append_signed(char* cursor, char* end, int value,
                             unsigned minimum_digits) noexcept {
    if (cursor + 1 < end) {
      *cursor++ = value < 0 ? '-' : '+';
    }
    const unsigned magnitude = static_cast<unsigned>(value < 0 ? -value : value);
    return append_unsigned(cursor, end, magnitude, minimum_digits);
  }

  static void terminate_text(char* cursor, char* end) noexcept {
    if (cursor < end) {
      *cursor = '\0';
    }
  }

  static void format_note(const TunerVoice& voice,
                          char (&text)[8]) noexcept {
    static constexpr std::array<const char*, 12> kNames{
        "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    const std::uint8_t note = std::min<std::uint8_t>(voice.midi_note, 127U);
    const int octave = static_cast<int>(note / 12U) - 1;
    char* const end = text + sizeof(text);
    char* cursor = append_literal(text, end, kNames[note % 12U]);
    if (octave < 0 && cursor + 1 < end) {
      *cursor++ = '-';
    }
    cursor = append_unsigned(cursor, end,
                             static_cast<unsigned>(octave < 0 ? -octave : octave));
    terminate_text(cursor, end);
  }

  static void format_cents(const TunerVoice& voice,
                           char (&text)[12]) noexcept {
    if (!voice.cents_valid || voice.state != TunerVoiceState::tracking) {
      char* const end = text + sizeof(text);
      terminate_text(append_literal(text, end, "--"), end);
      return;
    }
    const int cents = std::clamp(
        static_cast<int>(std::lround(static_cast<double>(voice.cents_q8) / 256.0)),
        -50, 50);
    char* const end = text + sizeof(text);
    char* cursor = append_signed(text, end, cents, 2U);
    cursor = append_literal(cursor, end, "¢");
    terminate_text(cursor, end);
  }

  static void format_confidence(const TunerVoice& voice,
                                char (&text)[16]) noexcept {
    const unsigned percent = std::min(
        100U, static_cast<unsigned>(std::lround(
                  static_cast<double>(voice.confidence_q15) * 100.0 / 32767.0)));
    char* const end = text + sizeof(text);
    char* cursor = append_unsigned(text, end, percent);
    cursor = append_literal(cursor, end, "%");
    terminate_text(cursor, end);
  }

  static void format_voice_header(std::uint8_t voice_count,
                                  std::uint8_t max_polyphony,
                                  char (&text)[32]) noexcept {
    char* const end = text + sizeof(text);
    char* cursor = append_unsigned(text, end, voice_count);
    cursor = append_literal(cursor, end, " ACTIVE  ·  LIMIT ");
    cursor = append_unsigned(cursor, end, max_polyphony);
    terminate_text(cursor, end);
  }

  void draw_tuner_card(VSTGUI::CDrawContext* context,
                       const VSTGUI::CRect& card,
                       std::size_t slot,
                       const TunerVoice* voice) const {
    if (context == nullptr) {
      return;
    }
    char slot_text[8]{};
    char* const slot_end = slot_text + sizeof(slot_text);
    char* slot_cursor = append_literal(slot_text, slot_end, "V");
    slot_cursor = append_unsigned(slot_cursor, slot_end,
                                  static_cast<unsigned>(slot + 1U), 2U);
    terminate_text(slot_cursor, slot_end);
    if (voice == nullptr) {
      draw_rounded_surface(context, card,
                           VSTGUI::CColor(12U, 17U, 23U, 255U),
                           kPanelEdgeSoft, 5.0);
      draw_label(context, slot_text,
                 VSTGUI::CRect(card.left + 8.0, card.top + 5.0,
                                card.right - 8.0, card.top + 20.0),
                 kMutedLow, VSTGUI::kLeftText);
      const double center = card.getCenter().x;
      draw_rule(context, VSTGUI::CPoint(card.left + 14.0, card.bottom - 30.0),
                VSTGUI::CPoint(card.right - 14.0, card.bottom - 30.0),
                kPanelEdgeSoft);
      draw_rule(context, VSTGUI::CPoint(center, card.bottom - 34.0),
                VSTGUI::CPoint(center, card.bottom - 26.0), kMutedLow);
      return;
    }
    const bool tracking = voice->state == TunerVoiceState::tracking;
    const VSTGUI::CColor state_color = tracking ? kCyan : kAmber;
    draw_rounded_surface(context, card,
                         tracking ? VSTGUI::CColor(15U, 28U, 34U, 255U)
                                  : VSTGUI::CColor(28U, 25U, 18U, 255U),
                         state_color, 5.0, 1.0);
    char note[8]{};
    char cents[12]{};
    char confidence[16]{};
    format_note(*voice, note);
    format_cents(*voice, cents);
    format_confidence(*voice, confidence);
    draw_label(context, slot_text,
               VSTGUI::CRect(card.left + 8.0, card.top + 5.0,
                              card.right - 8.0, card.top + 20.0),
               state_color, VSTGUI::kLeftText);
    draw_label(context, confidence,
               VSTGUI::CRect(card.left + 8.0, card.top + 5.0,
                              card.right - 8.0, card.top + 20.0),
               kMuted, VSTGUI::kRightText);
    context->setFont(VSTGUI::kNormalFontVeryBig);
    context->setFontColor(kText);
    context->drawString(note,
                        VSTGUI::CRect(card.left + 8.0, card.top + 21.0,
                                     card.right - 8.0, card.top + 50.0),
                        VSTGUI::kCenterText, true);
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(state_color);
    context->drawString(tracking ? "TRACKING" : "ACQUIRING",
                        VSTGUI::CRect(card.left + 8.0, card.top + 48.0,
                                     card.right - 8.0, card.top + 65.0),
                        VSTGUI::kCenterText, true);
    draw_label(context, "CENTS",
               VSTGUI::CRect(card.left + 8.0, card.top + 65.0,
                              card.getCenter().x - 2.0, card.top + 80.0),
               kMutedLow, VSTGUI::kLeftText);
    context->setFontColor(kText);
    context->drawString(cents,
                        VSTGUI::CRect(card.getCenter().x - 1.0,
                                     card.top + 64.0, card.right - 8.0,
                                     card.top + 81.0),
                        VSTGUI::kRightText, true);
    const double rail_y = card.bottom - 26.0;
    draw_rule(context, VSTGUI::CPoint(card.left + 12.0, rail_y),
              VSTGUI::CPoint(card.right - 12.0, rail_y), kPanelEdge, 2.0);
    draw_rule(context, VSTGUI::CPoint(card.getCenter().x, rail_y - 4.0),
              VSTGUI::CPoint(card.getCenter().x, rail_y + 4.0), kMuted);
    if (tracking && voice->cents_valid) {
      const double cents_value = std::clamp(
          static_cast<double>(voice->cents_q8) / 256.0, -50.0, 50.0);
      const double indicator_x =
          card.left + 12.0 + (cents_value + 50.0) / 100.0 *
                                   (card.getWidth() - 24.0);
      context->setFillColor(state_color);
      context->drawEllipse(VSTGUI::CRect(indicator_x - 3.0, rail_y - 3.0,
                                         indicator_x + 3.0, rail_y + 3.0),
                           VSTGUI::kDrawFilled);
    }
    const unsigned lit = std::min(
        5U, static_cast<unsigned>(std::lround(
                static_cast<double>(voice->confidence_q15) * 5.0 / 32767.0)));
    const double segment_width = (card.getWidth() - 28.0) / 5.0;
    for (unsigned index = 0U; index < 5U; ++index) {
      VSTGUI::CRect segment(card.left + 12.0 + index * segment_width,
                            card.bottom - 12.0,
                            card.left + 12.0 + (index + 1U) * segment_width - 2.0,
                            card.bottom - 8.0);
      context->setFillColor(index < lit ? state_color : kPanelEdgeSoft);
      context->drawRect(segment, VSTGUI::kDrawFilled);
    }
  }

  void draw_tuner(VSTGUI::CDrawContext* context) const {
    if (context == nullptr) {
      return;
    }
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(kCyan);
    context->drawString("02  /  POLYPHONIC PITCH ARRAY",
                        scaled_rect(24.0, 278.0, 620.0, 300.0),
                        VSTGUI::kLeftText, true);
    const bool tracking = has_tuner_snapshot_ &&
                          tuner_snapshot_.state == TunerFrameState::tracking &&
                          tuner_snapshot_.voice_count > 0U;
    if (tracking) {
      char header[32]{};
      format_voice_header(tuner_snapshot_.voice_count,
                          tuner_snapshot_.max_polyphony, header);
      context->setFontColor(kText);
      context->drawString(header, scaled_rect(680.0, 278.0, 1000.0, 300.0),
                          VSTGUI::kRightText, true);
    } else {
      context->setFontColor(tuner_snapshot_.state == TunerFrameState::unavailable
                                ? kAmber
                                : kMuted);
      context->drawString(tuner_snapshot_.state == TunerFrameState::unavailable
                              ? "TUNER UNAVAILABLE"
                              : "NO VOICED ESTIMATES",
                          scaled_rect(620.0, 278.0, 1000.0, 300.0),
                          VSTGUI::kRightText, true);
    }
    for (std::size_t index = 0U; index < kMaxVoices; ++index) {
      const double left = 24.0 + static_cast<double>(index) * 122.0;
      const TunerVoice* voice =
          tracking && index < tuner_snapshot_.voice_count
              ? &tuner_snapshot_.voices[index]
              : nullptr;
      draw_tuner_card(context, scaled_rect(left, 306.0, left + 116.0, 424.0),
                      index, voice);
    }
    context->setFont(VSTGUI::kNormalFontSmall);
    context->setFontColor(kMuted);
    context->drawString("REAL-TIME DETECTOR ESTIMATES  ·  ±50 CENT WINDOW  ·  NOT MIDI OUTPUT",
                        scaled_rect(24.0, 427.0, 1000.0, 442.0),
                        VSTGUI::kCenterText, true);
  }

  VSTGUI::CRect scaled_rect(double left, double top, double right,
                            double bottom) const noexcept {
    const VSTGUI::CRect bounds = getViewSize();
    const double x_scale = bounds.getWidth() / kEditorWidth;
    const double y_scale = bounds.getHeight() / kEditorHeight;
    return VSTGUI::CRect(bounds.left + left * x_scale,
                          bounds.top + top * y_scale,
                          bounds.left + right * x_scale,
                          bounds.top + bottom * y_scale);
  }

  void relayout_controls() {
    for (std::size_t index = 0; index < controls_.size(); ++index) {
      if (controls_[index] == nullptr) {
        continue;
      }
      const EditorRect& original = layouts_[index].bounds;
      const VSTGUI::CRect resized = scaled_rect(
          original.left, original.top, original.right, original.bottom);
      controls_[index]->setViewSize(resized);
      controls_[index]->setMouseableArea(resized);
    }
  }

  std::array<EditorControlLayout, kEditorControlCount> layouts_{};
  std::array<M3DeckControl*, kEditorControlCount> controls_{};
  const TunerTelemetry& tuner_telemetry_;
  TunerSnapshot tuner_snapshot_{};
  bool has_tuner_snapshot_{};
#if defined(M3_TESTING)
  std::size_t tuner_invalidation_count_{};
#endif
};

class M3Editor final : public VSTGUI::VST3Editor {
 public:
  explicit M3Editor(M3Component& component)
      : VSTGUI::VST3Editor(new StaticEditorDescription(), &component,
                           kEditorTemplateName),
        component_(component),
        edit_controller_(component) {
    getUIDescription()->forget();
    setRect(Steinberg::ViewRect(0, 0, kEditorWidth, kEditorHeight));
    static_cast<void>(setEditorSizeConstrains(
        VSTGUI::CPoint(kEditorWidth, kEditorHeight),
        VSTGUI::CPoint(kEditorMaximumWidth, kEditorMaximumHeight)));
    enableTooltips(true);
    enableShowEditButton(false);
  }

  M3RootSurface* surface() const noexcept { return surface_; }

  bool refresh_tuner_for_test() noexcept {
    return surface_ != nullptr && surface_->refresh_tuner();
  }

  bool tuner_snapshot_for_test(TunerSnapshot& snapshot) const noexcept {
    return surface_ != nullptr && surface_->tuner_snapshot_for_test(snapshot);
  }

#if defined(M3_TESTING)
  std::size_t tuner_invalidation_count_for_test() const noexcept {
    return surface_ == nullptr ? 0U
                               : surface_->tuner_invalidation_count_for_test();
  }
#endif

#if defined(M3_TESTING)
  double content_scale_factor_for_test() const noexcept {
    return getContentScaleFactor();
  }
#endif

 protected:
  ~M3Editor() override = default;

  bool PLUGIN_API open(void* parent, const VSTGUI::PlatformType& type) override {
    if (!VSTGUI::VST3Editor::open(parent, type)) {
      return false;
    }
    if (VSTGUI::CFrame* editor_frame = getFrame()) {
      editor_frame->setFocusColor(kCyan);
      editor_frame->setFocusWidth(2.0);
      editor_frame->setFocusDrawingEnabled(true);
    }
    if (surface_ != nullptr) {
      static_cast<void>(surface_->refresh_tuner());
      tuner_timer_ = VSTGUI::makeOwned<VSTGUI::CVSTGUITimer>(
          [this](VSTGUI::CVSTGUITimer*) {
            if (surface_ != nullptr) {
              static_cast<void>(surface_->refresh_tuner());
            }
          },
          50U, true);
    }
    return true;
  }

  void PLUGIN_API close() override {
    if (tuner_timer_) {
      static_cast<void>(tuner_timer_->stop());
      tuner_timer_ = nullptr;
    }
    VSTGUI::VST3Editor::close();
    surface_ = nullptr;
  }

  VSTGUI::CView* createView(
      const VSTGUI::UIAttributes& attributes,
      const VSTGUI::IUIDescription* ui_description) override {
    const std::string* custom_view = attributes.getAttributeValue(
        VSTGUI::IUIDescription::kCustomViewName);
    if (custom_view != nullptr && *custom_view == kRootViewName) {
      auto* surface =
          new (std::nothrow) M3RootSurface(this, edit_controller_,
                                           component_.tuner_telemetry());
      if (surface == nullptr) {
        return nullptr;
      }
      surface_ = surface;
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
    if (!std::isfinite(scaled) || scaled < 1.0 ||
        scaled > static_cast<double>(
                     std::numeric_limits<Steinberg::int32>::max())) {
      return false;
    }
    physical = static_cast<Steinberg::int32>(scaled);
    return true;
  }

  M3Component& component_;
  Steinberg::Vst::EditController& edit_controller_;
  M3RootSurface* surface_{};
  VSTGUI::SharedPointer<VSTGUI::CVSTGUITimer> tuner_timer_{};
  double logical_width_{static_cast<double>(kEditorWidth)};
  double logical_height_{static_cast<double>(kEditorHeight)};
};

}  // namespace

#if defined(M3_TESTING)
namespace {

M3DeckControl* test_control(Steinberg::IPlugView& view,
                            ParameterId parameter_id) noexcept {
  auto* editor = static_cast<M3Editor*>(&view);
  return editor->surface() == nullptr
             ? nullptr
             : editor->surface()->control_for(parameter_id);
}

VSTGUI::CPoint test_control_point(const M3DeckControl& control,
                                  double x_fraction,
                                  double y_fraction) noexcept {
  const VSTGUI::CRect bounds = control.getViewSize();
  return VSTGUI::CPoint(
      bounds.left + bounds.getWidth() * std::clamp(x_fraction, 0.0, 1.0),
      bounds.top + bounds.getHeight() * std::clamp(y_fraction, 0.0, 1.0));
}

}  // namespace

bool editor_pointer_down_for_test(Steinberg::IPlugView& view,
                                  ParameterId parameter_id,
                                  double x_fraction, double y_fraction,
                                  bool default_reset) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  VSTGUI::MouseDownEvent event(
      test_control_point(*control, x_fraction, y_fraction),
      VSTGUI::MouseEventButtonState(VSTGUI::MouseButton::Left));
  if (default_reset) {
    static_cast<void>(event.modifiers = VSTGUI::ModifierKey::Control);
  }
  control->dispatchEvent(event);
  return static_cast<bool>(event.consumed);
}

bool editor_pointer_drag_for_test(Steinberg::IPlugView& view,
                                  ParameterId parameter_id,
                                  double vertical_delta) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  VSTGUI::CPoint point = test_control_point(*control, 0.5, 0.5);
  point.y += vertical_delta;
  VSTGUI::MouseMoveEvent event(
      point, VSTGUI::MouseEventButtonState(VSTGUI::MouseButton::Left));
  control->dispatchEvent(event);
  return static_cast<bool>(event.consumed);
}

bool editor_pointer_up_for_test(Steinberg::IPlugView& view,
                                ParameterId parameter_id) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  VSTGUI::MouseUpEvent event(
      test_control_point(*control, 0.5, 0.5),
      VSTGUI::MouseEventButtonState(VSTGUI::MouseButton::Left));
  control->dispatchEvent(event);
  return static_cast<bool>(event.consumed);
}

bool editor_pointer_cancel_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  VSTGUI::MouseCancelEvent event;
  control->dispatchEvent(event);
  return static_cast<bool>(event.consumed);
}

bool editor_wheel_for_test(Steinberg::IPlugView& view,
                           ParameterId parameter_id,
                           double vertical_delta) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  VSTGUI::MouseWheelEvent event;
  event.mousePosition = test_control_point(*control, 0.5, 0.5);
  event.deltaY = vertical_delta;
  control->dispatchEvent(event);
  return static_cast<bool>(event.consumed);
}

bool editor_remove_control_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id) noexcept {
  auto* editor = static_cast<M3Editor*>(&view);
  return editor->surface() != nullptr &&
         editor->surface()->remove_control(parameter_id);
}

bool editor_control_bounds_for_test(Steinberg::IPlugView& view,
                                    ParameterId parameter_id,
                                    EditorRect& bounds) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  if (control == nullptr) {
    return false;
  }
  const VSTGUI::CRect view_bounds = control->getViewSize();
  bounds = EditorRect{view_bounds.left, view_bounds.top, view_bounds.right,
                      view_bounds.bottom};
  return true;
}

std::size_t editor_control_invalidation_count_for_test(
    Steinberg::IPlugView& view, ParameterId parameter_id) noexcept {
  M3DeckControl* control = test_control(view, parameter_id);
  return control == nullptr ? 0U : control->invalidation_count_for_test();
}

double editor_content_scale_factor_for_test(
    Steinberg::IPlugView& view) noexcept {
  return static_cast<M3Editor*>(&view)->content_scale_factor_for_test();
}

bool editor_refresh_tuner_for_test(Steinberg::IPlugView& view) noexcept {
  return static_cast<M3Editor*>(&view)->refresh_tuner_for_test();
}

bool editor_tuner_snapshot_for_test(Steinberg::IPlugView& view,
                                    TunerSnapshot& snapshot) noexcept {
  return static_cast<M3Editor*>(&view)->tuner_snapshot_for_test(snapshot);
}

std::size_t editor_tuner_invalidation_count_for_test(
    Steinberg::IPlugView& view) noexcept {
  return static_cast<M3Editor*>(&view)->tuner_invalidation_count_for_test();
}
#endif

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
    M3Component& component) noexcept {
  return new (std::nothrow) M3Editor(component);
}

}  // namespace m3::vst3
