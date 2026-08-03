#include "my_agent/ui/input.hpp"

#include <cstddef>

namespace my_agent::ui {

namespace {

// 从前导字节读出这个 UTF-8 序列该有多长。非法前导返回 1 —— 按 1 字节消费掉，
// 保证循环一定推进而不是卡在同一个字节上。
[[nodiscard]]
std::size_t utf8_length(unsigned char lead) noexcept
{
    if (lead < 0x80) {
        return 1;
    }
    if ((lead & 0xE0) == 0xC0) {
        return 2;
    }
    if ((lead & 0xF0) == 0xE0) {
        return 3;
    }
    if ((lead & 0xF8) == 0xF0) {
        return 4;
    }
    return 1;
}

// 控制字节到按键。返回 Text 表示「不是控制键」。
// 回车是 \r 而不是 \n：raw mode 关掉了 ICRNL。认错会让回车毫无反应。
// \n 也一起认，因为管道喂进来的输入没经过 termios。
[[nodiscard]]
Key::Kind control_kind(unsigned char byte) noexcept
{
    switch (byte) {
        case '\r':
        case '\n':
            return Key::Kind::Enter;
        case 0x7f:  // DEL
        case 0x08:  // BS，部分终端发这个
            return Key::Kind::Backspace;
        case 0x03:
            return Key::Kind::Interrupt;  // Ctrl-C：按键而非信号，见 ISIG 已关闭
        case 0x04:
            return Key::Kind::Eof;  // Ctrl-D
        default:
            return Key::Kind::Text;
    }
}

// 跳过一段未支持的转义序列，返回消耗的字节数；0 表示还没到齐、留到下次。
// 只需要认出**边界**而不是解析内容：CSI（ESC [ ... 终结符 0x40..0x7E）与
// 两字节序列（ESC + 一个字符）覆盖了方向键、Home/End、功能键。
[[nodiscard]]
std::size_t skip_escape(std::string_view text) noexcept
{
    if (text.size() < 2) {
        return 0;
    }
    if (text[1] != '[' && text[1] != 'O') {
        return 2;  // ESC + 单字符
    }
    for (std::size_t index = 2; index < text.size(); ++index) {
        const auto byte = static_cast<unsigned char>(text[index]);
        if (byte >= 0x40 && byte <= 0x7E) {
            return index + 1;  // 终结符
        }
    }
    return 0;  // 终结符还没到
}

}  // namespace

std::vector<Key> InputDecoder::feed(std::string_view bytes)
{
    buffer_.append(bytes);

    std::vector<Key> keys;
    std::size_t offset = 0;
    while (offset < buffer_.size()) {
        const auto lead = static_cast<unsigned char>(buffer_[offset]);

        if (lead == 0x1b) {  // ESC：转义序列的开头
            const std::size_t consumed = skip_escape(
                std::string_view{buffer_}.substr(offset)
            );
            if (consumed == 0) {
                break;  // 序列还没到齐，留到下一次 feed
            }
            offset += consumed;
            continue;  // 本切片不支持方向键等，整段丢弃而不是当文本显示
        }

        if (const Key::Kind kind = control_kind(lead); kind != Key::Kind::Text) {
            keys.push_back(Key{.kind = kind});
            offset += 1;
            continue;
        }

        const std::size_t length = utf8_length(lead);

        // 序列还没到齐：留在缓冲里等下一次 feed。read 不保证在字符边界上切，
        // 现在吐出去就是半个汉字 —— 插进输入行之后再也删不干净。
        if (offset + length > buffer_.size()) {
            break;
        }

        keys.push_back(Key{
            .kind = Key::Kind::Text,
            .text = buffer_.substr(offset, length),
        });
        offset += length;
    }

    buffer_.erase(0, offset);
    return keys;
}

}  // namespace my_agent::ui
