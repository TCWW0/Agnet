// 切片①（issue #40）Red 测试 —— 内容由你按交付清单亲手填入本文件。
// 契约见 include/my_agent/rag/rag.hpp；教材见 agentty/src/rag/bm25.cpp。

#include "my_agent/rag/rag.hpp"

#include <cmath>
#include <cstddef>
#include <gtest/gtest.h>
#include <string>
#include <string_view>
#include <vector>
#include <nlohmann/json.hpp>
#include <cstdint>
#include <utility>
#include <expected>

namespace{
    namespace rag = my_agent::rag;

    rag::Chunk make_chunk(std::string text){
        rag::Chunk c;
        c.path = "doc.md";
        c.line_start = 1;
        c.line_end = 1;
        c.text = std::move(text);
        return c;
    }

    // 简单的分词器
    std::vector<std::string> toks_of(std::string_view s){
        std::vector<std::string> out;
        rag::tokenize(s, out);
        return out;
    }

    // 最小的 utf-8 编码校验器，多字节序列必须完整(没被从中间切开)
    bool is_valid_utf8(std::string_view s){
        std::size_t i = 0;
        while(i<s.size()){
            const auto& b = static_cast<unsigned char>(s[i]);
            std::size_t len;
            if      ((b & 0x80) == 0x00) len = 1;
            else if ((b & 0xE0) == 0xC0) len = 2;
            else if ((b & 0xF0) == 0xE0) len = 3;
            else if ((b & 0xF8) == 0xF0) len = 4;
            else return false;                      // 孤立的延续字节
            if (i+len>s.size()) return false;       // 序列被截断
            for(std::size_t j=1;j<len;j++){
                if((static_cast<unsigned char>(s[i+j])&0xC0)!=0x80)
                    return false;
            }
            i+=len;
        }
        return true;
    }

    // 将整体按照换行符来进行切分
    std::vector<std::string> split_lines(std::string_view body) {
        std::vector<std::string> lines;
        std::size_t start = 0;
        for(std::size_t i=0;i<=body.size();++i){
            if(i == body.size()||body[i] =='\n'){
                lines.emplace_back(body.substr(start,i-start));
                start = i+1;
            }
        }
        return lines;
    }

} //namespace

// ── A. tokenize：分词契约（索引/查询共用的唯一入口）─────────────────────

TEST(Tokenize,LowercaseAlphanumericRuns) {
    EXPECT_EQ(toks_of("The Quick-Brown FOX"),
        (std::vector<std::string>{"the","quick","brown","fox"}));
}

//ASCII 字母/数字组成的普通 token，长度必须至少为 2 才会进入最终 token 列表。
TEST(Tokenize, DropsSingleCharacterTokens) {
    EXPECT_EQ(toks_of("a I am"), (std::vector<std::string>{"am"}));
}

//数字可以出现在 token 中，数字不是天然的分隔符。
TEST(Tokenize, DigitsAreKeptAndShortRunsDropped) {
    EXPECT_EQ(toks_of("k1=1.5"), (std::vector<std::string>{"k1"}));
}

// 中文字符默认按照2字进行切割
TEST(Tokenize, CjkRunBecomesOverlappingBigrams) {
    EXPECT_EQ(toks_of("检索引擎"),
              (std::vector<std::string>{"检索", "索引", "引擎"}));
    EXPECT_EQ(toks_of("注册表"),
              (std::vector<std::string>{"注册", "册表"}));
}

// 当中文字符长度只有1时，此时需要保留为token
TEST(Tokenize, LoneCjkCharIsEmittedAsIs) {
    EXPECT_EQ(toks_of("图"), (std::vector<std::string>{"图"}));
}

// 不同文字体系之间不能混在一起处理
TEST(Tokenize, MixedScriptRunsSplitAtBoundaries) {
    EXPECT_EQ(toks_of("配置BM25参数"),
              (std::vector<std::string>{"配置", "bm25", "参数"}));
}

// 对于极端的标点场景，不切分出token
TEST(Tokenize, PunctuationOnlyAndEmptyProduceNothing) {
    EXPECT_TRUE(toks_of("!!! ... ???").empty());
    EXPECT_TRUE(toks_of("").empty());
}

// ── B. chunker：切块契约（行对齐 + 双上限 + 面包屑 + overlap）────────────
TEST(Chunker,ChunksAreLineAlignedWithConsistentSpans){
    const std::string body =
        "first line\nsecond line\n\nthird line\nfourth line\nfifth line\n";
    const auto lines = split_lines(body);
    const auto chunks = rag::chunk_document("doc.md", body,
                                            /*max_lines=*/3, /*max_chars=*/1000,
                                            /*overlap=*/0);
    ASSERT_FALSE(chunks.empty());
    // span 内的源行逐字拼起来（每行带 '\n'）必须等于块的正文。
    for (const auto& c : chunks) {
        ASSERT_GE(c.line_start, 1);
        ASSERT_LE(c.line_end, static_cast<int>(lines.size()));
        ASSERT_LE(c.line_start, c.line_end);
        std::string expected;
        for (int ln = c.line_start; ln <= c.line_end; ++ln)
            expected += lines[ln - 1] + '\n';
        EXPECT_EQ(c.text, expected);
    }
    // 无内容丢失：每个非空白源行都落在某个块里。
    for (std::size_t i = 0; i < lines.size(); ++i) {
        if (lines[i].find_first_not_of(" \t\r") == std::string::npos) continue;
        bool found = false;
        for (const auto& c : chunks)
            if (c.line_start <= static_cast<int>(i) + 1
                && static_cast<int>(i) + 1 <= c.line_end) { found = true; break; }
        EXPECT_TRUE(found) << "line " << (i + 1) << " lost";
    }
}

