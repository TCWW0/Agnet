import shlex
import subprocess
from typing import Dict, Any, Optional

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


class RunCommandTool(BaseTool):
    def __init__(self, workspace_root: str, allowlist: Optional[set] = None):
        super().__init__(name="run_command", description="执行受限 shell 命令（受白名单约束）")
        self.workspace_root = workspace_root
        self.allowlist = allowlist or {"python", "pytest", "g++", "make", "git"}

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "cmd": Property(
                    type="string",
                    description="命令字符串（将被拆分）",
                    enum=["python", "pytest", "g++", "make", "git"]  # 仅允许这些命令，参数不限制
                ),
                "timeout_sec": Property(type="integer", description="超时时间，秒"),
            },
            required=["cmd"],
        )
        return ToolDesc(name="run_command", description="执行受限命令", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> "ValidationResult":
        cmd = params.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            return ValidationResult(valid=False, message="missing 'cmd'")
        parts = shlex.split(cmd)
        if not parts:
            return ValidationResult(valid=False, message="empty command")
        base = parts[0]
        if base not in self.allowlist:
            return ValidationResult(valid=False, message=f"command not allowed: {base}")
        try:
            timeout = int(params.get("timeout_sec", 30))
        except Exception:
            timeout = 30
        return ValidationResult(valid=True, parsed_params={"cmd_parts": parts, "timeout": timeout})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        parts_raw = params.get("cmd_parts")
        if not isinstance(parts_raw, (list, tuple)) or not parts_raw:
            return ToolResponse(tool_name=self.name, status="error", output="invalid cmd_parts")
        parts = [str(p) for p in parts_raw]
        timeout = int(params.get("timeout", 30))
        try:
            proc = subprocess.run(parts, capture_output=True, text=True, timeout=timeout, cwd=self.workspace_root)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            details = {"exit_code": proc.returncode}
            if proc.returncode == 0:
                return ToolResponse(tool_name=self.name, status="success", output=stdout.strip(), details={**details, "stderr": stderr})
            else:
                return ToolResponse(tool_name=self.name, status="error", output=stderr.strip() or stdout.strip(), details=details)
        except subprocess.TimeoutExpired:
            return ToolResponse(tool_name=self.name, status="error", output="timeout")
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

