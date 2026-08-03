#pragma once

#include <chrono>
#include <optional>

namespace my_agent::ui {

// 帧率合并。Ollama 一秒能吐几十个 token，每个都重绘会把时间全花在 write 上，
// 而人眼分辨不出 20fps 以上的差别。
//
// 时间由调用方注入而不是自己读时钟：判定因此是纯的、可确定性测试的 —— 靠 sleep
// 制造时间流逝的测试在负载下会随机失败。
class RepaintClock {
public:
    using Clock = std::chrono::steady_clock;

    explicit RepaintClock(int frames_per_second);

    // 请求一次重绘。返回是否现在就画。窗口内被压掉时会记住这次请求，
    // 由 time_until_next_paint 报出补画的时机 —— 合并是延迟而不是丢弃。
    [[nodiscard]]
    bool should_paint(Clock::time_point now);

    // poll 的超时。有待补的更新时返回到下个窗口边界的剩余时间；无事可做时返回
    // -1（无限等），这是空闲时占 0% CPU 与占满一核的分界。
    [[nodiscard]]
    std::chrono::milliseconds time_until_next_paint(Clock::time_point now) const;

private:
    std::chrono::milliseconds frame_budget_;
    std::optional<Clock::time_point> last_paint_;
    bool pending_{false};  // 窗口内被压掉、还没补上的更新
};

}  // namespace my_agent::ui
