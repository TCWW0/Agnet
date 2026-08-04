#include "my_agent/ui/maya_projection.hpp"

#include <maya/dsl.hpp>
#include <maya/style/color.hpp>
#include <maya/style/theme.hpp>

#include <optional>
#include <vector>

namespace my_agent::ui {

namespace {

[[nodiscard]]
std::optional<maya::Color> to_maya_color(
    StyleColor color,
    const maya::Theme& theme
) noexcept
{
    switch (color) {
        case StyleColor::Default:
            return std::nullopt;
        case StyleColor::Text:
            return theme.text;
        case StyleColor::Muted:
            return theme.muted;
        case StyleColor::Primary:
            return theme.primary;
        case StyleColor::Secondary:
            return theme.secondary;
        case StyleColor::Accent:
            return theme.accent;
        case StyleColor::Success:
            return theme.success;
        case StyleColor::Error:
            return theme.error;
        case StyleColor::Warning:
            return theme.warning;
        case StyleColor::Info:
            return theme.info;
        case StyleColor::Surface:
            return theme.surface;
        case StyleColor::Background:
            return theme.background;
        case StyleColor::Border:
            return theme.border;
    }
    return std::nullopt;
}

[[nodiscard]]
maya::Style to_maya_style(const StyledLine& line, const maya::Theme& theme)
{
    maya::Style style;
    if (const std::optional<maya::Color> color =
            to_maya_color(line.foreground, theme)) {
        style = style.with_fg(*color);
    }
    if (const std::optional<maya::Color> color =
            to_maya_color(line.background, theme)) {
        style = style.with_bg(*color);
    }
    if (line.bold) {
        style = style.with_bold();
    }
    if (line.dim) {
        style = style.with_dim();
    }
    return style;
}

}  // namespace

maya::Element to_maya_element(const Frame& frame, const maya::Theme& theme)
{
    std::vector<maya::Element> rows;
    rows.reserve(frame.lines.size());

    for (auto line = frame.lines.rbegin(); line != frame.lines.rend(); ++line) {
        rows.push_back(
            (maya::dsl::text(line->text, to_maya_style(*line, theme))
             | maya::dsl::shrink(0.0F))
                .build()
        );
    }

    return maya::dsl::vstack()
        .direction(maya::ColumnReverse)
        .overflow(maya::Overflow::Hidden)
        (std::move(rows));
}

}  // namespace my_agent::ui
