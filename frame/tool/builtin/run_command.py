import shlex
import subprocess
from typing import Dict, Any, Optional, Set

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


DEFAULT_ALLOWLIST = ("python", "python3", "pytest", "g++", "make", "git")


class RunCommandTool(BaseTool):
    def __init__(self, workspace_root: str, allowlist: Optional[Set[str]] = None):
        super().__init__(name="run_command", description="执行受限 shell 命令（受白名单约束）")
        self.workspace_root = workspace_root
        self.allowlist = allowlist or set(DEFAULT_ALLOWLIST)

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "command": Property(
                    type="string",
                    description="命令主程序名（推荐），例如 python/pytest/make/git",
                    enum=list(DEFAULT_ALLOWLIST),
                ),
                "args": Property(
                    type="string",
                    description="参数字符串（推荐），会以 shlex 规则拆分，例如 '-m pytest -q frame/test'",
                ),
                "timeout_sec": Property(type="integer", description="超时时间，秒"),
            },
            required=["command"],
        )
        return ToolDesc(name="run_command", description="执行受限命令", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> "ValidationResult":
        command = params.get("command")
        args = params.get("args", "")

        if not isinstance(command, str) or not command.strip():
            return ValidationResult(valid=False, message="missing 'command'")
        if not isinstance(args, str):
            return ValidationResult(valid=False, message="'args' must be string")

        base = command.strip()

        if base not in self.allowlist:
            return ValidationResult(valid=False, message=f"command not allowed: {base}")

        parts = [base, *shlex.split(args)]

        if base in {"python", "python3"} and len(parts) == 1:
            return ValidationResult(
                valid=False,
                message="interactive python is not allowed; provide args such as '-m pytest ...' or '<script>.py'",
            )

        try:
            timeout = int(params.get("timeout_sec", 30))
        except Exception:
            timeout = 30
        timeout = min(max(timeout, 1), 120)

        command_line = " ".join(shlex.quote(p) for p in parts)
        parsed = {
            "cmd_parts": parts,
            "timeout": timeout,
            "command_base": base,
            "command_line": command_line,
        }
        return ValidationResult(valid=True, parsed_params=parsed)

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        parts_raw = params.get("cmd_parts")
        if not isinstance(parts_raw, (list, tuple)) or not parts_raw:
            return ToolResponse(tool_name=self.name, status="error", output="invalid cmd_parts")
        parts = [str(p) for p in parts_raw]
        timeout = int(params.get("timeout", 30))
        command_base = str(params.get("command_base", ""))
        command_line = str(params.get("command_line", " ".join(parts)))
        try:
            proc = subprocess.run(parts, capture_output=True, text=True, timeout=timeout, cwd=self.workspace_root)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            details = {"exit_code": proc.returncode, "command": command_line, "command_base": command_base}
            if proc.returncode == 0:
                return ToolResponse(tool_name=self.name, status="success", output=stdout.strip(), details={**details, "stderr": stderr})
            else:
                return ToolResponse(tool_name=self.name, status="error", output=stderr.strip() or stdout.strip(), details=details)
        except subprocess.TimeoutExpired:
            return ToolResponse(
                tool_name=self.name,
                status="error",
                output="timeout",
                details={"error_type": "timeout", "command": command_line, "command_base": command_base},
            )
        except Exception as e:
            return ToolResponse(
                tool_name=self.name,
                status="error",
                output=str(e),
                details={"error_type": "tool_invocation_error", "command": command_line, "command_base": command_base},
            )

