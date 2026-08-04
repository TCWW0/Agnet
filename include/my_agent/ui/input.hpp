#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace my_agent::ui {

// 一次按键。text 非空表示可见字符（可能是多字节的 UTF-8），否则看 kind。
struct Key {
    enum class Kind {
        Text,
        Enter,
        Backspace,
        ClearInput,
        Left,
        Right,
        Up,
        Down,
        Home,
        End,
        Interrupt,  // Ctrl-C
        Eof,        // Ctrl-D
    };

    Kind kind{Kind::Text};
    std::string text;
};

// 字节流 -> 按键。有状态：一个 UTF-8 字符可能跨两次 read 到达（中文占 3 字节，
// 而 read 只保证返回「已就绪的字节」），残缺序列必须留到下一次 feed 缝合，
// 否则会把半个汉字当成非法字节吐出去。
class InputDecoder {
public:
    [[nodiscard]]
    std::vector<Key> feed(std::string_view bytes);

private:
    std::string buffer_;
};

}  // namespace my_agent::ui
