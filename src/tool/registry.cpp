#include "my_agent/tool/tool.hpp"

#include <cmath>
#include <format>
#include <string>

namespace my_agent::tool {
namespace {

ExecResult execute_calculator(const nlohmann::json& args)
{
    if (!args.is_object()
        || !args.contains("operation")
        || !args["operation"].is_string()
        || !args.contains("left")
        || !args["left"].is_number()
        || !args.contains("right")
        || !args["right"].is_number()) {
        return std::unexpected(ToolError{
            .kind = ErrorKind::InvalidArgs,
            .message = "calculator requires operation, left, and right",
        });
    }

    const std::string operation = args["operation"].get<std::string>();
    if (operation != "multiply") {
        return std::unexpected(ToolError{
            .kind = ErrorKind::InvalidArgs,
            .message = "unsupported calculator operation: " + operation,
        });
    }

    const double value =
        args["left"].get<double>() * args["right"].get<double>();
    if (!std::isfinite(value)) {
        return std::unexpected(ToolError{
            .kind = ErrorKind::InvalidArgs,
            .message = "calculator result is not finite",
        });
    }

    return ToolOutput{.text = std::format("{}", value)};
}

ToolDef calculator()
{
    return ToolDef{
        .name = "calculator",
        .description = "Multiply two numbers.",
        .input_schema = nlohmann::json{
            {"type", "object"},
            {"properties", nlohmann::json{
                {"operation", nlohmann::json{
                    {"type", "string"},
                    {"enum", nlohmann::json::array({"multiply"})},
                }},
                {"left", nlohmann::json{{"type", "number"}}},
                {"right", nlohmann::json{{"type", "number"}}},
            }},
            {"required", nlohmann::json::array({
                "operation",
                "left",
                "right",
            })},
            {"additionalProperties", false},
        },
        .execute = execute_calculator,
    };
}

} // namespace

std::string ToolError::render() const
{
    switch (kind) {
        case ErrorKind::InvalidArgs:
            return "[invalid args] " + message;
        case ErrorKind::NotFound:
            return "[not found] " + message;
    }
    return message;
}

const std::vector<ToolDef>& registry()
{
    static const std::vector<ToolDef> tools{calculator()};
    return tools;
}

const ToolDef* find(std::string_view name)
{
    for (const ToolDef& definition : registry()) {
        if (definition.name == name) {
            return &definition;
        }
    }
    return nullptr;
}

ExecResult execute(std::string_view name, const nlohmann::json& args)
{
    const ToolDef* definition = find(name);
    if (definition == nullptr) {
        return std::unexpected(ToolError{
            .kind = ErrorKind::NotFound,
            .message = "unknown tool: " + std::string{name},
        });
    }
    return definition->execute(args);
}

} // namespace my_agent::tool