// 限制一个chunk的最大容量限制不被打破
TEST(Chunker, RespectsMaxCharsBound) {
    std::string body;
    for (int i = 0; i < 30; ++i) body += "0123456789xxxxx\n";   // 16 字节/行
    const auto chunks = rag::chunk_document("big.md", body,
                                            /*max_lines=*/100, /*max_chars=*/64,
                                            /*overlap=*/0);
    ASSERT_GT(chunks.size(), 1u);
    for (const auto& c : chunks) {
        std::string_view t = c.text;
        if (!t.empty() && t.back() == '\n') t.remove_suffix(1);  // 容忍行终止符
        EXPECT_LE(t.size(), 64u) << "chunk overruns max_chars";
    }
}

// 优先按行切chunk，如果某一行达到了上限，直接在达到上限时切掉
TEST(Chunker, HardSplitsOversizedLine) {
    const std::string body(5000, 'a');   // 单行 5000 字符，无换行
    const auto chunks = rag::chunk_document("min.js", body,
                                            /*max_lines=*/40, /*max_chars=*/1000,
                                            /*overlap=*/0);
    ASSERT_FALSE(chunks.empty());
    std::size_t total = 0;
    for (const auto& c : chunks) {
        std::string_view t = c.text;
        if (!t.empty() && t.back() == '\n') t.remove_suffix(1);
        EXPECT_LE(t.size(), 1000u);
        total += t.size();
    }
    EXPECT_EQ(total, 5000u);   // 分片无损：拼回原文
}

TEST(Chunker, HardSplitNeverCutsUtf8Codepoint) {
    std::string line;
    for (int i = 0; i < 400; ++i) line += "汉";   // 400 × 3 字节 = 1200 字节
    const auto chunks = rag::chunk_document("u.md", line,
                                            /*max_lines=*/40, /*max_chars=*/500,
                                            /*overlap=*/0);
    ASSERT_FALSE(chunks.empty());
    std::size_t han_count = 0;
    for (const auto& c : chunks) {
        std::string_view t = c.text;
        if (!t.empty() && t.back() == '\n') t.remove_suffix(1);
        EXPECT_TRUE(is_valid_utf8(t));
        for (std::size_t pos = 0; pos + 3 <= t.size(); pos += 3)
            if (t.substr(pos, 3) == "汉") ++han_count;
    }
    EXPECT_EQ(han_count, 400u);   // 没有码点被吞掉
}

TEST(Chunker, HeadingBreadcrumbCarriesPathAndHeadings) {
    const std::string body =
        "# 安装\n"
        "## Linux\n"
        "run the setup script\n"
        "\n"
        "## macOS\n"
        "brew install everything\n";
    const auto chunks = rag::chunk_document("guide.md", body,
                                            /*max_lines=*/3, /*max_chars=*/200,
                                            /*overlap=*/0);
    ASSERT_FALSE(chunks.empty());
    bool found_linux = false, found_macos = false;
    for (const auto& c : chunks) {
        if (c.text.find("setup script") != std::string::npos) {
            EXPECT_EQ(c.context, "guide.md › 安装 › Linux");
            found_linux = true;
        }
        if (c.text.find("brew install") != std::string::npos) {
            EXPECT_EQ(c.context, "guide.md › 安装 › macOS");
            found_macos = true;
        }
    }
    EXPECT_TRUE(found_linux);
    EXPECT_TRUE(found_macos);
}

TEST(Chunker, SkipsWhitespaceOnlyChunks) {
    EXPECT_TRUE(rag::chunk_document("blank.md", "\n\n   \n\t\n",
                                    40, 1600, 4).empty());
}

TEST(Chunker, OverlapRepeatsBoundaryLines) {
    const std::string body = "l1\nl2\nl3\nl4\nl5\nl6";
    const auto chunks = rag::chunk_document("o.md", body,
                                            /*max_lines=*/3, /*max_chars=*/1000,
                                            /*overlap_lines=*/1);
    ASSERT_GE(chunks.size(), 2u);
    // 相邻块之间有行重叠：后块起点 ≤ 前块终点。
    for (std::size_t i = 1; i < chunks.size(); ++i)
        EXPECT_LE(chunks[i].line_start, chunks[i - 1].line_end);
    // overlap 也不能丢内容：每行仍在某个块里。
    const auto lines = split_lines(body);
    for (std::size_t i = 0; i < lines.size(); ++i) {
        bool found = false;
        for (const auto& c : chunks)
            if (c.line_start <= static_cast<int>(i) + 1
                && static_cast<int>(i) + 1 <= c.line_end) { found = true; break; }
        EXPECT_TRUE(found) << "line " << (i + 1) << " lost";
    }
}

