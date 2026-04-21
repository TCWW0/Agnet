from __future__ import annotations

from collections import defaultdict
import re

from .models import ElementRecord
from .postprocessor import promote_inline_heading

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _is_page_counter_noise(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", text))


def _looks_author_line(text: str) -> bool:
    lowered = text.lower()
    return "," in text and (" and " in lowered or "et al" in lowered)


def _looks_real_heading(text: str) -> bool:
    if not text:
        return False
    if len(text) > 120:
        return False
    if text[0].islower():
        return False
    if text.endswith((".", ":", ";", ",")):
        return False

    words = [word for word in text.split() if any(char.isalpha() for char in word)]
    if not words:
        return False

    if text.isupper():
        return True

    leading_caps = sum(1 for word in words if word[0].isupper())
    if (leading_caps / len(words)) >= 0.5:
        return True

    # Sentence-case section names are common in academic PDFs.
    if words[0][0].isupper() and len(words) <= 10 and not any(mark in text for mark in ".?!"):
        return True

    return False


def _format_title(text: str, heading_index: int) -> str:
    level = 1 if heading_index == 0 else 2
    return f"{'#' * level} {text}"


def _detect_repeated_header_footer_noise(elements: list[ElementRecord]) -> set[str]:
    text_pages: dict[str, set[int]] = defaultdict(set)

    for element in elements:
        page = element.metadata.page_number
        if page is None:
            continue

        normalized_text = _normalize_text(element.text)
        if not normalized_text:
            continue
        if len(normalized_text) > 80:
            continue

        text_pages[normalized_text].add(page)

    repeated_noise: set[str] = set()
    for text, pages in text_pages.items():
        if len(pages) < 3:
            continue

        words = text.split()
        if len(words) <= 10:
            repeated_noise.add(text)

    return repeated_noise


def _to_markdown_block(element: ElementRecord, heading_index: int) -> str:
    normalized_text = _normalize_text(element.text)

    if element.element_type == "PageBreak":
        return "---"

    if not normalized_text:
        return ""

    if _is_page_counter_noise(normalized_text):
        return ""

    if element.element_type in {"Title", "Header"}:
        if heading_index > 0 and _looks_author_line(normalized_text):
            return normalized_text
        if not _looks_real_heading(normalized_text):
            return promote_inline_heading(normalized_text)
        return _format_title(normalized_text, heading_index)

    if element.element_type in {"ListItem"}:
        clean = normalized_text.lstrip("-* ").strip()
        return f"- {clean}"

    if element.element_type in {"Table", "TableChunk"}:
        return f"```table\n{normalized_text}\n```"

    return promote_inline_heading(normalized_text)


def render_markdown(elements: list[ElementRecord]) -> tuple[list[ElementRecord], str]:
    """Convert parsed elements to markdown blocks and full markdown string."""

    rendered_elements: list[ElementRecord] = []
    markdown_blocks: list[str] = []
    repeated_noise = _detect_repeated_header_footer_noise(elements)

    heading_index = 0
    for element in elements:
        if _normalize_text(element.text) in repeated_noise:
            continue

        markdown = _to_markdown_block(element, heading_index)
        if not markdown:
            continue

        if markdown.startswith("#"):
            heading_index += 1

        rendered = element.model_copy(update={"markdown": markdown})
        rendered_elements.append(rendered)
        markdown_blocks.append(markdown)

    markdown_text = "\n\n".join(markdown_blocks).strip() + "\n"
    return rendered_elements, markdown_text
