"""工具协议兼容层。

`ToolResult` 已迁移到 `frame.core.message`，本模块保留：
- `ToolResult` 重导出（兼容旧引用）
- `normalize_tool_result` 工具函数
"""

from typing import Any, Optional

from frame.core.message import ToolResult


def normalize_tool_result(
    raw: Any,
    tool_name: Optional[str] = None,
    request_id: Optional[str] = None,
    original_input: Any = None,
) -> ToolResult:
    """将各种原始输出归一化为 `ToolResult`。

    - 若 `raw` 已是 `ToolResult`，直接返回
    - 若 `raw` 是包含 `version` 的 dict，尝试按 `ToolResult` 反序列化
    - 否则将 `raw` 包装为 `status=ok` 的 `output`
    """
    if isinstance(raw, ToolResult):
        return raw

    if isinstance(raw, dict) and raw.get("version"):
        try:
            return ToolResult.from_dict(raw)
        except Exception:
            pass

    tr = ToolResult(
        tool_name=tool_name or "",
        request_id=request_id,
        status="ok",
        output=raw,
        original_input=original_input,
    )
    try:
        if tr.status == "ok":
            tr.nl = str(tr.output)
        else:
            tr.nl = tr.error_message or (str(tr.error_code) if tr.error_code is not None else None)
    except Exception:
        tr.nl = None
    return tr


__all__ = ["ToolResult", "normalize_tool_result"]
