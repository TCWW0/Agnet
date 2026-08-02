#include "my_agent/runtime/async_host.hpp"

#include <chrono>
#include <cstddef>
#include <semaphore>
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
    std::counting_semaphore<8> owner_wake{0};

    my_agent::StreamEffect fake_stream =
        [&](my_agent::Request, my_agent::EventSink sink) {
            provider_thread = std::this_thread::get_id();

            sink(my_agent::Msg{
                my_agent::StreamTextDelta{.text = "pong"},
            });
            sink(my_agent::Msg{my_agent::StreamFinished{}});

            provider_finished.release();
        };

    my_agent::AsyncHost host{
        std::move(fake_stream),
        // 释放一个信号量使得 acquire 能够成功
        [&owner_wake] { owner_wake.release(); },
    };

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

    EXPECT_TRUE(owner_wake.try_acquire_for(1s));

    host.drain_inbox();

    const my_agent::Model& after_drain = host.model();
    EXPECT_TRUE(std::holds_alternative<my_agent::Idle>(after_drain.phase));
    ASSERT_EQ(std::size_t{2}, after_drain.thread.messages.size());
    EXPECT_EQ("pong", after_drain.thread.messages.back().text);
}
