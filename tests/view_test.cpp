#include "my_agent/ui/text_width.hpp"
#include "my_agent/ui/view.hpp"

#include <string>
#include <vector>

#include <gtest/gtest.h>

namespace {

my_agent::Model model_with(std::vector<my_agent::Message> messages = {})
{
    my_agent::Model model;
    model.thread.messages = std::move(messages);
    return model;
}

// 场景：一条用户消息投影成帧。
// 领域语义：view 是 Model 的**投影** —— 对话历史必须出现在帧里，否则用户看不到
// 自己说过什么。这是整个渲染层最基本的契约，后面所有测试都相对它定义。
// Red 原因：仓库尚不存在 ui::view（编译错误）。
TEST(ViewTest, RendersUserMessageText)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "hello"},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    bool found = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text.find("hello") != std::string::npos) {
            found = true;
        }
    }
    EXPECT_TRUE(found);
}

// 场景：一问一答两条消息。
// 领域语义：光有文本不够 —— 用户必须能分辨哪句是自己说的、哪句是模型说的。
// 纯文本终端里没有气泡也没有头像，唯一的手段是行首标记。这条测试锁住「每条消息
// 带可区分的说话人前缀」，并且两个角色的前缀不同（否则区分为零）。
// Red 原因：当前实现只推 message.text，两行都没有前缀。
TEST(ViewTest, AttributesEachMessageToItsSpeaker)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "ping"},
        {.role = my_agent::Role::Assistant, .text = "pong"},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    ASSERT_LE(2u, frame.lines.size());
    const std::string& user_line = frame.lines[0].text;
    const std::string& assistant_line = frame.lines[1].text;

    // 前缀 = 消息文本之前的部分。断言两个角色的前缀都非空且互不相同。
    const std::size_t user_at = user_line.find("ping");
    const std::size_t assistant_at = assistant_line.find("pong");
    ASSERT_NE(std::string::npos, user_at);
    ASSERT_NE(std::string::npos, assistant_at);

    const std::string user_prefix = user_line.substr(0, user_at);
    const std::string assistant_prefix = assistant_line.substr(0, assistant_at);
    EXPECT_FALSE(user_prefix.empty());
    EXPECT_FALSE(assistant_prefix.empty());
    EXPECT_NE(user_prefix, assistant_prefix);
}

// 场景：一条比终端宽的消息。
// 领域语义：Frame 的每一行都是**已经能放进终端**的一行。如果 view 把超宽文本原样
// 交出去，终端会自己回卷 —— 那意味着实际占用的行数超出 Frame 的行数，后面所有基于
// 行数的定位（光标落点、滚动、差分）全部失准。所以折行必须发生在 view 里，
// 用的是显示列而不是字节，宽度上界是 columns 减去说话人前缀占的列。
// Red 原因：当前实现直接拼接，长消息会得到一条 60 列的行。
TEST(ViewTest, WrapsMessagesToFitTheGivenWidth)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User,
         .text = "折行必须按显示列算而不是按字节算否则终端会自己回卷"},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 20, .rows = 10}
    );

    ASSERT_LT(1u, frame.lines.size());  // 50 列的文本放不进 20 列，必须折
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        EXPECT_GE(20, my_agent::ui::display_width(line.text)) << line.text;
    }
}

// 场景：模型正在生成，最后一条 assistant 消息还是空的。
// 领域语义：这是整个 TUI 存在的理由。现有行式 REPL 的实测缺陷正是「敲完回车之后
// 19 秒里屏幕一片死寂」—— 用户无法分辨是在思考还是已经卡死。所以 Streaming 期间
// 帧里必须有一处可见的状态提示，且它不能依赖已到达的文本（第一个 token 之前就得有）。
// Red 原因：当前实现只投影 messages，phase 完全没参与投影。
TEST(ViewTest, ShowsWorkInFlightWhileStreaming)
{
    my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "hello"},
        {.role = my_agent::Role::Assistant, .text = ""},
    });
    model.phase = my_agent::Streaming{};

    const my_agent::ui::Frame streaming = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    model.phase = my_agent::Idle{};
    const my_agent::ui::Frame idle = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    // 提示只在 Streaming 时出现：两帧必须不同，否则这个提示没有信息量。
    ASSERT_LT(idle.lines.size(), streaming.lines.size());
    EXPECT_FALSE(streaming.lines.back().text.empty());
}

// 场景：一个待审批的工具调用停在 AwaitingPermission。
// 领域语义：审批的前提是知道自己在批什么。Model 里 PendingPermission 只存一个 id，
// 工具名和参数在最后一条消息的 tool_calls 里 —— 把 id 解析成人类可读的描述正是
// view 的职责（Model 不该为了显示而冗余存一份）。屏幕上只出现一个哈希串就等于
// 逼用户盲批，这是权限闭环里最危险的失效方式。
// Red 原因：当前状态行只有固定的 "... awaiting approval"，不含工具名。
TEST(ViewTest, NamesTheToolAwaitingApproval)
{
    my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "clean up"},
        {.role = my_agent::Role::Assistant,
         .text = "",
         .error = std::nullopt,
         .tool_calls =
             {
                 {.id = "call_7f3a", .name = "bash", .args = {{"command", "rm -rf /"}}},
             }},
    });
    model.phase = my_agent::AwaitingPermission{};
    model.pending_permission = my_agent::PendingPermission{.id = "call_7f3a"};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 60, .rows = 10}
    );

    bool names_tool = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text.find("bash") != std::string::npos) {
            names_tool = true;
        }
    }
    EXPECT_TRUE(names_tool);
}

