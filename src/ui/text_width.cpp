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

// East_Asian_Width = Wide / Fullwidth 的**完整**区间，按 first 升序且互不重叠。
//
// 真相来源：Unicode 16.0.0 `EastAsianWidth.txt` 里属性为 W 或 F 的全部行。
// 只用这一个来源，**不叠加** Emoji_Presentation —— 判据（unicode_width_oracle.hpp）
// 认的就是 EAW W|F，多叠一层会在区域指示符之类的码点上和判据分歧，那种分歧里
// 实现与判据谁对谁错说不清楚。
//
// 原始 291 条，把首尾相邻的合并成 122 条。合并没有跨过任何空隙：区间之间的保留
// 码点在源文件里本身就显式标着 W（例如 `2A6E0..2A6FF ; W # Cn <reserved>`）——
// Unicode 给 CJK 平面的未分配码点预置 W，正是为了将来分配时终端布局不变。
//
// 用一次性抽取脚本转录，**没有**接进构建。这张表会在引入 maya 后被它自带的宽度表
// 取代，为一周后要删的代码建生成链不划算 —— 这是 PRD「先修再迁」的已知代价。
constexpr std::array<Range, 122> kWideRanges{{
    {0x1100, 0x115F},  // HANGUL CHOSEONG KIYEOK
    {0x231A, 0x231B},  // WATCH
    {0x2329, 0x232A},  // LEFT-POINTING ANGLE BRACKET (+1 more)
    {0x23E9, 0x23EC},  // BLACK RIGHT-POINTING DOUBLE TRIANGLE
    {0x23F0, 0x23F0},  // ALARM CLOCK
    {0x23F3, 0x23F3},  // HOURGLASS WITH FLOWING SAND
    {0x25FD, 0x25FE},  // WHITE MEDIUM SMALL SQUARE
    {0x2614, 0x2615},  // UMBRELLA WITH RAIN DROPS
    {0x2630, 0x2637},  // TRIGRAM FOR HEAVEN
    {0x2648, 0x2653},  // ARIES
    {0x267F, 0x267F},  // WHEELCHAIR SYMBOL
    {0x268A, 0x268F},  // MONOGRAM FOR YANG
    {0x2693, 0x2693},  // ANCHOR
    {0x26A1, 0x26A1},  // HIGH VOLTAGE SIGN
    {0x26AA, 0x26AB},  // MEDIUM WHITE CIRCLE
    {0x26BD, 0x26BE},  // SOCCER BALL
    {0x26C4, 0x26C5},  // SNOWMAN WITHOUT SNOW
    {0x26CE, 0x26CE},  // OPHIUCHUS
    {0x26D4, 0x26D4},  // NO ENTRY
    {0x26EA, 0x26EA},  // CHURCH
    {0x26F2, 0x26F3},  // FOUNTAIN
    {0x26F5, 0x26F5},  // SAILBOAT
    {0x26FA, 0x26FA},  // TENT
    {0x26FD, 0x26FD},  // FUEL PUMP
    {0x2705, 0x2705},  // WHITE HEAVY CHECK MARK
    {0x270A, 0x270B},  // RAISED FIST
    {0x2728, 0x2728},  // SPARKLES
    {0x274C, 0x274C},  // CROSS MARK
    {0x274E, 0x274E},  // NEGATIVE SQUARED CROSS MARK
    {0x2753, 0x2755},  // BLACK QUESTION MARK ORNAMENT
    {0x2757, 0x2757},  // HEAVY EXCLAMATION MARK SYMBOL
    {0x2795, 0x2797},  // HEAVY PLUS SIGN
    {0x27B0, 0x27B0},  // CURLY LOOP
    {0x27BF, 0x27BF},  // DOUBLE CURLY LOOP
    {0x2B1B, 0x2B1C},  // BLACK LARGE SQUARE
    {0x2B50, 0x2B50},  // WHITE MEDIUM STAR
    {0x2B55, 0x2B55},  // HEAVY LARGE CIRCLE
    {0x2E80, 0x2E99},  // CJK RADICAL REPEAT
    {0x2E9B, 0x2EF3},  // CJK RADICAL CHOKE
    {0x2F00, 0x2FD5},  // KANGXI RADICAL ONE
    {0x2FF0, 0x303E},  // IDEOGRAPHIC DESCRIPTION CHARACTER LEFT TO RIGHT (+40 more)
    {0x3041, 0x3096},  // HIRAGANA LETTER SMALL A
    {0x3099, 0x30FF},  // COMBINING KATAKANA-HIRAGANA VOICED SOUND MARK (+8 more)
    {0x3105, 0x312F},  // BOPOMOFO LETTER B
    {0x3131, 0x318E},  // HANGUL LETTER KIYEOK
    {0x3190, 0x31E5},  // IDEOGRAPHIC ANNOTATION LINKING MARK (+4 more)
    {0x31EF, 0x321E},  // IDEOGRAPHIC DESCRIPTION CHARACTER SUBTRACTION (+2 more)
    {0x3220, 0x3247},  // PARENTHESIZED IDEOGRAPH ONE (+1 more)
    {0x3250, 0xA48C},  // PARTNERSHIP SIGN (+13 more)
    {0xA490, 0xA4C6},  // YI RADICAL QOT
    {0xA960, 0xA97C},  // HANGUL CHOSEONG TIKEUT-MIEUM
    {0xAC00, 0xD7A3},  // HANGUL SYLLABLE GA
    {0xF900, 0xFAFF},  // CJK COMPATIBILITY IDEOGRAPH-F900 (+3 more)
    {0xFE10, 0xFE19},  // PRESENTATION FORM FOR VERTICAL COMMA (+3 more)
    {0xFE30, 0xFE52},  // PRESENTATION FORM FOR VERTICAL TWO DOT LEADER (+24 more)
    {0xFE54, 0xFE66},  // SMALL SEMICOLON (+11 more)
    {0xFE68, 0xFE6B},  // SMALL REVERSE SOLIDUS (+2 more)
    {0xFF01, 0xFF60},  // FULLWIDTH EXCLAMATION MARK (+27 more)
    {0xFFE0, 0xFFE6},  // FULLWIDTH CENT SIGN (+4 more)
    {0x16FE0, 0x16FE4},  // TANGUT ITERATION MARK (+3 more)
    {0x16FF0, 0x16FF1},  // VIETNAMESE ALTERNATE READING MARK CA
    {0x17000, 0x187F7},  // TANGUT IDEOGRAPH-17000
    {0x18800, 0x18CD5},  // TANGUT COMPONENT-001 (+1 more)
    {0x18CFF, 0x18D08},  // KHITAN SMALL SCRIPT CHARACTER-18CFF (+1 more)
    {0x1AFF0, 0x1AFF3},  // KATAKANA LETTER MINNAN TONE-2
    {0x1AFF5, 0x1AFFB},  // KATAKANA LETTER MINNAN TONE-7
    {0x1AFFD, 0x1AFFE},  // KATAKANA LETTER MINNAN NASALIZED TONE-7
    {0x1B000, 0x1B122},  // KATAKANA LETTER ARCHAIC E (+1 more)
    {0x1B132, 0x1B132},  // HIRAGANA LETTER SMALL KO
    {0x1B150, 0x1B152},  // HIRAGANA LETTER SMALL WI
    {0x1B155, 0x1B155},  // KATAKANA LETTER SMALL KO
    {0x1B164, 0x1B167},  // KATAKANA LETTER SMALL WI
    {0x1B170, 0x1B2FB},  // NUSHU CHARACTER-1B170
    {0x1D300, 0x1D356},  // MONOGRAM FOR EARTH
    {0x1D360, 0x1D376},  // COUNTING ROD UNIT DIGIT ONE
    {0x1F004, 0x1F004},  // MAHJONG TILE RED DRAGON
    {0x1F0CF, 0x1F0CF},  // PLAYING CARD BLACK JOKER
    {0x1F18E, 0x1F18E},  // NEGATIVE SQUARED AB
    {0x1F191, 0x1F19A},  // SQUARED CL
    {0x1F200, 0x1F202},  // SQUARE HIRAGANA HOKA
    {0x1F210, 0x1F23B},  // SQUARED CJK UNIFIED IDEOGRAPH-624B
    {0x1F240, 0x1F248},  // TORTOISE SHELL BRACKETED CJK UNIFIED IDEOGRAPH-672C
    {0x1F250, 0x1F251},  // CIRCLED IDEOGRAPH ADVANTAGE
    {0x1F260, 0x1F265},  // ROUNDED SYMBOL FOR FU
    {0x1F300, 0x1F320},  // CYCLONE
    {0x1F32D, 0x1F335},  // HOT DOG
    {0x1F337, 0x1F37C},  // TULIP
    {0x1F37E, 0x1F393},  // BOTTLE WITH POPPING CORK
    {0x1F3A0, 0x1F3CA},  // CAROUSEL HORSE
    {0x1F3CF, 0x1F3D3},  // CRICKET BAT AND BALL
    {0x1F3E0, 0x1F3F0},  // HOUSE BUILDING
    {0x1F3F4, 0x1F3F4},  // WAVING BLACK FLAG
    {0x1F3F8, 0x1F43E},  // BADMINTON RACQUET AND SHUTTLECOCK (+2 more)
    {0x1F440, 0x1F440},  // EYES
    {0x1F442, 0x1F4FC},  // EAR
    {0x1F4FF, 0x1F53D},  // PRAYER BEADS
    {0x1F54B, 0x1F54E},  // KAABA
    {0x1F550, 0x1F567},  // CLOCK FACE ONE OCLOCK
    {0x1F57A, 0x1F57A},  // MAN DANCING
    {0x1F595, 0x1F596},  // REVERSED HAND WITH MIDDLE FINGER EXTENDED
    {0x1F5A4, 0x1F5A4},  // BLACK HEART
    {0x1F5FB, 0x1F64F},  // MOUNT FUJI (+1 more)
    {0x1F680, 0x1F6C5},  // ROCKET
    {0x1F6CC, 0x1F6CC},  // SLEEPING ACCOMMODATION
    {0x1F6D0, 0x1F6D2},  // PLACE OF WORSHIP
    {0x1F6D5, 0x1F6D7},  // HINDU TEMPLE
    {0x1F6DC, 0x1F6DF},  // WIRELESS
    {0x1F6EB, 0x1F6EC},  // AIRPLANE DEPARTURE
    {0x1F6F4, 0x1F6FC},  // SCOOTER
    {0x1F7E0, 0x1F7EB},  // LARGE ORANGE CIRCLE
    {0x1F7F0, 0x1F7F0},  // HEAVY EQUALS SIGN
    {0x1F90C, 0x1F93A},  // PINCHED FINGERS
    {0x1F93C, 0x1F945},  // WRESTLERS
    {0x1F947, 0x1F9FF},  // FIRST PLACE MEDAL
    {0x1FA70, 0x1FA7C},  // BALLET SHOES
    {0x1FA80, 0x1FA89},  // YO-YO
    {0x1FA8F, 0x1FAC6},  // SHOVEL
    {0x1FACE, 0x1FADC},  // MOOSE
    {0x1FADF, 0x1FAE9},  // SPLATTER
    {0x1FAF0, 0x1FAF8},  // HAND WITH INDEX FINGER AND THUMB CROSSED
    {0x20000, 0x2FFFD},  // CJK UNIFIED IDEOGRAPH-20000 (+14 more)
    {0x30000, 0x3FFFD},  // CJK UNIFIED IDEOGRAPH-30000 (+3 more)
}};

// 有序且互不重叠是二分查找的前提。这张表是转录进来的，插错一行的后果是某段码点
// 静默算错宽度 —— 那种错误在运行期只表现为「布局偶尔歪一格」，极难归因到表上。
// 所以在编译期挡住：改表时顺序错了直接编译失败，而不是等某个用户打出那个字。
static_assert(
    [] {
        for (std::size_t index = 0; index + 1 < kWideRanges.size(); ++index) {
            if (kWideRanges[index].first > kWideRanges[index].last) {
                return false;  // 区间自身首尾反了
            }
            if (kWideRanges[index].last >= kWideRanges[index + 1].first) {
                return false;  // 与后一个区间重叠，或没按 first 升序
            }
        }
        return true;
    }(),
    "kWideRanges must stay sorted by first and non-overlapping for binary search"
);

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
