#pragma once

#include "my_agent/tool/tool.hpp"

#include <filesystem>
#include <vector>

namespace my_agent::tool::detail {

// allowed_roots 把可读范围从 workspace 放宽到「workspace ∪ 这些根」。
// 存在的理由只有一个：skill 常装在 $HOME 下，完全在工作区之外，而 SKILL.md 正文
// 会引用同目录里的脚本和参考文件（Tier3）。不放宽，那些引用一读就被边界拒掉。
//
// **只放宽读。** 这个列表不参与任何写入判断 —— 一个装在 $HOME 的 skill 目录可读，
// 不意味着 agent 可以往那里写。
[[nodiscard]]
ToolDef make_read_tool(
    std::filesystem::path workspace_root,
    std::vector<std::filesystem::path> allowed_roots = {}
);

} // namespace my_agent::tool::detail
