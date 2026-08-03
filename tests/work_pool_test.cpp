#include "my_agent/runtime/work_pool.hpp"

#include <atomic>
#include <cstddef>
#include <mutex>
#include <semaphore>
#include <thread>
#include <vector>

#include <gtest/gtest.h>

using namespace std::chrono_literals;

// 场景：向共享池投递比容量更多的阻塞任务。
// 领域语义：共享池是弹性但有界的 —— 按需 spawn，绝不超过容量上限。上限的意义
// 是防止一次工具风暴把线程数炸开；有界的代价是超出的任务排队等待。
// Red 原因：仓库尚不存在 WorkPool（编译错误）。
TEST(WorkPoolTest, SharedPoolRunsAtMostMaxWorkersTasksConcurrently)
{
    constexpr unsigned kMaxWorkers = 2;
    constexpr int kTasks = 6;

    std::counting_semaphore<kTasks> started{0};
    std::binary_semaphore gate{0};
    std::atomic_int concurrent{0};
    std::atomic_int peak{0};

    my_agent::WorkPool pool{kMaxWorkers};

    for (int i = 0; i < kTasks; ++i) {
        pool.task([&] {
            const int now = concurrent.fetch_add(1) + 1;
            int seen = peak.load();
            while (now > seen && !peak.compare_exchange_weak(seen, now)) {
            }

            started.release();
            gate.acquire();
            concurrent.fetch_sub(1);
            gate.release();  // 交棒给下一个等待者，形成串行放行
        });
    }

    // 恰好 kMaxWorkers 个任务能同时在飞，第 kMaxWorkers + 1 个必须排队。
    for (unsigned i = 0; i < kMaxWorkers; ++i) {
        ASSERT_TRUE(started.try_acquire_for(1s));
    }
    EXPECT_FALSE(started.try_acquire_for(100ms));

    gate.release();

    for (int i = 0; i < kTasks - static_cast<int>(kMaxWorkers); ++i) {
        ASSERT_TRUE(started.try_acquire_for(1s));
    }

    EXPECT_EQ(static_cast<int>(kMaxWorkers), peak.load());
}

// 场景：串行投递一批短任务，每个都在下一个投递前跑完。
// 领域语义：worker 复用（warm reuse）。这是"池"而不是"每任务一线程"的全部理由
// —— 一串 read/grep 工具调用应该只付一次线程构造成本（~百 µs），后续走 condvar
// 唤醒（~几十 µs）。观测手段是线程 id：全部任务应该落在同一个 worker 上。
// Red 原因：若实现按每任务 spawn 线程，会看到多个不同的线程 id。
TEST(WorkPoolTest, SharedPoolReusesAWarmWorkerForSequentialTasks)
{
    constexpr int kTasks = 8;

    // 容量固定为 1，让"复用"与"新建"在观测上无法混淆。容量更大时 spawn 判据读
    // 到的 idle_count_ 是个快照：worker 跑完任务、还没重新登记为 idle 的窗口里
    // 投递，会看到 idle_count_ == 0 从而多开一个线程。那是有意的保守行为（最坏
    // 只到上限），但会让"必须是同一个 worker"的断言变得不确定。
    my_agent::WorkPool pool{1};

    std::mutex seen_mutex;
    std::vector<std::thread::id> seen;

    for (int i = 0; i < kTasks; ++i) {
        std::binary_semaphore done{0};

        pool.task([&] {
            {
                const std::lock_guard<std::mutex> lock{seen_mutex};
                seen.push_back(std::this_thread::get_id());
            }
            done.release();
        });

        // 等它跑完再投下一个，保证投递时总有 idle worker 可复用。
        ASSERT_TRUE(done.try_acquire_for(1s));
    }

    ASSERT_EQ(static_cast<std::size_t>(kTasks), seen.size());
    for (const std::thread::id& id : seen) {
        EXPECT_EQ(seen.front(), id);
    }
}

// 场景：共享池被永久 wedge 的任务打满，此时投递一个隔离任务。
// 领域语义：双通道分离的核心证明，也是本项目系统设计叙事的要点。共享池是有界
// 的，所以一个卡死的任务会永久占掉一个槽位；打满之后共享池上的新任务再也跑不
// 起来。隔离通道必须不受影响 —— 卡住的隔离任务只泄漏一个线程，而卡住的共享池
// 任务会饿死所有后续任务。工具执行走隔离通道正是因为它可能卡在死掉的挂载点上。
// Red 原因：若两条通道共用一个池，隔离任务会一起被饿死。
TEST(WorkPoolTest, IsolatedTaskCompletesWhileSharedPoolIsSaturated)
{
    constexpr unsigned kMaxWorkers = 2;

    std::counting_semaphore<kMaxWorkers> wedged{0};
    std::binary_semaphore isolated_done{0};
    std::binary_semaphore shared_after_saturation{0};

    // wedge 住的任务必须能被放行，否则 ~WorkPool 会永久 join 挂死。
    std::binary_semaphore unwedge{0};

    {
        my_agent::WorkPool pool{kMaxWorkers};

        for (unsigned i = 0; i < kMaxWorkers; ++i) {
            pool.task([&] {
                wedged.release();
                unwedge.acquire();
                unwedge.release();  // 交棒，让所有 wedge 任务都能退出
            });
        }

        // 两个 worker 都已进入并卡住，池现在满了。
        for (unsigned i = 0; i < kMaxWorkers; ++i) {
            ASSERT_TRUE(wedged.try_acquire_for(1s));
        }

        // 共享池上的新任务确实跑不起来 —— 这是"池已饱和"的证据。
        pool.task([&] { shared_after_saturation.release(); });
        EXPECT_FALSE(shared_after_saturation.try_acquire_for(100ms));

        // 隔离通道不受影响。这是本测试的断言核心。
        pool.task_isolated([&] { isolated_done.release(); });
        EXPECT_TRUE(isolated_done.try_acquire_for(1s));

        unwedge.release();
    }
}

// 场景：池里有空闲 worker 时直接析构。
// 领域语义：关停必须干净收尾。worker 阻塞在 condvar 上等活，stop_token 本身就是
// 关停信号 —— condition_variable_any 的 stop_token 重载让它立刻返回，jthread
// 析构自动 join。不需要额外的 shutdown_ 标志，也不会挂死。
// Red 原因：若 wait 没带 stop_token，idle worker 永远等不到 notify，析构挂死。
TEST(WorkPoolTest, DestructorJoinsIdleWorkersWithoutHanging)
{
    std::binary_semaphore ran{0};

    {
        my_agent::WorkPool pool{4};
        pool.task([&] { ran.release(); });
        ASSERT_TRUE(ran.try_acquire_for(1s));
        // 此刻 worker 已回到 idle 等待状态，离开作用域即触发析构。
    }

    SUCCEED();  // 走到这里就说明析构没有挂死
}

// 场景：request_stop 之后继续投递。
// 领域语义：stop 是终态。已请求停止后投递的任务必须被丢弃而不是排队 —— 否则
// 析构时要么执行一个宿主已不再关心的任务，要么等一个永远不会被消费的队列。
// Red 原因：若 task() 不查 stop，任务会被压进队列。
TEST(WorkPoolTest, TasksSubmittedAfterStopAreDiscarded)
{
    std::atomic_bool ran{false};

    {
        my_agent::WorkPool pool{2};
        pool.request_stop();

        pool.task([&] { ran.store(true); });
        pool.task_isolated([&] { ran.store(true); });
    }

    EXPECT_FALSE(ran.load());
}
