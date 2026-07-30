#include "my_agent/domain/conversation.hpp"

#include <string>
#include <variant>

namespace my_agent{
    bool ToolCall::is_pending() const noexcept
    {
        return std::holds_alternative<Pending>(status);
    }

    const std::string& ToolCall::output() const noexcept
    {
        static const std::string empty;
        if (const auto* done = std::get_if<Done>(&status)) {
            return done->output;
        }
        if (const auto* failed = std::get_if<Failed>(&status)) {
            return failed->output;
        }
        return empty;
    }
}// namespace my_agent
