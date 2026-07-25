#include "my_agent/agent.hpp"

#include <cstdlib>
#include <iostream>
#include <string_view>
#include <variant>

namespace {

void check(bool condition, std::string_view description)
{
    if (!condition) {
        std::cerr << "FAIL: " << description << '\n';
        std::exit(EXIT_FAILURE);
    }
}

// 当一个外部世界提交一个消息过后，对应的状态应该发生改变，同时附属的不变量不能够被违反
void submit_from_idle_starts_streaming_turn()
{
    const my_agent::Step step = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    check(
        std::holds_alternative<my_agent::Streaming>(step.model.phase),
        "submit should enter Streaming"
    );

    const my_agent::Thread& thread = step.model.thread;

    check(
        thread.messages.size() == 2,
        "submit should append a input msg and an assistant placeholder"
    );

    check(
        thread.messages[0].role == my_agent::Role::User,
        "the appended message should belong to the user"
    );

    check(
        thread.messages[0].text == "ping",
        "the appended message should preserve its text"
    );

    // submit 被接受后，Core为本轮回复创建空的Assistant占位消息
    check(
        thread.messages[1].role == my_agent::Role::Assistant,
        "the second message should be an assistant placeholder"
    );

    // 占位消息初始为空，后续Provider反馈由Runtime转换为Msg
    // 再由 Core 通过 update() 追加文本
    check(
        thread.messages[1].text.empty(),
        "the assistant placeholder should start empty"
    );

    check(
        std::holds_alternative<my_agent::StartStream>(step.cmd),
        "submit should request a stream"
    );

    const my_agent::StartStream& command =
        std::get<my_agent::StartStream>(step.cmd);

    check(
        command.prompt == "ping",
        "the stream command should carry the submitted prompt"
    );
}

// 当一个runtime成功处理对应的StartStream事件并且重新产生一个StreamTextDelta的Msg之后
// 对应的Core被期望能够正确将该Msg中的内容append到message中并且返回NoCommand
void stream_text_delta_appends_to_assistant_placeholder(){
    const my_agent::Step submitted = my_agent::update(
        my_agent::Model{}, 
        my_agent::Msg{
            my_agent::Submit{
                .text="ping",
            },
        }
    );

    // 模拟Runtime处理了这个 返回的step并且重新构造了一个消息返回给core
    const my_agent::Step streamed = my_agent::update(
        submitted.model, 
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "po",
            }
        }
    );

    check(
        std::holds_alternative<my_agent::Streaming>(streamed.model.phase),
        "text delta should keep the turn Streaming"
    );

    const my_agent::Thread& thread = streamed.model.thread;
    check(thread.messages.size()==2, 
        "text delta should not create another message");
        
    check(thread.messages[0].text=="ping", 
        "text delta should preserve the user message");

    const my_agent::Message& assistant = thread.messages[1];
    check(assistant.role==my_agent::Role::Assistant, 
        "Text delta should target the assistant placeholder");

    check(assistant.text=="po", 
        "text delta should append text to the assistant placeholder");
    
    check(std::holds_alternative<my_agent::NoCommand>(streamed.cmd),
    "text delta should not request an external effect");

    const my_agent::Step second_delta = my_agent::update(
        submitted.model,
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "ng",
            }
        }
    );

    check(
        second_delta.model.thread.messages[1].text=="pong", 
        "text deltas should accumulate in the assistant message"
    );

    check(thread.messages.size()==2, 
    "text delta should not create another message");
        
    check(thread.messages[0].text=="ping", 
    "text delta should preserve the user message");

    check(std::holds_alternative<my_agent::NoCommand>(second_delta.cmd),
    "text delta should append text to the assistant placeholder ");   
    // TODO: 如何标识一个流的结束，如何处理一个流中实际上可能隐藏了的工具调用请求等可能需要外部服务的
}

} // namespace

int main()
{
    submit_from_idle_starts_streaming_turn();
    std::cout<<"PASS: submit_from_idle_starts_streaming_turn\n";
    stream_text_delta_appends_to_assistant_placeholder();
    std::cout<<"PASS: stream_text_delta_appends_to_assistant_placeholder\n";

    return EXIT_SUCCESS;
}
