#pragma once

#include <optional>
#include <string>
#include <variant>
#include <vector>

#include <nlohmann/json.hpp>

namespace my_agent{
    enum class Role{
        User,
        Assistant,
    };

    struct ToolCall{
        struct Pending{};
        struct Done{
            std::string output;
        };
        struct Failed{
            std::string output;
        };
        struct Rejected{
            std::string output;
        };

        using Status = std::variant<Pending,Done,Failed,Rejected>;

        std::string id;
        std::string name;
        nlohmann::json args;
        Status status{Pending{}};

        [[nodiscard]]
        bool is_pending() const noexcept;

        [[nodiscard]]
        const std::string& output() const noexcept;
    };

    // 代表对话记录中的一条消息：谁说的+说了什么
    struct Message{
        Role role;
        std::string text;
        std::optional<std::string> error;
        std::vector<ToolCall> tool_calls;
    };

    // 一个会话线程，由一段完整的有顺序的会话历史所组成
    struct Thread{
        std::vector<Message> messages;
    };

    struct PendingPermission {
        std::string id;
    };
}// namespace my_agent
