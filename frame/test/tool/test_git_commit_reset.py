import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.git_commit import GitCommitTool
from frame.tool.builtin.git_reset import GitResetTool


def _init_repo(ws: Path):
    ws.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.email", "you@example.com"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=ws, check=True)


def test_git_commit_and_reset_via_tool(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    # initial commit A
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "A"], cwd=repo, check=True)
    commit_a = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo).stdout.strip()

    # change and commit B using tool
    (repo / "f.txt").write_text("v2\n")
    tool = GitCommitTool(str(repo))
    res = tool.execute({"message": "B via tool"})
    assert res.status == "success", res.output
    commit_b = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo).stdout.strip()
    assert commit_a != commit_b

    # reset to commit_a via tool
    reset_tool = GitResetTool(str(repo))
    r = reset_tool.execute({"target": commit_a})
    assert r.status == "success", r.output
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo).stdout.strip()
    assert head == commit_a
