# PDF Trans Tool Architecture v2

## 1. Purpose

Build a reusable PDF-to-Markdown conversion tool that can be embedded into an agent service, with improved readability and retrieval quality.

## 2. Scope

This document covers:

- Current verified converter behavior
- Directory and module architecture
- Agent embedding interface
- Postprocessor strategy for heading quality
- Next development phases and acceptance criteria

## 3. Verified Current Effect

Validation command:

```bash
/root/agent/.venv/bin/python -m pdf_trans.cli \
  --input /root/agent/pdf_trans/endtoend.pdf \
  --output-dir /root/agent/pdf_trans/outputs \
  --partition-strategy auto \
  --chunk-strategy by_title \
  --max-chars 1800 \
  --overlap-chars 200
```

Observed result:

- elements: 92
- chunks: 43
- generated artifacts:
  - outputs/output.md
  - outputs/elements.json
  - outputs/chunks.ndjson
  - outputs/chunks_preview.md
  - outputs/chunks_report.html

Heading quality checks in output.md confirm promoted section headings:

- `## Duplicate message suppression`
- `## Conclusions`
- `## Acknowledgements`
- `## References`

## 4. Current Directory Structure

```text
pdf_trans/
  __init__.py
  README.md
  requirements.txt
  config.py
  models.py
  parser.py
  markdown_formatter.py
  postprocessor.py
  chunker.py
  exporter.py
  visualize.py
  pipeline.py
  service.py
  cli.py
  demo.py
  tests/
    test_markdown_formatter.py
    test_chunker.py
    test_exporter.py
    test_pipeline_integration.py
    test_service.py
  outputs/
  docx/
```

## 5. Module Responsibilities

- parser.py
  - Convert unstructured PDF elements into typed ElementRecord entries.
- markdown_formatter.py
  - Map element types to markdown blocks and apply readability normalization.
- postprocessor.py
  - Promote inline headings and normalize section heading rendering.
- chunker.py
  - Build retrieval chunks; split by markdown heading markers for better recall.
- exporter.py
  - Write markdown/json/ndjson/preview outputs.
- visualize.py
  - Generate HTML report for manual chunk boundary inspection.
- pipeline.py
  - Orchestrate parse -> format -> chunk -> export flow.
- service.py
  - Stable embedding contract for external agent runtimes.

## 6. Agent Embedding Contract

### 6.1 Python API

- Request model: ConvertRequest
- Response model: ConvertResponse
- Function: convert_pdf(request)

### 6.2 JSON Tool API

- Function: convert_pdf_from_dict(payload)
- Input example:

```json
{
  "pdf_path": "/root/agent/pdf_trans/endtoend.pdf",
  "output_dir": "/root/agent/pdf_trans/outputs",
  "partition_strategy": "auto",
  "chunk_strategy": "by_title",
  "max_chunk_chars": 1800,
  "chunk_overlap_chars": 200
}
```

- Output includes:
  - elements_count
  - chunks_count
  - markdown_path
  - elements_json_path
  - chunks_ndjson_path
  - chunks_preview_md_path
  - html_report_path

## 7. Postprocessor Strategy (Implemented)

- Promote sentence-case title/header lines to markdown headings when safe.
- Convert inline heading patterns into section headers, for example:
  - `References 1. ...` -> `## References` + body
  - `Conclusions ...` -> `## Conclusions` + body
- Preserve non-heading lowercase fragments to avoid false positives.

## 8. Remaining Gaps

- Reference section list normalization is still partial (mixed plain lines and bullet list items).
- Some paragraph breaks still reflect PDF extraction artifacts.
- Section metadata is not yet exported as explicit fields in ChunkRecord.

## 9. Next Phases

### Phase 1: Retrieval-oriented structure metadata

- Add optional `section_title`, `section_path`, and `is_reference` fields in chunks.
- Add heading-aware chunk boundary tests for noisy PDFs.

### Phase 2: Reference normalization

- Build reference parser to transform bibliography entries into a consistent list format.
- Preserve citation indices and original text for traceability.

### Phase 3: Agent runtime hardening

- Add timeout/retry wrapper around conversion calls.
- Add strict error schema for tool-call compatibility.
- Add artifact lifecycle strategy (retention and cleanup policy).

## 10. Acceptance Criteria for Future Iteration

- Headings are correctly promoted for major sections in >= 95% sampled pages.
- Chunk boundaries align with heading starts for key sections.
- Service interface remains backward-compatible for existing agent calls.
- Integration tests pass on at least one real paper PDF and one noisy scan-like PDF.
