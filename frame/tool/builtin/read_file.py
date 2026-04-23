"""实现一个安全的读取文件的工具，限制只能读取特定目录下的文件，并且在读取前进行路径验证，防止路径遍历攻击。"""

import os

from frame.tool.base import BaseTool, ToolDesc, ToolParameters, Property, ToolResponse, ValidationResult
from frame.core.logger import Logger,global_logger
from typing import Dict, Optional

class ReadFileTool(BaseTool):
    def __init__(self, base_dir: str,max_lines: int = 400,logger: Optional[Logger] = None):
        super().__init__(
            name="read_file",
            description=f"一个安全的读取文件的工具，限制只能读取特定目录下的文件，并且在读取前进行路径验证，防止路径遍历攻击。只能读取{base_dir}目录下的文件。",
        )
        self.base_dir = base_dir
        self.logger = logger or global_logger
        self.max_lines = max_lines

    @classmethod
    def desc(cls) -> ToolDesc:
        file_path = Property(
            type="string",
            description="要读取的文件相对路径，相对于工具的base_dir，将会以base_dir作为根目录进行路径验证",
        )

        params = ToolParameters(
            properties={
                "file_path": file_path,
            },
            required=["file_path"]
        )

        # 读取的行的范围,指的是本次读取的行数范围，默认为0-400，通过修改这俩个参数来实现其他区域的读取
        params.properties["start_line"] = Property(
            type="integer",
            description="要读取的文件的起始行号，默认为0，表示从文件开头开始读取",
        )
        params.properties["end_line"] = Property(
            type="integer",
            description="要读取的文件的结束行号，默认为400，表示读取到文件的第400行，实际读取时会取start_line和end_line的交集，并且end_line不会超过文件的总行数",
        )

        return ToolDesc(
            name="read_file",
            description=f"一个安全的读取文件的工具，限制只能读取特定目录下的文件，并且在读取前进行路径验证，防止路径遍历攻击。只能读取工具初始化时指定的base_dir目录下的文件。",
            parameters=params,
        )
    
    def valid_paras(self, params: Dict[str, str]) -> "ValidationResult":
        # 解析并规范参数
        file_path = params.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            return ValidationResult(valid=False, message="missing 'file_path' parameter")

        abs_path = os.path.abspath(os.path.join(self.base_dir, file_path))
        # 验证是否存在
        if not os.path.isfile(abs_path):
            self.logger.error(f"File not found: {abs_path}")
            return ValidationResult(valid=False, message=f"file not found: {file_path}")
        # 验证路径是否在base_dir下，防止路径遍历
        base_dir_norm = os.path.abspath(self.base_dir)
        if not abs_path.startswith(base_dir_norm + os.sep) and abs_path != base_dir_norm:
            self.logger.error(f"Path traversal attempt detected: {abs_path}")
            return ValidationResult(valid=False, message="path traversal detected")

        # 解析行号
        try:
            start_line = int(params.get("start_line", 0))
        except Exception:
            start_line = 0
        try:
            end_line = int(params.get("end_line", self.max_lines))
        except Exception:
            end_line = self.max_lines

        # 约束范围
        if start_line < 0:
            start_line = 0
        if end_line < start_line:
            end_line = start_line + self.max_lines
        # 限制单次读取行数以防资源滥用
        if end_line - start_line > self.max_lines:
            end_line = start_line + self.max_lines

        return ValidationResult(valid=True, parsed_params={"abs_path": abs_path, "start_line": start_line, "end_line": end_line})

    def _execute_impl(self, params: Dict[str, str]) -> ToolResponse:
        abs_path = params.get("abs_path") or os.path.abspath(os.path.join(self.base_dir, params.get("file_path", "")))
        start_line = int(params.get("start_line", 0))
        end_line = int(params.get("end_line", self.max_lines))

        # 安全保护，再次检查文件存在
        if not os.path.isfile(abs_path):
            return ToolResponse(tool_name=self.name, status="error", output=f"file not found: {abs_path}")

        try:
            # 以utf-8读取文本文件
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))

        total = len(lines)
        # 边界约束
        start = max(0, start_line)
        end = min(total, end_line)
        selected = lines[start:end]

        # 限制输出大小（按字符数），以避免过大
        content = "".join(selected)
        max_chars = 1000000  # 1MB
        if len(content) > max_chars:
            content = content[:max_chars]

        rel_path = os.path.relpath(abs_path, self.base_dir)
        details = {"path": rel_path, "start_line": start, "end_line": end, "total_lines": total}
        return ToolResponse(tool_name=self.name, status="success", output=content, details=details)
        