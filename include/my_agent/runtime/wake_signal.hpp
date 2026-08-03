#pragma once

#include <chrono>

namespace my_agent {

// owner thread 阻塞等待后台事件的唤醒原语，对齐 Maya 的 PosixWakeFd。
//
// 语义是"电平"而非"边沿"：signal() 置起一个标志，wait() 消费它。多次 signal
// 合并成一次唤醒，这正是我们要的 —— drain_inbox() 一次 swap 走整批消息，所以
// N 条消息只需要一次唤醒。同样重要的是标志会保持置起：signal() 发生在 owner
// 进入 wait() 之前时不会丢失唤醒，否则会永久挂死。
//
// 底层是 eventfd（不可用时退回自管道），因为 mutex + condition_variable **无法被
// poll** —— 而 TUI 必须在等唤醒的同时等键盘和 SIGWINCH。fd() 让这三者进同一个
// poll 集合。eventfd 的计数器天然满足上面两条语义：非零即可读（电平），
// 一次读走全部计数（合并）。
class WakeSignal {
public:
    WakeSignal();
    ~WakeSignal();

    WakeSignal(const WakeSignal&) = delete;
    WakeSignal& operator=(const WakeSignal&) = delete;

    // 多生产者安全。
    void signal();

    // owner thread only。返回时标志已被清除。
    void wait();

    // owner thread only。超时返回 false，且不清除标志。
    [[nodiscard]]
    bool wait_for(std::chrono::milliseconds timeout);

    // 可放进 poll 集合的读端。signal() 后可读，wait() 消费后不再可读。
    // 构造失败时返回 -1（惰性哨兵），调用方应退回超时轮询而不是拒绝启动。
    [[nodiscard]]
    int fd() const noexcept;

private:
    // eventfd 时两者相同；自管道回退时分别是读端与写端。
    int read_fd_{-1};
    int write_fd_{-1};
};

}  // namespace my_agent
