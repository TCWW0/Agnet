from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional
from datetime import datetime, timezone


@dataclass
class ToolResult:
    version: str = "1.0"
    tool_name: str = ""
    request_id: Optional[str] = None
    status: str = "ok"  # ok | error | partial
    output: Any = None
    original_input: Optional[str] = None
    nl: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        d = dict(data)
        # Ensure timestamp is a string; fallback to now if missing or falsy
        ts = d.get("timestamp")
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        else:
            ts = str(ts)
        return cls(
            version=d.get("version", "1.0"),
            tool_name=d.get("tool_name", ""),
            request_id=d.get("request_id"),
            status=d.get("status", "ok"),
            output=d.get("output"),
            original_input=d.get("original_input"),
            nl=d.get("nl"),
            error_code=d.get("error_code"),
            error_message=d.get("error_message"),
            timestamp=ts,
            duration_ms=d.get("duration_ms"),
            meta=d.get("meta"),
        )


def normalize_tool_result(raw: Any, tool_name: Optional[str] = None, request_id: Optional[str] = None, original_input: Optional[str] = None) -> ToolResult:
    """Normalize various legacy/raw tool outputs into a ToolResult instance.

    - If `raw` is already a ToolResult, return it.
    - If `raw` is a dict that contains a `version` key, try to parse it.
    - Otherwise wrap `raw` as the `output` and mark as `ok`.
    """
    if isinstance(raw, ToolResult):
        return raw

    if isinstance(raw, dict) and raw.get("version"):
        try:
            return ToolResult.from_dict(raw)
        except Exception:
            # fallthrough to wrapping
            pass

    # Primitive or arbitrary value -> wrap as output
    tr = ToolResult(
        tool_name=tool_name or "",
        request_id=request_id,
        status="ok",
        output=raw,
        original_input=original_input,
    )
    # generate a short natural-language summary if possible
    try:
        if tr.status == "ok":
            tr.nl = str(tr.output)
        else:
            tr.nl = tr.error_message or str(tr.error_code) if tr.error_code is not None else None
    except Exception:
        tr.nl = None
    return tr
