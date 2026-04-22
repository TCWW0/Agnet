from __future__ import annotations

from pathlib import Path

from src.schemas import ChatMessage
from src.skill_rag.engine import SkillRagChatEngine


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_skill_rag_engine_uses_summary_and_chunks(tmp_path: Path) -> None:
    kb_root = tmp_path / "Knowledge-Base"
    chunks_root = tmp_path / "Knowledge-Base-Chunks"
    summary_root = tmp_path / "Knowledge-Base-File-Summary"

    _write(
        kb_root / "Product-Line-A-Smartwatch-Series" / "SW-1500-Sport.md",
        "SW-1500 is athlete-focused, rugged, and designed for outdoor training.",
    )
    _write(
        chunks_root / "Product-Line-A-Smartwatch-Series" / "SW-1500-Sport" / "1-40.md",
        "athlete focused rugged training watch with long battery",
    )
    _write(
        summary_root / "summary_demo.json",
        '{"Product-Line-A-Smartwatch-Series/SW-1500-Sport.md": "Athlete-focused, rugged, 36h battery"}',
    )

    engine = SkillRagChatEngine(
        knowledge_base_root=kb_root,
        knowledge_chunks_root=chunks_root,
        knowledge_summary_root=summary_root,
        top_k=2,
        max_skill_calls=2,
    )

    answer = engine.generate([ChatMessage(role="user", content="SW-1500 的核心定位是什么？")])

    assert "Evidence summary" in answer
    assert "SW-1500" in answer

    traces = engine.get_last_trace()
    assert traces
    assert traces[0]["skill_id"] in {"map_skill", "vector_retrieve_skill"}


def test_skill_rag_engine_path_retrieval(tmp_path: Path) -> None:
    kb_root = tmp_path / "Knowledge-Base"
    chunks_root = tmp_path / "Knowledge-Base-Chunks"
    summary_root = tmp_path / "Knowledge-Base-File-Summary"

    _write(
        kb_root / "Product-Line-A-Smartwatch-Series" / "SW-1500-Sport.md",
        "Line 1: rugged sports watch\nLine 2: battery 36h\nLine 3: IP68",
    )
    _write(
        chunks_root / "placeholder" / "1-10.md",
        "fallback chunk",
    )
    _write(
        summary_root / "summary_demo.json",
        '{"Product-Line-A-Smartwatch-Series/SW-1500-Sport.md": "Sports positioning"}',
    )

    engine = SkillRagChatEngine(
        knowledge_base_root=kb_root,
        knowledge_chunks_root=chunks_root,
        knowledge_summary_root=summary_root,
        top_k=2,
        max_skill_calls=3,
    )

    query = "请读取 Product-Line-A-Smartwatch-Series/SW-1500-Sport.md 并总结重点"
    answer = engine.generate([ChatMessage(role="user", content=query)])

    assert "Knowledge-Base/Product-Line-A-Smartwatch-Series/SW-1500-Sport.md" in answer
    traces = engine.get_last_trace()
    assert traces
    assert traces[0]["skill_id"] == "path_retrieve_skill"
