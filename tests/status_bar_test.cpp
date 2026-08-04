#include "my_agent/ui/status_bar.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <string>

namespace {

const my_agent::ui::StatusSegment& segment_named(
    const my_agent::ui::StatusBar& bar,
    my_agent::ui::StatusSegmentKind kind
)
{
    const auto found = std::find_if(
        bar.segments.begin(),
        bar.segments.end(),
        [kind](const my_agent::ui::StatusSegment& segment) {
            return segment.kind == kind;
        }
    );
    EXPECT_NE(found, bar.segments.end());
    return *found;
}

}  // namespace

TEST(StatusBarTest, KeepsActivityLastAndUsesTheFixedDegradationRanking)
{
    const my_agent::ui::StatusBar bar = my_agent::ui::build_status_bar({
        .phase = my_agent::ui::StatusPhase::Streaming,
        .tool_name = {},
        .model_name = "qwen3.5:latest",
        .context_used = 4096,
        .context_limit = 8192,
        .tokens_per_second = 12.5,
        .elapsed_seconds = 3.25,
    });

    const auto& throughput = segment_named(
        bar, my_agent::ui::StatusSegmentKind::Throughput
    );
    const auto& elapsed = segment_named(
        bar, my_agent::ui::StatusSegmentKind::Elapsed
    );
    const auto& model = segment_named(
        bar, my_agent::ui::StatusSegmentKind::Model
    );
    const auto& context_bar = segment_named(
        bar, my_agent::ui::StatusSegmentKind::ContextBar
    );
    const auto& context_count = segment_named(
        bar, my_agent::ui::StatusSegmentKind::ContextCount
    );
    const auto& activity = segment_named(
        bar, my_agent::ui::StatusSegmentKind::Activity
    );

    EXPECT_LT(throughput.keep, elapsed.keep);
    EXPECT_LT(elapsed.keep, model.keep);
    EXPECT_LT(model.keep, context_bar.keep);
    EXPECT_LT(context_bar.keep, context_count.keep);
    EXPECT_TRUE(activity.always);
    EXPECT_NE(std::string::npos, activity.text.find("thinking"));
    EXPECT_NE(std::string::npos, throughput.text.find("12.5"));
    EXPECT_NE(std::string::npos, context_count.text.find("4096"));
}