// 最多 3 空格缩进的 ``` 仍是合法围栏（CommonMark）。不认缩进围栏时，
// fence 状态从未进入，围栏内的空行会被当成语义断点，代码块被劈开。
TEST(Chunker, IndentedFenceKeepsBlockIntact) {
    const std::string body =
        "intro line\n"
        "  ```bash\n"
        "a=1\n"
        "\n"
        "b=2\n"
        "```\n"
        "after fence\n";
    const auto chunks = rag::chunk_document("f.md", body, 40, 1000, 0);
    const rag::Chunk* code = nullptr;
    for (const auto& c : chunks)
        if (c.text.find("a=1") != std::string::npos) code = &c;
    ASSERT_NE(code, nullptr);
    EXPECT_NE(code->text.find("b=2"), std::string::npos);
}

// ~~~ 是等价的围栏标记（CommonMark）。同样要进 fence 状态。
TEST(Chunker, TildeFenceKeepsBlockIntact) {
    const std::string body =
        "intro line\n"
        "~~~python\n"
        "x = 1\n"
        "\n"
        "y = 2\n"
        "~~~\n"
        "after fence\n";
    const auto chunks = rag::chunk_document("t.md", body, 40, 1000, 0);
    const rag::Chunk* code = nullptr;
    for (const auto& c : chunks)
        if (c.text.find("x = 1") != std::string::npos) code = &c;
    ASSERT_NE(code, nullptr);
    EXPECT_NE(code->text.find("y = 2"), std::string::npos);
}

// ── C. BM25：建索引 + 打分检索契约 ────────────────────────────────────────

TEST(Bm25, RareTermRanksItsChunkFirst) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("the quick brown fox jumps"),
        make_chunk("lazy dogs sleep all afternoon"),
        make_chunk("pelican migration over oceans"),
        make_chunk("compiler passes and inlining"),
    };
    const auto idx = rag::build_bm25(chunks);
    EXPECT_EQ(idx.doc_count, 4u);
    EXPECT_EQ(idx.doc_len, (std::vector<std::uint32_t>{5, 5, 4, 4}));
    EXPECT_DOUBLE_EQ(idx.avg_doc_len, 4.5);

    const auto hits = rag::bm25_search(idx, "pelican", 4);
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits[0].first, 2u);

    const auto hits2 = rag::bm25_search(idx, "compiler inlining", 4);
    ASSERT_FALSE(hits2.empty());
    EXPECT_EQ(hits2[0].first, 3u);
}

TEST(Bm25, MultiWordCoverageBeatsSingleWordRepetition) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("chunker soft limit hard limit"),   // 覆盖两个查询词
        make_chunk("chunker chunker overview"),        // 只中一个词，tf=2
        make_chunk("unrelated content entirely"),
    };
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "chunker limit", 3);
    ASSERT_GE(hits.size(), 2u);
    EXPECT_EQ(hits[0].first, 0u);
    EXPECT_GT(hits[0].second, hits[1].second);   // 明确胜出，非侥幸
}

TEST(Bm25, RareTermOutranksUbiquitousTerm) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("deploy config and common setup"),
        make_chunk("logging common severity levels"),
        make_chunk("pelican migration common over oceans"),
    };
    const auto idx = rag::build_bm25(chunks);
    // "common" 在全部 3 个文档出现（idf≈0.13）；"pelican" 只在 1 个（idf≈1.2）。
    const auto hits = rag::bm25_search(idx, "common pelican", 3);
    ASSERT_GE(hits.size(), 3u);
    EXPECT_EQ(hits[0].first, 2u);
}

TEST(Bm25, SaturationCapsTermFrequencyAtK1) {
    // 等长文档（dl=12, avgdl=12 → 长度项=1），同一查询词 tf=1 vs tf=10。
    // 期望值由公式手算（独立真值，非从实现反推）：
    //   idf     = ln((2-2+0.5)/(2+0.5) + 1) = ln(1.2)
    //   sat(1)  = 1·(1+1.5)/(1 + 1.5·1)     = 1.0
    //   sat(10) = 10·(1+1.5)/(10 + 1.5·1)   = 25/11.5 ≈ 2.174
    const std::vector<rag::Chunk> chunks{
        make_chunk("kangaroo pad pad pad pad pad pad pad pad pad pad pad"),
        make_chunk("kangaroo kangaroo kangaroo kangaroo kangaroo kangaroo "
                   "kangaroo kangaroo kangaroo kangaroo pad pad"),
    };
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "kangaroo", 2);
    ASSERT_EQ(hits.size(), 2u);
    double s1 = 0.0, s10 = 0.0;
    for (const auto& [doc, score] : hits) {
        if (doc == 0u) s1 = score;
        else           s10 = score;
    }
    const double idf = std::log(0.5 / 2.5 + 1.0);
    EXPECT_NEAR(s1,  idf * 1.0,        1e-9);
    EXPECT_NEAR(s10, idf * 25.0 / 11.5, 1e-9);
    EXPECT_LT(s10, 10.0 * s1);   // tf×10 换不来 10×分数 —— 饱和封顶
}

