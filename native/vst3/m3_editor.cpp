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
#if defined(M3_TESTING)
#include "vstgui/lib/cbitmap.h"
#include "vstgui/lib/coffscreencontext.h"
#endif
#include "vstgui/lib/cdrawcontext.h"
#include "vstgui/lib/cfont.h"
#include "vstgui/lib/cgradient.h"
#include "vstgui/lib/cgraphicspath.h"
#include "vstgui/lib/cgraphicstransform.h"
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
constexpr ParameterId kMidiRoutingId = 0x4D330001U;
constexpr ParameterId kProfileModeId = 0x4D330002U;
constexpr ParameterId kA4ReferenceId = 0x4D330003U;
constexpr ParameterId kInputTrimId = 0x4D330004U;
constexpr ParameterId kSensitivityId = 0x4D330005U;
constexpr ParameterId kResponseId = 0x4D330006U;
constexpr ParameterId kLowestMidiNoteId = 0x4D330007U;
constexpr ParameterId kHighestMidiNoteId = 0x4D330008U;
constexpr ParameterId kMaximumPolyphonyId = 0x4D330009U;
constexpr ParameterId kMaximumFretId = 0x4D33000AU;
constexpr ParameterId kVelocityModeId = 0x4D33000BU;
constexpr ParameterId kFixedVelocityId = 0x4D33000CU;
constexpr ParameterId kMidiChannelId = 0x4D33000DU;

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
          "maxSize": "2048, 936",
          "minSize": "1024, 468",
          "mouse-enabled": "true",
          "opacity": "1",
          "origin": "0, 0",
          "size": "1024, 468",
          "transparent": "false"
        }
      }
    }
  }
}
)";

const VSTGUI::CColor kGraphite{14U, 21U, 26U, 255U};
const VSTGUI::CColor kPanelBottom{18U, 26U, 31U, 255U};
const VSTGUI::CColor kPanelRaised{39U, 48U, 54U, 255U};
const VSTGUI::CColor kPanelEdge{94U, 106U, 111U, 255U};
const VSTGUI::CColor kPanelEdgeSoft{49U, 61U, 67U, 255U};
const VSTGUI::CColor kText{248U, 243U, 230U, 255U};
const VSTGUI::CColor kCaption{226U, 228U, 220U, 255U};
const VSTGUI::CColor kMuted{177U, 181U, 176U, 255U};
const VSTGUI::CColor kMutedLow{106U, 116U, 119U, 255U};
const VSTGUI::CColor kCyan{255U, 91U, 18U, 255U};
const VSTGUI::CColor kAmber{255U, 126U, 38U, 255U};
const VSTGUI::CColor kRed{255U, 64U, 30U, 255U};
const VSTGUI::CColor kChromeFace{21U, 31U, 36U, 255U};
const VSTGUI::CColor kChromeFaceRaised{32U, 43U, 48U, 255U};
const VSTGUI::CColor kChromeHighlight{133U, 145U, 148U, 150U};
const VSTGUI::CColor kChromeShadow{3U, 6U, 8U, 235U};
const VSTGUI::CColor kButtonHot{226U, 48U, 12U, 255U};
const VSTGUI::CColor kButtonHotTop{255U, 129U, 54U, 255U};
const VSTGUI::CColor kIvory{244U, 237U, 218U, 255U};
const VSTGUI::CColor kIvoryShade{222U, 213U, 192U, 255U};
const VSTGUI::CColor kIvoryHighlight{255U, 251U, 239U, 255U};
const VSTGUI::CColor kInk{14U, 17U, 18U, 255U};
const VSTGUI::CColor kInTuneBlue{23U, 103U, 183U, 255U};
const VSTGUI::CColor kInTuneBlueBloom{23U, 103U, 232U, 255U};
const VSTGUI::CColor kInTuneBlueHighlight{112U, 196U, 255U, 255U};

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

void draw_filled_rounded_surface(VSTGUI::CDrawContext* context,
                                 const VSTGUI::CRect& rect,
                                 const VSTGUI::CColor& fill,
                                 VSTGUI::CCoord radius) {
  if (context == nullptr) {
    return;
  }
  auto path = VSTGUI::owned(context->createGraphicsPath());
  if (!path) {
    return;
  }
  if (radius > 0.0) {
    path->addRoundRect(rect, radius);
  } else {
    path->addRect(rect);
  }
  context->setFillColor(fill);
  context->drawGraphicsPath(path, VSTGUI::CDrawContext::kPathFilled);
}

void fill_material_surface(VSTGUI::CDrawContext* context,
                           const VSTGUI::CRect& rect,
                           const VSTGUI::CColor& top,
                           const VSTGUI::CColor& middle,
                           const VSTGUI::CColor& bottom,
                           VSTGUI::CCoord radius) {
  if (context == nullptr) {
    return;
  }
  auto path = VSTGUI::owned(context->createGraphicsPath());
  auto gradient = VSTGUI::owned(
      VSTGUI::CGradient::create(0.0, 1.0, top, bottom));
  if (!path || !gradient) {
    return;
  }
  if (radius > 0.0) {
    path->addRoundRect(rect, radius);
  } else {
    path->addRect(rect);
  }
  gradient->addColorStop(0.48, middle);
  context->fillLinearGradient(path, *gradient, rect.getTopLeft(),
                              rect.getBottomLeft());
}

