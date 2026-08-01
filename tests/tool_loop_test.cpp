#include "my_agent/runtime/agent.hpp"
#include "my_agent/runtime/headless_runner.hpp"

#include <algorithm>
#include <cstddef>
#include <expected>
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
    const auto calculator = std::ranges::find_if(
        initial_request.tools,
        [](const my_agent::ToolSpec& tool) {
            return tool.name == "calculator";
        }
    );
    ASSERT_NE(initial_request.tools.end(), calculator);

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

TEST(ToolLoopTest, SerialToolSchedulingTracksCurrentlyExecutingCallId)
{
    my_agent::Step submitted = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{.text = "Calculate 6 * 7 and 5 * 8"},
        }
    );

    my_agent::Step first_call_received = my_agent::update(
        std::move(submitted.model),
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

    my_agent::Step second_call_received = my_agent::update(
        std::move(first_call_received.model),
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

    my_agent::Step first_call_started = my_agent::update(
        std::move(second_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    const auto* first_execution = std::get_if<my_agent::ExecutingTool>(
        &first_call_started.model.phase
    );
    ASSERT_NE(nullptr, first_execution);
    EXPECT_EQ("calculator-call-1", first_execution->id);

    const auto* run_first =
        std::get_if<my_agent::RunTool>(&first_call_started.cmd);
    ASSERT_NE(nullptr, run_first);
    EXPECT_EQ("calculator-call-1", run_first->id);

    const my_agent::Step second_call_started = my_agent::update(
        std::move(first_call_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "calculator-call-1",
                .result = my_agent::tool::ToolOutput{.text = "42"},
            },
        }
    );

    const auto* second_execution = std::get_if<my_agent::ExecutingTool>(
        &second_call_started.model.phase
    );
    ASSERT_NE(nullptr, second_execution);
    EXPECT_EQ("calculator-call-2", second_execution->id);

    const auto* run_second =
        std::get_if<my_agent::RunTool>(&second_call_started.cmd);
    ASSERT_NE(nullptr, run_second);
    EXPECT_EQ("calculator-call-2", run_second->id);
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

TEST(ToolLoopTest, MinimalProfilePausesReadToolForPermissionAfterStreamFinishes)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read CMakeLists.txt"},
        }
    );

    my_agent::Step tool_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    const my_agent::Step stream_finished = my_agent::update(
        std::move(tool_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
        stream_finished.model.phase
    ));
    ASSERT_TRUE(stream_finished.model.pending_permission.has_value());
    EXPECT_EQ(
        "read-call-1",
        stream_finished.model.pending_permission->id
    );
    EXPECT_TRUE(std::holds_alternative<my_agent::NoCommand>(
        stream_finished.cmd
    ));
}

