#include "my_agent/ui/view.hpp"

#include <string_view>
#include <type_traits>
#include <variant>

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

Frame view(const Model& model, const UiState& ui, Size /*size*/)
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
    }

    if (const std::string status = status_line(model); !status.empty()) {
        frame.lines.push_back(StyledLine{.text = status});
    }

    // 输入行放最后：光标要落在这里。显示列折行与裁剪属于 Maya/后续输入编辑器，
    // view 只保留 UiState 里的完整文本。
    frame.lines.push_back(StyledLine{
        .text = std::string{kInputPrompt} + ui.input,
    });
    return frame;
}

}  // namespace my_agent::ui
