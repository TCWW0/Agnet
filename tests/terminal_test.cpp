#include "my_agent/ui/terminal.hpp"

#include <csignal>
#include <string>

#include <fcntl.h>
#include <sys/wait.h>
#include <pty.h>
#include <termios.h>
#include <unistd.h>

#include <gtest/gtest.h>

namespace {

// 场景：把两行帧转成终端字节。
// 领域语义：全帧重绘是**覆写**而不是清屏重画 —— 先清屏会让整个界面闪一下。覆写的
// 代价是上一帧更长的行会留下尾巴（"允许 bash？" 覆写在 "允许 read_file？" 上会剩
// "le?"）。所以每行写完必须擦到行尾。这是全帧重绘唯一的正确性要求。
// Red 原因：仓库尚不存在 ui::frame_bytes（编译错误）。
TEST(TerminalTest, ErasesToEndOfEachLineSoLongerPreviousLinesLeaveNoResidue)
{
    const my_agent::ui::Frame frame{
        .lines = {{.text = "first"}, {.text = "second"}},
    };

    const std::string bytes = my_agent::ui::frame_bytes(frame);

    // 每行正文之后紧跟 EL（擦到行尾）。
    EXPECT_NE(std::string::npos, bytes.find("first\x1b[K"));
    EXPECT_NE(std::string::npos, bytes.find("second\x1b[K"));
}

// 场景：多行帧的行定位。
// 领域语义：帧的第 n 行必须落在屏幕的第 n 行。靠 "\n" 推进是错的 —— raw mode 下
// 没有 ONLCR，"\n" 只下移一行不回到第 1 列，第二行就会从第一行的结尾处开始，
// 整个界面呈阶梯状。所以每行前必须显式 CUP 定位到 (row, 1)。
// Red 原因：当前实现只拼接正文，没有任何定位序列。
TEST(TerminalTest, PositionsEachLineAtItsOwnRow)
{
    const my_agent::ui::Frame frame{
        .lines = {{.text = "first"}, {.text = "second"}},
    };

    const std::string bytes = my_agent::ui::frame_bytes(frame);

    const std::size_t row1 = bytes.find("\x1b[1;1H");
    const std::size_t row2 = bytes.find("\x1b[2;1H");
    ASSERT_NE(std::string::npos, row1);
    ASSERT_NE(std::string::npos, row2);
    EXPECT_LT(row1, row2);
    EXPECT_LT(row1, bytes.find("first"));
    EXPECT_LT(bytes.find("first"), row2);
}

// 场景：这一帧比上一帧短。
// 领域语义：EL 只擦横向残留，纵向残留要靠 ED。审批提示消失后帧少一行，如果不擦，
// "allow bash? [y/n]" 会永久留在屏幕上 —— 用户会以为还有东西等着批。全帧重绘的
// 纵向对偶：最后一行之后擦到屏幕底部。
// Red 原因：当前实现写完最后一行就结束，没有 ED。
TEST(TerminalTest, ErasesBelowTheLastLineSoAShorterFrameLeavesNoResidue)
{
    const my_agent::ui::Frame frame{.lines = {{.text = "only"}}};

    const std::string bytes = my_agent::ui::frame_bytes(frame);

    const std::size_t erase_below = bytes.find("\x1b[J");
    ASSERT_NE(std::string::npos, erase_below);
    EXPECT_LT(bytes.find("only"), erase_below);  // 必须在正文之后，否则擦掉自己
}

// 场景：进入与退出全屏的字节序列。
// 领域语义：退出序列必须是进入序列的**精确逆操作，且顺序相反**。进入是
// 「切备用屏 → 藏光标」，退出必须是「显光标 → 回主屏」。顺序反了会把光标显示在
// 备用屏上、再切回主屏 —— 主屏的光标状态取决于终端实现，可能留下隐藏的光标，
// 用户的 shell 从此看不见自己在打什么。这是崩溃恢复要恢复的东西，必须先钉死顺序。
// Red 原因：仓库尚不存在 enter_bytes / leave_bytes（编译错误）。
TEST(TerminalTest, LeaveSequenceReversesEnterSequenceInOppositeOrder)
{
    const std::string enter{my_agent::ui::enter_bytes()};
    const std::string leave{my_agent::ui::leave_bytes()};

    const std::string alt_screen_on = "\x1b[?1049h";
    const std::string alt_screen_off = "\x1b[?1049l";
    const std::string cursor_hide = "\x1b[?25l";
    const std::string cursor_show = "\x1b[?25h";

    ASSERT_NE(std::string::npos, enter.find(alt_screen_on));
    ASSERT_NE(std::string::npos, enter.find(cursor_hide));
    ASSERT_NE(std::string::npos, leave.find(cursor_show));
    ASSERT_NE(std::string::npos, leave.find(alt_screen_off));

    EXPECT_LT(enter.find(alt_screen_on), enter.find(cursor_hide));
    EXPECT_LT(leave.find(cursor_show), leave.find(alt_screen_off));
}

// 场景：在非 tty 上构造驱动（CI、管道、`my_agent | tee`）。
// 领域语义：非 tty 不是错误，是一种正常的运行方式 —— 但 termios 和转义序列在那里
// 都没有意义。驱动必须能构造成功且自报 `!is_tty()`，让前端据此回退到行式输出。
// 反过来如果构造失败或照样吐转义序列，重定向到文件的输出里就会混进一堆乱码。
// Red 原因：仓库尚不存在 TerminalDriver（编译错误）。
TEST(TerminalTest, ReportsNonTtyInsteadOfFailingWhenOutputIsNotATerminal)
{
    const int devnull = ::open("/dev/null", O_WRONLY);
    ASSERT_LE(0, devnull);

    {
        my_agent::ui::TerminalDriver driver{devnull, devnull};
        EXPECT_FALSE(driver.is_tty());
    }

    ::close(devnull);
}

// 场景：在真 pty 上进入 raw mode 然后析构。
// 领域语义：这是整个 TUI 里唯一会**损坏用户环境**的失效。raw mode 关掉了 ECHO 和
// ICANON，没还原的话退出后 shell 不回显、退格不工作，用户得敲 `reset` 才能救回来。
// 所以驱动必须真的进 raw mode（否则读不到单键），并且析构后 termios 必须逐字段
// 等于进入前的样子。前面几条测试都在断言字节串，这条断言的是**系统状态**。
// Red 原因：驱动虽已实现，但这是第一条真正验证还原的测试 —— 它保护的不变量
// 无法从字节串断言，必须要一个真 tty。
TEST(TerminalTest, RestoresTerminalAttributesExactlyOnDestruction)
{
    int primary = -1;
    int replica = -1;
    if (::openpty(&primary, &replica, nullptr, nullptr, nullptr) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    termios before{};
    ASSERT_EQ(0, ::tcgetattr(replica, &before));

    termios inside{};
    {
        my_agent::ui::TerminalDriver driver{replica, replica};
        ASSERT_TRUE(driver.is_tty());
        ASSERT_EQ(0, ::tcgetattr(replica, &inside));
        // 真的进了 raw mode：回显与行缓冲都关掉了，否则读不到单个按键。
        EXPECT_EQ(0u, inside.c_lflag & static_cast<tcflag_t>(ECHO));
        EXPECT_EQ(0u, inside.c_lflag & static_cast<tcflag_t>(ICANON));
    }

    termios after{};
    ASSERT_EQ(0, ::tcgetattr(replica, &after));
    EXPECT_EQ(before.c_lflag, after.c_lflag);
    EXPECT_EQ(before.c_iflag, after.c_iflag);
    EXPECT_EQ(before.c_oflag, after.c_oflag);
    EXPECT_EQ(before.c_cc[VMIN], after.c_cc[VMIN]);
    EXPECT_EQ(before.c_cc[VTIME], after.c_cc[VTIME]);

    ::close(replica);
    ::close(primary);
}

// 场景：进入 raw mode 之后进程被 SIGSEGV 杀掉。
// 领域语义：析构函数在 SIGSEGV 下不执行，所以 RAII 保护不了这条路径 —— 而这正是
// 唯一会把用户的 shell 弄坏的路径（raw mode 没还原 = 不回显、退格不工作，
// 得敲 reset）。所以必须有一条不依赖栈展开的还原路径。
// 用 fork：子进程进 raw mode 后故意 SIGSEGV，父进程检查共享的 pty 是否已还原。
// 这是唯一能真正验证「崩溃后终端可用」的做法 —— 在同进程里断言只能测到函数本身，
// 测不到它确实被信号触发。
// Red 原因：仓库尚不存在 install_crash_handler（编译错误）。
TEST(TerminalTest, RestoresTerminalWhenTheProcessCrashesWithoutUnwinding)
{
    int primary = -1;
    int replica = -1;
    if (::openpty(&primary, &replica, nullptr, nullptr, nullptr) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    termios before{};
    ASSERT_EQ(0, ::tcgetattr(replica, &before));

    const pid_t child = ::fork();
    ASSERT_LE(0, child);
    if (child == 0) {
        my_agent::ui::TerminalDriver driver{replica, replica};
        driver.install_crash_handler();
        // 故意崩溃。析构函数不会跑，只有信号处理器有机会还原。
        std::raise(SIGSEGV);
        ::_exit(0);  // 到不了这里
    }

    int status = 0;
    ASSERT_EQ(child, ::waitpid(child, &status, 0));

    termios after{};
    ASSERT_EQ(0, ::tcgetattr(replica, &after));
    EXPECT_EQ(before.c_lflag, after.c_lflag);
    EXPECT_EQ(before.c_iflag, after.c_iflag);
    EXPECT_EQ(before.c_oflag, after.c_oflag);

    ::close(replica);
    ::close(primary);
}

// 场景：往一个已经写不进去的 fd 上渲染。
// 领域语义：`render()` 必须报告是否**完整**写完，因为调用方要据此决定是否
// commit 已渲染状态。写失败却报成功，front 就会声称屏幕上有实际没写进去的内容，
// 之后每一次差分都建立在假前提上，而且这种残留不会自愈。
// 用管道模拟：读端关掉后写入立即失败。
// Red 原因：仓库尚不存在 render()（编译错误）。
TEST(TerminalTest, RenderReportsFailureSoTheCallerDoesNotCommitAnUnwrittenFrame)
{
    int pipe_fds[2] = {-1, -1};
    ASSERT_EQ(0, ::pipe(pipe_fds));
    ::close(pipe_fds[0]);  // 读端关掉：写入会拿到 EPIPE

    // SIGPIPE 默认会杀掉进程，这里要的是 write 返回 -1。
    const auto previous = std::signal(SIGPIPE, SIG_IGN);

    my_agent::ui::TerminalDriver driver{pipe_fds[1], pipe_fds[1]};
    const my_agent::ui::Frame frame{.lines = {{.text = "content"}}};

    EXPECT_FALSE(driver.render(frame));

    std::signal(SIGPIPE, previous);
    ::close(pipe_fds[1]);
}

// 场景：非 tty 上查询尺寸。
// 领域语义：管道没有尺寸，但折行仍然需要一个宽度 —— 返回 0 列会让 wrap 什么都不吐，
// 整个界面空白。所以失败时必须退回一个可用的默认值（80x24 是 VT100 以来的惯例）。
// Red 原因：仓库尚不存在 size()（编译错误）。
TEST(TerminalTest, FallsBackToAUsableSizeWhenTheTerminalHasNone)
{
    const int devnull = ::open("/dev/null", O_WRONLY);
    ASSERT_LE(0, devnull);

    const my_agent::ui::TerminalDriver driver{devnull, devnull};
    const my_agent::ui::Size size = driver.size();

    EXPECT_LT(0, size.columns);
    EXPECT_LT(0, size.rows);

    ::close(devnull);
}

}  // namespace
