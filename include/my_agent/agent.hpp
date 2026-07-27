#pragma once

#include <string>
#include <variant>
#include <vector>

namespace my_agent{
    enum class Role{
        User,
        Assistant,
    };

    // 代表对话记录中的一条消息：谁说的+说了什么
    struct Message{
        Role role;
        std::string text;
    };

    // 一个会话线程，由一段完整的有顺序的会话历史所组成
    struct Thread{
        std::vector<Message> messages;
    };

    struct Request{
        std::vector<Message> messages;
    };

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
    };

    /* 表示一个明确已经发生的事情,eg:用户提交了这段文本，是对于外部事件的一个封装
     * 后续可以继续进行扩展
    */
    struct Submit{
        std::string text;
    };

    struct StreamTextDelta{
        std::string text;
    };

    struct StreamFinished{
    };

    // 一个Agent所能够接受事件的统一入口，注意是事件，当前Submit就是一种简单的文本的提交
    using Msg = std::variant<Submit,StreamTextDelta,StreamFinished>;

    // agent 核心希望交付给外部的信息，外部可以使用这个结构体中的信息来继续操作
    struct StartStream{
        Request request;
    };

    struct NoCommand{};

    // 从Agent中流转出来的信息，外界后续将只面对这个结构
    using Cmd = std::variant<NoCommand,StartStream>;

    // 语义是 新的内部状态+需要执行的外部指令
    struct Step{
        Model model;
        Cmd cmd;
    };

    // 根据一个 Msg 生成后继 Model 和需要执行的 Cmd。
    // Model 按值传入：调用方可以复制旧快照，也可以通过 std::move()
    // 转移状态所有权。update() 不保留对输入 Model 或 Msg 的引用。
    [[nodiscard]]
    Step update(Model model,Msg msg);
}// namespace my_agent
