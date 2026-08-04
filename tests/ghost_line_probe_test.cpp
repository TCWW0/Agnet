// 幽灵行 pty 复现探针（切片 #12）。
//
// 存在的理由：幽灵行是用户报告的现象，肉眼在 20 行以上的滚动输出里不可靠。
// 这个文件把它变成一条**可复现、可归因**的失败断言，作为后续两片的验收标准。
// 本片刻意**不修任何东西** —— 产出就是这些红。
//
// 三层结构，每层都不可省：
//   1. 真 pty —— 真实的 raw mode、真实的 write、真实的驱动。字节串断言做不到。
//   2. VirtualTerminal —— pty **不解释**转义序列，所以「屏幕上有没有幽灵行」
//      必须把抓到的字节喂进一个会记账的模型。
//   3. unicode_width_oracle —— 官方 Unicode 16.0.0 数据。用生产渲染路径的宽度判据
//      驱动量具，欠算会在两边同时发生、互相抵消，溢出永远量不出来。
//
// 探针自身的验证：断言用哨兵串 GH7ZQ（不可能预先存在），基线在敲键**之前**抓。

#include "my_agent/ui/terminal.hpp"
#include "my_agent/ui/ui_loop.hpp"
#include "virtual_terminal.hpp"

#include <chrono>
#include <cstddef>
#include <string>
#include <thread>

#include <poll.h>
#include <pty.h>
#include <unistd.h>

#include <gtest/gtest.h>

