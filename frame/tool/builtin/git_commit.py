import subprocess
from typing import Dict, Any

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


class GitCommitTool(BaseTool):
    def __init__(self, workspace_root: str):
        super().__init__(name="git_commit", description="将当前工作区变更做本地提交 (不 push)")
        self.workspace_root = workspace_root

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={"message": Property(type="string", description="commit message")},
            required=["message"],
        )
        return ToolDesc(name="git_commit", description="git commit (local)", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        msg = params.get("message")
        if not isinstance(msg, str) or not msg.strip():
            return ValidationResult(valid=False, message="non-empty commit message required")
        return ValidationResult(valid=True, parsed_params={"message": msg.strip()})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        message_raw = params.get("message")
        if not isinstance(message_raw, str) or not message_raw.strip():
            return ToolResponse(tool_name=self.name, status="error", output="invalid commit message")
        message = message_raw.strip()
        try:
            # stage all changes
            add = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=self.workspace_root, timeout=10)
            if add.returncode != 0:
                return ToolResponse(tool_name=self.name, status="error", output=add.stderr or add.stdout)

            commit = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True, cwd=self.workspace_root, timeout=15)
            if commit.returncode != 0:
                # handle nothing to commit case
                out = commit.stdout or commit.stderr or "commit failed"
                return ToolResponse(tool_name=self.name, status="error", output=out)

            rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=self.workspace_root, timeout=5)
            commit_id = (rev.stdout or "").strip()
            return ToolResponse(tool_name=self.name, status="success", output=f"committed {commit_id}", details={"commit_id": commit_id})
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

