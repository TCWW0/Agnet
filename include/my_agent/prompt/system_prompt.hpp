#pragma once

#include <string>
#include <vector>

namespace my_agent::prompt {

// 构建系统提示所需的外部事实。宿主在 effect 侧采集它们（读环境、读文件），
// build() 本身保持纯 —— 这样提示的内容可以不碰文件系统直接断言。
struct Context {
    std::string working_directory;
    std::string operating_system;

    // M7 的注入点。memory 条目与 skill 目录都要读文件，所以由调用方填。
    std::vector<std::string> memories;
    std::string skills_catalog;
};

// 按 agentty 的风格分节：每个可变部分是一个 XML 标签块，模型容易定位，我们也
// 容易在不动静态基底的前提下增删某一节。
[[nodiscard]]
std::string build(const Context& context);

// 采集当前进程的环境事实。这是 build() 之外唯一碰 IO 的部分。
[[nodiscard]]
Context capture_environment();

}  // namespace my_agent::prompt
