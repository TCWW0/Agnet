#include "my_agent/ui/maya_projection.hpp"
#include "my_agent/ui/view.hpp"
#include "virtual_terminal.hpp"

#include <maya/render/frame.hpp>
#include <maya/style/theme.hpp>

#include <gtest/gtest.h>

#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr const char* kFirstLine = "FRAME2MAYAFIRST7F3A";
constexpr const char* kSecondLine = "FRAME2MAYASECOND7F3A";
constexpr const char* kStyledLine = "FRAME2MAYASTYLE7F3A";

[[nodiscard]]
std::vector<std::string_view> split_sgr_params(std::string_view params)
{
    std::vector<std::string_view> result;
    while (!params.empty()) {
        const std::size_t next = params.find(';');
        result.push_back(params.substr(0, next));
        if (next == std::string_view::npos) {
            break;
        }
        params.remove_prefix(next + 1);
    }
    return result;
}

[[nodiscard]]
bool has_sgr_sequence_with_params(
    std::string_view bytes,
    const std::vector<std::string_view>& expected_params
)
{
    std::size_t offset = 0;
    while ((offset = bytes.find("\x1b[", offset)) != std::string_view::npos) {
        const std::size_t end = bytes.find('m', offset + 2);
        if (end == std::string_view::npos) {
            return false;
        }
        const std::vector<std::string_view> params =
            split_sgr_params(bytes.substr(offset + 2, end - offset - 2));
        bool all_found = true;
        for (std::string_view expected : expected_params) {
            bool found = false;
            for (std::string_view actual : params) {
                if (actual == expected) {
                    found = true;
                    break;
                }
            }
            all_found = all_found && found;
        }
        if (all_found) {
            return true;
        }
        offset = end + 1;
    }
    return false;
}

}  // namespace

TEST(MayaProjectionTest, RendersFrameLinesThroughMaya)
{
    const my_agent::ui::Frame frame{
        .lines =
            {
                my_agent::ui::StyledLine{.text = kFirstLine},
                my_agent::ui::StyledLine{.text = kSecondLine},
            },
    };

    maya::FrameBuffer framebuffer{80, 6};
    const std::string& bytes =
        framebuffer.render(
            my_agent::ui::to_maya_element(frame, maya::theme::dark),
            maya::theme::dark
        );

    EXPECT_NE(bytes.find(kFirstLine), std::string::npos) << bytes;
    EXPECT_NE(bytes.find(kSecondLine), std::string::npos)
        << "The rendered bytes must carry content from our own Frame IR.";
}

TEST(MayaProjectionTest, CarriesStyledLineAttributesThroughMaya)
{
    const my_agent::ui::Frame frame{
        .lines =
            {
                my_agent::ui::StyledLine{
                    .text = kStyledLine,
                    .foreground = my_agent::ui::StyleColor::Error,
                    .background = my_agent::ui::StyleColor::Info,
                    .bold = true,
                    .dim = true,
                },
            },
    };

    maya::FrameBuffer framebuffer{80, 3};
    const std::string& bytes =
        framebuffer.render(
            my_agent::ui::to_maya_element(frame, maya::theme::dark_ansi),
            maya::theme::dark_ansi
        );

    EXPECT_TRUE(has_sgr_sequence_with_params(bytes, {"1", "91", "106"})) << bytes;
    EXPECT_NE(bytes.find(kStyledLine), std::string::npos) << bytes;
}

TEST(MayaProjectionTest, FitsStatusBarFragmentsAndKeepsActivityOnANarrowScreen)
{
    const my_agent::ui::StatusBar status = my_agent::ui::build_status_bar({
        .phase = my_agent::ui::StatusPhase::Streaming,
        .model_name = "qwen3.5:latest",
        .context_used = 4096,
        .context_limit = 8192,
        .tokens_per_second = 12.5,
        .elapsed_seconds = 3.25,
    });
    const my_agent::ui::Frame frame{
        .lines = {{.text = my_agent::ui::plain_status_text(status)}},
        .status_bar = status,
        .status_bar_line = 0,
    };

    maya::FrameBuffer framebuffer{22, 4};
    const std::string& bytes = framebuffer.render(
        my_agent::ui::to_maya_element(frame, maya::theme::dark),
        maya::theme::dark
    );

    EXPECT_NE(bytes.find("thinking"), std::string::npos) << bytes;
    EXPECT_EQ(bytes.find("qwen3.5:latest"), std::string::npos) << bytes;
    EXPECT_EQ(bytes.find("tok/s"), std::string::npos) << bytes;
}

