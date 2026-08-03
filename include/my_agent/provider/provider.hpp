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

        // 由宿主在 effect 侧填充，不是 update() 填的：构建系统提示要读文件
        // （memory / skills），而 update() 必须保持纯。缺省为空。
        std::string system_prompt;
    };

    using EventSink = std::function<void(Msg)>;
    using StreamEffect = std::function<void(Request,EventSink)>;
}// namespace my_agent