TEST(Bm25, ShortDocOutranksLongDocAtEqualTf) {
    std::string long_doc = "zebra";
    for (int i = 0; i < 30; ++i) long_doc += " fill";   // dl=31
    const std::vector<rag::Chunk> chunks{
        make_chunk("zebra facts"),      // dl=2，同样的 tf=1
        make_chunk(std::move(long_doc)),
    };
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "zebra", 2);
    ASSERT_EQ(hits.size(), 2u);
    EXPECT_EQ(hits[0].first, 0u);
}

TEST(Bm25, NoMatchReturnsEmptyAndTopKTruncates) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("alpha bravo one"),
        make_chunk("alpha bravo two"),
        make_chunk("alpha bravo three"),
    };
    const auto idx = rag::build_bm25(chunks);
    EXPECT_TRUE(rag::bm25_search(idx, "nonexistent term", 5).empty());
    const auto hits = rag::bm25_search(idx, "alpha bravo", 2);
    EXPECT_EQ(hits.size(), 2u);   // 3 个块都命中，但只取前 k
}

TEST(Bm25, EqualScoresTieBreakByChunkId) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("alpha xxx"),
        make_chunk("alpha yyy"),
        make_chunk("alpha zzz"),
    };
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "alpha", 3);
    ASSERT_EQ(hits.size(), 3u);
    EXPECT_EQ(hits[0].second, hits[1].second);
    EXPECT_EQ(hits[1].second, hits[2].second);
    EXPECT_EQ(hits[0].first, 0u);
    EXPECT_EQ(hits[1].first, 1u);
    EXPECT_EQ(hits[2].first, 2u);
}

TEST(Bm25, BreadcrumbTermsMakeBodylessChunkFindable) {
    const std::string body =
        "# 安装\n"
        "## Linux\n"
        "\n"
        "run the setup script\n"
        "\n"
        "## macOS\n"
        "\n"
        "brew install everything\n";
    const auto all = rag::chunk_document("guide.md", body, 3, 200, 0);
    // 只保留正文里没有 "linux" 的块 —— 让「面包屑里有 linux」成为唯一线索。
    std::vector<rag::Chunk> chunks;
    for (const auto& c : all)
        if (c.text.find("inux") == std::string::npos) chunks.push_back(c);
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "linux", 5);
    ASSERT_FALSE(hits.empty());
    EXPECT_NE(chunks[hits[0].first].text.find("setup script"),
              std::string::npos);
}

TEST(Bm25, ChineseCorpusIsSearchableViaBigrams) {
    const std::vector<rag::Chunk> chunks{
        make_chunk("注册表的配置方法"),
        make_chunk("日志系统的初始化"),
        make_chunk("网络连接的超时设置"),
    };
    const auto idx = rag::build_bm25(chunks);
    const auto hits = rag::bm25_search(idx, "如何配置注册表", 3);
    // ↑ agentty 原版 tokenizer 在这里直接失明（中文产出零 token）。
    ASSERT_FALSE(hits.empty());
    EXPECT_EQ(hits.size(), 1u);   // 只有块 0 与查询共享 bigram
    EXPECT_EQ(hits[0].first, 0u);
}

TEST(EmbedInput,NomicDocAndQueryPrefixes) {
    EXPECT_EQ(rag::embed_input_text("nomic-embed-text", rag::EmbedRole::Doc, "安装指南"),
            "search_document: 安装指南");
    EXPECT_EQ(rag::embed_input_text("nomic-embed-text", rag::EmbedRole::Query,"怎么安装"),
              "search_query: 怎么安装");
}

TEST(EmbedInput, ModelMatchIsCaseInsensitiveSubstring) {
    // 教材同款：小写化后子串匹配 —— 带标签的 "nomic-embed-text:latest" 也要命中
    EXPECT_EQ(rag::embed_input_text("Nomic-Embed-Text:latest",rag::EmbedRole::Doc, "x"),
              "search_document: x");
}

TEST(EmbedInput, E5FamilyUsesPassageAndQuery) {
    EXPECT_EQ(rag::embed_input_text("multilingual-e5-large",rag::EmbedRole::Doc, "x"),
              "passage: x");
    EXPECT_EQ(rag::embed_input_text("multilingual-e5-large",rag::EmbedRole::Query, "x"),
              "query: x");
}

