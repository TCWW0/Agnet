#include "my_agent/ui/text_width.hpp"

#include "unicode_width_oracle.hpp"

#include <cstddef>
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

// --- 以下是切片 #12 的红色基线：度量现有宽度表的欠算，不修任何东西 -------------
//
// 期望值的真相来源是 Unicode 16.0.0 官方 `EastAsianWidth.txt`（East_Asian_Width
// 属性为 W 或 F 即 2 列），**不是**用与实现相同的方式重算出来的 —— 那样测试按构造
// 必然通过。每条断言下面注明了官方数据里对应的那一行。
//
// 独立第二判据：tmux 3.2a 在 3 列宽的窗口里渲染 `A✅B`，✅ 占掉第 2、3 列，B 被挤到
// 第二行；对照组 `AxB` 不折行。真实终端与官方数据一致，与本实现分歧。

// 场景：emoji presentation 字符的显示宽度。
// 领域语义：头文件已经声称 char_width 对「有 emoji 表现形式的字符」返回 2，
// 而实现里 kWideRanges 根本没有这几个码点 —— 注释是意图，不是事实。
// 这一条锁死那个缺口。欠算是会导致**溢出**的那个方向：模型回答里一个 ✅ 就让
// 后面每一行横向错开一列，而错开的行数随 emoji 个数累积。
// Red 原因：U+2705 落在 {0x2E80,0x303E} 之前、{0x1100,0x115F} 之后的空隙里，
// char_width 走 in_wide_ranges 返回 false，得到 1 而不是 2。
TEST(TextWidthTest, EmojiPresentationCharactersAreTwoColumnsWide)
{
    // EastAsianWidth-16.0.0.txt: `2705 ; W # So WHITE HEAVY CHECK MARK`
    EXPECT_EQ(2, my_agent::ui::char_width(U'✅'));  // ✅
    // `274C ; W # So CROSS MARK`
    EXPECT_EQ(2, my_agent::ui::char_width(U'❌'));  // ❌
    // `1F7E0..1F7EB ; W # So [12] LARGE ORANGE CIRCLE..LARGE BROWN SQUARE`
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U0001F7E2'));  // 🟢
    // `26A1 ; W # So HIGH VOLTAGE SIGN`
    EXPECT_EQ(2, my_agent::ui::char_width(U'⚡'));  // ⚡
    // `2B50 ; W # So WHITE MEDIUM STAR`
    EXPECT_EQ(2, my_agent::ui::char_width(U'⭐'));  // ⭐
}

// 场景：CJK 统一表意文字扩展区（B 区起，U+20000 以上的增补平面）。
// 领域语义：这是欠算里体积最大的一块 —— 官方 W/F 集合共 182,719 个码点，本实现的
// 22 条 range 只覆盖 43,694 个；单是 U+20000..U+2A6DF 一段就漏了 42,720 个。
// 这些字在人名、地名、古籍引用里会真实出现，而漏算的后果和 emoji 完全一样：
// wrap 以为放得下，终端里实际溢出。
// Red 原因：kWideRanges 的最后一条是 {0x1F900,0x1F9FF}，增补平面的表意文字
// 整体不在表内。
TEST(TextWidthTest, CjkExtensionIdeographsBeyondTheBmpAreTwoColumnsWide)
{
    // EastAsianWidth-16.0.0.txt: `20000..2A6DF ; W # Lo [42720] CJK UNIFIED
    // IDEOGRAPH-20000..CJK UNIFIED IDEOGRAPH-2A6DF`（扩展 B）
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U00020000'));
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U0002A6DF'));
    // `2A700..2B739 ; W`（扩展 C）与 `2B820..2CEA1 ; W`（扩展 E）
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U0002A700'));
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U0002B820'));
    // `2CEB0..2EBE0 ; W`（扩展 F，7,473 个码点）
    EXPECT_EQ(2, my_agent::ui::char_width(U'\U0002CEB0'));
}

// 场景：含 emoji 的文本折行后，某一行的真实显示宽度超出了给定列宽。
// 领域语义：这条是把宽度表和幽灵行**连起来**的那一条 —— 前两条只说「量错了」，
// 这条说「量错了会让 wrap 违反它自己的契约」。wrap 承诺返回的每一行都不超过
// columns 列；欠算之下它以为 5 个 ✅ 占 5 列（放得进 6 列），实际占 10 列。
// 超宽行进到终端渲染路径之后就是幽灵行：光标越过右边距 → DECAWM 未关 → 备用屏
// 滚动一行 → 后续所有 CUP 绝对定位落到错位的物理行上。
//
// 宽度用 tests/unicode_width_oracle.hpp 量，不用 display_width —— 用被测函数量
// 被测函数的输出，无论实现对错都会通过。
// Red 原因：char_width(U'✅') 返回 1，wrap 把 5 个 emoji 全塞进一行。
TEST(TextWidthTest, WrapNeverEmitsALineWiderThanTheGivenColumns)
{
    const std::vector<std::string> lines = my_agent::ui::wrap("✅✅✅✅✅", 6);

    ASSERT_FALSE(lines.empty()) << "5 个 emoji 不该一行都不出";
    for (std::size_t index = 0; index < lines.size(); ++index) {
        const int width = my_agent::test::oracle_display_width(lines[index]);
        ASSERT_NE(my_agent::test::kUnknownWidth, width)
            << "判据不认识第 " << index << " 行里的某个码点，断言无从成立";
        EXPECT_LE(width, 6) << "第 " << index << " 行 \"" << lines[index]
                            << "\" 实占 " << width << " 列，超出 6 列的契约";
    }
}

}  // namespace
