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

} // namespace

int main()
{
    submit_from_idle_starts_streaming_turn();

    std::cout << "PASS: submit_from_idle_starts_streaming_turn\n";
    return EXIT_SUCCESS;
}
