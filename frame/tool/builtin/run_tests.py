import subprocess
from typing import Dict, Any

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult


class RunTestsTool(BaseTool):
    def __init__(self, workspace_root: str, pytest_cmd: str = "pytest -q"):
        super().__init__(name="run_tests", description="运行项目测试套件（pytest）")
        self.workspace_root = workspace_root
        self.pytest_cmd = pytest_cmd

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(properties={"pattern": Property(type="string", description="pytest pattern or args")}, required=[])
        return ToolDesc(name="run_tests", description="Run test suite (pytest)", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> "ValidationResult":
        # 参数可选，接受 pattern
        return ValidationResult(valid=True, parsed_params={"pattern": params.get("pattern", "")})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        pattern = params.get("pattern", "")
        cmd = self.pytest_cmd.split()
        if pattern:
            cmd += [pattern]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.workspace_root)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            details = {"exit_code": proc.returncode}
            status = "success" if proc.returncode == 0 else "error"
            return ToolResponse(tool_name=self.name, status=status, output=stdout + "\n" + stderr, details=details)
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

