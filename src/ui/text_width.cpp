#include "my_agent/ui/text_width.hpp"

#include <algorithm>
#include <array>
#include <cstddef>

namespace my_agent::ui {

namespace {

struct Range {
    char32_t first;
    char32_t last;
};

// East_Asian_Width = Wide / Fullwidth 的区间，按 first 升序且互不重叠。
// 只覆盖真实对话里会出现的范围（CJK、假名、韩文、全角标点、常用 emoji），
// 不做完整 UCD 表 —— 那需要一条生成链，而这里的取舍是够用优先。
constexpr std::array<Range, 22> kWideRanges{{
    {0x1100, 0x115F},    // 韩文字母 Jamo 初声
    {0x2E80, 0x303E},    // CJK 部首补充、康熙部首、CJK 符号与标点
    {0x3041, 0x33FF},    // 平假名、片假名、注音、韩文兼容字母、CJK 兼容
    {0x3400, 0x4DBF},    // CJK 扩展 A
    {0x4E00, 0x9FFF},    // CJK 统一表意文字（最常用的那一段）
    {0xA000, 0xA4CD},    // 彝文音节
    {0xAC00, 0xD7A3},    // 韩文音节
    {0xF900, 0xFAFF},    // CJK 兼容表意文字
    {0xFE10, 0xFE19},    // 竖排标点
    {0xFE30, 0xFE6B},    // CJK 兼容形式、小写变体
    {0xFF01, 0xFF60},    // 全角 ASCII 与标点
    {0xFFE0, 0xFFE6},    // 全角货币符号
    {0x1F004, 0x1F004},  // 麻将红中
    {0x1F0CF, 0x1F0CF},  // 小丑牌
    {0x1F18E, 0x1F18E},  // AB 型血
    {0x1F191, 0x1F19A},  // CL/COOL/FREE 等方形标志
    {0x1F200, 0x1F320},  // 封入字符补充、天气与自然
    {0x1F32D, 0x1F335},  // 食物
    {0x1F337, 0x1F37C},  // 植物与饮料
    {0x1F380, 0x1F393},  // 庆典与物件
    {0x1F3A0, 0x1F6FF},  // 交通与地图、杂项符号与象形文字
    {0x1F900, 0x1F9FF},  // 补充符号与象形文字（含表情与手势）
}};

[[nodiscard]]
bool in_wide_ranges(char32_t code_point) noexcept
{
    // upper_bound 找到第一个 first 大于 code_point 的区间，候选是它的前一个。
    const auto it = std::ranges::upper_bound(
        kWideRanges, code_point, {}, &Range::first
    );
    if (it == kWideRanges.begin()) {
        return false;
    }
    return code_point <= std::prev(it)->last;
}

// 解码一个 UTF-8 序列。返回码点与消耗的字节数；非法序列返回 {U+FFFD, 1}，
// 也就是「按 1 列计并前进 1 字节」，保证调用方的循环一定推进、不会死循环。
struct Decoded {
    char32_t code_point;
    std::size_t size;
};

[[nodiscard]]
Decoded decode_utf8(std::string_view text) noexcept
{
    const auto byte = [text](std::size_t index) {
        return static_cast<unsigned char>(text[index]);
    };

    const unsigned char lead = byte(0);
    if (lead < 0x80) {
        return {lead, 1};
    }

    const auto is_continuation = [](unsigned char value) {
        return (value & 0xC0) == 0x80;
    };

    std::size_t length = 0;
    char32_t code_point = 0;
    if ((lead & 0xE0) == 0xC0) {
        length = 2;
        code_point = lead & 0x1F;
    } else if ((lead & 0xF0) == 0xE0) {
        length = 3;
        code_point = lead & 0x0F;
    } else if ((lead & 0xF8) == 0xF0) {
        length = 4;
        code_point = lead & 0x07;
    } else {
        return {0xFFFD, 1};  // 落单的续字节或非法前导
    }

    if (text.size() < length) {
        return {0xFFFD, 1};
    }
    for (std::size_t index = 1; index < length; ++index) {
        if (!is_continuation(byte(index))) {
            return {0xFFFD, 1};
        }
        code_point = (code_point << 6) | (byte(index) & 0x3F);
    }
    return {code_point, length};
}

}  // namespace

int char_width(char32_t code_point) noexcept
{
    if (code_point < 0x20) {
        return 0;
    }
    // 0x1100 是 kWideRanges 第一个区间的起点。ASCII、拉丁、框线字符（U+2500..）
    // 全在这条线以下，而它们占了 TUI 里绝大多数字符 —— 短路掉二分查找。
    // 这个上界必须跟 kWideRanges[0].first 保持一致。
    if (code_point < 0x1100) {
        return 1;
    }
    return in_wide_ranges(code_point) ? 2 : 1;
}

int display_width(std::string_view text)
{
    int width = 0;
    while (!text.empty()) {
        const Decoded decoded = decode_utf8(text);
        width += char_width(decoded.code_point);
        text.remove_prefix(decoded.size);
    }
    return width;
}

std::vector<std::string> wrap(std::string_view text, int columns)
{
    if (columns <= 0) {
        return {};
    }

    std::vector<std::string> lines;
    std::string current;
    int current_width = 0;
    // 当前行里最后一个空格的字节位置，用于回退断行。npos 表示这一行还没有空格，
    // 只能硬断 —— 长 URL 和 CJK 都走那条路。
    std::size_t last_space = std::string::npos;

    while (!text.empty()) {
        const Decoded decoded = decode_utf8(text);
        const int width = char_width(decoded.code_point);

        // 放不下就先收行。判定用 > 而不是 >=：正好填满的那一行是合法的。
        if (current_width + width > columns && !current.empty()) {
            if (last_space != std::string::npos) {
                // 在空格处断开，空格本身不进任何一行 —— 行尾空格在有背景色的
                // 终端里会显示成一块脏色。空格之后已经填进去的部分挪到下一行。
                std::string carry = current.substr(last_space + 1);
                current.resize(last_space);
                lines.push_back(std::move(current));
                current = std::move(carry);
                current_width = display_width(current);
            } else {
                lines.push_back(std::move(current));
                current.clear();
                current_width = 0;
            }
            last_space = std::string::npos;
        }

        if (decoded.code_point == U' ') {
            last_space = current.size();
        }
        current.append(text.substr(0, decoded.size));
        current_width += width;
        text.remove_prefix(decoded.size);
    }

    if (!current.empty()) {
        lines.push_back(std::move(current));
    }
    return lines;
}

}  // namespace my_agent::ui
