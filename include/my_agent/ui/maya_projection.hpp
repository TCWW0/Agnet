#pragma once

#include "my_agent/ui/view.hpp"

#include <maya/element/element.hpp>

namespace maya {
struct Theme;
}  // namespace maya

namespace my_agent::ui {

// Thin boundary between this project's pure view projection and Maya. All UI
// decisions stay in Frame/StyledLine; this layer only translates that IR into
// a Maya Element tree.
[[nodiscard]]
maya::Element to_maya_element(const Frame& frame, const maya::Theme& theme);

}  // namespace my_agent::ui
