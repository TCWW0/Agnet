from __future__ import annotations

import json

from pdf_trans.exporter import (
    export_chunk_preview_markdown,
    export_chunks_ndjson,
    export_elements_json,
    export_markdown,
)
from pdf_trans.models import ChunkRecord, ElementMetadata, ElementRecord


def test_exporters_write_expected_files(tmp_path) -> None:
    elements = [
        ElementRecord(
            element_id="e1",
            element_type="NarrativeText",
            text="hello",
            markdown="hello",
            metadata=ElementMetadata(filename="sample.pdf", page_number=1),
        )
    ]
    chunks = [
        ChunkRecord(
            chunk_id="c1",
            chunk_index=0,
            text="hello",
            markdown="hello",
            element_ids=["e1"],
            source_file="sample.pdf",
            page_start=1,
            page_end=1,
            strategy="static_chars",
            estimated_tokens=2,
            char_count=5,
        )
    ]

    markdown_path = tmp_path / "output.md"
    elements_path = tmp_path / "elements.json"
    chunks_path = tmp_path / "chunks.ndjson"
    preview_path = tmp_path / "chunks_preview.md"

    export_markdown("hello", markdown_path)
    export_elements_json(elements, elements_path)
    export_chunks_ndjson(chunks, chunks_path)
    export_chunk_preview_markdown(chunks, preview_path)

    assert markdown_path.read_text(encoding="utf-8") == "hello"

    elements_payload = json.loads(elements_path.read_text(encoding="utf-8"))
    assert len(elements_payload) == 1
    assert elements_payload[0]["element_id"] == "e1"

    chunk_line = chunks_path.read_text(encoding="utf-8").strip().splitlines()[0]
    assert json.loads(chunk_line)["chunk_id"] == "c1"

    preview_text = preview_path.read_text(encoding="utf-8")
    assert "Chunk 0" in preview_text
    assert "estimated_tokens: 2" in preview_text
