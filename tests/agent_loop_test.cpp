#include "my_agent/runtime/agent.hpp"

#include <cstddef>
#include <variant>

#include <gtest/gtest.h>

namespace {

// 当一个外部世界提交一个消息过后，对应的状态应该发生改变，同时附属的不变量不能够被违反
TEST(AgentLoopTest, SubmitFromIdleStartsStreamingTurn)
{
    const my_agent::Step step = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    EXPECT_TRUE(
        std::holds_alternative<my_agent::Streaming>(step.model.phase)
    );

    const my_agent::Thread& thread = step.model.thread;

    ASSERT_EQ(std::size_t{2}, thread.messages.size());

    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("ping", thread.messages[0].text);

    // submit 被接受后，Core 为本轮回复创建空的 Assistant 占位消息。
    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[1].role);

    // 占位消息初始为空，后续 Provider 反馈由 Runtime 转换为 Msg，
    // 再由 Core 通过 update() 追加文本。
    EXPECT_TRUE(thread.messages[1].text.empty());

    ASSERT_TRUE(
        std::holds_alternative<my_agent::StartStream>(step.cmd)
    );

    const my_agent::StartStream& command =
        std::get<my_agent::StartStream>(step.cmd);

    ASSERT_EQ(std::size_t{1}, command.request.messages.size());
    EXPECT_EQ(my_agent::Role::User, command.request.messages[0].role);
    EXPECT_EQ("ping", command.request.messages[0].text);
}

// 当 Runtime 成功处理 StartStream 并产生 StreamTextDelta 后，Core 应当
// 将文本追加到 Assistant 占位消息中，并返回 NoCommand。
TEST(AgentLoopTest, StreamTextDeltaAppendsToAssistantPlaceholder)
{
    const my_agent::Step submitted = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    // 模拟 Runtime 处理了返回的 Step，并将 Provider 文本转换为 Core Msg。
    const my_agent::Step streamed = my_agent::update(
        submitted.model,
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "po",
            },
        }
    );

    EXPECT_TRUE(
        std::holds_alternative<my_agent::Streaming>(streamed.model.phase)
    );

    const my_agent::Thread& thread = streamed.model.thread;

    ASSERT_EQ(std::size_t{2}, thread.messages.size());

    EXPECT_EQ("ping", thread.messages[0].text);

    const my_agent::Message& assistant = thread.messages[1];
    EXPECT_EQ(my_agent::Role::Assistant, assistant.role);
    EXPECT_EQ("po", assistant.text);

    EXPECT_TRUE(
        std::holds_alternative<my_agent::NoCommand>(streamed.cmd)
    );
}

TEST(AgentLoopTest, StreamTextDeltasAccumulateInAssistantPlaceholder)
{
    const my_agent::Step submitted = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    const my_agent::Step first_delta = my_agent::update(
        submitted.model,
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "po",
            },
        }
    );

    const my_agent::Step second_delta = my_agent::update(
        first_delta.model,
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "ng",
            },
        }
    );

    EXPECT_TRUE(
        std::holds_alternative<my_agent::Streaming>(
            second_delta.model.phase
        )
    );

    const my_agent::Thread& thread = second_delta.model.thread;

    ASSERT_EQ(std::size_t{2}, thread.messages.size());

    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("ping", thread.messages[0].text);
    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[1].role);
    EXPECT_EQ("pong", thread.messages[1].text);

    EXPECT_TRUE(
        std::holds_alternative<my_agent::NoCommand>(second_delta.cmd)
    );
}

TEST(AgentLoopTest, StreamFinishedReturnsToIdleWithoutChangingThread)
{
    const my_agent::Step submitted = my_agent::update(
        my_agent::Model{},
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    const my_agent::Step streamed = my_agent::update(
        submitted.model,
        my_agent::Msg{
            my_agent::StreamTextDelta{
                .text = "pong",
            },
        }
    );

    const my_agent::Step finished = my_agent::update(
        streamed.model,
        my_agent::Msg{
            my_agent::StreamFinished{},
        }
    );

    EXPECT_TRUE(
        std::holds_alternative<my_agent::Idle>(finished.model.phase)
    );

    const my_agent::Thread& thread = finished.model.thread;

    ASSERT_EQ(std::size_t{2}, thread.messages.size());

    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("ping", thread.messages[0].text);
    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[1].role);
    EXPECT_EQ("pong", thread.messages[1].text);

    EXPECT_TRUE(
        std::holds_alternative<my_agent::NoCommand>(finished.cmd)
    );
}

} // namespace
