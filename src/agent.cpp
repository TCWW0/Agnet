#include "my_agent/agent.hpp"

#include <utility>
#include <variant>

namespace my_agent{
    namespace {
        /*
        * 对于一个apply函数，对应的期望是负责将被类型确定后的Msg往model其中的队列投递，并且保证对应model状态的正确转变
        */

        // 对于一个 Submit 类型的信息，对应的只需要将消息压到对应的队列中去并且更新一个流式传输状态即可
        Cmd apply(Model& model,const Submit& submit)
        {
            model.thread.messages.push_back(Message{
                .role = my_agent::Role::User,
                .text = submit.text,
            });
            model.thread.messages.push_back(Message{
                .role = my_agent::Role::Assistant,
                .text = {}
            });
            model.phase = Streaming{};
            // TODO: 做出更合适的上下文的包装，后续需要考虑这个暴露出去的事件应该如何来处理：是要一次性返回全部Prompt还是每次增量返回
            return StartStream{.prompt = submit.text};
        }

        Cmd apply(Model& model,const StreamTextDelta& delta)
        {
            my_agent::Thread& thread = model.thread;
            my_agent::Message& latest_msg = thread.messages.back();
            latest_msg.text += delta.text;
            return NoCommand{};
        }
    }

    // 对于update，其可能接受不同类型的msg，对应的 Msg 代表的多种类型其都已经被发配来进行处理
    Step update(Model model,Msg msg)
    {
        Cmd cmd = std::visit(
            [&model](const auto& event) -> Cmd{
                return apply(model,event);
            },
            msg
        );
        return Step{
            .model = std::move(model),
            .cmd = std::move(cmd),
        };
    }



}
