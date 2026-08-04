#pragma once

#include "my_agent/ui/input.hpp"

#include <cstddef>
#include <string>

namespace my_agent::ui {

struct InputEditorState {
    std::string buffer;
    std::size_t cursor{std::string::npos};
};

[[nodiscard]]
InputEditorState edit_input(
    std::string buffer,
    std::size_t cursor,
    const Key& key
);

}  // namespace my_agent::ui
