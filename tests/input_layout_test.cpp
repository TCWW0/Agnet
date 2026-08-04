#include "my_agent/ui/input_layout.hpp"

#include <gtest/gtest.h>

namespace {

using my_agent::ui::InputLayout;
using my_agent::ui::layout_input;

TEST(InputLayoutTest, WrapsThePromptAndReportsTheWrappedCursor)
{
    const InputLayout layout = layout_input(
        "0123456789abcdef", std::string::npos, 10
    );

    ASSERT_EQ(2u, layout.lines.size());
    EXPECT_EQ("> 01234567", layout.lines[0]);
    EXPECT_EQ("89abcdef", layout.lines[1]);
    EXPECT_EQ(1u, layout.cursor_line);
    EXPECT_EQ(8, layout.cursor_column);
}

TEST(InputLayoutTest, KeepsWideCharactersWholeWhenWrapping)
{
    const InputLayout layout = layout_input("a你b", 4, 5);

    ASSERT_EQ(2u, layout.lines.size());
    EXPECT_EQ("> a你", layout.lines[0]);
    EXPECT_EQ("b", layout.lines[1]);
    EXPECT_EQ(1u, layout.cursor_line);
    EXPECT_EQ(0, layout.cursor_column);
}

TEST(InputLayoutTest, ReportsCursorRowAndColumnAcrossLogicalLines)
{
    const InputLayout layout = layout_input("first\nsecond", 8, 20);

    ASSERT_EQ(2u, layout.lines.size());
    EXPECT_EQ("> first", layout.lines[0]);
    EXPECT_EQ("second", layout.lines[1]);
    EXPECT_EQ(1u, layout.cursor_line);
    EXPECT_EQ(2, layout.cursor_column);
}

TEST(InputLayoutTest, AddsAContinuationRowForAnEndCursorAtTheRightEdge)
{
    const InputLayout layout = layout_input("12345678", std::string::npos, 10);

    ASSERT_EQ(2u, layout.lines.size());
    EXPECT_EQ("> 12345678", layout.lines[0]);
    EXPECT_TRUE(layout.lines[1].empty());
    EXPECT_EQ(1u, layout.cursor_line);
    EXPECT_EQ(0, layout.cursor_column);
}

}  // namespace