TEST(EmbedInput, UnknownModelGetsNoPrefix) {
    // 错误前缀会伤害不认识它的模型 —— 认不出的名字必须原样放行
    EXPECT_EQ(rag::embed_input_text("llama3", rag::EmbedRole::Doc, "原文"),
              "原文");
    EXPECT_EQ(rag::embed_input_text("llama3", rag::EmbedRole::Query, "原文"),
              "原文");
}

TEST(EmbedRequest, CarriesModelAndOrderedInputArray) {
    const auto body = rag::build_embed_request_body(
        "nomic-embed-text", {"第一条", "second text"});
    const auto j = nlohmann::json::parse(body);   // 能严格解析 = 是合法 JSON
    EXPECT_EQ(j.at("model"), "nomic-embed-text");
    ASSERT_EQ(j.at("input").size(), 2u);
    EXPECT_EQ(j.at("input")[0], "第一条");
    EXPECT_EQ(j.at("input")[1], "second text");
}

TEST(EmbedRequest, EscapesJsonSpecialsInText) {
    // 文本带引号/制表/换行也必须活着过线：靠严格 JSON 转义，不是字符串拼接
    const auto body =
        rag::build_embed_request_body("m", {"quote\" and\ttab\nnewline"});
    const auto j = nlohmann::json::parse(body);
    EXPECT_EQ(j.at("input")[0].get<std::string>(),
              "quote\" and\ttab\nnewline");
}

TEST(EmbedResponse, HappyPathReturnsAlignedVectors) {
    const auto r = rag::parse_embed_response(
        R"({"embeddings":[[0.1,0.2,0.3],[0.4,0.5,0.6]]})", 2);
    ASSERT_TRUE(r.has_value());
    ASSERT_EQ(r->size(), 2u);
    ASSERT_EQ((*r)[0].size(), 3u);
    EXPECT_FLOAT_EQ((*r)[0][0], 0.1f);
    EXPECT_FLOAT_EQ((*r)[1][2], 0.6f);
}

TEST(EmbedResponse, LegacySingleShapeOnlyValidForCountOne) {
    // 旧端点的单数 "embedding"：单条请求时合法（教材兼容同款）
    const auto ok =
        rag::parse_embed_response(R"({"embedding":[0.5,0.6]})", 1);
    ASSERT_TRUE(ok.has_value());
    EXPECT_FLOAT_EQ((*ok)[0][1], 0.6f);
    // 但批量请求拿到它 = 数量失守 → err
    const auto bad =
        rag::parse_embed_response(R"({"embedding":[0.5,0.6]})", 2);
    EXPECT_FALSE(bad.has_value());
}

TEST(EmbedResponse, CountMismatchIsError) {
    // 数量守卫是解析层最要紧的一道岗：
    // 错位（chunk-id↔向量对不上）比整批失败危险得多 —— 失败会降级，错位是静默腐烂
    EXPECT_FALSE(rag::parse_embed_response(
        R"({"embeddings":[[0.1],[0.2]]})", 3).has_value());
}

TEST(EmbedResponse, RaggedRowsAreError) {
    // 行长不齐 = 响应损坏（768 维模型不会返回 767 维）
    EXPECT_FALSE(rag::parse_embed_response(
        R"({"embeddings":[[0.1,0.2],[0.3]]})", 2).has_value());
}

TEST(EmbedResponse, MalformedBodiesAreErrorNotCrash) {
    EXPECT_FALSE(rag::parse_embed_response(R"({"foo":1})", 1).has_value());            // 缺字段
    EXPECT_FALSE(rag::parse_embed_response(R"({"embeddings":"x"})", 1).has_value());   // 顶层非数组
    EXPECT_FALSE(rag::parse_embed_response(R"({"embeddings":[0.1]})", 1).has_value()); // 行非数组
    EXPECT_FALSE(rag::parse_embed_response(R"({"embeddings":[["a"]]})", 1).has_value()); // 非数字元素
    EXPECT_FALSE(rag::parse_embed_response(R"({"embeddings":[[]]})", 1).has_value());  // 空行
    EXPECT_FALSE(rag::parse_embed_response(R"({"embeddings":[]})", 1).has_value());    // 空批
    EXPECT_FALSE(rag::parse_embed_response("not json at all", 1).has_value());         // 垃圾体
}

TEST(Cosine, IdenticalVectorsScoreOne) {
    const std::vector<float> v{0.3f, -0.4f, 0.5f};
    EXPECT_NEAR(rag::cosine_sim(v, v), 1.0, 1e-9);
}

TEST(Cosine, OrthogonalScoresZeroAndOppositeScoresMinusOne) {
    EXPECT_NEAR(rag::cosine_sim({1.f, 0.f}, {0.f, 1.f}), 0.0, 1e-9);
    EXPECT_NEAR(rag::cosine_sim({1.f, 0.f}, {-1.f, 0.f}), -1.0, 1e-9);
}

