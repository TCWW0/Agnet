#include "my_agent/ui/repaint_clock.hpp"

#include <algorithm>

namespace my_agent::ui {

RepaintClock::RepaintClock(int frames_per_second)
    : frame_budget_{
          std::chrono::milliseconds{frames_per_second > 0 ? 1000 / frames_per_second : 0}
      }
{
}

bool RepaintClock::should_paint(Clock::time_point now)
{
    if (last_paint_ && now - *last_paint_ < frame_budget_) {
        pending_ = true;  // 记住这次，由 time_until_next_paint 报出补画时机
        return false;
    }
    last_paint_ = now;
    pending_ = false;
    return true;
}

std::chrono::milliseconds RepaintClock::time_until_next_paint(Clock::time_point now) const
{
    if (!pending_ || !last_paint_) {
        return std::chrono::milliseconds{-1};  // 无事可做：无限等，让出 CPU
    }
    const auto elapsed =
        std::chrono::duration_cast<std::chrono::milliseconds>(now - *last_paint_);
    // 已经过了窗口就返回 0：立刻补画，而不是负数（poll 会当成无限等）。
    return std::max(std::chrono::milliseconds{0}, frame_budget_ - elapsed);
}

}  // namespace my_agent::ui
