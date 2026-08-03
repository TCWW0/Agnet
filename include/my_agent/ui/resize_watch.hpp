#pragma once

namespace my_agent::ui {

// 把 SIGWINCH 转成一个可 poll 的 fd（自管道技巧）。
//
// 为什么必须转成 fd：信号处理器里几乎什么都不能做 —— 不能加锁、不能分配、不能
// 调 ioctl 查尺寸。而事件循环此刻正阻塞在 poll 上，只有一个 fd 变可读才能把它
// 叫醒。所以处理器只做一件 async-signal-safe 的事：往管道里写一个字节。
//
// 为什么不能省掉这层、只靠 poll 被 EINTR 打断：那依赖处理器已安装（默认忽略的
// 信号根本不打断 poll），也依赖处理器不带 SA_RESTART。更要紧的是 EINTR 只能让
// 循环转一圈，重排本身还得靠重绘 —— 而重绘可能正好被帧预算跳过。走 fd 这条路，
// 重排和别的事件走的是同一条路径。
//
// RAII：构造时安装处理器，析构时精确还原成之前的处理器。进程级副作用的作用域
// 因此和 UI 循环一致 —— 循环退出后（比如回退到行式 REPL）不该再有残留的处理器。
// 不可拷贝也不可移动：处理器指向的全局写端只有一个，复制会让还原语义变得含糊。
//
// 约束：同一时刻只该存在一个实例。处理器只认得全局变量，所以后构造的胜出，而且
// 内层析构会把全局状态一并清掉 —— 外层从此也收不到信号（tests/resize_watch_test
// 里 characterization 过这个行为）。run_ui 里那一个实例的作用域覆盖整个循环，
// 实际路径上不会嵌套，所以没有为嵌套加计数栈 —— 那是为不存在的场景写代码。
class ResizeWatch {
public:
    ResizeWatch();
    ~ResizeWatch();

    ResizeWatch(const ResizeWatch&) = delete;
    ResizeWatch& operator=(const ResizeWatch&) = delete;

    // 放进 poll 集合的读端。自管道创建失败时返回 -1 —— 此时窗口变化不再唤醒
    // 循环（屏幕停在旧宽度直到下一个事件），但循环照常跑，不该因此拒绝启动。
    [[nodiscard]]
    int fd() const noexcept;

    // 取走已积攒的信号字节，并返回是否真的发生过窗口变化。
    // 必须取走：管道是电平的，不读就一直可读，poll 每次立刻返回，循环退化成忙转。
    // 合并是对的 —— 拖动窗口会连发几十个 SIGWINCH，而重排只需要按最终尺寸做一次。
    [[nodiscard]]
    bool drain() noexcept;

private:
    int read_fd_{-1};
    int write_fd_{-1};
};

}  // namespace my_agent::ui
