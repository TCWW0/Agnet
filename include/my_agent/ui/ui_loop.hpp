#pragma once

#include "my_agent/runtime/async_host.hpp"
#include "my_agent/runtime/model.hpp"
#include "my_agent/runtime/msg.hpp"
#include "my_agent/ui/input.hpp"
#include "my_agent/ui/terminal.hpp"
#include "my_agent/ui/view.hpp"

#include <functional>
#include <optional>

namespace my_agent::ui {

// 一次按键的结果。msg 有值表示这次按键跨越了前端与领域的边界 —— 绝大多数按键
// （编辑输入行）不会，这正是 UiState 不进 Model 的理由。
struct KeyOutcome {
    std::optional<Msg> msg;
    bool quit{false};
};

// 按键 -> UiState 变更 + 可选领域事件。纯：不碰终端、不碰 host。
// 需要 model 是因为同一个按键在不同 phase 下含义不同（AwaitingPermission 时
// 'y' 是批准而不是文本）。
[[nodiscard]]
KeyOutcome apply_key(const Key& key, UiState& ui, const Model& model);

// 事件循环。poll 在 {stdin, wake_fd} 上等，因此流式输出进行中也能读键盘 ——
// 这是 run_until_quiescent 做不到的（它在 phase 是 Streaming 时不返回）。
// 非 tty 时立即返回 false，调用方回退到行式 REPL。
bool run_ui(AsyncHost& host, TerminalDriver& terminal);

using StatusProvider = std::function<StatusBarInput()>;

bool run_ui(
    AsyncHost& host,
    TerminalDriver& terminal,
    StatusProvider status_provider
);

}  // namespace my_agent::ui