TEST(ToolLoopTest, MatchingPermissionApprovalRunsToolAndEntersExecutingPhase)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read CMakeLists.txt"},
        }
    );

    my_agent::Step tool_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step awaiting_permission = my_agent::update(
        std::move(tool_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    const my_agent::Step approved = my_agent::update(
        std::move(awaiting_permission.model),
        my_agent::Msg{
            my_agent::PermissionApprove{.id = "read-call-1"},
        }
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::ExecutingTool>(
        approved.model.phase
    ));
    EXPECT_FALSE(approved.model.pending_permission.has_value());

    const auto* run_tool = std::get_if<my_agent::RunTool>(&approved.cmd);
    ASSERT_NE(nullptr, run_tool);
    EXPECT_EQ("read-call-1", run_tool->id);
    EXPECT_EQ("read", run_tool->name);
}

TEST(ToolLoopTest, PermissionPauseResumesMixedToolBatchInEmissionOrder)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read the project, then calculate 6 * 7"},
        }
    );

    my_agent::Step read_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step calculator_call_received = my_agent::update(
        std::move(read_call_received.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "calculator-call-2",
                .name = "calculator",
                .args = nlohmann::json{
                    {"operation", "multiply"},
                    {"left", 6},
                    {"right", 7},
                },
            },
        }
    );

    my_agent::Step awaiting_read_permission = my_agent::update(
        std::move(calculator_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
        awaiting_read_permission.model.phase
    ));
    ASSERT_TRUE(awaiting_read_permission.model.pending_permission.has_value());
    EXPECT_EQ(
        "read-call-1",
        awaiting_read_permission.model.pending_permission->id
    );

    my_agent::Step read_started = my_agent::update(
        std::move(awaiting_read_permission.model),
        my_agent::Msg{
            my_agent::PermissionApprove{.id = "read-call-1"},
        }
    );

    const auto* read_execution = std::get_if<my_agent::ExecutingTool>(
        &read_started.model.phase
    );
    ASSERT_NE(nullptr, read_execution);
    EXPECT_EQ("read-call-1", read_execution->id);

    const auto* run_read = std::get_if<my_agent::RunTool>(&read_started.cmd);
    ASSERT_NE(nullptr, run_read);
    EXPECT_EQ("read-call-1", run_read->id);

    my_agent::Step calculator_started = my_agent::update(
        std::move(read_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "read-call-1",
                .result = my_agent::tool::ToolOutput{
                    .text = "project contents",
                },
            },
        }
    );

    const auto* calculator_execution = std::get_if<my_agent::ExecutingTool>(
        &calculator_started.model.phase
    );
    ASSERT_NE(nullptr, calculator_execution);
    EXPECT_EQ("calculator-call-2", calculator_execution->id);

    const auto* run_calculator =
        std::get_if<my_agent::RunTool>(&calculator_started.cmd);
    ASSERT_NE(nullptr, run_calculator);
    EXPECT_EQ("calculator-call-2", run_calculator->id);

    const my_agent::Step batch_completed = my_agent::update(
        std::move(calculator_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "calculator-call-2",
                .result = my_agent::tool::ToolOutput{.text = "42"},
            },
        }
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(
        batch_completed.model.phase
    ));

    const auto* continuation =
        std::get_if<my_agent::StartStream>(&batch_completed.cmd);
    ASSERT_NE(nullptr, continuation);
    ASSERT_EQ(std::size_t{2}, continuation->request.messages.size());

    const my_agent::Message& tool_message =
        continuation->request.messages.back();
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& read_call = tool_message.tool_calls[0];
    EXPECT_EQ("read-call-1", read_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Done>(
        read_call.status
    ));
    EXPECT_EQ("project contents", read_call.output());

    const my_agent::ToolCall& calculator_call = tool_message.tool_calls[1];
    EXPECT_EQ("calculator-call-2", calculator_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Done>(
        calculator_call.status
    ));
    EXPECT_EQ("42", calculator_call.output());
}

TEST(ToolLoopTest, ApprovedToolFailureContinuesWithLaterToolInBatch)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read the project, then calculate 6 * 7"},
        }
    );

    my_agent::Step read_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step calculator_call_received = my_agent::update(
        std::move(read_call_received.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "calculator-call-2",
                .name = "calculator",
                .args = nlohmann::json{
                    {"operation", "multiply"},
                    {"left", 6},
                    {"right", 7},
                },
            },
        }
    );

    my_agent::Step awaiting_permission = my_agent::update(
        std::move(calculator_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    my_agent::Step read_started = my_agent::update(
        std::move(awaiting_permission.model),
        my_agent::Msg{
            my_agent::PermissionApprove{.id = "read-call-1"},
        }
    );

    my_agent::Step calculator_started = my_agent::update(
        std::move(read_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "read-call-1",
                .result = std::unexpected(my_agent::tool::ToolError{
                    .kind = my_agent::tool::ErrorKind::NotFound,
                    .message = "read could not open requested file",
                }),
            },
        }
    );

    const auto* calculator_execution = std::get_if<my_agent::ExecutingTool>(
        &calculator_started.model.phase
    );
    ASSERT_NE(nullptr, calculator_execution);
    EXPECT_EQ("calculator-call-2", calculator_execution->id);

    const auto* run_calculator =
        std::get_if<my_agent::RunTool>(&calculator_started.cmd);
    ASSERT_NE(nullptr, run_calculator);
    EXPECT_EQ("calculator-call-2", run_calculator->id);

    const my_agent::Step batch_completed = my_agent::update(
        std::move(calculator_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "calculator-call-2",
                .result = my_agent::tool::ToolOutput{.text = "42"},
            },
        }
    );

    const auto* continuation =
        std::get_if<my_agent::StartStream>(&batch_completed.cmd);
    ASSERT_NE(nullptr, continuation);
    ASSERT_EQ(std::size_t{2}, continuation->request.messages.size());

    const my_agent::Message& tool_message =
        continuation->request.messages.back();
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& failed_read = tool_message.tool_calls[0];
    EXPECT_EQ("read-call-1", failed_read.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Failed>(
        failed_read.status
    ));
    EXPECT_EQ(
        "[not found] read could not open requested file",
        failed_read.output()
    );

    const my_agent::ToolCall& successful_calculation =
        tool_message.tool_calls[1];
    EXPECT_EQ("calculator-call-2", successful_calculation.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Done>(
        successful_calculation.status
    ));
    EXPECT_EQ("42", successful_calculation.output());
}

