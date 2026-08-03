#include "my_agent/runtime/async_host.hpp"
#include "my_agent/tool/tool.hpp"

#include <atomic>
#include <cstddef>
#include <semaphore>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <variant>

#include <gtest/gtest.h>

using namespace std::chrono_literals;

// 场景：Provider 已经在真实后台线程完成了一次文本回合的事件投递。
// 领域语义：后台事件只有进入 owner thread 的 drain/update 流程后，才能成为
// Model 中的事实；Inbox 投递本身只能唤醒 owner，不能直接修改 Core 状态。
// Red 时失败原因：仓库尚不存在公开 AsyncHost seam，也没有跨线程 Inbox/wake
// 与 owner-thread drain 的实现。
TEST(AsyncHostTest, BackgroundProviderEventsChangeModelOnlyWhenOwnerDrainsInbox)
{
    const std::thread::id owner_thread = std::this_thread::get_id();
    std::thread::id provider_thread;

    // 用于本测试了解当前 Provider 已经处理完成了对应的投递
    std::binary_semaphore provider_finished{0};

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            provider_thread = std::this_thread::get_id();

            sink(my_agent::Msg{
                my_agent::StreamTextDelta{.text = "pong"},
            });
            sink(my_agent::Msg{my_agent::StreamFinished{}});

            provider_finished.release();
        };

    my_agent::AsyncHost host{std::move(fake_stream)};

    host.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "ping"},
    });

    ASSERT_TRUE(provider_finished.try_acquire_for(1s));
    EXPECT_NE(owner_thread, provider_thread);

    const my_agent::Model& before_drain = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(
        before_drain.phase
    ));
    ASSERT_EQ(std::size_t{2}, before_drain.thread.messages.size());
    EXPECT_TRUE(before_drain.thread.messages.back().text.empty());

    EXPECT_TRUE(host.wait_wake(1s));

    host.drain_inbox();

    const my_agent::Model& after_drain = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(after_drain.phase));
    ASSERT_EQ(std::size_t{2}, after_drain.thread.messages.size());
    EXPECT_EQ("pong", after_drain.thread.messages.back().text);
}

// 场景：Provider 产生一个无需审批的工具调用，Core 随后要求宿主执行它。
// 领域语义：工具可以在后台线程完成，但 ToolExecOutput 只有经过 owner thread
// 的 drain/update 流程后，才能把 ToolCall 从 Pending 转换为 Done。
// 当前失败原因：AsyncHost 尚未公开 ToolExecEffect 注入 seam，RunTool 路径也
// 尚未把工具结果投递回 Inbox。
TEST(AsyncHostTest, BackgroundToolResultChangesModelOnlyWhenOwnerDrainsInbox)
{
    const std::thread::id owner_thread = std::this_thread::get_id();
    std::thread::id tool_thread;

    std::binary_semaphore first_provider_finished{0};
    std::binary_semaphore tool_finished{0};

    std::atomic_size_t stream_calls{0};
    std::string executed_name;
    std::string executed_expression;

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            if (stream_calls.fetch_add(1) != 0) {
                return;
            }

            sink(my_agent::Msg{
                my_agent::StreamToolCall{
                    .id = "call-1",
                    .name = "calculator",
                    .args = {{"expression", "1 + 1"}},
                },
            });
            sink(my_agent::Msg{my_agent::StreamFinished{}});

            first_provider_finished.release();
        };

    my_agent::ToolExecEffect fake_tool =
        [&](std::string_view name, const nlohmann::json& args)
            -> my_agent::tool::ExecResult {
            tool_thread = std::this_thread::get_id();
            executed_name = name;
            executed_expression =
                args.at("expression").get<std::string>();

            tool_finished.release();
            return my_agent::tool::ToolOutput{.text = "2"};
        };

    my_agent::AsyncHost host{
        std::move(fake_stream),
        std::move(fake_tool),
    };

    host.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "calculate"},
    });

    ASSERT_TRUE(first_provider_finished.try_acquire_for(1s));
    ASSERT_TRUE(host.wait_wake(1s));

    host.drain_inbox();

    ASSERT_TRUE(tool_finished.try_acquire_for(1s));
    EXPECT_NE(owner_thread, tool_thread);
    EXPECT_EQ("calculator", executed_name);
    EXPECT_EQ("1 + 1", executed_expression);

    const my_agent::Model& before_tool_drain = host.model();
    const auto* executing = std::get_if<my_agent::ExecutingTool>(
        &before_tool_drain.phase
    );
    ASSERT_NE(nullptr, executing);
    EXPECT_EQ("call-1", executing->id);

    ASSERT_EQ(
        std::size_t{1},
        before_tool_drain.thread.messages.back().tool_calls.size()
    );
    EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Pending>(
        before_tool_drain.thread.messages.back().tool_calls.front().status
    ));

    ASSERT_TRUE(host.wait_wake(1s));
    host.drain_inbox();

    const my_agent::Model& after_tool_drain = host.model();
    ASSERT_EQ(std::size_t{3}, after_tool_drain.thread.messages.size());

    const my_agent::ToolCall& completed =
        after_tool_drain.thread.messages.at(1).tool_calls.front();
    const auto* done = std::get_if<my_agent::ToolCall::Done>(
        &completed.status
    );
    ASSERT_NE(nullptr, done);
    EXPECT_EQ("2", done->output);
}

