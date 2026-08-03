#pragma once

#include <chrono>
#include <condition_variable>
#include <mutex>

namespace my_agent {

// owner thread 阻塞等待后台事件的唤醒原语，对齐 Maya 的 PosixWakeFd。
//
// 语义是"电平"而非"边沿"：signal() 置起一个标志，wait() 消费它。多次 signal
// 合并成一次唤醒，这正是我们要的 —— drain_inbox() 一次 swap 走整批消息，所以
// N 条消息只需要一次唤醒。同样重要的是标志会保持置起：signal() 发生在 owner
// 进入 wait() 之前时不会丢失唤醒，否则会永久挂死。
//
// 用 mutex + condition_variable 而不是 binary_semaphore：后者在已置起时再
// release() 会突破 max()==1 从而进入未定义行为，而"已经置起时再 signal"恰好
// 是这里的常态。未来换成 eventfd 只需要替换这个类。
class WakeSignal {
public:
    // 多生产者安全。
    void signal()
    {
        {
            const std::lock_guard<std::mutex> lock{mutex_};
            signaled_ = true;
        }
        cv_.notify_all();
    }

    // owner thread only。返回时标志已被清除。
    void wait()
    {
        std::unique_lock<std::mutex> lock{mutex_};
        cv_.wait(lock, [this] { return signaled_; });
        signaled_ = false;
    }

    // owner thread only。超时返回 false，且不清除标志。
    [[nodiscard]]
    bool wait_for(std::chrono::milliseconds timeout)
    {
        std::unique_lock<std::mutex> lock{mutex_};
        if (!cv_.wait_for(lock, timeout, [this] { return signaled_; })) {
            return false;
        }
        signaled_ = false;
        return true;
    }

private:
    std::mutex mutex_;
    std::condition_variable cv_;
    bool signaled_{false};
};

}  // namespace my_agent
