import subprocess
from typing import Dict, Any

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


class GitResetTool(BaseTool):
    def __init__(self, workspace_root: str):
        super().__init__(name="git_reset", description="回滚到指定提交或撤销当前修改")
        self.workspace_root = workspace_root

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(properties={"target": Property(type="string", description="commit id or HEAD")}, required=["target"])
        return ToolDesc(name="git_reset", description="git reset --hard <target>", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        target = params.get("target")
        if not isinstance(target, str) or not target.strip():
            return ValidationResult(valid=False, message="target is required")
        return ValidationResult(valid=True, parsed_params={"target": target.strip()})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        target_raw = params.get("target")
        if not isinstance(target_raw, str) or not target_raw.strip():
            return ToolResponse(tool_name=self.name, status="error", output="invalid target")
        target = target_raw.strip()
        try:
            proc = subprocess.run(["git", "reset", "--hard", target], capture_output=True, text=True, cwd=self.workspace_root, timeout=20)
            if proc.returncode != 0:
                return ToolResponse(tool_name=self.name, status="error", output=proc.stderr or proc.stdout)
            return ToolResponse(tool_name=self.name, status="success", output=f"reset to {target}")
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

