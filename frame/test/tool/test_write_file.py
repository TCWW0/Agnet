from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.write_file import WriteFileTool


def test_write_file_overwrite_and_append(tmp_path) -> None:
    tool = WriteFileTool(str(tmp_path))

    r1 = tool.execute({"path": "a.txt", "content": "hello"})
    assert r1.status == "success"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"

    r2 = tool.execute({"path": "a.txt", "content": " world", "append": True})
    assert r2.status == "success"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello world"


def test_write_file_rejects_traversal(tmp_path) -> None:
    tool = WriteFileTool(str(tmp_path))
    r = tool.execute({"path": "../x.txt", "content": "x"})
    assert r.status == "error"
