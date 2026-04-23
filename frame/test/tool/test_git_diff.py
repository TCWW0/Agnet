import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.git_diff import GitDiffTool


def _init_repo(ws: Path):
    ws.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.email", "you@example.com"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=ws, check=True)
    (ws / "init.txt").write_text("init\n")
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=ws, check=True)


def test_git_diff_nonempty(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    # modify file
    (repo / "init.txt").write_text("modified\n")
    tool = GitDiffTool(str(repo))
    res = tool.execute({})
    assert res.status == "success"
    assert "modified" in res.output


def test_git_diff_clean(tmp_path):
    repo = tmp_path / "repo2"
    _init_repo(repo)
    tool = GitDiffTool(str(repo))
    res = tool.execute({})
    assert res.status == "success"
    # clean repo should produce empty output
    assert res.output.strip() == ""
