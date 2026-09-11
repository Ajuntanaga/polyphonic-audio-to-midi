#pragma once

#include <cstddef>
#include <cstdint>

#include "m3/parameter_contract.hpp"

namespace m3::vst3 {

enum class EditorPresentation : std::uint8_t {
  knob,
  segment,
  toggle,
  note_range,
  momentary,
  status,
};

struct EditorRect final {
  double left;
  double top;
  double right;
  double bottom;
};

struct EditorControlLayout final {
  ParameterId parameter_id;
  EditorPresentation presentation;
  EditorRect bounds;
  bool visible;
  bool enabled;
};

inline constexpr std::size_t kEditorControlCount = 16;
inline constexpr std::int32_t kEditorWidth = 1024;
inline constexpr std::int32_t kEditorHeight = 808;
inline constexpr std::int32_t kEditorMaximumWidth = 2048;
inline constexpr std::int32_t kEditorMaximumHeight = 1616;

EditorControlLayout editor_control_layout(std::size_t index,
                                          const PersistentConfig& config,
                                          Status status) noexcept;
const char* status_label(Status status) noexcept;
std::uint32_t status_color(Status status) noexcept;

}  // namespace m3::vst3
