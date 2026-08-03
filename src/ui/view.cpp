#include "my_agent/ui/view.hpp"

#include "my_agent/ui/text_width.hpp"

#include <string_view>
#include <type_traits>
#include <variant>
#include <vector>

namespace my_agent::ui {

namespace {

constexpr std::string_view kInputPrompt = "> ";

// 说话人标记。纯文本终端里没有气泡也没有头像，行首这两个字符就是全部的区分手段。
// 都是 1 列宽的 ASCII，所以缩进对得齐；宽字符会让不同角色的正文起始列错开。
[[nodiscard]]
std::string_view speaker_prefix(Role role) noexcept
{
    return role == Role::User ? "> " : "* ";
}

// 把 tool_call id 解析成工具名。Model 只在 PendingPermission / ExecutingTool 里存 id，
// 名字在历史消息的 tool_calls 里 —— 显示用的反查放在 view，Model 不为渲染冗余存一份。
// 从后往前找：待审批和在执行的调用总是最近那条 assistant 消息发起的。
// 找不到时退回 id 本身，宁可显示哈希串也不能显示空白。
[[nodiscard]]
std::string tool_name_for(const Model& model, const std::string& id)
{
    for (auto message = model.thread.messages.rbegin();
         message != model.thread.messages.rend();
         ++message) {
        for (const ToolCall& call : message->tool_calls) {
            if (call.id == id) {
                return call.name;
            }
        }
    }
    return id;
}

// 取末尾能放进 columns 列的那一段。往前找 UTF-8 字符边界（续字节高两位是 10），
// 逐个试更长的后缀，留最后一个还放得下的 —— 切在字符中间会吐出非法 UTF-8。
// 后缀宽度重复计算，是 O(n²)，但输入行只有几十个字符，不值得为它建索引。
[[nodiscard]]
std::string tail_within(std::string_view text, int columns)
{
    if (columns <= 0) {
        return {};
    }
    if (display_width(text) <= columns) {
        return std::string{text};
    }

    std::size_t best = text.size();  // 连最后一个字都放不下时返回空，而不是溢出
    for (std::size_t offset = text.size(); offset > 0; --offset) {
        if ((static_cast<unsigned char>(text[offset - 1]) & 0xC0) == 0x80) {
            continue;
        }
        if (display_width(text.substr(offset - 1)) > columns) {
            break;
        }
        best = offset - 1;
    }
    return std::string{text.substr(best)};
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
                const std::string name =
                    model.pending_permission
                        ? tool_name_for(model, model.pending_permission->id)
                        : std::string{"tool"};
                return "allow " + name + "? [y/n]";
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
        const int indent = static_cast<int>(prefix.size());  // 前缀全是 1 列宽 ASCII
        // 续行缩进到与首行正文同列，读起来才是一段而不是若干条消息。
        // 极窄终端下 columns - indent 可能 <= 0，wrap 对非正列宽返回空，
        // 于是那条消息一行都不出 —— 宁可不出，也不能吐出超宽行破坏行数契约。
        const std::vector<std::string> wrapped =
            wrap(message.text, size.columns - indent);

        bool first = true;
        for (const std::string& line : wrapped) {
            frame.lines.push_back(StyledLine{
                .text = (first ? std::string{prefix} : std::string(prefix.size(), ' '))
                        + line,
            });
            first = false;
        }

        // 失败必须看得见。StreamError 把 phase 打回 Idle 并写下 error —— 状态行因此
        // 变空、正文可能一个字都没有，于是「回车之后什么都没发生」与卡死无从区分。
        // 跟在正文之后而不是替换它：流到一半才断的回合，已经吐出来的那半段仍然是
        // 用户要看的上下文。前缀用 ! 而不是 * —— 纯文本终端里行首那两个字符是唯一
        // 的区分手段，和正常回答同前缀会让人以为模型就是这么答的。
        if (message.error) {
            const std::vector<std::string> wrapped_error =
                wrap("! " + *message.error, size.columns);
            for (const std::string& line : wrapped_error) {
                frame.lines.push_back(StyledLine{.text = line});
            }
        }
    }

    if (const std::string status = status_line(model); !status.empty()) {
        frame.lines.push_back(StyledLine{.text = status});
    }

    // 输入行放最后：光标要落在这里，而终端的光标定位是相对帧的行号算的。
    // 它必须恰好一行，所以超宽时横向滚动而不是折行 —— 折行会让下面所有行号偏移。
    frame.lines.push_back(StyledLine{
        .text = std::string{kInputPrompt}
                + tail_within(ui.input, size.columns - static_cast<int>(kInputPrompt.size())),
    });

    // 裁到 rows 行，保留尾部。溢出的行会被终端从顶部顶掉，那样 Frame 的行号
    // 和屏幕的物理行就对不上了；而尾部才是用户当下要看的（最新消息 + 状态行）。
    const std::size_t rows = size.rows > 0 ? static_cast<std::size_t>(size.rows) : 0;
    if (frame.lines.size() > rows) {
        frame.lines.erase(
            frame.lines.begin(),
            frame.lines.begin()
                + static_cast<std::ptrdiff_t>(frame.lines.size() - rows)
        );
    }
    return frame;
}

}  // namespace my_agent::ui
