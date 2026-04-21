from __future__ import annotations

from pdf_trans.chunker import build_chunks
from pdf_trans.models import ElementMetadata, ElementRecord


def _element(index: int, element_type: str, markdown: str, page: int = 1) -> ElementRecord:
    return ElementRecord(
        element_id=f"e{index}",
        element_type=element_type,
        text=markdown,
        markdown=markdown,
        metadata=ElementMetadata(filename="sample.pdf", page_number=page),
    )


def test_by_title_chunking_creates_multiple_chunks() -> None:
    elements = [
        _element(1, "Title", "# Intro", 1),
        _element(2, "NarrativeText", "A" * 90, 1),
        _element(3, "Title", "## Method", 2),
        _element(4, "NarrativeText", "B" * 90, 2),
    ]

    chunks = build_chunks(elements, strategy="by_title", max_chunk_chars=80, overlap_chars=20)

    assert len(chunks) >= 2
    assert chunks[0].strategy == "by_title"
    assert chunks[0].page_start is not None
    assert chunks[0].page_end is not None


def test_by_title_chunking_uses_markdown_heading_markers() -> None:
    elements = [
        _element(1, "NarrativeText", "# Intro", 1),
        _element(2, "NarrativeText", "A" * 90, 1),
        _element(3, "NarrativeText", "## References\n\n1. ref", 2),
        _element(4, "NarrativeText", "B" * 90, 2),
    ]

    chunks = build_chunks(elements, strategy="by_title", max_chunk_chars=120, overlap_chars=20)

    assert len(chunks) >= 2
    assert any("## References" in chunk.markdown for chunk in chunks)


def test_static_chunking_progress_with_large_overlap() -> None:
    elements = [
        _element(1, "NarrativeText", "alpha " * 20),
        _element(2, "NarrativeText", "beta " * 20),
        _element(3, "NarrativeText", "gamma " * 20),
    ]

    chunks = build_chunks(elements, strategy="static_chars", max_chunk_chars=80, overlap_chars=70)

    assert 1 <= len(chunks) <= 12
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.char_count > 0 for chunk in chunks)
