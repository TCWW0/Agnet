#include "my_agent/ui/input_layout.hpp"

#include <cstddef>

namespace my_agent::ui {

namespace {

struct CodePoint {
    char32_t value{0};
    std::size_t bytes{1};
};

[[nodiscard]]
bool is_continuation(unsigned char byte) noexcept
{
    return (byte & 0xc0u) == 0x80u;
}

[[nodiscard]]
CodePoint next_code_point(std::string_view text, std::size_t offset) noexcept
{
    const unsigned char lead = static_cast<unsigned char>(text[offset]);
    if (lead < 0x80u) {
        return CodePoint{.value = lead};
    }

    std::size_t length = 0;
    char32_t value = 0;
    if (lead >= 0xc2u && lead <= 0xdfu) {
        length = 2;
        value = lead & 0x1fu;
    } else if (lead >= 0xe0u && lead <= 0xefu) {
        length = 3;
        value = lead & 0x0fu;
    } else if (lead >= 0xf0u && lead <= 0xf4u) {
        length = 4;
        value = lead & 0x07u;
    } else {
        return CodePoint{.value = lead};
    }

    if (offset + length > text.size()) {
        return CodePoint{.value = lead};
    }
    for (std::size_t index = 1; index < length; ++index) {
        const unsigned char byte = static_cast<unsigned char>(
            text[offset + index]
        );
        if (!is_continuation(byte)) {
            return CodePoint{.value = lead};
        }
        value = (value << 6) | (byte & 0x3fu);
    }
    return CodePoint{.value = value, .bytes = length};
}

[[nodiscard]]
int code_point_width(char32_t value) noexcept
{
    if (value == 0x200d || (value >= 0x300u && value <= 0x36fu)
        || (value >= 0xfe00u && value <= 0xfe0fu)) {
        return 0;
    }
    if (value >= 0x1100u && value <= 0x115fu) {
        return 2;
    }
    if (value >= 0x2329u && value <= 0x232au) {
        return 2;
    }
    if (value >= 0x2e80u && value <= 0xa4cfu) {
        return 2;
    }
    if (value >= 0xacu && value <= 0xd7a3u) {
        return 2;
    }
    if (value >= 0xf900u && value <= 0xfaffu) {
        return 2;
    }
    if (value >= 0xfe10u && value <= 0xfe6fu) {
        return 2;
    }
    if (value >= 0xff01u && value <= 0xff60u) {
        return 2;
    }
    if (value >= 0xffe0u && value <= 0xffe6u) {
        return 2;
    }
    if (value >= 0x2600u && value <= 0x27bfu) {
        return 2;
    }
    if (value >= 0x1f300u && value <= 0x1faffu) {
        return 2;
    }
    return value < 0x20u || value == 0x7fu ? 0 : 1;
}

}  // namespace

InputLayout layout_input(
    std::string_view buffer,
    std::size_t cursor,
    int columns
)
{
    const int width_limit = columns > 0 ? columns : 1;
    if (cursor == std::string::npos || cursor > buffer.size()) {
        cursor = buffer.size();
    }
    while (cursor > 0 && cursor < buffer.size()
           && is_continuation(static_cast<unsigned char>(buffer[cursor]))) {
        --cursor;
    }

    InputLayout result;
    result.lines.emplace_back("> ");
    int current_width = 2;

    std::size_t offset = 0;
    while (offset < buffer.size()) {
        const CodePoint code_point = next_code_point(buffer, offset);
        if (code_point.value == '\n') {
            if (offset == cursor && current_width == width_limit) {
                result.lines.emplace_back();
                current_width = 0;
                result.cursor_line = result.lines.size() - 1;
                result.cursor_column = 0;
            } else {
                if (offset == cursor) {
                    result.cursor_line = result.lines.size() - 1;
                    result.cursor_column = current_width;
                }
                result.lines.emplace_back();
                current_width = 0;
            }
            offset += code_point.bytes;
            continue;
        }

        const int glyph_width = code_point_width(code_point.value);
        if (current_width > 0
            && current_width + glyph_width > width_limit) {
            result.lines.emplace_back();
            current_width = 0;
        }
        if (offset == cursor) {
            result.cursor_line = result.lines.size() - 1;
            result.cursor_column = current_width;
        }

        result.lines.back().append(buffer, offset, code_point.bytes);
        current_width += glyph_width;
        offset += code_point.bytes;
    }

    if (cursor == buffer.size()) {
        result.cursor_line = result.lines.size() - 1;
        result.cursor_column = current_width;
    }

    if (!buffer.empty() && current_width == width_limit
        && cursor == buffer.size()) {
        result.lines.emplace_back();
        result.cursor_line = result.lines.size() - 1;
        result.cursor_column = 0;
    }

    return result;
}

}  // namespace my_agent::ui
