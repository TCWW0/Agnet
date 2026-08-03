#include "my_agent/ui/ui_loop.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <string>
#include <thread>
#include <variant>

#include <fcntl.h>
#include <poll.h>
#include <pty.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <gtest/gtest.h>

namespace {

using my_agent::ui::apply_key;
using my_agent::ui::Key;
using my_agent::ui::KeyOutcome;
using my_agent::ui::UiState;

// 场景：Idle 时敲字然后回车。
// 领域语义：输入行的编辑完全属于前端 —— 只有回车才产生一条领域事件。这是
// 「UiState 不进 Model」这个分层决定的可执行版本：敲了 5 个字符只有第 6 次
// 按键（回车）跨越边界，而不是 6 次都进 update()。回车后输入行必须清空，
// 否则下一句会带着上一句的残留。
// Red 原因：仓库尚不存在 ui::apply_key（编译错误）。
TEST(UiLoopTest, OnlyEnterCrossesIntoTheDomainAndItClearsTheInputLine)
{
    UiState ui;
    my_agent::Model model;

    for (const char letter : std::string{"hello"}) {
        const KeyOutcome outcome =
            apply_key(Key{.kind = Key::Kind::Text, .text = std::string(1, letter)}, ui, model);
        EXPECT_FALSE(outcome.msg.has_value()) << "编辑不该产生领域事件";
    }
    ASSERT_EQ("hello", ui.input);

    const KeyOutcome outcome = apply_key(Key{.kind = Key::Kind::Enter}, ui, model);
    ASSERT_TRUE(outcome.msg.has_value());
    EXPECT_TRUE(ui.input.empty()) << "回车后必须清空，否则下一句带着残留";
}

// 场景：AwaitingPermission 时按 y / n。
// 领域语义：同一个按键在不同 phase 下含义不同 —— 这正是 apply_key 需要看 model 的
// 唯一理由。审批期间 'y' 是批准而不是往输入行插入字母 'y'。批准/拒绝必须带上
// pending_permission 的 id：审批的对象是某一次具体调用，用错 id 会批准另一个工具。
// Red 原因：当前实现无视 phase，'y' 会被当成文本插进输入行。
TEST(UiLoopTest, InterpretsYesAndNoAsApprovalOnlyWhileAwaitingPermission)
{
    my_agent::Model model;
    model.phase = my_agent::AwaitingPermission{};
    model.pending_permission = my_agent::PendingPermission{.id = "call_7f3a"};

    UiState approve_ui;
    const KeyOutcome approved =
        apply_key(Key{.kind = Key::Kind::Text, .text = "y"}, approve_ui, model);
    ASSERT_TRUE(approved.msg.has_value());
    ASSERT_TRUE(std::holds_alternative<my_agent::PermissionApprove>(*approved.msg));
    EXPECT_EQ("call_7f3a", std::get<my_agent::PermissionApprove>(*approved.msg).id);
    EXPECT_TRUE(approve_ui.input.empty()) << "审批期间的按键不该进输入行";

    UiState reject_ui;
    const KeyOutcome rejected =
        apply_key(Key{.kind = Key::Kind::Text, .text = "n"}, reject_ui, model);
    ASSERT_TRUE(rejected.msg.has_value());
    ASSERT_TRUE(std::holds_alternative<my_agent::PermissionReject>(*rejected.msg));
    EXPECT_EQ("call_7f3a", std::get<my_agent::PermissionReject>(*rejected.msg).id);

    // Idle 时同一个键仍然是普通文本。
    UiState idle_ui;
    const my_agent::Model idle;
    const KeyOutcome typed =
        apply_key(Key{.kind = Key::Kind::Text, .text = "y"}, idle_ui, idle);
    EXPECT_FALSE(typed.msg.has_value());
    EXPECT_EQ("y", idle_ui.input);
}

// 场景：删掉一个汉字。
// 领域语义：退格删的是**字符**而不是字节。按字节删会在输入行里留下 2 个残缺字节，
// 屏幕显示成乱码方块，而且再按一次退格也删不干净 —— 这是中文输入下必然遇到的 bug。
// Red 原因：当前实现完全没处理 Backspace。
TEST(UiLoopTest, BackspaceDeletesAWholeCharacterNotAByte)
{
    UiState ui{.input = "你好"};
    const my_agent::Model model;

    const KeyOutcome outcome = apply_key(Key{.kind = Key::Kind::Backspace}, ui, model);

    EXPECT_FALSE(outcome.msg.has_value());
    EXPECT_EQ("你", ui.input);  // 而不是 "你" 加两个残缺字节
}

// 场景：输入行为空时按退格。
// 领域语义：没有正确答案，只有可接受的失败方式 —— 不能越界。空串上 pop_back
// 是未定义行为。characterization：固定成无操作。
TEST(UiLoopTest, BackspaceOnAnEmptyInputLineIsANoOp)
{
    UiState ui;
    const my_agent::Model model;

    const KeyOutcome outcome = apply_key(Key{.kind = Key::Kind::Backspace}, ui, model);

    EXPECT_FALSE(outcome.msg.has_value());
    EXPECT_TRUE(ui.input.empty());
}

// 场景：空输入行上按回车。
// 领域语义：不该发一条空的 Submit —— 那会让模型收到一条空用户消息，浪费一次
// 往返，而且有些 provider 会直接报错。回车在空行上应该什么都不做。
// Red 原因：当前实现无条件发 Submit。
TEST(UiLoopTest, EnterOnAnEmptyLineDoesNotSubmit)
{
    UiState ui;
    const my_agent::Model model;

    const KeyOutcome outcome = apply_key(Key{.kind = Key::Kind::Enter}, ui, model);

    EXPECT_FALSE(outcome.msg.has_value());
}

// 场景：Ctrl-D 与 Ctrl-C。
// 领域语义：这两个是唯一的退出路径，必须被认出来 —— 否则用户只能靠 SIGKILL 退出，
// 而那条路上备用屏和 termios 都还不回去。本切片不做中断（那需要新的 Msg 变体和
// 协作停止），所以 Ctrl-C 也是退出。
// Red 原因：当前实现对这两个键返回空结果，循环不会退出。
TEST(UiLoopTest, CtrlDAndCtrlCRequestQuitSoTheTerminalIsAlwaysRestored)
{
    UiState ui;
    const my_agent::Model model;

    EXPECT_TRUE(apply_key(Key{.kind = Key::Kind::Eof}, ui, model).quit);
    EXPECT_TRUE(apply_key(Key{.kind = Key::Kind::Interrupt}, ui, model).quit);
}

// 场景：非 tty 上启动 UI。
// 领域语义：非 tty（CI、管道、重定向）必须让调用方知道要回退，而不是往文件里吐
// 转义序列。返回 false 就是那个信号。
TEST(UiLoopTest, DeclinesToRunWithoutATtySoTheCallerCanFallBack)
{
    const int devnull = ::open("/dev/null", O_RDWR);
    ASSERT_LE(0, devnull);

    my_agent::ui::TerminalDriver terminal{devnull, devnull};
    my_agent::AsyncHost host{[](my_agent::Request, my_agent::EventSink) {}};

    EXPECT_FALSE(my_agent::ui::run_ui(host, terminal));

    ::close(devnull);
}

// 场景：流式 token 在**回合结束之前**就出现在屏幕上。
// 领域语义：这是整个 issue #10 存在的理由。行式 REPL 实测的缺陷是「敲完回车之后
// 19 秒死寂，然后整段一次性出现」—— 因为 run_until_quiescent 在 phase 是 Streaming
// 时不返回。这条测试断言的正是那个缺陷已被修掉：stream effect 故意**不结束**
// （只发 delta，不发 StreamFinished），所以 run_until_quiescent 永远不会返回；
// 如果屏幕上能看到 delta 的内容，说明重绘发生在流进行中而不是回合结束后。
//
// 用真 pty：这不是能靠字节串断言的东西 —— 要证明的是「在那个时刻已经写到终端上」。
TEST(UiLoopTest, PaintsStreamingTextBeforeTheTurnEnds)
{
    int primary = -1;
    int replica = -1;
    if (::openpty(&primary, &replica, nullptr, nullptr, nullptr) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    // 故意不发 StreamFinished：回合永不结束，只有流中重绘才能让内容上屏。
    // 用 release 而不是 sleep 一个固定时长：断言做完才放 worker 走，既保证
    // 「观察发生在回合结束之前」，又不让测试为一个猜的时长白等。
    std::atomic<bool> release{false};
    my_agent::AsyncHost host{
        [&release](my_agent::Request, my_agent::EventSink sink) {
            sink(my_agent::Msg{my_agent::StreamTextDelta{.text = "STREAMED"}});
            while (!release.load(std::memory_order_acquire)) {
                std::this_thread::sleep_for(std::chrono::milliseconds{5});
            }
        }};

    std::thread ui_thread{[&host, replica] {
        my_agent::ui::TerminalDriver terminal{replica, replica};
        static_cast<void>(my_agent::ui::run_ui(host, terminal));
    }};

    // 必须等驱动进了 raw mode 才能敲键：tcsetattr 用的是 TCSAFLUSH，会丢弃此前
    // 已排队的输入。切备用屏的字节是在 tcsetattr **之后**写的，所以看到它就等于
    // 那次 flush 已经过去了 —— 用它同步，而不是 sleep 一个猜的时长。
    std::string seen;
    const auto ready_by = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < ready_by
           && seen.find("\x1b[?1049h") == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }
    ASSERT_NE(std::string::npos, seen.find("\x1b[?1049h")) << "驱动没能进入全屏";

    // 敲 "hi" + 回车，让 host 进入 Streaming。
    const std::string typed = "hi\r";
    ASSERT_EQ(static_cast<ssize_t>(typed.size()),
              ::write(primary, typed.data(), typed.size()));

    // 读 pty 直到看到 delta 的内容，或超时。
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < deadline
           && seen.find("STREAMED") == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }

