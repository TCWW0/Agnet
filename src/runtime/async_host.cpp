#include "my_agent/provider/provider.hpp"
#include "my_agent/runtime/async_host.hpp"
#include "my_agent/runtime/agent.hpp"
#include "my_agent/runtime/msg.hpp"
#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <variant>
#include <vector>

namespace my_agent{
    struct AsyncHost::InboxState{
        explicit InboxState(WakeOwner wake):wake_owner(std::move(wake))
        {
        }

        // 生产者(Worker Thread) 推送数据的接口，只在数据由0->1时进行通知
        void post(Msg msg)
        {
            bool should_wake = false;
            {
                std::lock_guard<std::mutex> lock{mutex};

                should_wake = messages.empty();
                messages.push_back(std::move(msg));
            }

            if (should_wake&&wake_owner){
                wake_owner();
            }
        }

        // 消费者"消费(取出)"数据的接口
        std::vector<Msg> drain()
        {
            std::vector<Msg> batch;
            {
                std::lock_guard<std::mutex> lock(mutex);
                batch.swap(messages);
            }
            return batch;
        }

        WakeOwner wake_owner;           // 生产者通知消费者的方式
        std::mutex mutex;
        std::vector<Msg> messages;

    };

    AsyncHost::AsyncHost(StreamEffect stream,WakeOwner wake_owner)
        :stream_(std::move(stream)),inbox_(std::make_shared<InboxState>(std::move(wake_owner)))
    {}

    AsyncHost::~AsyncHost() = default;

    const Model& AsyncHost::model() const noexcept
    {
        return current_model_;
    }

    void AsyncHost::dispatch(Msg msg)
    {
        process_msg(std::move(msg));
    }

    void AsyncHost::drain_inbox()
    {
        // 只交换一次稳定批次
        std::vector<Msg> batch = inbox_->drain();
        for(Msg& msg:batch){
            process_msg(std::move(msg));
        }
    }

    void AsyncHost::process_msg(Msg msg)
    {
        Step step = update(std::move(current_model_),std::move(msg));
        current_model_ = std::move(step.model);
        std::visit([this](auto&& command){execute_cmd(std::move(command));},std::move(step.cmd));
    }

    void AsyncHost::execute_cmd(NoCommand)
    {
    }

    void AsyncHost::execute_cmd(StartStream command)
    {
        StreamEffect stream = stream_;
        std::shared_ptr<InboxState> inbox = inbox_;

        workers_.emplace_back(
            [
                stream = std::move(stream),
                inbox = std::move(inbox),
                request = std::move(command.request)
            ]() mutable {
                EventSink sink = [inbox] (Msg msg){
                    inbox -> post(std::move(msg));
                };

                stream(std::move(request),std::move(sink));
            }
        );
    }

    void AsyncHost::execute_cmd(RunTool)
    {
        // TODO
        throw std::logic_error{
            "AsyncHost does not execute tools in M5 slice 1"
        };
    }
}
