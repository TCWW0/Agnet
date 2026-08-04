#include "my_agent/ui/maya_projection.hpp"

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