TEST(ToolLoopTest, ProfileChangeKeepsCurrentPermissionAndAppliesToLaterTool)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read two project files"},
        }
    );

    my_agent::Step first_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step second_call_received = my_agent::update(
        std::move(first_call_received.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-2",
                .name = "read",
                .args = nlohmann::json{
                    {"path", "include/my_agent/runtime/agent.hpp"},
                },
            },
        }
    );

    my_agent::Step awaiting_first_permission = my_agent::update(
        std::move(second_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    ASSERT_TRUE(awaiting_first_permission.model.pending_permission.has_value());
    EXPECT_EQ(
        "read-call-1",
        awaiting_first_permission.model.pending_permission->id
    );

    my_agent::Step profile_changed = my_agent::update(
        std::move(awaiting_first_permission.model),
        my_agent::Msg{
            my_agent::SetProfile{.profile = my_agent::Profile::Write},
        }
    );

    EXPECT_EQ(my_agent::Profile::Write, profile_changed.model.profile);
    EXPECT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
        profile_changed.model.phase
    ));
    ASSERT_TRUE(profile_changed.model.pending_permission.has_value());
    EXPECT_EQ("read-call-1", profile_changed.model.pending_permission->id);
    EXPECT_TRUE(std::holds_alternative<my_agent::NoCommand>(
        profile_changed.cmd
    ));

    my_agent::Step first_call_started = my_agent::update(
        std::move(profile_changed.model),
        my_agent::Msg{
            my_agent::PermissionApprove{.id = "read-call-1"},
        }
    );

    const auto* first_execution = std::get_if<my_agent::ExecutingTool>(
        &first_call_started.model.phase
    );
    ASSERT_NE(nullptr, first_execution);
    EXPECT_EQ("read-call-1", first_execution->id);

    const auto* run_first =
        std::get_if<my_agent::RunTool>(&first_call_started.cmd);
    ASSERT_NE(nullptr, run_first);
    EXPECT_EQ("read-call-1", run_first->id);

    const my_agent::Step second_call_started = my_agent::update(
        std::move(first_call_started.model),
        my_agent::Msg{
            my_agent::ToolExecOutput{
                .id = "read-call-1",
                .result = my_agent::tool::ToolOutput{
                    .text = "project contents",
                },
            },
        }
    );

    EXPECT_FALSE(second_call_started.model.pending_permission.has_value());

    const auto* second_execution = std::get_if<my_agent::ExecutingTool>(
        &second_call_started.model.phase
    );
    ASSERT_NE(nullptr, second_execution);
    EXPECT_EQ("read-call-2", second_execution->id);

    const auto* run_second =
        std::get_if<my_agent::RunTool>(&second_call_started.cmd);
    ASSERT_NE(nullptr, run_second);
    EXPECT_EQ("read-call-2", run_second->id);
}

