#pragma once

#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <stop_token>
#include <thread>
#include <vector>

namespace my_agent {

// 后台任务的两条通道，对齐 agentty 的 BackgroundQueue（maya/app/app.hpp）。
//
// 共享池（task）：弹性但有界。0 线程启动，第一次投递才 spawn；worker 复用而不
// 是每个任务建一个线程，一串工具调用因此只付一次线程构造成本（~百 µs）而不是
// 每次都付。忙时按需 spawn 到上限，所以一条长 HTTP 流不会挤掉短工具调用。
//
// 隔离通道（task_isolated）：每个任务一个 detached 线程。给可能永久卡在阻塞
// syscall 上的工作用（死掉的 NFS 挂载、僵住的子进程）。卡住的隔离任务只泄漏
// 一个线程；卡住的共享池任务会永久占掉池里一个槽位并饿死后续任务。
class WorkPool {
public:
    explicit WorkPool(unsigned max_workers = std::thread::hardware_concurrency());
    ~WorkPool();

    WorkPool(const WorkPool&) = delete;
    WorkPool& operator=(const WorkPool&) = delete;
    WorkPool(WorkPool&&) = delete;
    WorkPool& operator=(WorkPool&&) = delete;

    // 投递到共享池。
    void task(std::function<void()> fn);

    // 投递到独立的 detached 线程。
    void task_isolated(std::function<void()> fn);

    // 幂等。
    void request_stop() noexcept;

    [[nodiscard]]
    std::stop_token stop_token() const noexcept;

private:
    void worker_loop(std::stop_token stop);

    std::mutex mutex_;
    std::condition_variable_any cv_;
    std::deque<std::function<void()>> work_;

    // 构造时 reserve 到 max_workers_，所以 task() 里的 emplace_back 永不
    // realloc —— worker_loop 持有的 this 指针始终稳定。
    std::vector<std::jthread> workers_;

    int idle_count_{0};
    unsigned max_workers_;
    std::stop_source stop_source_{};
};

}  // namespace my_agent
