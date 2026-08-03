#include "my_agent/provider/sse.hpp"

#include <cstddef>
#include <string>
#include <string_view>
#include <utility>

namespace my_agent::provider::sse {
namespace {

std::string_view trim_leading_space(std::string_view value)
{
    // 规范说 field 名后的单个空格是分隔符的一部分，要去掉。
    if (!value.empty() && value.front() == ' ') {
        value.remove_prefix(1);
    }
    return value;
}

}  // namespace

void FrameAssembler::feed(std::string_view chunk, const EventHandler& on_event)
{
    buf_.append(chunk);

    std::size_t start = 0;
    while (true) {
        const std::size_t newline = buf_.find('\n', start);
        if (newline == std::string::npos) {
            break;
        }

        std::string_view line =
            std::string_view{buf_}.substr(start, newline - start);
        // 服务端可能发 CRLF；\r 若留着会污染 data 的最后一个字节。
        if (!line.empty() && line.back() == '\r') {
            line.remove_suffix(1);
        }

        consume_line(line, on_event);
        start = newline + 1;
    }

    buf_.erase(0, start);
}

void FrameAssembler::consume_line(std::string_view line, const EventHandler& on_event)
{
    // 空行 = 事件边界。这是与 NDJSON 的本质差异：换行只分隔字段，空行才分隔事件。
    if (line.empty()) {
        if (has_data_) {
            on_event(pending_);
        }
        pending_ = Event{};
        has_data_ = false;
        return;
    }

    // 以冒号开头的行是注释（心跳 keep-alive），忽略。
    if (line.front() == ':') {
        return;
    }

    const std::size_t colon = line.find(':');
    const std::string_view field = line.substr(0, colon);
    const std::string_view value =
        colon == std::string_view::npos
            ? std::string_view{}
            : trim_leading_space(line.substr(colon + 1));

    if (field == "event") {
        pending_.name = value;
        return;
    }

    if (field == "data") {
        // 同一事件的多行 data 按规范用 '\n' 拼接。
        if (has_data_) {
            pending_.data.push_back('\n');
        }
        pending_.data.append(value);
        has_data_ = true;
    }

    // id / retry 等字段与我们无关，静默丢弃。
}

}  // namespace my_agent::provider::sse
