<!-- markdownlint-disable-file -->

# Task Research Notes: PDF to MD 转换系统设计

## Research Executed

### File Analysis

- /root/agent/pdf_trans/demo.py
  - 使用 `unstructured.partition.pdf.partition_pdf`（`strategy="fast"`）对 PDF 分段；
  - 将 `Title` -> 二级标题（`##`），`NarrativeText` -> 普通段落，`ListItem` -> `- ` 列表，`Table` -> 用 ```table ``` 包裹并写入 `el.text`；
  - 脚本最终写出 `output.md` 文件。
  - 结论：当前实现是一个最小可行示例（POC），直接映射 `unstructured` 元素到 Markdown，缺少：精细 chunking、metadata（page, bbox, element id）、token-aware 切分与导出格式（JSON/NDJSON）供 RAG 使用。

### Code Search Results

- `partition_pdf`
  - 在仓库/外部代码中实际匹配到：
    - `unstructured/unstructured/partition/pdf.py`（实现、策略、decorator `@add_chunking_strategy`）
    - `test_unstructured/partition/pdf_image/test_pdf.py`（大量关于 `fast`/`hi_res`/`ocr_only` 策略的测试）
    - `unstructured/partition/auto.py`（`partition()` 路由到 `partition_pdf`）
- `chunking_strategy` / `add_chunking_strategy`
  - `partition_pdf` 上使用了 `add_chunking_strategy` 装饰器，表明 `unstructured` 自身支持在分段后进行分块策略。

### External Research

- #githubRepo:"Unstructured-IO/unstructured partition_pdf"
  - 实证要点：`partition_pdf` 支持 `strategy`（`fast`/`hi_res`/`ocr_only`），可选 `include_page_breaks`、`infer_table_structure`、`starting_page_number` 等参数；内部实现会产出可带 metadata（filename、page_number、coordinates/bbox、detection_origin）的 `Element` 列表；库里也有 `chunking` 相关工具与测试用例（可复用）。

- #fetch:https://docs.unstructured.io
  - 关键信息：`unstructured` 的 docs 描述了 partition（high_res/fast）、enrichments（generative OCR、table->HTML 等）、可以导出 JSON 视图以供 RAG 使用；UI 支持可视化 bounding-box，并能导出 JSON 分段结果。

- #fetch:https://developers.openai.com/api/docs/guides/retrieval
  - 关键信息：向量检索/文件上传处默认 chunk 策略：`max_chunk_size_tokens` 默认 800，`chunk_overlap_tokens` 默认 400；添加文件时可传 `chunking_strategy`，并可对文件设置 `attributes`（metadata）用于过滤；RAG 最佳实践包含：保留来源与上下文、适当 chunk 大小与 overlap、保存检索时的评分/来源以便溯源。

## Key Discoveries

### Project Structure

- 目前 `pdf_trans/` 内已有一个轻量 POC：`demo.py` 和样例 `endtoend.pdf`、`output.md`；该目录是合适的实现位置（用户要求尽量不污染外部设计）。
- 推荐方案：在 `pdf_trans/` 内新增模块化代码（parser、md-formatter、chunker、exporter、visualizer），并保持单一入口脚本（或 CLI）以便集成测试。

### Implementation Patterns

- 使用 `unstructured.partition.pdf.partition_pdf(...)` 提取元素（保留 metadata）；
- 对 `Element` 做两层处理：
  1. 语义化映射 -> Markdown（保留元素类型、页码、bbox、source）
  2. Token-aware 或 结构化 title-aware chunking -> 生成可索引 chunk（每个 chunk 带 metadata）
- 存储/导出：
  - 用 NDJSON/JSON 每行一 chunk（包含 metadata 字段）方便批量上传到向量 DB；
  - 同时保留单一 `*.md` 文档用于人工查看与 diff；
- 可视化/验证：输出一个小型 HTML/静态页面或 Notebook，展示 chunk 对应的原始页面、bbox 与 markdown 片段，便于人工评估切分质量并调整参数。

### Complete Examples

```python
# 示例：将 PDF -> elements -> 带 metadata 的 markdown chunks
from unstructured.partition.pdf import partition_pdf
from uuid import uuid4

def elements_to_chunks(elements):
    # 简化示例：按 Title 分组再做 token-based 拆分
    chunks = []
    for el in elements:
        metadata = {
            "filename": el.metadata.filename,
            "page": getattr(el.metadata, "page_number", None),
            "bbox": getattr(el.metadata, "coordinates", None),
            "type": el.__class__.__name__,
        }
        text = el.text.strip() if hasattr(el, "text") else ""
        chunks.append({"id": str(uuid4()), "text": text, "metadata": metadata})
    return chunks

els = partition_pdf("example.pdf", strategy="fast")
chunks = elements_to_chunks(els)
# 导出为 NDJSON/MD、并供后续 chunker/embeddings 使用
```

