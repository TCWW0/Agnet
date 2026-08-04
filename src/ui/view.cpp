#include "my_agent/ui/view.hpp"
#include "my_agent/ui/input_layout.hpp"
#include "my_agent/tool/tool.hpp"

#include <algorithm>
#include <cstddef>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>

namespace my_agent::ui {

namespace {

constexpr std::string_view kInputPrompt = "> ";
constexpr std::size_t kMaxToolOutputCharacters = 240;

// 说话人标记。纯文本终端里没有气泡也没有头像，行首这两个字符就是全部的区分手段。
// 都是 1 列宽的 ASCII，所以缩进对得齐；宽字符会让不同角色的正文起始列错开。
[[nodiscard]]
std::string_view speaker_prefix(Role role) noexcept
{
    return role == Role::User ? "> " : "* ";
}

[[nodiscard]]
const ToolCall* tool_call_for(const Model& model, const std::string& id)
{
    for (auto message = model.thread.messages.rbegin();
         message != model.thread.messages.rend();
         ++message) {
        for (auto call = message->tool_calls.rbegin();
             call != message->tool_calls.rend(); ++call) {
            if (call->id == id) {
                return &*call;
            }
        }
    }
    return nullptr;
}

[[nodiscard]]
std::string tool_name_for(const Model& model, const std::string& id)
{
    if (const ToolCall* call = tool_call_for(model, id)) {
        return call->name;
    }
    return id;
}

[[nodiscard]]
std::string effect_label(tool::EffectSet effects)
{
    std::string result;
    const auto append = [&result](std::string_view label) {
        if (!result.empty()) {
            result += ',';
        }
        result += label;
    };
    if (effects.has(tool::Effect::ReadFs)) {
        append("read_fs");
    }
    if (effects.has(tool::Effect::WriteFs)) {
        append("write_fs");
    }
    if (effects.has(tool::Effect::Net)) {
        append("net");
    }
    if (effects.has(tool::Effect::Exec)) {
        append("exec");
    }
    return result.empty() ? "none" : result;
}

[[nodiscard]]
std::size_t utf8_codepoint_count(std::string_view text) noexcept
{
    std::size_t count = 0;
    for (const unsigned char byte : text) {
        if ((byte & 0xc0u) != 0x80u) {
            ++count;
        }
    }
    return count;
}

[[nodiscard]]
std::string truncate_tool_output(std::string_view output)
{
    if (utf8_codepoint_count(output) <= kMaxToolOutputCharacters) {
        return std::string{output};
    }

    std::size_t visible_end = 0;
    std::size_t visible_characters = 0;
    while (visible_end < output.size()
           && visible_characters < kMaxToolOutputCharacters) {
        const unsigned char byte = static_cast<unsigned char>(output[visible_end]);
        const std::size_t width = (byte & 0x80u) == 0
            ? 1
            : (byte & 0xe0u) == 0xc0
                ? 2
                : (byte & 0xf0u) == 0xe0 ? 3 : 4;
        if (visible_end + width > output.size()) {
            break;
        }
        visible_end += width;
        ++visible_characters;
    }

    const std::size_t elided = utf8_codepoint_count(output.substr(visible_end));
    return std::string{output.substr(0, visible_end)}
        + " [... " + std::to_string(elided) + " characters elided]";
}

struct ToolStatusPresentation {
    std::string_view label;
    StyleColor color;
};

[[nodiscard]]
ToolStatusPresentation tool_status(const ToolCall& call) noexcept
{
    return std::visit(
        [](const auto& status) noexcept -> ToolStatusPresentation {
            using T = std::decay_t<decltype(status)>;
            if constexpr (std::is_same_v<T, ToolCall::Pending>) {
                return {"pending", StyleColor::Warning};
            } else if constexpr (std::is_same_v<T, ToolCall::Done>) {
                return {"done", StyleColor::Success};
            } else if constexpr (std::is_same_v<T, ToolCall::Failed>) {
                return {"failed", StyleColor::Error};
            } else {
                return {"rejected", StyleColor::Secondary};
            }
        },
        call.status
    );
}

void append_tool_call(Frame& frame, const ToolCall& call)
{
    const ToolStatusPresentation presentation = tool_status(call);
    frame.lines.push_back(StyledLine{
        .text = "+-- tool_call [" + std::string{presentation.label} + "] "
            + call.name,
        .foreground = presentation.color,
        .bold = true,
    });
    frame.lines.push_back(StyledLine{
        .text = "| args: " + call.args.dump(),
        .foreground = StyleColor::Muted,
        .dim = true,
    });
    if (!call.is_pending()) {
        const std::string output = call.output().empty()
            ? "(empty)"
            : truncate_tool_output(call.output());
        frame.lines.push_back(StyledLine{
            .text = "| output: " + output,
            .foreground = presentation.color,
        });
    }
    frame.lines.push_back(StyledLine{
        .text = "+--",
        .foreground = presentation.color,
    });
}

// 忙碌提示。Idle 返回空串表示「这一帧不需要状态行」—— 空闲时占一行反而是噪声。
// 提示必须不依赖已到达的文本：第一个 token 到达之前它就得在屏幕上，
// 否则用户分不清模型在想还是进程卡死了。
[[nodiscard]]
std::string status_line(const Model& model)
{
    return std::visit(
        [&model](const auto& value) -> std::string {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, Streaming>) {
                return "... thinking";
            } else if constexpr (std::is_same_v<T, ExecutingTool>) {
                return "... running " + tool_name_for(model, value.id);
            } else if constexpr (std::is_same_v<T, AwaitingPermission>) {
                if (!model.pending_permission) {
                    return "allow tool? [y/n]";
                }
                const ToolCall* call = tool_call_for(
                    model, model.pending_permission->id
                );
                const std::string name = call
                    ? call->name
                    : model.pending_permission->id;
                const tool::ToolDef* definition = tool::find(name);
                const tool::EffectSet effects = definition
                    ? definition->effects
                    : tool::EffectSet{};
                const std::string args = call ? call->args.dump() : "{}";
                return "allow " + name
                    + "? effect=" + effect_label(effects)
                    + " args: " + args + " [y/n]";
            } else {
                return {};
            }
        },
        model.phase
    );
}

}  // namespace

