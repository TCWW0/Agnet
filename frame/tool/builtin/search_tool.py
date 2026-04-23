import os
import json
from typing import Dict, Optional, Any

from frame.tool.base import (
    BaseTool,
    ToolDesc,
    ToolParameters,
    Property,
    ToolResponse,
    ValidationResult,
)


class SearchTool(BaseTool):
    def __init__(self, base_dir: str, max_results_default: int = 100):
        super().__init__(name="search", description="在工作区内进行文本搜索，返回匹配位置")
        self.base_dir = os.path.abspath(base_dir)
        self.max_results_default = max_results_default

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "query": Property(type="string", description="搜索查询字符串"),
                "path": Property(type="string", description="相对于工作区的路径，默认为根"),
                "max_results": Property(type="integer", description="最大返回条数")
            },
            required=["query"],
        )
        return ToolDesc(name="search", description="文本搜索工具", parameters=params)

    def valid_paras(self, params: Dict[str, Any]) -> "ValidationResult":
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            return ValidationResult(valid=False, message="missing 'query'")
        path = params.get("path", ".")
        try:
            max_results = int(params.get("max_results", self.max_results_default))
        except Exception:
            max_results = self.max_results_default
        if max_results <= 0:
            max_results = self.max_results_default
        return ValidationResult(valid=True, parsed_params={"query": query, "path": path, "max_results": max_results})

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        query_raw = params.get("query")
        if not isinstance(query_raw, str):
            return ToolResponse(tool_name=self.name, status="error", output="missing 'query' parameter")
        query = query_raw

        relpath_raw = params.get("path", ".")
        relpath = relpath_raw if isinstance(relpath_raw, str) else "."

        try:
            max_results = int(params.get("max_results", self.max_results_default))
        except Exception:
            max_results = self.max_results_default

        base = os.path.abspath(os.path.join(self.base_dir, relpath))
        # 防止超出 workspace
        if not base.startswith(self.base_dir):
            return ToolResponse(tool_name=self.name, status="error", output="path traversal detected")

        results = []
        for root, _, files in os.walk(base):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for ln, line in enumerate(f, start=1):
                            if query in line:
                                results.append({"path": os.path.relpath(fpath, self.base_dir), "line": ln, "snippet": line.strip()})
                                if len(results) >= max_results:
                                    break
                except Exception:
                    # 忽略无法读取的文件
                    continue
            if len(results) >= max_results:
                break

        return ToolResponse(tool_name=self.name, status="success", output=json.dumps(results, ensure_ascii=False), details={"count": len(results)})

