from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from frame.tool.base import BaseTool, Property, ToolDesc, ToolParameters, ToolResponse, ValidationResult


class ListDirTool(BaseTool):
    def __init__(self, base_dir: str, max_entries: int = 200):
        super().__init__(name="list_dir", description="列出工作区内目录内容")
        self.base_dir = os.path.abspath(base_dir)
        self.max_entries = max(1, int(max_entries))

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "path": Property(type="string", description="相对于工作区根目录的目录路径，默认为根目录"),
                "max_entries": Property(type="integer", description="最大返回条目数"),
            },
            required=[],
        )
        return ToolDesc(name="list_dir", description="List files and folders under workspace", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        path_raw = params.get("path", ".")
        path = path_raw if isinstance(path_raw, str) else "."
        try:
            max_entries = int(params.get("max_entries", self.max_entries))
        except Exception:
            max_entries = self.max_entries
        if max_entries <= 0:
            max_entries = self.max_entries
        return ValidationResult(valid=True, parsed_params={"path": path, "max_entries": max_entries})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        rel_path_raw = params.get("path", ".")
        rel_path = rel_path_raw if isinstance(rel_path_raw, str) else "."
        max_entries = int(params.get("max_entries", self.max_entries))

        abs_path = os.path.abspath(os.path.join(self.base_dir, rel_path))
        if not abs_path.startswith(self.base_dir):
            return ToolResponse(tool_name=self.name, status="error", output="path traversal detected")
        if not os.path.isdir(abs_path):
            return ToolResponse(tool_name=self.name, status="error", output=f"directory not found: {rel_path}")

        entries: List[Dict[str, Any]] = []
        try:
            for name in sorted(os.listdir(abs_path)):
                item_path = os.path.join(abs_path, name)
                entries.append(
                    {
                        "name": name,
                        "type": "dir" if os.path.isdir(item_path) else "file",
                    }
                )
                if len(entries) >= max_entries:
                    break
        except Exception as exc:
            return ToolResponse(tool_name=self.name, status="error", output=str(exc))

        return ToolResponse(
            tool_name=self.name,
            status="success",
            output=json.dumps(entries, ensure_ascii=False),
            details={"count": len(entries), "path": os.path.relpath(abs_path, self.base_dir)},
        )
