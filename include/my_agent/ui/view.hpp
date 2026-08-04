#pragma once

#include "my_agent/runtime/model.hpp"
#include "my_agent/ui/markdown_scanner.hpp"
#include "my_agent/ui/status_bar.hpp"

#include <cstddef>
#include <optional>
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
    std::size_t cursor{std::string::npos};
    StatusBarInput status;
};

// 一行待渲染文本。样式字段属于自有中间表示；Maya 只在下一层机械转换时出现。
struct StyledLine {
    std::string text;
    StyleColor foreground{StyleColor::Default};
    StyleColor background{StyleColor::Default};
    bool bold{false};
    bool dim{false};
};

struct CursorPosition {
    int row{0};
    int column{0};
};

struct MarkdownLayer {
    std::size_t message_index{0};
    std::string committed_prefix;
    std::string active_tail;
};

struct MarkdownMessageState {
    std::string source;
    markdown::ScanState scanner;
    std::string committed_prefix;
    std::vector<StyledLine> committed_lines;
    std::size_t committed_prefix_parse_count{0};
};

struct MarkdownState {
    std::vector<MarkdownMessageState> messages;
};

// 一整屏的内容。渲染层拿到它之后才去碰终端 —— Frame 本身不含任何转义序列。
struct Frame {
    std::vector<StyledLine> lines;
    std::vector<MarkdownLayer> markdown_layers;
    std::optional<CursorPosition> cursor;
    std::optional<StatusBar> status_bar;
    std::optional<std::size_t> status_bar_line;
};

// Model 的投影。纯函数：不碰终端、不碰时钟、不碰文件，因此可以脱离 tty 单测。
[[nodiscard]]
Frame view(const Model& model, const UiState& ui, Size size);

[[nodiscard]]
Frame view(
    const Model& model,
    const UiState& ui,
    Size size,
    MarkdownState& markdown_state
);

}  // namespace my_agent::ui
