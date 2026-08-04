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
//   3. unicode_width_oracle —— 官方 Unicode 16.0.0 数据。用被测的 display_width
//      驱动量具，欠算会在两边同时发生、互相抵消，溢出永远量不出来。
//
// 探针自身的验证：断言用哨兵串 GH7ZQ（不可能预先存在），基线在敲键**之前**抓。

#include "my_agent/ui/terminal.hpp"
#include "my_agent/ui/text_width.hpp"
#include "my_agent/ui/ui_loop.hpp"
#include "unicode_width_oracle.hpp"
#include "virtual_terminal.hpp"

#include <chrono>
#include <cstddef>
#include <string>
#include <thread>
#include <vector>

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
// 必须放在 payload **尾部**。输入行超宽时 tail_within 从头部裁（保留末尾那一段，
// 因为用户正在打的是末尾），放在开头的哨兵会被裁掉 —— 实测过：临时把 U+2705 补进
// 宽度表之后，探针报「输入行从未上屏」而不是报溢出。那种探针依赖欠算才能同步，
// 修好 bug 反而失去鉴别力。
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
// 算术（40 列，提示符 "> " 占 2 列，tail_within 得到 38 列）：
//   欠算之下 display_width("✅"×25) = 25 ≤ 38，整串原样返回；
//   真实宽度 2 + 25×2 = 52 列，比 40 列多 12 列 —— 末行溢出，滚动。
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
    payload += kSentinel;  // 尾部：tail_within 保尾，两种宽度实现下都可见
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

    // 输入行必须**恰好占一个物理行**。这是 view 明写的契约（"它必须恰好一行，
    // 所以超宽时横向滚动而不是折行 —— 折行会让下面所有行号偏移"）。
    // 溢出把它变成两个物理行，于是：帧的行号和屏幕的物理行从此错开，
    // 而 ED(0) 从错位的光标处开始擦，第二个物理行上的残留擦不掉 ——
    // 屏幕上多出一行谁都没打算画的内容，这就是幽灵行。
    const std::vector<std::string> rows = screen.screen();
    int rows_holding_payload = 0;
    for (const std::string& row : rows) {
        if (row.find("\xE2\x9C\x85") != std::string::npos) {
            ++rows_holding_payload;
        }
    }
    EXPECT_EQ(1, rows_holding_payload)
        << "输入行的内容散落在 " << rows_holding_payload
        << " 个物理行上，帧行号与屏幕物理行已错开";
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

// 负向断言（切片 #13 写入）：证明成因 2（无条件 EL）独立于成因 3（宽度欠算）。
//
// 它替换掉 #13 原本写的那条「补齐宽度表后上面两条 pty 探针仍然失败」—— 实测推翻了
// 它：补表之后两条**同时转绿**。欠算正是把行推到右边距的那个力，tail_within 一旦
// 按真实宽度裁剪，输入行就够不到边距，DECAWM 也就没东西可咬。两者是串联的，不是
// 独立的。真正独立于宽度表的是这一条：纯 ASCII，不经过任何宽度判断。
//
// 机制（ECMA-48 §8.3.118）：内容填满至第 W-1 列时光标**停在**那里并置待换行位，
// 不前进到第 W 列。frame_bytes 紧接着发 \x1b[K（EL）从光标处擦到行尾 —— 擦掉的
// 正是刚画上去的最后一格。
//
// 帧里必须有第二行：ED(0) 同样从停在末列的光标处擦起，若填满的行是帧的最后一行，
// ED 会擦掉和 EL 同一格，红就无法归因给 EL。真实帧里输入行永远在最后，填满的行
// 只出现在中间 —— 所以「后面还有一行」也才是真实形态。
//
// 不用 pty：缺陷完全在 frame_bytes 的字节生成里，真驱动只会引入线程与超时的噪声，
// 对这条机制没有额外鉴别力；驱动那一层由上面两条 pty 探针覆盖。
//
// Red 原因：frame_bytes 无条件发 EL。#14 为填满至 W-1 列的行跳过 EL 后转绿。
TEST(GhostLineProbeTest, ALineThatExactlyFillsTheWidthKeepsItsLastCell)
{
    // wrap() 明写「正好填满的那一行是合法的」（判定用 > 而不是 >=），所以这条路径
    // 真实可达。无空格的长串走硬断分支，第一行必然正好填满。
    const std::vector<std::string> wrapped =
        my_agent::ui::wrap(std::string(2 * kColumns, 'x'), kColumns);

    ASSERT_FALSE(wrapped.empty()) << "折行一行都没出";
    ASSERT_EQ(kColumns, my_agent::test::oracle_display_width(wrapped.front()))
        << "第一行没有正好填满，这条探针的前提不成立";

    // 填满的行在中间，后面跟一行输入行 —— 与真实帧的形态一致。
    const my_agent::ui::Frame frame{
        .lines = {{.text = wrapped.front()}, {.text = "> "}},
    };

    my_agent::test::VirtualTerminal screen{kColumns, kRows};
    screen.feed(my_agent::ui::enter_bytes());
    // 传 kColumns：填满行的显示宽度正好等于列数，frame_bytes 据此跳过 EL，
    // 停在末列的光标不再擦掉刚画的最后一格。这正是 #14 的转绿点。
    screen.feed(my_agent::ui::frame_bytes(frame, kColumns));

    ASSERT_TRUE(screen.unhandled().empty())
        << "量具遇到了没记账的序列：" << screen.unhandled().front();

    // 不必再写「未填满时必须照常发 EL」的对照：terminal_test 的
    // ErasesToEndOfEachLineSoLongerPreviousLinesLeaveNoResidue 已经守着那一侧，
    // #14 若图省事直接删掉 EL，那条会变红。
    EXPECT_EQ(wrapped.front(), screen.screen().front())
        << "正好填满整行的那一行少了最后一格 —— EL 从停在第 W-1 列的光标处擦起，"
           "擦掉的正是刚画上去的那个字符";
}

}  // namespace
