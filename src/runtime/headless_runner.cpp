#include "my_agent/runtime/headless_runner.hpp"

#include "my_agent/runtime/agent.hpp"
#include "my_agent/tool/tool.hpp"

#include <cassert>
#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace my_agent {
    namespace {
        bool has_pending_tool_calls(const Request& request) noexcept
        {
            for (const Message& message : request.messages) {
                for (const ToolCall& tool_call : message.tool_calls) {
                    if (tool_call.is_pending()) {
                        return true;
                    }
                }
            }
            return false;
        }
    }

    HeadlessRunner::HeadlessRunner(StreamEffect stream)
        :stream_(std::move(stream))
    {
    }

    void HeadlessRunner::execute_cmd(NoCommand ){
    }

    void HeadlessRunner::execute_cmd(StartStream cmd){
        const bool has_pending = has_pending_tool_calls(cmd.request);
        assert(!has_pending && "cannot start stream with pending tool calls");
        if (has_pending) {
            throw std::logic_error{
                "cannot start stream with pending tool calls"
            };
        }

        EventSink enqueue= [this](Msg msg){
            pending_msgs_.push_back(std::move(msg));
        };
        stream_(
            std::move(cmd.request),
            std::move(enqueue)
        );
    }

    void HeadlessRunner::execute_cmd(RunTool cmd){
        tool::ExecResult result = tool::execute(cmd.name,cmd.args);
        pending_msgs_.push_back(Msg{
            ToolExecOutput{
                .id = std::move(cmd.id),
                .result = std::move(result),
            },
        });
    }


    const Model& HeadlessRunner::dispatch(Msg msg)
    {
        pending_msgs_.push_back(std::move(msg));
        while (!pending_msgs_.empty()){
            // 注意维护pending队列的消息顺序，否则可能会出现一些
            auto msgs = std::move(pending_msgs_);
            pending_msgs_.clear();
            for (auto& msg:msgs)
            {
                auto next_step=update(std::move(current_model_),std::move(msg));
                current_model_ = std::move(next_step.model);
                std::visit(
                    [this](auto&& cmd){
                        execute_cmd(std::move(cmd));
                    },std::move(next_step.cmd)
                );
            }
        }
        return current_model_;
    }

} // namespace my_agent
