#pragma once

#include "my_agent/domain/profile.hpp"
#include "my_agent/tool/tool.hpp"

#include <optional>
#include <string>
#include <variant>

#include <nlohmann/json.hpp>

namespace my_agent{
    /* 表示一个明确已经发生的事情,eg:用户提交了这段文本，是对于外部事件的一个封装
     * 后续可以继续进行扩展
    */
    struct Submit{
        std::string text;
    };

    struct StreamTextDelta{
        std::string text;
    };

    struct StreamToolCall{
        std::string id;
        std::string name;
        nlohmann::json args;
    };

    struct StreamError{
        std::string message;
    };

    struct ToolExecOutput{
        std::string id;
        tool::ExecResult result;
    };

    struct StreamFinished{
    };

    struct SetProfile{
        Profile profile;
    };

    struct PermissionApprove {
        std::string id;
    };

    struct PermissionReject{
        std::string id;
        std::optional<std::string> feedback{};
    };

    // 一个Agent所能够接受事件的统一入口，注意是事件，当前Submit就是一种简单的文本的提交
    using Msg = std::variant<Submit,StreamTextDelta,StreamToolCall,
        StreamFinished,StreamError,ToolExecOutput,SetProfile,PermissionApprove,
        PermissionReject>;
}// namespace my_agent
