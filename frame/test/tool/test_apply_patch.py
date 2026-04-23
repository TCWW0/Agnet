import os
import sys
from pathlib import Path

# ensure repository root is on sys.path when tests run from inside frame/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.apply_patch import ApplyPatchTool


def test_apply_patch_success(tmp_path):
    workspace = tmp_path
    f = workspace / "foo.txt"
    f.write_text("line1\nline2\n")
    tool = ApplyPatchTool(str(workspace))
    patch = (
        "--- a/foo.txt\n"
        "+++ b/foo.txt\n"
        "@@ -1,2 +1,2 @@\n"
        " line1\n"
        "-line2\n"
        "+line-two\n"
    )
    res = tool.execute({"patch": patch})
    assert res.status == "success", res.output
    assert "foo.txt" in (res.details or {}).get("applied_files", [])
    assert (workspace / "foo.txt").read_text() == "line1\nline-two\n"


def test_apply_patch_invalid_path(tmp_path):
    workspace = tmp_path
    f = workspace / "foo.txt"
    f.write_text("line1\n")
    tool = ApplyPatchTool(str(workspace))
    patch = (
        "--- a/../../etc/passwd\n"
        "+++ b/../../etc/passwd\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    res = tool.execute({"patch": patch})
    assert res.status == "error"
