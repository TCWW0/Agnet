#pragma once

#include <functional>
#include <string>
#include <string_view>

namespace my_agent::provider::sse {

// SSE 帧装配器。与 Ollama 的 NDJSON 不同，SSE 的一个事件由若干行组成，以空行
// 结束，每行形如 `field: value`：
//
//     event: content_block_delta
//     data: {"type":"text_delta","text":"Hi"}
//     <空行>
//
// 我们只关心 event 与 data 两个字段。同一个事件里可以有多行 data，按规范要用
// '\n' 拼接。
//
// 与 Ollama 一样，字节切片边界与事件边界无关，所以需要跨切片缓冲。分帧独立成
// 类是为了能不联网直接喂人造字节流做单元测试 —— Anthropic 与 OpenAI 共用它。
struct Event {
    std::string name;  // event 字段；OpenAI 不发 event，这里为空
    std::string data;
};

using EventHandler = std::function<void(const Event&)>;

class FrameAssembler {
public:
    void feed(std::string_view chunk, const EventHandler& on_event);

private:
    void consume_line(std::string_view line, const EventHandler& on_event);

    std::string buf_;
    Event pending_{};
    bool has_data_{false};
};

}  // namespace my_agent::provider::sse
