from __future__ import annotations

import os
from typing import Any, Dict

from frame.tool.base import BaseTool, Property, ToolDesc, ToolParameters, ToolResponse, ValidationResult


class WriteFileTool(BaseTool):
    def __init__(self, base_dir: str, max_bytes: int = 1_000_000):
        super().__init__(name="write_file", description="在工作区内写入文本文件（UTF-8）")
        self.base_dir = os.path.abspath(base_dir)
        self.max_bytes = int(max_bytes)

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "path": Property(type="string", description="相对于工作区根目录的文件路径"),
                "content": Property(type="string", description="要写入的文本内容（UTF-8）"),
                "append": Property(type="boolean", description="是否以追加模式写入，默认 false"),
            },
            required=["path", "content"],
        )
        return ToolDesc(name="write_file", description="Write text file under workspace", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        rel_path = params.get("path")
        content = params.get("content")
        append = bool(params.get("append", False))

        if not isinstance(rel_path, str) or not rel_path.strip():
            return ValidationResult(valid=False, message="missing 'path'")
        if not isinstance(content, str):
            return ValidationResult(valid=False, message="missing 'content'")

        if len(content.encode("utf-8")) > self.max_bytes:
            return ValidationResult(valid=False, message="content too large")

        norm = os.path.normpath(rel_path)
        if norm.startswith("..") or os.path.isabs(norm):
            return ValidationResult(valid=False, message="path traversal not allowed")

        abs_path = os.path.abspath(os.path.join(self.base_dir, norm))
        if not abs_path.startswith(self.base_dir):
            return ValidationResult(valid=False, message="path outside workspace")

        return ValidationResult(
            valid=True,
            parsed_params={"abs_path": abs_path, "content": content, "append": append},
        )

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        abs_path = params.get("abs_path")
        content = params.get("content")
        append = bool(params.get("append", False))

        if not isinstance(abs_path, str) or not isinstance(content, str):
            return ToolResponse(tool_name=self.name, status="error", output="invalid params")

        try:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            mode = "a" if append else "w"
            with open(abs_path, mode, encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:
            return ToolResponse(tool_name=self.name, status="error", output=str(exc))

        rel = os.path.relpath(abs_path, self.base_dir)
        return ToolResponse(
            tool_name=self.name,
            status="success",
            output=f"wrote file: {rel}",
            details={"path": rel, "bytes": len(content.encode('utf-8')), "append": append},
        )
