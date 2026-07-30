#include "my_agent/runtime/agent.hpp"
#include "my_agent/runtime/headless_runner.hpp"

#include <cstddef>
#include <string>
#include <utility>
#include <variant>
#include <vector>

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

TEST(ToolLoopTest, ExecutesCalculatorToolAndContinuesToFinalAnswer)
{
    std::vector<my_agent::Request> received_requests;
    std::size_t provider_turn = 0;

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request request, my_agent::EventSink sink) {
            received_requests.push_back(std::move(request));

            if (provider_turn++ == 0) {
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "calculator-call-1",
                        .name = "calculator",
                        .args = nlohmann::json{
                            {"operation", "multiply"},
                            {"left", 6},
                            {"right", 7},
                        },
                    },
                });
            } else {
                sink(my_agent::Msg{
                    my_agent::StreamTextDelta{
                        .text = "The result is 42.",
                    },
                });
            }

            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::HeadlessRunner runner{std::move(fake_stream)};

    const my_agent::Model& model = runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "Calculate 6 * 7"},
    });

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));

    ASSERT_EQ(std::size_t{2}, received_requests.size());

    const my_agent::Request& initial_request = received_requests[0];
    ASSERT_EQ(std::size_t{1}, initial_request.tools.size());
    EXPECT_EQ("calculator", initial_request.tools[0].name);

    const my_agent::Request& continuation_request = received_requests[1];
    ASSERT_EQ(std::size_t{2}, continuation_request.messages.size());

    const my_agent::Message& tool_message =
        continuation_request.messages[1];
    EXPECT_EQ(my_agent::Role::Assistant, tool_message.role);
    ASSERT_EQ(std::size_t{1}, tool_message.tool_calls.size());
    EXPECT_EQ("calculator", tool_message.tool_calls[0].name);
    EXPECT_EQ("42", tool_message.tool_calls[0].output());

    const my_agent::Thread& thread = model.thread;
    ASSERT_EQ(std::size_t{3}, thread.messages.size());
    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("Calculate 6 * 7", thread.messages[0].text);

    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[1].role);
    ASSERT_EQ(std::size_t{1}, thread.messages[1].tool_calls.size());
    EXPECT_EQ("42", thread.messages[1].tool_calls[0].output());

    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[2].role);
    EXPECT_EQ("The result is 42.", thread.messages[2].text);
}

// M3 的同步调度契约：Core 每次只交付一个 RunTool。
// 进入 Maya 并发 Task 层后，应保留“整批终态后才能 continuation”的语义，
// 但不再要求 StreamFinished 后只能立即产生单个 RunTool。
TEST(ToolLoopTest, MultipleToolCallsRunInEmissionOrderBeforeStreamingContinues)
{
    const my_agent::Step submitted = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{.text = "Calculate 6 * 7 and 5 * 8"},
        }
    );

    const my_agent::Step first_call_received = my_agent::update(
        submitted.model,
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "calculator-call-1",
                .name = "calculator",
                .args = nlohmann::json{
                    {"operation", "multiply"},
                    {"left", 6},
                    {"right", 7},
                },
            },
        }
    );

    const my_agent::Step second_call_received = my_agent::update(
        first_call_received.model,
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "calculator-call-2",
                .name = "calculator",
                .args = nlohmann::json{
                    {"operation", "multiply"},
                    {"left", 5},
                    {"right", 8},
                },
            },
        }
    );

    const my_agent::Step stream_finished = my_agent::update(
        second_call_received.model,
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    // 这里之后真实运行可能不满足，因为存在并发
    const auto* run_first = std::get_if<my_agent::RunTool>(
        &stream_finished.cmd
    );
    ASSERT_NE(nullptr, run_first);
    EXPECT_EQ("calculator-call-1", run_first->id);

    const my_agent::Step first_call_completed = my_agent::update(
        stream_finished.model,
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "calculator-call-1",
                .result = my_agent::tool::ToolOutput{.text = "42"},
            },
        }
    );

    const auto* run_second = std::get_if<my_agent::RunTool>(
        &first_call_completed.cmd
    );
    ASSERT_NE(nullptr, run_second);
    EXPECT_EQ("calculator-call-2", run_second->id);

    const my_agent::Step second_call_completed = my_agent::update(
        first_call_completed.model,
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "calculator-call-2",
                .result = my_agent::tool::ToolOutput{.text = "40"},
            },
        }
    );

    const auto* continuation = std::get_if<my_agent::StartStream>(
        &second_call_completed.cmd
    );
    ASSERT_NE(nullptr, continuation);

    ASSERT_EQ(std::size_t{2}, continuation->request.messages.size());
    const my_agent::Message& tool_message =
        continuation->request.messages[1];
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());
    EXPECT_EQ("calculator-call-1", tool_message.tool_calls[0].id);
    EXPECT_EQ("42", tool_message.tool_calls[0].output());
    EXPECT_EQ("calculator-call-2", tool_message.tool_calls[1].id);
    EXPECT_EQ("40", tool_message.tool_calls[1].output());
}

