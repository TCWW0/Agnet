from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PartitionStrategy = Literal["auto", "fast", "hi_res", "ocr_only"]
ChunkStrategy = Literal["by_title", "static_chars"]


class PipelineConfig(BaseModel):
    """Runtime configuration for PDF conversion pipeline."""

    pdf_path: Path
    output_dir: Path = Field(default=Path("pdf_trans/outputs"))
    partition_strategy: PartitionStrategy = Field(default="auto")
    include_page_breaks: bool = Field(default=False)
    chunk_strategy: ChunkStrategy = Field(default="by_title")
    max_chunk_chars: int = Field(default=1800, ge=200)
    chunk_overlap_chars: int = Field(default=200, ge=0)
    export_html_report: bool = Field(default=True)

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
