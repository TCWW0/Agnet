#include "my_agent/ui/view.hpp"

#include <string>
#include <string_view>
#include <vector>

#include <gtest/gtest.h>

namespace {

my_agent::Model model_with(std::vector<my_agent::Message> messages = {})
{
    my_agent::Model model;
    model.thread.messages = std::move(messages);
    return model;
}

std::string rendered_text(const my_agent::ui::Frame& frame)
{
    std::string result;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        result += line.text;
        result += '\n';
    }
    return result;
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
// 领域语义：view 只负责 Model -> 自有语义 IR；显示宽度、折行与最终 cell 裁剪已经
// 移交 Maya。Frame 里应保留完整文本，避免在自己的投影层再维护一套宽度表。
TEST(ViewTest, LeavesLongMessagesWholeForMayaLayout)
{
    const std::string message = "折行必须交给 Maya renderer 和 Yoga 而不是自有 view";
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = message},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 20, .rows = 10}
    );

    bool found = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text == "> " + message) {
            found = true;
        }
    }
    EXPECT_TRUE(found);
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

TEST(ViewTest, ProjectsStatusBarMetadataAlongsideTheActivePhase)
{
    my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "hello"},
        {.role = my_agent::Role::Assistant, .text = ""},
    });
    model.phase = my_agent::Streaming{};

    my_agent::ui::UiState ui;
    ui.status.model_name = "qwen3.5:latest";
    ui.status.context_used = 4096;
    ui.status.context_limit = 8192;
    ui.status.tokens_per_second = 12.5;

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, ui, my_agent::ui::Size{.columns = 80, .rows = 10}
    );

    ASSERT_TRUE(frame.status_bar.has_value());
    ASSERT_TRUE(frame.status_bar_line.has_value());
    EXPECT_EQ(frame.lines.at(*frame.status_bar_line).text,
              my_agent::ui::plain_status_text(*frame.status_bar));
    EXPECT_NE(
        std::string::npos,
        frame.lines.at(*frame.status_bar_line).text.find("thinking")
    );
    EXPECT_NE(
        std::string::npos,
        frame.lines.at(*frame.status_bar_line).text.find("qwen3.5:latest")
    );
    EXPECT_NE(
        std::string::npos,
        frame.lines.at(*frame.status_bar_line).text.find("12.5")
    );
    EXPECT_NE(
        std::string::npos,
        frame.lines.at(*frame.status_bar_line).text.find("4096/8192")
    );
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

TEST(ViewTest, RendersEachToolCallStateAsAVisiblyDistinctCard)
{
    const nlohmann::json args = {
        {"operation", "multiply"},
        {"left", 6},
        {"right", 7},
    };
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::Assistant,
         .text = "",
         .tool_calls = {
             {.id = "pending", .name = "calculator", .args = args},
             {.id = "done", .name = "calculator", .args = args,
              .status = my_agent::ToolCall::Done{.output = "42"}},
             {.id = "failed", .name = "calculator", .args = args,
              .status = my_agent::ToolCall::Failed{.output = "bad input"}},
             {.id = "rejected", .name = "calculator", .args = args,
              .status = my_agent::ToolCall::Rejected{.output = "denied"}},
         }},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 80, .rows = 30}
    );

    const std::string text = rendered_text(frame);
    EXPECT_NE(std::string::npos, text.find("[pending]"));
    EXPECT_NE(std::string::npos, text.find("[done]"));
    EXPECT_NE(std::string::npos, text.find("[failed]"));
    EXPECT_NE(std::string::npos, text.find("[rejected]"));

    const auto find_line = [&frame](std::string_view marker)
        -> const my_agent::ui::StyledLine* {
        for (const my_agent::ui::StyledLine& line : frame.lines) {
            if (line.text.find(marker) != std::string::npos) {
                return &line;
            }
        }
        return nullptr;
    };
    const my_agent::ui::StyledLine* pending = find_line("[pending]");
    const my_agent::ui::StyledLine* done = find_line("[done]");
    const my_agent::ui::StyledLine* failed = find_line("[failed]");
    const my_agent::ui::StyledLine* rejected = find_line("[rejected]");
    ASSERT_NE(nullptr, pending);
    ASSERT_NE(nullptr, done);
    ASSERT_NE(nullptr, failed);
    ASSERT_NE(nullptr, rejected);
    EXPECT_NE(pending->foreground, done->foreground);
    EXPECT_NE(pending->foreground, failed->foreground);
    EXPECT_NE(pending->foreground, rejected->foreground);
    EXPECT_NE(done->foreground, failed->foreground);
    EXPECT_NE(done->foreground, rejected->foreground);
    EXPECT_NE(failed->foreground, rejected->foreground);
}