TEST(Cosine, ScaleInvariantBecauseDirectionIsMeaning) {
    // 模长是干扰项（文本长度等 nuisance），只有方向编码意思 ——
    // 这就是「cosine 不用欧氏距离」的全部理由，写进测试钉死
    const std::vector<float> a{0.1f, 0.2f};
    const std::vector<float> b{1.f, 2.f};   // 同方向、10 倍模长
    EXPECT_NEAR(rag::cosine_sim(a, b), 1.0, 1e-9);
}

TEST(Cosine, MismatchedDimsAndEmptyScoreZero) {
    // 维度不齐 = 状态已腐（建库和查询用了不同维度的模型）：
    // 返回 0 = 零相似、退出竞争 —— 宁可少一个候选，绝不拿错位向量算分
    EXPECT_EQ(rag::cosine_sim({1.f, 2.f}, {1.f, 2.f, 3.f}), 0.0);
    EXPECT_EQ(rag::cosine_sim({}, {}), 0.0);
}

TEST(RankedIds, StripsScoresKeepsOrder) {
    const std::vector<std::pair<std::uint32_t, double>> scored{
        {7u, 9.9}, {2u, 3.3}, {5u, 0.1}};
    EXPECT_EQ(rag::ranked_ids(scored),
              (std::vector<std::uint32_t>{7u, 2u, 5u}));
    EXPECT_TRUE(rag::ranked_ids({}).empty());
}

TEST(Rrf, SingleListKeepsItsRankOrder) {
    // 融合分 = 1/(k + rank_1based)（rank 从 1 数起 —— 教材同款 off-by-one 语义）
    const auto fused = rag::rrf_fuse({{5u, 3u, 1u}}, 60.0, 2);
    ASSERT_EQ(fused.size(), 2u);
    EXPECT_EQ(fused[0].first, 5u);
    EXPECT_DOUBLE_EQ(fused[0].second, 1.0 / 61.0);
    EXPECT_EQ(fused[1].first, 3u);
    EXPECT_DOUBLE_EQ(fused[1].second, 1.0 / 62.0);
}

TEST(Rrf, BothRoadsAgreeBeatsOneRoad) {
    // 两路共识 > 单路意见：2 号在两路各拿一个位次，压过只在一路拿第一的 1 号
    // —— 这是「为什么融合」的最小实例
    const auto fused = rag::rrf_fuse({{1u, 2u}, {2u, 3u}}, 60.0, 3);
    ASSERT_EQ(fused.size(), 3u);
    EXPECT_EQ(fused[0].first, 2u);   // 1/61 + 1/62
    EXPECT_EQ(fused[1].first, 1u);   // 1/61
    EXPECT_EQ(fused[2].first, 3u);   // 1/62
    EXPECT_DOUBLE_EQ(fused[0].second, 1.0 / 61.0 + 1.0 / 62.0);
}

TEST(Rrf, EqualFusedScoresTieBreakByChunkId) {
    const auto fused = rag::rrf_fuse({{9u}, {2u}}, 60.0, 2);
    ASSERT_EQ(fused.size(), 2u);
    EXPECT_EQ(fused[0].first, 2u);   // 同为 1/61 → 确定性：id 升序
    EXPECT_EQ(fused[1].first, 9u);
}

TEST(Rrf, TruncatesToOutK) {
    const auto fused = rag::rrf_fuse({{4u, 1u, 7u}}, 60.0, 1);
    ASSERT_EQ(fused.size(), 1u);
    EXPECT_EQ(fused[0].first, 4u);
}

TEST(Rrf, DeepRankStillContributes) {
    // 候选池深度的存在理由：第 40 名不是零分，是 1/(60+40)——
    // 深位候选仍能在两路叠加后浮上来（hybrid_search 的 pool 语义由此而来）
    std::vector<std::uint32_t> list(40);
    for (std::uint32_t i = 0; i < 40; ++i) list[i] = i;
    const auto fused = rag::rrf_fuse({list}, 60.0, 40);
    ASSERT_EQ(fused.size(), 40u);
    EXPECT_EQ(fused[39].first, 39u);
    EXPECT_DOUBLE_EQ(fused[39].second, 1.0 / 100.0);
}

TEST(Rrf, EmptyInputGivesEmptyOutput) {
    EXPECT_TRUE(rag::rrf_fuse({}, 60.0, 5).empty());
    EXPECT_TRUE(rag::rrf_fuse({{}, {}}, 60.0, 5).empty());
}

// ── 切片 #41 Red 第三批：建库与混合查询（假 backend 模拟模型）────────────
// EmbedBackend 是 std::function —— 测试里用 lambda 假扮 Ollama：
// 按文本内容分发可控向量、记录调用形状（批量数/角色）、按需注入故障。
// 这就是「可注入 backend」决策的全部回报：不碰网络就能钉死管线语义。