TEST(ToolLoopTest, ContinuesWithLaterToolAfterEarlierToolFails)
{
    std::vector<my_agent::Request> received_requests;
    std::size_t provider_turn = 0;

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request request, my_agent::EventSink sink) {
            received_requests.push_back(std::move(request));

            if (provider_turn++ == 0) {
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "calculator-call-1",
                        .name = "calculator",
                        .args = nlohmann::json{
                            {"operation", "divide"},
                            {"left", 6},
                            {"right", 3},
                        },
                    },
                });
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "calculator-call-2",
                        .name = "calculator",
                        .args = nlohmann::json{
                            {"operation", "multiply"},
                            {"left", 5},
                            {"right", 8},
                        },
                    },
                });
            } else {
                sink(my_agent::Msg{
                    my_agent::StreamTextDelta{
                        .text = "The first calculation failed; "
                                "the second result is 40.",
                    },
                });
            }

            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::HeadlessRunner runner{std::move(fake_stream)};

    const my_agent::Model& model = runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "Divide 6 by 3 and multiply 5 by 8"},
    });

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_EQ(std::size_t{2}, received_requests.size());

    const my_agent::Request& continuation_request = received_requests[1];
    ASSERT_EQ(std::size_t{2}, continuation_request.messages.size());

    const my_agent::Message& tool_message =
        continuation_request.messages[1];
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& failed_call = tool_message.tool_calls[0];
    EXPECT_EQ("calculator-call-1", failed_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Failed>(
        failed_call.status
    ));
    EXPECT_EQ(
        "[invalid args] unsupported calculator operation: divide",
        failed_call.output()
    );

    const my_agent::ToolCall& successful_call = tool_message.tool_calls[1];
    EXPECT_EQ("calculator-call-2", successful_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Done>(
        successful_call.status
    ));
    EXPECT_EQ("40", successful_call.output());

    ASSERT_EQ(std::size_t{3}, model.thread.messages.size());
    EXPECT_EQ(
        "The first calculation failed; the second result is 40.",
        model.thread.messages[2].text
    );
}

TEST(ToolLoopTest, ContinuesStreamingWhenFinalToolInBatchFails)
{
    std::vector<my_agent::Request> received_requests;
    std::size_t provider_turn = 0;

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request request, my_agent::EventSink sink) {
            received_requests.push_back(std::move(request));

            if (provider_turn++ == 0) {
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "calculator-call-1",
                        .name = "calculator",
                        .args = nlohmann::json{
                            {"operation", "multiply"},
                            {"left", 6},
                            {"right", 7},
                        },
                    },
                });
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "calculator-call-2",
                        .name = "calculator",
                        .args = nlohmann::json{
                            {"operation", "divide"},
                            {"left", 8},
                            {"right", 2},
                        },
                    },
                });
            } else {
                sink(my_agent::Msg{
                    my_agent::StreamTextDelta{
                        .text = "The first result is 42; "
                                "the second calculation failed.",
                    },
                });
            }

            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::HeadlessRunner runner{std::move(fake_stream)};

    const my_agent::Model& model = runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "Multiply 6 by 7 and divide 8 by 2"},
    });

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_EQ(std::size_t{2}, received_requests.size());

    const my_agent::Request& continuation_request = received_requests[1];
    ASSERT_EQ(std::size_t{2}, continuation_request.messages.size());

    const my_agent::Message& tool_message =
        continuation_request.messages[1];
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& successful_call = tool_message.tool_calls[0];
    EXPECT_EQ("calculator-call-1", successful_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Done>(
        successful_call.status
    ));
    EXPECT_EQ("42", successful_call.output());

    const my_agent::ToolCall& failed_call = tool_message.tool_calls[1];
    EXPECT_EQ("calculator-call-2", failed_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Failed>(
        failed_call.status
    ));
    EXPECT_EQ(
        "[invalid args] unsupported calculator operation: divide",
        failed_call.output()
    );

    ASSERT_EQ(std::size_t{3}, model.thread.messages.size());
    EXPECT_EQ(
        "The first result is 42; the second calculation failed.",
        model.thread.messages[2].text
    );
}