// 场景：历史比屏幕长。
// 领域语义：屏幕只有 rows 行，Frame 不能比它长 —— 多出来的行终端会顶掉最上面的内容，
// 而被顶掉的是**哪一端**由溢出顺序决定，不受控制。所以裁剪必须在 view 里做，
// 并且保留尾部：最近的消息和状态行是用户当下需要的，最早的消息可以滚上去。
// 反过来保留头部会让屏幕永远停在第一句话上，流式输出完全看不见。
// Red 原因：当前实现无条件推入所有消息，20 条消息会得到 20 行。
TEST(ViewTest, KeepsTheMostRecentLinesWhenHistoryExceedsTheScreen)
{
    std::vector<my_agent::Message> messages;
    for (int index = 0; index < 20; ++index) {
        messages.push_back({
            .role = my_agent::Role::User,
            .text = "line" + std::to_string(index),
        });
    }
    const my_agent::Model model = model_with(std::move(messages));

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 5}
    );

    EXPECT_GE(5u, frame.lines.size());

    bool has_newest = false;
    bool has_oldest = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text.find("line19") != std::string::npos) {
            has_newest = true;
        }
        if (line.text.find("line0") != std::string::npos) {
            has_oldest = true;
        }
    }
    EXPECT_TRUE(has_newest);
    EXPECT_FALSE(has_oldest);
}

// 场景：用户正在打字，还没按回车。
// 领域语义：正在编辑的那行字**不属于领域** —— update() 不关心用户打了一半的东西，
// 它只在提交时看到一条完整的 Submit。所以输入缓冲属于 UiState 而不是 Model，
// 这条测试把这个归属钉死。同时它必须显示在最后一行：光标要落在这里，
// 而终端的光标定位是相对帧的行号算的。
// Red 原因：当前实现完全忽略 ui 参数，输入内容不出现在帧里。
TEST(ViewTest, ShowsTheInputBufferOnTheLastLine)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "earlier"},
    });
    const my_agent::ui::UiState ui{.input = "half-typed"};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, ui, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    ASSERT_FALSE(frame.lines.empty());
    EXPECT_NE(std::string::npos, frame.lines.back().text.find("half-typed"));
}

// 场景：用户打的一行字超过了终端宽度。
// 领域语义：输入行不能像消息那样折成多行 —— 它必须恰好占一行，因为光标落点是按
// 帧的行号算的，输入行一变高，下面所有行号全部偏移。终端的通用做法是**横向滚动**：
// 只显示尾部，因为光标在末尾，用户要看的是自己刚敲的字。
// Red 原因：当前实现把 ui.input 原样拼上，60 列的输入会得到一条超宽行。
TEST(ViewTest, ScrollsTheInputLineHorizontallyInsteadOfGrowingTaller)
{
    const my_agent::Model model = model_with();
    const my_agent::ui::UiState ui{
        .input = "0123456789012345678901234567890123456789abcdefXYZ",
    };

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, ui, my_agent::ui::Size{.columns = 20, .rows = 10}
    );

    ASSERT_EQ(1u, frame.lines.size());  // 只有输入行，且只有一行
    EXPECT_GE(20, my_agent::ui::display_width(frame.lines.back().text));
    // 保留的是尾部：光标在末尾，用户要看见刚敲进去的字。
    EXPECT_NE(std::string::npos, frame.lines.back().text.find("abcdefXYZ"));
}

// 场景：终端窄到连提示符都放不下。
// 领域语义：输入提示符本身固定占 2 列，1 列宽的终端里没有正确答案，只有可接受的
// 失败方式。锁两条：**必须还有输入行**（少一行会让光标定位算到别人头上），
// **切出来必须是合法 UTF-8**（切在汉字中间会显示成乱码方块）。
// 这是 characterization 测试 —— 探查现有行为后固定下来，防止日后"顺手优化"成
// 丢行或半个字符。
TEST(ViewTest, KeepsTheInputLineIntactEvenWhenTheTerminalIsTooNarrow)
{
    const my_agent::Model model = model_with();
    const my_agent::ui::UiState ui{.input = "输入"};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, ui, my_agent::ui::Size{.columns = 1, .rows = 10}
    );

    ASSERT_EQ(1u, frame.lines.size());
    // 放不下的字被丢掉，剩下的只有提示符 —— 而不是半个字符。
    EXPECT_EQ("> ", frame.lines.back().text);
}

}  // namespace