// 场景：Minimal Profile 下，Provider 返回一个需要审批的 read 工具调用。
// owner thread 经多轮 drain 和 dispatch 交错完成：暂停等待审批 → 审批通过
// → 后台执行工具 → continuation Provider 请求 → 最终文本。
// 领域语义：M4 的完整权限闭环在 M5 异步宿主边界中正确运行。Provider 和
// Tool 均在后台线程执行，Model 仅在 owner 调用 drain_inbox 后变更。
// 当前是 characterization test：AsyncHost 已实现 Inbox/wake/后台 worker，
// Core 的 update() 已包含完整权限逻辑，组合路径预期直接通过。
TEST(AsyncHostTest, MinimalProfilePermissionFlowCompletesAcrossAsyncBoundary)
{
    const std::thread::id owner_thread = std::this_thread::get_id();
    std::thread::id provider_thread;
    std::thread::id tool_thread;

    std::binary_semaphore first_provider_finished{0};
    std::binary_semaphore tool_finished{0};
    std::binary_semaphore second_provider_finished{0};

    std::atomic_size_t stream_calls{0};
    std::string executed_name;
    std::string executed_path;

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            provider_thread = std::this_thread::get_id();

            const size_t call = stream_calls.fetch_add(1);
            if (call == 0) {
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "call-1",
                        .name = "read",
                        .args = {{"path", "test.txt"}},
                    },
                });
                sink(my_agent::Msg{my_agent::StreamFinished{}});
                first_provider_finished.release();
            } else {
                sink(my_agent::Msg{
                    my_agent::StreamTextDelta{.text = "done"},
                });
                sink(my_agent::Msg{my_agent::StreamFinished{}});
                second_provider_finished.release();
            }
        };

    my_agent::ToolExecEffect fake_tool =
        [&](std::string_view name, const nlohmann::json& args)
            -> my_agent::tool::ExecResult {
            tool_thread = std::this_thread::get_id();
            executed_name = name;
            executed_path = args.at("path").get<std::string>();
            tool_finished.release();
            return my_agent::tool::ToolOutput{.text = "file content here"};
        };

    my_agent::AsyncHost host{
        std::move(fake_stream),
        std::move(fake_tool),
    };

    // 设为 Minimal，确保后续工具需要审批
    host.dispatch(my_agent::Msg{
        my_agent::SetProfile{my_agent::Profile::Minimal},
    });

    // 提交用户输入，启动 Provider
    host.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "read file"},
    });

    // 等待 Provider 在线程中完成第一次调用
    ASSERT_TRUE(first_provider_finished.try_acquire_for(1s));
    EXPECT_NE(owner_thread, provider_thread);

    // drain 前：Model 仍在 Streaming，文本为空
    {
        const my_agent::Model& m = host.model();
        EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(m.phase));
        ASSERT_EQ(std::size_t{2}, m.thread.messages.size());
        EXPECT_TRUE(m.thread.messages.back().text.empty());
    }

    ASSERT_TRUE(host.wait_wake(1s));
    host.drain_inbox();

    // 第一次 drain 后：Core 判定 read + Minimal → 需要审批，暂停
    {
        const my_agent::Model& m = host.model();
        EXPECT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
            m.phase
        ));
        ASSERT_TRUE(m.pending_permission.has_value());
        EXPECT_EQ("call-1", m.pending_permission->id);

        ASSERT_EQ(std::size_t{2}, m.thread.messages.size());
        ASSERT_EQ(std::size_t{1},
            m.thread.messages.back().tool_calls.size());
        EXPECT_TRUE(std::holds_alternative<my_agent::ToolCall::Pending>(
            m.thread.messages.back().tool_calls.front().status
        ));
    }

    // owner 审批通过
    host.dispatch(my_agent::Msg{
        my_agent::PermissionApprove{.id = "call-1"},
    });

    // dispatch 后：Model 立即进入 ExecutingTool（dispatch 是同步的）
    {
        const my_agent::Model& m = host.model();
        const auto* executing = std::get_if<my_agent::ExecutingTool>(
            &m.phase
        );
        ASSERT_NE(nullptr, executing);
        EXPECT_EQ("call-1", executing->id);
        EXPECT_FALSE(m.pending_permission.has_value());
    }

    // 等待 Tool 在线程中完成
    ASSERT_TRUE(tool_finished.try_acquire_for(1s));
    EXPECT_NE(owner_thread, tool_thread);
    EXPECT_EQ("read", executed_name);
    EXPECT_EQ("test.txt", executed_path);

    ASSERT_TRUE(host.wait_wake(1s));
    host.drain_inbox();

    // 第二次 drain 后：Tool Done → continuation StartStream → 新 Provider worker
    // Model 进入 Streaming（等待第二次 Provider 调用的结果）
    {
        const my_agent::Model& m = host.model();
        EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(m.phase));

        ASSERT_GE(m.thread.messages.size(), std::size_t{2});
        const my_agent::ToolCall& completed_tc =
            m.thread.messages.at(1).tool_calls.front();
        const auto* done = std::get_if<my_agent::ToolCall::Done>(
            &completed_tc.status
        );
        ASSERT_NE(nullptr, done);
        EXPECT_EQ("file content here", done->output);
    }

    // 等待第二次 Provider 调用完成
    ASSERT_TRUE(second_provider_finished.try_acquire_for(1s));
    ASSERT_TRUE(host.wait_wake(1s));
    host.drain_inbox();

    // 第三次 drain 后：最终文本到达，回合结束
    {
        const my_agent::Model& m = host.model();
        EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(m.phase));

        ASSERT_EQ(std::size_t{3}, m.thread.messages.size());
        EXPECT_EQ("done", m.thread.messages.back().text);
    }
}