### API and Schema Documentation

建议的 chunk JSON schema（每个 chunk 一条记录）:

```json
{
  "id": "uuid",
  "text": "...",
  "source_file": "endtoend.pdf",
  "page": 12,
  "element_type": "NarrativeText",
  "bbox": [[x1,y1],[x2,y2],...],
  "tokens": 420,
  "chunk_id": 0,
  "chunk_strategy": "by_title|static_tokens",
  "created_at": 1710000000
}
```

### Configuration Examples

```json
{
  "partition": { "strategy": "auto", "include_page_breaks": true },
  "chunking": { "type": "static_tokens", "max_chunk_tokens": 800, "overlap_tokens": 200 },
  "export": { "format": ["ndjson","md"], "vector_store": "chroma" }
}
```

### Technical Requirements

- Python 3.9+
- 必需包：`unstructured`（已安装），`openai`（如使用 OpenAI 向量服务 / Embeddings API），`chromadb`/`faiss`/`pinecone-client`（任选）、`tiktoken` 或其他 tokenizer 用于 token 计数。
- 可选工具：`pdf2image`、`pytesseract`（OCR 路径）、可视化依赖（Flask/Streamlit/Notebook）

## Recommended Approach

单一路线（推荐且已验证可行）：

- 本地增量流水线（满足用户“先小范围实现、后逐步放宽格式假设”的要求）：
  1. 使用 `unstructured.partition_pdf`（策略：`auto` 或基于文件复杂度的 `fast/hi_res`）产生 `Element` 列表并保留 metadata；
  2. 先实现两种分块策略：
     - `by_title`：基于 `Title` 元素的结构化分块（适用于论文/报告类）
     - `static_tokens`：基于 token 数的静态切分 + 重叠（适用于无明确标题的文档）
  3. 生成两种导出：可读的 `output.md`（便于人工验证）和机器友好的 `chunks.ndjson`（每行一个 chunk 带 metadata）
  4. 支持可视化验证（HTML/Notebook）：展示 chunk->page->bbox->md 三联视图，用于评估切分质量并调整参数；
  5. 将 `chunks.ndjson` 上传到目标向量库（Chroma/FAISS/Pinecone/OpenAI vector stores），并保存映射 `chunk_id -> source metadata` 以便溯源。

理由：该方案最小侵入（只在 `pdf_trans/` 下实现），可快速验证分块效果，并能平滑扩展到使用 `unstructured` 的高精度 `hi_res` 流水线或使用外部 enrichments（table->HTML、generative OCR）。

## Implementation Guidance

- **Objectives**: 从 PDF 可靠生成对 RAG 有用的 chunk（含 metadata），并能人工与自动化评估切分质量。
- **Key Tasks**:
  - 在 `pdf_trans/` 下新增 `parser.py`, `formatter.py`, `chunker.py`, `exporter.py`, `visualize.py` 五个模块；
  - `parser.py`: 负责调用 `partition_pdf` 并将 Element 列表序列化为中间 JSON（包含原始 metadata）；
  - `formatter.py`: 将元素映射为 Markdown（可选：保留 front-matter YAML）；
  - `chunker.py`: 实现 `by_title` 与 `static_tokens` 两种策略（用 `tiktoken` 估算 tokens）；
  - `exporter.py`: 支持 `ndjson`、`md`、`html(visualize)` 导出，并提供批量上传向量库的工具（可选：OpenAI 的 `client.vector_stores.files.create_and_poll` 示例）；
  - `visualize.py`: 生成本地 HTML/Notebook 以供人工检查（page、bbox、md-chunk 三视图）。
- **Dependencies**: `unstructured`, `tiktoken` (或词元估算函数)、`chromadb`/`pinecone-client`、`openai`（如需 embeddings）；
- **Success Criteria**:
  - 成功将样例 `endtoend.pdf` 产出 `output.md` 与 `chunks.ndjson`；
  - 可视化页面正确展示 chunk->源页->bbox；
  - 向量库可成功索引上传的 chunk（并能用语义检索返回合理片段）；
  - 在论文类 PDF（带 Title 的）上，`by_title` 策略优于单纯 token 静态切分（更高召回/精确度于人工评估）。


## Recommended Next Step

在 `pdf_trans/` 里实现最小 POC：
- `parser.py`（wrap `partition_pdf` 并输出 elements.json）
- `formatter.py`（elements -> md）
- `chunker.py`（实现 `by_title` + `static_tokens`）
- `exporter.py`（ndjson/md 输出）
- `visualize.py`（Notebook/HTML 验证）

完成后运行：

```bash
python -m pdf_trans.parser --input endtoend.pdf --out elements.json
python -m pdf_trans.formatter --elements elements.json --out output.md
python -m pdf_trans.chunker --elements elements.json --out chunks.ndjson --strategy static_tokens
```
