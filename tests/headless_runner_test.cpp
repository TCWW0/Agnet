#include <cstddef>
#include <gtest/gtest.h>
#include <optional>
#include <string>
#include <utility>
#include <variant>
#include "my_agent/agent.hpp"
#include "my_agent/headless_runner.hpp"

TEST(HeadlessRunnerTest, CompletesStreamingTurnWithFakeProvider)
{
    int stream_calls = 0;
    std::string received_user_text;

    my_agent::StreamEffect fake_stream = 
        [&](my_agent::Request request,my_agent::EventSink sink){
            ++stream_calls;
            received_user_text = std::move(request.messages.front().text);
            sink(
                my_agent::Msg{
                    my_agent::StreamTextDelta{
                        .text = "po",
                    }
                }
            );
            sink(
                my_agent::Msg{
                    my_agent::StreamTextDelta{
                        .text = "ng",
                    },
                }
            );
            sink(
                my_agent::Msg{
                    my_agent::StreamFinished{},
                }
            );
        };

    my_agent::HeadlessRunner runner{
        std::move(fake_stream),
    };

    // 此时使用的是一个空的model
    const my_agent::Model& final_model = runner.dispatch(
        my_agent::Msg{
            my_agent::Submit{
                .text = "ping",
            },
        }
    );

    EXPECT_EQ(1,stream_calls);
    EXPECT_EQ("ping",received_user_text);

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(final_model.phase));

    const my_agent::Thread& thread = final_model.thread;

    ASSERT_EQ(std::size_t{2},thread.messages.size());
    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("ping", thread.messages[0].text);
    EXPECT_EQ(my_agent::Role::Assistant, thread.messages[1].role);
    EXPECT_EQ("pong",thread.messages[1].text);
}

TEST(HeadlessRunnerTest, SecondTurnRequestContainsPriorConversationAndLatestUserMessage)
{
    std::optional<my_agent::Request> latest_request;
    std::string reply = "first answer";

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request request,my_agent::EventSink sink){
            latest_request = std::move(request);

            sink(my_agent::Msg{
                my_agent::StreamTextDelta{.text=reply},
            });
            sink(my_agent::Msg{
                my_agent::StreamFinished{},
            });
        };

    my_agent::HeadlessRunner runner {
        fake_stream
    };

    (void)runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "first question"},
    });

    latest_request.reset();
    reply = "second answer";

    (void)runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "second question"},
    });

    ASSERT_TRUE(latest_request.has_value());

    const auto& messages = latest_request->messages;
    ASSERT_EQ(std::size_t{3}, messages.size());

    EXPECT_EQ(my_agent::Role::User, messages[0].role);
    EXPECT_EQ("first question", messages[0].text);

    EXPECT_EQ(my_agent::Role::Assistant, messages[1].role);
    EXPECT_EQ("first answer", messages[1].text);

    EXPECT_EQ(my_agent::Role::User, messages[2].role);
    EXPECT_EQ("second question", messages[2].text);
}

TEST(HeadlessRunnerTest, ProviderErrorWithoutTextReturnsToIdleAndMarksAssistantMessage)
{
    my_agent::StreamEffect fake_stream =
        [](my_agent::Request, my_agent::EventSink sink) {
            sink(my_agent::Msg{
                my_agent::StreamError{.message = "network unavailable"},
            });
        };

    my_agent::HeadlessRunner runner{std::move(fake_stream)};

    const my_agent::Model& model = runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "StreamError Test"},
    });

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));

    const my_agent::Thread& thread = model.thread;
    ASSERT_EQ(std::size_t{2}, thread.messages.size());
    EXPECT_EQ(my_agent::Role::User, thread.messages[0].role);
    EXPECT_EQ("StreamError Test", thread.messages[0].text);

    const my_agent::Message& assistant = thread.messages[1];
    EXPECT_EQ(my_agent::Role::Assistant, assistant.role);
    EXPECT_TRUE(assistant.text.empty());
    ASSERT_TRUE(assistant.error.has_value());
    EXPECT_EQ("network unavailable", *assistant.error);
}

TEST(HeadlessRunnerTest, ProviderErrorAfterTextPreservesPartialAssistantMessage)
{
    my_agent::StreamEffect fake_stream =
        [](my_agent::Request, my_agent::EventSink sink) {
            sink(my_agent::Msg{
                my_agent::StreamTextDelta{.text = "partial answer"},
            });
            sink(my_agent::Msg{
                my_agent::StreamError{.message = "content filtering policy"},
            });
        };

    my_agent::HeadlessRunner runner{std::move(fake_stream)};

    const my_agent::Model& model = runner.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "answer this question"},
    });

    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));

    const my_agent::Thread& thread = model.thread;
    ASSERT_EQ(std::size_t{2}, thread.messages.size());

    const my_agent::Message& assistant = thread.messages[1];
    EXPECT_EQ(my_agent::Role::Assistant, assistant.role);
    EXPECT_EQ("partial answer", assistant.text);
    ASSERT_TRUE(assistant.error.has_value());
    EXPECT_EQ("content filtering policy", *assistant.error);
}
