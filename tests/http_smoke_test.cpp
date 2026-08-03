#include "my_agent/http/http_client.hpp"

#include <gtest/gtest.h>

#include <string>

namespace {

// Ollama 的默认地址；集成测试全都以它可达为前提。
constexpr const char* kOllamaHost = "localhost";
constexpr int kOllamaPort = 11434;

bool ollama_reachable()
{
    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest probe{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/tags",
        .headers = {},
        .body = {},
        .use_tls = false,
    };

    // /api/tags 只接受 GET，POST 会拿到非 2xx —— 但那已经证明连接建立成功，
    // 只有 ConnectionFailed 才说明服务不可达。
    const my_agent::http::HttpResult result =
        client.post_stream(probe, [](std::string_view) { return true; });

    return result
        || result.error().kind != my_agent::http::HttpErrorKind::ConnectionFailed;
}

TEST(HttpSmokeTest, CompletesRealTlsHandshake)
{
    // TLS 路径由 cpp-httplib 的 CMake 以 INTERFACE 方式开启。这里做一次真实
    // 握手，保证依赖没有静默退化成没有 HTTPS 的构建。切片 6 的 Anthropic /
    // OpenAI 传输依赖这条路径。
    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = "api.anthropic.com",
        .port = 443,
        .path = "/v1/messages",
        .headers = {{"Content-Type", "application/json"}},
        .body = "{}",
        .use_tls = true,
    };

    const my_agent::http::HttpResult result =
        client.post_stream(request, [](std::string_view) { return true; });

    ASSERT_FALSE(result.has_value());
    if (result.error().kind == my_agent::http::HttpErrorKind::ConnectionFailed) {
        GTEST_SKIP() << "no outbound HTTPS: " << result.error().message;
    }

    // 没有 API key，握手成功后必然被拒。拿到任何 HTTP 状态码就已经证明 TLS
    // 通道建立成功，同时也验证了 Non2xx 映射。具体是 401 还是 403 取决于
    // 边缘层，不作断言。
    EXPECT_EQ(my_agent::http::HttpErrorKind::Non2xx, result.error().kind);
    EXPECT_GE(result.error().status, 400);
    EXPECT_LT(result.error().status, 500);
}

TEST(HttpSmokeTest, StreamsChunksFromLocalOllama)
{
    if (!ollama_reachable()) {
        GTEST_SKIP() << "Ollama is not reachable on localhost:11434";
    }

    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/chat",
        .headers = {{"Content-Type", "application/json"}},
        .body = R"({"model":"qwen3.5:latest","stream":true,"think":false,)"
                R"("messages":[{"role":"user","content":"say hi"}]})",
        .use_tls = false,
    };

    std::string received;
    const my_agent::http::HttpResult result =
        client.post_stream(request, [&received](std::string_view chunk) {
            received.append(chunk);
            return true;
        });

    ASSERT_TRUE(result.has_value()) << result.error().message;
    EXPECT_NE(std::string::npos, received.find("\"done\":true"));
}

TEST(HttpSmokeTest, ReportsAbortWhenChunkCallbackReturnsFalse)
{
    if (!ollama_reachable()) {
        GTEST_SKIP() << "Ollama is not reachable on localhost:11434";
    }

    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/chat",
        .headers = {{"Content-Type", "application/json"}},
        .body = R"({"model":"qwen3.5:latest","stream":true,"think":false,)"
                R"("messages":[{"role":"user","content":"count from 1 to 200"}]})",
        .use_tls = false,
    };

    int chunks = 0;
    const my_agent::http::HttpResult result =
        client.post_stream(request, [&chunks](std::string_view) {
            ++chunks;
            return false;
        });

    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(my_agent::http::HttpErrorKind::Aborted, result.error().kind);
    EXPECT_EQ(1, chunks);
}

TEST(HttpSmokeTest, ReportsNon2xxWithStatusAndBody)
{
    if (!ollama_reachable()) {
        GTEST_SKIP() << "Ollama is not reachable on localhost:11434";
    }

    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/chat",
        .headers = {{"Content-Type", "application/json"}},
        .body = R"({"model":"definitely-not-a-real-model","stream":true,"messages":[]})",
        .use_tls = false,
    };

    bool saw_chunk = false;
    const my_agent::http::HttpResult result =
        client.post_stream(request, [&saw_chunk](std::string_view) {
            saw_chunk = true;
            return true;
        });

    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(my_agent::http::HttpErrorKind::Non2xx, result.error().kind);
    EXPECT_GE(result.error().status, 400);
    // 错误响应体不应该被当成事件流交给回调。
    EXPECT_FALSE(saw_chunk);
}

}  // namespace
