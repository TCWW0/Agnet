#include "my_agent/ui/text_width.hpp"

#include <string>
#include <vector>

#include <gtest/gtest.h>

namespace {

// 场景：纯 ASCII 文本量宽度。
// 领域语义：显示宽度的单位是**终端列**，不是字节也不是码点。ASCII 是三者恰好
// 相等的特例，所以它是这个 seam 最基础的锚点 —— 后面的宽字符测试全部相对它定义。
// Red 原因：仓库尚不存在 ui::display_width（编译错误）。
TEST(TextWidthTest, AsciiWidthEqualsCharacterCount)
{
    EXPECT_EQ(5, my_agent::ui::display_width("hello"));
}

// 场景：中日韩表意文字。
// 领域语义：一个汉字在终端里占 2 列，而它的 UTF-8 编码是 3 字节。这条测试锁死
// 「按字节量宽度」这个最容易犯的错 —— 那会让 4 个字算成 12 列，边框错位 8 列。
// Red 原因：当前实现直接返回 text.size()，会得到 12 而不是 8。
TEST(TextWidthTest, CjkIdeographsAreTwoColumnsWide)
{
    EXPECT_EQ(8, my_agent::ui::display_width("你好世界"));
}

// 场景：宽字符恰好卡在列宽边界上。
// 领域语义：这是 TUI 里唯一会**损坏数据**的折行错误。宽 3 列时「你好」占 4 列，
// 天真实现会在第 3 列处切开 —— 而第 3 列落在「好」这个字的 3 个字节中间，
// 切出来的两半都不是合法 UTF-8，终端显示成乱码方块。正确行为是把整个字推到下一行，
// 宁可留一列空白。
// Red 原因：仓库尚不存在 ui::wrap（编译错误）。
TEST(TextWidthTest, WrapNeverSplitsAWideCharacterAcrossLines)
{
    const std::vector<std::string> lines = my_agent::ui::wrap("你好", 3);

    ASSERT_EQ(2u, lines.size());
    EXPECT_EQ("你", lines[0]);
    EXPECT_EQ("好", lines[1]);
}

// 场景：英文句子折行。
// 领域语义：拉丁文字靠空格分词，从单词中间断开会显著降低可读性
// （"hello world" 折成 "hello wo" / "rld"）。所以有空格可断时应该在空格处断，
// 并且不要把那个空格留在行尾 —— 行尾空格在有背景色的终端里会显示成一块脏色。
// CJK 不需要这个规则（任何字之间都可断），所以这条只约束有空格的情况。
// Red 原因：当前实现逐字符填满即断，会得到 "hello wo" / "rld"。
TEST(TextWidthTest, WrapBreaksAtWordBoundariesForLatinText)
{
    const std::vector<std::string> lines = my_agent::ui::wrap("hello world", 8);

    ASSERT_EQ(2u, lines.size());
    EXPECT_EQ("hello", lines[0]);
    EXPECT_EQ("world", lines[1]);
}

// 场景：宽字符根本放不进给定列宽（极窄终端）。
// 领域语义：一个 2 列的字放不进 1 列，此时没有正确答案，只有可接受的失败方式。
// 必须锁住两条：**不能死循环**（放不下就不推进的实现会挂死渲染线程），
// **不能丢字**（宁可溢出一列，也不能静默吞掉用户的文本）。选择溢出。
// 这是一条 characterization 测试 —— 不是 Red 驱动出来的，而是探查现有行为后
// 把它固定下来，防止日后"顺手优化"成丢字或挂死。
TEST(TextWidthTest, WrapEmitsWideCharacterEvenWhenItCannotFit)
{
    const std::vector<std::string> lines = my_agent::ui::wrap("你好", 1);

    ASSERT_EQ(2u, lines.size());
    EXPECT_EQ("你", lines[0]);
    EXPECT_EQ("好", lines[1]);
}

}  // namespace