TEST(EmbedCorpus, BatchesAt64WithDocRoleAndMapsById) {
    std::vector<rag::Chunk> chunks;
    for (int i = 0; i < 130; ++i)
        chunks.push_back(make_chunk("c" + std::to_string(i)));

    std::vector<std::size_t> batch_sizes;
    std::vector<rag::EmbedRole> roles;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>& texts,
            rag::EmbedRole role)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
            batch_sizes.push_back(texts.size());
            roles.push_back(role);
            std::vector<std::vector<float>> out;
            for (const auto& t : texts)
                out.push_back({static_cast<float>(std::stoi(t.substr(1))),
                               1.f});
            return out;
        };

    const auto dense = rag::embed_corpus(chunks, backend, rag::EmbedConfig{});
    ASSERT_TRUE(dense.has_value());
    EXPECT_EQ(dense->vecs.size(), 130u);
    ASSERT_EQ(dense->vecs[42].size(), 2u);
    EXPECT_FLOAT_EQ(dense->vecs[42][0], 42.f);   // id↔向量对位：第 42 块拿第 42 个向量
    ASSERT_EQ(batch_sizes.size(), 3u);           // 130 = 64 + 64 + 2
    EXPECT_EQ(batch_sizes[0], 64u);
    EXPECT_EQ(batch_sizes[1], 64u);
    EXPECT_EQ(batch_sizes[2], 2u);
    for (rag::EmbedRole r : roles) EXPECT_EQ(r, rag::EmbedRole::Doc);
}

TEST(EmbedCorpus, EmbedInputIsContextPrefixedBody) {
    rag::Chunk c = make_chunk("运行安装脚本");
    c.context = "guide.md › 安装 › Linux";
    std::string seen;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>& texts,
            rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
            seen = texts.front();
            return std::vector<std::vector<float>>{{1.f}};
        };
    ASSERT_TRUE(
        rag::embed_corpus({c}, backend, rag::EmbedConfig{}).has_value());
    // 面包屑前缀（context 空则裸 text —— 上一测试的 "c42" 已钉住该分支）
    EXPECT_EQ(seen, "guide.md › 安装 › Linux\n运行安装脚本");
}

TEST(EmbedCorpus, AnyBatchFailureFailsWholeCorpus) {
    std::vector<rag::Chunk> chunks;
    for (int i = 0; i < 65; ++i)
        chunks.push_back(make_chunk("c" + std::to_string(i)));
    std::size_t calls = 0;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>& texts,
            rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
            if (++calls == 2)   // 第二批（第 65 块那批）失败
                return std::unexpected(std::string{"模拟后端故障"});
            return std::vector<std::vector<float>>(texts.size(), {1.f});
        };
    // 整体 err —— 绝不交出 64/65 的半截 dense（语料中段的静默质量悬崖）
    EXPECT_FALSE(
        rag::embed_corpus(chunks, backend, rag::EmbedConfig{}).has_value());
    EXPECT_EQ(calls, 2u);
}

TEST(EmbedCorpus, RaggedDimsAcrossBatchesIsError) {
    std::vector<rag::Chunk> chunks;
    for (int i = 0; i < 70; ++i)
        chunks.push_back(make_chunk("c" + std::to_string(i)));
    std::size_t calls = 0;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>& texts,
            rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
            const std::size_t dim = (++calls == 1) ? 2 : 3;   // 跨批换维度
            return std::vector<std::vector<float>>(
                texts.size(), std::vector<float>(dim, 1.f));
        };
    EXPECT_FALSE(
        rag::embed_corpus(chunks, backend, rag::EmbedConfig{}).has_value());
    // 两批都被调过 + 这个假 backend 从不主动失败 → err 只能来自维度守卫。
    // （没有这条断言，本测试会被「无条件 err」的桩假绿 —— Red 阶段的陷阱）
    EXPECT_EQ(calls, 2u);
}

TEST(EmbedCorpus, EmptyCorpusGivesEmptyDenseNoCalls) {
    bool called = false;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>&,
            rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
            called = true;
            return std::vector<std::vector<float>>{};
        };
    const auto dense = rag::embed_corpus({}, backend, rag::EmbedConfig{});
    ASSERT_TRUE(dense.has_value());       // 空 dense 是合法状态（BM25-only）
    EXPECT_TRUE(dense->vecs.empty());
    EXPECT_FALSE(called);
}