// 场景：shutdown 调用 request_stop() 后，正在执行中的 worker 的 EventSink
// 检查 stop_requested() 为 true，从而跳过 Inbox 投递。
// 领域语义：stop 是对所有后台 worker 的协作通知。Worker 在完成 Provider
// 调用后，投递结果前检查 stop_token——若宿主已请求停止，则静默丢弃结果，
// 不投递到 Inbox，不唤醒 owner。
// Red 原因：AsyncHost 尚无 shutdown() 方法（编译错误）；worker 也未捕获
// stop_token 或在其 EventSink 中检查 stop_requested()。
TEST(AsyncHostTest, WorkerSinkSkipsPostingAfterShutdownRequestsStop)
{
    std::binary_semaphore stream_blocked{0};
    std::binary_semaphore release_stream{0};
    std::binary_semaphore stream_returned{0};

    my_agent::StreamEffect blocking_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            stream_blocked.release();
            release_stream.acquire();  // 阻塞，等待测试释放
            sink(my_agent::Msg{
                my_agent::StreamTextDelta{.text = "late"},
            });
            sink(my_agent::Msg{my_agent::StreamFinished{}});
            stream_returned.release();
        };

    my_agent::AsyncHost host{std::move(blocking_stream)};

    host.dispatch(my_agent::Msg{
        my_agent::Submit{.text = "ping"},
    });

    // Worker 已启动并阻塞在 release_stream 上
    ASSERT_TRUE(stream_blocked.try_acquire_for(1s));

    // Helper 线程：在 shutdown 调用 request_stop 后释放 worker
    std::thread releaser([&] {
        std::this_thread::sleep_for(50ms);
        release_stream.release();
    });

    // owner 线程调用 shutdown：request_stop → join 所有 worker
    host.shutdown();  // RED: 'shutdown' is not a member of 'my_agent::AsyncHost'

    releaser.join();

    // Worker 已返回（stream_returned 被 release）
    EXPECT_TRUE(stream_returned.try_acquire_for(100ms));

    // 核心断言：sink 检查了 stop_token，跳过了 post，wake 未被触发
    EXPECT_FALSE(host.wait_wake(100ms));

    // Model 仍停留在 Streaming（没有任何消息到达）
    EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(
        host.model().phase
    ));
}

