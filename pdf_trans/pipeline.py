from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .chunker import build_chunks
from .config import PipelineConfig
from .exporter import (
    export_chunk_preview_markdown,
    export_chunks_ndjson,
    export_elements_json,
    export_markdown,
)
from .markdown_formatter import render_markdown
from .parser import parse_pdf_to_elements
from .visualize import export_chunk_report_html


class PipelineResult(BaseModel):
    elements_count: int
    chunks_count: int
    markdown_path: Path
    elements_json_path: Path
    chunks_ndjson_path: Path
    chunks_preview_md_path: Path
    html_report_path: Optional[Path] = None


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    config.ensure_output_dir()

    parsed_elements = parse_pdf_to_elements(
        pdf_path=config.pdf_path,
        strategy=config.partition_strategy,
        include_page_breaks=config.include_page_breaks,
    )
    rendered_elements, markdown = render_markdown(parsed_elements)

    chunks = build_chunks(
        elements=rendered_elements,
        strategy=config.chunk_strategy,
        max_chunk_chars=config.max_chunk_chars,
        overlap_chars=config.chunk_overlap_chars,
    )

    markdown_path = config.output_dir / "output.md"
    elements_json_path = config.output_dir / "elements.json"
    chunks_ndjson_path = config.output_dir / "chunks.ndjson"
    chunks_preview_md_path = config.output_dir / "chunks_preview.md"

    export_markdown(markdown, markdown_path)
    export_elements_json(rendered_elements, elements_json_path)
    export_chunks_ndjson(chunks, chunks_ndjson_path)
    export_chunk_preview_markdown(chunks, chunks_preview_md_path)

    html_report_path = None
    if config.export_html_report:
        html_report_path = config.output_dir / "chunks_report.html"
        export_chunk_report_html(chunks, html_report_path)

    return PipelineResult(
        elements_count=len(rendered_elements),
        chunks_count=len(chunks),
        markdown_path=markdown_path,
        elements_json_path=elements_json_path,
        chunks_ndjson_path=chunks_ndjson_path,
        chunks_preview_md_path=chunks_preview_md_path,
        html_report_path=html_report_path,
    )
