#pragma once

#include <expected>
#include <functional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace my_agent::http {

enum class HttpErrorKind {
    ConnectionFailed,  // 连不上、DNS 失败、TLS 握手失败
    Timeout,
    Non2xx,            // 建立了连接并拿到响应，但状态码不是 2xx
    Aborted,           // ChunkCallback 返回 false 主动中止
};

struct HttpError {
    HttpErrorKind kind;
    int status{0};          // 仅 Non2xx 有意义
    std::string message;
};

// 与 tool::ExecResult 相同的惯用法
using HttpResult = std::expected<void, HttpError>;

using Header = std::pair<std::string, std::string>;

struct HttpRequest {
    std::string host;
    int port{0};
    std::string path;
    std::vector<Header> headers;
    std::string body;
    bool use_tls{false};
    // 0 = http 层默认（连接 10s / 读 600s）；>0 = 把连接超时与读超时同时
    // 收紧到该值。socket 级语义：是单次连接/单次读的等待上限，不是整个
    // 请求的墙钟预算（对端慢滴漏不会触发）。
    int timeout_ms{0};
};

// 返回 false 中止流；HttpClient 会以 HttpErrorKind::Aborted 结束
using ChunkCallback = std::function<bool(std::string_view)>;

// 对 cpp-httplib 的薄适配：明文与 TLS 共用一套 API。
// post_stream 同步阻塞，由调用方放到 worker 线程上执行。
class HttpClient {
public:
    [[nodiscard]]
    HttpResult post_stream(const HttpRequest& request, ChunkCallback on_chunk) const;

    // 非流式便捷口：整包收齐后一次返回。错误语义与 post_stream 完全一致
    // （Non2xx 时 message 就是错误响应体）。内部复用 post_stream，
    // 整包累积的负担留在 http 层，不摊给每个调用方。
    [[nodiscard]]
    std::expected<std::string, HttpError> post(const HttpRequest& request) const;
};

}  // namespace my_agent::http
