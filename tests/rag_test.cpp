// 切片①（issue #40）Red 测试 —— 内容由你按交付清单亲手填入本文件。
// 契约见 include/my_agent/rag/rag.hpp；教材见 agentty/src/rag/bm25.cpp。

#include "my_agent/rag/rag.hpp"

#include <cmath>
#include <cstddef>
#include <gtest/gtest.h>
#include <string>
#include <string_view>
#include <vector>

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