
#pragma once

#include "my_agent/provider/provider.hpp"
#include "my_agent/runtime/agent.hpp"
#include "my_agent/runtime/model.hpp"

#include <functional>
#include <memory>
#include <thread>
#include <vector>

namespace my_agent {

using WakeOwner = std::function<void()>;

class AsyncHost{
public:
    AsyncHost(StreamEffect stream, WakeOwner wake_owner);
    ~AsyncHost();

    AsyncHost(const AsyncHost&) = delete;
    AsyncHost& operator=(const AsyncHost&) = delete;
    AsyncHost(AsyncHost&&) = delete;
    AsyncHost& operator=(AsyncHost&&) = delete;

    // Owner-thread only. 用于接受用户输入、审批等 owner 侧操作
    void dispatch(Msg msg);

    // 交换出当前 Inbox 消息批次，并按 FIFO 顺序交给 Core
    void drain_inbox();

    [[nodiscard]]
    const Model& model() const noexcept;

private:
    struct InboxState;

    void process_msg(Msg msg);
    void execute_cmd(NoCommand cmd);
    void execute_cmd(StartStream cmd);
    void execute_cmd(RunTool cmd);

private:
    Model current_model_{};

    // StreamEffect 本身同步运行，但其运行在后台线程中
    StreamEffect stream_;

    std::shared_ptr<InboxState> inbox_;

    std::vector<std::jthread> workers_;
};

}  // namespace my_agent
