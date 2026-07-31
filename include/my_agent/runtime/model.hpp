#pragma once

#include "my_agent/domain/conversation.hpp"
#include "my_agent/domain/profile.hpp"

#include <variant>

namespace my_agent{
    // 明确表示一个Thread的闲置状态
    struct Idle{
    };

    // 表示当前正在等待/接受模型的流式输出
    struct Streaming{
    };

    // 将多个阶段聚合。这样即能够保证一个状态的原子性以及独占性，也能方便管理
    using Phase = std::variant<Idle,Streaming>;

    // 这是对于系统核心的瞬时建模，应该包含的是当前系统的状态信息
    struct Model{
        Phase phase{Idle{}};
        Thread thread{};
        Profile profile{Profile::Write};
    };
}// namespace my_agent
