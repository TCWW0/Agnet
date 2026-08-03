#include "my_agent/runtime/wake_signal.hpp"

#include <chrono>
#include <thread>

#include <poll.h>

#include <gtest/gtest.h>

namespace {

using namespace std::chrono_literals;

// 以下三条是 characterization 测试：不是 Red 驱动出来的，而是在把内部实现换成
// eventfd **之前**先把现有语义钉死。这个类的三条语义都是「不这样就永久挂死」级别的，
// 换实现时必须逐条保住。

// 场景：signal() 发生在 wait() 之前。
// 领域语义：电平而非边沿。后台 worker 完全可能在 owner 还没进 wait() 时就投完消息
// 并 signal()。如果那次唤醒丢掉，owner 会在已经有消息可读的情况下永久阻塞 ——
// 这是 M5 里最难查的一类挂死。
TEST(WakeSignalTest, SignalBeforeWaitIsNotLost)
{
    my_agent::WakeSignal wake;
    wake.signal();

    EXPECT_TRUE(wake.wait_for(1s));
}

// 场景：连续多次 signal()，只等一次。
// 领域语义：合并是**正确**行为而不是妥协 —— drain_inbox() 一次 swap 走整批消息，
// 所以 N 条消息只需要一次唤醒。反过来说，N 次 signal 必须只留下一次待消费的唤醒，
// 否则 owner 会在 inbox 已空的情况下多转 N-1 圈空循环。
TEST(WakeSignalTest, RepeatedSignalsCoalesceIntoOneWake)
{
    my_agent::WakeSignal wake;
    wake.signal();
    wake.signal();
    wake.signal();

    ASSERT_TRUE(wake.wait_for(1s));
    EXPECT_FALSE(wake.wait_for(50ms));  // 第一次 wait 已消费掉全部
}

// 场景：另一个线程稍后 signal()。
// 领域语义：多生产者安全，且 wait() 真的会被跨线程唤醒。超时返回 false 且**不**
// 消费标志 —— TUI 的 poll 循环靠超时做帧率合并，它不能因为一次超时就丢掉唤醒。
TEST(WakeSignalTest, WaitIsWokenByAnotherThreadAndTimeoutDoesNotConsume)
{
    my_agent::WakeSignal wake;

    EXPECT_FALSE(wake.wait_for(50ms));  // 先来一次超时

    std::thread producer{[&wake] {
        std::this_thread::sleep_for(20ms);
        wake.signal();
    }};

    EXPECT_TRUE(wake.wait_for(1s));
    producer.join();
}

// 场景：TUI 要在等唤醒的同时等键盘。
// 领域语义：mutex + condition_variable **无法被 poll**，这是「流式输出期间读不到
// 键盘」的根本原因 —— owner 线程要么阻塞在 cv 里（stdin 不在等待集合中），
// 要么阻塞在 read 里（inbox 没人 drain）。暴露一个 fd 之后，唤醒才能和 stdin、
// SIGWINCH 一起进同一个 poll。
// 语义要求：signal() 之后 fd 可读（POLLIN），wait() 消费之后不再可读 ——
// 否则 poll 会立刻返回，循环空转烧满 CPU。
// Red 原因：仓库尚不存在 WakeSignal::fd()（编译错误）。
TEST(WakeSignalTest, ExposesAPollableDescriptorThatClearsAfterWait)
{
    my_agent::WakeSignal wake;
    const int wake_fd = wake.fd();
    ASSERT_LE(0, wake_fd);

    pollfd probe{.fd = wake_fd, .events = POLLIN, .revents = 0};

    ASSERT_EQ(0, ::poll(&probe, 1, 0)) << "未 signal 时不该可读";

    wake.signal();
    probe.revents = 0;
    ASSERT_EQ(1, ::poll(&probe, 1, 0));
    EXPECT_TRUE((probe.revents & POLLIN) != 0);

    ASSERT_TRUE(wake.wait_for(1s));

    // 消费之后必须不再可读，否则 poll 立刻返回，循环空转烧 CPU。
    probe.revents = 0;
    EXPECT_EQ(0, ::poll(&probe, 1, 0));
}

}  // namespace
