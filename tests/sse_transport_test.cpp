#include "my_agent/provider/sse.hpp"

#include <string>
#include <vector>

#include <gtest/gtest.h>

namespace {

// 把装配出的事件收集起来，断言完整序列而不是逐个回调。
std::vector<my_agent::provider::sse::Event> collect(
    my_agent::provider::sse::FrameAssembler& assembler,
    const std::vector<std::string>& chunks
)
{
    std::vector<my_agent::provider::sse::Event> events;
    for (const std::string& chunk : chunks) {
        assembler.feed(chunk, [&events](const my_agent::provider::sse::Event& event) {
            events.push_back(event);
        });
    }
    return events;
}

}  // namespace

// 场景：一个规范的 SSE 事件，event 与 data 各一行，空行收尾。
// 领域语义：SSE 的事件边界是**空行**，不是换行 —— 这是与 Ollama NDJSON 的第一
// 个本质差异。装配器在看到空行之前不能把任何东西交出去。
// Red 原因：仓库尚无 sse.cpp 实现，FrameAssembler::feed 无定义。
TEST(SseFrameAssemblerTest, EmitsOneEventOnBlankLineTerminator)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {"event: content_block_delta\ndata: {\"text\":\"Hi\"}\n\n"}
    );

    ASSERT_EQ(std::size_t{1}, events.size());
    EXPECT_EQ("content_block_delta", events.front().name);
    EXPECT_EQ("{\"text\":\"Hi\"}", events.front().data);
}

// 场景：同一个事件被 TCP 切成了任意几段，切点甚至落在字段名中间。
// 领域语义：字节切片边界与事件边界毫无关系 —— 这正是分帧器必须存在、而不能
// 在回调里就地 parse 的原因。跨切片缓冲是它唯一的职责。
TEST(SseFrameAssemblerTest, AssemblesOneEventAcrossArbitraryChunkBoundaries)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {"eve", "nt: content_bl", "ock_delta\nda", "ta: {\"text\":\"H", "i\"}\n", "\n"}
    );

    ASSERT_EQ(std::size_t{1}, events.size());
    EXPECT_EQ("content_block_delta", events.front().name);
    EXPECT_EQ("{\"text\":\"Hi\"}", events.front().data);
}

// 场景：一个切片里塞了两个完整事件。
// 领域语义：一次 feed 可能装配出任意多个事件，装配器不能假设"一次一个"。
TEST(SseFrameAssemblerTest, EmitsEveryEventContainedInASingleChunk)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {"event: a\ndata: 1\n\nevent: b\ndata: 2\n\n"}
    );

    ASSERT_EQ(std::size_t{2}, events.size());
    EXPECT_EQ("a", events.at(0).name);
    EXPECT_EQ("1", events.at(0).data);
    EXPECT_EQ("b", events.at(1).name);
    EXPECT_EQ("2", events.at(1).data);
}

// 场景：一个事件带多行 data，且中间夹了注释行与 CRLF 行尾。
// 领域语义：多行 data 按规范用 '\n' 拼接；以 ':' 开头的注释行是 keep-alive
// 心跳，不能当成字段；CRLF 的 '\r' 若不剥掉会污染 data 末字节，让下游 JSON
// 解析在真实服务端上莫名失败。
TEST(SseFrameAssemblerTest, JoinsMultipleDataLinesAndIgnoresCommentsAndCarriageReturns)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {": keep-alive\r\nevent: message\r\ndata: line-one\r\ndata: line-two\r\n\r\n"}
    );

    ASSERT_EQ(std::size_t{1}, events.size());
    EXPECT_EQ("message", events.front().name);
    EXPECT_EQ("line-one\nline-two", events.front().data);
}

// 场景：只有 data 没有 event 字段。
// 领域语义：OpenAI 从不发 event 字段，只发 data —— 同一个装配器必须能同时服务
// Anthropic（带 event 名）和 OpenAI（不带），否则两个 provider 就得各写一份分帧。
TEST(SseFrameAssemblerTest, EmitsDataOnlyEventsWithAnEmptyName)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {"data: {\"id\":\"x\"}\n\ndata: [DONE]\n\n"}
    );

    ASSERT_EQ(std::size_t{2}, events.size());
    EXPECT_TRUE(events.at(0).name.empty());
    EXPECT_EQ("{\"id\":\"x\"}", events.at(0).data);
    EXPECT_EQ("[DONE]", events.at(1).data);
}

// 场景：流在事件中途断掉，最后一个事件没有收到收尾空行。
// 领域语义：没有终止符的残帧**不能**投出去 —— 它可能是被截断的半个 JSON，
// 交给下游只会变成一次解析失败。宁可丢弃不完整的事件，也不投半成品。
TEST(SseFrameAssemblerTest, WithholdsAnUnterminatedTrailingEvent)
{
    my_agent::provider::sse::FrameAssembler assembler;

    const std::vector<my_agent::provider::sse::Event> events = collect(
        assembler,
        {"event: done\ndata: {\"partial\":tru"}
    );

    EXPECT_TRUE(events.empty());
}
