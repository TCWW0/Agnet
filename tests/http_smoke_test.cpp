#include "my_agent/http/http_client.hpp"

#include <gtest/gtest.h>

#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <string>
#include <thread>

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

TEST(HttpSmokeTest, PostReturnsWholeBodyFromLocalOllama)
{
    if (!ollama_reachable()) {
        GTEST_SKIP() << "Ollama is not reachable on localhost:11434";
    }

    // post() 的本职：非流式整包。embed 端点天然无流，是最贴切的验尸对象。
    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/embed",
        .headers = {{"Content-Type", "application/json"}},
        .body = R"({"model":"nomic-embed-text:latest","input":["hello"]})",
        .use_tls = false,
    };

    const auto result = client.post(request);
    ASSERT_TRUE(result.has_value()) << result.error().message;
    // 严格的 JSON 断言归 rag 的 parse_embed_response（57 测试钉着），
    // 这里只需证明整包收齐：含 embeddings 数组的完整响应体。
    EXPECT_NE(std::string::npos, result->find("\"embeddings\""));
}

TEST(HttpSmokeTest, PostMapsNon2xxWithStatus)
{
    if (!ollama_reachable()) {
        GTEST_SKIP() << "Ollama is not reachable on localhost:11434";
    }

    // /api/tags 只接受 GET：POST 必然非 2xx。验证 post() 的错误映射
    // 与 post_stream 一致 —— kind、status 透传，错误体不进成功通道。
    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = kOllamaHost,
        .port = kOllamaPort,
        .path = "/api/tags",
        .headers = {},
        .body = {},
        .use_tls = false,
    };

    const auto result = client.post(request);
    ASSERT_FALSE(result.has_value());
    EXPECT_EQ(my_agent::http::HttpErrorKind::Non2xx, result.error().kind);
    EXPECT_GE(result.error().status, 400);
}

TEST(HttpSmokeTest, PostHonorsReadTimeout)
{
    // 哑 socket：accept 之后只收不回 —— 读超时的最小保真对端。测的是
    // 客户端，对端越 dumb 越好：不引入第二个 HTTP 实现，耦合面为零。
    const int listen_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_GE(listen_fd, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = 0;  // 端口交给内核，避免撞车
    ASSERT_EQ(0, ::bind(listen_fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)));
    ASSERT_EQ(0, ::listen(listen_fd, 1));
    socklen_t addr_len = sizeof(addr);
    ASSERT_EQ(0, ::getsockname(listen_fd, reinterpret_cast<sockaddr*>(&addr), &addr_len));
    const int port = ntohs(addr.sin_port);

    // 服务线程：阻塞读直到对端关连接（客户端超时后 Client 析构即关），
    // 于是线程自然退出，测试收尾不需要额外的唤醒机制。
    std::thread silent([listen_fd] {
        const int conn = ::accept(listen_fd, nullptr, nullptr);
        if (conn < 0) {
            return;
        }
        char sink[64];
        while (::read(conn, sink, sizeof(sink)) > 0) {
        }
        ::close(conn);
    });

    const my_agent::http::HttpClient client;
    const my_agent::http::HttpRequest request{
        .host = "127.0.0.1",
        .port = port,
        .path = "/api/embed",
        .headers = {{"Content-Type", "application/json"}},
        .body = R"({"model":"x","input":["y"]})",
        .use_tls = false,
        .timeout_ms = 300,
    };

    const auto t0 = std::chrono::steady_clock::now();
    const auto result = client.post(request);
    const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - t0).count();

    ::close(listen_fd);
    silent.join();

    ASSERT_FALSE(result.has_value()) << result.error().message;
    EXPECT_EQ(my_agent::http::HttpErrorKind::Timeout, result.error().kind);
    // 预算 300ms 真的生效：若还挂在默认读超时上，这里等的是 600s。
    EXPECT_LT(elapsed_ms, 1500);
}

