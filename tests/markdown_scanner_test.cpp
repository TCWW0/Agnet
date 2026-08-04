#include "my_agent/ui/markdown_scanner.hpp"

#include <gtest/gtest.h>

#include <string>
#include <string_view>
#include <vector>

namespace {

using my_agent::ui::markdown::ScanResult;
using my_agent::ui::markdown::ScanState;

TEST(MarkdownScannerTest, CommitsCompletePlainLinesButLeavesActiveTail)
{
    ScanState state;

    const ScanResult first = my_agent::ui::markdown::scan("hello\nworld", state);

    EXPECT_EQ(6u, first.committed_prefix_length);
    EXPECT_EQ(6u, state.last_boundary);
    EXPECT_EQ(11u, state.scan_position);
    EXPECT_EQ(1u, first.newly_committed_boundaries.size());
    EXPECT_EQ(6u, first.newly_committed_boundaries.front());
}

TEST(MarkdownScannerTest, DoesNotCommitAnUnclosedFence)
{
    ScanState state;

    const ScanResult result = my_agent::ui::markdown::scan(
        "intro\n```cpp\nreturn 0;\n", state
    );

    EXPECT_EQ(6u, result.committed_prefix_length);
    EXPECT_TRUE(state.in_fence);
    EXPECT_FALSE(state.fence_safe_to_commit);
    ASSERT_EQ(1u, result.newly_committed_boundaries.size());
    EXPECT_EQ(6u, result.newly_committed_boundaries.front());
}

TEST(MarkdownScannerTest, CommitsTheWholeFenceOnlyAfterItsClosingLine)
{
    ScanState state;
    std::string accumulated = "intro\n```cpp\nreturn 0;\n";

    static_cast<void>(my_agent::ui::markdown::scan(accumulated, state));
    accumulated += "```\nnext\n";
    const ScanResult result = my_agent::ui::markdown::scan(accumulated, state);

    EXPECT_EQ(32u, result.committed_prefix_length);
    EXPECT_FALSE(state.in_fence);
    EXPECT_TRUE(state.fence_safe_to_commit);
    ASSERT_EQ(2u, result.newly_committed_boundaries.size());
    EXPECT_EQ(27u, result.newly_committed_boundaries.at(0));
    EXPECT_EQ(32u, result.newly_committed_boundaries.at(1));
}

TEST(MarkdownScannerTest, ChunkingDoesNotChangeCommittedBoundarySequence)
{
    const auto collect_boundaries = [](const std::vector<std::string>& chunks) {
        ScanState state;
        std::string accumulated;
        std::vector<std::size_t> boundaries;
        for (const std::string& chunk : chunks) {
            accumulated += chunk;
            const ScanResult result = my_agent::ui::markdown::scan(
                accumulated, state
            );
            boundaries.insert(
                boundaries.end(),
                result.newly_committed_boundaries.begin(),
                result.newly_committed_boundaries.end()
            );
        }
        return boundaries;
    };

    const std::vector<std::size_t> expected{4u, 23u, 27u};
    EXPECT_EQ(
        expected,
        collect_boundaries({
            "one\n", "```py\n", "print(1)\n", "```\n", "two\n"
        })
    );
    EXPECT_EQ(
        expected,
        collect_boundaries({"one\n```py\nprint(1)\n", "```\ntwo\n"})
    );
}

TEST(MarkdownScannerTest, ScansNewBytesOnceAndDoesNothingOnRepeatedFrames)
{
    ScanState state;
    std::string accumulated = "first\nsecond";

    static_cast<void>(my_agent::ui::markdown::scan(accumulated, state));
    EXPECT_EQ(accumulated.size(), state.scan_position);

    accumulated += "\nthird";
    const ScanResult second = my_agent::ui::markdown::scan(accumulated, state);
    EXPECT_EQ(accumulated.size(), state.scan_position);
    EXPECT_EQ(13u, second.committed_prefix_length);

    const ScanResult repeated = my_agent::ui::markdown::scan(accumulated, state);
    EXPECT_TRUE(repeated.newly_committed_boundaries.empty());
    EXPECT_EQ(accumulated.size(), state.scan_position);
    EXPECT_EQ(13u, repeated.committed_prefix_length);
}

TEST(MarkdownScannerTest, FinishCommitsACompleteTrailingLineWithoutNewline)
{
    ScanState state;

    const ScanResult result = my_agent::ui::markdown::finish(
        "final line", state
    );

    EXPECT_EQ(10u, result.committed_prefix_length);
    EXPECT_FALSE(state.in_fence);
    EXPECT_EQ(10u, state.last_boundary);
}

TEST(MarkdownScannerTest, FinishStillWithholdsAnUnclosedFence)
{
    ScanState state;

    const ScanResult result = my_agent::ui::markdown::finish(
        "```cpp\nreturn 0;", state
    );

    EXPECT_EQ(0u, result.committed_prefix_length);
    EXPECT_TRUE(state.in_fence);
    EXPECT_FALSE(state.fence_safe_to_commit);
}

}  // namespace