TEST(MayaProjectionTest, CarriesToolCardDetailsToFrameBufferBytes)
{
    my_agent::Model model;
    model.thread.messages.push_back({
        .role = my_agent::Role::Assistant,
        .text = "",
        .tool_calls = {
            {.id = "remember-1", .name = "remember",
             .args = { {"text", "Use zsh"}, {"scope", "project"} }},
        },
    });
    model.phase = my_agent::AwaitingPermission{};
    model.pending_permission = my_agent::PendingPermission{.id = "remember-1"};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model,
        my_agent::ui::UiState{},
        my_agent::ui::Size{.columns = 120, .rows = 12}
    );
    maya::FrameBuffer framebuffer{120, 12};
    const std::string& bytes = framebuffer.render(
        my_agent::ui::to_maya_element(frame, maya::theme::dark),
        maya::theme::dark
    );

    EXPECT_NE(bytes.find("[pending]"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("remember"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("effect=write_fs"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("Use zsh"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("project"), std::string::npos) << bytes;
}

TEST(MayaProjectionTest, CarriesCommittedMarkdownAndActiveTextToFrameBufferBytes)
{
    my_agent::Model model;
    model.thread.messages.push_back({
        .role = my_agent::Role::Assistant,
        .text = "# Heading\n```cpp\nint answer = 42;\n```\n",
    });
    model.phase = my_agent::Streaming{};

    const my_agent::ui::Frame frame = my_agent::ui::view(
        model,
        my_agent::ui::UiState{},
        my_agent::ui::Size{.columns = 100, .rows = 12}
    );
    maya::FrameBuffer framebuffer{100, 12};
    const std::string& bytes = framebuffer.render(
        my_agent::ui::to_maya_element(frame, maya::theme::dark),
        maya::theme::dark
    );

    EXPECT_NE(bytes.find("Heading"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("cpp"), std::string::npos) << bytes;
    EXPECT_NE(bytes.find("int answer = 42;"), std::string::npos) << bytes;
}

TEST(MayaProjectionTest, WrapsMixedEmojiAndCjkTextThroughMaya)
{
    const my_agent::ui::Frame frame{
        .lines =
            {
                my_agent::ui::StyledLine{
                    .text = "你好 ✅ alpha beta TAIL17",
                },
            },
    };

    maya::FrameBuffer framebuffer{12, 5};
    const std::string& bytes =
        framebuffer.render(
            my_agent::ui::to_maya_element(frame, maya::theme::dark),
            maya::theme::dark
        );

    my_agent::test::VirtualTerminal terminal{12, 5};
    terminal.feed(bytes);

    ASSERT_TRUE(terminal.unhandled().empty())
        << "Unhandled sequence: " << terminal.unhandled().front();
    EXPECT_EQ(0, terminal.right_margin_overruns()) << bytes;

    int occupied_rows = 0;
    bool tail_visible = false;
    for (const std::string& row : terminal.screen()) {
        if (!row.empty()) {
            ++occupied_rows;
        }
        if (row.find("TAIL17") != std::string::npos) {
            tail_visible = true;
        }
    }
    EXPECT_LT(1, occupied_rows) << bytes;
    EXPECT_TRUE(tail_visible) << bytes;
}

TEST(MayaProjectionTest, ClipsOverflowingFramesAtTheTop)
{
    const my_agent::ui::Frame frame{
        .lines =
            {
                my_agent::ui::StyledLine{.text = "old0"},
                my_agent::ui::StyledLine{.text = "old1"},
                my_agent::ui::StyledLine{.text = "old2"},
                my_agent::ui::StyledLine{.text = "new3"},
                my_agent::ui::StyledLine{.text = "new4"},
            },
    };

    maya::FrameBuffer framebuffer{12, 3};
    const std::string& bytes =
        framebuffer.render(
            my_agent::ui::to_maya_element(frame, maya::theme::dark),
            maya::theme::dark
        );

    my_agent::test::VirtualTerminal terminal{12, 3};
    terminal.feed(bytes);

    ASSERT_TRUE(terminal.unhandled().empty())
        << "Unhandled sequence: " << terminal.unhandled().front();

    bool old_visible = false;
    bool newest_visible = false;
    for (const std::string& row : terminal.screen()) {
        old_visible = old_visible || row.find("old0") != std::string::npos;
        newest_visible = newest_visible || row.find("new4") != std::string::npos;
    }
    EXPECT_FALSE(old_visible) << bytes;
    EXPECT_TRUE(newest_visible) << bytes;
}

TEST(MayaProjectionTest, VeryNarrowTerminalsDoNotCrash)
{
    const my_agent::ui::Frame frame{
        .lines =
            {
                my_agent::ui::StyledLine{.text = "> ✅你TAIL17"},
            },
    };

    for (const int columns : {1, 2}) {
        maya::FrameBuffer framebuffer{columns, 3};
        const std::string& bytes =
            framebuffer.render(
                my_agent::ui::to_maya_element(frame, maya::theme::dark),
                maya::theme::dark
            );

        my_agent::test::VirtualTerminal terminal{columns, 3};
        terminal.feed(bytes);

        ASSERT_TRUE(terminal.unhandled().empty())
            << "Unhandled sequence at " << columns
            << " columns: " << terminal.unhandled().front();
        EXPECT_EQ(0, terminal.right_margin_overruns()) << bytes;
        EXPECT_EQ(3u, terminal.screen().size());
    }
}
