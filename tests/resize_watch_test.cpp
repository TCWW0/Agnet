#include "my_agent/ui/resize_watch.hpp"

#include <csignal>

#include <poll.h>

#include <gtest/gtest.h>

namespace {

using my_agent::ui::ResizeWatch;

// 就绪判定抽出来：这个类的全部对外语义就是「fd 可读」，测试也只该看这个。
[[nodiscard]]
bool readable(int fd)
{
    pollfd probe{.fd = fd, .events = POLLIN, .revents = 0};
    return ::poll(&probe, 1, 0) > 0 && (probe.revents & POLLIN) != 0;
}

// 场景：信号到达前后 fd 的可读状态。
// 领域语义：这个类存在的唯一理由是把信号变成 poll 看得见的东西。信号处理器里
// 不能加锁、不能分配、不能查尺寸，而事件循环此刻正阻塞在 poll 上 —— 只有 fd
// 变可读能把它叫醒。drain 之后必须回到不可读：管道是电平的，不清就一直亮着，
// poll 每次立刻返回，循环退化成忙转。
TEST(ResizeWatchTest, MakesTheSignalVisibleToPollAndClearsAfterDraining)
{
    ResizeWatch watch;
    ASSERT_LE(0, watch.fd()) << "本环境应能建管道";

    EXPECT_FALSE(readable(watch.fd())) << "没信号时不该可读";

    ASSERT_EQ(0, ::raise(SIGWINCH));
    EXPECT_TRUE(readable(watch.fd())) << "信号必须让 poll 看得见";

    EXPECT_TRUE(watch.drain());
    EXPECT_FALSE(readable(watch.fd())) << "drain 之后必须不可读，否则 poll 空转";
    EXPECT_FALSE(watch.drain()) << "没有新信号时 drain 不该报告变化";
}

// 场景：拖动窗口边框，SIGWINCH 连发几十次。
// 领域语义：合并是**正确**的而不是优化 —— 重排只需要按最终尺寸做一次，
// 中间尺寸画出来的帧全是浪费。所以 N 次信号只该换来一次「发生了变化」。
TEST(ResizeWatchTest, CoalescesABurstOfSignalsIntoASingleReportedChange)
{
    ResizeWatch watch;
    ASSERT_LE(0, watch.fd());

    for (int i = 0; i < 50; ++i) {
        ASSERT_EQ(0, ::raise(SIGWINCH));
    }

    EXPECT_TRUE(watch.drain());
    EXPECT_FALSE(readable(watch.fd())) << "一次 drain 必须读空，不能留下残余字节";
    EXPECT_FALSE(watch.drain());
}

// 场景：UI 循环退出（比如回退到行式 REPL）之后又收到 SIGWINCH。
// 领域语义：安装处理器是进程级副作用，作用域必须和 UI 循环一致。析构后还留着
// 处理器，意味着它会往已经关掉的 fd 上写 —— 那个 fd 号可能已被别的东西复用，
// 写进去就是静默的数据损坏。所以析构必须精确还原成之前的处理器。
TEST(ResizeWatchTest, RestoresThePreviousHandlerSoNothingWritesToAClosedPipe)
{
    struct sigaction before{};
    ASSERT_EQ(0, ::sigaction(SIGWINCH, nullptr, &before));

    {
        ResizeWatch watch;
        ASSERT_LE(0, watch.fd());
        struct sigaction during{};
        ASSERT_EQ(0, ::sigaction(SIGWINCH, nullptr, &during));
        ASSERT_NE(before.sa_handler, during.sa_handler) << "构造时本该换掉处理器";
    }

    struct sigaction after{};
    ASSERT_EQ(0, ::sigaction(SIGWINCH, nullptr, &after));
    EXPECT_EQ(before.sa_handler, after.sa_handler) << "析构必须原样装回";

    // 还原之后再发一次信号：进程不该因此崩，也不该有人往关掉的管道里写。
    // SIGWINCH 的默认动作是忽略，所以这里活下来本身就是断言。
    EXPECT_EQ(0, ::raise(SIGWINCH));
}

// 场景：两个 watch 先后存在。
// 领域语义：没有正确答案，只有可接受的失败方式 —— 处理器指向的全局写端只有一个，
// 所以后来者胜出。characterization：固定这个行为，并确认第二个能正常工作、
// 第一个不再收到（而不是崩溃或往错误的 fd 写）。
TEST(ResizeWatchTest, TheMostRecentlyConstructedWatchOwnsTheSignal)
{
    ResizeWatch first;
    ASSERT_LE(0, first.fd());
    {
        ResizeWatch second;
        ASSERT_LE(0, second.fd());

        ASSERT_EQ(0, ::raise(SIGWINCH));
        EXPECT_TRUE(readable(second.fd())) << "后构造的应拿到信号";
        EXPECT_FALSE(readable(first.fd())) << "先构造的不再收到";
        EXPECT_TRUE(second.drain());
    }

    // 内层析构之后外层**也**收不到了：全局写端与「已保存的旧处理器」都只有一份，
    // 内层撤下时把它们一并清掉。这不是想要的行为，但也不是崩溃 —— 记下来是为了
    // 让「同时只该存在一个」这条约束有据可查，而不是靠读实现才发现。
    // run_ui 里那一个实例的作用域覆盖整个循环，所以实际路径上不会嵌套。
    ASSERT_EQ(0, ::raise(SIGWINCH));
    EXPECT_FALSE(readable(first.fd()))
        << "characterization：嵌套后外层不再工作，约束是同时只存在一个";
}

}  // namespace
