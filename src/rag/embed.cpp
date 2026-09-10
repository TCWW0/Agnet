// 切片 #41（issue #41）语义路 —— Ollama /api/embed 客户端 + 前缀方言。
// 本文件先是可编译空桩：rag_test 的 Red 阶段要求「编译过、断言挂」，
// Green 实现由用户按交付的 Red 测试亲手填入（学习线分工，见记忆
// feedback_tdd_division）。教材对照：agentty/src/rag/corpus.cpp 的
// embed_texts / prefix_style / with_doc_prefix / with_query_prefix。
//
// 实现依赖在这里、且只在这里：nlohmann 与 my_agent_http 都不进头文件
// （接口纯净原则，见 rag.hpp 顶部注释）。
#include "my_agent/http/http_client.hpp"
#include "my_agent/rag/rag.hpp"
#include "nlohmann/json_fwd.hpp"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <expected>
#include <nlohmann/json.hpp>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace my_agent::rag {

// ── 纯函数（Red 第一批的目标）────────────────────────────────────────────

std::string embed_input_text(std::string_view model, EmbedRole role, std::string_view text) {
    std::string m (model);
    for (auto& c:m)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));

    std::string_view doc_prefix,query_prefix;
    if (m.find("nomic-embed")!=std::string::npos){
        doc_prefix = "search_document: ";
        query_prefix = "search_query: ";
    } else if (m.find("e5") != std::string::npos && 
               m.find("nomic") == std::string::npos) {
        doc_prefix = "passage: ";
        query_prefix = "query: ";
    } else {
        return std::string{text};
    }

    std::string out(role==EmbedRole::Doc?doc_prefix:query_prefix);
    out+=text;
    return out;
}

std::string build_embed_request_body(std::string_view model,
                                     const std::vector<std::string>& texts) {
    nlohmann::json body;
    body["model"] = std::string{model};
    body["input"] = texts;
    return body.dump();  // 桩：空请求体（Red 应挂）
}

std::expected<std::vector<std::vector<float>>, std::string>
parse_embed_response(std::string_view body, std::size_t expected_count) {
    nlohmann::json j;
    try{
        j = nlohmann::json::parse(body);
    } catch(const std::exception& e){
        return std::unexpected(std::string{"embed 相应不是合法 JSON: "}+e.what());
    }

    const nlohmann::json* arr = nullptr;
    nlohmann::json wrapped;
    if (j.contains("embeddings") && j["embeddings"].is_array()) {
        arr = &j["embeddings"];
    } else if (j.contains("embedding") && j["embedding"].is_array()) {
        wrapped = nlohmann::json::array({j["embedding"]});
        arr = &wrapped;
    }
    if (!arr)
        return std::unexpected(std::string{"embed 相应缺 embeddings/embedding 数组"});

    // 数量守卫：解析层最要紧的一道岗。错位比失败危险得多 ——
    // 失败会降级（显式、可诊断），错位是 chunk-id↔向量对不上号的静默腐烂。
    if (arr->size() != expected_count)
        return std::unexpected("embed 响应数量失守: 期望 " +
                               std::to_string(expected_count) + " 条, 实得 " +
                               std::to_string(arr->size()) + " 条");
    if (arr->empty())
        return std::unexpected(std::string{"embed 响应为空批"});

    std::vector<std::vector<float>> out;
    out.reserve(arr->size());
    std::size_t dim = 0;
    for (const auto& row : *arr) {
        if (!row.is_array())
            return std::unexpected(std::string{"embed 响应的行不是数组"});
        if (row.empty())
            return std::unexpected(std::string{"embed 响应含空向量"});
        if (dim == 0)
            dim = row.size();      // 首行定基准维度
        else if (row.size() != dim)
            return std::unexpected("embed 响应行长不齐: 基准 " +
                                   std::to_string(dim) + " 维, 实得 " +
                                   std::to_string(row.size()) + " 维");

        std::vector<float> v;
        v.reserve(row.size());
        for (const auto& x : row) {
            if (!x.is_number())
                return std::unexpected(
                    std::string{"embed 响应含非数字元素"});
            v.push_back(static_cast<float>(x.get<double>()));
        }
        out.push_back(std::move(v));
    }
    return out;
}

// ── 真实后端（HTTP 胶水：方言 → 拼包 → POST → 解析+数量守卫）────────────

std::expected<std::vector<std::vector<float>>, std::string>
ollama_embed(const EmbedConfig& cfg, const std::vector<std::string>& texts, EmbedRole role) {
    if (cfg.model.empty())
        return std::unexpected(std::string{"未配置 embed 模型"});
    if (texts.empty())
        return std::unexpected(std::string{"embed 输入为空批"});

    std::vector<std::string> prefixed;
    prefixed.reserve(texts.size());
    for (const auto& t:texts)
        prefixed.push_back(embed_input_text(cfg.model, role, t));
    const std::string body = build_embed_request_body(cfg.model, prefixed);

    http::HttpClient client;
    const auto result = client.post(
        http::HttpRequest{
            .host       = cfg.host,
            .port       = cfg.port,
            .path       = "/api/embed",
            .headers    = {{"content-type","application/json"}},
            .body       = body,
            .use_tls    = false,
            .timeout_ms = cfg.timeout_ms,
        }
    );
    // Non2xx 时错误响应体已在 http 层收进 message（如 Ollama 的
    // "model not found" 诊断），这里不需要再拼。
    if (!result)
        return std::unexpected("HTTP 失败：" + result.error().message);
    return parse_embed_response(*result, texts.size());
}

// ── 建库（Red 第三批的目标）──────────────────────────────────────────────

std::expected<DenseIndex, std::string>
embed_corpus(const std::vector<Chunk>& chunks, const EmbedBackend& backend, const EmbedConfig& cfg) {
    DenseIndex dense;
    if (chunks.empty()) return dense;
    dense.vecs.reserve(chunks.size());
    for (std::size_t base = 0;base < chunks.size();base += kEmbedBatch){
        const std::size_t hi = std::min(base + kEmbedBatch,chunks.size());

        std::vector<std::string> inputs;
        inputs.reserve(hi-base);
        for(std::size_t i = base;i<hi;++i){
            if (chunks[i].context.empty()){
                inputs.push_back(chunks[i].text);
            }else {
                inputs.push_back(chunks[i].context + '\n' + chunks[i].text);
            }
        }

        auto batch = backend(cfg,inputs,EmbedRole::Doc);
        if (!batch)
            return std::unexpected("第"+std::to_string(base/kEmbedBatch +1)+
                                "批向量化失败："+std::move(batch).error());
        if (batch -> size() != hi -base)
            return std::unexpected("backend 返回数量与输入不符: 期望 " +
                                   std::to_string(hi - base) + " 实得 " +
                                   std::to_string(batch->size()));

        for (auto& v : *batch) {
            if (v.empty())
                return std::unexpected(std::string{"backend 返回空向量"});
            // 维度守卫：与首向量对齐（首个向量本身免检，它就是基准）——
            // 跨批换维度（换模型）在这里拦下，错位比失败危险得多
            if (!dense.vecs.empty() &&
                v.size() != dense.vecs.front().size())
                return std::unexpected("向量维度不齐: 首批 " +
                                       std::to_string(dense.vecs.front().size()) +
                                       " 维, 实得 " +
                                       std::to_string(v.size()) + " 维");
            dense.vecs.push_back(std::move(v));
        }
    }
    return dense;
}

} // namespace my_agent::rag
