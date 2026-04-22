from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..base import BaseSkill
from ..models import SkillCallInput, SkillEvidence, SkillResult
from ..utils import guess_query_paths, iter_text_files, lexical_score, safe_read_text, tokenize


@dataclass(frozen=True)
class _SummaryEntry:
    source_path: str
    summary: str


class MapSkill(BaseSkill):
    skill_id = "map_skill"
    intent = "Navigate summary map and find candidate source files"

    def __init__(self, summary_root: Path, default_top_k: int = 5) -> None:
        self._summary_root = summary_root
        self._default_top_k = default_top_k
        self._entries = self._build_entries()

    def run(self, inp: SkillCallInput) -> SkillResult:
        query_tokens = tokenize(inp.query)
        if not query_tokens or not self._entries:
            return SkillResult(
                skill_id=self.skill_id,
                summary="No summary entries available for map navigation.",
                evidence=[],
                meta={"candidateCount": len(self._entries)},
            )

        scored: list[tuple[float, _SummaryEntry]] = []
        for entry in self._entries:
            score = lexical_score(query_tokens, tokenize(entry.source_path + " " + entry.summary))
            if score <= 0:
                continue
            scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_k = int(inp.options.get("top_k", self._default_top_k))
        selected = scored[:top_k]

        evidence = [
            SkillEvidence(source_path=item.source_path, snippet=item.summary, score=score)
            for score, item in selected
        ]

        return SkillResult(
            skill_id=self.skill_id,
            summary=f"Map skill selected {len(evidence)} candidate summaries.",
            evidence=evidence,
            meta={"candidateCount": len(self._entries)},
        )

    def _build_entries(self) -> list[_SummaryEntry]:
        entries: list[_SummaryEntry] = []

        for file_path in iter_text_files(self._summary_root, max_files=200):
            text = safe_read_text(file_path, max_chars=200_000)
            if not text.strip():
                continue

            if file_path.suffix.lower() == ".json":
                entries.extend(self._extract_from_json(text))
            else:
                entries.extend(self._extract_from_text(text))

        dedup: dict[str, _SummaryEntry] = {}
        for entry in entries:
            key = f"{entry.source_path}::{entry.summary}"
            dedup[key] = entry

        return list(dedup.values())

    def _extract_from_json(self, text: str) -> list[_SummaryEntry]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, dict):
            return []

        entries: list[_SummaryEntry] = []
        for source_path, value in payload.items():
            if not isinstance(source_path, str):
                continue

            if isinstance(value, str):
                summary = value.strip()
                if summary:
                    entries.append(_SummaryEntry(source_path=source_path, summary=summary))
                continue

            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    summary = str(item.get("summary", "")).strip()
                    if not summary:
                        continue
                    start = item.get("start")
                    end = item.get("end")
                    if isinstance(start, int) and isinstance(end, int):
                        line_hint = f"lines {start}-{end}"
                        entries.append(_SummaryEntry(source_path=source_path, summary=f"{summary} ({line_hint})"))
                    else:
                        entries.append(_SummaryEntry(source_path=source_path, summary=summary))
                continue

            if isinstance(value, dict):
                summary = str(value.get("summary", "")).strip()
                if summary:
                    entries.append(_SummaryEntry(source_path=source_path, summary=summary))

        return entries

    def _extract_from_text(self, text: str) -> list[_SummaryEntry]:
        entries: list[_SummaryEntry] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if "：" in line:
                left, right = line.split("：", 1)
            elif ":" in line and ".md" in line:
                left, right = line.split(":", 1)
            else:
                continue

            candidates = guess_query_paths(left)
            if not candidates:
                candidates = guess_query_paths(line)
            if not candidates:
                continue

            summary = right.strip()
            if not summary:
                continue

            entries.append(_SummaryEntry(source_path=candidates[0], summary=summary))

        return entries
