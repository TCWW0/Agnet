from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator, Literal, TypedDict, cast


StreamEventType = Literal["chunk", "paragraph", "meta", "done", "error", "heartbeat"]


class StreamFrame(TypedDict, total=False):
    protocolVersion: str
    type: StreamEventType
    messageId: str
    seq: int
    paragraphId: str
    role: str
    format: Literal["markdown", "text"]
    text: str
    timestamp: str
    meta: dict[str, Any]


class StreamFramer:
    """Convert raw token/text chunks into protocol V1 structured frames."""

    PROTOCOL_VERSION = "1.0"

    def __init__(
        self,
        message_id: str,
        paragraph_marker: str = "<|PARA|>",
        role: str = "assistant",
        output_format: Literal["markdown", "text"] = "markdown",
    ) -> None:
        if not paragraph_marker:
            raise ValueError("paragraph_marker must not be empty")

        self._message_id = message_id
        self._paragraph_marker = paragraph_marker
        self._role = role
        self._output_format = output_format

        self._seq = 0
        self._paragraph_index = 0

        self._scan_buffer = ""
        self._paragraph_buffer = ""

    def push_text(self, text: str) -> Iterator[StreamFrame]:
        """Ingest streaming text and emit chunk/paragraph frames incrementally."""
        if not text:
            return

        self._scan_buffer += text

        while self._scan_buffer:
            marker_index = self._scan_buffer.find(self._paragraph_marker)
            if marker_index >= 0:
                before_marker = self._scan_buffer[:marker_index]
                if before_marker:
                    yield self._emit_chunk(before_marker)
                yield from self._flush_paragraph()
                self._scan_buffer = self._scan_buffer[marker_index + len(self._paragraph_marker) :]
                continue

            hold_len = self._longest_marker_prefix_len(self._scan_buffer)
            if hold_len > 0:
                safe_text = self._scan_buffer[:-hold_len]
                self._scan_buffer = self._scan_buffer[-hold_len:]
            else:
                safe_text = self._scan_buffer
                self._scan_buffer = ""

            if safe_text:
                yield self._emit_chunk(safe_text)

            break

    def error(self, message: str) -> StreamFrame:
        return self._build_frame("error", meta={"error": message})

    def finalize(self) -> Iterator[StreamFrame]:
        """Flush remaining text and emit final paragraph/done frames."""
        if self._scan_buffer:
            trailing_text = self._scan_buffer
            self._scan_buffer = ""
            if trailing_text:
                yield self._emit_chunk(trailing_text)

        yield from self._flush_paragraph()
        yield self._build_frame("done", meta={"paragraphCount": self._paragraph_index})

    def _emit_chunk(self, text: str) -> StreamFrame:
        self._paragraph_buffer += text
        return self._build_frame("chunk", text=text)

    def _flush_paragraph(self) -> Iterator[StreamFrame]:
        if not self._paragraph_buffer:
            return

        self._paragraph_index += 1
        paragraph_id = f"p{self._paragraph_index}"
        paragraph_text = self._paragraph_buffer
        self._paragraph_buffer = ""

        yield self._build_frame("paragraph", paragraph_id=paragraph_id, text=paragraph_text)

    def _build_frame(
        self,
        frame_type: StreamEventType,
        *,
        text: str | None = None,
        paragraph_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> StreamFrame:
        self._seq += 1
        frame: StreamFrame = {
            "protocolVersion": self.PROTOCOL_VERSION,
            "type": frame_type,
            "messageId": self._message_id,
            "seq": self._seq,
            "role": self._role,
            "timestamp": _utc_now_iso(),
        }

        if text is not None:
            frame["text"] = text
            # cast to the Literal union so type-checkers accept assignment
            frame["format"] = cast(Literal["markdown", "text"], self._output_format)
        if paragraph_id is not None:
            frame["paragraphId"] = paragraph_id
        if meta is not None:
            frame["meta"] = meta
        return frame

    def _longest_marker_prefix_len(self, value: str) -> int:
        max_len = min(len(value), len(self._paragraph_marker) - 1)
        for size in range(max_len, 0, -1):
            if value.endswith(self._paragraph_marker[:size]):
                return size
        return 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")