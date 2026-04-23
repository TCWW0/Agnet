from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.list_dir import ListDirTool


def test_list_dir_returns_entries(tmp_path) -> None:
    workspace = tmp_path
    (workspace / "alpha.txt").write_text("a\n")
    (workspace / "nested").mkdir()
    tool = ListDirTool(str(workspace))

    result = tool.execute({"path": "."})

    assert result.status == "success"
    assert "alpha.txt" in result.output
    assert "nested" in result.output
    assert (result.details or {}).get("count") == 2


def test_list_dir_rejects_traversal(tmp_path) -> None:
    tool = ListDirTool(str(tmp_path))

    result = tool.execute({"path": "../"})

    assert result.status == "error"
