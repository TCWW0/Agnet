#pragma once

#include <expected>
#include <functional>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "my_agent/tool/effects.hpp"

namespace my_agent::tool {

struct ToolOutput {
    std::string text;
};

enum class ErrorKind {
    InvalidArgs,
    NotFound,
    OutOfWorkspace,
};

struct ToolError {
    ErrorKind kind;
    std::string message;

    [[nodiscard]]
    std::string render() const;
};

using ExecResult = std::expected<ToolOutput, ToolError>;

struct ToolDef {
    std::string name;
    std::string description;
    nlohmann::json input_schema;
    EffectSet effects{};
    std::function<ExecResult(const nlohmann::json&)> execute;
};

[[nodiscard]]
const std::vector<ToolDef>& registry();

[[nodiscard]]
const ToolDef* find(std::string_view name);

[[nodiscard]]
ExecResult execute(std::string_view name, const nlohmann::json& args);

} // namespace my_agent::tool
