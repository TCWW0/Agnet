from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .config import ChunkStrategy, PartitionStrategy, PipelineConfig
from .pipeline import PipelineResult, run_pipeline


class ConvertRequest(BaseModel):
    """Stable request contract for embedding the converter in agent services."""

    pdf_path: Path
    output_dir: Path = Field(default=Path("pdf_trans/outputs"))
    partition_strategy: PartitionStrategy = Field(default="auto")
    include_page_breaks: bool = Field(default=False)
    chunk_strategy: ChunkStrategy = Field(default="by_title")
    max_chunk_chars: int = Field(default=1800, ge=200)
    chunk_overlap_chars: int = Field(default=200, ge=0)
    export_html_report: bool = Field(default=True)


class ConvertResponse(BaseModel):
    elements_count: int
    chunks_count: int
    markdown_path: Path
    elements_json_path: Path
    chunks_ndjson_path: Path
    chunks_preview_md_path: Path
    html_report_path: Optional[Path] = None

    @classmethod
    def from_pipeline_result(cls, result: PipelineResult) -> "ConvertResponse":
        return cls(
            elements_count=result.elements_count,
            chunks_count=result.chunks_count,
            markdown_path=result.markdown_path,
            elements_json_path=result.elements_json_path,
            chunks_ndjson_path=result.chunks_ndjson_path,
            chunks_preview_md_path=result.chunks_preview_md_path,
            html_report_path=result.html_report_path,
        )


def convert_pdf(request: ConvertRequest) -> ConvertResponse:
    pipeline_config = PipelineConfig(
        pdf_path=request.pdf_path,
        output_dir=request.output_dir,
        partition_strategy=request.partition_strategy,
        include_page_breaks=request.include_page_breaks,
        chunk_strategy=request.chunk_strategy,
        max_chunk_chars=request.max_chunk_chars,
        chunk_overlap_chars=request.chunk_overlap_chars,
        export_html_report=request.export_html_report,
    )
    return ConvertResponse.from_pipeline_result(run_pipeline(pipeline_config))


def convert_pdf_from_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """JSON-friendly wrapper for tool calls from external agent runtimes."""

    request = ConvertRequest.model_validate(payload)
    response = convert_pdf(request)
    return response.model_dump(mode="json")