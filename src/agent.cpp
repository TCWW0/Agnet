#include "my_agent/agent.hpp"

#include <utility>

namespace my_agent{
    Step update(Model model,Msg msg)
    {
        // 将本轮的消息进行一轮封装，作为一次提交加入到队列中去，同时启动流程
        const Submit& submit = std::get<Submit>(msg);
        model.thread.messages.push_back(
            Message{
                .role = Role::User,
                .text = submit.text,
            }
        );
        model.phase = Streaming{};

        // 接受用户提交后，预先创建本轮流式回复的 Assistant 占位消息
        model.thread.messages.push_back(
            Message{
                .role = Role::Assistant,
                .text = {},
            }
        );

        return Step{
            .model = std::move(model),
            .cmd = Cmd{
                StartStream{
                    .prompt = submit.text,
                }
            },
        };
    }
}
