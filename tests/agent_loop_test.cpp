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
        thread.messages.size() == 1,
        "submit should append exactly one message"
    );

    check(
        thread.messages.front().role == my_agent::Role::User,
        "the appended message should belong to the user"
    );

    check(
        thread.messages.front().text == "ping",
        "the appended message should preserve its text"
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