TEST(Hybrid, FusesBm25AndDenseIntoRRFOrder) {
    // 词法路（query "beta"）：A(=0) 第1、B(=1) 第2，C(=2) 零交集缺席
    // 语义路（假向量）：dense 名次 B, C, A（全为正相似）
    const std::vector<rag::Chunk> chunks{
        make_chunk("beta"),         // A: id 0
        make_chunk("alpha beta"),   // B: id 1
        make_chunk("alpha alpha"),  // C: id 2
    };
    const rag::Bm25Index idx = rag::build_bm25(chunks);
    const rag::DenseIndex dense{{{0.f, 1.f}, {1.f, 0.f}, {1.f, 1.f}}};
    const rag::EmbedConfig cfg{.model = "fake-model"};
    const rag::EmbedBackend backend =
        [](const rag::EmbedConfig&,
           const std::vector<std::string>& texts,
           rag::EmbedRole role)
           -> std::expected<std::vector<std::vector<float>>, std::string> {
        EXPECT_EQ(texts.size(), 1u);               // 查询只向量化一次
        EXPECT_EQ(role, rag::EmbedRole::Query);
        return std::vector<std::vector<float>>{{1.f, 0.1f}};
    };
    const auto fused = rag::hybrid_search(idx, dense, "beta", backend, cfg, 3);
    ASSERT_EQ(fused.size(), 3u);
    // RRF 手算：B = 1/62(词法r2) + 1/61(语义r1) > A = 1/61 + 1/63 > C = 1/62
    EXPECT_EQ(fused[0].first, 1u);
    EXPECT_EQ(fused[1].first, 0u);
    EXPECT_EQ(fused[2].first, 2u);   // C 词法路根本没看见 —— 靠语义路浮上来
    EXPECT_DOUBLE_EQ(fused[0].second, 1.0 / 62.0 + 1.0 / 61.0);
}

TEST(Hybrid, ZeroCosineChunksStayOutOfDenseRank) {
    // 零相似（无信号/维度腐烂）不得进 dense 名次表 ——
    // 否则 RRF 白送它 1/(60+rank)，纯噪音
    const std::vector<rag::Chunk> chunks{
        make_chunk("beta"),         // A: id 0
        make_chunk("gamma gamma"),  // Z: id 1
    };
    const rag::Bm25Index idx = rag::build_bm25(chunks);
    const rag::DenseIndex dense{{{1.f, 0.f}, {0.f, 1.f}}};
    const rag::EmbedConfig cfg{.model = "fake-model"};
    const rag::EmbedBackend backend =
        [](const rag::EmbedConfig&,
           const std::vector<std::string>&,
           rag::EmbedRole)
           -> std::expected<std::vector<std::vector<float>>, std::string> {
        return std::vector<std::vector<float>>{{1.f, 0.f}};
    };
    const auto fused = rag::hybrid_search(idx, dense, "beta", backend, cfg, 5);
    ASSERT_EQ(fused.size(), 1u);   // Z 两路都没份
    EXPECT_EQ(fused[0].first, 0u);
    // A = 词法第1名 + 语义第1名
    EXPECT_DOUBLE_EQ(fused[0].second, 2.0 / 61.0);
}

TEST(Hybrid, EmptyDenseDegradesToBm25WithoutCallingBackend) {
    const std::vector<rag::Chunk> chunks{make_chunk("beta"),
                                         make_chunk("alpha beta")};
    const rag::Bm25Index idx = rag::build_bm25(chunks);
    bool called = false;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
            const std::vector<std::string>&,
            rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
        called = true;
        return std::vector<std::vector<float>>{{1.f}};
    };
    const rag::EmbedConfig cfg{.model = "fake-model"};
    const auto fused =
        rag::hybrid_search(idx, rag::DenseIndex{}, "beta", backend, cfg, 2);
    EXPECT_EQ(fused, rag::bm25_search(idx, "beta", 2));   // 逐位一致，含原始分
    EXPECT_FALSE(called);   // dense 空 → 查询向量化都是浪费
}

TEST(Hybrid, QueryEmbedFailureDegradesToBm25) {
    const std::vector<rag::Chunk> chunks{make_chunk("beta"),
                                         make_chunk("alpha beta")};
    const rag::Bm25Index idx = rag::build_bm25(chunks);
    const rag::DenseIndex dense{{{1.f, 0.f}, {0.f, 1.f}}};
    const rag::EmbedBackend backend =
        [](const rag::EmbedConfig&,
           const std::vector<std::string>&,
           rag::EmbedRole)
           -> std::expected<std::vector<std::vector<float>>, std::string> {
        return std::unexpected(std::string{"模拟查询向量化失败"});
    };
    const rag::EmbedConfig cfg{.model = "fake-model"};
    const auto fused =
        rag::hybrid_search(idx, dense, "beta", backend, cfg, 2);
    EXPECT_EQ(fused, rag::bm25_search(idx, "beta", 2));
}

TEST(Hybrid, EmptyModelDegradesWithoutCallingBackend) {
    const std::vector<rag::Chunk> chunks{make_chunk("beta"),
                                         make_chunk("alpha beta")};
    const rag::Bm25Index idx = rag::build_bm25(chunks);
    bool called = false;
    const rag::EmbedBackend backend =
        [&](const rag::EmbedConfig&,
           const std::vector<std::string>&,
           rag::EmbedRole)
            -> std::expected<std::vector<std::vector<float>>, std::string> {
        called = true;
        return std::vector<std::vector<float>>{{1.f}};
    };
    const rag::EmbedConfig cfg{.model = ""};   // 未配模型 = BM25-only
    const auto fused =
        rag::hybrid_search(idx, rag::DenseIndex{}, "beta", backend, cfg, 2);
    EXPECT_EQ(fused, rag::bm25_search(idx, "beta", 2));
    EXPECT_FALSE(called);
}