    EXPECT_NE(std::string::npos, seen.find("STREAMED"))
        << "流式内容必须在回合结束前就上屏";

    // 断言已经做完，现在才放 worker 走。送 Ctrl-D 让循环退出，然后拆掉 host。
    release.store(true, std::memory_order_release);
    const char eof = 0x04;
    static_cast<void>(::write(primary, &eof, 1));
    ui_thread.join();
    host.shutdown();

    ::close(replica);
    ::close(primary);
}

// 场景：回合已经结束，最后一段文本必须上屏。
// 领域语义：这是上一条测试**不**覆盖的那一半。流进行中每个 delta 都带来一次唤醒，
// 所以哪怕重绘被帧率跳过，下一次唤醒也会把它补上。但 StreamFinished 之后不再有
// 唤醒 —— 如果那一刻的重绘正好落在帧预算内被跳过，就没有任何后续事件来补画，
// 最后一段回答永远停在 inbox 里，屏幕上少一截。RepaintClock 的 pending +
// time_until_next_paint 就是为这个而存在：跳过的重绘必须换来一个有限的 poll 超时。
//
// 用真 pty，并且**故意**让 delta 紧跟 Submit 到达（同一个帧预算内）以逼出那个跳过。
TEST(UiLoopTest, PaintsTheFinalChunkEvenThoughNoWakeFollowsTheEndOfTheStream)
{
    int primary = -1;
    int replica = -1;
    if (::openpty(&primary, &replica, nullptr, nullptr, nullptr) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    // 正常终结的流：发完 delta 立刻 StreamFinished，此后不再有任何唤醒。
    my_agent::AsyncHost host{[](my_agent::Request, my_agent::EventSink sink) {
        sink(my_agent::Msg{my_agent::StreamTextDelta{.text = "LASTCHUNK"}});
        sink(my_agent::Msg{my_agent::StreamFinished{}});
    }};

    std::thread ui_thread{[&host, replica] {
        my_agent::ui::TerminalDriver terminal{replica, replica};
        static_cast<void>(my_agent::ui::run_ui(host, terminal));
    }};

    std::string seen;
    const auto ready_by = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < ready_by
           && seen.find("\x1b[?1049h") == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }
    ASSERT_NE(std::string::npos, seen.find("\x1b[?1049h")) << "驱动没能进入全屏";

    const std::string typed = "hi\r";
    ASSERT_EQ(static_cast<ssize_t>(typed.size()),
              ::write(primary, typed.data(), typed.size()));

    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < deadline
           && seen.find("LASTCHUNK") == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }

    EXPECT_NE(std::string::npos, seen.find("LASTCHUNK"))
        << "回合结束后不再有唤醒，被帧率跳过的那一帧必须靠 poll 超时补画";

    const char eof = 0x04;
    static_cast<void>(::write(primary, &eof, 1));
    ui_thread.join();
    host.shutdown();

    ::close(replica);
    ::close(primary);
}

