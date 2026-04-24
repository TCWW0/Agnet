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
            combined = (stdout + "\n" + stderr).strip()
            details: Dict[str, Any] = {"exit_code": proc.returncode}
            if proc.returncode != 0:
                lowered = combined.lower()
                if "file or directory not found" in lowered:
                    details.update(
                        {
                            "error_type": "tests_not_found",
                            "action_hint": "Create or point to an existing pytest file before retrying run_tests.",
                        }
                    )
                elif "no tests ran" in lowered or "collected 0 items" in lowered:
                    details.update(
                        {
                            "error_type": "no_tests_collected",
                            "action_hint": "Add at least one test_*.py test case and rerun run_tests.",
                        }
                    )
            status = "success" if proc.returncode == 0 else "error"
            return ToolResponse(tool_name=self.name, status=status, output=stdout + "\n" + stderr, details=details)
        except Exception as e:
            err_text = str(e)
            details: Dict[str, Any] = {"error_type": "tool_invocation_error"}
            if isinstance(e, FileNotFoundError):
                details["error_type"] = "pytest_not_installed"
                details["action_hint"] = "Ensure pytest is installed or set run_tests pytest_cmd to a valid executable."
            return ToolResponse(tool_name=self.name, status="error", output=err_text, details=details)