namespace {

// 40 列 x 8 行：足够窄让溢出必然发生，足够宽让失败形态读得出来。
constexpr int kColumns = 40;
constexpr int kRows = 8;

// 哨兵：不可能预先存在于任何一帧里。用途是证明探针抓到的是**我这次输入**产生的
// 那一帧，而不是别的什么东西 —— 上一轮的教训是「断言匹配的文本已经在缓冲区里」
// 这种循环论证在验证代码里特别隐蔽。
//
// 必须放在 payload **尾部**。它证明探针抓到的是本次输入产生的帧，而不是历史缓冲里
// 早就存在的文本；尾部哨兵也能穿过旧的横向裁剪实现和新的 Maya 包装实现。
constexpr std::string_view kSentinel = "GH7ZQ";

// 读 pty 直到 needle 出现或超时。返回是否见到。
[[nodiscard]]
bool read_until(int fd, std::string& sink, std::string_view needle, int seconds)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{seconds};
    while (std::chrono::steady_clock::now() < deadline) {
        if (sink.find(needle) != std::string::npos) {
            return true;
        }
        pollfd probe{.fd = fd, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[8192];
            const ssize_t count = ::read(fd, buffer, sizeof(buffer));
            if (count > 0) {
                sink.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }
    return sink.find(needle) != std::string::npos;
}

// 场景：用户在输入行里粘了一串 emoji（真实场景：从聊天记录或 issue 里复制）。
// 领域语义：输入行是帧的**最后一行**，画在屏幕最末行上。这是幽灵行必然发生的位置 ——
// 中间行溢出时下一行的 CUP 会清掉待换行状态，溢出被同帧治好；而末行溢出**没有下一行**，
// 于是备用屏滚动，此后每一次 CUP 都落在错位的物理行上。
//
// 算术（40 列，提示符 "> " 占 2 列）：
//   真实宽度 2 + 25×2 + 5 = 57 列，比 40 列多 17 列。旧实现会让末行溢出；
//   Maya 迁移后应在 cell canvas 内包装/裁剪，不让终端物理滚动。
//
// Red 原因：char_width(U'✅') 返回 1（成因 3），且 DECAWM 从未关闭（成因 1，
// 全仓库 grep `?7l` 零命中）。两者相乘才有滚动 —— 这也是为什么两片修完才能变绿。
TEST(GhostLineProbeTest, PastingEmojiIntoTheInputLineDoesNotScrollTheAltScreen)
{
    int primary = -1;
    int replica = -1;
    winsize initial{
        .ws_row = static_cast<unsigned short>(kRows),
        .ws_col = static_cast<unsigned short>(kColumns),
        .ws_xpixel = 0,
        .ws_ypixel = 0,
    };
    if (::openpty(&primary, &replica, nullptr, nullptr, &initial) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    // 不需要 provider：输入行不进 Model，本条只测投影与帧字节。
    my_agent::AsyncHost host{[](my_agent::Request, my_agent::EventSink) {}};
    std::thread ui_thread{[&host, replica] {
        my_agent::ui::TerminalDriver terminal{replica, replica};
        static_cast<void>(my_agent::ui::run_ui(host, terminal));
    }};

    // 必须等驱动进 raw mode 才能敲键：tcsetattr 用 TCSAFLUSH，会丢弃此前排队的输入。
    // 备用屏字节写在 tcsetattr 之后，所以它是一个有效的同步点。
    std::string seen;
    ASSERT_TRUE(read_until(primary, seen, "\x1b[?1049h", 5)) << "驱动没能进入全屏";

    // 基线在副作用**之前**抓：哨兵此刻必须不在，否则后面「它出现了」证明不了任何事。
    ASSERT_EQ(std::string::npos, seen.find(kSentinel))
        << "哨兵在敲键之前就已经存在，探针无鉴别力";

    std::string payload;
    for (int index = 0; index < 25; ++index) {
        payload += "\xE2\x9C\x85";  // U+2705 ✅，EastAsianWidth-16.0.0 判定 W（2 列）
    }
    payload += kSentinel;  // 尾部：旧横向裁剪和新 Maya 包装下都可见
    ASSERT_EQ(static_cast<ssize_t>(payload.size()),
              ::write(primary, payload.data(), payload.size()));

    ASSERT_TRUE(read_until(primary, seen, kSentinel, 5)) << "输入行从未上屏";
    // 再多读一会：最后一个 emoji 所在的那一帧可能还在路上，早断言会漏掉溢出。
    static_cast<void>(read_until(primary, seen, "\xFF", 1));

    const char eof = 0x04;
    static_cast<void>(::write(primary, &eof, 1));
    ui_thread.join();
    host.shutdown();
    ::close(replica);
    ::close(primary);

    my_agent::test::VirtualTerminal screen{kColumns, kRows};
    screen.feed(seen);

    ASSERT_TRUE(screen.unhandled().empty())
        << "量具遇到了没记账的序列/码点，断言无从成立：" << screen.unhandled().front();
    ASSERT_TRUE(screen.in_alt_screen()) << "字节流里没有备用屏，抓错了东西";

    EXPECT_EQ(0, screen.right_margin_overruns())
        << "光标越过了右边距 " << screen.right_margin_overruns() << " 次";

    EXPECT_EQ(0, screen.scrolls_in_alt_screen())
        << "备用屏滚动了 " << screen.scrolls_in_alt_screen()
        << " 次 —— Maya 应该在自己的 cell canvas 内处理长输入，而不是让终端物理滚动";
}

// 场景：屏幕已被历史消息占满，此时输入行落在**最末物理行**上并溢出。
// 领域语义：这是上一条不覆盖的那一半，也是三处成因叠加最完整的形态。
// 中间行溢出时，下一行的 CUP 会清掉待换行状态，损害局限在「多占一行」；
// 而末行溢出**没有下一行**可定位 —— 备用屏整体上滚，顶行被顶掉，
// 此后每一次绝对定位都落在错位的物理行上。这才是用户报告的「重复打印」。
//
// 用真 provider（假的流式回答）把帧填满 8 行：文本用纯 ASCII，宽度可预测，
// 保证幽灵行的成因**只有** emoji 那一条，不与折行本身混在一起。
//
// Red 原因：同上一条（成因 1 + 成因 3），但失败形态是滚动而不是多占一行。
TEST(GhostLineProbeTest, OverflowOnTheLastRowDoesNotScrollAwayTheHistory)
{
    int primary = -1;
    int replica = -1;
    winsize initial{
        .ws_row = static_cast<unsigned short>(kRows),
        .ws_col = static_cast<unsigned short>(kColumns),
        .ws_xpixel = 0,
        .ws_ypixel = 0,
    };
    if (::openpty(&primary, &replica, nullptr, nullptr, &initial) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    // 每段 30 个 x，40 列下折成一行；8 段足够把 8 行的帧填满并触发尾部裁剪。
    std::string reply;
    for (int index = 0; index < 8; ++index) {
        reply += std::string(30, 'x');
        reply += ' ';
    }
    my_agent::AsyncHost host{[reply](my_agent::Request, my_agent::EventSink sink) {
        sink(my_agent::Msg{my_agent::StreamTextDelta{.text = reply}});
        sink(my_agent::Msg{my_agent::StreamFinished{}});
    }};

    std::thread ui_thread{[&host, replica] {
        my_agent::ui::TerminalDriver terminal{replica, replica};
        static_cast<void>(my_agent::ui::run_ui(host, terminal));
    }};

    std::string seen;
    ASSERT_TRUE(read_until(primary, seen, "\x1b[?1049h", 5)) << "驱动没能进入全屏";
    ASSERT_EQ(std::string::npos, seen.find(kSentinel))
        << "哨兵在敲键之前就已经存在，探针无鉴别力";

    // 先发一句让 provider 吐出长回答，把屏幕填满。
    const std::string ask = "go\r";
    ASSERT_EQ(static_cast<ssize_t>(ask.size()), ::write(primary, ask.data(), ask.size()));
    ASSERT_TRUE(read_until(primary, seen, std::string(30, 'x'), 5)) << "长回答没上屏";

    // 屏幕填满之后再抓一次基线：这才是 emoji 输入的「之前」。
    const std::size_t baseline = seen.size();

    std::string payload;
    for (int index = 0; index < 25; ++index) {
        payload += "\xE2\x9C\x85";  // U+2705 ✅，官方判定 W（2 列）
    }
    payload += kSentinel;  // 尾部：理由同上一条
    ASSERT_EQ(static_cast<ssize_t>(payload.size()),
              ::write(primary, payload.data(), payload.size()));
    ASSERT_TRUE(read_until(primary, seen, kSentinel, 5)) << "输入行从未上屏";
    static_cast<void>(read_until(primary, seen, "\xFF", 1));
    ASSERT_GT(seen.size(), baseline) << "emoji 输入之后一个字节都没多出来";

    const char eof = 0x04;
    static_cast<void>(::write(primary, &eof, 1));
    ui_thread.join();
    host.shutdown();
    ::close(replica);
    ::close(primary);

    my_agent::test::VirtualTerminal screen{kColumns, kRows};
    screen.feed(seen);

    ASSERT_TRUE(screen.unhandled().empty())
        << "量具遇到了没记账的序列/码点：" << screen.unhandled().front();
    ASSERT_TRUE(screen.in_alt_screen()) << "字节流里没有备用屏，抓错了东西";

    EXPECT_EQ(0, screen.scrolls_in_alt_screen())
        << "备用屏滚动了 " << screen.scrolls_in_alt_screen()
        << " 次 —— 此后每一次 CUP 都落在错位的物理行上，这就是幽灵行";
}

}  // namespace
