#pragma once
// my_agent::rag — 文档 RAG 主干（学习线：复刻 agentty/src/rag/ 的主干四片）。
//
// 本头文件是切片 #40 的接缝契约：chunker + tokenize + BM25（词匹配路）。
// 语义路（embed + cosine + RRF 融合）是切片 #41，Corpus 建库落盘是 #42，
// search_docs 工具接线是 #43。
//
// 设计要点：
//   • tokenize 是索引端与查询端共用的唯一分词入口 —— 同一个函数保证两边
//     词表一致，这是 BM25 正确性的前提。
//       - ASCII：小写字母数字连续段为一个 token；不足 2 字节的 token
//         丢弃（单字符无检索信号）。
//       - 非 ASCII：按 UTF-8 码点解码，连续段切重叠二元组（CJK bigram，
//         Lucene CJKBigramFilter 思路：无词典、对新词免疫、索引与查询
//         切法必然一致）。孤立单字段原样发出。
//   • BM25 常量：k1 = 1.5（tf 饱和），b = 0.75（长度归一）。
//   • chunker：行对齐切块。max_lines 是软上限（绝不在代码围栏中间断开），
//     max_chars 是硬上限（超长单行先按 UTF-8 边界强制分片再进切块循环）。

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace my_agent::rag {

// 一个可检索单元：源文档中一段有界的、行对齐的切片。
struct Chunk {
    std::string path;       // 源文件（相对路径）
    int line_start = 0;     // 1-based，闭区间
    int line_end   = 0;     // 1-based，闭区间
    std::string text;       // 块正文（逐字保留；喂给模型的就是它）

    // 面包屑（contextual retrieval）：块所在的文档 + 标题链，
    // 形如 "guide.md › 安装 › Linux"。参与 BM25 索引（标题 token 以
    // 3 份副本入袋 = 字段加权），但绝不作为正文展示。
    std::string context;
};

// 分词：s 的 token 序列追加进 out（不清空 out）。索引与查询共用。
void tokenize(std::string_view s, std::vector<std::string>& out);

// Okapi BM25 倒排索引。term_ids 由索引自身持有（非全局），多语料可共存。
struct Bm25Index {
    struct Posting { std::uint32_t doc; std::uint32_t tf; };
    std::vector<std::vector<Posting>> postings;  // term-id → 出现名单
    std::vector<std::uint32_t>        doc_len;   // chunk-id → token 总数（含重复）
    double avg_doc_len = 0.0;
    std::size_t doc_count = 0;
    std::unordered_map<std::string, std::uint32_t> term_ids;  // 词串 → term-id
};

// 建索引：每块的正文 + 面包屑（3 份副本字段加权）一起进词袋。
[[nodiscard]] Bm25Index build_bm25(const std::vector<Chunk>& chunks);

// 打分检索：按分数降序返回 (chunk-id, score)，截断至前 k；零交集的块
// 不出现在结果里；同分按 chunk-id 升序。
[[nodiscard]] std::vector<std::pair<std::uint32_t, double>>
bm25_search(const Bm25Index& idx, std::string_view query, std::size_t k);

// 切块：把一份文档拆成有界的行对齐块。max_lines 软上限（不打断代码
// 围栏），max_chars 硬上限（超长行先按 UTF-8 边界分片），overlap_lines
// 让跨块边界的事实落进相邻两个块。
[[nodiscard]] std::vector<Chunk>
chunk_document(const std::string& path, const std::string& body,
               std::size_t max_lines = 40, std::size_t max_chars = 1600,
               std::size_t overlap_lines = 4);

} // namespace my_agent::rag