TEST(ToolLoopTest, LateStreamFinishedDoesNotRedispatchApprovedTool)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read CMakeLists.txt"},
        }
    );

    my_agent::Step tool_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step awaiting_permission = my_agent::update(
        std::move(tool_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    my_agent::Step approved = my_agent::update(
        std::move(awaiting_permission.model),
        my_agent::Msg{
            my_agent::PermissionApprove{.id = "read-call-1"},
        }
    );

    const my_agent::Step late_stream_finished = my_agent::update(
        std::move(approved.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::ExecutingTool>(
        late_stream_finished.model.phase
    ));
    EXPECT_FALSE(late_stream_finished.model.pending_permission.has_value());
    EXPECT_TRUE(std::holds_alternative<my_agent::NoCommand>(
        late_stream_finished.cmd
    ));
}

TEST(ToolLoopTest, RejectingFirstPermissionAdvancesToNextPendingPermission)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read CMakeLists.txt"},
        }
    );

    my_agent::Step tool_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step second_tool_call_received = my_agent::update(
        std::move(tool_call_received.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-2",
                .name = "read",
                .args = nlohmann::json{
                    {"path", "include/my_agent/runtime/agent.hpp"},
                },
            },
        }
    );

    my_agent::Step awaiting_permission = my_agent::update(
        std::move(second_tool_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    const my_agent::Step rejected = my_agent::update(
        std::move(awaiting_permission.model),
        my_agent::Msg{
            my_agent::PermissionReject{
                .id = "read-call-1",
                .feedback = "Use the information already available.",
            },
        }
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
        rejected.model.phase
    ));
    ASSERT_TRUE(rejected.model.pending_permission.has_value());
    EXPECT_EQ(
        "read-call-2",
        rejected.model.pending_permission->id
    );
    EXPECT_TRUE(std::holds_alternative<my_agent::NoCommand>(rejected.cmd));

    const my_agent::Message& tool_message =
        rejected.model.thread.messages.back();
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& rejected_call = tool_message.tool_calls[0];
    EXPECT_EQ("read-call-1", rejected_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Rejected>(
        rejected_call.status
    ));
    EXPECT_EQ(
        "User rejected this tool call. Feedback: "
        "Use the information already available.",
        rejected_call.output()
    );

    const my_agent::ToolCall& next_call = tool_message.tool_calls[1];
    EXPECT_EQ("read-call-2", next_call.id);
    EXPECT_TRUE(next_call.is_pending());
}

TEST(ToolLoopTest, RejectingFinalPermissionContinuesWithCompleteBatchResults)
{
    my_agent::Model model{};
    model.profile = my_agent::Profile::Minimal;

    my_agent::Step submitted = my_agent::update(
        std::move(model),
        my_agent::Msg{
            my_agent::Submit{.text = "Read two project files"},
        }
    );

    my_agent::Step first_call_received = my_agent::update(
        std::move(submitted.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-1",
                .name = "read",
                .args = nlohmann::json{{"path", "CMakeLists.txt"}},
            },
        }
    );

    my_agent::Step second_call_received = my_agent::update(
        std::move(first_call_received.model),
        my_agent::Msg{
            my_agent::StreamToolCall{
                .id = "read-call-2",
                .name = "read",
                .args = nlohmann::json{
                    {"path", "include/my_agent/runtime/agent.hpp"},
                },
            },
        }
    );

    my_agent::Step awaiting_first_permission = my_agent::update(
        std::move(second_call_received.model),
        my_agent::Msg{my_agent::StreamFinished{}}
    );

    my_agent::Step awaiting_second_permission = my_agent::update(
        std::move(awaiting_first_permission.model),
        my_agent::Msg{
            my_agent::PermissionReject{
                .id = "read-call-1",
                .feedback = "Use the information already available.",
            },
        }
    );

    const my_agent::Step rejected_final = my_agent::update(
        std::move(awaiting_second_permission.model),
        my_agent::Msg{
            my_agent::PermissionReject{.id = "read-call-2"},
        }
    );

    EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(
        rejected_final.model.phase
    ));
    EXPECT_FALSE(rejected_final.model.pending_permission.has_value());

    const auto* start_stream =
        std::get_if<my_agent::StartStream>(&rejected_final.cmd);
    ASSERT_NE(nullptr, start_stream);
    ASSERT_EQ(std::size_t{2}, start_stream->request.messages.size());

    const my_agent::Message& tool_message =
        start_stream->request.messages.back();
    ASSERT_EQ(std::size_t{2}, tool_message.tool_calls.size());

    const my_agent::ToolCall& first_call = tool_message.tool_calls[0];
    EXPECT_EQ("read-call-1", first_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Rejected>(
        first_call.status
    ));
    EXPECT_EQ(
        "User rejected this tool call. Feedback: "
        "Use the information already available.",
        first_call.output()
    );

    const my_agent::ToolCall& second_call = tool_message.tool_calls[1];
    EXPECT_EQ("read-call-2", second_call.id);
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Rejected>(
        second_call.status
    ));
    EXPECT_EQ("User rejected this tool call.", second_call.output());
}
