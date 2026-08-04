#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace my_agent::ui {

struct InputLayout {
    std::vector<std::string> lines;
    std::size_t cursor_line{0};
    int cursor_column{0};
};

[[nodiscard]]
InputLayout layout_input(
    std::string_view buffer,
    std::size_t cursor,
    int columns
);

}  // namespace my_agent::ui