// 场景：owner 提交输入后直接进入阻塞事件循环，不再手摇 wake/drain。
// 领域语义：run_until_quiescent 是 owner thread 的主循环 —— 阻塞等唤醒、
// drain Inbox、把 Msg 交给 update()、解释返回的 Cmd，直到没有 in-flight
// worker 可等为止。一个纯文本回合的静止点是 Idle。
TEST(AsyncHostTest, RunUntilQuiescentDrivesATextTurnToIdle)
{
    my_agent::StreamEffect fake_stream =
        [](my_agent::Request, my_agent::EventSink sink) {
            sink(my_agent::Msg{my_agent::StreamTextDelta{.text = "po"}});
            sink(my_agent::Msg{my_agent::StreamTextDelta{.text = "ng"}});
            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::AsyncHost host{std::move(fake_stream)};

    host.dispatch(my_agent::Msg{my_agent::Submit{.text = "ping"}});
    host.run_until_quiescent();

    const my_agent::Model& model = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_EQ(std::size_t{2}, model.thread.messages.size());
    EXPECT_EQ("pong", model.thread.messages.back().text);
}

// 场景：Minimal Profile 下工具需要审批，循环必须在 AwaitingPermission 上返回。
// 领域语义：AwaitingPermission 时等的是 owner 自己的审批输入，没有后台 worker
// 会送来消息 —— 继续 wait 会永久挂死。所以它和 Idle 同为静止点。审批后再次进
// 入循环，工具执行与 continuation 都在同一次调用内跑完。
TEST(AsyncHostTest, RunUntilQuiescentReturnsWhileAwaitingPermission)
{
    std::atomic_size_t stream_calls{0};

    my_agent::StreamEffect fake_stream =
        [&stream_calls](my_agent::Request, my_agent::EventSink sink) {
            if (stream_calls.fetch_add(1) == 0) {
                sink(my_agent::Msg{
                    my_agent::StreamToolCall{
                        .id = "call-1",
                        .name = "read",
                        .args = {{"path", "test.txt"}},
                    },
                });
            } else {
                sink(my_agent::Msg{my_agent::StreamTextDelta{.text = "done"}});
            }
            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::ToolExecEffect fake_tool =
        [](std::string_view, const nlohmann::json&)
            -> my_agent::tool::ExecResult {
            return my_agent::tool::ToolOutput{.text = "file content here"};
        };

    my_agent::AsyncHost host{std::move(fake_stream), std::move(fake_tool)};

    host.dispatch(my_agent::Msg{
        my_agent::SetProfile{my_agent::Profile::Minimal},
    });
    host.dispatch(my_agent::Msg{my_agent::Submit{.text = "read file"}});

    host.run_until_quiescent();

    {
        const my_agent::Model& model = host.model();
        ASSERT_TRUE(std::holds_alternative<my_agent::AwaitingPermission>(
            model.phase
        ));
        ASSERT_TRUE(model.pending_permission.has_value());
        EXPECT_EQ("call-1", model.pending_permission->id);
    }

    host.dispatch(my_agent::Msg{
        my_agent::PermissionApprove{.id = "call-1"},
    });
    host.run_until_quiescent();

    const my_agent::Model& model = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_EQ(std::size_t{3}, model.thread.messages.size());
    EXPECT_EQ("done", model.thread.messages.back().text);
}

// 场景：Provider 实现有 bug，一个终态事件都没投就返回了。
// 领域语义：事件循环把 phase 当作 in-flight 计数器，这依赖"每次 stream 调用
// 恰好投出一个终态事件"的边界保证。宿主必须在 worker 包装层强制这条保证，
// 否则 owner 会永久停在 Streaming 上等一个永不到来的消息。用超时兜会让测试
// flaky，所以在 worker 返回时合成 StreamError。
TEST(AsyncHostTest, RunUntilQuiescentSurvivesStreamReturningWithoutTerminalEvent)
{
    my_agent::StreamEffect silent_stream =
        [](my_agent::Request, my_agent::EventSink) {};

    my_agent::AsyncHost host{std::move(silent_stream)};

    host.dispatch(my_agent::Msg{my_agent::Submit{.text = "ping"}});
    host.run_until_quiescent();

    const my_agent::Model& model = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_TRUE(model.thread.messages.back().error.has_value());
    EXPECT_NE(
        std::string::npos,
        model.thread.messages.back().error->find("terminal event")
    );
}

// 场景：Provider 抛异常逃出 stream 调用。
// 领域语义：同一条边界保证的另一半。异常若逃出 worker 线程会触发
// std::terminate，宿主必须把它收敛成一次 StreamError 交回 Core，让回合以
// 可见的错误结束而不是整个进程崩掉。
TEST(AsyncHostTest, RunUntilQuiescentConvertsStreamExceptionIntoStreamError)
{
    my_agent::StreamEffect throwing_stream =
        [](my_agent::Request, my_agent::EventSink) {
            throw std::runtime_error{"provider exploded"};
        };

    my_agent::AsyncHost host{std::move(throwing_stream)};

    host.dispatch(my_agent::Msg{my_agent::Submit{.text = "ping"}});
    host.run_until_quiescent();

    const my_agent::Model& model = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(model.phase));
    ASSERT_TRUE(model.thread.messages.back().error.has_value());
    EXPECT_EQ("provider exploded", *model.thread.messages.back().error);
}

// 场景：shutdown 后 owner 再次进入事件循环。
// 领域语义：stop 是终态。循环入口先查 stop_requested 直接返回，否则 shutdown
// 与 run 的竞态会让 owner 阻塞在一个再也不会有人 signal 的 wake 上。
TEST(AsyncHostTest, RunUntilQuiescentReturnsImmediatelyAfterShutdown)
{
    std::binary_semaphore stream_blocked{0};
    std::binary_semaphore release_stream{0};

    my_agent::StreamEffect blocking_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            stream_blocked.release();
            release_stream.acquire();
            sink(my_agent::Msg{my_agent::StreamFinished{}});
        };

    my_agent::AsyncHost host{std::move(blocking_stream)};

    host.dispatch(my_agent::Msg{my_agent::Submit{.text = "ping"}});
    ASSERT_TRUE(stream_blocked.try_acquire_for(1s));

    std::thread releaser([&] {
        std::this_thread::sleep_for(50ms);
        release_stream.release();
    });

    host.shutdown();
    releaser.join();

    // Streaming 不是静止点，但 stop 已请求 —— 必须立刻返回而不是永久阻塞。
    host.run_until_quiescent();

    EXPECT_TRUE(std::holds_alternative<my_agent::Streaming>(
        host.model().phase
    ));
}
