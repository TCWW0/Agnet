#include "my_agent/http/http_client.hpp"

#include <httplib.h>

#include <chrono>
#include <format>
#include <string>
#include <utility>

namespace my_agent::http {
namespace {

HttpError connection_error(httplib::Error error)
{
    // httplib 把超时和连接失败分成多个枚举值，这里收敛成我们关心的两类。
    const bool timed_out = error == httplib::Error::ConnectionTimeout
        || error == httplib::Error::Timeout
        || error == httplib::Error::Read
        || error == httplib::Error::Write;

    return HttpError{
        .kind = timed_out ? HttpErrorKind::Timeout : HttpErrorKind::ConnectionFailed,
        .status = 0,
        .message = httplib::to_string(error),
    };
}

std::string content_type_of(const HttpRequest& request)
{
    for (const Header& header : request.headers) {
        if (header.first == "Content-Type") {
            return header.second;
        }
    }
    return "application/json";
}

}  // namespace

HttpResult HttpClient::post_stream(const HttpRequest& request, ChunkCallback on_chunk) const
{
    // httplib::Client 支持 scheme://host:port 形式，编译进 OpenSSL 后同一个类型
    // 同时处理明文与 TLS，因此不需要在 Client / SSLClient 之间分支。
    httplib::Client client{std::format(
        "{}://{}:{}",
        request.use_tls ? "https" : "http",
        request.host,
        request.port
    )};

    // 请求自带预算时收紧到毫秒级；默认走宽超时（流式响应没有可预期
    // 的总时长，读超时必须放宽，否则长回答会被截断）。
    if (request.timeout_ms > 0) {
        const auto budget = std::chrono::milliseconds{request.timeout_ms};
        client.set_connection_timeout(budget);
        client.set_read_timeout(budget);
    } else {
        client.set_connection_timeout(10, 0);
        client.set_read_timeout(600, 0);
    }

    httplib::Headers headers;
    for (const Header& header : request.headers) {
        headers.emplace(header.first, header.second);
    }

    headers.emplace("Content-Type", content_type_of(request));

    bool aborted = false;
    bool is_success = true;

    // 非 2xx 时响应体是错误描述而不是事件流，收集起来用于报错。
    std::string error_body;

    // Post 的重载里没有同时接收 ResponseHandler 的版本，所以走 send(Request)：
    // 它直接暴露 response_handler + content_receiver 两个字段，能在 body 到达
    // 之前先看到状态码。
    httplib::Request wire;
    wire.method = "POST";
    wire.path = request.path;
    wire.headers = std::move(headers);
    wire.body = request.body;

    wire.response_handler = [&is_success](const httplib::Response& response) {
        is_success = response.status >= 200 && response.status < 300;
        return true;
    };

    wire.content_receiver =
        [&on_chunk, &aborted, &is_success, &error_body](
            const char* data, std::size_t length, std::size_t, std::size_t) {
            if (!is_success) {
                error_body.append(data, length);
                return true;
            }

            if (!on_chunk(std::string_view{data, length})) {
                aborted = true;
                return false;
            }
            return true;
        };

    httplib::Result result = client.send(wire);

    if (aborted) {
        return std::unexpected(HttpError{
            .kind = HttpErrorKind::Aborted,
            .status = 0,
            .message = "stream aborted by caller",
        });
    }

    if (!result) {
        return std::unexpected(connection_error(result.error()));
    }

    if (result->status < 200 || result->status >= 300) {
        return std::unexpected(HttpError{
            .kind = HttpErrorKind::Non2xx,
            .status = result->status,
            .message = error_body.empty() ? result->reason : error_body,
        });
    }

    return {};
}

std::expected<std::string, HttpError> HttpClient::post(const HttpRequest& request) const
{
    // 整包 = 流的累积。错误路径（超时/连接失败/Non2xx/中止）原样透传，
    // Non2xx 的响应体已由 post_stream 收进 error.message。
    std::string body;
    const HttpResult result = post_stream(request, [&body](std::string_view chunk) {
        body.append(chunk);
        return true;
    });
    if (!result) {
        return std::unexpected(result.error());
    }
    return body;
}

}  // namespace my_agent::http
