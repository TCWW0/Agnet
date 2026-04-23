import subprocess
from typing import Dict, Any

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


class GitDiffTool(BaseTool):
    def __init__(self, workspace_root: str, max_output: int = 200_000):
        super().__init__(name="git_diff", description="获取当前工作区与最近提交的 diff")
        self.workspace_root = workspace_root
        self.max_output = int(max_output)

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(properties={}, required=[])
        return ToolDesc(name="git_diff", description="git diff (read-only)", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        # no params needed
        return ValidationResult(valid=True)

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        try:
            proc = subprocess.run(["git", "diff", "--no-color"], capture_output=True, text=True, cwd=self.workspace_root, timeout=10)
            out = proc.stdout or ""
            if len(out) > self.max_output:
                out = out[: self.max_output] + "\n...[truncated]"
            return ToolResponse(tool_name=self.name, status="success", output=out, details={"exit_code": proc.returncode})
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

