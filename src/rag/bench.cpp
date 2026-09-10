// rag_bench 主干：已知答案合成的检索质量基准（#40 的 BM25-only 一级）。
// 全文已在对话中交付（/tmp 验证：agentty/docs 上 recall@5=0.997，MRR=0.980，
// 6 miss 全为近失）—— 由你手敲填入本文件。
// 用法: rag_bench <docs目录> [k]
// 契约见 include/my_agent/rag/rag.hpp；对照 agentty/src/rag/bench.cpp。

#include "my_agent/rag/rag.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <unordered_map>
#include <filesystem>
#include <fstream>

namespace rag = my_agent::rag;
namespace fs = std::filesystem;

namespace {

bool covers(const rag::Chunk& c,const rag::Chunk& gold){
    return c.path == gold.path
        && c.line_start <= gold.line_end
        && gold.line_start <= c.line_end;
}

std::string synthesize_query(const rag::Chunk& c,const rag::Bm25Index& idx) {
    std::vector<std::string> toks;
    rag::tokenize(c.text, toks);

    std::unordered_map<std::string, std::uint32_t> tf;
    for (const auto& t:toks) ++tf[t];

    const double N = static_cast<double>(idx.doc_count);
    struct Scored {double score;const std::string* term;};
    std::vector<Scored> scored;
    scored.reserve(tf.size());
        for (const auto& [term, count] : tf) {
        auto it = idx.term_ids.find(term);
        if (it == idx.term_ids.end()) continue;   // 理论不可达：词就在本块里
        const double df = static_cast<double>(idx.postings[it->second].size());
        scored.push_back({count * std::log((N + 1.0) / (df + 0.5)), &term});
    }
    // 排序全定：分数降序，同分按字典序 —— 同语料永远出同一组查询。
    std::sort(scored.begin(), scored.end(), [](const Scored& a, const Scored& b) {
        if (a.score != b.score) return a.score > b.score;
        return *a.term < *b.term;
    });

    std::string q;
    for (std::size_t i = 0; i < scored.size() && i < 4; ++i) {
        if (!q.empty()) q += ' ';
        q += *scored[i].term;
    }
    return q;
}

std::string miss_line(std::string_view tag, std::string_view query,
                      const rag::Chunk& gold) {
    std::string s = "  [";
    s += tag;
    s += "] \"";
    s += query;
    s += "\" -> ";
    s += gold.path;
    s += ":" + std::to_string(gold.line_start) + "-" + std::to_string(gold.line_end);
    return s;
}

}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "用法: rag_bench <docs目录> [k]\n";
        return 1;
    }
    const fs::path root = argv[1];
    const std::size_t k = argc >= 3 ? std::stoul(argv[2]) : 5;

    // 1) 收语料：递归找 .md，路径排序 —— 目录遍历顺序不定，排序换确定性。
    std::vector<fs::path> files;
    for (const auto& entry : fs::recursive_directory_iterator(root))
        if (entry.is_regular_file() && entry.path().extension() == ".md")
            files.push_back(entry.path());
    std::sort(files.begin(), files.end());
    if (files.empty()) {
        std::cerr << "目录里没有 .md: " << root << "\n";
        return 1;
    }

    // 2) 建库：真实语料 chunk → 倒排索引（同时是本片的端到端验证）。
    std::vector<rag::Chunk> chunks;
    for (const auto& f : files) {
        std::ifstream in(f, std::ios::binary);
        std::string body{std::istreambuf_iterator<char>(in),
                         std::istreambuf_iterator<char>()};
        for (auto& c : rag::chunk_document(f.string(), body))
            chunks.push_back(std::move(c));
    }
    const rag::Bm25Index idx = rag::build_bm25(chunks);

    // 3) 合成已知答案查询（过短块词袋贫乏，只会污染指标）。
    struct Case { std::string query; std::uint32_t gold; };
    std::vector<Case> cases;
    for (std::uint32_t d = 0; d < chunks.size(); ++d)
        if (chunks[d].text.size() >= 120)
            cases.push_back({synthesize_query(chunks[d], idx), d});

    // 4) 跑检索，覆盖匹配统计。取 pool 个结果，名次才知道。
    const std::size_t pool = std::max<std::size_t>(k * 5, 30);
    double recall = 0.0, mrr = 0.0;
    std::vector<std::string> misses;
    const auto t0 = std::chrono::steady_clock::now();
    for (const auto& [query, gold] : cases) {
        const auto ranked = rag::bm25_search(idx, query, pool);
        bool found = false;
        std::size_t rank = 0;
        for (; rank < ranked.size(); ++rank)
            if (covers(chunks[ranked[rank].first], chunks[gold])) { found = true; break; }
        if (!found) {
            misses.push_back(miss_line("rank>" + std::to_string(pool), query,
                                       chunks[gold]));
            continue;
        }
        mrr += 1.0 / static_cast<double>(rank + 1);
        if (rank < k) {
            recall += 1.0;
        } else {
            misses.push_back(miss_line("rank " + std::to_string(rank + 1), query,
                                       chunks[gold]));
        }
    }
    const auto t1 = std::chrono::steady_clock::now();

    // 5) 报告。
    const double n = static_cast<double>(cases.size());
    std::cout << "files=" << files.size()
              << " chunks=" << chunks.size()
              << " queries=" << cases.size()
              << " k=" << k << "\n";
    std::cout << "recall@" << k << " = " << (n > 0 ? recall / n : 0.0) << "\n";
    std::cout << "MRR      = " << (n > 0 ? mrr / n : 0.0) << "\n";
    const double us = cases.empty() ? 0.0
        : std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count()
          / static_cast<double>(cases.size());
    std::cout << us << " us/query\n";
    if (!misses.empty()) {
        std::cout << "misses: " << misses.size() << " (showing first 10)\n";
        for (std::size_t i = 0; i < misses.size() && i < 10; ++i)
            std::cout << misses[i] << "\n";
    }
    return 0;
}
