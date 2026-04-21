from __future__ import annotations

import math
from hashlib import sha1
from typing import Iterable, Optional

from .models import ChunkRecord, ElementRecord

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None


def estimate_tokens(text: str) -> int:
    if not text:
        return 0

    if tiktoken is not None:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            pass

    return max(1, math.ceil(len(text) / 4))


def _element_block(element: ElementRecord) -> str:
    return (element.markdown or element.text).strip()


def _is_heading_element(element: ElementRecord) -> bool:
    block = _element_block(element)
    return block.startswith("#")


def _split_by_title(elements: list[ElementRecord]) -> list[list[ElementRecord]]:
    groups: list[list[ElementRecord]] = []
    current: list[ElementRecord] = []

    for element in elements:
        if _is_heading_element(element) and current:
            groups.append(current)
            current = [element]
            continue
        current.append(element)

    if current:
        groups.append(current)

    return groups


def _static_chunk_elements(
    elements: list[ElementRecord],
    max_chunk_chars: int,
    overlap_chars: int,
) -> list[list[ElementRecord]]:
    chunks: list[list[ElementRecord]] = []
    cursor = 0

    while cursor < len(elements):
        current: list[ElementRecord] = []
        current_chars = 0
        index = cursor

        while index < len(elements):
            block = _element_block(elements[index])
            if not block:
                index += 1
                continue

            additional = len(block) + (2 if current else 0)
            if current and current_chars + additional > max_chunk_chars:
                break

            current.append(elements[index])
            current_chars += additional
            index += 1

        if not current:
            # Single over-limit element fallback.
            current = [elements[cursor]]
            index = cursor + 1

        chunks.append(current)

        if index >= len(elements):
            break

        if overlap_chars <= 0:
            cursor = index
            continue

        previous_cursor = cursor
        back_chars = 0
        overlap_start = index
        probe = index - 1
        while probe >= 0 and back_chars < overlap_chars:
            back_chars += len(_element_block(elements[probe])) + 2
            overlap_start = probe
            probe -= 1

        if overlap_start >= index:
            next_cursor = index
        else:
            next_cursor = overlap_start

        # Ensure forward progress even with very large overlap.
        if next_cursor <= previous_cursor:
            next_cursor = index

        cursor = next_cursor

    return chunks


def _chunk_from_groups(
    groups: Iterable[list[ElementRecord]],
    strategy_name: str,
    max_chunk_chars: int,
    overlap_chars: int,
) -> list[ChunkRecord]:
    chunk_records: list[ChunkRecord] = []

    for group in groups:
        static_groups = _static_chunk_elements(group, max_chunk_chars, overlap_chars)
        for static_group in static_groups:
            markdown_blocks = [_element_block(element) for element in static_group if _element_block(element)]
            markdown_text = "\n\n".join(markdown_blocks).strip()
            if not markdown_text:
                continue

            pages = [
                element.metadata.page_number
                for element in static_group
                if element.metadata.page_number is not None
            ]
            source_file = next(
                (
                    element.metadata.filename
                    for element in static_group
                    if element.metadata.filename
                ),
                None,
            )
            chunk_index = len(chunk_records)
            chunk_id_source = f"{chunk_index}|{strategy_name}|{markdown_text[:200]}".encode(
                "utf-8", errors="ignore"
            )

            chunk_records.append(
                ChunkRecord(
                    chunk_id=sha1(chunk_id_source).hexdigest()[:16],
                    chunk_index=chunk_index,
                    text=markdown_text,
                    markdown=markdown_text,
                    element_ids=[element.element_id for element in static_group],
                    source_file=source_file,
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                    strategy=strategy_name,
                    estimated_tokens=estimate_tokens(markdown_text),
                    char_count=len(markdown_text),
                )
            )

    return chunk_records


def _make_chunk(
    chunk_index: int,
    strategy_name: str,
    markdown_text: str,
    element_ids: list[str],
    source_file: Optional[str],
    page_start: Optional[int],
    page_end: Optional[int],
) -> ChunkRecord:
    chunk_id_source = f"{chunk_index}|{strategy_name}|{markdown_text[:200]}".encode(
        "utf-8", errors="ignore"
    )
    return ChunkRecord(
        chunk_id=sha1(chunk_id_source).hexdigest()[:16],
        chunk_index=chunk_index,
        text=markdown_text,
        markdown=markdown_text,
        element_ids=element_ids,
        source_file=source_file,
        page_start=page_start,
        page_end=page_end,
        strategy=strategy_name,
        estimated_tokens=estimate_tokens(markdown_text),
        char_count=len(markdown_text),
    )


def _is_merge_candidate(markdown_text: str, element_ids: list[str]) -> bool:
    stripped = markdown_text.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    return len(stripped) < 80 and len(element_ids) <= 1


def _merge_small_chunks(chunks: list[ChunkRecord], min_chars: int = 120) -> list[ChunkRecord]:
    if not chunks:
        return chunks

    merged: list[ChunkRecord] = []
    index = 0

    while index < len(chunks):
        current = chunks[index]
        combined_markdown = current.markdown
        combined_element_ids = list(current.element_ids)
        source_file = current.source_file
        page_start = current.page_start
        page_end = current.page_end
        strategy = current.strategy

        # Merge tiny chunks into the next chunk to avoid isolated headings.
        probe = index
        while (
            len(combined_markdown) < min_chars
            and _is_merge_candidate(combined_markdown, combined_element_ids)
            and (probe + 1) < len(chunks)
        ):
            candidate_next = chunks[probe + 1]
            if "\n\n" in combined_markdown and candidate_next.markdown.lstrip().startswith("#"):
                break

            probe += 1
            nxt = candidate_next
            combined_markdown = f"{combined_markdown}\n\n{nxt.markdown}".strip()
            combined_element_ids.extend(nxt.element_ids)

            if source_file is None:
                source_file = nxt.source_file

            if page_start is None:
                page_start = nxt.page_start
            elif nxt.page_start is not None:
                page_start = min(page_start, nxt.page_start)

            if page_end is None:
                page_end = nxt.page_end
            elif nxt.page_end is not None:
                page_end = max(page_end, nxt.page_end)

        merged.append(
            _make_chunk(
                chunk_index=len(merged),
                strategy_name=strategy,
                markdown_text=combined_markdown,
                element_ids=combined_element_ids,
                source_file=source_file,
                page_start=page_start,
                page_end=page_end,
            )
        )
        index = probe + 1

    return merged


def build_chunks(
    elements: list[ElementRecord],
    strategy: str,
    max_chunk_chars: int,
    overlap_chars: int,
) -> list[ChunkRecord]:
    if strategy == "by_title":
        groups = _split_by_title(elements)
        chunks = _chunk_from_groups(groups, strategy, max_chunk_chars, overlap_chars)
        return _merge_small_chunks(chunks)

    if strategy == "static_chars":
        groups = [elements]
        chunks = _chunk_from_groups(groups, strategy, max_chunk_chars, overlap_chars)
        return _merge_small_chunks(chunks)

    raise ValueError(f"Unsupported chunk strategy: {strategy}")
