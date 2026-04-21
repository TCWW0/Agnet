from __future__ import annotations

from pathlib import Path

import pytest

from pdf_trans.config import PipelineConfig
from pdf_trans.pipeline import run_pipeline


@pytest.mark.integration
def test_pipeline_runs_with_sample_pdf(tmp_path) -> None:
    sample_pdf = Path("/root/agent/pdf_trans/endtoend.pdf")
    if not sample_pdf.exists():
        pytest.skip("sample pdf does not exist")

    result = run_pipeline(
        PipelineConfig(
            pdf_path=sample_pdf,
            output_dir=tmp_path / "outputs",
            partition_strategy="fast",
            chunk_strategy="by_title",
            max_chunk_chars=1800,
            chunk_overlap_chars=200,
            export_html_report=False,
        )
    )

    assert result.elements_count > 0
    assert result.chunks_count > 0

    markdown_text = result.markdown_path.read_text(encoding="utf-8")
    assert "END-TO-END" in markdown_text or "End-to-End" in markdown_text

    chunks_text = result.chunks_ndjson_path.read_text(encoding="utf-8")
    assert chunks_text.strip()
