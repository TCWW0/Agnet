#include "my_agent/runtime/work_pool.hpp"

#include <algorithm>
#include <system_error>
#include <utility>

namespace my_agent {

WorkPool::WorkPool(unsigned max_workers)
    : max_workers_(std::max(1u, max_workers))
{
    workers_.reserve(max_workers_);
}

WorkPool::~WorkPool()
{
    request_stop();

    // condition_variable_any 的 stop_token 重载会在 stop 时自行返回，但 worker
    // 可能正处在两次迭代之间，补一次 notify 保证它看到。
    cv_.notify_all();

    // jthread 析构自动 join，clear() 让 join 在这里发生 —— 队列成员随后才析构，
    // 保证没有 worker 还在访问它们。隔离通道的线程是 detach 的，不在这里等。
    workers_.clear();
}

void WorkPool::task(std::function<void()> fn)
{
    const std::lock_guard<std::mutex> lock{mutex_};

    if (stop_source_.stop_requested()) {
        return;
    }

    work_.push_back(std::move(fn));

    // 有 idle worker 就复用它（condvar 唤醒 ~几十 µs），只在全忙且未到上限时
    // 才付线程构造的代价。
    if (idle_count_ == 0 && workers_.size() < max_workers_) {
        try {
            workers_.emplace_back([this](std::stop_token stop) {
                worker_loop(std::move(stop));
            });
        } catch (const std::system_error&) {
            // 撞到系统线程上限。已有 worker 会通过下面的 notify 接走这个任务，
            // 下一次 task() 还能再试 spawn。最坏情况只是排队等待。
        }
    }

    cv_.notify_one();
}

void WorkPool::task_isolated(std::function<void()> fn)
{
    if (stop_source_.stop_requested()) {
        return;
    }

    try {
        // detach 而不是 join：隔离通道存在的意义就是任务可能永久 wedge，析构时
        // join 会让宿主永久挂死，正好毁掉隔离的目的。调用方负责让任务捕获的
        // 状态（Inbox / WakeSignal）用 shared_ptr 持有，从而活得比池久。
        std::thread{std::move(fn)}.detach();
    } catch (const std::system_error&) {
        // pthread_create 返回 EAGAIN。退化到共享池而不是丢掉这份工作 —— 最坏
        // 情况是共享池也满了，表现为排队，仍严格优于丢弃。
        task(std::move(fn));
    }
}

void WorkPool::request_stop() noexcept
{
    stop_source_.request_stop();
    cv_.notify_all();
}

std::stop_token WorkPool::stop_token() const noexcept
{
    return stop_source_.get_token();
}

void WorkPool::worker_loop(std::stop_token stop)
{
    while (!stop.stop_requested()) {
        std::function<void()> job;
        {
            std::unique_lock<std::mutex> lock{mutex_};
            ++idle_count_;
            // wait(lock, stop, pred)：pred 为真或 stop 被请求时返回。stop_token
            // 本身就是关停信号，不需要额外的 shutdown_ 标志。
            cv_.wait(lock, stop, [this] { return !work_.empty(); });
            --idle_count_;

            if (work_.empty()) {
                return;  // stop 已请求且队列已空
            }

            job = std::move(work_.front());
            work_.pop_front();
        }

        // 一个任务崩掉不能带走它的 worker —— 排在后面的任务会永远等不到执行。
        // 调用方已经在自己的包装层把失败转成消息投递回宿主了，走到这里说明是
        // 意料之外的东西，吞掉是安全的。
        try {
            job();
        } catch (...) {
        }
    }
}

}  // namespace my_agent
