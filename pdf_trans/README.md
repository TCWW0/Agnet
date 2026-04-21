# PDF to Markdown Converter

This module provides a local pipeline for:

- Parsing PDF with `unstructured`
- Rendering markdown for human inspection
- Generating chunked NDJSON for RAG ingestion
- Exporting chunk previews in Markdown and HTML

## Quick Start

From workspace root:

```bash
source .venv/bin/activate
python -m pdf_trans.cli --input /root/agent/pdf_trans/endtoend.pdf
```

Generated files are written to `pdf_trans/outputs` by default:

- `output.md`
- `elements.json`
- `chunks.ndjson`
- `chunks_preview.md`
- `chunks_report.html`

## Architecture

The toolkit is organized in layered modules:

- `parser.py`: unstructured PDF elements -> typed records
- `markdown_formatter.py`: element-to-markdown rendering
- `postprocessor.py`: readability post-processing (heading normalization)
- `chunker.py`: chunk generation for retrieval
- `exporter.py`: markdown/json/ndjson export
- `visualize.py`: HTML review report
- `pipeline.py`: orchestration
- `service.py`: stable embedding API for agent services
- `cli.py`: terminal entrypoint

## Agent Embedding API

Use the service facade when calling from another runtime:

```python
from pdf_trans.service import ConvertRequest, convert_pdf

request = ConvertRequest(
  pdf_path="/root/agent/pdf_trans/endtoend.pdf",
  output_dir="/root/agent/pdf_trans/outputs",
  chunk_strategy="by_title",
)
response = convert_pdf(request)
print(response.model_dump(mode="json"))
```

JSON-based runtimes can call:

```python
from pdf_trans.service import convert_pdf_from_dict

result = convert_pdf_from_dict({
  "pdf_path": "/root/agent/pdf_trans/endtoend.pdf",
  "output_dir": "/root/agent/pdf_trans/outputs",
  "chunk_strategy": "by_title",
})
```

## CLI Options

```bash
python -m pdf_trans.cli \
  --input /root/agent/pdf_trans/endtoend.pdf \
  --output-dir /root/agent/pdf_trans/outputs \
  --partition-strategy auto \
  --chunk-strategy by_title \
  --max-chars 1800 \
  --overlap-chars 200
```

## Run Tests

```bash
source .venv/bin/activate
pytest -q pdf_trans/tests
```
