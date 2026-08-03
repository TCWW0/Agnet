#pragma once

#include "my_agent/provider/provider.hpp"
#include "my_agent/runtime/agent.hpp"
#include "my_agent/runtime/model.hpp"
#include "my_agent/runtime/wake_signal.hpp"
#include "my_agent/tool/tool.hpp"

#include <chrono>
#include <functional>
#include <memory>
#include <string_view>
#include <stop_token>
#include <thread>
#include <vector>

namespace my_agent {

using ToolExecEffect = std::function<tool::ExecResult(std::string_view,const nlohmann::json&)>;

class AsyncHost{
public:
    explicit AsyncHost(StreamEffect stream);
    AsyncHost(StreamEffect stream, ToolExecEffect execute_tool);
    ~AsyncHost();

    AsyncHost(const AsyncHost&) = delete;
    AsyncHost& operator=(const AsyncHost&) = delete;
    AsyncHost(AsyncHost&&) = delete;
    AsyncHost& operator=(AsyncHost&&) = delete;

    // Owner-thread only. 用于接受用户输入、审批等 owner 侧操作
    void dispatch(Msg msg);

    // 交换出当前 Inbox 消息批次，并按 FIFO 顺序交给 Core
    void drain_inbox();

    // Owner-thread only. 阻塞事件循环：drain → 判定静止 → 等唤醒。
    // 在没有 in-flight worker 可等时返回，也就是 phase 已经是 Idle（回合结束）
    // 或 AwaitingPermission（等的是 owner 自己的审批输入）。
    void run_until_quiescent();

    // Owner-thread only. 测试用的唤醒观测 seam：等一次后台唤醒信号。
    [[nodiscard]]
    bool wait_wake(std::chrono::milliseconds timeout);

    void shutdown();

    [[nodiscard]]
    const Model& model() const noexcept;

private:
    struct InboxState;

    void process_msg(Msg msg);
    void execute_cmd(NoCommand cmd);
    void execute_cmd(StartStream cmd);
    void execute_cmd(RunTool cmd);

    [[nodiscard]]
    bool is_quiescent() const noexcept;

private:
    Model current_model_{};

    StreamEffect stream_;
    ToolExecEffect execute_tool_;

    // shared_ptr 而非成员对象：切片 3 的隔离通道会 detach 线程，那些线程可能
    // 活得比 host 久，共享所有权让它们不会对已析构的 WakeSignal 调 signal()。
    std::shared_ptr<WakeSignal> wake_;
    std::shared_ptr<InboxState> inbox_;

    std::stop_source stop_source_{};
    std::vector<std::jthread> workers_;
};

}  // namespace my_agent
