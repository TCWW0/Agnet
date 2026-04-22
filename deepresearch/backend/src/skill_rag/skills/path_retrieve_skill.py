from __future__ import annotations

from pathlib import Path

from ..base import BaseSkill
from ..models import SkillCallInput, SkillEvidence, SkillResult
from ..utils import guess_query_paths, iter_text_files, lexical_score, path_within_root, safe_read_text, tokenize


class PathRetrieveSkill(BaseSkill):
    skill_id = "path_retrieve_skill"
    intent = "Read exact files from knowledge base using explicit or inferred paths"

    def __init__(self, knowledge_base_root: Path) -> None:
        self._kb_root = knowledge_base_root
        self._file_index = self._build_file_index()

    def run(self, inp: SkillCallInput) -> SkillResult:
        explicit_paths = guess_query_paths(inp.query)
        selected_files: list[Path] = []

        for raw_path in explicit_paths:
            candidate = self._resolve_query_path(raw_path)
            if candidate is not None and candidate.is_file():
                selected_files.append(candidate)

        if not selected_files:
            selected_files = self._search_files_by_name(inp.query, top_k=2)

        evidence: list[SkillEvidence] = []
        for path in selected_files:
            snippet = safe_read_text(path, max_chars=1400).strip()
            if not snippet:
                continue
            relative_path = str(path.relative_to(self._kb_root)).replace("\\", "/")
            score = lexical_score(tokenize(inp.query), tokenize(relative_path + " " + snippet[:240]))
            evidence.append(
                SkillEvidence(
                    source_path=f"Knowledge-Base/{relative_path}",
                    snippet=snippet,
                    score=score,
                )
            )

        return SkillResult(
            skill_id=self.skill_id,
            summary=f"Path retrieve returned {len(evidence)} file candidates.",
            evidence=evidence,
            meta={"indexCount": len(self._file_index)},
        )

    def _resolve_query_path(self, raw_path: str) -> Path | None:
        normalized = raw_path.replace("\\", "/").strip("/")
        if normalized.lower().startswith("knowledge-base/"):
            normalized = normalized[len("knowledge-base/") :]

        if not normalized:
            return None

        candidate = (self._kb_root / normalized).resolve()
        if not candidate.exists() or not path_within_root(candidate, self._kb_root):
            return None
        return candidate

    def _search_files_by_name(self, query: str, top_k: int) -> list[Path]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, Path]] = []
        for path in self._file_index:
            relative = str(path.relative_to(self._kb_root)).replace("\\", "/")
            score = lexical_score(query_tokens, tokenize(relative))
            if score <= 0:
                continue
            scored.append((score, path))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def _build_file_index(self) -> list[Path]:
        return [path for path in iter_text_files(self._kb_root, max_files=3000) if path.suffix.lower() == ".md"]
