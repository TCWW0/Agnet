#pragma once

#include "my_agent/tool/tool.hpp"

#include <filesystem>

namespace my_agent::tool::detail {

[[nodiscard]]
ToolDef make_read_tool(std::filesystem::path workspace_root);

} // namespace my_agent::tool::detail