TEST(ViewTest, ShowsActualToolArgumentsInTheCard)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::Assistant,
         .text = "",
         .tool_calls = {
             {.id = "read-1", .name = "read",
              .args = { {"path", "notes.md"}, {"limit", 2} }},
         }},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 80, .rows = 10}
    );

    const std::string text = rendered_text(frame);
    EXPECT_NE(std::string::npos, text.find("args:"));
    EXPECT_NE(std::string::npos, text.find("notes.md"));
    EXPECT_NE(std::string::npos, text.find("limit"));
}

TEST(ViewTest, ShowsPermissionToolEffectAndArguments)
{
    my_agent::Model model = model_with({
        {.role = my_agent::Role::Assistant,
         .text = "",
         .tool_calls = {
             {.id = "remember-1", .name = "remember",
              .args = { {"text", "Use zsh"}, {"scope", "project"} }},
         }},
    });
    model.phase = my_agent::AwaitingPermission{};
    model.pending_permission = my_agent::PendingPermission{.id = "remember-1"};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 100, .rows = 10}
    );

    const std::string text = rendered_text(frame);
    EXPECT_NE(std::string::npos, text.find("allow remember"));
    EXPECT_NE(std::string::npos, text.find("effect=write_fs"));
    EXPECT_NE(std::string::npos, text.find("Use zsh"));
    EXPECT_NE(std::string::npos, text.find("project"));
}

TEST(ViewTest, TruncatesLongToolOutputAndReportsElidedCharacters)
{
    const std::string output(400, 'x');
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::Assistant,
         .text = "",
         .tool_calls = {
             {.id = "done-1", .name = "calculator", .args = {},
              .status = my_agent::ToolCall::Done{.output = output}},
         }},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 80, .rows = 10}
    );

    const std::string text = rendered_text(frame);
    EXPECT_NE(std::string::npos, text.find("output:"));
    EXPECT_NE(std::string::npos, text.find("characters elided"));
    EXPECT_EQ(std::string::npos, text.find(output));
}

// 场景：历史比屏幕长。
// 领域语义：裁剪物理屏幕是 Maya 的职责。view 不能先丢历史，否则后续 Maya 布局层
// 无法决定应按什么组件边界、输入高度或滚动策略保留尾部。
TEST(ViewTest, LeavesCompleteHistoryForMayaToClip)
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
    EXPECT_TRUE(has_oldest);
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

TEST(ViewTest, WrapsLongInputAndCarriesTheCursorPosition)
{
    const my_agent::Model model = model_with();
    const my_agent::ui::UiState ui{
        .input = "012345678901234567890123456789",
        .cursor = 23,
    };

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, ui, my_agent::ui::Size{.columns = 10, .rows = 10}
    );

    ASSERT_EQ(4u, frame.lines.size());
    EXPECT_EQ("> 01234567", frame.lines[0].text);
    EXPECT_EQ("8901234567", frame.lines[1].text);
    EXPECT_EQ("8901234567", frame.lines[2].text);
    EXPECT_EQ("89", frame.lines[3].text);
    ASSERT_TRUE(frame.cursor.has_value());
    EXPECT_EQ(8, frame.cursor->row);
    EXPECT_EQ(5, frame.cursor->column);
}

// 场景：Ollama 连不上，StreamError 落在消息的 error 字段上。
// 领域语义：失败必须看得见。StreamError 把 phase 打回 Idle 并写下 error —— 也就是
// 状态行变空、正文一个字都没有。如果帧里不体现 error，用户看到的是「回车之后什么
// 都没发生」，与卡死无从区分，只能猜是不是自己网络坏了。行式 REPL 有 report_errors
// 专门打这个，TUI 必须由 view 承担同一件事，否则接进去就是功能退化。
// Red 原因：当前 view 完全没有读 message.error。
TEST(ViewTest, ShowsTheFailureSoASilentDeadEndIsNeverMistakenForAHang)
{
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::User, .text = "hi"},
        {.role = my_agent::Role::Assistant, .text = "", .error = "connection refused"},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 40, .rows = 10}
    );

    bool found = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text.find("connection refused") != std::string::npos) {
            found = true;
        }
    }
    EXPECT_TRUE(found) << "错误必须上屏，否则与卡死无从区分";
}

// 场景：错误文本比终端还宽。
// 领域语义：错误仍必须上屏，但它不再由 view 按自有宽度表折行；完整错误文本交给
// Maya，渲染层负责按终端列数重排和裁剪。
TEST(ViewTest, LeavesLongFailureMessageWholeForMayaLayout)
{
    const std::string error =
        "connection refused while dialing localhost:11434 after 3 attempts";
    const my_agent::Model model = model_with({
        {.role = my_agent::Role::Assistant,
         .text = "",
         .error = error},
    });

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model, my_agent::ui::UiState{}, my_agent::ui::Size{.columns = 24, .rows = 10}
    );

    bool found = false;
    for (const my_agent::ui::StyledLine& line : frame.lines) {
        if (line.text == "! " + error) {
            found = true;
        }
    }
    EXPECT_TRUE(found);
}

}  // namespace
