#pragma once

#include "my_agent/runtime/model.hpp"

#include <string>
#include <vector>

namespace my_agent::ui {

// 终端尺寸，单位是格（列 x 行）而不是像素。
struct Size {
    int columns{80};
    int rows{24};
};

// 只属于前端、不属于领域的瞬时状态。它不该进 Model：update() 不关心用户打了一半的
// 东西，只在提交时看到一条完整的 Submit。
struct UiState {
    std::string input;
};

// 一行待渲染文本。目前只有正文；颜色/加粗等属性等到有测试需要区分时再加，
// 类型名先把位置占住，免得届时改动所有调用点。
struct StyledLine {
    std::string text;
};

// 一整屏的内容。渲染层拿到它之后才去碰终端 —— Frame 本身不含任何转义序列。
struct Frame {
    std::vector<StyledLine> lines;
};

// Model 的投影。纯函数：不碰终端、不碰时钟、不碰文件，因此可以脱离 tty 单测。
[[nodiscard]]
Frame view(const Model& model, const UiState& ui, Size size);

}  // namespace my_agent::ui
