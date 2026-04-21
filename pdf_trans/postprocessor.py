from __future__ import annotations

import re

_INLINE_HEADING_SPLIT_PATTERN = re.compile(
    r"^(?P<head>[A-Z][^.!?]{1,90}?)\s+(?P<body>(?:[A-Z][A-Za-z]|[0-9]{1,2}\.|[A-Z]{2,}).*)$"
)
_SINGLE_WORD_HEADINGS = {
    "abstract",
    "acknowledgements",
    "acknowledgments",
    "appendix",
    "conclusion",
    "conclusions",
    "discussion",
    "introduction",
    "references",
    "results",
    "summary",
}


def _word_count(text: str) -> int:
    return len([part for part in text.split() if part])


def _looks_inline_heading_candidate(head: str, body: str) -> bool:
    heading_words = _word_count(head)
    if heading_words == 0 or heading_words > 10:
        return False

    if len(body) < 12:
        return False

    if heading_words == 1 and head.lower() not in _SINGLE_WORD_HEADINGS:
        return False

    if head.endswith((":", ";", ",")):
        return False

    return True


def promote_inline_heading(markdown_text: str, default_level: int = 2) -> str:
    """Promote inlined section headings like `References 1. ...` to markdown headings."""

    stripped = markdown_text.strip()
    if not stripped:
        return markdown_text

    if stripped.startswith(("#", "- ", "```", ">")):
        return markdown_text

    match = _INLINE_HEADING_SPLIT_PATTERN.match(stripped)
    if not match:
        return markdown_text

    heading = match.group("head").strip()
    body = match.group("body").strip()
    if not _looks_inline_heading_candidate(heading, body):
        return markdown_text

    level = max(1, min(default_level, 6))
    return f"{'#' * level} {heading}\n\n{body}"