from __future__ import annotations

import re
from pathlib import Path


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:md|txt|json)", re.IGNORECASE)


def tokenize(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.lower())


def lexical_score(query_tokens: list[str], target_tokens: list[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0

    query_set = set(query_tokens)
    target_set = set(target_tokens)
    overlap = query_set.intersection(target_set)
    if not overlap:
        return 0.0

    return len(overlap) / max(len(query_set), 1)


def iter_text_files(root: Path, max_files: int = 2000) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []

    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        result.append(path)
        if len(result) >= max_files:
            break
    return result


def safe_read_text(path: Path, max_chars: int = 6000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def guess_query_paths(query: str) -> list[str]:
    return [match.group(0).replace("\\", "/") for match in _PATH_PATTERN.finditer(query)]
