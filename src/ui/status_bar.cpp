#include "my_agent/ui/status_bar.hpp"

#include <algorithm>
#include <iomanip>
#include <limits>
#include <sstream>
#include <utility>

namespace my_agent::ui {

namespace {

std::string decimal(double value, int precision)
{
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(precision) << value;
    return stream.str();
}

StatusSegment activity_segment(const StatusBarInput& input)
{
    switch (input.phase) {
        case StatusPhase::Streaming:
            return {
                .kind = StatusSegmentKind::Activity,
                .text = "▌ thinking",
                .keep = std::numeric_limits<int>::max(),
                .always = true,
                .foreground = StyleColor::Accent,
            };
        case StatusPhase::ExecutingTool:
            return {
                .kind = StatusSegmentKind::Activity,
                .text = "▌ running " + (input.tool_name.empty()
                    ? std::string{"tool"}
                    : input.tool_name),
                .keep = std::numeric_limits<int>::max(),
                .always = true,
                .foreground = StyleColor::Success,
            };
        case StatusPhase::AwaitingPermission:
        {
            std::string text = "▌ allow " + (input.tool_name.empty()
                ? std::string{"tool"}
                : input.tool_name);
            if (!input.permission_effect.empty()
                || !input.permission_args.empty()) {
                text += "? effect="
                    + (input.permission_effect.empty()
                        ? std::string{"none"}
                        : input.permission_effect)
                    + " args: "
                    + (input.permission_args.empty()
                        ? std::string{"{}"}
                        : input.permission_args)
                    + " [y/n]";
            }
            return {
                .kind = StatusSegmentKind::Activity,
                .text = std::move(text),
                .keep = std::numeric_limits<int>::max(),
                .always = true,
                .foreground = StyleColor::Warning,
            };
        }
        case StatusPhase::Idle:
            return {
                .kind = StatusSegmentKind::Activity,
                .text = "▌ ready",
                .keep = std::numeric_limits<int>::max(),
                .always = true,
                .foreground = StyleColor::Muted,
            };
    }
    return {};
}

std::string context_bar(std::size_t used, std::size_t limit)
{
    constexpr std::size_t kCells = 10;
    const std::size_t filled = limit == 0
        ? 0
        : std::min(kCells, (used * kCells + limit - 1) / limit);
    std::string result{"· ctx ["};
    for (std::size_t index = 0; index < filled; ++index) {
        result += "\xE2\x96\x88";
    }
    for (std::size_t index = filled; index < kCells; ++index) {
        result += "\xC2\xB7";
    }
    result += ']';
    return result;
}

}  // namespace

StatusBar build_status_bar(const StatusBarInput& input)
{
    StatusBar result;
    result.segments.push_back(activity_segment(input));

    if (input.tokens_per_second) {
        result.segments.push_back(StatusSegment{
            .kind = StatusSegmentKind::Throughput,
            .text = "· " + decimal(*input.tokens_per_second, 1) + " tok/s",
            .keep = 1,
            .foreground = StyleColor::Accent,
        });
    }

    if (input.elapsed_seconds) {
        result.segments.push_back(StatusSegment{
            .kind = StatusSegmentKind::Elapsed,
            .text = "· " + decimal(*input.elapsed_seconds, 1) + "s",
            .keep = 2,
            .foreground = StyleColor::Muted,
        });
    }

    if (!input.model_name.empty()) {
        result.segments.push_back(StatusSegment{
            .kind = StatusSegmentKind::Model,
            .text = "· model " + input.model_name,
            .keep = 3,
            .foreground = StyleColor::Primary,
        });
    }

    if (input.context_used && input.context_limit && *input.context_limit > 0) {
        result.segments.push_back(StatusSegment{
            .kind = StatusSegmentKind::ContextBar,
            .text = context_bar(*input.context_used, *input.context_limit),
            .keep = 4,
            .foreground = StyleColor::Info,
        });
    }

    if (input.context_used) {
        const std::string limit = input.context_limit
            ? "/" + std::to_string(*input.context_limit)
            : std::string{};
        result.segments.push_back(StatusSegment{
            .kind = StatusSegmentKind::ContextCount,
            .text = "· ctx " + std::to_string(*input.context_used) + limit,
            .keep = 5,
            .foreground = StyleColor::Info,
        });
    }

    return result;
}

std::string plain_status_text(const StatusBar& bar)
{
    std::string result;
    for (const StatusSegment& segment : bar.segments) {
        if (!result.empty()) {
            result += ' ';
        }
        result += segment.text;
    }
    return result;
}

}  // namespace my_agent::ui