// 场景：拖动窗口改变终端宽度，不碰键盘。
// 领域语义：折行宽度来自终端，宽度变了屏幕上的每一行都算错了 —— 变窄时文字被
// 截掉，变宽时留着一堆无用的换行。此时**没有任何键盘或后台事件**，poll 正阻塞着，
// 所以必须由 SIGWINCH 自己把循环叫醒。实测过当前实现：TIOCSWINSZ 之后 pty 上
// 一个字节都没有，屏幕一直停在旧宽度，直到用户碰巧按了别的键才刷新。
// Red 原因：仓库尚未安装 SIGWINCH 处理器（默认是忽略），循环收不到通知。
TEST(UiLoopTest, ReflowsOnTerminalResizeWithoutWaitingForAKeypress)
{
    int primary = -1;
    int replica = -1;
    winsize initial{.ws_row = 24, .ws_col = 80, .ws_xpixel = 0, .ws_ypixel = 0};
    if (::openpty(&primary, &replica, nullptr, nullptr, &initial) != 0) {
        GTEST_SKIP() << "openpty unavailable in this environment";
    }

    // 40 个 A：80 列时一行放得下，20 列时必须折成多行。宽度是否被重新读取，
    // 看的就是屏幕上一行到底有多少个 A。
    const std::string wide_text(40, 'A');
    my_agent::AsyncHost host{[wide_text](my_agent::Request, my_agent::EventSink sink) {
        sink(my_agent::Msg{my_agent::StreamTextDelta{.text = wide_text}});
        sink(my_agent::Msg{my_agent::StreamFinished{}});
    }};

    std::thread ui_thread{[&host, replica] {
        my_agent::ui::TerminalDriver terminal{replica, replica};
        static_cast<void>(my_agent::ui::run_ui(host, terminal));
    }};

    std::string seen;
    const auto ready_by = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < ready_by
           && seen.find("\x1b[?1049h") == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }
    ASSERT_NE(std::string::npos, seen.find("\x1b[?1049h")) << "驱动没能进入全屏";

    // 先确认 80 列下整段在一行里 —— 否则后面「变窄了」的断言无从对比。
    const std::string typed = "hi\r";
    ASSERT_EQ(static_cast<ssize_t>(typed.size()),
              ::write(primary, typed.data(), typed.size()));
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < until
           && seen.find(wide_text) == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                seen.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }
    ASSERT_NE(std::string::npos, seen.find(wide_text)) << "80 列下这段本该在一行里";

    // 变窄，然后只发 SIGWINCH —— 不碰键盘。内核只把这个信号发给 pty 的前台进程组，
    // 测试进程不在其中，所以由测试自己 raise：要证明的是「信号到达后屏幕重排」，
    // 谁投递的信号不属于这条不变量。
    winsize narrow{.ws_row = 24, .ws_col = 20, .ws_xpixel = 0, .ws_ypixel = 0};
    ASSERT_EQ(0, ::ioctl(primary, TIOCSWINSZ, &narrow));
    std::string after;
    ASSERT_EQ(0, ::raise(SIGWINCH));

    const std::string narrow_line(18, 'A');  // 20 列减去 2 列发言人前缀
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds{5};
    while (std::chrono::steady_clock::now() < deadline
           && after.find(narrow_line) == std::string::npos) {
        pollfd probe{.fd = primary, .events = POLLIN, .revents = 0};
        if (::poll(&probe, 1, 200) > 0) {
            char buffer[4096];
            const ssize_t count = ::read(primary, buffer, sizeof(buffer));
            if (count > 0) {
                after.append(buffer, static_cast<std::size_t>(count));
            }
        }
    }

    EXPECT_NE(std::string::npos, after.find(narrow_line))
        << "变窄后必须按新宽度重排，而不是等到下一次按键";
    EXPECT_EQ(std::string::npos, after.find(wide_text))
        << "旧宽度的整行不该再出现在重排后的帧里";

    const char eof = 0x04;
    static_cast<void>(::write(primary, &eof, 1));
    ui_thread.join();
    host.shutdown();

    ::close(replica);
    ::close(primary);
}

}  // namespace
