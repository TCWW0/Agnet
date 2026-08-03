#include "my_agent/ui/ui_loop.hpp"

#include "my_agent/ui/repaint_clock.hpp"

#include <cerrno>
#include <chrono>
#include <cstddef>
#include <string_view>
#include <variant>

#include <poll.h>
#include <unistd.h>

namespace my_agent::ui {

namespace {

// 20fps：人眼分辨不出更高的刷新，而 Ollama 一秒能吐几十个 token。
constexpr int kFramesPerSecond = 20;

// 唤醒机制降级成惰性哨兵时的轮询周期。此时没有 fd 可等，只能定期 drain ——
// 比永久挂死好，比忙轮询省。
constexpr int kSentinelPollMs = 50;

}  // namespace

KeyOutcome apply_key(const Key& key, UiState& ui, const Model& model)
{
    // 审批期间按键改变含义：这是 apply_key 需要看 model 的唯一理由。
    // id 取自 pending_permission —— 审批的对象是某一次具体调用，用错 id 会批准
    // 另一个工具。没有 pending id 时按键落回普通文本，而不是发一条无主的批准。
    if (std::holds_alternative<AwaitingPermission>(model.phase) && model.pending_permission
        && key.kind == Key::Kind::Text) {
        const std::string& id = model.pending_permission->id;
        if (key.text == "y" || key.text == "Y") {
            return KeyOutcome{.msg = Msg{PermissionApprove{.id = id}}};
        }
        if (key.text == "n" || key.text == "N") {
            return KeyOutcome{.msg = Msg{PermissionReject{.id = id}}};
        }
        return {};  // 其他键在审批期间无意义，不该插进输入行
    }

    switch (key.kind) {
        case Key::Kind::Text:
            ui.input += key.text;
            return {};

        case Key::Kind::Enter: {
            // 空行不发 Submit：模型会收到一条空用户消息，白跑一次往返，
            // 有些 provider 还会直接报错。
            if (ui.input.empty()) {
                return {};
            }
            Msg msg = Submit{.text = ui.input};
            ui.input.clear();  // 不清会让下一句带着上一句的残留
            return KeyOutcome{.msg = std::move(msg)};
        }

        case Key::Kind::Backspace:
            // 往前退到字符边界（续字节高两位是 10）。按字节删会在输入行里留下
            // 残缺字节，显示成乱码方块，而且再按一次也删不干净。
            while (!ui.input.empty()) {
                const auto byte = static_cast<unsigned char>(ui.input.back());
                ui.input.pop_back();
                if ((byte & 0xC0) != 0x80) {
                    break;  // 删到前导字节为止
                }
            }
            return {};

        case Key::Kind::Eof:
        case Key::Kind::Interrupt:
            // 唯一的退出路径。不认这两个键，用户只能 SIGKILL —— 那条路上
            // 备用屏和 termios 都还不回去。
            return KeyOutcome{.quit = true};
    }
    return {};
}

bool run_ui(AsyncHost& host, TerminalDriver& terminal)
{
    if (!terminal.is_tty()) {
        return false;  // 调用方回退到行式 REPL
    }

    UiState ui;
    InputDecoder decoder;
    RepaintClock clock{kFramesPerSecond};

    // 开局先画一帧：否则屏幕在用户敲第一个键之前是空的。
    static_cast<void>(clock.should_paint(RepaintClock::Clock::now()));
    static_cast<void>(terminal.render(view(host.model(), ui, terminal.size())));

    const int wake_fd = host.wake_fd();
    // 键盘 fd 由驱动给出，不能假定 STDIN_FILENO —— 假定会让驱动持有的 fd 被彻底忽略，
    // 于是按键永远读不到（在 pty 上实测过：只画出提示符，敲进去的字节没人取）。
    const int keyboard_fd = terminal.input_fd();
    bool running = true;
    while (running) {
        // drain -> paint -> poll。
        // drain 必须在 poll 之前：唤醒是电平合并的，若不先消费掉已到达的消息，
        // 「消息已在 inbox 但唤醒已被消费」会让 poll 白等一个超时周期。
        // paint 在 drain 之后画的是刚 drain 出来的状态，事件于是在**本轮**上屏；
        // 这是延迟而非正确性 —— 实测把两者换序，流式测试依然通过，因为跳过的
        // 重绘会置上 pending，poll 因此拿到有限超时并在一个帧预算内补画。
        // 兜底在 RepaintClock，顺序只决定落后一帧还是两帧。
        host.drain_inbox();

        if (clock.should_paint(RepaintClock::Clock::now())) {
            static_cast<void>(terminal.render(view(host.model(), ui, terminal.size())));
        }

        pollfd fds[2] = {
            {.fd = keyboard_fd, .events = POLLIN, .revents = 0},
            {.fd = wake_fd, .events = POLLIN, .revents = 0},
        };
        // wake_fd < 0 是惰性哨兵（eventfd 与自管道都失败）。此时只 poll stdin，
        // 并强制一个有限超时，靠轮询 drain_inbox 继续推进而不是永久挂死。
        const bool has_wake = wake_fd >= 0;
        const std::chrono::milliseconds pending =
            clock.time_until_next_paint(RepaintClock::Clock::now());
        const int timeout = has_wake ? static_cast<int>(pending.count())
                                     : static_cast<int>(kSentinelPollMs);

        const int ready = ::poll(fds, has_wake ? 2 : 1, timeout);
        if (ready < 0) {
            if (errno == EINTR) {
                continue;  // SIGWINCH 等信号打断，重来
            }
            break;
        }

        // 唤醒是电平的：不取走那个计数，POLLIN 就一直亮着，poll 每次立刻返回，
        // 循环退化成忙转（实测 eventfd 不清时空转烧 CPU），而且 poll 的超时从此
        // 失效 —— 帧率补画那条路径被永久短路。0ms 只清信号、不阻塞。
        if (has_wake && (fds[1].revents & POLLIN) != 0) {
            static_cast<void>(host.wait_wake(std::chrono::milliseconds{0}));
        }

        if ((fds[0].revents & POLLIN) != 0) {
            char bytes[512];
            const ssize_t count = ::read(keyboard_fd, bytes, sizeof(bytes));
            if (count > 0) {
                for (const Key& key :
                     decoder.feed(std::string_view{bytes, static_cast<std::size_t>(count)})) {
                    const KeyOutcome outcome = apply_key(key, ui, host.model());
                    if (outcome.quit) {
                        running = false;
                        break;
                    }
                    if (outcome.msg) {
                        host.dispatch(*outcome.msg);
                    }
                }
            } else if (count == 0) {
                running = false;  // stdin 关闭
            }
        }

    }

    return true;
}

}  // namespace my_agent::ui
