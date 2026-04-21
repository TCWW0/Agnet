from __future__ import annotations

import json
from pathlib import Path

from .models import ChunkRecord, ElementRecord


def export_elements_json(elements: list[ElementRecord], output_path: Path) -> None:
    payload = [element.model_dump(mode="json") for element in elements]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_markdown(markdown: str, output_path: Path) -> None:
    output_path.write_text(markdown, encoding="utf-8")


def export_chunks_ndjson(chunks: list[ChunkRecord], output_path: Path) -> None:
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_chunk_preview_markdown(chunks: list[ChunkRecord], output_path: Path) -> None:
    lines: list[str] = ["# Chunk Preview"]

    for chunk in chunks:
        lines.append("")
        lines.append(f"## Chunk {chunk.chunk_index}")
        lines.append(f"- chunk_id: {chunk.chunk_id}")
        lines.append(f"- pages: {chunk.page_start} -> {chunk.page_end}")
        lines.append(f"- strategy: {chunk.strategy}")
        lines.append(f"- chars: {chunk.char_count}")
        lines.append(f"- estimated_tokens: {chunk.estimated_tokens}")
        lines.append("")
        lines.append(chunk.markdown)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