void overlay_edge_vignette(VSTGUI::CDrawContext* context,
                           const VSTGUI::CRect& rect,
                           VSTGUI::CCoord radius,
                           std::uint8_t edge_alpha) {
  if (context == nullptr || edge_alpha == 0U) {
    return;
  }
  auto path = VSTGUI::owned(context->createGraphicsPath());
  auto gradient = VSTGUI::owned(VSTGUI::CGradient::create(
      0.0, 1.0, VSTGUI::CColor(0U, 2U, 3U, edge_alpha),
      VSTGUI::CColor(0U, 2U, 3U, edge_alpha)));
  if (!path || !gradient) {
    return;
  }
  if (radius > 0.0) {
    path->addRoundRect(rect, radius);
  } else {
    path->addRect(rect);
  }
  gradient->addColorStop(0.22, VSTGUI::CColor(0U, 2U, 3U, 0U));
  gradient->addColorStop(0.78, VSTGUI::CColor(0U, 2U, 3U, 0U));
  context->fillLinearGradient(path, *gradient, rect.getTopLeft(),
                              rect.getTopRight());
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

VSTGUI::CFontRef instrument_font() noexcept {
  static const auto font = VSTGUI::makeOwned<VSTGUI::CFontDesc>(
      editor_instrument_font_family(), 12.0);
  return font.get();
}

void draw_ascii_tracked(VSTGUI::CDrawContext* context, const char* text,
                        const VSTGUI::CRect& rect,
                        VSTGUI::CHoriTxtAlign align,
                        VSTGUI::CCoord tracking) {
  if (context == nullptr || text == nullptr || tracking <= 0.0) {
    return;
  }
  std::size_t length = 0U;
  double width = 0.0;
  for (const char* cursor = text; *cursor != '\0'; ++cursor) {
    char glyph[2]{*cursor, '\0'};
    width += context->getStringWidth(glyph);
    ++length;
  }
  if (length > 1U) {
    width += tracking * static_cast<double>(length - 1U);
  }
  double x = rect.left;
  if (align == VSTGUI::kCenterText) {
    x = rect.getCenter().x - width * 0.5;
  } else if (align == VSTGUI::kRightText) {
    x = rect.right - width;
  }
  for (const char* cursor = text; *cursor != '\0'; ++cursor) {
    char glyph[2]{*cursor, '\0'};
    const double glyph_width = context->getStringWidth(glyph);
    context->drawString(
        glyph,
        VSTGUI::CRect(x, rect.top, x + glyph_width + 1.0, rect.bottom),
        VSTGUI::kLeftText, true);
    x += glyph_width + tracking;
  }
}

void draw_embossed_text(
    VSTGUI::CDrawContext* context, const char* text,
    const VSTGUI::CRect& rect, VSTGUI::CCoord font_size,
    const VSTGUI::CColor& color,
    VSTGUI::CHoriTxtAlign align = VSTGUI::kCenterText,
    std::int32_t style = VSTGUI::kBoldFace,
    VSTGUI::CCoord shadow_offset = 1.4,
    VSTGUI::CCoord horizontal_scale = 1.0,
    bool use_instrument_font = true,
    VSTGUI::CCoord tracking = 0.0) {
  if (context == nullptr || text == nullptr) {
    return;
  }
  context->setFont(use_instrument_font ? instrument_font()
                                       : VSTGUI::kNormalFont,
                   font_size, style);
  const double anchor = align == VSTGUI::kLeftText
                            ? rect.left
                            : align == VSTGUI::kRightText ? rect.right
                                                          : rect.getCenter().x;
  VSTGUI::CGraphicsTransform condensed;
  condensed.translate(-anchor, 0.0)
      .scale(horizontal_scale, 1.0)
      .translate(anchor, 0.0);
  VSTGUI::CDrawContext::Transform transform(*context, condensed);
  VSTGUI::CRect shadow = rect;
  shadow.offset(shadow_offset, shadow_offset + 0.6);
  context->setFontColor(VSTGUI::CColor(1U, 3U, 4U, 220U));
  if (tracking > 0.0) {
    draw_ascii_tracked(context, text, shadow, align, tracking);
  } else {
    context->drawString(text, shadow, align, true);
  }
  context->setFontColor(color);
  if (tracking > 0.0) {
    draw_ascii_tracked(context, text, rect, align, tracking);
  } else {
    context->drawString(text, rect, align, true);
  }
}

void draw_beveled_panel(VSTGUI::CDrawContext* context,
                        const VSTGUI::CRect& rect,
                        VSTGUI::CCoord radius,
                        VSTGUI::CCoord shadow_offset) {
  if (context == nullptr) {
    return;
  }
  constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
  radius = std::min(radius, chrome.surface_corner_radius);
  VSTGUI::CRect shadow = rect;
  shadow.offset(0.0, shadow_offset);
  draw_filled_rounded_surface(context, shadow, kChromeShadow, radius);
  fill_material_surface(context, rect,
                        VSTGUI::CColor(48U, 59U, 64U, 255U),
                        VSTGUI::CColor(31U, 42U, 47U, 255U),
                        VSTGUI::CColor(17U, 27U, 32U, 255U), radius);
  overlay_edge_vignette(context, rect, radius,
                        chrome.chassis_vignette_alpha);
  auto outline = VSTGUI::owned(context->createGraphicsPath());
  if (outline) {
    outline->addRoundRect(rect, radius);
    context->setFrameColor(VSTGUI::CColor(116U, 128U, 131U, 205U));
    context->setLineWidth(1.0);
    context->drawGraphicsPath(outline, VSTGUI::CDrawContext::kPathStroked);
  }
  draw_rule(context,
            VSTGUI::CPoint(rect.left + radius, rect.top + 1.0),
            VSTGUI::CPoint(rect.right - radius, rect.top + 1.0),
            VSTGUI::CColor(188U, 198U, 198U, 92U), 1.0);
}

void draw_control_well(VSTGUI::CDrawContext* context,
                       const VSTGUI::CRect& rect,
                       VSTGUI::CCoord radius = 5.0) {
  if (context == nullptr) {
    return;
  }
  constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
  radius = std::min(radius, chrome.control_corner_radius);
  VSTGUI::CRect shadow = rect;
  shadow.offset(0.0, 2.0);
  draw_filled_rounded_surface(context, shadow, kChromeShadow, radius);
  fill_material_surface(context, rect,
                        VSTGUI::CColor(34U, 44U, 48U, 255U),
                        VSTGUI::CColor(20U, 29U, 33U, 255U),
                        VSTGUI::CColor(9U, 15U, 18U, 255U), radius);
  auto outline = VSTGUI::owned(context->createGraphicsPath());
  if (outline) {
    outline->addRoundRect(rect, radius);
    context->setFrameColor(VSTGUI::CColor(184U, 191U, 188U, 220U));
    context->setLineWidth(1.0);
    context->drawGraphicsPath(outline, VSTGUI::CDrawContext::kPathStroked);
  }
  draw_rule(context, VSTGUI::CPoint(rect.left + 6.0, rect.top + 1.0),
            VSTGUI::CPoint(rect.right - 6.0, rect.top + 1.0),
            VSTGUI::CColor(240U, 241U, 232U, 110U), 1.0);
}

void draw_settings_tile(VSTGUI::CDrawContext* context,
                        const VSTGUI::CRect& rect) {
  if (context == nullptr) {
    return;
  }
  VSTGUI::CRect tile = rect;
  tile.inset(1.0, 1.0);
  VSTGUI::CRect shadow = tile;
  shadow.offset(0.0, 2.0);
  draw_filled_rounded_surface(context, shadow, kChromeShadow, 4.0);
  fill_material_surface(context, tile,
                        VSTGUI::CColor(38U, 48U, 52U, 255U),
                        VSTGUI::CColor(23U, 33U, 37U, 255U),
                        VSTGUI::CColor(11U, 18U, 21U, 255U), 4.0);
  for (unsigned grain = 0U; grain < 4U; ++grain) {
    const double y = tile.top + 36.0 + static_cast<double>(grain) * 20.0;
    if (y >= tile.bottom - 6.0) {
      break;
    }
    draw_rule(context, VSTGUI::CPoint(tile.left + 5.0, y),
              VSTGUI::CPoint(tile.right - 5.0, y),
              VSTGUI::CColor(207U, 216U, 212U,
                             static_cast<std::uint8_t>(grain % 2U == 0U
                                                           ? 10U
                                                           : 6U)),
              1.0);
  }
  auto outline = VSTGUI::owned(context->createGraphicsPath());
  if (outline) {
    outline->addRoundRect(tile, 4.0);
    context->setFrameColor(VSTGUI::CColor(104U, 118U, 121U, 118U));
    context->setLineWidth(1.0);
    context->drawGraphicsPath(outline, VSTGUI::CDrawContext::kPathStroked);
  }
  draw_rule(context, VSTGUI::CPoint(tile.left + 5.0, tile.top + 1.0),
            VSTGUI::CPoint(tile.right - 5.0, tile.top + 1.0),
            VSTGUI::CColor(204U, 212U, 207U, 44U), 1.0);
}

void draw_soft_rect_glow(VSTGUI::CDrawContext* context,
                         const VSTGUI::CRect& rect,
                         const VSTGUI::CColor& color,
                         VSTGUI::CCoord radius,
                         VSTGUI::CCoord spread,
                         std::uint8_t outer_alpha,
                         std::uint8_t inner_alpha) {
  if (context == nullptr || spread <= 0.0) {
    return;
  }
  constexpr std::size_t kLayers = 6U;
  for (std::size_t layer = 0U; layer < kLayers; ++layer) {
    const double t = static_cast<double>(layer) /
                     static_cast<double>(kLayers - 1U);
    const double extension = spread * (1.0 - t * 0.82);
    const auto alpha = static_cast<std::uint8_t>(std::lround(
        static_cast<double>(outer_alpha) +
        (static_cast<double>(inner_alpha) - outer_alpha) * t));
    VSTGUI::CRect halo = rect;
    halo.extend(extension, extension);
    draw_filled_rounded_surface(
        context, halo,
        VSTGUI::CColor(color.red, color.green, color.blue, alpha),
        radius + extension);
  }
}

void draw_beveled_button(VSTGUI::CDrawContext* context,
                         const VSTGUI::CRect& rect,
                         const VSTGUI::CColor& fill,
                         VSTGUI::CCoord radius, bool glow) {
  if (context == nullptr) {
    return;
  }
  constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
  radius = std::min(radius, chrome.control_corner_radius);
  VSTGUI::CRect face = rect;
  face.inset(chrome.button_face_inset, chrome.button_face_inset);
  face.bottom -= chrome.button_shadow_offset;
  VSTGUI::CRect shadow = face;
  shadow.offset(0.0, chrome.button_shadow_offset);
  draw_filled_rounded_surface(context, shadow, kChromeShadow, radius);
  if (glow) {
    draw_soft_rect_glow(context, face, kCyan, radius,
                        chrome.button_glow_spread,
                        chrome.glow_outer_alpha,
                        chrome.glow_inner_alpha);
  }
  const bool hot_face = fill.red > 100U && fill.green < 100U;
  fill_material_surface(
      context, face,
      hot_face ? VSTGUI::CColor(255U, 112U, 34U, 255U)
               : VSTGUI::CColor(39U, 49U, 52U, 255U),
      hot_face ? VSTGUI::CColor(235U, 60U, 14U, 255U)
               : VSTGUI::CColor(24U, 33U, 37U, 255U),
      fill, radius);
  auto outline = VSTGUI::owned(context->createGraphicsPath());
  if (outline) {
    outline->addRoundRect(face, radius);
    context->setFrameColor(
        glow ? VSTGUI::CColor(255U, 111U, 34U, 235U)
             : VSTGUI::CColor(178U, 187U, 185U, 220U));
    context->setLineWidth(glow ? 1.35 : 1.0);
    context->drawGraphicsPath(outline, VSTGUI::CDrawContext::kPathStroked);
  }
  draw_rule(context, VSTGUI::CPoint(face.left + radius, face.top + 1.0),
            VSTGUI::CPoint(face.right - radius, face.top + 1.0),
            glow ? VSTGUI::CColor(255U, 222U, 174U, 190U)
                 : kChromeHighlight,
            1.0);
}

void draw_chevron(VSTGUI::CDrawContext* context,
                   const VSTGUI::CPoint& center, bool up,
                   const VSTGUI::CColor& color) {
  if (context == nullptr) {
    return;
  }
  const double direction = up ? -1.0 : 1.0;
  const VSTGUI::CPoint tip(center.x, center.y + direction * 3.0);
  draw_rule(context, VSTGUI::CPoint(center.x - 4.0, center.y - direction),
            tip, color, 1.8);
  draw_rule(context, tip,
            VSTGUI::CPoint(center.x + 4.0, center.y - direction), color, 1.8);
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

VSTGUI::CRect to_rect(const EditorRect& rect) noexcept {
  return VSTGUI::CRect(rect.left, rect.top, rect.right, rect.bottom);
}

void prepare_crisp_drawing(VSTGUI::CDrawContext* context) noexcept {
  if (context != nullptr) {
    context->setDrawMode(VSTGUI::kAntiAliasing | VSTGUI::kNonIntegralMode);
  }
}

const char* const* segment_labels(ParameterId id,
                                  std::size_t& count) noexcept {
  static const char* const kMidiRoutingLabels[] = {"SINGLE", "PER VOICE"};
  static const char* const kModeLabels[] = {"M3", "GENERAL"};
  static const char* const kVelocityLabels[] = {"FIXED", "DYNAMIC"};
  static const char* const kSensitivityLabels[] = {"LOW", "MED", "HIGH"};
  static const char* const kResponseLabels[] = {"SLOW", "FAST"};
  count = 0U;
  if (id == kMidiRoutingId) {
    count = std::size(kMidiRoutingLabels);
    return kMidiRoutingLabels;
  }
  if (id == kProfileModeId) {
    count = std::size(kModeLabels);
    return kModeLabels;
  }
  if (id == kVelocityModeId) {
    count = std::size(kVelocityLabels);
    return kVelocityLabels;
  }
  if (id == kSensitivityId) {
    count = std::size(kSensitivityLabels);
    return kSensitivityLabels;
  }
  if (id == kResponseId) {
    count = std::size(kResponseLabels);
    return kResponseLabels;
  }
  return nullptr;
}

const char* segment_title(ParameterId id) noexcept {
  if (id == kMidiRoutingId) {
    return "MIDI ROUTING";
  }
  if (id == kProfileModeId) {
    return "INSTRUMENT PROFILE";
  }
  if (id == kVelocityModeId) {
    return "VELOCITY MODE";
  }
  if (id == kSensitivityId) {
    return "SENSITIVITY";
  }
  if (id == kResponseId) {
    return "RESPONSE";
  }
  return "MODE";
}

const char* settings_knob_title(ParameterId id) noexcept {
  if (id == kA4ReferenceId) {
    return "A4 REFERENCE";
  }
  if (id == kInputTrimId) {
    return "INPUT TRIM";
  }
  if (id == kSensitivityId) {
    return "SENSITIVITY";
  }
  if (id == kResponseId) {
    return "RESPONSE";
  }
  if (id == kMaximumPolyphonyId) {
    return "MAX POLYPHONY";
  }
  if (id == kMaximumFretId) {
    return "MAXIMUM FRET";
  }
  if (id == kFixedVelocityId) {
    return "FIXED VELOCITY";
  }
  if (id == kMidiChannelId) {
    return "MIDI CH / START";
  }
  return "VALUE";
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
                Steinberg::Vst::EditController& controller,
                EditorSurfacePage page)
      : VSTGUI::CControl(to_rect(layout.bounds), control_listener,
                         static_cast<Steinberg::int32>(layout.parameter_id)),
        layout_(layout),
        controller_(controller) {
    const ParameterSpec* spec = find_parameter(layout.parameter_id);
    if (spec != nullptr) {
      setTooltipText(spec->name);
      setDefaultValue(static_cast<float>(plain_to_normalized(
          *spec, spec->default_value)));
      setWheelInc(1.0F / static_cast<float>(spec->step_count));
    }
    set_layout(layout, page);
  }

  ~M3DeckControl() noexcept override { cancel_interaction(); }

  void set_dependent_control(M3DeckControl* dependent) noexcept {
    dependent_control_ = dependent;
  }

  void set_layout(const EditorControlLayout& layout,
                  EditorSurfacePage page) noexcept {
    layout_ = layout;
    page_ = page;
    if (layout_.parameter_id == kFixedVelocityId &&
        page == EditorSurfacePage::settings) {
      // Keep the dependent value visible as a truthful locked state while
      // Dynamic velocity is selected. interaction_allowed() remains the gate.
      layout_.visible = true;
      layout_.enabled = true;
    }
    setVisible(layout_.visible);
    setMouseEnabled(layout_.visible && layout_.enabled);
    setWantsFocus(layout_.visible && layout_.enabled);
    invalid();
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
    prepare_crisp_drawing(context);
    const double normalized = std::clamp(
        controller_.getParamNormalized(layout_.parameter_id), 0.0, 1.0);
    setValueNormalized(static_cast<float>(normalized));
    if (page_ == EditorSurfacePage::settings &&
        layout_.presentation != EditorPresentation::status &&
        layout_.presentation != EditorPresentation::momentary) {
      draw_settings_tile(context, getViewSize());
    }
    switch (layout_.presentation) {
      case EditorPresentation::knob:
        if (page_ == EditorSurfacePage::tuner &&
            (layout_.parameter_id == kSensitivityId ||
             layout_.parameter_id == kResponseId)) {
          draw_compact_range(context, normalized);
        } else {
          draw_knob(context, normalized);
        }
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
      case EditorPresentation::compact_value:
        draw_compact_value(context, normalized);
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
        layout_.presentation == EditorPresentation::compact_value ||
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
      if (layout_.parameter_id == kResponseId) {
        requested = 1.0 - requested;
      }
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
         layout_.presentation != EditorPresentation::compact_value &&
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
      draw_embossed_text(
          context, "FIXED VELOCITY",
          VSTGUI::CRect(bounds.left + 8.0, bounds.top + 7.0,
                        bounds.right - 8.0, bounds.top + 27.0),
          12.0, kCaption, VSTGUI::kCenterText, VSTGUI::kBoldFace, 0.8,
          1.0, true, 0.7);
      draw_embossed_text(
          context, "LOCKED",
          VSTGUI::CRect(bounds.left + 8.0, bounds.top + 38.0,
                        bounds.right - 8.0, bounds.top + 73.0),
          19.0, kMutedLow, VSTGUI::kCenterText, VSTGUI::kBoldFace, 1.0);
      draw_embossed_text(
          context, "SELECT FIXED MODE",
          VSTGUI::CRect(bounds.left + 8.0, bounds.bottom - 31.0,
                        bounds.right - 8.0, bounds.bottom - 9.0),
          10.5, kAmber, VSTGUI::kCenterText, VSTGUI::kNormalFace, 0.7);
      return;
    }
    const bool settings = page_ == EditorSurfacePage::settings;
    const ParameterSpec* spec = find_parameter(layout_.parameter_id);
    if (settings) {
      draw_embossed_text(
          context, settings_knob_title(layout_.parameter_id),
          VSTGUI::CRect(bounds.left + 6.0, bounds.top + 7.0,
                        bounds.right - 6.0, bounds.top + 27.0),
          12.0, kCaption, VSTGUI::kCenterText, VSTGUI::kBoldFace, 0.8,
          1.0, true, 0.45);
    }
    const VSTGUI::CCoord diameter = settings
        ? std::min<VSTGUI::CCoord>(76.0, bounds.getWidth() - 34.0)
        : std::min(bounds.getWidth(), bounds.getHeight() - 28.0);
    const VSTGUI::CPoint center(
        bounds.getCenter().x,
        settings ? bounds.top + 64.0 : bounds.top + diameter / 2.0);
    VSTGUI::CRect dial(center.x - diameter / 2.0, center.y - diameter / 2.0,
                       center.x + diameter / 2.0, center.y + diameter / 2.0);
    dial.inset(settings ? 3.0 : 8.0, settings ? 3.0 : 8.0);
    VSTGUI::CRect broad_shadow = dial;
    broad_shadow.extend(2.0, 1.0);
    broad_shadow.offset(2.0, 4.0);
    context->setFillColor(VSTGUI::CColor(1U, 3U, 4U, 105U));
    context->drawEllipse(broad_shadow, VSTGUI::kDrawFilled);
    VSTGUI::CRect contact_shadow = dial;
    contact_shadow.offset(1.2, 2.4);
    context->setFillColor(VSTGUI::CColor(1U, 3U, 4U, 215U));
    context->drawEllipse(contact_shadow, VSTGUI::kDrawFilled);
    context->setFillColor(kPanelBottom);
    context->setFrameColor(kPanelEdgeSoft);
    context->setLineWidth(1.0);
    context->drawEllipse(dial, VSTGUI::kDrawFilledAndStroked);
    context->setFrameColor(kPanelEdge);
    context->setLineWidth(3.0);
    constexpr float kStartAngle = static_cast<float>(
        135.0 * VSTGUI::Constants::pi / 180.0);
    constexpr float kSweepAngle = static_cast<float>(
        270.0 * VSTGUI::Constants::pi / 180.0);
    context->drawArc(dial, kStartAngle, kStartAngle + kSweepAngle,
                     VSTGUI::kDrawStroked);
    context->setFrameColor(kCyan);
    context->setLineWidth(3.0);
    context->drawArc(dial, kStartAngle,
                     kStartAngle +
                         static_cast<float>(normalized) * kSweepAngle,
                     VSTGUI::kDrawStroked);
    VSTGUI::CRect rim_highlight = dial;
    rim_highlight.inset(2.0, 2.0);
    context->setFrameColor(VSTGUI::CColor(208U, 216U, 212U, 72U));
    context->setLineWidth(1.2);
    context->drawArc(
        rim_highlight,
        static_cast<float>(205.0 * VSTGUI::Constants::pi / 180.0),
        static_cast<float>(326.0 * VSTGUI::Constants::pi / 180.0),
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
    if (settings) {
      draw_embossed_text(
          context, value_text,
          VSTGUI::CRect(bounds.left + 4.0, bounds.bottom - 28.0,
                        bounds.right - 4.0, bounds.bottom - 7.0),
          12.5, kText, VSTGUI::kCenterText, VSTGUI::kBoldFace, 0.8);
    } else {
      draw_label(context, value_text,
                 VSTGUI::CRect(bounds.left, bounds.bottom - 27.0,
                                bounds.right, bounds.bottom - 7.0),
                 kText);
    }
    if (!settings) {
      draw_label(context, spec == nullptr ? "" : spec->name,
                 VSTGUI::CRect(bounds.left, bounds.bottom - 18.0,
                                bounds.right, bounds.bottom),
                 kMuted);
    }
  }

  void draw_compact_value(VSTGUI::CDrawContext* context,
                          double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    const char* title = layout_.parameter_id == kA4ReferenceId
                            ? "A4 REFERENCE"
                            : layout_.parameter_id == kMidiChannelId
                                  ? "MIDI CH"
                                  : "VALUE";
    draw_embossed_text(
        context, title,
        VSTGUI::CRect(bounds.left + 2.0, bounds.top, bounds.right - 2.0,
                      bounds.top + 19.0),
        chrome.control_caption_font_size,
        page_ == EditorSurfacePage::tuner ? kCaption : kMuted,
        VSTGUI::kLeftText);
    VSTGUI::CRect selector(bounds.left + 1.0, bounds.top + 23.0,
                           bounds.right - 1.0, bounds.bottom - 3.0);
    draw_control_well(context, selector, 5.0);
    const double arrow_left = selector.right - 27.0;
    draw_rule(context, VSTGUI::CPoint(arrow_left, selector.top + 1.0),
              VSTGUI::CPoint(arrow_left, selector.bottom - 1.0),
              kPanelEdge, 1.0);
    char value_text[128]{};
    parameter_text(normalized, value_text);
    draw_embossed_text(
        context, value_text,
        VSTGUI::CRect(selector.left + 4.0, selector.top,
                      arrow_left - 2.0, selector.bottom),
        chrome.control_value_font_size, kText);
    draw_chevron(context,
                 VSTGUI::CPoint(arrow_left + 13.5, selector.top + 11.0), true,
                 kText);
    draw_chevron(context,
                 VSTGUI::CPoint(arrow_left + 13.5, selector.bottom - 10.0),
                 false, kText);
  }

  void draw_compact_range(VSTGUI::CDrawContext* context,
                          double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    draw_embossed_text(
        context,
        layout_.parameter_id == kSensitivityId ? "SENSITIVITY" : "RESPONSE",
        VSTGUI::CRect(bounds.left + 2.0, bounds.top, bounds.right - 2.0,
                      bounds.top + 19.0),
        chrome.control_caption_font_size,
        page_ == EditorSurfacePage::tuner ? kCaption : kMuted,
        VSTGUI::kLeftText);
    std::size_t count = 0U;
    const char* const* labels = segment_labels(layout_.parameter_id, count);
    if (labels == nullptr || count < 2U) {
      return;
    }
    const double display_normalized =
        layout_.parameter_id == kResponseId ? 1.0 - normalized : normalized;
    const std::size_t selected = static_cast<std::size_t>(std::llround(
        display_normalized * static_cast<double>(count - 1U)));
    VSTGUI::CRect selector(bounds.left + 1.0, bounds.top + 23.0,
                           bounds.right - 1.0, bounds.bottom - 3.0);
    draw_control_well(context, selector, 5.0);
    const double width = selector.getWidth() / static_cast<double>(count);
    for (std::size_t index = 0U; index < count; ++index) {
      const double item = static_cast<double>(index);
      VSTGUI::CRect segment(selector.left + width * item, selector.top,
                            selector.left + width * (item + 1.0),
                            selector.bottom);
      if (index == selected) {
        VSTGUI::CRect active = segment;
        draw_beveled_button(context, active, kButtonHot, 4.0, true);
      } else if (index > 0U) {
        draw_rule(context, VSTGUI::CPoint(segment.left, segment.top + 8.0),
                  VSTGUI::CPoint(segment.left, segment.bottom - 8.0),
                  kPanelEdgeSoft);
      }
      draw_embossed_text(context, labels[index], segment, 13.5,
                         index == selected ? kText : kCaption,
                         VSTGUI::kCenterText, VSTGUI::kNormalFace, 0.9);
    }
  }

  void draw_segment(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    const char* title = segment_title(layout_.parameter_id);
    if (page_ == EditorSurfacePage::tuner) {
      if (layout_.parameter_id == kMidiRoutingId) {
        title = "MIDI MODE";
      } else if (layout_.parameter_id == kProfileModeId) {
        title = "PROFILE";
      }
    }
    draw_embossed_text(
        context, title,
        VSTGUI::CRect(bounds.left + (page_ == EditorSurfacePage::settings ? 7.0 : 2.0),
                      bounds.top + (page_ == EditorSurfacePage::settings ? 7.0 : 0.0),
                      bounds.right - (page_ == EditorSurfacePage::settings ? 7.0 : 2.0),
                      bounds.top + (page_ == EditorSurfacePage::settings ? 27.0 : 19.0)),
        chrome.control_caption_font_size,
        page_ == EditorSurfacePage::tuner ? kCaption : kMuted,
        page_ == EditorSurfacePage::tuner ? VSTGUI::kLeftText
                                          : VSTGUI::kCenterText,
        VSTGUI::kBoldFace, 0.8, 1.0, true,
        page_ == EditorSurfacePage::settings ? 0.55 : 0.0);
    std::size_t count = 0U;
    const char* const* labels = segment_labels(layout_.parameter_id, count);
    if (labels == nullptr || count < 2U) {
      return;
    }
    const double display_normalized =
        layout_.parameter_id == kResponseId ? 1.0 - normalized : normalized;
    const std::size_t selected = static_cast<std::size_t>(std::llround(
        display_normalized * static_cast<double>(count - 1U)));
    VSTGUI::CRect selector = page_ == EditorSurfacePage::settings
        ? VSTGUI::CRect(bounds.left + 8.0, bounds.top + 42.0,
                        bounds.right - 8.0, bounds.bottom - 23.0)
        : VSTGUI::CRect(bounds.left + 1.0, bounds.top + 23.0,
                        bounds.right - 1.0, bounds.bottom - 3.0);
    draw_control_well(context, selector, 5.0);
    const double width = selector.getWidth() / static_cast<double>(count);
    for (std::size_t index = 0; index < count; ++index) {
      VSTGUI::CRect segment(
          selector.left + width * static_cast<double>(index), selector.top,
          selector.left + width * static_cast<double>(index + 1U),
          selector.bottom);
      if (index == selected) {
        VSTGUI::CRect active = segment;
        draw_beveled_button(context, active, kButtonHot, 4.0, true);
        draw_rule(context,
                  VSTGUI::CPoint(active.left + 7.0, active.bottom - 3.0),
                  VSTGUI::CPoint(active.right - 7.0, active.bottom - 3.0),
                  kCyan, 2.0);
      } else if (index > 0U) {
        draw_rule(context, VSTGUI::CPoint(segment.left, segment.top + 6.0),
                  VSTGUI::CPoint(segment.left, segment.bottom - 6.0),
                  kPanelEdgeSoft);
      }
      draw_embossed_text(context, labels[index], segment, 13.5,
                         index == selected ? kText : kCaption,
                         VSTGUI::kCenterText, VSTGUI::kNormalFace, 0.9);
    }
  }

  void draw_toggle(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    const bool enabled = normalized >= 0.5;
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    draw_embossed_text(
        context, "DRY AUDIO",
        VSTGUI::CRect(bounds.left + (page_ == EditorSurfacePage::settings ? 7.0 : 2.0),
                      bounds.top + (page_ == EditorSurfacePage::settings ? 7.0 : 0.0),
                      bounds.right - (page_ == EditorSurfacePage::settings ? 7.0 : 2.0),
                      bounds.top + (page_ == EditorSurfacePage::settings ? 27.0 : 19.0)),
        chrome.control_caption_font_size,
        page_ == EditorSurfacePage::tuner ? kCaption : kMuted,
        page_ == EditorSurfacePage::tuner ? VSTGUI::kLeftText
                                          : VSTGUI::kCenterText,
        VSTGUI::kBoldFace, 0.8, 1.0, true,
        page_ == EditorSurfacePage::settings ? 0.55 : 0.0);
    VSTGUI::CRect selector = page_ == EditorSurfacePage::settings
        ? VSTGUI::CRect(bounds.left + 8.0, bounds.top + 42.0,
                        bounds.right - 8.0, bounds.bottom - 23.0)
        : VSTGUI::CRect(bounds.left + 1.0, bounds.top + 23.0,
                        bounds.right - 1.0, bounds.bottom - 3.0);
    draw_control_well(context, selector, 5.0);
    const double half = selector.getWidth() / 2.0;
    const VSTGUI::CRect off(selector.left, selector.top, selector.left + half,
                            selector.bottom);
    const VSTGUI::CRect monitor(selector.left + half, selector.top,
                                selector.right, selector.bottom);
    VSTGUI::CRect active = enabled ? monitor : off;
    draw_beveled_button(context, active, kButtonHot, 4.0, true);
    draw_embossed_text(context, "OFF", off, 13.5,
                       enabled ? kMuted : kText, VSTGUI::kCenterText,
                       VSTGUI::kNormalFace, 0.9);
    draw_embossed_text(context, "MONITOR", monitor, 11.5,
                       enabled ? kText : kMuted, VSTGUI::kCenterText,
                       VSTGUI::kNormalFace, 0.9);
  }

  void draw_note_range(VSTGUI::CDrawContext* context,
                       double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    context->setFillColor(kCyan);
    context->drawRect(VSTGUI::CRect(bounds.left + 1.0, bounds.top + 14.0,
                                    bounds.left + 4.0, bounds.bottom - 14.0),
                      VSTGUI::kDrawFilled);
    char value_text[128]{};
    parameter_text(normalized, value_text);
    draw_embossed_text(
        context,
        layout_.parameter_id == kLowestMidiNoteId ? "LOW LIMIT"
                                                  : "HIGH LIMIT",
        VSTGUI::CRect(bounds.left + 12.0, bounds.top + 7.0,
                      bounds.right - 10.0, bounds.top + 27.0),
        12.0, kCaption, VSTGUI::kLeftText, VSTGUI::kBoldFace, 0.8,
        1.0, true, 0.65);
    draw_embossed_text(
        context, value_text,
        VSTGUI::CRect(bounds.left + 12.0, bounds.top + 38.0,
                      bounds.right - 10.0, bounds.top + 78.0),
        24.0, kText, VSTGUI::kLeftText, VSTGUI::kBoldFace, 1.0);
    draw_embossed_text(
        context, "MIDI NOTE  ·  LINKED",
        VSTGUI::CRect(bounds.left + 12.0, bounds.bottom - 31.0,
                      bounds.right - 9.0, bounds.bottom - 9.0),
        9.5, kCyan, VSTGUI::kLeftText, VSTGUI::kNormalFace, 0.7);
  }

  void draw_momentary(VSTGUI::CDrawContext* context) const {
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    VSTGUI::CRect face = bounds;
    face.inset(chrome.momentary_face_inset,
               chrome.momentary_face_inset);
    draw_beveled_button(context, face,
                        panic_pressed_
                            ? VSTGUI::CColor(226U, 57U, 16U, 255U)
                            : kButtonHot,
                        7.0, true);
    draw_embossed_text(
        context, panic_pressed_ ? "PANIC HELD" : "PANIC",
        VSTGUI::CRect(face.left + 10.0, face.top + 3.0,
                      face.right - 10.0, face.bottom - 4.0),
        22.5, kText);
  }

  void draw_status(VSTGUI::CDrawContext* context, double normalized) const {
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    const int status_index = std::clamp(
        static_cast<int>(std::llround(normalized * 5.0)), 0, 5);
    const Status status = static_cast<Status>(status_index);
    draw_embossed_text(
        context, "M3",
        VSTGUI::CRect(bounds.left + 12.0, bounds.top + 1.0,
                      bounds.left + 126.0, bounds.bottom - 4.0),
        chrome.header_logo_font_size, VSTGUI::CColor(255U, 244U, 218U, 255U),
        VSTGUI::kLeftText, VSTGUI::kBoldFace, 2.8, 1.20, false);
    draw_rule(context, VSTGUI::CPoint(bounds.left + 132.0, bounds.top + 17.0),
              VSTGUI::CPoint(bounds.left + 132.0, bounds.bottom - 12.0),
              VSTGUI::CColor(183U, 191U, 190U, 205U), 1.0);
    draw_embossed_text(
        context, "POLYPHONIC TUNER",
        VSTGUI::CRect(bounds.left + 158.0,
                      bounds.top + chrome.header_title_top_offset,
                      bounds.right - 6.0,
                      bounds.top + chrome.header_title_top_offset + 43.0),
        chrome.header_title_font_size, kText, VSTGUI::kLeftText,
        VSTGUI::kBoldFace, 1.7, 1.0, true,
        chrome.header_title_tracking);
    draw_embossed_text(
        context, "A U D I O   →   M I D I",
        VSTGUI::CRect(bounds.left + 159.0, bounds.top + 44.0,
                      bounds.right - 104.0, bounds.bottom - 7.0),
        12.0, kCaption, VSTGUI::kLeftText, VSTGUI::kNormalFace, 1.0, 1.08);
    if (status != Status::ready) {
      context->setFillColor(status_deck_color(status));
      context->setFrameColor(
          VSTGUI::CColor(kCyan.red, kCyan.green, kCyan.blue, 48U));
      context->setLineWidth(3.0);
      context->drawEllipse(VSTGUI::CRect(bounds.right - 94.0,
                                         bounds.bottom - 29.0,
                                         bounds.right - 86.0,
                                         bounds.bottom - 21.0),
                           VSTGUI::kDrawStroked);
      context->drawEllipse(VSTGUI::CRect(bounds.right - 92.0,
                                         bounds.bottom - 27.0,
                                         bounds.right - 88.0,
                                         bounds.bottom - 23.0),
                           VSTGUI::kDrawFilled);
      draw_embossed_text(
          context, status_label(status),
          VSTGUI::CRect(bounds.right - 82.0, bounds.bottom - 36.0,
                        bounds.right - 2.0, bounds.bottom - 14.0),
          9.5, status_deck_color(status), VSTGUI::kLeftText,
          VSTGUI::kNormalFace, 0.8);
    }
  }

  EditorControlLayout layout_;
  EditorSurfacePage page_{EditorSurfacePage::settings};
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

class M3SettingsButton final : public VSTGUI::CControl {
 public:
  using ToggleCallback = void (*)(void*) noexcept;

  M3SettingsButton(const EditorRect& bounds, const bool& settings_open,
                   void* callback_context, ToggleCallback callback)
      : VSTGUI::CControl(to_rect(bounds), nullptr, -1),
        settings_open_(settings_open),
        callback_context_(callback_context),
        callback_(callback) {
    setWantsFocus(true);
    setTooltipText("Open or close tuner settings");
  }

  void draw(VSTGUI::CDrawContext* context) override {
    if (context == nullptr) {
      return;
    }
    prepare_crisp_drawing(context);
    const VSTGUI::CRect bounds = getViewSize();
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    if (settings_open_) {
      VSTGUI::CRect button = bounds;
      button.inset(1.0, 1.0);
      draw_beveled_button(context, button, kPanelBottom, 4.0, true);
      const VSTGUI::CPoint back_tip(button.left + 14.0,
                                    button.getCenter().y - 1.0);
      draw_rule(context,
                VSTGUI::CPoint(back_tip.x + 5.0, back_tip.y - 4.0),
                back_tip, kText, 1.8);
      draw_rule(context, back_tip,
                VSTGUI::CPoint(back_tip.x + 5.0, back_tip.y + 4.0),
                kText, 1.8);
      draw_embossed_text(
          context, "DONE",
          VSTGUI::CRect(button.left + 30.0, button.top,
                        button.right - 8.0, button.bottom - 2.0),
          13.5, kText, VSTGUI::kCenterText, VSTGUI::kBoldFace, 0.9,
          1.0, true, 0.8);
      setDirty(false);
      return;
    }
    draw_embossed_text(
        context, "SETTINGS",
        VSTGUI::CRect(bounds.left + 2.0, bounds.top, bounds.right - 2.0,
                      bounds.top + 19.0),
        chrome.control_caption_font_size, kCaption, VSTGUI::kLeftText,
        VSTGUI::kBoldFace, 0.9);
    VSTGUI::CRect button(bounds.left + 1.0, bounds.top + 23.0,
                         bounds.right - 1.0, bounds.bottom - 3.0);
    draw_beveled_button(context, button, kPanelBottom, 7.0, true);
    {
      const VSTGUI::CPoint center(button.left + 22.0,
                                  button.getCenter().y - 1.0);
      constexpr std::array<double, 8> kGearAngles{{
          0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0}};
      for (const double degrees : kGearAngles) {
        const double angle = degrees * VSTGUI::Constants::pi / 180.0;
        draw_rule(context,
                  VSTGUI::CPoint(center.x + 1.5 + std::cos(angle) * 7.0,
                                 center.y + 2.0 + std::sin(angle) * 7.0),
                  VSTGUI::CPoint(center.x + 1.5 + std::cos(angle) * 10.0,
                                 center.y + 2.0 + std::sin(angle) * 10.0),
                  VSTGUI::CColor(2U, 4U, 5U, 220U), 3.0);
        draw_rule(context,
                  VSTGUI::CPoint(center.x + std::cos(angle) * 7.0,
                                 center.y + std::sin(angle) * 7.0),
                  VSTGUI::CPoint(center.x + std::cos(angle) * 10.0,
                                 center.y + std::sin(angle) * 10.0),
                  kText, 2.5);
      }
      context->setFrameColor(kText);
      context->setLineWidth(2.5);
      context->drawEllipse(
          VSTGUI::CRect(center.x - 7.0, center.y - 7.0,
                        center.x + 7.0, center.y + 7.0),
          VSTGUI::kDrawStroked);
      context->drawEllipse(
          VSTGUI::CRect(center.x - 2.0, center.y - 2.0,
                        center.x + 2.0, center.y + 2.0),
          VSTGUI::kDrawFilled);
      draw_embossed_text(
          context, "SETTINGS",
          VSTGUI::CRect(bounds.left + 40.0, bounds.top + 22.0,
                        bounds.right - 6.0, bounds.bottom - 4.0),
          14.0, kText);
    }
    setDirty(false);
  }

  VSTGUI::CMouseEventResult onMouseDown(
      VSTGUI::CPoint&, const VSTGUI::CButtonState& buttons) override {
    if (!buttons.isLeftButton() || callback_ == nullptr) {
      return VSTGUI::kMouseEventNotHandled;
    }
    callback_(callback_context_);
    return VSTGUI::kMouseEventHandled;
  }

  void onKeyboardEvent(VSTGUI::KeyboardEvent& event) override {
    if (event.type == VSTGUI::EventType::KeyDown && callback_ != nullptr &&
        (event.virt == VSTGUI::VirtualKey::Space ||
         event.virt == VSTGUI::VirtualKey::Return ||
         event.virt == VSTGUI::VirtualKey::Enter)) {
      callback_(callback_context_);
      event.consumed = true;
    }
  }

 private:
  const bool& settings_open_;
  void* callback_context_{};
  ToggleCallback callback_{};

  CLASS_METHODS_NOCOPY(M3SettingsButton, VSTGUI::CControl)
};

class M3RootSurface final : public VSTGUI::CViewContainer {
 public:
  M3RootSurface(VSTGUI::IControlListener* listener,
                Steinberg::Vst::EditController& controller,
                const TunerTelemetry& tuner_telemetry)
      : VSTGUI::CViewContainer(
            VSTGUI::CRect(0.0, 0.0, kEditorWidth, kEditorHeight)),
        controller_(controller),
        tuner_telemetry_(tuner_telemetry) {
    setBackgroundColor(kGraphite);
    const PersistentConfig config{};
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      layouts_[index] = editor_control_layout(
          index, config, Status::ready, EditorSurfacePage::tuner);
      controls_[index] = new (std::nothrow) M3DeckControl(
          layouts_[index], listener, controller, EditorSurfacePage::tuner);
      if (controls_[index] != nullptr) {
        static_cast<void>(addView(controls_[index]));
      }
    }
    M3DeckControl* velocity_mode = control_for(kVelocityModeId);
    if (velocity_mode != nullptr) {
      velocity_mode->set_dependent_control(control_for(kFixedVelocityId));
    }
    settings_button_ = new (std::nothrow) M3SettingsButton(
        editor_settings_button_bounds(), settings_open_, this,
        &M3RootSurface::toggle_settings_callback);
    if (settings_button_ != nullptr) {
      static_cast<void>(addView(settings_button_));
    }
  }

  bool settings_open() const noexcept { return settings_open_; }

  bool toggle_settings() noexcept {
    settings_open_ = !settings_open_;
    const EditorSurfacePage page = settings_open_
                                       ? EditorSurfacePage::settings
                                       : EditorSurfacePage::tuner;
    PersistentConfig config{};
    config.velocity_mode =
        controller_.getParamNormalized(kVelocityModeId) >= 0.5
            ? VelocityMode::dynamic
            : VelocityMode::fixed;
    for (std::size_t index = 0; index < layouts_.size(); ++index) {
      layouts_[index] =
          editor_control_layout(index, config, Status::ready, page);
      if (controls_[index] != nullptr) {
        controls_[index]->set_layout(layouts_[index], page);
      }
    }
    relayout_controls();
    if (settings_button_ != nullptr) {
      settings_button_->invalid();
    }
    invalid();
    return true;
  }

  bool refresh_tuner() noexcept {
    TunerSnapshot snapshot;
    bool changed = false;
    if (tuner_telemetry_.read_latest(snapshot) &&
        (!has_tuner_snapshot_ ||
         snapshot.generation != tuner_snapshot_.generation)) {
      tuner_snapshot_ = snapshot;
      has_tuner_snapshot_ = true;
      changed = true;
      const bool tracking = snapshot.state == TunerFrameState::tracking;
      for (std::size_t index = 0U; index < kMaxVoices; ++index) {
        const bool active = tracking && index < snapshot.voice_count &&
                            snapshot.voices[index].cents_valid;
        if (!active) {
          needle_active_[index] = false;
          continue;
        }
        const TunerVoice& voice = snapshot.voices[index];
        needle_targets_[index] = std::clamp(
            static_cast<double>(voice.cents_q8) / 256.0, -50.0, 50.0);
        if (!needle_active_[index] || needle_notes_[index] != voice.midi_note) {
          needle_positions_[index] = needle_targets_[index];
        }
        needle_notes_[index] = voice.midi_note;
        needle_active_[index] = true;
      }
    }

    for (std::size_t index = 0U; index < kMaxVoices; ++index) {
      if (!needle_active_[index]) {
        continue;
      }
      const double next = advance_tuner_needle(
          needle_positions_[index], needle_targets_[index], 1.0 / 60.0);
      if (next != needle_positions_[index]) {
        needle_positions_[index] = next;
        changed = true;
      }
    }
    if (!changed) {
      return false;
    }
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

  bool control_visible(ParameterId parameter_id) const noexcept {
    const M3DeckControl* control = control_for(parameter_id);
    return control != nullptr && control->isVisible();
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
    prepare_crisp_drawing(context);
    const VSTGUI::CRect bounds = getViewSize();
    draw_chassis(context, bounds);
    draw_input_activity(context);
    if (settings_open_) {
      draw_settings_panel(context);
    } else {
      draw_tuner_panel(context);
    }
    if (!settings_open_) {
      draw_rule(context,
                scaled_rect(18.0, 344.0, 1006.0, 344.0).getTopLeft(),
                scaled_rect(18.0, 344.0, 1006.0, 344.0).getTopRight(),
                kPanelEdge, 1.0);
      draw_rule(context,
                scaled_rect(18.0, 442.0, 1006.0, 442.0).getTopLeft(),
                scaled_rect(18.0, 442.0, 1006.0, 442.0).getTopRight(),
                kPanelEdgeSoft, 1.0);
    }
  }

 private:
  static void toggle_settings_callback(void* context) noexcept {
    if (context != nullptr) {
      static_cast<void>(
          static_cast<M3RootSurface*>(context)->toggle_settings());
    }
  }

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
    static_cast<void>(max_polyphony);
    char* const end = text + sizeof(text);
    char* cursor = append_unsigned(text, end, voice_count);
    cursor = append_literal(cursor, end, " NOTES  •  LIVE");
    terminate_text(cursor, end);
  }

  void draw_chassis(VSTGUI::CDrawContext* context,
                    const VSTGUI::CRect& bounds) const {
    constexpr EditorChromeMetrics chrome = editor_chrome_metrics();
    fill_material_surface(context, bounds,
                          VSTGUI::CColor(45U, 56U, 61U, 255U),
                          VSTGUI::CColor(28U, 39U, 45U, 255U),
                          VSTGUI::CColor(18U, 27U, 31U, 255U), 0.0);
    overlay_edge_vignette(context, bounds, 0.0,
                          chrome.chassis_vignette_alpha);

    const VSTGUI::CRect header = scaled_rect(16.0, 16.0, 1008.0, 101.0);
    draw_beveled_panel(context, header, 10.0, chrome.surface_shadow_offset);

    if (!settings_open_) {
      const VSTGUI::CRect control_rail =
          scaled_rect(16.0, 342.0, 1008.0, 446.0);
      fill_material_surface(context, control_rail,
                            VSTGUI::CColor(34U, 45U, 50U, 255U),
                            VSTGUI::CColor(23U, 33U, 38U, 255U),
                            VSTGUI::CColor(12U, 20U, 24U, 255U), 0.0);
      overlay_edge_vignette(context, control_rail, 0.0,
                            chrome.chassis_vignette_alpha);
      draw_rule(context,
                scaled_rect(18.0, 343.0, 1006.0, 343.0).getTopLeft(),
                scaled_rect(18.0, 343.0, 1006.0, 343.0).getTopRight(),
                VSTGUI::CColor(151U, 164U, 166U, 155U), 1.0);
      draw_rule(context,
                scaled_rect(18.0, 440.0, 1006.0, 440.0).getTopLeft(),
                scaled_rect(18.0, 440.0, 1006.0, 440.0).getTopRight(),
                VSTGUI::CColor(111U, 124U, 127U, 120U), 1.0);
      constexpr std::array<double, 7> kDividers{
          {156.0, 284.0, 400.0, 530.0, 654.0, 754.0, 872.0}};
      for (double x : kDividers) {
        const VSTGUI::CRect divider = scaled_rect(x, 351.0, x, 432.0);
        draw_rule(context, divider.getTopLeft(), divider.getBottomLeft(),
                  VSTGUI::CColor(151U, 161U, 160U, 125U), 1.0);
      }
    }
  }

  void draw_input_activity(VSTGUI::CDrawContext* context) const {
    const VSTGUI::CRect area = scaled_rect(552.0, 16.0, 856.0, 100.0);
    draw_rule(context, VSTGUI::CPoint(area.left, area.top + 18.0),
              VSTGUI::CPoint(area.left, area.bottom - 9.0), kPanelEdge, 1.0);
    draw_embossed_text(
        context, "INPUT",
        VSTGUI::CRect(area.left + 18.0, area.top + 13.0,
                      area.right - 4.0, area.top + 33.0),
        12.0, kCaption, VSTGUI::kLeftText, VSTGUI::kBoldFace, 1.0);
    std::uint16_t confidence = 0U;
    if (has_tuner_snapshot_ &&
        tuner_snapshot_.state == TunerFrameState::tracking) {
      for (std::size_t index = 0U; index < tuner_snapshot_.voice_count;
           ++index) {
        confidence = std::max(confidence,
                              tuner_snapshot_.voices[index].confidence_q15);
      }
    }
    constexpr std::size_t kBars = editor_input_meter_bar_count();
    const std::size_t lit = static_cast<std::size_t>(std::lround(
        static_cast<double>(confidence) * kBars / 32767.0));
    const double left = area.left + 18.0;
    const double width = (area.getWidth() - 38.0) / kBars;
    for (std::size_t index = 0U; index < kBars; ++index) {
      const double bar_index = static_cast<double>(index);
      const VSTGUI::CRect bar(left + width * bar_index, area.top + 35.0,
                              left + width * bar_index + width - 2.5,
                              area.bottom - 25.0);
      VSTGUI::CRect bar_shadow = bar;
      bar_shadow.offset(1.0, 2.0);
      context->setFillColor(VSTGUI::CColor(2U, 5U, 7U, 210U));
      context->drawRect(bar_shadow, VSTGUI::kDrawFilled);
      if (index < lit) {
        VSTGUI::CRect halo = bar;
        halo.extend(1.5, 1.5);
        context->setFillColor(
            VSTGUI::CColor(kCyan.red, kCyan.green, kCyan.blue, 42U));
        context->drawRect(halo, VSTGUI::kDrawFilled);
      }
      context->setFillColor(index < lit ? kCyan
                                        : VSTGUI::CColor(63U, 74U, 78U, 255U));
      context->drawRect(bar, VSTGUI::kDrawFilled);
      if (index < lit) {
        draw_rule(context, VSTGUI::CPoint(bar.left, bar.top),
                  VSTGUI::CPoint(bar.right, bar.top), kAmber, 1.0);
      }
    }
    draw_embossed_text(
        context, "-60",
        VSTGUI::CRect(area.left + 18.0, area.bottom - 24.0,
                      area.left + 62.0, area.bottom - 2.0),
        10.0, kCaption, VSTGUI::kLeftText, VSTGUI::kNormalFace, 0.8);
    draw_embossed_text(
        context, "-12",
        VSTGUI::CRect(area.right - 88.0, area.bottom - 24.0,
                      area.right - 45.0, area.bottom - 2.0),
        10.0, kCaption, VSTGUI::kCenterText, VSTGUI::kNormalFace, 0.8);
    draw_embossed_text(
        context, "0 dB",
        VSTGUI::CRect(area.right - 48.0, area.bottom - 24.0,
                      area.right - 2.0, area.bottom - 2.0),
        10.0, kCaption, VSTGUI::kRightText, VSTGUI::kNormalFace, 0.8);
  }

  void draw_settings_panel(VSTGUI::CDrawContext* context) const {
    const EditorRect raw = editor_settings_panel_bounds();
    const VSTGUI::CRect panel =
        scaled_rect(raw.left, raw.top, raw.right, raw.bottom);
    VSTGUI::CRect shadow = panel;
    shadow.offset(0.0, 5.0);
    draw_filled_rounded_surface(context, shadow,
                                VSTGUI::CColor(3U, 6U, 8U, 225U), 7.0);
    fill_material_surface(context, panel,
                          VSTGUI::CColor(41U, 51U, 55U, 255U),
                          VSTGUI::CColor(24U, 34U, 38U, 255U),
                          VSTGUI::CColor(12U, 20U, 23U, 255U), 7.0);
    overlay_edge_vignette(context, panel, 7.0, 26U);
    auto outline = VSTGUI::owned(context->createGraphicsPath());
    if (outline) {
      outline->addRoundRect(panel, 7.0);
      context->setFrameColor(VSTGUI::CColor(126U, 139U, 141U, 210U));
      context->setLineWidth(1.0);
      context->drawGraphicsPath(outline, VSTGUI::CDrawContext::kPathStroked);
    }
    draw_embossed_text(context, "SETTINGS",
                       scaled_rect(32.0, 115.0, 174.0, 145.0),
                       18.0, kText, VSTGUI::kLeftText,
                       VSTGUI::kBoldFace, 1.0, 1.0, true, 1.2);
    draw_embossed_text(context, "ALL PARAMETERS",
                       scaled_rect(180.0, 117.0, 360.0, 143.0),
                       11.5, kCaption, VSTGUI::kLeftText,
                       VSTGUI::kNormalFace, 0.8, 1.0, true, 0.8);
    draw_embossed_text(context, "PERFORMANCE CONFIGURATION",
                       scaled_rect(580.0, 117.0, 858.0, 143.0),
                       10.5, kMuted, VSTGUI::kRightText,
                       VSTGUI::kNormalFace, 0.7, 1.0, true, 0.55);
    draw_rule(context, scaled_rect(28.0, 151.0, 996.0, 151.0).getTopLeft(),
              scaled_rect(28.0, 151.0, 996.0, 151.0).getTopRight(),
              VSTGUI::CColor(151U, 164U, 166U, 115U), 1.0);
    draw_rule(context, scaled_rect(28.0, 286.0, 996.0, 286.0).getTopLeft(),
              scaled_rect(28.0, 286.0, 996.0, 286.0).getTopRight(),
              VSTGUI::CColor(126U, 139U, 141U, 70U), 1.0);
  }

  void draw_tuner_panel(VSTGUI::CDrawContext* context) const {
    const EditorRect raw = editor_tuner_display_bounds();
    VSTGUI::CRect panel =
        scaled_rect(raw.left, raw.top, raw.right, raw.bottom);
    VSTGUI::CRect deep_shadow = panel;
    deep_shadow.offset(0.0, 7.0);
    draw_rounded_surface(context, deep_shadow,
                         VSTGUI::CColor(3U, 6U, 8U, 235U),
                         VSTGUI::CColor(3U, 6U, 8U, 255U), 14.0, 2.0);
    draw_rounded_surface(context, panel, VSTGUI::CColor(5U, 9U, 11U, 255U),
                         kPanelEdge, 14.0, 2.0);
    draw_static_glow_outline(context, panel, kPanelEdge, 14.0);
    VSTGUI::CRect bezel = panel;
    bezel.inset(6.0, 6.0);
    draw_rounded_surface(context, bezel, VSTGUI::CColor(27U, 32U, 31U, 255U),
                         VSTGUI::CColor(4U, 7U, 8U, 255U), 10.0, 2.0);
    VSTGUI::CRect ivory = bezel;
    ivory.inset(4.0, 4.0);
    draw_rounded_surface(context, ivory, kIvory, kIvoryShade, 7.0, 1.0);
    VSTGUI::CRect highlight = ivory;
    highlight.bottom = highlight.top + 3.0;
    context->setFillColor(kIvoryHighlight);
    context->drawRect(highlight, VSTGUI::kDrawFilled);
    draw_tuner(context, ivory);
  }

  void draw_tuner_lane(VSTGUI::CDrawContext* context,
                       const VSTGUI::CRect& lane,
                       const TunerVoice* voice,
                       double displayed_cents,
                       bool needle_active) const {
    if (context == nullptr) {
      return;
    }
    const bool tracking = voice != nullptr &&
                          voice->state == TunerVoiceState::tracking;
    const bool cents_valid = tracking && voice->cents_valid && needle_active;
    const bool in_tune = cents_valid && std::abs(displayed_cents) <= 2.0;
    const VSTGUI::CColor needle_color = in_tune ? kInTuneBlue : kCyan;

    draw_label(context, "-50",
               VSTGUI::CRect(lane.left + 4.0, lane.top + 6.0,
                              lane.left + 40.0, lane.top + 26.0),
               kInk, VSTGUI::kLeftText);
    draw_label(context, "0",
               VSTGUI::CRect(lane.getCenter().x - 14.0, lane.top - 2.0,
                              lane.getCenter().x + 14.0, lane.top + 22.0),
               kInk);
    draw_label(context, "+50",
               VSTGUI::CRect(lane.right - 40.0, lane.top + 6.0,
                              lane.right - 4.0, lane.top + 26.0),
               kInk, VSTGUI::kRightText);

    const EditorRect lane_bounds{lane.left, lane.top, lane.right, lane.bottom};
    const VSTGUI::CRect arc =
        to_rect(editor_tuner_meter_arc_bounds(lane_bounds));
    VSTGUI::CRect arc_shadow = arc;
    arc_shadow.offset(1.5, 2.5);
    if (in_tune) {
      VSTGUI::CRect outer_glow = arc_shadow;
      outer_glow.offset(0.0, 2.0);
      constexpr float kOuterGlowStart = static_cast<float>(
          VSTGUI::Constants::pi * (220.0 / 180.0));
      constexpr float kOuterGlowEnd = static_cast<float>(
          VSTGUI::Constants::pi * (320.0 / 180.0));
      context->setFrameColor(VSTGUI::CColor(
          kInTuneBlueBloom.red, kInTuneBlueBloom.green,
          kInTuneBlueBloom.blue, 34U));
      context->setLineWidth(14.0);
      context->drawArc(outer_glow, kOuterGlowStart, kOuterGlowEnd,
                       VSTGUI::kDrawStroked);

      VSTGUI::CRect middle_glow = arc_shadow;
      middle_glow.offset(0.0, 1.35);
      constexpr float kMiddleGlowStart = static_cast<float>(
          VSTGUI::Constants::pi * (232.0 / 180.0));
      constexpr float kMiddleGlowEnd = static_cast<float>(
          VSTGUI::Constants::pi * (308.0 / 180.0));
      context->setFrameColor(VSTGUI::CColor(
          kInTuneBlue.red, kInTuneBlue.green, kInTuneBlue.blue, 58U));
      context->setLineWidth(8.0);
      context->drawArc(middle_glow, kMiddleGlowStart, kMiddleGlowEnd,
                       VSTGUI::kDrawStroked);

      VSTGUI::CRect inner_glow = arc_shadow;
      inner_glow.offset(0.0, 0.8);
      constexpr float kInnerGlowStart = static_cast<float>(
          VSTGUI::Constants::pi * (250.0 / 180.0));
      constexpr float kInnerGlowEnd = static_cast<float>(
          VSTGUI::Constants::pi * (290.0 / 180.0));
      context->setFrameColor(VSTGUI::CColor(
          kInTuneBlueHighlight.red, kInTuneBlueHighlight.green,
          kInTuneBlueHighlight.blue, 86U));
      context->setLineWidth(3.2);
      context->drawArc(inner_glow, kInnerGlowStart, kInnerGlowEnd,
                       VSTGUI::kDrawStroked);
    }
    context->setFrameColor(VSTGUI::CColor(58U, 51U, 41U, 118U));
    context->setLineWidth(5.5);
    constexpr float kArcStart =
        static_cast<float>(VSTGUI::Constants::pi);
    constexpr float kArcEnd =
        static_cast<float>(VSTGUI::Constants::pi * 2.0);
    context->drawArc(arc_shadow, kArcStart, kArcEnd,
                     VSTGUI::kDrawStroked);
    context->setFrameColor(kInk);
    context->setLineWidth(2.2);
    context->drawArc(arc, kArcStart, kArcEnd, VSTGUI::kDrawStroked);

    const VSTGUI::CPoint pivot = arc.getCenter();
    const double outer_x = arc.getWidth() * 0.5;
    const double outer_y = arc.getHeight() * 0.5;
    constexpr std::array<double, 5> kTickAngles{{200.0, 235.0, 270.0,
                                                 305.0, 340.0}};
    for (std::size_t index = 0U; index < kTickAngles.size(); ++index) {
      const double angle = kTickAngles[index] * VSTGUI::Constants::pi / 180.0;
      const double inner_x = outer_x - (index == 2U ? 12.0 : 8.0);
      const double inner_y = outer_y - (index == 2U ? 12.0 : 8.0);
      draw_rule(context,
                VSTGUI::CPoint(pivot.x + std::cos(angle) * inner_x,
                               pivot.y + std::sin(angle) * inner_y),
                VSTGUI::CPoint(pivot.x + std::cos(angle) * outer_x,
                               pivot.y + std::sin(angle) * outer_y),
                kInk, index == 2U ? 3.0 : 1.2);
    }

    if (cents_valid) {
      const double angle_degrees = 270.0 + displayed_cents * 1.4;
      const double angle = angle_degrees * VSTGUI::Constants::pi / 180.0;
      const VSTGUI::CPoint endpoint(
          pivot.x + std::cos(angle) * outer_x,
          pivot.y + std::sin(angle) * outer_y);
      draw_rule(context, VSTGUI::CPoint(pivot.x + 2.0, pivot.y + 2.5),
                VSTGUI::CPoint(endpoint.x + 2.0, endpoint.y + 2.5),
                VSTGUI::CColor(53U, 42U, 30U, 150U), 5.0);
      draw_rule(context, pivot, endpoint,
                VSTGUI::CColor(needle_color.red, needle_color.green,
                                 needle_color.blue, 38U),
                9.0);
      draw_rule(context, pivot, endpoint,
                VSTGUI::CColor(needle_color.red, needle_color.green,
                                 needle_color.blue, 94U),
                5.0);
      draw_rule(context, pivot, endpoint, needle_color, 3.2);
      if (in_tune) {
        const double length = std::hypot(endpoint.x - pivot.x,
                                         endpoint.y - pivot.y);
        const VSTGUI::CPoint highlight_offset(
            length > 0.0 ? (endpoint.y - pivot.y) * 0.55 / length : 0.0,
            length > 0.0 ? (pivot.x - endpoint.x) * 0.55 / length : 0.0);
        draw_rule(
            context,
            VSTGUI::CPoint(pivot.x + highlight_offset.x,
                           pivot.y + highlight_offset.y),
            VSTGUI::CPoint(endpoint.x + highlight_offset.x,
                           endpoint.y + highlight_offset.y),
            VSTGUI::CColor(kInTuneBlueHighlight.red,
                             kInTuneBlueHighlight.green,
                             kInTuneBlueHighlight.blue, 210U),
            1.0);
      }
      context->setFillColor(needle_color);
      context->drawEllipse(VSTGUI::CRect(pivot.x - 3.0, pivot.y - 3.0,
                                         pivot.x + 3.0, pivot.y + 3.0),
                           VSTGUI::kDrawFilled);
    }

    char note[8]{"--"};
    if (voice != nullptr) {
      format_note(*voice, note);
    }
    context->setFont(VSTGUI::kNormalFont, 36.0, VSTGUI::kBoldFace);
    context->setFontColor(kInk);
    context->drawString(note,
                        VSTGUI::CRect(lane.left + 4.0, pivot.y + 4.0,
                                     lane.right - 4.0, pivot.y + 50.0),
                        VSTGUI::kCenterText, true);

    char cents[12]{"--"};
    if (cents_valid) {
      const int rounded = std::clamp(
          static_cast<int>(std::lround(displayed_cents)), -50, 50);
      char* const end = cents + sizeof(cents);
      terminate_text(append_signed(cents, end, rounded, 1U), end);
    }
    context->setFont(VSTGUI::kNormalFont, 20.0, VSTGUI::kBoldFace);
    context->setFontColor(cents_valid && !in_tune ? kCyan : kInk);
    context->drawString(cents,
                        VSTGUI::CRect(lane.left + 4.0, pivot.y + 44.0,
                                     lane.right - 4.0, pivot.y + 72.0),
                        VSTGUI::kCenterText, true);
    draw_label(context, "cents",
               VSTGUI::CRect(lane.left + 4.0, pivot.y + 68.0,
                              lane.right - 4.0, pivot.y + 90.0),
               kInk);
  }

  void draw_tuner(VSTGUI::CDrawContext* context,
                  const VSTGUI::CRect& ivory) const {
    if (context == nullptr) {
      return;
    }
    context->setFont(VSTGUI::kNormalFont, 16.0, VSTGUI::kBoldFace);
    context->setFontColor(kInk);
    const bool tracking = has_tuner_snapshot_ &&
                          tuner_snapshot_.state == TunerFrameState::tracking &&
                          tuner_snapshot_.voice_count > 0U;
    if (tracking) {
      char header[32]{};
      format_voice_header(tuner_snapshot_.voice_count,
                          tuner_snapshot_.max_polyphony, header);
      context->setFontColor(kInk);
      context->setFont(VSTGUI::kNormalFont, 16.0, VSTGUI::kBoldFace);
      context->drawString(header,
                          VSTGUI::CRect(ivory.left + 18.0, ivory.top + 5.0,
                                       ivory.right - 18.0, ivory.top + 30.0),
                          VSTGUI::kLeftText, true);
    } else {
      context->setFont(VSTGUI::kNormalFontSmall);
      context->setFontColor(VSTGUI::CColor(89U, 82U, 68U, 255U));
      context->drawString(tuner_snapshot_.state == TunerFrameState::unavailable
                              ? "TUNER UNAVAILABLE"
                              : "NO VOICED ESTIMATES",
                          VSTGUI::CRect(ivory.left + 430.0, ivory.top + 13.0,
                                       ivory.right - 18.0, ivory.top + 40.0),
                          VSTGUI::kRightText, true);
    }
    const double lane_left = ivory.left + 8.0;
    const double lane_right = ivory.right - 8.0;
    const double lane_top = ivory.top + 32.0;
    const double lane_bottom = ivory.bottom - 5.0;
    const double lane_width = (lane_right - lane_left) / kMaxVoices;
    for (std::size_t index = 0U; index < kMaxVoices; ++index) {
      const double left = lane_left + static_cast<double>(index) * lane_width;
      const TunerVoice* voice =
          tracking && index < tuner_snapshot_.voice_count
              ? &tuner_snapshot_.voices[index]
              : nullptr;
      if (index > 0U) {
        draw_rule(context, VSTGUI::CPoint(left, lane_top + 1.0),
                  VSTGUI::CPoint(left, lane_bottom - 1.0),
                  VSTGUI::CColor(164U, 155U, 135U, 255U), 1.0);
      }
      draw_tuner_lane(
          context, VSTGUI::CRect(left, lane_top, left + lane_width, lane_bottom),
          voice, needle_positions_[index], needle_active_[index]);
    }
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
    if (settings_button_ != nullptr) {
      const EditorRect original = settings_open_
          ? editor_settings_done_button_bounds()
          : editor_settings_button_bounds();
      const VSTGUI::CRect resized = scaled_rect(
          original.left, original.top, original.right, original.bottom);
      settings_button_->setViewSize(resized);
      settings_button_->setMouseableArea(resized);
    }
  }

  std::array<EditorControlLayout, kEditorControlCount> layouts_{};
  std::array<M3DeckControl*, kEditorControlCount> controls_{};
  Steinberg::Vst::EditController& controller_;
  const TunerTelemetry& tuner_telemetry_;
  M3SettingsButton* settings_button_{};
  TunerSnapshot tuner_snapshot_{};
  std::array<double, kMaxVoices> needle_positions_{};
  std::array<double, kMaxVoices> needle_targets_{};
  std::array<std::uint8_t, kMaxVoices> needle_notes_{};
  std::array<bool, kMaxVoices> needle_active_{};
  bool has_tuner_snapshot_{};
  bool settings_open_{};
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

  std::size_t attach_refresh_count_for_test() const noexcept {
    return attach_refresh_count_;
  }
#endif

  Steinberg::tresult PLUGIN_API attached(
      void* parent, Steinberg::FIDString type) override {
    const Steinberg::tresult result =
        VSTGUI::VST3Editor::attached(parent, type);
    if (result_ok(result)) {
      // VSTGUI builds and invalidates the view before the native platform
      // frame is attached. Hosts such as REAPER can reuse the same plug-view
      // after showing their generic parameter UI, so that early invalidation
      // is not guaranteed to produce a fresh expose. Invalidate once more
      // after attachment to repaint the complete opaque editor surface.
      if (VSTGUI::CFrame* editor_frame = getFrame()) {
        editor_frame->invalid();
      }
#if defined(M3_TESTING)
      ++attach_refresh_count_;
#endif
    }
    return result;
  }

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
          16U, true);
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
#if defined(M3_TESTING)
  std::size_t attach_refresh_count_{};
#endif
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

bool editor_control_visible_for_test(Steinberg::IPlugView& view,
                                     ParameterId parameter_id) noexcept {
  auto* editor = static_cast<M3Editor*>(&view);
  return editor->surface() != nullptr &&
         editor->surface()->control_visible(parameter_id);
}

bool editor_settings_open_for_test(Steinberg::IPlugView& view) noexcept {
  auto* editor = static_cast<M3Editor*>(&view);
  return editor->surface() != nullptr && editor->surface()->settings_open();
}

bool editor_toggle_settings_for_test(Steinberg::IPlugView& view) noexcept {
  auto* editor = static_cast<M3Editor*>(&view);
  return editor->surface() != nullptr && editor->surface()->toggle_settings();
}

bool editor_render_rgba_for_test(Steinberg::IPlugView& view,
                                 std::uint8_t* rgba,
                                 std::size_t byte_count) noexcept {
  constexpr std::size_t width = static_cast<std::size_t>(kEditorWidth);
  constexpr std::size_t height = static_cast<std::size_t>(kEditorHeight);
  constexpr std::size_t required = width * height * 4U;
  auto* editor = static_cast<M3Editor*>(&view);
  M3RootSurface* surface = editor->surface();
  if (surface == nullptr || rgba == nullptr || byte_count != required) {
    return false;
  }
  const auto offscreen = VSTGUI::COffscreenContext::create(
      VSTGUI::CPoint(kEditorWidth, kEditorHeight));
  if (!offscreen) {
    return false;
  }
  offscreen->beginDraw();
  surface->draw(offscreen.get());
  offscreen->endDraw();
  const auto pixels = VSTGUI::owned(
      VSTGUI::CBitmapPixelAccess::create(offscreen->getBitmap(), false));
  if (!pixels || pixels->getBitmapWidth() != width ||
      pixels->getBitmapHeight() != height) {
    return false;
  }
  do {
    VSTGUI::CColor color;
    pixels->getColor(color);
    const std::size_t offset =
        (static_cast<std::size_t>(pixels->getY()) * width +
         static_cast<std::size_t>(pixels->getX())) *
        4U;
    rgba[offset] = color.red;
    rgba[offset + 1U] = color.green;
    rgba[offset + 2U] = color.blue;
    rgba[offset + 3U] = color.alpha;
  } while (++(*pixels));
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

std::size_t editor_attach_refresh_count_for_test(
    Steinberg::IPlugView& view) noexcept {
  return static_cast<M3Editor*>(&view)->attach_refresh_count_for_test();
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
