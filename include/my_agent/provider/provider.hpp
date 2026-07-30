#pragma once

#include "my_agent/domain/conversation.hpp"
#include "my_agent/runtime/msg.hpp"

#include <functional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace my_agent{
    struct ToolSpec{
        std::string name;
        std::string description;
        nlohmann::json input_schema;
    };

    struct Request{
        std::vector<Message> messages;
        std::vector<ToolSpec> tools;
    };

    using EventSink = std::function<void(Msg)>;
    using StreamEffect = std::function<void(Request,EventSink)>;
}// namespace my_agent