Frame view(const Model& model, const UiState& ui, Size size)
{
    Frame frame;
    for (const Message& message : model.thread.messages) {
        const std::string_view prefix = speaker_prefix(message.role);
        if (!message.text.empty()) {
            frame.lines.push_back(StyledLine{
                .text = std::string{prefix} + message.text,
            });
        }

        // 失败必须看得见。StreamError 把 phase 打回 Idle 并写下 error —— 状态行因此
        // 变空、正文可能一个字都没有，于是「回车之后什么都没发生」与卡死无从区分。
        // 跟在正文之后而不是替换它：流到一半才断的回合，已经吐出来的那半段仍然是
        // 用户要看的上下文。前缀用 ! 而不是 * —— 纯文本终端里行首那两个字符是唯一
        // 的区分手段，和正常回答同前缀会让人以为模型就是这么答的。
        if (message.error) {
            frame.lines.push_back(StyledLine{.text = "! " + *message.error});
        }
        for (const ToolCall& call : message.tool_calls) {
            append_tool_call(frame, call);
        }
    }

    if (const std::string status = status_line(model); !status.empty()) {
        frame.lines.push_back(StyledLine{.text = status});
    }

    const InputLayout input = layout_input(ui.input, ui.cursor, size.columns);
    for (const std::string& line : input.lines) {
        frame.lines.push_back(StyledLine{.text = line});
    }

    const int row_count = size.rows > 0 ? size.rows : 1;
    const std::size_t input_rows = input.lines.size();
    const std::size_t visible_input_rows = std::min<std::size_t>(
        input_rows, static_cast<std::size_t>(row_count)
    );
    const std::size_t first_visible_input_row = input_rows > visible_input_rows
        ? input_rows - visible_input_rows
        : 0;
    const std::size_t visible_cursor_line =
        input.cursor_line >= first_visible_input_row
        ? input.cursor_line - first_visible_input_row
        : 0;
    frame.cursor = CursorPosition{
        .row = row_count - static_cast<int>(visible_input_rows)
            + static_cast<int>(std::min<std::size_t>(
                visible_cursor_line, visible_input_rows - 1
            )),
        .column = input.cursor_column,
    };
    return frame;
}

}  // namespace my_agent::ui
