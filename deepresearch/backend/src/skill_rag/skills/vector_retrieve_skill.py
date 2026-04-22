from __future__ import annotations

from pathlib import Path

from ..base import BaseSkill
from ..models import SkillCallInput, SkillEvidence, SkillResult
from ..utils import iter_text_files, lexical_score, safe_read_text, tokenize


class VectorRetrieveSkill(BaseSkill):
    """A lightweight lexical retriever over pre-chunked files.

    This is intentionally deterministic for early-phase rollout and tests.
    """

    skill_id = "vector_retrieve_skill"
    intent = "Retrieve semantically related chunks from chunked knowledge corpus"

    def __init__(self, chunks_root: Path, default_top_k: int = 4) -> None:
        self._chunks_root = chunks_root
        self._default_top_k = default_top_k
        self._chunk_index = self._build_chunk_index()

    def run(self, inp: SkillCallInput) -> SkillResult:
        query_tokens = tokenize(inp.query)
        if not query_tokens or not self._chunk_index:
            return SkillResult(
                skill_id=self.skill_id,
                summary="No chunk index available for vector retrieval.",
                evidence=[],
                meta={"chunkCount": len(self._chunk_index)},
            )

        top_k = int(inp.options.get("top_k", self._default_top_k))
        scored: list[tuple[float, Path, str]] = []

        for chunk_file in self._chunk_index:
            content = safe_read_text(chunk_file, max_chars=2600)
            if not content:
                continue
            score = lexical_score(query_tokens, tokenize(content[:1200]))
            if score <= 0:
                continue
            scored.append((score, chunk_file, content))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:top_k]

        evidence: list[SkillEvidence] = []
        for score, chunk_file, content in selected:
            rel = str(chunk_file.relative_to(self._chunks_root)).replace("\\", "/")
            evidence.append(
                SkillEvidence(
                    source_path=f"Knowledge-Base-Chunks/{rel}",
                    snippet=content[:600].strip(),
                    score=score,
                )
            )

        return SkillResult(
            skill_id=self.skill_id,
            summary=f"Vector retrieve selected {len(evidence)} chunk candidates.",
            evidence=evidence,
            meta={"chunkCount": len(self._chunk_index)},
        )

    def _build_chunk_index(self) -> list[Path]:
        return [path for path in iter_text_files(self._chunks_root, max_files=5000) if path.suffix.lower() == ".md"]
