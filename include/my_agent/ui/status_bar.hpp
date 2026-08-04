#pragma once

#include "my_agent/ui/style.hpp"

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace my_agent::ui {

enum class StatusPhase {
    Idle,
    Streaming,
    ExecutingTool,
    AwaitingPermission,
};

struct StatusBarInput {
    StatusPhase phase{StatusPhase::Idle};
    std::string tool_name;
    std::string permission_effect;
    std::string permission_args;
    std::string model_name;
    std::optional<std::size_t> context_used;
    std::optional<std::size_t> context_limit;
    std::optional<double> tokens_per_second;
    std::optional<double> elapsed_seconds;
};

enum class StatusSegmentKind {
    Activity,
    Throughput,
    Elapsed,
    Model,
    ContextBar,
    ContextCount,
};

struct StatusSegment {
    StatusSegmentKind kind;
    std::string text;
    int keep{0};
    bool always{false};
    StyleColor foreground{StyleColor::Default};
};

struct StatusBar {
    std::vector<StatusSegment> segments;
};

[[nodiscard]]
StatusBar build_status_bar(const StatusBarInput& input);

[[nodiscard]]
std::string plain_status_text(const StatusBar& bar);

}  // namespace my_agent::ui
