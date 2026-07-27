#include "my_agent/headless_runner.hpp"
#include "my_agent/agent.hpp"

#include <cstddef>
#include <vector>
#include <utility>

namespace my_agent {

    HeadlessRunner::HeadlessRunner(StreamEffect stream)
        :stream_(std::move(stream))
    {
    }

    void HeadlessRunner::execute_cmd(NoCommand ){
    }

    void HeadlessRunner::execute_cmd(StartStream cmd){
        EventSink enqueue= [this](Msg msg){
            pending_msgs_.push_back(std::move(msg));
        };
        stream_(
            std::move(cmd),
            std::move(enqueue)
        );
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