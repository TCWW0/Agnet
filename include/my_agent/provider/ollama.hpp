#pragma once

#include "my_agent/http/http_client.hpp"
#include "my_agent/provider/provider.hpp"

#include <memory>
#include <string>
#include <string_view>

namespace my_agent::provider::ollama {

// Ollama /api/chat 的响应是 NDJSON：一行一个 JSON 帧。HTTP 层交上来的是任意
// 字节切片，一行可能跨多个切片，也可能一个切片里有好几行 —— 所以需要一个跨
// 切片保留残余的行装配器。
//
// 这是整条传输链路上唯一的有状态部分。单独成类而不是藏在闭包里，是为了能不联网
// 直接喂人为切碎的字节流做单元测试：分帧 + 帧到 Msg 的映射才是真正容易出错的
// 地方，而它与 HTTP 无关。
class StreamDecoder {
public:
    // 消费一个字节切片，对其中每个完整行投出对应的 Msg。
    void feed(std::string_view chunk, const EventSink& sink);

private:
    void process_line(std::string_view line, const EventSink& sink);

    std::string line_buf_;
};

// 把 Thread 历史与工具规格编成 Ollama 的请求体。
[[nodiscard]]
std::string build_request_body(std::string_view model, const Request& request);

// 组装成 StreamEffect：宿主把它放到共享池的 worker 上跑。
[[nodiscard]]
StreamEffect make_stream(
    std::string host,
    int port,
    std::string model,
    std::shared_ptr<http::HttpClient> client
);

}  // namespace my_agent::provider::ollama
