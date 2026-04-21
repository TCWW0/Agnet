from __future__ import annotations

from pathlib import Path

import pdf_trans.service as service
from pdf_trans.pipeline import PipelineResult


def test_convert_pdf_from_dict_uses_pipeline_contract(tmp_path, monkeypatch) -> None:
    fake_result = PipelineResult(
        elements_count=12,
        chunks_count=5,
        markdown_path=tmp_path / "output.md",
        elements_json_path=tmp_path / "elements.json",
        chunks_ndjson_path=tmp_path / "chunks.ndjson",
        chunks_preview_md_path=tmp_path / "chunks_preview.md",
        html_report_path=tmp_path / "chunks_report.html",
    )

    def _fake_run_pipeline(_config):
        return fake_result

    monkeypatch.setattr(service, "run_pipeline", _fake_run_pipeline)

    payload = {
        "pdf_path": str(tmp_path / "sample.pdf"),
        "output_dir": str(tmp_path / "outputs"),
        "chunk_strategy": "by_title",
        "partition_strategy": "auto",
    }
    response = service.convert_pdf_from_dict(payload)

    assert response["elements_count"] == 12
    assert response["chunks_count"] == 5
    assert response["markdown_path"].endswith("output.md")


def test_convert_request_accepts_path_objects() -> None:
    request = service.ConvertRequest(pdf_path=Path("/tmp/input.pdf"))
    assert request.chunk_strategy == "by_title"
    assert request.partition_strategy == "auto"