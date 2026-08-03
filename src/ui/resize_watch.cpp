#include "my_agent/ui/resize_watch.hpp"

#include <atomic>
#include <cerrno>
#include <csignal>

#include <fcntl.h>
#include <unistd.h>

namespace my_agent::ui {

namespace {

// 处理器只认得全局变量 —— 拿不到 this。用 atomic<int> 而不是裸 int：写端由构造
// 函数在 owner 线程设置，处理器可能在别的线程上跑，需要一个明确的同步点。
// -1 表示没有可写的管道，此时处理器什么都不做。
std::atomic<int> g_resize_write_fd{-1};

// 唯一允许出现在这里的调用是 write：不能加锁（处理器可能打断持锁的代码，
// 一加就死锁）、不能分配、更不能 ioctl 查尺寸。查尺寸留给循环自己在安全上下文做。
extern "C" void resize_signal_handler(int)
{
    const int fd = g_resize_write_fd.load(std::memory_order_relaxed);
    if (fd < 0) {
        return;
    }
    // errno 必须存下来再还原：处理器打断的那段代码可能正要读 errno，
    // 这里的 write 失败会把它冲掉，造成一个几乎无法复现的诡异 bug。
    const int saved_errno = errno;
    const char token = 'w';
    static_cast<void>(::write(fd, &token, 1));
    errno = saved_errno;
}

[[nodiscard]]
bool make_nonblocking_cloexec(int fd) noexcept
{
    const int flags = ::fcntl(fd, F_GETFL);
    if (flags < 0 || ::fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
        return false;
    }
    return ::fcntl(fd, F_SETFD, FD_CLOEXEC) >= 0;
}

// 保存进入时的处理器，析构时原样装回。
struct sigaction g_previous_action{};
bool g_previous_saved = false;

}  // namespace

ResizeWatch::ResizeWatch()
{
    int pipe_fds[2] = {-1, -1};
    if (::pipe(pipe_fds) != 0) {
        return;  // 惰性哨兵：fd() 返回 -1，窗口变化不再唤醒循环
    }
    // 写端非阻塞是硬要求：拖动窗口时信号来得比循环 drain 得快，管道会满。
    // 阻塞的写端会让处理器卡在 write 里 —— 而它正打断着主线程，于是整个进程死锁。
    if (!make_nonblocking_cloexec(pipe_fds[0]) || !make_nonblocking_cloexec(pipe_fds[1])) {
        ::close(pipe_fds[0]);
        ::close(pipe_fds[1]);
        return;
    }
    read_fd_ = pipe_fds[0];
    write_fd_ = pipe_fds[1];

    // 先发布写端再装处理器：反过来的话，装好处理器与写端可见之间存在一个窗口，
    // 落在窗口里的信号会被丢掉。
    g_resize_write_fd.store(write_fd_, std::memory_order_release);

    struct sigaction action{};
    action.sa_handler = resize_signal_handler;
    ::sigemptyset(&action.sa_mask);
    // 不设 SA_RESTART：让 poll 以 EINTR 返回，循环于是立刻转一圈去 drain，
    // 而不必等到 poll 超时。管道那条路是主路径，EINTR 只是让它更快到达。
    action.sa_flags = 0;
    if (::sigaction(SIGWINCH, &action, &g_previous_action) == 0) {
        g_previous_saved = true;
    }
}

ResizeWatch::~ResizeWatch()
{
    // 顺序：先摘处理器，再撤下写端，最后关 fd。反过来会让一个正在跑的处理器
    // 拿到已经关掉的 fd —— 那个 fd 号可能已经被别的东西复用，写进去就是数据损坏。
    if (g_previous_saved) {
        static_cast<void>(::sigaction(SIGWINCH, &g_previous_action, nullptr));
        g_previous_saved = false;
    }
    g_resize_write_fd.store(-1, std::memory_order_release);

    if (read_fd_ >= 0) {
        ::close(read_fd_);
    }
    if (write_fd_ >= 0) {
        ::close(write_fd_);
    }
}

int ResizeWatch::fd() const noexcept
{
    return read_fd_;
}

bool ResizeWatch::drain() noexcept
{
    if (read_fd_ < 0) {
        return false;
    }
    bool any = false;
    char scratch[64];
    // 读到空为止：一次拖动攒下的几十个字节全部取走，只报告一次变化。
    while (::read(read_fd_, scratch, sizeof(scratch)) > 0) {
        any = true;
    }
    return any;
}

}  // namespace my_agent::ui
